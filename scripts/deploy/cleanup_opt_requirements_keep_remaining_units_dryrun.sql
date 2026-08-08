-- DRY-RUN: requirements whose supplier_inn is not among remaining opt_units.

\echo === Requirements to DELETE (no matching opt_units row) ===
SELECT
  r.id,
  r.supplier_inn,
  COALESCE(r.supplier_name, '') AS supplier_name,
  r.status,
  r.title,
  r.received_at
FROM opt_requirements r
WHERE NOT EXISTS (
  SELECT 1 FROM opt_units u WHERE u.inn = r.supplier_inn
)
ORDER BY r.supplier_inn, r.id;

\echo === Counts ===
SELECT
  (SELECT COUNT(*) FROM opt_requirements) AS total_requirements,
  (
    SELECT COUNT(*)
    FROM opt_requirements r
    WHERE NOT EXISTS (SELECT 1 FROM opt_units u WHERE u.inn = r.supplier_inn)
  ) AS to_delete,
  (
    SELECT COUNT(*)
    FROM opt_requirements r
    WHERE EXISTS (SELECT 1 FROM opt_units u WHERE u.inn = r.supplier_inn)
  ) AS to_keep;
