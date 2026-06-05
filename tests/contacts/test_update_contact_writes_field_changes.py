from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_patch_writes_one_row_per_changed_field(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    create_resp = await client.post(
        "/api/v1/contacts",
        headers=admin_headers,
        json={"full_name": "Patch Me", "phone": "+79001111111", "custom_fields": {"city": "SPB"}},
    )
    assert create_resp.status_code == 201, create_resp.text
    contact_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        headers=admin_headers,
        json={
            "full_name": "Patch Me Updated",
            "phone": "+79002222222",
            "custom_fields": {"city": "Moscow"},
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            count = connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM contact_field_changes
                    WHERE contact_id = :contact_id
                    """
                ),
                {"contact_id": contact_id},
            ).scalar_one()
            fields = (
                connection.execute(
                    text(
                        """
                    SELECT field_name FROM contact_field_changes
                    WHERE contact_id = :contact_id
                    ORDER BY field_name
                    """
                    ),
                    {"contact_id": contact_id},
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert count == 2
    assert set(fields) == {"custom_fields.city", "phone"}
