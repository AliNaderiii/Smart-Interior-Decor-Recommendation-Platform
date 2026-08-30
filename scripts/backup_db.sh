#!/usr/bin/env bash
# ==============================================================================
# Smart Interior Decor Recommendation Platform — Database Backup Script (T-3.4)
# ==============================================================================
# Performs logical pg_dump in PostgreSQL Custom Format (-Fc) with integrity check
# and retention-based pruning.
#
# Usage:
#   ./scripts/backup_db.sh [backup_dir] [retention_days]
#
# Environment variables supported:
#   DATABASE_URL or (PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSWORD)
#   BACKUP_RETENTION_DAYS (default: 14)
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${1:-backups}"
RETENTION_DAYS="${2:-${BACKUP_RETENTION_DAYS:-14}}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/smartdecor_db_${TIMESTAMP}.dump"
LOG_FILE="${BACKUP_DIR}/backup.log"

echo "[$(date -u)] Starting database backup to ${BACKUP_FILE}..." | tee -a "$LOG_FILE"

# Determine execution mode: DATABASE_URL, local pg_dump, or docker compose
if command -v pg_dump >/dev/null 2>&1; then
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump -d "$DATABASE_URL" -Fc -Z 6 -f "$BACKUP_FILE"
  else
    PGUSER="${PGUSER:-decor}"
    PGDATABASE="${PGDATABASE:-decor}"
    PGHOST="${PGHOST:-localhost}"
    PGPORT="${PGPORT:-5432}"
    pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -Z 6 -f "$BACKUP_FILE"
  fi
elif command -v docker >/dev/null 2>&1 && docker compose ps postgres >/dev/null 2>&1; then
  PGUSER="${POSTGRES_USER:-decor}"
  PGDATABASE="${POSTGRES_DB:-decor}"
  docker compose exec -T postgres pg_dump -U "$PGUSER" -d "$PGDATABASE" -Fc -Z 6 > "$BACKUP_FILE"
else
  echo "[ERROR] Neither pg_dump nor active docker compose postgres found." | tee -a "$LOG_FILE" >&2
  exit 1
fi

# Verify backup integrity
if [ ! -s "$BACKUP_FILE" ]; then
  echo "[ERROR] Backup file is empty or was not created: ${BACKUP_FILE}" | tee -a "$LOG_FILE" >&2
  exit 2
fi

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | awk '{print $1}')
echo "[$(date -u)] Backup created successfully: ${BACKUP_FILE} (${BACKUP_SIZE})" | tee -a "$LOG_FILE"

# Prune old backups older than RETENTION_DAYS
echo "[$(date -u)] Pruning backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..." | tee -a "$LOG_FILE"
find "$BACKUP_DIR" -maxdepth 1 -name "smartdecor_db_*.dump" -type f -mtime +"$RETENTION_DAYS" -exec rm -f {} +

echo "[$(date -u)] Backup and pruning routine finished." | tee -a "$LOG_FILE"
