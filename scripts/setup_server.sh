#!/usr/bin/env bash
set -euo pipefail

# Freeparty server bootstrap for Ubuntu 22.04+
# Usage:
#   ./scripts/setup_server.sh \
#     --site-domain freeparty.tg11.org \
#     --server-ip 127.5.0.0 \
#     --app-port 18000 \
#     [--reset-db]

SITE_DOMAIN="${SITE_DOMAIN:-freeparty.tg11.org}"
SERVER_IP="${SERVER_IP:-127.5.0.0}"
APP_PORT="${APP_PORT:-18000}"
NON_INTERACTIVE="false"
RESET_DB="false"

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
    --reset-db)
      RESET_DB="true"
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
COMPOSE_V1="false"
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    COMPOSE_V1="true"
  else
    echo "Neither 'docker compose' nor 'docker-compose' is available on PATH."
    exit 1
  fi
fi

if [[ "${COMPOSE_V1}" == "true" ]]; then
  echo "Detected docker-compose v1. Running a cleanup pass to avoid known recreate bug (KeyError: ContainerConfig)."
  "${COMPOSE_BIN[@]}" down --remove-orphans || true
fi

if [[ "${RESET_DB}" == "true" ]]; then
  echo "Reset mode enabled: removing containers and DB volume before startup."
  "${COMPOSE_BIN[@]}" down --volumes --remove-orphans || true
fi

echo "Configuring .env for deployment..."
python3 - <<'PY' "$SITE_DOMAIN" "$SERVER_IP" "$APP_PORT"
import pathlib
import re
import secrets
import sys
from urllib.parse import quote, unquote, urlparse

site_domain = sys.argv[1]
server_ip = sys.argv[2]
app_port = sys.argv[3]
env_path = pathlib.Path('.env')
text = env_path.read_text(encoding='utf-8')

required_updates = {
    'DJANGO_SETTINGS_MODULE': 'config.settings.production',
    'DEBUG': 'False',
    'SITE_SCHEME': 'https',
    'SITE_DOMAIN': site_domain,
    'BIND_IP': server_ip,
    'WEB_PORT': app_port,
}

db_password_match = re.search(r'^POSTGRES_PASSWORD=(.*)$', text, re.M)
db_password = db_password_match.group(1).strip() if db_password_match else ""
database_url_match = re.search(r'^DATABASE_URL=(.*)$', text, re.M)
database_url = database_url_match.group(1).strip() if database_url_match else ""
if not db_password and database_url:
    parsed_database_url = urlparse(database_url)
    db_password = unquote(parsed_database_url.password or "")
if not db_password or db_password == "replace-with-random-local-password":
    db_password = secrets.token_urlsafe(32)
encoded_db_password = quote(db_password, safe="")
for key, value in {
    'POSTGRES_DB': 'freeparty',
    'POSTGRES_USER': 'freeparty',
    'POSTGRES_PASSWORD': db_password,
    'DATABASE_URL': f'postgres://freeparty:{encoded_db_password}@db:5432/freeparty',
}.items():
    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.M)
    replacement = f'{key}={value}'
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        if not text.endswith('\n'):
            text += '\n'
        text += replacement + '\n'

for key, value in required_updates.items():
    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.M)
    replacement = f'{key}={value}'
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        if not text.endswith('\n'):
            text += '\n'
        text += replacement + '\n'

# Keep custom infra port overrides from existing .env (e.g. DB_PORT=5433).
# Only set these defaults if missing.
default_only = {
    'DB_PORT': '5432',
    'REDIS_PORT': '6379',
    'SMTP_PORT': '1025',
    'MAILHOG_UI_PORT': '8025',
}

for key, value in default_only.items():
    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.M)
    if not pattern.search(text):
        if not text.endswith('\n'):
            text += '\n'
        text += f'{key}={value}\n'

for key in ('ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'CORS_ALLOWED_ORIGINS'):
    text = re.sub(rf'^{re.escape(key)}=.*$', '', text, flags=re.M)

if not text.endswith('\n'):
    text += '\n'

text += f'ALLOWED_HOSTS={site_domain},localhost,127.0.0.1\n'
text += f'CSRF_TRUSTED_ORIGINS=https://{site_domain}\n'
text += f'CORS_ALLOWED_ORIGINS=https://{site_domain}\n'

env_path.write_text(text, encoding='utf-8')
PY

echo "Starting Docker stack..."
"${COMPOSE_BIN[@]}" up --detach --build --remove-orphans

echo "Running migrations..."
if ! "${COMPOSE_BIN[@]}" exec -T web python manage.py migrate --fake-initial; then
  echo "Migration failed."
  echo "If this is a fresh server and data is disposable, re-run with --reset-db."
  echo "If data must be preserved, inspect migration state in django_migrations before retrying."
  exit 1
fi

echo "Collecting static files..."
if ! "${COMPOSE_BIN[@]}" exec -T web python manage.py collectstatic --noinput --clear; then
  echo "collectstatic failed. This is usually host bind-mount permissions on staticfiles/media."
  echo "Run: sudo ./scripts/fix_permissions.sh --path $(pwd)"
  exit 1
fi

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

Recommended: install Docker Compose v2 plugin and use 'docker compose' (legacy docker-compose v1 is deprecated).

EOF
