from __future__ import annotations

import pytest
import schemathesis
from fastapi import FastAPI


@pytest.fixture(scope="session")
def api_schema(test_settings: object) -> schemathesis.schemas.BaseSchema:
    del test_settings
    from app.main import create_app

    app: FastAPI = create_app()
    return schemathesis.openapi.from_asgi("/api/openapi.json", app)
