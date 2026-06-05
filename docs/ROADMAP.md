# Дорожная карта (Roadmap)

> Сроки указаны в **«разработчико-неделях»** для команды из 4–6 человек (см. `teams/00_overview.md`). На одного синьора с full-time умножай ×2.5–×3. На команду из джунов — ×1.5.

---

## Фаза 0. Подготовка (1 неделя)

**Цель:** все разработчики могут запустить проект локально и работать параллельно.

| Задача | Кто |
|---|---|
| Репозиторий, ветки, правила PR | DevOps + Tech Lead |
| `docker-compose.dev.yaml` (postgres+redis+minio) | DevOps |
| Скелет FastAPI: app factory, settings, db, alembic, structlog, pytest | Backend Core |
| Скелет Vue 3: vite, eslint, prettier, pinia, naive-ui, axios, ws-клиент | Frontend |
| CI: lint+тесты на push, образы на main | DevOps |
| Sentry DSN, env шаблоны, README setup | DevOps |

**Definition of Done фазы:** новый разработчик клонит репу и через ≤30 минут видит «Hello World» от FastAPI и фронта.

---

## Фаза 1. Ядро и аутентификация (2 недели)

**Цель:** есть юзеры, отделы, группы, роли, login и матрица прав.

| Задача | Кто |
|---|---|
| Миграции: users, departments, groups, audit_log | Backend Core |
| RBAC: permissions, role mapping, scope-резолвер | Backend Core |
| Auth: login, refresh, logout, ws-ticket, force-logout | Backend Core |
| API: users CRUD, departments CRUD, groups CRUD | Backend Core |
| Outbox + EventBus + audit-handler | Backend Core |
| Тесты: матрица RBAC по эндпоинтам | QA + Backend Core |
| Frontend: страницы Login, MyProfile, Admin/Departments, Admin/Groups, Admin/Users | Frontend |
| Frontend: глобальный store auth + permissions, гарды роутера | Frontend |

**Demo:** админ создаёт отдел → senior'а → senior создаёт группу → senior создаёт юзера → юзер логинится.

---

## Фаза 2. Контакты и статусы (1.5 недели)

**Цель:** карточка клиента и справочники готовы до того, как начнём чат.

| Задача | Кто |
|---|---|
| Миграции: contacts, contact_field_changes, statuses, files | Backend Contacts |
| API: contacts CRUD + history + поиск | Backend Contacts |
| Custom fields схема (JSONB) + валидация | Backend Contacts |
| API: statuses CRUD | Backend Contacts |
| API: files upload/download (presigned MinIO) | Backend Contacts |
| Сериализация с маскированием `telegram_user_id` | Backend Contacts + Backend Core |
| Frontend: страницы Contacts, ContactView, custom fields editor | Frontend |
| Frontend: компонент истории изменений | Frontend |

**Demo:** оператор открывает контакт, редактирует поля, видит историю «кто и когда менял».

---

## Фаза 3. Чаты + интеграция с готовыми ботами (2 недели)

**Цель:** входящие/исходящие сообщения работают через контракт `BOTS_INTEGRATION.md`, multi-bot, базовое назначение.

> Боты — внешние сервисы. Эта фаза не делает ботов, а делает **контракт интеграции и ингест/диспетчер**. Фаза стала легче по сравнению с «писать aiogram», но прибавилась работа над контрактом и mock-ботом.

| Задача | Кто |
|---|---|
| Миграции: bots, bot_events_inbox, bot_outbound_log, chats, messages | Backend Chats + Bots Integration |
| Финализация контракта `BOTS_INTEGRATION.md` с разработчиками ботов | Bots Integration + Tech Lead |
| Mock-бот (отдельный сервис для тестов) | QA + Bots Integration |
| API: `bots` CRUD, генерация HMAC-секретов, ротация | Bots Integration |
| Endpoint `POST /api/v1/bot-events` с HMAC, anti-replay, идемпотентностью | Bots Integration |
| Маршрутизация событий (`message.received`/`edited`/`delivered`/`read`/`contact.updated`) | Bots Integration |
| Идемпотентность входящих по `(chat, external_id)` | Backend Chats |
| Сервис владения карточкой в группе — см. [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md) | Backend Contacts + Chats |
| API: `GET /chats`, `GET /chats/{id}`, `GET /chats/{id}/messages` | Backend Chats |
| API: `POST /chats/{id}/messages` (исходящее) + ARQ job `bots.send` | Backend Chats + Bots Integration |
| ARQ job `bots.download_attachment` (URL → MinIO) | Bots Integration |
| Health-check ARQ периодика (`bots.healthcheck_all`) | Bots Integration |
| WS Hub + Redis Pub/Sub bridge | Backend Chats |
| WS-события: `message.created`, `message.status_changed`, `chat.updated`, `attachment_ready` | Backend Chats |
| Frontend: ChatList, ChatView (виртуализированный список сообщений), composer | Frontend |
| Frontend: индикатор статуса доставки, аплоад файлов, плашка «бот недоступен» | Frontend |

**Demo:** контакт пишет боту → бот шлёт `message.received` в CRM → оператор получает в realtime → отвечает → CRM шлёт `send_message` боту → бот возвращает `ok` → статус в UI обновляется.

---

## Фаза 3.5. Владение карточкой в группе (1.5–2 недели)

**Цель:** владелец = карточка per group; группа видит и пишет в чаты; эскалация N мин; аудит on_behalf.

| Задача | Кто |
|---|---|
| Миграции: `contact_group_assignments`, `group_escalation_settings`, `message_reply_audit` | Backend Contacts |
| Ownership service + backfill | Backend Contacts |
| Refactor chats scope (GROUP visible) + outbound audit | Backend Chats |
| Escalation worker (owner → group → reassign) | Backend Core / Chats |
| API: contact transfers, escalation settings, reply-audit | Backend Contacts |
| Frontend: бейдж владельца, фильтры, transfer карточки | Frontend |

См. [`AUDIT_REFACTOR_OWNERSHIP.md`](AUDIT_REFACTOR_OWNERSHIP.md).

**Cutover (2026-05-17):** `0015` partial unique на активный contact transfer; legacy `chat_transfers` API выключен по умолчанию; drop таблиц — [`LEGACY_OWNERSHIP_REMOVAL.md`](LEGACY_OWNERSHIP_REMOVAL.md) (фаза 2).

---

## Фаза 4. Передача карточки и takeover (1.5 недели) — **✅ функционал (2026-05-17)**

**Цель:** transfer **карточки в группе** + senior takeover.

| Задача | Кто | Статус |
|---|---|---|
| Миграции: `contact_group_transfers` | Backend Contacts | ✅ |
| API transfers: create / approve / accept (contact + group_id) | Backend Contacts | ✅ |
| Auto-expire (ARQ периодика) | Backend Chats | ✅ |
| Гонки и оптимистичная блокировка (`version`, `0018_cgt_version`) | Backend Chats | ✅ |
| API takeover: on/off, конфликт-резолюция | Backend Chats | ✅ |
| WS-события: `transfer.*`, `chat.takeover_*` | Backend Chats | ✅ |
| Frontend: inbox передач карточки (принять/отклонить) | Frontend | ✅ |
| Frontend: senior-вид «На апрув» | Frontend | ✅ |
| Frontend: режим takeover (баннер, заблокированный input) | Frontend | ✅ |
| Notifications: звук при новом transfer-предложении | Frontend | backlog |

**Demo:** user A → передать → senior апрувит → user B видит «принять» → принимает → чат переходит. Senior захватывает чат → user A не может писать → senior пишет → отпускает.

**Pre-Phase-6 Gate (G1–G3):** G1 — pytest + ruff + migrations/read P0; G2 — unread per-operator, scope, `expected_version` на FE; G3 — docs/DX/compose (`make gate`). См. [`teams/07_qa.md`](teams/07_qa.md) § Gate fix P0.

---

## Фаза 5. Поиск, фильтры, UX-полировка (1 неделя) — **✅ 100% (2026-05-17)**

| Задача | Кто | Статус |
|---|---|---|
| Postgres FTS на messages.body (`0016_messages_fts_ru`) | Backend Chats | ✅ |
| Фильтры списка чатов (status, bot, unread, assigned, card_owner) | Backend Chats + Frontend | ✅ |
| Глобальный поиск контактов и сообщений (`GET /search`) | Backend Chats + Frontend | ✅ |
| Аватарки контактов (генерация инициалов) | Frontend | ✅ |
| Drag-n-drop файлов в чат | Frontend | ✅ |
| Hotkeys (Ctrl+K, Ctrl+Enter отправка) | Frontend | ✅ |
| Тёмная тема (persist `crm-theme-mode`) | Frontend | ✅ |

**Приёмка:** `docs/teams/07_qa.md` §8 — verdict **READY**, quality gate зелёный.

---

## Фаза 6. Наблюдаемость и хардненинг (1 неделя) — **✅ 100% (2026-05-17)**

| Задача | Кто | Статус |
|---|---|---|
| Метрики Prometheus (HTTP, WS, queues, bot ingest/outbound rates) | DevOps + Backend | ✅ |
| Дашборды Grafana | DevOps | ✅ |
| Структурные логи + маскирование PII | Backend Core + DevOps | ✅ |
| Sentry интеграция (frontend + backend) | DevOps | ✅ |
| Алерты: queue depth, bot outbound failures, signature_invalid, ws-disconnect rate | DevOps | ✅ |
| Бэкапы Postgres + MinIO + восстановление | DevOps | ✅ |
| Pen-test: проверка scope обхода, RBAC, IDOR | QA | ✅ (`tests/rbac/`, `docs/SECURITY_CHECKLIST.md`) |
| Load-test: smoke 20 VU, цель 10k msg/h | QA | ✅ (`scripts/load/k6_smoke.js`, вне CI) |

**Приёмка:** `docs/teams/07_qa.md` §9 — verdict **READY FOR PHASE 7**.

---

## Фаза 7. Стейджинг и прод-релиз (1 неделя) — **✅ GATE (2026-05-17)**

| Задача | Кто | Статус |
|---|---|---|
| `Dockerfile` приложения, multi-stage build | DevOps | ✅ |
| `docker-compose` staging/prod + Traefik + TLS | DevOps | ✅ |
| CI деплой staging (`deploy-staging.yml`) | DevOps | ✅ |
| Smoke на staging (`scripts/smoke/staging_smoke.sh`) | QA | ✅ |
| UAT чеклист (`scripts/smoke/uat_checklist.md`) | QA + заказчик | ✅ шаблон |
| Деплой в прод, первый админ (`docs/DEPLOY.md`) | DevOps | ✅ runbook |
| Документация пользователей (`docs/user/`) | Tech Lead + QA | ✅ v1 |

**Приёмка:** `docs/teams/07_qa.md` §10 — verdict **READY FOR PHASE 7.5 (хвосты релиза + техдолг)**.

**Хвосты (не блокер GATE):** Playwright E2E, полный restore backup на staging, live Sentry на prod.

---

## Фаза 7.5. Хвосты релиза + техдолг (~0.5–1 неделя)

**Цель:** закрыть ops-хвосты ф.7 и накопленный техдолг **без** домена лидов.

| Задача | Кто | Статус |
|---|---|---|
| Staging VPS + DNS + smoke на реальном URL (F7-2, F7-4) | DevOps + QA | ⏳ ops |
| Sentry live на staging/prod (F7-5) | DevOps | ⏳ |
| Backup cron + UAT sign-off (F7-6, F7-7) | DevOps + заказчик | ⏳ |
| Admin UI (`/admin` в operator SPA) | Frontend + Backend | ✅ |
| Legacy DROP / unread cutover | Backend | ✅ `0025`: DROP `unread_count_user`, archive `chat_transfers`, contact assignee cols — [`LEGACY_OWNERSHIP_REMOVAL.md`](LEGACY_OWNERSHIP_REMOVAL.md) |
| pg_trgm GIN (contacts/chats preview) | Backend | ✅ `0024_pg_trgm_search` |
| Playwright E2E (Epic 4) | QA | OPTIONAL |
| Restore backup cycle на staging | DevOps | не гонялся |

**Не входит в 7.5:** лиды, воронка сделок, `ensure_lead` → **фаза 8**.

**Приёмка:** `docs/teams/07_qa.md` §10 хвосты закрыты или явно deferred; старт ф.8 не блокируется отсутствием Playwright.

---

## Фаза 8. Лиды (~1.5 недели) — **✅ L8-1…L8-10 + gate (2026-05-17)**

**Цель:** сделка = лид per `(contact_id, group_id)`; воронка на лиде; метка чата отдельно; сообщения с `lead_id`; сводка `crm_summary`.

> **Gate vs scope:** **L8 GATE полный** = `make gate` / `gate-full` (`docs/teams/07_qa.md` §11, L8-GATE-1…4). **L8-1…L8-5** — ядро (миграции, `ensure_lead`, kind). **L8-6…L8-10** — API, RBAC/`crm_summary`, WS, UI, operator docs. **Verdict (2026-05-17):** L8-GATE-1…4 ✅; полный `pytest -q` **442** passed (2×) → **READY** для ф.7.5.

> Канон: [`LEADS.md`](LEADS.md). Схема — [`DATABASE.md`](DATABASE.md) §6–7. API — [`API_CONTRACT.md`](API_CONTRACT.md) §9. WS — [`EVENTS.md`](EVENTS.md) §3.8.

| ID | Задача | Кто | Статус |
|---|---|---|---|
| **L8-1** | Миграции `0019`–`0022`: `leads`, `statuses.kind`, `current_lead_id`, `messages.lead_id`, audit enums, list index; backfill | Backend | ✅ |
| **L8-2** | `ensure_lead`, cutover `lead_id`, kind-валидация (`PATCH /chats/.../status_id` → `chat_label` only) | Backend Chats | ✅ |
| **L8-3** | API: `/contacts/{id}/leads`, `/leads/{id}`, patch, close; `crm_summary` на контакте | Backend | ✅ |
| **L8-4** | WS `lead.*`; UI воронка / закрытие / фильтры | FE + Backend | ✅ |
| **L8-5** | RBAC + `tests/leads/` (**23**); operator-quickstart § лиды | QA | ✅ |

**Demo:** клиент пишет → создаётся лид «новый» → оператор ведёт по воронке → закрывает лид → клиент пишет снова → **новый** лид; в чате видны оба цикла по `lead_id`.

**Приёмка:** `docs/teams/07_qa.md` §11.

**Хвосты → ф.7.5:** Admin UI статусов, Playwright (legacy DROP/unread — ✅ `0025`).

**Не входит в ф.8 (v1.1+):** retention purge; **department-боты** (ingest `group_id`); materialized `crm_summary`. См. [`LEADS.md`](LEADS.md) §4, §7.

---

## Сводный таймлайн

| Фаза | Недели | Накопительно |
|---|---|---|
| 0. Подготовка | 1 | 1 |
| 1. Ядро и Auth | 2 | 3 |
| 2. Контакты и статусы | 1.5 | 4.5 |
| 3. Чаты + интеграция ботов | 2 | 6.5 |
| 4. Передача и takeover | 1.5 | 8 |
| 5. Поиск и UX | 1 | 9 |
| 6. Observability + harden | 1 | 10 |
| 7. Релиз | 1 | 11 |
| 7.5. Хвосты релиза + техдолг | 0.5–1 | 11.5–12 |
| 8. Лиды | 1.5 | **13–13.5 недель** ✅ L8-1…L8-10 + gate (2026-05-17) |

Это «правдивый» оптимистичный план для команды 4–6 разработчиков. Соло — добавь буфер +50%.

---

## Что после релиза (v1.1+)

- Retention / purge закрытых лидов (`LEAD_RETENTION_DAYS`, job — см. [`LEADS.md`](LEADS.md) §4).
- WhatsApp / VK / Web-widget как новые каналы (использовать ту же модель чатов).
- Quick replies и шаблоны сообщений.
- Команды (slash-commands) внутри чата.
- Аналитика по операторам (avg response time, active hours).
- Передача чата по очередям (skill-based routing).
- 2FA для admin/senior.
- Импорт/экспорт контактов CSV.
- Centrifugo вместо встроенного WS-хаба (когда упрёмся).

---

## Слабые места плана

1. **Сроки оптимистичные.** Без QA на ранних фазах появятся регрессы, которые сожрут полнедели на каждой фазе.
2. **Фаза 3 рискованная** из-за **зависимости от готовности ботов**. Если разработчики ботов не успевают реализовать контракт — наша фаза 3 ждёт. Митигация: mock-бот в Фазе 1, разработка контракта на бумаге в Фазе 2, синки с авторами ботов еженедельно.
3. **Frontend — один поток.** Если фронтендеров двое, можно резать вертикально (auth+org vs chats+contacts) и параллелить.
4. **RBAC-тесты часто откладывают** — после первого же бага начинаются переписывания. Тесты на матрицу прав обязательны в Фазе 1, не позже.
5. **Стейджинг в Фазе 7 — поздно.** Поднять простой стейджинг в Фазе 1 и катить туда после каждого мерджа.
