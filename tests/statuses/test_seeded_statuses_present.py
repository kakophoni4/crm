from __future__ import annotations

import pytest
from httpx import AsyncClient

_EXPECTED_OPEN = (

    ("new", "Новый", 0),

    ("in_progress", "В работе", 10),

)



_EXPECTED_TERMINAL = (

    ("won", "Успешная продажа", 900),

    ("lost", "Неуспешная продажа", 910),

)





@pytest.mark.asyncio

async def test_seeded_statuses_present(

    client: AsyncClient,

    db_ready: None,

    operator_a_headers: dict[str, str],

) -> None:

    response = await client.get("/api/v1/statuses", headers=operator_a_headers)

    assert response.status_code == 200, response.text



    by_code = {item["code"]: item for item in response.json()["items"]}

    for code, label, sort_order in _EXPECTED_OPEN + _EXPECTED_TERMINAL:

        assert code in by_code, f"missing seeded status: {code}"

        row = by_code[code]

        assert row["label"] == label

        assert row["sort_order"] == sort_order

        assert row["is_active"] is True

    assert "qualified" not in by_code

