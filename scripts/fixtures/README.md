# OPT fixtures (public / synthetic only)

В git хранятся **только синтетические** данные для тестов и примеров.

## Нельзя коммитить

- Реальные лавки, парки компаний, заявки (xlsx/xls)
- Сгенерированные seed SQL с боевыми ИНН/КПП
- Логи, архивы, выгрузки 1С

Такие файлы лежат **локально на VPS** или у оператора, пути в `.gitignore`.

## Примеры в репозитории

| Файл | Назначение |
|------|------------|
| `opt_units.example.json` | 3 тестовые лавки |
| `opt_park_categories.example.json` | пример категорий/ставок |
| `opt-test-zayavka-spec.json` | спецификация заявки для тестов парсера |

## Локальные (gitignored) рабочие файлы

| Файл | Назначение |
|------|------------|
| `scripts/opt_units_vane.json` | полный список лавок (из xlsx) |
| `scripts/opt_park_categories.json` | парк компаний из xlsx |
| `scripts/deploy/seed-opt-lavki.sql` | SQL для VPS, генерируется скриптами |
| `scripts/deploy/seed-opt-park-categories.sql` | SQL категорий, генерируется |

### Генерация на VPS

```bash
# из xlsx (файл только на сервере, не в git)
py scripts/opt_sync_lavki_from_xlsx.py --xlsx /path/to/lavki.xlsx
py scripts/opt_sync_park_from_xlsx.py --xlsx /path/to/park.xlsx
bash scripts/deploy/seed-opt-lavki.sh
```

### Тестовый xlsx для pytest

```bash
py scripts/opt_build_test_zayavka.py
# → scripts/fixtures/opt-test-crm.xlsx (gitignored)
```
