#!/bin/sh
set -eu
if [ "${1:-}" = gunicorn ]; then
  python manage.py migrate --noinput
  python manage.py atlas seed
  python manage.py collectstatic --noinput
  python manage.py atlas rebuild
fi
exec "$@"
