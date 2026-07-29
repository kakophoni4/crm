-- DRY-RUN only: preview which opt_units would be deleted.
-- Keep list from «КОМПАНИИ В СРМ» spreadsheet.

CREATE TEMP TABLE keep_inn(inn text PRIMARY KEY);
INSERT INTO keep_inn(inn) VALUES
  ('9731112323'),
  ('9718148521'),
  ('9731112362'),
  ('7704817881'),
  ('7708721010'),
  ('9703234390'),
  ('9722111250'),
  ('7716256800'),
  ('9721259849'),
  ('9723264555'),
  ('9701321496'),
  ('7720959139'),
  ('9725197569'),
  ('9725197600'),
  ('7743359603'),
  ('9729097741'),
  ('7734474261'),
  ('7724774530'),
  ('9731112429'),
  ('9724051292'),
  ('7718139114'),
  ('7707795812'),
  ('9725029797'),
  ('7714995442'),
  ('7733414245'),
  ('7733418909'),
  ('7733419081'),
  ('7733430705'),
  ('7733418962'),
  ('7733419099'),
  ('9729355449'),
  ('9729347374'),
  ('9729352800'),
  ('5011036907'),
  ('7743289160'),
  ('7720897958'),
  ('7751376874'),
  ('7751377028'),
  ('7708455826'),
  ('5009111280'),
  ('7751170344'),
  ('9715519143'),
  ('9707053229'),
  ('9722110200'),
  ('7716255980'),
  ('9726107977'),
  ('9719029573'),
  ('7733857550'),
  ('7720478315'),
  ('9734020085'),
  ('9722110190'),
  ('9725197625'),
  ('7720959604'),
  ('7725346640'),
  ('7733286184'),
  ('9718291017'),
  ('9723266873'),
  ('7751381578'),
  ('7736374030'),
  ('7720960600'),
  ('9725200003'),
  ('9718078916'),
  ('9710091961'),
  ('7718253642'),
  ('9729355495'),
  ('9729352582'),
  ('7725354440'),
  ('9721259824'),
  ('9701321506'),
  ('7716949498'),
  ('9718251783'),
  ('7733412061'),
  ('7733362702'),
  ('7716936690'),
  ('7724864960'),
  ('9718288381'),
  ('9724231190'),
  ('7751375824'),
  ('9725197181'),
  ('9715519249'),
  ('7733406614'),
  ('7726418680'),
  ('9709054034'),
  ('7734474060'),
  ('7708413375'),
  ('7728324349'),
  ('9729323581');

\echo '=== Units NOT in keep list ==='
SELECT
  u.id,
  u.inn,
  u.name,
  u.is_active,
  COALESCE(ord.active_orders, 0) AS active_orders,
  CASE
    WHEN COALESCE(ord.active_orders, 0) > 0 THEN 'BLOCKED: has orders'
    ELSE 'OK to delete'
  END AS action
FROM opt_units u
LEFT JOIN LATERAL (
  SELECT COUNT(DISTINCT o.id) AS active_orders
  FROM lead_opt_order_lines l
  JOIN lead_opt_orders o ON o.id = l.order_id
  WHERE l.supplier_inn = u.inn
    AND o.deleted_at IS NULL
) ord ON TRUE
WHERE NOT EXISTS (SELECT 1 FROM keep_inn k WHERE k.inn = u.inn)
ORDER BY active_orders DESC, u.name;

\echo '=== Counts ==='
SELECT
  COUNT(*) FILTER (WHERE COALESCE(ord.active_orders, 0) = 0) AS ok_to_delete,
  COUNT(*) FILTER (WHERE COALESCE(ord.active_orders, 0) > 0) AS blocked_with_orders
FROM opt_units u
LEFT JOIN LATERAL (
  SELECT COUNT(DISTINCT o.id) AS active_orders
  FROM lead_opt_order_lines l
  JOIN lead_opt_orders o ON o.id = l.order_id
  WHERE l.supplier_inn = u.inn
    AND o.deleted_at IS NULL
) ord ON TRUE
WHERE NOT EXISTS (SELECT 1 FROM keep_inn k WHERE k.inn = u.inn);

\echo '=== Keep-list INNs missing in CRM ==='
SELECT k.inn AS missing_in_crm
FROM keep_inn k
WHERE NOT EXISTS (SELECT 1 FROM opt_units u WHERE u.inn = k.inn)
ORDER BY k.inn;
