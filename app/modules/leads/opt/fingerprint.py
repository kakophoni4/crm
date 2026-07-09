from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from app.modules.leads.opt.parser import ParsedApplication

_ACTIVE_DUPLICATE_STATUSES = frozenset({"queued", "submitting", "submitted"})


def compute_application_fingerprint(parsed: ParsedApplication) -> str:
    lines = sorted(
        [
            {
                "supplier_inn": line.supplier_inn,
                "document_date": line.document_date.isoformat(),
                "amount": format(line.amount.quantize(Decimal("0.01")), "f"),
            }
            for line in parsed.lines
        ],
        key=lambda row: (row["supplier_inn"], row["document_date"], row["amount"]),
    )
    payload = {"buyer_inn": parsed.buyer_inn, "lines": lines}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_active_duplicate_status(status: str) -> bool:
    return status in _ACTIVE_DUPLICATE_STATUSES
