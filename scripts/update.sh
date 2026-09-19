#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/backup.sh
docker compose build web
docker compose stop web
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d web
docker compose ps
