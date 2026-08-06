"""SBIS KV/IV receipts: repository helpers, ingest, ACL tree, order binding."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.opt_receipt import OptReceipt
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.leads.opt.periods import normalize_period_code
from app.modules.leads.opt.receipt_pdf import (
    normalize_receipt_filename,
    parse_receipt_pdf,
    short_name_from_filename,
)
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids
from app.shared.exceptions import NotFound, ValidationError

_FILENAME_SAFE = re.compile(r"[^\w\-+.() ]+", re.UNICODE)


def receipt_external_id(*, source_path: str, content_sha256: str | None = None) -> str:
    """Stable id: prefer content hash, else path hash."""
    if content_sha256:
        return f"sbis-kv:{content_sha256[:40]}"
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:40]
    return f"sbis-kv-path:{digest}"


def _safe_name(value: str) -> str:
    cleaned = _FILENAME_SAFE.sub("_", value).strip() or "file"
    return cleaned[:120]


class OptReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: str) -> OptReceipt | None:
        result = await self._session.execute(
            select(OptReceipt).where(OptReceipt.external_id == external_id),
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, receipt_id: int) -> OptReceipt | None:
        result = await self._session.execute(
            select(OptReceipt).where(OptReceipt.id == receipt_id),
        )
        return result.scalar_one_or_none()

    async def add(self, row: OptReceipt) -> OptReceipt:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_for_inns_period(
        self,
        *,
        inns: set[str],
        period_code: str | None,
        include_corrections: bool = False,
    ) -> list[OptReceipt]:
        if not inns:
            return []
        stmt = select(OptReceipt).where(OptReceipt.supplier_inn.in_(sorted(inns)))
        if period_code:
            stmt = stmt.where(OptReceipt.period_code == period_code)
        if not include_corrections:
            stmt = stmt.where(OptReceipt.is_correction.is_(False))
        stmt = stmt.order_by(
            OptReceipt.supplier_inn,
            OptReceipt.is_correction,
            OptReceipt.doc_kind,
            OptReceipt.id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        supplier_inns: set[str] | None,
        period_code: str | None = None,
    ) -> list[OptReceipt]:
        stmt: Select[tuple[OptReceipt]] = select(OptReceipt)
        if supplier_inns is not None:
            if not supplier_inns:
                return []
            stmt = stmt.where(OptReceipt.supplier_inn.in_(sorted(supplier_inns)))
        if period_code:
            stmt = stmt.where(OptReceipt.period_code == period_code)
        stmt = stmt.order_by(
            OptReceipt.period_code.desc(),
            OptReceipt.supplier_inn,
            OptReceipt.is_correction,
            OptReceipt.doc_kind,
            OptReceipt.id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_unit_by_short_name(self, short_name: str) -> OptUnit | None:
        needle = short_name.strip()
        if not needle:
            return None
        result = await self._session.execute(
            select(OptUnit).where(func.lower(OptUnit.name).like(f"%{needle.casefold()}%")),
        )
        rows = list(result.scalars().all())
        if len(rows) == 1:
            return rows[0]
        # Prefer active exact-ish match
        for row in rows:
            if needle.casefold() in (row.name or "").casefold():
                return row
        return rows[0] if rows else None


async def ingest_receipt_pdf(
    session: AsyncSession,
    *,
    external_id: str,
    pdf_bytes: bytes,
    source_filename: str,
    supplier_inn: str | None = None,
    supplier_kpp: str | None = None,
    supplier_name: str | None = None,
    period_code: str | None = None,
    doc_kind: str | None = None,
    metadata: dict[str, Any] | None = None,
    replace_existing: bool = True,
) -> tuple[OptReceipt, bool]:
    repo = OptReceiptRepository(session)
    existing = await repo.get_by_external_id(external_id.strip())
    source_filename = normalize_receipt_filename(source_filename)

    parsed = parse_receipt_pdf(pdf_bytes, filename=source_filename)
    inn = (supplier_inn or parsed.supplier_inn or "").strip()
    if not inn:
        unit = None
        short = parsed.parsed_name or short_name_from_filename(source_filename)
        if short:
            unit = await repo.resolve_unit_by_short_name(short)
            if unit:
                inn = unit.inn
        if not inn:
            raise ValidationError(
                message="Не удалось определить ИНН из PDF — укажите supplier_inn",
                details={"filename": source_filename},
            )

    period = normalize_period_code(period_code or parsed.period_code)
    if not period:
        raise ValidationError(
            message="Не удалось определить период из PDF — укажите period_code (например 2/26)",
            details={"filename": source_filename},
        )

    kind = (doc_kind or parsed.doc_kind or "receipt").strip().lower()
    if kind not in {"receipt", "notice"}:
        kind = "receipt"
    is_correction = bool(parsed.is_correction)
    if isinstance(metadata, dict) and "is_correction" in metadata:
        is_correction = bool(metadata.get("is_correction"))

    unit = await session.execute(select(OptUnit).where(OptUnit.inn == inn))
    unit_row = unit.scalar_one_or_none()
    kpp = supplier_kpp or parsed.supplier_kpp or (unit_row.kpp if unit_row else None)
    name = (
        supplier_name
        or parsed.supplier_name
        or (unit_row.name if unit_row else None)
        or parsed.parsed_name
    )

    files = FilesService(session)
    uploaded = await files.create_upload(
        uploaded_by=None,
        data=pdf_bytes,
        original_name=source_filename,
        mime_type="application/pdf" if pdf_bytes.startswith(b"%PDF") else "application/octet-stream",
    )

    received_at = datetime.now(UTC).replace(tzinfo=None)
    meta = dict(metadata or {})
    meta.setdefault("parsed", {
        "inn": parsed.supplier_inn,
        "kpp": parsed.supplier_kpp,
        "period_code": parsed.period_code,
        "doc_kind": parsed.doc_kind,
        "short_name": parsed.parsed_name,
        "is_correction": is_correction,
    })

    if existing is not None:
        if not replace_existing:
            return existing, False
        existing.supplier_inn = inn
        existing.supplier_kpp = kpp
        existing.supplier_name = name
        existing.period_code = period
        existing.doc_kind = kind
        existing.is_correction = is_correction
        existing.source_filename = source_filename
        existing.parsed_name = parsed.parsed_name
        existing.pdf_file_id = uploaded.id
        existing.metadata_json = meta
        existing.updated_at = received_at
        await session.flush()
        await session.refresh(existing)
        return existing, False

    row = OptReceipt(
        external_id=external_id.strip(),
        supplier_inn=inn,
        supplier_kpp=kpp,
        supplier_name=name,
        period_code=period,
        doc_kind=kind,
        is_correction=is_correction,
        source_filename=source_filename,
        parsed_name=parsed.parsed_name,
        pdf_file_id=uploaded.id,
        metadata_json=meta,
        received_at=received_at,
    )
    created = await repo.add(row)
    return created, True


async def visible_receipt_supplier_inns(
    session: AsyncSession,
    actor: User,
    ctx: ScopeContext,
) -> set[str] | None:
    """None = all inns. Empty set = none."""
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
    if role in {UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT}:
        return None

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
        return {str(inn) for inn in result.scalars().all() if inn}

    groups = visible_group_ids(ctx)
    if groups == SCOPE_ALL:
        return None
    if not isinstance(groups, set) or not groups:
        return set()

    gids = set(groups)
    if role == UserRole.SENIOR and actor.department_id is not None:
        dept_groups = await session.execute(
            select(Group.id).where(Group.department_id == actor.department_id),
        )
        gids = {int(g) for g in dept_groups.scalars().all()} or gids

    if not gids:
        return set()

    stmt = (
        select(LeadOptOrderLine.supplier_inn)
        .join(LeadOptOrder, LeadOptOrder.id == LeadOptOrderLine.order_id)
        .join(Lead, Lead.id == LeadOptOrder.lead_id)
        .where(
            Lead.group_id.in_(sorted(gids)),
            LeadOptOrder.deleted_at.is_(None),
        )
        .distinct()
    )
    result = await session.execute(stmt)
    return {str(inn) for inn in result.scalars().all() if inn}


def build_receipts_zip(rows: list[tuple[OptReceipt, bytes]]) -> bytes:
    buf = BytesIO()
    used_names: set[str] = set()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        for receipt, content in rows:
            base = receipt.source_filename or f"{receipt.doc_kind}_{receipt.supplier_inn}.pdf"
            name = _safe_name(base)
            if name in used_names:
                stem = name[:-4] if name.lower().endswith(".pdf") else name
                name = f"{stem}_{receipt.id}.pdf"
            used_names.add(name)
            zf.writestr(name, content)
    return buf.getvalue()


async def load_receipt_pdf_bytes(session: AsyncSession, receipt: OptReceipt) -> bytes:
    if receipt.pdf_file_id is None:
        raise NotFound(message="PDF квитанции не найден")
    files = FilesService(session)
    content, _mime, _name = await files.get_bytes(receipt.pdf_file_id)
    return content
