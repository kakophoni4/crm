#!/usr/bin/python3
"""Exercise all published real endpoints with an ephemeral identity; always remove it.

Run as crm-vpn-control on CRM. No subscriptions, passwords or tokens are printed.
Use --happ-only to exercise published Happ profiles and failover without walking
every standalone transport or testing Mihomo.
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
    if '--happ-only' in sys.argv and '--mihomo' in sys.argv:
        raise SystemExit('Choose --happ-only or --mihomo')
    spec = importlib.util.spec_from_file_location('vpn_check_control', '/opt/crm-vpn/control_service.py')
    control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
    cleanup_nodes = list(control.NODES)
    if '--node' in sys.argv:
        node_id = sys.argv[sys.argv.index('--node') + 1]
        control.NODES = [node for node in control.NODES if node['id'] == node_id]
        if not control.NODES:
            raise SystemExit('Unknown inventory node')
    original_home = control.HOME
    failures = []
    with tempfile.TemporaryDirectory(prefix='live-check-', dir=original_home) as work:
        directory = Path(work); directory.chmod(0o700)
        # Admission is shared across nodes: the identity must exist in the central
        # database, rather than an isolated test DB. No CRM contact is created.
        value = control.create({'contact_id': 2000000000 + secrets.randbelow(100000),
                                'contact_name': 'Ephemeral VPN test', 'days': 1, 'kind': 'gift', 'actor_id': 0})
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
                if view['ready_nodes'] == len(control.NODES) and len(proxies) >= 3 * len(control.NODES): break
                time.sleep(2)
            if view['ready_nodes'] != len(control.NODES) or len(proxies) < 3 * len(control.NODES):
                raise RuntimeError('Not all endpoints were provisioned')
            print(json.dumps({'all_countries': len(control.NODES), 'endpoints': len(proxies), 'provisioning': 'ok'}), flush=True)
            if '--mihomo' in sys.argv:
                secret = secrets.token_urlsafe(32)
                config = directory / 'mihomo.json'
                suffix = '&view=all' if '--expanded' in sys.argv else ''
                with urllib.request.urlopen(control.PUBLIC + '/sub/' + row['token'] + '?format=clash' + suffix, timeout=15) as response:
                    data = json.load(response)
                choices = next(group['proxies'] for group in data['proxy-groups'] if group['name'] == 'VPN')
                data.update({'mixed-port': 19351, 'external-controller': '127.0.0.1:19350', 'secret': secret})
                # Mihomo reads JSON through YAML: escaped UTF-16 surrogate pairs
                # for flag emoji are rejected, whereas actual UTF-8 is valid.
                config.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8'); config.chmod(0o600)
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
                        for choice in choices:
                            request = urllib.request.Request('http://127.0.0.1:19350/proxies/VPN', method='PUT', data=json.dumps({'name': choice}).encode(),
                                headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
                            with urllib.request.urlopen(request, timeout=5): pass
                            result = subprocess.run(['curl', '--silent', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19351',
                                '--output', '/dev/null', '--write-out', '%{http_code}', 'https://www.gstatic.com/generate_204'],capture_output=True,text=True,timeout=25)
                            ok = result.returncode == 0 and result.stdout == '204'
                            print(json.dumps({'mihomo_choice': choice, 'relay_ok': ok}),flush=True)
                            if not ok:
                                failures.append(choice)
                                print('Mihomo curl diagnostic:', result.returncode, result.stderr[:300], flush=True)
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
                              'realitySettings': {'serverName': proxy['servername'], 'fingerprint': proxy.get('client-fingerprint', 'chrome'),
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
                            text = log_file.read_text().lower()
                            flags = {marker: marker in text for marker in ('authentication failed', 'no recent network activity', 'timeout', 'certificate', 'connection refused', 'failed to initialize')}
                            print(json.dumps({'endpoint_diagnostic': proxy['name'], 'client_exit': process.poll(),
                                              'curl_exit': result.returncode, 'flags': flags}), flush=True)
                            retained = original_home / ('live-endpoint-' + str(index) + '-error.log')
                            for sensitive in (identity, row['password'], proxy.get('obfs-password', '')):
                                if sensitive: text = text.replace(sensitive.lower(), '[redacted]')
                            retained.write_text(text); retained.chmod(0o600)
                    finally:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
            if '--mihomo' not in sys.argv and '--happ-only' not in sys.argv:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1 if '--sequential' in sys.argv else 7) as pool:
                    list(pool.map(check, enumerate(proxies)))
            if '--failover' in sys.argv or '--happ-only' in sys.argv:
                test_happ_failover(control, directory, proxies, automatic, row['token'])
            # Re-read node counters after actual traffic; both protocols must be visible.
            usage_totals = {'up': 0, 'down': 0, 'hy_up': 0, 'hy_down': 0}
            required_metrics = ('up', 'down') if '--happ-only' in sys.argv else tuple(usage_totals)
            for attempt in range(16):
                usage_totals = dict.fromkeys(usage_totals, 0)
                for node in control.NODES:
                    usage = control.node_call(node['id'], {'operation': 'usage'})['users'].get(identity, {})
                    for metric in usage_totals:
                        usage_totals[metric] += usage.get(metric, 0)
                if all(usage_totals[metric] > 0 for metric in required_metrics):
                    break
                # The panel persists Xray traffic on its own periodic schedule.
                time.sleep(2)
            print(json.dumps({'traffic_recorded': {key: value > 0 for key, value in usage_totals.items()}}), flush=True)
            if not all(usage_totals[metric] > 0 for metric in required_metrics):
                failures.append('usage')
        finally:
            control.mutate(identity, {'action': 'revoke', 'actor_id': 0})
            cleanup_failed = []
            # The live reconciler may provision a test identity beyond --node.
            for node in cleanup_nodes:
                try:
                    control.node_call(node['id'], {'operation': 'sync', 'id': identity, 'password': row['password'], 'expires_at': row['expires_at'], 'enabled': False})
                    control.node_call(node['id'], {'operation': 'delete', 'id': identity})
                except Exception:
                    cleanup_failed.append(node['id'])
            print(json.dumps({'test_identity_removed': not cleanup_failed, 'cleanup_failed_nodes': cleanup_failed}), flush=True)
            if cleanup_failed:
                failures.append('cleanup')
            else:
                with control.database() as db:
                    for table in ('connection_leases', 'events', 'deliveries', 'counters', 'usage_state'):
                        db.execute('DELETE FROM ' + table + ' WHERE subscription_id=?', (identity,))
                    db.execute('DELETE FROM subscriptions WHERE id=?', (identity,))
    if failures:
        raise SystemExit('Failed checks: ' + ', '.join(failures))
    print('All published Happ profiles and traffic checks passed' if '--happ-only' in sys.argv else
          'All published VPN relays and per-protocol counters passed', flush=True)


def test_happ_failover(control, directory, proxies, automatic, subscription_token):
    """Real direct relays must survive blocked UDP and three unavailable countries."""
    import copy
    environment = {**os.environ, 'XRAY_LOCATION_ASSET': '/opt/crm-vpn/geo'}
    with urllib.request.urlopen(control.PUBLIC + '/sub/' + subscription_token + '?format=happ', timeout=15) as response:
        profiles = json.load(response)
    for index, profile in enumerate(profiles):
        path = directory / ('happ-validate-' + str(index) + '.json')
        path.write_text(json.dumps(profile)); path.chmod(0o600)
        checked = subprocess.run(['/opt/crm-vpn/bin/xray', 'run', '-test', '-c', str(path)],
                                 capture_output=True, env=environment, timeout=30)
        if checked.returncode:
            raise RuntimeError('Published Happ profile validation failed')
    # Country profiles must carry all methods of that country and relay traffic,
    # rather than silently selecting one fixed endpoint during compaction.
    mode_names = ('⚡ Автовыбор', '🛡️ Автовыбор · белые списки')
    countries_profiles = [profile for profile in profiles if profile['remarks'] not in mode_names]
    for index, profile in enumerate(countries_profiles):
        config = copy.deepcopy(profile); config['inbounds'][0]['port'] = 19371
        path = directory / ('happ-country-' + str(index) + '.json')
        path.write_text(json.dumps(config)); path.chmod(0o600)
        with (directory / ('happ-country-' + str(index) + '.log')).open('w') as log:
            process = subprocess.Popen(['/opt/crm-vpn/bin/xray', 'run', '-c', str(path)], stdout=log, stderr=log, env=environment)
            try:
                time.sleep(3)
                result = subprocess.run(['curl', '-sS', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19371',
                    '-o', '/dev/null', '-w', '%{http_code}', 'https://www.gstatic.com/generate_204'], capture_output=True, text=True, timeout=25)
                if result.returncode or result.stdout != '204':
                    raise RuntimeError('Happ country relay failed: ' + profile['remarks'])
                kind = 'happ_test' if profile['remarks'].startswith('🧪 Тест') else 'happ_country'
                print(json.dumps({kind: profile['remarks'], 'relay_ok': True}), flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
    regular_names, restricted_names = control.split_automatic(proxies, automatic)
    if restricted_names:
        restricted = next(profile for profile in profiles if profile['remarks'] == mode_names[1])
        config = copy.deepcopy(restricted); config['inbounds'][0]['port'] = 19371
        path = directory / 'happ-restricted.json'
        path.write_text(json.dumps(config)); path.chmod(0o600)
        with (directory / 'happ-restricted.log').open('w') as log:
            process = subprocess.Popen(['/opt/crm-vpn/bin/xray', 'run', '-c', str(path)], stdout=log, stderr=log, env=environment)
            try:
                time.sleep(7)
                result = subprocess.run(['curl', '-sS', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19371',
                    '-o', '/dev/null', '-w', '%{http_code}', 'https://www.gstatic.com/generate_204'], capture_output=True, text=True, timeout=25)
                if result.returncode or result.stdout != '204':
                    raise RuntimeError('Happ restricted mode relay failed')
                print(json.dumps({'happ_mode': 'restricted', 'relay_ok': True}), flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
    regular = next(profile for profile in profiles if profile['remarks'] == mode_names[0])
    countries = list(dict.fromkeys(name.split(' · ')[0] for name in regular_names))
    for scenario in ('normal', 'udp_blocked', 'three_countries_blocked'):
        if scenario == 'three_countries_blocked' and len(countries) <= 3:
            print(json.dumps({'happ_failover': scenario, 'skipped': 'requires_at_least_four_countries'}), flush=True)
            continue
        config = copy.deepcopy(regular); config['inbounds'][0]['port'] = 19371
        for name, outbound in zip(regular_names, config['outbounds']):
            blocked = (scenario == 'udp_blocked' and outbound['protocol'] == 'hysteria') or (
                scenario == 'three_countries_blocked' and name.split(' · ')[0] in countries[:3])
            if blocked:
                if outbound['protocol'] == 'vless':
                    outbound['settings']['vnext'][0].update(address='127.0.0.1', port=1)
                else:
                    outbound['settings'].update(address='127.0.0.1', port=1)
        path = directory / ('happ-auto-' + scenario + '.json')
        path.write_text(json.dumps(config)); path.chmod(0o600)
        with (directory / ('happ-auto-' + scenario + '.log')).open('w') as log:
            process = subprocess.Popen(['/opt/crm-vpn/bin/xray', 'run', '-c', str(path)],
                                       stdout=log, stderr=log, env=environment)
            try:
                time.sleep(7)
                result = subprocess.run(['curl', '-sS', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19371',
                                         '-o', '/dev/null', '-w', '%{http_code}', 'https://www.gstatic.com/generate_204'],
                                        capture_output=True, text=True, timeout=25)
                if result.returncode or result.stdout != '204':
                    raise RuntimeError('Happ automatic failover failed: ' + scenario)
                print(json.dumps({'happ_failover': scenario, 'relay_ok': True}), flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__ == '__main__':
    main()
