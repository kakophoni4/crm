#!/usr/bin/env python3
"""Pull FNS requirements from sbis-norm on the HOST network (not Docker).

Docker→sbis often stalls on large PDF bodies (file_b64). Run this on the CRM host:

  export SBIS_NORM_API_BASE_URL=http://127.0.0.1:18000   # socat proxy, or direct :8000
  export CRM_INGEST_BASE_URL=http://127.0.0.1:19001      # crm-staging-api published port
  export ACCOUNTING_INGEST_TOKEN=...                      # from deploy/.env.staging
  python3 scripts/sbis_norm_host_pull.py

Only .pdf are ingested; .p7m are mark-synced and skipped.
"""

from __future__ import annotations

import base64
import json
import os
import sys
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
    timeout: float = 180.0,
) -> Any:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _is_pdf(name: object) -> bool:
    return str(name or "").strip().lower().endswith(".pdf")


def main() -> int:
    sbis = _env("SBIS_NORM_API_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
    crm = _env("CRM_INGEST_BASE_URL", "http://127.0.0.1:19001").rstrip("/")
    token = _env("ACCOUNTING_INGEST_TOKEN")
    if not token:
        print("ACCOUNTING_INGEST_TOKEN is required", file=sys.stderr)
        return 2

    created = existing = skipped = failed = marked = 0
    max_pages = int(_env("SBIS_NORM_SYNC_MAX_PAGES", "500") or "500")

    for _page in range(max_pages):
        listing = _request(
            "GET",
            f"{sbis}/api/sbis/requirements/?unsynced=1&limit=1",
            timeout=60,
        )
        rows = (listing or {}).get("results") or []
        if not rows:
            break
        item = rows[0]
        sbis_id = int(item["id"])
        name = item.get("storage_file_name") or ""

        if not _is_pdf(name):
            _request(
                "POST",
                f"{sbis}/api/sbis/requirements/mark-synced/",
                data=json.dumps({"ids": [sbis_id]}).encode(),
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            skipped += 1
            marked += 1
            print(f"skip-non-pdf id={sbis_id} {name}")
            continue

        try:
            detail = _request(
                "GET",
                f"{sbis}/api/sbis/requirements/{sbis_id}/",
                timeout=180,
            )
            file_b64 = (detail or {}).get("file_b64") or ""
            if not file_b64:
                raise RuntimeError("empty file_b64")
            raw = base64.b64decode(file_b64)
            filename = str(detail.get("storage_file_name") or f"requirement_{sbis_id}.pdf")
            inn = str(detail.get("inn") or "").strip()
            title = str(detail.get("doc_title") or "Требование ФНС").strip() or "Требование ФНС"
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
                    "sbis_doc_id": detail.get("sbis_doc_id"),
                    "content_sha256": detail.get("content_sha256"),
                    "document_date": detail.get("document_date"),
                    "storage_file_name": filename,
                },
            }
            ingest = _request(
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
            _request(
                "POST",
                f"{sbis}/api/sbis/requirements/mark-synced/",
                data=json.dumps({"ids": [sbis_id]}).encode(),
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            marked += 1
            print(f"pdf ok id={sbis_id} inn={inn} bytes={len(raw)} created={ingest.get('created')}")
        except Exception as exc:
            failed += 1
            print(f"pdf FAIL id={sbis_id}: {exc}", file=sys.stderr)
            # do not mark-synced — retry next run
            break

    print(
        f"done created={created} existing={existing} skipped_non_pdf={skipped} "
        f"marked={marked} failed={failed}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
