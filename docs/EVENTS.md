# Шина событий

> Внутренняя шина для коммуникации между модулями монолита **и** для realtime-доставки в UI. Транспорт: Redis Pub/Sub. Долгоиграющие задачи (отправка боту, скачивание медиа, аудит) — отдельно через ARQ.

---

## 1. Зачем

1. **Decoupling.** Модуль `chats` не знает про модуль `audit`. Он публикует событие, аудит подписан и пишет в БД. Это даёт лёгкий выезд в микросервисы.
2. **Realtime.** WS Hub подписан на каналы `user.{id}` и `chat.{id}` — все события автоматически летят в браузер.
3. **Аудит.** Подписчик `audit` пишет всё в `audit_log`.
4. **Notifications.** Подписчик `notifications` отправляет push/email/Telegram.

---

## 2. Транспорты

| Тип задачи | Транспорт | Гарантии |
|---|---|---|
| Realtime UI обновление | Redis Pub/Sub | At-most-once. Потеря приемлема — UI всё равно перерисуется при reload. |
| Аудит-запись | **Outbox-таблица** + ARQ | At-least-once. Не теряется. |
| Отправка боту | ARQ job | At-least-once с идемпотентностью по `request_id` (см. `BOTS_INTEGRATION.md`). |
| Уведомления (email/push) | ARQ job | At-least-once. |

> **Outbox-паттерн.** Когда мы пишем сущность в БД, в той же транзакции пишем запись в `events_outbox`. Отдельный воркер вычитывает outbox и публикует/обрабатывает. Это гарантирует, что событие либо есть, либо нет — не бывает «БД написал, но событие не отправил».

### `events_outbox`
| Поле | Тип |
|---|---|
| id | BIGINT PK |
| topic | TEXT |
| payload | JSONB |
| created_at | TIMESTAMPTZ |
| processed_at | TIMESTAMPTZ NULL |
| attempts | INT DEFAULT 0 |
| last_error | TEXT NULL |

---

## 3. Каталог событий

Формат имени: `<entity>.<action>` в lowercase. Все события — JSON. Обязательные поля:
```json
{
  "event": "chat.message.received",
  "event_id": "ulid",
  "occurred_at": "2026-05-16T12:34:56Z",
  "actor_id": 5,                    // null для системных
  "payload": { ... }                // схема зависит от event
}
```

### 3.1 Auth
| Событие | Когда | payload |
|---|---|---|
| `auth.login` | успешный login | `{ user_id, ip, ua }` |
| `auth.logout` | logout | `{ user_id, jti }` |
| `auth.force_logout` | force-logout | `{ target_user_id, by_user_id }` |
| `auth.password_changed` | смена пароля | `{ user_id }` |

### 3.2 Org
| Событие | payload |
|---|---|
| `department.created` | `{ department_id, name, head_user_id }` |
| `department.updated` | `{ department_id, changes }` |
| `department.deleted` | `{ department_id }` |
| `department.head_assigned` | `{ department_id, user_id }` |
| `group.created` | `{ group_id, department_id, name }` |
| `group.updated` | |
| `group.deleted` | |
| `user.created` | `{ user_id, email, role, group_id }` |
| `user.updated` | `{ user_id, changes }` |
| `user.disabled` | `{ user_id, by_user_id }` |
| `user.moved_group` | `{ user_id, from_group_id, to_group_id }` |

### 3.3 Bots
| Событие | payload |
|---|---|
| `bot.added` | `{ bot_id, code, owner_type, owner_id }` |
| `bot.updated` | `{ bot_id, changes }` |
| `bot.activated` / `bot.deactivated` | `{ bot_id }` |
| `bot.secret_rotated` | `{ bot_id, which: 'inbound'|'outbound'|'both' }` |
| `bot.health_changed` | `{ bot_id, alive: bool }` |
| `bot.signature_invalid` | `{ bot_id, ip, reason }` (для security-алёрта) |
| `bot.removed` | `{ bot_id }` |

### 3.4 Chats / Messages
| Событие | payload |
|---|---|
| `chat.created` | `{ chat_id, contact_id, bot_id, current_user_id }` |
| `chat.assigned` | DEPRECATED → `contact.ownership.assigned` |
| `contact.ownership.assigned` | `{ contact_id, group_id, owner_user_id, source }` |
| `contact.ownership.transferred` | `{ contact_id, group_id, from_user_id, to_user_id }` |
| `contact.ownership.reassigned` | `{ contact_id, group_id, old_owner, new_owner, reason: 'timeout' }` |
| `contact.escalation.owner_notify` | `{ contact_id, group_id, owner_user_id, chat_id }` |
| `contact.escalation.group_notify` | `{ contact_id, group_id, chat_id, pending_since }` |
| `message.replied.on_behalf` | `{ message_id, chat_id, card_owner_user_id, author_user_id }` |
| `chat.status_changed` | `{ chat_id, from_status_id, to_status_id }` |
| `chat.takeover_started` | `{ chat_id, takeover_user_id, displaced_user_id }` |
| `chat.takeover_ended` | `{ chat_id, takeover_user_id }` |
| `chat.message.received` | `{ chat_id, message_id, contact_id, attachments_pending: int }` |
| `chat.message.created` | `{ chat_id, message_id, author_user_id }` (исходящее, queued) |
| `chat.message.status_changed` | `{ message_id, status, external_id?, failure_code?, failure_reason? }` |
| `chat.message.attachment_ready` | `{ message_id, attachment_index, file_id }` (после скачивания из URL бота в MinIO) |
| `chat.message.attachment_failed` | `{ message_id, attachment_index, reason }` |

### 3.5 Transfers (карточка в группе)
| Событие | payload |
|---|---|
| `contact.transfer.requested` | `{ transfer_id, contact_id, group_id, from, to, requested_by, state }` |
| `transfer.requested` | DEPRECATED (chat-level) |
| `transfer.senior_approved` | `{ transfer_id, senior_id }` |
| `transfer.senior_declined` | `{ transfer_id, senior_id }` |
| `transfer.recipient_accepted` | `{ transfer_id, recipient_id }` |
| `transfer.recipient_declined` | `{ transfer_id, recipient_id }` |
| `transfer.cancelled` | `{ transfer_id, by_user_id }` |
| `transfer.expired` | `{ transfer_id }` |

### 3.6 Contacts
| Событие | payload |
|---|---|
| `contact.created` | `{ contact_id }` |
| `contact.field_changed` | `{ contact_id, field, old, new, by_user_id }` |
| `contact.merged` | `{ kept_id, removed_id }` |
| `contact.deleted` | `{ contact_id }` |

### 3.7 Files
| Событие | payload |
|---|---|
| `file.uploaded` | `{ file_id, by_user_id, mime, size }` |

### 3.8 Leads (фаза 8)

> Канон: [`LEADS.md`](LEADS.md). WS-типы в [`API_CONTRACT.md`](API_CONTRACT.md) §14.

| Событие | Когда | payload |
|---|---|---|
| `lead.created` | `ensure_lead` / `POST /leads` | `{ lead_id, contact_id, group_id, chat_id?, status_id, source }` |
| `lead.status_changed` | `PATCH /leads/{id}` (смена `status_id`) | `{ lead_id, contact_id, group_id, from_status_id, to_status_id, by_user_id }` |
| `lead.closed` | `POST /leads/{id}/close` | `{ lead_id, contact_id, group_id, chat_id?, closed_at, closed_by_user_id, status_id }` |

Outbox → Redis → WS Hub. Каналы: `group.{group_id}`, `user.{card_owner_user_id}` (если есть), `chat.{chat_id}` при открытом чате.

---

## 4. Каналы Redis Pub/Sub (для realtime)

Внутренние топики и Redis-каналы — разные вещи. Топик `chat.message.received` мапится в каналы Redis по правилам:

| Топик | Каналы Redis (один publish, может быть много каналов) |
|---|---|
| `chat.message.received` | `chat.{chat_id}`, `user.{current_user_id}` (если назначен), `dept.{department_id}` (для senior'ов отдела) |
| `chat.message.created` | те же |
| `chat.takeover_started` | `chat.{chat_id}`, `user.{displaced_user_id}` |
| `transfer.requested` (с `state=pending_senior`) | `dept_seniors.{department_id}` |
| `transfer.requested` (с `state=pending_recipient`) | `user.{to_user_id}` |
| `transfer.recipient_accepted` | `user.{from_user_id}`, `user.{to_user_id}`, `dept.{department_id}` |
| `lead.created` / `lead.status_changed` / `lead.closed` | `group.{group_id}`, `user.{card_owner_user_id}`, `chat.{chat_id}` |

WS Hub каждого Pod'а подписан на каналы:
- `user.{id}` для каждого активного юзера на этом Pod'е,
- `chat.{id}` для каждого открытого чата на фронте,
- `dept.{id}` и `dept_seniors.{id}` для senior'ов на этом Pod'е.

Это даёт точную доставку без широковещания.

---

## 5. Подписчики (handlers внутри монолита)

```
Publisher: chats service
   │
   ▼
Pub/Sub bus (in-process router + Redis bridge)
   │
   ├─▶ audit.subscribe([*])              # пишет в audit_log
   ├─▶ realtime.subscribe([              # WS Hub
   │      "chat.*", "transfer.*", "user.*"
   │   ])
   ├─▶ notifications.subscribe([
   │      "transfer.requested", "transfer.accepted", ...
   │   ])
   └─▶ assignment.subscribe([
          "chat.message.received"        # авто-назначение, если current_user_id=NULL
       ])
```

Все подписчики идемпотентны (повторная обработка не должна привести к дублям). Метод реализации:
- ID события (`event_id`) хранится в Redis на 24 часа,
- при повторной обработке — пропускаем.

---

## 6. Контракт publisher'а

```python
# shared/events.py
class EventBus:
    async def publish(self, topic: str, payload: dict, *, actor_id: int | None = None): ...

# в сервисе:
async def send_message(...):
    async with uow.transaction():
        msg = await repo.create_message(...)
        await uow.outbox.add(
            topic="chat.message.created",
            payload={"chat_id": chat.id, "message_id": msg.id, ...},
            actor_id=actor.id,
        )
    # outbox-воркер вычитает и опубликует
```

Из приложения **никогда** не публикуем напрямую в Pub/Sub — только через outbox. Это гарантирует «событие после успешной транзакции».

Исключение: события, которые не критичны и не должны переживать рестарт (например, `presence.changed`) — могут идти в Pub/Sub напрямую.

---

## 7. Схема файлов в коде

```
app/shared/events/
├── bus.py             # EventBus interface
├── outbox.py          # Outbox writer + worker
├── redis_bridge.py    # читает Redis Pub/Sub, диспатчит локально
├── topics.py          # константы топиков
└── handlers.py        # подписки

app/modules/audit/handlers.py     # пишет audit_log по wildcard *
app/realtime/hub.py               # подписка + WS push
app/modules/notifications/handlers.py
```

---

## 8. Слабые места шины

1. **Outbox-воркер становится узким местом** при росте RPS. Решение: горизонтальное масштабирование с PostgreSQL `SKIP LOCKED`.
2. **Redis Pub/Sub без персистентности.** Если все Pod'ы упали в момент publish — событие потеряно. Для realtime приемлемо, для бизнес-логики — outbox обязателен.
3. **Идемпотентность по event_id 24 часа** — не покрывает редкий случай «обработали → сохранили → упали без коммита → перезапустили через 25 часов». Митигация: внутри подписчика — идемпотентные операции (UPSERT по доменному ключу).
4. **«Пожар подписчиков»** — если один handler падает, остальные не должны страдать. Каждый handler в `try/except` + Sentry, **без** возврата ошибки в bus.
5. **Глобальный wildcard у audit** — растёт нагрузка. Если станет горячо, разделить на `audit-critical` (org, auth) и `audit-volume` (messages) с разной retention-политикой.
