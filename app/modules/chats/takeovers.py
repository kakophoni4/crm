from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.repository import ChatRepository
from app.modules.chats.scope import can_view_chat_async, chat_department_id
from app.modules.chats.serialization import to_takeover_response
from app.modules.chats.timeutil import utc_now
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.chat_takeover import ChatTakeover
from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.realtime.events import publish
from app.shared.exceptions import Conflict, NotFound, PermissionDenied


class ChatTakeoversService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ChatRepository(session)
        self._scope_loader = ScopeLoader(session)

    def _can_takeover_department(self, actor: User, chat_dept_id: int | None) -> bool:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return True
        if role == UserRole.SENIOR:
            return actor.department_id is not None and actor.department_id == chat_dept_id
        return False

    def _can_takeover_group(self, actor: User, chat_group_id: int | None, ctx) -> bool:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role != UserRole.GROUP_SENIOR:
            return False
        if chat_group_id is None:
            return False
        return chat_group_id in set(ctx.actor_group_ids)

    async def start(
        self,
        actor: User,
        chat_id: int,
        *,
        reason: str | None,
    ) -> tuple[ChatTakeover, dict[str, Any]]:
        ctx = await self._scope_loader.load(actor)
        chat = await self._repo.get_by_id(chat_id)
        if chat is None:
            raise NotFound(message="Chat not found")

        dept_id = chat_department_id(chat)
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        allowed = (
            self._can_takeover_department(actor, dept_id)
            if role != UserRole.GROUP_SENIOR
            else self._can_takeover_group(actor, chat.assigned_group_id, ctx)
        )
        if not allowed:
            raise PermissionDenied(message="Takeover allowed only in your scope")

        if not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")

        active = await self._repo.get_active_takeover(chat_id)
        if active is not None:
            raise Conflict(message="Takeover already active for this chat")

        takeover = ChatTakeover(
            chat_id=chat_id,
            senior_user_id=actor.id,
            reason=reason,
        )
        takeover = await self._repo.add_takeover(takeover)

        scope: dict[str, Any] = {}
        if dept_id is not None:
            scope["department_id"] = dept_id
        if chat.assigned_user_id is not None:
            scope["user_id"] = chat.assigned_user_id

        await publish(
            "chat.takeover.started",
            {
                "chat_id": chat_id,
                "takeover_id": takeover.id,
                "senior_user_id": actor.id,
            },
            scope=scope,
        )
        return takeover, {"chat_id": chat_id, "takeover_id": takeover.id}

    async def release(
        self,
        actor: User,
        chat_id: int,
    ) -> tuple[ChatTakeover, dict[str, Any]]:
        takeover = await self._repo.get_active_takeover(chat_id)
        if takeover is None:
            raise NotFound(message="No active takeover for this chat")

        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if takeover.senior_user_id != actor.id and role != UserRole.ADMIN:
            raise PermissionDenied(message="Only takeover senior or admin can release")

        takeover.released_at = utc_now()
        await self._session.flush()

        await publish(
            "chat.takeover.released",
            {
                "chat_id": chat_id,
                "takeover_id": takeover.id,
                "senior_user_id": takeover.senior_user_id,
            },
        )
        return takeover, {"chat_id": chat_id, "takeover_id": takeover.id}

    def to_response(self, takeover: ChatTakeover) -> dict[str, Any]:
        return to_takeover_response(takeover).model_dump()
