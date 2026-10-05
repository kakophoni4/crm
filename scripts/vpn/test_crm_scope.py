"""VPN API contact scope and role regression checks without external services."""
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.db.models.enums import UserRole
from app.modules.vpn.router import router
from app.shared.db import get_db
from app.shared.exceptions import NotFound, register_exception_handlers
from app.shared.security.deps import current_user


class ScopeTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI(); app.include_router(router); register_exception_handlers(app)
        self.actor = SimpleNamespace(id=7, role=UserRole.USER)
        self.db = AsyncMock()
        app.dependency_overrides[current_user] = lambda: self.actor
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.scope_patch = patch('app.modules.vpn.router.ContactService.get_contact', new_callable=AsyncMock)
        self.scope = self.scope_patch.start()
        self.control_patch = patch('app.modules.vpn.router.control', new_callable=AsyncMock)
        self.control = self.control_patch.start()
        self.identity = '83f12507-1856-4008-8715-1c42c9101128'

    def tearDown(self):
        self.client.close(); self.scope_patch.stop(); self.control_patch.stop()

    def test_manager_cannot_list_all_subscriptions(self):
        response = self.client.get('/api/v1/vpn/subscriptions')
        self.assertEqual(response.status_code, 403); self.control.assert_not_awaited()

    def test_foreign_contact_cannot_receive_gift(self):
        self.scope.side_effect = NotFound()
        response = self.client.post('/api/v1/vpn/subscriptions', json={'contact_id': 12, 'days': 30, 'kind': 'gift'})
        self.assertEqual(response.status_code, 404); self.control.assert_not_awaited()

    def test_trial_is_bound_to_authorized_chat_contact_and_actor(self):
        self.scope.return_value = {'linked_bots': [{'bot_id': 5, 'bot_name': 'Linked bot'}]}
        self.db.get.return_value = SimpleNamespace(full_name='Visible contact', telegram_user_id=123, telegram_username='visible')
        self.control.return_value = {'id': self.identity, 'kind': 'trial', 'telegram_user_id': 123}
        request_key = str(uuid.uuid4())
        with patch('app.modules.vpn.router.ChatService.get_chat', new_callable=AsyncMock) as chat:
            chat.return_value = {'contact_id': 12, 'bot_id': 5}
            response = self.client.post('/api/v1/vpn/subscriptions', json={
                'contact_id': 12, 'kind': 'trial', 'days': 3, 'source_chat_id': 42,
                'source_bot_id': 5, 'idempotency_key': request_key})
        self.assertEqual(response.status_code, 201)
        body = self.control.await_args.args[2]
        self.assertEqual(body['actor_id'], 7)
        self.assertEqual(body['telegram_user_id'], 123)
        self.assertEqual(body['source_chat_id'], 42)
        self.assertEqual(body['days'], 3)
        self.assertEqual(body['idempotency_key'], request_key)
        self.assertNotIn('telegram_user_id', response.json())

    def test_foreign_contact_cannot_receive_trial(self):
        self.scope.side_effect = NotFound()
        response = self.client.post('/api/v1/vpn/subscriptions', json={'contact_id': 99, 'days': 1, 'kind': 'trial'})
        self.assertEqual(response.status_code, 404); self.control.assert_not_awaited()

    def test_foreign_contact_subscription_cannot_be_revoked(self):
        self.control.return_value = {'contact_id': 12}
        self.scope.side_effect = NotFound()
        response = self.client.post('/api/v1/vpn/subscriptions/' + self.identity + '/action', json={'action': 'revoke'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.control.await_count, 1)
        self.assertEqual(self.control.await_args.args[0], 'GET')

    def test_manager_cannot_change_node_configuration(self):
        response = self.client.post('/api/v1/vpn/nodes/pl', json={'drained': True, 'capacity_mbps': 100})
        self.assertEqual(response.status_code, 403); self.control.assert_not_awaited()

    def test_manager_cannot_replace_bot(self):
        response = self.client.post('/api/v1/vpn/bot/prepare', json={'token': 'x' * 40})
        self.assertEqual(response.status_code, 403); self.control.assert_not_awaited()

    def test_manager_request_queue_hides_foreign_and_unlinked_contacts(self):
        self.control.return_value = {'items': [
            {'id': 1, 'contact_id': 12, 'user_id': 123},
            {'id': 2, 'contact_id': 99, 'user_id': 456},
            {'id': 3, 'contact_id': None, 'user_id': 789},
        ]}
        result = MagicMock()
        result.all.return_value = [SimpleNamespace(id=12, full_name='Visible contact', telegram_username='visible')]
        self.db.execute.return_value = result
        with patch('app.modules.vpn.router.ScopeLoader.load', new_callable=AsyncMock):
            with patch('app.modules.vpn.router.contact_visibility_clause', return_value=None):
                response = self.client.get('/api/v1/vpn/bot/requests?state=open')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()['items']], [1])
        self.assertEqual(response.json()['items'][0]['contact_name'], 'Visible contact')
        self.assertNotIn('user_id', response.json()['items'][0])

    def test_foreign_request_cannot_be_renewed(self):
        self.control.return_value = {'contact_id': 99}
        self.scope.side_effect = NotFound()
        response = self.client.post('/api/v1/vpn/bot/requests/1/renew', json={'days': 30})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.control.await_count, 1)

    def test_empty_manager_queue_count_is_zero(self):
        self.control.return_value = {'items': []}
        response = self.client.get('/api/v1/vpn/bot/requests/count')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'open': 0})

    def test_manager_cannot_close_unlinked_bot_request(self):
        self.control.return_value = {'contact_id': None}
        response = self.client.post('/api/v1/vpn/bot/requests/1', json={'state': 'done'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.control.await_count, 1)

    def test_foreign_chat_cannot_be_purchase_source(self):
        self.scope.return_value = {'linked_bots': []}
        with patch('app.modules.vpn.router.ChatService.get_chat', new_callable=AsyncMock) as chat:
            chat.return_value = {'contact_id': 99, 'bot_id': None}
            response = self.client.post('/api/v1/vpn/subscriptions', json={'contact_id': 12, 'source_chat_id': 3})
        self.assertEqual(response.status_code, 422); self.control.assert_not_awaited()

    def test_source_bot_must_belong_to_contact(self):
        self.scope.return_value = {'linked_bots': [{'bot_id': 5, 'bot_name': 'Linked bot'}]}
        response = self.client.post('/api/v1/vpn/subscriptions', json={'contact_id': 12, 'source_bot_id': 6})
        self.assertEqual(response.status_code, 422); self.control.assert_not_awaited()

    def test_manager_read_hides_restricted_telegram_id(self):
        self.scope.return_value = {}
        self.control.return_value = {'items': [{'contact_id': 12, 'telegram_user_id': 123456}]}
        response = self.client.get('/api/v1/vpn/subscriptions?contact_id=12')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('telegram_user_id', response.json()['items'][0])


if __name__ == '__main__':
    unittest.main()
