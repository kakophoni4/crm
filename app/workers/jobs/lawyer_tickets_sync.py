from app.shared.db import get_session_factory
from app.shared.redis import get_redis
from app.workers.jobs.queue import enqueue

JOB_TYPE = 'lawyer_tickets_sync'


async def schedule_lawyer_tickets_sync() -> None:
    if await get_redis().set('crm:lawyer:tickets:scheduled', '1', nx=True, ex=120):
        await enqueue(JOB_TYPE, {})


async def sync_lawyer_tickets(_job_type: str, _payload: dict[str, object]) -> None:
    from app.modules.lawyer_registry.service import LawyerRegistryService

    async with get_session_factory()() as session:
        await LawyerRegistryService(session).sync_from_tickets()
        await session.commit()
