"""Lazy, stable one-room-per-subscription placement; no client credentials in CRM views."""
import hashlib
import hmac
import os
import time
import uuid

JITSI_BASE = os.environ.get('VPN_OLCRTC_JITSI_BASE', '').rstrip('/')


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS olcrtc_rooms (
        subscription_id TEXT PRIMARY KEY REFERENCES subscriptions(id), node_id TEXT NOT NULL,
        room TEXT NOT NULL, ready INTEGER NOT NULL DEFAULT 0, checked_at REAL,
        requested_at REAL NOT NULL)''')


def key(row):
    return hmac.new(row['password'].encode(), ('olcrtc-room:' + row['id']).encode(), hashlib.sha256).hexdigest()


def ensure(db, row, nodes):
    existing = db.execute('SELECT * FROM olcrtc_rooms WHERE subscription_id=?', (row['id'],)).fetchone()
    if existing or not JITSI_BASE or not nodes:
        return existing
    counts = {item[0]: item[1] for item in db.execute('''SELECT r.node_id,COUNT(*) FROM olcrtc_rooms r
        JOIN subscriptions s ON s.id=r.subscription_id WHERE s.enabled=1 AND s.expires_at>?
        GROUP BY r.node_id''', (time.time(),))}
    node = min(nodes, key=lambda name: counts.get(name, 0))
    room = JITSI_BASE + '/btt-' + uuid.uuid4().hex
    db.execute('INSERT OR IGNORE INTO olcrtc_rooms(subscription_id,node_id,room,requested_at) VALUES(?,?,?,?)',
               (row['id'], node, room, time.time()))
    return db.execute('SELECT * FROM olcrtc_rooms WHERE subscription_id=?', (row['id'],)).fetchone()


def links(db, row):
    room = db.execute('SELECT * FROM olcrtc_rooms WHERE subscription_id=?', (row['id'],)).fetchone()
    if not room or not room['ready'] or not room['checked_at'] or time.time() - room['checked_at'] > 120:
        return []
    return ['olcrtc://jitsi?datachannel@' + room['room'] + '#' + key(row) + '$🛡️ olcRTC · ' + room['node_id'].upper()]


def reconcile(database, node_call, node):
    if not JITSI_BASE:
        return
    with database() as db:
        rows = db.execute('''SELECT s.*,r.room FROM subscriptions s JOIN olcrtc_rooms r
            ON r.subscription_id=s.id WHERE r.node_id=?''', (node['id'],)).fetchall()
    response = node_call(node['id'], {'operation': 'rtc_sync', 'rooms': [
        {'id': row['id'], 'room': row['room'], 'key': key(row), 'expires_at': row['expires_at'],
         'enabled': bool(row['enabled']) and row['deleted_at'] is None} for row in rows]})
    with database() as db:
        for row in rows:
            result = response['rooms'].get(row['id'], {})
            db.execute('UPDATE olcrtc_rooms SET ready=?,checked_at=? WHERE subscription_id=?',
                       (int(bool(result.get('ready'))), time.time(), row['id']))
            for metric in ('up', 'down'):
                if metric not in result:
                    continue
                name = 'rtc_' + metric
                current = int(result[metric])
                prior = db.execute('SELECT last_value,total FROM counters WHERE subscription_id=? AND node_id=? AND metric=?',
                                   (row['id'], node['id'], name)).fetchone()
                total = (prior['total'] if prior else 0) + (current-prior['last_value'] if prior and current >= prior['last_value'] else current)
                db.execute('INSERT INTO counters VALUES(?,?,?,?,?,?) ON CONFLICT(subscription_id,node_id,metric) DO UPDATE SET last_value=excluded.last_value,total=excluded.total,checked_at=excluded.checked_at',
                           (row['id'], node['id'], name, current, total, time.time()))
