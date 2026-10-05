#!/usr/bin/python3
"""Initialise a fresh VPN node from a sanitised schema/template, never clone users or keys."""
from __future__ import annotations

import copy
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


def run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError('Command failed: ' + args[0])
    return result.stdout


def setup(plan: dict) -> dict:
    db_path = Path('/etc/x-ui/x-ui.db')
    if db_path.exists():
        return {'node': plan['node']['id'], 'status': 'existing_configuration_preserved'}
    node = plan['node']
    Path('/etc/x-ui').mkdir(mode=0o700, exist_ok=True)
    Path('/etc/crm-vpn').mkdir(mode=0o700, exist_ok=True)
    private = {'panel_username': 'crm-' + secrets.token_hex(5),
               'panel_password': secrets.token_urlsafe(32), 'panel_path': '/' + secrets.token_urlsafe(24) + '/',
               'hysteria_password': secrets.token_urlsafe(32), 'obfs_password': secrets.token_urlsafe(32),
               'traffic_stats_secret': secrets.token_urlsafe(32)}
    credentials = Path('/etc/crm-vpn/bootstrap.json')
    # Create with restrictive permissions before writing any secret.
    fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(private, stream)
    with sqlite3.connect(db_path) as db:
        db.executescript(plan['schema'])
        for index, original in enumerate(plan['inbounds']):
            inbound = copy.deepcopy(original)
            inbound['id'] = index + 1
            inbound['user_id'] = 1
            inbound['listen'] = node['ips'][index]
            inbound['remark'] = 'CRM ' + node['id'].upper() + ' Reality ' + str(index + 1)
            inbound['tag'] = 'crm-reality-' + str(index + 1)
            inbound['up'] = inbound['down'] = inbound['total'] = inbound['expiry_time'] = 0
            settings = json.loads(inbound['settings'])
            settings['clients'] = []
            inbound['settings'] = json.dumps(settings)
            stream = json.loads(inbound['stream_settings'])
            output = run(['/usr/local/x-ui/bin/xray-linux-amd64', 'x25519'])
            keys = dict(line.split(': ', 1) for line in output.splitlines() if ': ' in line)
            reality = stream['realitySettings']
            reality['privateKey'] = keys['PrivateKey']
            reality['shortIds'] = [secrets.token_hex(8)]
            reality.setdefault('settings', {})['publicKey'] = keys.get('Password (PublicKey)', keys.get('PublicKey'))
            inbound['stream_settings'] = json.dumps(stream)
            columns = list(inbound)
            db.execute('INSERT INTO inbounds (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', list(inbound.values()))
        db.execute("INSERT INTO settings(key,value) VALUES('webListen','127.0.0.1')")
        db.execute("INSERT INTO settings(key,value) VALUES('subEnable','false')")
    db_path.chmod(0o600)
    run(['/usr/local/x-ui/x-ui', 'setting', '-username', private['panel_username'], '-password', private['panel_password'],
         '-port', '2053', '-listenIP', '127.0.0.1', '-webBasePath', private['panel_path']])
    Path('/etc/systemd/system/x-ui.service').write_text(Path('/usr/local/x-ui/x-ui.service.debian').read_text())
    hysteria = Path('/etc/hysteria')
    hysteria.mkdir(mode=0o700, exist_ok=True)
    run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-days', '365',
         '-keyout', '/etc/hysteria/server.key', '-out', '/etc/hysteria/server.crt',
         '-subj', '/CN=' + node['ips'][2], '-addext', 'subjectAltName=IP:' + node['ips'][2]])
    (hysteria / 'server.key').chmod(0o600)
    config = ('listen: ' + node['ips'][2] + ':8444\n'
              'tls:\n  cert: /etc/hysteria/server.crt\n  key: /etc/hysteria/server.key\n'
              'auth:\n  type: userpass\n  userpass:\n    bootstrap: ' + private['hysteria_password'] + '\n'
              'obfs:\n  type: salamander\n  salamander:\n    password: ' + private['obfs_password'] + '\n'
              'trafficStats:\n  listen: 127.0.0.1:9999\n  secret: ' + private['traffic_stats_secret'] + '\n'
              'ignoreClientBandwidth: true\n'
              'masquerade:\n  type: proxy\n  proxy:\n    url: https://www.cloudflare.com\n    rewriteHost: true\n')
    config_path = hysteria / 'config-8444.yaml'
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(config)
    Path('/etc/systemd/system/hysteria-server-8444.service').write_text(
        '[Unit]\nDescription=CRM Hysteria2 VPN\nAfter=network-online.target\nWants=network-online.target\n'
        '[Service]\nExecStart=/usr/local/bin/hysteria server --config /etc/hysteria/config-8444.yaml\n'
        'Restart=on-failure\nRestartSec=5\nLimitNOFILE=1048576\nUser=root\n'
        '[Install]\nWantedBy=multi-user.target\n')
    # Keep panel/statistics loopback only. Add VPN rules without resetting the existing firewall.
    if Path('/usr/sbin/ufw').exists():
        run(['ufw', 'allow', '443/tcp'])
        run(['ufw', 'allow', '8444/udp'])
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'x-ui', 'hysteria-server-8444'])
    time.sleep(3)
    for name in ('x-ui', 'hysteria-server-8444'):
        run(['systemctl', 'is-active', '--quiet', name])
    return {'node': node['id'], 'status': 'configured', 'vless_ips': node['ips'][:2],
            'hysteria_ip': node['ips'][2], 'panel': '127.0.0.1:2053', 'clients_cloned': 0}


if __name__ == '__main__':
    print(json.dumps(setup(json.load(sys.stdin))))
