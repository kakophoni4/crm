# Лиды (Leads) — канон фазы 8

> **Сделка = лид.** Один контакт в группе может иметь несколько лидов во времени (повторные обращения после закрытия). Активный лид — единственный с `closed_at IS NULL` на паре `(contact_id, group_id)`.
>
> Связанные документы: [`DATABASE.md`](DATABASE.md) §6–7, [`API_CONTRACT.md`](API_CONTRACT.md) §9, [`EVENTS.md`](EVENTS.md) §3.8, [`RBAC_MATRIX.md`](RBAC_MATRIX.md), [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md), [`ROADMAP.md`](ROADMAP.md) фаза 8, приёмка — [`teams/07_qa.md`](teams/07_qa.md) §11.

---

## 1. Глоссарий

| Термин | Описание |
|--------|----------|
| **Contact (Контакт)** | Глобальная карточка клиента. Владение и scope — per **group** → [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md). |
| **Chat (Чат)** | Тред `(contact_id, bot_id)`. Группа чата — из `assigned_group_id` / владельца бота. UI показывает **активный лид** через `chats.current_lead_id`. |
| **Lead (Лид)** | Одна «сделка» / цикл работы с клиентом **в рамках группы**: `(contact_id, group_id)`. Имеет воронку (`status_id` → `lead_pipeline`), даты открытия/закрытия, привязку сообщений. |
| **chat_label** | Вид справочника `statuses.kind = 'chat_label'`. Значение `chats.status_id` — **не воронка**, а метка диалога: «новый клиент», «постоянный клиент» (default — «новый»). |
| **lead_pipeline** | Вид справочника `statuses.kind = 'lead_pipeline'`. Значение `leads.status_id` — этап воронки сделки (новый → в работе → … → закрыт). |
| **crm_summary** | Агрегированная сводка для дашборда (счётчики открытых лидов, по статусам воронки) **без** раскрытия чужих лидов вне scope актора. |

---

## 2. Правила домена

### 2.1 Создание лида: `ensure_lead` на inbound

При обработке входящего сообщения (`message.received` → ingest):

1. Определить `contact_id`, `group_id` чата (scope группы бота / `assigned_group_id`).
2. Найти **открытый** лид: `SELECT … FROM leads WHERE contact_id = ? AND group_id = ? AND closed_at IS NULL LIMIT 1`.
3. **Если нет** — `INSERT` новый лид (`opened_at = now()`, `status_id` = default этап воронки, `source = 'inbound'`).
4. **Если есть** — использовать его id.
5. Обновить `chats.current_lead_id` на id этого лида.
6. Записать сообщение с `messages.lead_id = <lead_id>` (после cutover — обязательно, см. §2.3).

Псевдокод:

```text
lead = find_open_lead(contact_id, group_id)
if lead is None:
    lead = insert_lead(...)
chat.current_lead_id = lead.id
message.lead_id = lead.id
```

### 2.2 Повторное обращение после закрытия

**Если последний лид по `(contact_id, group_id)` закрыт** (`closed_at IS NOT NULL`) **и нет другого открытого**:

- Следующее **inbound**-сообщение создаёт **новый** лид (новый `INSERT`), а не переоткрывает старый.
- `chats.current_lead_id` переключается на новый лид.
- История переписки в чате сохраняется; сообщения старого цикла остаются с `lead_id` закрытого лида.

Явное правило: **один открытый лид на пару (contact, group)**; закрытие финализирует цикл; новый цикл = новый row в `leads`.

Исходящее без предшествующего inbound в новом цикле (оператор пишет первым после закрытия): тот же `ensure_lead` — при отсутствии открытого лида создаётся лид с `source = 'outbound'` или `'manual'`.

### 2.3.1 Фильтр сообщений по лиду (v1.1)

`GET /api/v1/chats/{chat_id}/messages?lead_id=<id>` — только сообщения указанного лида (тот же контакт; при `assigned_group_id` на чате — лид той же группы). Чужой `lead_id` → **404**.

UI: табы «Текущая сделка» / «Весь чат» (`messageScope` в operator SPA).

Автотесты: `tests/leads/test_messages_lead_filter.py`, `frontend/tests/unit/chats.messages-scope.spec.ts`.

### 2.3 Сообщения и cutover `lead_id`

| Период | `messages.lead_id` |
|--------|---------------------|
| До cutover (backfill) | `NULL` допустим для исторических строк |
| После cutover ф.8 | **NOT NULL** для всех **новых** `inbound` и `outbound` |

Cutover = деплой кода, который всегда вызывает `ensure_lead` перед insert сообщения. Backfill проставляет `lead_id` для активных чатов (§6).

### 2.4 `chats.current_lead_id`

- Указывает на **активный** (открытый) лид в UI списка чатов и шапки чата.
- При закрытии лида: `current_lead_id` → `NULL` до следующего inbound/outbound с `ensure_lead`.
- Не путать с владельцем карточки (`contact_group_assignments`) и с `last_handled_by_user_id`.

### 2.5 Разделение статусов чата и лида

| Поле | Справочник | Назначение |
|------|------------|------------|
| `chats.status_id` | только `statuses` с `kind = 'chat_label'` | Метка клиента в списке чатов; default — код «новый» (новый клиент) |
| `leads.status_id` | только `statuses` с `kind = 'lead_pipeline'` | Воронка сделки; смена через API/ UI лида |

Сервисный слой **отклоняет** присвоение `lead_pipeline` на `chats.status_id` и `chat_label` на `leads.status_id`.

### 2.6 `PATCH /chats/{id}/status_id` (только `chat_label`)

Эндпоинт `PATCH /api/v1/chats/{chat_id}/status_id` с телом `{ "status_id": <int> }`:

- Перед записью вызывается `ensure_status_kind(..., StatusKind.CHAT_LABEL)` в `ChatService.update_status_id`.
- Статус с `kind = 'lead_pipeline'` → **422** `validation_error` (сообщение упоминает `chat_label`).
- Воронка сделки меняется только через `PATCH /api/v1/leads/{id}` (`status_id` → `lead_pipeline`).

Автотест: `tests/leads/test_status_kind_validation.py::test_patch_chat_status_id_rejects_lead_pipeline`.

> Legacy `PATCH /chats/{id}/status` (enum `ChatStatus`) — отдельный путь; для меток справочника используйте `status_id`.

### 2.7 Audit events (`audit_log`)

Записи в `audit_log` через декоратор `@audit` (см. `app/modules/audit/decorator.py`). Enum `audit_action` расширен миграциями `0020` / `0021`.

| `audit_action` | Когда | Эндпоинт / путь |
|----------------|--------|------------------|
| `lead.close` | Закрытие лида | `POST /api/v1/leads/{id}/close` |
| `lead.status.update` | Смена только `status_id` воронки | `PATCH /api/v1/leads/{id}` (только `status_id`) |
| `lead.create` | Ручное создание лида | `POST /api/v1/contacts/{id}/leads` |
| `lead.update` | PATCH полей `title` / `custom_fields` (без смены статуса или вместе с ним, кроме «только status») | `PATCH /api/v1/leads/{id}` |

Правило выбора action на PATCH: `_resolve_patch_audit_action` в `LeadApiService` — «только `status_id`» → `lead.status.update`; иначе при наличии полей → `lead.update`; пустой PATCH → audit skip.

Inbound `ensure_lead` **не** пишет `lead.create` в audit (только WS `lead.created`).

Автотесты: `tests/leads/test_lead_audit.py`.

---

## 3. RBAC и `crm_summary`

### 3.1 Список и детали лидов

- **User:** `GET /leads` и `GET /leads/{id}` только по `group_id` ∈ видимых группах актора (та же модель scope, что у чатов — см. [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md)).
- **Senior:** лиды отдела (все группы отдела).
- **Admin:** все лиды.

Создание лида вручную, смена статуса, закрытие — в scope группы лида; чужая группа → `404` (не `403`, единообразно с чатами).

**Старший** может менять статус и закрывать сделку по любому лиду **своего отдела**, даже если он **не владелец карточки** (`contact_group_assignments.owner_user_id`). Проверка — scope отдела / видимость чата, не card owner.

### 3.2 `crm_summary`

`GET /api/v1/crm-summary` (или вложенный ресурс — см. [`API_CONTRACT.md`](API_CONTRACT.md)):

- Возвращает **агрегаты**: `open_leads_count`, `by_pipeline_status: [{ status_id, code, count }]`, опционально `closed_today_count`.
- Scope такой же, как у списка лидов: user — своя группа; senior — отдел; admin — глобально.
- **Не** отдаёт списки чужих лидов, PII контактов и preview сообщений — только счётчики.

---

## 4. Retention (v1.2 production)

| Элемент | Поведение |
|---------|-----------|
| `leads.retention_expires_at` | `NULL` = хранить бессрочно; при закрытии лида выставляется, если задан `LEAD_RETENTION_DAYS` |
| App setting `LEAD_RETENTION_DAYS` | `int \| None`, default `NULL` (= не выставлять срок) |
| `LEAD_PURGE_ENABLED` | default `false` — job **никогда не DELETE**; при `true` — реальный purge |
| Purge job | `purge_expired_leads` в `run_periodic_maintenance` |

**DELETE (только при `LEAD_PURGE_ENABLED=true`):**

```sql
DELETE FROM leads
WHERE closed_at IS NOT NULL
  AND retention_expires_at IS NOT NULL
  AND retention_expires_at < now();
```

**Политика сообщений:** строки `messages` **не удаляются**. FK `messages.lead_id` → `leads.id` с `ON DELETE SET NULL`: после purge `lead_id` становится `NULL`, текст и вложения сохраняются (anonymize не применяется).

При `POST /leads/{id}/close`: если `LEAD_RETENTION_DAYS = N > 0`, то `retention_expires_at = closed_at + N days`.

Автотесты: `tests/leads/test_lead_retention.py` (`stub` при `false`, `deletes` при `true`).

---

## 5. События WebSocket / шина

Realtime-типы (WS push, см. [`EVENTS.md`](EVENTS.md)):

| Тип | Когда |
|-----|--------|
| `lead.created` | После `INSERT` лида (`ensure_lead` или ручное создание) |
| `lead.status_changed` | `PATCH` статуса воронки |
| `lead.closed` | Установка `closed_at` / финальный статус «закрыт» |

Каналы доставки: `group.{group_id}`, `user.{owner}` (если есть владелец карточки), `chat.{chat_id}` при открытом чате.

---

## 6. Миграция и backfill

**Цель:** один открытый лид на каждый **активный** чат группы (есть сообщения или `last_message_at IS NOT NULL`, чат не archived).

Алгоритм backfill (одна транзакция на батч):

1. Для каждого `chat` с `assigned_group_id` и активностью:
   - `contact_id`, `group_id` из чата.
   - Если уже есть открытый лид на пару — привязать `chats.current_lead_id`, проставить `messages.lead_id` где `NULL` (опционально только за последние N дней — зафиксировать в миграции).
   - Иначе `INSERT` lead (`opened_at` = `chat.created_at` или `last_message_at`, `status_id` = default pipeline, `source = 'migration'`).
2. `UPDATE chats SET current_lead_id = lead.id`.
3. `UPDATE messages SET lead_id = lead.id WHERE chat_id = chat.id AND lead_id IS NULL` (для активных чатов).

После backfill — включить NOT NULL constraint на `messages.lead_id` **только для новых** строк (CHECK или триггер + cutover в приложении).

Seed справочника:

- `chat_label`: `new_client` («Новый клиент»), `returning_client` («Постоянный клиент») — default на чатах без метки → `new_client`.
- `lead_pipeline`: `new`, `in_progress`, `waiting_client`, `done`, `cancelled` (точный набор — в миграции seed).

---

## 7. OUT OF SCOPE / TODO (после ф.8)

| Задача | Описание |
|--------|----------|
| **ARQ purge** | Фоновая job по `retention_expires_at` / `LEAD_RETENTION_DAYS` — v1.1+; в ф.8 колонка только в схеме. |
| **Department-бот** | Бот с `owner_type = department` / без ровно одной группы: при **0** группах — synthetic `__department_inbox__`; при **2+** группах — чат и владение на одной из реальных групп (с доступным staff), не inbox. |

### Department-боты (v1.2 decision — вариант 1)

| Решение | Детали |
|---------|--------|
| **Ingest, 0 групп** | Чат: `assigned_group_id = NULL` → synthetic `__department_inbox__` для лида и ownership. |
| **Ingest, 2+ групп** | Чат и лид на одной из реальных групп бота (предпочтение группам с available staff); inbox не используется. |
| **Ingest, 1 группа** | Как group-бот: чат/лид/ownership на этой группе. |
| **RBAC** | Лид виден по `leads.group_id` / scope группы; для inbox — senior отдела. |

Вариант 2 (`leads.department_id` nullable) **не выбран** — схема `leads.group_id NOT NULL` сохранена.

Автотест: `tests/leads/test_department_bot_synthetic_group.py`.

---

## 8. Слабые места

1. **Гонка двух inbound** без уникального индекса на открытый лид — возможны два открытых лида. Митигация: partial unique `UNIQUE (contact_id, group_id) WHERE closed_at IS NULL`.
2. **Длинные чаты с одной «сделкой»** — оператор может закрыть лид, а клиент пишет в тот же тред; UX должен явно показывать «новую сделку».
3. **crm_summary** — Redis TTL 5 min (`CRM_SUMMARY_CACHE_*`); при отключении кэша — live COUNT.
4. **Retention отложен** — таблица `leads` растёт бессрочно до включения purge.
5. **Backfill lead_id на старые сообщения** — объём UPDATE; батчи по `chat_id`, окно maintenance.
