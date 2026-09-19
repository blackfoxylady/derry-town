#!/bin/sh
# Isolated PostgreSQL/Docker acceptance test. Never uses the production project volumes.
set -eu
cd "$(dirname "$0")/.."
project="derry-check-$(date +%s)-$$"
export DERRY_PORT="${DERRY_TEST_PORT:-18080}" DERRY_BIND=127.0.0.1
compose() { docker compose -p "$project" "$@"; }
work="$(mktemp -d)"
cleanup() { compose down -v >/dev/null; rm -rf "$work"; }
trap cleanup EXIT HUP INT TERM
compose up -d --build --wait --wait-timeout 240
compose exec -T web python manage.py test tests --verbosity 2
compose exec -T web python scripts/check_baseline.py
compose exec -T web python manage.py atlas edit 12 --name 'Library acceptance test' --author acceptance --reason 'Check restart persistence'
compose restart web
compose up -d --wait --wait-timeout 240
compose exec -T web python manage.py atlas show feature 12 > "$work/before.json"
compose exec -T web python -c 'from urllib.request import urlopen; import json; d=json.load(urlopen("http://127.0.0.1:8000/api/v1/map/")); assert next(s for s in d["data"]["sites"] if s["id"]==12)["name"]=="Library acceptance test"'
compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' > "$work/backup.dump"
compose exec -T web python manage.py atlas delete 12 --author acceptance --reason 'Check backup restore'
compose stop web
compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction --exit-on-error --no-owner' < "$work/backup.dump"
compose up -d --wait --wait-timeout 240
compose exec -T web python manage.py atlas show feature 12 > "$work/after.json"
cmp "$work/before.json" "$work/after.json"
compose exec -T web python manage.py atlas render --output /app/var/acceptance
printf '%s\n' 'PASS: fresh install, PostgreSQL tests, seed fidelity, restart, API, pg_dump/pg_restore, PDF/SVG.'
