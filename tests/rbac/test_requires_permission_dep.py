from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.exceptions import register_exception_handlers
from app.shared.security.deps import current_user
from app.shared.security.permissions import requires_all_permissions, requires_permission
from tests.rbac.conftest import make_user

_require_users_create = requires_permission(Permission.USERS_CREATE)
_require_profile_and_admin = requires_all_permissions(
    Permission.PROFILE_PASSWORD_UPDATE,
    Permission.USERS_CREATE,
)
_require_both_profile_fields = requires_all_permissions(
    Permission.PROFILE_PASSWORD_UPDATE,
    Permission.PROFILE_FULL_NAME_UPDATE,
)


def _rbac_test_app() -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)
    router = APIRouter()

    @router.get("/any")
    async def any_perm(
        user: User = Depends(_require_users_create),
    ) -> dict[str, int]:
        return {"user_id": user.id}

    @router.get("/all")
    async def all_perms(
        user: User = Depends(_require_profile_and_admin),
    ) -> dict[str, int]:
        return {"user_id": user.id}

    @router.get("/profile-all")
    async def profile_all_perms(
        user: User = Depends(_require_both_profile_fields),
    ) -> dict[str, int]:
        return {"user_id": user.id}

    application.include_router(router)
    return application


@pytest.fixture
def rbac_app() -> FastAPI:
    return _rbac_test_app()


@pytest.fixture
async def rbac_client(rbac_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=rbac_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_requires_permission_denied_with_details(
    rbac_app: FastAPI,
    rbac_client: AsyncClient,
) -> None:
    user = make_user(user_id=1, role=UserRole.USER, department_id=1, group_id=1)
    rbac_app.dependency_overrides[current_user] = lambda: user

    response = await rbac_client.get("/any")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "permission_denied"
    assert body["error"]["details"]["required"] == [Permission.USERS_CREATE.value]

    rbac_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_requires_permission_granted(rbac_app: FastAPI, rbac_client: AsyncClient) -> None:
    user = make_user(user_id=1, role=UserRole.ADMIN)
    rbac_app.dependency_overrides[current_user] = lambda: user

    response = await rbac_client.get("/any")
    assert response.status_code == 200
    assert response.json() == {"user_id": 1}

    rbac_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_requires_all_permissions_partial_denied(
    rbac_app: FastAPI,
    rbac_client: AsyncClient,
) -> None:
    user = make_user(user_id=2, role=UserRole.USER, department_id=1, group_id=1)
    rbac_app.dependency_overrides[current_user] = lambda: user

    response = await rbac_client.get("/all")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    assert set(response.json()["error"]["details"]["required"]) == {
        Permission.PROFILE_PASSWORD_UPDATE.value,
        Permission.USERS_CREATE.value,
    }

    rbac_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_requires_all_permissions_granted(
    rbac_app: FastAPI,
    rbac_client: AsyncClient,
) -> None:
    user = make_user(user_id=3, role=UserRole.USER, department_id=1, group_id=1)
    rbac_app.dependency_overrides[current_user] = lambda: user

    response = await rbac_client.get("/profile-all")
    assert response.status_code == 200

    rbac_app.dependency_overrides.clear()
