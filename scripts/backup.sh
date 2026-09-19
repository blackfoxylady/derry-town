#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
dest="${1:-backups/derry-$(date -u +%Y%m%dT%H%M%SZ).dump}"
test ! -e "$dest" || { echo 'Destination already exists' >&2; exit 1; }
temp="$dest.partial"
trap 'rm -f "$temp"' EXIT HUP INT TERM
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$temp"
test -s "$temp"
mv "$temp" "$dest"
sha256sum "$dest" > "$dest.sha256"
echo "Backup: $dest"
# Медиа (фотографии): дамп БД хранит записи, файлы уносим отдельным архивом.
# У контейнера прежней версии каталога media ещё нет — тогда шаг пропускается.
if docker compose exec -T web test -d /app/media; then
  media="${dest%.dump}-media.tar.gz"
  mtemp="$media.partial"
  trap 'rm -f "$temp" "$mtemp"' EXIT HUP INT TERM
  docker compose exec -T web tar -C /app -czf - media > "$mtemp"
  test -s "$mtemp"
  mv "$mtemp" "$media"
  sha256sum "$media" > "$media.sha256"
  echo "Media backup: $media"
else
  echo "Media backup skipped: /app/media is absent in the running container."
fi
