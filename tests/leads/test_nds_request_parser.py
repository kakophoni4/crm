from __future__ import annotations

from pathlib import Path

from app.modules.leads.opt.nds_request_parser import (
    looks_like_nds_request,
    parse_nds_request_workbook,
)


def test_parse_sample_nds_request_file() -> None:
    path = Path(__file__).resolve().parents[1] / "63. ЗАПРОС НДС 2 КВ. 2026Г..xlsx"
    if not path.exists():
        # Sample workbook may be absent in CI — skip lightly.
        return
    content = path.read_bytes()
    assert looks_like_nds_request(content)
    result = parse_nds_request_workbook(content)
    assert result.matched
    assert result.application is not None
    assert result.application.buyer_inn == "6321443710"
    assert len(result.application.lines) >= 40
    assert result.application.lines[0].supplier_inn == "9704271074"
    assert result.application.lines[0].amount > 0


def test_reject_random_bytes() -> None:
    assert not looks_like_nds_request(b"not-an-excel")
    result = parse_nds_request_workbook(b"not-an-excel")
    assert result.matched is False
