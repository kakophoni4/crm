#!/usr/bin/python3
"""Install the pinned RTC supervisor on VPN nodes; no payload travels through CRM."""
import datetime
import hashlib
import json
import subprocess
from pathlib import Path


def run(args, data=None, timeout=180):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('remote_operation_failed')
    return result.stdout


UNIT = '''[Unit]
Description=CRM VPN private olcRTC rooms
After=network-online.target crm-vpn-auth.service
Wants=network-online.target
[Service]
User=crm-vpn-rtc
Group=crm-vpn-rtc
ExecStart=/usr/local/libexec/crm-vpn-olcrtc /var/lib/crm-vpn-rtc/rooms.json
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
MemoryMax=512M
TasksMax=512
LimitNOFILE=65536
[Install]
WantedBy=multi-user.target
'''


def main():
    nodes = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    source = Path('/opt/crm-vpn')
    binary = (source / 'crm-vpn-olcrtc').read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for node in nodes:
        ssh = ['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id']]
        backup = '/etc/crm-vpn/backups/olcrtc-' + stamp
        run([*ssh, f'install -d -m 700 {backup}; cp -p /usr/local/libexec/crm-vpn-agent {backup}/node_agent.py'])
        try:
            run([*ssh, 'getent group crm-vpn-rtc >/dev/null || groupadd --system crm-vpn-rtc; id crm-vpn-rtc >/dev/null 2>&1 || useradd --system --gid crm-vpn-rtc --no-create-home --shell /usr/sbin/nologin crm-vpn-rtc; install -d -o root -g crm-vpn-rtc -m 750 /var/lib/crm-vpn-rtc; test -f /var/lib/crm-vpn-rtc/rooms.json || printf "[]" > /var/lib/crm-vpn-rtc/rooms.json; chown root:crm-vpn-rtc /var/lib/crm-vpn-rtc/rooms.json; chmod 640 /var/lib/crm-vpn-rtc/rooms.json'])
            run([*ssh, 'cat > /usr/local/libexec/crm-vpn-olcrtc.new; chmod 755 /usr/local/libexec/crm-vpn-olcrtc.new'], binary)
            actual = run([*ssh, 'sha256sum /usr/local/libexec/crm-vpn-olcrtc.new']).decode().split()[0]
            if actual != digest:
                raise RuntimeError('binary_checksum_mismatch')
            run([*ssh, 'mv /usr/local/libexec/crm-vpn-olcrtc.new /usr/local/libexec/crm-vpn-olcrtc'])
            run([*ssh, 'install -d -m 755 /usr/local/share/crm-vpn-olcrtc'])
            for name in ('UPSTREAM_LICENSE', 'UPSTREAM_NOTICE'):
                run([*ssh, 'cat > /usr/local/share/crm-vpn-olcrtc/' + name + '; chmod 644 /usr/local/share/crm-vpn-olcrtc/' + name], (source / name).read_bytes())
            run([*ssh, 'cat > /usr/local/libexec/olcrtc_node.py; chmod 644 /usr/local/libexec/olcrtc_node.py'], (source / 'olcrtc_node.py').read_bytes())
            run([*ssh, 'cat > /usr/local/libexec/crm-vpn-agent; chmod 755 /usr/local/libexec/crm-vpn-agent'], (source / 'node_agent.py').read_bytes())
            run([*ssh, 'python3 -m py_compile /usr/local/libexec/olcrtc_node.py /usr/local/libexec/crm-vpn-agent'])
            run([*ssh, 'cat > /etc/systemd/system/crm-vpn-olcrtc.service'], UNIT.encode())
            run([*ssh, 'systemctl daemon-reload; systemctl restart crm-vpn-auth; systemctl enable --now crm-vpn-olcrtc; systemctl is-active --quiet crm-vpn-auth crm-vpn-olcrtc x-ui hysteria-server-8444'])
            print(json.dumps({'node': node['id'], 'rtc_installed': True, 'sha256': digest}), flush=True)
        except Exception:
            run([*ssh, f'systemctl stop crm-vpn-olcrtc; cp -p {backup}/node_agent.py /usr/local/libexec/crm-vpn-agent; systemctl restart crm-vpn-auth'])
            raise RuntimeError('rtc_install_rolled_back:' + node['id']) from None


if __name__ == '__main__':
    main()
