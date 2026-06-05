# Security checklist (ручной pen-test)

> Дополняет автотесты `tests/rbac/` и матрицу `docs/RBAC_MATRIX.md`.  
> Прогонять перед релизом на **staging** с тестовыми учётками admin / senior / user.

---

## 1. Аутентификация и сессии

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-1 | Login с неверным паролем | 401, без утечки «user exists» | |
| S-2 | Brute-force login (10+ попыток / IP) | 429 rate limit | |
| S-3 | Refresh с отозванным / поддельным refresh token | 401 | |
| S-4 | Доступ к API с истёкшим access token | 401 | |
| S-5 | WS ticket одноразовый / с коротким TTL | Повторное подключение с тем же ticket — отказ | |
| S-6 | Force-logout: после события старый access не работает | 401 на защищённых маршрутах | |

## 2. RBAC и scope (IDOR)

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-7 | User `GET /chats/{id}` чужой группы | **404** (не 403 с телом чата) | |
| S-8 | User `GET /contacts/{id}` другого отдела | **404** | |
| S-9 | User `POST /chats/{id}/messages` вне скоупа | **404** | |
| S-10 | `GET /search?q=…` — нет результатов из чужого отдела/группы | Пустые `items` | |
| S-11 | Operator `POST /api/v1/bots` | **403** | |
| S-12 | Senior не создаёт admin / не меняет чужой отдел | **403** / **404** | |
| S-13 | Список `GET /chats` не содержит чаты вне GROUP/DEPARTMENT скоупа | Только разрешённые id | |
| S-14 | `GET /contacts/{id}/audit` на чужой контакт | **404** | |
| S-15 | Contact transfer: нельзя approve чужого отдела | **404** / **403** | |

Автопокрытие smoke: `pytest tests/rbac/test_endpoint_matrix.py -q`.

### Leads (IDOR, CRM summary, status kind)

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-LEAD-1 | User `GET /leads/{id}` лида чужой группы | **404** (не 403 с телом) | |
| S-LEAD-2 | User `POST /contacts/{id}/leads` с `group_id` вне своей группы | **403** или **404** | |
| S-LEAD-3 | `GET /contacts/{id}/leads` не возвращает лиды с `group_id` чужой группы | Только свой `group_id` в items | |
| S-LEAD-4 | `crm_summary.prior_leads_count` на чужом/невидимом контакте | **404** на контакт; нет утечки счётчика | |
| S-LEAD-5 | `PATCH /leads/{id}` со `status_id` kind=`chat_label` (не pipeline) | **422** / отказ валидации | |
| S-LEAD-6 | `GET /contacts/{id}/leads` >60/min или `POST /contacts/{id}/leads` >30/min per user | **429** `rate_limited` | |
| S-LEAD-7 | `GET /crm-summary` не раскрывает чужие лиды (titles, contact PII) | Только счётчики в scope | |

## 3. PII и маскирование

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-16 | `telegram_user_id` в API для user/senior | Отсутствует или замаскирован | |
| S-17 | Admin видит полный `telegram_user_id` | Только с ролью admin | |
| S-18 | Логи / Sentry: нет паролей, токенов, полного telegram id | Маскирование в structlog/Sentry before-send | |
| S-19 | Presigned URL файлов — TTL и scope | Чужой user не скачивает файл | |

## 4. Bot ingest (HMAC)

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-20 | `POST /bot-events` без подписи | **401** | |
| S-21 | Повтор `X-Event-Id` (replay) | Идемпотентность, без дубля сообщения | |
| S-22 | Неверный `X-Timestamp` (> skew) | **401** | |
| S-23 | Событие на неактивный bot | Отказ / игнор по контракту | |

## 5. Инфраструктура и заголовки

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-24 | `/metrics` на prod при `METRICS_ENABLED=false` | **404** | |
| S-25 | CORS: только разрешённые origins | Нет `*` с credentials на prod | |
| S-26 | Adminer / MailHog / MinIO console не торчат в prod | Закрыто VPN / не опубликовано | |
| S-27 | TLS на staging/prod (Traefik) | Валидный сертификат, HSTS | |

## 6. Нагрузка и отказоустойчивость (выборочно)

| # | Проверка | Ожидание | ✓ |
|---|----------|----------|---|
| S-28 | k6 smoke 20 VU (`scripts/load/k6_smoke.js`) | error rate &lt; 5 %, login OK | |
| S-29 | Backup Postgres dry-run restore | Документированный restore ≤ RPO | |
| S-30 | Redis down 30 с | API degraded, без порчи данных | |

## 7. Регресс после изменений RBAC

1. Обновить `docs/RBAC_MATRIX.md` при новых эндпоинтах.
2. `pytest tests/rbac -q` — зелёный.
3. `pytest -q` — полный пакет.

---

**Версия:** фаза 6 (2026-05-17).  
**Не в scope:** внешний pen-test от сторонней фирмы, Playwright E2E.
