# Книги продаж СБИС → CRM

На диске **kali** (`146.19.125.77`):

```text
/opt/sbis-norm/data/sales_books/
  <ИНН_продавца>/
    <ИНН_покупателя>.pdf   ← короткие выписки (ingest)
    _full.pdf              ← полная книга — НИКОГДА не ingest / не отдаём
  _summary.tsv / _*.tsv    ← пропускаем
```

## CRM

```bash
cd ~/crm && git pull
bash scripts/deploy/vps/update.sh
docker exec crm-staging-api alembic upgrade head   # 0096_opt_sales_book_extracts (+ 0097 owners)
```

Токен: тот же `ACCOUNTING_INGEST_TOKEN`, что у квитанций.

## Kali `.77`

```bash
export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
export ACCOUNTING_INGEST_TOKEN='…'
export SBIS_SALES_BOOKS_DIR=/opt/sbis-norm/data/sales_books
# опционально — только metadata.period_hint, UI фильтрует по заявкам периода:
# export SBIS_SALES_BOOKS_PERIOD_HINT=2/26

python3 scripts/sbis_sales_books_host_pull.py
```

`external_id = sbis-sb:{sha256[:40]}`.

## После ingest

- В периоде (хранилище / пикер чата): папка **Книги продаж** — выписки, для которых есть неудалённая заявка с `period_code` и парой `(supplier_inn, buyer_inn)`.
- В заявке: **Скачать / Отправить книгу продаж** — только короткие PDF по парам заявки (несколько вложений; ZIP при скачивании).
- ACL как у квитанций: admin/chief — всё; бухгалтер — назначенные лавки (seller); senior — отдел; иначе — пары из заявок видимых групп.

## API

| Метод | Путь |
|-------|------|
| POST | `/api/v1/accounting/sales-books/ingest/multipart` |
| GET | `/api/v1/leads/{id}/opt-orders/{id}/sales-book-extracts` |
| GET | `…/sales-book-extracts/archive` |
| POST | `…/send-sales-book` |
| GET | `/api/v1/storage/receipts/tree` (поле `sales_books` в периоде) |
| GET | `/api/v1/storage/sales-books/{id}/download` |
