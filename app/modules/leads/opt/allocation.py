from decimal import Decimal, ROUND_HALF_UP


def allocate_amount(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split an amount without losing cents; the last row absorbs rounding."""
    if not weights:
        return []
    total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    denominator = sum(weights)
    if not denominator:
        weights = [Decimal(1)] * len(weights)
        denominator = Decimal(len(weights))
    result = []
    remaining = total
    for weight in weights[:-1]:
        value = min(remaining, (total * weight / denominator).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        result.append(value)
        remaining -= value
    return [*result, remaining]
