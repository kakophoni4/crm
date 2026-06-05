# SNI split: HTTPS для CRM + VPN (xray REALITY) на одном `:443`

**Сервер:** `146.19.125.77`  
**Домены CRM:** `app.crmkanasha.org`, `api.crmkanasha.org`  
**VPN:** xray REALITY на том же IP, порт **443** (снаружи)

---

## Как это работает

```
                    ┌─────────────────────────────────────┐
  Browser HTTPS     │  nginx stream (:443, ssl_preread)   │
  SNI=app.crm...    │                                     │
        ──────────► │  app/api SNI  ──► 127.0.0.1:8443    │──► CRM (TLS terminate)
                    │  default      ──► 127.0.0.1:10443   │──► xray REALITY (TCP passthrough)
  VPN client        │                                     │
  (REALITY)         └─────────────────────────────────────┘
        ──────────►       (не CRM SNI → default → xray)
```

- **CRM:** nginx **завершает TLS** на `127.0.0.1:8443`, сертификат Let's Encrypt.
- **VPN:** xray слушает **только** `127.0.0.1:10443`. Снаружи `:443` — stream **проксирует TCP** без расшифровки → REALITY работает как раньше.
- **Let's Encrypt:** выпуск через **порт 80** (HTTP-01), `:443` для certbot не нужен.

---

## Файлы в репозитории

| Файл | Назначение |
|------|------------|
| `deploy/server/nginx/stream-sni.conf` | Диспетчер SNI на `:443` |
| `deploy/server/nginx/crmkanasha-ssl.conf` | HTTPS CRM на `:8443` |
| `deploy/server/nginx/crmkanasha.conf` | HTTP `:80` + ACME webroot |
| `deploy/server/nginx/crmkanasha-redirect.conf` | Редирект HTTP→HTTPS (после установки) |
| `scripts/deploy/vps/install-sni-split.sh` | Автоустановка на VPS |

---

## Быстрая установка (на сервере)

```bash
ssh root@146.19.125.77
cd /root/crm
git pull   # или scp обновлённых файлов
bash scripts/deploy/vps/install-sni-split.sh
```

Скрипт спросит подтверждение на каждом опасном шаге.

### Ручной порядок (если без скрипта)

#### 1. Сертификаты (порт 80, VPN не трогаем)

```bash
apt install -y nginx certbot
mkdir -p /var/www/certbot /etc/nginx/stream.conf.d
cp deploy/server/nginx/crmkanasha.conf /etc/nginx/sites-available/crmkanasha
ln -sf /etc/nginx/sites-available/crmkanasha /etc/nginx/sites-enabled/00-crmkanasha
nginx -t && systemctl reload nginx

certbot certonly --webroot -w /var/www/certbot \
  -d app.crmkanasha.org -d api.crmkanasha.org \
  --agree-tos -m admin@crmkanasha.org
```

#### 2. Перенести xray с `:443` на внутренний порт

Отредактировать `/usr/local/etc/xray/config.json` — inbound VPN:

```json
{
  "listen": "127.0.0.1",
  "port": 10443,
  "protocol": "vless",
  ...
}
```

**Было:** `"port": 443` (и часто `"listen": "0.0.0.0"`).

```bash
cp /usr/local/etc/xray/config.json /usr/local/etc/xray/config.json.bak
# правка вручную или jq (см. install-sni-split.sh)
systemctl restart xray
ss -tlnp | grep xray
# должно быть 127.0.0.1:10443, НЕ :443
```

Клиенты VPN **не меняют порт** — по-прежнему `IP:443`. Меняется только то, *кто* слушает 443 (теперь nginx stream).

#### 3. Включить SNI split + HTTPS CRM

```bash
# stream {} в nginx.conf если нет:
grep -q stream.conf.d /etc/nginx/nginx.conf || cat >> /etc/nginx/nginx.conf << 'EOF'

stream {
    include /etc/nginx/stream.conf.d/*.conf;
}
EOF

cp deploy/server/nginx/stream-sni.conf /etc/nginx/stream.conf.d/00-sni-split.conf
cp deploy/server/nginx/crmkanasha-ssl.conf /etc/nginx/sites-available/crmkanasha-ssl
ln -sf /etc/nginx/sites-available/crmkanasha-ssl /etc/nginx/sites-enabled/01-crmkanasha-ssl

nginx -t && systemctl reload nginx
```

#### 4. Редирект HTTP → HTTPS

```bash
cp deploy/server/nginx/crmkanasha-redirect.conf /etc/nginx/sites-available/crmkanasha
nginx -t && systemctl reload nginx
```

#### 5. Обновить CRM env и пересобрать frontend

```bash
cd /root/crm
sed -i 's|^CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=https://app.crmkanasha.org|' deploy/.env.staging
sed -i 's|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=https://api.crmkanasha.org/api/v1|' deploy/.env.staging
sed -i 's|^VITE_WS_URL=.*|VITE_WS_URL=wss://api.crmkanasha.org/ws|' deploy/.env.staging
bash scripts/deploy/vps/update.sh
```

---

## Проверка

```bash
ss -tlnp | grep -E ':443|:80|:8443|:10443'

curl -I https://app.crmkanasha.org/
curl https://api.crmkanasha.org/healthz

# VPN — с телефона/ПК подключиться как раньше (IP:443, та же подписка Happ)
```

Ожидаемые слушатели:

| Порт | Процесс | Назначение |
|------|---------|------------|
| `:443` | nginx | SNI split |
| `:80` | nginx | ACME + redirect |
| `:8443` | nginx | CRM TLS |
| `:10443` | xray | VPN (localhost) |

---

## Откат

```bash
# 1. Убрать stream
rm /etc/nginx/stream.conf.d/00-sni-split.conf
rm /etc/nginx/sites-enabled/01-crmkanasha-ssl

# 2. Вернуть xray на :443
# восстановить config.json из .bak, port 443, listen 0.0.0.0
systemctl restart xray

# 3. HTTP-only CRM
cp deploy/server/nginx/crmkanasha.conf /etc/nginx/sites-available/crmkanasha
nginx -t && systemctl reload nginx
```

---

## Частые проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| VPN не коннектится | xray всё ещё на `:443` вместе с nginx | `ss -tlnp \| grep 443` — только nginx |
| VPN не коннектится | xray не на `10443` | проверить config + `systemctl restart xray` |
| CRM HTTPS 502 | Docker не поднят | `crm-status`, порты `19001`/`19090` |
| certbot fail | DNS / firewall | A-записи → `146.19.125.77`, `:80` открыт |
| WS не работает | старый frontend | rebuild с `wss://` в VITE_WS_URL |
| REALITY на 8443 не работал раньше | клиенты шли на 8443 напрямую | при SNI split клиенты идут на **443**, xray внутри |

---

## Продление сертификата

```bash
certbot renew --dry-run
# hook: /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh (создаёт install-sni-split.sh)
```

---

*Обновлено: 2026-05-26*
