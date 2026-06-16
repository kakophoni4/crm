from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)


def default_green_api_url(instance_id: str) -> str:
    shard = (instance_id or "").strip()[:4]
    if not shard.isdigit():
        return "https://api.green-api.com"
    return f"https://{shard}.api.green-api.com"


def default_green_media_url(instance_id: str) -> str:
    return default_green_api_url(instance_id)


def whatsapp_webhook_url(public_base: str, bot_code: str) -> str:
    return f"{public_base.rstrip('/')}/{bot_code}"


async def sync_green_webhook(
    *,
    api_url: str,
    instance_id: str,
    api_token: str,
    webhook_url: str,
) -> None:
    url = f"{api_url.rstrip('/')}/waInstance{instance_id}/setSettings/{api_token}"
    payload = {
        "webhookUrl": webhook_url,
        "incomingWebhook": "yes",
        "outgoingWebhook": "yes",
        "outgoingMessageWebhook": "yes",
        "outgoingAPIMessageWebhook": "yes",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
    if response.status_code >= 400:
        logger.warning(
            "green_set_settings_failed",
            status=response.status_code,
            body=response.text[:500],
        )
        raise RuntimeError(f"GREEN setSettings failed HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if not data.get("saveSettings"):
        raise RuntimeError(f"GREEN setSettings rejected: {data}")
