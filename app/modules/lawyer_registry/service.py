from __future__ import annotations

from datetime import UTC, date, datetime
from time import monotonic
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.lawyer_director import (
    LawyerDirector,
    LawyerDirectorPayment,
    LawyerParserAlert,
    LawyerShop,
)
from app.modules.db.models.user import User
from app.modules.lawyer_registry.repository import LawyerRegistryRepository
from app.modules.lawyer_registry.schemas import (
    LawyerAlertListResponse,
    LawyerAlertOut,
    LawyerDirectorCreateRequest,
    LawyerDirectorListResponse,
    LawyerDirectorOut,
    LawyerDirectorPatchRequest,
    LawyerImportResponse,
    LawyerPaymentCreateRequest,
    LawyerPaymentOut,
    LawyerShopCreateRequest,
    LawyerShopOut,
    LawyerShopPatchRequest,
)
from app.modules.lawyer_registry.tickets_map import (
    merge_unreliable,
    payload_items,
    status_from_company,
)
from app.modules.lawyer_registry.xlsx import director_name_key, normalize_inn, parse_svodnaya
from app.shared.exceptions import NotFound, ValidationError

logger = structlog.get_logger(__name__)
_TICKETS_SYNC_COOLDOWN_SEC = 60.0
_last_tickets_sync_at = 0.0


def _money(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


class LawyerRegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LawyerRegistryRepository(session)

    def _shop_out(self, shop: LawyerShop, director_name: str | None = None) -> LawyerShopOut:
        return LawyerShopOut(
            id=shop.id,
            inn=shop.inn,
            name=shop.name,
            director_id=shop.director_id,
            director_name=director_name,
            kind=shop.kind,
            registered_at=shop.registered_at,
            planned_payout=_money(shop.planned_payout),
            company_status=shop.company_status,
            sale_priority=shop.sale_priority,
            unreliable=shop.unreliable,
            treatment_status=shop.treatment_status,
            ecsp_status=shop.ecsp_status,
            ecsp_until=shop.ecsp_until,
            zsk=shop.zsk,
            banks=shop.banks,
            accounts_status=shop.accounts_status,
            manager=shop.manager,
            phone=shop.phone,
            telegram=shop.telegram,
            accountant=shop.accountant,
            comment=shop.comment,
            source=shop.source,
            last_parser_at=shop.last_parser_at,
            pinned_at=shop.pinned_at,
            hidden_at=shop.hidden_at,
            created_at=shop.created_at,
        )

    def _director_out(
        self,
        director: LawyerDirector,
        *,
        shop_count: int = 0,
        last_paid_period: str | None = None,
        shops: list[LawyerShopOut] | None = None,
        payments: list[LawyerPaymentOut] | None = None,
    ) -> LawyerDirectorOut:
        return LawyerDirectorOut(
            id=director.id,
            full_name=director.full_name,
            salary_plan=_money(director.salary_plan),
            dirovod=director.dirovod,
            company_status=director.company_status,
            companies_status=director.companies_status,
            ecsp_status=director.ecsp_status,
            ecsp_until=director.ecsp_until,
            banks=director.banks,
            accounts_status=director.accounts_status,
            phone=director.phone,
            telegram=director.telegram,
            passport=director.passport,
            inn_personal=director.inn_personal,
            snils=director.snils,
            birth_date=director.birth_date,
            in_touch=director.in_touch,
            note=director.note,
            pinned_at=director.pinned_at,
            shop_count=shop_count,
            last_paid_period=last_paid_period,
            shops=shops or [],
            payments=payments or [],
        )

    async def _ensure_director(
        self,
        name: str | None,
        *,
        actor_id: int | None,
        extra: dict[str, Any] | None = None,
    ) -> LawyerDirector | None:
        cleaned = " ".join((name or "").split())
        if not cleaned:
            return None
        key = director_name_key(cleaned)
        row = await self._repo.get_director_by_key(key)
        if row is None:
            row = LawyerDirector(
                full_name=cleaned,
                name_key=key,
                created_by=actor_id,
                **{k: v for k, v in (extra or {}).items() if v not in (None, "")},
            )
            try:
                async with self._session.begin_nested():
                    await self._repo.add(row)
            except IntegrityError:
                row = await self._repo.get_director_by_key(key)
                if row is None:
                    raise ValidationError(
                        message=f"Директор уже есть в реестре: {cleaned}",
                    ) from None
        if extra:
            for field, value in extra.items():
                if value not in (None, "") and getattr(row, field, None) in (None, ""):
                    setattr(row, field, value)
            self._repo.touch(row)
        return row

    async def list_tree(
        self,
        *,
        q: str | None = None,
        kind: str | None = None,
        company_status: str | None = None,
        unreliable: str | None = None,
        zsk: str | None = None,
        ecsp_status: str | None = None,
        manager: str | None = None,
        dirovod: str | None = None,
        include_shops: bool = False,
        include_hidden: bool = False,
    ) -> LawyerDirectorListResponse:
        try:
            await self.sync_from_tickets()
        except Exception:
            logger.warning("lawyer_registry_tickets_sync_failed", exc_info=True)
        filtered = any(
            [q, kind, company_status, unreliable, zsk, ecsp_status, manager, dirovod],
        )
        shops = await self._repo.list_shops(
            q=q,
            kind=kind,
            company_status=company_status,
            unreliable=unreliable,
            zsk=zsk,
            ecsp_status=ecsp_status,
            manager=manager,
            dirovod=dirovod,
            include_hidden=include_hidden,
        )
        directors = await self._repo.list_directors()
        by_id = {row.id: row for row in directors}
        names = {row.id: row.full_name for row in directors}
        if filtered:
            keep_ids = {shop.director_id for shop in shops if shop.director_id is not None}
            directors = [row for row in directors if row.id in keep_ids]
            include_shops = True
        director_ids = [row.id for row in directors]
        counts = await self._repo.shop_counts(director_ids, include_hidden=include_hidden)
        if not include_hidden and not filtered:
            all_counts = await self._repo.shop_counts(director_ids, include_hidden=True)
            directors = [
                row
                for row in directors
                if counts.get(row.id, 0) > 0 or all_counts.get(row.id, 0) == 0
            ]
            director_ids = [row.id for row in directors]
        last_paid = await self._repo.last_paid_periods(director_ids)
        shops_by_dir: dict[int, list[LawyerShop]] = {}
        orphans: list[LawyerShop] = []
        if include_shops or filtered:
            source = shops if filtered else await self._repo.list_shops(include_hidden=include_hidden)
            for shop in source:
                if shop.director_id is None:
                    orphans.append(shop)
                else:
                    shops_by_dir.setdefault(shop.director_id, []).append(shop)
        pinned = await self._repo.list_shops(pinned_only=True, include_hidden=include_hidden)
        items = [
            self._director_out(
                director,
                shop_count=len(shops_by_dir.get(director.id, []))
                if include_shops or filtered
                else counts.get(director.id, 0),
                last_paid_period=last_paid.get(director.id),
                shops=[
                    self._shop_out(shop, director.full_name)
                    for shop in shops_by_dir.get(director.id, [])
                ]
                if include_shops or filtered
                else [],
            )
            for director in directors
        ]
        return LawyerDirectorListResponse(
            items=items,
            orphan_shops=[self._shop_out(shop) for shop in orphans],
            pinned_shops=[self._shop_out(shop, names.get(shop.director_id or 0)) for shop in pinned],
            total_directors=len(items),
            total_shops=len(shops) if filtered else int(sum(counts.values())),
            unread_alerts=await self._repo.unread_alert_count(),
        )

    async def get_director(self, director_id: int) -> LawyerDirectorOut:
        director = await self._repo.get_director(director_id)
        if director is None:
            raise NotFound(message="Директор не найден")
        shops = await self._repo.list_shops(director_id=director_id, include_hidden=True)
        payments = await self._repo.list_payments(director_id)
        shop_names = {shop.id: shop.name for shop in shops}
        return self._director_out(
            director,
            shop_count=len(shops),
            last_paid_period=(await self._repo.last_paid_periods([director_id])).get(director_id),
            shops=[self._shop_out(shop, director.full_name) for shop in shops],
            payments=[
                LawyerPaymentOut(
                    id=row.id,
                    director_id=row.director_id,
                    shop_id=row.shop_id,
                    shop_name=shop_names.get(row.shop_id) if row.shop_id else None,
                    period_ym=row.period_ym,
                    amount=float(row.amount),
                    paid_at=row.paid_at,
                    note=row.note,
                    created_at=row.created_at,
                )
                for row in payments
            ],
        )

    async def create_director(
        self,
        actor: User,
        body: LawyerDirectorCreateRequest,
    ) -> LawyerDirectorOut:
        extra = body.model_dump(exclude={"full_name"}, exclude_none=True)
        row = await self._ensure_director(body.full_name, actor_id=actor.id, extra=extra)
        if row is None:
            raise ValidationError(message="Укажите ФИО директора")
        return await self.get_director(row.id)

    async def patch_director(
        self,
        actor: User,
        director_id: int,
        body: LawyerDirectorPatchRequest,
    ) -> LawyerDirectorOut:
        director = await self._repo.get_director(director_id)
        if director is None:
            raise NotFound(message="Директор не найден")
        data = body.model_dump(exclude_unset=True)
        pinned = data.pop("pinned", None)
        if "full_name" in data and data["full_name"]:
            director.full_name = " ".join(str(data.pop("full_name")).split())
            director.name_key = director_name_key(director.full_name)
        for field, value in data.items():
            setattr(director, field, value)
        if pinned is True:
            director.pinned_at = datetime.now(UTC)
        elif pinned is False:
            director.pinned_at = None
        self._repo.touch(director)
        await self._session.flush()
        return await self.get_director(director.id)

    async def create_shop(self, actor: User, body: LawyerShopCreateRequest) -> LawyerShopOut:
        inn = normalize_inn(body.inn)
        if not inn:
            raise ValidationError(message="Некорректный ИНН")
        existing = await self._repo.get_shop_by_inn(inn)
        if existing is not None:
            raise ValidationError(message="Лавка с таким ИНН уже есть")
        director: LawyerDirector | None = None
        if body.director_id is not None:
            director = await self._repo.get_director(body.director_id)
        elif body.director_name:
            director = await self._ensure_director(body.director_name, actor_id=actor.id)
        data = body.model_dump(exclude={"inn", "director_name", "director_id"}, exclude_none=True)
        shop = LawyerShop(
            inn=inn,
            director_id=director.id if director else None,
            source="manual",
            created_by=actor.id,
            **data,
        )
        await self._repo.add(shop)
        await self._push_to_parser(inn)
        return self._shop_out(shop, director.full_name if director else None)

    async def patch_shop(
        self,
        actor: User,
        shop_id: int,
        body: LawyerShopPatchRequest,
    ) -> LawyerShopOut:
        shop = await self._repo.get_shop(shop_id)
        if shop is None:
            raise NotFound(message="Лавка не найдена")
        data = body.model_dump(exclude_unset=True)
        pinned = data.pop("pinned", None)
        hidden = data.pop("hidden", None)
        director_name = data.pop("director_name", None)
        if director_name:
            director = await self._ensure_director(director_name, actor_id=actor.id)
            shop.director_id = director.id if director else None
        if "director_id" in data:
            shop.director_id = data.pop("director_id")
        for field, value in data.items():
            setattr(shop, field, value)
        if pinned is True:
            shop.pinned_at = datetime.now(UTC)
        elif pinned is False:
            shop.pinned_at = None
        if hidden is True:
            shop.hidden_at = datetime.now(UTC)
        elif hidden is False:
            shop.hidden_at = None
        self._repo.touch(shop)
        await self._session.flush()
        director = await self._repo.get_director(shop.director_id) if shop.director_id else None
        return self._shop_out(shop, director.full_name if director else None)

    async def add_payment(
        self,
        actor: User,
        director_id: int,
        body: LawyerPaymentCreateRequest,
    ) -> LawyerPaymentOut:
        director = await self._repo.get_director(director_id)
        if director is None:
            raise NotFound(message="Директор не найден")
        if body.shop_id is not None:
            shop = await self._repo.get_shop(body.shop_id)
            if shop is None:
                raise NotFound(message="Лавка не найдена")
        existing = await self._repo.find_payment(director_id, body.shop_id, body.period_ym)
        if existing is not None:
            existing.amount = body.amount
            existing.paid_at = body.paid_at or date.today()
            existing.note = body.note
            row = existing
        else:
            row = LawyerDirectorPayment(
                director_id=director_id,
                shop_id=body.shop_id,
                period_ym=body.period_ym,
                amount=body.amount,
                paid_at=body.paid_at or date.today(),
                note=body.note,
                created_by=actor.id,
            )
            await self._repo.add(row)
        shop = await self._repo.get_shop(row.shop_id) if row.shop_id else None
        return LawyerPaymentOut(
            id=row.id,
            director_id=row.director_id,
            shop_id=row.shop_id,
            shop_name=shop.name if shop else None,
            period_ym=row.period_ym,
            amount=float(row.amount),
            paid_at=row.paid_at,
            note=row.note,
            created_at=row.created_at,
        )

    async def delete_payment(self, payment_id: int) -> None:
        row = await self._repo.get_payment(payment_id)
        if row is None:
            raise NotFound(message="Выплата не найдена")
        await self._repo.delete_payment(row)

    async def list_alerts(self) -> LawyerAlertListResponse:
        items = await self._repo.list_alerts(unread_only=False, limit=100)
        return LawyerAlertListResponse(
            items=[LawyerAlertOut.model_validate(row) for row in items],
            unread=await self._repo.unread_alert_count(),
        )

    async def mark_alerts_read(self, alert_ids: list[int] | None) -> None:
        await self._repo.mark_alerts_read(alert_ids)

    async def import_svodnaya(self, actor: User, content: bytes) -> LawyerImportResponse:
        parsed = parse_svodnaya(content)
        directors_created = 0
        shops_created = 0
        shops_updated = 0
        payments_created = 0
        for item in parsed["shops"]:
            director = await self._ensure_director(
                item.get("director_name"),
                actor_id=actor.id,
                extra={
                    "in_touch": item.get("in_touch"),
                    "passport": item.get("passport"),
                    "inn_personal": item.get("inn_personal"),
                    "snils": item.get("snils"),
                    "birth_date": item.get("birth_date"),
                },
            )
            if director is not None and director.id and item.get("director_name"):
                if director.created_at == director.updated_at:
                    directors_created += 0
            shop = await self._repo.get_shop_by_inn(item["inn"])
            payload = {
                key: item.get(key)
                for key in (
                    "name",
                    "kind",
                    "registered_at",
                    "planned_payout",
                    "company_status",
                    "sale_priority",
                    "unreliable",
                    "treatment_status",
                    "ecsp_status",
                    "ecsp_until",
                    "zsk",
                    "banks",
                    "accounts_status",
                    "manager",
                    "phone",
                    "telegram",
                    "accountant",
                    "comment",
                    "source",
                )
            }
            if shop is None:
                shop = LawyerShop(
                    inn=item["inn"],
                    director_id=director.id if director else None,
                    created_by=actor.id,
                    **{k: v for k, v in payload.items() if v is not None},
                )
                await self._repo.add(shop)
                shops_created += 1
            else:
                for key, value in payload.items():
                    if value not in (None, ""):
                        setattr(shop, key, value)
                if director is not None:
                    shop.director_id = director.id
                self._repo.touch(shop)
                shops_updated += 1
            if director is not None and item.get("planned_payout") and not director.salary_plan:
                director.salary_plan = item["planned_payout"]
            if director is not None:
                if item.get("ecsp_status") and not director.ecsp_status:
                    director.ecsp_status = item.get("ecsp_status")
                if item.get("ecsp_until") and not director.ecsp_until:
                    director.ecsp_until = item.get("ecsp_until")
                if item.get("banks") and not director.banks:
                    director.banks = item.get("banks")
                if item.get("accounts_status") and not director.accounts_status:
                    director.accounts_status = item.get("accounts_status")
                if item.get("company_status") and not director.companies_status:
                    director.companies_status = item.get("company_status")
        shop_by_name: dict[str, LawyerShop] = {}
        for shop in await self._repo.list_shops():
            shop_by_name.setdefault(shop.name.casefold(), shop)
        for pay in parsed["payments"]:
            director = await self._ensure_director(pay["director_name"], actor_id=actor.id)
            if director is None:
                continue
            shop = shop_by_name.get((pay.get("shop_name") or "").casefold())
            existing = await self._repo.find_payment(
                director.id,
                shop.id if shop else None,
                pay["period_ym"],
            )
            if existing is not None:
                continue
            await self._repo.add(
                LawyerDirectorPayment(
                    director_id=director.id,
                    shop_id=shop.id if shop else None,
                    period_ym=pay["period_ym"],
                    amount=pay["amount"],
                    paid_at=date.fromisoformat(f"{pay['period_ym']}-01"),
                    created_by=actor.id,
                ),
            )
            payments_created += 1
        return LawyerImportResponse(
            directors=len(await self._repo.list_directors()),
            shops=shops_created,
            payments=payments_created,
            updated=shops_updated,
        )

    async def sync_from_tickets(self) -> int:
        global _last_tickets_sync_at
        now = monotonic()
        if now - _last_tickets_sync_at < _TICKETS_SYNC_COOLDOWN_SEC:
            return 0
        from app.modules.tickets.client import SmertnikiUnavailable, smertniki_request

        try:
            companies_payload = await smertniki_request("GET", "/api/v1/companies")
            tickets_payload = await smertniki_request(
                "GET",
                "/api/v1/tickets",
                params={"status": "in_progress"},
            )
        except SmertnikiUnavailable:
            return 0
        _last_tickets_sync_at = now

        companies = payload_items(companies_payload)
        tickets = payload_items(tickets_payload)
        inns = [normalize_inn(row.get("inn")) for row in companies]
        inns = [inn for inn in inns if inn]
        if not inns:
            return 0
        shops = await self._repo.shops_by_inns(inns)
        titles_by_inn: dict[str, list[str]] = {}
        for ticket in tickets:
            inn = normalize_inn(ticket.get("company_inn") or ticket.get("inn"))
            title = str(ticket.get("title") or "").strip()
            if inn and title:
                titles_by_inn.setdefault(inn, []).append(title)

        alerts = 0
        for company in companies:
            inn = normalize_inn(company.get("inn"))
            if not inn:
                continue
            shop = shops.get(inn)
            if shop is None:
                continue
            changes: list[str] = []
            next_unreliable = merge_unreliable(
                shop.unreliable,
                address=bool(company.get("unreliable_address")),
                director=bool(company.get("unreliable_director")),
                founder=bool(company.get("unreliable_founder")),
            )
            if (shop.unreliable or "").strip() != (next_unreliable or "").strip():
                changes.append(f"недостоверка: {shop.unreliable or '—'} → {next_unreliable or '—'}")
                shop.unreliable = next_unreliable
            next_status = status_from_company(company, shop.company_status)
            if (shop.company_status or "").strip() != (next_status or "").strip():
                changes.append(f"статус: {shop.company_status or '—'} → {next_status or '—'}")
                shop.company_status = next_status
            titles = titles_by_inn.get(inn) or []
            if titles:
                treatment = "; ".join(titles)[:500]
                if (shop.treatment_status or "").strip() != treatment:
                    changes.append("лечение из тикетов")
                    shop.treatment_status = treatment
            incoming_name = str(company.get("short_name") or company.get("name") or "").strip()
            if incoming_name and not (shop.name or "").strip():
                shop.name = incoming_name
                changes.append(f"название: {incoming_name}")
            if changes:
                self._repo.touch(shop)
                await self._repo.add(
                    LawyerParserAlert(
                        shop_id=shop.id,
                        inn=inn,
                        title=f"Тикеты обновили {shop.name}",
                        details="; ".join(changes)[:2000],
                    ),
                )
                alerts += 1
        return alerts

    async def sync_from_parser(self, lots: list[Any]) -> int:
        inns = [normalize_inn(getattr(lot, "inn", None)) for lot in lots]
        inns = [inn for inn in inns if inn]
        shops = await self._repo.shops_by_inns(inns)
        alerts = 0
        seen: set[str] = set()
        for lot in lots:
            inn = normalize_inn(getattr(lot, "inn", None))
            if not inn or inn in seen:
                continue
            seen.add(inn)
            shop = shops.get(inn)
            if shop is None:
                continue
            fields = getattr(lot, "fields", None) or {}
            changes: list[str] = []

            def apply(field: str, incoming: str | None) -> None:
                if not incoming:
                    return
                current = getattr(shop, field)
                if (current or "").strip() != incoming.strip():
                    if current:
                        changes.append(f"{field}: {current} → {incoming}")
                    else:
                        changes.append(f"{field}: {incoming}")
                    setattr(shop, field, incoming)

            apply("name", fields.get("name"))
            apply("zsk", fields.get("zsk"))
            apply("unreliable", fields.get("egrul_reliability"))
            registered = fields.get("registered_at")
            if registered and not shop.registered_at:
                from app.modules.lawyer_registry.xlsx import _as_date

                parsed_date = _as_date(registered)
                if parsed_date:
                    shop.registered_at = parsed_date
                    changes.append(f"дата регистрации: {parsed_date.isoformat()}")
            shop.last_parser_at = datetime.now(UTC)
            self._repo.touch(shop)
            if changes:
                await self._repo.add(
                    LawyerParserAlert(
                        shop_id=shop.id,
                        inn=inn,
                        title=f"Парсер обновил {shop.name}",
                        details="; ".join(changes)[:2000],
                    ),
                )
                alerts += 1
        return alerts

    async def _push_to_parser(self, inn: str) -> None:
        try:
            from app.modules.tickets.client import smertniki_request

            await smertniki_request(
                "POST",
                "/api/v1/companies/inns",
                json={"inns": [inn], "check_new": True},
            )
        except Exception:
            logger.warning("lawyer_registry_smertniki_add_failed", inn=inn, exc_info=True)
