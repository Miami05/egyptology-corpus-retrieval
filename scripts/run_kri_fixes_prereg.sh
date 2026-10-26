#!/usr/bin/env bash
# The exact command list of docs/kri-fixes-preregistration-2026-10-26.md §5.
# Run it as:   bash scripts/run_kri_fixes_prereg.sh
# (bash, not zsh: zsh does not word-split, and this file is the registered commands).
# tests/test_check_kri_fixes_gates.py checks that §5 reproduces this file verbatim.
#
# Two environment variables exist ONLY to prove steps 0-1 run before the registered run
# (a dry check into a scratch directory). The registered run sets neither:
#   KRI_RUNS_BASE   parent directory of the attempt directory (default ~/egyptology-runs)
#   KRI_STOP_AFTER  stop cleanly after this step number (default: run every step)
set -euo pipefail

WT=/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/kri-fixes-2026-10-26
BRANCH=kri-fixes-2026-10-26
PY=/Users/lediodurmishaj/venvs/egyptology/bin/python
PRIV=/Users/lediodurmishaj/projects/Egyptology-APP/data/private
BASE=$HOME/egyptology-runs/remeasure-2026-10-25     # attempt 2 of the 2026-10-25 run
B=data/benchmarks
MANIFEST_SHA=ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba
RUNS=${KRI_RUNS_BASE:-$HOME/egyptology-runs}
STOP_AFTER=${KRI_STOP_AFTER:-}

# A fresh attempt directory, never an existing one: evidence is never overwritten.
N=1
while [ -e "$RUNS/kri-fixes-2026-10-26-attempt$N" ]; do N=$((N + 1)); done
R=$RUNS/kri-fixes-2026-10-26-attempt$N
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
    log "STOP at $label (rule h): fix on a new commit, addendum, re-run everything"
    echo "STOP at $label (exit $code); see $R/run_log.txt" >&2
    exit "$code"
  fi
}
done_after() {
  if [ "$STOP_AFTER" = "$1" ]; then
    log "stopped after step $1 (KRI_STOP_AFTER; not a registered run)"
    echo "stopped after step $1 (KRI_STOP_AFTER)"
    exit 0
  fi
}

# Step 0 - the right worktree, branch and a clean tree; pin everything.
cd "$WT"
run step0-toplevel test "$(git rev-parse --show-toplevel)" = "$WT"
run step0-branch test "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH"
run step0-clean test -z "$(git status --porcelain)"
run step0-private-dir test -d "$PRIV"
run step0-attempt2-dir test -d "$BASE"
git rev-parse HEAD > "$R/commit.txt"
shasum -a 256 data/processed/examples.csv scripts/eval_guards.py \
  scripts/run_reading_model_eval.py scripts/run_kri_fixes_eval.py \
  scripts/check_kri_fixes_gates.py scripts/run_kri_fixes_prereg.sh > "$R/shas.txt"
printf '%s\n' \
  "44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2  data/processed/examples.csv" \
  "17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950  scripts/eval_guards.py" \
  "373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5  scripts/run_reading_model_eval.py" \
  > "$R/pinned_shas.txt"
run step0-pinned-shas shasum -a 256 -c "$R/pinned_shas.txt"
"$PY" --version > "$R/env.txt"
"$PY" -m pip freeze >> "$R/env.txt"
done_after 0

# Step 1 - the split manifest, checked against section 2 by content.
mkdir "$R/_step1"
run step1-manifest "$PY" scripts/run_kri_fixes_eval.py \
  --split-manifest "$R/split_manifest.csv" --max-test-rows 1 \
  --positions "$R/_step1/positions.csv" --lines "$R/_step1/lines.csv" \
  --summary "$R/_step1/summary.csv" > "$R/step1.txt" 2>&1
echo "$MANIFEST_SHA  $R/split_manifest.csv" > "$R/manifest_sha.txt"
run step1-manifest-sha shasum -a 256 -c "$R/manifest_sha.txt"
done_after 1

# Step 2 - the paired harness, all five arms, full test split (~11-12 min).
run step2-harness "$PY" scripts/run_kri_fixes_eval.py \
  --positions "$R/kri_positions.csv" --lines "$R/kri_lines.csv" \
  --summary "$R/kri_summary.csv" \
  --calibration "$R/kri_summary_calibration.csv" > "$R/step2.txt" 2>&1

# Step 3 - rules (a), (b), (c), (d), (g): gates, decision, listings, calibration.
run step3-gates "$PY" scripts/check_kri_fixes_gates.py harness --run-dir "$R" \
  > "$R/step3_gates.txt" 2>&1

# Step 4 - rule (e), the expert paste gate.
for M in auto declared; do
  run "step4-paste-$M" "$PY" scripts/run_expert_paste_eval.py \
    --queries "$B/expert_paste_queries.csv" --stage "$M" \
    --results "$R/paste_$M.csv" > "$R/paste_$M.txt" 2>&1
done
run step4-paste-check "$PY" scripts/check_kri_fixes_gates.py paste --run-dir "$R" \
  > "$R/step4_gates.txt" 2>&1

# Step 5 - rule (e2), the Urk. IV / St Andrews gate, both modes.
for M in auto declared; do
  run "step5-urkiv-$M" "$PY" scripts/check_standrews_urkiv_gate.py \
    --private-dir "$PRIV" --stage "$M" > "$R/urkiv_standrews_$M.txt" 2>&1
done

# Step 6 - rule (e3), held-out stage routing, against attempt 2's sample.
run step6-routing "$PY" scripts/run_stage_routing_eval.py --seed 20261025 \
  --per-stage 200 --results "$R/routing.csv" > "$R/routing_summary.txt" 2>&1
run step6-routing-check "$PY" scripts/check_kri_fixes_gates.py routing --run-dir "$R" \
  --baseline-dir "$BASE" > "$R/step6_gates.txt" 2>&1

# Step 7 - rule (f), the competitive sanity check, per query against attempt 2.
CE=("$PY" scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4)
for S in v4 holdout le_v1; do
  case $S in
    v4)      F=$B/competitive_ambiguity_eval_queries_v4.csv ;;
    holdout) F=$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv ;;
    le_v1)   F=$B/competitive_ambiguity_eval_queries_le_v1.csv ;;
  esac
  run "step7-$S-T" "${CE[@]}" --benchmark "$F" --stage auto --exclude-twins 0.7 \
    --expected-tokens current --results "$R/${S}_T_auto.csv" \
    --failures "$R/${S}_T_auto_fail.csv" > "$R/${S}_T_auto.txt" 2>&1
  run "step7-$S-L" "${CE[@]}" --benchmark "$F" --stage auto --exclude-twins 0 \
    --expected-tokens frozen --results "$R/${S}_L_auto.csv" \
    --failures "$R/${S}_L_auto_fail.csv" > "$R/${S}_L_auto.txt" 2>&1
done
run step7-competitive-check "$PY" scripts/check_kri_fixes_gates.py competitive \
  --run-dir "$R" --baseline-dir "$BASE" > "$R/step7_gates.txt" 2>&1

# Step 8 - the release check (no pytest here: step 9 runs it once), then determinism:
# its own v4 L, v4 T and paste runs must reproduce steps 7 and 4 exactly.
run step8-verify "$PY" scripts/verify_release.py --skip-tests > "$R/verify_release.txt" 2>&1
run step8-verify-check "$PY" scripts/check_kri_fixes_gates.py verify --run-dir "$R" \
  > "$R/step8_gates.txt" 2>&1

# Step 9 - the full test suite, once, output kept.
run step9-pytest "$PY" -m pytest -q > "$R/pytest.txt" 2>&1

log "ALL STEPS PASSED"
echo "all steps passed; results in $R"
