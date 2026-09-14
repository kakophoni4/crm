#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/compose.sh"
check_failed=0
for service in api worker; do
  echo "Проверка ИИ из $service"
  compose exec -T "$service" python - <<'PY' || check_failed=1
import json
import os
import urllib.error
import urllib.request

base = os.environ.get('AI_SERVICE_BASE_URL', '').rstrip('/')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
failed = False
for path, key_name in [('/v1/capabilities','AI_SERVICE_REPLY_KEY'),('/v1/connection','AI_SERVICE_ADMIN_KEY')]:
    key = os.environ.get(key_name)
    if not key or not base:
        print(path, 'НЕ НАСТРОЕНО:', key_name if not key else 'AI_SERVICE_BASE_URL')
        failed = True
        continue
    request = urllib.request.Request(base + path, headers={'Authorization':'Bearer ' + key})
    try:
        with opener.open(request, timeout=15) as response:
            result = json.load(response)
            print(path, 'HTTP', response.status)
            for name in ('configured','training_available','contract_version','model'):
                if name in result:
                    print(' ', name, result[name])
    except urllib.error.HTTPError as exc:
        print(path, 'HTTP', exc.code)
        failed = True
    except (urllib.error.URLError, TimeoutError, ValueError):
        print(path, 'Нет корректного ответа сервиса')
        failed = True
raise SystemExit(1 if failed else 0)
PY
done

exit "$check_failed"
