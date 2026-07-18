#!/usr/bin/env python3
"""Pull FNS requirements from sbis-norm (binary /file/ endpoint).

Preferred path after sbis-norm API update:

  GET  …/requirements/?unsynced=1
  GET  …/requirements/<id>/file/     ← raw PDF bytes
  POST …/requirements/mark-synced/

Run on CRM host (or anywhere that can reach both sbis and CRM ingest):

  export SBIS_NORM_API_BASE_URL=http://146.19.125.77:8000
  # or via host proxy: http://127.0.0.1:18000
  export CRM_INGEST_BASE_URL=http://127.0.0.1:19001
  export ACCOUNTING_INGEST_TOKEN=...
  python3 scripts/sbis_norm_host_pull.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from typing import Any


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _request_json(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> Any:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _request_bytes(url: str, *, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _is_pdf(name: object) -> bool:
    return str(name or "").strip().lower().endswith(".pdf")


def main() -> int:
    sbis = _env("SBIS_NORM_API_BASE_URL", "http://146.19.125.77:8000").rstrip("/")
    crm = _env("CRM_INGEST_BASE_URL", "http://127.0.0.1:19001").rstrip("/")
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
                inn = str(item.get("inn") or "").strip()
                title = str(item.get("doc_title") or "Требование ФНС").strip() or "Требование ФНС"
                payload = {
                    "external_id": f"sbis-req:{sbis_id}",
                    "supplier_inn": inn,
                    "title": title,
                    "status": "new",
                    "pdf_base64": base64.b64encode(raw).decode("ascii"),
                    "pdf_filename": filename,
                    "metadata": {
                        "source": "sbis-norm-host-pull",
                        "sbis_id": sbis_id,
                        "sbis_doc_id": item.get("sbis_doc_id"),
                        "content_sha256": item.get("content_sha256"),
                        "document_date": item.get("document_date"),
                        "storage_file_name": filename,
                        "file_url": item.get("file_url"),
                    },
                }
                ingest = _request_json(
                    "POST",
                    f"{crm}/api/v1/accounting/requirements/ingest",
                    data=json.dumps(payload).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "X-Accounting-Ingest-Token": token,
                    },
                    timeout=120,
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


if __name__ == "__main__":
    raise SystemExit(main())
