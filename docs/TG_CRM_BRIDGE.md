# Telegram ↔ CRM bridge

> **Полная актуальная документация:** [`TELEGRAM_INTEGRATION.md`](TELEGRAM_INTEGRATION.md)

Двусторонняя связь: сообщения из Telegram → CRM, ответ оператора из CRM → Telegram.

## Быстрый старт (VPS)

### 1. Создай бота в Telegram

1. Открой [@BotFather](https://t.me/BotFather)
2. `/newbot` → имя → username (например `crm_test_kanasha_bot`)
3. Скопируй **token** (`123456789:AAH...`)

### 2. Залей файлы с Windows

```powershell
cd "C:\Users\chirt\Downloads\Новая папка"
ssh root@146.19.125.77 "mkdir -p /root/crm/scripts/bots/tg_crm_bridge"
scp -r scripts\bots\tg_crm_bridge\* root@146.19.125.77:/root/crm/scripts/bots/tg_crm_bridge/
scp deploy\server\docker-compose.vps.yaml root@146.19.125.77:/root/crm/deploy/server/
```

### 3. Установка на сервере

```bash
cd /root/crm
sed -i 's/\r$//' scripts/bots/tg_crm_bridge/install.sh
sed -i 's/\r$//' scripts/bots/tg_crm_bridge/finish_setup.sh
chmod +x scripts/bots/tg_crm_bridge/install.sh scripts/bots/tg_crm_bridge/finish_setup.sh
TG_BOT_TOKEN='ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER' bash scripts/bots/tg_crm_bridge/install.sh
```

Если Docker уже пересобран, а скрипт упал на **логине** (JSONDecodeError / HTTP 422):

```bash
cd /root/crm
SKIP_DOCKER=1 bash scripts/bots/tg_crm_bridge/finish_setup.sh
# или: ADMIN_PASS='ваш_пароль' SKIP_DOCKER=1 bash scripts/bots/tg_crm_bridge/finish_setup.sh
```

Скрипт: venv, systemd, обновит `outbound_url` бота, перезапустит worker (если не `SKIP_DOCKER=1`).

### 4. Проверка

1. Telegram → открой своего бота → **Start** → напиши «Привет»
2. https://app.crmkanasha.org → чат с твоим контактом
3. Ответь из CRM → сообщение должно прийти **в Telegram**

### Логи

```bash
journalctl -u tg-crm-bridge -f
docker logs crm-staging-worker --tail 50
```

### Обновление после правок (фото + live-чат)

**Windows** — залить файлы:

```powershell
cd "C:\Users\chirt\Downloads\Новая папка"
scp scripts\bots\tg_crm_bridge\main.py root@146.19.125.77:/root/crm/scripts/bots/tg_crm_bridge/
scp scripts\bots\tg_crm_bridge\update_bridge.sh root@146.19.125.77:/root/crm/scripts/bots/tg_crm_bridge/
scp scripts\deploy\vps\fix-live-chat.sh root@146.19.125.77:/root/crm/scripts/deploy/vps/
```

**Сервер:**

```bash
cd /root/crm
sed -i 's/\r$//' scripts/bots/tg_crm_bridge/update_bridge.sh scripts/deploy/vps/fix-live-chat.sh
chmod +x scripts/bots/tg_crm_bridge/update_bridge.sh scripts/deploy/vps/fix-live-chat.sh
bash scripts/bots/tg_crm_bridge/update_bridge.sh
bash scripts/deploy/vps/fix-live-chat.sh
```

После этого: Ctrl+F5 в браузере — новые сообщения без F5; фото через несколько секунд.

### Остановка

```bash
systemctl stop tg-crm-bridge
```
