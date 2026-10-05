#!/usr/bin/python3
"""Install the restricted provisioning key and node agents from CRM."""
import concurrent.futures
import json
import ipaddress
import os
import pwd
import shlex
import subprocess
from pathlib import Path


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=90, check=True, **kwargs).stdout


def main():
    ssh_source = str(ipaddress.ip_address(os.environ['VPN_CRM_SSH_SOURCE']))
    try:
        account = pwd.getpwnam('crm-vpn-control')
    except KeyError:
        run(['useradd', '--system', '--home-dir', '/var/lib/crm-vpn-control', '--shell', '/usr/sbin/nologin', 'crm-vpn-control'])
        account = pwd.getpwnam('crm-vpn-control')
    home = Path('/var/lib/crm-vpn-control')
    for path in (home, home / '.ssh'):
        path.mkdir(parents=True, exist_ok=True); path.chmod(0o700)
        os.chown(path, account.pw_uid, account.pw_gid)
    key = home / '.ssh/id_ed25519'
    if not key.exists():
        run(['runuser', '-u', account.pw_name, '--', 'ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'crm-vpn-control', '-f', str(key)])
    public = key.with_suffix('.pub').read_text().strip()
    nodes = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    def install(node):
        ssh = ['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id']]
        run([*ssh, 'install -d -m 755 /usr/local/libexec; cat > /usr/local/libexec/crm-vpn-agent; chmod 755 /usr/local/libexec/crm-vpn-agent'], input=Path('/opt/crm-vpn/node_agent.py').read_text())
        run([*ssh, 'python3 /usr/local/libexec/crm-vpn-agent --install'])
        line = f'from="{ssh_source}",restrict,command="/usr/local/libexec/crm-vpn-agent" ' + public
        run([*ssh, 'grep -qF ' + shlex.quote(public.split()[1]) + ' /root/.ssh/authorized_keys || printf \'%s\\n\' ' + shlex.quote(line) + ' >> /root/.ssh/authorized_keys'])
        print(json.dumps({'node': node['id'], 'agent_installed': True}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        list(pool.map(install, nodes))
    config = ('Host vpn-*\n  User root\n  IdentityFile /var/lib/crm-vpn-control/.ssh/id_ed25519\n  IdentitiesOnly yes\n'
              '  BatchMode yes\n  StrictHostKeyChecking yes\n  UserKnownHostsFile /var/lib/crm-vpn-control/.ssh/known_hosts\n  ConnectTimeout 8\n')
    for node in nodes:
        config += '\nHost vpn-' + node['id'] + '\n  HostName ' + node['host'] + '\n'
    for name, content in (('config', config), ('known_hosts', Path('/etc/crm-vpn/known_hosts').read_text())):
        path = home / '.ssh' / name; path.write_text(content); path.chmod(0o600)
        os.chown(path, account.pw_uid, account.pw_gid)
    for node in nodes:
        result = json.loads(run(['runuser', '-u', account.pw_name, '--', 'ssh', '-F', str(home / '.ssh/config'), 'vpn-' + node['id']], input='{"operation":"metadata"}'))
        assert result['ok'] and len(result['endpoints']) == 3
        print(json.dumps({'node': node['id'], 'restricted_key_verified': True}), flush=True)


if __name__ == '__main__':
    main()
