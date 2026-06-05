from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.auth.schemas import RelaxedEmail
from app.modules.db.models.enums import (
    UserAvailability,
    UserDeletionRequestState,
    UserPresence,
    UserRole,
    UserStatus,
)

PasswordField = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: str
    role: UserRole
    department_id: int | None
    group_id: int | None
    status: UserStatus
    presence: UserPresence
    availability: UserAvailability
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserOut]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    email: RelaxedEmail | None = None
    full_name: str = Field(min_length=1, max_length=256)
    password: PasswordField
    role: UserRole = UserRole.USER
    group_id: int = Field(gt=0)


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=256)
    group_id: int | None = Field(default=None, gt=0)
    role: UserRole | None = None
    status: UserStatus | None = None
    availability: UserAvailability | None = None


class ResetPasswordResponse(BaseModel):
    temporary_password: str


class ForceLogoutResponse(BaseModel):
    ok: bool = True


class UserDeletionRequestCreateBody(BaseModel):
    comment: str | None = Field(default=None, max_length=4000)


class UserDeletionRequestRejectBody(BaseModel):
    admin_comment: str | None = Field(default=None, max_length=4000)


class UserDeletionRequestOut(BaseModel):
    id: int
    target_user_id: int
    requested_by_user_id: int
    state: UserDeletionRequestState
    comment: str | None
    admin_comment: str | None
    decided_at: datetime | None
    decided_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    target_full_name: str | None = None
    requested_by_full_name: str | None = None


class UserDeletionRequestListResponse(BaseModel):
    items: list[UserDeletionRequestOut]
