#!/usr/bin/env bash
# Patch matrix-caddy Caddyfile: route /green/* on API host(s) to wa-crm-bridge (host :8766).
#
# Usage (on VPS as root):
#   bash scripts/deploy/vps/patch-caddy-wa-green.sh
#   API_DOMAIN=api.crmkanasha.org APP_DOMAIN=app.crmkanasha.org bash scripts/deploy/vps/patch-caddy-wa-green.sh
set -euo pipefail

CADDY_CONTAINER="${CADDY_CONTAINER:-matrix-caddy}"
API_DOMAIN="${API_DOMAIN:-api.crmkanasha.org}"
APP_DOMAIN="${APP_DOMAIN:-app.crmkanasha.org}"
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

run_python() {
  python3 - "$@" << 'PY'
import re
import sys

path = sys.argv[1]
api_domain = sys.argv[2]
app_domain = sys.argv[3]
marker = sys.argv[4]
text = open(path, encoding="utf-8").read()
changed = False


def hosts_list(site_line: str) -> list[str]:
    return [h.strip() for h in site_line.strip().removesuffix("{").split(",") if h.strip()]


def add_alias_to_site_line(site_line: str, alias: str) -> str:
    hosts = hosts_list(site_line)
    if alias in hosts:
        return site_line
    return f"{alias}, {site_line.strip().removesuffix('{').strip()} {{\n"


def patch_simple(site_header: str, indent: str, target: str, closing: str, start: int, end: int) -> None:
    global text, changed
    site_header = add_alias_to_site_line(site_header, api_domain)
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
    changed = True


def find_site_line_before_marker() -> int | None:
    lines = text.splitlines(keepends=True)
    marker_idx = next((i for i, line in enumerate(lines) if marker in line), None)
    if marker_idx is None:
        return None
    for i in range(marker_idx, -1, -1):
        if lines[i].strip().endswith("{"):
            return i
    return None


def ensure_aliases() -> None:
    global text, changed
    idx = find_site_line_before_marker()
    if idx is not None:
        lines = text.splitlines(keepends=True)
        new_line = add_alias_to_site_line(lines[idx], api_domain)
        if new_line != lines[idx]:
            lines[idx] = new_line
            text = "".join(lines)
            changed = True
            print(f"Added API alias {api_domain}")
        return

    # No marker yet — try API block by :19001 upstream (simple layout).
    api_upstream = re.compile(
        r"^(\S+.*\{\n)"
        r"((?:[ \t].*\n)*?)"
        r"(\s*)reverse_proxy\s+(\S*19001\S*)\s*\n"
        r"(\s*\})",
        re.MULTILINE,
    )
    m = api_upstream.search(text)
    if not m:
        return
    site = m.group(1)
    new_site = add_alias_to_site_line(site, api_domain)
    if new_site != site:
        text = text[: m.start()] + new_site + text[m.start() + len(site) :]
        changed = True
        print(f"Added API alias {api_domain} to existing API block")

    # Frontend block: first :19090 upstream.
    fe_upstream = re.compile(
        r"^(\S+.*\{\n)"
        r"((?:[ \t].*\n)*?)"
        r"(\s*)reverse_proxy\s+(\S*19090\S*)\s*\n"
        r"(\s*\})",
        re.MULTILINE,
    )
    m_fe = fe_upstream.search(text)
    if not m_fe:
        return
    site_fe = m_fe.group(1)
    new_site_fe = add_alias_to_site_line(site_fe, app_domain)
    if new_site_fe != site_fe:
        text = text[: m_fe.start()] + new_site_fe + text[m_fe.start() + len(site_fe) :]
        changed = True
        print(f"Added app alias {app_domain}")


if marker not in text:
    simple = re.compile(
        rf"({re.escape(api_domain)}\s*\{{\n)"
        rf"(\s*)reverse_proxy\s+(\S+)\s*\n"
        rf"(\s*\}})",
        re.MULTILINE,
    )
    m = simple.search(text)
    if m:
        patch_simple(m.group(1), m.group(2), m.group(3), m.group(4), m.start(), m.end())
        print(f"Patched simple reverse_proxy block for {api_domain}")
    else:
        api_upstream = re.compile(
            r"^(\S+.*\{\n)"
            r"((?:[ \t].*\n)*?)"
            r"(\s*)reverse_proxy\s+(\S*19001\S*)\s*\n"
            r"(\s*\})",
            re.MULTILINE,
        )
        m_api = api_upstream.search(text)
        if m_api:
            site = m_api.group(1).strip().split("{", 1)[0].strip()
            patch_simple(
                m_api.group(1),
                m_api.group(3),
                m_api.group(4),
                m_api.group(5),
                m_api.start(),
                m_api.end(),
            )
            print(f"Patched API block ({site}) via :19001 upstream")
        else:
            with_handle = re.compile(
                rf"({re.escape(api_domain)}\s*\{{\n)(\s*)",
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
                changed = True
                print(f"Inserted /green handle into {api_domain} block")
            else:
                print(
                    f"Could not auto-patch API block in {path}.\n"
                    f"Tried domain={api_domain!r} and reverse_proxy targets containing :19001.\n"
                    f"Inspect: grep -nE '19001|crmkanasha|green' {path}",
                    file=sys.stderr,
                )
                sys.exit(1)

ensure_aliases()

if changed:
    open(path, "w", encoding="utf-8").write(text)
elif marker in text:
    print("No Caddyfile changes needed")
PY
}

patch_file() {
  local path="$1"
  [[ -f "$path" ]] || die "Caddyfile not found: $path"

  if grep -q "$MARKER" "$path"; then
    info "Green route already present"
  else
    cp "$path" "${path}.bak.$(date +%Y%m%d%H%M%S)"
    info "Backup created; patching $path"
  fi

  run_python "$path" "$API_DOMAIN" "$APP_DOMAIN" "$MARKER"
}

verify() {
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" \
    -X POST "https://${API_DOMAIN}/green/webhook/whatsapp_supp" \
    -H "Content-Type: application/json" \
    -d '{"typeWebhook":"incomingMessageReceived"}' || true)"
  info "POST https://${API_DOMAIN}/green/webhook/whatsapp_supp → HTTP $code"
  if [[ "$code" == "200" ]]; then
    return 0
  fi

  info "Diagnose: bridge on host"
  curl -sS -o /dev/null -w "  127.0.0.1:8766 → HTTP %{http_code}\n" \
    -X POST "http://127.0.0.1:8766/green/webhook/whatsapp_supp" \
    -H "Content-Type: application/json" \
    -d '{"typeWebhook":"incomingMessageReceived"}' || true

  info "Diagnose: from inside Caddy container"
  docker exec "$CADDY_CONTAINER" wget -q -S -O /dev/null \
    --post-data='{"typeWebhook":"incomingMessageReceived"}' \
    --header='Content-Type: application/json' \
    "http://host.docker.internal:8766/green/webhook/whatsapp_supp" 2>&1 | head -3 || true

  die "Expected HTTP 200 on https://${API_DOMAIN}/green/webhook/..."
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
