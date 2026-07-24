#!/usr/bin/env python3
"""Find invoice-level duplicates in NDS scan state.

Compares rows as supplier|date|amount (счёт-фактура). Buyer may differ across
form layouts — those are reported as soft dups that inflate totals when
dedupe-key still includes buyer.

Usage:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/audit_nds_invoice_dups.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

_DEFAULT_STATE = Path("/tmp/crm_nds_scan_state.json")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


def _invoice_key_from_stored(key: str) -> str | None:
    """Accept both buyer|supplier|date|amount and supplier|date|amount."""
    parts = str(key).split("|")
    if len(parts) == 4:
        _buyer, supplier, day, amount = parts
        return f"{supplier}|{day}|{amount}"
    if len(parts) == 3:
        return str(key)
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state-file", default=str(_DEFAULT_STATE))
    args = p.parse_args()
    path = Path(args.state_file)
    if not path.exists():
        _log(f"state missing: {path}")
        return 1

    st = json.loads(path.read_text(encoding="utf-8"))
    files: dict[str, Any] = st.get("files") or {}

    # invoice_key -> list of (buyer, file_name, commission_share_hint)
    by_inv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    file_comms: list[tuple[str, Decimal, list[str]]] = []

    for meta in files.values():
        if not isinstance(meta, dict) or meta.get("status") != "hit":
            continue
        name = str(meta.get("name") or "?")
        buyer = str(meta.get("buyer_inn") or "?")
        try:
            comm = Decimal(str(meta.get("commission") or 0))
        except Exception:
            comm = Decimal("0")
        keys = [str(k) for k in (meta.get("line_keys") or []) if k]
        file_comms.append((name, comm, keys))
        for k in keys:
            inv = _invoice_key_from_stored(k)
            if not inv:
                continue
            parts = k.split("|")
            row_buyer = parts[0] if len(parts) == 4 else buyer
            by_inv[inv].append(
                {
                    "buyer": row_buyer,
                    "file": name,
                    "stored_key": k,
                },
            )

    soft_dup_groups = {
        inv: rows
        for inv, rows in by_inv.items()
        if len({r["buyer"] for r in rows}) > 1 or len({r["file"] for r in rows}) > 1
    }

    # Estimate inflated commission: files whose EVERY line_key maps to an invoice
    # already seen in an earlier file (by scan order ≈ state iteration order).
    seen_inv: set[str] = set()
    inflated = Decimal("0")
    inflated_files: list[tuple[str, Decimal, int]] = []
    for name, comm, keys in file_comms:
        invs = []
        for k in keys:
            inv = _invoice_key_from_stored(k)
            if inv:
                invs.append(inv)
        if not invs:
            continue
        if all(inv in seen_inv for inv in invs):
            inflated += comm
            inflated_files.append((name, comm, len(invs)))
        for inv in invs:
            seen_inv.add(inv)

    unique_invoice = len(by_inv)
    multi_buyer = sum(
        1 for inv, rows in by_inv.items() if len({r["buyer"] for r in rows}) > 1
    )

    _log("=== INVOICE DEDUP AUDIT ===")
    _log(f"state: {path}")
    _log(f"stored unique_к_оплате: {st.get('unique_commission')}")
    _log(f"stored unique_lines (keys): {len(st.get('line_keys') or [])}")
    _log(f"invoice keys (supplier|date|amount): {unique_invoice}")
    _log(f"invoices with multiple buyers: {multi_buyer}")
    _log(f"soft-dup invoice groups (multi file and/or multi buyer): {len(soft_dup_groups)}")
    _log(
        f"estimated commission from fully-duplicate files: {_money(inflated)} "
        f"({len(inflated_files)} files)",
    )
    try:
        stored_c = Decimal(str(st.get("unique_commission") or 0))
    except Exception:
        stored_c = Decimal("0")
    _log(f"rough adjusted к_оплате ≈ {_money(stored_c - inflated)}")

    _log("")
    _log("=== MULTI-BUYER INVOICES (same SF, different buyer INN) ===")
    shown = 0
    for inv, rows in sorted(soft_dup_groups.items(), key=lambda x: -len(x[1])):
        buyers = sorted({r["buyer"] for r in rows})
        if len(buyers) < 2:
            continue
        files_n = sorted({r["file"] for r in rows})
        _log(f"  {inv}")
        _log(f"    buyers={buyers}")
        _log(f"    files={files_n[:6]}{'...' if len(files_n) > 6 else ''}")
        shown += 1
        if shown >= 25:
            _log(f"  ... +more")
            break

    _log("")
    _log("=== FILES WHOSE LINES ARE ALL PRIOR INVOICES (likely pure dups) ===")
    for name, comm, n in inflated_files[:40]:
        _log(f"  {_money(comm)}  lines={n}  {name}")
    if len(inflated_files) > 40:
        _log(f"  ... +{len(inflated_files) - 40} more")

    _log("")
    _log(
        "Next: rescan with default --dedupe-key invoice "
        "(supplier|date|amount) to collapse these in totals.",
    )
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
