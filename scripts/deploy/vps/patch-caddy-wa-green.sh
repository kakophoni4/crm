#!/usr/bin/env bash
# Patch matrix-caddy Caddyfile: route /green/* on api.* to wa-crm-bridge (host :8766).
#
# Usage (on VPS as root):
#   bash scripts/deploy/vps/patch-caddy-wa-green.sh
#   API_DOMAIN=api.crmkanasha.org bash scripts/deploy/vps/patch-caddy-wa-green.sh
set -euo pipefail

CADDY_CONTAINER="${CADDY_CONTAINER:-matrix-caddy}"
API_DOMAIN="${API_DOMAIN:-api.crmkanasha.org}"
MARKER="# wa-crm-bridge green webhooks"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

require_root() { [[ "$(id -u)" -eq 0 ]] || die "Run as root"; }

find_caddyfile_host() {
  docker inspect "$CADDY_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}'
}

reload_caddy() {
  docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile
  docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile
}

patch_file() {
  local path="$1"
  [[ -f "$path" ]] || die "Caddyfile not found: $path"

  if grep -q "$MARKER" "$path"; then
    info "Already patched ($MARKER)"
    return 0
  fi

  cp "$path" "${path}.bak.$(date +%Y%m%d%H%M%S)"
  info "Backup created; patching $path"

  python3 - "$path" "$API_DOMAIN" "$MARKER" << 'PY'
import re
import sys

path, domain, marker = sys.argv[1:4]
text = open(path, encoding="utf-8").read()

if marker in text:
    sys.exit(0)


def patch_simple(site_header: str, indent: str, target: str, closing: str, start: int, end: int) -> bool:
    global text
    block = (
        f"{site_header}"
        f"{indent}{marker}\n"
        f"{indent}handle /green/* {{\n"
        f"{indent}    reverse_proxy host.docker.internal:8766\n"
        f"{indent}}}\n"
        f"{indent}handle {{\n"
        f"{indent}    reverse_proxy {target}\n"
        f"{indent}}}\n"
        f"{closing}"
    )
    text = text[:start] + block + text[end:]
    return True


#   api.crmkanasha.org {
#       reverse_proxy host.docker.internal:19001
#   }
simple = re.compile(
    rf"({re.escape(domain)}\s*\{{\n)"
    rf"(\s*)reverse_proxy\s+(\S+)\s*\n"
    rf"(\s*\}})",
    re.MULTILINE,
)
m = simple.search(text)
if m:
    patch_simple(m.group(1), m.group(2), m.group(3), m.group(4), m.start(), m.end())
    print(f"Patched simple reverse_proxy block for {domain}")
    open(path, "w", encoding="utf-8").write(text)
    sys.exit(0)

# Site label may differ (import, env) — match API upstream by port 19001.
api_upstream = re.compile(
    r"^(\S+.*\{\n)"  # site address line
    r"((?:[ \t].*\n)*?)"
    r"(\s*)reverse_proxy\s+(\S*19001\S*)\s*\n"
    r"(\s*\})",
    re.MULTILINE,
)
m_api = api_upstream.search(text)
if m_api:
    site = m_api.group(1).strip().split("{", 1)[0].strip()
    patch_simple(m_api.group(1), m_api.group(3), m_api.group(4), m_api.group(5), m_api.start(), m_api.end())
    print(f"Patched API block ({site}) via :19001 upstream")
    open(path, "w", encoding="utf-8").write(text)
    sys.exit(0)

# Already uses handle — insert green handle right after opening brace.
with_handle = re.compile(
    rf"({re.escape(domain)}\s*\{{\n)(\s*)",
    re.MULTILINE,
)
m2 = with_handle.search(text)
if m2:
    indent = m2.group(2)
    insert = (
        f"{indent}{marker}\n"
        f"{indent}handle /green/* {{\n"
        f"{indent}    reverse_proxy host.docker.internal:8766\n"
        f"{indent}}}\n"
    )
    pos = m2.end()
    text = text[:pos] + insert + text[pos:]
    open(path, "w", encoding="utf-8").write(text)
    print(f"Inserted /green handle into {domain} block")
    sys.exit(0)

print(
    f"Could not auto-patch API block in {path}.\n"
    f"Tried domain={domain!r} and reverse_proxy targets containing :19001.\n"
    f"Inspect: grep -nE '19001|crmkanasha|green' {path}\n"
    f"Add manually (see deploy/caddy/api-wa-green-snippet.caddy).",
    file=sys.stderr,
)
sys.exit(1)
PY
}

verify() {
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" \
    -X POST "https://${API_DOMAIN}/green/webhook/whatsapp_supp" \
    -H "Content-Type: application/json" \
    -d '{"typeWebhook":"incomingMessageReceived"}' || true)"
  info "POST https://${API_DOMAIN}/green/webhook/whatsapp_supp → HTTP $code"
  [[ "$code" == "200" ]] || die "Expected HTTP 200 (bridge returns 200 for test payload)"
}

main() {
  require_root
  docker ps --format '{{.Names}}' | grep -qx "$CADDY_CONTAINER" \
    || die "Container $CADDY_CONTAINER is not running"

  local host_path
  host_path="$(find_caddyfile_host)"
  [[ -n "$host_path" ]] || die "Cannot find Caddyfile mount for $CADDY_CONTAINER"

  info "Caddyfile: $host_path"
  patch_file "$host_path"
  reload_caddy
  verify
  info "Done — GREEN API webhooks should reach wa-crm-bridge"
}

main "$@"
