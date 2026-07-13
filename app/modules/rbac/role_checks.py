"""Shared role predicates for senior / group_senior / admin."""

from __future__ import annotations

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User


def normalize_role(role: UserRole | str) -> UserRole:
    return role if isinstance(role, UserRole) else UserRole(str(role))


def actor_role(actor: User) -> UserRole:
    return normalize_role(actor.role)


def is_admin(role: UserRole | str) -> bool:
    return normalize_role(role) == UserRole.ADMIN


def is_department_senior(role: UserRole | str) -> bool:
    return normalize_role(role) == UserRole.SENIOR


def is_group_senior(role: UserRole | str) -> bool:
    return normalize_role(role) == UserRole.GROUP_SENIOR


def is_manager(role: UserRole | str) -> bool:
    """Department senior or group senior (not admin)."""
    return normalize_role(role) in {UserRole.SENIOR, UserRole.GROUP_SENIOR}


def can_force_card_owner(role: UserRole | str) -> bool:
    return normalize_role(role) in {
        UserRole.ADMIN,
        UserRole.SENIOR,
        UserRole.GROUP_SENIOR,
    }
