#!/bin/sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-python}"
BASE_URL="${BASE_URL:-}"
RUN_TARGETED_TESTS="${RUN_TARGETED_TESTS:-0}"

if [ -z "$BASE_URL" ]; then
  SITE_SCHEME_VALUE="${SITE_SCHEME:-http}"
  SITE_DOMAIN_VALUE="${SITE_DOMAIN:-localhost:8000}"
  BASE_URL="${SITE_SCHEME_VALUE}://${SITE_DOMAIN_VALUE}"
fi

echo "[verify] Django checks"
"$PYTHON_BIN" manage.py check

echo "[verify] migration drift"
"$PYTHON_BIN" manage.py makemigrations --check --dry-run

if [ "$RUN_TARGETED_TESTS" = "1" ]; then
  echo "[verify] targeted tests"
  "$PYTHON_BIN" manage.py test apps.core.tests.MentionAndHashtagLinkifyTests apps.profiles.tests.ParentalControlsTests
fi

echo "[verify] live health"
curl --fail --silent --show-error "$BASE_URL/health/live/" > /dev/null

echo "[verify] ready health"
curl --fail --silent --show-error "$BASE_URL/health/ready/" > /dev/null

echo "[verify] api live health"
curl --fail --silent --show-error "$BASE_URL/api/v1/health/live/" > /dev/null

echo "[verify] api ready health"
curl --fail --silent --show-error "$BASE_URL/api/v1/health/ready/" > /dev/null

echo "[verify] deployment verification passed for $BASE_URL"
