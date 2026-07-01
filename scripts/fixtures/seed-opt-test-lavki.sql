-- Lavki for scripts/fixtures/Заявка-тест-CRM.xlsx (NAVEL-style test application)
-- Run after seed-opt-lavki.sh or standalone:
--   docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/fixtures/seed-opt-test-lavki.sql

INSERT INTO opt_units (inn, kpp, name, category_code, is_active) VALUES
  ('7703822568', NULL, 'Лавка 7703822568', 'TECH', TRUE),
  ('7743622734', '774301001', 'СПЕЦАВТОТРАНССЕРВИС ООО', 'TECH', TRUE),
  ('7713151911', '771401001', 'СК ДОМРЕМСТРОЙ ПЛЮС ООО', 'TECH', TRUE),
  ('7720313708', '772001001', 'АСВ-ТЕХНОЛОГИИ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = EXCLUDED.kpp,
  name = EXCLUDED.name,
  category_code = EXCLUDED.category_code,
  is_active = TRUE;
