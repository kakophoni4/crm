#!/usr/bin/env bash
# Fetch KPP from FNS EGRUL for all lavki in opt_units_vane.json and refresh seed SQL.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
py -3 scripts/opt_enrich_requisites.py --only-missing "$@"
echo "Apply on server: bash scripts/deploy/seed-opt-lavki.sh"
