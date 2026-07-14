from __future__ import annotations

from datetime import UTC, datetime

from app.modules.contacts.after_hours import is_within_working_hours


def test_within_weekday_window() -> None:
    # 2026-07-10 12:00 UTC = 15:00 Europe/Moscow on Friday
    now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    assert is_within_working_hours(
        now.replace(tzinfo=None),
        timezone="Europe/Moscow",
        working_hours={"fri": [["09:00", "18:00"]], "sat": [], "sun": []},
    )


def test_outside_weekday_window() -> None:
    # 2026-07-10 20:00 UTC = 23:00 Europe/Moscow on Friday
    now = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
    assert not is_within_working_hours(
        now.replace(tzinfo=None),
        timezone="Europe/Moscow",
        working_hours={"fri": [["09:00", "18:00"]]},
    )


def test_weekend_empty_is_outside() -> None:
    # 2026-07-11 Saturday 12:00 Moscow
    now = datetime(2026, 7, 11, 9, 0, tzinfo=UTC)
    assert not is_within_working_hours(
        now.replace(tzinfo=None),
        timezone="Europe/Moscow",
        working_hours={"sat": [], "sun": []},
    )
