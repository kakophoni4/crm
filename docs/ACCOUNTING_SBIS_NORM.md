# Интеграция CRM ↔ sbis-norm (требования ФНС)

## Публичный API sbis-norm

С **другого** сервера / из CRM (не с localhost на хосте sbis-norm):

```
http://<SBIS_NORM_HOST>:8000
```

`127.0.0.1:8000` — только на самом хосте sbis-norm.

Проверка с внешней машины:

```bash
curl -sS "http://<SBIS_NORM_HOST>:8000/api/sbis/requirements/?unsynced=1&limit=3"
curl -sS "http://<SBIS_NORM_HOST>:8000/api/sbis/requirements/12/"
curl -sS -X POST "http://<SBIS_NORM_HOST>:8000/api/sbis/requirements/mark-synced/" \
  -H "Content-Type: application/json" \
  -d '{"ids":[12]}'
```

Если таймаут/refuse — на VPS (kali):

```bash
ss -lntp | grep 8000
ufw status
ufw allow 8000/tcp
```

## Поток

```
СБИС → sbis-norm (сканер 17:00 МСК) :8000
           │
           ├─ pull (CRM worker каждый час, без ручного запроса):
           │    GET http://<SBIS_NORM_HOST>:8000/api/sbis/requirements/?unsynced=1
           │    GET .../requirements/{id}/   → file_b64
           │    ingest → opt_requirements + MinIO
           │    POST .../mark-synced/
           │    (кнопка «Забрать из СБИС» — опционально, вне очереди)
           │
           └─ push (опционально):
                POST {CRM}/api/v1/accounting/requirements/webhook
                → CRM тянет detail + mark-synced
```

В кабинете бухгалтерии: вкладка **Требования** — список подтягивается **автоматически каждый час**.
Кнопка **Забрать из СБИС сейчас** — опциональный ручной запуск вне расписания.

## Env (CRM)

| Переменная | Назначение |
|------------|------------|
| `SBIS_NORM_API_BASE_URL` | Публичный URL sbis-norm (не `127.0.0.1` с другого хоста) |
| `SBIS_NORM_API_TOKEN` | `REQUIREMENTS_API_TOKEN` на стороне sbis-norm (если задан) |
| `SBIS_NORM_SYNC_ENABLED` | `true` — авто-pull воркером (по умолчанию вкл.) |
| `SBIS_NORM_SYNC_INTERVAL_SECONDS` | Интервал авто-pull (по умолчанию **3600** = 1 час) |
| `SBIS_NORM_SYNC_BATCH_LIMIT` | Размер страницы (по умолчанию 50) |
| `SBIS_NORM_WEBHOOK_TOKEN` | Токен для входящего webhook (= `REQUIREMENTS_WEBHOOK_TOKEN`) |
| `ACCOUNTING_INGEST_TOKEN` | Для ручного/стороннего `POST .../requirements/ingest` |

Пример:

```env
SBIS_NORM_API_BASE_URL=http://<SBIS_NORM_HOST>:8000
SBIS_NORM_API_TOKEN=
SBIS_NORM_SYNC_ENABLED=true
SBIS_NORM_SYNC_INTERVAL_SECONDS=3600
SBIS_NORM_SYNC_BATCH_LIMIT=50
```

## Env (sbis-norm) для push

```
REQUIREMENTS_WEBHOOK_URL=https://api.<domain>/api/v1/accounting/requirements/webhook
REQUIREMENTS_WEBHOOK_TOKEN=<тот же, что SBIS_NORM_WEBHOOK_TOKEN>
```

## Идемпотентность

`external_id` в CRM = `sbis-req:{id}`. Повторный sync не создаёт дубликат, но всё равно делает `mark-synced`.

## Ручной запуск

- UI: Бухгалтерия → Требования → «Забрать из СБИС»
- API: `POST /api/v1/accounting/requirements/sync` (нужен `accounting.manage`)
