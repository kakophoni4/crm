"""Private Telegram cabinet with one persistent screen per user and bot."""
import json
import threading
import time
import urllib.error

try:
    from scripts.vpn import bot_ui
except ImportError:
    import bot_ui


def request(control, user_id, kind, identity=None, days=None):
    if kind not in ('renew', 'buy', 'support') or (days is not None and days not in bot_ui.PERIODS):
        raise ValueError('invalid_bot_request')
    with control.database() as db:
        db.execute('BEGIN IMMEDIATE')
        subscription = db.execute('SELECT id,contact_id FROM subscriptions WHERE id=? AND telegram_user_id=? AND deleted_at IS NULL', (identity, user_id)).fetchone() if identity else db.execute('SELECT id,contact_id FROM subscriptions WHERE telegram_user_id=? AND deleted_at IS NULL ORDER BY expires_at DESC LIMIT 1', (user_id,)).fetchone()
        if (identity or kind == 'renew') and not subscription:
            return 'Подписка недоступна. Вернитесь в «Мой VPN».'
        contact_id = subscription['contact_id'] if subscription else None
        subscription_id = subscription['id'] if subscription and kind != 'buy' else None
        existing = db.execute("SELECT * FROM bot_requests WHERE user_id=? AND kind=? AND state='open' AND subscription_id IS ?", (user_id, kind, subscription_id)).fetchone()
        if existing:
            return 'Заявка уже ожидает менеджера. Повторно отправлять её не нужно.'
        db.execute('INSERT INTO bot_requests(contact_id,subscription_id,user_id,kind,created_at,requested_days) VALUES(?,?,?,?,?,?)', (contact_id, subscription_id, user_id, kind, time.time(), days))
        return 'Заявка сохранена. Менеджер поможет с ' + ('продлением' if kind == 'renew' else 'подключением' if kind == 'buy' else 'VPN') + '.'


def error_description(exc):
    try:
        return str(json.loads(exc.read(4096)).get('description', '')).lower()
    except (ValueError, OSError, AttributeError):
        return ''


def publish(control, user_id, text, markup, token, state, selected, callback_message=None, bot_id=None):
    """Edit the canonical menu; create a replacement only if it was deleted."""
    callback_message = callback_message or {}
    bot_id = control.BOT_ID if bot_id is None else bot_id
    old_id = callback_message.get('message_id') if callback_message.get('from', {}).get('id', bot_id) == bot_id else None
    message_id = state['message_id'] if state else old_id
    body = {'chat_id': user_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True, 'reply_markup': markup}
    if message_id:
        try:
            control.telegram('editMessageText', {**body, 'message_id': message_id}, token)
        except urllib.error.HTTPError as exc:
            description = error_description(exc)
            if exc.code == 400 and 'message is not modified' in description:
                pass
            elif exc.code == 400 and any(reason in description for reason in ('message to edit not found', "message can't be edited", 'message_id_invalid')):
                message_id = None
            else:
                raise
    if not message_id:
        result = control.telegram('sendMessage', body, token)
        message_id = result.get('message_id')
        if not isinstance(message_id, int) or message_id <= 0:
            raise RuntimeError('telegram_message_missing')
    with control.database() as db:
        db.execute('INSERT INTO bot_screens(bot_id,user_id,message_id,subscription_id,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(bot_id,user_id) DO UPDATE SET message_id=excluded.message_id,subscription_id=excluded.subscription_id,updated_at=excluded.updated_at', (bot_id, user_id, message_id, selected['id'] if selected else None, time.time()))
    if old_id and old_id != message_id:
        try:
            control.telegram('deleteMessage', {'chat_id': user_id, 'message_id': old_id}, token)
        except Exception:
            # Old Telegram messages may no longer be deletable. Never retry a completed action for cleanup.
            pass


def handle(control, update, token):
    callback = update.get('callback_query')
    message = callback.get('message', {}) if callback else update.get('message', {})
    sender = callback.get('from', {}) if callback else message.get('from', {})
    user_id = sender.get('id')
    if message.get('chat', {}).get('type') != 'private' or sender.get('is_bot') or not user_id or message['chat'].get('id') != user_id:
        return
    bot_id = control.BOT_ID
    if callback:
        try:
            control.telegram('answerCallbackQuery', {'callback_query_id': callback['id']}, token)
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                raise
            # Expired callback acknowledgements must not prevent a valid menu action.
    action = callback.get('data', 'home') if callback else message.get('text', '').split(' ', 1)[0].split('@', 1)[0]
    action = {'/start': 'home', '/menu': 'home', '/status': 'home', '/subscription': 'subscriptions', '/help': 'support', '/buy': 'buy', '/support': 'support', 'status': 'home', 'instructions': 'connect', 'countries': 'support', 'Статус': 'home', 'Моя': 'subscriptions'}.get(action, action)
    with control.database() as db:
        db.execute('INSERT INTO bot_users VALUES(?,?,?,?) ON CONFLICT(bot_id,user_id) DO UPDATE SET last_seen=excluded.last_seen', (bot_id, user_id, time.time(), time.time()))
        views = [control.subscription_view(row, db) for row in db.execute('SELECT * FROM subscriptions WHERE telegram_user_id=? AND deleted_at IS NULL ORDER BY expires_at DESC', (user_id,))]
        state_row = db.execute('SELECT * FROM bot_screens WHERE bot_id=? AND user_id=?', (bot_id, user_id)).fetchone()
        state = dict(state_row) if state_row else None
        requests = [dict(row) for row in db.execute("SELECT * FROM bot_requests WHERE user_id=? AND state='open' ORDER BY created_at DESC", (user_id,))]
    selected = bot_ui.choose(views, state['subscription_id'] if state else None)
    notice = ''
    if action.startswith(('select:', 'renew:', 'confirm_renew:', 'ask_renew:')):
        identity = action.split(':')[1]
        selected_target = next((value for value in views if value['id'] == identity), None)
        if not selected_target:
            action, notice = 'home', 'Подписка недоступна. Обновите кабинет.'
        else:
            selected = selected_target
    if action.startswith(('ask_renew:', 'ask_buy:')) or action in ('confirm_buy', 'confirm_support', 'ask_support') or action.startswith('confirm_renew:'):
        kind = 'renew' if action.startswith(('ask_renew:', 'confirm_renew:')) else 'buy' if action.startswith('ask_buy:') or action == 'confirm_buy' else 'support'
        days = None
        if action.startswith(('ask_renew:', 'ask_buy:')):
            try:
                days = int(action.rsplit(':', 1)[1])
                if days not in bot_ui.PERIODS:
                    raise ValueError('invalid_days')
            except ValueError:
                action, notice = 'home', 'Выберите срок кнопками в меню.'
        if action != 'home':
            notice = request(control, user_id, kind, selected['id'] if selected else None, days)
            with control.database() as db:
                requests = [dict(row) for row in db.execute("SELECT * FROM bot_requests WHERE user_id=? AND state='open' ORDER BY created_at DESC", (user_id,))]
            if 'недоступна' not in notice:
                notice = ''  # Pending status on the home screen is the acknowledgement.
            action = 'home'
    if action.startswith('renew:'):
        text, markup = bot_ui.periods('renew', selected, requests)
    elif action == 'buy':
        text, markup = bot_ui.periods('buy', selected, requests)
    elif action.startswith('list:') or action == 'subscriptions' and len(views) > 1:
        try: page = int(action.split(':', 1)[1]) if ':' in action else 0
        except ValueError: page = 0
        text, markup = bot_ui.subscriptions(views, page)
    elif action == 'support':
        text, markup = bot_ui.help_screen(requests)
    elif action == 'apps' and selected and selected['status'] == 'active':
        text, markup = bot_ui.apps()
    elif action == 'connect' or action.startswith('client:'):
        key = action.split(':', 1)[1] if ':' in action else 'happ'
        if selected and selected['status'] == 'active' and key in bot_ui.client_guides.CLIENTS:
            text, markup = bot_ui.connect(selected, control.PUBLIC, key)
        else:
            text, markup = bot_ui.home(selected, views, requests, user_id, time.time(), 'Для подключения нужна активная подписка.')
    else:
        text, markup = bot_ui.home(selected, views, requests, user_id, time.time(), notice)
    publish(control, user_id, text, markup, token, state, selected, message if callback else None, bot_id=bot_id)


def deliver_notifications(control):
    while True:
        try:
            with control.database() as db:
                rows = db.execute("SELECT * FROM bot_notifications WHERE status='pending' AND next_try<=? ORDER BY id LIMIT 20", (time.time(),)).fetchall()
            for row in rows:
                status, error, delay = 'sent', None, 0
                try:
                    control.telegram('sendMessage', {'chat_id': row['user_id'], 'text': row['text'], 'disable_web_page_preview': True}, row['token'])
                except urllib.error.HTTPError as exc:
                    status, error, delay = 'pending', 'telegram_' + str(exc.code), 60
                    if exc.code in (400, 401, 403) or row['attempts'] >= 4:
                        status = 'failed'
                    if exc.code == 429:
                        try: delay = min(3600, max(30, int(json.load(exc).get('parameters', {}).get('retry_after', 60))))
                        except Exception: pass
                except Exception:
                    status, error, delay = ('failed' if row['attempts'] >= 4 else 'pending'), 'network_error', 60
                with control.database() as db:
                    db.execute('UPDATE bot_notifications SET status=?,attempts=attempts+1,next_try=?,error=?,token=? WHERE id=?', (status, time.time() + delay, error, row['token'] if status == 'pending' else '', row['id']))
                time.sleep(0.08)
        except Exception:
            control.log.warning('Notification queue retry')
        time.sleep(5)


def run(control):
    threading.Thread(target=deliver_notifications, args=(control,), daemon=True).start()
    initialized = None
    while True:
        token = control.BOT_TOKEN
        if not token:
            time.sleep(5); continue
        try:
            if initialized != token:
                bot = control.telegram('getMe', {}, token)
                if control.telegram('getWebhookInfo', {}, token).get('url'):
                    control.log.warning('Cabinet webhook exists; polling paused')
                    time.sleep(30); continue
                with control.BOT_LOCK:
                    if token != control.BOT_TOKEN: continue
                    control.BOT_USERNAME, control.BOT_ID = bot['username'], bot['id']
                control.telegram('setMyCommands', {'commands': [{'command': 'start', 'description': 'Открыть мой VPN'}]}, token)
                control.telegram('setChatMenuButton', {'menu_button': {'type': 'commands'}}, token)
                initialized = token
            offset_key = 'telegram_offset:' + str(control.BOT_ID)
            with control.database() as db:
                offset = db.execute('SELECT value FROM settings WHERE key=?', (offset_key,)).fetchone()
                if not offset:
                    offset = db.execute("SELECT value FROM settings WHERE key='telegram_offset'").fetchone()
                    if offset:
                        db.execute('INSERT INTO settings VALUES(?,?)', (offset_key, offset[0]))
                        db.execute("DELETE FROM settings WHERE key='telegram_offset'")
            updates = control.telegram('getUpdates', {'offset': int(offset[0]) if offset else 0, 'timeout': 25, 'allowed_updates': ['message', 'callback_query']}, token)
            for update in updates:
                if token != control.BOT_TOKEN: break
                try:
                    handle(control, update, token)
                except urllib.error.HTTPError as exc:
                    if exc.code not in (400, 403):
                        raise
                    # A deleted message or blocked recipient must not stop other clients.
                    control.log.warning('Telegram update cannot be delivered; skipping')
                with control.BOT_LOCK:
                    if token != control.BOT_TOKEN: break
                    with control.database() as db:
                        db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (offset_key, str(update['update_id'] + 1)))
        except Exception:
            control.log.warning('Telegram cabinet retry')
            time.sleep(10)
