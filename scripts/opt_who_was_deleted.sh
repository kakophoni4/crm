#!/usr/bin/env bash
# Forensic: what OPT orders were deleted / missing. Run on VPS.
set -euo pipefail

echo "=============================================="
echo "1) Soft-deleted in DB (только после миграции 0085)"
echo "=============================================="
docker exec crm-staging-api python scripts/opt_deleted_orders.py --list --limit 100 || true

echo ""
echo "=============================================="
echo "2) API/worker logs: delete events (7 дней)"
echo "=============================================="
docker logs crm-staging-api --since 168h 2>&1 \
  | grep -Ei 'opt\.order\.deleted|DELETE.*/opt-orders/|"event".*deleted' \
  | tail -n 100 || echo "(пусто в api)"
docker logs crm-staging-worker --since 168h 2>&1 \
  | grep -Ei 'opt\.order\.deleted|lead_purge' \
  | tail -n 50 || echo "(пусто в worker)"

echo ""
echo "=============================================="
echo "3) Proxy access logs (если есть)"
echo "=============================================="
for d in /var/log/nginx /var/log/caddy /var/log/traefik; do
  if [[ -d "$d" ]]; then
    echo "-- $d --"
    grep -REi 'DELETE.*/opt-orders/' "$d" 2>/dev/null | tail -n 40 || true
  fi
done
ls /var/log/nginx 2>/dev/null || true

echo ""
echo "=============================================="
echo "4) Mole: заявки с Удален=true и СуммаИтого>0 (реальные)"
echo "=============================================="
docker exec -e PYTHONUNBUFFERED=1 crm-staging-api python - <<'PY'
import asyncio, json
from app.modules.leads.opt.mole_client import filter_orders, get_order
from app.modules.leads.opt.sync_diff import mole_crm_id, mole_is_deleted

async def main():
    rows = await filter_orders(period_iso="2026-04-01")
    deleted = [r for r in rows if isinstance(r, dict) and mole_is_deleted(r)]
    print(f"total Удален=true: {len(deleted)}")
    with_sum = []
    for r in deleted:
        cid = mole_crm_id(r) or "?"
        total = float(r.get("СуммаИтого") or 0)
        buyer = (r.get("Покупатель") or {}).get("ИНН")
        name = (r.get("Покупатель") or {}).get("Наименование")
        print(f"  {cid} sum={total} buyer={buyer} {name!r}")
        if total > 0:
            with_sum.append(cid)
            try:
                full = await get_order(cid)
                reg = full.get("Реестр") or []
                print(f"    GET registry_len={len(reg) if isinstance(reg, list) else reg} sum={full.get('СуммаИтого')}")
                open(f"/tmp/mole_deleted_{cid}.json","w",encoding="utf-8").write(
                    json.dumps(full, ensure_ascii=False, indent=2, default=str)
                )
            except Exception as e:
                print(f"    GET fail: {e}")
    print(f"with_sum>0: {len(with_sum)}")
    open("/tmp/mole_deleted_with_sum.txt","w").write("\n".join(with_sum))

asyncio.run(main())
PY

echo ""
echo "=============================================="
echo "5) CRM: покупатели, у которых раньше были заявки vs сейчас"
echo "   (косвенно — сделки с Excel-заявкой и 0 orders)"
echo "=============================================="
docker exec crm-staging-postgres psql -U crm -d crm -c "
WITH app_files AS (
  SELECT DISTINCT m.lead_id,
         left(coalesce(att->>'filename', att->>'name'), 80) AS fname
  FROM messages m
  CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(m.attachments)='array' THEN m.attachments ELSE '[]'::jsonb END
  ) att
  WHERE m.lead_id IS NOT NULL
    AND (
      lower(coalesce(att->>'filename', att->>'name','')) LIKE '%заявк%'
      OR lower(coalesce(att->>'filename', att->>'name','')) LIKE '%zayavk%'
      OR lower(coalesce(att->>'filename', att->>'name','')) LIKE 'файл заяв%'
      OR lower(coalesce(att->>'filename', att->>'name','')) LIKE 'форма_заяв%'
      OR lower(coalesce(att->>'filename', att->>'name','')) LIKE 'форма заяв%'
    )
)
SELECT l.id AS lead_id,
       l.created_at::date,
       c.full_name,
       c.telegram_username,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS orders,
       string_agg(DISTINCT a.fname, ' | ') AS app_files
FROM leads l
JOIN app_files a ON a.lead_id = l.id
LEFT JOIN contacts c ON c.id = l.contact_id
WHERE l.closed_at IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NULL
  )
GROUP BY l.id, l.created_at, c.full_name, c.telegram_username
ORDER BY l.id DESC
LIMIT 80;
"

echo ""
echo "=============================================="
echo "6) Сделки Vera / regmeg — текущее состояние"
echo "=============================================="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT l.id, l.created_at::date, c.full_name, c.telegram_username,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS orders,
       (SELECT coalesce(sum(o.commission_due),0) FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS commission
FROM leads l
JOIN contacts c ON c.id = l.contact_id
WHERE c.telegram_username ILIKE '%garant16%'
   OR c.telegram_username ILIKE '%regmeg%'
   OR c.full_name ILIKE '%Vera Alex%'
ORDER BY l.id DESC;
"

echo ""
echo "DONE. Если п.4 with_sum>0 — это реальные удалёнки в 1С."
echo "Если п.4 пусто — из 1С не восстановить; смотри п.5 (Excel на сделках без заявок)."
