#!/usr/bin/env python3
"""Telegram <-> CRM bridge: TG messages -> CRM inbound; CRM outbound -> Telegram."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tg_crm_bridge")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def sign_inbound(event_id: str, timestamp: str, body: bytes, secret: str) -> str:
    digest = hashlib.sha256(body).hexdigest()
    canonical = f"{event_id}.{timestamp}.{digest}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_outbound(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    secret: str,
    signature: str,
) -> bool:
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


def _pick_largest_photo(photos: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not photos:
        return None
    return max(photos, key=lambda p: p.get("file_size") or p.get("width") or 0)


# Cloud Telegram Bot API cannot return file paths for downloads above ~20 MB.
TG_BOT_API_MAX_FILE_BYTES = 20 * 1024 * 1024


def _fmt_mb(size_bytes: int | None) -> str:
    if size_bytes is None or size_bytes <= 0:
        return "?"
    return f"{size_bytes / (1024 * 1024):.1f}"


async def _telegram_file_url(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
) -> tuple[str | None, str | None]:
    """Return (download_url, error_description)."""
    resp = await client.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id},
    )
    data = resp.json()
    if not data.get("ok"):
        desc = str(data.get("description") or data)
        log.warning("getFile failed for %s: %s", file_id, data)
        return None, desc
    file_path = (data.get("result") or {}).get("file_path")
    if not file_path:
        return None, "Telegram не вернул путь к файлу"
    return f"https://api.telegram.org/file/bot{token}/{file_path}", None


async def _build_attachments(
    client: httpx.AsyncClient,
    token: str,
    tg_message: dict[str, Any],
) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []

    async def add(
        *,
        att_type: str,
        file_id: str,
        mime: str | None = None,
        filename: str | None = None,
        size_bytes: int | None = None,
    ) -> None:
        name = (filename or "").strip() or "файл"
        size_int = int(size_bytes) if size_bytes is not None else None
        too_big = size_int is not None and size_int > TG_BOT_API_MAX_FILE_BYTES

        url: str | None = None
        error: str | None = None
        if too_big:
            error = (
                f"«{name}» ({_fmt_mb(size_int)} МБ) слишком большой для бота Telegram "
                f"(лимит 20 МБ). Попросите прислать архив поменьше или ссылку на облако."
            )
            log.warning(
                "skip getFile for oversized file %s (%s bytes)",
                name,
                size_int,
            )
        else:
            url, tg_error = await _telegram_file_url(client, token, file_id)
            if not url:
                error = (
                    f"Не удалось скачать «{name}» из Telegram"
                    + (f" ({_fmt_mb(size_int)} МБ)" if size_int else "")
                    + ". Обычно так бывает с файлами больше 20 МБ — нужна ссылка на облако."
                )
                if tg_error:
                    log.warning("attachment unresolved: %s", tg_error)

        entry: dict[str, Any] = {
            "type": att_type,
            "url": url,
            "mime": mime,
            "filename": filename,
            "size_bytes": size_bytes,
        }
        if not url:
            entry["status"] = "failed"
            entry["error"] = error
        attachments.append(entry)

    photo = _pick_largest_photo(tg_message.get("photo") or [])
    if photo and photo.get("file_id"):
        await add(
            att_type="photo",
            file_id=str(photo["file_id"]),
            mime="image/jpeg",
            size_bytes=photo.get("file_size"),
        )

    document = tg_message.get("document")
    if isinstance(document, dict) and document.get("file_id"):
        await add(
            att_type="document",
            file_id=str(document["file_id"]),
            mime=document.get("mime_type"),
            filename=document.get("file_name"),
            size_bytes=document.get("file_size"),
        )

    video = tg_message.get("video")
    if isinstance(video, dict) and video.get("file_id"):
        await add(
            att_type="document",
            file_id=str(video["file_id"]),
            mime=video.get("mime_type") or "video/mp4",
            filename=video.get("file_name"),
            size_bytes=video.get("file_size"),
        )

    voice = tg_message.get("voice")
    if isinstance(voice, dict) and voice.get("file_id"):
        await add(
            att_type="voice",
            file_id=str(voice["file_id"]),
            mime=voice.get("mime_type") or "audio/ogg",
            filename="voice.ogg",
            size_bytes=voice.get("file_size"),
        )

    audio = tg_message.get("audio")
    if isinstance(audio, dict) and audio.get("file_id"):
        await add(
            att_type="document",
            file_id=str(audio["file_id"]),
            mime=audio.get("mime_type") or "audio/mpeg",
            filename=audio.get("file_name") or audio.get("title") or "audio",
            size_bytes=audio.get("file_size"),
        )

    sticker = tg_message.get("sticker")
    if isinstance(sticker, dict) and sticker.get("file_id"):
        is_animated = bool(sticker.get("is_animated") or sticker.get("is_video"))
        await add(
            att_type="document" if is_animated else "photo",
            file_id=str(sticker["file_id"]),
            mime="video/webm" if sticker.get("is_video") else "image/webp",
            filename="sticker.webp",
            size_bytes=sticker.get("file_size"),
        )

    return attachments


def _message_text(tg_message: dict[str, Any], attachments: list[dict[str, Any]]) -> str:
    text = (tg_message.get("text") or tg_message.get("caption") or "").strip()
    if text:
        return text
    if not attachments:
        return ""
    first = attachments[0]
    att_type = str(first.get("type") or "document")
    filename = str(first.get("filename") or "").strip()
    if att_type == "photo":
        return "Фото"
    if att_type == "voice":
        return "Голосовое сообщение"
    if att_type == "document" and filename.startswith("sticker"):
        return "Стикер"
    if filename:
        return filename
    return "Вложение"


class Bridge:
    def __init__(self) -> None:
        self.tg_token = _env("TG_BOT_TOKEN")
        self.crm_api = _env("CRM_API_BASE", "https://api.crmkanasha.org").rstrip("/")
        self.bot_code = _env("BOT_CODE", "test_bot_1")
        self.inbound_secret = _env("INBOUND_SECRET")
        self.outbound_secret = _env("OUTBOUND_SECRET")
        self.listen_host = _env("LISTEN_HOST", "0.0.0.0")
        self.listen_port = int(_env("LISTEN_PORT", "8765") or "8765")
        if not self.tg_token:
            raise SystemExit("TG_BOT_TOKEN is required")
        if not self.inbound_secret or not self.outbound_secret:
            raise SystemExit("INBOUND_SECRET and OUTBOUND_SECRET are required")

    async def send_to_crm(self, tg_message: dict[str, Any]) -> None:
        user = tg_message.get("from") or {}
        tg_user_id = user.get("id")
        if tg_user_id is None:
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            attachments = await _build_attachments(client, self.tg_token, tg_message)
            text = _message_text(tg_message, attachments)
            if not text and not attachments:
                log.debug("Skip empty TG message %s", tg_message.get("message_id"))
                return

            event_id = f"tg-{tg_message.get('message_id')}-{int(time.time())}"
            occurred_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            envelope = {
                "event": "message.received",
                "event_id": event_id,
                "occurred_at": occurred_at,
                "bot_code": self.bot_code,
                "payload": {
                    "contact": {
                        "telegram_user_id": int(tg_user_id),
                        "telegram_username": user.get("username"),
                        "first_name": user.get("first_name"),
                        "last_name": user.get("last_name"),
                    },
                    "message": {
                        "external_id": str(tg_message.get("message_id")),
                        "text": text,
                        "attachments": attachments,
                    },
                },
            }
            body = json.dumps(envelope, separators=(",", ":")).encode()
            unix_ts = str(int(time.time()))
            signature = sign_inbound(event_id, unix_ts, body, self.inbound_secret)

            resp = await client.post(
                f"{self.crm_api}/api/v1/bot-events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Bot-Code": self.bot_code,
                    "X-Event-Id": event_id,
                    "X-Timestamp": unix_ts,
                    "X-Signature": f"sha256={signature}",
                },
            )
        if resp.status_code != 202:
            log.error("CRM inbound failed %s: %s", resp.status_code, resp.text)
        else:
            log.info(
                "CRM accepted tg_user=%s text=%r attachments=%d",
                tg_user_id,
                text[:80],
                len(attachments),
            )

    async def send_telegram(self, chat_id: int, text: str) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {data}")
        result = data["result"]
        return {
            "status": "ok",
            "external_id": str(result.get("message_id")),
            "telegram_message_id": result.get("message_id"),
        }

    async def fetch_crm_file(self, file_id: int) -> tuple[bytes, str, str]:
        path = f"/api/v1/bot-outbound/files/{file_id}"
        url = f"{self.crm_api}{path}"
        timestamp = str(int(time.time()))
        signature = sign_outbound("GET", path, timestamp, b"", self.outbound_secret)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                url,
                headers={
                    "X-Bot-Code": self.bot_code,
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

    async def send_telegram_media(
        self,
        chat_id: int,
        *,
        data: bytes,
        filename: str,
        mime: str,
        caption: str | None,
        as_photo: bool,
    ) -> dict[str, Any]:
        method = "sendPhoto" if as_photo else "sendDocument"
        url = f"https://api.telegram.org/bot{self.tg_token}/{method}"
        field = "photo" if as_photo else "document"
        form: dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            form["caption"] = caption
        files = {field: (filename, data, mime)}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, data=form, files=files)
        payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {payload}")
        result = payload["result"]
        return {
            "status": "ok",
            "external_id": str(result.get("message_id")),
            "telegram_message_id": result.get("message_id"),
        }

    async def handle_outbound(self, request: web.Request) -> web.Response:
        body = await request.read()
        timestamp = request.headers.get("X-CRM-Timestamp", "")
        signature = request.headers.get("X-CRM-Signature", "")
        if not verify_outbound(
            "POST",
            request.path,
            timestamp,
            body,
            self.outbound_secret,
            signature,
        ):
            log.warning("Invalid outbound signature")
            return web.json_response(
                {"status": "error", "message": "invalid signature"},
                status=401,
            )

        try:
            envelope = json.loads(body.decode())
        except json.JSONDecodeError:
            return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        command = envelope.get("command")
        payload = envelope.get("payload") or {}
        log.info("Outbound command=%s payload_keys=%s", command, list(payload.keys()))

        if command != "send_message":
            return web.json_response({"status": "ok", "skipped": True})

        contact = payload.get("contact") or {}
        message = payload.get("message") or {}
        attachments = payload.get("attachments") or []
        tg_user_id = contact.get("telegram_user_id")
        text = (message.get("text") or "").strip()
        if tg_user_id is None:
            return web.json_response(
                {"status": "error", "message": "missing telegram_user_id"},
                status=422,
            )
        if not text and not attachments:
            return web.json_response(
                {"status": "error", "message": "missing text or attachments"},
                status=422,
            )

        try:
            tg_chat_id = int(tg_user_id)
            last_result: dict[str, Any] | None = None

            if attachments:
                for index, att in enumerate(attachments):
                    file_id = att.get("file_id")
                    if file_id is None:
                        continue
                    file_bytes, mime, filename = await self.fetch_crm_file(int(file_id))
                    att_filename = att.get("filename") or filename
                    att_mime = att.get("mime") or mime
                    caption = text if index == 0 and text else None
                    as_photo = att.get("type") == "photo" or str(att_mime).startswith("image/")
                    last_result = await self.send_telegram_media(
                        tg_chat_id,
                        data=file_bytes,
                        filename=str(att_filename),
                        mime=str(att_mime),
                        caption=caption,
                        as_photo=as_photo,
                    )
                    log.info(
                        "Sent media to TG user %s file_id=%s photo=%s",
                        tg_user_id,
                        file_id,
                        as_photo,
                    )
                if last_result is not None:
                    return web.json_response(last_result)

            if text:
                result = await self.send_telegram(tg_chat_id, text)
                log.info("Sent to TG user %s: %r", tg_user_id, text[:80])
                return web.json_response(result)

            return web.json_response(
                {"status": "error", "message": "nothing sent"},
                status=422,
            )
        except Exception as exc:
            log.exception("Telegram send failed")
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    async def handle_health(self, request: web.Request) -> web.Response:
        timestamp = request.headers.get("X-CRM-Timestamp", "")
        signature = request.headers.get("X-CRM-Signature", "")
        if signature and not verify_outbound(
            "GET",
            request.path,
            timestamp,
            b"",
            self.outbound_secret,
            signature,
        ):
            return web.Response(status=401, text="invalid signature")
        return web.Response(text="ok")

    async def poll_telegram(self) -> None:
        offset = 0
        url = f"https://api.telegram.org/bot{self.tg_token}/getUpdates"
        log.info("Telegram long polling started")
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                try:
                    resp = await client.get(
                        url,
                        params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                    )
                    data = resp.json()
                    if not data.get("ok"):
                        log.error("getUpdates error: %s", data)
                        await asyncio.sleep(5)
                        continue
                    for update in data.get("result", []):
                        offset = int(update["update_id"]) + 1
                        message = update.get("message")
                        if message:
                            await self.send_to_crm(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("poll loop error")
                    await asyncio.sleep(5)

    async def run(self) -> None:
        app = web.Application()
        app.router.add_post("/crm/cmd", self.handle_outbound)
        app.router.add_get("/crm/health", self.handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.listen_host, self.listen_port)
        await site.start()
        log.info("Outbound listener http://%s:%s/crm/cmd", self.listen_host, self.listen_port)

        poll_task = asyncio.create_task(self.poll_telegram())
        try:
            await asyncio.Event().wait()
        finally:
            poll_task.cancel()
            await runner.cleanup()


def main() -> None:
    bridge = Bridge()
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Stopped")


if __name__ == "__main__":
    main()
