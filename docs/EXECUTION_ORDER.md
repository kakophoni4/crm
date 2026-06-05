# Порядок выполнения задач

> Этот документ — практический «как двигаться». Источник технических деталей — `ROADMAP.md` (фазы) и `teams/*.md` (backlog'и). Здесь — **критический путь**, **зависимости** и **что можно делать параллельно**.

---

## 1. Принципы

1. **Сначала фундамент.** Без `auth + RBAC + оргструктура` нельзя писать ничего, что должно проверять права.
2. **Контракты раньше реализации.** Перед тем как два модуля начинают параллельную работу, согласован публичный контракт (REST/WS/событие/таблица).
3. **Параллелизм через моки.** Если зависишь от команды, у которой ещё не готов API — делаешь mock и идёшь дальше. Mock-сервер на FastAPI/MSW.
4. **Тесты в каждой фазе.** RBAC-тесты — обязательно с Фазы 1, не позже.
5. **Демо после каждой недели.** Любая неделя должна заканчиваться демонстрируемым результатом, даже если урезанным.

---

## 2. Граф зависимостей (что без чего нельзя)

```
DevOps:dev-compose
       │
       ▼
Backend Core: скелет, db, settings, logging
       │
       ├──────────────────────────────────────────┐
       ▼                                          ▼
Backend Core: auth (login/refresh)        Frontend: скелет, layout, axios
       │                                          │
       ├──────────────────────────────────────────┘
       ▼
Backend Core: RBAC + scope + оргструктура (users/dept/groups)
       │
       ├──────────────────────────────────────────┐
       ▼                                          ▼
Backend Core: EventBus + outbox + audit    Frontend: login + admin org
       │
       ├────────────────────────────┐
       ▼                            ▼
Backend Contacts: contacts/    Backend Chats: миграции chats/messages
files/statuses                      │
       │                            ├─ ингест API ◀─── Bots Integration: контракт
       │                            │
       │                            ▼
       └──────────▶ Backend Chats: list/get/messages
                            │
                            ▼
                   Backend Chats: outbound (POST messages)
                            │
                            ├──── Bots Integration: outbound dispatcher
                            │
                            ▼
                   Backend Chats: WebSocket Hub
                            │
                            ▼
              *** Фаза 3.5: Contact Ownership (см. CONTACT_OWNERSHIP.md) ***
              contact_group_assignments, escalation worker, reply audit
              refactor scope (group-visible chats), contact transfers
                            │
                            ├─────────── Frontend: ownership UI + escalation settings
                            │
                            ▼
                   Backend Chats: takeover (опционально после ownership)
                            │
                            ├─────────── Frontend: transfers + takeover UI
                            │
                            ▼
                   Search + UX polish
                            │
                            ▼
                   Observability + Harden
                            │
                            ▼
                   Stage → UAT → Release
```

---

## 3. План по неделям (для команды 4 чел: 2 BE + 1 FE + 1 DevOps/QA)

> Если команда меньше — задачи не исчезают, удлиняется длительность недели. Если команда больше — режем неделю по треку. **Не перескакивать через фундамент** даже при большой команде.

### Неделя 1 — Подготовка
| Трек | Задачи | Демо |
|---|---|---|
| DevOps | Репозиторий, ветки, правила PR, CI на lint+test, `docker-compose.dev.yaml` (postgres+redis+minio), `.env.example` | `docker compose up`, healthchecks зелёные |
| BE Core | Скелет FastAPI: `create_app`, settings, db, structlog, alembic init, `/healthz`, OpenAPI с Bearer | `GET /healthz` → 200 |
| FE | `npm create vite`, eslint/prettier, naive-ui, layout (sidebar+top-bar), router | пустые страницы, тёмная тема |
| QA | Шаблон pytest, testcontainers fixture | `pytest -q` зелёный |

### Неделя 2 — Auth + начало оргструктуры
| Трек | Задачи | Демо |
|---|---|---|
| BE Core | Миграция users/departments/groups, login/refresh/logout, `/auth/me`, force-logout, ws-ticket | curl логинится |
| BE Core (2-й) | Реестр permissions, маппинг ролей, scope-функции (users/groups/dept) | unit-тесты scope |
| FE | Pinia auth store, axios interceptor, страница Login, гард `requireAuth` | логин-логаут работает |
| DevOps | Скрипт сидов (создать первого admin), CI matrix py3.12 | `seed.py` создаёт admin |

### Неделя 3 — Оргструктура + EventBus
| Трек | Задачи | Демо |
|---|---|---|
| BE Core | CRUD users/departments/groups с применением scope, бизнес-правила (senior↔dept, user↔group) | админ создаёт отдел/группу/юзера через API |
| BE Core (2-й) | Outbox-таблица, EventBus, redis-bridge, audit handler (wildcard) | каждое CRUD пишет в audit_log |
| FE | Страницы Admin: Departments, Groups, Users; форма «создать» с валидацией | админ создаёт оргструктуру через UI |
| QA | RBAC-матрица как параметризованный тест по эндпоинтам auth/users/dept/groups | падает при нарушении правил |

> **Точка синхронизации:** конец недели 3 — оргструктура работает end-to-end через UI. Это **первый видимый продукт**.

### Неделя 4 — Контакты + статусы + файлы
| Трек | Задачи | Демо |
|---|---|---|
| BE Contacts | Миграции contacts/contact_field_changes/statuses/files; CRUD; маскирование `telegram_user_id`; diff JSONB; история | `/api/v1/contacts` работает с маскированием |
| BE Contacts (2-й) | `files` upload в MinIO, presigned URL, `files_service.upload_from_url` | загрузка/скачивание файла |
| FE | Страница Contacts (список + поиск), ContactCard (inline-редактирование, история по полям), Statuses CRUD | оператор редактирует контакт, видит историю |
| QA | E2E: создать админа → создать senior'а → создать юзера → юзер редактирует контакт | сценарий проходит |

### Неделя 5 — Чаты: модель и просмотр + контракт интеграции с ботами
| Трек | Задачи | Демо |
|---|---|---|
| BE Chats | Миграции chats/messages, репозиторий + scope, `GET /chats`, `GET /chats/{id}`, `GET /chats/{id}/messages`, FTS-индекс | оператор видит фейковые чаты в API |
| BE Bots Integration | **Контракт `BOTS_INTEGRATION.md`** + endpoints `POST /api/v1/bot-events/*`, валидация HMAC, идемпотентность | бот шлёт событие через curl, сообщение появляется в БД |
| FE | Skeleton chat-center: список чатов, открытый чат с историей, без отправки | UI показывает фейковые чаты |
| QA | Mock-бот (FastAPI), скрипты эмуляции входящих | mock шлёт события, появляются в UI |

> **Точка синхронизации:** конец недели 5 — есть контракт интеграции с ботами и идёт ингест.

### Неделя 6 — Чаты: отправка + realtime + assignment
| Трек | Задачи | Демо |
|---|---|---|
| BE Chats | `POST /chats/{id}/messages` (queued), assignment service, WebSocket Hub, Pub/Sub bridge, события message.* | оператор отправляет, через секунду бэкграунд-job шлёт в бота |
| BE Bots Integration | Outbound dispatcher: ARQ job, HTTP к боту с HMAC, retry policy, статусы доставки | mock-бот получает запрос, мы видим status='sent' |
| FE | Composer (textarea, attachments, Ctrl+Enter), индикаторы статуса, realtime через WS | end-to-end общение через mock-бота |
| QA | Нагрузочный k6: 100 операторов одновременно | SLO p95 ≤ 200мс держится |

### Неделя 7 — Передача и перехват
| Трек | Задачи | Демо |
|---|---|---|
| BE Chats | Миграция chat_transfers, state-machine API (create/approve/decline/accept/reject/cancel/expire), `version` для гонок | сценарий «user A → senior → user B» проходит |
| BE Chats (2-й) | Takeover: API on/off, валидация при отправке, события, audit | senior захватывает чат, отпускает |
| FE | Transfers UI (входящие на апрув / на акцепт), модал «передать», нотификации со звуком | UX передачи работает целиком |
| FE (2-й) | Takeover UI (баннер, заблокированный composer) | senior может перехватывать |
| QA | E2E на оба сценария + state-machine тесты с asyncio.gather (гонки) | тесты зелёные |

### Неделя 8 — Поиск + UX-полировка
| Трек | Задачи | Демо |
|---|---|---|
| BE Chats | FTS-поиск, фильтры списка чатов (status, bot, unread), сортировки | поиск работает |
| FE | Hotkeys (Ctrl+K, /), drag-n-drop файлов, аватарки контактов, skeleton loading, browser-нотификации | UX комфортный |
| FE (2-й) | Адаптив до 768px, доступность (a11y) | работает на ноутбуке/планшете |
| QA | Visual smoke на основных страницах, accessibility audit | a11y issues = 0 critical |

### Неделя 9 — Наблюдаемость + хардненинг
| Трек | Задачи | Демо |
|---|---|---|
| DevOps | Prometheus + Grafana дашборды, Loki + Promtail, Sentry init, алёрты | дашборды живые |
| BE | Метрики на горячие пути, маскирование PII в логах, sentry-фильтры | проверено вручную |
| QA | Security pass: IDOR, JWT manipulation, XSS, SSRF, brute-force | чек-лист пройден |
| QA (2-й) | Chaos-light: stop-redis 30s, stop-postgres 10s | данные не теряются |

### Неделя 10 — Stage + UAT
| Трек | Задачи | Демо |
|---|---|---|
| DevOps | Прод-стенд (Traefik+TLS), деплой staging, бэкапы Postgres+MinIO, тест восстановления | staging работает, бэкап восстанавливается |
| QA | Полный регресс на staging, UAT с заказчиком | go-list для прода |
| BE/FE | Багфиксы по UAT | bug count → 0 critical |

### Неделя 11 — Релиз
| Трек | Задачи |
|---|---|
| DevOps | Деплой в прод, мониторинг 48 часов |
| QA | Smoke на проде |
| BE/FE | Hotfix-готовность |
| Tech Lead | Документация для пользователей, обучение операторов |

---

## 4. Что можно параллелить с самого начала

| Параллельные потоки | Условие |
|---|---|
| FE auth и BE auth | согласован формат `/auth/login` ответа (3 поля: access, refresh, user) |
| FE admin org и BE org CRUD | согласованы DTO users/dept/groups |
| Bots Integration (контракт) и Backend Chats (модель) | разные люди, контракт согласован на бумаге раньше |
| QA E2E и FE | E2E пишутся параллельно фичам, гоняются после релиза фичи |
| DevOps observability и BE | DevOps готовит инфру, BE добавляет инструментирование по мере появления endpoint'ов |

---

## 5. Что **нельзя** делать параллельно

| Конфликт | Почему |
|---|---|
| BE Chats до того как готов RBAC scope | вся логика «кто что видит» завязана на scope-функции |
| Bots Integration outbound до того как готов `chats_service.send` | outbound-job дёргает chats_service |
| FE chat-center до того как готов `/chats` API и WS-протокол | mock'и не покрывают realtime — будет много переделок |
| Transfer до того как стабилизирован Chats core | гонки в transfer-механике мешают тестировать |

---

## 6. Минимально-полезный продукт по чекпоинтам

| Конец недели | Что демонстрируется |
|---|---|
| 1 | Запускается, healthchecks |
| 2 | Логин работает |
| 3 | Админ создаёт оргструктуру через UI |
| 4 | Контакты + история редактирования |
| 5 | Контракт ботов готов, ингест в БД |
| 6 | **End-to-end общение** через mock-бота |
| 7 | Передача и перехват чатов |
| 8 | Поиск + полировка UX |
| 9 | Дашборды + security pass |
| 10 | Staging + UAT |
| 11 | Прод |

---

## 7. Последовательность для одиночного разработчика

Если работаешь один — параллелить не получится, чисти от треков и иди по строкам:

1. DevOps скелет (1–2 дня).
2. BE Core: auth (3–4 дня).
3. BE Core: RBAC + оргструктура CRUD (1 неделя).
4. **FE: login + admin org** (на этом этапе впервые «видно продукт») (1 неделя).
5. BE Core: EventBus + outbox + audit (3 дня).
6. BE Contacts (1 неделя).
7. FE Contacts (3 дня).
8. **Контракт BOTS_INTEGRATION** (2 дня — на бумаге раньше реализации).
9. BE Chats: модель + список (1 неделя).
10. BE Bots Integration: ингест (3 дня).
11. BE Chats: отправка + WS Hub (1 неделя).
12. BE Bots Integration: outbound (3 дня).
13. FE chat-center (1.5 недели).
14. BE Chats: transfers + takeover (1 неделя).
15. FE transfers + takeover UI (3 дня).
16. Поиск + полировка (3 дня).
17. Observability + бэкапы (3 дня).
18. Релиз.

**Итого ≈ 14–16 недель в одиночку.** Если параллелить хотя бы FE и BE через mock'и — режется до 11–12.

---

## 8. Слабые места порядка

1. **Откладывание UI оргструктуры на «потом»** — самая частая ошибка. Фронт обязан появиться к концу недели 3, иначе бэк уходит в отрыв и пилит избыточно.
2. **Контракт ботов «согласуем когда дойдём»** — сорвёт неделю 5. Контракт обсуждается с авторами ботов в неделю 1, документ финализируется в неделю 4, реализация — неделя 5–6.
3. **Транзитивные зависимости от outbox-воркера** — без него аудит и WS встают. Запустить раньше, чем подключатся первые подписчики, минимум за 2 дня.
4. **Параллельный chat-center и outbound dispatcher** — фронт не сможет нормально тестировать, если outbound молчит. Mock-бот обязателен.
5. **Транзитная зона недели 6** — самая нагруженная (отправка + WS + assignment + dispatcher). Разнести на 6А и 6Б, если команда меньше 4 человек.
