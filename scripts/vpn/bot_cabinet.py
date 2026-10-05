"""Private Telegram cabinet and durable migration notifications. No tokens in logs."""
import json
import threading
import time
import urllib.error

try:
    from scripts.vpn import client_guides
except ImportError:
    import client_guides


def keyboard():
    return {'inline_keyboard': [
        [{'text': '🔐 Мои подписки', 'callback_data': 'subscriptions'}, {'text': '📊 Статус и трафик', 'callback_data': 'status'}],
        [{'text': '📲 Скачать приложения', 'callback_data': 'apps'}, {'text': '📱 Как подключиться', 'callback_data': 'instructions'}],
        [{'text': '🌍 Страны и AUTO', 'callback_data': 'countries'}],
        [{'text': '🛒 Купить VPN', 'callback_data': 'buy'}, {'text': '💬 Помощь', 'callback_data': 'support'}],
        [{'text': '🪪 Мой Telegram ID', 'callback_data': 'identity'}]]}


def request(control, user_id, kind, identity=None):
    with control.database() as db:
        subscription = db.execute('SELECT id,contact_id FROM subscriptions WHERE id=? AND telegram_user_id=? AND deleted_at IS NULL', (identity, user_id)).fetchone() if identity else db.execute('SELECT id,contact_id FROM subscriptions WHERE telegram_user_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1', (user_id,)).fetchone()
        if identity and not subscription:
            return 'Эта подписка недоступна. Откройте «Мои подписки».'
        contact_id = subscription['contact_id'] if subscription else None
        subscription_id = subscription['id'] if subscription and kind == 'renew' else None
        existing = db.execute("SELECT id FROM bot_requests WHERE user_id=? AND kind=? AND state='open' AND subscription_id IS ?", (user_id, kind, subscription_id)).fetchone()
        if existing:
            return f'Заявка №{existing[0]} уже ожидает ответа менеджера. Повторно создавать её не нужно.'
        cursor = db.execute('INSERT INTO bot_requests(contact_id,subscription_id,user_id,kind,created_at) VALUES(?,?,?,?,?)', (contact_id, subscription_id, user_id, kind, time.time()))
        return f'Заявка №{cursor.lastrowid} сохранена в CRM. Менеджер увидит её и поможет с {"продлением" if kind == "renew" else "покупкой" if kind == "buy" else "подключением"}. Деньги не списаны.'


def handle(control, update, token):
    callback = update.get('callback_query')
    message = callback.get('message', {}) if callback else update.get('message', {})
    sender = callback.get('from', {}) if callback else message.get('from', {})
    if message.get('chat', {}).get('type') != 'private' or sender.get('is_bot') or not sender.get('id'):
        return
    user_id = sender['id']
    if callback:
        control.telegram('answerCallbackQuery', {'callback_query_id': callback['id']}, token)
    action = callback.get('data', 'home') if callback else message.get('text', '').split(' ', 1)[0].split('@', 1)[0]
    action = {'/start': 'home', '/menu': 'home', '/status': 'status', '/subscription': 'subscriptions', '/help': 'instructions', '/buy': 'buy', '/support': 'support', 'Статус': 'status', 'Моя': 'subscriptions'}.get(action, action)
    with control.database() as db:
        db.execute('INSERT INTO bot_users VALUES(?,?,?,?) ON CONFLICT(bot_id,user_id) DO UPDATE SET last_seen=excluded.last_seen', (control.BOT_ID, user_id, time.time(), time.time()))
        rows = db.execute('SELECT * FROM subscriptions WHERE telegram_user_id=? AND deleted_at IS NULL ORDER BY expires_at DESC', (user_id,)).fetchall()
        views = [control.subscription_view(row, db) for row in rows]
    markup = keyboard()
    if action in ('subscriptions', 'status'):
        if not views:
            text = f'🔐 Подписок пока нет.\nЕсли VPN уже выдан, сообщите менеджеру Telegram ID: {user_id}. Он привяжет подписку к вашему контакту.\nДля новой подписки нажмите «Купить VPN».'
        else:
            control.telegram('sendMessage', {'chat_id': user_id, 'text': '🔐 Ваши VPN-подписки' if action == 'subscriptions' else '📊 Срок и использование VPN', 'reply_markup': markup}, token)
            for value in views[:20]:
                labels = {'active': '🟢 Активна', 'provisioning': '🟡 Настраивается', 'expired': '⌛ Истекла', 'revoked': '⛔ Отключена'}
                remaining = max(0, int((value['expires_at'] - time.time()) / 86400))
                text = f"{labels[value['status']]} · {'Подарок' if value['kind'] == 'gift' else 'Покупка'}\nДо {time.strftime('%d.%m.%Y %H:%M UTC', time.gmtime(value['expires_at']))} · осталось {remaining} дн.\nОтправлено: {value['upload_bytes'] / 1024**3:.2f} ГБ\nПолучено: {value['download_bytes'] / 1024**3:.2f} ГБ"
                if action == 'subscriptions' and value['status'] == 'active':
                    text += '\n\nHapp:\n' + value['happ_url'] + '\n\nKoala Clash / Clash Meta:\n' + value['clash_url'] + '\n\nv2rayNG:\n' + value['v2rayng_url'] + '\n\nСкачивание и инструкция с вашей ссылкой:\n' + value['guide_url'] + '\n\nНе передавайте ссылку подписки другим людям.'
                buttons = [[{'text': 'Продлить эту подписку', 'callback_data': 'renew:' + value['id']}], [{'text': 'Как подключиться', 'callback_data': 'instructions'}, {'text': 'Меню', 'callback_data': 'home'}]]
                control.telegram('sendMessage', {'chat_id': user_id, 'text': text, 'disable_web_page_preview': True, 'reply_markup': {'inline_keyboard': buttons}}, token)
            return
    elif action.startswith('renew:'):
        identity = action.split(':', 1)[1]
        if not any(value['id'] == identity for value in views):
            text = 'Подписка недоступна.'
        else:
            text = 'Отправить менеджеру заявку на продление этой подписки? Цена и срок согласуются с менеджером.'
            markup = {'inline_keyboard': [[{'text': 'Да, запросить продление', 'callback_data': 'confirm_renew:' + identity}], [{'text': 'Отмена', 'callback_data': 'home'}]]}
    elif action.startswith('confirm_renew:'):
        text = request(control, user_id, 'renew', action.split(':', 1)[1])
    elif action in ('buy', 'support'):
        text = 'Хотите оформить новую VPN-подписку?' if action == 'buy' else 'Не удаётся подключиться? Сначала обновите подписку в приложении, переключите страну и проверьте подключение через мобильную сеть. Если это не помогло, отправьте заявку менеджеру.'
        markup = {'inline_keyboard': [[{'text': 'Отправить заявку менеджеру', 'callback_data': 'confirm_' + action}], [{'text': 'Назад', 'callback_data': 'home'}]]}
    elif action in ('confirm_buy', 'confirm_support'):
        text = request(control, user_id, action.removeprefix('confirm_'))
    elif action == 'identity':
        text = f'🪪 Ваш Telegram ID: {user_id}\nСообщите его менеджеру для привязки VPN. ID берётся из Telegram и не вводится вручную в боте.'
    elif action in ('instructions', 'apps'):
        text = '📱 Выберите приложение\n\nНа Android рекомендуем Happ. Устанавливать всё сразу не нужно. Нажмите на приложение: появятся APK, подробные шаги и ваша ссылка.\n\n' + client_guides.KOALA_ANDROID
        markup = {'inline_keyboard': [[{'text': client['name'], 'callback_data': 'client:' + key}] for key, client in client_guides.CLIENTS.items()] + [[{'text': 'Все инструкции на сайте', 'url': control.PUBLIC + '/apps'}], [{'text': 'Меню', 'callback_data': 'home'}]]}
    elif action.startswith('client:'):
        key = action.removeprefix('client:')
        if key not in client_guides.CLIENTS:
            return
        client = next(item for item in client_guides.catalog(control.PUBLIC) if item['id'] == key)
        text = '📱 ' + client_guides.guide_text(key)
        if key == 'koala':
            text = client_guides.KOALA_ANDROID + '\n\n' + text
        else:
            text = client_guides.INSTALL + '\n\n' + text
        buttons = []
        if client.get('download_url'):
            buttons.append([{'text': '📥 Скачать APK · ' + client['name'], 'url': client['download_url']}])
            if key == 'v2rayng':
                buttons.append([{'text': 'APK для старого телефона', 'url': control.PUBLIC + '/downloads/v2rayng-arm7.apk'}])
        else:
            buttons.append([{'text': 'Официальные релизы', 'url': client['source']}])
        active = [value for value in views if value['status'] == 'active']
        for value in active[:5]:
            url = value['subscription_url'] + '?format=' + client['format']
            text += '\n\nВаша ссылка (до ' + time.strftime('%d.%m.%Y', time.gmtime(value['expires_at'])) + '):\n' + url
            buttons.append([{'text': 'Инструкция с моей ссылкой', 'url': value['guide_url'] + '#' + key}])
        if not active:
            text += '\n\nАктивной подписки пока нет. Откройте «Мои подписки» или запросите покупку/продление.'
        buttons += [[{'text': 'Другие приложения', 'callback_data': 'apps'}, {'text': 'Мои подписки', 'callback_data': 'subscriptions'}], [{'text': 'Помощь', 'callback_data': 'support'}, {'text': 'Меню', 'callback_data': 'home'}]]
        markup = {'inline_keyboard': buttons}
    elif action == 'countries':
        text = '🌍 Польша · Сербия · Эстония · Финляндия · Швейцария · Румыния · Казахстан\n\nВ Happ выберите «Автовыбор · RU напрямую», в Koala Clash и Clash Meta — AUTO. Приложение проверяет задержку с вашего устройства среди персонально распределённых серверов. Страну можно выбрать вручную. Скорость зависит также от вашей сети.'
    else:
        text = '🔐 VPN — личный кабинет\n\nЗдесь можно получить ссылки подключения, проверить срок и трафик, узнать как подключиться и запросить покупку или продление.\n\nВыберите действие ниже 👇'
    control.telegram('sendMessage', {'chat_id': user_id, 'text': text, 'disable_web_page_preview': True, 'reply_markup': markup}, token)


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
                control.telegram('setMyCommands', {'commands': [{'command': 'start', 'description': 'Личный кабинет VPN'}, {'command': 'subscription', 'description': 'Мои подписки и ссылки'}, {'command': 'status', 'description': 'Срок и трафик'}, {'command': 'help', 'description': 'Инструкция подключения'}, {'command': 'buy', 'description': 'Купить VPN'}, {'command': 'support', 'description': 'Помощь менеджера'}]}, token)
                initialized = token
            with control.database() as db:
                offset = db.execute("SELECT value FROM settings WHERE key='telegram_offset'").fetchone()
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
                        db.execute("INSERT INTO settings VALUES('telegram_offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(update['update_id'] + 1),))
        except Exception:
            control.log.warning('Telegram cabinet retry')
            time.sleep(10)
