#!/usr/bin/env python3
"""Send a signed test message.received event to CRM (Bot -> CRM integration smoke)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


def sign_inbound(event_id: str, timestamp: str, body: bytes, secret: str) -> str:
    canonical = f"{event_id}.{timestamp}.{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="POST signed event to /api/v1/bot-events")
    parser.add_argument("--api-base", default="https://api.crmkanasha.org")
    parser.add_argument("--bot-code", required=True)
    parser.add_argument("--inbound-secret", required=True)
    parser.add_argument("--event-id", default="")
    parser.add_argument("--telegram-user-id", type=int, default=999888777)
    parser.add_argument("--external-id", default="")
    parser.add_argument("--text", default="Test message from send_test_event.py")
    args = parser.parse_args()

    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    event_id = args.event_id or f"test-{int(time.time())}"
    external_id = args.external_id or f"msg-{int(time.time())}"

    envelope = {
        "event": "message.received",
        "event_id": event_id,
        "occurred_at": ts,
        "bot_code": args.bot_code,
        "payload": {
            "contact": {
                "telegram_user_id": args.telegram_user_id,
                "telegram_username": "test_bot_user",
                "first_name": "Test",
                "last_name": "BotUser",
            },
            "message": {
                "external_id": external_id,
                "text": args.text,
                "attachments": [],
            },
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode()
    unix_ts = str(int(time.time()))
    signature = sign_inbound(event_id, unix_ts, body, args.inbound_secret)

    url = f"{args.api_base.rstrip('/')}/api/v1/bot-events"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Bot-Code": args.bot_code,
            "X-Event-Id": event_id,
            "X-Timestamp": unix_ts,
            "X-Signature": f"sha256={signature}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            print(f"HTTP {resp.status}")
            print(raw)
            return 0 if resp.status == 202 else 1
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(exc.read().decode(), file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
