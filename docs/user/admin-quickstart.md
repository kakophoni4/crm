# Быстрый старт — администратор (v1)

> **UI:** в operator SPA доступен раздел **Админка** (`/admin`) для пользователей с ролью `admin`. Старшие (`senior`) видят только «Эскалацию»; org-CRUD — у admin.

## Что доступно в веб-интерфейсе (`/admin`)

| Раздел | Путь | Задачи |
|--------|------|--------|
| Dashboard | `/admin` | Ссылки на все подразделы |
| Отделы | `/admin/departments` | Список, создание, редактирование, удаление пустых отделов |
| Группы | `/admin/groups` | Фильтр по отделу, CRUD групп |
| Пользователи | `/admin/users` | CRUD, роль, группа, сброс пароля |
| Боты | `/admin/bots` | Список, создание, ротация inbound/outbound секретов |
| Статусы | `/admin/statuses` | Вкладки `chat_label` и `lead_pipeline`, создание и деактивация |

Войдите под учётной записью admin → в боковом меню пункт **«Админка»**.

## Что по-прежнему через API / DevOps

| Задача | Как |
|--------|-----|
| Первый администратор на staging | Seed при миграции (`SEED_ADMIN_*` в env) — см. [`../DEPLOY.md`](../DEPLOY.md) |
| Первый администратор на production | Смена seed-пароля + UI/API — см. [`../DEPLOY.md`](../DEPLOY.md) § «Первый реальный админ в prod» |
| Мониторинг, бэкапы, TLS | DevOps — [`../DEPLOY.md`](../DEPLOY.md), [`../OBSERVABILITY.md`](../OBSERVABILITY.md) |

## Минимальный сценарий (UI или API)

1. **Отдел** — `/admin/departments` или `POST /api/v1/departments`
2. **Группа** — `/admin/groups` или `POST /api/v1/groups` с `department_id`
3. **Оператор** — `/admin/users` или `POST /api/v1/users` с `group_id`
4. **Метка чата** — `/admin/statuses` → вкладка «Метки чатов» → создать `chat_label` (появится в чатах после обновления списка)

Пример через curl (после `POST /api/v1/auth/login`):

```bash
curl -sS -X POST "$API/departments" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Продажи"}'
```

Полный контракт: [`../API_CONTRACT.md`](../API_CONTRACT.md). RBAC: [`../RBAC_MATRIX.md`](../RBAC_MATRIX.md).

## Безопасность (обязательно на prod)

- Смените пароль seed-админа сразу после первого входа.
- Очистите `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` в env после bootstrap.
- Не передавайте `inbound_secret` / `outbound_secret` в мессенджерах и почте без шифрования.
- Включите бэкапы Postgres и MinIO на сервере (cron) — [`../OBSERVABILITY.md`](../OBSERVABILITY.md).

## Приёмка

- Автоматический smoke после деплоя: `scripts/smoke/staging_smoke.sh`
- UAT заказчика: [`../../scripts/smoke/uat_checklist.md`](../../scripts/smoke/uat_checklist.md)

Операторам выдайте [`operator-quickstart.md`](operator-quickstart.md).
