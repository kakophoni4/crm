"""Critical lifecycle and isolation tests, runnable without CRM databases or servers."""
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        os.environ['VPN_NODES_FILE'] = str(Path(__file__).with_name('nodes.example.json'))
        spec = importlib.util.spec_from_file_location('vpn_control_test', Path(__file__).with_name('control_service.py'))
        self.control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.control)
        self.control.HOME = Path(self.temporary.name)
        self.control.API_KEY = 'test-control-key-' + 'x' * 32
        self.control.initialize()
        self.metrics = {'nodes': [{'id': node['id'], 'eligible_for_new_users': True, 'cpu_percent': 5, 'memory_percent': 30}
                                  for node in self.control.NODES]}
        self.mock = patch.object(self.control, 'snapshot', return_value=self.metrics)
        self.mock.start()

    def tearDown(self):
        self.mock.stop(); self.temporary.cleanup()

    def create(self):
        return self.control.create({'contact_id': 12, 'contact_name': 'Test contact', 'days': 30, 'kind': 'gift', 'actor_id': 5})

    def ready(self, identity):
        with self.control.database() as db:
            db.execute("UPDATE deliveries SET version=1,status='synced' WHERE subscription_id=?", (identity,))
            for node in self.control.NODES:
                endpoints = [{'type': 'vless', 'server': node['host'], 'port': 443, 'public_key': 'test-public-key',
                              'short_id': '12345678', 'sni': 'example.com', 'network': 'xhttp', 'xhttp': {'path': '/test', 'mode': 'auto'}},
                             {'type': 'hysteria2', 'server': node['ips'][2], 'port': 8444, 'obfs': 'test-obfs', 'pin': 'ab' * 32}]
                db.execute('INSERT INTO endpoints VALUES(?,?,?)', (node['id'], json.dumps(endpoints), time.time()))

    def test_personal_secrets_unique_and_hidden(self):
        first, second = self.create(), self.create()
        self.assertNotEqual(first['subscription_url'], second['subscription_url'])
        self.assertNotEqual(first['id'], second['id'])
        self.assertNotIn('password', first)
        self.assertNotIn('token', first)
        self.assertEqual(first['ready_nodes'], 0)
        self.assertEqual(first['status'], 'provisioning')

    def test_all_countries_and_balanced_auto(self):
        value = self.create(); self.ready(value['id'])
        with self.control.database() as db:
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, links, automatic = self.control.connection_configs(row, db)
        self.assertEqual(len(proxies), 14)
        self.assertEqual(len(links), 14)
        self.assertEqual(len(automatic), 6)  # two protocols on three assigned countries
        self.assertEqual({proxy['server'] for proxy in proxies if proxy['type'] == 'vless'}, {node['host'] for node in self.control.NODES})
        self.metrics['nodes'][0]['eligible_for_new_users'] = False
        self.assertNotIn('pl', self.control.ranked_nodes(value['id'], self.metrics))

    def test_distribution_and_overload_weight(self):
        counts = dict.fromkeys([node['id'] for node in self.control.NODES], 0)
        for number in range(1400):
            counts[self.control.ranked_nodes(str(number), self.metrics)[0]] += 1
        self.assertTrue(all(140 < count < 260 for count in counts.values()), counts)
        self.metrics['nodes'][0]['cpu_percent'] = 80
        loaded = sum(self.control.ranked_nodes(str(number), self.metrics)[0] == 'pl' for number in range(1400))
        self.assertLess(loaded, 40)

    def test_revocation_renewal_and_rotated_link(self):
        value = self.create(); self.ready(value['id'])
        revoked = self.control.mutate(value['id'], {'action': 'revoke', 'actor_id': 5})
        self.assertEqual(revoked['status'], 'revoked'); self.assertEqual(revoked['ready_nodes'], 0)
        renewed = self.control.mutate(value['id'], {'action': 'renew', 'actor_id': 5, 'days': 7})
        self.assertTrue(renewed['enabled']); self.assertEqual(renewed['expires_at'], value['expires_at'] + 7 * 86400)
        rotated = self.control.mutate(value['id'], {'action': 'rotate_link', 'actor_id': 5})
        self.assertNotEqual(rotated['subscription_url'], value['subscription_url'])
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 4)

    def test_deleted_subscription_is_hidden_and_cannot_be_reactivated(self):
        value = self.create(); self.ready(value['id'])
        self.control.mutate(value['id'], {'action': 'delete', 'actor_id': 5})
        with self.control.database() as db:
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            self.assertFalse(row['enabled']); self.assertIsNotNone(row['deleted_at'])
            self.assertEqual(row['version'], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE action='delete'").fetchone()[0], 1)
        with self.assertRaises(ValueError):
            self.control.mutate(value['id'], {'action': 'resume', 'actor_id': 5})
        server = self.control.ThreadingHTTPServer(('127.0.0.1', 0), self.control.Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + '/sub/' + value['subscription_url'].split('/sub/')[1])
            self.assertEqual(denied.exception.code, 404)
            request = urllib.request.Request(base + '/internal/subscriptions', headers={'Authorization': 'Bearer ' + self.control.API_KEY})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(json.load(response)['items'], [])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_http_denies_internal_without_key_and_revoked_public_subscription(self):
        value = self.create(); self.ready(value['id'])
        server = self.control.ThreadingHTTPServer(('127.0.0.1', 0), self.control.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        path = value['subscription_url'].split('/sub/')[1]
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + '/internal/subscriptions')
            self.assertEqual(denied.exception.code, 404)
            with urllib.request.urlopen(base + '/sub/' + path + '?format=clash') as response:
                config = json.load(response)
                self.assertEqual(len(config['proxies']), 14)
                self.assertIn('GEOIP,RU,DIRECT', config['rules'])
            with urllib.request.urlopen(base + '/sub/' + path + '?format=happ') as response:
                profiles = json.load(response)
                self.assertEqual(len(profiles), 15)
                hysteria = [p['outbounds'][0] for p in profiles[1:] if p['outbounds'][0]['protocol'] == 'hysteria']
                self.assertEqual(len(hysteria), 7)
                for outbound in hysteria:
                    self.assertEqual(outbound['settings']['version'], 2)
                    stream = outbound['streamSettings']
                    self.assertEqual(stream['tlsSettings']['pinnedPeerCertSha256'], 'ab' * 32)
                    self.assertEqual(stream['finalmask']['udp'][0]['settings']['password'], 'test-obfs')
                    with self.control.database() as db:
                        credential = db.execute('SELECT id,password FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
                    self.assertEqual(stream['hysteriaSettings']['auth'], credential['id'] + ':' + credential['password'])
                self.assertTrue(any(p['protocol'] == 'hysteria' for p in profiles[0]['outbounds']))
                self.assertIn('Автовыбор', profiles[0]['remarks'])
                self.assertEqual(profiles[0]['routing']['balancers'][0]['strategy']['type'], 'leastPing')
                self.assertIn('geoip:ru', profiles[0]['routing']['rules'][1]['ip'])
                profile = json.loads(__import__('base64').b64decode(response.headers['routing'].removeprefix('happ://routing/onadd/')))
                self.assertIn('geosite:category-ru', profile['DirectSites'])
            self.control.mutate(value['id'], {'action': 'revoke', 'actor_id': 5})
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + '/sub/' + path)
            self.assertEqual(denied.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_bot_change_requires_bound_single_use_confirmation(self):
        self.control.BOT_ID = 100
        self.control.BOT_TOKEN = 'old-private-token'
        with self.control.database() as db:
            db.execute('INSERT INTO bot_users VALUES(?,?,?,?)', (100, 555, time.time(), time.time()))
        server = self.control.ThreadingHTTPServer(('127.0.0.1', 0), self.control.Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def post(path, body):
            request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                headers={'Authorization': 'Bearer ' + self.control.API_KEY, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                return json.load(response)
        def telegram(method, body, token=None):
            return {'username': 'test_bot'} if method == 'getMe' else {'url': ''}
        try:
            with patch.object(self.control, 'telegram', side_effect=telegram):
                prepared = post('/internal/bot/prepare', {'token': 'new-secret-token-' + 'x' * 30, 'actor_id': 5})
                self.assertNotIn('token', prepared)
                body = {'challenge': prepared['challenge'], 'actor_id': 6, 'confirmation': 'ЗАМЕНИТЬ БОТА'}
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    post('/internal/bot/confirm', body)
                self.assertEqual(denied.exception.code, 400)
                body['actor_id'] = 5; body['confirmation'] = 'wrong'
                with self.assertRaises(urllib.error.HTTPError): post('/internal/bot/confirm', body)
                body['confirmation'] = 'ЗАМЕНИТЬ БОТА'
                self.assertEqual(post('/internal/bot/confirm', body)['username'], 'test_bot')
                with self.assertRaises(urllib.error.HTTPError): post('/internal/bot/confirm', body)
                with self.control.database() as db:
                    self.assertIsNotNone(db.execute("SELECT value FROM settings WHERE key='telegram_token'").fetchone())
                    self.assertNotIn('secret-token', db.execute("SELECT details FROM events WHERE action='bot_changed'").fetchone()[0])
                    notification = db.execute('SELECT * FROM bot_notifications').fetchone()
                    self.assertEqual(notification['user_id'], 555)
                    self.assertEqual(notification['token'], 'old-private-token')
                    self.assertIn('https://t.me/test_bot', notification['text'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_cabinet_refuses_foreign_subscription_and_deduplicates_requests(self):
        spec = importlib.util.spec_from_file_location('cabinet_test', Path(__file__).with_name('bot_cabinet.py'))
        cabinet = importlib.util.module_from_spec(spec); spec.loader.exec_module(cabinet)
        value = self.create()
        with self.control.database() as db:
            db.execute('UPDATE subscriptions SET telegram_user_id=? WHERE id=?', (555, value['id']))
        cabinet.request(self.control, 666, 'renew', value['id'])
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bot_requests').fetchone()[0], 0)
        first = cabinet.request(self.control, 555, 'renew', value['id'])
        second = cabinet.request(self.control, 555, 'renew', value['id'])
        self.assertIn('сохранена', first); self.assertIn('уже ожидает', second)
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bot_requests').fetchone()[0], 1)
        update = {'callback_query': {'id': 'callback-test', 'from': {'id': 666},
            'data': 'confirm_renew:' + value['id'], 'message': {'chat': {'type': 'private', 'id': 666}}}}
        with patch.object(self.control, 'telegram', return_value={}) as telegram:
            cabinet.handle(self.control, update, 'test-token')
        self.assertIn('недоступна', telegram.call_args.args[1]['text'])
        self.assertNotIn(value['subscription_url'], telegram.call_args.args[1]['text'])
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bot_requests').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT user_id FROM bot_users').fetchone()[0], 666)
        self.ready(value['id'])
        update['callback_query']['data'] = 'client:happ'
        with patch.object(self.control, 'telegram', return_value={}) as telegram:
            cabinet.handle(self.control, update, 'test-token')
        self.assertNotIn(value['subscription_url'], telegram.call_args.args[1]['text'])
        update['callback_query']['from']['id'] = 555
        with patch.object(self.control, 'telegram', return_value={}) as telegram:
            cabinet.handle(self.control, update, 'test-token')
        self.assertIn(value['subscription_url'], telegram.call_args.args[1]['text'])

    def test_personal_guide_revocation_and_download_path_isolation(self):
        value = self.create(); self.ready(value['id'])
        server = self.control.ThreadingHTTPServer(('127.0.0.1', 0), self.control.Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        guide = base + '/sub/' + value['subscription_url'].split('/sub/')[1] + '?format=guide'
        try:
            with urllib.request.urlopen(guide) as response:
                self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
                page = response.read().decode()
                self.assertIn(value['happ_url'], page)
                self.assertIn(value['v2rayng_url'], page)
            with urllib.request.urlopen(base + '/apps') as response:
                self.assertNotIn(value['subscription_url'], response.read().decode())
            for path in ('/downloads/../control.env', '/downloads/manifest.json', '/downloads/happ.apk.tmp'):
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(base + path)
                self.assertEqual(denied.exception.code, 404)
            self.control.mutate(value['id'], {'action': 'revoke', 'actor_id': 5})
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(guide)
            self.assertEqual(denied.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_reconciler_retries_without_marking_failure_ready(self):
        value = self.create()
        def node_call(node_id, body):
            if body['operation'] == 'metadata':
                return {'endpoints': []}
            if body['operation'] == 'usage':
                return {'users': {}}
            raise RuntimeError('node failed')
        with patch.object(self.control, 'node_call', side_effect=node_call):
            self.control.reconcile_node(self.control.NODES[0])
        with self.control.database() as db:
            delivery = db.execute('SELECT * FROM deliveries WHERE subscription_id=? AND node_id=?', (value['id'], 'pl')).fetchone()
        self.assertEqual(delivery['status'], 'retrying'); self.assertEqual(delivery['version'], 0)

    def test_request_renewal_is_atomic_and_retries_do_not_add_days(self):
        value = self.create()
        with self.control.database() as db:
            db.execute('UPDATE subscriptions SET telegram_user_id=555 WHERE id=?', (value['id'],))
            identity = db.execute("INSERT INTO bot_requests(contact_id,subscription_id,user_id,kind,created_at) VALUES(?,?,?,?,?)", (12, value['id'], 555, 'renew', time.time())).lastrowid
        first = self.control.renew_request(identity, {'days': 7, 'actor_id': 5})
        second = self.control.renew_request(identity, {'days': 7, 'actor_id': 5})
        self.assertFalse(first['already_processed']); self.assertTrue(second['already_processed'])
        with self.control.database() as db:
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            self.assertEqual(row['expires_at'], value['expires_at'] + 7 * 86400)
            self.assertEqual(db.execute('SELECT state FROM bot_requests WHERE id=?', (identity,)).fetchone()[0], 'done')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE subscription_id=? AND action='renew'", (value['id'],)).fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
