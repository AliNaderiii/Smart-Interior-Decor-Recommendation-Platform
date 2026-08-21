#!/usr/bin/env bash
# One-shot logical PostgreSQL backup with retention (see docs/DISASTER_RECOVERY.md §2).
# Usage: POSTGRES_USER=decor POSTGRES_DB=decor ./scripts/backup.sh
# Schedule (host cron):
#   15 2 * * *  cd /opt/decor && ./scripts/backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
mkdir -p backups

: "${POSTGRES_USER:?set POSTGRES_USER}"
: "${POSTGRES_DB:=decor}"

STAMP=$(date -u +%Y%m%dT%H%MZ)
OUT="backups/decor-${STAMP}.dump"

# pg_dump through the postgres service container (same network, no host client).
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "$OUT"

# Retention: keep 14 daily dumps (adjust to your RPO).
find backups -name 'decor-*.dump' -mtime +14 -delete

echo "backup complete: $OUT ($(du -h "$OUT" | cut -f1))"
echo "next: copy off-site, e.g. aws s3 cp $OUT s3://decor-backups/ --recursive"
