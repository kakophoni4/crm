-- Upsert lavki from opt_units_vane.json / лавки Ване.xlsx
-- Run on server:
--   docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/deploy/seed-opt-lavki.sql

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7730303346', 'ПЛАНКА ПЛЮС (ГРУППА В)', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7707487208', 'ПЛАНКА (ГРУППА В)', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731112323', 'ООО "Афина"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718148521', 'Лифт Комплекс', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729097741', 'Континент', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731112362', 'Глория', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7704817881', 'Принтера', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720865730', 'РД', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733412223', 'Диез', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7708721010', 'ООО "Рысь"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9703234390', 'БАЗИС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9722111250', 'НОВА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7716256800', 'ОКТА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9721259849', 'КЕДР ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9723264555', 'СИТИ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9701321496', 'СПИРИТ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720959139', 'ПРОМ-С-ГРУПП ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9725197569', 'МЕРИДИАН ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9725197600', 'СПЕКТР ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9723135775', 'ЛАЙТ ХАУС', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751231244', 'ооо зеленое золото', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7704452736', 'ооо амк рента', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9706050539', 'ооо тронг', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9714062471', 'ооо гндал', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7708443210', 'ооо усна', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9728146428', 'ооо продторг', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7736365892', 'ооо стройком', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9707041287', 'ооо меркурий', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9703198569', 'ооо пск', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9705235791', 'ооо мр базис', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718273321', 'ооо ледком', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9726093812', 'ооо астра', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751352626', 'ооо клин', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9728150696', 'ооо скай', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9726093724', 'ооо вояж', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751364195', 'ооо диспут', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7708451444', 'ооо кларикон', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751364283', 'ооо легем', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751364212', 'ооо сансет', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7708451437', 'ооо прайм', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751364220', 'ооо абсолют сервис', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733413587', 'ООО Закат', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733413523', 'ООО Сатурн', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733412209', 'ООО Дача', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733422870', 'ГРОЗА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733424500', 'ПИКАССО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733421605', 'ФОТОН', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9719053696', 'АЗХА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718231498', 'ГОРГОНА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9723206017', 'АИН', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733414291', 'ООО ШУРУП', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733424740', 'ООО ТЕМПЕРА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733411861', 'ООО РАСКАТ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733186461', 'ООО ПОЛИМЕДРЕСУРС', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7736316905', 'ООО КУРОРТ ТВ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9704063532', 'ООО ФЛАГМАН ГРУПП', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9723236879', 'ИНСОМА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733419620', 'ООО "Топаз"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733430818', 'ООО "Шторм"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9725029797', 'ООО "Авиагаз-Азия"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7706507606', 'ООО "ФИНБИЗНЕСКОМПАНИ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7714995442', 'ООО "ТД СМ-рейд"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720741823', 'ЭлементТорг', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9726031510', 'Доминанта', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7702557532', 'ООО "Альянс-Ресурс"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733414414', 'Дорога', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733414421', 'Кипарис', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733413883', 'Арфа', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733414245', 'Скат', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733418909', 'Спектр', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733419081', 'Волна', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733430705', 'Орион', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733418962', 'Аркада', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733419099', 'Рико', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731111337', 'Ника', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731111351', 'Престиж', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731111954', 'Виктория', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733428671', 'Иволга', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733424726', 'Кардинал', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733427371', 'Арго', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731110894', 'Дион', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731110830', 'Феникс', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9731110887', 'Авалон', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9721251871', 'ВЕРТИКАЛЬ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729401776', 'ЛОБЕЛИЯ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729355449', 'ООО "Паром"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729347374', 'ООО "Феликс"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729352800', 'ООО "Визит"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7736372811', 'КАПИТОЛИЯ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9713031600', 'ГРИНДЭКС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720957607', 'ПРОМСИСТЕМС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('5011036907', 'ООО ТЭК', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7743289160', 'ОМСР', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720897958', 'ГС ГРАНД', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751376874', 'АВАНГАРД ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751377028', 'ОПТИМА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7708455826', 'ПРОГРЕСС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729349639', 'ПИОН ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729349614', 'ВЕСНА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729349276', 'ТИТАН ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9713030597', 'АГАТ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9721256975', 'ТАЙНИ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('5009069380', 'ООО "Вентиндастри-СМ"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('5009111280', 'ООО "Вентфос"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751170344', 'ООО "Двенадцать"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9715519143', 'ДВИЖЕНИЕ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9707053229', 'ЭНЕРГИЯ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9722110200', 'СИРИУС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7716255980', 'РЕСУРС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9726107977', 'СФЕРА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9719029573', 'ДИР ПАРТС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733857550', 'АВТОПРОЕКТ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720478315', 'ИТЦ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733429040', 'КРАТЕР ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733429442', 'САФАРИ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733419469', 'СЕЛЕНА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7703128790', 'ООО "Авиакомплект"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9726006827', 'ООО "Геоинвестпроект"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9734020085', 'АВРОРА2 ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9717186355', 'КРОНОС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9722110190', 'ЗИНТЕР', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9725197625', 'ЛЕГЕМ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720959604', 'ДИСПУТ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9705235826', 'МИЛТОН ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7708445313', 'АЛЕКСА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9722089653', 'НОРДПРОМ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733591759', 'ООО "Авангард"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7725346640', 'ООО "Инвестиционная Инициатива"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7733286184', 'ООО "Мосторг"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751380912', 'ПОБЕДА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9723266200', 'ИМПЕРИЯ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718290373', 'ПРЕМИУМ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718291017', 'КЕЛЬТ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9723266873', 'АБИКОМ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7751381578', 'ДИЛЕММА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7736374030', 'БИОР ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7720960600', 'НОВАТЭК ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9725200003', 'НОВЭКС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718078916', 'ООО "Илиона"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9710091961', 'ООО "Мариус»', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7718253642', 'ООО "Марко Профи"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729355495', 'ЗЕРО ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9729352582', 'РОСА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7725354440', 'СЕРВИС-ПАРТНЕР МОНТАЖ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9721259824', 'ИСТА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9701321506', 'МАЯК ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7714463014', 'ооо суши бар 4.3', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9726009144', 'ооо регион холдинг', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7704617145', 'ооо строймонтаж', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718255315', 'РИГЕЛЬ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9704240301', 'МЕНСА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9707028695', 'БИЗНЕС ОАЗИС ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7743446937', 'САНТЕХНИКОН ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9707024845', 'ООО Код', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9713011121', 'ООО Опора топ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9727177432', 'ООО Окова', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9704235943', 'ООО Янтарь', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9704236626', 'ДРАЙВ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9713011562', 'КОРОНА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9724178926', 'ЛИГАОПТ ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9707025334', 'МЕРИТА ООО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9707027853', 'ДИОГЕН', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9705221968', 'АБИКОМ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7743445443', 'ХАМАЛЬ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9713012862', 'ШЕРАТАН', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9704238976', 'БОНИТА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9705221742', 'ЭНЗО', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9713012774', 'АГОРА', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('7734497195', 'МОДИ', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;

INSERT INTO opt_units (inn, name, category_code, is_active)
VALUES ('9718251783', 'ООО "Трансглоб"', 'TECH', TRUE)
ON CONFLICT (inn) DO UPDATE SET
  name = EXCLUDED.name,
  category_code = COALESCE(opt_units.category_code, 'TECH'),
  is_active = TRUE;
