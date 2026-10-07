"""Private room configs and authorization adapter for the node's olcRTC supervisor."""
import hashlib
import hmac
import json
import os
import sqlite3
import time
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

STATE = Path('/etc/crm-vpn')
ROOMS = Path('/var/lib/crm-vpn-rtc/rooms.json')


def auth_token(identity, config):
    return hmac.new(config['lease_token'].encode(), ('olcrtc-auth:' + identity).encode(), hashlib.sha256).hexdigest()


def authorize(body, authorization, central):
    identity = str(uuid.UUID(body['subscription_id']))
    config = json.loads((STATE / 'agent.json').read_text())
    if not hmac.compare_digest(authorization, 'Bearer ' + auth_token(identity, config)):
        return {'allowed': False}
    device = body['device_id']
    if not isinstance(device, str) or not 1 <= len(device) <= 256:
        return {'allowed': False}
    lease = str(uuid.UUID(body['lease_id']))
    action = body['action']
    if action not in ('acquire', 'renew', 'release'):
        return {'allowed': False}
    with closing(sqlite3.connect((STATE / 'clients.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT expiry,enabled FROM clients WHERE id=?', (identity,)).fetchone()
    if action != 'release' and (not row or not row[1] or row[0] <= time.time()):
        return {'allowed': False}
    # Relays expose their own address. Stable device slots share the same global
    # admission ledger as direct external IPs, without pretending to know an IP.
    import ipaddress
    digest = hashlib.sha256((identity + ':' + device).encode()).digest()
    slot = str(ipaddress.IPv6Address(bytes.fromhex('fd73') + digest[:14]))
    return central({'subscription_id': identity, 'lease_id': lease, 'action': action, 'ip': slot})


def reconcile(body):
    requested = body['rooms']
    if not isinstance(requested, list) or len(requested) > 128:
        raise ValueError('invalid_room_batch')
    config = json.loads((STATE / 'agent.json').read_text())
    try:
        prior = json.loads(ROOMS.read_text())
    except FileNotFoundError:
        prior = []
    ports = {item['id']: int(item['stats'].rsplit(':', 1)[1]) for item in prior}
    used = set(ports.values())
    desired = []
    for item in requested:
        identity = str(uuid.UUID(item['id']))
        url = urlsplit(item['room'])
        key = bytes.fromhex(item['key'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or len(key) != 32:
            raise ValueError('invalid_room')
        if not item['enabled'] or item['expires_at'] <= time.time():
            continue
        port = ports.get(identity)
        if port is None:
            port = next(value for value in range(25000, 26000) if value not in used)
            used.add(port)
        desired.append({'id': identity, 'room': item['room'], 'key': item['key'],
                        'auth_token': auth_token(identity, config), 'stats': '127.0.0.1:' + str(port)})
    if desired != prior:
        candidate = ROOMS.with_suffix('.new')
        candidate.write_text(json.dumps(desired))
        import grp
        os.chown(candidate, 0, grp.getgrnam('crm-vpn-rtc').gr_gid)
        candidate.chmod(0o640)
        candidate.replace(ROOMS)
    result = {}
    for item in desired:
        try:
            with urllib.request.urlopen('http://' + item['stats'] + '/stats', timeout=1) as response:
                data = json.load(response)
            result[item['id']] = {'ready': data['link'] == 'up', 'up': data['total']['up'], 'down': data['total']['down']}
        except Exception:
            result[item['id']] = {'ready': False}
    return {'rooms': result}
