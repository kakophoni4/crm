"""Room isolation, shared admission, expiry and mixed subscription regression tests."""
import json
import sqlite3
import tempfile
import time
import unittest
import uuid
import threading
import urllib.request
from urllib.parse import urlsplit, parse_qs
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from scripts.vpn import olcrtc_control, olcrtc_node, client_guides, bot_ui
from scripts.vpn import test_control


class RoomTests(unittest.TestCase):
    setUp = test_control.ControlTests.setUp
    tearDown = test_control.ControlTests.tearDown
    create = test_control.ControlTests.create
    ready = test_control.ControlTests.ready

    def test_mixed_subscription_headers_and_lazy_allocation(self):
        value = self.create(); self.ready(value['id'])
        server = self.control.ThreadingHTTPServer(('127.0.0.1', 0), self.control.Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        url = 'http://127.0.0.1:' + str(server.server_port) + '/sub/' + value['subscription_url'].split('/sub/')[1]
        try:
            with patch.object(olcrtc_control, 'JITSI_BASE', 'https://meet.example.com'):
                with urllib.request.urlopen(url + '?format=happ') as response:
                    self.assertEqual(response.status, 200)
                with self.control.database() as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM olcrtc_rooms').fetchone()[0], 0)
                with urllib.request.urlopen(url + '?format=ghostlane') as response:
                    self.assertTrue(response.headers['announce'].startswith('base64:'))
                    self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
                    self.assertNotIn('Olcrtc', response.read().decode())
                with self.control.database() as db:
                    db.execute('UPDATE olcrtc_rooms SET ready=1,checked_at=?', (time.time(),))
                with urllib.request.urlopen(url + '?format=ghostlane') as response:
                    payload = response.read().decode()
                    self.assertIn('Olcrtc', payload)
                    self.assertNotIn('vless://', payload)
                    self.assertIn('hysteria2://', payload)
                    config = json.loads(payload)
                    self.assertEqual(config['version'], 4)
                    self.assertIsNone(response.headers.get('profile-title'))
                    groups = {item['metadata']['subscription']['name'] for item in config['locations']}
                    self.assertEqual(groups, {'Обычный VPN · все страны', 'Обход ограничений · olcRTC'})
                    self.assertIsNone(response.headers.get('announce'))
                    ordinary = [item for item in config['locations'] if item['kind'] != 'Olcrtc']
                    with self.control.database() as db:
                        row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
                        expected_links = self.control.connection_configs(row, db)[1]
                    self.assertEqual(len(ordinary), sum(link.startswith('hysteria2://') for link in expected_links))
                    for item in ordinary:
                        if item['kind'] == 'Hysteria2':
                            link = item['raw_link']
                            authority = link.split('://', 1)[1].split('?', 1)[0]
                            self.assertNotIn('/', authority)
                            self.assertNotIn('%3A', authority)
                            self.assertIn(':', authority.split('@', 1)[0])
                            int(authority.rsplit(':', 1)[1])
                    rtc_entries = [item for item in config['locations'] if item['kind'] == 'Olcrtc']
                    self.assertEqual(len(rtc_entries), 1)
                    self.assertEqual(rtc_entries[0]['metadata']['name'], 'Подключиться · olcRTC')
                    self.assertIn('белыми списками', rtc_entries[0]['metadata']['subscription']['announce'])
                    self.assertEqual(rtc_entries[0]['auth_provider'], 'jitsi')
                    self.assertEqual(rtc_entries[0]['transport']['type'], 'datachannel')
                    self.assertEqual(len(rtc_entries[0]['endpoint']['key']), 64)
                    self.assertEqual(config['active_location_id'], rtc_entries[0]['storage_id'])
                    self.assertEqual(config['locations'][0]['kind'], 'Olcrtc')
                with urllib.request.urlopen(url + '?format=ghostlane&view=all') as response:
                    advanced = json.load(response)
                    self.assertEqual(advanced, config)
                with urllib.request.urlopen(url + '?format=happ') as response:
                    self.assertNotIn('olcrtc://', response.read().decode())
        finally:
            server.shutdown(); thread.join(); server.server_close()
    def test_stable_private_room_per_client_and_balanced_placement(self):
        first, second = self.create(), self.create()
        with patch.object(olcrtc_control, 'JITSI_BASE', 'https://meet.example.com'), self.control.database() as db:
            a = db.execute('SELECT * FROM subscriptions WHERE id=?', (first['id'],)).fetchone()
            b = db.execute('SELECT * FROM subscriptions WHERE id=?', (second['id'],)).fetchone()
            room = olcrtc_control.ensure(db, a, ['pl', 'fi'])
            self.assertEqual(room['node_id'], 'pl')
            self.assertEqual(olcrtc_control.ensure(db, a, ['fi', 'pl'])['room'], room['room'])
            other = olcrtc_control.ensure(db, b, ['pl', 'fi'])
            self.assertEqual(other['node_id'], 'fi')
            self.assertNotEqual(other['room'], room['room'])
            self.assertNotEqual(olcrtc_control.key(a), olcrtc_control.key(b))
            self.assertEqual(olcrtc_control.links(db, a), [])
            db.execute('UPDATE olcrtc_rooms SET ready=1,checked_at=?', (time.time(),))
            self.assertTrue(olcrtc_control.links(db, a)[0].startswith('olcrtc://jitsi?datachannel@'))
            db.execute('UPDATE olcrtc_rooms SET checked_at=?', (time.time() - 121,))
            self.assertEqual(olcrtc_control.links(db, a), [])

    def test_rtc_devices_share_limit_with_direct_connections_and_release(self):
        value = self.create(); self.ready(value['id'])
        with tempfile.TemporaryDirectory() as directory, patch.object(olcrtc_node, 'STATE', Path(directory)):
            state = Path(directory)
            config = {'lease_token': 'test-rtc-node-token'}
            (state / 'agent.json').write_text(json.dumps(config))
            with closing(sqlite3.connect(state / 'clients.sqlite')) as db, db:
                db.execute('CREATE TABLE clients(id TEXT,expiry REAL,enabled INTEGER)')
                db.execute('INSERT INTO clients VALUES(?,?,1)', (value['id'], time.time() + 3600))
            authorization = 'Bearer ' + olcrtc_node.auth_token(value['id'], config)
            direct = {'action': 'acquire', 'subscription_id': value['id'], 'lease_id': str(uuid.uuid4()), 'ip': '203.0.113.5'}
            self.assertTrue(self.control.connection_lease('fi', direct)['allowed'])
            body = {'action': 'acquire', 'subscription_id': value['id'], 'lease_id': str(uuid.uuid4()), 'device_id': 'phone'}
            central = lambda payload: self.control.connection_lease('pl', payload)
            self.assertFalse(olcrtc_node.authorize(body, 'Bearer wrong', central)['allowed'])
            self.assertTrue(olcrtc_node.authorize(body, authorization, central)['allowed'])
            second = dict(body, lease_id=str(uuid.uuid4()), device_id='laptop')
            self.assertTrue(olcrtc_node.authorize(second, authorization, central)['allowed'])
            third = dict(body, lease_id=str(uuid.uuid4()), device_id='tablet')
            self.assertFalse(olcrtc_node.authorize(third, authorization, central)['allowed'])
            olcrtc_node.authorize(dict(second, action='release'), authorization, central)
            self.assertTrue(olcrtc_node.authorize(third, authorization, central)['allowed'])
            self.assertTrue(olcrtc_node.authorize(dict(body, action='renew'), authorization, central)['allowed'])
            with closing(sqlite3.connect(state / 'clients.sqlite')) as db, db:
                db.execute('UPDATE clients SET enabled=0')
            self.assertFalse(olcrtc_node.authorize(dict(body, action='renew'), authorization, central)['allowed'])
            olcrtc_node.authorize(dict(body, action='release'), authorization, central)
            with self.control.database() as db:
                view = self.control.subscription_view(db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone(), db)
            self.assertEqual(view['occupied_slots'], 2)
            self.assertNotIn('connections', view)

    def test_ghostlane_guide_covers_all_platforms_and_bot(self):
        value = self.create()
        page = client_guides.page('https://vpn.example.com', value['subscription_url'])
        for marker in ('ghostlane-ios', 'ghostlane-desktop', 'format=ghostlane', 'id6795355210', 'Добавить в Ghostlane', 'proofkit://add?url='):
            self.assertIn(marker, page)
        text, markup = bot_ui.connect(value, 'https://vpn.example.com', 'ghostlane')
        self.assertIn('olcRTC', text)
        for label in ('Обход ограничений · olcRTC', 'Обычный VPN · все страны', 'Добавить в Ghostlane'):
            self.assertIn(label, text)
        self.assertIn('format=ghostlane', json.dumps(markup))

    def test_native_import_preserves_subscription_payload_for_every_client(self):
        subscription = 'https://vpn.example.com/sub/token%2Fwith%20escape'
        for key in ('happ', 'happ-ios', 'ghostlane', 'ghostlane-ios', 'ghostlane-desktop', 'clashmeta', 'v2rayng', 'koala'):
            link = client_guides.import_link(key, subscription)
            expected_format = 'ghostlane' if key.startswith('ghostlane') else 'happ' if key.startswith('happ') else 'clash' if key in ('koala', 'clashmeta') else 'v2rayng'
            payload = link.removeprefix('happ://add/') if key.startswith('happ') else parse_qs(urlsplit(link).query)['url'][0]
            self.assertEqual(payload, subscription + '?format=' + expected_format)
        page = client_guides.page('https://vpn.example.com', subscription)
        for name in ('Happ', 'Ghostlane', 'Clash Meta', 'v2rayNG', 'Koala Clash'):
            self.assertIn('Добавить в ' + name, page)
        self.assertIsNone(client_guides.import_link('happ', None))

if __name__ == '__main__':
    unittest.main()
