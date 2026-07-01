from __future__ import annotations

from app.modules.leads.opt.buyer_lookup import lookup_buyer_by_inn
from app.modules.leads.opt.egrul import lookup_party_by_inn
from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.db.models.opt_unit import OptUnit


async def resolve_buyer_requisites(
    repo: OptOrderRepository,
    buyer_inn: str,
) -> tuple[str | None, str | None]:
    kpp, name = lookup_buyer_by_inn(buyer_inn)
    if kpp and name:
        return kpp, name

    buyer = await repo.get_buyer_by_inn(buyer_inn)
    if buyer and buyer.kpp and buyer.name:
        return buyer.kpp, buyer.name

    party = await lookup_party_by_inn(buyer_inn)
    if party is None:
        return None, None

    await repo.upsert_buyer(inn=buyer_inn, kpp=party.kpp, name=party.name)
    return party.kpp, party.name


async def ensure_unit_requisites(repo: OptOrderRepository, unit: OptUnit) -> OptUnit:
    if unit.kpp and unit.name:
        return unit

    party = await lookup_party_by_inn(unit.inn)
    if party is None:
        return unit

    await repo.update_unit_requisites(
        unit,
        kpp=party.kpp,
        name=party.name if party.name else None,
    )
    return unit
