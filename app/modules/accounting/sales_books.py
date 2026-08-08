"""Short SBIS sales-book extracts: ingest, ACL pairs, storage/order helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.opt_sales_book_extract import OptSalesBookExtract
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids
from app.shared.exceptions import NotFound, ValidationError

_FILENAME_SAFE = re.compile(r"[^\w\-+.() ]+", re.UNICODE)
_INN_RE = re.compile(r"^\d{10}(\d{2})?$")


def sales_book_external_id(*, content_sha256: str) -> str:
    return f"sbis-sb:{content_sha256[:40]}"


def _safe_name(value: str) -> str:
    cleaned = _FILENAME_SAFE.sub("_", value).strip() or "file"
    return cleaned[:120]


def normalize_inn(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value).strip())
    if not digits or not _INN_RE.match(digits):
        return None
    return digits


def is_full_book_filename(filename: str) -> bool:
    name = filename.strip().replace("\\", "/").split("/")[-1].casefold()
    return name == "_full.pdf" or name.endswith("_full.pdf")


class OptSalesBookExtractRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: str) -> OptSalesBookExtract | None:
        result = await self._session.execute(
            select(OptSalesBookExtract).where(
                OptSalesBookExtract.external_id == external_id,
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_seller_buyer_source(
        self,
        *,
        seller_inn: str,
        buyer_inn: str,
        source_path: str | None,
    ) -> OptSalesBookExtract | None:
        """Stable business key for re-import after PDF regeneration.

        Content hash in external_id changes when extracts are rebuilt from
        _full.pdf — lookup by seller×buyer×source_path (then seller×buyer).
        """
        path = (source_path or "").strip().replace("\\", "/") or None
        if path:
            result = await self._session.execute(
                select(OptSalesBookExtract)
                .where(
                    OptSalesBookExtract.seller_inn == seller_inn,
                    OptSalesBookExtract.buyer_inn == buyer_inn,
                    OptSalesBookExtract.source_path == path,
                )
                .order_by(OptSalesBookExtract.id.asc())
                .limit(1),
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return row
            # Older rows may store only the filename, or an absolute path ending.
            filename = path.rsplit("/", 1)[-1]
            result = await self._session.execute(
                select(OptSalesBookExtract)
                .where(
                    OptSalesBookExtract.seller_inn == seller_inn,
                    OptSalesBookExtract.buyer_inn == buyer_inn,
                    or_(
                        OptSalesBookExtract.source_path == filename,
                        OptSalesBookExtract.source_path.endswith(f"/{filename}"),
                        OptSalesBookExtract.source_filename == filename,
                    ),
                )
                .order_by(OptSalesBookExtract.id.asc())
                .limit(1),
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return row

        result = await self._session.execute(
            select(OptSalesBookExtract)
            .where(
                OptSalesBookExtract.seller_inn == seller_inn,
                OptSalesBookExtract.buyer_inn == buyer_inn,
            )
            .order_by(OptSalesBookExtract.id.asc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def get(self, extract_id: int) -> OptSalesBookExtract | None:
        result = await self._session.execute(
            select(OptSalesBookExtract).where(OptSalesBookExtract.id == extract_id),
        )
        return result.scalar_one_or_none()

    async def add(self, row: OptSalesBookExtract) -> OptSalesBookExtract:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_for_pairs(
        self,
        pairs: set[tuple[str, str]],
    ) -> list[OptSalesBookExtract]:
        if not pairs:
            return []
        sellers = {s for s, _ in pairs}
        buyers = {b for _, b in pairs}
        result = await self._session.execute(
            select(OptSalesBookExtract)
            .where(
                OptSalesBookExtract.seller_inn.in_(sellers),
                OptSalesBookExtract.buyer_inn.in_(buyers),
                OptSalesBookExtract.pdf_file_id.is_not(None),
            )
            .order_by(
                OptSalesBookExtract.seller_inn,
                OptSalesBookExtract.buyer_inn,
                OptSalesBookExtract.id,
            ),
        )
        rows = list(result.scalars().all())
        wanted = pairs
        return [r for r in rows if (r.seller_inn, r.buyer_inn) in wanted]


async def ingest_sales_book_pdf(
    session: AsyncSession,
    *,
    external_id: str,
    pdf_bytes: bytes,
    source_filename: str,
    seller_inn: str | None = None,
    buyer_inn: str | None = None,
    seller_name: str | None = None,
    buyer_name: str | None = None,
    source_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[OptSalesBookExtract, bool]:
    if is_full_book_filename(source_filename) or (
        source_path and is_full_book_filename(source_path)
    ):
        raise ValidationError(message="Полные книги (_full.pdf) не принимаются")

    seller = normalize_inn(seller_inn)
    buyer = normalize_inn(buyer_inn)
    # Infer from path sales_books/<seller>/<buyer>.pdf
    path = (source_path or source_filename or "").replace("\\", "/")
    parts = [p for p in path.split("/") if p]
    if seller is None and len(parts) >= 2:
        seller = normalize_inn(parts[-2])
    if buyer is None and parts:
        stem = parts[-1]
        if stem.casefold().endswith(".pdf"):
            stem = stem[:-4]
        buyer = normalize_inn(stem)
    if seller is None or buyer is None:
        raise ValidationError(message="Не удалось определить ИНН продавца/покупателя")

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValidationError(message="Файл не является PDF")

    repo = OptSalesBookExtractRepository(session)
    path_norm = (source_path or "").strip().replace("\\", "/") or None
    existing = await repo.get_by_seller_buyer_source(
        seller_inn=seller,
        buyer_inn=buyer,
        source_path=path_norm,
    )
    if existing is None:
        existing = await repo.get_by_external_id(external_id.strip())

    files = FilesService(session)
    uploaded = await files.create_upload(
        uploaded_by=None,
        data=pdf_bytes,
        original_name=source_filename.strip() or f"{buyer}.pdf",
        mime_type="application/pdf",
    )
    received_at = datetime.now(UTC).replace(tzinfo=None)
    meta = dict(metadata or {})
    meta.setdefault("content_sha256", hashlib.sha256(pdf_bytes).hexdigest())
    new_external_id = external_id.strip()

    if existing is not None:
        # Refresh content-hash id when free (regenerated PDF has a new SHA).
        if existing.external_id != new_external_id:
            conflict = await repo.get_by_external_id(new_external_id)
            if conflict is None or conflict.id == existing.id:
                existing.external_id = new_external_id
        existing.seller_inn = seller
        existing.buyer_inn = buyer
        if seller_name:
            existing.seller_name = seller_name.strip() or existing.seller_name
        if buyer_name:
            existing.buyer_name = buyer_name.strip() or existing.buyer_name
        if path_norm:
            existing.source_path = path_norm
        existing.source_filename = source_filename.strip() or existing.source_filename
        existing.pdf_file_id = uploaded.id
        existing.metadata_json = {**(existing.metadata_json or {}), **meta}
        existing.received_at = received_at
        existing.updated_at = received_at
        await session.flush()
        await session.refresh(existing)
        return existing, False

    row = OptSalesBookExtract(
        external_id=new_external_id,
        seller_inn=seller,
        buyer_inn=buyer,
        seller_name=(seller_name or "").strip() or None,
        buyer_name=(buyer_name or "").strip() or None,
        source_path=path_norm,
        source_filename=source_filename.strip() or f"{buyer}.pdf",
        pdf_file_id=uploaded.id,
        metadata_json=meta,
        received_at=received_at,
    )
    created = await repo.add(row)
    return created, True


async def visible_sales_book_pairs(
    session: AsyncSession,
    actor: User,
    ctx: ScopeContext,
) -> set[tuple[str, str]] | None:
    """None = unrestricted (admin/chief). Empty set = none. Else allowed (seller, buyer)."""
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
    if role in {UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT}:
        return None

    seller_filter: set[str] | None = None
    if role == UserRole.ACCOUNTANT:
        from app.modules.db.models.opt_accountant_unit_assignment import (
            OptAccountantUnitAssignment,
        )

        result = await session.execute(
            select(OptUnit.inn)
            .join(
                OptAccountantUnitAssignment,
                OptAccountantUnitAssignment.unit_id == OptUnit.id,
            )
            .where(OptAccountantUnitAssignment.user_id == actor.id),
        )
        seller_filter = {str(inn) for inn in result.scalars().all() if inn}
        if not seller_filter:
            return set()

    groups = visible_group_ids(ctx)
    gids: set[int] | None
    if role == UserRole.ACCOUNTANT:
        # Accountants are scoped by assigned lavkas, not chat groups.
        gids = None
    elif groups == SCOPE_ALL:
        return None
    elif isinstance(groups, set) and groups:
        gids = set(groups)
        if role == UserRole.SENIOR and actor.department_id is not None:
            dept_groups = await session.execute(
                select(Group.id).where(Group.department_id == actor.department_id),
            )
            gids = {int(g) for g in dept_groups.scalars().all()} or gids
    else:
        return set()

    stmt = (
        select(LeadOptOrderLine.supplier_inn, LeadOptOrder.buyer_inn)
        .join(LeadOptOrder, LeadOptOrder.id == LeadOptOrderLine.order_id)
        .join(Lead, Lead.id == LeadOptOrder.lead_id)
        .where(
            LeadOptOrder.deleted_at.is_(None),
            LeadOptOrderLine.supplier_inn.is_not(None),
            LeadOptOrder.buyer_inn.is_not(None),
        )
    )
    if gids is not None:
        stmt = stmt.where(Lead.group_id.in_(gids))
    result = await session.execute(stmt)
    pairs: set[tuple[str, str]] = set()
    for seller_raw, buyer_raw in result.all():
        seller = normalize_inn(str(seller_raw) if seller_raw else None)
        buyer = normalize_inn(str(buyer_raw) if buyer_raw else None)
        if not seller or not buyer:
            continue
        if seller_filter is not None and seller not in seller_filter:
            continue
        pairs.add((seller, buyer))
    return pairs


async def order_sales_book_pairs(order: LeadOptOrder) -> set[tuple[str, str]]:
    buyer = normalize_inn(order.buyer_inn)
    if not buyer:
        return set()
    pairs: set[tuple[str, str]] = set()
    for line in order.lines or []:
        seller = normalize_inn(line.supplier_inn)
        if seller:
            pairs.add((seller, buyer))
    return pairs


async def pairs_for_period_orders(
    session: AsyncSession,
    *,
    period_code: str,
    visible_pairs: set[tuple[str, str]] | None,
    visible_group_ids_set: set[int] | None,
) -> set[tuple[str, str]]:
    """Pairs from non-deleted orders in period, intersected with ACL pairs."""
    period = (period_code or "").strip()
    if not period:
        return set()
    stmt = (
        select(LeadOptOrderLine.supplier_inn, LeadOptOrder.buyer_inn)
        .join(LeadOptOrder, LeadOptOrder.id == LeadOptOrderLine.order_id)
        .join(Lead, Lead.id == LeadOptOrder.lead_id)
        .where(
            LeadOptOrder.deleted_at.is_(None),
            LeadOptOrder.period_code == period,
            LeadOptOrderLine.supplier_inn.is_not(None),
            LeadOptOrder.buyer_inn.is_not(None),
        )
    )
    if visible_group_ids_set is not None:
        stmt = stmt.where(Lead.group_id.in_(visible_group_ids_set))
    result = await session.execute(stmt)
    pairs: set[tuple[str, str]] = set()
    for seller_raw, buyer_raw in result.all():
        seller = normalize_inn(str(seller_raw) if seller_raw else None)
        buyer = normalize_inn(str(buyer_raw) if buyer_raw else None)
        if not seller or not buyer:
            continue
        pair = (seller, buyer)
        if visible_pairs is not None and pair not in visible_pairs:
            continue
        pairs.add(pair)
    return pairs


async def load_sales_book_pdf_bytes(
    session: AsyncSession,
    row: OptSalesBookExtract,
) -> bytes:
    if row.pdf_file_id is None:
        raise NotFound(message="PDF книги продаж не найден")
    files = FilesService(session)
    content, _mime, _name = await files.get_bytes(row.pdf_file_id)
    return content


def sales_book_download_name(row: OptSalesBookExtract) -> str:
    seller = _safe_name(row.seller_name or row.seller_inn)
    buyer = _safe_name(row.buyer_name or row.buyer_inn)
    return f"книга-продаж-{seller}-{buyer}.pdf"


def build_sales_books_zip(
    rows: list[tuple[OptSalesBookExtract, bytes]],
) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        used: set[str] = set()
        for row, raw in rows:
            name = sales_book_download_name(row)
            if name in used:
                stem = name[:-4] if name.lower().endswith(".pdf") else name
                name = f"{stem}-{row.id}.pdf"
            used.add(name)
            zf.writestr(name, raw)
    return buf.getvalue()
