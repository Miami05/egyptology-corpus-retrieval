#!/usr/bin/env bash
# Experiment 3, step 3: the pinned commands of ROADMAP.md, Experiment 3 addendum
# 2026-10-26, "Pinned commands (both arms, same flags; the arms differ only in the
# commit)", for both arms in one overnight run, alone on the machine.
#
# Run it as:   bash scripts/run_exp3_prereg.sh BASE_SHA FA_SHA
#   BASE_SHA  the exact parent commit of the F-a change (after any KRI merge): today's
#             code plus the F-a switch, which defaults OFF (app/services/faithful.py).
#   FA_SHA    the F-a commit: BASE_SHA plus the one line `EXP3_FA_DEFAULT = True`
#             (make it with scripts/exp3_make_fa_arm.sh BASE_SHA).
# Both are full 40-hex ids the approver signed off on. Step 0 stops unless FA^ is BASE,
# the two differ only in that one line, main is contained in BASE, and the switch
# reads off in base and ON in fa with the environment variable unset (so the $CE
# lines are byte-identical in both arms: the arms differ only in the commit).
#
# Sets: v4, held-out 1, LE-v1, NAME-v1, held-out 2; stored and faithful queries; pools
# C (--exclude-twins 0) and T (--exclude-twins 0.7). Held-out 3 is not read here: it
# opens once, later, for the selected configuration only (addendum, step 4).
# (bash, not zsh: zsh does not word-split, and this file is the registered commands.)
#
# One environment variable exists ONLY to prove step 0 before the registered run (a
# dry check into a scratch directory). The registered run does not set it:
#   EXP3_RUNS_BASE  parent directory of the attempt directory (default ~/egyptology-runs)
#   EXP3_STOP_AFTER  stop cleanly after this step ("0": after the checks and worktrees)
set -euo pipefail

if [ "$#" -ne 2 ] || ! [[ "$1" =~ ^[0-9a-f]{40}$ ]] || ! [[ "$2" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: bash scripts/run_exp3_prereg.sh BASE_SHA FA_SHA (full 40-hex commit ids)" >&2
  exit 2
fi
BASE_SHA=$1
FA_SHA=$2

REPO=/Users/lediodurmishaj/projects/Egyptology-APP
PY=/Users/lediodurmishaj/venvs/egyptology/bin/python
B=data/benchmarks
CORPUS_SHA=44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2
HO2=$B/competitive_ambiguity_eval_queries_holdout2_2026-10-27.csv
RUNS=${EXP3_RUNS_BASE:-$HOME/egyptology-runs}
STOP_AFTER=${EXP3_STOP_AFTER:-}

# A fresh attempt directory, never an existing one: evidence is never overwritten.
DAY=$(date +%F)
N=1
while [ -e "$RUNS/exp3-$DAY-attempt$N" ]; do N=$((N + 1)); done
R=$RUNS/exp3-$DAY-attempt$N
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

# Step 0 - the commit pair, the switch, the environment; pin everything.
cd "$REPO"
printf 'base %s\nfa %s\n' "$BASE_SHA" "$FA_SHA" > "$R/approved_commits.txt"
run step0-no-switch-env test -z "${WHYPTOLOGY_EXP3_FA:-}"
# NC data never enters a run directory: nothing private is configured for these runs.
unset PRIVATE_DATA_DIR REVIEWER_KEY || true
run step0-base-exists git cat-file -e "$BASE_SHA^{commit}"
run step0-fa-exists git cat-file -e "$FA_SHA^{commit}"
run step0-fa-parent test "$(git rev-parse "$FA_SHA^")" = "$BASE_SHA"
run step0-fa-one-file test "$(git diff --name-only "$BASE_SHA" "$FA_SHA")" = "app/services/faithful.py"
run step0-fa-one-line test "$(git diff -U0 "$BASE_SHA" "$FA_SHA" | grep -E '^[-+][^-+]')" \
  = "$(printf '%s\n%s' '-EXP3_FA_DEFAULT = False' '+EXP3_FA_DEFAULT = True')"
# "the exact parent commit of the F-a change, after any KRI merge"
run step0-base-contains-main git merge-base --is-ancestor main "$BASE_SHA"
run step0-ho2-committed git cat-file -e "$BASE_SHA:$HO2"
"$PY" --version > "$R/env.txt"
"$PY" -m pip freeze >> "$R/env.txt"

# One detached worktree per arm, at its pinned commit (the corpus is git-lfs).
for ARM in base fa; do
  case $ARM in base) SHA=$BASE_SHA ;; fa) SHA=$FA_SHA ;; esac
  WT=$REPO/.claude/worktrees/exp3-run-$DAY-attempt$N-$ARM
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
  log "stopped after step 0 (EXP3_STOP_AFTER; not a registered run)"
  echo "stopped after step 0 (EXP3_STOP_AFTER)"
  exit 0
fi

# Steps 1-2 - the pinned commands, base arm first, then fa; identical lines in both.
CE=("$PY" scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4 \
  --stage auto --expected-tokens current)
for ARM in base fa; do
  WT=$(cat "$R/$ARM/worktree.txt")
  A=$R/$ARM
  cd "$WT"
  git rev-parse HEAD > "$A/commit.txt"
  shasum -a 256 data/processed/examples.csv > "$A/corpus_sha256.txt"
  run "$ARM-step0" "$PY" scripts/exp3_step0_faithful_queries.py --out-csv "$A/step0.csv" \
    --log "$A/step0_log.txt" --faithful-benchmarks-dir "$A/faithful"
  run "$ARM-faithful-holdout2" "$PY" scripts/exp3_faithful_benchmark_file.py "$HO2" \
    "$A/faithful/faithful_$(basename "$HO2")" > "$A/faithful_holdout2.txt" 2>&1
  for S in v4 holdout1 le_v1 name_v1 holdout2; do
    case $S in
      v4)       F=$B/competitive_ambiguity_eval_queries_v4.csv ;;
      holdout1) F=$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv ;;
      le_v1)    F=$B/competitive_ambiguity_eval_queries_le_v1.csv ;;
      name_v1)  F=$B/competitive_ambiguity_eval_queries_name_v1.csv ;;
      holdout2) F=$HO2 ;;
    esac
    for Q in stored faithful; do
      case $Q in stored) BQ=$F ;; faithful) BQ=$A/faithful/faithful_$(basename "$F") ;; esac
      run "$ARM-$S-$Q-C" "${CE[@]}" --benchmark "$BQ" --exclude-twins 0 \
        --results "$A/${S}_${Q}_C.csv" --failures "$A/${S}_${Q}_C_fail.csv" \
        > "$A/${S}_${Q}_C.txt" 2>&1
      run "$ARM-$S-$Q-T" "${CE[@]}" --benchmark "$BQ" --exclude-twins 0.7 \
        --results "$A/${S}_${Q}_T.csv" --failures "$A/${S}_${Q}_T_fail.csv" \
        > "$A/${S}_${Q}_T.txt" 2>&1
    done
  done
  for M in auto declared; do
    run "$ARM-paste-$M" "$PY" scripts/run_expert_paste_eval.py \
      --queries "$B/expert_paste_queries.csv" --stage "$M" \
      --results "$A/paste_$M.csv" > "$A/paste_$M.txt" 2>&1
  done
  run "$ARM-segmentation" bash -c "\"$PY\" scripts/run_segmentation_eval.py > \"$A/segmentation.txt\""
  if [ "$ARM" = fa ]; then
    run fa-verify-release bash -c "\"$PY\" scripts/verify_release.py --skip-tests > \"$A/verify_release.txt\" 2>&1"
  fi
  (cd "$A" && shasum -a 256 ./*.csv ./*.txt faithful/*.csv > sha256.txt)
done

# Step 3 - the mechanical comparisons the hard gates name (recorded, never a stop:
# the decision is read from these files and the per-query tables afterwards).
cd "$R"
{
  echo "== step 0 output identical between the arms (reads no ranker code)"
  for f in step0.csv step0_log.txt; do cmp "base/$f" "fa/$f" && echo "same $f"; done || true
  for f in base/faithful/*.csv; do cmp "$f" "fa/faithful/$(basename "$f")" && echo "same $(basename "$f")"; done || true
  echo "== corpus sha256"
  cat base/corpus_sha256.txt fa/corpus_sha256.txt
  echo "== stored folded-ASCII queries: per-query results identical, C and T"
  for S in v4 holdout1 le_v1 name_v1 holdout2; do
    for P in C T; do
      if cmp -s "base/${S}_stored_$P.csv" "fa/${S}_stored_$P.csv"; then
        echo "IDENTICAL ${S}_stored_$P.csv"
      else
        echo "DIFFERS   ${S}_stored_$P.csv"
      fi
    done
  done
  echo "== segmentation byte-identical"
  if cmp -s base/segmentation.txt fa/segmentation.txt; then echo IDENTICAL; else echo DIFFERS; fi
} > "$R/gates_mechanical.txt" 2>&1
"$PY" - "$R" > "$R/routing_diff.txt" 2>&1 <<'PYEOF' || log "routing_diff failed (see routing_diff.txt)"
import sys
from pathlib import Path

import pandas as pd

run = Path(sys.argv[1])
print("faithful queries whose stage_used differs between base and fa")
for s in ("v4", "holdout1", "le_v1", "name_v1", "holdout2"):
    for p in ("C", "T"):
        a = pd.read_csv(run / "base" / f"{s}_faithful_{p}.csv", dtype=str, keep_default_na=False)
        b = pd.read_csv(run / "fa" / f"{s}_faithful_{p}.csv", dtype=str, keep_default_na=False)
        m = a.merge(b, on="benchmark_id", suffixes=("_base", "_fa"))
        d = m[m["stage_used_base"] != m["stage_used_fa"]]
        ids = " ".join(f"{r.benchmark_id}({r.stage_used_base or '-'}->{r.stage_used_fa or '-'})" for r in d.itertuples())
        print(f"{s} {p}: {len(d)}/{len(m)} {ids}")
PYEOF
shasum -a 256 gates_mechanical.txt routing_diff.txt run_log.txt > sha256_top.txt

log "ALL STEPS RAN"
echo "all steps ran; results in $R (worktrees kept: see */worktree.txt)"
