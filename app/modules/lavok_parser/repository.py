from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.lavok_parser_lot import LavokParserLot
from app.modules.lavok_parser.xlsx import SNAPSHOT_FIELDS, ParsedLotRow


class LavokParserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_sheet_dates(self) -> list[date]:
        result = await self._session.execute(
            select(LavokParserLot.sheet_date)
            .where(LavokParserLot.is_deleted.is_(False))
            .distinct()
            .order_by(LavokParserLot.sheet_date.desc()),
        )
        return list(result.scalars().all())

    def _filtered_query(
        self,
        *,
        sheet_date: date | None,
        q: str | None,
        include_deleted: bool,
    ) -> Select[tuple[LavokParserLot]]:
        stmt = select(LavokParserLot)
        if sheet_date is not None:
            stmt = stmt.where(LavokParserLot.sheet_date == sheet_date)
        if not include_deleted:
            stmt = stmt.where(LavokParserLot.is_deleted.is_(False))
        needle = (q or "").strip()
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    LavokParserLot.inn.ilike(like),
                    LavokParserLot.name.ilike(like),
                ),
            )
        return stmt.order_by(LavokParserLot.score.desc().nullslast(), LavokParserLot.id.asc())

    async def list_lots(
        self,
        *,
        sheet_date: date | None,
        q: str | None,
        include_deleted: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[LavokParserLot], int]:
        filtered = self._filtered_query(
            sheet_date=sheet_date,
            q=q,
            include_deleted=include_deleted,
        )
        total = int(
            (await self._session.execute(select(func.count()).select_from(filtered.subquery()))).scalar_one(),
        )
        rows = list(
            (await self._session.execute(filtered.limit(limit).offset(offset))).scalars().all(),
        )
        return rows, total

    async def get_by_id(self, lot_id: int) -> LavokParserLot | None:
        return await self._session.get(LavokParserLot, lot_id)

    async def get_by_inn_date(self, inn: str, sheet_date: date) -> LavokParserLot | None:
        result = await self._session.execute(
            select(LavokParserLot).where(
                LavokParserLot.inn == inn,
                LavokParserLot.sheet_date == sheet_date,
            ),
        )
        return result.scalar_one_or_none()

    async def upsert_parsed(self, parsed: list[ParsedLotRow]) -> tuple[int, int]:
        inns = {row.inn for row in parsed}
        dates = {row.sheet_date for row in parsed}
        existing_rows = list(
            (
                await self._session.execute(
                    select(LavokParserLot).where(
                        LavokParserLot.inn.in_(inns),
                        LavokParserLot.sheet_date.in_(dates),
                    ),
                )
            ).scalars().all(),
        )
        by_key = {(row.inn, row.sheet_date): row for row in existing_rows}
        created = 0
        updated = 0
        now = datetime.now(UTC)
        for row in parsed:
            existing = by_key.get((row.inn, row.sheet_date))
            if existing is None:
                lot = LavokParserLot(
                    inn=row.inn,
                    sheet_date=row.sheet_date,
                    mark="new",
                    is_deleted=False,
                    created_at=now,
                    updated_at=now,
                )
                for field in SNAPSHOT_FIELDS:
                    setattr(lot, field, row.fields.get(field))
                self._session.add(lot)
                by_key[(row.inn, row.sheet_date)] = lot
                created += 1
                continue
            for field in SNAPSHOT_FIELDS:
                setattr(existing, field, row.fields.get(field))
            existing.updated_at = now
            updated += 1
        await self._session.flush()
        return created, updated
