"""Read-only smoke test of Happ JSON using an existing active subscription."""
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import control_service as control


def main():
    with control.database() as db:
        row = db.execute('SELECT * FROM subscriptions WHERE enabled=1 AND expires_at>? ORDER BY created_at LIMIT 1', (time.time(),)).fetchone()
        if row is None:
            raise RuntimeError('No active subscription to verify')
        proxies, _, automatic = control.connection_configs(row, db)
    profiles = control.happ_configs(proxies, automatic)
    environment = {**os.environ, 'XRAY_LOCATION_ASSET': '/opt/crm-vpn/geo'}
    with tempfile.TemporaryDirectory(dir=control.HOME, prefix='happ-check-') as temporary:
        directory = Path(temporary)
        for index, profile in enumerate(profiles):
            path = directory / (str(index) + '.json')
            profile['inbounds'][0]['port'] = 19361
            path.write_text(json.dumps(profile)); path.chmod(0o600)
            result = subprocess.run(['/opt/crm-vpn/bin/xray', 'run', '-test', '-c', str(path)], capture_output=True, env=environment)
            if result.returncode:
                raise RuntimeError('Happ configuration validation failed: ' + result.stderr.decode()[-300:])
        print('All Happ profiles validated with RU geodata', flush=True)
        for failover in (False, True):
            config = profiles[0]
            if failover:
                config['outbounds'][0]['settings']['vnext'][0]['port'] = 1
            config['log']['loglevel'] = 'info'
            path = directory / 'auto.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
            with (directory / 'auto.log').open('w') as log:
                process = subprocess.Popen(['/opt/crm-vpn/bin/xray', 'run', '-c', str(path)], env=environment, stdout=log, stderr=log)
                try:
                    time.sleep(6)
                    result = subprocess.run(['curl', '-sS', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19361', '-o', '/dev/null', '-w', '%{http_code}', 'https://www.gstatic.com/generate_204'], capture_output=True, text=True)
                    assert result.returncode == 0 and result.stdout == '204', 'AUTO failed'
                    result = subprocess.run(['curl', '-sS', '--max-time', '15', '--socks5-hostname', '127.0.0.1:19361', '-o', '/dev/null', '-w', '%{http_code}', 'https://yandex.ru'], capture_output=True, text=True)
                    time.sleep(.5)
                    logs = (directory / 'auto.log').read_text()
                    assert '[socks -> direct]' in logs, 'RU route did not select direct'
                    print(json.dumps({'happ_auto': True, 'first_node_disabled': failover, 'ru_direct_route': True}), flush=True)
                finally:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
        with urllib.request.urlopen(control.PUBLIC + '/sub/' + row['token'] + '?format=clash', timeout=15) as response:
            mihomo = json.load(response)
        mihomo['mixed-port'] = 19362; mihomo['log-level'] = 'info'
        path = directory / 'mihomo.json'; path.write_text(json.dumps(mihomo)); path.chmod(0o600)
        result = subprocess.run(['/opt/crm-vpn/bin/mihomo', '-t', '-d', str(directory), '-f', str(path)], capture_output=True, timeout=60)
        assert result.returncode == 0, 'Published Mihomo configuration did not validate'
        with (directory / 'mihomo.log').open('w') as log:
            process = subprocess.Popen(['/opt/crm-vpn/bin/mihomo', '-d', str(directory), '-f', str(path)], stdout=log, stderr=log)
            try:
                time.sleep(6)
                result = subprocess.run(['curl', '-sS', '--max-time', '20', '--socks5-hostname', '127.0.0.1:19362', '-o', '/dev/null', '-w', '%{http_code}', 'https://www.gstatic.com/generate_204'], capture_output=True, text=True)
                assert result.returncode == 0 and result.stdout == '204', 'Mihomo AUTO failed'
                subprocess.run(['curl', '-sS', '--max-time', '15', '--socks5-hostname', '127.0.0.1:19362', '-o', '/dev/null', 'https://yandex.ru'], capture_output=True)
                time.sleep(.5)
                logs = (directory / 'mihomo.log').read_text()
                assert 'DIRECT' in logs and 'yandex.ru' in logs, 'Mihomo RU route did not select direct'
                print('Published Mihomo AUTO and RU direct routing passed', flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__ == '__main__':
    main()
