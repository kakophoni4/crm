# Модель данных

> PostgreSQL 16. Все таблицы — `snake_case`. Первичный ключ — `id BIGSERIAL` (или `BIGINT GENERATED ALWAYS AS IDENTITY`). Все таблицы имеют `created_at TIMESTAMPTZ DEFAULT now()` и `updated_at TIMESTAMPTZ DEFAULT now()` (триггер обновляет).
>
> Источник истины — Alembic-миграции. Этот файл фиксирует **намерение** схемы, миграции должны его реализовать.

---

## 1. Оргструктура

### `users`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| email | CITEXT UNIQUE NOT NULL | |
| password_hash | TEXT NOT NULL | bcrypt/argon2 |
| full_name | TEXT NOT NULL | |
| role | user_role NOT NULL | enum: 'user', 'senior', 'admin' |
| group_id | BIGINT NULL FK groups.id | NULL для admin и senior без группы |
| status | user_status NOT NULL DEFAULT 'active' | enum: 'active', 'disabled' |
| presence | user_presence NOT NULL DEFAULT 'offline' | enum: 'online', 'away', 'busy', 'offline' |
| availability | user_availability NOT NULL DEFAULT 'available' | enum: 'available', 'do_not_assign' |
| last_seen_at | TIMESTAMPTZ NULL | |
| created_by | BIGINT NULL FK users.id | |

Индексы: `idx_users_group_id`, `idx_users_role`, `idx_users_email_lower (email)`.

### `departments`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| name | TEXT NOT NULL | |
| head_user_id | BIGINT NULL FK users.id | Senior отдела |
| created_by | BIGINT NULL FK users.id | |

Уникально: `name`.

### `groups`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| name | TEXT NOT NULL | |
| department_id | BIGINT NOT NULL FK departments.id | |
| created_by | BIGINT NULL FK users.id | |

Уникально: `(department_id, name)`. Индекс: `idx_groups_department`.

### Ограничения целостности
- Юзер с `role='user'` обязан иметь `group_id` (CHECK).
- Юзер с `role='senior'` обязан быть `head_user_id` ровно одного отдела (проверяется в сервисном слое + триггер для отчёта неконсистентности).
- Юзер с `role='admin'` имеет `group_id IS NULL`.

---

## 2. Аутентификация

### Сессии (Redis, не в БД)
- `refresh:{user_id}:{jti}` → JSON `{ip, ua, created_at, expires_at}`, TTL = срок жизни refresh.
- Logout = `DEL` ключа.
- Force-logout user = `SCAN refresh:{user_id}:*` + `DEL`.
- Лист отзыва не нужен — отсутствие ключа = отозван.

### `password_reset_tokens` (опционально)
| id | user_id | token_hash | expires_at | used_at |

### `audit_log` (общий)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| actor_id | BIGINT NULL FK users.id | |
| action | TEXT NOT NULL | напр. 'user.create', 'chat.transfer.approve' |
| entity_type | TEXT NOT NULL | |
| entity_id | BIGINT NULL | |
| payload | JSONB NOT NULL DEFAULT '{}' | до/после/контекст |
| ip | INET NULL | |
| user_agent | TEXT NULL | |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Индексы: `idx_audit_actor`, `idx_audit_entity (entity_type, entity_id)`, `idx_audit_created_at BRIN`. Партиционирование по месяцу (после первого года).

---

## 3. Контакты

### `contacts`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| display_name | TEXT NOT NULL | имя/название контакта |
| phone | TEXT NULL | E.164 |
| email | CITEXT NULL | |
| telegram_user_id | BIGINT NULL UNIQUE | **видим только админу** |
| telegram_username | TEXT NULL | без @, видим всем у кого есть доступ |
| custom_fields | JSONB NOT NULL DEFAULT '{}' | произвольные поля по схеме |
| created_by | BIGINT NULL FK users.id | |

> **Владение карточкой** — `contact_group_assignments` ([`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md)). Колонки `contacts.assigned_user_id` / `assigned_group_id` удалены в `0025`.

Индексы: `unique idx_contacts_telegram_user_id`, `idx_contacts_telegram_username`, `idx_contacts_phone`, GIN на `custom_fields`.

### `contact_group_assignments` (владение карточкой в группе)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| contact_id | BIGINT NOT NULL FK contacts.id | |
| group_id | BIGINT NOT NULL FK groups.id | scope владения |
| owner_user_id | BIGINT NULL FK users.id | владелец; NULL = пул группы |
| assigned_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| assignment_source | TEXT NOT NULL | `auto_round_robin`, `auto_first_responder`, `auto_random_available`, `manual_transfer`, `senior_assign`, `migration` |
| last_owner_response_at | TIMESTAMPTZ NULL | последний исходящий от владельца в группе |
| pending_inbound_at | TIMESTAMPTZ NULL | входящее, ждущее ответа владельца (таймер N) |
| escalated_to_group_at | TIMESTAMPTZ NULL | когда уведомили всю группу |

Уникально: `(contact_id, group_id)`. Индексы: `(group_id, owner_user_id)`, `(owner_user_id)`, `(pending_inbound_at) WHERE pending_inbound_at IS NOT NULL`.

### `contact_group_transfers`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| contact_id | BIGINT NOT NULL FK contacts.id | |
| group_id | BIGINT NOT NULL FK groups.id | **только эта группа** |
| from_user_id | BIGINT NOT NULL FK users.id | прежний владелец |
| to_user_id | BIGINT NOT NULL FK users.id | |
| requested_by | BIGINT NOT NULL FK users.id | |
| state | transfer_state NOT NULL | как `chat_transfers` |
| senior_user_id | BIGINT NULL | |
| senior_decided_at | TIMESTAMPTZ NULL | |
| recipient_decided_at | TIMESTAMPTZ NULL | |
| force_assigned | BOOLEAN DEFAULT FALSE | |
| comment | TEXT NULL | |
| expires_at | TIMESTAMPTZ NOT NULL | |
| version | INT NOT NULL DEFAULT 1 | optimistic lock на approve/accept (`expected_version` query) |

Индексы: `(contact_id, group_id, state)`, `(to_user_id) WHERE state IN pending_*`.

### `chat_read_state` (per-operator unread, миграция `0017`)
| Поле | Тип | Описание |
|---|---|---|
| user_id | BIGINT PK FK users.id | |
| chat_id | BIGINT PK FK chats.id | |
| last_read_message_id | BIGINT NULL FK messages.id | |
| read_at | TIMESTAMPTZ NOT NULL | |

Канон unread — `chat_read_state` / `unread_for_me` (колонка `chats.unread_count_user` удалена в `0025`).

> **Alembic head:** `0025_legacy_ownership_phase2` (… → `0024_pg_trgm_search` → `0025`). GIN `pg_trgm` — миграция `0024`.

**Миграция `0015`:** partial unique `uq_cgt_active_contact_group` на `(contact_id, group_id)` WHERE `state IN ('pending_senior','pending_recipient','pending','approved')` — не более одного активного transfer на пару (дублирует app-guard + защита от гонок).

### `group_escalation_settings`
| Поле | Тип | Описание |
|---|---|---|
| group_id | BIGINT PK FK groups.id | |
| first_response_timeout_minutes | INT NOT NULL DEFAULT 15 | **N**, настраивает senior |
| new_contact_reassign_strategy | TEXT NOT NULL DEFAULT 'first_responder' | `first_responder` \| `random_available` |
| notify_owner_on_inbound | BOOLEAN DEFAULT TRUE | |
| notify_group_on_escalation | BOOLEAN DEFAULT TRUE | |
| updated_by | BIGINT NULL FK users.id | |
| updated_at | TIMESTAMPTZ | |

### `contact_field_changes` (поле-уровень аудит)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| contact_id | BIGINT NOT NULL FK contacts.id | |
| user_id | BIGINT NOT NULL FK users.id | кто менял |
| field_name | TEXT NOT NULL | например 'display_name' или 'custom_fields.company' |
| old_value | TEXT NULL | сериализованное прежнее значение |
| new_value | TEXT NULL | сериализованное новое значение |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Индексы: `idx_cfc_contact (contact_id, created_at DESC)`. Партиционирование по месяцу при росте.

---

## 4. Боты (внешняя интеграция)

> CRM не работает с Telegram API напрямую. Боты — внешние сервисы, общение с CRM по контракту `BOTS_INTEGRATION.md` (HTTP + HMAC).

### `bots`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| code | TEXT NOT NULL UNIQUE | короткий идентификатор (`support_a`, `sales_b`) |
| name | TEXT NOT NULL | название для UI |
| purpose | TEXT NULL | назначение |
| owner_type | bot_owner_type NOT NULL | enum: 'department', 'group' |
| owner_id | BIGINT NOT NULL | id department или group (валидация в сервисе) |
| outbound_url | TEXT NOT NULL | endpoint бота для приёма команд от CRM |
| health_url | TEXT NULL | если NULL — выводится из outbound_url |
| inbound_secret_encrypted | TEXT NOT NULL | HMAC ключ для верификации входящих от бота (`pgp_sym_encrypt`) |
| previous_inbound_secret_encrypted | TEXT NULL | для grace period при ротации |
| previous_inbound_secret_valid_until | TIMESTAMPTZ NULL | |
| outbound_secret_encrypted | TEXT NOT NULL | HMAC ключ для подписи команд CRM → бот |
| ip_allowlist | CIDR[] NULL | если задан — входящие принимаются только с этих IP |
| is_active | BOOLEAN NOT NULL DEFAULT TRUE | если false — CRM не шлёт команды и игнорирует входящие |
| last_seen_at | TIMESTAMPTZ NULL | от health-check |
| created_by | BIGINT NULL FK users.id | |

Индексы: `idx_bots_owner (owner_type, owner_id)`, уникально `code`.
CHECK на уровне сервиса: при `owner_type='group'` — `owner_id` в `groups`; при `'department'` — в `departments`.

### `bot_events_inbox` (идемпотентность входящих)
| Поле | Тип | Описание |
|---|---|---|
| event_id | TEXT PK | ULID/UUID от бота, переданный в `X-Bot-Event-Id` |
| bot_id | BIGINT NOT NULL FK bots.id | |
| event_type | TEXT NOT NULL | для отчётов |
| received_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Индексы: `idx_bei_received_at BRIN`. Чистка ARQ-периодикой каждые 6 часов: `DELETE WHERE received_at < now() - INTERVAL '24 hours'`.

### `bot_outbound_log` (идемпотентность исходящих + аудит)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| bot_id | BIGINT NOT NULL FK bots.id | |
| message_id | BIGINT NOT NULL FK messages.id | |
| request_id | TEXT NOT NULL UNIQUE | переданный в `X-CRM-Request-Id` |
| status | bot_outbound_status NOT NULL | enum: 'queued', 'sent', 'failed' |
| attempts | INT NOT NULL DEFAULT 0 | |
| last_error_code | TEXT NULL | |
| last_error_message | TEXT NULL | |
| latency_ms | INT NULL | время последней успешной попытки |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| completed_at | TIMESTAMPTZ NULL | |

Уникально: `(message_id)` — один outbound-лог на сообщение. Индексы: `idx_bol_status_pending (status) WHERE status='queued'`, `idx_bol_bot_created (bot_id, created_at DESC)`.

---

## 5. Чаты и сообщения

### `chats`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| contact_id | BIGINT NOT NULL FK contacts.id | |
| bot_id | BIGINT NOT NULL FK bots.id | |
| assigned_group_id | BIGINT NULL FK groups.id | денормализация группы бота |
| last_handled_by_user_id | BIGINT NULL FK users.id | кто последний писал (**не** владелец) |
| takeover_user_id | BIGINT NULL FK users.id | senior, временно перехвативший |
| status_id | BIGINT NULL FK statuses.id | только `kind = 'chat_label'` — см. [`LEADS.md`](LEADS.md) |
| current_lead_id | BIGINT NULL FK leads.id | активный лид в UI; см. [`LEADS.md`](LEADS.md) |
| last_message_at | TIMESTAMPTZ NULL | |
| last_message_preview | TEXT NULL | для списка |
| unread_count_for_operator | INT NOT NULL DEFAULT 0 | |
| version | INT NOT NULL DEFAULT 0 | оптимистичная блокировка |

Уникально: `(contact_id, bot_id)` — один чат на (контакт, бот).
Индексы: `idx_chats_current_user`, `idx_chats_takeover_user`, `idx_chats_status`, `idx_chats_last_message_at DESC`, `idx_chats_bot_id`.

### `messages`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| chat_id | BIGINT NOT NULL FK chats.id | |
| lead_id | BIGINT NULL FK leads.id | после cutover ф.8 — NOT NULL для новых inbound/outbound; см. [`LEADS.md`](LEADS.md) |
| direction | message_direction NOT NULL | enum: 'in', 'out' |
| author_user_id | BIGINT NULL FK users.id | NULL для входящих; для out — оператор/senior |
| author_role_at_send | TEXT NULL | snapshot роли (для аудита takeover) |
| body | TEXT NULL | текст |
| attachments | JSONB NOT NULL DEFAULT '[]' | массив `{type, file_id?, url_pending?, mime, size, filename, failed?}` |
| external_id | TEXT NULL | id сообщения у бота (для матчинга edited/delivered) |
| telegram_message_id | BIGINT NULL | id в Telegram (если бот его передаёт) |
| reply_to_external_id | TEXT NULL | для тредов |
| status | message_status NOT NULL DEFAULT 'queued' | enum: 'queued', 'sent', 'delivered', 'read', 'failed' |
| failure_code | TEXT NULL | error_code из ответа бота |
| failure_reason | TEXT NULL | человекочитаемое описание |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Индексы: `idx_messages_chat_created (chat_id, created_at DESC)`, уникально `(chat_id, external_id)` для идемпотентности входящих от бота, `idx_messages_status (status) WHERE status = 'queued'` для воркера.

**FTS (миграция `0016`):** generated column `search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian', coalesce(text, ''))) STORED` + GIN `idx_messages_search_vector`. Поиск: `search_vector @@ plainto_tsquery('russian', $q)`; подсветка — `ts_headline('russian', text, plainto_tsquery(...))`. API: `GET /api/v1/chats/search` (отдельно от preview `GET /chats?q=` ilike).

### `message_reply_audit` (обязательный аудит исходящих)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| message_id | BIGINT NOT NULL UNIQUE FK messages.id | |
| chat_id | BIGINT NOT NULL FK chats.id | |
| contact_id | BIGINT NOT NULL FK contacts.id | |
| group_id | BIGINT NOT NULL FK groups.id | |
| card_owner_user_id | BIGINT NOT NULL FK users.id | владелец карточки **на момент отправки** |
| author_user_id | BIGINT NOT NULL FK users.id | кто нажал «Отправить» |
| is_on_behalf | BOOLEAN NOT NULL | `author != owner` |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Индексы: `(contact_id, created_at DESC)`, `(card_owner_user_id, created_at DESC)`, `(author_user_id)`.

### `chat_transfers_archived_2026` (legacy, фаза 2)

> Таблица `chat_transfers` переименована в `0025`. Канон — `contact_group_transfers`. См. [`LEGACY_OWNERSHIP_REMOVAL.md`](LEGACY_OWNERSHIP_REMOVAL.md).
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| chat_id | BIGINT NOT NULL FK chats.id | |
| from_user_id | BIGINT NOT NULL FK users.id | кто передаёт |
| to_user_id | BIGINT NOT NULL FK users.id | кому |
| requested_by | BIGINT NOT NULL FK users.id | инициатор (User или Senior) |
| state | transfer_state NOT NULL | enum: 'pending_senior', 'pending_recipient', 'accepted', 'declined_senior', 'declined_recipient', 'cancelled', 'expired' |
| senior_user_id | BIGINT NULL FK users.id | кто апрувил/реджектил |
| senior_decided_at | TIMESTAMPTZ NULL | |
| recipient_decided_at | TIMESTAMPTZ NULL | |
| force_assigned | BOOLEAN NOT NULL DEFAULT FALSE | для админа |
| comment | TEXT NULL | |
| expires_at | TIMESTAMPTZ NOT NULL | автоматический expire |

Индексы: `idx_transfers_chat`, `idx_transfers_state`, `idx_transfers_to_user (to_user_id) WHERE state = 'pending_recipient'`.
Активный transfer на чат — только один в состоянии `pending_*` (партиальный уникальный индекс).

### `chat_participants_history` (для отчётов)
Опционально: лог, как менялся `current_user_id` чата (snapshot перед каждым изменением).

---

## 6. Статусы (фаза 8 — черновик)

> Канон разделения чат / лид: [`LEADS.md`](LEADS.md). Миграция ф.8 вводит `kind` и seed для `chat_label` и `lead_pipeline`. Legacy `applies_to` (`chat` \| `contact`) — удалить или маппить при backfill.

### `statuses`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| code | TEXT NOT NULL UNIQUE | напр. `new_client`, `in_progress` |
| kind | TEXT NOT NULL | `chat_label` \| `lead_pipeline` (см. `StatusKind` в ORM) |
| label | TEXT NOT NULL | UI-название (бывш. `name`) |
| color | TEXT NULL | hex, опционально |
| sort_order | INT NOT NULL DEFAULT 0 | |
| is_active | BOOLEAN NOT NULL DEFAULT TRUE | |
| created_at / updated_at | TIMESTAMPTZ | |

**Правила привязки:**

| `kind` | Используется в | Примеры кодов |
|--------|----------------|---------------|
| `chat_label` | `chats.status_id` | `new_client` (default), `returning_client` |
| `lead_pipeline` | `leads.status_id` | `new`, `in_progress`, `waiting_client`, `done`, `cancelled` |

Индекс: `idx_statuses_kind_active (kind, sort_order) WHERE is_active`.

---

## 7. Лиды (фаза 8 — черновик)

> Канон: [`LEADS.md`](LEADS.md).

### `leads`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| contact_id | BIGINT NOT NULL FK contacts.id | |
| group_id | BIGINT NOT NULL FK groups.id | scope владения и RBAC |
| chat_id | BIGINT NULL FK chats.id | чат, в котором открыт лид (если известен) |
| status_id | BIGINT NOT NULL FK statuses.id | только `statuses.kind = 'lead_pipeline'` |
| opened_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| closed_at | TIMESTAMPTZ NULL | `NULL` = открытый лид |
| closed_by_user_id | BIGINT NULL FK users.id | |
| source | TEXT NOT NULL | `inbound`, `outbound`, `manual`, `migration` |
| retention_expires_at | TIMESTAMPTZ NULL | ф.8: всегда NULL; purge — TODO |
| created_at / updated_at | TIMESTAMPTZ | |

Уникально (рекомендуется): partial unique `(contact_id, group_id) WHERE closed_at IS NULL` — не более одного открытого лида.

Индексы: `(group_id, status_id) WHERE closed_at IS NULL`, `(contact_id, group_id, opened_at DESC)`, `(chat_id)`.

**Список лидов контакта (миграция `0022_leads_list_index`):** `idx_leads_contact_created_id` на `(contact_id, created_at DESC, id DESC)` — пагинация `GET /contacts/{id}/leads`.

---

## 8. Файлы

### `files`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| storage_key | TEXT NOT NULL UNIQUE | путь в MinIO |
| original_name | TEXT NOT NULL | |
| mime | TEXT NOT NULL | |
| size_bytes | BIGINT NOT NULL | |
| sha256 | BYTEA NOT NULL | |
| uploaded_by | BIGINT NOT NULL FK users.id | |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Сообщения ссылаются на файлы через `attachments.file_id`.

---

## 9. Реестр модулей (для будущего расширения)

### `module_registry`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| code | TEXT UNIQUE NOT NULL | |
| name | TEXT NOT NULL | |
| version | TEXT NOT NULL | |
| status | module_status NOT NULL | enum: 'enabled', 'disabled' |
| metadata | JSONB NOT NULL DEFAULT '{}' | menu_items, permissions, base_url для внешних модулей |

На старте используется как «фича-флаги» для встроенных модулей. Готовая инфраструктура для будущих внешних модулей (когда отойдём от монолита).

---

## 10. Enum-типы

```sql
CREATE TYPE user_role AS ENUM ('user', 'senior', 'admin');
CREATE TYPE user_status AS ENUM ('active', 'disabled');
CREATE TYPE user_presence AS ENUM ('online', 'away', 'busy', 'offline');
CREATE TYPE user_availability AS ENUM ('available', 'do_not_assign');
CREATE TYPE bot_owner_type AS ENUM ('department', 'group');
CREATE TYPE bot_outbound_status AS ENUM ('queued', 'sent', 'failed');
CREATE TYPE message_direction AS ENUM ('in', 'out');
CREATE TYPE message_status AS ENUM ('queued', 'sent', 'delivered', 'read', 'failed');
CREATE TYPE transfer_state AS ENUM (
  'pending_senior', 'pending_recipient',
  'accepted', 'declined_senior', 'declined_recipient',
  'cancelled', 'expired'
);
CREATE TYPE status_target AS ENUM ('chat', 'contact');  -- legacy; ф.8 → kind TEXT
-- StatusKind (app): 'chat_label', 'lead_pipeline'
CREATE TYPE module_status AS ENUM ('enabled', 'disabled');
```

---

## 11. Производительность

### Индексы, которые точно понадобятся
- `idx_messages_chat_created` — основной запрос «сообщения чата».
- `idx_messages_search_vector` (GIN) — FTS по тексту сообщений (`0016`).
- `idx_chats_current_user` — «мои чаты».
- `idx_chats_last_message_at DESC` — сортировка списка.
- `idx_leads_group_open (group_id) WHERE closed_at IS NULL` — открытые лиды и `crm_summary`.
- `idx_leads_contact_created_id` (`0022`) — `GET /contacts/{id}/leads` с cursor.
- `idx_messages_lead_id` — фильтр сообщений по лиду в UI.
- `idx_transfers_to_user WHERE state='pending_recipient'` — push-уведомления юзеру.
- BRIN на `audit_log.created_at` — дешёвая сортировка по времени для огромной таблицы.

### Партиционирование (этап 2)
- `messages` по месяцу при > 50M строк.
- `audit_log` по месяцу при > 20M.
- `contact_field_changes` по месяцу при > 10M.

### Что **нельзя** делать
- LIKE '%abc%' по `messages.body` без триграммного индекса (`pg_trgm`) или FTS.
- `JSONB ?` без GIN-индекса.
- Сортировка по `last_message_at` без индекса.

---

## 12. Безопасность данных

- Поле `users.password_hash` — не выходит за пределы БД, никогда не сериализуется.
- Поле `contacts.telegram_user_id` — отдельный сериализатор `ContactAdminOut`, для всех остальных это поле отсутствует в ответе.
- Поля `bots.inbound_secret_encrypted` / `outbound_secret_encrypted` — расшифровываются только при ротации (выдача один раз через UI) и в момент HMAC-операций. Никогда не попадают в API-ответ.
- В `audit_log.payload` запрещено писать `telegram_user_id`, `inbound_secret`, `outbound_secret`. Утилита `audit.write(...)` фильтрует.

---

## 13. Слабые места модели

1. **`bot_owner_type` + `bot_owner_id` — полиморфная ссылка**, не защищена FK на уровне БД. Митигация: проверка в сервисе и периодический целостностный отчёт.
2. **`messages.attachments` как JSONB** — удобно, но теряется FK на `files`. Альтернатива — отдельная таблица `message_attachments`. Решение: оставляем JSONB ради скорости, делаем background-job, который проверяет orphans.
3. **`unread_count_for_operator` в `chats`** — денормализация, может уйти в рассинхрон. Митигация: триггер на `messages` или периодический пересчёт.
4. **`version`-поле против гонок** — работает только если все апдейтеры его проверяют. Закрепить ревью-чеклист.
5. **`statuses.kind`** — два справочника в одной таблице; ошибочная привязка к `chats`/`leads` ловится в сервисе. Partial unique на открытый лид обязателен против гонок inbound.
6. **`leads` без retention job** — рост таблицы до ф.8.1+ (см. [`LEADS.md`](LEADS.md) §4).
7. **Legacy `statuses.applies_to`** — при миграции на `kind` нужен one-shot map `chat`→`chat_label`, контактные статусы — отдельное решение.
8. **`bot_events_inbox` без партиционирования** — при тысячах входящих/час таблица быстро растёт. ARQ-чистка обязательна; при большом RPS — партиционирование по дню.
9. **Уникальность `messages.(chat_id, external_id)`** требует, чтобы бот действительно генерировал уникальные `external_id`. Если бот ошибся — будет 23505 conflict, и сообщение потеряется. Решение: при конфликте отвечать 200 (это идемпотентный duplicate), но логировать.
