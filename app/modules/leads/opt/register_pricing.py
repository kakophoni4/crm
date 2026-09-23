from decimal import Decimal
from app.modules.leads.opt.allocation import allocate_amount

def register_line_pricing(order, lines):
    breakdown = order.volume_by_category or {}
    old_rates = {Decimal(str(v['rate_percent'])) for v in breakdown.values()
                 if isinstance(v, dict) and v.get('rate_percent') is not None}
    fallback = next(iter(old_rates)) if len(old_rates) == 1 else None
    rates = {line.id: Decimal(str(line.pricing_rate_percent))
             if getattr(line, 'pricing_rate_percent', None) is not None else fallback for line in lines}
    estimated = any(rate is None for rate in rates.values())
    weights = [Decimal(str(line.amount)) * (rates[line.id] if not estimated else Decimal(1)) for line in lines]
    amounts = allocate_amount(Decimal(str(order.commission_due or 0)), weights)
    return rates, dict(zip((line.id for line in lines), amounts)), estimated
