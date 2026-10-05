#!/usr/bin/python3
"""Read-only VPN node telemetry. Intended as an SSH forced command; no secrets leave node."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path


def command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    return result.stdout.strip()


def collect() -> dict[str, object]:
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0]) * 1024
    cpu = [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    interfaces = {}
    for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
        name, values = line.split(':', 1)
        name = name.strip()
        if name == 'lo' or name.startswith(('veth', 'br-', 'docker', 'tun', 'wg')):
            continue
        fields = values.split()
        interfaces[name] = {'rx_bytes': int(fields[0]), 'tx_bytes': int(fields[8]),
                            'rx_drops': int(fields[3]), 'tx_drops': int(fields[11])}
    services = {}
    for name in ('x-ui', 'hysteria-server-8444'):
        services[name] = command(['systemctl', 'is-active', name]) == 'active'
    sockets = command(['ss', '-Hnt', 'state', 'established', '( sport = :443 )'])
    traffic: dict[str, object] = {'available': False}
    database = Path('/etc/x-ui/x-ui.db')
    if database.exists():
        try:
            with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True, timeout=2) as db:
                rows = db.execute('SELECT enable, up, down, last_online FROM client_traffics').fetchall()
            traffic = {'available': True, 'configured_clients': len(rows),
                       'enabled_clients': sum(bool(row[0]) for row in rows),
                       'recent_clients': sum(int(row[3] or 0) > (time.time() - 120) * 1000 for row in rows),
                       'upload_bytes': sum(int(row[1] or 0) for row in rows),
                       'download_bytes': sum(int(row[2] or 0) for row in rows)}
        except (sqlite3.Error, ValueError):
            traffic = {'available': False, 'error': 'panel_statistics_unavailable'}
    disk = shutil.disk_usage('/')
    pressure = {}
    for resource in ('cpu', 'memory', 'io'):
        path = Path('/proc/pressure') / resource
        if path.exists():
            pressure[resource] = path.read_text().strip()
    return {'schema_version': 1, 'timestamp': time.time(), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'cpu_count': os.cpu_count(), 'cpu_total': sum(cpu), 'cpu_idle': cpu[3] + cpu[4],
            'cpu_steal': cpu[7], 'load_average': os.getloadavg(),
            'memory_total_bytes': memory['MemTotal'], 'memory_available_bytes': memory.get('MemAvailable', memory['MemFree']),
            'disk_total_bytes': disk.total, 'disk_free_bytes': disk.free,
            'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
            'interfaces': interfaces, 'services': services, 'vpn_tcp_connections': len(sockets.splitlines()) if sockets else 0,
            'xray_traffic': traffic, 'pressure': pressure}


if __name__ == '__main__':
    print(json.dumps(collect(), separators=(',', ':')))
