#!/usr/bin/env python3
"""Pull FNS requirements from sbis-norm (binary /file/) and push into CRM ingest.

Run on kali (localhost sbis) — CRM→sbis body path is broken.

  export SBIS_NORM_API_BASE_URL=http://127.0.0.1:8000
  export CRM_INGEST_BASE_URL=https://api.bttsrvvrs.org
  export ACCOUNTING_INGEST_TOKEN=...
  python3 scripts/sbis_norm_host_pull.py

Daemon (poll CRM pull-claim after UI «Забрать из СБИС»):

  python3 scripts/sbis_norm_host_pull.py --daemon
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from typing import Any


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


def _request_json(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> Any:
    _code, body = _request(method, url, data=data, headers=headers, timeout=timeout)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _request_bytes(url: str, *, timeout: float = 120.0) -> bytes:
    _code, body = _request("GET", url, timeout=timeout)
    return body


def _is_pdf(name: object) -> bool:
    return str(name or "").strip().lower().endswith(".pdf")


def _multipart_ingest(
    crm: str,
    token: str,
    *,
    external_id: str,
    supplier_inn: str,
    title: str,
    filename: str,
    raw: bytes,
    metadata: dict[str, Any],
) -> Any:
    boundary = f"----crm{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    add_field("external_id", external_id)
    add_field("supplier_inn", supplier_inn)
    add_field("title", title)
    add_field("status", "new")
    add_field("metadata_json", json.dumps(metadata, ensure_ascii=False))

    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="pdf"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
    )
    chunks.append(raw)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)

    code, resp = _request(
        "POST",
        f"{crm}/api/v1/accounting/requirements/ingest/multipart",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Accounting-Ingest-Token": token,
        },
        timeout=120,
    )
    if code >= 400:
        raise RuntimeError(f"ingest HTTP {code}: {resp[:500]!r}")
    if not resp:
        return None
    return json.loads(resp.decode("utf-8"))


def run_pull() -> int:
    sbis = _env("SBIS_NORM_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    crm = _env("CRM_INGEST_BASE_URL", "https://api.bttsrvvrs.org").rstrip("/")
    token = _env("ACCOUNTING_INGEST_TOKEN")
    if not token:
        print("ACCOUNTING_INGEST_TOKEN is required", file=sys.stderr)
        return 2

    created = existing = skipped = failed = marked = 0
    max_pages = int(_env("SBIS_NORM_SYNC_MAX_PAGES", "500") or "500")
    batch = max(1, int(_env("SBIS_NORM_SYNC_BATCH_LIMIT", "20") or "20"))

    for _page in range(max_pages):
        listing = _request_json(
            "GET",
            f"{sbis}/api/sbis/requirements/?unsynced=1&limit={batch}",
            timeout=60,
        )
        rows = (listing or {}).get("results") or []
        if not rows:
            break

        mark_ids: list[int] = []
        for item in rows:
            sbis_id = int(item["id"])
            name = item.get("storage_file_name") or ""

            if not _is_pdf(name):
                mark_ids.append(sbis_id)
                skipped += 1
                print(f"skip-non-pdf id={sbis_id} {name}")
                continue

            try:
                raw = _request_bytes(
                    f"{sbis}/api/sbis/requirements/{sbis_id}/file/",
                    timeout=120,
                )
                if not raw:
                    raise RuntimeError("empty file body")
                filename = str(name or f"requirement_{sbis_id}.pdf")
                # ASCII-safe filename for Content-Disposition; keep real name in metadata
                safe_name = f"requirement_{sbis_id}.pdf"
                inn = str(item.get("inn") or "").strip()
                title = str(item.get("doc_title") or "Требование ФНС").strip() or "Требование ФНС"
                metadata = {
                    "source": "sbis-norm-host-pull",
                    "sbis_id": sbis_id,
                    "sbis_doc_id": item.get("sbis_doc_id"),
                    "content_sha256": item.get("content_sha256"),
                    "document_date": item.get("document_date"),
                    "storage_file_name": filename,
                    "file_url": item.get("file_url"),
                }
                ingest = _multipart_ingest(
                    crm,
                    token,
                    external_id=f"sbis-req:{sbis_id}",
                    supplier_inn=inn,
                    title=title,
                    filename=safe_name,
                    raw=raw,
                    metadata=metadata,
                )
                if ingest and ingest.get("created"):
                    created += 1
                else:
                    existing += 1
                mark_ids.append(sbis_id)
                print(
                    f"pdf ok id={sbis_id} inn={inn} bytes={len(raw)} "
                    f"created={ingest.get('created') if ingest else None}"
                )
            except Exception as exc:
                failed += 1
                print(f"pdf FAIL id={sbis_id}: {exc}", file=sys.stderr)

        if mark_ids:
            _request_json(
                "POST",
                f"{sbis}/api/sbis/requirements/mark-synced/",
                data=json.dumps({"ids": mark_ids}).encode(),
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            marked += len(mark_ids)

        if len(rows) < batch:
            break

    print(
        f"done created={created} existing={existing} skipped_non_pdf={skipped} "
        f"marked={marked} failed={failed}"
    )
    return 0 if failed == 0 else 1


def claim_once(crm: str, token: str) -> bool:
    code, body = _request(
        "POST",
        f"{crm}/api/v1/accounting/requirements/pull-claim",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Accounting-Ingest-Token": token,
        },
        timeout=30,
    )
    if code >= 400:
        print(f"claim HTTP {code}: {body[:300]!r}", file=sys.stderr)
        return False
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return False
    return bool(payload.get("claimed"))


def run_daemon() -> int:
    crm = _env("CRM_INGEST_BASE_URL", "https://api.bttsrvvrs.org").rstrip("/")
    token = _env("ACCOUNTING_INGEST_TOKEN")
    if not token:
        print("ACCOUNTING_INGEST_TOKEN is required", file=sys.stderr)
        return 2
    interval = max(2, int(_env("SBIS_NORM_PULL_POLL_SECONDS", "5") or "5"))
    print(f"daemon: poll {crm} every {interval}s", flush=True)
    while True:
        try:
            if claim_once(crm, token):
                print("claimed pull request — running", flush=True)
                run_pull()
        except Exception as exc:
            print(f"daemon error: {exc}", file=sys.stderr)
        time.sleep(interval)


def main() -> int:
    if "--daemon" in sys.argv:
        return run_daemon()
    return run_pull()


if __name__ == "__main__":
    raise SystemExit(main())
