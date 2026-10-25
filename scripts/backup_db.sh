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
# defaults that match the server layout in DEPLOYMENT.md. When DB_PATH is not given
# and DATABASE_URL is a `sqlite:///...` URL (the unit reads it from egyptology.env,
# the same place the app does), the file named there is backed up, so the app and
# the backup cannot disagree about where the database is. Other knobs:
#
#   RETENTION_DAYS   how long to keep daily snapshots (default 30). The first
#                    snapshot of each month is also kept for ever in monthly/
#   PYTHON           interpreter for the fallback path (default: the server venv)
#   OFFSITE_TARGET   where the day's file goes off this machine: an rclone remote
#                    (`b2:bucket/path`, the Backblaze setup in DEPLOYMENT.md) or an
#                    rsync destination — see below
#   RCLONE           rclone binary (default ~/bin/rclone)
#   OFFSITE_PRUNE    0 = never delete old files off-site from here (use this with
#                    an application key that has no delete right, and let the
#                    bucket's lifecycle rule expire the dailies). Default 1
#   HEALTHCHECK_URL  a healthchecks.io-style ping URL: pinged on success, and at
#                    `<url>/fail` on any failure, so a missed night raises an alert
#   ALLOW_ANNOTATION_DROP=1
#                    accept a snapshot with fewer annotations than the previous
#                    one (a deliberate deletion); without it the run fails
#   BACKUP_STAMP     the date in the file names (default today, YYYY-MM-DD); tests
#
# Exit codes: 0 all good; 1 no database; 2 the copy is corrupt; 3 the copy is
# readable but holds fewer annotations than the previous snapshot (it is kept as
# egyptology-<date>.db.gz.suspect, and nothing older is touched, not on this
# machine and not off-site). Any non-zero exit means no good backup was taken
# today, and the systemd unit will show `failed`.

set -euo pipefail

DB_PATH="${1:-${DB_PATH:-}}"
if [[ -z "$DB_PATH" && "${DATABASE_URL:-}" == sqlite:///* ]]; then
  DB_PATH="${DATABASE_URL#sqlite:///}"
  DB_PATH="${DB_PATH%%\?*}"
  if [[ "$DB_PATH" == :* ]]; then
    DB_PATH=""                     # sqlite:///:memory: has no file to back up
  elif [[ "$DB_PATH" != /* ]]; then
    # The app resolves a relative path against the clone (app/core/config.py).
    DB_PATH="${REPO_DIR:-/home/ledio/egyptology}/${DB_PATH}"
  fi
fi
DB_PATH="${DB_PATH:-/home/ledio/egyptology/egyptology.db}"
BACKUP_DIR="${2:-${BACKUP_DIR:-/home/ledio/egyptology-backups}}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PYTHON="${PYTHON:-/home/ledio/venvs/egyptology/bin/python}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"
ALLOW_ANNOTATION_DROP="${ALLOW_ANNOTATION_DROP:-0}"
OFFSITE_PRUNE="${OFFSITE_PRUNE:-1}"

# ---------------------------------------------------------------------------
# Off-machine copy. A backup on the same disk as the database survives a bad
# deploy or a wrong DELETE; it does not survive the disk. THIS IS THE HOOK the
# lead has to fill in: any rsync destination — `user@host:/path/`, a mounted
# share, an rclone remote wrapped in a small script. Empty means "on-box only",
# which is what it is today, and the script says so in its output rather than
# passing silently.
# ---------------------------------------------------------------------------
OFFSITE_TARGET="${OFFSITE_TARGET:-}"

STAMP="${BACKUP_STAMP:-$(date +%Y-%m-%d)}"
MONTH="${STAMP%-*}"                # YYYY-MM
SNAPSHOT="${BACKUP_DIR}/egyptology-${STAMP}.db"
ARCHIVE="${SNAPSHOT}.gz"
MONTHLY_DIR="${BACKUP_DIR}/monthly"
MONTHLY_FILE="${MONTHLY_DIR}/egyptology-${MONTH}.db.gz"
WORK_DIR=""

# Runs on every exit: cleans the scratch folder and reports the outcome to the
# heartbeat URL. A failure to ping is only a warning; it never changes the exit
# code, and it cannot turn a good backup into a failed one.
finish() {
  local rc=$?
  trap - EXIT
  if [[ -n "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
  fi
  if [[ -n "$HEALTHCHECK_URL" ]]; then
    local url="${HEALTHCHECK_URL%/}"
    if [[ $rc -ne 0 ]]; then
      url="${url}/fail"
    fi
    if ! curl -fsS -m 10 --retry 2 -o /dev/null "$url" >/dev/null 2>&1; then
      echo "backup: warning — could not reach the health check URL" >&2
    fi
  fi
  exit "$rc"
}
trap finish EXIT

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

# What is in the archive? integrity_check proves the file is a sound database,
# not that the annotations are still in it: a bad migration or a wrong DELETE
# gives a perfectly healthy file with an empty annotations table, and retention
# would then age the last good copy out. So count rows in the ARCHIVE (what a
# restore would use), and compare with the newest earlier snapshot.
WORK_DIR="$(mktemp -d)"

# $1 = a .db.gz file; prints "<examples> <annotations>". A missing table counts as 0.
count_archive() {
  gzip -t "$1" || return 1
  gzip -dc "$1" > "${WORK_DIR}/count.db" || return 1
  "$PYTHON" - "${WORK_DIR}/count.db" <<'PY' || return 1
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)


def count(table):
    found = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if found is None:
        return 0
    return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


print(count("examples"), count("annotations"))
connection.close()
PY
  rm -f "${WORK_DIR}/count.db"
}

if ! TODAY_COUNTS="$(count_archive "$ARCHIVE")"; then
  echo "backup: ${ARCHIVE} failed gzip/row-count verification — keeping it for inspection" >&2
  exit 2
fi
read -r EXAMPLES ANNOTATIONS <<<"$TODAY_COUNTS"
echo "backup: archive holds examples=${EXAMPLES} annotations=${ANNOTATIONS}"

PREVIOUS="$(find "$BACKUP_DIR" -maxdepth 1 -name 'egyptology-*.db.gz' ! -name "egyptology-${STAMP}.db.gz" | sort | tail -n 1)"
if [[ -z "$PREVIOUS" ]]; then
  echo "backup: no earlier snapshot to compare with — skipping the row-count comparison"
elif ! PREVIOUS_COUNTS="$(count_archive "$PREVIOUS")"; then
  echo "backup: warning — could not read ${PREVIOUS}; skipping the row-count comparison" >&2
else
  read -r PREV_EXAMPLES PREV_ANNOTATIONS <<<"$PREVIOUS_COUNTS"
  echo "backup: previous $(basename "$PREVIOUS") holds examples=${PREV_EXAMPLES} annotations=${PREV_ANNOTATIONS}"
  SUSPECT=""
  if [[ "$ANNOTATIONS" -lt "$PREV_ANNOTATIONS" ]]; then
    SUSPECT="annotations fell from ${PREV_ANNOTATIONS} to ${ANNOTATIONS}"
  elif [[ "$EXAMPLES" -eq 0 && "$PREV_EXAMPLES" -gt 0 ]]; then
    SUSPECT="examples fell from ${PREV_EXAMPLES} to 0"
  elif [[ "$EXAMPLES" -lt "$PREV_EXAMPLES" ]]; then
    # A deliberate corpus shrink is legitimate, so this only warns.
    echo "backup: warning — examples fell from ${PREV_EXAMPLES} to ${EXAMPLES}" >&2
  fi
  if [[ -n "$SUSPECT" ]]; then
    if [[ "$ALLOW_ANNOTATION_DROP" == "1" ]]; then
      echo "backup: ${SUSPECT} — accepted because ALLOW_ANNOTATION_DROP=1" >&2
    else
      # A name the retention glob does not match, so it is never aged out, and the
      # older good snapshots stay untouched: no retention, monthly copy or off-site
      # copy happens after this point.
      mv -f "$ARCHIVE" "${ARCHIVE}.suspect"
      echo "backup: ${SUSPECT} compared with $(basename "$PREVIOUS")." >&2
      echo "backup: kept today's copy as ${ARCHIVE}.suspect and changed nothing else." >&2
      echo "backup: if this was deliberate, run again with ALLOW_ANNOTATION_DROP=1." >&2
      exit 3
    fi
  fi
fi

# The long tail: the first good snapshot of every month, kept for ever. Daily
# retention only looks at the top level of BACKUP_DIR (-maxdepth 1), never here.
if [[ ! -f "$MONTHLY_FILE" ]]; then
  mkdir -p "$MONTHLY_DIR"
  cp "$ARCHIVE" "$MONTHLY_FILE"
  echo "backup: first snapshot of ${MONTH}, kept for good as ${MONTHLY_FILE}"
fi

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
    # The monthly copy goes up every run, not only on the night it is made: a
    # failed upload then heals itself, and --checksum makes an existing one a no-op.
    "$RCLONE" copyto "$MONTHLY_FILE" "${OFFSITE_TARGET%/}/monthly/$(basename "$MONTHLY_FILE")" --checksum
    if [[ "$OFFSITE_PRUNE" == "1" ]]; then
      # Same retention off-site as on-box; a remote that never expires files
      # would silently grow forever. --max-depth 1 keeps this to the daily files:
      # without it the include pattern would also match monthly/ and delete the
      # long tail. Not fatal: a key without delete rights is the safer setup, and
      # then the bucket's lifecycle rule does the expiring.
      "$RCLONE" delete "${OFFSITE_TARGET%/}" --max-depth 1 --min-age "${RETENTION_DAYS}d" --include 'egyptology-*.db.gz' \
        || echo "backup: warning — off-site prune failed (a key without delete rights is fine; rely on the B2 lifecycle rule)" >&2
    fi
    "$RCLONE" ls "${OFFSITE_TARGET%/}" | tail -n 3
  else
    rsync -a --partial "$ARCHIVE" "$OFFSITE_TARGET"
    # -R with the `/./` marker creates monthly/ at the destination.
    rsync -aR --partial "${BACKUP_DIR}/./monthly/$(basename "$MONTHLY_FILE")" "$OFFSITE_TARGET"
  fi
  echo "backup: offsite copy done"
else
  echo "backup: OFFSITE_TARGET is empty — this snapshot exists only on this disk"
fi
