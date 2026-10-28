#!/usr/bin/env bash
# Experiment 3, step 4: the one-time held-out 3 confirmation of the selected configuration
# (F-a), on the SAME commit pair as the registered run (ROADMAP.md, Experiment 3 section,
# step 4 and the re-scope addendum, plus the 2026-10-28 note that pins this runner).
#
# Run it as:   bash scripts/run_exp3_step4.sh BASE_SHA FA_SHA
# Both must be the pinned pair below (the registered run's arms); anything else stops at step 0.
#   base e2a9596316ba9d0aa3457eb648a4892712bd1b0a
#   fa   b4844a1e1dd5875e93dde7c9173435a2bfd765b8
#
# What it does, per arm (one detached worktree each, at the pinned commit): verify held-out 3's
# sha256 against the build log (and against the sha pinned here) BEFORE anything reads it; build
# its faithful benchmark file with scripts/exp3_faithful_benchmark_file.py (the helper used for
# held-out 2; the fold-back check must hold on every row); then the IDENTICAL $CE command lines
# of scripts/run_exp3_prereg.sh, stored and faithful queries, pools C (--exclude-twins 0) and
# T (--exclude-twins 0.7). Finally scripts/check_exp3_step4.py applies the frozen rule
# mechanically to held-out 3 faithful and writes gate_step4.txt (PASS/FAIL per pool, overall).
#
# HELD-OUT 3 IS SEALED until this run. Nothing before the EXP3_STOP_AFTER=0 exit touches its
# content: step 0 only asks git whether the path exists in each commit. The runner never prints
# the file; it only hashes it, hands it to the faithful-file helper and to the harness.
# (bash, not zsh: zsh does not word-split, and this file is the registered commands.)
#
# One environment variable exists ONLY to prove step 0 before the real run (a dry check into a
# scratch directory). The real run does not set it:
#   EXP3_RUNS_BASE  parent directory of the attempt directory (default ~/egyptology-runs)
#   EXP3_STOP_AFTER  "0": stop cleanly after the step-0 checks and worktrees, before any
#                    held-out 3 read
#
# Known, deliberate properties (review 2026-10-28):
#  - step0-base-contains-main is copied from the prereg and needs `main` to be an ancestor of
#    base. It holds while main is 51f3757. If anything is merged to main first, step 0 stops
#    (safely, before any read of held-out 3). Launch step 4 before merging anything; do not edit
#    this pinned runner afterwards to get around it.
#  - Step 0 makes git check each arm's worktree out, so the held-out 3 file is on disk there (as
#    in every checkout of these commits). It is not opened, read, hashed or parsed before step 1.
#  - A dry run (EXP3_STOP_AFTER=0) leaves its two worktrees behind. Remove them by hand:
#    git worktree remove --force $REPO/.claude/worktrees/exp3-step4-run-<date>-attempt<N>-{base,fa}
set -euo pipefail

BASE_PIN=e2a9596316ba9d0aa3457eb648a4892712bd1b0a
FA_PIN=b4844a1e1dd5875e93dde7c9173435a2bfd765b8
if [ "$#" -ne 2 ] || ! [[ "$1" =~ ^[0-9a-f]{40}$ ]] || ! [[ "$2" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: bash scripts/run_exp3_step4.sh BASE_SHA FA_SHA (full 40-hex commit ids)" >&2
  exit 2
fi
BASE_SHA=$1
FA_SHA=$2

REPO=/Users/lediodurmishaj/projects/Egyptology-APP
PY=/Users/lediodurmishaj/venvs/egyptology/bin/python
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SELF_REPO=$(git -C "$SELF_DIR" rev-parse --show-toplevel)
CHECKER=$SELF_DIR/check_exp3_step4.py
B=data/benchmarks
CORPUS_SHA=44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2
HO3=$B/competitive_ambiguity_eval_queries_holdout3_2026-10-27_SEALED.csv
HO3_SHA=c80100cf93e64a0649f0616eca795aac469dbef1a74b9ca51107bd6f16d2d838
BUILD_LOG=$B/exp3_heldout_build_log.txt
RUNS=${EXP3_RUNS_BASE:-$HOME/egyptology-runs}
STOP_AFTER=${EXP3_STOP_AFTER:-}

# A fresh attempt directory, never an existing one: evidence is never overwritten.
DAY=$(date +%F)
N=1
while [ -e "$RUNS/exp3-step4-$DAY-attempt$N" ]; do N=$((N + 1)); done
R=$RUNS/exp3-step4-$DAY-attempt$N
mkdir -p "$RUNS"
mkdir "$R"
echo "attempt directory: $R"

log() { echo "$(date -u +%FT%TZ) $*" >> "$R/run_log.txt"; }
# Every step goes through run: a non-zero exit is logged and STOPS the run.
run() {
  local label=$1
  shift
  log "START $label"
  local code=0
  "$@" || code=$?
  log "END $label exit=$code"
  if [ "$code" -ne 0 ]; then
    log "STOP at $label"
    echo "STOP at $label (exit $code); see $R/run_log.txt" >&2
    exit "$code"
  fi
}

# Step 0 - the commit pair, the switch, the environment, this runner; pin everything.
cd "$REPO"
printf 'base %s\nfa %s\n' "$BASE_SHA" "$FA_SHA" > "$R/approved_commits.txt"
run step0-pinned-base test "$BASE_SHA" = "$BASE_PIN"
run step0-pinned-fa test "$FA_SHA" = "$FA_PIN"
run step0-no-switch-env test -z "${WHYPTOLOGY_EXP3_FA:-}"
# A signal ignored at launch (nohup, `cmd &`) cannot be trapped again; refuse such a launch.
run step0-signals "$PY" -c "import signal, sys; sys.exit(any(signal.getsignal(s) == signal.SIG_IGN for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)))"
# NC data never enters a run directory: nothing private is configured for these runs.
unset PRIVATE_DATA_DIR REVIEWER_KEY || true
# The runner and the checker are the committed ones: a clean tree, and their own hashes kept.
run step0-runner-committed test -z "$(git -C "$SELF_REPO" status --porcelain -- scripts/run_exp3_step4.sh scripts/check_exp3_step4.py)"
git -C "$SELF_REPO" rev-parse HEAD > "$R/runner_commit.txt"
shasum -a 256 "$SELF_DIR/run_exp3_step4.sh" "$CHECKER" > "$R/runner_sha256.txt"
run step0-base-exists git cat-file -e "$BASE_SHA^{commit}"
run step0-fa-exists git cat-file -e "$FA_SHA^{commit}"
run step0-fa-parent test "$(git rev-parse "$FA_SHA^")" = "$BASE_SHA"
run step0-fa-one-file test "$(git diff --name-only "$BASE_SHA" "$FA_SHA")" = "app/services/faithful.py"
run step0-fa-one-line test "$(git diff -U0 "$BASE_SHA" "$FA_SHA" | grep -E '^[-+][^-+]')" \
  = "$(printf '%s\n%s' '-EXP3_FA_DEFAULT = False' '+EXP3_FA_DEFAULT = True')"
run step0-base-contains-main git merge-base --is-ancestor main "$BASE_SHA"
# Existence in the commits only (git cat-file -e reports, it does not print): no content read.
run step0-ho3-committed-base git cat-file -e "$BASE_SHA:$HO3"
run step0-ho3-committed-fa git cat-file -e "$FA_SHA:$HO3"
run step0-buildlog-committed git cat-file -e "$BASE_SHA:$BUILD_LOG"
"$PY" --version > "$R/env.txt"
"$PY" -m pip freeze >> "$R/env.txt"

# One detached worktree per arm, at its pinned commit (the corpus is git-lfs). The attempt
# number is in the name, so a dry run never blocks the real run.
for ARM in base fa; do
  case $ARM in base) SHA=$BASE_SHA ;; fa) SHA=$FA_SHA ;; esac
  WT=$REPO/.claude/worktrees/exp3-step4-run-$DAY-attempt$N-$ARM
  run "step0-worktree-$ARM" git worktree add --detach "$WT" "$SHA"
  mkdir "$R/$ARM"
  echo "$WT" > "$R/$ARM/worktree.txt"
  (cd "$WT" && git lfs pull >/dev/null 2>&1 || true)
  echo "$CORPUS_SHA  $WT/data/processed/examples.csv" > "$R/$ARM/pinned_corpus_sha.txt"
  run "step0-corpus-$ARM" shasum -a 256 -c "$R/$ARM/pinned_corpus_sha.txt"
  run "step0-clean-$ARM" test -z "$(git -C "$WT" status --porcelain)"
  (cd "$WT" && "$PY" -c 'from app.services.faithful import faithful_search_enabled as f; print("ON" if f() else "off")') \
    > "$R/$ARM/switch.txt"
done
run step0-switch-base test "$(cat "$R/base/switch.txt")" = "off"
run step0-switch-fa test "$(cat "$R/fa/switch.txt")" = "ON"
if [ "$STOP_AFTER" = "0" ]; then
  log "stopped after step 0 (EXP3_STOP_AFTER; not a registered run; held-out 3 not read)"
  echo "stopped after step 0 (EXP3_STOP_AFTER); held-out 3 not read"
  exit 0
fi

# Step 1 - held-out 3 is opened here, once. First its sha256: the build log's recorded value
# must equal the value pinned in this file, and the file in each arm's worktree must equal both.
BUILD_LOG_SHA=$(awk -v f="$HO3" '$1 == f && $2 == "sha256" {print $3}' "$REPO/.claude/worktrees/exp3-step4-run-$DAY-attempt$N-base/$BUILD_LOG")
echo "$BUILD_LOG_SHA" > "$R/ho3_sha256_from_build_log.txt"
run step1-ho3-sha-buildlog-equals-pin test "$BUILD_LOG_SHA" = "$HO3_SHA"
for ARM in base fa; do
  WT=$(cat "$R/$ARM/worktree.txt")
  echo "$HO3_SHA  $WT/$HO3" > "$R/$ARM/ho3_sha_check.txt"
  run "step1-ho3-sha-$ARM" shasum -a 256 -c "$R/$ARM/ho3_sha_check.txt"
done

# Steps 2 - the pinned commands of run_exp3_prereg.sh, held-out 3 only, base arm first, then fa.
CE=("$PY" scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4 \
  --stage auto --expected-tokens current)
for ARM in base fa; do
  WT=$(cat "$R/$ARM/worktree.txt")
  A=$R/$ARM
  cd "$WT"
  git rev-parse HEAD > "$A/commit.txt"
  shasum -a 256 data/processed/examples.csv > "$A/corpus_sha256.txt"
  run "$ARM-faithful-holdout3" "$PY" scripts/exp3_faithful_benchmark_file.py "$HO3" \
    "$A/faithful/faithful_$(basename "$HO3")" > "$A/faithful_holdout3.txt" 2>&1
  S=holdout3
  for Q in stored faithful; do
    case $Q in stored) BQ=$HO3 ;; faithful) BQ=$A/faithful/faithful_$(basename "$HO3") ;; esac
    run "$ARM-$S-$Q-C" "${CE[@]}" --benchmark "$BQ" --exclude-twins 0 \
      --results "$A/${S}_${Q}_C.csv" --failures "$A/${S}_${Q}_C_fail.csv" \
      > "$A/${S}_${Q}_C.txt" 2>&1
    run "$ARM-$S-$Q-T" "${CE[@]}" --benchmark "$BQ" --exclude-twins 0.7 \
      --results "$A/${S}_${Q}_T.csv" --failures "$A/${S}_${Q}_T_fail.csv" \
      > "$A/${S}_${Q}_T.txt" 2>&1
  done
  (cd "$A" && shasum -a 256 ./*.csv ./*.txt faithful/*.csv > sha256.txt)
done

# Step 3 - the frozen rule, mechanically, on held-out 3 faithful (stdlib-only checker, run from
# the committed runner checkout, so it reads no arm's code). A FAIL is a result, not a crash:
# it is logged and the run ends normally; only an unjudgeable input (exit 2) stops it.
cd "$R"
GATE_CODE=0
"$PY" "$CHECKER" --base-c base/holdout3_faithful_C.csv --fa-c fa/holdout3_faithful_C.csv \
  --base-t base/holdout3_faithful_T.csv --fa-t fa/holdout3_faithful_T.csv \
  --out "$R/gate_step4.txt" || GATE_CODE=$?
log "gate_step4 exit=$GATE_CODE (0 PASS, 1 FAIL, 2 unjudgeable)"
{
  echo "== informational, not part of the rule: stored folded-ASCII queries, per-query results base vs fa"
  for P in C T; do
    if cmp -s "base/holdout3_stored_$P.csv" "fa/holdout3_stored_$P.csv"; then
      echo "IDENTICAL holdout3_stored_$P.csv"
    else
      echo "DIFFERS   holdout3_stored_$P.csv"
    fi
  done
  echo "== corpus sha256"
  cat base/corpus_sha256.txt fa/corpus_sha256.txt
} > "$R/step4_info.txt" 2>&1
if [ "$GATE_CODE" -eq 2 ]; then
  log "STOP at gate_step4 (unjudgeable)"
  shasum -a 256 gate_step4.txt step4_info.txt run_log.txt runner_sha256.txt > sha256_top.txt 2>/dev/null || true
  echo "STOP: gate unjudgeable; see $R/gate_step4.txt" >&2
  exit 2
fi
# The final log line goes in before the checksum, so sha256_top.txt matches the files.
log "ALL STEPS RAN"
shasum -a 256 gate_step4.txt step4_info.txt run_log.txt runner_sha256.txt > sha256_top.txt
echo "all steps ran; results in $R (worktrees kept: see */worktree.txt)"
tail -1 "$R/gate_step4.txt"
