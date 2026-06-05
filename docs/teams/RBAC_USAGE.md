# RBAC usage guide

> Source of truth for rules: [`RBAC_MATRIX.md`](../RBAC_MATRIX.md). This document explains how to apply permissions and scope in handlers.

## Permission checks in routes

Use FastAPI dependencies from `app.shared.security.permissions`:

```python
from fastapi import APIRouter, Depends

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.security.permissions import requires_all_permissions, requires_permission

router = APIRouter()

@router.post("/users")
async def create_user(
    user: User = Depends(requires_permission(Permission.USERS_CREATE_IN_DEP)),
) -> None:
    ...
```

- `requires_permission(*perms)` — actor needs **any** of the listed permissions (OR).
- `requires_all_permissions(*perms)` — actor needs **every** listed permission (AND).

On denial the API returns `403` with `error.code = permission_denied` and `error.details.required` listing slug strings.

## Programmatic checks

```python
from app.modules.rbac.role_map import has_permission, has_any_permission
from app.modules.rbac.permissions import Permission

if has_permission(actor.role, Permission.CHATS_TRANSFER_APPROVE):
    ...
```

Admin always passes `has_permission` for every slug.

## Scope (data visibility)

Scope helpers live in `app.modules.rbac.scope`. They are **pure** (no DB): preload membership into `ScopeContext` in the service layer, then filter queries.

```python
from app.modules.rbac.scope import ScopeContext, visible_user_ids, SCOPE_ALL

ctx = ScopeContext(
    actor=current_user,
    group_member_ids=frozenset(member_ids),
    department_user_ids=frozenset(dept_user_ids),
    department_senior_id=head_user_id,
    department_group_ids=frozenset(group_ids),
)

user_scope = visible_user_ids(ctx)
if user_scope == SCOPE_ALL:
    # no extra WHERE on users
elif user_scope:
    stmt = stmt.where(User.id.in_(user_scope))
else:
    stmt = stmt.where(false())
```

Use the same pattern for `visible_group_ids` and `visible_department_ids`.

`can_act_on_user(ctx, target)` — use before transfer/takeover/user PATCH when the target user must fall inside actor scope (senior cannot edit another senior).

## Anti-patterns

1. **Hardcoding role strings** (`if user.role == "admin"`) — use `UserRole` and `has_permission` / `ROLE_PERMISSIONS` only.
2. **Checking permissions without scope** — `users.read` allows the action, but the row must still match `visible_user_ids`.
3. **Returning ORM rows before scope** — repositories must apply scope in SQL, not filter in Python after a wide SELECT.
4. **Importing `app.modules.auth` from RBAC** — RBAC depends only on `app.modules.db.models`.
5. **Database-driven permissions** — not supported in Round 1–7; role map is static in `role_map.py`.
6. **Duplicating matrix in handlers** — add a `Permission` slug and map it in `role_map.py`, then test in `tests/rbac/`.

## Tests

```bash
pytest tests/rbac -q --cov=app/modules/rbac --cov-report=term-missing
```

When changing access rules, update `docs/RBAC_MATRIX.md` first, then `permissions.py`, `role_map.py`, and parametrized expectations in `tests/rbac/test_role_map_complete.py`.
