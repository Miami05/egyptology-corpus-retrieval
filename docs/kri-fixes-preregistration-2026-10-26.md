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
**content** and not only by the sha of the code that derives it. Step 0 regenerates it and a
mismatch stops the run.

**Training/test hygiene.** Every model the harness builds — the pooled one and each
stage-restricted one — is fitted on the training partition only, and each stage subset is
taken from the *training* frame. No test row is in either side of the pooled/stage
comparison. `tests/test_kri_fixes_eval.py` checks this.

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

**Expected scale, stated in advance.** A 500-row dry run found **3** firing positions, **9**
split cartouches and **38** singleton ties. Extrapolated to 3,473 rows that is of the order
of **20 firing positions**. That is a very small denominator and rule (b2) below is written
for it: the point is recorded now, before the numbers, so that a result based on a handful of
positions cannot later be presented as a measured gain.

## 4. Pass rules

Fixed before the run. Every rule is evaluated on `$R/kri_summary.csv` unless stated.

**(a) Non-firing positions must not lose accuracy beyond the tolerance.**
`acc_other(all_on) ≥ acc_other(all_off) − 0.002`, where `other` is every position that
neither fires nor neighbours a firing one. The tolerance is absolute accuracy and is about
40 positions in roughly 20,000 — chosen before the run as the scale at which a stage-routing
move on a few lines could plausibly land. It is a tolerance, not a target. The paired
`better_than_baseline` / `worse_than_baseline` counts at those positions are reported beside
it. **FAIL stops the run.**

**(b) Firing positions, paired.** `acc_firing(all_on) ≥ acc_firing(all_off)`, reported with
the paired counts (on-better / off-better / unchanged) and with every firing position listed
individually from `$R/kri_positions.csv`. The pooled fallback ships only if this holds.

**(b2) Low-n guard, pre-registered because the dry run says it will bite.** If the number of
firing positions is **< 30**, rule (b) is **reported, not gated**: no claim of improvement
may be made from it, in the results note or to an expert, whichever direction it points. The
branch may still merge on (a), (c) and (e) — those are "nothing else broke" rules — but item
§5.1 of the fixes doc stays open and the feature remains an unvalidated heuristic. This rule
is strictly tighter than (b); it cannot be used to rescue a failing (b).

**(c) Cartouche: no new boundary errors outside cartouches.**
`boundary_errors_outside_cartouche(all_on) ≤ boundary_errors_outside_cartouche(all_off)`,
that being false boundaries plus missed boundaries at positions outside any cartouche span.
Also reported, not gated: boundary precision / recall / F1, exact-segmentation count, and
`cartouches_split` (expected to fall to 0 in the constraint-on arms). **FAIL stops the run.**

**(d) Stage routing: counted and listed.** `stage_changed_vs_baseline` for every arm, and
every changed line listed individually — row id, stage off, stage on, and the per-stage
attested coverage from both — from `$R/kri_lines.csv`. No threshold: this is a rule about
disclosure, not about a number. A run that reports a count without the list fails it.

**(e) Expert paste gate: 8/8 in `auto` and 8/8 in `declared`.** The hard constraint every
segmentation and reading change in this project has had to clear. **FAIL stops the run.**

**(f) Competitive sets, sanity check only.** v4, held-out and LE-v1, legacy (`L`) and
twin-controlled (`T`), at or above the release floors `top3_useful_floor` 0.80 and
`mrr_floor` 0.70 from `data/benchmarks/release_baseline.json`, with **0** top-3 answers lost
against the attempt-2 numbers in `docs/remeasure-results-2026-10-26-attempt2.md`. Stated in
the results note as *not exercising the decoder or the segmenter*: it can only detect
collateral damage, and passing it is not evidence for any of the three features. **FAIL stops
the run.**

**(g) Calibration: reported, never gated.** Reliability bins and the Brier score for the
chosen reading's confidence, for `all_off` (undiscounted share) and `all_on` (with the `/k`
discount), from `$R/kri_summary_calibration.csv`. No pass rule: there is no pre-registered
target for what a confidence *should* read, and inventing one after seeing the bins would be
the thing this document exists to prevent. What the note must say is whether the discount
moved the Brier score and in which direction.

**(h) Stop on any failure.** Stop, record it in `$R/run_log.txt`, fix on a new commit, write
a dated addendum to this document, and re-run **all** of §5 on the new pinned commit. Every
attempt's `$R` is kept, renamed `…-attemptN`, and listed in the results note. **No subset
re-runs and no reuse of a number from a failed attempt** (the A2.9 rule of
`docs/remeasure-preregistration-2026-10-25.md`).

## 5. Exact commands

One heavy process at a time, nothing else running. Every step appends `START`, `END` and
`exit` lines to `$R/run_log.txt`.

```bash
PY=~/venvs/egyptology/bin/python
B=data/benchmarks
R=~/egyptology-runs/kri-fixes-2026-10-26          # outside the repo and outside iCloud
mkdir -p "$R"
log() { echo "$(date -u +%FT%TZ) $*" >> "$R/run_log.txt"; }
run() { log "START $1"; shift; "$@" ; c=$?; log "exit $c"; log "END"; return $c; }
```

**Step 0 — pin everything.**

```bash
run step0-commit git rev-parse HEAD > "$R/commit.txt"
git status --porcelain >> "$R/commit.txt"          # must be empty
shasum -a 256 data/processed/examples.csv scripts/eval_guards.py \
    scripts/run_reading_model_eval.py scripts/run_kri_fixes_eval.py > "$R/shas.txt"
$PY --version > "$R/env.txt"; $PY -m pip freeze >> "$R/env.txt"
```

**Step 1 — the split manifest, checked against §2.**

```bash
run step1-manifest $PY scripts/run_kri_fixes_eval.py \
    --split-manifest "$R/split_manifest.csv" --max-test-rows 1 \
    --positions "$R/_discard_positions.csv" --lines "$R/_discard_lines.csv" \
    --summary "$R/_discard_summary.csv" > "$R/step1.txt" 2>&1
shasum -a 256 "$R/split_manifest.csv" >> "$R/shas.txt"
# must be ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba; a
# mismatch means the split moved and STOPS the run.
```

**Step 2 — the paired harness, all five arms, full test split (~11–12 min).**

```bash
run step2-harness $PY scripts/run_kri_fixes_eval.py \
    --positions "$R/kri_positions.csv" --lines "$R/kri_lines.csv" \
    --summary "$R/kri_summary.csv" \
    --calibration "$R/kri_summary_calibration.csv" > "$R/step2.txt" 2>&1
```

**Step 3 — rules (b) and (d): the individual listings, not just the counts.**

```bash
run step3-listings $PY - <<'PYEOF' > "$R/step3.txt" 2>&1
import pandas as pd, os
R = os.path.expanduser("~/egyptology-runs/kri-fixes-2026-10-26")
positions = pd.read_csv(f"{R}/kri_positions.csv")
lines = pd.read_csv(f"{R}/kri_lines.csv")
firing = positions[(positions["arm"] == "all_on") & (positions["class"] == "firing")]
base = positions[positions["arm"] == "all_off"].set_index(["row_id", "position"])
print(f"(b) firing positions: {len(firing)}")
for _, row in firing.iterrows():
    off = base.loc[(row["row_id"], row["position"])]
    print(f"  {row['row_id']}#{row['position']} stage={row['stage']} gold={row['gold_reading']!r} "
          f"off={off['predicted']!r}({off['correct']}) on={row['predicted']!r}({row['correct']}) "
          f"stage_count={row['stage_attested_count']} pooled_count={row['attested_count']}")
off_lines = lines[lines["arm"] == "all_off"].set_index("row_id")
on_lines = lines[lines["arm"] == "all_on"].set_index("row_id")
moved = [i for i in on_lines.index if off_lines.loc[i, "stage"] != on_lines.loc[i, "stage"]]
print(f"(d) lines whose stage moved: {len(moved)}")
for row_id in moved:
    print(f"  {row_id}: {off_lines.loc[row_id, 'stage']!r} -> {on_lines.loc[row_id, 'stage']!r} "
          f"| coverage off {off_lines.loc[row_id, 'coverage']} | on {on_lines.loc[row_id, 'coverage']}")
PYEOF
```

**Step 4 — rule (e), the expert paste gate.**

```bash
for M in auto declared; do
  run step4-paste-$M $PY scripts/run_expert_paste_eval.py \
      --queries $B/expert_paste_queries.csv --stage $M \
      --results "$R/paste_$M.csv" > "$R/paste_$M.txt" 2>&1
done
```

**Step 5 — rule (f), the competitive sanity check.**

```bash
CE="$PY scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4"
for S in v4 holdout le_v1; do
  case $S in
    v4)      F=$B/competitive_ambiguity_eval_queries_v4.csv ;;
    holdout) F=$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv ;;
    le_v1)   F=$B/competitive_ambiguity_eval_queries_le_v1.csv ;;
  esac
  run step5-$S-T $CE --benchmark $F --stage auto --exclude-twins 0.7 \
      --expected-tokens current --results "$R/${S}_T_auto.csv" \
      --failures "$R/${S}_T_auto_fail.csv" > "$R/${S}_T_auto.txt" 2>&1
  run step5-$S-L $CE --benchmark $F --stage auto --exclude-twins 0 \
      --expected-tokens frozen --results "$R/${S}_L_auto.csv" \
      --failures "$R/${S}_L_auto_fail.csv" > "$R/${S}_L_auto.txt" 2>&1
done
run step5-verify $PY scripts/verify_release.py > "$R/verify_release.txt" 2>&1
```

**Step 6 — the full test suite, once, output kept.**

```bash
run step6-pytest $PY -m pytest -q > "$R/pytest.txt" 2>&1
```

`--benchmark` is always explicit: the competitive harness's own default is the contaminated
v1 set.

## 6. What the results note must contain

A dated note, `docs/kri-fixes-results-2026-10-26.md`, with: the pinned commit and every sha
from step 0; each rule (a)–(h) with PASS / FAIL / REPORTED and the number it was decided on;
the firing-position listing and the stage-change listing in full; the calibration table for
both arms; and a verdict in one line. If (b2) bit, the note says in plain words that the
pooled fallback's own benefit is **unmeasured** and must not be quoted.

## 7. Known limits of this measurement, stated before it runs

1. **The firing sample is tiny** (§3) and the split has no Ramses or AES rows left in it, so
   the stage mix the pooled fallback depends on is narrower than production's.
2. **The reading track uses gold groupings.** It measures reading, not reading-after-
   segmentation; the cartouche constraint reaches it only through the stage router. A
   combined end-to-end number would need the §4e-style strict rule and is not attempted here.
3. **Nothing here measures the KRI material**, which is private and excluded. The
   pre-registered KRI test of `docs/plan-data-cleanup-2026-10-26.md` §4d/§4e is separate and
   unaffected by this document.
4. **The decode still prefers the singleton on the traced positions** (`docs/kri-selftest-
   fixes-2026-10-26.md` §1, the transition-smoothing defect). This measurement cannot fix
   that and is not designed to detect it; if (b) comes out flat, that is the most likely
   reason.
