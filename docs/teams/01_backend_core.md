# Backend Core

> Фундамент всего бэкенда. Без этой команды у остальных не будет ни базы, ни прав, ни событий.

---

## 1. Зона ответственности

- Скелет FastAPI: фабрика приложения, конфиг, lifecycle, middleware, DI.
- Подключение БД: SQLAlchemy 2 async, sessions, unit-of-work, Alembic.
- Аутентификация: login, refresh-tokens (Redis), logout, force-logout, ws-ticket.
- Авторизация: реестр permissions, маппинг ролей, scope-резолвер.
- Оргструктура: users, departments, groups (CRUD + бизнес-правила).
- Общий audit_log + outbox + event-bus + redis-bridge.
- Структурное логирование, маскирование PII, request-id middleware.
- Обработка ошибок (единый формат).

---

## 2. Стек и зависимости

```
fastapi ^0.111
uvicorn[standard] ^0.30
sqlalchemy[asyncio] ^2.0
asyncpg ^0.29
alembic ^1.13
pydantic ^2.7
pydantic-settings ^2.3
passlib[bcrypt] ^1.7      # или argon2-cffi
python-jose[cryptography] ^3.3
redis ^5.0                # async client
arq ^0.26
structlog ^24.1
sentry-sdk ^2.5
httpx ^0.27               # для тестов и интеграций
pytest ^8.2 + pytest-asyncio + httpx
```

---

## 3. Backlog

### Epic 1. Скелет приложения
- [ ] `app/main.py` — фабрика `create_app()`, lifespan (init redis, db, bus).
- [ ] `app/shared/settings.py` — Pydantic Settings, переменные из env.
- [ ] `app/shared/db.py` — async engine, session factory, `get_db()` DI.
- [ ] `app/shared/redis.py` — async Redis-клиент.
- [ ] `app/shared/logging.py` — structlog config, JSON output, request_id.
- [ ] Middleware: request-id, логирование запросов/ответов, error handler.
- [ ] `alembic/` инициализация, первая пустая миграция.
- [ ] Healthcheck `GET /healthz` (db ping, redis ping).
- [ ] OpenAPI с Bearer-схемой, тегами по модулям.
- [ ] **DoD:** `uvicorn app.main:app` поднимается, `/healthz` зелёный, swagger открывается.

### Epic 2. БД и оргструктура
- [ ] Миграция: `users`, `departments`, `groups`, enums.
- [ ] Модели SQLAlchemy + relationships.
- [ ] Репозитории (async): users, departments, groups.
- [ ] Сервисы: `users_service`, `departments_service`, `groups_service` с бизнес-правилами:
  - senior может создавать только в свой отдел;
  - user обязан иметь `group_id`;
  - department нельзя удалить с активными группами;
  - и т.д. (см. `RBAC_MATRIX.md`).
- [ ] Pydantic schemas: входные/выходные DTO, исключение `password_hash`.
- [ ] **DoD:** unit-тесты на сервисы (95%+ покрытие бизнес-правил).

### Epic 3. Auth
- [ ] Хеширование паролей (passlib).
- [ ] JWT access (15 мин, HS256), refresh (UUID jti, хранится в Redis с TTL).
- [ ] `POST /auth/login` (rate-limit 10/мин по IP).
- [ ] `POST /auth/refresh`, `POST /auth/logout`.
- [ ] `GET /auth/me` (с расчётом permissions).
- [ ] `POST /auth/me/password` (требует старый пароль).
- [ ] `POST /auth/ws-ticket` (короткоживущий, 60 сек, в Redis).
- [ ] `POST /users/{id}/force-logout` (с проверкой scope).
- [ ] **DoD:** интеграционные тесты login/refresh/logout/force-logout.

### Epic 4. RBAC и Scope
- [ ] `core/auth/permissions.py` — реестр констант.
- [ ] `core/auth/rbac.py` — карта роль → permissions.
- [ ] `core/auth/scope.py` — `build_*_scope(actor)` функции для users, departments, groups, chats, contacts, audit, bots.
- [ ] DI-зависимости: `require_permission(P.X)`, `require_role('admin')`.
- [ ] Тесты на каждый scope-резолвер.
- [ ] **DoD:** RBAC-матрица выполняется тестами автоматически (см. `07_qa.md`).

### Epic 5. CRUD API
- [ ] `users` API (см. `API_CONTRACT.md` §3).
- [ ] `departments` API (§4).
- [ ] `groups` API (§5).
- [ ] Везде применён scope, везде пишется audit-event.

### Epic 6. Шина событий и аудит
- [ ] `events_outbox` миграция.
- [ ] `shared/events/bus.py` — интерфейс EventBus.
- [ ] `shared/events/outbox.py` — writer (в той же транзакции) и worker (ARQ).
- [ ] `shared/events/redis_bridge.py` — публикация в Pub/Sub после outbox.
- [ ] `shared/events/topics.py` — все константы из `EVENTS.md`.
- [ ] `modules/audit/handlers.py` — wildcard subscriber, пишет в `audit_log`.
- [ ] PII-фильтр в `audit.write()` (telegram_user_id, inbound_secret, outbound_secret, password).
- [ ] **DoD:** при создании юзера в БД появляется и outbox-запись и audit-запись.

### Epic 7. Платформа для других команд
- [ ] Документ `developer-guide.md` (внутри репы): «как добавить модуль».
- [ ] Шаблон модуля (cookie-cutter или просто пример папки).
- [ ] Шаблоны Pydantic-схем, репозиториев, тестов.

---

## 4. Точки интеграции

### Что Backend Core отдаёт другим
- `app/core/auth/dependencies.py`: `current_user`, `require_permission`, `require_role`.
- `app/core/auth/scope.py`: scope-функции (chats, contacts использует).
- `app/shared/events/bus.py`: API публикации событий.
- `app/shared/db.py`: `get_db` DI.
- Сервисы users/departments/groups для других модулей (через интерфейс, не напрямую).

### Что Backend Core берёт
- Ничего, кроме инфраструктуры (DevOps).

---

## 5. Definition of Done команды (готовность к Фазе 2)

- ✅ FastAPI поднимается, healthz зелёный.
- ✅ Можно создать админа через скрипт `seed.py`.
- ✅ Login/refresh/logout работают.
- ✅ CRUD users/departments/groups работает с RBAC.
- ✅ Outbox + audit пишут события.
- ✅ Тесты RBAC-матрицы проходят.
- ✅ Документация `API_CONTRACT.md` для §2–§5 совпадает с реализацией.

---

## 6. Слабые места команды

1. **JWT secret и прочие — в env.** Если не подключить Vault/Doppler, секреты будут расползаться по `.env` файлам разработчиков. Зафиксировать «никаких prod-секретов в .env».
2. **Scope-функции — горячая зона.** Любая ошибка → утечка данных. Не мерджить scope-изменения без peer review + тестов.
3. **Force-logout user в распределённой среде** требует консистентного Redis. Пока один Redis-инстанс — ок; при кластере проверить, что все ноды видят `DEL`.
4. **Outbox-воркер — единая точка.** Если он остановлен, события копятся в БД, аудит и WS пуши встают. Алёрт на `events_outbox WHERE processed_at IS NULL AND created_at < now() - 30 sec`.
5. **JWT с длинным TTL access-token** — частая ошибка. Держим 15 мин, ни в коем случае не «1 день для удобства».
