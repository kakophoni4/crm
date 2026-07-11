from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.leads.opt.fingerprint import compute_application_fingerprint
from app.modules.leads.opt.parser import ParsedApplication, ParsedApplicationLine


def _sample_parsed(*, buyer_inn: str = "7700000100", amount: str = "100000.00") -> ParsedApplication:
    return ParsedApplication(
        buyer_inn=buyer_inn,
        lines=[
            ParsedApplicationLine(
                supplier_inn="7700000001",
                document_date=date(2025, 3, 15),
                amount=Decimal(amount),
            ),
        ],
    )


def test_fingerprint_stable_for_same_content() -> None:
    first = compute_application_fingerprint(_sample_parsed())
    second = compute_application_fingerprint(_sample_parsed())
    assert first == second
    assert len(first) == 64


def test_fingerprint_changes_when_amount_differs() -> None:
    base = compute_application_fingerprint(_sample_parsed())
    changed = compute_application_fingerprint(_sample_parsed(amount="100000.01"))
    assert base != changed


def test_fingerprint_ignores_line_order() -> None:
    line_a = ParsedApplicationLine(
        supplier_inn="1111111111",
        document_date=date(2025, 1, 1),
        amount=Decimal("10.00"),
    )
    line_b = ParsedApplicationLine(
        supplier_inn="2222222222",
        document_date=date(2025, 2, 2),
        amount=Decimal("20.00"),
    )
    forward = compute_application_fingerprint(
        ParsedApplication(buyer_inn="7700000100", lines=[line_a, line_b]),
    )
    reverse = compute_application_fingerprint(
        ParsedApplication(buyer_inn="7700000100", lines=[line_b, line_a]),
    )
    assert forward == reverse
