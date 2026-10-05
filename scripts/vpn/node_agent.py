#!/usr/bin/python3
"""Restricted JSON-over-SSH provisioning; loopback Hysteria authentication server."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = Path('/etc/crm-vpn')


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def database():
    connection = sqlite3.connect(STATE / 'clients.sqlite', timeout=20, factory=ManagedConnection)
    connection.execute('CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, password TEXT NOT NULL, expiry REAL NOT NULL, enabled INTEGER NOT NULL)')
    return connection


def panel(path, body=None):
    config = json.loads((STATE / 'agent.json').read_text())
    request = urllib.request.Request(config['panel_url'] + '/panel/api/' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + config['panel_token'], 'Content-Type': 'application/json'})
    # TLS panel certificates may be self-signed. The API is reached only over loopback.
    context = ssl._create_unverified_context() if config['panel_url'].startswith('https:') else None
    with urllib.request.urlopen(request, timeout=20, context=context) as response:
        result = json.load(response)
    if not result.get('success'):
        raise RuntimeError('panel_operation_failed')
    return result.get('obj')


def sync(body):
    identity = str(uuid.UUID(body['id']))
    expiry = float(body['expires_at'])
    if not 0 < expiry < 4102444800:
        raise ValueError('invalid_expiry')
    if not isinstance(body['enabled'], bool) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', body['password']):
        raise ValueError('invalid_credentials')
    config = json.loads((STATE / 'agent.json').read_text())
    email = 'crm-vpn-' + identity
    client = {'email': email, 'id': identity, 'subId': identity.replace('-', ''),
              'enable': body['enabled'], 'expiryTime': int(expiry * 1000), 'totalGB': 0,
              'limitIp': 0, 'limitHwid': 0, 'flow': '', 'tgId': 0, 'comment': 'CRM VPN'}
    # Existence is determined locally without masking authentication/API failures as "absent".
    db = sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True)
    exists = db.execute('SELECT 1 FROM clients WHERE email=?', (email,)).fetchone()
    db.close()
    if exists:
        panel('clients/update/' + email, client)
    else:
        panel('clients/add', {'client': client, 'inboundIds': config['inbound_ids']})
    with database() as connection:
        connection.execute('INSERT INTO clients VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET password=excluded.password,expiry=excluded.expiry,enabled=excluded.enabled',
                           (identity, body['password'], expiry, int(body['enabled'])))
    if not body['enabled'] or expiry <= time.time():
        hy_request('/kick', [identity])
    return {'synced': True}


def delete(body):
    identity = str(uuid.UUID(body['id']))
    email = 'crm-vpn-' + identity
    db = sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True)
    exists = db.execute('SELECT 1 FROM clients WHERE email=?', (email,)).fetchone()
    db.close()
    # This operation can remove only CRM-managed UUID clients, never legacy accounts.
    if exists:
        panel('clients/del/' + email, {})
    with database() as connection:
        connection.execute('DELETE FROM clients WHERE id=?', (identity,))
    hy_request('/kick', [identity])
    return {'deleted': True}


def hy_request(path, body=None):
    config = json.loads((STATE / 'agent.json').read_text())
    request = urllib.request.Request('http://127.0.0.1:9999' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': config['stats_secret'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        value = response.read()
    return json.loads(value) if value else {}


def usage():
    db = sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True)
    rows = db.execute("SELECT email,SUM(up),SUM(down),MAX(last_online) FROM client_traffics WHERE email LIKE 'crm-vpn-%' GROUP BY email").fetchall()
    db.close()
    result = {email.removeprefix('crm-vpn-'): {'up': up or 0, 'down': down or 0, 'last_online': last or 0}
              for email, up, down, last in rows}
    traffic = hy_request('/traffic')
    online = hy_request('/online')
    for identity, values in traffic.items():
        if not re.fullmatch(r'[0-9a-f-]{36}', identity):
            continue
        row = result.setdefault(identity, {'up': 0, 'down': 0, 'last_online': 0})
        # Keep independent protocol counters so an HY restart cannot cancel an Xray delta.
        row['hy_up'] = values.get('tx', 0)
        row['hy_down'] = values.get('rx', 0)
        row['hy_online'] = online.get(identity, 0)
    return {'users': result}


class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.path != '/auth' or not 0 < size <= 8192:
                raise ValueError('invalid_request')
            body = json.loads(self.rfile.read(size))
            credential = str(body.get('auth', ''))
            config = json.loads((STATE / 'agent.json').read_text())
            legacy = config.get('legacy_auth', {})
            identity, separator, password = credential.partition(':')
            allowed = False
            with database() as connection:
                row = connection.execute('SELECT password,expiry,enabled FROM clients WHERE id=?', (identity,)).fetchone()
            if row and separator:
                allowed = bool(row[2]) and row[1] > time.time() and hmac.compare_digest(row[0], password)
            if not allowed:
                if legacy.get('type') == 'password' and hmac.compare_digest(str(legacy.get('password', '')), credential):
                    allowed, identity = True, 'legacy'
                elif legacy.get('type') == 'userpass':
                    stored = legacy.get('userpass', {}).get(identity)
                    allowed = bool(stored) and hmac.compare_digest(str(stored), password)
                    identity = 'legacy-' + identity
            encoded = json.dumps({'ok': allowed, 'id': identity if allowed else ''}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception:
            self.send_error(400)


def install():
    import os
    import yaml
    STATE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect('/etc/x-ui/x-ui.db')
    settings = dict(db.execute('SELECT key,value FROM settings'))
    inbounds = [(identity, json.loads(stream)) for identity, stream in db.execute("SELECT id,stream_settings FROM inbounds WHERE protocol='vless' AND enable=1")]
    db.close()
    config_path = STATE / 'agent.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not config.get('panel_token'):
        output = subprocess.check_output(['/usr/local/x-ui/x-ui', 'setting', '-getApiToken', '-tokenName', 'crm-vpn'], text=True)
        config['panel_token'] = output.split('apiToken:')[-1].strip()
    scheme = 'https' if settings.get('webCertFile') or settings.get('webCert') else 'http'
    config['panel_url'] = scheme + '://127.0.0.1:' + str(settings.get('webPort', '2053')) + '/' + settings.get('webBasePath', '').strip('/')
    config['panel_url'] = config['panel_url'].rstrip('/')
    config['inbound_ids'] = [identity for identity, stream in inbounds if stream.get('security') == 'reality']
    if len(config['inbound_ids']) != 2:
        raise RuntimeError('unexpected_inbound_layout')
    hy_path = Path('/etc/hysteria/config-8444.yaml')
    original = hy_path.read_text()
    hy = yaml.safe_load(original)
    config.setdefault('legacy_auth', hy.get('auth', {}))
    import secrets
    config.setdefault('stats_secret', secrets.token_urlsafe(32))
    backup = STATE / 'hysteria-before-crm.yaml'
    if not backup.exists():
        backup.write_text(original); backup.chmod(0o600)
    hy['auth'] = {'type': 'http', 'http': {'url': 'http://127.0.0.1:9898/auth'}}
    hy['trafficStats'] = {'listen': '127.0.0.1:9999', 'secret': config['stats_secret']}
    config_path.write_text(json.dumps(config)); config_path.chmod(0o600)
    with database():
        pass
    (STATE / 'clients.sqlite').chmod(0o600)
    # Validate panel access before changing the running Hysteria config.
    panel('inbounds/list')
    service = Path('/etc/systemd/system/crm-vpn-auth.service')
    service.write_text('[Unit]\nDescription=CRM VPN local authentication\nAfter=network.target\n[Service]\nExecStart=/usr/bin/python3 /usr/local/libexec/crm-vpn-agent --auth\nRestart=always\nRestartSec=2\nUMask=0077\nNoNewPrivileges=true\nProtectSystem=strict\nReadWritePaths=/etc/crm-vpn\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'crm-vpn-auth'], check=True)
    if yaml.safe_load(original) != hy:
        temporary = hy_path.with_suffix('.tmp')
        temporary.write_text(yaml.safe_dump(hy, sort_keys=False)); temporary.chmod(0o600)
        os.replace(temporary, hy_path)
        subprocess.run(['systemctl', 'restart', 'hysteria-server-8444'], check=True)
    print(json.dumps({'installed': True, 'inbounds': len(config['inbound_ids'])}))


def metadata():
    import yaml
    db = sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True)
    config = json.loads((STATE / 'agent.json').read_text())
    endpoints = []
    for identity, host, port, settings in db.execute("SELECT id,listen,port,stream_settings FROM inbounds WHERE protocol='vless' AND enable=1"):
        if identity not in config['inbound_ids']:
            continue
        stream = json.loads(settings); reality = stream['realitySettings']
        output = subprocess.check_output(['/usr/local/x-ui/bin/xray-linux-amd64', 'x25519', '-i', reality['privateKey']], text=True)
        public = re.search(r'(?:Password \(PublicKey\)|PublicKey):\s*(\S+)', output).group(1)
        endpoints.append({'type': 'vless', 'server': host, 'port': port, 'public_key': public,
                          'sni': reality['serverNames'][0], 'short_id': reality['shortIds'][0],
                          'network': stream['network'], 'xhttp': stream.get('xhttpSettings', {})})
    db.close()
    hy = yaml.safe_load(Path('/etc/hysteria/config-8444.yaml').read_text())
    cert = Path(hy['tls']['cert']).read_text()
    der = base64.b64decode(''.join(cert.strip().splitlines()[1:-1]))
    host, port = hy['listen'].rsplit(':', 1)
    endpoints.append({'type': 'hysteria2', 'server': host, 'port': int(port),
                      'obfs': hy.get('obfs', {}).get('salamander', {}).get('password', ''),
                      'pin': hashlib.sha256(der).hexdigest()})
    return {'endpoints': endpoints}


if __name__ == '__main__':
    if sys.argv[1:] == ['--install']:
        install()
    elif sys.argv[1:] == ['--auth']:
        ThreadingHTTPServer(('127.0.0.1', 9898), AuthHandler).serve_forever()
    else:
        try:
            body = json.loads(sys.stdin.buffer.read(65537))
            operation = body.get('operation')
            result = sync(body) if operation == 'sync' else delete(body) if operation == 'delete' else metadata() if operation == 'metadata' else usage() if operation == 'usage' else None
            if result is None:
                raise ValueError('invalid_operation')
            print(json.dumps({'ok': True, **result}))
        except Exception:
            # Never expose provider credentials, command output, or bearer tokens to callers.
            print(json.dumps({'ok': False, 'error': 'node_operation_failed'}))
            sys.exit(1)
