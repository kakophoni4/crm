# Load testing (CRM Chat Center)

Нагрузочные сценарии **не входят** в CI по умолчанию (тяжёлые, требуют staging и данных).

## Цель (фаза 6)

| Метрика | Ориентир |
|---------|----------|
| Сообщения | **~10 000 исходящих / час** на кластер (операторы + боты) |
| API p95 | ≤ 200 ms (см. `docs/teams/07_qa.md`, Epic 5) |
| Ошибки | error rate &lt; 0.1 % |

Скрипт `k6_smoke.js` — **smoke**, не полный soak: 20 VU, login → list chats → send message.

## Требования

- [k6](https://k6.io/docs/get-started/installation/) 0.49+
- Развёрнутый API (staging или local `uvicorn`)
- Пользователь с правом `CHATS_WRITE` и хотя бы один чат в скоупе

## Прогон против staging

```bash
export BASE_URL="https://staging.example.com"
export LOAD_EMAIL="load.operator@your-org.local"
export LOAD_PASSWORD="***"
# опционально: фиксированный чат
export LOAD_CHAT_ID="123"

k6 run scripts/load/k6_smoke.js
```

PowerShell:

```powershell
$env:BASE_URL = "https://staging.example.com"
$env:LOAD_EMAIL = "load.operator@your-org.local"
$env:LOAD_PASSWORD = "***"
k6 run scripts/load/k6_smoke.js
```

### Параметры

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `BASE_URL` | `http://localhost:8000` | Корень API (без `/api/v1`) |
| `LOAD_EMAIL` / `LOAD_PASSWORD` | dev operator из seed | Учётка оператора |
| `LOAD_CHAT_ID` | (авто из list) | ID чата для `POST …/messages` |
| `K6_VUS` | `20` | Виртуальные пользователи |
| `K6_DURATION` | `5m` | Длительность сценария |
| `K6_SLEEP` | `3` | Пауза между итерациями VU (сек) |

### Оценка 10k msg/h

При 20 VU и `K6_SLEEP=3` ожидайте порядка **~400 msg/min** (~24k/h) если каждый цикл успешен — на staging сначала снизьте VU или увеличьте sleep, затем наращивайте до целевого RPS. Смотрите `crm_messages_sent` и Grafana (`docs/OBSERVABILITY.md`).

## Локальный smoke

```bash
docker compose -f docker/docker-compose.dev.yaml up -d postgres redis
alembic upgrade head
# API + seed (operator.chats.a@crm.local / TestPass!234567)
uvicorn app.main:app --port 8000

k6 run scripts/load/k6_smoke.js
```

## CI

Не подключать к `.github/workflows/ci.yml` без отдельного workflow `workflow_dispatch` и выделенного staging.
