from __future__ import annotations

from app.workers.bots.dispatch_outbound import dispatch_outbound_command
from app.workers.bots.download_attachment import download_attachment
from app.workers.bots.health_check import bot_health_check
from app.workers.bots.process_event import process_bot_event
from app.workers.bots.queue import register_handler, start_worker


def register_bot_workers() -> None:
    register_handler("process_bot_event", process_bot_event)
    register_handler("download_attachment", download_attachment)
    register_handler("dispatch_outbound", dispatch_outbound_command)
    register_handler("bot_health_check", bot_health_check)


__all__ = ["register_bot_workers", "start_worker"]
