#!/usr/bin/python3
"""Install opt-in global admission on the existing CRM VPN nodes, with per-node rollback.

Run on CRM after building xray-crm and deploying control_service.py. Privileged SSH
inventory, node tokens and backups stay in /etc/crm-vpn; never enter Git.
"""
import datetime
import hashlib
import gzip
import json
import secrets
import shlex
import sqlite3
import subprocess
from pathlib import Path


def run(args, data=None, timeout=90):
    process = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if process.returncode:
        raise RuntimeError('remote_operation_failed')
    return process.stdout


def main():
    nodes = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    binary = Path('/opt/crm-vpn/xray-crm').read_bytes()
    agent = Path('/opt/crm-vpn/node_agent.py').read_bytes()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    digest = hashlib.sha256(binary).hexdigest()
    compressed = Path('/opt/crm-vpn/xray-crm.gz')
    compressed.write_bytes(gzip.compress(binary))
    with sqlite3.connect('/var/lib/crm-vpn-control/control.sqlite') as db:
        for node in nodes:
            key = 'lease_token:' + node['id']
            db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', (key, secrets.token_urlsafe(48)))
    for node in nodes:
        ssh = ['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id']]
        current = run([*ssh, 'sha256sum /usr/local/x-ui/bin/xray-linux-amd64 /usr/local/libexec/crm-vpn-agent; test ! -f /etc/crm-vpn/xray-guard.enabled || printf "guard-enabled\\n"']).decode()
        if digest in current and hashlib.sha256(agent).hexdigest() in current and 'guard-enabled' in current:
            print(json.dumps({'node': node['id'], 'global_admission_installed': True, 'already_current': True}), flush=True)
            continue
        version = run([*ssh, '/usr/local/x-ui/bin/xray-linux-amd64 version']).decode().splitlines()[0]
        if not version.startswith('Xray 26.9.9 '):
            raise RuntimeError('unsupported_node_core_version:' + node['id'])
        backup = '/etc/crm-vpn/backups/connection-limits-' + stamp
        run([*ssh, f'install -d -m 700 {backup}; cp -p /usr/local/libexec/crm-vpn-agent {backup}/node_agent.py; cp -p /usr/local/x-ui/bin/xray-linux-amd64 {backup}/xray-linux-amd64; cp -p /etc/crm-vpn/agent.json {backup}/agent.json; test ! -f /etc/crm-vpn/xray-guard.enabled || touch {backup}/guard-enabled'])
        config = json.loads(run([*ssh, 'cat /etc/crm-vpn/agent.json']))
        with sqlite3.connect('/var/lib/crm-vpn-control/control.sqlite') as db:
            config['lease_token'] = db.execute('SELECT value FROM settings WHERE key=?', ('lease_token:' + node['id'],)).fetchone()[0]
        config['lease_url'] = 'https://vpn.bttsrvvrs.org/node/lease/' + node['id']
        try:
            run([*ssh, 'umask 077; cat > /etc/crm-vpn/agent.json'], json.dumps(config).encode())
            run([*ssh, 'cat > /usr/local/libexec/crm-vpn-agent; chmod 755 /usr/local/libexec/crm-vpn-agent'], agent)
            # Prove this node can reach and authenticate against central admission first.
            probe = "import importlib.machinery; a=importlib.machinery.SourceFileLoader('agent','/usr/local/libexec/crm-vpn-agent').load_module(); assert a.central_lease({'action':'heartbeat','leases':[]})['denied']==[]"
            run([*ssh, 'python3 -c ' + shlex.quote(probe)])
            run([*ssh, 'systemctl restart crm-vpn-auth; systemctl is-active --quiet crm-vpn-auth'])
            run(['scp', '-q', '-F', '/etc/crm-vpn/ssh_config', str(compressed), 'vpn-' + node['id'] + ':/etc/crm-vpn/xray-crm.gz'], timeout=180)
            run([*ssh, 'gzip -dc /etc/crm-vpn/xray-crm.gz > /usr/local/x-ui/bin/xray-crm.new; chmod 755 /usr/local/x-ui/bin/xray-crm.new'])
            actual = run([*ssh, 'sha256sum /usr/local/x-ui/bin/xray-crm.new']).decode().split()[0]
            if actual != digest:
                raise RuntimeError('core_checksum_mismatch')
            run([*ssh, '/usr/local/x-ui/bin/xray-crm.new run -test -config /usr/local/x-ui/bin/config.json'])
            run([*ssh, 'touch /etc/crm-vpn/xray-guard.enabled; mv /usr/local/x-ui/bin/xray-crm.new /usr/local/x-ui/bin/xray-linux-amd64; systemctl restart x-ui; sleep 2; systemctl is-active --quiet x-ui; /usr/local/x-ui/bin/xray-linux-amd64 api statssys --server=127.0.0.1:62789 >/dev/null'])
            # Pre-upgrade HY sessions authenticated under the old root UUID must re-admit.
            kick = "import importlib.machinery,re; a=importlib.machinery.SourceFileLoader('agent','/usr/local/libexec/crm-vpn-agent').load_module(); ids=[i for i in a.hy_request('/online') if re.fullmatch(r'[0-9a-f-]{36}',i)]; a.hy_request('/kick',ids) if ids else None"
            run([*ssh, 'python3 -c ' + shlex.quote(kick)])
            print(json.dumps({'node': node['id'], 'global_admission_installed': True, 'core_sha256': digest}), flush=True)
        except Exception:
            run([*ssh, f'cp -p {backup}/xray-linux-amd64 /usr/local/x-ui/bin/xray-linux-amd64; cp -p {backup}/node_agent.py /usr/local/libexec/crm-vpn-agent; cp -p {backup}/agent.json /etc/crm-vpn/agent.json; if [ -f {backup}/guard-enabled ]; then touch /etc/crm-vpn/xray-guard.enabled; else rm -f /etc/crm-vpn/xray-guard.enabled; fi; systemctl restart crm-vpn-auth x-ui'])
            raise RuntimeError('node_upgrade_rolled_back:' + node['id']) from None


if __name__ == '__main__':
    main()
