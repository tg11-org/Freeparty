#!/bin/sh
set -e

if [ "$#" -gt 0 ]; then
	exec "$@"
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
