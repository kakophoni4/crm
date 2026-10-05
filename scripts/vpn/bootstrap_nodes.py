#!/usr/bin/python3
"""Run on CRM as root after pinned SSH setup. Fresh nodes only; PL/RS never overwritten."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

SSH = ['ssh', '-F', '/etc/crm-vpn/ssh_config']
ROOT = Path('/opt/crm-vpn')


def remote(node: str, command: str, *, data: bytes | None = None, timeout: int = 120) -> bytes:
    result = subprocess.run([*SSH, 'vpn-' + node, command], input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Remote operation failed on ' + node + ': ' + result.stderr.decode(errors='replace')[:200])
    return result.stdout


def main(apply: bool) -> None:
    config = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())
    fresh = []
    for node in config['nodes']:
        exists = remote(node['id'], 'test -f /etc/x-ui/x-ui.db && printf existing || printf fresh').decode()
        print(json.dumps({'node': node['id'], 'configuration': exists, 'apply': apply}), flush=True)
        if exists == 'fresh':
            fresh.append(node)
    if not apply or not fresh:
        return
    # Same verified versions as PL; configuration and private credentials are excluded.
    archive = remote('pl', 'tar -czf - -C /usr/local x-ui/x-ui x-ui/x-ui.service.debian x-ui/bin/xray-linux-amd64 x-ui/bin/geoip.dat x-ui/bin/geosite.dat', timeout=180)
    hysteria = remote('pl', 'cat /usr/local/bin/hysteria')
    template_code = """import sqlite3,json
db=sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True)
schema=';\\n'.join(row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"))+';'
db.row_factory=sqlite3.Row
inbounds=[dict(row) for row in db.execute('SELECT * FROM inbounds WHERE protocol=\"vless\" ORDER BY id LIMIT 2')]
for inbound in inbounds:
 settings=json.loads(inbound['settings']);settings['clients']=[];inbound['settings']=json.dumps(settings)
 stream=json.loads(inbound['stream_settings']);r=stream['realitySettings'];r['privateKey']='';r['shortIds']=[];r.setdefault('settings',{})['publicKey']='';inbound['stream_settings']=json.dumps(stream)
print(json.dumps({'schema':schema,'inbounds':inbounds}))
"""
    template = json.loads(remote('pl', "python3 - <<'PY'\n" + template_code + '\nPY'))
    if len(template['inbounds']) != 2:
        raise RuntimeError('Expected two VLESS Reality templates on PL')
    for node in fresh:
        remote(node['id'], 'tar -xzf - -C /usr/local', data=archive, timeout=180)
        remote(node['id'], 'install -d -m 755 /usr/local/bin; cat > /usr/local/bin/hysteria; chmod 755 /usr/local/bin/hysteria', data=hysteria)
        remote(node['id'], 'cat > /root/crm-vpn-node-setup.py; chmod 700 /root/crm-vpn-node-setup.py', data=(ROOT / 'node_setup.py').read_bytes())
        result = remote(node['id'], 'python3 /root/crm-vpn-node-setup.py', data=json.dumps({**template, 'node': node}).encode())
        print(result.decode(), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
