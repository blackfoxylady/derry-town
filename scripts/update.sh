#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/backup.sh
docker compose build web
docker compose stop web
docker compose run --rm web python manage.py migrate --noinput
# New derivative sizes (pass 11: 480/960 for the gallery) are created before the site starts.
docker compose run --rm web python manage.py photos rebuild || echo "WARNING: some photo derivatives failed, see photos check"
docker compose up -d web
# Locators are rendered on a PC and committed (pass 5): warn when they lag behind the map data.
docker compose run --rm web python manage.py render_locators check || echo "WARNING: locators are stale, see render_locators --help"
docker compose ps
