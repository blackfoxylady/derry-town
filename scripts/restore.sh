#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test "$#" -eq 2 && test "$2" = --yes || { echo 'Usage: sh scripts/restore.sh backups/file.dump --yes (replaces current DB)' >&2; exit 1; }
test -s "$1"
docker compose up -d db
docker compose exec -T db sh -c 'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 1; done'
docker compose exec -T db pg_restore --list < "$1" >/dev/null
docker compose stop web
# The restore is atomic. On error the old DB remains and the web stays stopped.
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction --exit-on-error' < "$1"
docker compose up -d web
echo 'Restored. Check docker compose ps and /healthz/.'
