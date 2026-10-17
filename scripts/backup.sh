#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
# --auto — ночной бэкап из cron: только БД, в backups/auto/, копии старше 14 дней
# удаляются. Без него — полный бэкап (БД + медиа), как и раньше.
auto=0
if [ "${1:-}" = --auto ]; then auto=1; shift; fi
mkdir -p backups
if [ "$auto" = 1 ]; then
  mkdir -p backups/auto
  dest="backups/auto/derry-$(date -u +%Y%m%dT%H%M%SZ).dump"
else
  dest="${1:-backups/derry-$(date -u +%Y%m%dT%H%M%SZ).dump}"
fi
test ! -e "$dest" || { echo 'Destination already exists' >&2; exit 1; }
temp="$dest.partial"
trap 'rm -f "$temp"' EXIT HUP INT TERM
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$temp"
test -s "$temp"
mv "$temp" "$dest"
sha256sum "$dest" > "$dest.sha256"
echo "Backup: $dest"
if [ "$auto" = 1 ]; then
  find backups/auto -type f -name 'derry-*.dump*' -mtime +13 -delete
  exit 0
fi
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
