#!/usr/bin/env bash
# Nightly snapshot of the SQLite database, with retention and a verified copy.
#
# egyptology.db holds the corpus ids *and every annotation an expert has written*.
# The corpus half is regenerable from data/processed/examples.csv; the annotations
# are not, and until this ran the database was as safe as one disk.
#
#   scripts/backup_db.sh [DB_PATH] [BACKUP_DIR]
#
# Both also come from the environment (DB_PATH, BACKUP_DIR), and both have
# defaults that match the server layout in DEPLOYMENT.md. Other knobs:
#
#   RETENTION_DAYS   how long to keep snapshots (default 30)
#   PYTHON           interpreter for the fallback path (default: the server venv)
#   OFFSITE_TARGET   where the day's file goes off this machine: an rclone remote
#                    (`b2:bucket/path`, the Backblaze setup in DEPLOYMENT.md) or an
#                    rsync destination — see below
#   RCLONE           rclone binary (default ~/bin/rclone)
#
# Exit codes: 0 all good; non-zero means no verified backup was taken today, and
# the systemd unit will show `failed`.

set -euo pipefail

DB_PATH="${1:-${DB_PATH:-/home/ledio/egyptology/egyptology.db}}"
BACKUP_DIR="${2:-${BACKUP_DIR:-/home/ledio/egyptology-backups}}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PYTHON="${PYTHON:-/home/ledio/venvs/egyptology/bin/python}"

# ---------------------------------------------------------------------------
# Off-machine copy. A backup on the same disk as the database survives a bad
# deploy or a wrong DELETE; it does not survive the disk. THIS IS THE HOOK the
# lead has to fill in: any rsync destination — `user@host:/path/`, a mounted
# share, an rclone remote wrapped in a small script. Empty means "on-box only",
# which is what it is today, and the script says so in its output rather than
# passing silently.
# ---------------------------------------------------------------------------
OFFSITE_TARGET="${OFFSITE_TARGET:-}"

STAMP="$(date +%Y-%m-%d)"
SNAPSHOT="${BACKUP_DIR}/egyptology-${STAMP}.db"
ARCHIVE="${SNAPSHOT}.gz"

if [[ ! -f "$DB_PATH" ]]; then
  echo "backup: no database at $DB_PATH" >&2
  exit 1
fi
mkdir -p "$BACKUP_DIR"

# `.backup` (the online backup API), never `cp`: a plain copy of a live SQLite
# file can catch a half-written page or miss a committed one still in the WAL,
# and you find out at restore time. Both branches below use the same API — the
# CLI's `.backup` command and Python's `Connection.backup` are the same call.
if command -v sqlite3 >/dev/null 2>&1; then
  echo "backup: snapshotting with the sqlite3 CLI"
  sqlite3 "$DB_PATH" ".backup '${SNAPSHOT}'"
else
  # Ubuntu 24.04 server as installed has no sqlite3 CLI and `ledio` has no sudo
  # to add one, so this is the path that actually runs there.
  echo "backup: no sqlite3 CLI; snapshotting with $PYTHON"
  "$PYTHON" - "$DB_PATH" "$SNAPSHOT" <<'PY'
import sqlite3
import sys

source_path, target_path = sys.argv[1], sys.argv[2]
# Read-only URI so a backup can never be what modifies the live database.
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
target = sqlite3.connect(target_path)
with target:
    source.backup(target)
target.close()
source.close()
PY
fi

# Verify the copy we just took, not the original: the point is to learn *now*
# that a snapshot is unreadable, rather than on the day it is needed.
echo "backup: checking integrity of ${SNAPSHOT}"
INTEGRITY="$(
  "$PYTHON" - "$SNAPSHOT" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print(connection.execute("PRAGMA integrity_check").fetchone()[0])
connection.close()
PY
)"
if [[ "$INTEGRITY" != "ok" ]]; then
  echo "backup: integrity_check said '${INTEGRITY}' — keeping the bad copy for inspection" >&2
  exit 2
fi
echo "backup: integrity_check ok"

rm -f "$ARCHIVE"
gzip -9 "$SNAPSHOT"
echo "backup: wrote ${ARCHIVE} ($(du -h "$ARCHIVE" | cut -f1))"

# Retention. -mtime +N is "older than N days", so 30 keeps a month of dailies.
# Scoped to this exact filename shape so nothing else in the directory is at risk.
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name 'egyptology-*.db.gz' -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)"
echo "backup: retention ${RETENTION_DAYS}d — removed ${DELETED} old snapshot(s), $(find "$BACKUP_DIR" -maxdepth 1 -name 'egyptology-*.db.gz' | wc -l) kept"

if [[ -n "$OFFSITE_TARGET" ]]; then
  echo "backup: copying to ${OFFSITE_TARGET}"
  # An rclone remote looks like `b2:bucket/path` — a bare name before the first
  # colon, no `@` and no `/`. Anything else (`user@host:/path/`, a mounted dir)
  # is an rsync destination. rclone is a static binary in ~/bin (no sudo needed).
  RCLONE="${RCLONE:-$HOME/bin/rclone}"
  if [[ "$OFFSITE_TARGET" =~ ^[A-Za-z0-9_-]+: ]]; then
    "$RCLONE" copyto "$ARCHIVE" "${OFFSITE_TARGET%/}/$(basename "$ARCHIVE")" --checksum
    # Same retention off-site as on-box; a remote that never expires files
    # would silently grow forever.
    "$RCLONE" delete "${OFFSITE_TARGET%/}" --min-age "${RETENTION_DAYS}d" --include 'egyptology-*.db.gz'
    "$RCLONE" ls "${OFFSITE_TARGET%/}" | tail -n 3
  else
    rsync -a --partial "$ARCHIVE" "$OFFSITE_TARGET"
  fi
  echo "backup: offsite copy done"
else
  echo "backup: OFFSITE_TARGET is empty — this snapshot exists only on this disk"
fi
