"""Pull FNS requirements from sbis-norm into CRM accounting cabinet.

Flow (sbis-norm API v2 — binary file endpoint):
  1. GET /api/sbis/requirements/?unsynced=1
  2. Keep only storage_file_name ending with .pdf (.p7m → mark-synced, skip)
  3. GET /api/sbis/requirements/{id}/file/  → raw PDF bytes
  4. AccountingService.ingest_requirement (idempotent by external_id)
  5. POST /api/sbis/requirements/mark-synced/ after successful save

Do not use detail?include_file=1 / file_b64.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting import sbis_norm_client
from app.modules.accounting.schemas import AccountingRequirementIngestRequest
from app.modules.accounting.service import AccountingService
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

EXTERNAL_ID_PREFIX = "sbis-req:"


@dataclass
class SbisNormSyncResult:
    fetched: int = 0
    created: int = 0
    existing: int = 0
    failed: int = 0
    marked_synced: int = 0
    skipped_non_pdf: int = 0
    errors: list[str] = field(default_factory=list)


def external_id_for_sbis(sbis_id: int) -> str:
    return f"{EXTERNAL_ID_PREFIX}{sbis_id}"


def _is_pdf_filename(name: object) -> bool:
    return str(name or "").strip().lower().endswith(".pdf")


def _parse_received_at(raw: object, document_date: object) -> datetime | None:
    """Return naive UTC datetime for TIMESTAMP WITHOUT TIME ZONE columns."""
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(UTC).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    if isinstance(document_date, str) and document_date.strip():
        try:
            d = date.fromisoformat(document_date.strip())
            return datetime(d.year, d.month, d.day)
        except ValueError:
            pass
    return None


def _guess_mime(filename: str | None, raw: bytes) -> str:
    name = (filename or "").lower()
    if raw.startswith(b"%PDF") or name.endswith(".pdf"):
        return "application/pdf"
    if raw.startswith(b"PK") or name.endswith(".zip"):
        return "application/zip"
    stripped = raw.lstrip()
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<") or name.endswith(".xml"):
        return "application/xml"
    return "application/octet-stream"


def map_meta_to_ingest(
    meta: dict[str, Any],
    *,
    pdf_bytes: bytes,
) -> AccountingRequirementIngestRequest:
    sbis_id = int(meta["id"])
    inn = str(meta.get("inn") or "").strip()
    title = str(meta.get("doc_title") or "Требование ФНС").strip() or "Требование ФНС"
    filename = str(meta.get("storage_file_name") or f"requirement_{sbis_id}.pdf").strip()
    metadata: dict[str, Any] = {
        "source": "sbis-norm",
        "sbis_id": sbis_id,
        "sbis_doc_id": meta.get("sbis_doc_id"),
        "sbis_stage_id": meta.get("sbis_stage_id"),
        "content_sha256": meta.get("content_sha256"),
        "document_date": meta.get("document_date"),
        "file_size": meta.get("file_size"),
        "storage_file_name": filename,
        "file_url": meta.get("file_url"),
        "mime_type": _guess_mime(filename, pdf_bytes),
    }
    return AccountingRequirementIngestRequest(
        external_id=external_id_for_sbis(sbis_id),
        supplier_inn=inn,
        title=title,
        description=None,
        status="new",
        received_at=_parse_received_at(meta.get("created_at"), meta.get("document_date")),
        metadata=metadata,
        pdf_base64=None,
        pdf_filename=filename,
    )


async def _ingest_pdf(
    service: AccountingService,
    meta: dict[str, Any],
) -> tuple[bool, int]:
    """Download binary PDF and ingest. Returns (created, sbis_id)."""
    sbis_id = int(meta["id"])
    raw = await sbis_norm_client.get_requirement_file(sbis_id)
    if not raw.startswith(b"%PDF") and not _is_pdf_filename(meta.get("storage_file_name")):
        raise ValueError("downloaded body is not a PDF")
    body = map_meta_to_ingest(meta, pdf_bytes=raw)
    if not body.supplier_inn:
        raise ValueError("empty inn")
    ingested = await service.ingest_requirement(
        body,
        pdf_bytes=raw,
        pdf_filename=body.pdf_filename,
    )
    return ingested.created, sbis_id


async def sync_requirement_by_id(
    session: AsyncSession,
    sbis_id: int,
    *,
    mark: bool = True,
) -> SbisNormSyncResult:
    result = SbisNormSyncResult(fetched=1)
    service = AccountingService(session)
    try:
        detail = await sbis_norm_client.get_requirement(sbis_id)
        filename = detail.get("storage_file_name")
        if not _is_pdf_filename(filename):
            result.skipped_non_pdf = 1
            if mark:
                await sbis_norm_client.mark_synced([sbis_id])
                result.marked_synced = 1
            return result
        created, _ = await _ingest_pdf(service, detail)
        if created:
            result.created = 1
        else:
            result.existing = 1
        if mark:
            await sbis_norm_client.mark_synced([sbis_id])
            result.marked_synced = 1
    except Exception as exc:
        result.failed = 1
        result.errors.append(f"id={sbis_id}: {exc}")
        logger.exception("sbis_norm_sync_item_failed", sbis_id=sbis_id)
    return result


async def sync_unsynced_requirements(
    session: AsyncSession,
    *,
    limit: int | None = None,
    max_pages: int = 50,
) -> SbisNormSyncResult:
    settings = get_settings()
    if not settings.sbis_norm_api_base_url.strip():
        logger.info("sbis_norm_sync_skipped_no_base_url")
        return SbisNormSyncResult()

    batch_limit = limit or settings.sbis_norm_sync_batch_limit
    batch_limit = max(1, min(batch_limit, 500))
    aggregate = SbisNormSyncResult()
    service = AccountingService(session)

    for _page in range(max_pages):
        listing = await sbis_norm_client.list_requirements(unsynced=True, limit=batch_limit)
        rows = listing.get("results") or []
        if not isinstance(rows, list) or not rows:
            break

        ok_ids: list[int] = []
        skip_ids: list[int] = []
        for item in rows:
            if not isinstance(item, dict) or item.get("id") is None:
                aggregate.failed += 1
                aggregate.errors.append("list item without id")
                continue
            sbis_id = int(item["id"])
            aggregate.fetched += 1

            if not _is_pdf_filename(item.get("storage_file_name")):
                aggregate.skipped_non_pdf += 1
                skip_ids.append(sbis_id)
                continue

            try:
                created, _ = await _ingest_pdf(service, item)
                if created:
                    aggregate.created += 1
                else:
                    aggregate.existing += 1
                ok_ids.append(sbis_id)
            except Exception as exc:
                await session.rollback()
                aggregate.failed += 1
                aggregate.errors.append(f"id={sbis_id}: {exc}")
                logger.exception("sbis_norm_sync_item_failed", sbis_id=sbis_id)
                service = AccountingService(session)

        mark_ids = ok_ids + skip_ids
        if mark_ids:
            try:
                marked = await sbis_norm_client.mark_synced(mark_ids)
                aggregate.marked_synced += int(marked.get("updated") or len(mark_ids))
            except Exception as exc:
                aggregate.errors.append(f"mark-synced failed: {exc}")
                logger.exception("sbis_norm_mark_synced_failed", ids=mark_ids)

        if len(rows) < batch_limit:
            break

    logger.info(
        "sbis_norm_sync_done",
        fetched=aggregate.fetched,
        created=aggregate.created,
        existing=aggregate.existing,
        failed=aggregate.failed,
        skipped_non_pdf=aggregate.skipped_non_pdf,
        marked_synced=aggregate.marked_synced,
    )
    return aggregate
