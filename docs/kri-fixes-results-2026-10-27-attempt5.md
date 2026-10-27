# KRI fixes: pre-registered measurement results, attempt 5 (2026-10-27)

This is the run of `docs/kri-fixes-preregistration-2026-10-26.md` §5 on branch
`kri-fixes-2026-10-26`, at run commit `447cc1dcc2d2339b22b5897b19017c2aeded4cf5`, into
`~/egyptology-runs/kri-fixes-2026-10-26-attempt5`. Nothing in the code, the rules or the
inputs was changed during the run. Every gate decision below is quoted as the runner and
`scripts/check_kri_fixes_gates.py` made it; none was re-decided here.

**Verdict: ALL STEPS PASSED (steps 0-9, every `END ... exit=0`, `run_log.txt` ends in
`ALL STEPS PASSED`). Gated rules (a), (c), (e), (e2), (e3) and (f) PASS. Rule (b) produced the
decision DISABLE (off-better 7 > on-better 4 over positions), so the pooled fallback ships
default off. Rules (d) and (g) are reported only. Rule (h) was not triggered.**

This is the first attempt that ran all of §5 to the end. Attempt 1 failed rule (c) at step 3;
attempts 2, 3 and 4 never reached a verdict on every step (history below). **No number from
attempts 2, 3 or 4 is used for any decision in this note.** Attempt 1 is mentioned once, in
"Relation to attempt 1", as context only; none of its numbers decides anything here.

**No number here is an independent accuracy figure.** This was a pilot-informed registration:
the first 500 test rows were decoded before the rules were fixed (§3). BBAW's lexicon-assisted
numbers are not held-out (§2), and BBAW supplies 1,013 of the 3,473 test lines. The pooled
fallback did not reach (b) outcome 3, so **no benefit of the pooled fallback may be claimed or
quoted**. The three heuristics (pooled fallback, singleton `/k` discount, cartouche constraint)
are exploratory heuristics and ship as such (§1).

## Attempt history

| Attempt | Run commit | Directory | Outcome | Cause (from the 2026-10-27 addenda) | Used for a decision here? |
| --- | --- | --- | --- | --- | --- |
| 1 | `1733c165e23c017d0c121e7c9b9809f67c325b8e` | `...-attempt1` | **FAILED** at step 3 | Rule (c): 3,300 boundary errors outside cartouches against 3,299 (cartouche candidate-window defect on one line). Steps 4-9 did not run. Note: `docs/kri-fixes-results-2026-10-26.md` | No |
| 2 | `6b616c4` | `...-attempt2` | **INTERRUPTED** (neither passed nor failed) | The Mac went to sleep at about 55% of step 9; steps 0-8 logged `exit=0`, `run_log.txt` ends at `START step9-pytest` with no `END` | No |
| 3 | `6b616c4` | `...-attempt3` | **FAILED** at step 9 | 2 of 1,582 tests, the `[HUP]` and `[INT]` cases of `tests/test_audit_ops.py::test_an_interrupted_deploy_rolls_back_and_leaves_no_marker`. Launched as `nohup caffeinate ... &`: the launcher left SIGHUP and SIGINT ignored, so the deploy script's traps could not run. Reproduced; the same tests pass when run normally. No product code or test changed | No |
| 4 | `eae95cd` | `...-attempt4` | **FAILED** at step 9 | 1 of 1,575 tests, `tests/test_check_kri_fixes_gates.py::test_the_preregistration_reproduces_the_runner_verbatim`: addendum (2) added `step0-signals` to the runner but not to §5's copy | No |
| 5 | `447cc1dcc2d2339b22b5897b19017c2aeded4cf5` | `...-attempt5` | **ALL STEPS PASSED** | none | **Yes, this note** |

Under rule (h), attempts 1, 3 and 4 stay FAILED and attempt 2 stays interrupted. Each directory
was allocated fresh by the runner and none was touched by attempt 5. Between attempts the only
changes were: the pooled-fallback default and the cartouche window fix (after 1, commits
`97ddff2`, `43fbecb`, `744d10b`), the `step0-signals` runner check (after 3, commit `eae95cd`),
and the §5 copy of the runner (after 4, commit `447cc1d`). No rule, budget, threshold, constant,
split or arm definition changed in any of them (addenda 1 to 3).

## Step 0: pinned state

| Item | Value | Source in `$R` |
| --- | --- | --- |
| Attempt directory `$R` | `~/egyptology-runs/kri-fixes-2026-10-26-attempt5` (fresh; attempts 1-4 existed) | runner stdout (`kri-fixes-attempt5-console.log`) |
| Approved commit | `447cc1dcc2d2339b22b5897b19017c2aeded4cf5` | `approved_commit.txt` |
| HEAD at run | `447cc1dcc2d2339b22b5897b19017c2aeded4cf5` (equal; toplevel, branch, clean tree, private dir, baseline dir asserted) | `commit.txt`, `run_log.txt` |
| Signal check | `step0-signals` exit 0 (SIGHUP, SIGINT and SIGTERM not ignored at launch) | `run_log.txt` |
| `data/processed/examples.csv` | `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` (pinned, OK) | `shas.txt`, `pinned_shas.txt` |
| `scripts/eval_guards.py` | `17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950` (pinned, OK) | `shas.txt` |
| `scripts/run_reading_model_eval.py` | `373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5` (pinned, OK) | `shas.txt` |
| `scripts/run_kri_fixes_eval.py` | `79033a49b6e4263ff85ad1d4fed266eb9956577000003f40a689cae5a4b219eb` | `shas.txt` |
| `scripts/check_kri_fixes_gates.py` | `5349e9cfae59d83f9684ba254ad8d65ba671f3af8ce1b14ac045269a293dab14` | `shas.txt` |
| `scripts/run_kri_fixes_prereg.sh` | `ada3feb0b07e5d489ec579b34c4bc99141e767e9656e23ff9282e7d1f6833366` | `shas.txt` |
| Interpreter | Python 3.12.13 (full `pip freeze` in the file) | `env.txt` |
| Split manifest (step 1) | `ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba`, OK | `manifest_sha.txt` |
| Split | 59,504 aligned sentences, train 52,210 / test 3,473 (BBAW 1,013, TLA 2,460); dropped 829 exact duplicates, 202 near-duplicates, 2,790 lexicon-leaking rows, all as §2 | `step1.txt`, `step2.txt` |

The two harness and checker shas equal the ones recorded for attempt 1; the runner's sha differs
because `step0-signals` was added to it (addendum 2).

## Rule table

"Attempt 2" inside rules (e3) and (f) means attempt 2 of the 2026-10-25 re-measurement
(`~/egyptology-runs/remeasure-2026-10-25`, the runner's `$BASE`), not attempt 2 of this series.

| Rule | Gate | Number from attempt 5 | Status | Source file |
| --- | --- | --- | --- | --- |
| (a) collateral, `all_on` | other net <= 5; neighbour net <= 2; lines exact net <= 3 | other: n = 25,711, better 0, worse 0, net 0. Neighbour: n = 60, better 0, worse 0, net 0. Lines exact: gained 0, lost 1, net 1 (the lost line is TLA:1132, through its firing position #3). Position sign-test p n/a (no discordant positions). Whole-line sign-test p = 1 (exact two-sided, gained 0 / lost 1; the checker prints no p for lines) | **PASS** | `step3_gates.txt`, `kri_summary.csv`, `kri_lines.csv` |
| (a) collateral, `cartouche_only` | same budgets | other net 0, neighbour net 0, lines gained 0 / lost 0, net 0 | **PASS** | same |
| (b) firing positions, `all_on` vs `all_off` | decision order of §4(b) | n = 37 positions in 31 lines. Positions: on-better 4, off-better 7, unchanged 26, position sign-test p = 0.5488 (reported only). Lines: on-better 4, off-better 4, tied 23, line sign-test p = 1. Outcome 2: off-better > on-better at any n | **DECISION: DISABLE** | `step3_gates.txt` |
| (c) boundary errors outside cartouches, `all_on` | <= `all_off` | 3,299 vs `all_off` 3,299 (FP 1,695 + FN 1,604 in both) | **PASS** | `step3_gates.txt`, `kri_summary.csv` |
| (c) boundary errors outside cartouches, `cartouche_only` | <= `all_off` | 3,299 vs `all_off` 3,299 | **PASS** | same |
| (d) harness stage moves | counted and listed, no threshold | 0 lines moved in each of `pooled_only`, `discount_only`, `cartouche_only`, `all_on`; listing length equals the summary count (0) | **REPORTED** | `step3_gates.txt`, `kri_summary.csv` |
| (e) expert paste gate | 8/8 `auto` and 8/8 `declared` | `auto` 8/8, `declared` 8/8 | **PASS** | `step4_gates.txt`, `paste_auto.txt`, `paste_declared.txt` |
| (e2) Urk. IV / St Andrews gate | `GATE: PASS` in `auto` and `declared` | `auto`: expert paste checks 8/8, `GATE: PASS`. `declared`: 8/8, `GATE: PASS`. Both print "St Andrews rows in the pool: 0" and retrieval pool 27,917 of 138,131 | **PASS** | `urkiv_standrews_auto.txt`, `urkiv_standrews_declared.txt` |
| (e3) held-out stage routing | Earlier -> Demotic = Late -> Demotic = 0/200; sample identical to attempt 2 | Earlier -> Demotic 0/200, Late -> Demotic 0/200 (script rule PASS); sample identical to attempt 2 (400 pastes); chosen stage changed against attempt 2: 0 (listed, not gated) | **PASS** | `routing_summary.txt`, `step6_gates.txt`, `routing.csv` |
| (f) competitive sets, sanity check | zero top-3 answers lost per query vs attempt 2; v4 T-auto floors top-3 >= 0.80, MRR >= 0.70 | All six runs: lost none, gained none (table below). v4 T-auto top-3 0.85 >= 0.8, MRR 0.75 >= 0.7 | **PASS** | `step7_gates.txt` |
| (f) determinism | `verify_release.py --skip-tests` reproduces steps 7 and 4, READY | LEGACY pool SAME (top-3 0.9, MRR 0.8, 2 failures); TWIN-CONTROLLED pool SAME (0.85, 0.75, 3 failures); paste 8/8 SAME; verdict READY, expert pastes 8/8 | **PASS** | `step8_gates.txt`, `verify_release.txt` |
| (g) calibration | reported, never gated | Brier, all positions: discount +0.000117323 (worse), correction +0.003600955 (worse), combined +0.003878482 (worse). With reading: +0.000118036, +0.003622854, +0.003902069 | **REPORTED** | `step3_gates.txt`, `kri_summary_calibration.csv`, `kri_positions.csv` |
| (h) stop on any failure | every step through `run` | No step exited non-zero; no STOP line in `run_log.txt`; `ALL STEPS PASSED` at 16:31:02Z | **NOT TRIGGERED** | `run_log.txt` |

The step-9 test suite (not a numbered rule) gave `1575 passed, 7 skipped, 2 warnings in 596.41s`
(`pytest.txt`). The two warnings are pandas `DtypeWarning` notices on reading `examples.csv`.

### Source-stratified counts

From `kri_summary.csv`, reported only.

| Scope | Arm | acc_all | Firing n (+/-) | Other (+/-) | Lines exact (gained/lost) | Boundary errors outside cartouches | Cartouches split | Boundaries inside cartouches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | all_off | 0.766235 | 37 | +0/-0 | 844 lines exact | 3,299 (FP 1,695 + FN 1,604) | 16 / 336 | 32 |
| all | cartouche_only | 0.766235 | 37 (+0/-0) | +0/-0 | 0 / 0 | 3,299 (FP 1,695 + FN 1,604) | 0 / 336 | 0 |
| all | all_on | 0.766119 | 37 (+4/-7) | +0/-0 | 0 / 1 | 3,299 (FP 1,695 + FN 1,604) | 0 / 336 | 0 |
| BBAW | all_off | 0.740056 | 21 | +0/-0 | 182 | 828 | 0 / 0 | 0 |
| BBAW | all_on | 0.739408 | 21 (+0/-6) | +0/-0 | 0 / 0 | 828 | 0 / 0 | 0 |
| TLA | all_off | 0.780865 | 16 | +0/-0 | 662 | 2,471 | 16 / 336 | 32 |
| TLA | all_on | 0.781046 | 16 (+4/-1) | +0/-0 | 0 / 1 | 2,471 | 0 / 336 | 0 |

`pooled_only` has the segmentation of `all_off` and `discount_only` is identical to `all_off` in
every count. Other reported (c) figures, for all lines:

| Measure | `all_off` | `cartouche_only` / `all_on` |
| --- | --- | --- |
| Boundary TP / FP / FN | 20,731 / 1,726 / 1,604 | 20,730 / 1,695 / 1,605 |
| Boundary F1 | 0.925656 | 0.926273 |
| Exact segmentations | 1,816 | 1,818 |

Per source, boundary F1 is 0.948870 (BBAW, unchanged in all arms) and 0.912511 -> 0.913464
(TLA, `all_off` -> `cartouche_only` / `all_on`).

## Rule (b): outcome and what ships

The decision is **DISABLE** (outcome 2 of §4(b)): on the 37 firing positions in 31 lines,
`all_on` was better than `all_off` at 4 positions and worse at 7 (26 unchanged); over firing
lines it was better on 4, worse on 4 and tied on 23 (line sign-test p = 1). The harm criterion
reads positions and low n does not suspend it, so the pooled fallback must default to off.

By source: BBAW +0/-6, TLA +4/-1. Four of the seven losses sit in one group in one line
(BBAW:2621, `2` -> `1/2`, stage count 3, pooled count 118). Reading the listing, three of the
four gains (TLA:154#4, TLA:588#1, TLA:1123#1) are case or bracket variants of the reading the
model already gave, which the scorer counts as gains because it matches exact strings.

**What ships:**

1. **The pooled fallback ships default off.** `USE_POOLED_FALLBACK_BY_DEFAULT = False` in
   `app/services/reading_model.py`, commit `97ddff2` (the follow-up commit that rule (b)
   outcome 2 requires, named in addendum 1). The code, the `POOLED_FALLBACK_*` constants and
   `attach_pooled` stay; the fallback runs only when a caller passes `use_pooled_fallback=True`.
   The harness passes the flag explicitly per arm, so this measurement is unaffected by the
   default. The pooled fallback's own benefit is **unmeasured** and must not be quoted; what was
   measured is harm in positions (4 gained, 7 lost) and a tie in lines.
2. **The cartouche constraint ships with the window counted in units**, commit `43fbecb`: a
   complete cartouche counts as one unit of `Segmenter.segment`'s candidate window. This is the
   configuration `cartouche_only` measured: rule (a) PASS, rule (c) PASS (3,299 against 3,299
   outside-cartouche errors), cartouches split 16 -> 0 of 336, boundaries inside cartouches
   32 -> 0, F1 0.925656 -> 0.926273, exact segmentations 1,816 -> 1,818.
3. **The `/k` discount is left as it is** (addendum 1, item 4). It is reported, never gated, and
   no target was registered. Attempt 5 measured it raising the Brier score (see (g)); that is
   recorded and no decision in this note rests on it.

The shipped reading configuration therefore corresponds to the `cartouche_only` arm with the
`/k` discount. As §1 says, all three ship as exploratory heuristics, and nothing in this note
is a claim that any of them improves accuracy.

## (c) What the cartouche arm changed

From `kri_lines.csv` (per-line counts, `cartouche_only` against `all_off`), read-only and not a
registered step. The constraint changed the boundary counts on 16 lines, all of them TLA. On
none of them did the number of boundary errors outside cartouche spans change: false positives
outside spans stay 1,695 and false negatives outside spans stay 1,604. The total false
positives fell by 31 (1,726 -> 1,695), all inside spans.

The one boundary the constraint cost is a true positive: total TP 20,731 -> 20,730 and total FN
1,604 -> 1,605, on the single line TLA:121 (TP 3 -> 2, FN 1 -> 2, FP 1 -> 0; the outside-span
counts are unchanged). Its gold boundary lies inside a matched cartouche, which the constrained
decoder cannot produce by design (see §7 of the pre-registration and the attempt-1 note on
TLA:121). It is a consequence of the rule, not a defect, and (c) does not gate it.

`all_on` and `cartouche_only` have identical segmentation counts.

## (d) Harness stage-change listing, in full

There are 0 stage moves in every arm, so the listing is empty and its length equals the
summary's count. As §7.3 registered, the harness router receives the gold-spaced paste, so a
count of 0 here is not evidence about routing on real pastes. That evidence is (e2) and (e3).

## (e3) Routing-change listing, in full

There is none: 0 pastes changed chosen stage against attempt 2 of the 2026-10-25 run, on the same
400 pastes (seed 20261025, 200 per stage). From `routing_summary.txt`:

| Measure | Value |
| --- | --- |
| Corpus rows / eligible after dedup | 130,472; Earlier Egyptian 9,885, Late Egyptian 31,310 |
| Pool (held out) | 130,045 rows (427 held out) |
| Earlier Egyptian chosen as Earlier / Late / Demotic / None | 178 / 21 / 0 / 1 |
| Late Egyptian chosen as Earlier / Late / Demotic / None | 13 / 187 / 0 / 0 |
| Earlier -> Demotic, Late -> Demotic | 0/200, 0/200 |
| Abstentions (None) | 1/400 |
| Reading accuracy, chosen stage's model | 0.8790 (2303/2620 aligned tokens) |
| Reading accuracy, true stage's model | 0.8821 (2311/2620 aligned tokens) |
| App choice differs from the A2.4 decision function (app's coverage) | 1/400 |
| App choice differs from A2.4 as written (own aligned rows' coverage) | 20/400 |
| Pastes whose app coverage differs from own-aligned-row coverage | 215/400 |

The last three rows are the script's own disclosures, reported as printed.

## (f) Competitive sets, per run

(f) does **not exercise the decoder or the segmenter**. It detects collateral damage only, and
passing it is not evidence for any of the three features. The per-query comparison is against
the 2026-10-25 re-measurement's files of the same name; `step7_gates.txt` prints identical
aggregates on both sides in every run, and the held-out and LE-v1 values also match those the
pre-registration §4(f) listed.

| Run | Queries | top-3 useful | MRR | Failures | Lost / gained per query | Status |
| --- | --- | --- | --- | --- | --- | --- |
| v4 T-auto | 20 | 0.85 | 0.75 | 3 | none / none | PASS (floors 0.80 / 0.70 met) |
| v4 L-auto | 20 | 0.9 | 0.8 | 2 | none / none | PASS |
| held-out T-auto | 20 | 0.75 | 0.6667 | 5 | none / none | PASS |
| held-out L-auto | 20 | 0.75 | 0.675 | 5 | none / none | PASS |
| LE-v1 T-auto | 30 | 0.8667 | 0.8 | 4 | none / none | PASS |
| LE-v1 L-auto | 30 | 0.8667 | 0.8 | 4 | none / none | PASS |

## (g) Calibration, reported only

Brier score, lower is better, from `kri_summary_calibration.csv` (5 decimals). **The deltas are
computed before rounding**: each score was recomputed from `kri_positions.csv` (the confidences
as the harness wrote them) and every recomputed score rounds to the CSV's value. The step-3
checker prints differences of the rounded scores, which is why its with_reading lines read
+0.00363 and +0.00391; those lines are quoted verbatim below and the figures here are the
precise ones.

| Confidence | Brier, all positions (n = 25,808) | Brier, with_reading (n = 25,652) |
| --- | --- | --- |
| `all_off` legacy (pre-branch) | 0.18847 | 0.18961 |
| `all_off` undiscounted (corrected) | 0.19207 | 0.19324 |
| `discount_only` discounted (corrected + /k) | 0.19219 | 0.19336 |
| `all_on` discounted (shipped confidence) | 0.19235 | 0.19352 |

| Comparison | All positions | with_reading |
| --- | --- | --- |
| Discount effect: `discount_only` discounted - `all_off` undiscounted | **+0.000117323** | **+0.000118036** |
| Correction effect: `all_off` undiscounted - `all_off` legacy | +0.003600955 | +0.003622854 |
| Combined effect: `all_on` discounted - `all_off` legacy (includes prediction changes; attributes nothing to /k) | +0.003878482 | +0.003902069 |

Unrounded scores: all positions, legacy 0.188468582, undiscounted 0.192069538, `discount_only`
discounted 0.192186860, `all_on` discounted 0.192347065; with_reading, 0.189614735,
0.193237589, 0.193355625, 0.193516804.

**The discount moved the Brier score up by about 0.00012 (+0.000117323 over all positions,
+0.000118036 with a reading), which is worse, in both subsets.** The correction of `be24b96` #1
also raised the Brier score. There is no pass rule here and none is inferred after the fact.

Reliability bins, `with_reading`, each cell n @ mean confidence / accuracy for the bins 0.0-0.1
through 0.9-1.0:

| Confidence | Bins |
| --- | --- |
| `all_off` legacy | 0 / 0 / 31 @ 0.258/0.226 / 202 @ 0.345/0.361 / 526 @ 0.440/0.508 / 1322 @ 0.532/0.522 / 1281 @ 0.653/0.562 / 1016 @ 0.750/0.656 / 2427 @ 0.842/0.778 / 18847 @ 0.987/0.820 |
| `all_off` undiscounted | 207 @ 0.053/0.464 / 340 @ 0.152/0.523 / 379 @ 0.246/0.512 / 438 @ 0.345/0.514 / 434 @ 0.436/0.498 / 1005 @ 0.527/0.514 / 979 @ 0.647/0.583 / 1006 @ 0.751/0.703 / 2187 @ 0.838/0.796 / 18677 @ 0.985/0.821 |
| `discount_only` discounted | 222 @ 0.053/0.446 / 382 @ 0.147/0.503 / 683 @ 0.248/0.457 / 396 @ 0.347/0.533 / 434 @ 0.436/0.498 / 686 @ 0.539/0.577 / 979 @ 0.647/0.583 / 1006 @ 0.751/0.703 / 2187 @ 0.838/0.796 / 18677 @ 0.985/0.821 |
| `all_on` discounted | 224 @ 0.053/0.451 / 382 @ 0.147/0.503 / 678 @ 0.248/0.459 / 396 @ 0.347/0.535 / 434 @ 0.436/0.498 / 688 @ 0.539/0.577 / 986 @ 0.648/0.579 / 1009 @ 0.751/0.704 / 2190 @ 0.838/0.795 / 18665 @ 0.985/0.821 |

## Relation to attempt 1 (context only, decides nothing)

Attempt 1 ran the code before the cartouche window fix. The reading-side counts of this attempt,
rules (a), (b), (d) and (g) (positions, cohorts, better/worse counts, Brier scores), equal those
attempt 1 reported, which is what one expects: the fix touches only `Segmenter.segment` on lines
with a cartouche longer than the window, and the reading track uses gold groupings (§7.2). The
differences are all in the cartouche arms: false positives 1,696 -> 1,695, hence outside-span
errors 3,300 -> 3,299, and F1 0.926253 -> 0.926273. None of attempt 1's numbers is carried into
this note's decisions; every number above was read from attempt 5's own files.

## Mechanisms

**Confirmed** (read directly from the run's files):

* The cartouche constraint does what it was written to do on this split: cartouches split
  16 -> 0 of 336, boundaries inside cartouches 32 -> 0, total false positives -31, exact
  segmentations +2, boundary F1 0.925656 -> 0.926273, with no change in outside-span errors.
* The pooled fallback fired at 37 positions in 31 lines (21 BBAW, 16 TLA), every one in
  `pooled_only` and `all_on`. It lost more than it gained over positions (4 vs 7), and lines
  tied 4 vs 4. It cost one exact line, TLA:1132.
* The `/k` discount changes no prediction (`discount_only` equals `all_off` in every count). It
  raised the Brier score by about 0.00012.
* No arm moved any line's stage in the harness, and (e3) moved no paste's chosen stage.
* No position outside the firing cohort changed outcome in any arm.

**Not shown by these files:** why the pooled fallback loses where it does (the BBAW numeral
group `2` -> `1/2` is the dominant loss, but the cause is not tested here); and whether it would
come out differently once the transition-smoothing defect of §7.5 is fixed.

## Known limits (pre-registration §7)

These were stated before the run and all still apply.

1. **The firing sample is tiny** (§3): 37 positions in 31 lines, against an expected order of 20.
   The split has no Ramses or AES rows left in it, so the stage mix the pooled fallback depends
   on is narrower than production's.
2. **The reading track uses gold groupings.** It measures reading, not reading-after-segmentation.
   The cartouche constraint reaches it only through the stage router. No end-to-end number is
   attempted.
3. **The harness router gets the gold-spaced paste**, and its spaces act as hints, so the
   cartouche constraint rarely gets to change routing segmentation there. The 0 stage moves in
   (d) therefore understate the routing effect on unspaced or quadrat-spaced pastes. (e2) and (e3)
   route real pastes and partly cover this; an unspaced-routing arm is not attempted.
4. **Nothing here measures the KRI material**, which is private and excluded. The pre-registered
   KRI test of `docs/plan-data-cleanup-2026-10-26.md` §4d/§4e is separate and unaffected by this
   note. No KRI text or number appears here.
5. **The decode still prefers the singleton on the traced positions** (the transition-smoothing
   defect, `docs/kri-selftest-fixes-2026-10-26.md` §1). This measurement cannot fix it and was
   not designed to detect it. The pre-registration named it as the likely reason if (b) came out
   flat; this run does not test that.
6. **Pilot-informed, and not independently held-out** (§2, §3). The first 500 test rows were
   decoded before the rules were fixed, and BBAW's lexicon-assisted numbers are not held-out.
   BBAW contributes 1,013 of the 3,473 test rows.
7. **Branch base.** `main` has moved on since `3465478`. The branch deletes nothing; a
   `diff main..HEAD` shows later docs as deletions only because of the older base. Merge, do not
   overwrite.

A further limit that follows from the above: the `/k` discount and the cartouche constraint were
not shown to help any accuracy measure here. The cartouche constraint reduces false boundaries
inside cartouches and costs one gold boundary on one line; the discount worsened the Brier score.

## Durations

| What | Duration | Kind | Source |
| --- | --- | --- | --- |
| Step 1 (manifest, 1-row dry decode) | 36.9 s | internal | `step1.txt` "total" |
| Step 2 harness, 3,473 rows x 5 arms | 942.4 s total (models 16.7 s; decode 904.0 s, 0.260 s per row) | internal | `step2.txt` |
| Step 2 harness | 14:55:37Z -> 15:11:20Z = 15 min 43 s | wall clock | `run_log.txt` |
| Step 9 pytest | 596.41 s (10 min 07 s wall: 16:20:55Z -> 16:31:02Z) | internal / wall | `pytest.txt`, `run_log.txt` |
| **Whole run, START step0 to ALL STEPS PASSED** | **14:54:56Z -> 16:31:02Z = 1 h 36 min 06 s** | wall clock | `run_log.txt` |

## Step 3 gate output (complete, verbatim)

`step3_gates.txt`, unedited. It contains the complete firing-position listing that §6 asks for
(`off` is `all_off`, `on` is `all_on`; `(1)`/`(0)` marks a correct/incorrect prediction; all rows
are from the public TLA/BBAW corpus). The on-better positions are TLA:154#4, TLA:588#1,
TLA:1123#1 and TLA:2119#1. The off-better positions are TLA:1132#3, BBAW:2621#3, #7, #14 and
#16, BBAW:2762#9 and BBAW:2830#14.

```
(a) collateral losses against all_off (net = worse - better)
          all_on     other: n=25711 better=0 worse=0 net=0 budget=5 sign-test p=n/a  PASS
          all_on neighbour: n=60 better=0 worse=0 net=0 budget=2 sign-test p=n/a  PASS
          all_on     lines: exact gained=0 lost=1 net=1 budget=3  PASS
  cartouche_only     other: n=25711 better=0 worse=0 net=0 budget=5 sign-test p=n/a  PASS
  cartouche_only neighbour: n=60 better=0 worse=0 net=0 budget=2 sign-test p=n/a  PASS
  cartouche_only     lines: exact gained=0 lost=0 net=0 budget=3  PASS
(b) firing positions (all_on vs all_off): n=37 in 31 lines, on-better=4 off-better=7 unchanged=26 position sign-test p=0.5488 (reported only)
    firing lines: on-better=4 off-better=4 tied=23 line sign-test p=1 (decides the claim)
    DECISION: DISABLE - off-better exceeds on-better; use_pooled_fallback must default to off before merge
    TLA:154#4 stage='Late Egyptian' gold='sšm-nfr' off='Sšm-nfr'(0) on='sšm-nfr'(1) fired_here=1 stage_count=3 pooled_count=71
    TLA:298#0 stage='Late Egyptian' gold='hꜣ' off='hꜣ'(1) on='hꜣ'(1) fired_here=1 stage_count=3 pooled_count=153
    TLA:331#7 stage='Earlier Egyptian' gold='šms.PL' off='⸢šms.pl⸣'(0) on='šmsw'(0) fired_here=1 stage_count=2 pooled_count=22
    TLA:581#5 stage='Late Egyptian' gold='mꜣꜥ.t' off='mꜣꜥ.t'(1) on='mꜣꜥ.t'(1) fired_here=1 stage_count=1 pooled_count=20
    TLA:588#1 stage='Late Egyptian' gold='ḥm(.t)-nṯr-ḥw.t-ḥr.w' off='ḥm.t-nṯr-Ḥw.t-Ḥr.w'(0) on='ḥm(.t)-nṯr-ḥw.t-ḥr.w'(1) fired_here=1 stage_count=2 pooled_count=24
    TLA:646#0 stage='Earlier Egyptian' gold='mꞽ.t.t' off='mꞽ.tt'(0) on='m-mꞽtt'(0) fired_here=1 stage_count=2 pooled_count=33
    TLA:662#12 stage='Earlier Egyptian' gold='ꞽy.t' off='ꞽy.t'(1) on='ꞽy.t'(1) fired_here=1 stage_count=2 pooled_count=30
    TLA:1123#1 stage='Late Egyptian' gold='ḥm(.t)-nṯr-ḥw.t-ḥr.w' off='ḥm.t-nṯr-Ḥw.t-Ḥr.w'(0) on='ḥm(.t)-nṯr-ḥw.t-ḥr.w'(1) fired_here=1 stage_count=2 pooled_count=24
    TLA:1132#3 stage='Earlier Egyptian' gold='mri̯.y' off='mri̯.y'(1) on='mry'(0) fired_here=1 stage_count=1 pooled_count=27
    TLA:1279#6 stage='Late Egyptian' gold='mꜣꜥ.t' off='mꜣꜥ.t'(1) on='mꜣꜥ.t'(1) fired_here=1 stage_count=1 pooled_count=20
    TLA:1500#0 stage='Earlier Egyptian' gold='ḫr' off='ḫr'(1) on='ḫr'(1) fired_here=1 stage_count=1 pooled_count=28
    TLA:1802#1 stage='Late Egyptian' gold='ꞽwꜣ' off='ꞽwꜣ'(1) on='ꞽwꜣ'(1) fired_here=1 stage_count=2 pooled_count=62
    TLA:2119#1 stage='Earlier Egyptian' gold='=k' off='=kw'(0) on='=k'(1) fired_here=1 stage_count=1 pooled_count=53
    TLA:2370#11 stage='Earlier Egyptian' gold='r-n.tꞽ' off='r-n.tꞽ'(1) on='r-n.tꞽ'(1) fired_here=1 stage_count=1 pooled_count=162
    TLA:2370#18 stage='Earlier Egyptian' gold='tꜣ.DU' off='tꜣ.du'(0) on='tꜣ.wy'(0) fired_here=1 stage_count=2 pooled_count=58
    TLA:2370#22 stage='Earlier Egyptian' gold='mn' off='mn'(1) on='mn'(1) fired_here=1 stage_count=1 pooled_count=26
    BBAW:2496#0 stage='Earlier Egyptian' gold='mki̯' off='mk'(0) on='mk'(0) fired_here=1 stage_count=2 pooled_count=26
    BBAW:2587#1 stage='Earlier Egyptian' gold='⸢ꞽr.t⸣' off='ꞽr.t(ꞽ)'(0) on='ꞽr.t'(0) fired_here=1 stage_count=1 pooled_count=30
    BBAW:2621#3 stage='Earlier Egyptian' gold='2' off='2'(1) on='1/2'(0) fired_here=1 stage_count=3 pooled_count=118
    BBAW:2621#7 stage='Earlier Egyptian' gold='2' off='2'(1) on='1/2'(0) fired_here=1 stage_count=3 pooled_count=118
    BBAW:2621#9 stage='Earlier Egyptian' gold='1' off='1'(1) on='1'(1) fired_here=1 stage_count=2 pooled_count=41
    BBAW:2621#14 stage='Earlier Egyptian' gold='2' off='2'(1) on='1/2'(0) fired_here=1 stage_count=3 pooled_count=118
    BBAW:2621#16 stage='Earlier Egyptian' gold='2' off='2'(1) on='1/2'(0) fired_here=1 stage_count=3 pooled_count=118
    BBAW:2678#2 stage='Earlier Egyptian' gold='nḥḥ' off='nḥḥ'(1) on='nḥḥ'(1) fired_here=1 stage_count=1 pooled_count=22
    BBAW:2762#9 stage='Earlier Egyptian' gold='rnp.t.pl' off='rnp.t.pl'(1) on='rnp.wt'(0) fired_here=1 stage_count=2 pooled_count=30
    BBAW:2800#1 stage='Earlier Egyptian' gold='{k}wꞽ' off='=kw'(0) on='=kwꞽ'(0) fired_here=1 stage_count=1 pooled_count=53
    BBAW:2830#14 stage='Earlier Egyptian' gold='mki̯' off='mki̯'(1) on='mk'(0) fired_here=1 stage_count=1 pooled_count=33
    BBAW:2871#5 stage='Earlier Egyptian' gold='1' off='2'(0) on='1/2'(0) fired_here=1 stage_count=3 pooled_count=118
    BBAW:2893#10 stage='Earlier Egyptian' gold='wsḫ.t' off='h(y)'(0) on='hꜣw'(0) fired_here=1 stage_count=1 pooled_count=35
    BBAW:2896#1 stage='Late Egyptian' gold='Sšm-nfr' off='sšm-nfr'(0) on='sšm-nfr'(0) fired_here=1 stage_count=3 pooled_count=71
    BBAW:2910#0 stage='Earlier Egyptian' gold='400' off='400'(1) on='400'(1) fired_here=1 stage_count=1 pooled_count=110
    BBAW:2938#0 stage='Earlier Egyptian' gold='db.t' off='db.t'(1) on='db.t'(1) fired_here=1 stage_count=2 pooled_count=34
    BBAW:3165#8 stage='Earlier Egyptian' gold='qn' off='qn'(1) on='qn'(1) fired_here=1 stage_count=2 pooled_count=34
    BBAW:3300#10 stage='Earlier Egyptian' gold='ḥqꜣ' off='ḥqꜣ'(1) on='ḥqꜣ'(1) fired_here=1 stage_count=3 pooled_count=45
    BBAW:3313#2 stage='Earlier Egyptian' gold='6.〈nw.t〉' off='6'(0) on='6'(0) fired_here=1 stage_count=3 pooled_count=562
    BBAW:3362#3 stage='Earlier Egyptian' gold='dwꜣ.w' off='d(w)ꜣ.w'(0) on='dwꜣw'(0) fired_here=1 stage_count=1 pooled_count=36
    BBAW:3457#5 stage='Earlier Egyptian' gold='⸢⸮mdw?⸣' off='mdw'(0) on='mdw'(0) fired_here=1 stage_count=3 pooled_count=69
    source:BBAW: firing n=21 +0/-6; other +0/-0 (reported only)
    source:TLA: firing n=16 +4/-1; other +0/-0 (reported only)
(c) all_on: boundary errors outside cartouches 3299 vs all_off 3299  PASS  (reported: F1 0.9262734584450402, seg_exact 1818, cartouches split 0 of 336, boundaries inside cartouches 0)
(c) cartouche_only: boundary errors outside cartouches 3299 vs all_off 3299  PASS  (reported: F1 0.9262734584450402, seg_exact 1818, cartouches split 0 of 336, boundaries inside cartouches 0)
(d) pooled_only: lines whose stage moved: 0
(d) discount_only: lines whose stage moved: 0
(d) cartouche_only: lines whose stage moved: 0
(d) all_on: lines whose stage moved: 0
(g) calibration, reported only (Brier; lower is better)
  subset=all: pre-branch confidence 0.18847; corrected, undiscounted 0.19207; corrected + /k (discount_only) 0.19219; all_on, shipped confidence 0.19235
    discount effect (discount_only discounted - all_off undiscounted): +0.00012
    correction effect (all_off undiscounted - all_off legacy): +0.00360
    combined (all_on shipped - all_off legacy): +0.00388
  subset=with_reading: pre-branch confidence 0.18961; corrected, undiscounted 0.19324; corrected + /k (discount_only) 0.19336; all_on, shipped confidence 0.19352
    discount effect (discount_only discounted - all_off undiscounted): +0.00012
    correction effect (all_off undiscounted - all_off legacy): +0.00363
    combined (all_on shipped - all_off legacy): +0.00391
harness: PASS
```

## Step 4 gate output (rule e), verbatim

`step4_gates.txt`:

```
(e) paste auto: 8/8  PASS
(e) paste declared: 8/8  PASS
paste: PASS
```

## Step 6 gate output (rule e3), verbatim

`step6_gates.txt`:

```
(e3) routing sample identical to attempt 2 (400 pastes)
(e3) chosen stage changed against attempt 2: 0 (listed, not gated)
routing: PASS
```

## Step 7 gate output (rule f), verbatim

`step7_gates.txt`:

```
(f) v4_T_auto: top-3 0.85 -> 0.85, MRR 0.75 -> 0.75; lost none, gained none  PASS
(f) v4_L_auto: top-3 0.9 -> 0.9, MRR 0.8 -> 0.8; lost none, gained none  PASS
(f) holdout_T_auto: top-3 0.75 -> 0.75, MRR 0.6667 -> 0.6667; lost none, gained none  PASS
(f) holdout_L_auto: top-3 0.75 -> 0.75, MRR 0.675 -> 0.675; lost none, gained none  PASS
(f) le_v1_T_auto: top-3 0.8667 -> 0.8667, MRR 0.8 -> 0.8; lost none, gained none  PASS
(f) le_v1_L_auto: top-3 0.8667 -> 0.8667, MRR 0.8 -> 0.8; lost none, gained none  PASS
(f) v4 T-auto release floors: top-3 0.85 >= 0.8, MRR 0.75 >= 0.7  PASS
competitive: PASS
```

## Step 8 gate output (rule f determinism), verbatim

`step8_gates.txt`:

```
(f) verify_release LEGACY pool vs v4_L_auto.txt: {'top3_useful_family_accuracy': ('0.9', '0.9'), 'mrr': ('0.8', '0.8'), 'failures': ('2', '2')}  SAME
(f) verify_release TWIN-CONTROLLED pool vs v4_T_auto.txt: {'top3_useful_family_accuracy': ('0.85', '0.85'), 'mrr': ('0.75', '0.75'), 'failures': ('3', '3')}  SAME
(f) verify_release paste 8/8 vs paste_auto 8/8  SAME
verify: PASS
```

## Run log (rule h), verbatim

`run_log.txt`:

```
2026-10-27T14:54:56Z START step0-toplevel
2026-10-27T14:54:56Z END step0-toplevel exit=0
2026-10-27T14:54:56Z START step0-branch
2026-10-27T14:54:56Z END step0-branch exit=0
2026-10-27T14:54:56Z START step0-approved-commit
2026-10-27T14:54:56Z END step0-approved-commit exit=0
2026-10-27T14:54:56Z START step0-clean
2026-10-27T14:54:56Z END step0-clean exit=0
2026-10-27T14:54:56Z START step0-private-dir
2026-10-27T14:54:56Z END step0-private-dir exit=0
2026-10-27T14:54:56Z START step0-attempt2-dir
2026-10-27T14:54:56Z END step0-attempt2-dir exit=0
2026-10-27T14:54:56Z START step0-signals
2026-10-27T14:54:56Z END step0-signals exit=0
2026-10-27T14:54:57Z START step0-pinned-shas
2026-10-27T14:54:57Z END step0-pinned-shas exit=0
2026-10-27T14:54:58Z START step1-manifest
2026-10-27T14:55:37Z END step1-manifest exit=0
2026-10-27T14:55:37Z START step1-manifest-sha
2026-10-27T14:55:37Z END step1-manifest-sha exit=0
2026-10-27T14:55:37Z START step2-harness
2026-10-27T15:11:20Z END step2-harness exit=0
2026-10-27T15:11:20Z START step3-gates
2026-10-27T15:11:23Z END step3-gates exit=0
2026-10-27T15:11:23Z START step4-paste-auto
2026-10-27T15:12:19Z END step4-paste-auto exit=0
2026-10-27T15:12:19Z START step4-paste-declared
2026-10-27T15:12:51Z END step4-paste-declared exit=0
2026-10-27T15:12:51Z START step4-paste-check
2026-10-27T15:12:51Z END step4-paste-check exit=0
2026-10-27T15:12:51Z START step5-urkiv-auto
2026-10-27T15:14:05Z END step5-urkiv-auto exit=0
2026-10-27T15:14:05Z START step5-urkiv-declared
2026-10-27T15:14:57Z END step5-urkiv-declared exit=0
2026-10-27T15:14:57Z START step6-routing
2026-10-27T15:16:54Z END step6-routing exit=0
2026-10-27T15:16:54Z START step6-routing-check
2026-10-27T15:16:54Z END step6-routing-check exit=0
2026-10-27T15:16:54Z START step7-v4-T
2026-10-27T15:23:26Z END step7-v4-T exit=0
2026-10-27T15:23:26Z START step7-v4-L
2026-10-27T15:29:59Z END step7-v4-L exit=0
2026-10-27T15:29:59Z START step7-holdout-T
2026-10-27T15:37:08Z END step7-holdout-T exit=0
2026-10-27T15:37:08Z START step7-holdout-L
2026-10-27T15:44:11Z END step7-holdout-L exit=0
2026-10-27T15:44:11Z START step7-le_v1-T
2026-10-27T15:55:15Z END step7-le_v1-T exit=0
2026-10-27T15:55:15Z START step7-le_v1-L
2026-10-27T16:06:24Z END step7-le_v1-L exit=0
2026-10-27T16:06:24Z START step7-competitive-check
2026-10-27T16:06:24Z END step7-competitive-check exit=0
2026-10-27T16:06:24Z START step8-verify
2026-10-27T16:20:54Z END step8-verify exit=0
2026-10-27T16:20:54Z START step8-verify-check
2026-10-27T16:20:55Z END step8-verify-check exit=0
2026-10-27T16:20:55Z START step9-pytest
2026-10-27T16:31:02Z END step9-pytest exit=0
2026-10-27T16:31:02Z ALL STEPS PASSED
```

## Deviations and operational notes

1. **No stop, no deviation.** No gated rule failed and no step was re-run. The only
   non-registered content in this note is the "(c) What the cartouche arm changed" read-out,
   the unrounded Brier deltas and the relation-to-attempt-1 paragraph, all read-only on the
   run's files; they change no verdict.
2. **Launch.** Addendum (2) planned attempt 4 to be launched with default signal dispositions
   in its own session under `caffeinate -dims`. For attempt 5 the run log records that
   `step0-signals` passed; this note does not record the launcher command beyond that.

## What follows

These are not actions taken here.

* The pre-registration and the attempt-1 note are not edited by this note.
* Rule (b) outcome 2 is already carried out (`97ddff2`); the pooled fallback stays off by default.
* §5.1 of `docs/kri-selftest-fixes-2026-10-26.md` (a sweep of the heuristic constants) stays
  open and would need its own pre-registration.
* Merging the branch is the lead's decision; nothing here pushes or merges.
