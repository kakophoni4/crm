#!/usr/bin/python3
"""Audit a pinned public community list against our inventory and TLS targets.

Run on CRM as root. No third-party code runs; list entries are data only.
IP/CIDR files are parsed and compared, never expanded into address-range scans.
Probes originate on our VPN nodes and do not establish mobile-ISP reachability.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import ipaddress
import json
import re
import subprocess
import urllib.request
from pathlib import Path

REPOSITORY = 'hxehex/russia-mobile-internet-whitelist'
FILES = ('whitelist.txt', 'ipwhitelist.txt', 'cidrwhitelist.txt')


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'CRM-VPN-read-only-audit'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise ValueError('Public list exceeds audit size limit')
    return data


def entries(data):
    return [line.split('#', 1)[0].strip() for line in data.decode('utf-8-sig').splitlines()
            if line.split('#', 1)[0].strip()]


def domain(value):
    value = value.rstrip('.').lower().encode('idna').decode('ascii')
    if len(value) > 253 or '.' not in value:
        raise ValueError('Invalid DNS name')
    if not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.')):
        raise ValueError('Invalid DNS name')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError('IP address is not a DNS target')


NODE_SCRIPT = r'''
import concurrent.futures,ipaddress,json,socket,ssl,subprocess,time
context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_3
context.set_alpn_protocols(['h2'])
def check(host):
 started=time.monotonic()
 try:
  resolved=subprocess.run(['getent','ahostsv4',host],capture_output=True,text=True,timeout=4)
  addresses=list(dict.fromkeys(line.split()[0] for line in resolved.stdout.splitlines() if line.split()))
  # External list entries must never make us probe internal/private endpoints.
  addresses=[address for address in addresses if ipaddress.ip_address(address).is_global]
  if not addresses:return {'host':host,'valid':False,'error':'NoPublicIPv4'}
  last=None
  for address in addresses[:2]:
   try:
    with socket.create_connection((address,443),timeout=4) as raw:
     with context.wrap_socket(raw,server_hostname=host) as stream:
      return {'host':host,'valid':stream.version()=='TLSv1.3' and stream.selected_alpn_protocol()=='h2',
       'tls':stream.version(),'alpn':stream.selected_alpn_protocol(),'ms':round((time.monotonic()-started)*1000)}
   except Exception as error:last=type(error).__name__
  return {'host':host,'valid':False,'error':last}
 except Exception as error:return {'host':host,'valid':False,'error':type(error).__name__}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for result in pool.map(check,HOSTS):print(json.dumps(result),flush=True)
'''


def survey(node, hosts):
    try:
        result = subprocess.run(['ssh', '-F', '/etc/crm-vpn/ssh_config', 'vpn-' + node['id'], 'python3', '-'],
                                input='HOSTS=' + repr(hosts) + '\n' + NODE_SCRIPT,
                                capture_output=True, text=True, timeout=240)
        if result.returncode:
            return {'node': node['id'], 'error': 'node_survey_failed', 'exit_code': result.returncode,
                    'stderr_flags': {marker: marker in result.stderr.lower() for marker in
                                     ('connection reset', 'connection closed', 'too many', 'permission denied', 'killed', 'traceback', 'syntaxerror')}}
        return {'node': node['id'], 'targets': [json.loads(line) for line in result.stdout.splitlines()]}
    except subprocess.TimeoutExpired:
        return {'node': node['id'], 'error': 'node_survey_timeout'}
    except ValueError:
        return {'node': node['id'], 'error': 'invalid_node_survey_response'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--survey', action='store_true', help='Probe every valid DNS target from every VPN node')
    parser.add_argument('--output', type=Path, default=Path('/var/lib/crm-vpn-control/whitelist-audit'))
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.chmod(0o700)
    commit = json.loads(download('https://api.github.com/repos/' + REPOSITORY + '/commits/main'))['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid repository revision')
    parsed = {}; statistics = {}
    for name in FILES:
        data = download('https://raw.githubusercontent.com/' + REPOSITORY + '/' + commit + '/' + name)
        path = args.output / name; path.write_bytes(data); path.chmod(0o600)
        values = entries(data); valid = []; invalid = 0
        for value in values:
            try:
                valid.append(domain(value) if name == 'whitelist.txt' else
                             ipaddress.ip_address(value) if name == 'ipwhitelist.txt' else ipaddress.ip_network(value, strict=False))
            except (ValueError, UnicodeError):
                invalid += 1
        parsed[name] = list(dict.fromkeys(valid))
        statistics[name] = {'entries': len(values), 'unique_valid': len(parsed[name]), 'invalid': invalid,
                            'sha256': hashlib.sha256(data).hexdigest()}
    nodes = json.loads(Path('/etc/crm-vpn/nodes.json').read_text())['nodes']
    listed_ips = set(parsed['ipwhitelist.txt']); listed_networks = parsed['cidrwhitelist.txt']
    inventory = []
    for node in nodes:
        ips = [ipaddress.ip_address(value) for value in node['ips']]
        inventory.append({'node': node['id'], 'addresses_checked': len(ips),
                          'exact_matches': sum(ip in listed_ips for ip in ips),
                          'subnet_matches': sum(any(ip.version == network.version and ip in network for network in listed_networks) for ip in ips)})
    summary = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'repository': REPOSITORY,
               'revision': commit, 'files': statistics, 'inventory': inventory,
               'broad_subnets': sum(network.prefixlen < (16 if network.version == 4 else 32) for network in listed_networks),
               'mobile_operator_verified': False}
    report = args.output / 'summary.json'; report.write_text(json.dumps(summary)); report.chmod(0o600)
    print(json.dumps(summary), flush=True)
    if not args.survey:
        return
    hosts = parsed['whitelist.txt']; batches = (len(hosts) + 47) // 48
    results_file = args.output / 'tls.jsonl'
    with results_file.open('w') as output:
        results_file.chmod(0o600)
        for index in range(batches):
            batch = hosts[index * 48:(index + 1) * 48]
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes)) as pool:
                results = list(pool.map(lambda node: survey(node, batch), nodes))
            for result in results:
                output.write(json.dumps(result) + '\n')
            output.flush()
            print(json.dumps({'tls_batch': index + 1, 'total_batches': batches,
                              'node_errors': [result['node'] for result in results if 'error' in result]}), flush=True)
    by_host = {host: [] for host in hosts}
    for line in results_file.read_text().splitlines():
        result = json.loads(line)
        for target in result.get('targets', []):
            by_host[target['host']].append({'node': result['node'], **target})
    compatible = [host for host, results in by_host.items() if len(results) == len(nodes) and all(result['valid'] for result in results)]
    summary.update({'tls_hosts_surveyed': len(hosts), 'tls_checks': sum(len(results) for results in by_host.values()),
                    'compatible_on_all_nodes': compatible,
                    'per_node_compatible': {node['id']: sum(target['valid'] for results in by_host.values() for target in results if target['node'] == node['id']) for node in nodes}})
    report.write_text(json.dumps(summary))
    print(json.dumps({key: value for key, value in summary.items() if key != 'compatible_on_all_nodes'} | {'compatible_on_all_nodes_count': len(compatible)}), flush=True)


if __name__ == '__main__':
    main()
