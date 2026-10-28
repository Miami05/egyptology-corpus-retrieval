#!/usr/bin/env bash
# The exact command list of docs/transition-smoothing-preregistration-2026-10-28.md section 8.
# Run it twice, in this order, one phase at a time:
#   bash scripts/run_transition_smoothing_prereg.sh dev  APPROVED_SHA
#   (commit $R/dev_record.json as docs/transition-smoothing-dev-record-2026-10-28.json - the
#    ONLY change - then take the new commit's full id as the second APPROVED_SHA)
#   bash scripts/run_transition_smoothing_prereg.sh test APPROVED_SHA
# APPROVED_SHA is the full 40-character commit id the approver signed off on for that phase.
# Step 0 stops unless HEAD is exactly that commit (a different clean commit on the branch,
# with different code, must not be able to run as the registered one).
# (bash, not zsh: zsh does not word-split, and this file is the registered commands).
# tests/test_check_transition_smoothing_gates.py checks that section 8 reproduces this file
# verbatim.
#
# Two environment variables exist ONLY to prove the first steps run before the registered
# run (a dry check into a scratch directory). The registered run sets neither:
#   TS_RUNS_BASE   parent directory of the attempt directory (default ~/egyptology-runs)
#   TS_STOP_AFTER  stop cleanly after this step number (default: run every step)
set -euo pipefail

if [ "$#" -ne 2 ] || ! [[ "$1" =~ ^(dev|test)$ ]] || ! [[ "$2" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: bash scripts/run_transition_smoothing_prereg.sh dev|test APPROVED_SHA (the full 40-hex commit id)" >&2
  exit 2
fi
PHASE=$1
APPROVED_SHA=$2

WT=/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/transition-smoothing-2026-10-28
BRANCH=transition-smoothing-2026-10-28
PY=/Users/lediodurmishaj/venvs/egyptology/bin/python
BASE=$HOME/egyptology-runs/remeasure-2026-10-25     # attempt 2 of the 2026-10-25 run
B=data/benchmarks
RECORD=docs/transition-smoothing-dev-record-2026-10-28.json
TEST_MANIFEST_SHA=ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba
DEV_MANIFEST_SHA_R10=52415842fbb209d955b5d28d48011f462cb5a0d756400c1f8e2d76f191263344
DEV_MANIFEST_SHA_R20=11dfe145090bb6a3ee4d846f428b595a8fba79787662193d9a20677b3328a0b3
RUNS=${TS_RUNS_BASE:-$HOME/egyptology-runs}
STOP_AFTER=${TS_STOP_AFTER:-}
SWITCH=EGYPTOLOGY_TRANSITION_SMOOTHING

# A fresh attempt directory, never an existing one: evidence is never overwritten.
N=1
while [ -e "$RUNS/transition-smoothing-2026-10-28-$PHASE-attempt$N" ]; do N=$((N + 1)); done
R=$RUNS/transition-smoothing-2026-10-28-$PHASE-attempt$N
mkdir -p "$RUNS"
mkdir "$R"
echo "attempt directory: $R"

log() { echo "$(date -u +%FT%TZ) $*" >> "$R/run_log.txt"; }
# Every step goes through run: a non-zero exit is logged and STOPS the run (rule h).
run() {
  local label=$1
  shift
  log "START $label"
  local code=0
  "$@" || code=$?
  log "END $label exit=$code"
  if [ "$code" -ne 0 ]; then
    log "STOP at $label (rule h): fix a harness or procedural fault on a new commit, addendum, re-run the phase"
    echo "STOP at $label (exit $code); see $R/run_log.txt" >&2
    exit "$code"
  fi
}
done_after() {
  if [ "$STOP_AFTER" = "$1" ]; then
    log "stopped after step $1 (TS_STOP_AFTER; not a registered run)"
    echo "stopped after step $1 (TS_STOP_AFTER)"
    exit 0
  fi
}

# Step 0 - the right worktree, branch and a clean tree; pin everything.
cd "$WT"
run step0-toplevel test "$(git rev-parse --show-toplevel)" = "$WT"
run step0-branch test "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH"
echo "$APPROVED_SHA" > "$R/approved_commit.txt"
run step0-approved-commit test "$(git rev-parse HEAD)" = "$APPROVED_SHA"
run step0-clean test -z "$(git status --porcelain)"
# The default decoder scheme must be add-k: a switch set in the launching shell would make
# the baseline arm something else.
run step0-switch-unset test -z "${!SWITCH:-}"
# No private data of any kind: no keyed directory in the environment, none in the worktree.
run step0-no-private-env test -z "${PRIVATE_DATA_DIR:-}"
run step0-no-private-dir test ! -e data/private
if [ "$PHASE" = test ]; then
  run step0-attempt2-dir test -d "$BASE"
fi
# The deploy tests trap HUP/INT/TERM; a signal ignored at launch (nohup, `cmd &`) cannot be
# trapped again, so those tests would fail for the launcher, not the code.
run step0-signals "$PY" -c "import signal, sys; sys.exit(any(signal.getsignal(s) == signal.SIG_IGN for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)))"
git rev-parse HEAD > "$R/commit.txt"
shasum -a 256 data/processed/examples.csv scripts/eval_guards.py \
  scripts/run_reading_model_eval.py scripts/run_kri_fixes_eval.py \
  scripts/check_kri_fixes_gates.py scripts/run_transition_smoothing_eval.py \
  scripts/check_transition_smoothing_gates.py scripts/run_transition_smoothing_prereg.sh \
  app/services/reading_model.py app/services/stage.py > "$R/shas.txt"
printf '%s\n' \
  "44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2  data/processed/examples.csv" \
  "17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950  scripts/eval_guards.py" \
  "373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5  scripts/run_reading_model_eval.py" \
  > "$R/pinned_shas.txt"
run step0-pinned-shas shasum -a 256 -c "$R/pinned_shas.txt"
"$PY" --version > "$R/env.txt"
"$PY" -m pip freeze >> "$R/env.txt"
done_after 0

# Step 1 - the split manifests, checked by content (section 2 and R4).
printf '%s\n' \
  "$TEST_MANIFEST_SHA  $R/manifests/split_manifest.csv" \
  "$DEV_MANIFEST_SHA_R10  $R/manifests/dev_manifest_r10.csv" \
  "$DEV_MANIFEST_SHA_R20  $R/manifests/dev_manifest_r20.csv" > "$R/manifest_sha.txt"
run step1-manifests "$PY" scripts/run_transition_smoothing_eval.py \
  --phase manifests --out-dir "$R/manifests" > "$R/step1.txt" 2>&1
run step1-manifest-sha shasum -a 256 -c "$R/manifest_sha.txt"
if [ "$PHASE" = test ]; then
  # The dev record is committed, names a primary arm, and is the only change since the dev run.
  run step1-preflight "$PY" scripts/check_transition_smoothing_gates.py preflight \
    --record "$RECORD" > "$R/step1_preflight.txt" 2>&1
  run step1-primary-arm "$PY" scripts/check_transition_smoothing_gates.py primary \
    --record "$RECORD" > "$R/primary_arm.txt"
  PRIMARY=$(cat "$R/primary_arm.txt")
fi
done_after 1

if [ "$PHASE" = dev ]; then
  # Step 2 - the dev stage: minimum counts first, then all four arms on the dev rows.
  run step2-dev-harness env -u "$SWITCH" -u PRIVATE_DATA_DIR "$PY" \
    scripts/run_transition_smoothing_eval.py --phase dev --out-dir "$R" > "$R/step2.txt" 2>&1

  # Step 3 - the dev manifest is the pinned one for its rate; R7 selects the primary arm.
  run step3-dev-manifest "$PY" scripts/check_transition_smoothing_gates.py dev-manifest \
    --run-dir "$R" > "$R/step3_manifest.txt" 2>&1
  run step3-dev-selection "$PY" scripts/check_transition_smoothing_gates.py dev \
    --run-dir "$R" > "$R/step3_selection.txt" 2>&1

  log "DEV PHASE DONE: commit $R/dev_record.json as $RECORD, then run the test phase"
  echo "dev phase done; selection in $R/step3_selection.txt, record in $R/dev_record.json"
  echo "next: commit it as $RECORD (nothing else), then run the test phase at that commit"
  exit 0
fi

# Step 2 - the test split, all four arms (every arm decodes under off's routing).
run step2-harness env -u "$SWITCH" -u PRIVATE_DATA_DIR "$PY" \
  scripts/run_transition_smoothing_eval.py --phase test --out-dir "$R" > "$R/step2.txt" 2>&1

# Step 3 - rules (c'), (d'), (e), (f'), (h), (i).
run step3-gates "$PY" scripts/check_transition_smoothing_gates.py harness --run-dir "$R" \
  --record "$RECORD" > "$R/step3_gates.txt" 2>&1

# Step 4 - rules (a) and (f') on the expert pastes: the primary arm, and the default beside it.
for M in auto declared none; do
  run "step4-paste-$M" env "$SWITCH=$PRIMARY" "$PY" scripts/run_expert_paste_eval.py \
    --queries "$B/expert_paste_queries.csv" --stage "$M" \
    --results "$R/paste_$M.csv" > "$R/paste_$M.txt" 2>&1
done
run step4-paste-auto-default env -u "$SWITCH" "$PY" scripts/run_expert_paste_eval.py \
  --queries "$B/expert_paste_queries.csv" --stage auto \
  --results "$R/paste_auto_off.csv" > "$R/paste_auto_off.txt" 2>&1
run step4-paste-check "$PY" scripts/check_transition_smoothing_gates.py paste --run-dir "$R" \
  --baseline-dir "$BASE" > "$R/step4_gates.txt" 2>&1

# Step 5 - none. Rule (b), the Urk. IV / St Andrews gate, is withdrawn from this run: it
# reads private rows, and this run reads only data/processed/examples.csv. The numbering of
# steps 6-8 is kept.

# Step 6 - rule (g'), the competitive sanity check, per query against attempt 2.
CE=("$PY" scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4)
for RUN in v4:T v4:L holdout:T holdout:C le_v1:T le_v1:C; do
  S=${RUN%%:*}
  M=${RUN##*:}
  case $S in
    v4)      F=$B/competitive_ambiguity_eval_queries_v4.csv ;;
    holdout) F=$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv ;;
    le_v1)   F=$B/competitive_ambiguity_eval_queries_le_v1.csv ;;
  esac
  case $M in
    T) ARGS=(--exclude-twins 0.7 --expected-tokens current) ;;
    C) ARGS=(--exclude-twins 0 --expected-tokens current) ;;
    L) ARGS=(--exclude-twins 0 --expected-tokens frozen) ;;
  esac
  run "step6-$S-$M" env "$SWITCH=$PRIMARY" "${CE[@]}" --benchmark "$F" --stage auto \
    "${ARGS[@]}" --results "$R/${S}_${M}_auto.csv" \
    --failures "$R/${S}_${M}_auto_fail.csv" > "$R/${S}_${M}_auto.txt" 2>&1
done
run step6-competitive-check "$PY" scripts/check_transition_smoothing_gates.py competitive \
  --run-dir "$R" --baseline-dir "$BASE" > "$R/step6_gates.txt" 2>&1

# Step 7 - the release check under the primary arm (no pytest here: step 8 runs it once),
# then determinism: its own v4 L, v4 T and paste runs must reproduce steps 6 and 4 exactly.
run step7-verify env "$SWITCH=$PRIMARY" "$PY" scripts/verify_release.py --skip-tests \
  > "$R/verify_release.txt" 2>&1
run step7-verify-check "$PY" scripts/check_transition_smoothing_gates.py verify --run-dir "$R" \
  > "$R/step7_gates.txt" 2>&1

# Step 8 - the full test suite, once, output kept, with the shipped default (the switch unset).
run step8-pytest env -u "$SWITCH" "$PY" -m pytest -q > "$R/pytest.txt" 2>&1

log "ALL STEPS PASSED"
echo "all steps passed; results in $R"
