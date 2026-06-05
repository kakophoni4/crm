from __future__ import annotations

import pytest

from app.modules.contacts.status_automation import (
    resolve_auto_contact_status,
    validate_manual_status_change,
)
from app.modules.db.models.enums import ContactStatus


def test_resolve_new_client() -> None:
    assert (
        resolve_auto_contact_status(closed_leads_count=0, other_bot_chats_count=0)
        == ContactStatus.NEW
    )


def test_resolve_active_after_closed_lead() -> None:
    assert (
        resolve_auto_contact_status(closed_leads_count=1, other_bot_chats_count=0)
        == ContactStatus.ACTIVE
    )
    assert (
        resolve_auto_contact_status(closed_leads_count=2, other_bot_chats_count=5)
        == ContactStatus.ACTIVE
    )


def test_resolve_returning_other_bot() -> None:
    assert (
        resolve_auto_contact_status(closed_leads_count=0, other_bot_chats_count=1)
        == ContactStatus.RETURNING
    )


def test_manual_only_illiquid() -> None:
    assert validate_manual_status_change(ContactStatus.NEW, ContactStatus.DISABLED) == (
        ContactStatus.DISABLED
    )
    with pytest.raises(ValueError, match="only_illiquid_manual"):
        validate_manual_status_change(ContactStatus.NEW, ContactStatus.ACTIVE)
    assert validate_manual_status_change(ContactStatus.DISABLED, ContactStatus.NEW) is None
