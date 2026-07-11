-- Synthetic lavki for scripts/fixtures/opt-test-zayavka-spec.json (dev/tests only)
-- Run standalone:
--   docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/fixtures/seed-opt-test-lavki.sql

INSERT INTO opt_units (inn, kpp, name, category_code, is_active) VALUES
  ('7700000001', '770001001', 'ООО "Тестовая лавка 1"', 'TECH', TRUE),
  ('7700000002', '770001001', 'ООО "Тестовая лавка 2"', 'TECH', TRUE),
  ('7700000003', '770001001', 'ООО "Тестовая лавка 3"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(EXCLUDED.category_code, opt_units.category_code),
  is_active = TRUE;
