# API контракт

> Базовый префикс: `/api/v1`. Все ответы — JSON. Аутентификация — `Authorization: Bearer <access_token>`. Все timestamp'ы — ISO-8601 UTC. Все запросы — `application/json`, кроме явно указанных.
>
> Финальный источник истины — OpenAPI-схема, генерируемая FastAPI (`/api/openapi.json`). Этот документ — намерение и согласованный контракт между бэкендом и фронтом.

---

## 1. Общее

### 1.1 Заголовки
- `Authorization: Bearer <access>` — обязательно для всех, кроме `/auth/*`.
- `X-Request-Id` — клиент может прислать, если нет — сервер сгенерирует.

### 1.2 Ошибки (единый формат)
```json
{
  "error": {
    "code": "validation_error",
    "message": "Field 'email' is required",
    "details": { "field": "email" },
    "request_id": "01J..."
  }
}
```

Коды:
| Код | HTTP | Когда |
|---|---|---|
| `validation_error` | 422 | Pydantic-валидация |
| `authentication_required` | 401 | Нет/невалидный access |
| `permission_denied` | 403 | Нет права |
| `not_found` | 404 | |
| `conflict` | 409 | Конфликт состояния (например, takeover уже активен) |
| `rate_limited` | 429 | Login: 10/min per IP (`auth:login:{ip}`); search: 60/min per user |
| `internal_error` | 500 | |

### 1.3 Пагинация
Cursor-based для списков сообщений и больших таблиц:
```
GET /api/v1/chats/{id}/messages?limit=50&before=<cursor>
→ { "items": [...], "next_cursor": "..." | null }
```
Offset-based для коротких списков (отделы, группы):
```
GET /api/v1/departments?page=1&size=20
→ { "items": [...], "total": 17, "page": 1, "size": 20 }
```

---

## 2. Auth

### `POST /api/v1/auth/login`
Req:
```json
{ "email": "user@example.com", "password": "..." }
```
Resp 200:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": { "id": 1, "email": "...", "full_name": "...", "role": "user" }
}
```

### `POST /api/v1/auth/refresh`
Req: `{ "refresh_token": "..." }` → новые access+refresh, старый refresh инвалидируется.

### `POST /api/v1/auth/logout`
Отзывает текущий refresh.

### `GET /api/v1/auth/me`
Текущий профиль с правами:
```json
{
  "id": 1,
  "email": "...",
  "full_name": "...",
  "role": "senior",
  "department_id": 3,
  "group_id": null,
  "presence": "online",
  "permissions": ["chats.read", "users.create.dept", "..."]
}
```

### `POST /api/v1/auth/me/password`
Смена своего пароля.

### `POST /api/v1/auth/ws-ticket`
Resp:
```json
{ "ticket": "<short-lived-token>", "expires_in": 60 }
```
Используется при connect к WS.

---

## 3. Users

### `GET /api/v1/users`
Query: `?role=&group_id=&department_id=&q=&page=&size=`. Возвращает только видимых актору.

### `GET /api/v1/users/{id}`
Карточка юзера в пределах видимости.

### `POST /api/v1/users` (senior, admin)
Req:
```json
{
  "email": "...", "full_name": "...", "password": "...",
  "role": "user", "group_id": 5
}
```
Senior может создать только в свой отдел.

### `PATCH /api/v1/users/{id}`
Поля: `full_name`, `group_id`, `status`, `availability`, и т.д.

### `POST /api/v1/users/{id}/reset-password` (senior своего отдела, admin)
Возвращает временный пароль или отправляет письмо (TBD).

### `POST /api/v1/users/{id}/force-logout` (senior своего отдела, admin)
Инвалидирует все refresh-токены.

---

## 4. Departments

### `GET /api/v1/departments`
- user/senior — видит только свой;
- admin — все.

### `POST /api/v1/departments` (admin)
```json
{ "name": "Продажи", "head_user_id": 12 }
```

### `PATCH /api/v1/departments/{id}` (admin)
Изменение `name`, `head_user_id`.

### `DELETE /api/v1/departments/{id}` (admin)
Только если нет групп и юзеров.

---

## 5. Groups

### `GET /api/v1/groups`
Query: `?department_id=`. Видимость по scope.

### `POST /api/v1/groups` (senior своего отдела, admin)
```json
{ "name": "Отдел продаж — поток A", "department_id": 3 }
```
Senior: `department_id` обязан совпадать со своим.

### `PATCH /api/v1/groups/{id}`
### `DELETE /api/v1/groups/{id}` (если нет активных юзеров)

---

## 6. Bots (внешние ботов-интеграторы)

> Боты — внешние сервисы, общение по контракту [`BOTS_INTEGRATION.md`](BOTS_INTEGRATION.md). CRM регистрирует у себя метаданные бота и выдаёт пару HMAC-ключей.

### `GET /api/v1/bots`
Видимость по scope. Поля для не-админа: `id`, `code`, `name`, `purpose`, `owner_type`, `owner_id`, `is_active`, `last_seen_at`. Для админа — плюс `outbound_url`, `health_url`, `ip_allowlist`, `created_at`. **Никогда** не возвращаются секреты.

### `POST /api/v1/bots` (admin)
Req:
```json
{
  "code": "support_a",
  "name": "Поддержка отдел A",
  "purpose": "Первичные обращения",
  "owner_type": "department",
  "owner_id": 3,
  "outbound_url": "https://bot.example.com/crm/cmd",
  "health_url": "https://bot.example.com/crm/health",
  "ip_allowlist": ["203.0.113.0/24"]
}
```
Resp 201 (секреты возвращаются **один раз**):
```json
{
  "id": 12,
  "code": "support_a",
  "name": "...",
  "outbound_url": "...",
  "is_active": true,
  "secrets": {
    "inbound_secret": "<base64url, 32 байта>",
    "outbound_secret": "<base64url, 32 байта>",
    "warning": "Это единственный раз, когда секреты видны. Сохраните их в хранилище бота."
  }
}
```

### `PATCH /api/v1/bots/{id}` (admin)
Меняет `name`, `purpose`, `owner_type`, `owner_id`, `outbound_url`, `health_url`, `ip_allowlist`, `is_active`.

### `DELETE /api/v1/bots/{id}` (admin)
Soft delete, `is_active=false`. Запись остаётся ради ссылок из chats/messages.

### `POST /api/v1/bots/{id}/rotate-secret` (admin)
Req:
```json
{ "which": "inbound" | "outbound" | "both" }
```
Resp:
```json
{
  "secrets": {
    "inbound_secret": "<новый, если запрошен>",
    "outbound_secret": "<новый, если запрошен>"
  },
  "grace_period_minutes": 5
}
```
Старый `inbound_secret` остаётся валидным 5 минут (поле `previous_inbound_secret_*`). Старый `outbound_secret` инвалидируется сразу — бот должен принять новый ключ до начала ротации, либо настроить grace на своей стороне.

---

## 7. Chats

### `GET /api/v1/chats`
Query (все опциональны, комбинируются через **AND**): `status`, `status_id`, `assigned_user_id`, `contact_id`, `bot_id`, `unread_only`, `needs_reply`, `card_owner_user_id`, `assigned_group_id`, `q`, `sort`, `cursor`, `limit` (default 50, max 100).

| Параметр | Описание |
|----------|----------|
| `status` | enum `open` \| `in_progress` \| `closed` \| `archived` |
| `status_id` | FK `statuses.id` (`kind = chat_label`) |
| `lead_status_id` | фильтр по `leads.status_id` активного лида (`JOIN` `chats.current_lead_id`) |
| `lead_open_only` | `true` → открытый лид (`closed_at IS NULL`); `false` → закрытый или нет лида |
| `assigned_user_id` | legacy `last_handled_by_user_id` (в scope актора) |
| `contact_id` | фильтр по контакту |
| `bot_id` | фильтр по боту |
| `unread_only=true` | **per-operator:** только `chat_read_state` vs последнее сообщение (как `unread_for_me`). Без сообщений чат не попадает в выборку. `POST /chats/{id}/read` обновляет только `chat_read_state`. |
| `sort=unread_first` | Сначала чаты с `unread_for_me=true` для актора, затем `last_message_at` desc, `id` desc. Требует аутентификацию (per-operator). |
| `needs_reply=true` | JOIN `contact_group_assignments`: `pending_inbound_at IS NOT NULL` OR `escalated_to_group_at IS NOT NULL` |
| `card_owner_user_id` | JOIN `contact_group_assignments` по `(contact_id, assigned_group_id)` → `owner_user_id` («мои карточки») |
| `assigned_group_id` | фильтр по группе чата (senior/admin; user — только своя группа в scope) |
| `q` | ilike по `last_message_preview` (не FTS; см. `/chats/search`) |
| `sort` | `last_message_at_desc` (default) \| `created_at_desc` \| `unread_first` (per-operator unread, см. выше) |
| `cursor` | keyset pagination (`last_message_at` + `id` для `last_message_at_desc`; `created_at` + `id` для `created_at_desc`; для `unread_first` cursor не поддерживается) |

Scope (`ownership_v2`): user видит **все чаты своей группы**, не только назначенные на себя. Фильтр `card_owner_user_id` сужает до «мои карточки».

Resp (фактическая схема API):
```json
{
  "items": [
    {
      "id": 101,
      "contact_id": 7,
      "contact_name": "Иван",
      "bot_id": 2,
      "assigned_user_id": 5,
      "assigned_group_id": 3,
      "assigned_department_id": 1,
      "card_owner_user_id": 5,
      "card_owner_name": "Аня",
      "card_owner_group_id": 3,
      "status": "open",
      "status_id": 2,
      "chat_label": { "status_id": 2, "code": "new_client", "label": "Новый клиент" },
      "current_lead": {
        "id": 42,
        "status_id": 12,
        "label": "В работе",
        "closed_at": null
      },
      "last_message_at": "...",
      "last_message_preview": "Здравствуйте, ...",
      "unread_for_me": true
    }
  ],
  "next_cursor": null
}
```

Поля непрочитанного:
| Поле | Описание |
|------|----------|
| `unread_for_me` | **per-operator (канон для UI):** `true`, если есть сообщения и у актора нет `chat_read_state` или `last_read_message_id` < id последнего сообщения. Бейдж, `unread_only`, `sort=unread_first`. |

### `GET /api/v1/search`
Глобальный поиск по контактам, сообщениям и чатам в одном запросе. **Rate-limit:** 60 req/min на `user_id` (in-memory fallback при недоступности Redis; см. `RBAC_MATRIX.md` §4).

Query:
| Параметр | Описание |
|----------|----------|
| `q` | min 2 символа |
| `types` | `contacts,messages,chats` (comma-separated; default — все три) |
| `limit_per_type` | default 10, max 25 |
| `contacts_cursor` | keyset для секции `contacts` |
| `messages_cursor` | keyset для секции `messages` (как `/chats/search`) |
| `chats_cursor` | keyset для секции `chats` (`last_message_at` + `id`) |

RBAC: `contacts` — `CONTACTS_READ` + scope `visible_user_ids`; `messages` — FTS + `CHATS_READ_*` + default scope (`group`/`department`/`all`); `chats` — ilike по `last_message_preview` и `contacts.full_name` + `CHATS_READ_*`.

Resp:
```json
{
  "contacts": { "items": [...], "next_cursor": null },
  "messages": { "items": [...], "next_cursor": null },
  "chats": { "items": [...], "next_cursor": null }
}
```

Секции, не запрошенные в `types`, возвращаются пустыми (`items: []`, `next_cursor: null`).

### `GET /api/v1/chats/search`
Полнотекстовый поиск по телу сообщений (Postgres FTS, lexer `russian`). Отдельно от preview-фильтра `GET /chats?q=` (ilike по `last_message_preview`).

Query: `q` (min 2 символа), `scope=mine|group|department|all` (по умолчанию: `group` для operator, `department` для senior, `all` для admin), `cursor`, `limit` (≤50, default 20), `highlight=true|false` (snippet с `<mark>` или plain).

RBAC: те же permissions, что `GET /chats` (`CHATS_READ_*`). Scope сужает выдачу внутри видимости актора (чужие группы не отдаются).

Resp:
```json
{
  "items": [
    {
      "chat_id": 101,
      "contact_id": 7,
      "message_id": 555,
      "snippet": "Договорились о <mark>согласованности</mark> поставки",
      "matched_at": "2026-05-17T12:00:00Z",
      "card_owner_user_id": 5
    }
  ],
  "next_cursor": "..."
}
```

### `POST /api/v1/chats/{id}/read`
Отметить чат прочитанным для текущего оператора.

Req (optional):
```json
{ "last_read_message_id": 555 }
```
Если `last_read_message_id` не передан — берётся последнее сообщение в чате.

Resp 200: `{ "chat_id", "user_id", "last_read_message_id", "read_at" }`. WS: `chat.read`, `chat.updated`.

### `GET /api/v1/chats/{id}`
Полная карточка чата.

### `GET /api/v1/chats/{id}/messages?limit=50&before=<cursor>`
Cursor-paged список сообщений.

### `POST /api/v1/chats/{id}/messages`
Req:
```json
{
  "body": "текст",
  "attachments": [{ "file_id": 123 }],
  "client_message_id": "uuid-от-клиента"
}
```
- `client_message_id` — для идемпотентности при повторной отправке.
- 200 → объект `Message` со статусом `queued`.
- 403 если takeover активен и актор — не takeover-юзер.

### `PATCH /api/v1/chats/{id}/status`
```json
{ "status": "open" }
```
Legacy enum `open` \| `in_progress` \| `closed` \| `archived`.

### `PATCH /api/v1/chats/{id}/status_id`
```json
{ "status_id": 4 }
```
Только `statuses` с `kind = chat_label` и `is_active = true`. Иначе `422` (`validation_error`).

### `POST /api/v1/chats/{id}/takeover` (senior, admin)
Перехват:
```json
{ }
```
409 если уже активен другой takeover.

### `DELETE /api/v1/chats/{id}/takeover` (senior, admin)
Снять свой/любой takeover (admin — любой).

### Legacy chat transfer routes (удалены в фазе 2)

Маршруты `POST /api/v1/chats/{id}/transfers`, `/transfer/request`, `/transfers/{id}/*`, `/transfer/force` **не зарегистрированы** (404).

Канон: `POST /api/v1/contacts/{id}/groups/{group_id}/transfers` — см. [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md), [`LEGACY_OWNERSHIP_REMOVAL.md`](LEGACY_OWNERSHIP_REMOVAL.md).

Req для admin:
```json
{ "to_user_id": 8, "force": true, "comment": "..." }
```

### `GET /api/v1/transfers?state=pending_senior|pending_recipient&direction=incoming`
Получить релевантные transfer'ы (входящие мне на апрув / на принятие).

### `POST /api/v1/transfers/{id}/approve` (senior отдела, admin)
Senior-step ОК → переход в `pending_recipient`, событие принимающему.

### `POST /api/v1/transfers/{id}/decline` (senior отдела, admin)
Senior-step отказ → `state='declined_senior'`.

### `POST /api/v1/transfers/{id}/accept` (recipient)
Принимающий принял → `state='accepted'`, чат меняет `current_user_id`.

### `POST /api/v1/transfers/{id}/reject` (recipient)
Принимающий отказался → `state='declined_recipient'`.

### `POST /api/v1/transfers/{id}/cancel` (requested_by)
Отозвать своё предложение, пока ещё в `pending_*`.

---

## 8. Contacts

### `GET /api/v1/contacts`
Query: `?q=&status_id=&page=&size=`. Скоп по видимости.
Поле `telegram_user_id` присутствует только для admin.

### `GET /api/v1/contacts/{id}`
Query: `embed_leads=true` — последние 5 лидов в scope актора (без `title`/`status` чужих групп).

Включает: основные поля, `custom_fields`, `chats_summary`, **`group_ownership`**: `[{ group_id, group_name, owner_user_id, owner_full_name, pending_inbound_at, escalated_at }]`, **`crm_summary`**: `{ prior_leads_count, first_registered_at }`.

- `prior_leads_count` — COUNT закрытых лидов по `contact_id` **без** фильтра по группе (для любого, кто видит контакт).
- `first_registered_at` — `contacts.created_at`.

Без `telegram_user_id`, кроме admin.

### `POST /api/v1/contacts/{id}/groups/{group_id}/transfers`
Передача **владения карточкой** внутри группы `group_id` (не затрагивает другие группы).
```json
{ "to_user_id": 8, "comment": "Уезжаю в отпуск" }
```
Flow: как §7 transfers (senior approve + recipient accept). Admin: `"force": true`.

### `GET /api/v1/contact-transfers?state=...&group_id=`
Inbox transfer'ов карточек (senior / recipient).

### `GET /api/v1/contacts/{id}/groups/{group_id}/reply-audit`
История исходящих с полями: `author`, `card_owner_at_send`, `is_on_behalf`, `chat_id`, `created_at`.

### `GET /api/v1/groups/{id}/escalation-settings` (senior, admin)
### `PATCH /api/v1/groups/{id}/escalation-settings` (senior, admin)
```json
{
  "first_response_timeout_minutes": 15,
  "new_contact_reassign_strategy": "first_responder"
}
```

### `POST /api/v1/contacts`
Создание вручную.

### `PATCH /api/v1/contacts/{id}`
Любое изменение поля → запись в `contact_field_changes`. Для `custom_fields` пишем разницу по ключам.

### `GET /api/v1/contacts/{id}/history`
Список изменений полей с автором и timestamp.

### `DELETE /api/v1/contacts/{id}`
Soft delete. Senior — только если все чаты в его отделе. Admin — всегда.

---

## 9. Leads (фаза 8)

> Канон: [`LEADS.md`](LEADS.md). Схема: [`DATABASE.md`](DATABASE.md) §6–7.

Права: `contacts.read` (список/детали), `contacts.update` (создание, patch, close). Scope группы — как у чатов; чужая группа на detail → `404`.

### `GET /api/v1/contacts/{id}/leads`
Список лидов контакта в **видимых** группах актора. Cursor keyset: `created_at` + `id` (desc).

Query (все опциональны, **AND**):

| Параметр | Описание |
|----------|----------|
| `group_id` | фильтр по группе (вне scope → `403`) |
| `status_id` | этап `lead_pipeline` |
| `open_only` | `true` / `false` → фильтр по `closed_at` |
| `cursor`, `limit` | default `limit=50`, max `100` |

Для лидов **вне** scope группы актора в списке не отдаются `title`, `status_id`, `status_code`, `status_label`, `custom_fields` (только `id`, `group_id`, даты).

Resp:
```json
{
  "items": [
    {
      "id": 42,
      "contact_id": 7,
      "group_id": 3,
      "chat_id": 101,
      "status_id": 12,
      "status_code": "in_progress",
      "status_label": "В работе",
      "title": "Сделка #1",
      "closed_at": null,
      "created_at": "..."
    }
  ],
  "next_cursor": null
}
```

### `POST /api/v1/contacts/{id}/leads`
Ручное создание (senior/admin или user **своей** группы).

Req:
```json
{ "group_id": 3, "bot_id": 2, "title": "Сделка вручную" }
```
Чат ищется по `(contact_id, assigned_group_id[, bot_id])`. Default `status_id` = `lead_pipeline` / `new`. `409`, если открытый лид на `(contact_id, group_id)` уже есть.

### `GET /api/v1/leads/{id}`
Детали лида; контакт должен быть виден, `lead.group_id` ∈ scope → иначе `404`.

### `PATCH /api/v1/leads/{id}`
```json
{ "status_id": 12, "title": "...", "custom_fields": { "key": "value" } }
```
`status_id` — только `lead_pipeline`, только открытый лид. Публикует `lead.status_changed`.

### `POST /api/v1/leads/{id}/close`
`closed_at = now()`, `chats.current_lead_id` → `NULL`. Публикует `lead.closed`.

### `crm_summary` на контакте
См. `GET /api/v1/contacts/{id}` — не отдельный endpoint.

### `GET /api/v1/crm-summary`
Глобальные агрегаты дашборда в scope актора (RBAC как у списка лидов). **Без** PII и списков чужих лидов.

**Response 200:**
```json
{
  "open_leads_count": 12,
  "closed_today_count": 3,
  "by_pipeline_status": [
    { "status_id": 5, "code": "new", "label": "Новый", "count": 8 }
  ]
}
```

| Поле | Описание |
|------|----------|
| `open_leads_count` | Открытые лиды (`closed_at IS NULL`) в видимых группах |
| `closed_today_count` | Закрытые сегодня (UTC) в scope |
| `by_pipeline_status` | До **5** этапов воронки по убыванию `count` (только открытые лиды) |

**Scope:** user — своя группа; senior — отдел; admin — все группы.

**Rate limit:** `GET /contacts/{id}/leads` — 60/min per user; `POST /contacts/{id}/leads` — 30/min (см. [`SECURITY_CHECKLIST.md`](SECURITY_CHECKLIST.md) S-LEAD-6).

---

## 10. Statuses

### `GET /api/v1/statuses?kind=chat_label|lead_pipeline`
Справочник статусов. Query: `include_inactive` (default `false`), `kind` (опционально — только `chat_label` или `lead_pipeline`; без фильтра — все виды).

`StatusOut` включает поле `kind`.

### `POST /api/v1/statuses` (admin)
```json
{
  "code": "vip_client",
  "kind": "chat_label",
  "label": "VIP клиент",
  "color": "#FFD700",
  "sort_order": 20
}
```
`kind` default `lead_pipeline`. Уникальность — пара `(code, kind)`.

### `PATCH /api/v1/statuses/{id}` (admin)
### `DELETE /api/v1/statuses/{id}` (admin)

`kind` нельзя сменить у записи, на которую ссылаются `chats` / `leads`.

### Ошибки kind на чатах и лидах
| Endpoint | `status_id` | Ошибка |
|----------|-------------|--------|
| `PATCH /api/v1/chats/{id}/status_id` | только `chat_label`, active | `422` если `lead_pipeline`, inactive или не найден |
| `PATCH /api/v1/leads/{id}` | только `lead_pipeline`, active, открытый лид | `422` если `chat_label`, inactive или не найден |

---

## 11. Files

### `POST /api/v1/files`
Multipart upload. Resp:
```json
{ "id": 12, "original_name": "...", "mime": "...", "size_bytes": 12345 }
```

### `GET /api/v1/files/{id}`
Возвращает короткоживущий presigned URL (5 минут) на MinIO.

---

## 12. Audit

### `GET /api/v1/audit?actor_id=&entity_type=&entity_id=&from=&to=&page=&size=`
Скоп по роли.

---

## 13. Bot events ingest (внешние боты → CRM)

### `POST /api/v1/bot-events`

Внешний endpoint для ботов. Полный контракт — [`BOTS_INTEGRATION.md`](BOTS_INTEGRATION.md).

Заголовки (обязательны):
- `X-Bot-Code` — код бота;
- `X-Bot-Timestamp` — UNIX seconds (anti-replay ±60 сек);
- `X-Bot-Event-Id` — ULID/UUID для идемпотентности 24 часа;
- `X-Bot-Signature` — `sha256=<hex>` HMAC от canonical-строки с `inbound_secret`.

Сервер:
1. Находит бота по `code`, проверяет `is_active`, IP allowlist.
2. Проверяет `Timestamp`, HMAC через `compare_digest`.
3. Проверяет `X-Bot-Event-Id` в `bot_events_inbox` (идемпотентность).
4. Маршрутизирует по `event` (см. `BOTS_INTEGRATION.md` §4.3).
5. Для `message.received` зовёт `chats_service.ingest_incoming_message(...)` и ставит ARQ job скачивания вложений.
6. Отвечает `200 {"status":"ok"}` (или `"duplicate"`).

Ошибки: `400` невалидный JSON, `401` HMAC/timestamp, `403` bot/IP, `409` конфликт состояния, `429` rate-limit, `5xx` внутренняя ошибка (бот должен ретраить).

SLA: ответ ≤ 2 сек p95.

---

## 14. WebSocket

### Connect: `wss://<host>/ws?ticket=<ws-ticket>`

После connect клиент получает событие `connected`:
```json
{ "type": "connected", "user_id": 1, "server_time": "..." }
```

Клиент шлёт heartbeat раз в 20 сек:
```json
{ "type": "ping" }
```
Сервер отвечает:
```json
{ "type": "pong" }
```

### Серверные события (push)

| Тип | Кому | Payload (схема) |
|---|---|---|
| `message.created` | актору, у которого этот чат видим | `{ chat_id, message }` |
| `message.status_changed` | автору сообщения | `{ chat_id, message_id, status, telegram_message_id?, failure_reason? }` |
| `chat.updated` | актору | `{ chat: {...} }` (status, current_user_id, takeover_user_id, last_message_*, unread_count) |
| `chat.takeover_started` | старому current_user_id | `{ chat_id, by_user_id }` |
| `chat.takeover_ended` | старому current_user_id | `{ chat_id }` |
| `transfer.requested_to_senior` | senior'у отдела | `{ transfer: {...} }` |
| `transfer.requested_to_recipient` | recipient | `{ transfer: {...} }` |
| `transfer.accepted` | from_user, recipient, senior, admin (если в скопе) | `{ transfer: {...} }` |
| `transfer.declined` | связанным | `{ transfer: {...}, reason: "senior"|"recipient" }` |
| `transfer.expired` | связанным | `{ transfer_id }` |
| `lead.created` | группа / владелец карточки | `{ lead_id, contact_id, group_id, chat_id?, status_id }` |
| `lead.status_changed` | то же | `{ lead_id, from_status_id, to_status_id }` |
| `lead.closed` | то же | `{ lead_id, closed_at, chat_id? }` |
| `presence.changed` | актору | `{ user_id, presence }` |

Клиент шлёт только `ping`. Все мутации — через REST. WS — однонаправленный для серверных пушей (упрощает auth и rate-limit).

---

## 15. Observability (не `/api/v1`)

| Endpoint | Auth | Описание |
|---|---|---|
| `GET /healthz` | нет | Liveness: `status` `ok` \| `degraded`, checks `db`, `redis` |
| `GET /readyz` | нет | Readiness: `200` + `status: ready` если db и redis доступны; иначе `503` + `not_ready` |
| `GET /metrics` | нет | Prometheus text exposition; **404**, если `METRICS_ENABLED=false` |

Метрики (при `METRICS_ENABLED=true`):

| Имя | Тип | Labels | Назначение |
|---|---|---|---|
| `http_requests_total` | counter | method, handler, status | HTTP (instrumentator) |
| `http_request_duration_seconds` | histogram | method, handler | HTTP latency (instrumentator) |
| `bot_events_ingest_total` | counter | `status` | `accepted`, `duplicate`, `rejected` |
| `bot_outbound_total` | counter | `status` | `sent`, `failed`, `retry` |
| `ws_connections_active` | gauge | — | активные WS |
| `redis_stream_pending` | gauge | `stream` | XPENDING для `crm:bots:jobs`, `crm:jobs` |

---

## 16. Версионирование контракта

- Префикс `/api/v1` фиксируется на жизненный цикл проекта.
- Breaking-changes — `/api/v2`, оба живут параллельно при необходимости.
- Дополнения (новые поля) — non-breaking, без бампа версии. Фронт обязан игнорировать незнакомые поля.

---

## 17. Слабые места контракта

1. **Поле `telegram_user_id` появляется/пропадает в зависимости от роли** — может удивить фронт. Документировать явно, добавить sentry-алёрт «пришёл tg_user_id не-админу» (никогда не должно быть).
2. **WS-события дублируют состояние из REST** — фронт может уйти в рассинхрон. Решение: при `chat.updated` фронт не доверяет полю слепо, а помечает чат «грязным» и при открытии перезапрашивает.
3. **Heartbeat 20 секунд** — Traefik по умолчанию закрывает idle WS через 60 сек. Согласовать.
4. **`force=true` при transfer** — нужно гарантировать аудит. Сервис обязан писать `audit_log.action='chat.transfer.force'` независимо.
5. **Cursor-based пагинация и удаление сообщений** — не делаем delete сообщений (в принципе), иначе курсор может сломаться.
