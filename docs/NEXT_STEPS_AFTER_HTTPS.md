# Следующие шаги после HTTPS (SNI split)

## 1. Hardening на сервере

```bash
cd /root/crm
# скопируй новые scripts/ с Windows (scp) или git pull
sed -i 's/\r$//' scripts/deploy/vps/*.sh scripts/bots/*.sh 2>/dev/null || true
chmod +x scripts/deploy/vps/post-https-setup.sh scripts/bots/provision_test_bot.sh

# бэкапы + проверки (seed не трогает)
bash scripts/deploy/vps/post-https-setup.sh

# после смены пароля admin в UI:
bash scripts/deploy/vps/post-https-setup.sh --clear-seed
```

## 2. Тестовый бот

```bash
cd /root/crm
bash scripts/bots/provision_test_bot.sh
```

Открой https://app.crmkanasha.org — чат с контактом `telegram_user_id` **999888777**.

Повторить событие:

```bash
source /root/crm/.secrets/test_bot_1.env
python3 /root/crm/scripts/bots/send_test_event.py \
  --api-base "$API_BASE" \
  --bot-code "$BOT_CODE" \
  --inbound-secret "$INBOUND_SECRET" \
  --text "Ещё одно тестовое сообщение"
```

## 3. С Windows — залить новые скрипты

```powershell
cd "C:\Users\chirt\Downloads\Новая папка"
scp scripts\deploy\vps\post-https-setup.sh root@146.19.125.77:/root/crm/scripts/deploy/vps/
scp scripts\deploy\vps\status.sh root@146.19.125.77:/root/crm/scripts/deploy/vps/
scp scripts\bots\provision_test_bot.sh root@146.19.125.77:/root/crm/scripts/bots/
scp scripts\bots\send_test_event.py root@146.19.125.77:/root/crm/scripts/bots/
```
