"""Compact Telegram screens. Rendering does not send messages or change subscriptions."""
import html
import math
from datetime import datetime, timedelta, timezone

try:
    from scripts.vpn import client_guides
except ImportError:
    import client_guides

PERIODS = (7, 14, 21, 30)
KINDS = {'gift': 'Подарок', 'purchase': 'Подписка', 'trial': 'Пробный период'}
STATUS = {'active': '🟢 VPN активен', 'provisioning': '⏳ Подключение готовится', 'expired': '⌛ Срок закончился', 'revoked': '⛔ Доступ отключён'}
MSK = timezone(timedelta(hours=3))


def button(text, action=None, url=None, copy=None, primary=False):
    return dict(text=text, **({'callback_data': action} if action else {'url': url} if url else {'copy_text': {'text': copy}}), **({'style': 'primary'} if primary else {}))


def keyboard(*rows):
    return {'inline_keyboard': [row for row in rows if row]}


def expiry(value):
    return datetime.fromtimestamp(value['expires_at'], MSK).strftime('%d.%m.%Y, %H:%M') + ' МСК'


def choose(views, identity=None):
    selected = next((value for value in views if value['id'] == identity), None)
    if selected and selected['status'] not in ('active', 'provisioning') and any(value['status'] == 'active' for value in views):
        selected = None
    return selected or min(views, key=lambda value: (['active', 'provisioning', 'expired', 'revoked'].index(value['status']), -value['expires_at']), default=None)


def pending(requests, kind, identity=None):
    return next((item for item in requests if item['kind'] == kind and (identity is None or item['subscription_id'] == identity)), None)


def request_status(item):
    period = f" на {item['requested_days']} дн." if item.get('requested_days') else ''
    label = {'renew': 'Продление', 'buy': 'Подключение', 'support': 'Помощь'}[item['kind']]
    return f'⏳ {label}{period}: заявка ожидает менеджера.'


def home(value, views, requests, user_id, now, notice=''):
    rows = []
    if value:
        seconds = max(0, value['expires_at'] - now)
        remaining = f'осталось {math.ceil(seconds / 86400)} дн.' if seconds >= 86400 else f'осталось {math.ceil(seconds / 3600)} ч.' if seconds else ''
        text = f"<b>Ваш VPN</b>\n\n{STATUS[value['status']]} · {KINDS.get(value['kind'], 'Подписка')}\nДо {expiry(value)}"
        if remaining:
            text += '\n' + remaining
        if value['status'] in ('active', 'provisioning'):
            text += f"\nИспользовано: {(value['upload_bytes'] + value['download_bytes']) / 1024**3:.2f} ГБ"
        if value['status'] == 'active':
            rows.append([button('📲 Подключить VPN', 'connect', primary=True)])
        elif value['status'] == 'provisioning':
            text += '\n\nПодождите немного и нажмите «Обновить».'
        elif value['status'] == 'expired':
            text += '\n\nПродлите подписку, чтобы снова подключиться.'
        else:
            text += '\n\nОбратитесь к менеджеру для восстановления доступа.'
        request = pending(requests, 'renew', value['id'])
        rows.append([button('⏳ Заявка на продление' if request else 'Продлить VPN', 'renew:' + value['id']), button('Помощь', 'support')])
    else:
        text = f'<b>Ваш VPN</b>\n\nПодписки пока нет.\nПолучите VPN или обратитесь к менеджеру.\n\nЕсли доступ уже выдан, сообщите менеджеру ваш Telegram ID: <code>{user_id}</code>.'
        rows.append([button('Получить VPN', 'buy', primary=True), button('Помощь', 'support')])
    if len(views) > 1:
        rows.append([button('Другие подписки', 'list:0')])
    rows.append([button('↻ Обновить', 'home')])
    relevant = [item for item in requests if item['kind'] != 'renew' or value and item['subscription_id'] == value['id']]
    for item in relevant[:3]:
        text += '\n\n' + request_status(item)
    if notice:
        text += '\n\n' + html.escape(notice)
    return text, keyboard(*rows)


def periods(kind, value, requests):
    identity = value['id'] if value and kind == 'renew' else None
    request = pending(requests, kind, identity)
    if request:
        return '<b>Заявка принята</b>\n\n' + request_status(request) + '\nПовторно отправлять её не нужно.', keyboard([button('← Мой VPN', 'home')])
    title = 'Продлить VPN' if kind == 'renew' else 'Получить VPN'
    text = '<b>' + title + '</b>\n\nВыберите срок — отправим заявку менеджеру.\nСтоимость и оплату согласует менеджер.'
    action = 'ask_renew:' + identity + ':' if identity else 'ask_buy:'
    choices = [button(str(days) + ' дн.', action + str(days)) for days in PERIODS]
    return text, keyboard(choices[:2], choices[2:], [button('← Мой VPN', 'home')])


def subscriptions(views, page=0):
    page = min(max(0, page), max(0, (len(views) - 1) // 5))
    rows = []
    for index, value in enumerate(views[page * 5:page * 5 + 5], page * 5 + 1):
        icon = '🟢' if value['status'] == 'active' else '⏳' if value['status'] == 'provisioning' else '⌛' if value['status'] == 'expired' else '⛔'
        label = f"{icon} {KINDS.get(value['kind'], 'VPN')} {index} · до " + datetime.fromtimestamp(value['expires_at'], MSK).strftime('%d.%m.%Y')
        rows.append([button(label, 'select:' + value['id'])])
    navigation = []
    if page:
        navigation.append(button('←', 'list:' + str(page - 1)))
    if (page + 1) * 5 < len(views):
        navigation.append(button('→', 'list:' + str(page + 1)))
    return '<b>Ваши подписки</b>\n\nВыберите нужную.', keyboard(*rows, navigation, [button('← Мой VPN', 'home')])


def connect(value, public, key='happ'):
    client = next(item for item in client_guides.catalog(public) if item['id'] == key)
    url = value['subscription_url'] + '?format=' + client['format']
    steps = {
        'happ': '1. Установите Happ.\n2. Скопируйте ссылку ниже → в Happ нажмите «+» → «Добавить из буфера».\n3. Выберите «Автовыбор» или страну и включите VPN.',
        'clashmeta': '1. Установите Clash Meta.\n2. Скопируйте ссылку → «Профили» → «+» → «URL» → сохраните и выберите профиль.\n3. Включите VPN, в группе VPN выберите AUTO.',
        'v2rayng': '1. Установите v2rayNG.\n2. Скопируйте ссылку → «☰» → «Группы» → «+» → сохраните. Затем «⋮» → «Обновить подписку».\n3. Выберите сервер и нажмите кнопку подключения.',
        'koala': '1. Установите Koala Clash на компьютер.\n2. Добавьте профиль по скопированной ссылке.\n3. Включите TUN и выберите AUTO.',
    }
    text = '<b>Подключение · ' + html.escape(client['name']) + '</b>\n\n' + steps[key]
    text += '\n\nВ системном запросе разрешите VPN.\nНе передавайте свою ссылку другим людям.'
    download = client.get('download_url') or client['source']
    return text, keyboard([button('↓ Скачать ' + client['name'], url=download, primary=True)],
                         [button('Скопировать ссылку', copy=url)],
                         [button('Пошаговая инструкция', url=value['guide_url'] + '#' + key)],
                         [button('Другое приложение', 'apps'), button('← Мой VPN', 'home')])


def apps():
    return '<b>Выберите приложение</b>\n\nУстановите одно. Для Android рекомендуем Happ.', keyboard(
        [button('Happ · Android', 'client:happ')],
        [button('Clash Meta · Android', 'client:clashmeta'), button('v2rayNG · Android', 'client:v2rayng')],
        [button('Koala Clash · компьютер', 'client:koala')], [button('← Мой VPN', 'home')])


def help_screen(requests):
    text = '<b>Не получается подключиться?</b>\n\n1. Обновите подписку в приложении.\n2. Выберите «Автовыбор» / AUTO и переподключитесь.\n3. Попробуйте Wi-Fi вместо мобильной сети или наоборот.\n\n«н/д» при проверке пинга само по себе не означает, что VPN не работает.'
    request = pending(requests, 'support')
    if request:
        text += '\n\n' + request_status(request)
    return text, keyboard([] if request else [button('Помощь менеджера', 'ask_support')], [button('← Мой VPN', 'home')])
