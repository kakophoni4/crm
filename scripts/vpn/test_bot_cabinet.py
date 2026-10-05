"""Telegram menu lifecycle tests with a local transport, never real recipients."""
import concurrent.futures
import copy
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from scripts.vpn import bot_cabinet, bot_ui


def telegram_error(description, code=400):
    return urllib.error.HTTPError('https://example.invalid', code, 'test error', {}, io.BytesIO(json.dumps({'description': description}).encode()))


class Telegram:
    def __init__(self):
        self.calls = []; self.messages = {}; self.next_id = 100; self.fail = None

    def __call__(self, method, body, token=None):
        self.calls.append((method, copy.deepcopy(body)))
        if self.fail and self.fail[0] == method:
            _, error = self.fail; self.fail = None; raise error
        if method == 'sendMessage':
            self.next_id += 1
            self.messages[self.next_id] = copy.deepcopy(body)
            return {'message_id': self.next_id}
        if method == 'editMessageText':
            old = self.messages.get(body['message_id'])
            if old is None:
                raise telegram_error('Bad Request: message to edit not found')
            if old['text'] == body['text'] and old['reply_markup'] == body['reply_markup']:
                raise telegram_error('Bad Request: message is not modified')
            self.messages[body['message_id']] = copy.deepcopy(body)
            return {'message_id': body['message_id']}
        if method == 'deleteMessage':
            self.messages.pop(body['message_id'], None)
        return True


class CabinetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        os.environ['VPN_NODES_FILE'] = str(Path(__file__).with_name('nodes.example.json'))
        spec = importlib.util.spec_from_file_location('cabinet_control_test', Path(__file__).with_name('control_service.py'))
        self.control = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.control)
        self.control.HOME = Path(self.temporary.name); self.control.BOT_ID = 123
        self.control.initialize()
        self.snapshot = patch.object(self.control, 'snapshot', return_value={'nodes': []}); self.snapshot.start()
        self.telegram = Telegram()
        self.transport = patch.object(self.control, 'telegram', side_effect=self.telegram); self.transport.start()

    def tearDown(self):
        self.transport.stop(); self.snapshot.stop(); self.temporary.cleanup()

    def subscription(self, user=555, days=30):
        value = self.control.create({'contact_id': 12, 'contact_name': 'Test contact', 'days': days, 'kind': 'trial', 'actor_id': 5, 'telegram_user_id': user})
        with self.control.database() as db:
            db.execute("UPDATE deliveries SET status='synced',version=1 WHERE subscription_id=?", (value['id'],))
        return value

    def command(self, text='/start', user=555):
        bot_cabinet.handle(self.control, {'message': {'message_id': 1, 'chat': {'type': 'private', 'id': user}, 'from': {'id': user}, 'text': text}}, 'test-placeholder')

    def callback(self, action, user=555, message_id=None):
        if message_id is None:
            with self.control.database() as db:
                row = db.execute('SELECT message_id FROM bot_screens WHERE bot_id=? AND user_id=?', (self.control.BOT_ID, user)).fetchone()
                message_id = row['message_id'] if row else 50
        bot_cabinet.handle(self.control, {'callback_query': {'id': 'test-callback', 'from': {'id': user}, 'data': action,
            'message': {'message_id': message_id, 'chat': {'type': 'private', 'id': user}, 'from': {'id': self.control.BOT_ID}}}}, 'test-placeholder')

    def screen(self, user=555):
        with self.control.database() as db:
            return dict(db.execute('SELECT * FROM bot_screens WHERE bot_id=? AND user_id=?', (self.control.BOT_ID, user)).fetchone())

    def requests(self):
        with self.control.database() as db:
            return [dict(row) for row in db.execute('SELECT * FROM bot_requests')]

    def test_one_message_survives_navigation_repeated_start_and_unchanged_refresh(self):
        self.subscription(); self.command(); initial = self.screen()
        self.callback('support'); self.callback('home'); self.callback('home'); self.command()
        self.assertEqual(initial['message_id'], self.screen()['message_id'])
        self.assertEqual(sum(method == 'sendMessage' for method, _ in self.telegram.calls), 1)
        self.assertEqual(len(self.telegram.messages), 1)

    def test_deleted_menu_is_replaced_once(self):
        self.command(); first = self.screen()['message_id']
        self.telegram.messages.pop(first)
        self.callback('home', message_id=first)
        second = self.screen()['message_id']; self.callback('home')
        self.assertNotEqual(first, second)
        self.assertEqual(sum(method == 'sendMessage' for method, _ in self.telegram.calls), 2)

    def test_old_menu_button_updates_canonical_screen_and_removes_old_bot_card(self):
        self.command(); canonical = self.screen()['message_id']
        self.telegram.messages[50] = {'text': 'Old menu', 'reply_markup': {}}
        self.callback('support', message_id=50)
        self.assertEqual(self.screen()['message_id'], canonical)
        self.assertNotIn(50, self.telegram.messages)
        self.assertEqual(len(self.telegram.messages), 1)

    def test_expired_callback_ack_does_not_lose_renewal(self):
        value = self.subscription(); self.command()
        self.telegram.fail = ('answerCallbackQuery', telegram_error('query is too old'))
        self.callback('ask_renew:' + value['id'] + ':14')
        self.assertEqual(self.requests()[0]['requested_days'], 14)
        self.assertEqual(self.requests()[0]['subscription_id'], value['id'])

    def test_repeat_renewal_creates_one_request_and_shows_pending_state(self):
        value = self.subscription(); self.command()
        for _ in range(3): self.callback('ask_renew:' + value['id'] + ':21')
        self.assertEqual(len(self.requests()), 1)
        self.callback('renew:' + value['id'])
        body = self.telegram.messages[self.screen()['message_id']]
        self.assertIn('на 21 дн.', body['text'])
        self.assertNotIn('ask_renew:', json.dumps(body))

    def test_simultaneous_request_retries_are_atomic(self):
        value = self.subscription()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: bot_cabinet.request(self.control, 555, 'renew', value['id'], 7), range(8)))
        self.assertEqual(len(self.requests()), 1)

    def test_foreign_subscription_and_invalid_duration_never_create_requests_or_leak_links(self):
        foreign = self.subscription(user=666); self.command()
        self.callback('ask_renew:' + foreign['id'] + ':7')
        self.assertFalse(self.requests())
        self.assertNotIn(foreign['subscription_url'], json.dumps(self.telegram.messages))
        own = self.subscription(); self.callback('ask_renew:' + own['id'] + ':999')
        self.assertFalse(self.requests())

    def test_copy_button_contains_only_current_users_selected_subscription(self):
        first = self.subscription(); second = self.subscription(); foreign = self.subscription(user=666)
        self.command(); self.callback('select:' + second['id']); self.callback('connect')
        body = self.telegram.messages[self.screen()['message_id']]
        encoded = json.dumps(body)
        self.assertIn(second['happ_url'], encoded)
        self.assertNotIn(first['subscription_url'], encoded)
        self.assertNotIn(foreign['subscription_url'], encoded)
        self.assertEqual(self.screen()['subscription_id'], second['id'])
        self.assertNotIn('client:', encoded)  # Other apps live behind one button.

    def test_expired_selected_subscription_cannot_show_connection_links(self):
        value = self.subscription(); self.command()
        with self.control.database() as db:
            db.execute('UPDATE subscriptions SET expires_at=? WHERE id=?', (time.time() - 1, value['id']))
        self.callback('connect')
        body = self.telegram.messages[self.screen()['message_id']]
        self.assertNotIn(value['subscription_url'], json.dumps(body))
        self.assertIn('Срок закончился', body['text'])

    def test_bot_change_keeps_screens_isolated_and_restart_reuses_screen(self):
        self.command(); first = self.screen()['message_id']; self.command('/menu')
        self.assertEqual(first, self.screen()['message_id'])
        self.control.BOT_ID = 456; self.command()
        self.assertNotEqual(first, self.screen()['message_id'])

    def test_rate_limit_does_not_create_another_menu(self):
        self.command(); initial = self.screen()['message_id']
        self.telegram.fail = ('editMessageText', telegram_error('Too Many Requests', 429))
        with self.assertRaises(urllib.error.HTTPError): self.callback('support')
        self.assertEqual(initial, self.screen()['message_id'])
        self.assertEqual(sum(method == 'sendMessage' for method, _ in self.telegram.calls), 1)

    def test_token_change_during_callback_keeps_old_message_in_old_bot_state(self):
        self.command()
        initial = self.screen()['message_id']
        def rotate_during_ack(method, body, token=None):
            result = self.telegram(method, body, token)
            if method == 'answerCallbackQuery': self.control.BOT_ID = 456
            return result
        with patch.object(self.control, 'telegram', side_effect=rotate_during_ack):
            self.callback('support')
        with self.control.database() as db:
            screens = [dict(row) for row in db.execute('SELECT * FROM bot_screens')]
        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0]['bot_id'], 123)
        self.assertEqual(screens[0]['message_id'], initial)

    def test_purchase_without_subscription_keeps_contact_unbound_and_shows_selected_period(self):
        self.command(); self.callback('ask_buy:7')
        row = self.requests()[0]
        self.assertEqual(row['requested_days'], 7)
        self.assertEqual(row['kind'], 'buy')
        self.assertIsNone(row['contact_id'])
        self.callback('buy')
        self.assertIn('Заявка принята', self.telegram.messages[self.screen()['message_id']]['text'])

    def test_pagination_and_telegram_payload_limits(self):
        views = []
        for _ in range(12):
            value = self.subscription()
            with self.control.database() as db:
                views.append(self.control.subscription_view(db.execute('SELECT * FROM subscriptions WHERE id=?', (value['id'],)).fetchone(), db))
        for page in (0, 1, 2, 999, -1):
            text, markup = bot_ui.subscriptions(views, page)
            self.assertLess(len(text), 4096)
            for row in markup['inline_keyboard']:
                for button in row: self.assertLessEqual(len(button['callback_data'].encode()), 64)
        self.command(); self.callback('connect')
        for row in self.telegram.messages[self.screen()['message_id']]['reply_markup']['inline_keyboard']:
            for button in row:
                if 'copy_text' in button: self.assertLessEqual(len(button['copy_text']['text']), 256)


if __name__ == '__main__':
    unittest.main()
