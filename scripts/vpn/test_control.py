"""Critical lifecycle and isolation tests, runnable without CRM databases or servers."""
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
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
        self.contact_sequence = getattr(self, 'contact_sequence', 11) + 1
        return self.control.create({'contact_id': self.contact_sequence, 'contact_name': 'Test contact', 'days': 30, 'kind': 'gift', 'actor_id': 5})

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

    def test_trial_creation_retry_preserves_subscription_and_audit(self):
        body = {'contact_id': 12, 'contact_name': 'Test contact', 'days': 3, 'kind': 'trial',
                'actor_id': 5, 'source_chat_id': 42, 'idempotency_key': str(uuid.uuid4())}
        first = self.control.create(body)
        second = self.control.create(body)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['expires_at'], second['expires_at'])
        self.assertNotIn('create_request_key', first)
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM subscriptions').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE action='trial'").fetchone()[0], 1)
        with self.assertRaises(ValueError):
            self.control.create({**body, 'contact_id': 99})

    def test_selected_periods_and_expired_trial_renewal(self):
        for days in (1, 3, 7, 14, 21):
            with self.subTest(days=days):
                with patch.object(self.control.time, 'time', return_value=1000000):
                    value = self.control.create({'contact_id': 12 + days, 'contact_name': 'Test contact', 'days': days, 'kind': 'trial', 'actor_id': 5})
                self.assertEqual(value['expires_at'], 1000000 + days * 86400)
                with patch.object(self.control.time, 'time', return_value=9000000):
                    renewed = self.control.mutate(value['id'], {'action': 'renew', 'days': days, 'actor_id': 5})
                self.assertEqual(renewed['expires_at'], 9000000 + days * 86400)
                self.assertTrue(renewed['enabled'])

    def test_one_day_trial_is_named_correctly_in_telegram_status(self):
        from scripts.vpn import bot_cabinet
        with patch.object(self.control.time, 'time', return_value=1000000):
            self.control.create({'contact_id': 12, 'contact_name': 'Test contact', 'days': 1,
                                 'kind': 'trial', 'actor_id': 5, 'telegram_user_id': 555})
        update = {'message': {'chat': {'type': 'private', 'id': 555}, 'from': {'id': 555}, 'text': '/status'}}
        with patch.object(self.control.time, 'time', return_value=1000001), patch.object(self.control, 'telegram', return_value={'message_id': 200}) as telegram:
            bot_cabinet.handle(self.control, update, 'test-placeholder')
        texts = [call.args[1].get('text', '') for call in telegram.call_args_list if call.args[0] == 'sendMessage']
        self.assertTrue(any('Пробный период' in text and 'осталось 24 ч.' in text for text in texts))

    def test_all_countries_and_balanced_auto(self):
        value = self.create(); self.ready(value['id'])
        with self.control.database() as db:
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, links, automatic = self.control.connection_configs(row, db)
        self.assertEqual(len(proxies), 14)
        self.assertEqual(len(links), 14)
        self.assertEqual(len(automatic), 14)  # every healthy country is probed from the client
        self.assertEqual({proxy['server'] for proxy in proxies if proxy['type'] == 'vless'}, {node['host'] for node in self.control.NODES})
        self.metrics['nodes'][0]['eligible_for_new_users'] = False
        self.assertNotIn('pl', self.control.ranked_nodes(value['id'], self.metrics))
        with self.control.database() as db:
            proxies, links, automatic = self.control.connection_configs(row, db)
        self.assertEqual(len(proxies), 14)  # manual profiles stay available
        self.assertEqual(len(automatic), 12)
        self.assertFalse(any(name.startswith(self.control.NODES[0]['name'] + ' ·') for name in automatic))

    def test_distribution_and_overload_weight(self):
        counts = dict.fromkeys([node['id'] for node in self.control.NODES], 0)
        for number in range(1400):
            counts[self.control.ranked_nodes(str(number), self.metrics)[0]] += 1
        self.assertTrue(all(140 < count < 260 for count in counts.values()), counts)
        self.metrics['nodes'][0]['cpu_percent'] = 80
        loaded = sum(self.control.ranked_nodes(str(number), self.metrics)[0] == 'pl' for number in range(1400))
        self.assertLess(loaded, 40)

    def test_transport_and_port_fallbacks_keep_distinct_profiles(self):
        value = self.create(); self.ready(value['id'])
        with self.control.database() as db:
            node = self.control.NODES[0]
            stored = json.loads(db.execute('SELECT data FROM endpoints WHERE node_id=?', (node['id'],)).fetchone()[0])
            first, hy = stored
            second = {**first, 'server': node['ips'][1]}
            endpoints = [first, second, {**hy, 'port': 443}, {**hy, 'variant': 'fallback'}]
            db.execute('UPDATE endpoints SET data=? WHERE node_id=?', (json.dumps(endpoints), node['id']))
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, links, automatic = self.control.connection_configs(row, db)
        local = [proxy for proxy in proxies if proxy['name'].startswith(node['name'] + ' ·')]
        self.assertEqual([proxy['xhttp-opts']['mode'] for proxy in local[:2]], ['auto', 'packet-up'])
        self.assertEqual([proxy['port'] for proxy in local[2:]], [443, 8444])
        self.assertEqual(len({proxy['name'] for proxy in proxies}), len(proxies))
        self.assertTrue(any('mode=packet-up' in link for link in links))
        self.assertEqual(len(automatic), len(proxies))
        auto = self.control.happ_configs(proxies, automatic)[0]
        self.assertEqual(auto['observatory']['probeInterval'], '30s')
        self.assertIn('https://dns.quad9.net/dns-query', auto['dns']['servers'])
        # A fixed server mode must never be changed to an incompatible client mode.
        endpoints[1]['xhttp'] = {'path': '/test', 'mode': 'stream-up'}
        with self.control.database() as db:
            db.execute('UPDATE endpoints SET data=? WHERE node_id=?', (json.dumps(endpoints), node['id']))
            proxies, _, _ = self.control.connection_configs(row, db)
        second = next(proxy for proxy in proxies if proxy['server'] == node['ips'][1] and proxy['type'] == 'vless')
        self.assertEqual(second['xhttp-opts']['mode'], 'stream-up')

    def test_gaming_variants_are_named_and_available_in_every_format(self):
        from scripts.vpn.install_operator_fallbacks import GAMING_TARGETS
        from urllib.parse import unquote
        value = self.create(); self.ready(value['id'])
        with self.control.database() as db:
            for node in self.control.NODES:
                stored = json.loads(db.execute('SELECT data FROM endpoints WHERE node_id=?', (node['id'],)).fetchone()[0])
                for index, (brand, target) in enumerate(GAMING_TARGETS.items()):
                    gaming = {**stored[0], 'port': 8450 + index, 'sni': target, 'game_brand': brand}
                    stored.append(gaming)
                db.execute('UPDATE endpoints SET data=? WHERE node_id=?', (json.dumps(stored), node['id']))
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, links, automatic = self.control.connection_configs(row, db)
        self.assertEqual(len(proxies), 63)
        self.assertEqual(len(automatic), 63)
        self.assertEqual(len(set(automatic)), 63)
        happ = self.control.happ_configs(proxies, automatic)
        self.assertEqual(len(happ), 8)
        self.assertEqual(len(self.control.happ_configs(proxies, automatic, expanded=True)), 64)
        clash = self.control.clash_configs(proxies, automatic)
        self.assertEqual(len(clash['proxies']), 63)
        groups = {group['name']: group for group in clash['proxy-groups']}
        self.assertEqual(groups['VPN']['proxies'], ['AUTO'] + [self.control.country_label(node['name']) for node in self.control.NODES])
        self.assertEqual(len(groups['AUTO']['proxies']), 63)
        self.assertTrue(all(group.get('hidden') for name, group in groups.items() if name != 'VPN'))
        for node in self.control.NODES:
            country = next(profile for profile in happ if profile['remarks'] == self.control.country_label(node['name']))
            self.assertEqual(len(country['outbounds']), 10)  # nine methods and direct
            self.assertEqual(len(groups[self.control.country_label(node['name'])]['proxies']), 9)
            self.assertEqual(country['routing']['balancers'][0]['strategy']['type'], 'leastPing')
            for index, (brand, target) in enumerate(GAMING_TARGETS.items()):
                name = node['name'] + ' · ' + brand
                proxy = next(proxy for proxy in proxies if proxy['name'] == name)
                self.assertEqual(proxy['servername'], target)
                self.assertEqual(proxy['port'], 8450 + index)
                self.assertTrue(any(unquote(link).endswith('#' + name) for link in links))
                self.assertTrue(any(outbound.get('streamSettings', {}).get('realitySettings', {}).get('serverName') == target
                                    for outbound in happ[0]['outbounds']))
                self.assertTrue(any(outbound.get('streamSettings', {}).get('realitySettings', {}).get('serverName') == target
                                    for outbound in country['outbounds']))

    def test_restricted_network_variants_stay_inside_compact_country_profiles(self):
        from scripts.vpn.install_operator_fallbacks import RESTRICTED_TARGETS
        from urllib.parse import unquote
        value = self.create(); self.ready(value['id'])
        with self.control.database() as db:
            for node in self.control.NODES:
                stored = json.loads(db.execute('SELECT data FROM endpoints WHERE node_id=?', (node['id'],)).fetchone()[0])
                for index, (brand, target) in enumerate(RESTRICTED_TARGETS.items()):
                    stored.append({**stored[0], 'port': 8460 + index, 'sni': target, 'service_brand': brand})
                db.execute('UPDATE endpoints SET data=? WHERE node_id=?', (json.dumps(stored), node['id']))
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, links, automatic = self.control.connection_configs(row, db)
        happ = self.control.happ_configs(proxies, automatic)
        clash = self.control.clash_configs(proxies, automatic)
        self.assertEqual(len(happ), 8)
        self.assertEqual(len(clash['proxy-groups'][0]['proxies']), 8)
        self.assertEqual(len(proxies), 56)
        self.assertEqual(len(automatic), 56)
        self.assertEqual(len({proxy['name'] for proxy in proxies}), 56)
        self.assertEqual(len(happ[0]['outbounds']), 57)  # all methods and direct
        groups = {group['name']: group for group in clash['proxy-groups']}
        self.assertEqual(len(groups['AUTO']['proxies']), 56)
        self.assertNotIn('AUTO · белые списки', groups)
        for node in self.control.NODES:
            country = next(profile for profile in happ if profile['remarks'] == self.control.country_label(node['name']))
            for brand, target in RESTRICTED_TARGETS.items():
                name = node['name'] + ' · БС · ' + brand
                self.assertTrue(any(proxy['name'] == name and proxy.get('servername') == target for proxy in clash['proxies']))
                self.assertTrue(any(unquote(link).endswith('#' + name) for link in links))
                self.assertTrue(any(outbound.get('streamSettings', {}).get('realitySettings', {}).get('serverName') == target
                                    for outbound in country['outbounds']))

    def test_tcp_qq_pilot_reaches_happ_and_uri_without_breaking_clash(self):
        from scripts.vpn.install_operator_fallbacks import RESTRICTED_TCP_TARGETS
        from urllib.parse import parse_qs, unquote, urlsplit
        value = self.create(); self.ready(value['id'])
        node = self.control.NODES[0]
        with self.control.database() as db:
            stored = json.loads(db.execute('SELECT data FROM endpoints WHERE node_id=?', (node['id'],)).fetchone()[0])
            for brand, options in RESTRICTED_TCP_TARGETS.items():
                stored.append({**stored[0], 'network': 'tcp', 'xhttp': {}, 'port': options['port'],
                               'sni': options['target'], 'service_brand': brand, 'fingerprint': 'qq'})
            db.execute('UPDATE endpoints SET data=? WHERE node_id=?', (json.dumps(stored), node['id']))
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, links, automatic = self.control.connection_configs(row, db)
        happ = self.control.happ_configs(proxies, automatic)
        clash = self.control.clash_configs(proxies, automatic)
        self.assertEqual(len(happ), 8)
        self.assertEqual(len(clash['proxy-groups'][0]['proxies']), 8)
        self.assertFalse(any(profile['remarks'].startswith('🧪 Тест') for profile in happ))
        for brand, options in RESTRICTED_TCP_TARGETS.items():
            label = node['name'] + ' · БС · ' + brand
            self.assertFalse(any(p['name'] == label for p in clash['proxies']))
            proxy = next(p for p in proxies if p['name'] == label)
            self.assertEqual(proxy['network'], 'tcp')
            self.assertEqual(proxy['client-fingerprint'], 'qq')
            self.assertNotIn('xhttp-opts', proxy)
            uri = next(urlsplit(link) for link in links if unquote(urlsplit(link).fragment) == label)
            self.assertEqual(uri.port, options['port'])
            query = parse_qs(uri.query)
            self.assertEqual(query['type'], ['tcp'])
            self.assertEqual(query['fp'], ['qq'])
            self.assertEqual(query['sni'], [options['target']])
            self.assertNotIn('path', query)
            outbound = next(o for o in happ[1]['outbounds'] if o.get('streamSettings', {}).get('realitySettings', {}).get('serverName') == options['target'])
            self.assertEqual(outbound['streamSettings']['network'], 'tcp')
            self.assertEqual(outbound['streamSettings']['realitySettings']['fingerprint'], 'qq')
            self.assertNotIn('xhttpSettings', outbound['streamSettings'])
        self.assertTrue(all(p['client-fingerprint'] == 'chrome' for p in proxies if p.get('network') == 'xhttp'))

    def test_verified_pilots_join_main_auto_and_countries_without_test_sections(self):
        from scripts.vpn.install_operator_fallbacks import RESTRICTED_TCP_TARGETS
        from scripts.vpn.install_shared_reality_sni import TARGETS
        value = self.create(); self.ready(value['id'])
        node = self.control.NODES[0]
        with self.control.database() as db:
            stored = json.loads(db.execute('SELECT data FROM endpoints WHERE node_id=?', (node['id'],)).fetchone()[0])
            for brand, options in RESTRICTED_TCP_TARGETS.items():
                stored.append({**stored[0], 'network': 'tcp', 'xhttp': {}, 'port': options['port'],
                               'sni': options['target'], 'service_brand': brand, 'fingerprint': 'chrome', 'test_profile': True})
            for brand, target in TARGETS.items():
                stored.append({**stored[0], 'port': 443, 'sni': target, 'service_brand': brand, 'fingerprint': 'chrome', 'test_profile': True})
            db.execute('UPDATE endpoints SET data=? WHERE node_id=?', (json.dumps(stored), node['id']))
        server = self.control.ThreadingHTTPServer(('127.0.0.1', 0), self.control.Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        path = '/sub/' + value['subscription_url'].split('/sub/')[1]
        try:
            with urllib.request.urlopen(base + path + '?format=happ') as response:
                profiles = json.load(response)
                self.assertEqual(response.headers['ping-type'], 'proxy')
            self.assertEqual(len(profiles), 8)
            self.assertEqual(profiles[0]['remarks'], '⚡ Автовыбор')
            self.assertEqual(len(profiles[0]['outbounds']), 21)
            self.assertEqual(len(profiles[1]['outbounds']), 9)
            for profile in profiles:
                self.assertNotIn('белые списки', profile['remarks'])
                self.assertNotIn('Тест', profile['remarks'])
                self.assertIn('observatory', profile)
                self.assertEqual(profile['routing']['rules'][-1]['balancerTag'], 'auto')
                self.assertEqual({item['protocol'] for item in profile['inbounds']}, {'socks', 'http'})
                self.assertTrue(all(item['listen'] == '127.0.0.1' for item in profile['inbounds']))
            with urllib.request.urlopen(base + path + '?format=clash') as response:
                clash = json.load(response)
            self.assertEqual(len(clash['proxies']), 20)
            self.assertEqual(len(clash['proxy-groups'][0]['proxies']), 8)
            groups = {group['name']: group for group in clash['proxy-groups']}
            self.assertEqual(len(groups['AUTO']['proxies']), 20)
            self.assertEqual(len(groups[self.control.country_label(node['name'])]['proxies']), 8)
            self.assertFalse(any('test-profile' in proxy for proxy in clash['proxies']))
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + '/sub/' + 'z' * 40 + '?format=happ')
            self.assertEqual(denied.exception.code, 404)
            self.control.mutate(value['id'], {'action': 'revoke', 'actor_id': 5})
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + path + '?format=happ')
            self.assertEqual(denied.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_compact_countries_stay_available_when_excluded_from_global_auto(self):
        value = self.create(); self.ready(value['id'])
        self.metrics['nodes'][0]['eligible_for_new_users'] = False
        with self.control.database() as db:
            row = db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone()
            proxies, _, automatic = self.control.connection_configs(row, db)
        country = self.control.NODES[0]['name']
        happ = self.control.happ_configs(proxies, automatic)
        self.assertEqual(len(happ), 8)
        self.assertTrue(any(profile['remarks'] == self.control.country_label(country) for profile in happ))
        self.assertEqual(len(happ[0]['outbounds']), 13)  # only healthy exits and direct
        groups = {group['name']: group for group in self.control.clash_configs(proxies, automatic)['proxy-groups']}
        self.assertIn(self.control.country_label(country), groups['VPN']['proxies'])
        self.assertFalse(any(name.startswith(country + ' · ') for name in groups['AUTO']['proxies']))
        self.assertEqual(len(groups[self.control.country_label(country)]['proxies']), 2)
        empty_auto = self.control.happ_configs(proxies, [])
        self.assertEqual(len(empty_auto), 7)
        self.assertTrue(all(profile.get('observatory') for profile in empty_auto))

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
                choices = config['proxy-groups'][0]['proxies']
                self.assertEqual(choices, ['AUTO'] + [self.control.country_label(node['name']) for node in self.control.NODES])
            with urllib.request.urlopen(base + '/sub/' + path + '?format=happ') as response:
                profiles = json.load(response)
                self.assertEqual(response.headers['ping-type'], 'proxy')
                self.assertEqual(response.headers['subscription-ping-onopen-enabled'], '1')
                self.assertEqual(len(profiles), 8)
                hysteria = [outbound for profile in profiles[1:] for outbound in profile['outbounds'] if outbound['protocol'] == 'hysteria']
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
            with urllib.request.urlopen(base + '/sub/' + path + '?format=happ&view=all') as response:
                self.assertEqual(len(json.load(response)), 15)
            with urllib.request.urlopen(base + '/sub/' + path + '?format=clash&view=all') as response:
                self.assertEqual(len(json.load(response)['proxy-groups'][0]['proxies']), 15)
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
        with patch.object(self.control, 'telegram', return_value={'message_id': 200}) as telegram:
            cabinet.handle(self.control, update, 'test-token')
        self.assertIn('недоступна', telegram.call_args.args[1]['text'])
        self.assertNotIn(value['subscription_url'], telegram.call_args.args[1]['text'])
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bot_requests').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT user_id FROM bot_users').fetchone()[0], 666)
        self.ready(value['id'])
        update['callback_query']['data'] = 'client:happ'
        with patch.object(self.control, 'telegram', return_value={'message_id': 200}) as telegram:
            cabinet.handle(self.control, update, 'test-token')
        self.assertNotIn(value['subscription_url'], telegram.call_args.args[1]['text'])
        update['callback_query']['from']['id'] = 555
        update['callback_query']['message']['chat']['id'] = 555
        with patch.object(self.control, 'telegram', return_value={'message_id': 200}) as telegram:
            cabinet.handle(self.control, update, 'test-token')
        self.assertIn(value['subscription_url'], json.dumps(telegram.call_args.args[1]))

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
                self.assertNotIn('🧪 Тест', page)
                self.assertNotIn('Автовыбор · белые списки', page)
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
