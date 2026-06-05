from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.db.models.enums import UserPresence, UserRole

RelaxedEmail = Annotated[
    str,
    StringConstraints(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$"),
]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)


class AuthUserSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    email: str
    full_name: str
    role: UserRole


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: AuthUserSummary


class TokenPairResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    email: str
    full_name: str
    role: UserRole
    department_id: int | None
    group_id: int | None
    presence: UserPresence
    permissions: list[str]
