"""Global admission, concurrency, NAT and issuance rules; no live credentials required."""
import concurrent.futures
import uuid
import unittest

from scripts.vpn import test_control


class ConnectionLimitTests(unittest.TestCase):
    setUp = test_control.ControlTests.setUp
    tearDown = test_control.ControlTests.tearDown
    create = test_control.ControlTests.create
    def lease(self, identity, ip, node='pl', lease_id=None, action='acquire'):
        lease_id = lease_id or str(uuid.uuid4())
        result = self.control.connection_lease(node, {'action': action, 'lease_id': lease_id, 'subscription_id': identity, 'ip': ip})
        return lease_id, result

    def test_global_limit_nat_and_release(self):
        value = self.create()
        self.assertEqual(value['device_limit'], 3)
        leases = [self.lease(value['id'], f'203.0.113.{i}', node) for i, node in zip(range(1, 4), ('pl', 'rs', 'fi'))]
        self.assertTrue(all(result['allowed'] for _, result in leases))
        self.assertTrue(self.lease(value['id'], '203.0.113.1', 'ch')[1]['allowed'])
        self.assertFalse(self.lease(value['id'], '203.0.113.4', 'ee')[1]['allowed'])
        self.lease(value['id'], '203.0.113.2', 'rs', leases[1][0], 'release')
        self.assertTrue(self.lease(value['id'], '203.0.113.4', 'ee')[1]['allowed'])
        with self.control.database() as db:
            view = self.control.subscription_view(db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone(), db)
        self.assertEqual(view['occupied_slots'], 3)
        self.assertEqual(view['connections'][0]['nodes'], 'pl,ch')

    def test_concurrent_nodes_cannot_overbook(self):
        value = self.create()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda i: self.lease(value['id'], f'203.0.113.{i}')[1]['allowed'], range(1, 11)))
        self.assertEqual(sum(results), 3)

    def test_eight_maximum_and_lowering_kicks_excess_on_heartbeat(self):
        value = self.create()
        self.control.mutate(value['id'], {'action': 'set_device_limit', 'device_limit': 8, 'actor_id': 5})
        leases = [self.lease(value['id'], f'203.0.113.{i}') for i in range(1, 9)]
        self.assertTrue(all(result['allowed'] for _, result in leases))
        self.assertFalse(self.lease(value['id'], '203.0.113.9')[1]['allowed'])
        for invalid in (2, 9, '8', 3.0, True, None):
            with self.assertRaises(ValueError):
                self.control.mutate(value['id'], {'action': 'set_device_limit', 'device_limit': invalid, 'actor_id': 5})
        self.control.mutate(value['id'], {'action': 'set_device_limit', 'device_limit': 3, 'actor_id': 5})
        renewed = [self.lease(value['id'], f'203.0.113.{i}', lease_id=entry[0], action='renew')[1]['allowed'] for i, entry in enumerate(leases, 1)]
        self.assertEqual(renewed, [True] * 3 + [False] * 5)

    def test_expired_leases_free_places_and_cannot_be_renewed(self):
        value = self.create()
        leases = [self.lease(value['id'], f'203.0.113.{i}') for i in range(1, 4)]
        with self.control.database() as db:
            db.execute('UPDATE connection_leases SET expires_at=0')
        self.assertFalse(self.lease(value['id'], '203.0.113.1', lease_id=leases[0][0], action='renew')[1]['allowed'])
        self.assertTrue(self.lease(value['id'], '203.0.113.4')[1]['allowed'])

    def test_node_cannot_release_foreign_lease(self):
        value = self.create()
        lease, _ = self.lease(value['id'], '203.0.113.1')
        with self.assertRaises(ValueError):
            self.lease(value['id'], '203.0.113.1', 'rs', lease, 'release')

    def test_revoked_subscription_cannot_hold_or_acquire_slots(self):
        value = self.create()
        lease, _ = self.lease(value['id'], '203.0.113.1')
        self.control.mutate(value['id'], {'action': 'revoke', 'actor_id': 5})
        self.assertFalse(self.lease(value['id'], '203.0.113.1', lease_id=lease, action='renew')[1]['allowed'])
        self.assertFalse(self.lease(value['id'], '203.0.113.2')[1]['allowed'])

    def test_active_subscription_requires_renewal_not_new_issuance(self):
        value = self.create()
        for kind in ('gift', 'purchase', 'trial'):
            with self.assertRaisesRegex(ValueError, 'active_subscription_exists'):
                self.control.create({'contact_id': value['contact_id'], 'contact_name': 'Test', 'days': 3, 'kind': kind, 'actor_id': 5})

    def test_trial_cannot_be_reissued_after_deletion_or_to_telegram_alias(self):
        body = {'contact_id': 99, 'telegram_user_id': 999, 'contact_name': 'Test', 'days': 1, 'kind': 'trial', 'actor_id': 5}
        trial = self.control.create(body)
        self.control.mutate(trial['id'], {'action': 'delete', 'actor_id': 5})
        for contact in (99, 100):
            with self.assertRaisesRegex(ValueError, 'trial_already_used'):
                self.control.create({**body, 'contact_id': contact})

    def test_ipv4_mapped_ipv6_counts_as_same_ip(self):
        value = self.create()
        self.lease(value['id'], '203.0.113.1')
        self.lease(value['id'], '::ffff:203.0.113.1', 'fi')
        with self.control.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(DISTINCT ip) FROM connection_leases').fetchone()[0], 1)
