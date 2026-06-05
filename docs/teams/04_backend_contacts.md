# Backend Contacts

> Карточка клиента, статусы, файлы, история изменений.

---

## 1. Зона ответственности

- Сущность `contacts` (CRUD, custom_fields JSONB, поиск).
- Аудит изменений полей (`contact_field_changes`).
- Маскирование `telegram_user_id` (видим только админу).
- Справочник `statuses` (для чатов и контактов).
- `files` + интеграция с MinIO (presigned URLs).
- Сервис `contacts_service.get_or_create_by_telegram(...)` для команды Bots Integration.
- **Владение карточкой в группе** — [`CONTACT_OWNERSHIP.md`](../CONTACT_OWNERSHIP.md): `contact_group_assignments`, transfers, escalation, `message_reply_audit`.

---

## 2. Стек и зависимости

```
fastapi
sqlalchemy[asyncio]
pydantic
boto3 / aioboto3 (S3-клиент для MinIO)
python-magic (определение mime)
```

Зависимости от других команд:
- `Backend Core`: auth, scope, EventBus, db.
- `Backend Chats`: использует `contacts_service` (read-only API).

---

## 3. Backlog

### Epic 1. Сущность контакта
- [ ] Миграция: `contacts` (с уникальным `telegram_user_id`, GIN на `custom_fields`).
- [ ] Модели + repository.
- [ ] DTO с двумя сериализаторами:
  - `ContactPublicOut` (без `telegram_user_id`);
  - `ContactAdminOut` (с полем);
  - выбор делается в роутере на основе роли актора.
- [ ] **DoD:** при сериализации не-админу `telegram_user_id` отсутствует. Sentry-алёрт на пропуск этой проверки.

### Epic 2. CRUD API
- [ ] `GET /api/v1/contacts?q=&status_id=&page=&size=` (с применением scope).
- [ ] `GET /api/v1/contacts/{id}` (с `chats_summary`).
- [ ] `POST /api/v1/contacts` (создание вручную).
- [ ] `PATCH /api/v1/contacts/{id}` (диффер для `custom_fields` по ключам).
- [ ] `DELETE /api/v1/contacts/{id}` (soft-delete).
- [ ] **DoD:** все эндпоинты покрыты тестами по матрице прав.

### Epic 3. Аудит полей контакта
- [ ] Миграция: `contact_field_changes`.
- [ ] Утилита `diff(old, new)` для plain полей и для JSONB `custom_fields` (по ключам, recursively не нужно).
- [ ] При `PATCH` — записать каждое изменённое поле отдельной строкой в `contact_field_changes` в той же транзакции.
- [ ] Outbox-event `contact.field_changed` для каждого поля.
- [ ] `GET /api/v1/contacts/{id}/history` — список с автором и timestamp.
- [ ] **DoD:** на UI у каждого поля видно «изменено: <user> <date>». Это требование `TECH_SPEC §5.3 US-14`.

### Epic 4. Custom fields
- [ ] Хранение в `contacts.custom_fields` JSONB.
- [ ] На MVP — без схемы (любой ключ, любое значение).
- [ ] Frontend получает поля как `key/value` и рендерит. Список «известных» ключей хранится в **отдельной таблице** `custom_field_definitions` (опционально).
- [ ] Поиск по custom_fields через `?` и `@>` операторы (нужен GIN-индекс).
- [ ] **DoD:** оператор может добавить произвольное поле «город» = «Москва», оно сохраняется и видно.

### Epic 5. `get_or_create_by_telegram`
- [ ] Сервис, дёргаемый из команды Bots Integration при обработке `message.received`:
  ```python
  contacts_service.get_or_create_by_telegram(
      telegram_user_id, telegram_username, first_name, last_name, language_code
  ) -> Contact
  ```
- [ ] Логика: SELECT по `telegram_user_id` UNIQUE; если есть → обновить `telegram_username`/имя/язык если изменились; если нет → INSERT.
- [ ] Идемпотентность: гонка двух запросов на одного контакта — `INSERT ... ON CONFLICT (telegram_user_id) DO UPDATE`.
- [ ] Outbox-event `contact.created` (при первом INSERT).
- [ ] **DoD:** 100 параллельных вызовов с одним telegram_user_id → один контакт.

### Epic 5b. Contact ownership (Фаза 3.5) — ПРИОРИТЕТ
> [`CONTACT_OWNERSHIP.md`](../CONTACT_OWNERSHIP.md), [`AUDIT_REFACTOR_OWNERSHIP.md`](../AUDIT_REFACTOR_OWNERSHIP.md).

- [ ] Миграции 0012–0014: `contact_group_assignments`, `group_escalation_settings`, `message_reply_audit`, `contact_group_transfers`.
- [ ] `ownership.py`: assign (round-robin), get_owner(contact, group), transfer flow.
- [ ] `escalation.py` + worker: N min → notify group → reassign new contact.
- [ ] API: `GET contact` с `group_ownership[]`; transfer endpoints; escalation settings.
- [ ] `GET .../reply-audit` — кто ответил, кто был владельцем.
- [ ] Интеграция: `get_or_create_by_telegram` + `ensure_assignment(contact, bot.group_id)`.
- [ ] **DoD:** transfer в группе A не меняет владельца в группе B; on_behalf в аудите.

### Epic 6. Статусы
- [ ] Миграция: `statuses`.
- [ ] CRUD-роуты для admin (см. `API_CONTRACT.md` §9).
- [ ] Кеш (Redis) на список статусов с invalidation при изменении.
- [ ] **DoD:** админ создаёт статус → он сразу доступен для чата.

### Epic 7. Файлы / MinIO
- [ ] Миграция: `files`.
- [ ] `POST /api/v1/files` (multipart upload):
  1. Стрим в MinIO (не держать в памяти весь файл);
  2. Считать sha256 на лету;
  3. Сохранить запись в БД;
  4. Outbox-event `file.uploaded`.
- [ ] `GET /api/v1/files/{id}` — генерация presigned URL (5 минут).
- [ ] Виртуальный сервис `files_service.upload_from_url(url)` для скачивания медиа по временному URL бота (стрим без локального диска).
- [ ] Лимит размера (env), запрет некоторых mime (TBD: exe, zip с паролем — на старте не запрещаем, только лог).
- [ ] **DoD:** оператор аплоадит 20 MB-файл, тот появляется в чате, скачивается обратно.

---

## 4. Точки интеграции

### Что Contacts отдаёт
- API `/api/v1/contacts/*`, `/api/v1/statuses/*`, `/api/v1/files/*`.
- Сервисы:
  - `contacts_service.get_or_create_by_telegram(...)`;
  - `files_service.upload(...)`, `files_service.upload_from_url(...)`;
  - `statuses_service.get(id)`.
- События `contact.*`, `file.uploaded`.

### Что Contacts берёт
- От Core: auth, scope, EventBus, db.

---

## 5. Definition of Done команды

- ✅ Все эндпоинты `/contacts`, `/statuses`, `/files` покрыты тестами.
- ✅ `telegram_user_id` маскируется в UI/API (E2E тест).
- ✅ Аудит полей контакта работает: UI отображает «кто менял».
- ✅ `get_or_create_by_telegram` идемпотентен под нагрузкой.
- ✅ Файлы 50 MB загружаются без OOM.

---

## 6. Слабые места команды

1. **`telegram_user_id` маскированием** не равен шифрованию. Один забытый сериализатор → утечка. Митигация: тест, который дёргает все маршруты от имени user/senior и проверяет, что в JSON нет ключа `telegram_user_id`.
2. **Custom fields без схемы** легко превращаются в свалку. Если у пяти операторов написано «компания», «название компании», «company» — поиск ломается. Согласовать со заказчиком: либо вводим schema-таблицу со старта, либо принимаем риск.
3. **`contact_field_changes` растёт быстро** при активной правке. Партиционирование с момента, когда таблица > 5M.
4. **Diff для `custom_fields` по ключам** — спорная глубина. Обходим один уровень. Если внутрь положили объект — не разворачиваем (одна строка `field='custom_fields.address'`). Зафиксировать.
5. **Soft-delete контакта** оставляет связанные чаты. UX-вопрос: показывать «контакт удалён» или скрывать чат? Согласовать с заказчиком.
6. **MinIO без репликации** — потеря тома = потеря всех файлов. Бэкап mirror'ом на другой хост — обязательно.
