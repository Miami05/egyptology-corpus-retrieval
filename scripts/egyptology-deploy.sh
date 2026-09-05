#!/usr/bin/env bash
# Update the Egyptology service from GitHub. Touches only /home/ledio.
#
# Canonical copy. The operational script the server runs lives at
# /home/ledio/egyptology-deploy.sh; this file is the source of truth for it.
# Install with:
#   scp scripts/egyptology-deploy.sh ledio@vela-optiplex-3070:egyptology-deploy.sh
# See DEPLOYMENT.md.
set -euo pipefail

REPO=/home/ledio/egyptology
VENV=/home/ledio/venvs/egyptology
CORPUS_CSV=data/processed/examples.csv

cd "$REPO"

BEFORE="$(git rev-parse HEAD)"
git pull --ff-only
AFTER="$(git rev-parse HEAD)"

if [[ "$BEFORE" == "$AFTER" ]]; then
  echo "deploy: already at $(git log -1 --format=%h) — nothing pulled"
else
  echo "deploy: $(git rev-parse --short "$BEFORE") -> $(git rev-parse --short "$AFTER")"
fi

"$VENV"/bin/pip install -q -r requirements.txt

# Operational copies of the repo scripts, kept outside the clone so a systemd
# unit never points into a tree that a failed or half-finished pull is rewriting.
# The repo is the canonical version; this loop is what keeps the two in step.
# Skipped rather than fatal when a script is not in this commit: these were first
# installed by hand, and a deploy of an older commit must not be the thing that
# takes the backup timer or the warm-up down.
for script in backup_db.sh warm_streamlit.py; do
  if [[ -f "$REPO/scripts/$script" ]]; then
    install -m 755 "$REPO/scripts/$script" "/home/ledio/bin/$script"
  else
    echo "deploy: scripts/$script not in this commit — keeping /home/ledio/bin/$script"
  fi
done

# The corpus. New CSV rows get database ids at boot only on a *fresh* database —
# `ensure_corpus_ready` seeds in bulk and then never re-imports, which is the
# guard that stops a deploy overwriting live annotations. On an existing database
# the new rows therefore stay unlinked, and a reviewer who opens one is told it is
# "not linked to the project database" and cannot save. `sync_new_examples` (what
# import_examples.py runs by default) inserts only the missing rows and touches no
# existing one, so it is safe to run on every corpus change and cheap when there
# is nothing to do.
#
# Before the restart, not after: the service should come up already able to save
# annotations on every row it shows.
#
# `cd "$REPO"` above matters twice here — import_examples.py reads the CSV by a
# relative path, and DATABASE_URL defaults to `sqlite:///egyptology.db`, also
# relative. Run from anywhere else it would quietly build a second database.
if [[ "$BEFORE" != "$AFTER" ]] && git diff --name-only "$BEFORE" "$AFTER" | grep -qx "$CORPUS_CSV"; then
  echo "deploy: $CORPUS_CSV changed — syncing new rows into the database"
  # The same environment the service reads, so the import cannot land in a
  # different database from the one the app will open. `set -a` exports every
  # assignment in the file; the unit's own Environment= lines are repeated here
  # because an EnvironmentFile cannot carry them.
  (
    set -a
    if [[ -f /home/ledio/egyptology.env ]]; then
      # shellcheck disable=SC1091
      source /home/ledio/egyptology.env
    fi
    PRIVATE_DATA_DIR=/home/ledio/egyptology-private
    ANNOTATIONS_DURABLE=1
    set +a
    # A non-writing pass first, so the log distinguishes "nothing to insert" from
    # "N inserted" before the real sync runs. It reports what the default sync
    # would insert AND what --refresh-existing would change, and writes nothing.
    echo "deploy: dry-run — what the sync would change:"
    "$VENV"/bin/python scripts/import_examples.py --dry-run
    echo "deploy: applying the sync:"
    "$VENV"/bin/python scripts/import_examples.py
  )
else
  echo "deploy: $CORPUS_CSV unchanged — no corpus import needed"
fi

systemctl --user restart egyptology.service
for i in $(seq 1 30); do
  sleep 2
  if curl -fsS -o /dev/null http://127.0.0.1:8502/_stcore/health; then
    echo "healthy on 8502 after ~$((i*2))s at $(git log -1 --format=%h)"
    # The unit's ExecStartPost warms the stage resource sets before this point,
    # so a `restart` that returns has already paid the ~60 s build. If that step
    # was skipped or failed, `journalctl --user -u egyptology.service` says so and
    # the first visitor's paste pays the build instead — the service is still up.
    exit 0
  fi
done

echo "deploy: service did not answer on 8502 after ~60s — last 30 journal lines:" >&2
journalctl --user -u egyptology.service -n 30 --no-pager >&2 || true
exit 1
