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
