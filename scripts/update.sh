#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/backup.sh
docker compose build web
docker compose stop web
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d web
# Locators are rendered on a PC and committed (pass 5): warn when they lag behind the map data.
docker compose run --rm web python manage.py render_locators check || echo "WARNING: locators are stale, see render_locators --help"
docker compose ps
