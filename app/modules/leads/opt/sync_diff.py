"""Pure helpers: compare CRM OPT payloads with Mole (1C) filter rows."""

from __future__ import annotations

from typing import Any, Literal

SyncActionKind = Literal["unchanged", "update", "restore", "check", "delete_extra"]

_AMOUNT_TOLERANCE = 0.01


def mole_crm_id(row: dict[str, Any]) -> str | None:
    raw = row.get("CRMid") or row.get("CrmId") or row.get("crm_id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def mole_is_deleted(row: dict[str, Any]) -> bool:
    raw = row.get("Удален")
    if raw is None:
        raw = row.get("Deleted")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes", "да"}
    return False


def _as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _floats_close(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= _AMOUNT_TOLERANCE


def _party_inn(party: object) -> str | None:
    if not isinstance(party, dict):
        return None
    raw = party.get("ИНН") or party.get("INN") or party.get("inn")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _registry_rows(order: dict[str, Any]) -> list[dict[str, Any]]:
    registry = order.get("Реестр") or order.get("Registry") or []
    if not isinstance(registry, list):
        return []
    return [row for row in registry if isinstance(row, dict)]


def mole_has_registry(order: dict[str, Any]) -> bool:
    """True when Mole payload includes registry lines (GET usually does; filter often does not)."""
    return bool(_registry_rows(order))


def _line_snapshot(row: dict[str, Any]) -> tuple[str, str | None, str | None, float | None, float | None, float | None]:
    crm_id = mole_crm_id(row) or ""
    supplier = row.get("Поставщик") or row.get("Supplier")
    inn = _party_inn(supplier)
    doc_date = row.get("ДатаДокумента") or row.get("DocumentDate")
    date_text = str(doc_date).strip()[:10] if doc_date is not None else None
    amount = _as_float(row.get("Сумма") if "Сумма" in row else row.get("Amount"))
    vat = _as_float(row.get("СуммаНДС") if "СуммаНДС" in row else row.get("VatAmount"))
    wo_vat = _as_float(
        row.get("СуммаБезНДС") if "СуммаБезНДС" in row else row.get("AmountWithoutVat"),
    )
    return crm_id, inn, date_text, amount, vat, wo_vat


def mole_period_date(row: dict[str, Any]) -> str | None:
    """Normalize Mole/CRM Период to YYYY-MM-DD (empty / 0001-01-01 → None)."""
    raw = row.get("Период") if "Период" in row else row.get("Period")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    date_part = text[:10]
    if date_part == "0001-01-01":
        return None
    return date_part


def periods_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """True when Mole period equals CRM payload period (or CRM/Mole omitted period)."""
    exp = mole_period_date(expected)
    if exp is None:
        return True
    # Filter rows often omit Период entirely — don't force update from headers alone.
    if "Период" not in actual and "Period" not in actual:
        return True
    act = mole_period_date(actual)
    return act == exp


def registries_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Compare CRM-built payload vs Mole order on registry lines + buyer INN."""
    exp_buyer = _party_inn(expected.get("Покупатель") or expected.get("Buyer"))
    act_buyer = _party_inn(actual.get("Покупатель") or actual.get("Buyer"))
    if exp_buyer and act_buyer and exp_buyer != act_buyer:
        return False

    exp_lines: dict[str, tuple[str, str | None, str | None, float | None, float | None, float | None]] = {}
    for row in _registry_rows(expected):
        snap = _line_snapshot(row)
        if not snap[0]:
            return False
        exp_lines[snap[0]] = snap

    act_lines: dict[str, tuple[str, str | None, str | None, float | None, float | None, float | None]] = {}
    for row in _registry_rows(actual):
        snap = _line_snapshot(row)
        if not snap[0]:
            continue
        act_lines[snap[0]] = snap

    if set(exp_lines) != set(act_lines):
        return False

    for key, exp in exp_lines.items():
        act = act_lines[key]
        if exp[1] and act[1] and exp[1] != act[1]:
            return False
        if exp[2] and act[2] and exp[2] != act[2]:
            return False
        if not _floats_close(exp[3], act[3]):
            return False
        if exp[4] is not None and act[4] is not None and not _floats_close(exp[4], act[4]):
            return False
        if exp[5] is not None and act[5] is not None and not _floats_close(exp[5], act[5]):
            return False
    return True


def content_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Registry + period must both match before sync skips a PUT."""
    return registries_match(expected, actual) and periods_match(expected, actual)


def plan_sync_actions(
    *,
    local_crm_ids: set[str],
    local_payloads: dict[str, dict[str, Any]],
    mole_orders: list[dict[str, Any]],
    soft_deleted_crm_ids: set[str] | None = None,
    protect_crm_ids: set[str] | None = None,
) -> list[tuple[SyncActionKind, str]]:
    """Decide per CRMid what to do. CRM is source of truth for membership + content.

    local_crm_ids / local_payloads: submitted orders to check/update/restore.
    protect_crm_ids: any non-deleted CRM order with crm_id (pending/failed/…) —
    never delete_extra even when not in the submitted sync set.
    soft_deleted_crm_ids: CRM soft-deleted submitted — Mole DELETE (even if missing
    from period filter). UI soft-delete does not call Mole; sync is the cleanup pass.
    """
    mole_by_id: dict[str, dict[str, Any]] = {}
    for row in mole_orders:
        crm_id = mole_crm_id(row)
        if crm_id:
            mole_by_id[crm_id] = row

    protected = set(local_crm_ids) | set(protect_crm_ids or ())
    actions: list[tuple[SyncActionKind, str]] = []
    scheduled_deletes: set[str] = set()

    for crm_id in sorted(local_crm_ids):
        payload = local_payloads[crm_id]
        remote = mole_by_id.get(crm_id)
        if remote is None or mole_is_deleted(remote):
            actions.append(("restore", crm_id))
            continue
        # orders/filter often returns headers only (no Реестр). Comparing then always
        # "mismatches" and sync re-POSTs/PUTs every run → new 1C docs. Defer to GET.
        if not mole_has_registry(remote):
            actions.append(("check", crm_id))
            continue
        if registries_match(payload, remote) and periods_match(payload, remote):
            actions.append(("unchanged", crm_id))
        else:
            actions.append(("update", crm_id))

    for crm_id, remote in sorted(mole_by_id.items()):
        if crm_id in protected:
            continue
        if mole_is_deleted(remote):
            continue
        actions.append(("delete_extra", crm_id))
        scheduled_deletes.add(crm_id)

    # Soft-deleted in CRM: delete in Mole by CRMid even if not in period filter.
    # Skip when filter already shows Удален — no need to DELETE again every sync.
    for crm_id in sorted(soft_deleted_crm_ids or ()):
        if not crm_id or crm_id in protected or crm_id in scheduled_deletes:
            continue
        remote = mole_by_id.get(crm_id)
        if remote is not None and mole_is_deleted(remote):
            continue
        actions.append(("delete_extra", crm_id))
        scheduled_deletes.add(crm_id)

    return actions
