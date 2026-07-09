-- Categories/rates from «Парк компаний» spreadsheet (2КВ2026, 09.07.2026)
-- Run after seed-opt-lavki.sql on server

-- Абсолют: ООО "Глория"
UPDATE opt_units
SET category_code = 'L',
    commission_rate_percent = 3.5,
    is_active = TRUE
WHERE inn = '9731112362';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9731112362', 'ООО "Глория"', 'L', 3.5, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9731112362');

-- Оптима: ООО "Лифт Комплекс"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '9718148521';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9718148521', 'ООО "Лифт Комплекс"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9718148521');

-- Оптима: ООО "К-Пласт"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '7743359603';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '7743359603', 'ООО "К-Пласт"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '7743359603');

-- Оптима: ООО "Лорриплюс"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '7724774530';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '7724774530', 'ООО "Лорриплюс"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '7724774530');

-- Оптима: ООО "Пионер"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '9731112429';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9731112429', 'ООО "Пионер"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9731112429');

-- Оптима: ООО "Континент"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '9729097741';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9729097741', 'ООО "Континент"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9729097741');

-- Оптима: ООО "Кохер"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '7734474261';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '7734474261', 'ООО "Кохер"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '7734474261');

-- Оптима: ООО "Рысь"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '7708721010';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '7708721010', 'ООО "Рысь"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '7708721010');

-- Оптима: ООО "Афина"
UPDATE opt_units
SET category_code = 'O',
    commission_rate_percent = 2.8,
    is_active = TRUE
WHERE inn = '9731112323';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9731112323', 'ООО "Афина"', 'O', 2.8, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9731112323');

-- Техничка: ООО "Паром"
UPDATE opt_units
SET category_code = 'TECH',
    commission_rate_percent = 1.1,
    is_active = TRUE
WHERE inn = '9729355449';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9729355449', 'ООО "Паром"', 'TECH', 1.1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9729355449');

-- Техничка: ООО "ТЭК"
UPDATE opt_units
SET category_code = 'TECH',
    commission_rate_percent = 1.1,
    is_active = TRUE
WHERE inn = '5011036907';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '5011036907', 'ООО "ТЭК"', 'TECH', 1.1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '5011036907');

-- Техничка: ООО "Илиона"
UPDATE opt_units
SET category_code = 'TECH',
    commission_rate_percent = 1.1,
    is_active = TRUE
WHERE inn = '9718078916';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9718078916', 'ООО "Илиона"', 'TECH', 1.1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9718078916');

-- Техничка: ООО "Дир Партс"
UPDATE opt_units
SET category_code = 'TECH',
    commission_rate_percent = 1.1,
    is_active = TRUE
WHERE inn = '9719029573';
INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
SELECT '9719029573', 'ООО "Дир Партс"', 'TECH', 1.1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '9719029573');
