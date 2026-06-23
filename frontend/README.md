# CRM Chat Center — Frontend

Vue 3 SPA для операторов, senior/admin ролей, чатов, контактов, лидов, настроек, ботов и телефонии.

## Требования

- Node.js 20+
- npm 10+
- Запущенный backend API на `http://localhost:8000`

## Быстрый Старт

```bash
cd frontend
cp -n .env.example .env
npm ci
npm run dev
```

Windows:

```powershell
cd frontend
copy .env.example .env
npm ci
npm run dev
```

Приложение: http://localhost:5173

## Env

Основные переменные в `.env.example`:

| Переменная | Назначение |
|---|---|
| `VITE_API_BASE_URL` | REST API base URL, обычно `http://localhost:8000/api/v1` |
| `VITE_WS_URL` | WebSocket endpoint, обычно `ws://localhost:8000/api/v1/ws` |
| `VITE_SENTRY_DSN` | Sentry DSN, опционально |
| `VITE_SENTRY_ENVIRONMENT` | Sentry environment |
| `VITE_LOG_DEBUG` | Debug logging in browser |
| `VITE_MAX_UPLOAD_PHOTO_BYTES` | UI limit for photo uploads |
| `VITE_MAX_UPLOAD_FILE_BYTES` | UI limit for file uploads |

## Скрипты

| Команда | Описание |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run build` | Typecheck + production build |
| `npm run preview` | Preview built bundle |
| `npm run typecheck` | `vue-tsc --noEmit` |
| `npm run lint` / `npm run lint:fix` | ESLint |
| `npm run test` | Vitest unit tests |
| `npm run gen:api` | Generate OpenAPI types from running backend |

## Структура

```text
src/
  app/        router, providers, theme, App.vue
  pages/      route-level views
  widgets/    layout and feature widgets
  features/   API clients and feature logic
  entities/   typed domain entities
  shared/     api, config, realtime, store, lib, ui
tests/
  unit/       Vitest unit tests
```

## Проверки

```bash
npm run lint
npm run typecheck
npm run test
```

Полная сборка:

```bash
npm run build
```
