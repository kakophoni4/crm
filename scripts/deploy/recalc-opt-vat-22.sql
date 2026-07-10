-- Пересчёт НДС в строках OPT-заявок: 20% -> 22% (сумма с НДС не меняется).
--
-- Автоматически выполняется миграцией alembic 0069_opt_vat_22_recalc при деплое.
-- Этот файл — для ручной проверки/повтора:
--   docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/deploy/recalc-opt-vat-22.sql

\echo '=== Строки с НДС ~20% (будут пересчитаны) ==='
SELECT COUNT(*) AS lines_to_fix
FROM lead_opt_order_lines
WHERE amount > 0
  AND amount_without_vat > 0
  AND ABS((vat_amount / amount_without_vat) * 100 - 20) < 1.5;

\echo '=== Пример до/после (первые 10) ==='
SELECT
    o.lead_id,
    o.order_no,
    l.line_no,
    l.supplier_inn,
    l.amount,
    l.vat_amount AS old_vat,
    l.amount_without_vat AS old_wo_vat,
    ROUND(l.amount - ROUND(l.amount / 1.22, 2), 2) AS new_vat,
    ROUND(l.amount / 1.22, 2) AS new_wo_vat
FROM lead_opt_order_lines l
JOIN lead_opt_orders o ON o.id = l.order_id
WHERE l.amount > 0
  AND l.amount_without_vat > 0
  AND ABS((l.vat_amount / l.amount_without_vat) * 100 - 20) < 1.5
ORDER BY o.id, l.line_no
LIMIT 10;

-- Раскомментируйте блок ниже для применения:
/*
BEGIN;

UPDATE lead_opt_order_lines l
SET
    amount_without_vat = ROUND(l.amount / 1.22, 2),
    vat_amount = ROUND(l.amount - ROUND(l.amount / 1.22, 2), 2),
    updated_at = now()
WHERE l.amount > 0
  AND l.amount_without_vat > 0
  AND ABS((l.vat_amount / l.amount_without_vat) * 100 - 20) < 1.5;

\echo '=== Обновлено строк ==='
SELECT COUNT(*) FROM lead_opt_order_lines
WHERE amount > 0
  AND amount_without_vat > 0
  AND ABS((vat_amount / amount_without_vat) * 100 - 22) < 1.5;

COMMIT;
*/
