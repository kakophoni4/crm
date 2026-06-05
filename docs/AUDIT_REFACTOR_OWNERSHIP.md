# Аудит: переход на модель «владение карточкой в группе»

> Дата аудита: 2026-05-16. Каноническая спека: [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md).

---

## 1. Резюме

| | |
|---|---|
| **Запрошенная модель** | Владелец = карточка **внутри группы**; чат общий для группы; transfer карточки; эскалация N мин; аудит «кто ответил / кто владелец». |
| **Текущая документация (до рефактора)** | Chat-centric: `current_user_id` на чате, transfer чата, user видит только свои чаты. |
| **Текущий код (факт)** | R1–R4 + FE ownership UI; `OWNERSHIP_V2=true`; pytest 342 passed; E2E-6/7 — `scripts/qa_e2e_ownership.py`. |
| **Сложность** | Рефактор **закрыт** (QA 2026-05-17). |

---

## 2. Матрица расхождений

| Область | Было (доки/код) | Должно быть | Статус кода |
|---------|-----------------|-------------|-------------|
| Владелец | `chats.current_user_id` / `contacts.assigned_user_id` | `contact_group_assignments.owner_user_id` | ✅ 0012 + `ownership.py` |
| Scope чатов user | только `current_user_id == self` | все чаты `assigned_group_id == my group` | ✅ `chats/scope.py` + `OWNERSHIP_V2` |
| Писать в чат | только свой чат | любой user группы | ✅ group write + `message_reply_audit` |
| Transfer | `chat_transfers` + `/chats/{id}/transfers` | `contact_group_transfers` + `/contacts/{id}/groups/{gid}/transfer` | ✅ contact transfers; chat API **410** (cutover 2026-05-17, см. `LEGACY_OWNERSHIP_REMOVAL.md`) |
| Assignment при inbound | `assignment_service.assign(chat)` | assign `(contact, group)` | ✅ `ownership_bridge.py` |
| Эскалация N мин | не описано | `group_escalation_settings` + worker | ✅ 0013 + `workers/escalation.py` |
| Перераспределение нового | round-robin на чат | first_responder / random_available | ✅ `escalation.py` |
| Аудит ответа | `author_user_id` на message | + `message_reply_audit` + owner snapshot | ✅ 0014 + `reply_audit.py` |
| Уведомления | всем assigned | сначала owner, потом group | ✅ WS topics `contact.escalation.*` |
| Multi-bot multi-group | US-32 (разные чаты) | + **разное владение per group** | ✅ per-group assignments |

---

## 3. Файлы: что менять

### 3.1 Документация (обновлено в этом рефакторе)

| Файл | Действие |
|------|----------|
| `CONTACT_OWNERSHIP.md` | **Создан** — источник истины |
| `AUDIT_REFACTOR_OWNERSHIP.md` | **Создан** — этот файл |
| `TECH_SPEC.md` | Обновлён §4, §5, глоссарий |
| `DATABASE.md` | Новые таблицы, deprecated поля |
| `ARCHITECTURE.md` | Потоки inbound/outbound/assignment/escalation |
| `RBAC_MATRIX.md` | Видимость чатов, transfer контакта, escalation |
| `API_CONTRACT.md` | Новые эндпоинты, deprecated |
| `EVENTS.md` | contact.ownership.*, escalation |
| `EXECUTION_ORDER.md` | Фаза 3.5 Refactor Ownership |
| `ROADMAP.md` | Вставка фазы |
| `teams/02_backend_chats.md` | Epic assignment → ownership |
| `teams/04_backend_contacts.md` | Per-group assignment, transfers |
| `teams/05_frontend.md` | UI владельца, on_behalf, escalation |
| `teams/07_qa.md` | E2E сценарии |
| `README.md` | Ссылка на CONTACT_OWNERSHIP |

### 3.2 Backend (субагенты — ещё не сделано)

| Путь | Действие |
|------|----------|
| `alembic/versions/0012_contact_group_ownership.py` | NEW |
| `alembic/versions/0013_group_escalation_settings.py` | NEW |
| `alembic/versions/0014_message_reply_audit.py` | NEW |
| `app/modules/db/models/contact_group_assignment.py` | NEW |
| `app/modules/contacts/ownership.py` | NEW — assign, transfer, get_owner |
| `app/modules/contacts/escalation.py` | NEW — timers, reassign |
| `app/modules/chats/scope.py` | REWRITE — group-visible |
| `app/modules/chats/service.py` | WRITE — on_behalf audit on send |
| `app/modules/bots/chats_bridge.py` | assign contact+group not chat user |
| `app/workers/escalation.py` | NEW |
| `app/modules/chats/transfers.py` | DEPRECATE → thin wrapper or remove |
| `tests/contacts/test_ownership_*.py` | NEW |
| `tests/chats/test_group_write_on_behalf.py` | NEW |

### 3.3 Frontend (субагент)

| Путь | Действие |
|------|----------|
| `features/contacts/ownership.ts` | owner badge, transfer card |
| `pages/chats/index.vue` | фильтры: Мои карточки / Группа / Просрочено |
| `widgets/chat/MessageBubble.vue` | on_behalf label |
| `features/settings/escalation.vue` | senior: N minutes |

---

## 4. Порядок внедрения (рекомендуемый)

```text
Фаза R1 — Schema + backfill (1–2 дня)
  0012 contact_group_assignments + backfill from chats/contacts
  0013 group_escalation_settings (defaults)
  0014 message_reply_audit

Фаза R2 — Core logic (3–5 дней)
  ownership service (assign, transfer contact in group)
  chats scope + write rules (group can write)
  inbound path (bots_bridge) uses group assignment
  outbound → message_reply_audit

Фаза R3 — Escalation worker (2 дня)
  Redis timers or scheduled scan pending_inbound_at
  notify owner → notify group → reassign new contact

Фаза R4 — API + deprecate (2 дня)
  New transfer endpoints; mark old chat transfer deprecated
  GET contact includes group_ownership[]

Фаза R5 — Frontend (3–4 дня)
  UI filters, badges, transfer card, escalation settings

Фаза R6 — QA + dual-run (2 дня)
  E2E: on_behalf audit, transfer within group only, escalation
```

**Параллельно:** R1 → (R2 + R3) → R4 → R5 → R6.

---

## 5. Backfill SQL (черновик)

```sql
-- Для каждого чата с bot.owner_type='group':
INSERT INTO contact_group_assignments (contact_id, group_id, owner_user_id, assigned_at, assignment_source)
SELECT DISTINCT c.contact_id, b.owner_id, c.assigned_user_id, c.created_at, 'migration_from_chat'
FROM chats c
JOIN bots b ON b.id = c.bot_id AND b.owner_type = 'group'
WHERE c.assigned_user_id IS NOT NULL
ON CONFLICT (contact_id, group_id) DO UPDATE
  SET owner_user_id = EXCLUDED.owner_user_id
  WHERE contact_group_assignments.owner_user_id IS NULL;
```

---

## 6. Критерии приёмки (DoD рефакторинга)

- [x] User группы G видит **все** чаты ботов с `owner_id=G`, не только свои. (`tests/chats/test_group_scope_ownership.py`)
- [x] User может **писать** в чат группы; в аудите видно owner vs author. (`message_reply_audit`, E2E-6)
- [x] Transfer **(contact, group)** меняет владельца; чат в **другой группе** того же contact — **без изменений**. (E2E-7, `test_contact_transfer_does_not_affect_other_group`)
- [x] Inbound: уведомление **сначала owner**; через N мин — **группе** (настройка senior). (`ownership_bridge`, E2E-7b)
- [x] Новый contact: если owner не ответил за N — reassign по стратегии группы. (`test_reassign_first_responder`, E2E-7b)
- [x] `GET /contacts/{id}/groups/{gid}/reply-audit` отдаёт `card_owner` + `author` + `is_on_behalf`.
- [x] pytest ownership/escalation (20+); chat transfer tests адаптированы под deprecated.
- [x] Документация согласована; QA E2E-6/7 в `teams/07_qa.md` (2026-05-17).

---

## 7. Слабые места рефакторинга

1. **Dual model period** — если оставить `current_user_id` и новую таблицу, логика разъедется. Нужен жёсткий cutover или feature flag `OWNERSHIP_V2`.
2. **Round 4 tests** — ~15+ тестов на chat transfer потребуют переписывания.
3. **Frontend уже на `/contacts`** — нужны новые поля API без breaking (добавить `group_ownership`, не удалять старые сразу).
4. **PostgreSQL 5433 / test DB** — миграции гонять на изолированной БД (см. README).
