# Команды и роли — общий обзор

> Этот документ читают все. У каждой команды/субагента — свой файл с детальным backlog'ом. Здесь — как они стыкуются.

---

## 1. Состав команд

| # | Команда / Субагент | Стек | Файл задач |
|---|---|---|---|
| 1 | **Backend Core** | Python, FastAPI, SQLAlchemy, Alembic | [`01_backend_core.md`](./01_backend_core.md) |
| 2 | **Backend Chats** | Python, FastAPI, asyncio, Redis | [`02_backend_chats.md`](./02_backend_chats.md) |
| 3 | **Backend Bots Integration** | Python, FastAPI, httpx, ARQ, HMAC | [`03_bots_integration.md`](./03_bots_integration.md) |
| 4 | **Backend Contacts** | Python, FastAPI, JSONB, MinIO | [`04_backend_contacts.md`](./04_backend_contacts.md) |
| 5 | **Frontend** | Vue 3, TS, Pinia, Vite, Naive UI | [`05_frontend.md`](./05_frontend.md) |
| 6 | **DevOps** | Docker, Traefik, Loki, Grafana, GH Actions | [`06_devops.md`](./06_devops.md) |
| 7 | **QA** | pytest, Playwright, k6 | [`07_qa.md`](./07_qa.md) |

> Если работаешь в одиночку — каждый файл = твой следующий стек задач. Если команда из 2 человек — один берёт Backend Core+Contacts+Bots Integration, второй Chats+Frontend, DevOps/QA делятся пополам.

---

## 2. Карта владения (ownership)

```
                    ┌──────────────────────────────────┐
                    │           Backend Core           │
                    │  auth, users, dept, groups, RBAC │
                    │  audit, outbox, event-bus,       │
                    │  скелет приложения               │
                    └──────┬─────────┬─────────┬───────┘
                           │         │         │
              ┌────────────┘         │         └────────────┐
              ▼                      ▼                      ▼
              ┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
   │ Backend Contacts   │ │  Backend Chats     │ │ Backend Bots Integ │
   │ contacts, custom,  │ │  chats, messages,  │ │ /bot-events ingest,│
   │ statuses, files,   │ │  transfers,        │ │ outbound dispatch, │
   │ field-history      │ │  takeover, WS Hub  │ │ HMAC, healthcheck  │
   └─────────┬──────────┘ └─────────┬──────────┘ └─────────┬──────────┘
             │                      │                      │
             └──────────────────────┼──────────────────────┘
                                    │ публичный REST + WS
                                    ▼
                          ┌────────────────────┐
                          │     Frontend       │
                          │ Vue 3 SPA          │
                          └────────────────────┘
                                    │
                                    │ всё это завёрнуто и катится
                                    ▼
                          ┌────────────────────┐
                          │      DevOps        │
                          │ Docker, CI, infra  │
                          └────────────────────┘
                                    │
                                    │ перед каждым релизом
                                    ▼
                          ┌────────────────────┐
                          │        QA          │
                          │ unit/e2e/load      │
                          └────────────────────┘
```

---

## 3. Жёсткие правила взаимодействия

1. **Никаких прямых обращений к чужим репозиториям.** Если модулю Chats нужен пользователь — он зовёт `users_service.get(id)`, а не `db.query(User)`.
2. **Любое изменение публичного интерфейса = PR в `docs/`.**
   - REST → `API_CONTRACT.md`
   - События → `EVENTS.md`
   - Схема БД → `DATABASE.md`
   - Права → `RBAC_MATRIX.md`
3. **События — основной канал между модулями.** Если завязка получилась через прямой вызов — задумайся, не должно ли быть событие.
4. **Тесты публичных интерфейсов обязательны.** Сервис без тестов на свой публичный API не мерджится.
5. **Имена пакетов и пути совпадают** с `ARCHITECTURE.md` §3.

---

## 4. Точки синхронизации между командами

| Что | Кто синкает | Когда |
|---|---|---|
| Скелет приложения, db, auth готов | Backend Core → все остальные | конец Фазы 1 |
| Контракт REST для chats | Backend Chats → Frontend | начало Фазы 3 |
| Контракт WS-событий | Backend Chats → Frontend | начало Фазы 3 |
| Публичный URL CRM для приёма `/bot-events` | DevOps → Backend Bots Integration | Фаза 3 (нужен HTTPS-домен) |
| Финализация контракта `BOTS_INTEGRATION.md` | Backend Bots Integration ↔ авторы ботов | Фаза 2 (на бумаге) → Фаза 3 (реализация) |
| Схемы кастом-полей контакта | Backend Contacts → Frontend | Фаза 2 |
| Метрики/логи | все → DevOps | Фаза 6 |

---

## 5. Структура задач в файлах команд

Каждый файл `teams/XX_*.md` имеет одинаковую структуру:

```
1. Зона ответственности
2. Стек и зависимости
3. Backlog (Epic → Story → Tasks)
4. Точки интеграции (что отдают / что берут от других)
5. Definition of Done для каждой Epic
6. Риски и слабые места команды
```

---

## 6. Типичный workflow задачи

1. Берёшь задачу из своего файла → обновляешь её статус (или Issue в трекере).
2. Если нужны данные/код от другой команды и его нет — открываешь Issue в их файле/трекере, **не блокируешь себя**: пишешь mock и идёшь дальше.
3. Реализуешь, **пишешь тесты**, открываешь PR.
4. PR должен ссылаться на эпик в `teams/XX_*.md` или на Issue.
5. Если изменился публичный контракт — в том же PR обновляешь соответствующий `docs/*.md`.
6. После мерджа — двигаешь чек-бокс в своём файле.

---

## 7. Что не делает Tech Lead

- Не пишет код за разработчиков.
- Не правит чужой PR без согласования.
- Делает: ревью архитектурных PR, разрешение конфликтов между модулями, контракты в `docs/`.
