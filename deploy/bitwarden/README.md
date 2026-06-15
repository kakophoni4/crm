# Vaultwarden — установка без деплоя CRM

Эта папка **полностью автономна**. Можно скопировать на сервер и установить, не делая `git pull` и не трогая CRM.

## Что меняется / что не трогается

| Действие | CRM |
|----------|-----|
| `docker compose up` для vaultwarden | ❌ не затрагивается |
| `deploy/.env.staging`, `update.sh` | ❌ не трогаются |
| Контейнеры crm-staging-* | ❌ не перезапускаются |
| nginx: +2 site для vault, +1 строка в SNI | ✅ только для vault |
| certbot: добавить домен в существующий сертификат | ✅ безопасно для CRM |

---

## Установка с Windows (без git pull на сервере)

### 1. DNS

A-запись: `huitawarden.bttsrvvrs.org` → `146.19.125.32`

### 2. Скопировать папку на VPS

PowerShell из корня проекта:

```powershell
scp -r deploy/bitwarden root@146.19.125.32:/opt/vaultwarden
```

### 3. Установить на сервере

```bash
ssh root@146.19.125.32
# если scp с Windows — убрать CRLF:
sed -i 's/\r$//' /opt/vaultwarden/install.sh
bash /opt/vaultwarden/install.sh
```

Сохраните **ADMIN_TOKEN**, который выведет скрипт.

### 4. Проверка

```bash
curl https://huitawarden.bttsrvvrs.org/alive
# OK
```

---

## Первый запуск (после установки)

1. Откройте https://huitawarden.bttsrvvrs.org/admin — вставьте ADMIN_TOKEN.
2. В `.env` временно включите регистрацию **или** создайте invite в админке:
   ```bash
   # вариант A: разрешить регистрацию на 10 минут
   sed -i 's/SIGNUPS_ALLOWED=false/SIGNUPS_ALLOWED=true/' /opt/vaultwarden/.env
   cd /opt/vaultwarden && docker compose --env-file .env up -d
   ```
3. Зарегистрируйтесь на https://huitawarden.bttsrvvrs.org
4. Снова выключите регистрацию (`SIGNUPS_ALLOWED=false`).

---

## Как пользоваться

См. [`docs/BITWARDEN_USER_GUIDE.md`](../../docs/BITWARDEN_USER_GUIDE.md) — пошагово для новичков.

Кратко:
- **Сайт:** https://huitawarden.bttsrvvrs.org
- **Приложения:** Bitwarden (Windows / Android / iOS / расширение браузера)
- **Self-hosted URL в приложении:** `https://huitawarden.bttsrvvrs.org`
- **Главный пароль** — один на весь сейф; его никто не восстановит, запомните или запишите offline.

---

## Обновление только Vaultwarden

```bash
cd /opt/vaultwarden
docker compose pull
docker compose --env-file .env up -d
```

CRM при этом не обновляется.
