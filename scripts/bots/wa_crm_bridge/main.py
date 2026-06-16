#!/usr/bin/env python3
"""WhatsApp (GREEN API) <-> CRM bridge — loads bot configs from CRM."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiohttp import web
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("wa_crm_bridge")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def sign_inbound(event_id: str, timestamp: str, body: bytes, secret: str) -> str:
    digest = hashlib.sha256(body).hexdigest()
    canonical = f"{event_id}.{timestamp}.{digest}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_outbound(method: str, path: str, timestamp: str, body: bytes, secret: str, signature: str) -> bool:
    digest = hashlib.sha256(body).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{digest}"
    expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    got = signature.strip().removeprefix("sha256=")
    return hmac.compare_digest(expected, got)


def sign_outbound(method: str, path: str, timestamp: str, body: bytes, secret: str) -> str:
    digest = hashlib.sha256(body).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{digest}"
    sig = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def chat_id_to_phone(chat_id: str) -> int | None:
    raw = (chat_id or "").split("@", 1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def phone_to_chat_id(phone: int | str) -> str:
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return f"{digits}@c.us"


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = full_name.strip().split(None, 1)
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _parse_inbound_message(webhook: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]] | None:
    message_data = webhook.get("messageData") or {}
    type_message = str(message_data.get("typeMessage") or "")

    if type_message == "textMessage":
        text_data = message_data.get("textMessageData") or {}
        text = str(text_data.get("textMessage") or "").strip()
        if text.startswith("{{SWE") and text.endswith("}}"):
            log.warning("GREEN API error placeholder in text: %s", text)
            return None
        return text, text, []

    if type_message == "extendedTextMessage":
        text_data = message_data.get("extendedTextMessageData") or {}
        text = str(text_data.get("text") or "").strip()
        return text, text, []

    if type_message == "quotedMessage":
        text_data = message_data.get("extendedTextMessageData") or {}
        text = str(text_data.get("text") or "").strip()
        return text, text, []

    file_types = {
        "imageMessage": "photo",
        "videoMessage": "document",
        "documentMessage": "document",
        "audioMessage": "voice",
    }
    if type_message in file_types:
        file_data = message_data.get("fileMessageData") or {}
        download_url = str(file_data.get("downloadUrl") or "").strip()
        if not download_url or download_url.startswith("{{"):
            log.warning("Missing downloadUrl for %s", type_message)
            return None
        caption = str(file_data.get("caption") or "").strip()
        mime = file_data.get("mimeType")
        filename = file_data.get("fileName")
        att_type = file_types[type_message]
        if att_type == "photo" and mime and not str(mime).startswith("image/"):
            att_type = "document"
        attachments = [
            {
                "type": att_type,
                "url": download_url,
                "mime": mime,
                "filename": filename,
            }
        ]
        text = caption or _default_attachment_label(att_type)
        return text, caption, attachments

    log.info("Unsupported GREEN message type: %s", type_message)
    return None


def _default_attachment_label(att_type: str) -> str:
    if att_type == "photo":
        return "Фото"
    if att_type == "voice":
        return "Голосовое сообщение"
    return "Файл"


@dataclass(frozen=True)
class BotConfig:
    bot_code: str
    inbound_secret: str
    outbound_secret: str
    green_api_url: str
    green_media_url: str
    green_instance_id: str
    green_api_token: str

    @property
    def green_base(self) -> str:
        return f"{self.green_api_url.rstrip('/')}/waInstance{self.green_instance_id}"

    @property
    def green_media_base(self) -> str:
        return f"{self.green_media_url.rstrip('/')}/waInstance{self.green_instance_id}"


class Bridge:
    def __init__(self) -> None:
        self.crm_api = _env("CRM_API_BASE", "http://127.0.0.1:19001").rstrip("/")
        self.sync_secret = _env("WA_BRIDGE_SYNC_SECRET")
        self.listen_host = _env("LISTEN_HOST", "0.0.0.0")
        self.listen_port = int(_env("LISTEN_PORT", "8766") or "8766")
        self.webhook_token = _env("WEBHOOK_TOKEN")
        self.bots: dict[str, BotConfig] = {}
        self._bots_lock = asyncio.Lock()

        if not self.sync_secret:
            raise SystemExit("WA_BRIDGE_SYNC_SECRET is required")

    async def reload_config(self) -> None:
        url = f"{self.crm_api}/api/v1/internal/wa-bridge/config"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"X-Wa-Bridge-Secret": self.sync_secret})
        if resp.status_code >= 400:
            raise RuntimeError(f"CRM config sync failed HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        loaded: dict[str, BotConfig] = {}
        for item in payload.get("items") or []:
            cfg = BotConfig(
                bot_code=str(item["bot_code"]),
                inbound_secret=str(item["inbound_secret"]),
                outbound_secret=str(item["outbound_secret"]),
                green_api_url=str(item["green_api_url"]),
                green_media_url=str(item["green_media_url"]),
                green_instance_id=str(item["green_instance_id"]),
                green_api_token=str(item["green_api_token"]),
            )
            loaded[cfg.bot_code] = cfg
        async with self._bots_lock:
            self.bots = loaded
        log.info("Loaded %d WhatsApp bot(s): %s", len(loaded), ", ".join(sorted(loaded)) or "—")

    async def config_loop(self) -> None:
        while True:
            try:
                await self.reload_config()
            except Exception:
                log.exception("Config sync failed")
            await asyncio.sleep(30)

    async def _get_bot(self, bot_code: str) -> BotConfig | None:
        async with self._bots_lock:
            return self.bots.get(bot_code)

    async def send_to_crm(
        self,
        cfg: BotConfig,
        *,
        phone: int,
        external_id: str,
        text: str,
        attachments: list[dict[str, Any]],
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        if not text and not attachments:
            return

        event_id = f"wa-{external_id}-{int(time.time())}"
        occurred_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        envelope = {
            "event": "message.received",
            "event_id": event_id,
            "occurred_at": occurred_at,
            "bot_code": cfg.bot_code,
            "payload": {
                "contact": {
                    "telegram_user_id": phone,
                    "first_name": first_name,
                    "last_name": last_name,
                },
                "message": {
                    "external_id": external_id,
                    "text": text,
                    "attachments": attachments,
                },
            },
        }
        body = json.dumps(envelope, separators=(",", ":")).encode()
        unix_ts = str(int(time.time()))
        signature = sign_inbound(event_id, unix_ts, body, cfg.inbound_secret)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.crm_api}/api/v1/bot-events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Bot-Code": cfg.bot_code,
                    "X-Event-Id": event_id,
                    "X-Timestamp": unix_ts,
                    "X-Signature": f"sha256={signature}",
                },
            )
        if resp.status_code != 202:
            log.error("CRM inbound failed %s: %s", resp.status_code, resp.text)
        else:
            log.info(
                "CRM accepted bot=%s phone=%s text=%r attachments=%d",
                cfg.bot_code,
                phone,
                text[:80],
                len(attachments),
            )

    async def handle_green_webhook(self, request: web.Request) -> web.Response:
        if self.webhook_token:
            token = request.headers.get("X-Webhook-Token", "")
            if not hmac.compare_digest(token, self.webhook_token):
                return web.Response(status=401, text="invalid webhook token")

        bot_code = request.match_info.get("bot_code", "").strip()
        cfg = await self._get_bot(bot_code)
        if cfg is None:
            log.warning("Unknown WhatsApp bot webhook: %s", bot_code)
            return web.Response(status=404, text="unknown bot")

        try:
            webhook = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="invalid json")

        if webhook.get("typeWebhook") != "incomingMessageReceived":
            return web.Response(text="ok")

        sender = webhook.get("senderData") or {}
        chat_id = str(sender.get("chatId") or "")
        if chat_id.endswith("@g.us"):
            return web.Response(text="ok")

        phone = chat_id_to_phone(chat_id)
        if phone is None:
            log.warning("Cannot parse phone from chat_id=%s", chat_id)
            return web.Response(text="ok")

        parsed = _parse_inbound_message(webhook)
        if parsed is None:
            return web.Response(text="ok")

        text, _caption, attachments = parsed
        external_id = str(webhook.get("idMessage") or f"wa-{phone}-{int(time.time())}")
        contact_name = sender.get("senderContactName") or sender.get("senderName") or sender.get("chatName")
        first_name, last_name = _split_name(str(contact_name) if contact_name else None)

        await self.send_to_crm(
            cfg,
            phone=phone,
            external_id=external_id,
            text=text,
            attachments=attachments,
            first_name=first_name,
            last_name=last_name,
        )
        return web.Response(text="ok")

    async def send_whatsapp_text(self, cfg: BotConfig, chat_id: str, text: str) -> dict[str, Any]:
        url = f"{cfg.green_base}/sendMessage/{cfg.green_api_token}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"chatId": chat_id, "message": text})
        data = resp.json()
        if resp.status_code >= 400:
            raise RuntimeError(f"GREEN sendMessage failed: {data}")
        return {"status": "ok", "external_id": str(data.get("idMessage") or "")}

    async def fetch_crm_file(self, cfg: BotConfig, file_id: int) -> tuple[bytes, str, str]:
        path = f"/api/v1/bot-outbound/files/{file_id}"
        url = f"{self.crm_api}{path}"
        timestamp = str(int(time.time()))
        signature = sign_outbound("GET", path, timestamp, b"", cfg.outbound_secret)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                url,
                headers={
                    "X-Bot-Code": cfg.bot_code,
                    "X-CRM-Timestamp": timestamp,
                    "X-CRM-Signature": signature,
                },
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"CRM file fetch failed HTTP {resp.status_code}: {resp.text[:200]}")
        filename = f"file_{file_id}"
        disposition = resp.headers.get("content-disposition", "")
        if "filename*=" in disposition:
            part = disposition.split("filename*=", 1)[-1]
            if "''" in part:
                filename = part.split("''", 1)[-1].strip('"')
        elif 'filename="' in disposition:
            filename = disposition.split('filename="', 1)[-1].split('"', 1)[0]
        mime = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, mime, filename

    async def send_whatsapp_file(
        self,
        cfg: BotConfig,
        chat_id: str,
        *,
        data: bytes,
        filename: str,
        mime: str,
        caption: str | None,
    ) -> dict[str, Any]:
        url = f"{cfg.green_media_base}/sendFileByUpload/{cfg.green_api_token}"
        form: dict[str, Any] = {"chatId": chat_id}
        if caption:
            form["caption"] = caption
        if filename:
            form["fileName"] = filename
        files = {"file": (filename, data, mime)}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, data=form, files=files)
        payload = resp.json()
        if resp.status_code >= 400:
            raise RuntimeError(f"GREEN sendFileByUpload failed: {payload}")
        return {"status": "ok", "external_id": str(payload.get("idMessage") or "")}

    async def handle_outbound(self, request: web.Request) -> web.Response:
        body = await request.read()
        timestamp = request.headers.get("X-CRM-Timestamp", "")
        signature = request.headers.get("X-CRM-Signature", "")

        try:
            envelope = json.loads(body.decode())
        except json.JSONDecodeError:
            return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        bot_code = str(envelope.get("bot_code") or "")
        cfg = await self._get_bot(bot_code)
        if cfg is None:
            return web.json_response({"status": "error", "message": "unknown bot"}, status=404)

        if not verify_outbound("POST", request.path, timestamp, body, cfg.outbound_secret, signature):
            log.warning("Invalid outbound signature for bot=%s", bot_code)
            return web.json_response({"status": "error", "message": "invalid signature"}, status=401)

        command = envelope.get("command")
        payload = envelope.get("payload") or {}
        if command != "send_message":
            return web.json_response({"status": "ok", "skipped": True})

        contact = payload.get("contact") or {}
        message = payload.get("message") or {}
        attachments = payload.get("attachments") or []
        phone = contact.get("telegram_user_id")
        text = (message.get("text") or "").strip()
        if phone is None:
            return web.json_response(
                {"status": "error", "message": "missing telegram_user_id (phone)"},
                status=422,
            )
        if not text and not attachments:
            return web.json_response(
                {"status": "error", "message": "missing text or attachments"},
                status=422,
            )

        chat_id = phone_to_chat_id(phone)
        try:
            last_result: dict[str, Any] | None = None
            if attachments:
                for index, att in enumerate(attachments):
                    file_id = att.get("file_id")
                    if file_id is None:
                        continue
                    file_bytes, mime, filename = await self.fetch_crm_file(cfg, int(file_id))
                    att_filename = att.get("filename") or filename
                    att_mime = att.get("mime") or mime
                    caption = text if index == 0 and text else None
                    last_result = await self.send_whatsapp_file(
                        cfg,
                        chat_id,
                        data=file_bytes,
                        filename=str(att_filename),
                        mime=str(att_mime),
                        caption=caption,
                    )
                if last_result is not None:
                    return web.json_response(last_result)
            if text:
                result = await self.send_whatsapp_text(cfg, chat_id, text)
                return web.json_response(result)
            return web.json_response({"status": "error", "message": "nothing sent"}, status=422)
        except Exception as exc:
            log.exception("WhatsApp send failed bot=%s", bot_code)
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    async def handle_health(self, request: web.Request) -> web.Response:
        timestamp = request.headers.get("X-CRM-Timestamp", "")
        signature = request.headers.get("X-CRM-Signature", "")
        if signature:
            async with self._bots_lock:
                configs = list(self.bots.values())
            if not any(
                verify_outbound("GET", request.path, timestamp, b"", cfg.outbound_secret, signature)
                for cfg in configs
            ):
                return web.Response(status=401, text="invalid signature")
        return web.Response(text="ok")

    async def run(self) -> None:
        try:
            await self.reload_config()
        except Exception:
            log.exception("Initial config sync failed, will retry every 30s")

        asyncio.create_task(self.config_loop())

        app = web.Application()
        app.router.add_post("/green/webhook/{bot_code}", self.handle_green_webhook)
        app.router.add_post("/crm/cmd", self.handle_outbound)
        app.router.add_get("/crm/health", self.handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.listen_host, self.listen_port)
        await site.start()
        log.info("WA bridge listening on http://%s:%s", self.listen_host, self.listen_port)
        log.info("Webhook pattern: /green/webhook/{bot_code}")

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()


def main() -> None:
    bridge = Bridge()
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Stopped")


if __name__ == "__main__":
    main()
