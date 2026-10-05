#!/usr/bin/python3
"""Collect VPN telemetry via restricted SSH into atomically replaced public snapshots."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import subprocess
import time
from pathlib import Path

CONFIG = Path('/etc/crm-vpn/nodes.json')
STATE = Path('/var/lib/crm-vpn/state')
SSH_CONFIG = '/var/lib/crm-vpn/.ssh/config'
log = logging.getLogger('crm-vpn-monitor')


def probe(node: dict, previous: dict | None) -> dict:
    started = time.monotonic()
    row = {key: node[key] for key in ('id', 'name', 'host', 'ips', 'capacity_mbps')}
    row['checked_at'] = time.time()
    try:
        result = subprocess.run(['ssh', '-F', SSH_CONFIG, 'vpn-' + node['id']],
                                capture_output=True, text=True, timeout=15, check=True)
        current = json.loads(result.stdout)
        row.update(status='online', raw=current, ssh_round_trip_ms=round((time.monotonic() - started) * 1000, 1))
        row['cpu_percent'] = None
        row['network_rx_mbps'] = None
        row['network_tx_mbps'] = None
        row['cpu_steal_percent'] = None
        row['memory_percent'] = round(100 * (1 - current['memory_available_bytes'] / current['memory_total_bytes']), 2)
        row['disk_percent'] = round(100 * (1 - current['disk_free_bytes'] / current['disk_total_bytes']), 2)
        prior = (previous or {}).get('raw')
        if prior and prior['boot_id'] == current['boot_id']:
            elapsed = current['timestamp'] - prior['timestamp']
            total = current['cpu_total'] - prior['cpu_total']
            idle = current['cpu_idle'] - prior['cpu_idle']
            if total > 0 and 0 < elapsed < 300:
                row['cpu_percent'] = round(max(0, min(100, 100 * (total - idle) / total)), 2)
                row['cpu_steal_percent'] = round(max(0, 100 * (current['cpu_steal'] - prior['cpu_steal']) / total), 2)
                for direction in ('rx', 'tx'):
                    delta = sum(max(0, data[direction + '_bytes'] - prior['interfaces'][name][direction + '_bytes'])
                                for name, data in current['interfaces'].items() if name in prior['interfaces'])
                    row['network_' + direction + '_mbps'] = round(delta * 8 / elapsed / 1_000_000, 3)
        capacity = node.get('capacity_mbps')
        peak = max(row['network_rx_mbps'] or 0, row['network_tx_mbps'] or 0)
        row['network_percent'] = round(peak / capacity * 100, 2) if capacity else None
        services = current['services']
        row['vpn_ready'] = all(services.values())
        reasons = []
        if not row['vpn_ready']:
            reasons.append('vpn_service_unavailable')
        if row['cpu_percent'] is None:
            reasons.append('warming_up')
        if (row['cpu_percent'] or 0) >= 85:
            reasons.append('high_cpu')
        if row['memory_percent'] >= 90:
            reasons.append('high_memory')
        if row['disk_percent'] >= 95:
            reasons.append('disk_full')
        if (row['network_percent'] or 0) >= 85:
            reasons.append('high_network')
        if (row['cpu_steal_percent'] or 0) >= 15:
            reasons.append('high_cpu_steal')
        row['placement_block_reasons'] = reasons
        row['eligible_for_new_users'] = not reasons
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        row.update(status='offline', vpn_ready=False, eligible_for_new_users=False,
                   placement_block_reasons=['telemetry_unavailable'])
        log.warning('Node %s unavailable', node['id'])
    return row


def cycle() -> dict:
    config = json.loads(CONFIG.read_text())
    previous = {}
    try:
        previous = {row['id']: row for row in json.loads((STATE / 'snapshot.json').read_text())['nodes']}
    except (FileNotFoundError, ValueError, KeyError):
        pass
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        rows = list(pool.map(lambda node: probe(node, previous.get(node['id'])), config['nodes']))
    snapshot = {'schema_version': 1, 'collected_at': time.time(), 'poll_interval_seconds': config['poll_interval_seconds'], 'nodes': rows}
    temporary = STATE / 'snapshot.tmp'
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False))
    temporary.chmod(0o644)
    os.replace(temporary, STATE / 'snapshot.json')
    day = time.strftime('%Y-%m-%d', time.gmtime())
    with (STATE / ('history-' + day + '.jsonl')).open('a', encoding='utf-8') as stream:
        compact = {**snapshot, 'nodes': [{key: value for key, value in row.items() if key != 'raw'} for row in rows]}
        stream.write(json.dumps(compact, ensure_ascii=False) + '\n')
    for path in STATE.glob('history-*.jsonl'):
        if path.stat().st_mtime < time.time() - 7 * 86400:
            path.unlink()
    return snapshot


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    STATE.mkdir(parents=True, exist_ok=True)
    while True:
        begin = time.monotonic()
        try:
            snapshot = cycle()
            log.info('Collected %s/%s nodes', sum(row['status'] == 'online' for row in snapshot['nodes']), len(snapshot['nodes']))
        except Exception:
            log.exception('Collection failed')
        time.sleep(max(1, 30 - (time.monotonic() - begin)))
