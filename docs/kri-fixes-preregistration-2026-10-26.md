# Pre-registration — measuring the KRI self-test fixes (2026-10-26)

What is being measured: the three changes of `docs/kri-selftest-fixes-2026-10-26.md`, on
branch `kri-fixes-2026-10-26`. This document is written and committed **before** the run.
Nothing below is a result.

```
pooled fallback   ReadingModel.uses_pooled_evidence — a stage-restricted model reads a
                  group whose stage evidence the filter emptied from the pooled counts
singleton /k      ReadingPrediction.confidence divides the chosen reading's share by the
                  number of readings tied with it on one attestation each
cartouche         Segmenter.segment forbids a boundary inside a matched cartouche
```

---

## 1. The constants are taken as they are, not tuned

`POOLED_FALLBACK_MAX_STAGE_COUNT = 3`, `POOLED_FALLBACK_MIN_POOLED_COUNT = 20`,
`POOLED_FALLBACK_MIN_RATIO = 10.0`, and the `/k` discount rule, are **exploratory
heuristics**. They were reasoned from one traced failure on ten non-expert lines of private
material (3 stage attestations against 37 pooled, a ratio of 12.3) and were **not fitted on
any evaluation split**. No sweep was run, and none is run here: this measurement asks
whether the heuristics as written do harm, not which values are best.

If they pass, they ship **as heuristics**, and the results note says so in those words. A
sweep remains an open item (`docs/kri-selftest-fixes-2026-10-26.md` §5.1) and would need its
own pre-registration with the grid fixed in advance.

The cartouche rule is not a tuned constant at all: it is a corpus fact (1,841 of 1,854
groups containing either cartouche sign hold a matched pair whole), counted before the rule
was written, and recorded in `app/data/normalizer.py`.

## 2. The split: existing, untouched, and pinned by content

The measurement uses the test split that `scripts/run_reading_model_eval.py` already
defines — `select_test_rows(..., split_by="text")` with that script's own defaults — and
`scripts/run_kri_fixes_eval.py` calls that same function rather than defining a split of its
own. Whole texts are held out (AES text id, Ramses' official test split; TLA and BBAW rows
have no text identity and are split by sentence — a limitation that script already prints),
exact duplicates and near-duplicates at Jaccard ≥ 0.8 are dropped, and the lexicon-leaking
sources (Ramses, AES) leave the test split while staying in training.

**It is untouched by this branch.** The split predates the branch (audit A56), no threshold
here was chosen with reference to it, and nothing in this branch changes `eval_guards.py`,
`run_reading_model_eval.py` or the corpus. The three constants come from private KRI material
that is not in the corpus at all.

Identity, recorded at step 0 and reproduced here so a reader can check it:

| | |
| --- | --- |
| corpus `data/processed/examples.csv` | sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2`, 130,472 rows |
| aligned sentences | 59,504 |
| train / test | 52,210 / 3,473 |
| dropped from test | 829 exact duplicates, 202 near-duplicates, 2,790 lexicon-leaking rows |
| test source mix | BBAW 1,013, TLA 2,460 |
| `scripts/eval_guards.py` | sha256 `17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950` |
| `scripts/run_reading_model_eval.py` | sha256 `373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5` |
| test-split manifest (`--split-manifest`) | sha256 `ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba` |

The manifest is the identity of every test row written to a file, so the split is pinned by
**content** and not only by the sha of the code that derives it. Step 1 regenerates it and a
mismatch stops the run.

**Training/test hygiene.** Every model the harness builds — the pooled one and each
stage-restricted one — is fitted on the training partition only, and each stage subset is
taken from the *training* frame. No test row is in either side of the pooled/stage
comparison. `tests/test_kri_fixes_eval.py` checks this.

**What that does not establish.** Training-frame separation is not full independence of
the evidence. The harness runs with the Helsinki lexicon on, as the app does, and the
inherited evaluator already marks BBAW's lexicon-assisted numbers as **not held-out**
(`LEXICON_TAINTED_SOURCES` in `run_reading_model_eval.py`); BBAW contributes 1,013 of the
3,473 test rows. The split stays frozen as it is (changing it now would be a new
registration), the harness writes every aggregate also per source (`scope =
source:BBAW` / `source:TLA` in `kri_summary.csv`), and **no aggregate from this run may be
described as an independently held-out validation**.

## 3. Why a new harness, and what it cannot do

Nothing already in the repository can see these changes.

* The competitive sets (v4, held-out, LE-v1) are **retrieval and suggestion** evaluations.
  They never call `ReadingModel.predict_sequence` or `Segmenter.segment`. Re-running them
  cannot validate this branch; it can only show that nothing else broke. Rule (f) below is
  labelled a sanity check for exactly that reason.
* `scripts/run_reading_model_eval.py` trains one model on the training split and never
  attaches a pooled model to it, so `uses_pooled_evidence` returns False there by
  construction and the pooled fallback can never fire.

`scripts/run_kri_fixes_eval.py` is the measurement. Five arms — `all_off`, `pooled_only`,
`discount_only`, `cartouche_only`, `all_on` — over the same split, stage-aware, writing one
row per position and one per line.

**Cohorts are per position.** A position is `firing` if the pooled fallback fires there in
any pooled arm (`pooled_only` or `all_on`; the union, because the two route with different
cartouche settings), `neighbour` if it is next to a firing position and does not fire
itself, and `other` otherwise. A position keeps that class in **every** arm, `all_off`
included, so every comparison below is paired over the same positions, joined on
`(row_id, position)`. An empty cohort's rate is blank, never 0.

**Three confidence numbers per position.** `confidence_legacy` is what shipped before this
branch: the leading candidate's score over the displayed top five. `confidence_undiscounted`
is the corrected number from `be24b96` #1, the chosen reading's share of the full
distribution. `confidence_discounted` is that number with the `/k` discount. `all_off`
reproduces the pre-branch **predictions**, but not the pre-branch **confidence**. That is why
the legacy number is recorded separately.

**Expected scale, and what was seen before these rules were fixed.** This is a
**pilot-informed** registration, not an untouched confirmatory one. Before the rules were
written, the harness was dry-run on the **first 25 and the first 500 rows of this same test
split** (and the reviewers ran 50 rows, on the same split, during the review of this
document). Those console summaries printed, per arm, `acc_all`, the firing count and its
accuracy, neighbour and other accuracy, the better/worse counts against `all_off`,
segmentation F1, the split-cartouche count and the stage-move count. Under the old
per-arm cohorts, the firing accuracy of `all_off` printed 0 by construction. The numbers
the registration used were: 3 firing positions, 9 split cartouches (0 with the constraint
on), segmentation F1 0.9092 → 0.9103 and 38 singleton ties, all on 500 rows; the 50-row
review run changed 0 positions outside the firing cohort. The round-1 fixes re-ran the same
first 50 rows with the shared cohorts, and that run printed every gate line of step 3. It
had 0 firing positions, 0 changed positions and 0 stage moves, and the Brier lines of (g)
showed the discount lowering the score by about 0.0017. **Every other printed number
must be treated as seen.** The first 500 rows are part of the evaluation split, and the
results note says so beside every number.

Extrapolated to 3,473 rows, 3 firing positions in 500 rows is of the order of **20 firing
positions**. Rule (b) is written for that denominator.

## 4. Pass rules

Fixed before the run. Every rule is evaluated by `scripts/check_kri_fixes_gates.py` on the
files in `$R`, and the step that evaluates it exits non-zero on a gated failure. Gates are
decided on **integer counts**, never on a rounded rate. The budgets are constants in that
script and must match the numbers here.

**(a) Collateral harm: engineering loss budgets.** This applies to `all_on` and to
`cartouche_only`, each paired with `all_off`. `cartouche_only` is included because it is
the configuration that ships if (b) disables the pooled fallback; the discount moves no
prediction. All three budgets must hold:

* `other` positions: `other_worse − other_better ≤ 5`
* `neighbour` positions: `neighbour_worse − neighbour_better ≤ 2`
* whole lines: `lines_exact_lost − lines_exact_gained ≤ 3`

These are **engineering loss budgets, not statistical non-inferiority margins**. They are
set against the size of what the change can gain. The pooled fallback is expected to act
on about 20 positions in about 20 lines (§3). Outside the firing cohort and its
neighbours, only a routing move or a Viterbi effect two or more positions away can change
an outcome, and the 50-row review run changed none. A configuration that loses, net, more
than a quarter of its own target scale in positions it does not target (5), more than about
5 % of the about 40 neighbours (2), or more than 3 whole lines, is not worth carrying as an
unvalidated heuristic, whatever it gains. The earlier accuracy tolerance (−0.002, about
45 positions) is withdrawn. It was looser than the whole expected effect.

The exact sign-test p-value of the discordant pairs is reported beside each count, as
uncertainty. **A pass shows that the harm stayed within the budget. It is not evidence of
an improvement.** **FAIL stops the run.**

**(b) Firing positions: one decision rule, paired.** On the firing cohort, `all_on` against
`all_off`: the on-better, off-better and unchanged counts, the number of distinct lines,
the exact two-sided sign test over positions (reported only), and the same counts and
test over **firing lines**: a firing line is on-better if its firing positions gained more
than they lost against `all_off`, off-better if they lost more, and tied otherwise. Every
firing position is listed individually. The decision, applied in this order:

1. **No firing position:** the feature was not exercised. It ships as an unvalidated
   heuristic, and the note says its effect is **unmeasured**.
2. **off-better > on-better, at any n:** the pooled fallback is **disabled.**
   `use_pooled_fallback` must default to off before this branch merges, in a follow-up
   commit the results note names. This is the harm criterion. Low n does not suspend it.
3. **on-better ≥ off-better, with at least 30 firing positions in at least 20 distinct
   lines, on-better > off-better in positions, on-better > off-better in lines, and the
   line-level sign-test p < 0.05:** it ships, and the improvement may be stated, with the
   paired position and line counts and the line-level p.
4. **Otherwise:** it ships as an **unvalidated heuristic**. No harm was measured, but no
   improvement may be claimed, in the results note or to an expert, in either direction.
   §5.1 of the fixes doc stays open.

The 20-line condition and the line-level test exist because 30 positions are not 30
independent observations when several sit in one line: positions in one line share one
routing choice and one decode. The claim is therefore tested with the line as the unit.
The position-level p is printed beside it, but no decision reads it. (b) is a **decision**, not a stop: its outcome is recorded
and the run continues. That is why (a) and (c) are also gated on `cartouche_only`.

**(c) Cartouche: no new boundary errors outside cartouches.** For `all_on` and for
`cartouche_only`: `boundary_errors_outside_cartouche(arm) ≤
boundary_errors_outside_cartouche(all_off)`. These are false boundaries plus missed
boundaries at positions outside any cartouche span. Also reported, not gated: boundary
precision / recall / F1, the exact-segmentation count, `cartouches_split` (cartouches with at
least one predicted boundary inside, expected to fall to 0 with the constraint on) and
`boundaries_inside_cartouches`. **FAIL stops the run.**

**(d) Stage routing in the harness: counted and listed.** For every arm,
`stage_changed_vs_baseline` and every changed line, listed individually: row id, stage
off, stage on, and the per-stage attested coverage from both. Stages are compared as
strings, so a line the router left unset in both arms is not a move. No threshold: this
is a rule about disclosure, not about a number. A listing whose length differs from the
summary's count stops the run.

**(e) Expert paste gate: 8/8 in `auto` and 8/8 in `declared`.** Every segmentation and
reading change in this project has had to clear this constraint. **FAIL stops the run.**

**(e2) Urk. IV / St Andrews gate, both modes.** This is
`check_standrews_urkiv_gate.py --private-dir "$PRIV"` in `auto` and in `declared`,
exactly as A2.2′ of the 2026-10-25 pre-registration (A7) defines it. It has rejected a
segmentation-adjacent change before (lexicon weight 0.39), and the cartouche constraint
changes segmentation and routing. Its own exit code decides: `GATE: PASS` or the run
stops. Its logs stay in `$R`.

**(e3) Held-out stage routing.** This is `run_stage_routing_eval.py --seed 20261025
--per-stage 200`, the A2.3 sample. A2.3's own rule (Earlier → Demotic and Late → Demotic
both 0/200) is gated by the script's exit code. Against attempt 2's
`routing.csv`, the sample must be the same pastes; a different sample stops the run.
Every paste whose chosen stage changed is listed, but changes are not gated.

**(f) Competitive sets, sanity check only.** v4, held-out and LE-v1, legacy (`L`, frozen
tokens, no twin control) and twin-controlled (`T`, `--exclude-twins 0.7`, current tokens),
`--stage auto`.

* **Zero top-3 answers lost, by query identity.** Each run's per-query
  `top3_useful_family_hit` is joined on `benchmark_id` with the attempt-2 file of the same
  name in `~/egyptology-runs/remeasure-2026-10-25/` (`{v4,holdout,le_v1}_{T,L}_auto.csv`).
  A query true there and false here is a loss. Gains and every `useful_family_rank` change
  are listed. An unchanged aggregate does not count, because a loss and a gain can cancel.
* **Release floors on their designated configuration only:** v4 T-auto, `top3_useful_floor`
  0.80 and `mrr_floor` 0.70 (`release_baseline.json`, `twin_controlled`). Held-out and
  LE-v1 have no floors. Their attempt-2 numbers (held-out L 0.75 / 0.6750, T 0.75 /
  0.6667; LE-v1 L 0.8667 / 0.80, T 0.8667 / 0.80) are reported beside this run's.
* **Determinism.** `verify_release.py --skip-tests` must print the same top-3, MRR and
  failure count as this run's v4 L-auto and v4 T-auto, and the same paste count as
  paste-auto. Its own per-query CSVs are temporary files it deletes, so the comparison is
  on the printed aggregates, kept in `verify_release.txt`. Its exit code (READY) is also
  gated.

The results note states that (f) does **not exercise the decoder or the segmenter**. It
can only detect collateral damage, and passing it is not evidence for any of the three
features. **FAIL stops the run.**

**(g) Calibration: reported, never gated.** The reliability bins and Brier score for each arm
and each confidence number, over all positions and over positions with a reading
(`subset = with_reading`). A no-reading position at confidence 0 is "perfectly calibrated",
so including it flatters the score. Three comparisons are reported separately:

* the **discount** effect: `discount_only` discounted against `all_off` undiscounted. The
  predictions are the same, so only the discount differs.
* the **correction** effect: `all_off` undiscounted against `all_off` legacy.
* the **combined** effect: `all_on` discounted against `all_off` legacy. This includes the
  pooled fallback's and the routing's prediction changes, so it attributes nothing to
  `/k`.

There is no pass rule. No target for what a confidence *should* read was registered, and
inventing one after seeing the bins would be the thing this document exists to prevent.
The note must say whether the discount moved the Brier score and in which direction.

**(h) Stop on any failure, mechanically.** Every step runs through `run` in the runner
below. Any non-zero exit (a failed gate, a pinned sha that does not match, a dirty tree, a
missing input, a HEAD that is not the approved commit) is logged in `$R/run_log.txt` and **ends the run**. After a stop: fix it on a
new commit, write a dated addendum to this document, and re-run **all** of §5 on the new
pinned commit. Each attempt gets its own `…-attemptN` directory, allocated fresh by the
runner (an existing directory is never reused, so no evidence is overwritten), and every
attempt is listed in the results note. **No subset re-runs, and no reuse of a number from a
failed attempt** (the A2.9 rule of `docs/remeasure-preregistration-2026-10-25.md`).

## 5. Exact commands

The commands are `scripts/run_kri_fixes_prereg.sh`, reproduced verbatim below.
`tests/test_check_kri_fixes_gates.py` fails if the two differ. Run it with **bash**:

```
cd /Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/kri-fixes-2026-10-26
bash scripts/run_kri_fixes_prereg.sh APPROVED_SHA
```

`APPROVED_SHA` is the full 40-character id of the commit the approver signed off on for
this run, written in the approval and copied into the results note. It is the one input
the runner takes, and without exactly one 40-hex argument it exits 2 before allocating
an attempt directory. It enters the worktree itself and asserts the toplevel, the branch,
that `HEAD` **is** `APPROVED_SHA`, and a clean tree. Together, the last two fix every
tracked file, the harness, the checker and the runner included. The shas in `shas.txt`
are recorded so the note can quote them. Use bash because zsh does not word-split, and
the command arrays need bash. Run one heavy process at a time, with nothing else running.
The registered run sets neither `KRI_RUNS_BASE` nor `KRI_STOP_AFTER`.

```bash
#!/usr/bin/env bash
# The exact command list of docs/kri-fixes-preregistration-2026-10-26.md §5.
# Run it as:   bash scripts/run_kri_fixes_prereg.sh APPROVED_SHA
# APPROVED_SHA is the full 40-character commit id the approver signed off on for this
# run. Step 0 stops unless HEAD is exactly that commit (a different clean commit on the
# branch, with different code, must not be able to run as the registered one).
# (bash, not zsh: zsh does not word-split, and this file is the registered commands).
# tests/test_check_kri_fixes_gates.py checks that §5 reproduces this file verbatim.
#
# Two environment variables exist ONLY to prove steps 0-1 run before the registered run
# (a dry check into a scratch directory). The registered run sets neither:
#   KRI_RUNS_BASE   parent directory of the attempt directory (default ~/egyptology-runs)
#   KRI_STOP_AFTER  stop cleanly after this step number (default: run every step)
set -euo pipefail

if [ "$#" -ne 1 ] || ! [[ "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: bash scripts/run_kri_fixes_prereg.sh APPROVED_SHA (the full 40-hex commit id)" >&2
  exit 2
fi
APPROVED_SHA=$1

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
echo "$APPROVED_SHA" > "$R/approved_commit.txt"
run step0-approved-commit test "$(git rev-parse HEAD)" = "$APPROVED_SHA"
run step0-clean test -z "$(git status --porcelain)"
run step0-private-dir test -d "$PRIV"
run step0-attempt2-dir test -d "$BASE"
# The deploy tests trap HUP/INT/TERM; a signal ignored at launch (nohup, `cmd &`) cannot be
# trapped again, so those tests would fail for the launcher, not the code (attempt 3).
run step0-signals "$PY" -c "import signal, sys; sys.exit(any(signal.getsignal(s) == signal.SIG_IGN for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)))"
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
```

`--benchmark` is always explicit: the competitive harness's own default is the contaminated
v1 set.

## 6. What the results note must contain

The note is a dated file, `docs/kri-fixes-results-2026-10-26.md`. It must contain:

* the attempt directory, the approved commit (`approved_commit.txt`, equal to
  `commit.txt`) and every sha from step 0;
* each rule (a)–(h) marked PASS, FAIL, DECISION or REPORTED, with the integer counts it was
  decided on, the source-stratified counts beside the aggregates, and the step-3, -6, -7
  and -8 gate files quoted;
* for (b), the firing-line counts and the line-level p beside the position counts;
* the firing-position listing, the harness stage-change listing and the routing-change
  listing, in full;
* the calibration table for the three comparisons of (g);
* a verdict in one line.

If (b) did not reach outcome 3, the note says in plain words that the pooled fallback's
own benefit is **unmeasured** and must not be quoted. The note also says that this was a
pilot-informed registration (§3) and that no number from it is independently held-out
(§2).

## 7. Known limits of this measurement, stated before it runs

1. **The firing sample is tiny** (§3), and the split has no Ramses or AES rows left in it.
   The stage mix the pooled fallback depends on is therefore narrower than production's.
2. **The reading track uses gold groupings.** It measures reading, not
   reading-after-segmentation. The cartouche constraint reaches it only through the stage
   router. A combined end-to-end number would need the §4e-style strict rule and is not
   attempted here.
3. **The harness router gets the gold-spaced paste**, and its spaces act as hints. The
   cartouche constraint therefore rarely gets to change the routing segmentation there,
   and `stage_changed_vs_baseline` understates the routing effect on real pastes that are
   unspaced or spaced by quadrat. (e2) and (e3) route real pastes and partly cover this;
   an unspaced-routing arm is not attempted.
4. **Nothing here measures the KRI material**, which is private and excluded. The
   pre-registered KRI test of `docs/plan-data-cleanup-2026-10-26.md` §4d/§4e is separate
   and unaffected by this document. That file is on `main` since `ac9158a`, after this
   branch's base `3465478`, so it is not in this worktree.
5. **The decode still prefers the singleton on the traced positions**
   (`docs/kri-selftest-fixes-2026-10-26.md` §1, the transition-smoothing defect). This
   measurement cannot fix that and is not designed to detect it. If (b) comes out flat,
   that is the most likely reason.
6. **Pilot-informed, and not independently held-out** (§2, §3). The first 500 test rows
   were decoded before the rules were fixed, and BBAW's lexicon-assisted numbers are not
   held-out.
7. **Branch base.** `main` has moved on since `3465478` (`ac9158a` adds docs). The branch
   deletes nothing. A `diff main..HEAD` shows those docs as deletions only because of the
   older base. Merge, do not overwrite.

## Revision log

**2026-10-26, round 1, before any full run** (Opus + Astra review of `5d8fe73`). This
document had not been run, so it was edited in place, not amended.

* **Cohorts** (both reviews, blocker). These were per arm, so `acc_firing(all_off)` was
  0/0 and read as 0.0, (b) could never fail, and (a) compared different populations. They
  are now per position and shared by all arms (§3), every comparison is paired on
  `(row_id, position)`, an empty cohort is blank, and gates read integer counts.
* **Confidence baseline** (both, blocker / should_fix). `all_off` did not reproduce the
  pre-branch confidence. `confidence_legacy` was added, and (g) now separates the
  discount, the correction and the combined effect. The Brier score is also reported
  without no-reading positions.
* **(b)/(b2)** (both, blocker / should_fix). The two rules contradicted each other. They
  are replaced by one ordered decision rule, with a harm criterion that low n does not
  suspend and a separate, stricter condition for claiming an improvement (≥ 30 positions,
  ≥ 20 lines, p < 0.05).
* **(a)** (both, should_fix). The −0.002 accuracy tolerance (about 45 positions) was
  looser than the whole expected effect. It is replaced by paired net-loss budgets on
  `other`, `neighbour` and whole lines, justified as engineering budgets, with sign-test
  p reported.
* **(f)** (Astra, blocker; Opus, should_fix). The v4 floors were applied to held-out and
  LE-v1, which fail them unchanged. Floors now apply to v4 T-auto only. "Zero answers
  lost" is checked per query against the named attempt-2 files, and verify_release's
  determinism check is restored.
* **(h) and §5** (both, blocker / should_fix). Stopping was a comment, `$CE` failed under
  zsh, there was no worktree assertion, step 3 hard-coded `$R`, and blank stages read as
  NaN. §5 is now an executable bash runner that asserts the worktree, branch, clean tree
  and pinned shas, stops on any non-zero exit, and allocates a fresh attempt directory.
  `scripts/check_kri_fixes_gates.py` evaluates every gate (reading CSVs with
  `keep_default_na=False`, reconciling listings against the summary), and a test pins the
  doc block to the runner.
* **Missing gates** (Opus, should_fix). (e2) is the Urk. IV / St Andrews gate in both modes,
  and (e3) is the held-out stage routing compared with attempt 2.
* **verify_release** (both). It now runs with `--skip-tests`, so pytest runs once (step 9).
* **Disclosure** (Astra, should_fix; Opus, nit). The pilot rows and the printed numbers are
  stated (§3). The BBAW lexicon limitation is stated, with source-stratified output (§2).
  The gold-spaced routing limit is §7.3.
* **Nits.** `cartouches_split` now counts cartouches, and the old quantity is
  `boundaries_inside_cartouches`. The `plan-data-cleanup` pointer now names where that file
  lives. The branch-base note is §7.7.
* **Test** (Astra, should_fix). The router-isolation test in `tests/test_stage.py` was
  vacuous: an ASCII paste normalises to nothing. It now uses a real sign and asserts both
  stages are scored. It fails if the router decodes with the pooled fallback on.

**2026-10-26, round 2, before any full run** (Astra re-check of `a39cf4c`). Still not
run, so edited in place again.

* **(b) claim unit** (should_fix). The 20-line condition did not stop correlated
  positions from producing a false significance: 20 gains in one line plus 19 unchanged
  firing lines gave a position-level p of 2 × 10⁻⁶ and "improvement may be stated",
  while the line-level sign test gives p = 1.0. The claim is now decided on a sign test
  over firing lines. A line's firing positions are netted, and on-better lines must also
  outnumber off-better lines. The position-level p is reported only. The harm criterion
  (outcome 2) is unchanged and still reads positions, because that is the stricter
  direction. `check_kri_fixes_gates.py` recomputes the line counts from
  `kri_positions.csv` and stops if their total disagrees with the summary's
  `firing_lines`. A test reproduces Astra's case.
* **Approved commit** (should_fix). HEAD and the file shas were recorded but never
  asserted, so any other clean commit on the branch would have passed step 0. The
  runner now takes the approved commit id as its one argument. Without exactly one
  40-hex id it refuses to start, and `step0-approved-commit` stops the run unless HEAD
  is that commit. Tests cover both.
* **Verification gap** (Astra could not create temporary directories in its sandbox).
  The fixture-based tests of this file's two test modules and steps 0–1 of the runner
  (`KRI_RUNS_BASE` set to a scratch directory, `KRI_STOP_AFTER=1`) were run outside the
  sandbox before the registered run. The release aggregate check stays step 8 of the
  registered run itself.

**2026-10-26, round 3, before any full run** (Astra re-check of `c5ee5b4`). Still not
run, so edited in place again.

* **Step 9 would have failed** (should_fix). `tests/test_verify_release.py` asserted
  that the committed `data/benchmarks/release_baseline.json` has no
  `expected_corpus_sha256`, but the baseline now pins it (the same corpus sha as §2), so
  the registered pytest step would have stopped the run. The test now reads the pinned
  hash from the baseline, checks it is 64 hex characters, and still requires that a
  shortened benchmark (18 rows, 18 queries) fails and the full 20 passes. It also
  checks that a different corpus hash is rejected against the pin.
* **Verification gap** (Astra's sandbox could not create temporary directories). The
  fixture tests of `tests/test_verify_release.py` and `tests/test_check_kri_fixes_gates.py`
  ran outside that sandbox, and steps 0–1 of the runner ran on the committed revision
  into a scratch `KRI_RUNS_BASE` with `KRI_STOP_AFTER=1`. The release aggregate check
  needs the full competitive and paste evaluations, so it is still verified only by
  step 8 of the registered run. Its parsing and floor logic are covered by the fixture
  tests.

## Addendum 2026-10-27 — after attempt 1

Appended after attempt 1 ran and failed. Everything above this heading is unchanged and
stays the registration. This addendum adds nothing to the rules: it records what failed,
what was changed on new commits and why, and what attempt 2 runs.

### What failed

Attempt 1 ran §5 at the approved commit `1733c165e23c017d0c121e7c9b9809f67c325b8e` into
`~/egyptology-runs/kri-fixes-2026-10-26-attempt1` and **stopped at step 3**. Gated rule
(c) failed for `all_on` and for `cartouche_only`: 3,300 boundary errors outside
cartouches against 3,299 for `all_off`. The +1 is one line, TLA:1980 (outside false
boundaries +1, inside −2). Steps 4–9 did not run, so (e), (e2), (e3) and (f) have no
result. Rule (a) passed; rule (b) decided **DISABLE** (37 firing positions, on-better 4,
off-better 7); (g) reported the `/k` discount raising the Brier score (+0.000117323 over
all positions). The results note, `docs/kri-fixes-results-2026-10-26.md` (`6b66d34`,
corrected in `e4ecab9`), records it. **Attempt 1 stays FAILED, and no number from it is
reused.**

### What changed, and why

1. **Rule (b) outcome 2: the pooled fallback defaults to off** — commit `97ddff2`.
   Outcome 2 requires that "`use_pooled_fallback` must default to off before this branch
   merges, in a follow-up commit the results note names"; this is that commit.
   `app/services/reading_model.py` gains `USE_POOLED_FALLBACK_BY_DEFAULT = False`, and
   `predict_sequence` / `predict_sequence_scored` take `use_pooled_fallback=None`,
   meaning that default. The code, the `POOLED_FALLBACK_*` constants and `attach_pooled`
   stay; `app.services.stage.build_stage_resources` still attaches the pooled model, so
   the fallback is available but used only when a caller passes `True`. The stage
   router already passed `False`. Tests assert it is off by default (on the model and
   through `build_stage_resources`) and that passing `True` still reads pooled.
2. **The cartouche constraint's candidate window** — commit `43fbecb`. Two independent
   post-run diagnoses (Opus and Astra, re-decoding TLA:1980 from the run commit's code)
   both classified the failure as an **implementation defect**, with the same numbers.
   `Segmenter.segment` counted its 10-glyph candidate window in raw glyphs; the
   constraint forbids every start inside a cartouche; and the only extra candidate was
   the span that is *exactly* the cartouche. A group holding a cartouche longer than the
   window plus a neighbouring sign was therefore never proposed, and every path had to
   cut at the cartouche's edge. On TLA:1980 (cartouche [12, 24)) that forced a new false
   boundary at 24, and `segment` returned −126.3658 while `score_segmentation`, the same
   objective, scores the legal grouping without that cut at −122.0077. The optimiser
   failing to find the best legal grouping breaks the invariant `score_segmentation`
   documents. The fix is general: the window is measured in units, a complete cartouche
   counting as one unit. With no cartouche in the stream it is exactly the old window,
   and the harness's constraint-off arms (which blank `cartouche_spans`) take that path,
   so `all_off`, `pooled_only` and `discount_only` segment exactly as before. Weights,
   forbidden interior cuts, the known-long-group candidates and the hint veto are
   unchanged. Seven synthetic tests (a cartouche of 11, 12 or 15 glyphs with one sign
   on its left or right, under a constant boundary prior; and a 15-glyph line on an
   attested toy corpus) fail before the fix and pass after; none uses TLA:1980.
   **TLA:121 is a different case and is not changed**: its gold cuts inside a matched
   cartouche (at 7, in [4, 11)), so the constrained decoder cannot produce that
   boundary by design, and no legal grouping scores better than the one chosen. That
   loss is a consequence of the rule, not a defect, and is not gated by (c).
   Whether attempt 2 passes (c) is not known in advance; the fix changes every line with
   a cartouche longer than the window, so no attempt-1 count carries over.
3. **A test double that step 9 would have stopped on** — commit `744d10b`. Two recording
   doubles in `tests/test_batch2_ranking.py` did not accept the `use_pooled_fallback`
   keyword the stage router has passed since the KRI self-test fixes, so 11 tests
   failed with `TypeError` at `1733c16`. Attempt 1 never reached step 9, so this did not
   affect it. Test-only change.
4. **The singleton `/k` discount is left as it is.** (g) is reported, never gated, and
   no target was registered. Attempt 1 measured it raising the Brier score by
   +0.000117323 (all positions) and +0.000118036 (with a reading); that is recorded,
   and nothing is changed because of it.

### What did not change

No rule, budget, threshold, constant, split, arm definition or command changed. §4 and
§5 stand as written; `scripts/check_kri_fixes_gates.py` and
`scripts/run_kri_fixes_prereg.sh` are byte-identical to `1733c16`. The runner has no
hard-coded commit pin to update: it takes the approved commit as its one argument and
asserts `HEAD` equals it at step 0. No change above was chosen to make a rule pass; the
cartouche fix is justified by the optimality invariant on synthetic input, not by the
gate count.

### Arms in attempt 2

The five arms are unchanged and still toggle each feature. The harness passes
`use_pooled_fallback=arm.pooled` explicitly on every decode, so `pooled_only` and
`all_on` still run the pooled fallback **on**, and the other three run it off, exactly
as in attempt 1; the change of the shipped default does not reach the harness. What
changed is only which configuration ships: with the fallback off by default, the shipped
reading configuration corresponds to `cartouche_only` with the `/k` discount. That is
why (a) and (c) were already gated on `cartouche_only` as well as `all_on` (§4a). Rule
(b) is decided afresh in attempt 2 by the unchanged rule; whether the default is
switched back on after attempt 2 is the lead's decision, not this addendum's.

### Attempt 2

* **Run commit:** the commit that adds this addendum. It is passed to the runner as
  `APPROVED_SHA` (`bash scripts/run_kri_fixes_prereg.sh APPROVED_SHA`) and its full
  id is copied into the attempt-2 results note.
* **Run directory:** `~/egyptology-runs/kri-fixes-2026-10-26-attempt2`, allocated fresh
  by the runner; attempt 1's directory is not touched.
* **Scope:** all of §5, steps 0–9. No subset re-run, no reuse of an attempt-1 number.
* **Before the run:** the test files touched by these commits were run one file at a
  time, and steps 0–1 of the runner ran on the run commit into a scratch
  `KRI_RUNS_BASE` with `KRI_STOP_AFTER=1`.

## Addendum 2026-10-27 (2) — attempts 2 and 3 did not finish; attempt 4

### Attempt 2: interrupted, not decided

Attempt 2 ran on `6b616c4` into `~/egyptology-runs/kri-fixes-2026-10-26-attempt2`. Steps 0–8
logged `exit=0`; step 9 (`pytest`) was cut off at about 55% when the Mac went to sleep, and
`run_log.txt` ends at `START step9-pytest` with no `END`. A run with no verdict for every step
is not a registered result: attempt 2 is recorded as **interrupted**, neither passed nor failed,
and none of its numbers is reused.

### Attempt 3: FAILED at step 9, caused by how it was launched

Attempt 3 ran on the same commit into `…-attempt3`. Steps 0–8 logged `exit=0` again; step 9
failed with 2 of 1,582 tests:
`tests/test_audit_ops.py::test_an_interrupted_deploy_rolls_back_and_leaves_no_marker[HUP]` and
`[INT]` (`[TERM]` passed). Attempt 3 stays **FAILED** under rule (h).

Cause, reproduced: attempt 3 was started as `nohup caffeinate -dims bash … &`. `nohup` sets
SIGHUP to ignored and a non-interactive `&` sets SIGINT to ignored; a signal ignored when bash
starts cannot be trapped again, so the deploy script's HUP/INT traps never ran in those tests.
The same three tests run the same way (`nohup … &`) fail in the same two cases; run normally,
they passed 25 times out of 25, also under CPU load. No product code or test changed.

### What changed

Only the runner: a new step-0 check, `step0-signals`, stops the run before anything is measured
if SIGHUP, SIGINT or SIGTERM is ignored. Rules, gates, arms, harness and every other step are
unchanged. Attempt 4 is launched with default signal dispositions in its own session (so the
Claude session ending cannot hang it up), under `caffeinate -dims`.

### Attempt 4

* **Run commit:** the commit that adds this addendum, passed as `APPROVED_SHA`.
* **Run directory:** the next fresh `~/egyptology-runs/kri-fixes-2026-10-26-attemptN`
  (attempt 4); attempts 1–3 are not touched.
* **Scope:** all of §5, steps 0–9. No subset re-run, no reuse of an attempt-2 or attempt-3 number.

## Addendum 2026-10-27 (3) — attempt 4 FAILED at step 9; attempt 5

Attempt 4 ran on `eae95cd` into `…-attempt4`. Steps 0–8 logged `exit=0`, and the deploy
signal tests that failed attempt 3 passed. Step 9 failed with 1 of 1,575 tests:
`tests/test_check_kri_fixes_gates.py::test_the_preregistration_reproduces_the_runner_verbatim`.
§5 of this document is the runner, verbatim, and addendum (2) added `step0-signals` to
`scripts/run_kri_fixes_prereg.sh` without adding it to the §5 copy. Attempt 4 stays **FAILED**
under rule (h).

**What changed:** the same three lines (two comment lines and `run step0-signals …`) are now in
§5's copy, so §5 and the runner are identical again. Nothing else changed. Before attempt 5 the
full test suite was run once on the run commit and passed.

**Attempt 5:** run commit = the commit that adds this addendum, passed as `APPROVED_SHA`; the
next fresh attempt directory; all of §5, steps 0–9; no number from attempts 2–4 is reused.
