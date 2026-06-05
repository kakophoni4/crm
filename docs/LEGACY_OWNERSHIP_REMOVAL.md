# Legacy ownership removal (phase 2)

> **Статус (2026-05-17):** фаза 2 выполнена. `0025_legacy_ownership_phase2`: архив `chat_transfers` → `chat_transfers_archived_2026`, DROP `contacts.assigned_user_id` / `assigned_group_id`, DROP `chats.unread_count_user`, удалены legacy chat-transfer routes и rollback-флаги `LEGACY_CHAT_TRANSFERS_ENABLED` / `UNREAD_LEGACY_BUMP`.

---

## 1. Что сделано в фазе 1 (safe cutover)

| Компонент | Действие |
|-----------|----------|
| `contact_group_assignments` | Канонический владелец карточки per `(contact_id, group_id)` |
| `contact_group_transfers` | Канонический transfer API |
| `0015_cgt_active_uq` | Partial unique: один активный transfer на `(contact_id, group_id)` |
| Legacy chat transfer API | **410** до фазы 2; с фазы 2 — **маршруты удалены (404)** |
| `chats.last_handled_by_user_id` | ORM `Chat.assigned_user_id` — только «кто последний писал», не владелец |

---

## 2. Что сделано в фазе 2 (destructive)

| Артефакт | Действие |
|----------|----------|
| `chat_transfers` | `RENAME TO chat_transfers_archived_2026` (миграция `0025`) |
| `ChatTransfer` ORM, `transfers.py`, `legacy_guards.py` | Удалены |
| `POST /api/v1/chats/{id}/transfers`, `/transfer/*`, `/transfers/{id}/*` | Удалены из router |
| `LEGACY_CHAT_TRANSFERS_ENABLED` | Удалён из settings / `.env.example` |
| `contacts.assigned_user_id`, `assigned_group_id` | DROP; scope — только group path (`contact_group_assignments` + чаты группы) |
| `chats.unread_count_user` | DROP; канон — `chat_read_state` / `unread_for_me` |
| `UNREAD_LEGACY_BUMP` | Удалён |

**Сохранено:** `chats.last_handled_by_user_id` (UX «последний оператор»).

---

## 3. Подготовка (фаза 2a, non-destructive)

| Ревизия | Действие |
|---------|----------|
| `0023_chat_transfers_deprecated` | COMMENT ON TABLE |
| `0024_pg_trgm_search` | GIN pg_trgm |
| `scripts/audit/legacy_usage_check.py` | COUNT `chat_transfers`, MAX(updated_at), audit_log legacy transfer actions |

**Проверка prod env (2026-05-17):** в `deploy/.env.staging`, `deploy/env.staging.example`, `deploy/env.prod.example` нет `LEGACY_CHAT_TRANSFERS_ENABLED=true`.

---

## 4. Чеклист (закрыт)

- [x] Репозиторий: нет `LEGACY_CHAT_TRANSFERS_ENABLED=true` в deploy env examples
- [x] `scripts/audit/legacy_usage_check.py` — pre-flight COUNT / MAX(updated_at)
- [x] Миграция `0025` + downgrade 1 шаг в dev
- [x] `pytest tests/chats tests/contacts tests/rbac` + полный `pytest -q`
- [x] API без `unread_count_user`; нет legacy `POST /chats/{id}/transfers`
- [ ] 14 дней: нет запросов на legacy routes в access-логах prod (ops, вне репозитория)
- [ ] Backup БД перед prod apply (ops)

---

## 5. Откат (dev)

```bash
alembic downgrade -1   # 0025 → 0024: восстанавливает колонки и chat_transfers
```

Код фазы 2 откатывается отдельным revert PR (router, ORM, scope).

---

## 6. Связанные документы

- [`CONTACT_OWNERSHIP.md`](CONTACT_OWNERSHIP.md)
- [`DATABASE.md`](DATABASE.md)
- [`API_CONTRACT.md`](API_CONTRACT.md)
- [`AUDIT_REFACTOR_OWNERSHIP.md`](AUDIT_REFACTOR_OWNERSHIP.md)
