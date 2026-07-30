from app.modules.leads.opt.receipt_pdf import (
    detect_doc_kind,
    period_code_from_text,
    short_name_from_filename,
)


def test_detect_doc_kind() -> None:
    assert detect_doc_kind("квитанция о приеме (К-ПЛАСТ).pdf") == "receipt"
    assert detect_doc_kind("извещение о вводе (РИКО).pdf") == "notice"


def test_short_name_from_filename() -> None:
    assert short_name_from_filename("квитанция о приеме (Миникей).pdf") == "Миникей"


def test_period_code_from_text() -> None:
    text = "Налоговая декларация по НДС за 2 квартал 2026 год"
    assert period_code_from_text(text) == "2/26"


def test_period_code_ignores_vat_rate_22() -> None:
    # Real receipt text often has «22» (VAT) near the period line — must not become 2/22.
    text = (
        "Налоговая декларация по налогу на добавленную стоимость\n"
        "ставка 22 процент\n"
        "за 2 квартал, 2026 год\n"
        "КНД 1166002"
    )
    assert period_code_from_text(text) == "2/26"


def test_period_code_with_nbsp() -> None:
    text = "за 2\u00a0квартал,\u00a02026\u00a0год"
    assert period_code_from_text(text) == "2/26"
