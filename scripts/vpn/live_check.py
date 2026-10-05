#!/usr/bin/python3
"""Exercise all 21 real endpoints with an ephemeral identity; always revoke/remove it.

Run as crm-vpn-control on CRM. No subscriptions, passwords or tokens are printed.
"""
import concurrent.futures
import importlib.util
import json
import os
import signal
import socket
import sys
import subprocess
import tempfile
import time
import secrets
import urllib.request
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location('vpn_check_control', '/opt/crm-vpn/control_service.py')
    control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
    original_home = control.HOME
    failures = []
    with tempfile.TemporaryDirectory(prefix='live-check-', dir=original_home) as work:
        directory = Path(work); directory.chmod(0o700)
        (directory / '.ssh').symlink_to(original_home / '.ssh', target_is_directory=True)
        control.HOME = directory; control.initialize()
        value = control.create({'contact_id': 1, 'contact_name': 'Ephemeral VPN test', 'days': 1, 'kind': 'gift', 'actor_id': 1})
        identity = value['id']
        with control.database() as db:
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone()
        try:
            for attempt in range(3):
                with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
                    list(pool.map(control.reconcile_node, control.NODES))
                with control.database() as db:
                    row = db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone()
                    view = control.subscription_view(row, db)
                    proxies, links, automatic = control.connection_configs(row, db)
                if view['ready_nodes'] == 7 and len(proxies) == 21: break
                time.sleep(2)
            if view['ready_nodes'] != 7 or len(proxies) != 21:
                raise RuntimeError('Not all 21 endpoints were provisioned')
            print(json.dumps({'all_countries': 7, 'endpoints': len(proxies), 'provisioning': 'ok'}), flush=True)
            if '--mihomo' in sys.argv:
                secret = secrets.token_urlsafe(32)
                config = directory / 'mihomo.json'
                data = {'mixed-port': 19351, 'external-controller': '127.0.0.1:19350', 'secret': secret,
                        'mode': 'rule', 'log-level': 'warning', 'proxies': proxies,
                        'proxy-groups': [{'name': 'VPN', 'type': 'select', 'proxies': [proxy['name'] for proxy in proxies]}], 'rules': ['MATCH,VPN']}
                config.write_text(json.dumps(data)); config.chmod(0o600)
                validation = subprocess.run(['/opt/crm-vpn/bin/mihomo', '-t', '-d', str(directory), '-f', str(config)], capture_output=True, text=True, timeout=30)
                if validation.returncode:
                    raise RuntimeError('Mihomo rejected exported configuration')
                print('Mihomo configuration validation passed', flush=True)
                with (directory / 'mihomo.log').open('w') as log:
                    process = subprocess.Popen(['/opt/crm-vpn/bin/mihomo', '-d', str(directory), '-f', str(config)], stdout=log, stderr=log)
                    try:
                        for attempt in range(50):
                            try:
                                with socket.create_connection(('127.0.0.1', 19350), timeout=.2): break
                            except OSError: time.sleep(.2)
                        for proxy in proxies:
                            request = urllib.request.Request('http://127.0.0.1:19350/proxies/VPN', method='PUT', data=json.dumps({'name': proxy['name']}).encode(),
                                headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
                            with urllib.request.urlopen(request, timeout=5): pass
                            result = subprocess.run(['curl', '--silent', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19351',
                                '--output', '/dev/null', '--write-out', '%{http_code}', 'https://www.gstatic.com/generate_204'],capture_output=True,text=True,timeout=25)
                            ok = result.returncode == 0 and result.stdout == '204'
                            print(json.dumps({'mihomo_endpoint': proxy['name'], 'relay_ok': ok}),flush=True)
                            if not ok:
                                failures.append(proxy['name'])
                                print('Mihomo curl diagnostic:', result.returncode, result.stderr[:300], flush=True)
                                break
                    finally:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
                if failures:
                    log_text = (directory / 'mihomo.log').read_text()
                    for sensitive in (identity, row['password'], secret):
                        log_text = log_text.replace(sensitive, '[redacted]')
                    retained = original_home / 'mihomo-check-error.log'
                    retained.write_text(log_text); retained.chmod(0o600)
                    print('Mihomo diagnostic:', '\n'.join(log_text.splitlines()[-4:]), flush=True)
            def check(index_proxy):
                index, proxy = index_proxy
                port = 19200 + index
                config = directory / ('client-' + str(index) + '.json')
                if proxy['type'] == 'vless':
                    stream = {'network': proxy['network'], 'security': 'reality',
                              'realitySettings': {'serverName': proxy['servername'], 'fingerprint': 'chrome',
                                                  'publicKey': proxy['reality-opts']['public-key'], 'shortId': proxy['reality-opts']['short-id']}}
                    if proxy['network'] == 'xhttp':
                        stream['xhttpSettings'] = proxy['xhttp-opts']
                    data = {'log': {'loglevel': 'error'}, 'inbounds': [{'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'auth': 'noauth', 'udp': True}}],
                            'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [{'address': proxy['server'], 'port': proxy['port'], 'users': [{'id': identity, 'encryption': 'none'}]}]}, 'streamSettings': stream}]}
                    command = ['/opt/crm-vpn/bin/xray', 'run', '-c', str(config)]
                else:
                    data = {'server': proxy['server'] + ':' + str(proxy['port']), 'auth': proxy['password'],
                            'tls': {'sni': proxy['sni'], 'insecure': True, 'pinSHA256': proxy['fingerprint']},
                            'socks5': {'listen': '127.0.0.1:' + str(port)},
                            'obfs': {'type': proxy['obfs'], 'salamander': {'password': proxy['obfs-password']}}}
                    command = ['/opt/crm-vpn/bin/hysteria', 'client', '-c', str(config)]
                config.write_text(json.dumps(data)); config.chmod(0o600)
                log_file = directory / ('client-' + str(index) + '.log')
                with log_file.open('w') as log:
                    process = subprocess.Popen(command, stdout=log, stderr=log)
                    try:
                        for attempt in range(40):
                            if process.poll() is not None:
                                break
                            try:
                                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                                    break
                            except OSError:
                                time.sleep(.2)
                        result = subprocess.run(['curl', '--silent', '--show-error', '--max-time', '20', '--socks5-hostname', '127.0.0.1:' + str(port),
                                                 '--output', '/dev/null', '--write-out', '%{http_code}', 'https://www.gstatic.com/generate_204'], capture_output=True, text=True, timeout=25)
                        ok = result.returncode == 0 and result.stdout == '204'
                        print(json.dumps({'endpoint': proxy['name'], 'relay_ok': ok, 'http_status': result.stdout}), flush=True)
                        if not ok:
                            failures.append(proxy['name'])
                    finally:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
            if '--mihomo' not in sys.argv:
                with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
                    list(pool.map(check, enumerate(proxies)))
            # Re-read node counters after actual traffic; both protocols must be visible.
            usage_totals = {'up': 0, 'down': 0, 'hy_up': 0, 'hy_down': 0}
            for node in control.NODES:
                usage = control.node_call(node['id'], {'operation': 'usage'})['users'].get(identity, {})
                for metric in usage_totals:
                    usage_totals[metric] += usage.get(metric, 0)
            print(json.dumps({'traffic_recorded': {key: value > 0 for key, value in usage_totals.items()}}), flush=True)
            if not all(value > 0 for value in usage_totals.values()):
                failures.append('usage')
        finally:
            revoked = control.mutate(identity, {'action': 'revoke', 'actor_id': 1})
            cleanup_failed = []
            for node in control.NODES:
                try:
                    control.node_call(node['id'], {'operation': 'sync', 'id': identity, 'password': row['password'], 'expires_at': row['expires_at'], 'enabled': False})
                    control.node_call(node['id'], {'operation': 'delete', 'id': identity})
                except Exception:
                    cleanup_failed.append(node['id'])
            print(json.dumps({'test_identity_removed': not cleanup_failed, 'cleanup_failed_nodes': cleanup_failed}), flush=True)
            if cleanup_failed:
                failures.append('cleanup')
    if failures:
        raise SystemExit('Failed checks: ' + ', '.join(failures))
    print('All 21 VPN relays and per-protocol counters passed', flush=True)


if __name__ == '__main__':
    main()
