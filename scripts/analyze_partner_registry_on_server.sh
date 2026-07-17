#!/usr/bin/env bash
# Run partner Forma_zayavki VAT aggregate on VPS (console only).
# Puts xlsx into DIR, copies analyzer into api container, prints report.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${PARTNER_FORMS_DIR:-/tmp/partner-forms}"
API="${CRM_API_CONTAINER:-crm-staging-api}"

mkdir -p "$DIR"
echo "Folder with partner xlsx: $DIR"
echo "Files:"
find "$DIR" -type f \( -iname '*.xlsx' -o -iname '*.xlsm' \) | head -50
count=$(find "$DIR" -type f \( -iname '*.xlsx' -o -iname '*.xlsm' \) | wc -l)
echo "Total xlsx: $count"
if [[ "$count" -eq 0 ]]; then
  echo "Put Forma_zayavki-style files into $DIR and re-run." >&2
  exit 1
fi

docker cp "$ROOT/scripts/analyze_partner_registry.py" "$API:/tmp/analyze_partner_registry.py"
docker cp "$DIR" "$API:/tmp/partner-forms-run"
docker exec -i "$API" python /tmp/analyze_partner_registry.py /tmp/partner-forms-run \
  --by-org --by-file --csv /tmp/partner_vat_summary.csv
docker cp "$API:/tmp/partner_vat_summary.csv" "$DIR/partner_vat_summary.csv" 2>/dev/null || true
echo "CSV (if written): $DIR/partner_vat_summary.csv"
