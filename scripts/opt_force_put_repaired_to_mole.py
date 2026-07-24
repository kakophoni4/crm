#!/usr/bin/env python3
"""Force PUT of repaired OPT orders to Mole (POST does not update existing)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder
from app.modules.leads.opt.mole_client import get_order, put_order
from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.leads.opt.service import OptOrderService
from app.shared.db import get_session_factory


IDS = [178, 179, 249, 250, 253]


async def main() -> None:
    sf = get_session_factory()
    async with sf() as session:
        service = OptOrderService(session)
        repo = OptOrderRepository(session)
        for oid in IDS:
            result = await session.execute(
                select(LeadOptOrder)
                .where(LeadOptOrder.id == oid)
                .options(selectinload(LeadOptOrder.lines)),
            )
            order = result.scalar_one_or_none()
            if order is None:
                print(f"order={oid}: missing")
                continue
            await service._ensure_order_requisites(order)
            payload = service._build_mole_payload(order)
            print(
                f"PUT order={oid} no={order.order_no} crm={order.crm_id} "
                f"lines={len(order.lines)} vol={order.total_volume}",
            )
            try:
                response = await put_order(order.crm_id, payload)
            except Exception as exc:
                print(f"  FAIL: {exc}")
                continue
            line_numbers = service._extract_line_numbers(response)
            print(f"  mole doc numbers: {len(line_numbers)}/{len(order.lines)}")
            # Keep restored document numbers if mole omitted them; fill missing only.
            for line in order.lines:
                doc = line_numbers.get(line.crm_id)
                if doc:
                    line.document_number = doc
            order.status = "submitted"
            order.submission_error = None
            order.submission_request = payload
            order.submission_response = response
            await session.commit()
            try:
                check = await get_order(order.crm_id)
                print(f"  GET sum={check.get('СуммаИтого')} (crm vol={order.total_volume})")
            except Exception as exc:
                print(f"  GET fail: {exc}")
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
