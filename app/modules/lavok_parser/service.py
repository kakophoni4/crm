from __future__ import annotations

from datetime import UTC, date, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

from app.modules.lavok_parser.repository import LavokParserRepository
from app.modules.lavok_parser.schemas import (
    LavokParserIngestJsonItem,
    LavokParserIngestJsonRequest,
    LavokParserIngestResponse,
    LavokParserListResponse,
    LavokParserLotOut,
    LavokParserLotPatchRequest,
)
from app.modules.lavok_parser.xlsx import (
    SNAPSHOT_FIELDS,
    ParsedLotRow,
    parse_lavok_xlsx,
    parse_sheet_date,
    stringify_field,
)
from app.modules.leads.opt.contact_buyer import normalize_inn
from app.shared.exceptions import NotFound, ValidationError

ALLOWED_MARKS = frozenset({"new", "watching", "taking", "skip"})


def _parse_item_sheet_date(raw: str) -> date:
    text = (raw or "").strip()
    parsed = parse_sheet_date(text)
    if parsed is not None:
        return parsed
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(message=f"Некорректная дата листа: {raw}") from exc


def rows_from_json_items(items: list[LavokParserIngestJsonItem]) -> list[ParsedLotRow]:
    rows: list[ParsedLotRow] = []
    for item in items:
        inn = normalize_inn(item.inn)
        if not inn:
            raise ValidationError(message=f"Некорректный ИНН: {item.inn}")
        fields = {key: stringify_field(getattr(item, key)) for key in SNAPSHOT_FIELDS}
        rows.append(ParsedLotRow(inn=inn, sheet_date=_parse_item_sheet_date(item.sheet_date), fields=fields))
    if not rows:
        raise ValidationError(message="Нет строк для загрузки")
    return rows


class LavokParserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LavokParserRepository(session)

    async def ingest(self, content: bytes) -> LavokParserIngestResponse:
        return await self.ingest_rows(parse_lavok_xlsx(content))

    async def ingest_json(self, body: LavokParserIngestJsonRequest) -> LavokParserIngestResponse:
        return await self.ingest_rows(rows_from_json_items(body.items))

    async def ingest_rows(self, parsed: list[ParsedLotRow]) -> LavokParserIngestResponse:
        if not parsed:
            raise ValidationError(message="Нет строк для загрузки")
        sheet_dates = {row.sheet_date for row in parsed}
        created, updated = await self._repo.upsert_parsed(parsed)
        try:
            from app.modules.lawyer_registry.service import LawyerRegistryService

            alerts = await LawyerRegistryService(self._session).sync_from_parser(parsed)
            if alerts:
                logger.info("lawyer_registry_parser_alerts", alerts=alerts)
        except Exception:
            logger.warning("lawyer_registry_parser_sync_failed", exc_info=True)
        await self._session.commit()
        return LavokParserIngestResponse(
            sheets=len(sheet_dates),
            upserted=created + updated,
            created=created,
            updated=updated,
        )

    async def list_lots(
        self,
        *,
        sheet_date: date | None,
        q: str | None,
        include_deleted: bool,
        mark: str | None = None,
        favorite_only: bool = False,
        limit: int,
        offset: int,
    ) -> LavokParserListResponse:
        dates = await self._repo.list_sheet_dates()
        if favorite_only:
            rows, total = await self._repo.list_latest_favorites(
                q=q,
                mark=mark,
                limit=limit,
                offset=offset,
            )
            return LavokParserListResponse(
                items=[LavokParserLotOut.model_validate(row) for row in rows],
                total=total,
                sheet_dates=dates,
                sheet_date=None,
            )
        effective = sheet_date or (dates[0] if dates else None)
        query_date = None if (q or "").strip() else effective
        rows, total = await self._repo.list_lots(
            sheet_date=query_date,
            q=q,
            include_deleted=include_deleted,
            mark=mark,
            favorite_only=False,
            limit=limit,
            offset=offset,
        )
        return LavokParserListResponse(
            items=[LavokParserLotOut.model_validate(row) for row in rows],
            total=total,
            sheet_dates=dates,
            sheet_date=effective,
        )

    async def patch_lot(self, lot_id: int, body: LavokParserLotPatchRequest) -> LavokParserLotOut:
        lot = await self._repo.get_by_id(lot_id)
        if lot is None or lot.is_deleted:
            raise NotFound(message="Строка парсера не найдена")
        if body.mark is not None:
            mark = body.mark.strip()
            if mark not in ALLOWED_MARKS:
                raise ValidationError(message="Неизвестная отметка")
            lot.mark = mark
        if body.note is not None:
            note = body.note.strip()
            lot.note = note or None
        if body.is_favorite is not None:
            lot.is_favorite = body.is_favorite
            if body.is_favorite and body.mark is None and lot.mark == "skip":
                lot.mark = "new"
        await self._repo.apply_inn_flags(
            lot.inn,
            mark=lot.mark if body.mark is not None or body.is_favorite is not None else None,
            is_favorite=lot.is_favorite if body.is_favorite is not None else None,
        )
        lot.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(lot)
        return LavokParserLotOut.model_validate(lot)

    async def delete_lot(self, lot_id: int) -> None:
        lot = await self._repo.get_by_id(lot_id)
        if lot is None or lot.is_deleted:
            raise NotFound(message="Строка парсера не найдена")
        lot.is_deleted = True
        lot.updated_at = datetime.now(UTC)
        await self._session.commit()


def parse_query_sheet_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    parsed = parse_sheet_date(text)
    if parsed is not None:
        return parsed
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(message="Некорректная дата листа") from exc
