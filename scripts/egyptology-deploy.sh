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
# Order, and why (audit A12, A40, A41, A45, A46, A11):
#   1. refuse to run on a dirty clone or a non-fast-forward upstream, touching nothing
#   2. record what is running NOW (commit, venv) in ~/egyptology-last-good*, before
#      anything changes, so a manual recovery always has the right target
#   3. build the TARGET commit's dependencies into a NEW release venv beside the live
#      one (from requirements.lock when the commit has one). The live venv is never
#      installed into, so a failing pip leaves the tree, the venv and the service as
#      they were. A commit whose dependencies did not change reuses the live venv
#   4. fast-forward the tree (STOP_BEFORE_UPDATE=1 stops the service first; default 0,
#      no public downtime: the unit's STREAMLIT_SERVER_FILE_WATCHER_TYPE=none keeps the
#      running process from picking up the new files), helpers, unit files, corpus sync
#      with the NEW venv, then stop, point ~/venvs/egyptology at the new venv, start, and
#      a real check that the app renders a result
#   5. any failure in 4: stop, restore the units, the tree and the venv link, start, and
#      re-run the same check; the old release venv is kept for exactly this
#
# Knobs (environment): INSTALL_UNITS=1 copies deploy/systemd/* into the user unit
# folder (default: only warn when they differ), STOP_BEFORE_UPDATE=0|1 (default 0),
# BASE_PYTHON (the interpreter that creates release venvs; default the live venv's).
# Tests point DEPLOY_HOME, HEALTH_URL, HEALTH_TRIES and HEALTH_INTERVAL elsewhere.
set -euo pipefail

HOME_DIR="${DEPLOY_HOME:-/home/ledio}"
REPO="$HOME_DIR/egyptology"
# What the unit runs. Since the release-venv deploy this is a symlink to one directory in
# $RELEASES; on a box that still has the original real directory, the first deploy that
# switches venvs moves it into $RELEASES (while the service is stopped).
VENV="$HOME_DIR/venvs/egyptology"
RELEASES="$HOME_DIR/venvs/egyptology-releases"
# Written into each release venv once its install succeeded: the dependency spec it was
# built from, so a deploy with the same spec reuses it instead of building another.
SPEC_MARKER=".egyptology-deps"
BIN_DIR="$HOME_DIR/bin"
ENV_FILE="$HOME_DIR/egyptology.env"
# What was running when the latest deploy started, written before anything changes:
# the commit, the venv directory, and the unit files the deploy replaced or added.
LAST_GOOD="$HOME_DIR/egyptology-last-good"
LAST_GOOD_VENV="$HOME_DIR/egyptology-last-good-venv"
LAST_GOOD_UNITS="$HOME_DIR/egyptology-last-good-units"
UNIT_DIR="$HOME_DIR/.config/systemd/user"
DEPLOY_COPY="$HOME_DIR/egyptology-deploy.sh"
CORPUS_CSV=data/processed/examples.csv
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8502/_stcore/health}"
APP_URL="${HEALTH_URL%/_stcore/health}"
HEALTH_TRIES="${HEALTH_TRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"
INSTALL_UNITS="${INSTALL_UNITS:-0}"
STOP_BEFORE_UPDATE="${STOP_BEFORE_UPDATE:-0}"
BASE_PYTHON="${BASE_PYTHON:-}"

# The paste the deploy check runs (expert paste query 1, the same one the unit's
# warm-up uses). It must render at least one result card: `class="suggestion-card"` is
# the attribute app/ui/whyptology_app.py writes on every card, so renaming the class
# means changing it here too, or every deploy will be rolled back as "never rendered a
# result". The attribute, not the bare class name: the theme stylesheet the app injects
# on every page contains `.suggestion-card {`, so the bare name would match a page with
# no result at all (warm_streamlit.py also ignores <style> blocks, as a second layer).
PASTE_001="𓆓𓂧 𓆑𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏼 𓂋𓍿 𓀀 𓏼𓎟𓏏"
EXPECT_TEXT='class="suggestion-card"'

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
# The checker is the TARGET commit's copy, saved to $CHECKER before anything changed, and
# the rollback runs the same one: an older commit's warm_streamlit.py may not know
# --expect-text, and a rollback must not be judged by a weaker check than the deploy.
verify_app() {
  wait_healthy || return 1
  "$VENV/bin/python" "$CHECKER" --url "$APP_URL" --timeout 180 \
    --expect-text "$EXPECT_TEXT" --query "$PASTE_001"
}

# --- release venvs (audit A12, A40, A45) ------------------------------------------

# The directory the service's venv path resolves to now: the symlink's target, or the
# path itself on a box that still has the original real directory there.
current_venv() {
  if [[ -L "$VENV" ]]; then
    readlink "$VENV"
  else
    echo "$VENV"
  fi
}

# "name==version" for every exact pin in a pip requirements file, the name normalised the
# way pip compares names (lower case, runs of - _ . as one -) and extras dropped.
# Comments, options (-r, -c, --hash ...) and line continuations are skipped.
pins() {
  awk '{
    sub(/#.*/, ""); gsub(/[[:space:]\\]/, "")
    if ($0 == "" || substr($0, 1, 1) == "-") next
    sub(/;.*/, "")
    if (!match($0, /==/)) next
    name = substr($0, 1, RSTART - 1); version = substr($0, RSTART + 2)
    sub(/\[.*\]/, "", name); name = tolower(name); gsub(/[-_.]+/, "-", name)
    print name "==" version
  }' "$1"
}

# Every requirement name in a requirements file, normalised like pins().
requirement_names() {
  awk '{
    sub(/#.*/, ""); gsub(/[[:space:]]/, "")
    if ($0 == "" || substr($0, 1, 1) == "-") next
    if (!match($0, /^[A-Za-z0-9._-]+/)) next
    name = tolower(substr($0, 1, RLENGTH)); gsub(/[-_.]+/, "-", name)
    print name
  }' "$1"
}

# Saves the target commit's dependency files into $SCRATCH and decides how the release
# venv is built. With requirements.lock (the full `pip freeze` of a tested venv) that is
# installed as is, after checking it agrees with every pin in requirements.txt: a lock
# left behind by a requirements.txt change must stop the deploy, not quietly win.
# Without a lock, requirements.txt is installed with every package it does NOT name held
# at the version the running venv has (constraints from `pip freeze`), so a deploy that
# changes nothing about dependencies cannot upgrade protobuf or tornado underneath the app.
prepare_dependency_spec() {
  local missing
  git show "$AFTER:requirements.txt" > "$SCRATCH/requirements.txt" || return 1
  if git cat-file -e "$AFTER:requirements.lock" 2>/dev/null; then
    git show "$AFTER:requirements.lock" > "$SCRATCH/requirements.lock" || return 1
    missing="$(comm -23 <(pins "$SCRATCH/requirements.txt" | sort -u) <(pins "$SCRATCH/requirements.lock" | sort -u))"
    if [[ -n "$missing" ]]; then
      echo "deploy: requirements.lock disagrees with requirements.txt — regenerate the lock; nothing touched. Pins missing from the lock:" >&2
      sed 's/^/deploy:   /' <<<"$missing" >&2
      return 1
    fi
    DEPS_MODE=lock
    { echo "# requirements.lock"; cat "$SCRATCH/requirements.lock"; } > "$SCRATCH/deps-spec"
  else
    DEPS_MODE=requirements
    { echo "# requirements.txt, no lock"; cat "$SCRATCH/requirements.txt"; } > "$SCRATCH/deps-spec"
  fi
}

# The constraints for a build without a lock (see prepare_dependency_spec).
write_constraints() {
  : > "$SCRATCH/constraints.txt"
  if ! "$PREVIOUS_VENV/bin/pip" freeze > "$SCRATCH/frozen.txt" 2>/dev/null; then
    echo "deploy: warning — could not list the running venv's packages; unpinned packages resolve fresh" >&2
    return 0
  fi
  requirement_names "$SCRATCH/requirements.txt" > "$SCRATCH/names.txt"
  pins "$SCRATCH/frozen.txt" \
    | awk -F'==' 'NR == FNR { named[$0] = 1; next } !($1 in named)' "$SCRATCH/names.txt" - \
    > "$SCRATCH/constraints.txt"
}

# Sets NEW_VENV: the live venv when it was built from the same spec, otherwise a new
# directory in $RELEASES, built and installed here. Never touches the live venv. The
# marker is written last, so a half-built venv is never mistaken for a finished one.
build_release_venv() {
  local current
  current="$(current_venv)"
  if [[ -f "$current/$SPEC_MARKER" ]] && cmp -s "$SCRATCH/deps-spec" "$current/$SPEC_MARKER"; then
    echo "deploy: dependencies unchanged — keeping the venv $current"
    NEW_VENV="$current"
    return 0
  fi
  mkdir -p "$RELEASES" || return 1
  NEW_VENV="$RELEASES/$(git rev-parse --short "$AFTER")-$(date +%Y%m%d%H%M%S)-$$"
  BUILT_VENV="$NEW_VENV"
  echo "deploy: building a release venv from $([[ $DEPS_MODE == lock ]] && echo requirements.lock || echo requirements.txt) at $NEW_VENV"
  "${BASE_PYTHON:-$current/bin/python}" -m venv "$NEW_VENV" || return 1
  if [[ "$DEPS_MODE" == lock ]]; then
    "$NEW_VENV/bin/pip" install -q -r "$SCRATCH/requirements.lock" || return 1
  else
    echo "deploy: no requirements.lock in this commit — packages requirements.txt does not pin stay at the running venv's versions"
    write_constraints || return 1
    "$NEW_VENV/bin/pip" install -q -r "$SCRATCH/requirements.txt" -c "$SCRATCH/constraints.txt" || return 1
  fi
  cp "$SCRATCH/deps-spec" "$NEW_VENV/$SPEC_MARKER" || return 1
}

# Points $VENV at $1. Called only while the service is stopped. A box that still has the
# original real directory at $VENV gets it moved into $RELEASES first (once), and every
# record that named it is updated, so a rollback can still point back at it.
point_venv_at() {
  local target="$1" legacy
  if [[ "$target" == "$VENV" && -d "$VENV" && ! -L "$VENV" ]]; then
    return 0                       # the original directory, and it is still there
  fi
  if [[ -d "$VENV" && ! -L "$VENV" ]]; then
    mkdir -p "$RELEASES" || return 1
    legacy="$RELEASES/original-$(date +%Y%m%d%H%M%S)"
    mv "$VENV" "$legacy" || return 1
    echo "deploy: moved the original venv to $legacy"
    [[ "$PREVIOUS_VENV" == "$VENV" ]] && PREVIOUS_VENV="$legacy"
    [[ "$target" == "$VENV" ]] && target="$legacy"
    [[ "$(cat "$LAST_GOOD_VENV" 2>/dev/null)" == "$VENV" ]] && write_file "$LAST_GOOD_VENV" "$legacy"
  fi
  if [[ "$(current_venv)" != "$target" ]]; then
    ln -sfn "$target" "$VENV" || return 1
    echo "deploy: $VENV -> $target"
  fi
}

# After a success: keep the venv now serving and the one it replaced (the rollback
# target); remove every other release venv. They are about 0.8 GB each.
prune_releases() {
  local dir live
  live="$(current_venv)"
  for dir in "$RELEASES"/*; do
    [[ -d "$dir" ]] || continue
    if [[ "$dir" == "$live" || "$dir" == "$PREVIOUS_VENV" ]]; then
      continue
    fi
    rm -rf "$dir" && echo "deploy: removed the old release venv $dir"
  done
}

write_file() {
  printf '%s\n' "$2" > "$1.tmp" && mv -f "$1.tmp" "$1"
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
#
# Before a unit is overwritten its current version is saved in $LAST_GOOD_UNITS, and a
# unit that did not exist is listed in $LAST_GOOD_UNITS/ADDED, so restore_units can put
# back exactly what was there (audit A12/A46).
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
      mkdir -p "$UNIT_DIR" "$LAST_GOOD_UNITS" || return 1
      if [[ -e "$UNIT_DIR/$name" ]]; then
        cp -p "$UNIT_DIR/$name" "$LAST_GOOD_UNITS/$name" || return 1
      else
        echo "$name" >> "$LAST_GOOD_UNITS/ADDED" || return 1
      fi
      UNITS_CHANGED=1
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

# Undo install_units: the saved versions go back, units this deploy added are removed.
restore_units() {
  local file name
  [[ "$UNITS_CHANGED" == "1" ]] || return 0
  if [[ -f "$LAST_GOOD_UNITS/ADDED" ]]; then
    while IFS= read -r name; do
      [[ -n "$name" ]] && { rm -f "$UNIT_DIR/$name" || return 1; }
    done < "$LAST_GOOD_UNITS/ADDED"
  fi
  for file in "$LAST_GOOD_UNITS"/*.service "$LAST_GOOD_UNITS"/*.timer; do
    [[ -f "$file" ]] || continue
    cp -p "$file" "$UNIT_DIR/$(basename "$file")" || return 1
  done
  systemctl --user daemon-reload || return 1
  echo "deploy: restored the unit files from before this deploy" >&2
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
# reads the CSV by a relative path. The NEW release venv runs it: it is the new code.
import_corpus() {
  (
    export PRIVATE_DATA_DIR="${PRIVATE_DATA_DIR:-$HOME_DIR/egyptology-private}"
    export ANNOTATIONS_DURABLE="${ANNOTATIONS_DURABLE:-1}"
    cd "$REPO" || exit 1
    # A non-writing pass first, so the log distinguishes "nothing to insert" from
    # "N inserted" before the real sync runs. It reports what the default sync
    # would insert AND what --refresh-existing would change, and writes nothing.
    echo "deploy: dry-run — what the sync would change:"
    "$NEW_VENV/bin/python" scripts/import_examples.py --dry-run || exit 1
    echo "deploy: applying the sync:"
    "$NEW_VENV/bin/python" scripts/import_examples.py || exit 1
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
  # Stop, switch, start rather than `restart`: the venv path must never change under a
  # running process. The downtime is the same as a restart's.
  systemctl --user stop egyptology.service || return 1
  STOPPED_AT="${STOPPED_AT:-$SECONDS}"
  point_venv_at "$NEW_VENV" || return 1
  systemctl --user start egyptology.service || return 1
  verify_app || return 1
  echo "deploy: the service was down for about $((SECONDS - STOPPED_AT))s"
}

# Back to what was running: stop first (a failed check can leave the new app serving),
# then the unit files, the commit and the venv link exactly as recorded before the
# deploy, start, and the SAME paste check the deploy failed, not just /_stcore/health
# (that is the false-health condition A11 describes). Never touches ignored files, so the
# database (*.db) is safe. A release venv built for the failed commit is removed.
rollback() {
  local target="$1"
  echo "deploy: FAILED — rolling back to $(git -C "$REPO" rev-parse --short "$target")" >&2
  systemctl --user stop egyptology.service \
    || echo "deploy: warning — could not stop the service before rolling back" >&2
  if restore_units \
    && git -C "$REPO" reset --hard "$target" \
    && point_venv_at "$PREVIOUS_VENV" \
    && install_helpers \
    && systemctl --user start egyptology.service \
    && verify_app; then
    if [[ -n "$BUILT_VENV" && "$BUILT_VENV" != "$(current_venv)" ]]; then
      rm -rf "$BUILT_VENV"
    fi
    echo "deploy: ROLLED BACK to $(git -C "$REPO" rev-parse --short "$target")" >&2
    return 0
  fi
  {
    echo "deploy: MANUAL: the rollback itself failed. On the box:"
    echo "  systemctl --user stop egyptology.service"
    if [[ "$UNITS_CHANGED" == "1" ]]; then
      echo "  # unit files: put back the copies in $LAST_GOOD_UNITS, delete the ones listed in"
      echo "  # $LAST_GOOD_UNITS/ADDED, then: systemctl --user daemon-reload"
    fi
    echo "  git -C $REPO reset --hard \$(cat $LAST_GOOD)"
    echo "  ln -sfn \"\$(cat $LAST_GOOD_VENV)\" $VENV"
    echo "  systemctl --user start egyptology.service"
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

  # What is running now, recorded before anything changes (audit A12): the manual
  # recovery in DEPLOYMENT.md reads these, and they exist even on a first failed deploy.
  PREVIOUS_VENV="$(current_venv)"
  write_file "$LAST_GOOD" "$BEFORE"
  write_file "$LAST_GOOD_VENV" "$PREVIOUS_VENV"
  rm -rf "$LAST_GOOD_UNITS"
  UNITS_CHANGED=0
  BUILT_VENV=""

  SCRATCH="$(mktemp -d)"
  trap 'rm -rf "$SCRATCH"' EXIT
  CHECKER="$SCRATCH/warm_streamlit.py"
  git show "$AFTER:scripts/warm_streamlit.py" > "$CHECKER" 2>/dev/null \
    || git show "$BEFORE:scripts/warm_streamlit.py" > "$CHECKER"

  # Dependencies first, into a separate release venv, while nothing live has changed.
  # If this fails, the tree, the live venv and the running service are untouched.
  if ! prepare_dependency_spec || ! build_release_venv; then
    if [[ -n "$BUILT_VENV" ]]; then
      rm -rf "$BUILT_VENV"
    fi
    echo "deploy: could not build the dependencies — the tree, the live venv and the running service are untouched" >&2
    exit 1
  fi

  if ! apply_new_tree; then
    if rollback "$BEFORE"; then
      exit 1
    fi
    exit 2
  fi

  prune_releases
  # Refresh the operational copy of this script from the repo. Never in place: the
  # running script may be that very file, so write beside it and rename over it.
  if [[ -f "$REPO/scripts/egyptology-deploy.sh" ]]; then
    install -m 755 "$REPO/scripts/egyptology-deploy.sh" "$DEPLOY_COPY.new" \
      && mv -f "$DEPLOY_COPY.new" "$DEPLOY_COPY" \
      || echo "deploy: warning — could not refresh $DEPLOY_COPY" >&2
  fi
  echo "deploy: done, serving $(git log -1 --format=%h) on $(current_venv); the previous state is in $LAST_GOOD and $LAST_GOOD_VENV"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
