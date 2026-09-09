import pytest

from app.modules.accounting.receipts import resolve_receipt_period
from app.modules.leads.opt.receipt_pdf import period_code_from_text
from app.shared.exceptions import ValidationError


@pytest.mark.parametrize("quarter", [1, 2, 3, 4])
def test_sbis_period_with_numeric_code(quarter):
    text = f"корректирующий (1), за\n{quarter} квартал, {20 + quarter}, 2026 год"
    assert period_code_from_text(text) == f"{quarter}/26"


def test_sbis_period_with_pdf_whitespace():
    assert period_code_from_text("за 1 к в а р т а л,\n21,\u00a02026 год") == "1/26"


@pytest.mark.parametrize("is_correction", [True, False])
def test_pdf_period_wins_over_batch_default(is_correction):
    assert resolve_receipt_period("1/26", "2/26", is_correction=is_correction) == "1/26"


def test_primary_can_use_hint_when_period_not_parsed():
    assert resolve_receipt_period(None, "2/26", is_correction=False) == "2/26"


def test_unparsed_correction_cannot_silently_inherit_batch_period():
    with pytest.raises(ValidationError):
        resolve_receipt_period(None, "2/26", is_correction=True)


def test_invalid_hint_does_not_override_pdf():
    assert resolve_receipt_period("1/26", "bad", is_correction=True) == "1/26"


async def test_reingest_updates_existing_period_and_stale_parsed_metadata(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    import app.modules.accounting.receipts as receipts
    from app.modules.leads.opt.receipt_pdf import ParsedReceiptPdf

    parsed = ParsedReceiptPdf(
        supplier_inn="7751377028", supplier_kpp=None, supplier_name="ОПТИМА",
        period_code="1/26", doc_kind="receipt", parsed_name="ОПТИМА",
        raw_text="за 1 квартал, 21, 2026 год", is_correction=True,
    )
    existing = SimpleNamespace(period_code="2/26")
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(kpp=None, name="ОПТИМА")
    session.execute.return_value = result
    monkeypatch.setattr(receipts, "parse_receipt_pdf", lambda *args, **kwargs: parsed)
    monkeypatch.setattr(receipts, "OptReceiptRepository", lambda _: SimpleNamespace(get_by_external_id=AsyncMock(return_value=existing)))
    monkeypatch.setattr(receipts, "FilesService", lambda _: SimpleNamespace(create_upload=AsyncMock(return_value=SimpleNamespace(id=99))))
    row, created = await receipts.ingest_receipt_pdf(
        session, external_id="test", pdf_bytes=b"%PDF test",
        source_filename="receipt.pdf", period_code="2/26",
        metadata={"parsed": {"period_code": "2/26"}},
    )
    assert not created
    assert row.period_code == "1/26"
    assert row.metadata_json["parsed"]["period_code"] == "1/26"
