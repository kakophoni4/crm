from __future__ import annotations

import structlog

from app.shared.db import get_session_factory

logger = structlog.get_logger(__name__)


async def task_due_reminders(_job_type: str, _payload: dict[str, object]) -> None:
    from app.modules.tasks.service import TaskService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TaskService(session)
        count = await service.send_due_reminders()
        await session.commit()
        if count:
            logger.info("task_due_reminders_sent", count=count)
