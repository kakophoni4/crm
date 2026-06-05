from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.modules.contacts.ownership import ensure_assignment, get_owner
from app.shared.db import get_session_factory


@pytest.mark.asyncio
async def test_assign_new_contact_round_robin(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_ids = ownership_org["contact_ids"]
    assert isinstance(contact_ids, list)
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)

    assignable = {user_ids["owner.op1@crm.local"], user_ids["owner.op2@crm.local"]}

    session_factory = get_session_factory()
    owners: list[int] = []
    async with session_factory() as session:
        for contact_id in contact_ids[:3]:
            result = await ensure_assignment(session, int(contact_id), group_id)
            await session.commit()
            assert result.owner_user_id in assignable
            owners.append(int(result.owner_user_id))

    assert len(set(owners)) >= 2


@pytest.mark.asyncio
async def test_get_owner_returns_assigned_user(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await ensure_assignment(session, contact_id, group_id)
        await session.commit()
        expected = result.owner_user_id

    async with session_factory() as session:
        owner = await get_owner(session, contact_id, group_id)
        assert owner == expected


@pytest.mark.asyncio
async def test_ensure_assignment_idempotent_when_owner_exists(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])

    session_factory = get_session_factory()
    async with session_factory() as session:
        first = await ensure_assignment(session, contact_id, group_id)
        await session.commit()
        second = await ensure_assignment(session, contact_id, group_id)
        await session.commit()
        assert first.owner_user_id == second.owner_user_id
        assert second.created is False


@pytest.mark.asyncio
async def test_round_robin_skips_do_not_assign(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][3])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    blocked = user_ids["owner.op3@crm.local"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await ensure_assignment(session, contact_id, group_id)
        await session.commit()
        assert result.owner_user_id != blocked


@pytest.mark.asyncio
async def test_parallel_inbound_assignments_are_atomic_round_robin(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_ids = [int(cid) for cid in ownership_org["contact_ids"][:2]]
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    owner_a = user_ids["owner.op1@crm.local"]
    owner_b = user_ids["owner.op2@crm.local"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            text(
                """
                DELETE FROM contact_group_assignments
                WHERE contact_id = ANY(:contact_ids) AND group_id = :gid
                """
            ),
            {"contact_ids": contact_ids, "gid": group_id},
        )
        await session.commit()

    async def _assign(contact_id: int) -> int | None:
        async with session_factory() as session:
            result = await ensure_assignment(session, contact_id, group_id)
            await session.commit()
            return result.owner_user_id

    owners = await asyncio.gather(*(_assign(contact_id) for contact_id in contact_ids))
    assert set(owners) == {owner_a, owner_b}
