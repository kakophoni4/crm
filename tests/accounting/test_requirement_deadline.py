"""Unit tests for FNS requirement deadline parsing."""

from __future__ import annotations

from datetime import date

from app.modules.accounting.requirement_deadline import (
    add_working_days,
    parse_working_days_from_text,
    resolve_response_due_date,
)


def test_add_working_days_skips_weekend() -> None:
    # Friday + 1 working day → Monday
    assert add_working_days(date(2026, 8, 7), 1) == date(2026, 8, 10)
    # Monday + 5 working days → next Monday
    assert add_working_days(date(2026, 8, 3), 5) == date(2026, 8, 10)


def test_parse_working_days_from_fns_boilerplate() -> None:
    text = (
        "В течение 5 рабочих дней со дня получения настоящего Требования "
        "необходимо представить пояснения или в течение 5 рабочих дней "
        "внести соответствующие исправления."
    )
    assert parse_working_days_from_text(text) == 5


def test_resolve_prefers_existing_sbis_due() -> None:
    parsed = resolve_response_due_date(
        existing=date(2026, 8, 20),
        received_on=date(2026, 8, 8),
        pdf_text="В течение 5 рабочих дней со дня получения",
    )
    assert parsed.source == "sbis"
    assert parsed.response_due_date == date(2026, 8, 20)


def test_resolve_uses_pdf_working_days() -> None:
    parsed = resolve_response_due_date(
        existing=None,
        received_on=date(2026, 8, 7),  # Friday
        pdf_text="В течение 5⁴ рабочих дней со дня получения настоящего Требования⁵",
    )
    assert parsed.source == "pdf_working_days"
    assert parsed.working_days == 5
    assert parsed.response_due_date == date(2026, 8, 14)  # Fri→Mon..Fri


def test_resolve_defaults_to_five_working_days() -> None:
    parsed = resolve_response_due_date(
        existing=None,
        received_on=date(2026, 8, 3),
        pdf_text="без явного срока",
    )
    assert parsed.source == "default_working_days"
    assert parsed.working_days == 5
    assert parsed.response_due_date == date(2026, 8, 10)
