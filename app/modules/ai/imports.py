# ruff: noqa: RUF001
"""Bounded, local-only preparation of raw CRM exports. Never auto-approves data."""

import gzip
import hashlib
import io
import json
import re
from typing import Any

from fastapi import Request

from app.modules.ai.router import DB, Admin, router
from app.shared.exceptions import AppError

MAX_BYTES = 32 * 1024 * 1024


def prepare(raw: bytes) -> Any:
    stream = gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b"\x1f\x8b" else io.BytesIO(raw)
    output, total, warnings = [], 0, []
    preview_bytes = 0
    try:
        for number in range(1, 10002):
            line = stream.readline(MAX_BYTES + 1)
            if not line:
                break
            total += len(line)
            if total > MAX_BYTES or number > 10000:
                raise AppError(
                    "too_large", "Распакованный архив превышает 32 МБ или 10000 строк", 413
                )
            obj = json.loads(line)
            messages = obj.get("messages")
            if not isinstance(messages, list) or not isinstance(obj.get("chat"), dict):
                raise ValueError()
            cid = (
                "anonymous-"
                + hashlib.sha256(str(obj["chat"].get("id", number)).encode()).hexdigest()[:16]
            )
            replacements: dict[str, str] = {}

            def mask(text: Any, replacements: Any = replacements) -> Any:
                def token(match: Any) -> Any:
                    value = match.group(0)
                    if value not in replacements:
                        replacements[value] = f"[ДАННЫЕ_{len(replacements) + 1}]"
                    return replacements[value]

                return re.sub(
                    (
                        "[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}|https?://\\S+|(?<!\\w)@\\w+|(?<!\\w)\\+"
                        "?\\d[\\d ()-]{7,}\\d"
                    ),
                    token,
                    text,
                )

            history: list[dict[str, str]] = []
            for m in sorted(
                messages, key=lambda m: (str(m.get("created_at", "")), int(m.get("id", 0)))
            ):
                if m.get("attachments"):
                    warnings.append(f"Строка {number}: содержимое вложений не прочитано")
                text = (m.get("text") or "").strip()
                if not text or text.startswith("/") or m.get("kind") == "system":
                    continue
                text = mask(text)
                inbound = m.get("direction") == "inbound"
                if (
                    not inbound
                    and m.get("sender_user_id")
                    and history
                    and history[-1]["role"] == "user"
                ):
                    preview_bytes += sum(len(x["content"].encode()) for x in history[-50:]) + len(
                        text.encode()
                    )
                    if preview_bytes > 8 * 1024 * 1024:
                        raise AppError(
                            "preview_too_large",
                            "Предпросмотр превышает 8 МБ. Разделите исходный архив.",
                            413,
                        )
                    output.append(
                        {
                            "chat_id": cid,
                            "system": "",
                            "messages": list(history[-50:]),
                            "answer": {"reply": text, "action": "reply", "reason": None},
                        }
                    )
                    if len(output) >= 200:
                        break
                    if len(output) > 10000:
                        raise AppError(
                            "too_large", "Более 10000 вариантов ответов. Разделите архив.", 413
                        )
                history.append({"role": "user" if inbound else "assistant", "content": text})
            # Return bounded previews, not duplicated full histories for an entire archive.
            if len(output) >= 200:
                warnings.append(
                    "Предпросмотр ограничен первыми 200 вариантами. Разделите архив дл"
                    "я обработки остальных."
                )
                output = output[:200]
                break
    except (ValueError, TypeError, KeyError, AttributeError, OSError, EOFError):
        raise AppError(
            "invalid_export",
            "Не удалось прочитать строку архива. Нужна выгрузка CRM chat/messages в JSONL или GZ.",
            422,
        ) from None
    return {
        "records": output,
        "warnings": list(dict.fromkeys(warnings))[:30],
        "notice": (
            "Email, телефоны, числовые реквизиты и ссылки заменены. ФИО, адрес"
            "а и смысл ответа нужно проверить вручную. Ни один пример не отпра"
            "влен в ИИ."
        ),
    }


@router.post("/prepare-export")
async def prepare_export(request: Request, actor: Admin, db: DB) -> Any:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise AppError("too_large", "Максимум 32 МБ", 413)
    import base64
    from uuid import uuid4

    from app.modules.db.models.ai import AIRequest

    rid = "crm-prepare-" + str(uuid4())
    db.add(
        AIRequest(
            id=rid,
            actor_id=actor.id,
            path="__prepare_export__",
            body={"archive": base64.b64encode(raw).decode("ascii")},
        )
    )
    await db.commit()
    return {"request_id": rid, "status": "queued"}
