"""Who may set / change OPT order period_code."""

from __future__ import annotations

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.leads.opt.periods import list_opt_period_codes, normalize_period_code
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission
from app.shared.exceptions import PermissionDenied, ValidationError


def _role(actor: User) -> UserRole:
    return actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))


def can_change_order_period(actor: User) -> bool:
    """Admin or chief accountant (accounting.manage)."""
    role = _role(actor)
    if role == UserRole.ADMIN:
        return True
    return has_permission(role, Permission.ACCOUNTING_MANAGE)


def can_set_missing_order_period(actor: User) -> bool:
    """Set period when empty: seniors + accountants + those who may change."""
    if can_change_order_period(actor):
        return True
    role = _role(actor)
    return role in {
        UserRole.SENIOR,
        UserRole.GROUP_SENIOR,
        UserRole.ACCOUNTANT,
    }


def resolve_writable_period_code(
    actor: User,
    *,
    current: str | None,
    requested: str,
) -> str:
    """Validate period and enforce set-vs-change rules. Returns normalized code."""
    new_code = normalize_period_code(requested)
    if new_code is None or new_code not in set(list_opt_period_codes()):
        raise ValidationError(message="Некорректный период")

    current_code = normalize_period_code(current) if current else None
    if current_code is None:
        if not can_set_missing_order_period(actor):
            raise PermissionDenied(message="Недостаточно прав для указания периода")
        return new_code

    if current_code == new_code:
        return new_code

    if not can_change_order_period(actor):
        raise PermissionDenied(
            message="Менять период может только главный бухгалтер или администратор",
        )
    return new_code
