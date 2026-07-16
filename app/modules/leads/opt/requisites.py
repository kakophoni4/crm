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
    if name:
        return kpp, name

    buyer = await repo.get_buyer_by_inn(buyer_inn)
    if buyer and buyer.name:
        return buyer.kpp, buyer.name

    party = await lookup_party_by_inn(buyer_inn)
    if party is None:
        return None, None

    await repo.upsert_buyer(inn=buyer_inn, kpp=party.kpp, name=party.name)
    return party.kpp, party.name


def _name_needs_enrichment(name: str | None) -> bool:
    """Short placeholders (Привет/Спектр) must be replaced with full legal names."""
    text = (name or "").strip()
    if not text:
        return True
    upper = text.casefold()
    if upper.startswith("общество ") or upper.startswith("ооо ") or upper.startswith('ооо"'):
        return False
    # Nickname / short seed from period rearrangements.
    return len(text) < 40


async def ensure_unit_requisites(repo: OptOrderRepository, unit: OptUnit) -> OptUnit:
    needs_kpp = not (unit.kpp and str(unit.kpp).strip())
    needs_name = _name_needs_enrichment(unit.name)
    if not needs_kpp and not needs_name:
        return unit

    party = await lookup_party_by_inn(unit.inn)
    if party is None:
        return unit

    await repo.update_unit_requisites(
        unit,
        kpp=party.kpp if needs_kpp else unit.kpp,
        name=party.name if needs_name and party.name else unit.name,
    )
    return unit
