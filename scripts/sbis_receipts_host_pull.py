#!/usr/bin/env python3
"""Push SBIS KV/IV receipt PDFs from kali filesystem into CRM.

Run on 146.19.125.77 (local disk access):

  export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
  export ACCOUNTING_INGEST_TOKEN=...
  export SBIS_RECEIPTS_DIR=/opt/sbis-norm/media/kv_iv_complete
  # optional fallback when PDF text has no year:
  export SBIS_RECEIPTS_DEFAULT_PERIOD=2/26
  python3 scripts/sbis_receipts_host_pull.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

_NAME_PAREN_RE = re.compile(r"\(([^)]+)\)\s*\.pdf$", re.IGNORECASE)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _short_name(filename: str) -> str | None:
    match = _NAME_PAREN_RE.search(filename.strip())
    if match is None:
        return None
    name = match.group(1).strip()
    return name.casefold() if name else None


def _is_notice(filename: str) -> bool:
    lower = filename.casefold()
    return "извещение" in lower or "ввод" in lower


def _request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return int(exc.code), body


def _multipart_ingest(
    crm: str,
    token: str,
    *,
    external_id: str,
    filename: str,
    raw: bytes,
    period_code: str | None = None,
) -> tuple[int, dict]:
    boundary = f"----crm{uuid.uuid4().hex}"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    add_field("external_id", external_id)
    add_field("source_filename", filename)
    if period_code:
        add_field("period_code", period_code)
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="pdf"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8")
        + raw
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    code, resp = _request(
        "POST",
        f"{crm.rstrip('/')}/api/v1/accounting/receipts/ingest/multipart",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Accounting-Ingest-Token": token,
        },
        timeout=180.0,
    )
    try:
        payload = json.loads(resp.decode("utf-8")) if resp else {}
    except json.JSONDecodeError:
        payload = {"raw": resp[:200].decode("utf-8", errors="replace")}
    return code, payload if isinstance(payload, dict) else {"raw": payload}


def _claim_pull(crm: str, token: str) -> bool:
    code, body = _request(
        "POST",
        f"{crm.rstrip('/')}/api/v1/accounting/receipts/pull-claim",
        headers={"X-Accounting-Ingest-Token": token},
        timeout=30.0,
    )
    if code != 200:
        return False
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(isinstance(data, dict) and data.get("claimed"))


def _iter_pdfs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def run_once(*, crm: str, token: str, directory: Path, default_period: str) -> int:
    files = _iter_pdfs(directory)
    # Notices first — their parsed period seeds receipts for the same short name.
    files = sorted(files, key=lambda p: (0 if _is_notice(p.name) else 1, p.name.casefold()))
    print(f"scan {directory}: {len(files)} pdf (default_period={default_period or '-'})")
    ok = 0
    fail = 0
    period_by_short: dict[str, str] = {}
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        external_id = f"sbis-kv:{digest[:40]}"
        short = _short_name(path.name)
        period_hint: str | None = None
        if not _is_notice(path.name):
            if short and short in period_by_short:
                period_hint = period_by_short[short]
            elif default_period:
                period_hint = default_period
        code, payload = _multipart_ingest(
            crm,
            token,
            external_id=external_id,
            filename=path.name,
            raw=raw,
            period_code=period_hint,
        )
        if 200 <= code < 300:
            created = payload.get("created")
            period = str(payload.get("period_code") or period_hint or "")
            corr = " correction" if payload.get("is_correction") else ""
            print(
                f"  OK {path.name} created={created} inn={payload.get('supplier_inn')} "
                f"period={period}{corr}"
            )
            if short and period:
                period_by_short.setdefault(short, period)
            ok += 1
        else:
            print(f"  FAIL {path.name} http={code} {payload}")
            fail += 1
    print(f"done ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


def main() -> int:
    crm = _env("CRM_INGEST_BASE_URL") or _env("CRM_API_BASE_URL")
    token = _env("ACCOUNTING_INGEST_TOKEN")
    directory = Path(_env("SBIS_RECEIPTS_DIR", "/opt/sbis-norm/media/kv_iv_complete"))
    default_period = _env("SBIS_RECEIPTS_DEFAULT_PERIOD", "2/26")
    daemon = "--daemon" in sys.argv
    if not crm or not token:
        print("Need CRM_INGEST_BASE_URL and ACCOUNTING_INGEST_TOKEN", file=sys.stderr)
        return 2
    if daemon:
        print(f"daemon watching claim + dir={directory}")
        while True:
            try:
                if _claim_pull(crm, token):
                    print("claimed pull — syncing")
                    run_once(
                        crm=crm,
                        token=token,
                        directory=directory,
                        default_period=default_period,
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"daemon error: {exc}", file=sys.stderr)
            time.sleep(15)
    return run_once(
        crm=crm,
        token=token,
        directory=directory,
        default_period=default_period,
    )


if __name__ == "__main__":
    raise SystemExit(main())
