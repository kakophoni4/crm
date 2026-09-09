import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "receipt_host_pull", Path(__file__).resolve().parents[2] / "scripts/sbis_receipts_host_pull.py"
)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


@pytest.mark.parametrize("explicit", [None, "3/24"])
def test_main_has_no_implicit_period(monkeypatch, explicit):
    monkeypatch.setenv("CRM_INGEST_BASE_URL", "https://crm.example")
    monkeypatch.setenv("ACCOUNTING_INGEST_TOKEN", "test")
    monkeypatch.delenv("SBIS_RECEIPTS_DEFAULT_PERIOD", raising=False)
    if explicit:
        monkeypatch.setenv("SBIS_RECEIPTS_DEFAULT_PERIOD", explicit)
    monkeypatch.setattr(agent.sys, "argv", ["agent"])
    calls = []
    monkeypatch.setattr(agent, "run_once", lambda **kw: calls.append(kw) or 0)
    assert agent.main() == 0
    assert calls[0]["default_period"] == (explicit or "")


@pytest.mark.parametrize("explicit", ["", "3/24"])
def test_period_never_carries_over_from_same_company(monkeypatch, tmp_path, explicit):
    (tmp_path / "извещение о вводе (Компания).pdf").write_bytes(b"notice")
    (tmp_path / "квитанция о приеме (Компания).pdf").write_bytes(b"receipt")
    calls = []
    def ingest(*args, **kwargs):
        calls.append(kwargs)
        return 200, {"period_code": "1/26", "created": True}
    monkeypatch.setattr(agent, "_multipart_ingest", ingest)
    assert agent.run_once(crm="https://crm.example", token="test",
                          directory=tmp_path, default_period=explicit) == 0
    assert len(calls) == 2
    assert all(call["period_code"] == (explicit or None) for call in calls)


@pytest.mark.parametrize("code, expected", [("receipt_not_vat", 0), ("validation_error", 1)])
def test_only_non_vat_errors_are_skipped(monkeypatch, tmp_path, capsys, code, expected):
    (tmp_path / "notice.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(agent, "_multipart_ingest", lambda *a, **kw: (422, {"error": {"code": code}}))
    assert agent.run_once(crm="https://crm.example", token="test", directory=tmp_path, default_period="") == expected
    output = capsys.readouterr().out
    assert ("SKIP" in output) == (expected == 0)
