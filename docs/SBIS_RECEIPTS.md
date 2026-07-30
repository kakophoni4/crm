# Квитанции СБИС (KV/IV) → CRM

Файлы на **`146.19.125.77`**: `/opt/sbis-norm/media/kv_iv_complete`  
(имена `квитанция о приеме (…).pdf` / `извещение о вводе (…).pdf`).

Тянуть **с этой же машины** скриптом из репо — агент читает диск на `.77` и шлёт multipart в API.  
Копировать PDF на CRM-хост **не нужно** (`scp` только если нельзя запускать Python на `.77`).

## CRM (сначала)

```bash
cd ~/crm && git pull
bash scripts/deploy/vps/update.sh
docker exec crm-staging-api alembic upgrade head   # 0091_opt_receipts
```

Токен ingest: `ACCOUNTING_INGEST_TOKEN` из `deploy/.env.staging` на CRM.

## Kali `.77`

```bash
cd ~/crm   # или куда склонирован crm
git pull

export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
export ACCOUNTING_INGEST_TOKEN='…из deploy/.env.staging на CRM…'
export SBIS_RECEIPTS_DIR=/opt/sbis-norm/media/kv_iv_complete

python3 scripts/sbis_receipts_host_pull.py
# фоном:
# python3 scripts/sbis_receipts_host_pull.py --daemon
```

PDF на стороне CRM парсятся (`pypdf`): ИНН, КПП, период («2 квартал 2026» → `2/26`), тип `receipt` / `notice`.

## После ingest

- В заявке (OPT, status submitted): **Скачать квитанции** / **Отправить квитанции** — если по ИНН лавок заявки и её `period_code` есть строки в `opt_receipts`.
- **Мои файлы** → вкладка **Квитанции** → периоды → скачать (ACL: admin/все; старший отдела/группы; оператор — по заявкам своих групп; бухгалтер — назначенные лавки).

## API (справка)

| Метод | Путь |
|-------|------|
| POST | `/api/v1/accounting/receipts/ingest/multipart` |
| POST | `/api/v1/accounting/receipts/pull-claim` |
| POST | `/api/v1/accounting/receipts/sync` |
| GET | `/api/v1/leads/{id}/opt-orders/{id}/receipts` |
| GET | `…/receipts/archive` |
| POST | `…/send-receipts` |
| GET | `/api/v1/storage/receipts/tree` |
| GET | `/api/v1/storage/receipts/{id}/download` |
