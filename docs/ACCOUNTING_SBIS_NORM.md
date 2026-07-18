# Интеграция CRM ↔ sbis-norm (требования ФНС)

## Публичный API sbis-norm

```
http://<SBIS_NORM_HOST>:8000
```

## Поток (актуальный)

```
СБИС → sbis-norm (сканер)
         │
         └─ pull CRM:
              GET  /api/sbis/requirements/?unsynced=1&limit=20
              → только storage_file_name.endswith(.pdf); .p7m → mark-synced
              GET  /api/sbis/requirements/<id>/file/   ← сырые байты PDF
              ingest → opt_requirements + MinIO
              POST /api/sbis/requirements/mark-synced/ {"ids":[…]}
```

**Не использовать** `GET …/<id>/?include_file=1` и поле `file_b64` — из‑за них были ReadTimeout.

Лёгкий detail (мета без файла) опционален: `GET …/<id>/`.  
В list есть подсказка `file_url`.

## Env (CRM)

| Переменная | Назначение |
|------------|------------|
| `SBIS_NORM_API_BASE_URL` | База sbis-norm; при Docker→LAN проблемах — host proxy `http://172.23.0.1:18000` |
| `SBIS_NORM_API_TOKEN` | если задан на sbis-norm |
| `SBIS_NORM_SYNC_ENABLED` | авто-pull воркером |
| `SBIS_NORM_SYNC_INTERVAL_SECONDS` | по умолчанию **43200** (2 раза/день) |
| `SBIS_NORM_SYNC_BATCH_LIMIT` | размер страницы list (по умолчанию **20**) |
| `SBIS_NORM_API_TIMEOUT_SECONDS` | read-timeout (по умолчанию **120**) |
| `SBIS_NORM_WEBHOOK_TOKEN` | входящий webhook |
| `ACCOUNTING_INGEST_TOKEN` | для `POST …/requirements/ingest` / host-скрипта |

Пример:

```env
SBIS_NORM_API_BASE_URL=http://146.19.125.77:8000
# If Docker body stalls: http://172.23.0.1:18000 + socat on host
SBIS_NORM_SYNC_ENABLED=true
SBIS_NORM_SYNC_INTERVAL_SECONDS=43200
SBIS_NORM_SYNC_BATCH_LIMIT=20
SBIS_NORM_API_TIMEOUT_SECONDS=120
```

## Ручной запуск

- UI: Бухгалтерия → Требования → «Забрать из СБИС» (фоновая job)
- Host fallback: `python3 scripts/sbis_norm_host_pull.py`
- Smoke файла:

```bash
curl -sS -m 60 -o /tmp/req5.pdf \
  "http://146.19.125.77:8000/api/sbis/requirements/5/file/"
file /tmp/req5.pdf
```

## Идемпотентность

`external_id` в CRM = `sbis-req:{id}`.
