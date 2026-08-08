#!/usr/bin/env python3
"""Push short SBIS sales-book extract PDFs from kali into CRM.

Layout on disk:
  sales_books/<seller_INN>/<buyer_INN>.pdf   — ingest these
  sales_books/<seller_INN>/_full.pdf         — NEVER ingest
  sales_books/_summary.tsv / _*.tsv          — skip

Run on 146.19.125.77:

  export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
  export ACCOUNTING_INGEST_TOKEN=...
  export SBIS_SALES_BOOKS_DIR=/opt/sbis-norm/data/sales_books
  # optional metadata tag only (UI filters by order period):
  export SBIS_SALES_BOOKS_PERIOD_HINT=2/26
  python3 scripts/sbis_sales_books_host_pull.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path

_INN_DIR_RE = re.compile(r"^\d{10}(\d{2})?$")
_BUYER_PDF_RE = re.compile(r"^(\d{10}(\d{2})?)\.pdf$", re.IGNORECASE)


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
    seller_inn: str,
    buyer_inn: str,
    source_path: str,
    period_hint: str | None = None,
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
    add_field("seller_inn", seller_inn)
    add_field("buyer_inn", buyer_inn)
    add_field("source_path", source_path)
    meta: dict[str, object] = {"source": "sbis_sales_books_host_pull"}
    if period_hint:
        meta["period_hint"] = period_hint
    add_field("metadata_json", json.dumps(meta, ensure_ascii=False))
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
        f"{crm.rstrip('/')}/api/v1/accounting/sales-books/ingest/multipart",
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


def _iter_extract_pdfs(root: Path) -> list[tuple[Path, str, str]]:
    """Return (path, seller_inn, buyer_inn) for short extracts only."""
    out: list[tuple[Path, str, str]] = []
    if not root.is_dir():
        return out
    for seller_dir in sorted(root.iterdir()):
        if not seller_dir.is_dir():
            continue
        seller = seller_dir.name.strip()
        if not _INN_DIR_RE.match(seller):
            continue
        for pdf in sorted(seller_dir.iterdir()):
            if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
                continue
            name = pdf.name
            if name.casefold() == "_full.pdf" or name.casefold().endswith("_full.pdf"):
                continue
            if name.startswith("_"):
                continue
            match = _BUYER_PDF_RE.match(name)
            if match is None:
                continue
            out.append((pdf, seller, match.group(1)))
    return out


def run_once(*, crm: str, token: str, directory: Path, period_hint: str) -> int:
    files = _iter_extract_pdfs(directory)
    print(f"scan {directory}: {len(files)} short extract pdfs")
    ok = 0
    fail = 0
    skipped = 0
    for path, seller, buyer in files:
        raw = path.read_bytes()
        if not raw.startswith(b"%PDF"):
            print(f"  SKIP not-pdf {path}")
            skipped += 1
            continue
        digest = hashlib.sha256(raw).hexdigest()
        external_id = f"sbis-sb:{digest[:40]}"
        rel = f"{seller}/{path.name}"
        code, payload = _multipart_ingest(
            crm,
            token,
            external_id=external_id,
            filename=path.name,
            raw=raw,
            seller_inn=seller,
            buyer_inn=buyer,
            source_path=rel,
            period_hint=period_hint or None,
        )
        if 200 <= code < 300:
            print(
                f"  OK {rel} created={payload.get('created')} "
                f"seller={payload.get('seller_inn')} buyer={payload.get('buyer_inn')}"
            )
            ok += 1
        else:
            print(f"  FAIL {rel} http={code} {payload}")
            fail += 1
    print(f"done ok={ok} fail={fail} skipped={skipped}")
    return 0 if fail == 0 else 1


def main() -> int:
    crm = _env("CRM_INGEST_BASE_URL") or _env("CRM_API_BASE_URL")
    token = _env("ACCOUNTING_INGEST_TOKEN")
    directory = Path(_env("SBIS_SALES_BOOKS_DIR", "/opt/sbis-norm/data/sales_books"))
    period_hint = _env("SBIS_SALES_BOOKS_PERIOD_HINT")
    if not crm or not token:
        print("Need CRM_INGEST_BASE_URL and ACCOUNTING_INGEST_TOKEN", file=sys.stderr)
        return 2
    try:
        token.encode("latin-1")
    except UnicodeEncodeError:
        print(
            "ACCOUNTING_INGEST_TOKEN содержит не-ASCII. "
            "Вставь реальный токен из CRM env.",
            file=sys.stderr,
        )
        return 2
    if "…" in token or token in {"СЮДА_ТОКЕН", "...", "TOKEN"}:
        print("ACCOUNTING_INGEST_TOKEN — плейсхолдер, нужен реальный токен", file=sys.stderr)
        return 2
    return run_once(crm=crm, token=token, directory=directory, period_hint=period_hint)


if __name__ == "__main__":
    raise SystemExit(main())
