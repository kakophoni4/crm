# Интеграция CRM ↔ sbis-norm (требования ФНС)

## Почему agent-режим

Путь **CRM `146.19.125.32` → sbis `146.19.125.77:8000`** отдаёт HTTP 200 и `Content-Length`, но **тело ответа не приходит** (0 bytes / ReadTimeout). Локально на kali `/file/` работает.

Поэтому по умолчанию `SBIS_NORM_SYNC_MODE=agent`:

```
UI «Забрать из СБИС»
  → POST /api/v1/accounting/requirements/sync
  → Redis flag pull_requested
  → kali: sbis_norm_host_pull.py --daemon
       → POST …/pull-claim  (claim)
       → GET  sbis localhost …/file/
       → POST https://api.bttsrvvrs.org/…/ingest/multipart
       → mark-synced
```

## Env (CRM)

| Переменная | Назначение |
|------------|------------|
| `SBIS_NORM_SYNC_MODE` | `agent` (по умолчанию) или `direct` |
| `ACCOUNTING_INGEST_TOKEN` | токен для ingest + pull-claim |
| `SBIS_NORM_SYNC_ENABLED` | периодический авто-флаг (2×/день) |
| `SBIS_NORM_SYNC_INTERVAL_SECONDS` | по умолчанию **43200** |
| `SBIS_NORM_API_BASE_URL` | только для `direct` |

## Kali daemon

```bash
export SBIS_NORM_API_BASE_URL=http://127.0.0.1:8000
export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
export ACCOUNTING_INGEST_TOKEN='…из /root/crm/deploy/.env.staging на 146…'
python3 /opt/sbis-norm/sbis_norm_host_pull.py --daemon
```

Разовый прогон без кнопки: без `--daemon`.

## API sbis-norm

```
GET  /api/sbis/requirements/?unsynced=1&limit=20
GET  /api/sbis/requirements/<id>/file/     ← сырые PDF
POST /api/sbis/requirements/mark-synced/ {"ids":[…]}
```

Не использовать `?include_file=1` / `file_b64`. Только `.pdf` (`.p7m` → mark-synced).

## Идемпотентность

`external_id` в CRM = `sbis-req:{id}`.
