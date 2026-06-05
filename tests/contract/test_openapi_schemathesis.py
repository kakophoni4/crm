"""OpenAPI contract smoke via schemathesis (optional gate: make contract-smoke)."""

from __future__ import annotations

import os

import pytest
import schemathesis
from hypothesis import settings
from schemathesis import checks
from schemathesis.pytest import from_fixture

EXAMPLES = int(os.getenv("SCHEMATHESIS_MAX_EXAMPLES", "50"))

_base = from_fixture("api_schema")
health_schema = _base.include(path_regex=r"^/healthz$")
login_schema = _base.include(path_regex=r"^/api/v1/auth/login$")


@health_schema.parametrize()
@settings(max_examples=EXAMPLES, deadline=None)
def test_healthz_contract(case: schemathesis.Case, db_ready: None) -> None:
    del db_ready
    response = case.call()
    case.validate_response(response, checks=(checks.status_code_conformance,))


@login_schema.parametrize()
@settings(max_examples=EXAMPLES, deadline=None)
def test_auth_login_contract_mock(case: schemathesis.Case, db_ready: None) -> None:
    """Fuzz login request shape; mock credentials → 401/422/429, never 5xx."""
    del db_ready
    if case.method.upper() != "POST":
        pytest.skip("login smoke covers POST only")
    case.body = {
        "username": os.getenv("SCHEMATHESIS_LOGIN_USERNAME", "contract_smoke"),
        "password": os.getenv("SCHEMATHESIS_LOGIN_PASSWORD", "not-a-real-password"),
    }
    response = case.call()
    assert response.status_code in {401, 422, 429}, response.text
    case.validate_response(response, checks=(checks.not_a_server_error,))
