#!/bin/sh
set -eu

# Daily Postgres backup for Freeparty with rolling retention.
# Defaults are safe for the current compose setup and can be overridden via env.
BACKUP_DIR="${BACKUP_DIR:-/var/backups/freeparty}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
RETENTION_COUNT="${RETENTION_COUNT:-7}"
PROJECT_DIR="${PROJECT_DIR:-/var/www/Freeparty}"
DB_CONTAINER="${DB_CONTAINER:-db}"
DB_NAME="${DB_NAME:-freeparty}"
DB_USER="${DB_USER:-freeparty}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/freeparty_db_${TIMESTAMP}.sql.gz"
TMP_FILE="$BACKUP_FILE.tmp"

# Use a temporary file then atomically move into place on success.
cd "$PROJECT_DIR"
docker compose exec -T "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip -9 > "$TMP_FILE"
mv "$TMP_FILE" "$BACKUP_FILE"

# Rolling retention by age.
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'freeparty_db_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

# Rolling retention by count: keep newest N backups.
ls -1t "$BACKUP_DIR"/freeparty_db_*.sql.gz 2>/dev/null | awk "NR > $RETENTION_COUNT" | xargs -r rm -f

echo "Backup complete: $BACKUP_FILE"
