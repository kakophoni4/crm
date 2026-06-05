# CRM Chat Center — Frontend

Vue 3 SPA (Epic 1): каркас с layout, темой, HTTP/WS-клиентами.

## Требования

- Node.js 20+
- npm 10+

## Быстрый старт

```bash
cd frontend
cp .env.example .env   # Windows: copy .env.example .env
npm install
npm run dev
```

Приложение: http://localhost:5173 (dashboard — «Hello, CRM Chat Center»).

## Скрипты

| Команда | Описание |
|---------|----------|
| `npm run dev` | Dev-сервер Vite |
| `npm run build` | Production-сборка |
| `npm run preview` | Превью сборки |
| `npm run typecheck` | Проверка TypeScript |
| `npm run lint` / `lint:fix` | ESLint |
| `npm run test` | Vitest (unit) |
| `npm run gen:api` | Генерация типов из OpenAPI (когда backend поднят) |

## Структура (FSD light)

```
src/
  app/          # router, theme, providers, App.vue
  pages/        # route-level views
  widgets/      # AppLayout (sidebar + topbar)
  features/     # (пусто)
  entities/     # (пусто)
  shared/       # api, config, lib, ui, store
```

## Переменные окружения

См. `.env.example`: `VITE_API_BASE_URL`, `VITE_WS_URL`, `VITE_SENTRY_DSN`.
