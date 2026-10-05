# Проверка игровых TLS-целей

Проверка: 5 октября 2026 года, с каждого VPN-узла.

Проверены 54 домена из 20 игровых сервисов и связанных платформ; 40 доменов прошли проверку на всех 7 узлах.

Критерии: корректный DNS, проверенный системным хранилищем сертификат, TLS 1.3 и ALPN `h2`.
Это техническая пригодность цели для текущего XHTTP/REALITY, а не проверка доступности из РФ.
Отказ означает несовместимость с выбранными критериями в момент замера; сайт может нормально работать в браузере.
Один замер не доказывает долговременную стабильность. Перед установкой выбранная цель проверяется ещё три раза.

| Сервис | Прошли на всех узлах | Не прошли |
| --- | --- | --- |
| Steam | `cdn.cloudflare.steamstatic.com`<br>`cdn.fastly.steamstatic.com`<br>`shared.fastly.steamstatic.com`<br>`shared.akamai.steamstatic.com` | `store.steampowered.com`<br>`steamcommunity.com`<br>`cdn.akamai.steamstatic.com` |
| Riot | `auth.riotgames.com`<br>`status.riotgames.com`<br>`playvalorant.com`<br>`www.leagueoflegends.com` | `www.riotgames.com`<br>`l3cdn.riotgames.com` |
| Roblox | `setup.rbxcdn.com`<br>`www.roblox.com` | `www.rbxcdn.com` |
| Epic Games | `www.epicgames.com`<br>`store.epicgames.com`<br>`download.epicgames.com`<br>`cdn1.unrealengine.com`<br>`static-assets-prod.epicgames.com`<br>`fastly-download.epicgames.com` | — |
| Battle.net | `www.blizzard.com`<br>`account.battle.net` | `www.battle.net` |
| EA | `www.ea.com`<br>`help.ea.com` | `accounts.ea.com` |
| Ubisoft | `www.ubisoft.com`<br>`staticctf.ubisoft.com` | `account.ubisoft.com` |
| Xbox | `www.xbox.com`<br>`assets.xboxservices.com` | — |
| PlayStation | `store.playstation.com` | `www.playstation.com` |
| Nintendo | `www.nintendo.com` | `accounts.nintendo.com` |
| GOG | `www.gog.com`<br>`images.gog-statics.com` | — |
| Rockstar Games | `www.rockstargames.com` | `socialclub.rockstargames.com` |
| Wargaming | `worldoftanks.eu`<br>`worldofwarships.eu` | — |
| Minecraft | `www.minecraft.net`<br>`piston-meta.mojang.com`<br>`piston-data.mojang.com` | — |
| Discord | `discord.com`<br>`cdn.discordapp.com` | — |
| Twitch | `www.twitch.tv`<br>`static.twitchcdn.net` | — |
| Bungie | `www.bungie.net` | — |
| Warframe | — | `www.warframe.com` |
| Path of Exile | `www.pathofexile.com` | — |
| Final Fantasy XIV | — | `www.finalfantasyxiv.com` |

## Добавленные входы

| Название в подписке | TLS-цель | Доступность |
| --- | --- | --- |
| Steam | `cdn.fastly.steamstatic.com` | Каждый узел |
| Riot | `auth.riotgames.com` | Каждый узел |
| Roblox | `setup.rbxcdn.com` | Каждый узел |
| Epic Games | `static-assets-prod.epicgames.com` | Каждый узел |
| Battle.net | `account.battle.net` | Каждый узел |
| EA | `www.ea.com` | Каждый узел |
| Ubisoft | `staticctf.ubisoft.com` | Каждый узел |

На каждом узле все семь дополнительных входов. Прежние TCP 443 и UDP 443/8444 сохранены.
Для дополнительных TLS-входов выбираются свободные TCP-порты 8443 и 8445–8499; 8444 не используется.
Занятые другими службами порты пропускаются. Уже установленный игровой вход сохраняет порт и ключи.
Все входы сохраняются внутри профилей стран и включены в AUTO при здоровом узле.
Отдельный ручной выбор транспорта в Happ/Clash доступен через `view=all`;
обычные URI-форматы сохраняют полный ручной список.
Вход использует TLS-имя игрового сервиса. Игровые UDP-протоколы он не имитирует,
трафик пользователя через Steam/Riot/Roblox не перенаправляется.
SNI не устраняет блокировку IP, подсети, нестандартного порта или сеть со списком разрешённых адресов.
С серверной стороны 8443 доступен; фильтрация этого порта у конкретного оператора проверяется с устройства клиента.

Время TLS в сыром отчёте включает DNS, соединение и handshake. Оно не равно ping VPN или игры.
Для воспроизведения: `python3 /opt/crm-vpn/probe_reality_targets.py` на CRM; `--node` и `--brand` сужают проверку.

Первичные документы: [Xray REALITY](https://xtls.github.io/en/config/transports/reality.html),
[домены Steam](https://help.steampowered.com/en/faqs/view/2EA8-4D75-DA21-31EB),
[домены Epic Games](https://www.epicgames.com/help/c-36624475/c-35761596/which-domains-need-to-be-whitelisted-to-reach-the-epic-servers-a15422130).
