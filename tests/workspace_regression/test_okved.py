from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.modules.leads.opt.router import update_order_okved
from app.modules.leads.opt.schemas import OptOrderOkvedUpdate
from app.shared.exceptions import NotFound


async def test_okved_updates_only_selected_order_and_can_be_cleared():
    first = SimpleNamespace(buyer_okved=None)
    second = SimpleNamespace(buyer_okved="62.01")
    service = SimpleNamespace(_get_order_for_actor=AsyncMock(return_value=first))
    db = AsyncMock()
    actor = SimpleNamespace(id=10)
    result = await update_order_okved(1, 2, OptOrderOkvedUpdate(buyer_okved=" 47.11 "), actor, service, db)
    service._get_order_for_actor.assert_awaited_once_with(actor, 1, 2)
    assert result.buyer_okved == first.buyer_okved == "47.11"
    assert second.buyer_okved == "62.01"
    result = await update_order_okved(1, 2, OptOrderOkvedUpdate(buyer_okved=" "), actor, service, db)
    assert result.buyer_okved is None


async def test_okved_checks_access_before_commit():
    service = SimpleNamespace(_get_order_for_actor=AsyncMock(side_effect=NotFound()))
    db = AsyncMock()
    with pytest.raises(NotFound):
        await update_order_okved(1, 2, OptOrderOkvedUpdate(buyer_okved="47.11"), SimpleNamespace(id=10), service, db)
    db.commit.assert_not_awaited()


def test_okved_is_optional_but_bounded():
    assert OptOrderOkvedUpdate().buyer_okved is None
    with pytest.raises(ValidationError):
        OptOrderOkvedUpdate(buyer_okved="1" * 201)
