#!/usr/bin/python3
"""VPN control plane: durable provisioning, subscriptions, usage and Telegram cabinet.

CRM authenticates managers and applies contact scope before calling /internal.
Public reverse proxy must expose only /sub/ and /health, never /internal.
"""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from scripts.vpn import client_guides, olcrtc_control
except ImportError:
    import client_guides
    import olcrtc_control

HOME = Path(os.environ.get('VPN_STATE_DIR', '/var/lib/crm-vpn-control'))
PUBLIC = os.environ.get('VPN_PUBLIC_BASE_URL', 'https://vpn.bttsrvvrs.org').rstrip('/')
API_KEY = os.environ.get('VPN_CONTROL_TOKEN', '')
BOT_TOKEN = os.environ.get('VPN_TELEGRAM_BOT_TOKEN', '')
BOT_USERNAME = ''
BOT_ID = 0
NODES = json.loads(Path(os.environ.get('VPN_NODES_FILE', '/etc/crm-vpn/nodes.json')).read_text())['nodes']
log = logging.getLogger('crm-vpn-control')
WAKE = threading.Event()
BOT_LOCK = threading.Lock()
BOT_CHALLENGES = {}


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def database():
    db = sqlite3.connect(HOME / 'control.sqlite', timeout=30, factory=ManagedConnection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def initialize():
    HOME.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY, contact_id INTEGER NOT NULL, contact_name TEXT NOT NULL,
            telegram_user_id INTEGER, telegram_username TEXT, source_bot_id INTEGER,
            source_bot_name TEXT, kind TEXT NOT NULL, created_by INTEGER NOT NULL,
            expires_at REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            token TEXT UNIQUE NOT NULL, password TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL, updated_at REAL NOT NULL, last_fetch REAL);
        CREATE INDEX IF NOT EXISTS subscriptions_contact ON subscriptions(contact_id);
        CREATE INDEX IF NOT EXISTS subscriptions_telegram ON subscriptions(telegram_user_id);
        CREATE TABLE IF NOT EXISTS deliveries (
            subscription_id TEXT REFERENCES subscriptions(id), node_id TEXT,
            version INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
            checked_at REAL, PRIMARY KEY(subscription_id,node_id));
        CREATE TABLE IF NOT EXISTS endpoints (node_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS counters (
            subscription_id TEXT REFERENCES subscriptions(id), node_id TEXT, metric TEXT,
            last_value INTEGER NOT NULL, total INTEGER NOT NULL, checked_at REAL NOT NULL,
            PRIMARY KEY(subscription_id,node_id,metric));
        CREATE TABLE IF NOT EXISTS usage_state (subscription_id TEXT, node_id TEXT,
            last_online REAL NOT NULL DEFAULT 0, hy_online INTEGER NOT NULL DEFAULT 0,
            checked_at REAL NOT NULL, PRIMARY KEY(subscription_id,node_id));
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, subscription_id TEXT REFERENCES subscriptions(id),
            actor_id INTEGER NOT NULL, action TEXT NOT NULL, at REAL NOT NULL, details TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bot_users (bot_id INTEGER, user_id INTEGER, first_seen REAL,
            last_seen REAL, PRIMARY KEY(bot_id,user_id));
        CREATE TABLE IF NOT EXISTS bot_screens (bot_id INTEGER, user_id INTEGER, message_id INTEGER,
            subscription_id TEXT, updated_at REAL NOT NULL, PRIMARY KEY(bot_id,user_id));
        CREATE TABLE IF NOT EXISTS bot_requests (id INTEGER PRIMARY KEY, contact_id INTEGER,
            subscription_id TEXT, user_id INTEGER NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
            created_at REAL NOT NULL, handled_at REAL, handled_by INTEGER);
        CREATE TABLE IF NOT EXISTS bot_notifications (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
            token TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0, error TEXT,
            created_at REAL NOT NULL);
        ''')
        if 'source_chat_id' not in {row[1] for row in db.execute('PRAGMA table_info(subscriptions)')}:
            db.execute('ALTER TABLE subscriptions ADD COLUMN source_chat_id INTEGER')
        if 'device_limit' not in {row[1] for row in db.execute('PRAGMA table_info(subscriptions)')}:
            db.execute('ALTER TABLE subscriptions ADD COLUMN device_limit INTEGER NOT NULL DEFAULT 3 CHECK(device_limit BETWEEN 3 AND 8)')
        db.execute('''CREATE TABLE IF NOT EXISTS connection_leases (
            lease_id TEXT PRIMARY KEY,node_id TEXT NOT NULL,subscription_id TEXT NOT NULL,
            ip TEXT NOT NULL,created_at REAL NOT NULL,expires_at REAL NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS leases_subscription ON connection_leases(subscription_id,expires_at)')
        if 'deleted_at' not in {row[1] for row in db.execute('PRAGMA table_info(subscriptions)')}:
            db.execute('ALTER TABLE subscriptions ADD COLUMN deleted_at REAL')
        if 'hidden' not in {row[1] for row in db.execute('PRAGMA table_info(subscriptions)')}:
            db.execute('ALTER TABLE subscriptions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0 CHECK(hidden IN (0,1))')
        if 'create_request_key' not in {row[1] for row in db.execute('PRAGMA table_info(subscriptions)')}:
            db.execute('ALTER TABLE subscriptions ADD COLUMN create_request_key TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS subscriptions_request ON subscriptions(create_request_key)')
        if 'requested_days' not in {row[1] for row in db.execute('PRAGMA table_info(bot_requests)')}:
            db.execute('ALTER TABLE bot_requests ADD COLUMN requested_days INTEGER')
        olcrtc_control.initialize(db)
    (HOME / 'control.sqlite').chmod(0o600)


def node_call(node_id, body):
    result = subprocess.run(['ssh', '-F', str(HOME / '.ssh/config'), 'vpn-' + node_id],
                            input=json.dumps(body), capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError('node_unavailable')
    value = json.loads(result.stdout)
    if not value.get('ok'):
        raise RuntimeError('node_operation_failed')
    return value


def snapshot():
    try:
        value = json.loads(Path('/var/lib/crm-vpn/state/snapshot.json').read_text())
        stale = time.time() - value['collected_at'] > 90
        with database() as db:
            overrides = {item['key']: json.loads(item['value']) for item in db.execute("SELECT * FROM settings WHERE key LIKE 'node:%'")}
        for row in value['nodes']:
            row.pop('raw', None)
            override = overrides.get('node:' + row['id'], {})
            row['drained'] = bool(override.get('drained'))
            capacity = override.get('capacity_mbps', row.get('capacity_mbps'))
            row['capacity_mbps'] = capacity
            peak = max(row.get('network_rx_mbps') or 0, row.get('network_tx_mbps') or 0)
            row['network_percent'] = round(peak * 100 / capacity, 2) if capacity else None
            if (row['network_percent'] or 0) >= 85:
                row['eligible_for_new_users'] = False
                if 'high_network' not in row['placement_block_reasons']:
                    row['placement_block_reasons'].append('high_network')
            if row['drained']:
                row['eligible_for_new_users'] = False
                row['placement_block_reasons'].append('maintenance')
            if stale:
                row['eligible_for_new_users'] = False
                row['placement_block_reasons'] = ['stale_telemetry']
        value['stale'] = stale
        return value
    except (OSError, ValueError, KeyError):
        return {'nodes': [], 'stale': True, 'collected_at': None}


def ranked_nodes(identity, metrics):
    """Weighted rendezvous placement: stable per user, spreads similar healthy nodes."""
    eligible = [row for row in metrics['nodes'] if row.get('eligible_for_new_users')]
    def rank(row):
        load = max(row.get('cpu_percent') or 0, row.get('network_percent') or 0,
                   max(0, (row.get('memory_percent') or 0) - 50) * 2)
        weight = max(.05, (100 - load) / 100) ** 2
        digest = hashlib.sha256((identity + ':' + row['id']).encode()).digest()
        uniform = (int.from_bytes(digest[:8], 'big') + 1) / (2**64 + 1)
        return -math.log(uniform) / weight
    return [row['id'] for row in sorted(eligible, key=rank)]


def subscription_view(row, db):
    value = dict(row)
    value.pop('password'); value.pop('token')
    value.pop('create_request_key', None)
    deliveries = [dict(item) for item in db.execute('SELECT node_id,version,status,checked_at FROM deliveries WHERE subscription_id=?', (row['id'],))]
    ready = sum(item['status'] == 'synced' and item['version'] == row['version'] for item in deliveries)
    value['delivery'] = deliveries
    value['ready_nodes'] = ready
    value['total_nodes'] = len(NODES)
    value['status'] = 'expired' if row['expires_at'] <= time.time() else 'revoked' if not row['enabled'] else 'active' if ready == len(NODES) else 'provisioning'
    value['subscription_url'] = PUBLIC + '/sub/' + row['token']
    value['happ_url'] = value['subscription_url'] + '?format=happ'
    value['clash_url'] = value['subscription_url'] + '?format=clash'
    value['raw_url'] = value['subscription_url'] + '?format=raw'
    value['guide_url'] = value['subscription_url'] + '?format=guide'
    value['v2rayng_url'] = value['subscription_url'] + '?format=v2rayng'
    value['ghostlane_url'] = value['subscription_url'] + '?format=ghostlane'
    value['recommended_nodes'] = ranked_nodes(row['id'], snapshot())
    counters = [dict(item) for item in db.execute('SELECT node_id,metric,total,checked_at FROM counters WHERE subscription_id=?', (row['id'],))]
    value['upload_bytes'] = sum(item['total'] for item in counters if item['metric'] in ('up', 'hy_up', 'rtc_up'))
    value['download_bytes'] = sum(item['total'] for item in counters if item['metric'] in ('down', 'hy_down', 'rtc_down'))
    value['usage_by_node'] = counters
    value['online'] = [dict(item) for item in db.execute('SELECT * FROM usage_state WHERE subscription_id=?', (row['id'],))]
    value['occupied_slots'] = db.execute('''SELECT COUNT(DISTINCT ip) FROM connection_leases
        WHERE subscription_id=? AND expires_at>?''', (row['id'], time.time())).fetchone()[0]
    return value


def issuance_state(db, contact_id, telegram_user_id=None):
    condition = 'contact_id=?'
    parameters = [int(contact_id)]
    if telegram_user_id is not None:
        condition += ' OR telegram_user_id=?'
        parameters.append(int(telegram_user_id))
    rows = db.execute('SELECT * FROM subscriptions WHERE hidden=0 AND (' + condition + ') ORDER BY created_at DESC', parameters).fetchall()
    existing = [row for row in rows if row['deleted_at'] is None]
    current = next((row for row in existing if row['enabled'] and row['expires_at'] > time.time()), existing[0] if existing else None)
    used = any(row['kind'] == 'trial' for row in rows)
    return {'can_create': current is None, 'trial_available': current is None and not used,
            'trial_used': used, 'current_subscription_id': current['id'] if current else None}


def connection_lease(node_id, body):
    """Atomic admission shared by every node and both VPN protocols. Never bans an IP globally."""
    lease_id = str(uuid.UUID(body['lease_id']))
    action = body['action']
    if action not in ('acquire', 'renew', 'release'):
        raise ValueError('invalid_lease_action')
    now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT * FROM connection_leases WHERE lease_id=?', (lease_id,)).fetchone()
        if prior and prior['node_id'] != node_id:
            raise ValueError('lease_owner_mismatch')
        if action == 'release':
            db.execute('DELETE FROM connection_leases WHERE lease_id=? AND node_id=?', (lease_id, node_id))
            return {'allowed': False}
        identity = str(uuid.UUID(body['subscription_id']))
        address = ipaddress.ip_address(body['ip'])
        ip = str(address.ipv4_mapped or address) if isinstance(address, ipaddress.IPv6Address) else str(address)
        if prior and (prior['subscription_id'] != identity or prior['ip'] != ip):
            raise ValueError('lease_identity_mismatch')
        if action == 'renew' and (not prior or prior['expires_at'] <= now):
            return {'allowed': False}
        db.execute('DELETE FROM connection_leases WHERE expires_at<=?', (now,))
        row = db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone()
        allowed = bool(row and row['enabled'] and row['deleted_at'] is None and row['expires_at'] > now)
        if allowed:
            active = [item[0] for item in db.execute('''SELECT ip FROM connection_leases WHERE subscription_id=?
                AND expires_at>? GROUP BY ip ORDER BY MIN(created_at),ip''', (identity, now))]
            allowed = ip in active[:row['device_limit']] or (ip not in active and len(active) < row['device_limit'])
        if not allowed:
            db.execute('DELETE FROM connection_leases WHERE lease_id=?', (lease_id,))
            return {'allowed': False}
        db.execute('''INSERT INTO connection_leases VALUES(?,?,?,?,?,?) ON CONFLICT(lease_id)
            DO UPDATE SET expires_at=excluded.expires_at''', (lease_id, node_id, identity, ip, now, now + 45))
        return {'allowed': True, 'ttl': 45}


def event(db, identity, actor, action, details):
    db.execute('INSERT INTO events(subscription_id,actor_id,action,at,details) VALUES(?,?,?,?,?)',
               (identity, actor, action, time.time(), json.dumps(details)))


def checked_device_limit(value):
    if type(value) is not int or not 3 <= value <= 8:
        raise ValueError('invalid_device_limit')
    return value


def create(body):
    limit = checked_device_limit(body.get('device_limit', 3))
    days = int(body['days'])
    hidden = body.get('hidden', False)
    if type(hidden) is not bool or hidden and (int(body['contact_id']) != 0 or body.get('telegram_user_id') is not None):
        raise ValueError('invalid_private_subscription')
    if not 1 <= days <= 3650 or body['kind'] not in ('gift', 'purchase', 'trial') or (int(body['contact_id']) <= 0 and not hidden):
        raise ValueError('invalid_subscription')
    request_key = str(uuid.UUID(body['idempotency_key'])) if body.get('idempotency_key') else None
    identity = str(uuid.uuid4()); now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if request_key:
            existing = db.execute('SELECT * FROM subscriptions WHERE create_request_key=?', (request_key,)).fetchone()
            if existing:
                if (existing['created_by'] != int(body['actor_id']) or existing['contact_id'] != int(body['contact_id'])
                        or existing['kind'] != body['kind'] or existing['source_chat_id'] != body.get('source_chat_id')
                        or existing['deleted_at'] is not None):
                    raise ValueError('creation_request_mismatch')
                return subscription_view(existing, db)
        eligibility = issuance_state(db, body['contact_id'], body.get('telegram_user_id'))
        if not hidden and not eligibility['can_create']:
            raise ValueError('active_subscription_exists')
        if body['kind'] == 'trial' and not eligibility['trial_available']:
            raise ValueError('trial_already_used')
        db.execute('''INSERT INTO subscriptions(id,contact_id,contact_name,telegram_user_id,telegram_username,source_bot_id,source_bot_name,
                    kind,created_by,expires_at,enabled,token,password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (identity, int(body['contact_id']), str(body['contact_name'])[:300], body.get('telegram_user_id'),
                    body.get('telegram_username'), body.get('source_bot_id'), body.get('source_bot_name'),
                    body['kind'], int(body['actor_id']), now + days * 86400, 1,
                    secrets.token_urlsafe(32), secrets.token_urlsafe(32), now, now))
        for node in NODES:
            db.execute('INSERT INTO deliveries(subscription_id,node_id) VALUES(?,?)', (identity, node['id']))
        db.execute('UPDATE subscriptions SET source_chat_id=? WHERE id=?', (body.get('source_chat_id'), identity))
        db.execute('UPDATE subscriptions SET create_request_key=? WHERE id=?', (request_key, identity))
        db.execute('UPDATE subscriptions SET device_limit=? WHERE id=?', (limit, identity))
        db.execute('UPDATE subscriptions SET hidden=? WHERE id=?', (int(hidden), identity))
        event(db, identity, body['actor_id'], body['kind'], {'days': days, 'source_bot_id': body.get('source_bot_id'), 'source_chat_id': body.get('source_chat_id')})
        value = subscription_view(db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone(), db)
    WAKE.set()
    return value


def mutate(identity, body):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone()
        if not row:
            raise LookupError('not_found')
        if row['deleted_at'] is not None:
            raise ValueError('subscription_deleted')
        action = body['action']; now = time.time()
        if action == 'renew':
            current = issuance_state(db, row['contact_id'], row['telegram_user_id'])['current_subscription_id']
            if current and current != identity:
                raise ValueError('active_subscription_exists')
            days = int(body['days'])
            if not 1 <= days <= 3650:
                raise ValueError('invalid_days')
            db.execute('UPDATE subscriptions SET expires_at=?,enabled=1,version=version+1,updated_at=? WHERE id=?',
                       (max(now, row['expires_at']) + days * 86400, now, identity))
        elif action in ('revoke', 'resume'):
            if action == 'resume' and row['expires_at'] <= now:
                raise ValueError('subscription_expired')
            if action == 'resume':
                current = issuance_state(db, row['contact_id'], row['telegram_user_id'])['current_subscription_id']
                if current and current != identity:
                    raise ValueError('active_subscription_exists')
            db.execute('UPDATE subscriptions SET enabled=?,version=version+1,updated_at=? WHERE id=?', (int(action == 'resume'), now, identity))
        elif action == 'rotate_link':
            db.execute('UPDATE subscriptions SET token=?,updated_at=? WHERE id=?', (secrets.token_urlsafe(32), now, identity))
        elif action == 'delete':
            db.execute('UPDATE subscriptions SET enabled=0,deleted_at=?,version=version+1,updated_at=? WHERE id=?', (now, now, identity))
        elif action == 'set_device_limit':
            limit = checked_device_limit(body.get('device_limit'))
            db.execute('UPDATE subscriptions SET device_limit=?,updated_at=? WHERE id=?', (limit, now, identity))
        else:
            raise ValueError('invalid_action')
        event(db, identity, body['actor_id'], action, {'days': body.get('days'), **({'device_limit': limit, 'previous_device_limit': row['device_limit']} if action == 'set_device_limit' else {})})
        value = subscription_view(db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone(), db)
    WAKE.set()
    return value


def renew_request(identity, body):
    days = int(body['days'])
    if not 1 <= days <= 3650:
        raise ValueError('invalid_days')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        request = db.execute('SELECT * FROM bot_requests WHERE id=?', (identity,)).fetchone()
        if not request:
            raise LookupError('not_found')
        if request['kind'] != 'renew':
            raise ValueError('not_renewal')
        if request['state'] == 'done':
            return {'already_processed': True}
        row = db.execute('SELECT * FROM subscriptions WHERE id=?', (request['subscription_id'],)).fetchone()
        if request['state'] != 'open' or not row or row['deleted_at'] is not None or row['contact_id'] != request['contact_id'] or row['telegram_user_id'] != request['user_id']:
            raise ValueError('request_unavailable')
        current = issuance_state(db, row['contact_id'], row['telegram_user_id'])['current_subscription_id']
        if current and current != row['id']:
            raise ValueError('active_subscription_exists')
        now = time.time()
        db.execute('UPDATE subscriptions SET expires_at=?,enabled=1,version=version+1,updated_at=? WHERE id=?',
                   (max(now, row['expires_at']) + days * 86400, now, row['id']))
        db.execute("UPDATE bot_requests SET state='done',handled_at=?,handled_by=? WHERE id=?", (now, int(body['actor_id']), identity))
        event(db, row['id'], int(body['actor_id']), 'renew', {'days': days, 'request_id': identity})
        event(db, row['id'], int(body['actor_id']), 'bot_request_handled', {'request_id': identity, 'state': 'done'})
    WAKE.set()
    return {'already_processed': False}


def reconcile_node(node):
    node_id = node['id']
    try:
        metadata = node_call(node_id, {'operation': 'metadata'})
        with database() as db:
            db.execute('INSERT INTO endpoints VALUES(?,?,?) ON CONFLICT(node_id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at',
                       (node_id, json.dumps(metadata['endpoints']), time.time()))
            pending = db.execute('''SELECT s.* FROM subscriptions s JOIN deliveries d ON d.subscription_id=s.id
                WHERE d.node_id=? AND (d.version<>s.version OR d.status<>'synced')''', (node_id,)).fetchall()
        for row in pending:
            try:
                node_call(node_id, {'operation': 'sync', 'id': row['id'], 'password': row['password'],
                                   'expires_at': row['expires_at'], 'enabled': bool(row['enabled']) and row['expires_at'] > time.time()})
                with database() as db:
                    db.execute("UPDATE deliveries SET version=?,status='synced',checked_at=? WHERE subscription_id=? AND node_id=?", (row['version'], time.time(), row['id'], node_id))
            except Exception:
                with database() as db:
                    db.execute("UPDATE deliveries SET status='retrying',checked_at=? WHERE subscription_id=? AND node_id=?", (time.time(), row['id'], node_id))
                log.warning('Provisioning retry required on %s', node_id)
        usage = node_call(node_id, {'operation': 'usage'})
        with database() as db:
            identities = {row[0] for row in db.execute('SELECT id FROM subscriptions')}
            for identity, data in usage['users'].items():
                if identity not in identities:
                    continue
                for metric in ('up', 'down', 'hy_up', 'hy_down'):
                    if metric not in data:
                        continue
                    current = max(0, int(data[metric]))
                    prior = db.execute('SELECT last_value,total FROM counters WHERE subscription_id=? AND node_id=? AND metric=?', (identity, node_id, metric)).fetchone()
                    total = (prior['total'] if prior else 0) + (current - prior['last_value'] if prior and current >= prior['last_value'] else current)
                    db.execute('INSERT INTO counters VALUES(?,?,?,?,?,?) ON CONFLICT(subscription_id,node_id,metric) DO UPDATE SET last_value=excluded.last_value,total=excluded.total,checked_at=excluded.checked_at',
                               (identity, node_id, metric, current, total, time.time()))
                db.execute('INSERT INTO usage_state VALUES(?,?,?,?,?) ON CONFLICT(subscription_id,node_id) DO UPDATE SET last_online=excluded.last_online,hy_online=excluded.hy_online,checked_at=excluded.checked_at',
                           (identity, node_id, (data.get('last_online') or 0) / 1000, data.get('hy_online', 0), time.time()))
        try:
            olcrtc_control.reconcile(database, node_call, node)
        except Exception:
            log.warning('Node %s room provisioning unavailable', node_id)
    except Exception:
        log.warning('Node %s control/usage unavailable', node_id)


def reconcile():
    while True:
        WAKE.clear()
        try:
            with database() as db:
                # Expiry is also enforced on each node; disabled versions trigger HY kicks.
                db.execute('UPDATE subscriptions SET enabled=0,version=version+1,updated_at=? WHERE enabled=1 AND expires_at<=?', (time.time(), time.time()))
            with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
                list(pool.map(reconcile_node, NODES))
        except Exception:
            log.exception('Reconciliation failed')
        WAKE.wait(30)


def connection_configs(row, db):
    delivery = {item['node_id']: item for item in db.execute('SELECT * FROM deliveries WHERE subscription_id=?', (row['id'],))}
    healthy = ranked_nodes(row['id'], snapshot())
    order = list(healthy)
    order += [node['id'] for node in NODES if node['id'] not in order]
    names = {node['id']: node['name'] for node in NODES}
    proxies = []; links = []; automatic = []
    # A server reachable from CRM may be blocked in the customer's network.
    # Keep every healthy exit available to the client's actual latency probes.
    eligible = set(healthy)
    for node_id in order:
        delivered = delivery.get(node_id)
        if not delivered or delivered['version'] != row['version'] or delivered['status'] != 'synced':
            continue
        metadata = db.execute('SELECT data FROM endpoints WHERE node_id=?', (node_id,)).fetchone()
        if not metadata:
            continue
        for index, endpoint in enumerate(json.loads(metadata['data'])):
            label = names[node_id] + ' · ' + ('VLESS ' + str(index + 1) if endpoint['type'] == 'vless' else 'Hysteria2')
            if endpoint['type'] == 'vless' and endpoint.get('game_brand') in ('Steam', 'Riot', 'Roblox', 'Epic Games', 'Battle.net', 'EA', 'Ubisoft'):
                label = names[node_id] + ' · ' + endpoint['game_brand']
            service = endpoint.get('service_brand', '')
            if endpoint['type'] == 'vless' and isinstance(service, str) and re.fullmatch(r'[A-Za-z0-9 ._-]{1,64}', service):
                label = names[node_id] + ' · БС · ' + service
            if endpoint.get('variant') == 'fallback':
                label += ' · резерв'
            proxy = {'name': label, 'type': endpoint['type'], 'server': endpoint['server'], 'port': endpoint['port'], 'udp': True}
            if endpoint.get('test_profile'):
                proxy['test-profile'] = True
            if endpoint['type'] == 'vless':
                xhttp = endpoint.get('xhttp', {})
                fingerprint = endpoint.get('fingerprint', 'chrome')
                if fingerprint not in ('chrome', 'qq'):
                    fingerprint = 'chrome'
                proxy.update(uuid=row['id'], tls=True, servername=endpoint['sni'], network=endpoint['network'],
                             **{'client-fingerprint': fingerprint, 'packet-encoding': 'xudp',
                                'reality-opts': {'public-key': endpoint['public_key'], 'short-id': endpoint['short_id'],
                                                 'support-x25519mlkem768': True}})
                if endpoint['network'] == 'xhttp':
                    proxy['alpn'] = ['h2']
                    mode = xhttp.get('mode', 'auto')
                    # Server auto accepts all modes. Preserve the first fast path;
                    # give the second address an independently compatible upload.
                    if index == 1 and mode == 'auto':
                        mode = 'packet-up'
                    proxy['xhttp-opts'] = {'path': xhttp.get('path', '/'), 'mode': mode}
                query = {'encryption': 'none', 'security': 'reality', 'type': endpoint['network'], 'sni': endpoint['sni'],
                         'fp': fingerprint, 'pbk': endpoint['public_key'], 'sid': endpoint['short_id']}
                if endpoint['network'] == 'xhttp':
                    query.update(path=proxy['xhttp-opts']['path'], mode=proxy['xhttp-opts']['mode'])
                uri = 'vless://' + row['id'] + '@' + endpoint['server'] + ':' + str(endpoint['port'])
            else:
                credential = row['id'] + ':' + row['password']
                proxy.update(password=credential, sni=endpoint['server'], **{'skip-cert-verify': True, 'fingerprint': endpoint['pin']})
                query = {'insecure': '1', 'sni': endpoint['server'], 'pinSHA256': endpoint['pin']}
                if endpoint['obfs']:
                    proxy.update(obfs='salamander', **{'obfs-password': endpoint['obfs']})
                    query.update(obfs='salamander', **{'obfs-password': endpoint['obfs']})
                uri = 'hysteria2://' + urllib.parse.quote(credential, safe='') + '@' + endpoint['server'] + ':' + str(endpoint['port']) + '/'
            proxies.append(proxy)
            links.append(uri + '?' + urllib.parse.urlencode(query) + '#' + urllib.parse.quote(label))
            if node_id in eligible:
                automatic.append(label)
    return proxies, links, automatic


def happ_routing_profile():
    return {'Name': 'BTT — RU напрямую', 'GlobalProxy': 'true',
            'RemoteDNSType': 'DoH', 'RemoteDNSDomain': 'https://cloudflare-dns.com/dns-query', 'RemoteDNSIP': '1.1.1.1',
            'DomesticDNSType': 'DoH', 'DomesticDNSDomain': 'https://common.dot.dns.yandex.net/dns-query', 'DomesticDNSIP': '77.88.8.8',
            'Geoipurl': PUBLIC + '/geo/geoip.dat', 'Geositeurl': PUBLIC + '/geo/geosite.dat',
            'DirectSites': ['geosite:category-ru', 'domain:ru', 'domain:su', 'domain:xn--p1ai'],
            'DirectIp': ['geoip:ru', 'geoip:private'], 'DomainStrategy': 'IPIfNonMatch', 'FakeDNS': 'false'}


def country_connections(proxies):
    """Keep a stable country order while retaining every transport variant."""
    groups = {node['name']: [] for node in NODES}
    for proxy in proxies:
        country = proxy['name'].split(' · ', 1)[0]
        groups.setdefault(country, []).append(proxy)
    return {country: members for country, members in groups.items() if members}


def country_label(country):
    flags = {'pl': '🇵🇱', 'rs': '🇷🇸', 'ee': '🇪🇪', 'fi': '🇫🇮', 'ch': '🇨🇭', 'ro': '🇷🇴', 'kz': '🇰🇿'}
    node = next((node for node in NODES if node['name'] == country), {})
    return (flags.get(node.get('id'), '') + ' ' + country).strip()


def ghostlane_configs(proxies, links, rtc_links):
    """Two native sections: a direct RTC channel and one global VPN chooser."""
    groups = {node['id']: [] for node in NODES}
    names = {node['name']: node for node in NODES}
    def entry(node, name, identity, **fields):
        return {'storage_id': 'btt_' + hashlib.sha256(identity.encode()).hexdigest()[:24],
                'name': node['id'].upper() + ' · ' + name,
                'metadata': {'name': country_label(node['name']) + ' · ' + name,
                    'subscription': {'name': 'Обычный VPN · все страны',
                        'announce': 'АВТО / Наименьшая задержка — выбор среди всех стран. При ограничениях выберите olcRTC.'}}, **fields}
    for proxy, link in zip(proxies, links):
        # Android/desktop Ghostlane ships Xray 25.3.6, whose REALITY handshake
        # fails against these exits. Only publish verified sing-box Hysteria2
        # exits, including when an old subscription URL contains view=all.
        if proxy['type'] != 'hysteria2':
            continue
        country, _, method = proxy['name'].partition(' · ')
        node = names[country]
        if proxy['type'] == 'hysteria2':
            # Ghostlane's parser treats the entire authority suffix as a port
            # and does not percent-decode userinfo. Its importer therefore needs
            # :port? (without /) and the literal UUID:password credential.
            parts = urllib.parse.urlsplit(link)
            link = urllib.parse.urlunsplit((parts.scheme,
                urllib.parse.unquote(parts.netloc), '', parts.query, parts.fragment))
        item = entry(node, method, link, kind='Hysteria2', raw_link=link)
        item['metadata']['name'] = country_label(country) + (' · резерв' if groups[node['id']] else '')
        groups[node['id']].append(item)
    for link in rtc_links:
        prefix, label = link.rsplit('$', 1)
        node_id = label.rsplit(' · ', 1)[-1].lower()
        node = next(node for node in NODES if node['id'] == node_id)
        room, key = prefix.removeprefix('olcrtc://jitsi?datachannel@').rsplit('#', 1)
        rtc = entry(node, 'olcRTC', room, kind='Olcrtc',
            auth_provider='jitsi', transport={'type': 'datachannel'}, endpoint={'room_id': room, 'key': key})
        rtc['metadata'] = {'name': 'Подключиться · olcRTC', 'subscription': {
            'name': 'Обход ограничений · olcRTC',
            'announce': 'Для сетей с белыми списками. Выберите «Подключиться · olcRTC» и включите VPN.'}}
        groups[node_id].append(rtc)
    locations = [item for members in groups.values() for item in members]
    # The native lowest-ping chooser skips RTC probes and stops after 3 failures.
    # Keep the working private channel first among unmeasured choices and select
    # it on a fresh import; this cannot override the application's measured ranks.
    locations.sort(key=lambda item: item['kind'] != 'Olcrtc')
    return {'version': 4, 'active_location_id': locations[0]['storage_id'] if locations else None, 'locations': locations}


def clash_configs(proxies, automatic, expanded=False):
    # Legacy QQ pilots failed on the tested Mihomo core. Verified Chrome
    # variants participate in ordinary selection, including former pilots.
    proxies = [{key: value for key, value in proxy.items() if key != 'test-profile'} for proxy in proxies if not (
               proxy['type'] == 'vless' and proxy.get('client-fingerprint') == 'qq' and ' · БС · ' in proxy['name'])]
    countries = country_connections(proxies)
    allowed = set(automatic)
    selected = [proxy['name'] for proxy in proxies if proxy['name'] in allowed]
    modes = ['AUTO'] if selected else []
    choices = [proxy['name'] for proxy in proxies] if expanded else [country_label(country) for country in countries]
    groups = [{'name': 'VPN', 'type': 'select', 'proxies': modes + choices}]
    probe = {'type': 'url-test', 'url': 'https://www.gstatic.com/generate_204',
             'interval': 30, 'tolerance': 30, 'lazy': False}
    if selected:
        groups.append({**probe, 'name': 'AUTO', 'proxies': selected, 'hidden': not expanded})
    if not expanded:
        for country, members in countries.items():
            groups.append({**probe, 'name': country_label(country), 'proxies': [proxy['name'] for proxy in members],
                           'hidden': True, 'lazy': True})
        # GLOBAL otherwise expands every raw proxy even in a compact profile.
        groups.append({'name': 'GLOBAL', 'type': 'select', 'proxies': ['VPN'], 'hidden': True})
    return {'mixed-port': 7890, 'allow-lan': False, 'mode': 'rule', 'log-level': 'warning', 'proxies': proxies,
            'geodata-mode': True, 'geox-url': {'geoip': PUBLIC + '/geo/geoip.dat', 'geosite': PUBLIC + '/geo/geosite.dat'},
            'proxy-groups': groups, 'rules': ['DOMAIN-SUFFIX,ru,DIRECT', 'DOMAIN-SUFFIX,su,DIRECT', 'DOMAIN-SUFFIX,xn--p1ai,DIRECT',
                'GEOSITE,category-ru,DIRECT', 'GEOIP,RU,DIRECT', 'GEOIP,LAN,DIRECT', 'MATCH,VPN']}


def happ_configs(proxies, automatic, expanded=False):
    def outbound(proxy, tag):
        if proxy['type'] == 'hysteria2':
            return {'tag': tag, 'protocol': 'hysteria',
                    'settings': {'version': 2, 'address': proxy['server'], 'port': proxy['port']},
                    'streamSettings': {'network': 'hysteria', 'security': 'tls',
                        'tlsSettings': {'serverName': proxy['sni'], 'pinnedPeerCertSha256': proxy['fingerprint']},
                        'hysteriaSettings': {'version': 2, 'auth': proxy['password']},
                        'finalmask': {'udp': [{'type': 'salamander', 'settings': {'password': proxy['obfs-password']}}]}}}
        stream = {'network': proxy['network'], 'security': 'reality',
                  'realitySettings': {'serverName': proxy['servername'], 'fingerprint': proxy.get('client-fingerprint', 'chrome'),
                                      'publicKey': proxy['reality-opts']['public-key'], 'shortId': proxy['reality-opts']['short-id']}}
        if proxy['network'] == 'xhttp':
            stream['xhttpSettings'] = proxy['xhttp-opts']
        return {'tag': tag, 'protocol': 'vless', 'settings': {'vnext': [{'address': proxy['server'], 'port': proxy['port'],
                'users': [{'id': proxy['uuid'], 'encryption': 'none'}]}]}, 'streamSettings': stream}
    def profile(name, selected, balanced=False):
        outbounds = [outbound(proxy, 'vpn-' + str(index)) for index, proxy in enumerate(selected)]
        rules = [{'type': 'field', 'domain': ['geosite:category-ru', 'domain:ru', 'domain:su', 'domain:xn--p1ai', 'domain:common.dot.dns.yandex.net'], 'outboundTag': 'direct'},
                 {'type': 'field', 'ip': ['geoip:ru', 'geoip:private'], 'outboundTag': 'direct'},
                 {'type': 'field', 'network': 'tcp,udp', **({'balancerTag': 'auto'} if balanced else {'outboundTag': 'vpn-0'})}]
        config = {'remarks': name, 'log': {'loglevel': 'warning'},
                  'inbounds': [{'tag': 'socks', 'listen': '127.0.0.1', 'port': 10808, 'protocol': 'socks', 'settings': {'auth': 'noauth', 'udp': True},
                                'sniffing': {'enabled': True, 'destOverride': ['http', 'tls', 'quic'], 'routeOnly': True}},
                               {'tag': 'http', 'listen': '127.0.0.1', 'port': 10809, 'protocol': 'http', 'settings': {'allowTransparent': False},
                                'sniffing': {'enabled': True, 'destOverride': ['http', 'tls'], 'routeOnly': True}}],
                  'outbounds': outbounds + [{'tag': 'direct', 'protocol': 'freedom'}],
                  'dns': {'hosts': {'cloudflare-dns.com': '1.1.1.1', 'dns.quad9.net': '9.9.9.9', 'common.dot.dns.yandex.net': '77.88.8.8'},
                          'servers': [{'address': 'https+local://common.dot.dns.yandex.net/dns-query',
                                       'domains': ['geosite:category-ru', 'domain:ru', 'domain:su', 'domain:xn--p1ai'], 'skipFallback': True},
                                      'https://cloudflare-dns.com/dns-query', 'https://dns.quad9.net/dns-query'], 'queryStrategy': 'UseIPv4'},
                  'routing': {'domainStrategy': 'IPIfNonMatch', 'rules': rules}}
        if balanced:
            config['routing']['balancers'] = [{'tag': 'auto', 'selector': ['vpn-'], 'fallbackTag': 'vpn-0', 'strategy': {'type': 'leastPing'}}]
            config['observatory'] = {'subjectSelector': ['vpn-'], 'probeUrl': 'https://www.gstatic.com/generate_204', 'probeInterval': '30s', 'enableConcurrency': True}
        return config
    supported = [proxy for proxy in proxies if proxy['type'] in ('vless', 'hysteria2')]
    allowed = set(automatic)
    selected = [proxy for proxy in supported if proxy['name'] in allowed]
    automatic_profile = [profile('⚡ Автовыбор', selected, True)] if selected else []
    if expanded:
        return automatic_profile + [profile(proxy['name'], [proxy]) for proxy in supported]
    return automatic_profile + [profile(country_label(country), members, True) for country, members in country_connections(supported).items()]


class Handler(BaseHTTPRequestHandler):
    server_version = 'VPN'
    def log_message(self, *args):
        # Subscription URLs are bearer secrets; access logs must not record them.
        pass

    def reply(self, status, value, content_type='application/json', headers=None):
        encoded = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode() if content_type == 'application/json' else value.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        if not headers or 'Cache-Control' not in headers:
            self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers(); self.wfile.write(encoded)

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 32768:
            raise ValueError('invalid_body')
        return json.loads(self.rfile.read(size))

    def dispatch(self):
        global BOT_TOKEN, BOT_USERNAME, BOT_ID
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path; query = urllib.parse.parse_qs(parsed.query)
        if path.startswith('/node/lease/') and self.command == 'POST':
            node_id = path.removeprefix('/node/lease/')
            if node_id not in {node['id'] for node in NODES}:
                raise LookupError('not_found')
            with database() as db:
                credential = db.execute('SELECT value FROM settings WHERE key=?', ('lease_token:' + node_id,)).fetchone()
            if not credential or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + credential['value']):
                return self.reply(403, {'error': 'forbidden'})
            body = self.body()
            if body.get('action') == 'heartbeat':
                leases = body.get('leases')
                if not isinstance(leases, list) or len(leases) > 64:
                    raise ValueError('invalid_leases')
                denied = [entry['lease_id'] for entry in leases if not connection_lease(node_id, {**entry, 'action': 'renew'})['allowed']]
                return self.reply(200, {'denied': denied, 'ttl': 45})
            return self.reply(200, connection_lease(node_id, body))
        if path.startswith('/downloads/') and self.command == 'GET':
            filename = path.removeprefix('/downloads/')
            allowed = {'ghostlane.apk', 'happ.apk', 'clashmeta.apk', 'v2rayng.apk', 'v2rayng-arm7.apk'}
            if filename not in allowed:
                raise LookupError('not_found')
            apk = client_guides.DOWNLOADS / filename
            if not apk.is_file():
                raise LookupError('not_found')
            with apk.open('rb') as source:
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.android.package-archive')
                self.send_header('Content-Length', str(os.fstat(source.fileno()).st_size))
                self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                while chunk := source.read(256 * 1024):
                    self.wfile.write(chunk)
            return
        if path in ('/', '/apps', '/connect') and self.command == 'GET':
            return self.reply(200, client_guides.page(PUBLIC, bot_username=BOT_USERNAME), 'text/html')
        if path in ('/geo/geoip.dat', '/geo/geosite.dat') and self.command == 'GET':
            geo = Path('/opt/crm-vpn/geo') / path.rsplit('/', 1)[1]
            if not geo.is_file():
                return self.reply(503, {'error': 'geo_unavailable'})
            return self.reply(200, geo.read_bytes(), 'application/octet-stream')
        if path == '/health' and self.command == 'GET':
            return self.reply(200, {'status': 'ok', 'bot_username': BOT_USERNAME})
        if path.startswith('/sub/') and self.command == 'GET':
            format_name = query.get('format', [''])[0]
            if not format_name and 'ghostlane' in self.headers.get('User-Agent', '').lower():
                format_name = 'ghostlane'
            token = path.removeprefix('/sub/')
            if not 30 <= len(token) <= 100:
                raise LookupError('not_found')
            with database() as db:
                row = db.execute('SELECT * FROM subscriptions WHERE token=?', (token,)).fetchone()
                if not row or row['deleted_at'] is not None:
                    raise LookupError('not_found')
                if not row['enabled'] or row['expires_at'] <= time.time():
                    return self.reply(403, {'error': 'subscription_inactive'})
                if query.get('format', [''])[0] == 'guide':
                    return self.reply(200, client_guides.page(PUBLIC, PUBLIC + '/sub/' + row['token'], BOT_USERNAME), 'text/html', {'Referrer-Policy': 'no-referrer', 'X-Robots-Tag': 'noindex, nofollow'})
                if format_name == 'ghostlane':
                    olcrtc_control.ensure(db, row, ranked_nodes(row['id'], snapshot()))
                    WAKE.set()
                proxies, links, automatic = connection_configs(row, db)
                if not links:
                    return self.reply(503, {'error': 'subscription_provisioning'})
                db.execute('UPDATE subscriptions SET last_fetch=? WHERE id=?', (time.time(), row['id']))
                view = subscription_view(row, db)
            headers = {'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer', 'profile-title': 'base64:' + base64.b64encode('BTT VPN'.encode()).decode(), 'profile-update-interval': '1',
                       'subscription-userinfo': 'upload=' + str(view['upload_bytes']) + '; download=' + str(view['download_bytes']) + '; total=0; expire=' + str(int(row['expires_at']))}
            if not format_name:
                agent = self.headers.get('User-Agent', '').lower()
                format_name = 'clash' if any(name in agent for name in ('clash', 'mihomo', 'stash', 'koala')) else 'happ' if 'happ' in agent else 'base64'
            expanded = query.get('view', [''])[0] == 'all'
            if format_name == 'ghostlane':
                with database() as db:
                    rtc_links = olcrtc_control.links(db, row)
                if not rtc_links:
                    notice = 'Обновите подписку через минуту: канал обхода ограничений готовится.'
                    headers['announce'] = 'base64:' + base64.b64encode(notice.encode()).decode()
                # A global profile-title overwrites every entry's folder name.
                headers.pop('profile-title', None)
                config = ghostlane_configs(proxies, links, rtc_links)
                return self.reply(200, config, 'application/json', headers)
            if format_name == 'clash':
                config = clash_configs(proxies, automatic, expanded)
                return self.reply(200, json.dumps(config, ensure_ascii=False, indent=2), 'application/yaml', headers)
            if format_name == 'happ':
                profiles = happ_configs(proxies, automatic, expanded)
                routing = happ_routing_profile()
                headers['routing'] = 'happ://routing/onadd/' + base64.b64encode(json.dumps(routing, ensure_ascii=False).encode()).decode()
                # Measure actual tunnel availability, including UDP-only entries;
                # ICMP/TCP ping alone does not test a Hysteria connection.
                headers.update({'ping-type': 'proxy', 'check-url-via-proxy': 'https://www.gstatic.com/generate_204',
                                'subscription-ping-onopen-enabled': '1'})
                return self.reply(200, profiles, headers=headers)
            if format_name not in ('raw', 'base64', 'happ-legacy', 'v2rayng'):
                raise ValueError('unsupported_format')
            if format_name in ('happ-legacy', 'v2rayng'):
                links = [link for link in links if link.startswith('vless://')]
            text = '\n'.join(links) + '\n'
            if format_name in ('base64', 'happ-legacy', 'v2rayng'):
                text = base64.b64encode(text.encode()).decode()
            return self.reply(200, text, 'text/plain', headers)
        if not path.startswith('/internal/') or not API_KEY or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + API_KEY):
            return self.reply(404, {'error': 'not_found'})
        if path == '/internal/fleet' and self.command == 'GET':
            data = snapshot(); data['bot_username'] = BOT_USERNAME
            return self.reply(200, data)
        if path == '/internal/bot/notifications' and self.command == 'GET':
            with database() as db:
                counts = {row['status']: row['count'] for row in db.execute('SELECT status,COUNT(*) AS count FROM bot_notifications GROUP BY status')}
            return self.reply(200, counts)
        if path == '/internal/bot/requests' and self.command == 'GET':
            contact = query.get('contact_id', [None])[0]
            state = query.get('state', [None])[0]
            if state is not None and state not in ('open', 'done', 'dismissed'):
                raise ValueError('invalid_state')
            conditions, parameters = [], []
            if contact:
                conditions.append('contact_id=?'); parameters.append(int(contact))
            if state:
                conditions.append('state=?'); parameters.append(state)
            sql = 'SELECT * FROM bot_requests' + (' WHERE ' + ' AND '.join(conditions) if conditions else '')
            sql += " ORDER BY CASE WHEN state='open' THEN 0 ELSE 1 END,id DESC"
            if state != 'open':
                sql += ' LIMIT 100'
            with database() as db:
                rows = db.execute(sql, parameters)
                return self.reply(200, {'items': [dict(row) for row in rows]})
        if path.startswith('/internal/bot/requests/'):
            if path.endswith('/renew') and self.command == 'POST':
                return self.reply(200, renew_request(int(path.split('/')[-2]), self.body()))
            identity = int(path.rsplit('/', 1)[1])
            with database() as db:
                row = db.execute('SELECT * FROM bot_requests WHERE id=?', (identity,)).fetchone()
                if not row:
                    raise LookupError('not_found')
                if self.command == 'POST':
                    body = self.body()
                    if body['state'] not in ('done', 'dismissed'):
                        raise ValueError('invalid_state')
                    db.execute('UPDATE bot_requests SET state=?,handled_at=?,handled_by=? WHERE id=?', (body['state'], time.time(), int(body['actor_id']), identity))
                    event(db, row['subscription_id'], int(body['actor_id']), 'bot_request_handled', {'request_id': identity, 'state': body['state']})
                return self.reply(200, dict(db.execute('SELECT * FROM bot_requests WHERE id=?', (identity,)).fetchone()))
        if path == '/internal/bot/prepare' and self.command == 'POST':
            body = self.body()
            token = body['token'].strip()
            if not 20 <= len(token) <= 200 or any(c.isspace() for c in token):
                raise ValueError('invalid_token')
            try:
                bot = telegram('getMe', {}, token)
                webhook = telegram('getWebhookInfo', {}, token)
            except Exception:
                raise ValueError('invalid_token') from None
            if webhook.get('url'):
                raise ValueError('bot_has_webhook')
            challenge = secrets.token_urlsafe(32)
            with BOT_LOCK:
                now = time.time()
                for key in list(BOT_CHALLENGES):
                    if BOT_CHALLENGES[key]['expires'] < now or BOT_CHALLENGES[key]['actor_id'] == int(body['actor_id']):
                        del BOT_CHALLENGES[key]
                if len(BOT_CHALLENGES) >= 32:
                    raise ValueError('too_many_pending_changes')
                BOT_CHALLENGES[challenge] = {'token': token, 'username': bot['username'], 'bot_id': bot.get('id', 0),
                    'actor_id': int(body['actor_id']), 'expires': now + 180}
            return self.reply(200, {'challenge': challenge, 'username': bot['username'], 'expires_in': 180})
        if path == '/internal/bot/confirm' and self.command == 'POST':
            body = self.body()
            with BOT_LOCK:
                pending = BOT_CHALLENGES.get(body['challenge'])
                if not pending or pending['expires'] < time.time() or pending['actor_id'] != int(body['actor_id']) or body.get('confirmation') != 'ЗАМЕНИТЬ БОТА':
                    raise ValueError('invalid_confirmation')
                with database() as db:
                    recipients = {row[0] for row in db.execute('SELECT user_id FROM bot_users WHERE bot_id=?', (BOT_ID,))}
                    # Bootstrap known linked clients from the pre-cabinet version; Telegram rejects unopened chats.
                    recipients.update(row[0] for row in db.execute('SELECT DISTINCT telegram_user_id FROM subscriptions WHERE telegram_user_id IS NOT NULL'))
                    notification_token = pending['token'] if pending['bot_id'] == BOT_ID else BOT_TOKEN
                    text = 'Кабинет VPN обновлён. Актуальный бот: https://t.me/' + pending['username'] + '\nВаши подписки и сроки сохранены. Откройте бота и нажмите «Запустить».'
                    if notification_token:
                        db.executemany('INSERT INTO bot_notifications(user_id,token,text,created_at) VALUES(?,?,?,?)', [(user, notification_token, text, time.time()) for user in recipients])
                    db.execute("INSERT INTO settings VALUES('telegram_token',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (pending['token'],))
                    db.execute("DELETE FROM settings WHERE key='telegram_offset'")
                    event(db, None, int(body['actor_id']), 'bot_changed', {'username': pending['username']})
                BOT_TOKEN = pending['token']; BOT_USERNAME = pending['username']; BOT_ID = pending['bot_id']
                BOT_CHALLENGES.clear()
            return self.reply(200, {'username': BOT_USERNAME, 'notifications_queued': len(recipients)})
        if path.startswith('/internal/nodes/') and self.command == 'POST':
            node_id = path.removeprefix('/internal/nodes/')
            if node_id not in {node['id'] for node in NODES}:
                raise LookupError('not_found')
            body = self.body(); capacity = body.get('capacity_mbps')
            if not isinstance(body.get('drained'), bool) or capacity is not None and not 1 <= float(capacity) <= 100000:
                raise ValueError('invalid_node_settings')
            with database() as db:
                data = {'drained': body['drained'], 'capacity_mbps': float(capacity) if capacity is not None else None}
                db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('node:' + node_id, json.dumps(data)))
                event(db, None, int(body['actor_id']), 'node_settings', {'node_id': node_id, **data})
            return self.reply(200, data)
        if path == '/internal/subscriptions' and self.command == 'POST':
            return self.reply(201, create(self.body()))
        if path == '/internal/subscriptions' and self.command == 'GET':
            with database() as db:
                contact = query.get('contact_id', [None])[0]
                rows = db.execute('SELECT * FROM subscriptions WHERE contact_id=? AND deleted_at IS NULL AND hidden=0 ORDER BY created_at DESC LIMIT 500', (int(contact),)) if contact else db.execute('SELECT * FROM subscriptions WHERE deleted_at IS NULL AND hidden=0 ORDER BY created_at DESC LIMIT 500')
                items = [subscription_view(row, db) for row in rows]
                eligibility = issuance_state(db, int(contact), query.get('telegram_user_id', [None])[0]) if contact else None
                return self.reply(200, {'items': items, 'eligibility': eligibility})
        if path.startswith('/internal/subscriptions/'):
            identity = str(uuid.UUID(path.removeprefix('/internal/subscriptions/')))
            with database() as db:
                private = db.execute('SELECT hidden FROM subscriptions WHERE id=?', (identity,)).fetchone()
                if private and private['hidden']:
                    raise LookupError('not_found')
            if self.command == 'POST':
                return self.reply(200, mutate(identity, self.body()))
            with database() as db:
                row = db.execute('SELECT * FROM subscriptions WHERE id=?', (identity,)).fetchone()
                if not row:
                    raise LookupError('not_found')
                value = subscription_view(row, db)
                value['events'] = [dict(item) for item in db.execute('SELECT * FROM events WHERE subscription_id=? ORDER BY id DESC LIMIT 100', (identity,))]
                return self.reply(200, value)
        return self.reply(404, {'error': 'not_found'})

    def handle_request(self):
        try:
            self.dispatch()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except LookupError:
            self.reply(404, {'error': 'not_found'})
        except (ValueError, KeyError, TypeError) as exc:
            reason = str(exc)
            self.reply(400, {'error': reason if reason in ('active_subscription_exists', 'trial_already_used', 'invalid_device_limit') else 'invalid_request'})
        except Exception:
            log.exception('Control request failed')
            self.reply(500, {'error': 'internal_error'})
    do_GET = handle_request
    do_POST = handle_request


def telegram(method, body, token=None):
    request = urllib.request.Request('https://api.telegram.org/bot' + (token or BOT_TOKEN) + '/' + method,
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=40) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('telegram_error')
    return result['result']


def cabinet():
    import sys
    from bot_cabinet import run
    run(sys.modules[__name__])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if len(API_KEY) < 32:
        raise SystemExit('VPN_CONTROL_TOKEN must be configured')
    initialize()
    with database() as db:
        saved_bot = db.execute("SELECT value FROM settings WHERE key='telegram_token'").fetchone()
        if saved_bot:
            BOT_TOKEN = saved_bot[0]
    threading.Thread(target=reconcile, daemon=True).start()
    threading.Thread(target=cabinet, daemon=True).start()
    servers = [ThreadingHTTPServer((host, 19191), Handler) for host in os.environ.get('VPN_LISTEN_HOSTS', '127.0.0.1,172.17.0.1').split(',')]
    for server in servers[:-1]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    servers[-1].serve_forever()
