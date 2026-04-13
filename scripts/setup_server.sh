#!/usr/bin/env bash
set -euo pipefail

# Freeparty server bootstrap for Ubuntu 22.04+
# Usage:
#   ./scripts/setup_server.sh \
#     --site-domain freeparty.tg11.org \
#     --server-ip 127.5.0.0 \
#     --app-port 18000

SITE_DOMAIN="${SITE_DOMAIN:-freeparty.tg11.org}"
SERVER_IP="${SERVER_IP:-127.5.0.0}"
APP_PORT="${APP_PORT:-18000}"
NON_INTERACTIVE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site-domain)
      SITE_DOMAIN="$2"
      shift 2
      ;;
    --server-ip)
      SERVER_IP="$2"
      shift 2
      ;;
    --app-port)
      APP_PORT="$2"
      shift 2
      ;;
    --yes)
      NON_INTERACTIVE="true"
      shift 1
      ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

if [[ ! -f compose.yaml ]]; then
  echo "Run this script from the repo root (compose.yaml not found)."
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

COMPOSE_BIN=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
  else
    echo "Neither 'docker compose' nor 'docker-compose' is available on PATH."
    exit 1
  fi
fi

echo "Configuring .env for deployment..."
python3 - <<'PY' "$SITE_DOMAIN" "$SERVER_IP" "$APP_PORT"
import pathlib
import re
import sys

site_domain = sys.argv[1]
server_ip = sys.argv[2]
app_port = sys.argv[3]
env_path = pathlib.Path('.env')
text = env_path.read_text(encoding='utf-8')

updates = {
    'DJANGO_SETTINGS_MODULE': 'config.settings.production',
    'DEBUG': 'False',
    'SITE_SCHEME': 'https',
    'SITE_DOMAIN': site_domain,
  'BIND_IP': server_ip,
    'WEB_PORT': app_port,
  'DB_PORT': '5432',
  'REDIS_PORT': '6379',
  'SMTP_PORT': '1025',
  'MAILHOG_UI_PORT': '8025',
}

for key, value in updates.items():
    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.M)
    replacement = f'{key}={value}'
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        if not text.endswith('\n'):
            text += '\n'
        text += replacement + '\n'

for key in ('ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'CORS_ALLOWED_ORIGINS'):
    text = re.sub(rf'^{re.escape(key)}=.*$', '', text, flags=re.M)

if not text.endswith('\n'):
    text += '\n'

text += f'ALLOWED_HOSTS={site_domain},localhost,127.0.0.1\n'
text += f'CSRF_TRUSTED_ORIGINS=https://{site_domain},http://{site_domain}\n'
text += f'CORS_ALLOWED_ORIGINS=https://{site_domain},http://{site_domain}\n'

env_path.write_text(text, encoding='utf-8')
PY

echo "Starting Docker stack..."
"${COMPOSE_BIN[@]}" up --detach --build

echo "Running migrations..."
"${COMPOSE_BIN[@]}" exec -T web python manage.py migrate

echo "Collecting static files..."
"${COMPOSE_BIN[@]}" exec -T web python manage.py collectstatic --noinput

if [[ "$NON_INTERACTIVE" != "true" ]]; then
  read -r -p "Create superuser now? [y/N] " CREATE_SUPERUSER
  if [[ "$CREATE_SUPERUSER" =~ ^[Yy]$ ]]; then
    "${COMPOSE_BIN[@]}" exec web python manage.py createsuperuser
  fi
fi

cat <<EOF

Setup complete.

App upstream (direct): http://${SERVER_IP}:${APP_PORT}
Primary URL: https://${SITE_DOMAIN}

Next steps:
1. Install Apache config from deploy/apache/freeparty.site.conf
2. Enable Apache modules: proxy proxy_http proxy_wstunnel headers rewrite ssl socache_shmcb
3. Reload Apache

EOF
