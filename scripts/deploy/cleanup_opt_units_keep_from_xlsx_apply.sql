-- APPLY: delete opt_units not in keep list AND without active orders.
-- Run DRY-RUN first: cleanup_opt_units_keep_from_xlsx_dryrun.sql

BEGIN;

CREATE TEMP TABLE keep_inn(inn text PRIMARY KEY) ON COMMIT DROP;
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

DELETE FROM opt_unit_period_availability p
USING opt_units u
WHERE p.inn = u.inn
  AND NOT EXISTS (SELECT 1 FROM keep_inn k WHERE k.inn = u.inn)
  AND NOT EXISTS (
    SELECT 1
    FROM lead_opt_order_lines l
    JOIN lead_opt_orders o ON o.id = l.order_id
    WHERE l.supplier_inn = u.inn
      AND o.deleted_at IS NULL
  );

DELETE FROM opt_units u
WHERE NOT EXISTS (SELECT 1 FROM keep_inn k WHERE k.inn = u.inn)
  AND NOT EXISTS (
    SELECT 1
    FROM lead_opt_order_lines l
    JOIN lead_opt_orders o ON o.id = l.order_id
    WHERE l.supplier_inn = u.inn
      AND o.deleted_at IS NULL
  );

\echo '=== Still blocked (kept because of orders) ==='
SELECT
  u.id,
  u.inn,
  u.name,
  COUNT(DISTINCT o.id) AS active_orders
FROM opt_units u
JOIN lead_opt_order_lines l ON l.supplier_inn = u.inn
JOIN lead_opt_orders o ON o.id = l.order_id AND o.deleted_at IS NULL
WHERE NOT EXISTS (SELECT 1 FROM keep_inn k WHERE k.inn = u.inn)
GROUP BY u.id, u.inn, u.name
ORDER BY active_orders DESC;

\echo '=== Remaining units count ==='
SELECT COUNT(*) AS units_left FROM opt_units;

COMMIT;
