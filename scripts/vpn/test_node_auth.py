"""Real loopback Hysteria auth against shared admission; no network credentials."""
import importlib.util
import json
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from scripts.vpn import test_control


class NodeAuthTests(unittest.TestCase):
    setUp = test_control.ControlTests.setUp
    tearDown = test_control.ControlTests.tearDown
    create = test_control.ControlTests.create

    def node(self, node_id, identity, password):
        spec = importlib.util.spec_from_file_location('auth_' + node_id, Path(__file__).with_name('node_agent.py'))
        agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)
        agent.STATE = Path(self.temporary.name) / node_id
        agent.STATE.mkdir(exist_ok=True)
        (agent.STATE / 'agent.json').write_text(json.dumps({'lease_url': 'https://control.test/node/lease/' + node_id}))
        with agent.database() as db:
            db.execute('INSERT INTO clients VALUES(?,?,?,?)', (identity, password, time.time() + 3600, 1))
        agent.central_lease = lambda body: self.control.connection_lease(node_id, body)
        return agent

    def auth(self, agent, identity, password, ip):
        server = agent.ThreadingHTTPServer(('127.0.0.1', 0), agent.AuthHandler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            request = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + '/auth',
                data=json.dumps({'addr': ip + ':20000', 'auth': identity + ':' + password}).encode(),
                headers={'Content-Type': 'application/json'})
            with patch.object(agent, 'note_failure'):
                with urllib.request.urlopen(request, timeout=3) as response:
                    return json.load(response)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_same_user_ip_can_authenticate_on_multiple_nodes(self):
        value = self.create(); password = 'fixture-password-' + 'x' * 32
        nodes = [self.node(node, value['id'], password) for node in ('pl', 'fi', 'ch')]
        for agent in nodes:
            self.assertTrue(self.auth(agent, value['id'], password, '203.0.113.1')['ok'])
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connection_leases').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT COUNT(DISTINCT ip) FROM connection_leases').fetchone()[0], 1)
        ids = [agent.hysteria_lease_id(value['id'] + '@203.0.113.1') for agent in nodes]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids[0], nodes[0].hysteria_lease_id(value['id'] + '@203.0.113.1'))

    def test_quota_and_node_owned_release_remain_enforced(self):
        value = self.create(); password = 'fixture-password-' + 'x' * 32
        first = self.node('pl', value['id'], password)
        second = self.node('fi', value['id'], password)
        for ip in ('203.0.113.1', '203.0.113.2', '203.0.113.3'):
            self.assertTrue(self.auth(first, value['id'], password, ip)['ok'])
        self.assertTrue(self.auth(second, value['id'], password, '203.0.113.1')['ok'])
        self.assertFalse(self.auth(second, value['id'], password, '203.0.113.4')['ok'])
        first.guard_release(first.hysteria_lease_id(value['id'] + '@203.0.113.2'))
        self.assertTrue(self.auth(second, value['id'], password, '203.0.113.4')['ok'])


if __name__ == '__main__':
    unittest.main()
