# Backend Chats

> Сердце CRM: чаты, сообщения, передачи, takeover, realtime-доставка.

---

## 1. Зона ответственности

- Сущности `chats`, `messages`, `chat_transfers`.
- Назначение оператора (assignment service).
- Передача чата (transfer flow с двойным подтверждением).
- Перехват старшим (takeover).
- WebSocket Hub (per-pod) + Redis Pub/Sub bridge.
- Доставка realtime-событий из EventBus в WS-клиента.
- Поиск по сообщениям (Postgres FTS на старте).

---

## 2. Стек и зависимости

```
fastapi (websockets)
sqlalchemy[asyncio]
redis (pub/sub)
arq (для авто-expire transfer'ов)
pydantic
```

Зависимости от других команд:
- `Backend Core`: auth, scope, EventBus, db.
- `Backend Bots Integration`: контракт `bots.send(message_id)` ARQ-job, обратные хуки `mark_outbound_sent/failed/delivered/read`.
- `Backend Contacts`: `contacts_service.get_or_create_by_telegram(...)`.

---

## 3. Backlog

### Epic 1. Базовая модель чатов
- [ ] Миграция: `chats`, `messages`, индексы.
- [ ] Модели + relationships (chat ↔ messages, chat ↔ contact, chat ↔ bot).
- [ ] Репозиторий чатов с применением scope.
- [x] `GET /api/v1/chats` (filters: status, status_id, assigned_user_id, contact_id, bot_id, unread_only, card_owner_user_id, assigned_group_id, q; sort; cursor pagination).
- [ ] `GET /api/v1/chats/{id}` (полная карточка).
- [ ] `GET /api/v1/chats/{id}/messages?limit&before`.
- [ ] `POST /api/v1/chats/{id}/read` (отметить прочитанным до X).
- [ ] **DoD:** оператор видит свои чаты, senior — отдела, admin — все. Тесты.

### Epic 2. Отправка сообщения
- [ ] `POST /api/v1/chats/{id}/messages` со статусом `queued`.
- [ ] Идемпотентность по `client_message_id` (уникальный индекс на `(chat_id, client_message_id)`).
- [ ] Валидация: чат видим, takeover не активен или актор — takeover-юзер.
- [ ] Enqueue ARQ-job `bots.send(message_id)` (контракт согласован с Bots Integration).
- [ ] Outbox-event `chat.message.created` для realtime.
- [ ] **DoD:** запросом из API оператор отправляет сообщение, видит его у себя в чате с `status=queued`, через секунду — `sent`.

### Epic 3. Приём сообщения (контракт с Bots Integration)
> Сервис ожидает, что Backend Bots Integration вызовет:
> ```python
> chats_service.ingest_incoming_message(
>     bot_id, contact_id, external_id,
>     body, attachments_pending, reply_to_external_id, sent_at
> )
> ```
> Контакт уже создан/обновлён командой Bots Integration через `contacts_service.get_or_create_by_telegram(...)`. Скачивание файлов из URL — тоже зона Bots Integration; здесь мы записываем только metadata.
- [ ] Реализовать `ingest_incoming_message`:
  - найти/создать chat по `(contact_id, bot_id)`;
  - если `current_user_id IS NULL` → `assignment_service.assign(chat)`;
  - сохранить message с `direction='in'`, `external_id`;
  - инкремент `unread_count_for_operator`;
  - outbox-event `chat.message.received`.
- [ ] Идемпотентность по `(chat_id, external_id)` через UNIQUE-индекс.
- [ ] Реализовать обратные хуки для Bots Integration:
  - `mark_outbound_sent(internal_id, external_id, telegram_message_id)`;
  - `mark_outbound_failed(internal_id, error_code, error_message)`;
  - `mark_outbound_delivered(internal_id, delivered_at)`;
  - `mark_outbound_read(internal_id, read_at)`.
- [ ] **DoD:** интеграционный тест: вызов `ingest_incoming_message` с mock-данными → сообщение в БД → событие в шине → конфликт по external_id отдаёт идемпотентный no-op.

### Epic 4. Assignment → **перенесено в Contacts (ownership)**
> Канон: [`CONTACT_OWNERSHIP.md`](../CONTACT_OWNERSHIP.md). Назначение на `contact_group_assignments`, не на `chats.current_user_id`.
- [ ] Inbound вызывает `ownership.ensure_assignment(contact, group_id)`.
- [ ] Chats scope: user видит **все чаты группы**.
- [ ] Outbound: `message_reply_audit` (owner vs author).

### Epic 5. Transfer flow (DEPRECATED chat-level)
> Новый flow: `contact_group_transfers` в [`04_backend_contacts.md`](04_backend_contacts.md).
- [ ] Миграция: `chat_transfers` + партиальный уникальный индекс на активный transfer.
- [ ] `POST /api/v1/chats/{id}/transfers` (роли: user → pending_senior; senior → pending_recipient; admin → pending_recipient или сразу accepted).
- [ ] `POST /transfers/{id}/approve` / `decline` (senior).
- [ ] `POST /transfers/{id}/accept` / `reject` (recipient).
- [ ] `POST /transfers/{id}/cancel` (requested_by).
- [ ] Авто-expire: ARQ периодика, `expires_at < now() AND state IN (pending_*)` → `expired`.
- [ ] Гонки: `version` на чате, или `SELECT ... FOR UPDATE` в транзакции.
- [ ] Все шаги пишут события `transfer.*` в outbox.
- [ ] **DoD:** state-machine покрыта тестами по всем переходам.

### Epic 6. Takeover
- [ ] `POST /api/v1/chats/{id}/takeover` (senior отдела, admin).
  - 409 если уже активен (`takeover_user_id IS NOT NULL`).
  - Записать `takeover_user_id`, событие `chat.takeover_started`.
- [ ] `DELETE /api/v1/chats/{id}/takeover`.
- [ ] При `POST /chats/{id}/messages` пишет тот, кто `takeover_user_id` (если активен), иначе `current_user_id`.
- [ ] `author_role_at_send` snapshot в каждом сообщении.
- [ ] **DoD:** Senior захватил → user не может писать → senior пишет → user видит сообщение → senior отпустил → user пишет.

### Epic 7. WebSocket Hub
- [ ] `app/realtime/hub.py` — реестр `dict[user_id, set[WebSocket]]`, корутины-обёртки.
- [ ] WS endpoint `wss://.../ws?ticket=...`:
  - валидация ticket → user_id;
  - при connect — добавить в hub, подписаться в Redis на `user.{id}`;
  - heartbeat ping/pong каждые 20 сек;
  - graceful disconnect.
- [ ] `app/realtime/redis_bridge.py`: один корутина-листенер на Pod, мультиплекс по каналам.
- [ ] Подписка на топики событий из EventBus → разворачивание в Redis Pub/Sub каналы (см. `EVENTS.md` §4).
- [ ] Динамическая подписка/отписка на `chat.{id}` при открытии/закрытии чата на фронте (через WS-сообщение или REST + sticky-channel).
  > Решение MVP: подписка на `user.{id}` всегда; на `chat.{id}` — нет, события доставляются через `user.{id}`. Это упрощает реализацию и достаточно для большинства сценариев. Возврат к `chat.{id}` подписке — если будет много observer'ов одного чата.
- [ ] **DoD:** браузерный клиент получает realtime событие `message.created` через ≤200мс p95.

### Epic 8. Поиск
- [ ] FTS-индекс на `messages.body` (Russian-lexer).
- [ ] `GET /api/v1/chats/search?q=...&scope=mine|department|all`.
- [ ] Возвращает релевантные чаты с подсветкой совпадений в превью.
- [ ] **DoD:** поиск по 100k сообщений отвечает < 200мс.

---

## 4. Точки интеграции

### Что Chats отдаёт
- API контракт `/api/v1/chats/*`, `/api/v1/transfers/*` (см. `API_CONTRACT.md`).
- WS-протокол (см. `API_CONTRACT.md` §13).
- Сервис `chats_service.ingest_incoming_message(...)` для команды Bots Integration.
- События `chat.*`, `transfer.*`, `message.*`.

### Что Chats берёт
- От Core: auth, scope, EventBus, db, audit (через bus автоматически).
- От Bots Integration: ARQ job `bots.send(message_id)` и обратные вызовы `mark_outbound_*`.
- От Contacts: `contacts_service.get_or_create_by_telegram(...)`, `files_service.presign(...)`.
- От Statuses (Contacts): `statuses_service.get(id)` для валидации.

---

## 5. Definition of Done команды

- ✅ Все эндпоинты `/chats`, `/transfers` реализованы и покрыты тестами.
- ✅ WS Hub отдаёт события клиенту.
- ✅ Assignment работает.
- ✅ Transfer и takeover проходят все тесты state-machine.
- ✅ Идемпотентность входящих и исходящих сообщений подтверждена тестами.
- ✅ FTS-поиск работает.

---

## 6. Слабые места команды

1. **WebSocket в монолите** ограничен по числу коннектов. Заложить абстракцию `RealtimePublisher`, чтобы при необходимости заменить hub на Centrifugo.
2. **Гонки в transfer-flow**. Самая частая ошибка: «принять transfer» одновременно с «отозвать». Покрыть тестами с `asyncio.gather`.
3. **Assignment без skill-routing** — на старте операторы будут получать «не свои» чаты. Согласовать с заказчиком, что v1 без skill-routing.
4. **Подписка только на `user.{id}` упрощает, но проигрывает** в сценарии «senior смотрит чат оператора». Senior получит event, только если он прямо заинтересован (через скоп). Если старший открыл чат и хочет видеть live — нужно добавить `chat.{id}` подписку. Прокачать на Фазе 5.
5. **Postgres FTS русский** — стеммер не идеален. Если поиск критичен — перейти на Meilisearch раньше.
6. **`unread_count_for_operator`** — денормализация. Триггер на messages должен инкрементить только для входящих и только пока чат не прочитан. Легко облажаться в SQL.
