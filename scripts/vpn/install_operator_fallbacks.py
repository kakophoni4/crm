#!/usr/bin/python3
"""Add direct operator fallbacks without replacing existing keys, IPs or ports.

Run as root on CRM. Backups and credentials remain in private node directories.
The existing Hysteria listener also becomes reachable on UDP/443. A third Reality
entry on its IP uses an independently validated TLS target. Install one node first.
"""
import argparse
import base64
import json
import re
import subprocess
from pathlib import Path


GAMING_TARGETS = {
    'Steam': 'cdn.fastly.steamstatic.com',
    'Riot': 'auth.riotgames.com',
    'Roblox': 'setup.rbxcdn.com',
    'Epic Games': 'static-assets-prod.epicgames.com',
    'Battle.net': 'account.battle.net',
    'EA': 'www.ea.com',
    'Ubisoft': 'staticctf.ubisoft.com',
}

# Passed three TLS 1.3/h2 probes from every inventory node. These are camouflage
# variants, not evidence that a mobile operator permits our destination IPs.
RESTRICTED_TARGETS = {
    'Yandex': 'yandex.ru',
    'Yandex ID': 'passport.yandex.ru',
    'VK': 'vk.com',
    'VK Video': 'vkvideo.ru',
    'Ozon': 'www.ozon.ru',
    'Wildberries': 'www.wildberries.ru',
}

# Public transport characteristics only; no third-party subscription credentials.
# Pilot these independently from XHTTP before extending the selected nodes.
RESTRICTED_TCP_TARGETS = {
    'MAX TCP QQ': {'target': 'max.ru', 'port': 5269},
    'Tilda TCP QQ': {'target': 'video.tilda.cc', 'port': 5222},
    'VK CDN TCP QQ': {'target': 'sun9-64.userapi.com', 'port': 6443},
}


NODE_SCRIPT = r"""
import base64,copy,datetime,hashlib,importlib.machinery,ipaddress,json,os,re,shutil,socket,sqlite3,ssl,subprocess,time
from pathlib import Path
import yaml

def run(args, check=True):
    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
    if check and result.returncode:
        raise RuntimeError('node_command_failed:'+args[0])
    return result

def target_ok(host):
    context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_3;context.set_alpn_protocols(['h2'])
    with socket.create_connection((host,443),timeout=5) as raw:
        with context.wrap_socket(raw,server_hostname=host) as stream:
            if stream.version()!='TLSv1.3' or stream.selected_alpn_protocol()!='h2':
                raise RuntimeError('reality_target_not_compatible')

def main(plan):
    state=Path('/etc/crm-vpn')
    agent_path=Path('/usr/local/libexec/crm-vpn-agent')
    agent_bytes=base64.b64decode(plan['agent'])
    auth_changed=hashlib.sha256(agent_path.read_bytes()).digest()!=hashlib.sha256(agent_bytes).digest()
    compile(agent_bytes,str(agent_path),'exec')
    agent=importlib.machinery.SourceFileLoader('fallback_agent',str(agent_path)).load_module()
    hy=yaml.safe_load(Path('/etc/hysteria/config-8444.yaml').read_text())
    host,port=hy['listen'].rsplit(':',1)
    host=str(ipaddress.IPv4Address(host));port=int(port)
    if host not in plan['ips'] or port!=8444:
        raise RuntimeError('unexpected_hysteria_listener')
    target_ok(plan['target'])
    if not shutil.which('iptables'):
        raise RuntimeError('iptables_unavailable')
    for unit in ('x-ui','hysteria-server-8444','crm-vpn-auth'):
        run(['systemctl','is-active','--quiet',unit])
    existing=agent.panel('inbounds/list')
    entry=next((item for item in existing if item.get('tag')=='crm-operator-fallback'),None)
    if not entry:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            probe.bind((host,443))
    udp=run(['ss','-Huln','sport = :443']).stdout
    if udp.strip():
        raise RuntimeError('udp_443_already_in_use')
    alias=state/'hysteria-443.json'
    service=Path('/etc/systemd/system/crm-vpn-hysteria-443.service')
    manager=Path('/usr/local/libexec/crm-vpn-hysteria-443')
    if any(p.exists() for p in (service,manager,alias)) and not (alias.exists() and manager.exists() and service.exists()):
        raise RuntimeError('incomplete_alias_installation_requires_review')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=state/'backups'/('operator-fallbacks-'+stamp)
    backup.mkdir(mode=0o700,parents=True,exist_ok=True)
    with sqlite3.connect('/etc/x-ui/x-ui.db') as source,sqlite3.connect(backup/'x-ui.db') as destination:
        source.backup(destination)
    paths=[agent_path,state/'agent.json',alias,service,manager]
    existed={str(path):path.exists() for path in paths}
    for index,path in enumerate(paths):
        if path.exists():
            shutil.copy2(path,backup/str(index))
    (backup/'manifest.json').write_text(json.dumps(existed))
    created_id=None
    try:
        alias.write_text(json.dumps({'ip':host,'target_port':port,'public_port':443}));alias.chmod(0o600)
        manager.write_text('''#!/usr/bin/python3
import ipaddress,json,subprocess,sys
from pathlib import Path
c=json.loads(Path('/etc/crm-vpn/hysteria-443.json').read_text())
ip=str(ipaddress.IPv4Address(c['ip']));port=int(c['target_port'])
if c['public_port']!=443 or port!=8444:raise SystemExit('Unexpected alias configuration')
for chain in ('PREROUTING','OUTPUT'):
 rule=[chain,'-p','udp','-d',ip+'/32','--dport','443','-m','comment','--comment','crm-vpn-hy443','-j','DNAT','--to-destination',ip+':'+str(port)]
 exists=subprocess.run(['iptables','-w','-t','nat','-C',*rule],capture_output=True).returncode==0
 if sys.argv[1]=='start' and not exists:subprocess.run(['iptables','-w','-t','nat','-A',*rule],check=True)
 if sys.argv[1]=='stop' and exists:subprocess.run(['iptables','-w','-t','nat','-D',*rule],check=True)
''');manager.chmod(0o755)
        service.write_text('[Unit]\nDescription=CRM VPN Hysteria UDP 443 alias\nAfter=network-online.target ufw.service\nWants=network-online.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/local/libexec/crm-vpn-hysteria-443 start\nExecStop=/usr/local/libexec/crm-vpn-hysteria-443 stop\n[Install]\nWantedBy=multi-user.target\n')
        run(['systemctl','daemon-reload']);run(['systemctl','enable','--now','crm-vpn-hysteria-443'])
        run([str(manager),'start'])  # Restore missing rules after a firewall reload.
        if not entry:
            source=next(item for item in existing if item.get('protocol')=='vless' and item.get('streamSettings',{}).get('security')=='reality')
            payload={key:copy.deepcopy(source[key]) for key in ('enable','listen','port','protocol','settings','streamSettings','sniffing')}
            payload.update(listen=host,port=443,enable=True,remark='CRM operator fallback',tag='crm-operator-fallback',expiryTime=0,total=0)
            clients=payload['settings'].get('clients',[])
            payload['settings']['clients']=[client for client in clients if client.get('email','').startswith('crm-vpn-')]
            reality=payload['streamSettings']['realitySettings']
            keys=run(['/usr/local/x-ui/bin/xray-linux-amd64','x25519']).stdout
            parsed=dict(line.split(': ',1) for line in keys.splitlines() if ': ' in line)
            reality['privateKey']=parsed['PrivateKey'];reality['shortIds']=[os.urandom(8).hex()]
            reality['target']=plan['target']+':443';reality.pop('dest',None);reality['serverNames']=[plan['target']]
            reality.setdefault('settings',{})['publicKey']=parsed.get('Password (PublicKey)',parsed.get('PublicKey'))
            payload['streamSettings']['network']='xhttp'
            payload['streamSettings']['xhttpSettings']={'path':'/assets/'+os.urandom(12).hex(),'mode':'auto'}
            entry=agent.panel('inbounds/add',payload)
            if not entry or not entry.get('id'):
                entry=next(item for item in agent.panel('inbounds/list') if item.get('tag')=='crm-operator-fallback')
            created_id=entry['id']
        config=json.loads((state/'agent.json').read_text())
        if entry['id'] not in config['inbound_ids']:
            config['inbound_ids'].append(entry['id'])
        (state/'agent.json').write_text(json.dumps(config));(state/'agent.json').chmod(0o600)
        candidate=agent_path.with_suffix('.new')
        candidate.write_bytes(agent_bytes);candidate.chmod(0o755);os.replace(candidate,agent_path)
        if auth_changed:
            run(['systemctl','restart','crm-vpn-auth'])
        run(['/usr/local/x-ui/bin/xray-linux-amd64','run','-test','-config','/usr/local/x-ui/bin/config.json'])
        run(['/usr/local/x-ui/bin/xray-linux-amd64','api','statssys','--server=127.0.0.1:62789'])
        for unit in ('x-ui','hysteria-server-8444','crm-vpn-auth','crm-vpn-hysteria-443'):
            run(['systemctl','is-active','--quiet',unit])
        with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True) as db:
            managed=db.execute("SELECT COUNT(*) FROM clients WHERE email LIKE 'crm-vpn-%'").fetchone()[0]
            attached=db.execute("SELECT COUNT(*) FROM client_inbounds ci JOIN clients c ON c.id=ci.client_id WHERE ci.inbound_id=? AND c.email LIKE 'crm-vpn-%'",(entry['id'],)).fetchone()[0]
        if attached!=managed:
            raise RuntimeError('fallback_missing_managed_clients')
        print(json.dumps({'node':plan['id'],'udp_443_alias':True,'original_udp_8444_preserved':True,'extra_reality_target':plan['target'],'managed_clients_attached':True}),flush=True)
    except Exception as error:
        if created_id is not None:
            agent.panel('inbounds/del/'+str(created_id),{})
        if not existed[str(service)]:
            run(['systemctl','disable','--now','crm-vpn-hysteria-443'],check=False)
        for index,path in enumerate(paths):
            if existed[str(path)]:shutil.copy2(backup/str(index),path)
            elif path.exists():path.unlink()
        run(['systemctl','daemon-reload'])
        if auth_changed:
            run(['systemctl','restart','crm-vpn-auth'])
        raise RuntimeError('node_fallbacks_rolled_back:'+type(error).__name__) from None
"""


GAMING_NODE_SCRIPT = r"""
def main_gaming(plan):
    state=Path('/etc/crm-vpn')
    agent_path=Path('/usr/local/libexec/crm-vpn-agent')
    agent_bytes=base64.b64decode(plan['agent'])
    compile(agent_bytes,str(agent_path),'exec')
    agent=importlib.machinery.SourceFileLoader('gaming_agent',str(agent_path)).load_module()
    host=str(ipaddress.IPv4Address(plan['ips'][0]))
    restricted=plan.get('restricted',False)
    raw=plan.get('restricted_tcp',False)
    if raw and not restricted:raise RuntimeError('raw_variant_requires_restricted_mode')
    metadata_key='restricted_inbounds' if restricted else 'gaming_inbounds'
    tag=('crm-restricted-' if restricted else 'crm-game-')+plan['brand'].lower().replace(' ','-').replace('.','-')
    for _ in range(3):target_ok(plan['target'])
    run(['systemctl','is-active','--quiet','x-ui'])
    firewall=run(['iptables','-S','INPUT']).stdout.strip()
    ufw_active=shutil.which('ufw') and run(['ufw','status']).stdout.startswith('Status: active')
    # Support the existing UFW firewall, but never reset it or replace its rules.
    if firewall!='-P INPUT ACCEPT' and not ufw_active:
        raise RuntimeError('gaming_port_requires_firewall_review')
    existing=agent.panel('inbounds/list')
    gaming_ports=(int(plan['port']),) if raw else (8443,*range(8445,8500))
    entry=next((item for item in existing if item.get('tag')==tag or
                (not restricted and item.get('tag')=='crm-game-fallback' and
                 item.get('streamSettings',{}).get('realitySettings',{}).get('serverNames')==[plan['target']])),None)
    if entry:
        port=entry['port']
        reality=entry.get('streamSettings',{}).get('realitySettings',{})
        if entry['listen']!=host or port not in gaming_ports or reality.get('serverNames')!=[plan['target']] or (raw and entry['streamSettings'].get('network')!='tcp'):
            raise RuntimeError('existing_gaming_entry_does_not_match_plan')
    else:
        used={item['port'] for item in existing if item.get('listen') in (host,'','0.0.0.0','::')}
        port=None
        for candidate in gaming_ports:
            if candidate in used:continue
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:probe.bind((host,candidate))
            except OSError as error:
                if error.errno==98:continue
                raise
            port=candidate;break
        if port is None:raise RuntimeError('no_free_gaming_port')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=state/'backups'/('gaming-fallbacks-'+stamp+'-'+tag)
    backup.mkdir(mode=0o700,parents=True,exist_ok=True)
    with sqlite3.connect('/etc/x-ui/x-ui.db') as source,sqlite3.connect(backup/'x-ui.db') as destination:
        source.backup(destination)
    paths=[agent_path,state/'agent.json']
    for index,path in enumerate(paths):shutil.copy2(path,backup/str(index))
    changed=agent_path.read_bytes()!=agent_bytes
    created_id=None
    firewall_added=False
    firewall_rule=['allow','in','to',host,'port',str(port),'proto','tcp','comment','crm-vpn-restricted' if restricted else 'crm-vpn-games']
    try:
        if ufw_active:
            before=run(['ufw','show','added']).stdout
            run(['ufw',*firewall_rule])
            firewall_added=run(['ufw','show','added']).stdout!=before
        if not entry:
            source=next(item for item in existing if item.get('protocol')=='vless' and item.get('streamSettings',{}).get('security')=='reality')
            payload={key:copy.deepcopy(source[key]) for key in ('enable','listen','port','protocol','settings','streamSettings','sniffing')}
            payload.update(listen=host,port=port,enable=True,remark='CRM '+plan['brand']+' TLS fallback',tag=tag,expiryTime=0,total=0)
            payload['settings']['clients']=[client for client in payload['settings'].get('clients',[]) if client.get('email','').startswith('crm-vpn-')]
            keys=run(['/usr/local/x-ui/bin/xray-linux-amd64','x25519']).stdout
            parsed=dict(line.split(': ',1) for line in keys.splitlines() if ': ' in line)
            reality=payload['streamSettings']['realitySettings']
            reality['privateKey']=parsed['PrivateKey'];reality['shortIds']=[os.urandom(8).hex()]
            reality['target']=plan['target']+':443';reality.pop('dest',None);reality['serverNames']=[plan['target']]
            reality.setdefault('settings',{})['publicKey']=parsed.get('Password (PublicKey)',parsed.get('PublicKey'))
            payload['streamSettings']['network']='tcp' if raw else 'xhttp'
            if raw:
                payload['streamSettings'].pop('xhttpSettings',None)
                payload['streamSettings']['tcpSettings']={}
            else:
                payload['streamSettings']['xhttpSettings']={'path':'/assets/'+os.urandom(12).hex(),'mode':'auto'}
            entry=agent.panel('inbounds/add',payload)
            if not entry or not entry.get('id'):
                entry=next(item for item in agent.panel('inbounds/list') if item.get('tag')==tag)
            created_id=entry['id']
        config=json.loads((state/'agent.json').read_text())
        if entry['id'] not in config['inbound_ids']:config['inbound_ids'].append(entry['id'])
        config.setdefault(metadata_key,{})[str(entry['id'])]={'brand':plan['brand'],'target':plan['target']}
        if raw:config[metadata_key][str(entry['id'])].update(fingerprint='chrome',test_profile=True)
        candidate=(state/'agent.json').with_suffix('.new')
        candidate.write_text(json.dumps(config));candidate.chmod(0o600);os.replace(candidate,state/'agent.json')
        candidate=agent_path.with_suffix('.new')
        candidate.write_bytes(agent_bytes);candidate.chmod(0o755);os.replace(candidate,agent_path)
        if changed:run(['systemctl','restart','crm-vpn-auth'])
        run(['/usr/local/x-ui/bin/xray-linux-amd64','run','-test','-config','/usr/local/x-ui/bin/config.json'])
        run(['/usr/local/x-ui/bin/xray-linux-amd64','api','statssys','--server=127.0.0.1:62789'])
        with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True) as db:
            managed=db.execute("SELECT COUNT(*) FROM clients WHERE email LIKE 'crm-vpn-%'").fetchone()[0]
            attached=db.execute("SELECT COUNT(*) FROM client_inbounds ci JOIN clients c ON c.id=ci.client_id WHERE ci.inbound_id=? AND c.email LIKE 'crm-vpn-%'",(entry['id'],)).fetchone()[0]
        if attached!=managed:raise RuntimeError('gaming_missing_managed_clients')
        print(json.dumps({'node':plan['id'],'tls_target':plan['target'],'brand':plan['brand'],'tcp_port':port,'managed_clients_attached':True}),flush=True)
    except Exception as error:
        if created_id is not None:agent.panel('inbounds/del/'+str(created_id),{})
        if firewall_added:run(['ufw','--force','delete',*firewall_rule],check=False)
        for index,path in enumerate(paths):shutil.copy2(backup/str(index),path)
        if changed:run(['systemctl','restart','crm-vpn-auth'])
        raise RuntimeError('gaming_fallback_rolled_back:'+type(error).__name__) from None
"""


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--node',help='Install only this inventory node first')
    variants=parser.add_mutually_exclusive_group()
    variants.add_argument('--gaming',action='store_true',help='Add every surveyed gaming TLS variant on every selected node')
    variants.add_argument('--restricted-network',action='store_true',help='Add surveyed Russian TLS targets; does not guarantee IP allowlist access')
    variants.add_argument('--restricted-tcp',action='store_true',help='Pilot TCP/REALITY with public Russian TLS names; requires --node')
    parser.add_argument('--exclude-target',action='append',choices=[value['target'] for value in RESTRICTED_TCP_TARGETS.values()],default=[])
    args=parser.parse_args()
    if args.restricted_tcp and not args.node:
        parser.error('--restricted-tcp requires --node for a separately verified pilot')
    if args.exclude_target and not args.restricted_tcp:
        parser.error('--exclude-target is supported only with --restricted-tcp')
    nodes=json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    if args.node:
        nodes=[node for node in nodes if node['id']==args.node]
        if not nodes:
            raise SystemExit('Unknown inventory node')
    agent=base64.b64encode(Path('/opt/crm-vpn/node_agent.py').read_bytes()).decode()
    for node in nodes:
        plan={key:node[key] for key in ('id','ips')}
        plan.update(agent=agent,target='www.apple.com' if node['id'] in ('ee','ch','kz') else 'www.microsoft.com')
        if args.restricted_tcp:
            plan.update(restricted=True,restricted_tcp=True)
            selected=[(brand,options) for brand,options in RESTRICTED_TCP_TARGETS.items() if options['target'] not in args.exclude_target]
            source=NODE_SCRIPT+GAMING_NODE_SCRIPT+'\nplan='+repr(plan)+'\nfor brand,options in '+repr(selected)+':\n main_gaming({**plan,"brand":brand,**options})\n'
        elif args.gaming or args.restricted_network:
            plan['restricted']=args.restricted_network
            targets=RESTRICTED_TARGETS if args.restricted_network else GAMING_TARGETS
            source=NODE_SCRIPT+GAMING_NODE_SCRIPT+'\nplan='+repr(plan)+'\nfor brand,target in '+repr(list(targets.items()))+':\n main_gaming({**plan,"brand":brand,"target":target})\n'
        else:
            source=NODE_SCRIPT+'\nmain('+repr(plan)+')\n'
        process=subprocess.run(['ssh','-F','/etc/crm-vpn/ssh_config','vpn-'+node['id'],'python3','-'],input=source,text=True,capture_output=True,timeout=180)
        if process.returncode:
            # Exceptions have fixed public messages; never echo unfiltered remote output.
            public = ('gaming_port_requires_firewall_review', 'existing_gaming_entry_does_not_match_plan',
                      'no_free_gaming_port', 'reality_target_not_compatible', 'gaming_fallback_rolled_back',
                      'node_fallbacks_rolled_back')
            reason=next((value for value in public if value in process.stderr),'remote_operation_failed')
            classes=re.findall(r'^(?:[a-z_]+\.)?([A-Za-z]+Error):',process.stderr,re.MULTILINE)
            frames=re.findall(r'File "<stdin>", line ([0-9]+),',process.stderr)
            kind=classes[-1] if classes else 'UnknownError'
            raise SystemExit('Fallback installation failed or rolled back on '+node['id']+': '+reason+' ('+kind+', source lines '+','.join(frames)+')')
        print(process.stdout.strip(),flush=True)


if __name__=='__main__':
    main()
