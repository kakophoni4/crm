from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.lawyer_director import (
    LawyerDirector,
    LawyerDirectorPayment,
    LawyerParserAlert,
    LawyerShop,
)


class LawyerRegistryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_director(self, director_id: int) -> LawyerDirector | None:
        return await self._session.get(LawyerDirector, director_id)

    async def get_director_by_key(self, name_key: str) -> LawyerDirector | None:
        for obj in (*self._session.new, *self._session.identity_map.values()):
            if isinstance(obj, LawyerDirector) and obj.name_key == name_key:
                return obj
        result = await self._session.execute(
            select(LawyerDirector).where(LawyerDirector.name_key == name_key),
        )
        return result.scalar_one_or_none()

    async def get_shop(self, shop_id: int) -> LawyerShop | None:
        return await self._session.get(LawyerShop, shop_id)

    async def get_shop_by_inn(self, inn: str) -> LawyerShop | None:
        result = await self._session.execute(select(LawyerShop).where(LawyerShop.inn == inn))
        return result.scalar_one_or_none()

    async def list_directors(self) -> list[LawyerDirector]:
        result = await self._session.execute(
            select(LawyerDirector).order_by(
                LawyerDirector.pinned_at.desc().nullslast(),
                LawyerDirector.full_name,
            ),
        )
        return list(result.scalars().all())

    async def list_shops(
        self,
        *,
        director_id: int | None = None,
        q: str | None = None,
        kind: str | None = None,
        company_status: str | None = None,
        unreliable: str | None = None,
        zsk: str | None = None,
        ecsp_status: str | None = None,
        manager: str | None = None,
        dirovod: str | None = None,
        pinned_only: bool = False,
    ) -> list[LawyerShop]:
        stmt = select(LawyerShop)
        if director_id is not None:
            stmt = stmt.where(LawyerShop.director_id == director_id)
        if kind:
            stmt = stmt.where(LawyerShop.kind == kind)
        if company_status:
            stmt = stmt.where(LawyerShop.company_status == company_status)
        if unreliable:
            stmt = stmt.where(LawyerShop.unreliable.ilike(f"%{unreliable}%"))
        if zsk:
            stmt = stmt.where(LawyerShop.zsk == zsk)
        if ecsp_status:
            stmt = stmt.where(LawyerShop.ecsp_status == ecsp_status)
        if manager:
            stmt = stmt.where(LawyerShop.manager.ilike(f"%{manager}%"))
        if pinned_only:
            stmt = stmt.where(LawyerShop.pinned_at.is_not(None))
        if dirovod:
            stmt = stmt.join(LawyerDirector, LawyerDirector.id == LawyerShop.director_id, isouter=True)
            stmt = stmt.where(LawyerDirector.dirovod.ilike(f"%{dirovod}%"))
        needle = (q or "").strip()
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    LawyerShop.inn.ilike(like),
                    LawyerShop.name.ilike(like),
                    LawyerShop.manager.ilike(like),
                    LawyerShop.banks.ilike(like),
                    LawyerShop.treatment_status.ilike(like),
                ),
            )
        stmt = stmt.order_by(LawyerShop.pinned_at.desc().nullslast(), LawyerShop.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_payments(self, director_id: int) -> list[LawyerDirectorPayment]:
        result = await self._session.execute(
            select(LawyerDirectorPayment)
            .where(LawyerDirectorPayment.director_id == director_id)
            .order_by(LawyerDirectorPayment.period_ym.desc(), LawyerDirectorPayment.id.desc()),
        )
        return list(result.scalars().all())

    async def last_paid_periods(self, director_ids: list[int]) -> dict[int, str]:
        if not director_ids:
            return {}
        result = await self._session.execute(
            select(
                LawyerDirectorPayment.director_id,
                func.max(LawyerDirectorPayment.period_ym),
            ).where(LawyerDirectorPayment.director_id.in_(director_ids))
            .group_by(LawyerDirectorPayment.director_id),
        )
        return {int(row[0]): str(row[1]) for row in result.all() if row[1]}

    async def shop_counts(self, director_ids: list[int]) -> dict[int, int]:
        if not director_ids:
            return {}
        result = await self._session.execute(
            select(LawyerShop.director_id, func.count(LawyerShop.id))
            .where(LawyerShop.director_id.in_(director_ids))
            .group_by(LawyerShop.director_id),
        )
        return {int(row[0]): int(row[1]) for row in result.all() if row[0] is not None}

    async def add(self, row: object) -> object:
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete_shop(self, shop: LawyerShop) -> None:
        await self._session.delete(shop)

    async def delete_director(self, director: LawyerDirector) -> None:
        await self._session.delete(director)

    async def delete_payment(self, payment: LawyerDirectorPayment) -> None:
        await self._session.delete(payment)

    async def get_payment(self, payment_id: int) -> LawyerDirectorPayment | None:
        return await self._session.get(LawyerDirectorPayment, payment_id)

    async def find_payment(
        self,
        director_id: int,
        shop_id: int | None,
        period_ym: str,
    ) -> LawyerDirectorPayment | None:
        stmt = select(LawyerDirectorPayment).where(
            LawyerDirectorPayment.director_id == director_id,
            LawyerDirectorPayment.period_ym == period_ym,
        )
        if shop_id is None:
            stmt = stmt.where(LawyerDirectorPayment.shop_id.is_(None))
        else:
            stmt = stmt.where(LawyerDirectorPayment.shop_id == shop_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_alerts(self, *, unread_only: bool, limit: int) -> list[LawyerParserAlert]:
        stmt = select(LawyerParserAlert).order_by(LawyerParserAlert.created_at.desc())
        if unread_only:
            stmt = stmt.where(LawyerParserAlert.is_read.is_(False))
        return list((await self._session.execute(stmt.limit(limit))).scalars().all())

    async def unread_alert_count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(LawyerParserAlert).where(
                LawyerParserAlert.is_read.is_(False),
            ),
        )
        return int(result.scalar_one())

    async def mark_alerts_read(self, alert_ids: list[int] | None) -> None:
        stmt = update(LawyerParserAlert).where(LawyerParserAlert.is_read.is_(False))
        if alert_ids:
            stmt = stmt.where(LawyerParserAlert.id.in_(alert_ids))
        await self._session.execute(stmt.values(is_read=True))

    async def shops_by_inns(self, inns: list[str]) -> dict[str, LawyerShop]:
        if not inns:
            return {}
        result = await self._session.execute(select(LawyerShop).where(LawyerShop.inn.in_(inns)))
        return {row.inn: row for row in result.scalars().all()}

    def touch(self, row: LawyerDirector | LawyerShop) -> None:
        row.updated_at = datetime.now(UTC)
