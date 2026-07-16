-- Check which park INNs already exist in opt_units.
-- Usage (VPS from repo root):
--   source scripts/deploy/vps/compose.sh
--   compose exec -T postgres psql -U crm -d crm < scripts/deploy/check-opt-park-inns.sql

WITH park(inn, name) AS (
  VALUES
    ('7708721010', 'ООО "Рысь"'),
    ('9729097741', 'ООО "Континент"'),
    ('9731112362', 'ООО "Глория"'),
    ('9718148521', 'ООО "Лифт Комплекс"'),
    ('7743359603', 'ООО "К-Пласт"'),
    ('7724774530', 'ООО "Лорриплюс"'),
    ('9731112429', 'ООО "Пионер"'),
    ('7734474261', 'ООО "Кохер"'),
    ('9731112323', 'ООО "Афина"'),
    ('9729355449', 'ООО "Паром"'),
    ('5011036907', 'ООО "ТЭК"'),
    ('9718078916', 'ООО "Илиона"'),
    ('9719029573', 'ООО "Дир Партс"')
)
SELECT
  p.inn,
  COALESCE(u.name, p.name) AS name,
  CASE
    WHEN u.id IS NULL THEN 'MISSING'
    WHEN u.is_active THEN 'ACTIVE'
    ELSE 'INACTIVE'
  END AS status,
  u.category_code,
  u.commission_rate_percent
FROM park p
LEFT JOIN opt_units u ON u.inn = p.inn
ORDER BY status, p.inn;

SELECT
  COUNT(*) FILTER (WHERE u.id IS NOT NULL AND u.is_active) AS already_active,
  COUNT(*) FILTER (WHERE u.id IS NOT NULL AND NOT u.is_active) AS exists_inactive,
  COUNT(*) FILTER (WHERE u.id IS NULL) AS missing
FROM (
  VALUES
    ('7708721010'), ('9729097741'), ('9731112362'), ('9718148521'),
    ('7743359603'), ('7724774530'), ('9731112429'), ('7734474261'),
    ('9731112323'), ('9729355449'), ('5011036907'), ('9718078916'),
    ('9719029573')
) AS park(inn)
LEFT JOIN opt_units u ON u.inn = park.inn;
