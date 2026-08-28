#!/usr/bin/env bash
# Patch matrix-caddy so CRM API streams large share downloads (no 15GB buffer)
# and does not time out during multipart uploads.
#
# Usage (on VPS as root):
#   bash scripts/deploy/vps/patch-caddy-large-share.sh
set -euo pipefail

CADDY_CONTAINER="${CADDY_CONTAINER:-matrix-caddy}"
MARKER="# crm-large-share"

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
  python3 - "$1" "$MARKER" << 'PY'
import re
import sys

path = sys.argv[1]
marker = sys.argv[2]
text = open(path, encoding="utf-8").read()
original = text

block = (
    "reverse_proxy {target} {{\n"
    "{indent}    {marker}\n"
    "{indent}    flush_interval -1\n"
    "{indent}    transport http {{\n"
    "{indent}        read_timeout 24h\n"
    "{indent}        write_timeout 24h\n"
    "{indent}    }}\n"
    "{indent}}}"
)

# Already patched.
if marker in text:
    print("Caddyfile already has large-share proxy settings")
    raise SystemExit(0)

# One-line reverse_proxy to :19001 (not already a block).
simple = re.compile(
    r"^([ \t]*)reverse_proxy[ \t]+(\S*19001\S*)[ \t]*\n(?![ \t]*\{)",
    re.MULTILINE,
)

def replace_simple(match: re.Match[str]) -> str:
    indent, target = match.group(1), match.group(2)
    return block.format(target=target, indent=indent, marker=marker) + "\n"

text, n = simple.subn(replace_simple, text)
if n:
    open(path, "w", encoding="utf-8").write(text)
    print(f"Patched {n} one-line reverse_proxy :19001 block(s)")
    raise SystemExit(0)

# reverse_proxy TARGET { ... } without our marker — inject settings after "{".
braced = re.compile(
    r"^([ \t]*)reverse_proxy[ \t]+(\S*19001\S*)[ \t]*\{[ \t]*\n",
    re.MULTILINE,
)

def replace_braced(match: re.Match[str]) -> str:
    indent, target = match.group(1), match.group(2)
    inner = indent + "    "
    return (
        f"{indent}reverse_proxy {target} {{\n"
        f"{inner}{marker}\n"
        f"{inner}flush_interval -1\n"
        f"{inner}transport http {{\n"
        f"{inner}    read_timeout 24h\n"
        f"{inner}    write_timeout 24h\n"
        f"{inner}}}\n"
    )

text, n = braced.subn(replace_braced, text)
if n:
    open(path, "w", encoding="utf-8").write(text)
    print(f"Patched {n} braced reverse_proxy :19001 block(s)")
    raise SystemExit(0)

print(
    f"Could not find reverse_proxy …:19001 in {path}.\n"
    "Inspect: grep -nE '19001|reverse_proxy' " + path,
    file=sys.stderr,
)
raise SystemExit(1)
PY
}

main() {
  require_root
  docker ps --format '{{.Names}}' | grep -qx "$CADDY_CONTAINER" \
    || die "Container $CADDY_CONTAINER is not running"

  local host_path
  host_path="$(find_caddyfile_host)"
  [[ -n "$host_path" ]] || die "Cannot find Caddyfile mount for $CADDY_CONTAINER"
  [[ -f "$host_path" ]] || die "Caddyfile not found on host: $host_path"

  info "Caddyfile: $host_path"
  if ! grep -q "$MARKER" "$host_path"; then
    cp "$host_path" "${host_path}.bak.$(date +%Y%m%d%H%M%S)"
    info "Backup created"
  fi
  run_python "$host_path"
  reload_caddy
  info "Caddy reloaded. Do not start host nginx — :443 is Caddy/docker-proxy."
}

main "$@"
