# Telegram ↔ CRM — актуальная документация

> **Версия:** 2026-06-05 · отражает текущий код в `main`  
> **Аудитория:** DevOps, разработчики ботов, админы CRM  
> **Низкоуровневый контракт:** [`BOTS_INTEGRATION.md`](BOTS_INTEGRATION.md)  
> **Референс-реализация бота:** `scripts/bots/tg_crm_bridge/`

---

## 1. Принцип

CRM **не работает с Telegram API напрямую** и **не хранит bot token**.

Telegram-бот — отдельный сервис. Связь с CRM только по HTTP с HMAC-подписью:

```
Клиент (Telegram)
       ↕  Telegram Bot API
  Telegram-бот (ваш код или tg_crm_bridge)
       ↕  HTTPS + HMAC
  CRM
    POST /api/v1/bot-events          ← входящие (Bot → CRM)
    POST bot.outbound_url              ← исходящие (CRM → Bot)
    GET  /api/v1/bot-outbound/files/*  ← скачивание вложений ботом
```

| Компонент | Где живёт | Задача |
|-----------|-----------|--------|
| **CRM API** | Docker `crm-staging-api` | Приём событий, чаты, контакты, лиды, UI |
| **CRM Worker** | Docker `crm-staging-worker` | Очередь исходящих команд на `outbound_url` |
| **Telegram-бот** | systemd / отдельный контейнер | Long polling TG, пересылка в CRM, отправка ответов |

---

## 2. URL (продакшен VPS)

Пример для текущего деплоя (`146.19.125.32`):

| Поверхность | URL |
|-------------|-----|
| CRM (UI) | `https://chat.bttsrvvrs.org` |
| API | `https://api.bttsrvvrs.org` |
| OpenAPI | `https://api.bttsrvvrs.org/api/docs` |
| WebSocket | `wss://api.bttsrvvrs.org/api/v1/ws` |
| **Bot ingest** | `POST https://api.bttsrvvrs.org/api/v1/bot-events` |
| Health API | `GET https://api.bttsrvvrs.org/healthz` |

### Переменные в `deploy/.env.staging`

```env
CORS_ALLOWED_ORIGINS=https://chat.bttsrvvrs.org
VITE_API_BASE_URL=https://api.bttsrvvrs.org/api/v1
VITE_WS_URL=wss://api.bttsrvvrs.org/api/v1/ws
```

`VITE_*` вшиваются в образ frontend при сборке — после изменения нужен `bash scripts/deploy/vps/update.sh`.

---

## 3. Регистрация бота в CRM

### 3.1 Admin → Боты — создание

| Поле | Обязательно | Описание |
|------|-------------|----------|
| `code` | да | Уникальный код, напр. `test_bot_1` |
| `name` | да | Отображаемое имя |
| `department_id` | да | Отдел, к которому привязан бот |
| `inbound_secret` | да | ≥16 символов, подпись Bot → CRM |
| `outbound_secret` | да | ≥16 символов, подпись CRM → Bot |
| `outbound_url` | да | URL приёма исходящих команд |
| `health_url` | нет | GET health-check (подписанный) |
| `ip_allowlist` | нет | CIDR; если пусто — любой IP |

Секреты **задаются при создании** и показываются **один раз**. Сохраните их в безопасное место (напр. `/root/crm/.secrets/test_bot_1.env`).

**Скрипт быстрого создания:**

```bash
cd /root/crm
API_BASE=https://api.bttsrvvrs.org \
ADMIN_USER=admin@example.com \
ADMIN_PASS='ваш_пароль' \
bash scripts/bots/provision_test_bot.sh
```

### 3.2 Senior → Боты — распределение по группам

Двухуровневая модель:

| Назначение групп | Куда попадают чаты | Кто видит |
|------------------|-------------------|-----------|
| **0 групп** | Ящик отдела (`__department_inbox__`) | Senior отдела |
| **2+ групп** | Ящик отдела | Senior отдела |
| **Ровно 1 группа** | Эта группа | Операторы группы + round-robin владельца |

Для теста с операторами: назначьте бота **ровно одной** группе, где есть пользователи с ролью `user` и доступностью **«Доступен»**.

Подробнее о владельце карточки: [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md).

---

## 4. Установка готового моста (tg_crm_bridge)

Референс-бот в репозитории: long polling Telegram + HTTP-сервер для исходящих.

### 4.1 BotFather

1. [@BotFather](https://t.me/BotFather) → `/newbot`
2. Скопировать **token** (`123456789:AAH...`)

### 4.2 Установка на VPS

```bash
cd /root/crm
sed -i 's/\r$//' scripts/bots/tg_crm_bridge/install.sh
chmod +x scripts/bots/tg_crm_bridge/install.sh

TG_BOT_TOKEN='ВАШ_ТОКЕН_ОТ_BOTFATHER' \
API_BASE=https://api.bttsrvvrs.org \
CRM_ROOT=/root/crm \
bash scripts/bots/tg_crm_bridge/install.sh
```

Скрипт:

- создаёт venv в `/root/crm-bots/`
- пишет `.env` с секретами из `.secrets/test_bot_1.env`
- слушает `0.0.0.0:8765`
- обновляет в CRM `outbound_url` = `http://host.docker.internal:8765/crm/cmd`
- регистрирует systemd-сервис `tg-crm-bridge`
- перезапускает CRM worker (нужен `host.docker.internal` в `deploy/server/docker-compose.vps.yaml`)

Если Docker уже собран, а скрипт упал на логине:

```bash
SKIP_DOCKER=1 ADMIN_PASS='пароль' bash scripts/bots/tg_crm_bridge/install.sh
```

### 4.3 Проверка end-to-end

1. Telegram → открыть бота → **Start** → написать «Привет»
2. `https://chat.bttsrvvrs.org` → чат с контактом появился
3. Ответить из CRM → сообщение приходит **в Telegram**

### 4.4 Логи и управление

```bash
systemctl status tg-crm-bridge
journalctl -u tg-crm-bridge -f
docker logs crm-staging-worker --tail 50
docker logs crm-staging-api --tail 50

systemctl stop tg-crm-bridge    # остановка
systemctl restart tg-crm-bridge # перезапуск
```

### 4.5 Обновление кода моста

```bash
cd /root/crm
git pull
cp scripts/bots/tg_crm_bridge/main.py /root/crm-bots/
systemctl restart tg-crm-bridge
```

---

## 5. Входящие события (Bot → CRM)

### 5.1 Endpoint

```
POST /api/v1/bot-events
Content-Type: application/json
```

### 5.2 Заголовки

| Заголовок | Описание |
|-----------|----------|
| `X-Bot-Code` | Код бота из CRM |
| `X-Event-Id` | Уникальный ID события (идемпотентность) |
| `X-Timestamp` | UNIX seconds |
| `X-Signature` | `sha256=<hex>` (префикс опционален) |

### 5.3 Подпись inbound

```
body       = сырые bytes HTTP body
digest     = sha256_hex(body)
canonical  = event_id + "." + timestamp + "." + digest
signature  = HMAC_SHA256(inbound_secret, canonical)
```

### 5.4 Anti-replay

Запрос отклоняется, если `|now - timestamp| > 300` секунд.

### 5.5 Envelope

```json
{
  "event": "message.received",
  "event_id": "tg-42-1747407296",
  "occurred_at": "2026-06-05T12:00:00Z",
  "bot_code": "test_bot_1",
  "payload": { }
}
```

### 5.6 Поддерживаемые события

#### `message.received` (основное)

```json
{
  "event": "message.received",
  "event_id": "01JABCDEF...",
  "occurred_at": "2026-06-05T12:00:00Z",
  "bot_code": "test_bot_1",
  "payload": {
    "contact": {
      "telegram_user_id": 123456789,
      "telegram_username": "ivan_xx",
      "first_name": "Иван",
      "last_name": "Иванов"
    },
    "message": {
      "external_id": "42",
      "text": "Здравствуйте",
      "attachments": [],
      "reply_to_external_id": null
    }
  }
}
```

**Входящее от клиента** (по умолчанию): поле `direction` не передаётся или `"inbound"`.

**Ответ клиенту из Telegram** (оператор ответил не через CRM UI): тот же `message.received`, в `message` добавить `"direction": "outbound"`. `contact.telegram_user_id` — **клиент** (получатель). CRM сохранит **исходящее** сообщение в чат без указания менеджера.

```json
"message": {
  "external_id": "99",
  "text": "Добрый день, помогу с заказом",
  "direction": "outbound",
  "attachments": []
}
```

**Эффект inbound:** upsert контакта → чат → открытый лид → назначение владельца (round-robin) → сохранение сообщения → загрузка вложений по URL (async).

**Эффект outbound:** сообщение в существующий чат клиента как исходящее, обновление preview, без эскалации ownership.

#### `message.edited`

```json
{
  "event": "message.edited",
  "payload": {
    "message": {
      "external_id": "42",
      "text": "Новый текст"
    }
  }
}
```

#### `contact.updated`

```json
{
  "event": "contact.updated",
  "payload": {
    "telegram_user_id": 123456789,
    "telegram_username": "new_name",
    "first_name": "Иван",
    "last_name": "Иванов"
  }
}
```

### 5.7 Ответы CRM

| HTTP | Body | Значение |
|------|------|----------|
| 202 | `{"status":"accepted"}` | Принято в обработку |
| 202 | `{"status":"duplicate"}` | Повтор того же `event_id` |
| 401 | — | Неверная подпись, timestamp, неактивный бот, IP не в allowlist |

### 5.8 Вложения (inbound)

В `message.attachments[]`:

```json
{
  "type": "photo",
  "url": "https://...",
  "mime": "image/jpeg",
  "filename": "photo.jpg",
  "size_bytes": 12345
}
```

CRM скачивает URL асинхронно (retry: 5s, 30s, 120s). Лимит: **10 MB** (`max_upload_bytes`).

---

## 6. Исходящие команды (CRM → Bot)

### 6.1 Когда срабатывает

Оператор отправляет сообщение в UI → `POST /api/v1/chats/{id}/messages` → worker ставит задачу → `POST bot.outbound_url`.

### 6.2 Envelope

```json
{
  "command": "send_message",
  "request_id": "01J...",
  "issued_at": "2026-06-05T12:00:00Z",
  "bot_code": "test_bot_1",
  "payload": {
    "internal_id": 999,
    "contact": {
      "telegram_user_id": 123456789
    },
    "message": {
      "text": "Ответ оператора"
    },
    "attachments": [
      {
        "file_id": 1,
        "type": "photo",
        "mime": "image/jpeg",
        "filename": "scan.jpg"
      }
    ],
    "reply_to_external_id": null
  }
}
```

### 6.3 Заголовки

```
Content-Type: application/json
X-CRM-Request-Id: 01J...
X-CRM-Timestamp: 1747407296
X-CRM-Signature: sha256=<hex>
```

### 6.4 Подпись outbound

```
digest     = sha256_hex(body)
canonical  = METHOD + "\n" + PATH + "\n" + timestamp + "\n" + digest
signature  = "sha256=" + HMAC_SHA256(outbound_secret, canonical)
```

`PATH` — путь URL без query (напр. `/crm/cmd` для `http://host:8765/crm/cmd`).

### 6.5 Ответ бота

Успех:

```json
{
  "status": "ok",
  "external_id": "43",
  "telegram_message_id": 43
}
```

Ошибка:

```json
{
  "status": "error",
  "message": "описание"
}
```

Retry worker: до **5** попыток, backoff **30s, 60s, 120s, 300s, 600s**.

### 6.6 Скачивание файлов ботом

Для вложений CRM отдаёт `file_id`. Бот скачивает:

```
GET /api/v1/bot-outbound/files/{file_id}
X-Bot-Code: test_bot_1
X-CRM-Timestamp: <unix>
X-CRM-Signature: sha256=<hex>
```

Подпись считается для `GET` с пустым body (как в `tg_crm_bridge/main.py`).

---

## 7. Health-check бота

Если задан `health_url`:

```
GET <health_url>
X-CRM-Timestamp: <unix>
X-CRM-Signature: sha256=<hex>
```

- `200` → бот healthy  
- иначе / timeout → unhealthy  

Интервал: `bot_health_check_interval_seconds` (по умолчанию **6 часов**).

Для `tg_crm_bridge`: `http://host.docker.internal:8765/crm/health`

---

## 8. Поток данных (полный цикл)

```
1. Клиент пишет в Telegram
2. tg_crm_bridge: getUpdates → POST /bot-events (message.received)
3. CRM worker: контакт, чат, лид, владелец, сообщение
4. WebSocket → UI оператора (realtime)
5. Оператор отвечает в CRM
6. CRM worker: POST outbound_url (send_message)
7. tg_crm_bridge: sendMessage / sendPhoto → Telegram
8. Клиент получает ответ
```

---

## 9. Чек-лист перед продом

- [ ] Бот создан в CRM (Admin), секреты сохранены в `.secrets/`
- [ ] `outbound_url` и `health_url` указывают на работающий сервис бота
- [ ] Worker имеет доступ к `outbound_url` (`host.docker.internal` для bridge)
- [ ] `tg-crm-bridge` (или свой бот) запущен: `systemctl status tg-crm-bridge`
- [ ] Senior назначил бота **одной** группе (если нужны операторы)
- [ ] В группе есть операторы: `role=user`, доступность **«Доступен»**
- [ ] Inbound HMAC: `event_id.timestamp.sha256(body)`
- [ ] Outbound endpoint проверяет `X-CRM-Signature`
- [ ] При retry inbound — **тот же** `event_id`, не новый
- [ ] `VITE_*` и `CORS_*` в `.env.staging` соответствуют домену UI
- [ ] `curl -sf https://api.<domain>/healthz` → OK

---

## 10. Типичные проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| **Network Error** в UI | Frontend собран с `localhost` в `VITE_*` | Проверить `deploy/.env.staging`, пересобрать frontend |
| Сообщения в TG, нет в CRM | Неверный HMAC / `X-Bot-Code` / бот неактивен | Логи API, проверить секреты |
| Есть в CRM, нет в TG | Bridge не запущен или worker не достучался до `outbound_url` | `journalctl -u tg-crm-bridge`, `docker logs crm-staging-worker` |
| **Владелец: Не назначен** | Бот не в одной группе / нет операторов «Доступен» | Senior → Боты → одна группа; проверить пользователей |
| Login 500 | Баг timezone на `last_seen_at` | `git pull` + пересборка API (коммит `3fb06ff+`) |
| Красная точка на своём ответе | Read state не обновлялся | `git pull` (коммит `b619e2d+`), пересборка API + frontend |
| `Permission denied` на deploy | `check-env.sh` без +x | `git pull` (коммит `ed6229d+`) или `bash scripts/deploy/vps/update.sh` |

---

## 11. Скрипты и файлы

| Путь | Назначение |
|------|------------|
| `docs/BOTS_INTEGRATION.md` | Детальный HTTP-контракт (as-built) |
| `docs/CONTACT_OWNERSHIP.md` | Владелец карточки, round-robin |
| `docs/LEADS.md` | Лиды и сделки |
| `scripts/bots/tg_crm_bridge/main.py` | Референс-реализация бота |
| `scripts/bots/tg_crm_bridge/install.sh` | Установка на VPS |
| `scripts/bots/provision_test_bot.sh` | Создание тестового бота + секреты |
| `scripts/deploy/vps/update.sh` | Сборка и перезапуск стека |
| `scripts/deploy/vps/fix-live-chat.sh` | Патч `VITE_*` / CORS под HTTPS |

---

## 12. Свой бот (не tg_crm_bridge)

Минимальные требования:

1. **Inbound:** long polling или webhook Telegram → формировать `message.received` → POST `/bot-events` с HMAC.
2. **Outbound:** HTTP-сервер на `outbound_url`, команда `send_message`, проверка `X-CRM-Signature`.
3. **Health:** GET endpoint на `health_url` с проверкой подписи (опционально).
4. **Идемпотентность:** один `event_id` на одно TG-сообщение при retry.
5. **Rate limit Telegram:** на стороне бота (CRM не ограничивает TG API).

Пример подписи inbound/outbound — в `scripts/bots/tg_crm_bridge/main.py` (функции `sign_inbound`, `verify_outbound`, `sign_outbound`).

---

## 13. Безопасность

- CRM **не хранит** Telegram bot token.
- `telegram_user_id` в API виден **только admin** (для user/senior маскируется).
- Секреты бота (`inbound_secret`, `outbound_secret`) — только при создании/ротации.
- Не коммитить `.secrets/` и `deploy/.env.staging` в git.
- Опционально: `ip_allowlist` на бота для ограничения источника inbound.
