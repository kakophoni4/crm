#!/usr/bin/python3
"""Pilot additional TLS names on an existing 443 entry without moving ingress.

The loopback HAProxy routes only REALITY origin handshakes. Public listeners,
keys, paths and client source addresses are preserved. Run as root on CRM;
backups stay private on the selected VPN node. This is not proof of ISP access.
"""
import argparse
import base64
import json
import subprocess
from pathlib import Path

try:
    from .install_operator_fallbacks import NODE_SCRIPT
except ImportError:
    from install_operator_fallbacks import NODE_SCRIPT

TARGETS = {
    'MAX HTTPS QQ': 'max.ru',
    'Tilda HTTPS QQ': 'video.tilda.cc',
    'VK CDN HTTPS QQ': 'sun9-64.userapi.com',
}


SHARED_NODE_SCRIPT = r'''
def main_shared(plan):
    state=Path('/etc/crm-vpn'); agent_path=Path('/usr/local/libexec/crm-vpn-agent')
    agent_bytes=base64.b64decode(plan['agent']); compile(agent_bytes,str(agent_path),'exec')
    agent=importlib.machinery.SourceFileLoader('shared_agent',str(agent_path)).load_module()
    config=json.loads((state/'agent.json').read_text())
    entry=next(item for item in agent.panel('inbounds/list') if item.get('tag')=='crm-operator-fallback')
    reality=entry['streamSettings']['realitySettings']
    if entry['port']!=443 or entry['listen'] not in plan['ips'] or entry['streamSettings']['network']!='xhttp':
        raise RuntimeError('unexpected_original_entry')
    existing=config.get('restricted_shared_inbounds',{}).get(str(entry['id']))
    original_target=existing['origin'] if existing else reality.get('target',reality.get('dest'))
    original_name=reality['serverNames'][0]
    if original_target!=original_name+':443':raise RuntimeError('original_target_requires_review')
    targets=[original_name,*plan['targets'].values()]
    if any(not re.fullmatch(r'[a-z0-9.-]{1,253}',host) for host in targets):raise RuntimeError('invalid_tls_name')
    for host in targets:
        for _ in range(3):
            for attempt in range(3):
                try:
                    target_ok(host);break
                except (OSError,ssl.SSLError):
                    if attempt==2:raise RuntimeError('preflight_tls_failed:'+host) from None
                    time.sleep(.5)
    unit=Path('/etc/systemd/system/crm-vpn-reality-target.service')
    ha=Path('/etc/haproxy/crm-vpn-reality.cfg')
    if (unit.exists() or ha.exists()) and not existing:raise RuntimeError('existing_router_requires_review')
    if not existing:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:probe.bind(('127.0.0.1',14443))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=state/'backups'/('shared-reality-'+stamp);backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    with sqlite3.connect('/etc/x-ui/x-ui.db') as source,sqlite3.connect(backup/'x-ui.db') as destination:source.backup(destination)
    (backup/'x-ui.db').chmod(0o600)
    fields=('id','enable','listen','port','protocol','settings','streamSettings','sniffing','tag','remark','expiryTime','total')
    original={key:copy.deepcopy(entry[key]) for key in fields if key in entry}
    saved=backup/'original-inbound.json';saved.write_text(json.dumps(original));saved.chmod(0o600)
    paths=(state/'agent.json',agent_path,ha,unit);existed=[path.exists() for path in paths]
    for index,path in enumerate(paths):
        if path.exists():shutil.copy2(path,backup/str(index));(backup/str(index)).chmod(0o600)
    was_active=run(['systemctl','is-active','--quiet','crm-vpn-reality-target'],False).returncode==0
    changed=False
    try:
        if not shutil.which('haproxy'):
            installed=subprocess.run(['env','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','--no-install-recommends','haproxy'],capture_output=True,text=True,timeout=180)
            if installed.returncode:
                diagnostic=backup/'package-install.log';diagnostic.write_text(installed.stdout+installed.stderr);diagnostic.chmod(0o600)
                raise RuntimeError('haproxy_install_failed')
            run(['systemctl','disable','--now','haproxy'])
        lines=['global','    nbthread 1','    maxconn 128','defaults','    mode tcp',
            '    timeout connect 5s','    timeout client 30s','    timeout server 30s',
            'resolvers system_dns','    parse-resolv-conf','    resolve_retries 2',
            '    timeout resolve 1s','    timeout retry 1s','    hold valid 30s',
            'frontend reality_origin','    bind 127.0.0.1:14443','    tcp-request inspect-delay 2s',
            '    acl hello req.ssl_hello_type 1','    acl allowed req.ssl_sni -i '+' '.join(targets),
            '    tcp-request content reject if hello !allowed','    tcp-request content accept if hello']
        for index,host in enumerate(targets):
            lines += ['    acl origin_'+str(index)+' req.ssl_sni -i '+host,
                      '    use_backend tls_'+str(index)+' if origin_'+str(index)]
        for index,host in enumerate(targets):
            # Resolve asynchronously; libc startup resolution can stall binding.
            lines += ['backend tls_'+str(index),'    server origin '+host+':443 resolvers system_dns resolve-prefer ipv4 init-addr none']
        ha.parent.mkdir(parents=True,exist_ok=True)
        candidate=ha.with_suffix('.new');candidate.write_text('\n'.join(lines)+'\n');candidate.chmod(0o644)
        validated=subprocess.run(['/usr/sbin/haproxy','-c','-f',str(candidate)],capture_output=True,text=True,timeout=10)
        if validated.returncode:
            diagnostic=backup/'router-validation.log';diagnostic.write_text(validated.stdout+validated.stderr);diagnostic.chmod(0o600)
            raise RuntimeError('router_config_invalid')
        os.replace(candidate,ha)
        unit.write_text('[Unit]\nDescription=CRM VPN loopback REALITY TLS origin router\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=simple\nUser=haproxy\nGroup=haproxy\nExecStart=/usr/sbin/haproxy -W -db -f /etc/haproxy/crm-vpn-reality.cfg\nRestart=on-failure\nRestartSec=2\nNoNewPrivileges=true\nPrivateTmp=true\nProtectHome=true\nProtectSystem=strict\nMemoryMax=64M\nTasksMax=32\n[Install]\nWantedBy=multi-user.target\n')
        run(['systemctl','daemon-reload']);run(['systemctl','enable','crm-vpn-reality-target']);run(['systemctl','restart','crm-vpn-reality-target'])
        run(['systemctl','is-active','--quiet','crm-vpn-reality-target'])
        # systemd can report Type=simple active before HAProxy binds its socket.
        for attempt in range(50):
            try:
                with socket.create_connection(('127.0.0.1',14443),timeout=.2):break
            except OSError:
                if attempt==49:raise RuntimeError('router_not_listening') from None
                time.sleep(.1)
        # Validate every SNI through the router before changing the live entry.
        context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_3;context.set_alpn_protocols(['h2'])
        for host in targets:
            for attempt in range(10):
                try:
                    with socket.create_connection(('127.0.0.1',14443),timeout=5) as raw:
                        with context.wrap_socket(raw,server_hostname=host) as stream:
                            if stream.version()!='TLSv1.3' or stream.selected_alpn_protocol()!='h2':raise RuntimeError('router_tls_validation_failed')
                    break
                except (OSError,ssl.SSLError):
                    if attempt==9:raise RuntimeError('router_tls_validation_failed') from None
                    time.sleep(.3)
        payload=copy.deepcopy(original);updated=payload['streamSettings']['realitySettings']
        updated['target']='127.0.0.1:14443';updated.pop('dest',None);updated['serverNames']=targets
        changed=True
        agent.panel('inbounds/update/'+str(entry['id']),payload)
        after=next(item for item in agent.panel('inbounds/list') if item['id']==entry['id'])
        actual=after['streamSettings']['realitySettings']
        if actual.get('target',actual.get('dest'))!='127.0.0.1:14443' or actual['serverNames']!=targets:raise RuntimeError('panel_update_not_applied')
        preserved=(after['listen']==entry['listen'] and after['port']==entry['port'] and
                   actual['privateKey']==reality['privateKey'] and actual['shortIds']==reality['shortIds'] and
                   after['streamSettings']['xhttpSettings']==entry['streamSettings']['xhttpSettings'])
        if not preserved:raise RuntimeError('original_parameters_changed')
        config.setdefault('restricted_shared_inbounds',{})[str(entry['id'])]={'origin':original_target,
            'variants':[{'brand':brand,'target':host,'fingerprint':'chrome','test_profile':True} for brand,host in plan['targets'].items()]}
        candidate=(state/'agent.json').with_suffix('.new');candidate.write_text(json.dumps(config));candidate.chmod(0o600);os.replace(candidate,state/'agent.json')
        candidate=agent_path.with_suffix('.new');candidate.write_bytes(agent_bytes);candidate.chmod(0o755);os.replace(candidate,agent_path)
        run(['/usr/local/x-ui/bin/xray-linux-amd64','run','-test','-config','/usr/local/x-ui/bin/config.json'])
        run(['/usr/local/x-ui/bin/xray-linux-amd64','api','statssys','--server=127.0.0.1:62789'])
        for name in ('x-ui','crm-vpn-auth','hysteria-server-8444','crm-vpn-reality-target'):run(['systemctl','is-active','--quiet',name])
        print(json.dumps({'node':plan['id'],'tcp_port':443,'variants':len(plan['targets']),
                          'public_listener_keys_path_preserved':preserved,'router_loopback_only':True}),flush=True)
    except Exception as error:
        if changed:
            try:agent.panel('inbounds/update/'+str(entry['id']),original)
            except Exception:raise RuntimeError('shared_router_restore_requires_review') from None
        if not was_active:run(['systemctl','disable','--now','crm-vpn-reality-target'],False)
        for index,path in enumerate(paths):
            if existed[index]:
                shutil.copy2(backup/str(index),path)
                path.chmod(0o755 if path==agent_path else 0o644 if path in (ha,unit) else 0o600)
            elif path.exists():path.unlink()
        run(['systemctl','daemon-reload'])
        if was_active:run(['systemctl','restart','crm-vpn-reality-target'])
        reason=str(error) if re.fullmatch(r'[a-z0-9_]{1,80}',str(error)) else type(error).__name__
        raise RuntimeError('shared_router_rolled_back:'+reason) from None
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True, help='One inventory node for a separately verified pilot')
    parser.add_argument('--exclude-target', action='append', choices=list(TARGETS.values()), default=[])
    args = parser.parse_args()
    nodes = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    node = next((node for node in nodes if node['id'] == args.node), None)
    if not node:
        parser.error('Unknown inventory node')
    plan = {key: node[key] for key in ('id', 'ips')}
    selected={brand:host for brand,host in TARGETS.items() if host not in args.exclude_target}
    if not selected:
        parser.error('At least one TLS target is required')
    plan.update(targets=selected, agent=base64.b64encode(Path('/opt/crm-vpn/node_agent.py').read_bytes()).decode())
    source = NODE_SCRIPT + SHARED_NODE_SCRIPT + '\nmain_shared(' + repr(plan) + ')\n'
    result = subprocess.run(['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id'], 'python3', '-'],
                            input=source, capture_output=True, text=True, timeout=300)
    if result.returncode:
        reasons = ('unexpected_original_entry', 'original_target_requires_review', 'existing_router_requires_review',
                   'haproxy_install_failed', 'router_config_invalid', 'router_not_listening', 'router_tls_validation_failed', 'panel_update_not_applied',
                   'original_parameters_changed', 'shared_router_restore_requires_review', 'shared_router_rolled_back')
        import re
        rollback = re.search(r'shared_router_rolled_back:([a-zA-Z0-9_]{1,80})', result.stderr)
        preflight = re.search(r'preflight_tls_failed:([a-z0-9.-]{1,253})', result.stderr)
        reason = ('preflight_tls_failed:' + preflight[1] if preflight else
                  'shared_router_rolled_back:' + rollback[1] if rollback else
                  next((value for value in reasons if value in result.stderr), 'remote_operation_failed'))
        raise SystemExit('Shared TLS pilot failed on ' + node['id'] + ': ' + reason)
    print(result.stdout.strip(), flush=True)


if __name__ == '__main__':
    main()
