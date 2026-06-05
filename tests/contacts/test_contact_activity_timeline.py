from __future__ import annotations

from datetime import UTC, datetime

from app.modules.contacts.activity_timeline import (
    _status_change_label,
    field_change_activity_item,
    lead_activity_items,
    transfer_activity_items,
)
from app.modules.db.models.enums import AuditAction, TransferStatus


class _User:
    def __init__(self, user_id: int, full_name: str) -> None:
        self.id = user_id
        self.full_name = full_name


class _Transfer:
    def __init__(
        self,
        transfer_id: int,
        *,
        state: TransferStatus,
        recipient_decided_at: datetime | None = None,
        senior_decided_at: datetime | None = None,
    ) -> None:
        self.id = transfer_id
        self.state = state
        self.created_at = datetime(2026, 1, 3, 9, 0, tzinfo=UTC)
        self.updated_at = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)
        self.recipient_decided_at = recipient_decided_at
        self.senior_decided_at = senior_decided_at
        self.from_user = _User(1, "Аня")
        self.to_user = _User(2, "Борис")
        self.requester = _User(1, "Аня")
        self.senior_user = _User(3, "Старший")


class _Change:
    def __init__(
        self,
        row_id: int,
        *,
        field_name: str = "note",
        old_value: str | None = "a",
        new_value: str | None = "b",
    ) -> None:
        self.id = row_id
        self.field_name = field_name
        self.old_value = old_value
        self.new_value = new_value
        self.changed_at = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
        self.changer = _User(4, "Ольга Козлова")


def test_field_change_includes_actor_and_details() -> None:
    item = field_change_activity_item(_Change(10))
    assert item.actor_name == "Ольга Козлова"
    assert "Пометка" in item.label
    assert "a" in item.label
    assert "b" in item.label


def test_status_change_label_from_to() -> None:
    label = _status_change_label(
        {"from_status_id": 1, "to_status_id": 2},
        status_labels={1: "Новый", 2: "В работе"},
        group_suffix=" (Продажи)",
    )
    assert label == "Этап сделки (Продажи): Новый → В работе"


class _Lead:
    def __init__(self, lead_id: int, *, closed: bool = False) -> None:
        self.id = lead_id
        self.created_at = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        self.closed_at = datetime(2026, 1, 2, 12, 0, tzinfo=UTC) if closed else None
        self.group = type("G", (), {"name": "Продажи"})()


class _Audit:
    def __init__(
        self,
        audit_id: int,
        *,
        action: AuditAction,
        payload: dict | None = None,
        actor_name: str | None = "Иван",
    ) -> None:
        self.id = audit_id
        self.action = action
        self.payload = payload or {}
        self.created_at = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
        self.actor = type("U", (), {"id": 1, "full_name": actor_name})() if actor_name else None


def test_lead_status_updates_listed_from_audits() -> None:
    lead = _Lead(7)
    audits = [
        _Audit(1, action=AuditAction.LEAD_CREATE),
        _Audit(
            2,
            action=AuditAction.LEAD_STATUS_UPDATE,
            payload={"from_status_id": 10, "to_status_id": 11},
        ),
        _Audit(3, action=AuditAction.LEAD_CLOSE),
    ]
    items = lead_activity_items(
        lead,
        audits,
        status_labels={10: "Новый", 11: "В работе"},
        user_names={1: "Иван"},
    )
    labels = [item.label for item in items]
    assert "Этап сделки (Продажи): Новый → В работе" in labels
    status_item = next(item for item in items if "→" in item.label)
    assert status_item.actor_name == "Иван"
    assert status_item.occurred_at == audits[1].created_at


def test_transfer_accepted_includes_actor() -> None:
    transfer = _Transfer(
        5,
        state=TransferStatus.ACCEPTED,
        recipient_decided_at=datetime(2026, 1, 4, 15, 0, tzinfo=UTC),
    )
    items = transfer_activity_items(transfer)
    assert items[0].actor_name == "Аня"
    assert "Аня" in items[0].label
    assert "Борис" in items[0].label
    assert items[1].actor_name == "Борис"
    assert items[1].label.startswith("Передача выполнена")
