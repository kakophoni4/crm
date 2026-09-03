from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Select, and_, func, or_, select, update
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
        mark: str | None = None,
        favorite_only: bool = False,
    ) -> Select[tuple[LavokParserLot]]:
        stmt = select(LavokParserLot)
        if sheet_date is not None:
            stmt = stmt.where(LavokParserLot.sheet_date == sheet_date)
        if not include_deleted:
            stmt = stmt.where(LavokParserLot.is_deleted.is_(False))
        if favorite_only:
            stmt = stmt.where(LavokParserLot.is_favorite.is_(True))
        if mark:
            stmt = stmt.where(LavokParserLot.mark == mark)
        needle = (q or "").strip()
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    LavokParserLot.inn.ilike(like),
                    LavokParserLot.name.ilike(like),
                ),
            )
        if needle and sheet_date is None:
            return stmt.order_by(
                LavokParserLot.sheet_date.desc(),
                LavokParserLot.score.desc().nullslast(),
                LavokParserLot.id.asc(),
            )
        return stmt.order_by(LavokParserLot.score.desc().nullslast(), LavokParserLot.id.asc())

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
    ) -> tuple[list[LavokParserLot], int]:
        filtered = self._filtered_query(
            sheet_date=sheet_date,
            q=q,
            include_deleted=include_deleted,
            mark=mark,
            favorite_only=favorite_only,
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
        prev_flags = await self._latest_flags_by_inn(inns)
        created = 0
        updated = 0
        now = datetime.now(UTC)
        for row in parsed:
            existing = by_key.get((row.inn, row.sheet_date))
            if existing is None:
                prev_mark, prev_fav = prev_flags.get(row.inn, ("new", False))
                lot = LavokParserLot(
                    inn=row.inn,
                    sheet_date=row.sheet_date,
                    mark=prev_mark,
                    is_favorite=prev_fav,
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

    async def _latest_flags_by_inn(self, inns: set[str]) -> dict[str, tuple[str, bool]]:
        if not inns:
            return {}
        result = await self._session.execute(
            select(LavokParserLot)
            .where(
                LavokParserLot.inn.in_(inns),
                LavokParserLot.is_deleted.is_(False),
            )
            .order_by(LavokParserLot.inn, LavokParserLot.sheet_date.desc()),
        )
        out: dict[str, tuple[str, bool]] = {}
        for row in result.scalars().all():
            if row.inn not in out:
                out[row.inn] = (row.mark or "new", bool(row.is_favorite))
        return out

    async def apply_inn_flags(
        self,
        inn: str,
        *,
        mark: str | None = None,
        is_favorite: bool | None = None,
    ) -> None:
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if mark is not None:
            values["mark"] = mark
        if is_favorite is not None:
            values["is_favorite"] = is_favorite
        if len(values) == 1:
            return
        await self._session.execute(
            update(LavokParserLot)
            .where(
                LavokParserLot.inn == inn,
                LavokParserLot.is_deleted.is_(False),
            )
            .values(**values),
        )

    async def list_latest_favorites(
        self,
        *,
        q: str | None,
        mark: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[LavokParserLot], int]:
        latest = (
            select(
                LavokParserLot.inn.label("inn"),
                func.max(LavokParserLot.sheet_date).label("sheet_date"),
            )
            .where(
                LavokParserLot.is_favorite.is_(True),
                LavokParserLot.is_deleted.is_(False),
            )
            .group_by(LavokParserLot.inn)
            .subquery()
        )
        stmt = (
            select(LavokParserLot)
            .join(
                latest,
                and_(
                    LavokParserLot.inn == latest.c.inn,
                    LavokParserLot.sheet_date == latest.c.sheet_date,
                ),
            )
            .where(LavokParserLot.is_deleted.is_(False))
        )
        if mark:
            stmt = stmt.where(LavokParserLot.mark == mark)
        needle = (q or "").strip()
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    LavokParserLot.inn.ilike(like),
                    LavokParserLot.name.ilike(like),
                ),
            )
        stmt = stmt.order_by(LavokParserLot.score.desc().nullslast(), LavokParserLot.id.asc())
        total = int(
            (await self._session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one(),
        )
        rows = list((await self._session.execute(stmt.limit(limit).offset(offset))).scalars().all())
        return rows, total
