# Bitwarden (Vaultwarden) — self-hosted password manager

Лёгкий сервер, совместимый с официальными клиентами Bitwarden (desktop, mobile, browser extension).

**URL:** `https://huitawarden.bttsrvvrs.org`  
**Сервер:** `146.19.125.32` (тот же VPS, что CRM на `bttsrvvrs.org`)  
**TLS:** nginx SNI split (как CRM + VPN)

---

## Установка без деплоя CRM

**Не делайте `git pull` и `crm-update`**, если не хотите катить изменения CRM.

### Вариант A — только папка Bitwarden (рекомендуется)

С Windows:

```powershell
.\scripts\deploy\vps\upload-bitwarden.ps1
```

На сервере:

```bash
bash /opt/vaultwarden/install.sh
```

Папка `deploy/bitwarden/` автономна: compose, nginx, install.sh. CRM-контейнеры не перезапускаются.

### Вариант B — из репозитория на сервере (тоже без CRM)

```bash
bash scripts/deploy/vps/install-bitwarden.sh
```

Скрипт поднимает только контейнер `vaultwarden` и правит nginx. **`update.sh` не вызывается.**

---

## Быстрая установка (если уже делали git pull)

```bash
ssh root@146.19.125.77
cd /root/crm
git pull

# DNS: A-запись huitawarden.bttsrvvrs.org → 146.19.125.32

bash scripts/deploy/vps/install-bitwarden.sh
```

Скрипт:
1. Создаёт `deploy/bitwarden/.env` с `ADMIN_TOKEN`
2. Поднимает контейнер Vaultwarden на `127.0.0.1:19180`
3. Расширяет сертификат Let's Encrypt для `huitawarden.bttsrvvrs.org`
4. Добавляет SNI-маршрут и nginx reverse proxy

---

## Ручная установка

### 1. Env и контейнер

```bash
cp deploy/bitwarden/env.example deploy/bitwarden/.env
# ADMIN_TOKEN: openssl rand -base64 48

cd deploy/bitwarden
docker compose --env-file .env up -d
curl http://127.0.0.1:19180/alive   # должно вернуть "OK"
```

### 2. Сертификат

```bash
certbot certonly --webroot -w /var/www/certbot \
  -d chat.bttsrvvrs.org -d api.bttsrvvrs.org -d huitawarden.bttsrvvrs.org \
  --expand
```

### 3. nginx

```bash
cp deploy/server/nginx/vaultwarden-http.conf /etc/nginx/sites-enabled/02-vaultwarden-http
cp deploy/server/nginx/vaultwarden-ssl.conf /etc/nginx/sites-enabled/03-vaultwarden-ssl
cp deploy/server/nginx/stream-sni.conf /etc/nginx/stream.conf.d/00-sni-split.conf
nginx -t && systemctl reload nginx
```

---

## Первый вход

1. **Админ-панель:** https://huitawarden.bttsrvvrs.org/admin  
   Токен — `ADMIN_TOKEN` из `deploy/bitwarden/.env`

2. **Регистрация:** по умолчанию `SIGNUPS_ALLOWED=false`. Включите временно в `.env` или приглашайте пользователей через `/admin`.

3. **Клиент Bitwarden:**  
   Settings → Self-hosted → Server URL = `https://huitawarden.bttsrvvrs.org`

Подробная инструкция для пользователей: [`docs/BITWARDEN_USER_GUIDE.md`](BITWARDEN_USER_GUIDE.md)

---

## Управление

```bash
# Статус
docker ps --filter name=vaultwarden
curl https://huitawarden.bttsrvvrs.org/alive

# Логи
docker logs vaultwarden -f --tail 100

# Обновление
cd /root/crm/deploy/bitwarden
docker compose pull
docker compose --env-file .env up -d

# Бэкап (volume с БД SQLite)
docker run --rm -v vaultwarden_vaultwarden-data:/data -v /root/backups:/backup \
  alpine tar czf /backup/vaultwarden-$(date +%F).tar.gz -C /data .
```

---

## Файлы

| Файл | Назначение |
|------|------------|
| `deploy/bitwarden/docker-compose.yaml` | Контейнер Vaultwarden |
| `deploy/bitwarden/env.example` | Шаблон переменных |
| `deploy/server/nginx/vaultwarden-ssl.conf` | HTTPS proxy |
| `deploy/server/nginx/vaultwarden-http.conf` | ACME + redirect |
| `deploy/server/nginx/stream-sni.conf` | SNI для `huitawarden.bttsrvvrs.org` |
| `scripts/deploy/vps/install-bitwarden.sh` | Автоустановка |

---

## Безопасность

- Контейнер слушает только `127.0.0.1:19180` — снаружи доступ только через HTTPS nginx.
- Держите `ADMIN_TOKEN` в секрете; не коммитьте `deploy/bitwarden/.env`.
- Рекомендуется 2FA для всех пользователей (в настройках аккаунта Bitwarden).
- Регулярно бэкапьте volume `vaultwarden-data`.

---

*Обновлено: 2026-06-14*
