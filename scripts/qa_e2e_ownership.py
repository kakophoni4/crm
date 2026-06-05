#!/usr/bin/env python3
"""QA E2E ownership scenarios (curl-equivalent via httpx). Run with API on :8000."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.bots.hmac_util import sign_inbound  # noqa: E402
from app.shared.security.passwords import hash_password  # noqa: E402
from tests.auth.conftest import _sync_database_url  # noqa: E402

BASE = "http://localhost:8000"
PASSWORD = "TestPass!234567"
INBOUND_SECRET = "e2e-inbound-secret-32chars-minimum"
DB_URL = "postgresql+psycopg://crm:crm@localhost:5433/crm"


def _login(client: httpx.Client, email: str) -> str:
    r = client.post(f"{BASE}/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _seed() -> dict[str, int | str]:
    ph = hash_password(PASSWORD)
    engine = create_engine(_sync_database_url(DB_URL))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM message_reply_audit"))
        conn.execute(text("DELETE FROM contact_group_transfers"))
        conn.execute(text("DELETE FROM contact_group_assignments"))
        conn.execute(text("DELETE FROM bot_events_inbox"))
        conn.execute(text("DELETE FROM messages"))
        conn.execute(text("DELETE FROM chats"))
        conn.execute(text("DELETE FROM contacts WHERE telegram_user_id IN (888001, 888002)"))
        conn.execute(text("DELETE FROM bots WHERE code IN ('e2e_bot_g', 'e2e_bot_h')"))
        conn.execute(text("DELETE FROM users WHERE email LIKE 'e2e.%@crm.local'"))

        conn.execute(
            text(
                "INSERT INTO departments (name) VALUES ('E2E Ownership Dept') "
                "ON CONFLICT (name) DO NOTHING"
            ),
        )
        dept_id = conn.execute(
            text("SELECT id FROM departments WHERE name = 'E2E Ownership Dept'"),
        ).scalar_one()

        for gname in ("E2E Group G", "E2E Group H"):
            conn.execute(
                text(
                    "INSERT INTO groups (name, department_id) VALUES (:n, :d) "
                    "ON CONFLICT (department_id, name) DO NOTHING",
                ),
                {"n": gname, "d": dept_id},
            )
        group_g = conn.execute(
            text("SELECT id FROM groups WHERE department_id = :d AND name = 'E2E Group G'"),
            {"d": dept_id},
        ).scalar_one()
        group_h = conn.execute(
            text("SELECT id FROM groups WHERE department_id = :d AND name = 'E2E Group H'"),
            {"d": dept_id},
        ).scalar_one()

        users = [
            ("e2e.anya@crm.local", "Аня", group_g),
            ("e2e.boris@crm.local", "Борис", group_g),
            ("e2e.senior@crm.local", "Старший", None),
        ]
        ids: dict[str, int] = {}
        for email, name, gid in users:
            if gid is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO users (email, password_hash, full_name, role, department_id)
                        VALUES (:e, :ph, :n, 'senior', :d)
                        """,
                    ),
                    {"e": email, "ph": ph, "n": name, "d": dept_id},
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            email, password_hash, full_name, role, group_id, department_id
                        )
                        VALUES (:e, :ph, :n, 'user', :g, :d)
                        """,
                    ),
                    {"e": email, "ph": ph, "n": name, "g": gid, "d": dept_id},
                )
            row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
            ids[email] = row.scalar_one()

        from app.shared.settings import get_settings

        key = get_settings().pgcrypto_key

        for code, gid in (("e2e_bot_g", group_g), ("e2e_bot_h", group_h)):
            conn.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id,
                        inbound_secret_encrypted, outbound_secret_encrypted,
                        outbound_url, health_url, is_active
                    )
                    VALUES (
                        :code, :name, 'group', :gid,
                        pgp_sym_encrypt(:sec, :key),
                        pgp_sym_encrypt(:sec, :key),
                        'https://example.invalid/out', 'https://example.invalid/health', TRUE
                    )
                    """,
                ),
                {"code": code, "name": code, "gid": gid, "sec": INBOUND_SECRET, "key": key},
            )

        bot_g = conn.execute(text("SELECT id FROM bots WHERE code = 'e2e_bot_g'")).scalar_one()

        contact_id = conn.execute(
            text(
                """
                INSERT INTO contacts (telegram_user_id, full_name, created_by)
                VALUES (888001, 'E2E Contact', :uid)
                RETURNING id
                """,
            ),
            {"uid": ids["e2e.anya@crm.local"]},
        ).scalar_one()

        chat_g = conn.execute(
            text(
                """
                INSERT INTO chats (
                    contact_id, bot_id, assigned_group_id, assigned_department_id, status
                )
                VALUES (:cid, :bid, :gid, :did, 'open')
                RETURNING id
                """,
            ),
            {"cid": contact_id, "bid": bot_g, "gid": group_g, "did": dept_id},
        ).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'manual_transfer')
                ON CONFLICT (contact_id, group_id) DO UPDATE
                    SET owner_user_id = EXCLUDED.owner_user_id
                """,
            ),
            {"cid": contact_id, "gid": group_g, "owner": ids["e2e.anya@crm.local"]},
        )
        conn.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'manual_transfer')
                ON CONFLICT (contact_id, group_id) DO UPDATE
                    SET owner_user_id = EXCLUDED.owner_user_id
                """,
            ),
            {"cid": contact_id, "gid": group_h, "owner": ids["e2e.anya@crm.local"]},
        )

        conn.execute(
            text(
                """
                UPDATE group_escalation_settings
                SET first_response_timeout_minutes = 1,
                    notify_owner_on_inbound = TRUE,
                    notify_group_on_escalation = TRUE
                WHERE group_id = :gid
                """,
            ),
            {"gid": group_g},
        )

    engine.dispose()
    return {
        "contact_id": contact_id,
        "chat_g": chat_g,
        "group_g": group_g,
        "group_h": group_h,
        "anya_id": ids["e2e.anya@crm.local"],
        "boris_id": ids["e2e.boris@crm.local"],
    }


def _sign_inbound(event_id: str, bot_code: str, tg_id: int) -> tuple[bytes, dict[str, str]]:
    envelope = {
        "event": "message.received",
        "event_id": event_id,
        "occurred_at": "2026-05-17T12:00:00Z",
        "bot_code": bot_code,
        "payload": {
            "contact": {
                "telegram_user_id": tg_id,
                "telegram_username": "e2e_user",
                "first_name": "E2E",
                "last_name": "Inbound",
            },
            "message": {
                "external_id": f"ext_{event_id}",
                "text": "inbound",
                "attachments": [],
                "sent_at": "2026-05-17T12:00:00Z",
            },
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    return body, {
        "X-Bot-Code": bot_code,
        "X-Event-Id": event_id,
        "X-Timestamp": ts,
        "X-Signature": sign_inbound(event_id, ts, body, INBOUND_SECRET),
        "Content-Type": "application/json",
    }


async def _run_async_jobs(*, event_id: str | None = None, run_escalation: bool = False) -> None:

    from app.shared.db import dispose_engine
    from app.shared.settings import get_settings

    os.environ["OWNERSHIP_V2"] = "true"
    get_settings.cache_clear()
    await dispose_engine()
    if event_id:
        from app.workers.bots.process_event import process_bot_event

        await process_bot_event("process_bot_event", {"event_id": event_id})
    if run_escalation:
        from app.workers.escalation import escalation_scan

        await escalation_scan()
    await dispose_engine()


def _curl_echo(method: str, url: str, headers: dict[str, str], body: bytes | None = None) -> None:
    parts = ["curl", "-sS", "-X", method, f"'{url}'"]
    for k, v in headers.items():
        parts.extend(["-H", f"'{k}: {v}'"])
    if body:
        parts.extend(["--data-binary", f"'{body.decode()}'"])
    print("  $", " ".join(parts))


def _preflight_db() -> None:
    """Ensure DB is migrated to head before E2E (idempotent after pytest session downgrade)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from alembic import command

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _sync_database_url(DB_URL))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()

    hint = (
        "Hint: after full pytest, fixture migrated_db runs `alembic downgrade base` — "
        "this preflight runs `alembic upgrade head` automatically. "
        "Set CRM_TEST_USE_LOCAL=1 if using docker postgres :5433."
    )

    print(f"preflight: alembic upgrade head (target {head!r})…", file=sys.stderr)
    command.upgrade(cfg, "head")

    engine = create_engine(_sync_database_url(DB_URL))
    try:
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1"),
            ).scalar_one_or_none()
            audit_exists = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'message_reply_audit'"
                    ")",
                ),
            ).scalar()
            cgt_version_col = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'contact_group_transfers' "
                    "AND column_name = 'version'"
                    ")",
                ),
            ).scalar()
            messages_lead_col = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'messages' AND column_name = 'lead_id'"
                    ")",
                ),
            ).scalar()
    finally:
        engine.dispose()

    if version != head:
        print(
            f"alembic upgrade failed: version={version!r}, head={head!r}.\n{hint}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not audit_exists:
        print(
            "Table message_reply_audit is missing (schema below head).\n"
            f"Run: alembic upgrade head\n{hint}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not cgt_version_col:
        print(
            f"contact_group_transfers.version missing (need migration {head!r}).\n"
            f"Run: alembic upgrade head\n{hint}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not messages_lead_col:
        print(
            f"messages.lead_id missing (need migration {head!r}).\n"
            f"Run: alembic upgrade head\n{hint}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"preflight OK: alembic at {head!r}", file=sys.stderr)


def main() -> int:
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    _preflight_db()
    results: list[tuple[str, bool, str]] = []

    try:
        httpx.get(f"{BASE}/healthz", timeout=2.0)
    except Exception as exc:
        print(f"API not reachable at {BASE}: {exc}", file=sys.stderr)
        return 1

    ctx = _seed()
    contact_id = int(ctx["contact_id"])
    chat_g = int(ctx["chat_g"])
    group_g = int(ctx["group_g"])
    group_h = int(ctx["group_h"])
    anya_id = int(ctx["anya_id"])
    boris_id = int(ctx["boris_id"])

    with httpx.Client(timeout=30.0) as client:
        # E2E-6: Boris replies, Anya owner → is_on_behalf=true
        token_boris = _login(client, "e2e.boris@crm.local")
        h_boris = {"Authorization": f"Bearer {token_boris}"}
        print("\n[E2E-6] Boris replies (Anya is card owner)")
        _curl_echo(
            "POST",
            f"{BASE}/api/v1/chats/{chat_g}/messages",
            {**h_boris, "Content-Type": "application/json"},
            json.dumps(
                {"text": "Ответ Бориса", "kind": "text", "idempotency_key": "e2e-on-behalf-1"},
            ).encode(),
        )
        r = client.post(
            f"{BASE}/api/v1/chats/{chat_g}/messages",
            headers=h_boris,
            json={"text": "Ответ Бориса", "kind": "text", "idempotency_key": "e2e-on-behalf-1"},
        )
        ok6 = r.status_code == 202
        audit = client.get(
            f"{BASE}/api/v1/contacts/{contact_id}/groups/{group_g}/reply-audit",
            headers=h_boris,
        )
        if audit.status_code == 200:
            payload = audit.json()
            items = payload.get("items", payload) if isinstance(payload, dict) else payload
            row = items[0] if items else {}
            on_behalf = row.get("is_on_behalf") is True
            owner_ok = row.get("card_owner_user_id") == anya_id
            ok6 = ok6 and on_behalf and owner_ok
            msg = f"audit is_on_behalf={row.get('is_on_behalf')}"
        else:
            msg = f"reply-audit {audit.status_code}"
        results.append(("E2E-6 on_behalf reply-audit", ok6, msg))

        # E2E-7b: Inbound -> owner notify; after timeout -> group (Anya still owner)
        print("\n[E2E-7b] Inbound escalation owner -> group")
        event_id = f"E2EINBOUND{int(time.time())}"
        body, hdrs = _sign_inbound(event_id, "e2e_bot_g", 888001)
        _curl_echo("POST", f"{BASE}/api/v1/bot-events", hdrs, body)
        inbound = client.post(f"{BASE}/api/v1/bot-events", content=body, headers=hdrs)
        ok_esc = inbound.status_code == 202
        if ok_esc:
            asyncio.run(_run_async_jobs(event_id=event_id))
        owner_only = False
        engine = create_engine(_sync_database_url(DB_URL))
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT pending_inbound_at, escalated_to_group_at, owner_user_id
                    FROM contact_group_assignments
                    WHERE contact_id = :cid AND group_id = :gid
                    """,
                ),
                {"cid": contact_id, "gid": group_g},
            ).one()
            owner_only = row.pending_inbound_at is not None and row.escalated_to_group_at is None
            ok_esc = ok_esc and owner_only
        engine.dispose()
        results.append(
            (
                "E2E-7b inbound pending (owner-only phase)",
                ok_esc,
                (
                    f"inbound={inbound.status_code} owner={row.owner_user_id} "
                    f"pending={row.pending_inbound_at is not None}"
                ),
            ),
        )

        engine = create_engine(_sync_database_url(DB_URL))
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE contact_group_assignments
                    SET pending_inbound_at = now() - interval '5 minutes',
                        escalated_to_group_at = NULL
                    WHERE contact_id = :cid AND group_id = :gid
                    """,
                ),
                {"cid": contact_id, "gid": group_g},
            )
        owner_before_scan = row.owner_user_id
        engine.dispose()

        asyncio.run(_run_async_jobs(run_escalation=True))

        engine = create_engine(_sync_database_url(DB_URL))
        with engine.connect() as conn:
            after = conn.execute(
                text(
                    """
                    SELECT escalated_to_group_at, owner_user_id, assignment_source
                    FROM contact_group_assignments
                    WHERE contact_id = :cid AND group_id = :gid
                    """,
                ),
                {"cid": contact_id, "gid": group_g},
            ).one()
        engine.dispose()
        group_escalated = (
            after.escalated_to_group_at is not None
            or after.owner_user_id != owner_before_scan
            or after.assignment_source.startswith("auto_")
        )
        results.append(
            (
                "E2E-7b group escalation after N min",
                group_escalated,
                (
                    f"owner {owner_before_scan}->{after.owner_user_id} "
                    f"source={after.assignment_source}"
                ),
            ),
        )

        # E2E-7: Transfer in group G (reset owners after escalation)
        engine = create_engine(_sync_database_url(DB_URL))
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE contact_group_assignments
                    SET owner_user_id = :anya, pending_inbound_at = NULL,
                        escalated_to_group_at = NULL
                    WHERE contact_id = :cid AND group_id IN (:g, :h)
                    """,
                ),
                {"anya": anya_id, "cid": contact_id, "g": group_g, "h": group_h},
            )
        engine.dispose()

        token_anya = _login(client, "e2e.anya@crm.local")
        token_senior = _login(client, "e2e.senior@crm.local")
        h_anya = {"Authorization": f"Bearer {token_anya}"}
        h_senior = {"Authorization": f"Bearer {token_senior}"}
        print("\n[E2E-7] Transfer card in group G (group H unchanged)")
        tr = client.post(
            f"{BASE}/api/v1/contacts/{contact_id}/groups/{group_g}/transfers",
            headers=h_anya,
            json={"to_user_id": boris_id, "comment": "e2e handoff"},
        )
        ok7 = tr.status_code == 201
        if ok7:
            tid = tr.json()["id"]
            ap = client.post(f"{BASE}/api/v1/contact-transfers/{tid}/approve", headers=h_senior)
            ac = client.post(f"{BASE}/api/v1/contact-transfers/{tid}/accept", headers=h_boris)
            detail = client.get(f"{BASE}/api/v1/contacts/{contact_id}", headers=h_boris)
            if ap.status_code != 200 or ac.status_code != 200 or detail.status_code != 200:
                ok7 = False
                msg = (
                    f"approve={ap.status_code} accept={ac.status_code} "
                    f"detail={detail.status_code}"
                )
            else:
                ownership_rows = detail.json().get("group_ownership", [])
                og = next(x for x in ownership_rows if x["group_id"] == group_g)
                oh = next(x for x in ownership_rows if x["group_id"] == group_h)
                ok7 = og["owner_user_id"] == boris_id and oh["owner_user_id"] == anya_id
                msg = f"G owner={og['owner_user_id']} H owner={oh['owner_user_id']}"
        else:
            msg = f"transfer {tr.status_code} {tr.text[:120]}"
        results.append(("E2E-7 transfer per-group isolation", ok7, msg))

        # E2E-8: close lead then inbound → new lead_id on second message
        print("\n[E2E-8] Close lead + inbound reopen cycle")
        ts_base = int(time.time())
        event_8a = f"E2ELEAD8A{ts_base}"
        event_8b = f"E2ELEAD8B{ts_base}"
        body_8a, hdrs_8a = _sign_inbound(event_8a, "e2e_bot_g", 888001)
        r_8a = client.post(f"{BASE}/api/v1/bot-events", content=body_8a, headers=hdrs_8a)
        ok8 = r_8a.status_code == 202
        lead_id_1: int | None = None
        if ok8:
            asyncio.run(_run_async_jobs(event_id=event_8a))
            engine = create_engine(_sync_database_url(DB_URL))
            with engine.connect() as conn:
                lead_id_1 = conn.execute(
                    text("SELECT current_lead_id FROM chats WHERE id = :cid"),
                    {"cid": chat_g},
                ).scalar_one()
            engine.dispose()
            if lead_id_1 is not None:
                ok8 = (
                    client.post(
                        f"{BASE}/api/v1/leads/{lead_id_1}/close",
                        headers=h_anya,
                    ).status_code
                    == 200
                )
            else:
                ok8 = False

        body_8b, hdrs_8b = _sign_inbound(event_8b, "e2e_bot_g", 888001)
        r_8b = client.post(f"{BASE}/api/v1/bot-events", content=body_8b, headers=hdrs_8b)
        ok8 = ok8 and r_8b.status_code == 202
        lead_pair: list[int | None] = []
        if ok8:
            asyncio.run(_run_async_jobs(event_id=event_8b))
            engine = create_engine(_sync_database_url(DB_URL))
            with engine.connect() as conn:
                lead_pair = [
                    row[0]
                    for row in conn.execute(
                        text(
                            """
                            SELECT lead_id FROM messages
                            WHERE external_event_id IN (:e1, :e2)
                            ORDER BY id
                            """
                        ),
                        {"e1": event_8a, "e2": event_8b},
                    ).all()
                ]
            engine.dispose()
            ok8 = (
                lead_id_1 is not None
                and len(lead_pair) == 2
                and lead_pair[0] == lead_id_1
                and lead_pair[1] is not None
                and lead_pair[1] != lead_id_1
            )
        results.append(
            (
                "E2E-8 close lead + inbound new lead",
                ok8,
                f"leads={lead_id_1}->{lead_pair}",
            ),
        )

        # E2E-9 (optional): messages tab — filter by lead_id vs full chat
        if os.getenv("QA_E2E_STEP9", "1").lower() not in {"0", "false", "no"}:
            print("\n[E2E-9] Messages scope: lead_id filter vs all chat")
            ok9 = False
            msg9 = "skipped — no leads from E2E-8"
            if ok8 and lead_id_1 is not None and len(lead_pair) == 2:
                open_lead_id = lead_pair[1]
                filtered = client.get(
                    f"{BASE}/api/v1/chats/{chat_g}/messages",
                    headers=h_anya,
                    params={"lead_id": open_lead_id},
                )
                all_msgs = client.get(
                    f"{BASE}/api/v1/chats/{chat_g}/messages",
                    headers=h_anya,
                )
                ok9 = filtered.status_code == 200 and all_msgs.status_code == 200
                if ok9:
                    filt_items = filtered.json().get("items", [])
                    all_items = all_msgs.json().get("items", [])
                    ok9 = (
                        len(filt_items) >= 1
                        and all(item.get("lead_id") == open_lead_id for item in filt_items)
                        and len(all_items) >= len(filt_items)
                    )
                    msg9 = f"filtered={len(filt_items)} all={len(all_items)} lead={open_lead_id}"
                else:
                    msg9 = f"filtered={filtered.status_code} all={all_msgs.status_code}"
            results.append(("E2E-9 messages lead tab (optional)", ok9, msg9))

    print("\n=== E2E results ===")
    all_ok = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok and "optional" not in name.lower():
            all_ok = False
        print(f"{status}\t{name}\t{detail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
