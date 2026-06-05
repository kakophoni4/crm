# Frontend

> Vue 3 SPA. Главный экран — чат-центр. Должен быть быстрым, удобным и красивым.

---

## 1. Зона ответственности

- Vue 3 проект (`/frontend`), TypeScript, Vite.
- Аутентификация (login, refresh, logout, ws-ticket).
- Глобальный store (Pinia) + permissions guard роутера.
- Страницы:
  - Login;
  - Chat-center (главная для оператора);
  - Contacts (список + карточка);
  - Admin (departments, groups, users, bots, statuses);
  - Profile.
- WebSocket клиент (auto-reconnect, sync state).
- UX-фишки: hotkeys, drag-n-drop, аватарки, тёмная тема, нотификации.
- Локализация (русский).

---

## 2. Стек

```
vue ^3.4
typescript ^5.4
vite ^5.3
pinia ^2.1
vue-router ^4.4
naive-ui ^2.38         # UI-кит (или PrimeVue по выбору)
axios ^1.7             # HTTP
@vueuse/core ^10.11    # утилиты
date-fns ^3.6
lucide-vue-next        # иконки
@formkit/auto-animate  # плавность
virtua ^0.30           # виртуализация списков сообщений
```

Тесты:
```
vitest, @vue/test-utils, @testing-library/vue, playwright
```

---

## 3. Backlog

### Epic 1. Скелет проекта
- [ ] `/frontend` структура: `src/{app, pages, features, entities, shared, widgets}` (методология FSD light).
- [ ] Конфиг Vite + alias.
- [ ] ESLint + Prettier + Stylelint.
- [ ] Базовый layout (sidebar, top-bar, content).
- [ ] Тёмная тема (через CSS variables + `useColorMode`).
- [ ] **DoD:** `npm run dev` поднимает «hello world» с layout'ом.

### Epic 2. Auth
- [ ] Pinia store `auth`: `user`, `permissions`, `accessToken`, `refreshToken`.
- [ ] Хранение refresh в `httpOnly`-cookie (если бэкенд это поддерживает) или sessionStorage. Access — в memory.
- [ ] Axios interceptor: подставляет Bearer, на 401 пробует refresh.
- [ ] Гард роутера: `requireAuth`, `requirePermission(P)`.
- [ ] Страница Login.
- [ ] Logout.
- [ ] **DoD:** перезагрузка страницы — пользователь остаётся залогинен (через refresh).

### Epic 3. WebSocket клиент
- [ ] `shared/ws.ts`: connect → берёт ticket из `/auth/ws-ticket`, открывает WS, реконнект с экспоненциальным backoff.
- [ ] Pinia store `realtime` с маппингом event-type → handlers.
- [ ] Heartbeat ping каждые 20 сек.
- [ ] При close 1001/1006 — переподключение с новым ticket.
- [ ] **DoD:** во вкладке стабильно держится коннект, переживает короткую потерю сети.

### Epic 4. Чат-центр (главный экран)
Layout:
```
+--------+--------------------------+--------------------------+
| Side   | Список чатов             | Открытый чат             |
| bar    |  фильтры (status, bot)   |  сообщения (виртуал)     |
|        |  поиск                   |  composer (textarea +    |
|        |  карточка чата (preview) |   attachments + send)    |
|        |                          |  side-panel: Карточка    |
|        |                          |  контакта                |
+--------+--------------------------+--------------------------+
```

- [ ] `pages/chat-center` со store `chats`.
- [ ] Список чатов: вирт-список (сортировка по `last_message_at`), бейдж непрочитанных, маркер takeover/transfer-pending.
- [ ] Открытие чата: догрузка истории (cursor pagination) при скролле наверх.
- [ ] Composer: textarea с autoresize, Ctrl+Enter — отправка, drag-n-drop файлов, paste картинок.
- [ ] Отображение статуса доставки (✓ queued, ✓ sent, ✓✓ delivered, ✓✓ read, ⚠ failed с reason).
- [ ] Realtime: на event `message.created` пушим в текущий список / увеличиваем бейдж.
- [ ] Side-panel «Контакт» — embedded ContactCard.
- [ ] **DoD:** оператор полноценно ведёт чат через mock-бота, а затем через реальный бот в Telegram.

### Epic 5. Карточка контакта
- [ ] `features/contact-card`.
- [ ] Поля: display_name, phone, email, telegram_username, custom fields.
- [ ] Inline-редактирование с PATCH на blur/Ctrl+Enter.
- [ ] Около каждого поля — подсказка с историей: «изменено пользователем Иван 13.05 в 14:32».
- [ ] Раздел «Чаты этого контакта» (сколько, по каким ботам).
- [ ] Если пользователь — admin, видно поле `telegram_user_id` (плашка «приватное»).
- [ ] **DoD:** редактирование — мгновенное, история открывается по клику на иконку.

### Epic 6. Передача чата (transfer UI)
- [ ] Кнопка «Передать» в открытом чате → модал «кому» (autocomplete по видимым юзерам).
- [ ] Если актор — user → текст «Запрос уйдёт старшему на согласование».
- [ ] Если senior → «Согласие будет получено у получателя».
- [ ] Pinia store `transfers`:
  - `outgoing` (мои инициированные);
  - `pending_my_approve` (для senior);
  - `pending_my_acceptance` (для recipient).
- [ ] Виджет уведомлений в верхней панели (бейдж + dropdown).
- [ ] Принять / Отклонить inline.
- [ ] Звук на новые предложения (отключаемо).
- [ ] **DoD:** end-to-end сценарий передачи проходит через UI.

### Epic 7. Takeover UI
- [ ] У senior'а в чужом чате — кнопка «Подключиться».
- [ ] Активный takeover: верхний баннер «Сейчас в чате руководитель: <имя>», composer заблокирован у текущего юзера.
- [ ] Отключение — кнопка «Отключиться» + ESC-shortcut.
- [ ] **DoD:** UX takeover'а не путает оператора и Senior'а.

### Epic 8. Admin-панель
- [ ] `pages/admin`: вкладки Departments, Groups, Users, Bots, Statuses.
- [ ] Таблица + модалки CRUD.
- [ ] Для бота: добавление с валидацией токена (на бэке), вывод username, owner_type, purpose.
- [ ] Назначение senior'а отделу.
- [ ] **DoD:** админ полностью управляет оргструктурой через UI.

### Epic 9. Контакты (страница)
- [ ] Список контактов с поиском и фильтром по статусу.
- [ ] Открытие карточки в side-panel или отдельной странице.
- [ ] Кнопка «Открыть чат» из карточки (если есть).

### Epic 10. UX-полировка
- [ ] Notifications API: запрос разрешения, push при новом сообщении в фоне.
- [ ] Hotkeys (Ctrl+K — глобальный поиск; Ctrl+Enter — отправка; / — фокус на поиск чатов).
- [ ] Анимации (auto-animate).
- [ ] Адаптив: до 1024px — режим «два колонки», ниже — мобильный flow (вкладка либо чаты, либо открытый чат).
- [ ] Skeleton loading.

---

## 4. Точки интеграции

### Контракт с бэкендом
- Полностью описан в `API_CONTRACT.md`. Любое изменение — синк через PR.
- Типы данных генерируем из OpenAPI:
  - `npm run gen:api` → `openapi-typescript` производит `src/shared/api/types.ts`.

### Что Frontend отдаёт
- Готовый билд для DevOps (статика в `/dist`).

### Что Frontend берёт
- API контракт (от всех бэкенд-команд).
- WS-протокол (от Backend Chats).
- DSN Sentry (от DevOps).

---

## 5. Definition of Done

- ✅ Все страницы из backlog реализованы.
- ✅ Lighthouse ≥ 85 для главной.
- ✅ E2E сценарии (Playwright) проходят (`07_qa.md`).
- ✅ Адаптив до 768px без поломок основной функциональности.
- ✅ Доступность (a11y): tab-навигация, aria-label на всём, контраст AA.

---

## 6. Слабые места команды

1. **WebSocket переподключения и состояние** — самая сложная часть. После переподключения нужно ресинкнуть открытые чаты. Решение: при reconnect помечаем все списки «грязными» и при показе перезапрашиваем.
2. **Виртуализация списка сообщений + автоскролл** — частый источник багов («скачет вверх», «не доскролливает к новому»). Закладывать запас на доделки.
3. **Отображение `telegram_user_id`** не должно протекать в HTML/Vue devtools для не-админов. Тестировать руками.
4. **Хранение access-token в memory** теряется при перезагрузке — это by design. Refresh-кука компенсирует.
5. **Нотификации браузера** работают только при HTTPS. На локальном HTTP их нет — учесть в QA.
6. **Темизация и динамический CSS** — если делать сложную, замедлит рендер. На MVP — две темы и хватит.
