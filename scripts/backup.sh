#!/usr/bin/env sh
# Бэкап PostgreSQL из docker compose. Запуск из корня репозитория (можно по cron):
#   ./scripts/backup.sh            → backups/music-YYYYmmdd-HHMMSS.dump, хранит последние 14
# Восстановление — docs/operations.md.
set -eu
cd "$(dirname "$0")/.."
KEEP="${KEEP:-14}"
mkdir -p backups
ts=$(date +%Y%m%d-%H%M%S)
out="backups/music-$ts.dump"
docker compose exec -T db pg_dump -U music -d music --format=custom --no-owner > "$out.tmp"
mv "$out.tmp" "$out"
echo "backup: $out ($(du -h "$out" | cut -f1))"
# Ротация: удалить всё старше последних $KEEP файлов.
ls -1t backups/music-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r f; do rm -f -- "$f"; done
