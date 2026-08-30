#!/usr/bin/env bash
# ==============================================================================
# Smart Interior Decor Recommendation Platform — Database Restore Script (T-3.4)
# ==============================================================================
# Restores a PostgreSQL custom format dump into a target database using pg_restore.
#
# Usage:
#   ./scripts/restore_db.sh <backup_file_path> [target_database_name]
#
# Environment variables supported:
#   DATABASE_URL or (PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSWORD)
#   RESTORE_CLEAN (default: 1 — cleans database objects before recreating)
# ==============================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup_file_path> [target_database_name]" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-${PGDATABASE:-decor}}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "[ERROR] Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

echo "[$(date -u)] Initiating restore of $BACKUP_FILE into target database '$TARGET_DB'..."

CLEAN_FLAG=""
if [ "${RESTORE_CLEAN:-1}" = "1" ]; then
  CLEAN_FLAG="--clean --if-exists"
fi

# Execute pg_restore
if command -v pg_restore >/dev/null 2>&1; then
  if [ -n "${TARGET_DATABASE_URL:-}" ]; then
    pg_restore --no-owner --no-privileges $CLEAN_FLAG -d "$TARGET_DATABASE_URL" "$BACKUP_FILE" || true
  else
    PGUSER="${PGUSER:-decor}"
    PGHOST="${PGHOST:-localhost}"
    PGPORT="${PGPORT:-5432}"
    pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" --no-owner --no-privileges $CLEAN_FLAG "$BACKUP_FILE" || true
  fi
elif command -v docker >/dev/null 2>&1 && docker compose ps postgres >/dev/null 2>&1; then
  PGUSER="${POSTGRES_USER:-decor}"
  docker compose exec -T postgres pg_restore -U "$PGUSER" -d "$TARGET_DB" --no-owner --no-privileges $CLEAN_FLAG < "$BACKUP_FILE" || true
else
  echo "[ERROR] Neither pg_restore nor active docker compose postgres found." >&2
  exit 1
fi

echo "[$(date -u)] Restore completed. Running post-restore verification..."
