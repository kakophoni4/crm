from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.rate_limit import login_rate_limit
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    MeResponse,
    RefreshRequest,
    TokenPairResponse,
)
from app.modules.auth.service import AuthService
from app.modules.db.models.user import User
from app.shared.db import get_db
from app.shared.security.deps import bearer_token, current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(db)


@router.post("/login", response_model=LoginResponse)
@login_rate_limit
async def login(
    request: Request,
    body: LoginRequest,
    service: Annotated[AuthService, Depends(_service)],
) -> LoginResponse:
    return await service.login(body.username, body.password)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(_service)],
) -> TokenPairResponse:
    return await service.refresh(body.refresh_token)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    body: LogoutRequest,
    _token: Annotated[str, Depends(bearer_token)],
    service: Annotated[AuthService, Depends(_service)],
) -> LogoutResponse:
    await service.logout(body.refresh_token)
    return LogoutResponse()


@router.get("/me", response_model=MeResponse)
async def me(
    user: Annotated[User, Depends(current_user)],
    service: Annotated[AuthService, Depends(_service)],
) -> MeResponse:
    return await service.me(user.id)
