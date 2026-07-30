# Квитанции СБИС (KV/IV)

## Поток

```
kali: /opt/sbis-norm/media/kv_iv_complete/*.pdf
  → scripts/sbis_receipts_host_pull.py
  → POST /api/v1/accounting/receipts/ingest/multipart
  → opt_receipts + MinIO
  → UI: заявка (ZIP / отправить) + Мои файлы → Квитанции
```

## Kali

```bash
export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
export ACCOUNTING_INGEST_TOKEN='…'
export SBIS_RECEIPTS_DIR=/opt/sbis-norm/media/kv_iv_complete
python3 /path/to/crm/scripts/sbis_receipts_host_pull.py
# или daemon (ждёт pull-claim + можно крутить cron):
python3 /path/to/crm/scripts/sbis_receipts_host_pull.py --daemon
```

PDF парсятся на стороне CRM (`pypdf`): ИНН, КПП, период («2 квартал 2026» → `2/26`), тип receipt/notice.

## CRM

После `git pull` + rebuild:

```bash
docker exec crm-staging-api alembic upgrade head   # 0091_opt_receipts
# убедиться что в образе есть pypdf
```

Кнопки в заявке появляются, если по ИНН лавок заявки и её `period_code` уже есть строки в `opt_receipts`.
