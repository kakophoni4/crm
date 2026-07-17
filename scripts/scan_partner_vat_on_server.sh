#!/usr/bin/env bash
# One-shot: scan all CRM-stored spreadsheets for partner Forma_zayavki VAT totals.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="${CRM_API_CONTAINER:-crm-staging-api}"

docker cp "$ROOT/scripts/analyze_partner_registry.py" "$API:/tmp/analyze_partner_registry.py"
docker cp "$ROOT/scripts/scan_partner_vat_from_storage.py" "$API:/tmp/scan_partner_vat_from_storage.py"
docker exec -i "$API" python /tmp/scan_partner_vat_from_storage.py
docker cp "$API:/tmp/partner_vat_from_storage.csv" /tmp/partner_vat_from_storage.csv 2>/dev/null || true
echo "Host CSV (if any): /tmp/partner_vat_from_storage.csv"
