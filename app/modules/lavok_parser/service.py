from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.lavok_parser.repository import LavokParserRepository
from app.modules.lavok_parser.schemas import (
    LavokParserIngestResponse,
    LavokParserListResponse,
    LavokParserLotOut,
    LavokParserLotPatchRequest,
)
from app.modules.lavok_parser.xlsx import parse_lavok_xlsx, parse_sheet_date
from app.shared.exceptions import NotFound, ValidationError

ALLOWED_MARKS = frozenset({"new", "watching", "taking", "skip"})


class LavokParserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LavokParserRepository(session)

    async def ingest(self, content: bytes) -> LavokParserIngestResponse:
        parsed = parse_lavok_xlsx(content)
        sheet_dates = {row.sheet_date for row in parsed}
        created, updated = await self._repo.upsert_parsed(parsed)
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
        limit: int,
        offset: int,
    ) -> LavokParserListResponse:
        dates = await self._repo.list_sheet_dates()
        effective = sheet_date or (dates[0] if dates else None)
        rows, total = await self._repo.list_lots(
            sheet_date=effective,
            q=q,
            include_deleted=include_deleted,
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
