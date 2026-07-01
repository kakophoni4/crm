-- Upsert lavki from opt_units_vane.json (with KPP from EGRUL)
-- Run on server:
--   docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/deploy/seed-opt-lavki.sql

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7730303346', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПЛАНКА ПЛЮС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7707487208', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПЛАНКА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731112323', '773101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АФИНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718148521', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛИФТ КОМПЛЕКС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729097741', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КОНТИНЕНТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731112362', '773101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГЛОРИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7704817881', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИНТЕРА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720865730', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РОДНАЯ ДОРОГА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733412223', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИЕЗ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7708721010', '770801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РЫСЬ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9703234390', '770301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "БАЗИС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9722111250', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "НОВА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7716256800', '771601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ОКТА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9721259849', '772101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КЕДР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9723264555', '772301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СИТИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9701321496', '770101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СПИРИТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720959139', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРОМ-С-ГРУПП"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9725197569', '772501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МЕРИДИАН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9725197600', '772501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СПЕКТР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9723135775', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛАЙТ ХАУС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751231244', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЗЕЛЕНОЕ ЗОЛОТО"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7704452736', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АМК РЕНТА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9706050539', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТРОНГ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9714062471', '771401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГНДАЛ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7708443210', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "УСНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9728146428', '772801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРОДТОРГ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7736365892', '772601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СТРОЙКОМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9707041287', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МЕРКУРИЙ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9703198569', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПСК"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9705235791', '770501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МР БАЗИС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718273321', '771801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛЕДКОМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9726093812', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АСТРА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751352626', '775101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КЛИН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9728150696', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СКАЙ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9726093724', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВОЯЖ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751364195', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИСПУТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7708451444', '770801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КЛАРИКОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751364283', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛЕГЕМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751364212', '772601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "САНСЕТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7708451437', '770801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРАЙМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751364220', '770501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АБСОЛЮТ-СЕРВИС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733413587', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЗАКАТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733413523', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "САТУРН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733412209', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДАЧА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733422870', '770501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГРОЗА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733424500', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПИКАССО"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733421605', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ФОТОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9719053696', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АЗХА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718231498', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГОРГОНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9723206017', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АИН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733414291', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ШУРУП"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733424740', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТЕМПЕРА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733411861', '773101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РАСКАТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733186461', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПОЛИМЕДРУС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7736316905', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КУРОРТ ТВ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9704063532', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ФЛАГМАН ГРУП"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9723236879', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИНСОМА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733419620', '771601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТОПАЗ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733430818', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ШТОРМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9725029797', '772301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВИАГАЗ-АЗИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7706507606', '770501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ФИНБИЗНЕСКОМПАНИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7714995442', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТОРГОВЫЙ ДОМ "СМ-ТРЕЙД"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720741823', '770501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЭЛЕМЕНТ ТОРГ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9726031510', '772601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДОМИНАНТА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7702557532', '773601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АЛЬЯНС-РЕСУРС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733414414', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДОРОГА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733414421', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КИПАРИС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733413883', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АРФА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733414245', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СКАТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733418909', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СПЕКТР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733419081', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВОЛНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733430705', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ОРИОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733418962', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АРКАДА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733419099', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РИКО"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731111337', '773101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "НИКА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731111351', '773101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРЕСТИЖ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731111954', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВИКТОРИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733428671', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИВОЛГА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733424726', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КАРДИНАЛ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733427371', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АРГО"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731110894', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731110830', '773101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ФЕНИКС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9731110887', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВАЛОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9721251871', '772101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВЕРТИКАЛЬ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729401776', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛОБЕЛИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729355449', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПАРОМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729347374', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ФЕЛИКС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729352800', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВИЗИТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7736372811', '773601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ " КАПИТОЛИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9713031600', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГРИНДЭКС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720957607', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРОМСИСТЕМС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('5011036907', '772201001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТЭК"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7743289160', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ОБСЛУЖИВАНИЕ МОНТАЖ СЕРВИС РЕМОНТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720897958', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГС ГРАНД"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751376874', '775101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВАНГАРД"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751377028', '775101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ОПТИМА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7708455826', '770801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРОГРЕСС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729349639', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПИОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729349614', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВЕСНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729349276', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТИТАН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9713030597', '771301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АГАТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9721256975', '772101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТАЙНИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('5009069380', '772401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВЕНТИНДАСТРИ-СМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('5009111280', '772401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВЕНТФОС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751170344', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДВЕНАДЦАТЬ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9715519143', '771501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДВИЖЕНИЕ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9707053229', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЭНЕРГИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9722110200', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СИРИУС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7716255980', '771601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РЕСУРС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9726107977', '772601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СФЕРА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9719029573', '772101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИР ПАРТС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733857550', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВТОПРОЕКТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720478315', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИНЖЕНЕРНО-ТЕХНОЛОГИЧЕСКИЙ ЦЕНТР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733429040', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КРАТЕР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733429442', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "САФАРИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733419469', '773301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СЕЛЕНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7703128790', '772201001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВИАКОМПЛЕКТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9726006827', '772601001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ГЕОИНВЕСТПРОЕКТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9734020085', '773401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВРОРА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9717186355', '771701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КРОНОС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9722110190', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЗИНТЕР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9725197625', '772501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛЕГЕМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720959604', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИСПУТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9705235826', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МИЛТОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7708445313', '770801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АЛЕКСА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9722089653', '772201001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "НОРДПРОМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733591759', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВАНГАРД"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7725346640', '772501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИНВЕСТИЦИОННАЯ ИНИЦИАТИВА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7733286184', '772701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МОСТОРГ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751380912', '775101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПОБЕДА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9723266200', '772301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИМПЕРИЯ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718290373', '771801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРЕМИУМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718291017', '771801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КЕЛЬТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9723266873', '772301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АБИКОМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7751381578', '775101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИЛЕММА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7736374030', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "БИОР"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7720960600', '772001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "НОВАТЭК"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9725200003', '772501001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "НОВЭКС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718078916', '771801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИЛИОНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9710091961', '771001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МАРИУС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7718253642', '771801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МАРКО ПРОФИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729355495', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЗЕРО"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9729352582', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РОСА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7725354440', '770901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СЕРВИС-ПАРТНЕР МОНТАЖ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9721259824', '772101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ИСТА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9701321506', '770101001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МАЯК"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7714463014', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СУШИ БАР 4:3"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9726009144', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РЕГИОН-ХОЛДИНГ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7704617145', '772701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СТРОЙМОНТАЖ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718255315', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РИГЕЛЬ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9704240301', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МЕНСА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9707028695', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "БИЗНЕС ОАЗИС"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7743446937', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "САНТЕХНИКОН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9707024845', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КОД"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9713011121', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ОПОРА ТОП"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9727177432', NULL, 'ООО Окова', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9704235943', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЯНТАРЬ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9704236626', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДРАЙВ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9713011562', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КОРОНА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9724178926', '770201001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЛИГАОПТ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9707025334', '770701001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МЕРИТА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9707027853', '772201001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ДИОГЕН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9705221968', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АБИКОМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7743445443', '774301001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ХАМАЛЬ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9713012862', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ШЕРАТАН"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9704238976', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "БОНИТА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9705221742', '772901001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ЭНЗО"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9713012774', '773001001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АГОРА"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('7734497195', '770401001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МОДИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, kpp, name, category_code, is_active)
VALUES ('9718251783', '771801001', 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТРАНСГЛОБ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;
