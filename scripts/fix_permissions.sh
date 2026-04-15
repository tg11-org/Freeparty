#!/usr/bin/env bash
set -euo pipefail

# Fix host-side permissions for bind-mounted paths used by containers.
# Intended for Linux hosts where /app is mounted from the repo checkout.
#
# Usage:
#   sudo ./scripts/fix_permissions.sh
#   sudo ./scripts/fix_permissions.sh --uid 1000 --gid 1000
#   sudo ./scripts/fix_permissions.sh --path /var/www/Freeparty

TARGET_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      TARGET_PATH="$2"
      shift 2
      ;;
    --uid)
      APP_UID="$2"
      shift 2
      ;;
    --gid)
      APP_GID="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

if [[ ! -d "$TARGET_PATH" ]]; then
  echo "Path does not exist: $TARGET_PATH"
  exit 1
fi

echo "Fixing permissions in: $TARGET_PATH"
echo "Using uid:gid = ${APP_UID}:${APP_GID}"

# Ensure required dirs exist.
mkdir -p "$TARGET_PATH/static" "$TARGET_PATH/staticfiles" "$TARGET_PATH/media"

# Ownership for writable runtime dirs.
chown -R "${APP_UID}:${APP_GID}" "$TARGET_PATH/staticfiles" "$TARGET_PATH/media"

# Keep project readable and directories traversable.
find "$TARGET_PATH" -type d -exec chmod 755 {} \;
find "$TARGET_PATH" -type f -exec chmod 644 {} \;

# Ensure scripts remain executable.
chmod +x "$TARGET_PATH/docker/entrypoint.sh" || true
chmod +x "$TARGET_PATH/scripts/"*.sh || true

# Writable runtime dirs for app user.
chmod -R u+rwX,g+rwX "$TARGET_PATH/staticfiles" "$TARGET_PATH/media"

echo "Done."
echo "Next: docker compose up --detach --build"
