"""Shared client names, downloads and connection guides for the website and bot."""
import html
import json
import os
from pathlib import Path

DOWNLOADS = Path(os.environ.get('VPN_DOWNLOADS_DIR', '/opt/crm-vpn/downloads'))
CLIENTS = {
    'ghostlane': {'name': 'Ghostlane', 'format': 'ghostlane', 'file': 'ghostlane.apk', 'source': 'https://github.com/ghostlane-project/ghostlane/releases',
                 'steps': ['Установите Ghostlane и откройте приложение.', 'Скопируйте ссылку подписки для Ghostlane.', 'Добавьте список серверов по ссылке: вставьте скопированную ссылку и сохраните.', 'Обновите список. Если канал ещё готовится, повторите обновление через минуту.', 'При ограничениях интернета откройте «Обход ограничений · olcRTC» и выберите «Подключиться · olcRTC». Для обычного VPN откройте «Обычный VPN · все страны» и выберите «Наименьшая задержка / АВТО».', 'Нажмите кнопку подключения и разрешите создание VPN. Повторное нажатие отключает VPN.']},
    'happ': {'name': 'Happ', 'format': 'happ', 'file': 'happ.apk', 'source': 'https://github.com/Happ-proxy/happ-android/releases',
             'steps': ['Установите Happ и откройте приложение.', 'В боте нажмите «Подключить VPN» → «Скопировать ссылку» или используйте кнопку ниже.', 'В Happ нажмите «+» → «Добавить из буфера обмена». Если приложение предлагает импорт ссылки, подтвердите его.', 'Выберите «Автовыбор» или страну с флагом — способ подключения подберётся автоматически.', 'Нажмите кнопку подключения. В системном запросе на создание VPN нажмите «ОК».', 'Откройте нужный сайт. Чтобы выключить VPN, снова нажмите кнопку подключения.']},
    'clashmeta': {'name': 'Clash Meta for Android', 'format': 'clash', 'file': 'clashmeta.apk', 'source': 'https://github.com/MetaCubeX/ClashMetaForAndroid/releases',
                  'steps': ['Установите Clash Meta for Android. Это отдельное Android-приложение, совместимое с форматом Koala Clash.', 'В боте нажмите «Подключить VPN» → «Другое приложение» → «Clash Meta» → «Скопировать ссылку» или используйте кнопку ниже.', 'Откройте «Профили» (Profiles) → «+» → «URL». Название: BTT VPN. Вставьте ссылку в поле URL и нажмите значок сохранения.', 'Дождитесь скачивания и выберите профиль BTT VPN.', 'Вернитесь на главный экран и нажмите «Остановлено» (Stopped). В запросе Android на создание VPN нажмите «ОК».', 'В разделе «Прокси» (Proxies) откройте группу VPN и выберите AUTO. Режим работы — «Правила» (Rule). Для отключения нажмите «Запущено» (Running).']},
    'v2rayng': {'name': 'v2rayNG', 'format': 'v2rayng', 'file': 'v2rayng.apk', 'source': 'https://github.com/2dust/v2rayNG/releases',
                 'steps': ['Установите v2rayNG и откройте приложение.', 'В боте нажмите «Подключить VPN» → «Другое приложение» → «v2rayNG» → «Скопировать ссылку» или используйте кнопку ниже.', 'Нажмите «☰» → «Группы» (Subscription group settings) → «+». Название: BTT VPN. Вставьте ссылку в поле URL и сохраните галочкой.', 'Вернитесь к списку серверов. Нажмите «⋮» → «Обновить подписку» (Update subscription). Дождитесь загрузки.', 'Нажмите на выбранный сервер, затем на круглую кнопку подключения внизу. В запросе Android нажмите «ОК».', 'Для смены сервера отключите VPN, выберите другой и подключитесь снова. В этом клиенте сервер выбирается вручную; для автоматического выбора используйте Happ.']},
    'koala': {'name': 'Koala Clash', 'format': 'clash', 'file': None, 'source': 'https://github.com/coolcoala/koala-clash/releases',
              'steps': ['На компьютере установите Koala Clash из официальных релизов для своей системы.', 'В боте нажмите «Подключить VPN» → «Другое приложение» → «Koala Clash» → «Скопировать ссылку» или используйте кнопку ниже.', 'Откройте раздел профилей/подписок, добавьте профиль по URL, вставьте ссылку и сохраните. Выберите скачанный профиль.', 'Включите режим TUN, чтобы VPN работал для приложений на компьютере. Подтвердите системный запрос, если он появился.', 'В группе VPN выберите AUTO. Режим — «Правила» (Rule). Для отключения выключите TUN.']},
}
INSTALL = 'Откройте скачанный APK → «Установить». Если Android попросит разрешение, нажмите «Настройки» → разрешите установку для этого браузера/Telegram → вернитесь к APK и нажмите «Установить». После установки это разрешение можно выключить. Устанавливать все приложения не нужно — выберите одно. Одновременно включайте только один VPN.'
HELP = 'Если не открываются сайты: выключите другой VPN, обновите подписку, переподключитесь и попробуйте Wi-Fi вместо мобильной сети или наоборот. В Happ сначала используйте «Автовыбор». «н/д» при проверке пинга само по себе не означает, что подключение не работает. Проверьте срок в боте; для продления или помощи нажмите «Помощь». При разрывах в фоне разрешите выбранному приложению работу без ограничений батареи в настройках Android.'
KOALA_ANDROID = 'Официальный APK Koala Clash для Android пока не опубликован в GitHub Releases автора. Для Android можно выбрать Happ, Clash Meta for Android или v2rayNG. Koala Clash для компьютера доступна по официальной ссылке.'
HAPP_IOS = {
    'id': 'happ-ios', 'name': 'Happ', 'format': 'happ',
    'source': 'https://apps.apple.com/us/app/happ-proxy-utility/id6504287215',
    'steps': ['Установите Happ из App Store.', 'Скопируйте ссылку своей подписки.',
              'Откройте Happ, нажмите «+» и выберите добавление из буфера обмена. Разрешите вставку, если iPhone спросит.',
              'Дождитесь загрузки подписки и выберите «Автовыбор» или нужную страну.',
              'Нажмите кнопку подключения. Разрешите добавление конфигурации VPN и подтвердите действие код-паролем или Face ID.',
              'Откройте нужный сайт. Для отключения снова нажмите кнопку подключения в Happ.'],
}
GHOSTLANE_IOS = dict(CLIENTS['ghostlane'], id='ghostlane-ios', file=None,
                    source='https://apps.apple.com/ru/app/ghostlane/id6795355210')
GHOSTLANE_DESKTOP = dict(CLIENTS['ghostlane'], id='ghostlane-desktop', file=None)


def catalog(public):
    try:
        manifest = json.loads((DOWNLOADS / 'manifest.json').read_text())
    except (OSError, ValueError):
        manifest = {}
    values = []
    for key, client in CLIENTS.items():
        value = dict(client, id=key)
        asset = manifest.get(key, {})
        if client['file'] and (DOWNLOADS / client['file']).is_file() and asset.get('sha256'):
            value.update(download_url=public + '/downloads/' + client['file'], version=asset.get('version'), sha256=asset['sha256'], size=asset.get('size'))
        values.append(value)
    return values


def guide_text(key):
    client = CLIENTS[key]
    return client['name'] + '\n\n' + '\n\n'.join(f'{index}. {step}' for index, step in enumerate(client['steps'], 1)) + '\n\n' + HELP


def page(public, subscription=None, bot_username=''):
    esc = html.escape
    bot_url = 'https://t.me/' + bot_username if bot_username else None
    descriptions = {'ghostlane': ('G', 'olcRTC и обычный VPN'), 'ghostlane-ios': ('G', 'olcRTC и обычный VPN'), 'ghostlane-desktop': ('G', 'olcRTC и обычный VPN'), 'happ': ('H', 'Рекомендуем · автовыбор'), 'happ-ios': ('H', 'iPhone · iPad · автовыбор'), 'clashmeta': ('C', 'Гибкие настройки'), 'v2rayng': ('V', 'Ручной выбор сервера'), 'koala': ('K', 'Windows · macOS · Linux')}
    buttons, panels = [], []
    for item in [*catalog(public), HAPP_IOS, GHOSTLANE_IOS, GHOSTLANE_DESKTOP]:
        key = item['id']
        active = key == 'happ'
        icon, description = descriptions[key]
        device = 'ios' if key.endswith('-ios') else 'desktop' if key in ('koala', 'ghostlane-desktop') else 'android'
        short_name = 'Clash Meta' if key == 'clashmeta' else item['name']
        buttons.append(f'<button type="button" class="app" id="choose-{key}" data-client="{key}" data-device="{device}" aria-controls="{key}" aria-pressed="{str(active).lower()}"' + (' hidden' if device != 'android' else '') + f'><span class="app-icon" aria-hidden="true">{icon}</span><span><strong>{esc(short_name)}</strong><small>{esc(description)}</small></span><span class="check" aria-hidden="true">✓</span></button>')
        panel = f'<section class="client-panel{" is-active" if active else ""}" id="{key}" aria-labelledby="choose-{key}"><div class="step"><span class="step-marker">1</span><div><h3>Установите {esc(item["name"])}</h3>'
        if key == 'ghostlane-ios':
            panel += '<p>Установите Ghostlane из App Store, затем вернитесь на эту страницу.</p><a class="btn" href="' + esc(item['source']) + '" target="_blank" rel="noreferrer">Скачать в App Store ↗</a>'
        elif key == 'ghostlane-desktop':
            panel += '<p>Выберите установщик Ghostlane для своей системы.</p><a class="btn" href="' + esc(item['source']) + '" target="_blank" rel="noreferrer">Скачать для компьютера ↗</a>'
        elif key == 'happ-ios':
            panel += '<p>Установите приложение из App Store, затем вернитесь на эту страницу.</p><a class="btn" href="' + esc(item['source']) + '" target="_blank" rel="noreferrer">Скачать в App Store ↗</a><details><summary>Приложение недоступно в моём регионе</summary><p>На <a href="https://happ.info" target="_blank" rel="noreferrer">сайте разработчика Happ</a> откройте Download → iOS и проверьте доступные варианты установки для своего региона.</p></details>'
        elif item.get('download_url'):
            panel += f'<p>Скачайте файл на телефон и откройте его для установки.</p><div class="download-row"><a class="btn" href="{esc(item["download_url"])}" download><span aria-hidden="true">↓</span> Скачать для Android</a><span class="file-meta">APK · {item["size"] / 1024**2:.0f} МБ · v{esc(str(item["version"]).lstrip("v"))}</span></div>'
            panel += '<details><summary>Не получается установить?</summary><p>' + esc(INSTALL) + '</p>'
            if key == 'v2rayng':
                panel += '<p>Для старого телефона, если основной файл не устанавливается: <a href="/downloads/v2rayng-arm7.apk">скачать другую версию APK</a>.</p>'
            panel += '</details>'
        elif key == 'koala':
            panel += '<p>Выберите установщик для своей системы на странице разработчика.</p><a class="btn" href="' + esc(item['source']) + '" target="_blank" rel="noreferrer">Скачать для компьютера ↗</a><details><summary>Можно установить на Android?</summary><p>' + esc(KOALA_ANDROID) + '</p></details>'
        else:
            panel += '<a class="btn" href="' + esc(item['source']) + '" target="_blank" rel="noreferrer">Скачать у разработчика ↗</a>'
        panel += '</div></div><div class="step"><span class="step-marker">2</span><div><h3>Добавьте свою подписку</h3>'
        if subscription:
            url = subscription + '?format=' + item['format']
            panel += '<p>Эта ссылка уже подготовлена для выбранного приложения.</p>' + f'<div class="copy-box"><textarea readonly rows="2" aria-label="Ссылка подписки для {esc(item["name"])}" id="url-{key}">{esc(url)}</textarea><button type="button" class="btn" data-copy="url-{key}">Копировать ссылку</button></div><div class="privacy">Не передавайте её другим людям.</div>'
        else:
            panel += '<p>В Telegram-кабинете нажмите «Подключить VPN», выберите приложение и скопируйте ссылку для ' + esc(item['name']) + '. Если подписку выдал менеджер, ссылка находится в его сообщении.</p>'
            if bot_url:
                panel += '<a class="btn secondary" href="' + esc(bot_url) + '">Получить ссылку в боте ↗</a>'
        panel += '</div></div><div class="step"><span class="step-marker">3</span><div><h3>Подключитесь в приложении</h3><ol class="instructions">' + ''.join('<li>' + esc(step) + '</li>' for step in item['steps'][2:]) + '</ol></div></div>'
        panel += '<div class="done">✓ Готово. VPN включается и выключается в приложении.</div><a class="source-link" href="' + esc(item['source']) + '" rel="noreferrer" target="_blank">Официальные релизы ' + esc(item['name']) + ' ↗</a></section>'
        panels.append(panel)
    template = Path(__file__).with_name('connect.html').read_text(encoding='utf-8')
    replacements = {'{{APP_BUTTONS}}': ''.join(buttons), '{{CLIENT_PANELS}}': ''.join(panels), '{{INSTALL}}': esc(INSTALL), '{{HELP}}': esc(HELP), '{{HEADER_LINK}}': '<a class="header-link" href="' + esc(bot_url) + '">Telegram-кабинет ↗</a>' if bot_url else '<a class="header-link" href="#happ">Как подключиться</a>', '{{SUPPORT_LINK}}': '<a class="btn secondary" href="' + esc(bot_url) + '">Открыть кабинет ↗</a>' if bot_url else '<p>Обратитесь к менеджеру, который выдал подписку.</p>'}
    # Replace only template placeholders in a single pass; never interpret user data.
    import re
    return re.sub(r'\{\{[A-Z_]+\}\}', lambda match: replacements[match.group()], template)
