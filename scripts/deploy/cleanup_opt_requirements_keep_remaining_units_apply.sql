-- APPLY: delete requirements not tied to remaining opt_units.

BEGIN;

\echo === Before ===
SELECT COUNT(*) AS requirements_before FROM opt_requirements;

DELETE FROM opt_requirements r
WHERE NOT EXISTS (
  SELECT 1 FROM opt_units u WHERE u.inn = r.supplier_inn
);

\echo === After ===
SELECT COUNT(*) AS requirements_after FROM opt_requirements;

\echo === Orphans check (should be 0) ===
SELECT COUNT(*) AS still_orphaned
FROM opt_requirements r
WHERE NOT EXISTS (SELECT 1 FROM opt_units u WHERE u.inn = r.supplier_inn);

COMMIT;
