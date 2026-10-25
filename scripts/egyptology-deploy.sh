#!/usr/bin/env bash
# Update the Egyptology service from GitHub. Touches only /home/ledio.
#
# Canonical copy. The operational script the server runs lives at
# /home/ledio/egyptology-deploy.sh; this file is the source of truth for it. A
# successful deploy refreshes that copy from the repo (the new copy takes effect
# on the NEXT run, never mid-run). The very first time, and any time the old copy
# is too old to know this, install it by hand:
#   scp scripts/egyptology-deploy.sh ledio@vela-optiplex-3070:egyptology-deploy.sh
# See DEPLOYMENT.md.
#
# Order, and why (audit A12, A40, A41, A46, A11):
#   1. refuse to run on a dirty clone or a non-fast-forward upstream, touching nothing
#   2. install the TARGET commit's requirements BEFORE the code changes: a failing
#      pip then leaves the tree and the running service exactly as they were
#   3. stop the service right before the tree changes, so no process ever sees files
#      change under it (STOP_BEFORE_UPDATE=0 turns this off), then fast-forward
#   4. helpers, unit files, corpus sync, restart, and a real check that the app
#      renders a result; any failure rolls the tree and venv back to the old commit
#
# Knobs (environment): INSTALL_UNITS=1 copies deploy/systemd/* into the user unit
# folder (default: only warn when they differ), STOP_BEFORE_UPDATE=0|1 (default 1).
# Tests point DEPLOY_HOME, HEALTH_URL, HEALTH_TRIES and HEALTH_INTERVAL elsewhere.
set -euo pipefail

HOME_DIR="${DEPLOY_HOME:-/home/ledio}"
REPO="$HOME_DIR/egyptology"
VENV="$HOME_DIR/venvs/egyptology"
BIN_DIR="$HOME_DIR/bin"
ENV_FILE="$HOME_DIR/egyptology.env"
LAST_GOOD="$HOME_DIR/egyptology-last-good"
UNIT_DIR="$HOME_DIR/.config/systemd/user"
DEPLOY_COPY="$HOME_DIR/egyptology-deploy.sh"
CORPUS_CSV=data/processed/examples.csv
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8502/_stcore/health}"
APP_URL="${HEALTH_URL%/_stcore/health}"
HEALTH_TRIES="${HEALTH_TRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"
INSTALL_UNITS="${INSTALL_UNITS:-0}"
STOP_BEFORE_UPDATE="${STOP_BEFORE_UPDATE:-1}"

# The paste the deploy check runs (expert paste query 1, the same one the unit's
# warm-up uses). It must render at least one `suggestion-card`: that string is a CSS
# class in app/ui/whyptology_app.py, so renaming the class means changing it here too,
# or every deploy will be rolled back as "never rendered a result".
PASTE_001="𓆓𓂧 𓆑𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏼 𓂋𓍿 𓀀 𓏼𓎟𓏏"
EXPECT_TEXT="suggestion-card"

# Read KEY=value lines into the environment WITHOUT executing them. systemd takes
# the file literally (a REVIEWER_KEY passphrase may hold spaces, `$` or `&`), and a
# shell `source` would run or mangle those.
load_env_file() {
  local file="$1" line key value
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    if [[ -z "$line" || "$line" == \#* || "$line" != *=* ]]; then
      continue
    fi
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 ]]; then
      case "$value" in
        \"*\") value="${value:1:${#value}-2}" ;;
        \'*\') value="${value:1:${#value}-2}" ;;
      esac
    fi
    export "$key=$value"
  done < "$file"
}

# True (0) when the corpus CSV differs between two commits, or when that cannot be
# told. `git diff --quiet` answers for that one path: 0 same, 1 different, anything
# else is an error and counts as "changed", because the sync is cheap and idempotent.
# (The old `git diff --name-only | grep -qx` form lost the race: grep exits at the
# first match, git gets SIGPIPE, and under pipefail the `if` read that as "no match",
# so a deploy with a big diff silently skipped the import.)
corpus_changed() {
  local rc=0
  git -C "$REPO" diff --quiet "$1" "$2" -- "$CORPUS_CSV" || rc=$?
  [[ $rc -ne 0 ]]
}

wait_healthy() {
  local i
  for i in $(seq 1 "$HEALTH_TRIES"); do
    sleep "$HEALTH_INTERVAL"
    if curl -fsS -o /dev/null "$HEALTH_URL"; then
      echo "healthy on ${APP_URL##*:} after ~$((i * HEALTH_INTERVAL))s at $(git -C "$REPO" log -1 --format=%h)"
      return 0
    fi
  done
  echo "deploy: service did not answer after ~$((HEALTH_TRIES * HEALTH_INTERVAL))s — last 30 journal lines:" >&2
  journalctl --user -u egyptology.service -n 30 --no-pager >&2 || true
  return 1
}

# "Healthy" only proves Streamlit answers; a crashing app answers too. This opens a
# real session, runs the paste, and fails unless a result card was drawn and no
# exception element was shown (scripts/warm_streamlit.py, audit A11).
verify_app() {
  wait_healthy || return 1
  "$VENV/bin/python" "$REPO/scripts/warm_streamlit.py" --url "$APP_URL" --timeout 180 \
    --expect-text "$EXPECT_TEXT" --query "$PASTE_001"
}

# Operational copies of the repo scripts, kept outside the clone so a systemd unit never
# points into a tree that a failed or half-finished update is rewriting. The repo is the
# canonical version; this loop is what keeps the two in step.
# Skipped rather than fatal when a script is not in this commit: these were first
# installed by hand, and a deploy of an older commit must not be the thing that
# takes the backup timer or the warm-up down.
install_helpers() {
  local script
  mkdir -p "$BIN_DIR" || return 1
  for script in backup_db.sh warm_streamlit.py; do
    if [[ -f "$REPO/scripts/$script" ]]; then
      install -m 755 "$REPO/scripts/$script" "$BIN_DIR/$script" || return 1
    else
      echo "deploy: scripts/$script not in this commit — keeping $BIN_DIR/$script"
    fi
  done
}

# The unit files are versioned in deploy/systemd/. They are installed only when asked
# (INSTALL_UNITS=1): they were reconstructed from prose, so the first install should
# follow a diff against the live ones, not a blind overwrite.
install_units() {
  local src="$REPO/deploy/systemd" file name installed=0 differs=0
  if [[ ! -d "$src" ]]; then
    echo "deploy: no deploy/systemd in this commit — leaving the installed units alone"
    return 0
  fi
  for file in "$src"/*.service "$src"/*.timer; do
    [[ -f "$file" ]] || continue
    name="$(basename "$file")"
    if cmp -s "$file" "$UNIT_DIR/$name"; then
      continue
    fi
    if [[ "$INSTALL_UNITS" == "1" ]]; then
      mkdir -p "$UNIT_DIR" || return 1
      install -m 644 "$file" "$UNIT_DIR/$name" || return 1
      echo "deploy: installed unit $name"
      installed=1
    else
      differs=1
    fi
  done
  if [[ $installed -eq 1 ]]; then
    systemctl --user daemon-reload || return 1
  fi
  if [[ $differs -eq 1 ]]; then
    echo "deploy: unit files differ from the installed ones; review, then run with INSTALL_UNITS=1"
  fi
  return 0
}

# The corpus. New CSV rows get database ids at boot only on a *fresh* database —
# `ensure_corpus_ready` seeds in bulk and then never re-imports, which is the
# guard that stops a deploy overwriting live annotations. On an existing database
# the new rows therefore stay unlinked, and a reviewer who opens one is told it is
# "not linked to the project database" and cannot save. `sync_new_examples` (what
# import_examples.py runs by default) inserts only the missing rows and touches no
# existing one, so it is safe to run on every corpus change and cheap when there is
# nothing to do. Before the restart, not after: the service should come up already
# able to save annotations on every row it shows.
#
# Runs with the environment the service reads (egyptology.env, already loaded by
# load_env_file), so the import cannot land in a different database from the one the
# app will open; the unit's own Environment= lines are repeated as defaults because
# an EnvironmentFile cannot carry them. The cwd is the clone, as import_examples.py
# reads the CSV by a relative path.
import_corpus() {
  (
    export PRIVATE_DATA_DIR="${PRIVATE_DATA_DIR:-$HOME_DIR/egyptology-private}"
    export ANNOTATIONS_DURABLE="${ANNOTATIONS_DURABLE:-1}"
    cd "$REPO" || exit 1
    # A non-writing pass first, so the log distinguishes "nothing to insert" from
    # "N inserted" before the real sync runs. It reports what the default sync
    # would insert AND what --refresh-existing would change, and writes nothing.
    echo "deploy: dry-run — what the sync would change:"
    "$VENV/bin/python" scripts/import_examples.py --dry-run || exit 1
    echo "deploy: applying the sync:"
    "$VENV/bin/python" scripts/import_examples.py || exit 1
  )
}

# Everything that changes the live tree or the service. Explicit `|| return 1` on every
# step: `set -e` is switched off inside a function called from `if !`, so it cannot be
# relied on here.
apply_new_tree() {
  if [[ "$BEFORE" != "$AFTER" ]]; then
    if [[ "$STOP_BEFORE_UPDATE" == "1" ]]; then
      echo "deploy: stopping the service before the files change"
      systemctl --user stop egyptology.service || return 1
      STOPPED_AT=$SECONDS
    fi
    git -C "$REPO" merge --ff-only "$AFTER" || return 1
  fi
  install_helpers || return 1
  install_units || return 1
  if [[ "$BEFORE" != "$AFTER" ]] && corpus_changed "$BEFORE" "$AFTER"; then
    echo "deploy: $CORPUS_CSV changed — syncing new rows into the database"
    import_corpus || return 1
  else
    echo "deploy: $CORPUS_CSV unchanged — no corpus import needed"
  fi
  systemctl --user restart egyptology.service || return 1
  verify_app || return 1
  if [[ -n "${STOPPED_AT:-}" ]]; then
    echo "deploy: the service was down for about $((SECONDS - STOPPED_AT))s"
  fi
}

# Back to the commit that was running, with the venv matching it, and a check that it
# serves. Never touches ignored files, so the database (*.db) is safe.
rollback() {
  local target="$1"
  echo "deploy: FAILED — rolling back to $(git -C "$REPO" rev-parse --short "$target")" >&2
  if git -C "$REPO" reset --hard "$target" \
    && "$VENV/bin/pip" install -q -r "$REPO/requirements.txt" \
    && install_helpers \
    && install_units \
    && systemctl --user restart egyptology.service \
    && wait_healthy; then
    echo "deploy: ROLLED BACK to $(git -C "$REPO" rev-parse --short "$target")" >&2
    return 0
  fi
  {
    echo "deploy: MANUAL: the rollback itself failed. On the box:"
    echo "  git -C $REPO reset --hard \$(cat $LAST_GOOD)"
    echo "  $VENV/bin/pip install -r $REPO/requirements.txt"
    echo "  systemctl --user restart egyptology.service"
  } >&2
  return 1
}

main() {
  cd "$REPO"
  load_env_file "$ENV_FILE"

  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "deploy: the clone has modified tracked files — refusing to deploy over them:" >&2
    git status --porcelain --untracked-files=no >&2
    exit 1
  fi
  case "${DATABASE_URL:-}" in
    sqlite:////*egyptology-data/*) ;;
    *)
      echo "deploy: warning — DATABASE_URL is not under $HOME_DIR/egyptology-data, so the database" >&2
      echo "deploy:   (the only irreplaceable file) still lives inside the clone; see DEPLOYMENT.md" >&2
      ;;
  esac

  BEFORE="$(git rev-parse HEAD)"
  git fetch -q origin
  AFTER="$(git rev-parse '@{u}')"
  if ! git merge-base --is-ancestor "$BEFORE" "$AFTER"; then
    echo "deploy: $(git rev-parse --short "$AFTER") upstream is not a fast-forward of $(git rev-parse --short "$BEFORE") — nothing touched" >&2
    exit 1
  fi
  if [[ "$BEFORE" == "$AFTER" ]]; then
    echo "deploy: already at $(git log -1 --format=%h) — nothing to pull"
  else
    echo "deploy: $(git rev-parse --short "$BEFORE") -> $(git rev-parse --short "$AFTER")"
    # The merge below smudges the LFS corpus (~69 MB); fetch it while the service is
    # still up so the download is not part of the downtime. Best effort.
    if corpus_changed "$BEFORE" "$AFTER" && git lfs version >/dev/null 2>&1; then
      git lfs fetch origin "$AFTER" >/dev/null || echo "deploy: LFS prefetch failed — the merge will download the corpus instead" >&2
    fi
  fi

  # Dependencies first, from the TARGET commit, while the old tree is still in place.
  # If pip fails, neither the tree nor the running service has been touched.
  SCRATCH="$(mktemp -d)"
  trap 'rm -rf "$SCRATCH"' EXIT
  git show "$AFTER:requirements.txt" > "$SCRATCH/requirements.txt"
  if ! "$VENV/bin/pip" install -q -r "$SCRATCH/requirements.txt"; then
    echo "deploy: pip failed — the tree and the running service are untouched; restoring the venv" >&2
    "$VENV/bin/pip" install -q -r "$REPO/requirements.txt" \
      || echo "deploy: MANUAL: could not restore the venv; run $VENV/bin/pip install -r $REPO/requirements.txt" >&2
    exit 1
  fi

  if ! apply_new_tree; then
    if rollback "$BEFORE"; then
      exit 1
    fi
    exit 2
  fi

  echo "$AFTER" > "$LAST_GOOD"
  # Refresh the operational copy of this script from the repo. Never in place: the
  # running script may be that very file, so write beside it and rename over it.
  if [[ -f "$REPO/scripts/egyptology-deploy.sh" ]]; then
    install -m 755 "$REPO/scripts/egyptology-deploy.sh" "$DEPLOY_COPY.new" \
      && mv -f "$DEPLOY_COPY.new" "$DEPLOY_COPY" \
      || echo "deploy: warning — could not refresh $DEPLOY_COPY" >&2
  fi
  echo "deploy: done, serving $(git log -1 --format=%h), recorded in $LAST_GOOD"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
