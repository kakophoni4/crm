# Архитектура

> Документ описывает **как** реализуется то, что в `TECH_SPEC.md`.

---

## 1. Принципы

1. **Modular monolith.** Один Python-процесс с логически разделёнными модулями. Между модулями — только сервисный слой и события, никаких прямых обращений к чужим репозиториям.
2. **Async-first.** FastAPI + SQLAlchemy 2 async + httpx async + Redis async-клиент. Никаких блокирующих вызовов в hot-path.
3. **Strict scoping.** Все запросы к БД проходят через `scope_resolver`, который возвращает фильтр по видимости актора. Это исключает «забыл проверить право».
4. **Events first.** Любое значимое действие публикует событие. Это даёт «бесплатный» аудит, intereoperability и лёгкий выезд в микросервисы.
5. **Один источник правды для прав.** Пакет `core/auth/` владеет всеми разрешениями; остальные модули его дёргают.

---

## 2. Контейнерная диаграмма (C4 — Containers)

```
   Клиент в Telegram                  Клиент в Telegram
        │                                   │
        ▼                                   ▼
  ┌────────────┐                      ┌────────────┐
  │   Bot A    │                      │   Bot B    │   ... (внешние сервисы,
  │ (Telegram) │                      │ (Telegram) │       не наша зона)
  └─────┬──────┘                      └─────┬──────┘
        │   HTTP+HMAC                       │
        │   (POST /api/v1/bot-events)       │
        │                                   │
        └───────────────┬───────────────────┘
                        │
                        ▼
┌────────────┐    ┌─────────────────────────┐
│  Browser   │    │   Reverse proxy:        │
│  Vue SPA   │◀──▶│   Traefik (TLS)         │
└────────────┘    └────────┬─────────────────┘
       ▲ WS/HTTPS          │
       │                   ▼
       │        ┌─────────────────────────┐         HTTP+HMAC
       │        │    FastAPI (app)        │  outbound  to bot.outbound_url
       │        │  ┌──────┬──────┬──────┐ │ ──────────────▶  Bot A/B/...
       └────────┤  │ HTTP │  WS  │ Bot  │ │                 (наш исходящий)
                │  │ API  │ hub  │ ingst│ │
                │  └──┬───┴──┬───┴──┬───┘ │
                │     │      │      │     │
                │  ┌──▼──────▼──────▼──┐  │
                │  │   Modules         │  │
                │  │  core/auth        │  │
                │  │  modules/chats    │  │
                │  │  modules/contacts │  │
                │  │  modules/bots     │  │  ← интеграционный модуль
                │  └──┬─────┬──────┬───┘  │
                └────┼─────┼──────┼──────-┘
                     │     │      │
        ┌────────────▼┐ ┌──▼───┐ ┌▼─────────┐
        │ PostgreSQL  │ │Redis │ │ MinIO    │
        │ 16          │ │  7   │ │ (S3)     │
        └─────────────┘ └──────┘ └──────────┘
                            ▲
                            │ ARQ jobs
                            │
              ┌─────────────┴───────────────┐
              │  Worker (ARQ)                │
              │  - bots.send                 │
              │  - bots.download_attachment  │
              │  - bots.healthcheck_all      │
              │  - process_audit / outbox    │
              │  - assignment                │
              │  - cleanup_jobs              │
              └──────────────────────────────┘
```

---

## 3. Логическое разделение приложения

```
crm/
├── app/
│   ├── core/
│   │   ├── auth/                # JWT, refresh-токены, RBAC, scope-резолвер
│   │   ├── users/               # пользователи, роли
│   │   ├── departments/         # отделы
│   │   ├── groups/              # группы
│   │   ├── audit/               # общий audit_log
│   │   └── module_registry/     # реестр внутренних модулей
│   ├── modules/
│   │   ├── chats/               # chats, messages, transfers, takeover
│   │   ├── contacts/            # контакты, custom fields, history
│   │   ├── statuses/            # справочник статусов
│   │   └── bots/                # внешние боты: ingest /bot-events, outbound dispatch (HTTP+HMAC)
│   ├── realtime/                # WebSocket hub, Redis Pub/Sub bridge
│   ├── workers/                 # ARQ tasks
│   ├── shared/                  # db, redis, settings, exceptions, logging
│   └── main.py                  # FastAPI app factory
├── alembic/
├── tests/
├── docker/
│   ├── docker-compose.dev.yaml  # только зависимости
│   ├── docker-compose.yaml      # полный стек (для прод/staging)
│   └── Dockerfile
├── frontend/                    # отдельный Vue 3 проект
└── docs/
```

---

## 4. Realtime: как работает WebSocket

```
Browser A           Browser B           Browser C
   │                    │                    │
   │ WS connect         │ WS connect         │ WS connect
   ▼                    ▼                    ▼
        ┌─────────────────────────────────────┐
        │     FastAPI WS Hub (per pod)        │
        │  Локальный реестр: user_id → conn[] │
        └──────────────┬──────────────────────┘
                       │ subscribe / publish
                       ▼
              ┌────────────────────┐
              │   Redis Pub/Sub    │
              │  channel: user.{id}│
              │  channel: chat.{id}│
              └────────────────────┘
                       ▲
                       │ publish from any service
                       │
        ┌──────────────┴──────────────────┐
        │ Bot ingest handler              │
        │ Chats service (after .send())   │
        │ Transfers service (state chg)   │
        └─────────────────────────────────┘
```

- На один Pod (один FastAPI-процесс) — локальный hub, который держит активные WS.
- Любой код, который хочет «доставить сообщение пользователю», публикует в Redis Pub/Sub в канал `user.{user_id}` или `chat.{chat_id}`.
- Локальный hub слушает свои каналы (subscribe по факту наличия активной сессии этого юзера/чата) и пушит в WS.
- Это даёт **горизонтальное масштабирование без липких сессий**: пользователь может быть подключен к любому Pod'у, событие найдёт его.

### Аутентификация WS
- В URL передаётся короткоживущий ticket-токен, выписанный по access-токену.
- При connect Hub валидирует ticket, привязывает соединение к user_id.
- Tickets живут 60 секунд, одноразовые (хранятся в Redis).

---

## 5. Боты (внешние) — поток

> CRM **не работает** с Telegram API напрямую. Боты — внешние сервисы. Контракт интеграции: [`BOTS_INTEGRATION.md`](BOTS_INTEGRATION.md).

### 5.1 Входящий

```
Bot (внешний сервис)
     │ POST /api/v1/bot-events
     │   X-Bot-Code, X-Bot-Timestamp, X-Bot-Event-Id, X-Bot-Signature
     ▼
[Bot ingest endpoint]
  ├─ найти bot по X-Bot-Code, проверить is_active
  ├─ проверить timestamp ±60 сек, IP allowlist
  ├─ проверить HMAC через compare_digest
  ├─ INSERT bot_events_inbox (event_id, bot_id) ON CONFLICT DO NOTHING
  │     └─ если конфликт → 200 {"status":"duplicate"}
  ├─ маршрутизация по event-type
  ▼
[handler: message.received]
  ├─ contacts_service.get_or_create_by_telegram(...)
  ├─ chats_service.ingest_incoming_message(...)
  │   ├─ найти/создать Chat (contact, bot); group_id ← bot.owner
  │   ├─ ownership_service.ensure_assignment(contact, group_id)  # round-robin → contact_group_assignments
  │   ├─ notify owner (WS); start pending_inbound_at timer (N min)
  │   ├─ записать Message direction='in'
  │   └─ event: chat.message.received → WS (owner first)
  └─ enqueue ARQ: bots.download_attachment(message_id, idx) для каждого вложения
        └─ httpx.stream(url) → MinIO → событие chat.message.attachment_ready
```

### 5.2 Исходящий

```
[Operator UI] POST /api/v1/chats/{id}/messages
     │
     ▼
[Chats API]
  ├─ проверить: user ∈ chat.assigned_group_id; takeover rules
  ├─ snapshot owner ← contact_group_assignments(contact, group)
  ├─ INSERT message_reply_audit(owner, author, is_on_behalf)
  ├─ если author==owner → last_owner_response_at; clear pending_inbound_at
  ├─ если author!=owner → is_on_behalf; optional notify owner
  ├─ записать Message direction='out', status='queued'
  ├─ INSERT bot_outbound_log (message_id, request_id=ULID, status='queued')
  ├─ enqueue ARQ: bots.send(message_id)
  └─ outbox-event: chat.message.created → UI оператора (queued)
                 │
                 ▼
[Worker: bots.send]
  ├─ загрузить message + chat + bot + outbound_log (проверка идемпотентности)
  ├─ для каждого attachment → presigned URL у MinIO (TTL 30 мин)
  ├─ собрать payload (см. BOTS_INTEGRATION.md §5.3)
  ├─ HMAC-подпись с outbound_secret
  ├─ httpx.post(bot.outbound_url, json=..., timeout=30)
  ├─ парсинг ответа:
  │     ├─ ok → mark_outbound_sent(internal_id, external_id, telegram_message_id)
  │     ├─ error retryable=true → raise → ARQ retry (30s, 2m, 10m, 30m)
  │     └─ error retryable=false → mark_outbound_failed(error_code, message)
  └─ outbox-event: chat.message.status_changed → UI обновляет тик
```

### 5.3 Владение карточкой и эскалация
> Канон: [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md).

**`contacts/ownership.py`**
1. При первом inbound в группе G: `contact_group_assignments(contact, G).owner_user_id` ← round-robin (available users в G).
2. Уведомление: **сначала owner**; `pending_inbound_at = now()`.
3. Worker `escalation.scan` каждые 30s:
   - если `now - pending_inbound_at > N` и нет ответа owner → `escalated_to_group_at`, WS **всей группе**;
   - если контакт **новый** в группе и стратегия `first_responder` / `random_available` → смена `owner_user_id`.
4. **Transfer** меняет owner только для `(contact_id, group_id)`.

**Писать в чат** может любой user группы; права не привязаны к `chats.last_handled_by_user_id`.

### 5.4 Health-check ботов
- ARQ периодика `bots.healthcheck_all` каждые 60 секунд.
- Для каждого активного бота — `httpx.get(bot.health_url, timeout=5)`.
- Метрика `bot_alive{bot_code}` + `bots.last_seen_at`.
- При флаппинге — алёрт.

---

## 6. RBAC и Scope

### 6.1 Декоратор уровня роутера
```python
@router.get("/chats")
async def list_chats(
    actor: User = Depends(require_permission("chats.read")),
    db: AsyncSession = Depends(get_db),
):
    scope = await build_chat_scope(actor)
    return await chats_service.list(db, scope)
```

### 6.2 Scope object
`build_chat_scope(actor)` возвращает объект:
```python
ChatScope(
    user_ids: list[int] | None,    # NULL = все
    department_ids: list[int] | None,
    own_only: bool,
)
```
Который репозиторий применяет в `WHERE`. Никакой бизнес-логики «по ролям» в репозиториях — только применение scope.

### 6.3 Где живёт правда о правах
- `core/auth/permissions.py` — реестр всех прав в виде констант.
- `core/auth/rbac.py` — отображение роль → набор прав.
- `core/auth/scope.py` — функции вида `build_*_scope(actor)`.
- Изменение матрицы прав = PR в эти файлы + обновление `RBAC_MATRIX.md`.

---

## 7. Хранение секретов

| Секрет | Где |
|---|---|
| Пароли пользователей | `bcrypt` в БД |
| JWT signing key | env / Vault, ротация раз в год |
| Refresh tokens | PostgreSQL `refresh_tokens`: хранится SHA-256 хэш токена, `jti`, срок жизни и `revoked_at`; logout/force-logout выставляют отзыв |
| Bot inbound/outbound HMAC secrets | БД с шифрованием (`pgcrypto` + ключ в env), выдаются через UI один раз при создании/ротации |
| Telegram user_id (клиента) | БД plain. Маскируется в API/логах. (При требовании — `pgcrypto`.) |

---

## 8. Логирование и наблюдаемость

- **Логи:** структурный JSON через `structlog`. Поля: `timestamp, level, request_id, user_id, action, ...`. PII (telegram_user_id, телефон) — в фильтре маскирования.
- **Метрики:** Prometheus `/metrics`, экспортируем: HTTP RPS/latency, active WS connections, Redis pub/sub throughput, bot outbound rate / latency / errors per bot, bot ingest rate, queue depth.
- **Tracing:** OpenTelemetry → Tempo/Jaeger (опционально на старте).
- **Errors:** Sentry, отдельный DSN для backend и frontend.

---

## 9. Развёртывание

### Dev
- `docker-compose.dev.yaml` поднимает только: postgres, redis, minio, adminer, mailhog. Приложение запускается из IDE через `uvicorn --reload`.
- Публичный URL для приёма `/api/v1/bot-events` от ботов — через `cloudflared` или `ngrok` туннель к локальному порту, либо постоянный sub-домен в DNS на staging.

### Staging / Prod
- Полный стек в Docker Compose (или Kubernetes на следующих этапах).
- Reverse proxy: Traefik с автоматическим Let's Encrypt.
- Бэкапы Postgres через `pg_dump` + `restic` в S3.
- MinIO в режиме single-node, бэкап через `mc mirror`.

---

## 10. Точки расширения (когда выносить в отдельные сервисы)

| Сценарий | Что вынести |
|---|---|
| WS-коннектов > 5k одновременно | Centrifugo как WS-gateway, FastAPI публикует ему |
| Bot ingest RPS высокий (100+ботов с активным трафиком) | Отдельный bot-gateway (Go или Python) перед основным API |
| Аналитика/отчёты тяжёлые | Отдельный read-only сервис на read-replica Postgres |
| Большой объём аудита | Партиционирование `audit_log` + архив в S3 (Parquet) |
| Поиск по сообщениям растёт | Meilisearch / OpenSearch вместо Postgres FTS |

### Поиск (фаза 5)

- **`GET /api/v1/search`** — единая точка для UI global search: контакты (`ilike` по `full_name`, `telegram_username`), сообщения (Postgres FTS, миграция `0016`), чаты (`ilike` по `last_message_preview` + имя контакта).
- RBAC: отдельный scope на каждый тип (контакты — `visible_user_ids`; чаты/сообщения — `chat_visibility_clause` / FTS scope как в `/chats/search`).
- Rate-limit: Redis counter `search:rate:{user_id}` (TTL 60s), fallback in-memory; 60 req/min per user (`SEARCH_RATE_LIMIT_PER_MINUTE`).
- Специализированный `GET /chats/search` сохраняется для глубокого FTS с `scope=mine|group|...`.

---

## 11. Слабые места архитектуры

1. **Один процесс — одна точка отказа.** В монолите рестарт уронит и API, и WS, и приём вебхуков. Митигируется N репликами за балансировщиком.
2. **Подписки Redis Pub/Sub не персистентны.** Если Pod упал во время отправки события — оно потеряно. Для критичных событий (например, доставка сообщения) — дублируем как ARQ job или в `outbox`-паттерн.
3. **Outbound HTTP к ботам** — синхронный HTTP с retry. Если несколько ботов разом «упали», очередь outbound может разрастись и стать узким местом. Митигация: bulkhead-isolation per bot (отдельная семафор-квота), алёрты на queue depth per bot.
4. **Round-robin assignment без учёта компетенций** — простой, но неоптимальный. На втором этапе добавить теги/навыки операторов и матчинг.
5. **WebSocket за Traefik** — нужна правильная настройка таймаутов и keepalive, иначе будут «молчаливые» дисконнекты. Добавить heartbeat.
6. **Refresh-токены завязаны на Postgres.** При недоступности БД refresh/logout/force-logout деградируют вместе с основным API; Redis всё ещё нужен для WS tickets, realtime Pub/Sub, rate limits, очередей и кэшей.
