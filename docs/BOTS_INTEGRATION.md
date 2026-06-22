# Контракт интеграции CRM ↔ Bots (AS-BUILT)

> **Операционная документация (VPS, bridge, чек-листы):** [`TELEGRAM_INTEGRATION.md`](TELEGRAM_INTEGRATION.md)  
> Аудитория: разработчики Telegram-ботов, интегрируемых с этой CRM.  
> Статус: v1.0, отражает **фактическое поведение текущего кода**.

Этот документ описывает только то, что реально работает в текущей версии сервиса.

---

## 1) Что сейчас поддерживается

- Входящие webhook-события от бота: `POST /api/v1/bot-events`.
- Проверка подписи HMAC для входящих событий.
- Проверка anti-replay по timestamp.
- Идемпотентность по `event_id` (`accepted` / `duplicate`).
- IP allowlist для входящих (если задан для бота).
- Фоновая загрузка inbound-вложений по URL из payload.
- Health-check бота по `health_url` (подписанный GET от CRM).

---

## 2) Регистрация бота в CRM

Бот создается админом через API/UI CRM.

Обязательные поля:
- `code` (уникальный код бота),
- `name`,
- `owner_type` (`department` или `group`),
- `owner_id`,
- `outbound_url`,
- `inbound_secret`,
- `outbound_secret`.

Опциональные:
- `health_url`,
- `ip_allowlist`.

Важно:
- В текущей реализации секреты **задаются при создании** (CRM не генерирует их автоматически).
- Один bot record = одна пара `inbound_secret` / `outbound_secret`.

---

## 3) Безопасность и подписи

### 3.1 Входящие (Bot -> CRM)

Endpoint:
```
POST /api/v1/bot-events
```

Обязательные заголовки:
```
Content-Type: application/json
X-Bot-Code: support_a
X-Event-Id: 01J...
X-Timestamp: 1747407296
X-Signature: sha256=<hex>   # также принимается без префикса sha256=
```

Каноническая строка для подписи inbound:
```
canonical = event_id + "." + timestamp + "." + sha256_hex(body)
signature = HMAC_SHA256(inbound_secret, canonical)
```

Где:
- `event_id` = значение `X-Event-Id`,
- `timestamp` = значение `X-Timestamp` (UNIX seconds),
- `body` = сырые bytes HTTP body.

Anti-replay:
- запрос отклоняется, если `abs(now - timestamp) > 300` секунд.

### 3.2 Исходящие (CRM -> Bot, когда включены outbound jobs)

Заголовки:
```
Content-Type: application/json
X-CRM-Request-Id: 01J...
X-CRM-Timestamp: 1747407296
X-CRM-Signature: sha256=<hex>
```

Каноническая строка для outbound/health:
```
canonical = method + "\n" + path + "\n" + timestamp + "\n" + sha256_hex(body)
signature = "sha256=" + HMAC_SHA256(outbound_secret, canonical)
```

---

## 4) Формат входящих событий

Общий envelope:
```json
{
  "event": "message.received",
  "event_id": "01J...",
  "occurred_at": "2026-05-16T12:34:56Z",
  "bot_code": "support_a",
  "payload": {}
}
```

### 4.1 Поддерживаемые `event`

#### `message.received` (основной)

Ожидается:
- `payload.contact.telegram_user_id` (обязательно),
- `payload.message.external_id` (обязательно),
- `payload.message.text` (опционально),
- `payload.message.attachments` (опционально),
- `payload.message.reply_to_external_id` (опционально),
- `payload.message.direction` (опционально): `"inbound"` (по умолчанию) или `"outbound"`.

Эффект при `direction` = `"inbound"` или поле отсутствует:
- upsert контакта,
- upsert чата,
- создание/поддержка открытого лида,
- сохранение входящего сообщения,
- enqueue загрузки вложений (если есть).

Эффект при `direction` = `"outbound"`:
- `contact.telegram_user_id` — **клиент** (получатель ответа в Telegram),
- запись **исходящего** сообщения в чат этого клиента (`sender_user_id` не задаётся),
- обновление preview чата и статуса «отвечено»,
- **без** эскалации ownership и **без** создания нового лида,
- идемпотентность по `external_id` в рамках чата (повтор не дублирует сообщение).

Пример ответа оператора из Telegram (тот же `event`, опциональное поле):

```json
{
  "event": "message.received",
  "event_id": "01JOUTBOUND001",
  "occurred_at": "2026-05-16T12:35:00Z",
  "bot_code": "support_a",
  "payload": {
    "contact": { "telegram_user_id": 123456789 },
    "message": {
      "external_id": "tg-msg-999",
      "text": "Добрый день, помогу с заказом",
      "direction": "outbound",
      "attachments": []
    }
  }
}
```

#### `message.edited`

Ожидается:
- `payload.message.external_id`,
- `payload.message.text` (новый текст).

Эффект:
- best-effort обновление текста ранее сохраненного inbound-сообщения.

#### `contact.updated`

Ожидается:
- `payload.telegram_user_id`,
- опционально `telegram_username`, `first_name`, `last_name`.

Эффект:
- обновление профиля контакта.

#### `call.received` (Bitcall / telephony)

This event is used by `channel = "bitcall"` bots. Bitcall-specific webhooks should be
normalized by a bridge/adaptor into this CRM envelope.

Required fields:
- `payload.contact.phone`
- `payload.call.external_id`

Optional fields:
- `payload.contact.full_name`, `first_name`, `last_name`
- `payload.call.direction` (`"inbound"` by default)
- `payload.call.status`
- `payload.call.duration_seconds`
- `payload.call.recording_url`
- `payload.call.recording_mime`
- `payload.call.recording_filename`

Effect:
- upsert contact by `phone`;
- upsert chat for the Bitcall bot;
- create/keep an open lead in the bot group/department inbox;
- save the call as an inbound chat message;
- attach `recording_url` as a `voice` attachment when present.

Example:

```json
{
  "event": "call.received",
  "event_id": "bitcall-call-001",
  "occurred_at": "2026-06-22T12:00:00Z",
  "bot_code": "bitcall_sales",
  "payload": {
    "contact": {
      "phone": "+79005550123",
      "full_name": "Bitcall Client"
    },
    "call": {
      "external_id": "call-001",
      "direction": "inbound",
      "status": "completed",
      "duration_seconds": 42,
      "recording_url": "https://example.test/recordings/call-001.mp3"
    }
  }
}
```

### 4.2 Что сейчас НЕ обрабатывается

Если придут события вроде:
- `message.delivered`,
- `message.read`,
- другие неизвестные `event`,

они будут приняты на уровне ingest и помечены как обработанные, но бизнес-эффект не выполняется (игнорируются worker-ом).

---

## 5) HTTP-ответы CRM на `/api/v1/bot-events`

Успех:
```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"status":"accepted"}
```

Повтор того же `event_id`:
```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"status":"duplicate"}
```

Невалидная подпись / timestamp / bot inactive / ip deny:
```http
HTTP/1.1 401 Unauthorized
```

Примечание: в текущей реализации даже невалидный JSON body для этого endpoint приводит к `401 Unauthorized` (а не к `400`).

---

## 6) Файлы (inbound attachments)

Для `message.received.payload.message.attachments[*].url`:
- CRM скачивает файл асинхронно.
- Retry-политика: `5s`, `30s`, `120s` (3 попытки).
- Если после 3 попыток не удалось:
  - attachment получает `status = "failed"` и поле `error`,
  - отдельное realtime-событие `chat.message.attachment_failed` сейчас не публикуется.

Текущий лимит upload в системе: `max_upload_bytes = 10 MB` (настраивается в settings).

---

## 7) Outbound команды CRM -> Bot (текущее состояние)

В коде существует worker-диспетчер outbound-команд:
- envelope:
```json
{
  "command": "<string>",
  "request_id": "01J...",
  "issued_at": "ISO8601",
  "bot_code": "support_a",
  "payload": {}
}
```
- отправка на `bot.outbound_url`,
- подпись `X-CRM-Signature`,
- retry при ошибках.

Retry worker-а:
- max attempts: `5`,
- backoff: `30s`, `60s`, `120s`, `300s`, `600s`,
- retry выполняется на любые исключения/HTTP >= 400.

Важно для интегратора:
- API контракт приема outbound у бота можно реализовывать уже сейчас.
- Но в текущей ветке операторское `POST /chats/{id}/messages` не ставит outbound-задачу в очередь автоматически.
- То есть полный "оператор написал в UI -> CRM отправила боту" зависит от отдельного подключения/доработки backend-пайплайна.

---

## 8) Health-check бота

Если у бота задан `health_url`, CRM периодически делает:
```
GET <health_url>
```

С заголовками подписи:
```
X-CRM-Timestamp: <unix-seconds>
X-CRM-Signature: sha256=<hex>
```

Правила:
- `200` => bot `healthy`,
- прочее/timeout => `unhealthy`.

Периодичность задается `bot_health_check_interval_seconds` (по умолчанию в коде: `21600`, то есть 6 часов).

---

## 9) Минимальный рабочий пример (Bot -> CRM)

```http
POST /api/v1/bot-events HTTP/1.1
Host: crm.example.com
Content-Type: application/json
X-Bot-Code: support_a
X-Event-Id: 01JABCDEF...
X-Timestamp: 1779102261
X-Signature: sha256=<hex>

{
  "event": "message.received",
  "event_id": "01JABCDEF...",
  "occurred_at": "2026-05-16T12:34:56Z",
  "bot_code": "support_a",
  "payload": {
    "contact": {
      "telegram_user_id": 123456789,
      "telegram_username": "ivan_xx",
      "first_name": "Иван",
      "last_name": "Иванов"
    },
    "message": {
      "external_id": "msg_001",
      "text": "Здравствуйте",
      "attachments": []
    }
  }
}
```

Ожидаемый ответ:
```json
{"status":"accepted"}
```

---

## 10) Чек-лист для разработчика TG-бота

- [ ] Есть endpoint отправки в CRM: `POST /api/v1/bot-events`.
- [ ] Формируются заголовки `X-Bot-Code`, `X-Event-Id`, `X-Timestamp`, `X-Signature`.
- [ ] Inbound HMAC считается по формуле `event_id.timestamp.sha256(body)`.
- [ ] Реализован retry бота при сетевых ошибках и 5xx CRM.
- [ ] Есть идемпотентность отправки у бота (не повторять новый `event_id` при ретрае того же события).
- [ ] Для вложений бот отдает доступный URL.
- [ ] Реализован endpoint приема outbound-команд (на будущее/при включении пайплайна).
- [ ] Реализован `health_url` и проверка подписи `X-CRM-Signature` для GET health.

---

## 11) Важно: границы этого контракта

- CRM не работает с Telegram API напрямую.
- CRM не хранит bot token.
- CRM не управляет процессом вашего бота.
- Rate-limit Telegram и надежность доставки в Telegram находятся на стороне бота.
