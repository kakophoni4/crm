#!/usr/bin/env python3
"""Push SBIS KV/IV receipt PDFs from kali filesystem into CRM.

Run on 146.19.125.77 (local disk access):

  export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
  export ACCOUNTING_INGEST_TOKEN=...
  export SBIS_RECEIPTS_DIR=/opt/sbis-norm/media/kv_iv_complete
  python3 scripts/sbis_receipts_host_pull.py
  python3 scripts/sbis_receipts_host_pull.py --daemon
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


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


def run_once(*, crm: str, token: str, directory: Path) -> int:
    files = _iter_pdfs(directory)
    print(f"scan {directory}: {len(files)} pdf")
    ok = 0
    fail = 0
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        external_id = f"sbis-kv:{digest[:40]}"
        code, payload = _multipart_ingest(
            crm,
            token,
            external_id=external_id,
            filename=path.name,
            raw=raw,
        )
        if 200 <= code < 300:
            created = payload.get("created")
            print(f"  OK {path.name} created={created} inn={payload.get('supplier_inn')} "
                  f"period={payload.get('period_code')}")
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
                    run_once(crm=crm, token=token, directory=directory)
                else:
                    # periodic light rescan every ~10 min even without claim
                    pass
            except Exception as exc:  # noqa: BLE001
                print(f"daemon error: {exc}", file=sys.stderr)
            time.sleep(15)
    return run_once(crm=crm, token=token, directory=directory)


if __name__ == "__main__":
    raise SystemExit(main())
