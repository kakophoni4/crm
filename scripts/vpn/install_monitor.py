#!/usr/bin/python3
"""Install telemetry on CRM. Monitoring key can execute only the read-only probe."""
from __future__ import annotations

import json
import ipaddress
import pwd
import shlex
import subprocess
from pathlib import Path


def run(args: list[str], **kwargs) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=30, **kwargs).stdout.strip()


def install() -> None:
    ssh_source = str(ipaddress.ip_address(os.environ['VPN_CRM_SSH_SOURCE']))
    try:
        account = pwd.getpwnam('crm-vpn')
    except KeyError:
        run(['useradd', '--system', '--home-dir', '/var/lib/crm-vpn', '--shell', '/usr/sbin/nologin', 'crm-vpn'])
        account = pwd.getpwnam('crm-vpn')
    home = Path('/var/lib/crm-vpn')
    for path, mode in ((home, 0o755), (home / '.ssh', 0o700), (home / 'state', 0o755)):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
        os.chown(path, account.pw_uid, account.pw_gid)
    key = home / '.ssh/id_ed25519'
    if not key.exists():
        run(['runuser', '-u', 'crm-vpn', '--', 'ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'crm-vpn-monitor', '-f', str(key)])
    public = key.with_suffix('.pub').read_text().strip()
    config = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())
    for node in config['nodes']:
        ssh = ['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id']]
        run([*ssh, 'install -d -m 755 /usr/local/libexec; cat > /usr/local/libexec/crm-vpn-metrics; chmod 755 /usr/local/libexec/crm-vpn-metrics'],
            input=Path('/opt/crm-vpn/node_probe.py').read_text())
        line = f'from="{ssh_source}",restrict,command="/usr/local/libexec/crm-vpn-metrics" ' + public
        run([*ssh, 'grep -qF ' + shlex.quote(public.split()[1]) + ' /root/.ssh/authorized_keys || printf \'%s\\n\' ' + shlex.quote(line) + ' >> /root/.ssh/authorized_keys'])
    ssh_config = ('Host vpn-*\n  User root\n  IdentityFile /var/lib/crm-vpn/.ssh/id_ed25519\n  IdentitiesOnly yes\n'
                  '  BatchMode yes\n  StrictHostKeyChecking yes\n  UserKnownHostsFile /var/lib/crm-vpn/.ssh/known_hosts\n  ConnectTimeout 8\n')
    for node in config['nodes']:
        ssh_config += '\nHost vpn-' + node['id'] + '\n  HostName ' + node['host'] + '\n'
    for name, content in (('config', ssh_config), ('known_hosts', Path('/etc/crm-vpn/known_hosts').read_text())):
        path = home / '.ssh' / name
        path.write_text(content)
        path.chmod(0o600)
        os.chown(path, account.pw_uid, account.pw_gid)
    # Non-secret inventory is readable by the unprivileged collector.
    Path('/etc/crm-vpn').chmod(0o755)
    Path('/etc/crm-vpn/nodes.json').chmod(0o644)
    for node in config['nodes']:
        data = run(['runuser', '-u', 'crm-vpn', '--', 'ssh', '-F', str(home / '.ssh/config'), 'vpn-' + node['id']])
        assert json.loads(data)['schema_version'] == 1
        print(json.dumps({'node': node['id'], 'forced_command_verified': True}), flush=True)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'crm-vpn-monitor'])


if __name__ == '__main__':
    install()
