from datetime import date

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
        accepted_date=date(2026, 8, 4), tax_kind="vat",
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
    assert row.source_filename == "receipt 04.08.2026.pdf"
    assert row.metadata_json["parsed"]["accepted_date"] == "2026-08-04"
    assert not created
    assert row.period_code == "1/26"
    assert row.metadata_json["parsed"]["period_code"] == "1/26"


@pytest.mark.parametrize("text, expected", [
    ("направлен 03.08.2026, принят 04.08.2026", "2026-08-04"),
    ("Документ подписан 04.08.26 12:31\n(MSK)", "2026-08-04"),
    ("принята 05.08.2026; 06.08.26 12:31 (MSK)", "2026-08-05"),
    ("принят 31.02.2026", None),
    ("направлен 03.08.2026", None),
])
def test_acceptance_date(text, expected):
    from app.modules.leads.opt.receipt_pdf import acceptance_date_from_text
    value = acceptance_date_from_text(text)
    assert (value.isoformat() if value else None) == expected


def test_dated_filename_replaces_export_date_and_is_idempotent():
    from app.modules.leads.opt.receipt_pdf import dated_receipt_filename
    original = "квитанция о приеме (ОПТИМА) 06-08-2026 abcdef12.pdf"
    expected = "квитанция о приеме (ОПТИМА) 04.08.2026.pdf"
    assert dated_receipt_filename(original, date(2026, 8, 4)) == expected
    assert dated_receipt_filename(expected, date(2026, 8, 4)) == expected


@pytest.mark.parametrize("text, kind", [
    ("КНД 1166002 декларация 1151001", "vat"),
    ("NO_NDS_7751_7751", "vat"),
    ("Налоговая декларация по налогу на добавленную стоимость", "vat"),
    ("Налоговая декларация по налогу на прибыль организаций 1151006, за 6 месяцев, квартальный, 2026 год NO_PRIB_7723_7723", "other"),
    ("КНД 1166002", None),
    ("", None),
])
def test_declaration_tax_kind(text, kind):
    from app.modules.leads.opt.receipt_pdf import tax_kind_from_text
    assert tax_kind_from_text(text) == kind


@pytest.mark.parametrize("kind, code", [("other", "receipt_not_vat"), (None, "validation_error")])
async def test_non_vat_is_rejected_before_upload(monkeypatch, kind, code):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    import app.modules.accounting.receipts as receipts
    from app.shared.exceptions import AppError
    monkeypatch.setattr(receipts, "OptReceiptRepository", lambda _: SimpleNamespace(get_by_external_id=AsyncMock(return_value=None)))
    monkeypatch.setattr(receipts, "parse_receipt_pdf", lambda *a, **kw: SimpleNamespace(tax_kind=kind))
    files = MagicMock()
    monkeypatch.setattr(receipts, "FilesService", files)
    with pytest.raises(AppError) as exc:
        await receipts.ingest_receipt_pdf(AsyncMock(), external_id="test", pdf_bytes=b"pdf", source_filename="test.pdf", period_code="2/26")
    assert exc.value.code == code
    files.assert_not_called()


def test_tax_disclosure_consent_is_not_vat():
    from app.modules.leads.opt.receipt_pdf import tax_kind_from_text
    text = "Код по КНД 1167001 Квитанция о приеме Согласие налогоплательщика IU_SOGNTOB_7733_7733_7733414245773301001_20260824_01a03328"
    assert tax_kind_from_text(text) == "other"
    # The receipt form alone does not identify the underlying document.
    assert tax_kind_from_text("Код по КНД 1167001 Квитанция о приеме") is None
