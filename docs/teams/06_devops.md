# DevOps

> Инфраструктура, сборка, деплой, наблюдаемость, бэкапы, безопасность периметра.

---

## 1. Зона ответственности

- Локальная среда разработки (`docker-compose.dev.yaml`) — postgres, redis, minio, adminer, mailhog.
- Публичный туннель/домен для приёма `/api/v1/bot-events` от ботов на dev (cloudflared/ngrok) и постоянный домен на staging/prod.
- Production-среда: Docker Compose на одной VPS на старте, опционально k3s/k8s позже.
- Reverse-proxy: Traefik (TLS via Let's Encrypt, маршрутизация к `app`, `frontend`, `minio`).
- CI/CD: GitHub Actions (или GitLab) — lint, тесты, build, deploy на staging/prod.
- Логи: Loki + Promtail + Grafana.
- Метрики: Prometheus + Grafana.
- Ошибки: Sentry (self-hosted или cloud).
- Бэкапы: Postgres (`pg_dump` + `restic`/`pgBackRest`), MinIO (`mc mirror`).
- Управление секретами: env + ансибл/dotenvx; перспективно — Vault/Doppler.

---

## 2. Стек

```
docker, docker-compose
traefik v3
prometheus + grafana + loki + promtail
sentry (self-hosted) или cloud
github actions
restic / pgbackrest
mc (minio client)
```

---

## 3. Backlog

### Epic 1. Dev-окружение
- [ ] `docker/docker-compose.dev.yaml`:
  - postgres:16 (с тюнингом для dev)
  - redis:7
  - minio + создание дефолтного бакета через `mc`
  - adminer (web UI для БД)
  - mailhog (для писем при reset password)
- [ ] `.env.example` со всеми переменными.
- [ ] README инструкция «как запустить за 5 минут».
- [ ] Скрипт `scripts/dev.ps1` / `dev.sh` — старт стека + миграции + сид первого админа.
- [ ] **DoD:** новый разработчик за ≤30 минут от клона до залогиненного админа.

### Epic 2. Публичный URL для ботов (Bot ingest)
- [ ] `cloudflared tunnel` (или ngrok) — обёртка-команда `make tunnel`.
- [ ] Документация: «как настроить `outbound_url` бота на наш публичный URL CRM, как mock-боту слать `/api/v1/bot-events`».
- [ ] Постоянный sub-домен на staging для авторов ботов, чтобы не пересоздавать конфиги.
- [ ] **DoD:** mock-бот реально доходит до локального FastAPI через `POST /api/v1/bot-events`.

### Epic 3. CI
- [ ] GitHub Actions: workflow `pr-checks` — lint, type-check, тесты бэк/фронт.
- [ ] Кэширование зависимостей (pip, npm).
- [ ] Бэйдж в README.
- [ ] **DoD:** PR блокируется при падении тестов.

### Epic 4. Build и образы
- [ ] `docker/Dockerfile` для backend (multi-stage: builder → runtime, slim, non-root user).
- [ ] `docker/Dockerfile.frontend` (build → nginx-alpine, статика).
- [ ] GHCR (или DockerHub): пуш образов на merge в main с тегами `:sha`, `:latest`, `:vX.Y.Z`.
- [ ] **DoD:** образы выходят за ≤5 мин.

### Epic 5. Production-стек (single-node)
- [ ] `docker/docker-compose.yaml` — `traefik`, `app`, `worker`, `frontend`, `postgres`, `redis`, `minio`, `loki`, `grafana`, `prometheus`.
- [ ] Traefik labels на сервисах + автоматический LE.
- [ ] Volume'ы и bind-mount'ы для данных.
- [ ] Restart policies (`always`).
- [ ] Health-checks для всех контейнеров.
- [ ] **DoD:** прод-стенд поднимается одной командой, TLS работает, домены маршрутизируются.

### Epic 6. CD
- [ ] GitHub Action `deploy-staging` — после merge в main → ssh на staging VPS → `docker compose pull && docker compose up -d`.
- [ ] Smoke-test после деплоя (curl `/healthz`, проверка фронта).
- [ ] Manual approval для прода.
- [ ] **DoD:** мердж в main даёт работающий staging через ≤10 минут.

### Epic 7. Логи
- [ ] Promtail на хосте читает контейнерные логи и шлёт в Loki.
- [ ] Loki retention 14 дней (env).
- [ ] Grafana дашборды:
  - HTTP-логи (status, latency, top routes);
  - Errors (level=error, по сервису);
  - Request flow по `request_id`.
- [ ] **DoD:** ищется по request_id за 1 секунду.

### Epic 8. Метрики
- [ ] Prometheus scrape:
  - FastAPI `/metrics` (через `prometheus-fastapi-instrumentator`);
  - ARQ метрики (queue depth);
  - Postgres exporter;
  - Redis exporter;
  - Node exporter (CPU/RAM/DISK).
- [ ] Дашборды:
  - System overview;
  - HTTP/WS;
  - Bots (ingest rate, outbound rate, latency, failures, signature_invalid, alive per bot);
  - Queue depth;
  - WS connections.
- [ ] Алёрты (Alertmanager → email/Telegram):
  - `api_5xx > 1%` за 5 минут;
  - `events_outbox_unprocessed > 100`;
  - `tg_send_failures > 5/мин`;
  - `disk_free < 10%`;
  - `db_connections > 80%`.
- [ ] **DoD:** алёрты срабатывают на тестовых сценариях.

### Epic 9. Sentry
- [ ] Self-hosted Sentry или Sentry SaaS (по бюджету).
- [ ] DSN backend и frontend в env.
- [ ] Release tracking (commit SHA в Sentry).
- [ ] PII filter в init (вырезаем `telegram_user_id`, `inbound_secret`, `outbound_secret`, `password`).
- [ ] **DoD:** ошибки бэка и фронта прилетают, sourcemaps работают.

### Epic 10. Бэкапы
- [ ] Postgres: `pg_dump` ежедневно в 03:00, `restic` в S3 (или другой MinIO bucket с другим хостом).
- [ ] MinIO: `mc mirror` ежедневно.
- [ ] Retention 14 дней + 4 еженедельных.
- [ ] **Тест восстановления** раз в месяц (документировать процедуру).
- [ ] **DoD:** проведено успешное восстановление на staging.

### Epic 11. Безопасность периметра
- [ ] UFW/iptables: открыты только 80/443 (и 22 для admin).
- [ ] fail2ban на ssh.
- [ ] Traefik → strict TLS, HSTS, security headers.
- [ ] Никаких портов postgres/redis/minio наружу.
- [ ] `/api/v1/bot-events` — единственная внешняя точка приёма событий, защищена HMAC + опциональным IP allowlist.
- [ ] Rate-limit на `/auth/login` и `/api/v1/bot-events` через Traefik middleware.
- [ ] **DoD:** `nmap` снаружи показывает только 80/443.

### Epic 12. Документация
- [ ] `docs/runbook/`:
  - что делать при падении приложения;
  - как ротировать секреты;
  - как добавить новый домен;
  - как восстановить БД из бэкапа;
  - как разобраться в логах через Grafana.

---

## 4. Точки интеграции

### Что DevOps отдаёт
- Готовая инфраструктура для разработки и прод.
- DSN Sentry, URL Grafana, runbook'и.
- Публичный URL для вебхуков (env `PUBLIC_BASE_URL`).

### Что DevOps берёт
- Образы из CI (от Backend и Frontend).
- Списки метрик и логов от каждой команды.

---

## 5. Definition of Done

- ✅ Прод-стенд поднимается с нуля одной командой.
- ✅ Логи и метрики заведены, дашборды показывают реальные данные.
- ✅ Восстановление из бэкапа протестировано.
- ✅ Алёрты приходят в выбранный канал.
- ✅ Обзор безопасности периметра — пройден.

---

## 6. Слабые места

1. **Single-node Docker Compose** — единственная точка отказа. Митигация на старте: бэкапы. После роста — переезд на k3s или managed-DB.
2. **MinIO без репликации single-node** — потеря диска = потеря файлов. Бэкап на другой хост обязателен.
3. **Self-hosted Sentry** жрёт ресурсы (Clickhouse, Kafka). На старте может быть проще SaaS.
4. **Cloudflared/ngrok туннели** — каждый разработчик получает свой URL. Зарегистрировать постоянный sub-домен в DNS, чтобы не пересоздавать вебхук бота при каждом перезапуске.
5. **Алёрты на email легко игнорируются.** Подключить Telegram-канал команды как минимум.
6. **Бэкапы без тестирования восстановления = нет бэкапов.** Месячный drill — обязательная процедура, а не опционал.
