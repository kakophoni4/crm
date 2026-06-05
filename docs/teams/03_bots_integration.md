# Backend Bots Integration

> Команда отвечает за **интеграцию CRM с готовыми ботами** через HTTP-контракт.
> Боты — внешние сервисы; CRM с Telegram API напрямую **не работает**.
> Финальный контракт для разработчиков ботов: [`BOTS_INTEGRATION.md`](../BOTS_INTEGRATION.md).

---

## 1. Зона ответственности

- Сущность `bots` (CRUD, генерация secrets, `outbound_url`).
- HTTP endpoint **входящих** событий от ботов: `POST /api/v1/bot-events` (HMAC-валидация, идемпотентность).
- Маппинг события → доменный вызов `chats_service.ingest_incoming_message(...)`.
- ARQ job отправки **исходящих** команд ботам (HTTP к `bot.outbound_url`, HMAC-подпись, retry).
- Скачивание медиафайлов по URL из бота → MinIO (через Files team).
- Health-check ботов (опрос `bot.outbound_url_base/health` каждые 60 сек).
- Поддержание контракта `BOTS_INTEGRATION.md` в актуальном состоянии.
- Метрики per-bot: latency, success rate, queue depth.

---

## 2. Стек и зависимости

```
fastapi
httpx (async client с pool'ом)
arq
redis
sqlalchemy[asyncio]
hmac/hashlib (стандартная библиотека)
pydantic v2
```

Зависимости от других команд:
- **Backend Core:** auth, scope, EventBus, settings, db, audit.
- **Backend Chats:** `chats_service.ingest_incoming_message(...)`, `chats_service.mark_outbound_sent(internal_id, external_id, telegram_message_id)`, `chats_service.mark_outbound_failed(internal_id, code, reason)`.
- **Backend Contacts:** `contacts_service.get_or_create_by_telegram(...)`, `files_service.upload_from_url(...)`.
- **DevOps:** публичный домен CRM (`PUBLIC_BASE_URL`), сетевая достижимость до `bot.outbound_url`.

---

## 3. Backlog

### Epic 1. Управление ботами
- [ ] Миграция `bots`:
  ```
  id, code UNIQUE, name, purpose,
  owner_type ('department'|'group'), owner_id,
  outbound_url, health_url (nullable, default = derived from outbound_url),
  inbound_secret (encrypted), outbound_secret (encrypted),
  ip_allowlist (cidr[] nullable),
  is_active BOOL,
  created_at, updated_at, created_by
  ```
- [ ] Шифрование секретов через `pgcrypto` + ключ в env.
- [ ] CRUD `bots_service`.
- [ ] `POST /api/v1/bots` (admin):
  1. Валидация полей.
  2. Генерация `inbound_secret` и `outbound_secret` (по 32 байта, base64url).
  3. Сохранение, **возврат секретов один раз** в ответе (потом не показываются).
  4. Outbox-event `bot.added`.
- [ ] `PATCH /api/v1/bots/{id}` (admin) — `name`, `purpose`, `owner_*`, `outbound_url`, `is_active`, `ip_allowlist`.
- [ ] `POST /api/v1/bots/{id}/rotate-secret` (admin) — генерация новых секретов с ответом одноразово.
- [ ] `DELETE /api/v1/bots/{id}` (admin) — soft delete.
- [ ] **DoD:** админ создаёт бота через UI, получает оба секрета один раз.

### Epic 2. Входящие события (HTTP endpoint)
- [ ] FastAPI endpoint `POST /api/v1/bot-events`.
- [ ] Middleware `verify_bot_signature`:
  1. Извлечь `X-Bot-Code`, найти `bot` (active).
  2. Проверить `X-Bot-Timestamp` (диапазон ±60 сек).
  3. Проверить IP allowlist (если задан).
  4. Вычислить canonical = `POST\n/api/v1/bot-events\n<ts>\nsha256(body)` и сравнить HMAC с `inbound_secret`. Использовать `hmac.compare_digest`.
- [ ] Идемпотентность: таблица `bot_events_inbox(event_id PK, bot_id, received_at)` с TTL 24 часа (или партиционирование по дням + чистка ARQ-периодикой). Перед обработкой — INSERT с ON CONFLICT DO NOTHING; если был конфликт → ответ `{"status":"duplicate"}`.
- [ ] Pydantic-схемы для каждого `event` типа.
- [ ] Маршрутизация:
  - `message.received` → `_handle_message_received(...)`;
  - `message.edited` → `_handle_message_edited(...)`;
  - `message.delivered` → `chats_service.mark_outbound_delivered(internal_id, ...)`;
  - `message.read` → `chats_service.mark_outbound_read(internal_id, ...)`;
  - `contact.updated` → `contacts_service.update_from_external(...)`.
- [ ] `_handle_message_received`:
  1. `contacts_service.get_or_create_by_telegram(...)`.
  2. `chats_service.ingest_incoming_message(bot_id, contact_id, external_id=msg.external_id, body, attachments_pending=...)`.
  3. Запустить ARQ job `bots.download_attachment(message_id, attachment_idx)` для каждого attachment с URL.
- [ ] **DoD:** интеграционный тест: подписанный POST → запись в БД → realtime-событие.

### Epic 3. Скачивание медиа
- [ ] ARQ job `bots.download_attachment(message_id, attachment_idx)`:
  1. Загрузить message + attachment metadata.
  2. Стрим `httpx.stream('GET', url)` → `files_service.upload_stream(...)`.
  3. Обновить `message.attachments[idx]` с реальным `file_id`.
  4. Outbox-event `chat.message.attachment_ready`.
- [ ] Retry: 3 попытки с backoff `5s, 30s, 2m`.
- [ ] При финальном fail — `attachments[idx].failed=true`, событие `chat.message.attachment_failed`.
- [ ] Лимит размера и mime-allowlist (env).
- [ ] **DoD:** входящее фото 5 MB сохраняется в MinIO в течение ≤ 10 секунд.

### Epic 4. Исходящие команды
- [ ] ARQ job `bots.send(message_id)` — вызывается из Backend Chats после insert исходящего message:
  1. Загрузить message + chat + bot.
  2. Сформировать payload (см. `BOTS_INTEGRATION.md` §5.3.1).
  3. Для каждого attachment — сгенерировать presigned URL у `files_service` (TTL 30 мин).
  4. Подписать HMAC с `outbound_secret`.
  5. `httpx.post(bot.outbound_url, json=..., headers=..., timeout=30)`.
  6. Парсить ответ:
     - `status=ok` → `chats_service.mark_outbound_sent(internal_id=message.id, external_id, telegram_message_id)`;
     - `status=error, retryable=true` → исключение, ARQ ретраит;
     - `status=error, retryable=false` → `chats_service.mark_outbound_failed(...)` с `error_code`.
- [ ] Идемпотентность: в БД таблица `bot_outbound_log(id, bot_id, request_id, message_id UNIQUE, status, attempts, last_error, ...)` — повторный job на тот же message не отправляет, если `status='sent'`.
- [ ] Retry: 4 попытки backoff `30s, 2m, 10m, 30m`.
- [ ] 429 c `Retry-After` — уважаем.
- [ ] **DoD:** оператор отправил → в течение 5 секунд бот получил, ответил, статус в UI обновился.

### Epic 5. Health-check ботов
- [ ] ARQ периодический job `bots.healthcheck_all` каждые 60 секунд.
- [ ] Для каждого `is_active=true` — `httpx.get(bot.health_url, timeout=5)`.
- [ ] Результат → метрика `bot_alive{bot_code=...}` (gauge 0/1) + поле `last_seen_at` в `bots`.
- [ ] При флапах больше N — алёрт.
- [ ] **DoD:** Grafana дашборд показывает живых/мёртвых ботов.

### Epic 6. Безопасность и аудит
- [ ] Все запросы к `/bot-events` логируются с `bot_code`, `event_id`, `event_type`. **Без** payload (только размер).
- [ ] Ошибки HMAC → audit-event `bot.signature_invalid` + Sentry-алёрт (потенциальная атака).
- [ ] Ротация секретов через UI: новый секрет действует сразу, старый — grace period 5 минут (хранится `previous_inbound_secret` с `valid_until`).
- [ ] CLI команда `manage.py bots dump_secrets <code>` — только для DevOps в чрезвычайных случаях, с логированием.

### Epic 7. Метрики и наблюдаемость
- [ ] Метрики per-bot:
  - `bot_inbound_events_total{bot_code, event_type, status}`;
  - `bot_outbound_requests_total{bot_code, status}`;
  - `bot_outbound_latency_seconds{bot_code}`;
  - `bot_signature_failures_total{bot_code}`;
  - `bot_alive{bot_code}`;
  - `bot_outbound_queue_depth{bot_code}`.
- [ ] Дашборд Grafana «Bots overview».
- [ ] Алёрты: `bot_alive=0 за 5 мин`, `signature_failures > 5/мин`, `outbound_latency_p95 > 10 сек`.

---

## 4. Точки интеграции

### Что Bots Integration отдаёт
- Endpoint `POST /api/v1/bot-events`.
- API `/api/v1/bots/*`.
- ARQ-job `bots.send(message_id)` — вызывается командой Chats.
- ARQ-job `bots.download_attachment(...)` — вызывается изнутри.
- События `bot.added/removed/updated/health_changed`.
- Контракт `BOTS_INTEGRATION.md` поддерживается этой командой.

### Что Bots Integration берёт
- От Core: auth, scope, settings, EventBus, db, audit.
- От Chats: `chats_service.ingest_incoming_message`, `mark_outbound_*`.
- От Contacts: `contacts_service.get_or_create_by_telegram`, `files_service.upload_from_url`/`upload_stream`/presigned URL.

---

## 5. Definition of Done команды

- ✅ Контракт `BOTS_INTEGRATION.md` финализирован и согласован с разработчиками ботов.
- ✅ Mock-бот (отдельный тестовый сервис) проходит полный цикл: receive → ingest → outbound → ack.
- ✅ Подделка HMAC отбрасывается с 401, кейс покрыт тестом.
- ✅ Идемпотентность входящих и исходящих подтверждена тестами.
- ✅ Скачивание медиа работает + dead-letter при недоступности URL.
- ✅ Health-check работает, метрики и алёрты заведены.
- ✅ Ротация секретов проходит без даунтайма.

---

## 6. Слабые места команды

1. **Утечка `inbound_secret`** = атакующий шлёт фейковые входящие. Митигация: ротация при подозрении, IP allowlist, мониторинг частоты `signature_failures`.
2. **`outbound_url` бота недоступен** → исходящие копятся в очереди, операторы видят `queued`. Алёрт обязателен; в UI показать «бот не отвечает».
3. **`url_expires_at` у входящих файлов** меньше реального времени попытки скачать → файл потерян. Нужно скачать ASAP после ingest, не откладывать. Reasonable timeout у URL — минимум 1 час, лучше 24.
4. **Идемпотентность outbound полагается на бот** — если бот не реализовал, повторный запрос пошлёт дубль клиенту. Покрыть в `BOTS_INTEGRATION.md` как обязательное требование, контролировать через тесты приёмки.
5. **Несколько каналов под одним `bot_code`** — если бот объединяет TG+WA, `telegram_user_id` коллизия не исключена (TG и WA имеют разные ID-пространства). Решение в v1: один бот = один канал; в v1.1 ввести поле `channel`.
6. **HMAC с `compare_digest`** — обязательно. Простой `==` уязвим к timing-атакам. Зафиксировать ревью-чеклист.
7. **Объём `bot_events_inbox`** растёт. Чистка по TTL обязательна, иначе через год — миллиарды строк.
