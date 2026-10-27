# KRI fixes: pre-registered measurement results, attempt 1 (2026-10-26)

This is the run of `docs/kri-fixes-preregistration-2026-10-26.md` §5 on branch
`kri-fixes-2026-10-26`. Nothing in the code, the rules or the inputs was changed during the
run. The fixes made after it are on later commits, recorded in the 2026-10-27 addendum to
the pre-registration; they do not alter anything this attempt measured.

**Verdict: FAILED at step 3. Gated rule (c) failed for both `all_on` and
`cartouche_only` (3,300 boundary errors outside cartouches, against 3,299 for `all_off`).
Under rule (h) the run stopped there, so steps 4–9 did not run and rules (e), (e2), (e3)
and (f) have no result.** Rule (a) passed. Rule (b) produced the decision **DISABLE**
(off-better 7 > on-better 4 over positions).

Under rule (h), this attempt's numbers cannot be reused. The pre-registration requires
three things before anything ships:

1. a fix on a new commit;
2. a dated addendum to the pre-registration;
3. a re-run of all of §5 into `…-attempt2`.

The numbers below record what attempt 1 measured. None of them is a result that the next
attempt may carry forward.

**No number here is an independent accuracy figure.** This was a pilot-informed
registration: the first 500 test rows were decoded before the rules were fixed (§3).
BBAW's lexicon-assisted numbers are not held-out (§2), and BBAW supplies 1,013 of the
3,473 test lines. Even if every rule had passed, the three heuristics would ship **as
heuristics**. The pooled fallback's own benefit is **unmeasured** and must not be quoted:
(b) did not reach outcome 3.

**Corrections after review (2026-10-27).** Five reporting corrections were applied to
this note after Astra's review of `6b66d34`; they are listed in "Corrections after
review" at the end. None changes a count, a gate or the verdict. Attempt 1 stays
**FAILED**. The step-3 gate output is now quoted complete and verbatim, in its own
section, apart from the corrections.

## Run approval (lead's decision, recorded as given)

The pre-run pair review took three rounds. In its final verdict, Astra returned
`fix_first` for one reason only, a verification gap: its sandbox could not create scratch
directories, so it could not run the fixture tests or the dry run. It stated: "No
additional code defect was found in the reviewed fixes". Opus then ran those checks:

| Check | Result |
| --- | --- |
| `tests/test_verify_release.py` | 61 passed |
| `tests/test_check_kri_fixes_gates.py` | 27 passed |
| Steps 0–1 dry run | exit 0, split-manifest sha OK |

The lead therefore approved the run at commit `1733c165e23c017d0c121e7c9b9809f67c325b8e`.

## Step 0: pinned state

| Item | Value | Source in `$R` |
| --- | --- | --- |
| Attempt directory `$R` | `~/egyptology-runs/kri-fixes-2026-10-26-attempt1` (first attempt; no earlier directory existed) | runner stdout |
| Approved commit | `1733c165e23c017d0c121e7c9b9809f67c325b8e` | `approved_commit.txt` |
| HEAD at run | `1733c165e23c017d0c121e7c9b9809f67c325b8e` (equal; tree clean, branch and toplevel asserted) | `commit.txt`, `run_log.txt` |
| `data/processed/examples.csv` | `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` (pinned, OK) | `shas.txt`, `pinned_shas.txt` |
| `scripts/eval_guards.py` | `17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950` (pinned, OK) | `shas.txt` |
| `scripts/run_reading_model_eval.py` | `373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5` (pinned, OK) | `shas.txt` |
| `scripts/run_kri_fixes_eval.py` | `79033a49b6e4263ff85ad1d4fed266eb9956577000003f40a689cae5a4b219eb` | `shas.txt` |
| `scripts/check_kri_fixes_gates.py` | `5349e9cfae59d83f9684ba254ad8d65ba671f3af8ce1b14ac045269a293dab14` | `shas.txt` |
| `scripts/run_kri_fixes_prereg.sh` | `066ac2d1d2b8d6166e34f8f6bc5b6a879dbc10e3d1ade6cfac45f9cc793345e0` | `shas.txt` |
| Interpreter | Python 3.12.13 (full `pip freeze` in the file) | `env.txt` |
| Split manifest (step 1) | `ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba`, OK | `manifest_sha.txt` |
| Split | 59,504 aligned sentences, train 52,210 / test 3,473 (BBAW 1,013, TLA 2,460); dropped 829 exact duplicates, 202 near-duplicates, 2,790 lexicon-leaking rows, all as §2 | `step1.txt`, `step2.txt` |

## Rule table

| Rule | Status | Decided on (integer counts) | Source file |
| --- | --- | --- | --- |
| (a) collateral, `all_on` | **PASS** | other: better 0, worse 0, net 0 ≤ 5 (n = 25,711). Neighbour: better 0, worse 0, net 0 ≤ 2 (n = 60). Lines exact: gained 0, lost 1, net 1 ≤ 3; whole-line sign-test p = 1 (one discordant line, TLA:1132, lost; exact two-sided test on gained 0 / lost 1, computed from these counts with the harness's `sign_test_p`; the checker prints no p for lines). Position sign-test p n/a (no discordant positions) | `step3_gates.txt`, `kri_summary.csv` |
| (a) collateral, `cartouche_only` | **PASS** | other net 0 ≤ 5. Neighbour net 0 ≤ 2. Lines gained 0, lost 0, net 0 ≤ 3; whole-line sign-test p n/a (no discordant lines) | same |
| (b) firing positions | **DECISION: DISABLE** | n = 37 positions in 31 lines. Positions: on-better 4, off-better 7, unchanged 26 (sign-test p = 0.5488, reported only). Lines: on-better 4, off-better 4, tied 23 (line sign-test p = 1). Outcome 2 applies because off-better > on-better | `step3_gates.txt` |
| (c) boundary errors outside cartouches, `all_on` | **FAIL** | 3,300 vs `all_off` 3,299 | `step3_gates.txt`, `kri_summary.csv` |
| (c) boundary errors outside cartouches, `cartouche_only` | **FAIL** | 3,300 vs `all_off` 3,299 | same |
| (d) harness stage moves | **REPORTED** | 0 lines moved in each of `pooled_only`, `discount_only`, `cartouche_only` and `all_on`. The listing length equals the summary count (0) | `step3_gates.txt` |
| (e) expert paste 8/8 auto + declared | **NOT RUN** (stopped at step 3) | none | none |
| (e2) Urk. IV / St Andrews gate | **NOT RUN** | none | none |
| (e3) held-out stage routing | **NOT RUN** | none | none |
| (f) competitive sanity check + determinism | **NOT RUN** | none | none |
| (g) calibration | **REPORTED** | Brier, all positions: discount +0.000117323 (worse), correction +0.003600955 (worse), combined +0.003878482 (worse). With_reading: discount +0.000118036, correction +0.003622854, combined +0.003902069. Deltas computed before rounding (see (g) below) | `step3_gates.txt`, `kri_summary_calibration.csv` |
| (h) stop on failure | **APPLIED** | `END step3-gates exit=1` and `STOP at step3-gates (rule h)` | `run_log.txt` |

### Source-stratified counts

These come from `kri_summary.csv` and are reported only.

| Scope | Arm | acc_all | Firing n (+/−) | Other (+/−) | Lines exact (gained/lost) | Boundary errors outside cartouches | Cartouches split | Boundaries inside cartouches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | all_off | 0.766235 | 37 | n/a | 844 lines exact | 3,299 (FP 1,695 + FN 1,604) | 16 / 336 | 32 |
| all | cartouche_only | 0.766235 | 37 (+0/−0) | +0/−0 | 0 / 0 | 3,300 (FP 1,696 + FN 1,604) | 0 / 336 | 0 |
| all | all_on | 0.766119 | 37 (+4/−7) | +0/−0 | 0 / 1 | 3,300 | 0 / 336 | 0 |
| BBAW | all_off | 0.740056 | 21 | n/a | 182 | 828 | 0 / 0 | 0 |
| BBAW | all_on | 0.739408 | 21 (+0/−6) | +0/−0 | 0 / 0 | 828 | 0 / 0 | 0 |
| TLA | all_off | 0.780865 | 16 | n/a | 662 | 2,471 | 16 / 336 | 32 |
| TLA | all_on | 0.781046 | 16 (+4/−1) | +0/−0 | 0 / 1 | 2,472 | 0 / 336 | 0 |

Other reported (c) figures, for all lines:

| Measure | `all_off` | `cartouche_only` / `all_on` |
| --- | --- | --- |
| Boundary TP / FP / FN | 20,731 / 1,726 / 1,604 | 20,730 / 1,696 / 1,605 |
| Boundary F1 | 0.925656 | 0.926253 |
| Exact segmentations | 1,816 | 1,818 |

`pooled_only` and `discount_only` have the same segmentation as `all_off`.

## (b) Firing-position listing, in full

This is quoted from `step3_gates.txt`, byte for byte (the listing lines, without the
checker's four-space indent; the complete file is quoted in "Step 3 gate output" below).
`off` is `all_off` and `on` is `all_on`; `(1)`/`(0)` marks a correct/incorrect
prediction. All rows come from the public TLA/BBAW corpus. The gold of BBAW:3313#2 is
`6.〈nw.t〉` with U+2329 and U+232A, exactly as in the corpus and the gate file (an earlier
version of this note had silently replaced them with U+3008 and U+3009).

```
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
```

The on-better positions are TLA:154#4, TLA:588#1, TLA:1123#1 and TLA:2119#1. The
off-better positions are TLA:1132#3, BBAW:2621#3, #7, #14 and #16, BBAW:2762#9 and
BBAW:2830#14. One whole line lost exactness: TLA:1132, through its firing position #3, in
`pooled_only` and `all_on`. No line gained exactness. No position outside the firing
cohort changed outcome in any arm.

## (d) Harness stage-change listing, in full

There are 0 stage moves in every arm, so the listing is empty. As §7.3 registered, the
harness router receives the gold-spaced paste. A count of 0 here is therefore not evidence
about routing on real pastes. That evidence was meant to come from (e2)/(e3), and those
did not run.

## Routing-change listing (rule e3)

There is none: step 6 did not run, so `routing.csv` and `step6_gates.txt` do not exist.
The gate files for steps 4, 6, 7 and 8, which §6 asks to quote, were never produced for
the same reason.

## (g) Calibration, reported only

Brier score, lower is better. The scores are from `kri_summary_calibration.csv`, which
rounds them to 5 decimal places. **The deltas are computed before rounding**: each Brier
score was recomputed from `kri_positions.csv` (the confidences as the harness wrote them,
6 decimal places; every recomputed score rounds to the CSV's value) and then subtracted.
The step-3 checker prints differences of the already-rounded scores, which is why its
with_reading lines read +0.00363 and +0.00391; those lines are quoted verbatim below and
are superseded by the figures here.

| Confidence | Brier, all positions (n = 25,808) | Brier, with_reading (n = 25,652) |
| --- | --- | --- |
| `all_off` legacy (pre-branch) | 0.18847 | 0.18961 |
| `all_off` undiscounted (corrected) | 0.19207 | 0.19324 |
| `discount_only` discounted (corrected + /k) | 0.19219 | 0.19336 |
| `all_on` discounted (shipped) | 0.19235 | 0.19352 |

| Comparison | All positions | with_reading |
| --- | --- | --- |
| Discount effect: `discount_only` discounted − `all_off` undiscounted | **+0.000117323** | **+0.000118036** |
| Correction effect: `all_off` undiscounted − `all_off` legacy | +0.003600955 | +0.003622854 |
| Combined effect: `all_on` discounted − `all_off` legacy (includes prediction changes; attributes nothing to /k) | +0.003878482 | +0.003902069 |

Unrounded scores (from `kri_positions.csv`): all positions — legacy 0.188468582,
undiscounted 0.192069538, `discount_only` discounted 0.192186860, `all_on` discounted
0.192347065; with_reading — 0.189614735, 0.193237589, 0.193355625, 0.193516804.

**The discount moved the Brier score up by about 0.00012 (+0.000117323 over all
positions, +0.000118036 with a reading), which is worse, in both subsets.**
The full-split result runs the other way from the 50-row pilot, where the discount
lowered the score by about 0.0017. The correction of `be24b96` #1 also raised the Brier
score. There is no pass rule here, and none is inferred after the fact.

Reliability bins, `with_reading`. Each cell is n @ mean confidence / accuracy, for the bins
0.0–0.1 through 0.9–1.0:

| Confidence | Bins |
| --- | --- |
| `all_off` legacy | 0 / 0 / 31 @ 0.258/0.226 / 202 @ 0.345/0.361 / 526 @ 0.440/0.508 / 1322 @ 0.532/0.522 / 1281 @ 0.654/0.562 / 1016 @ 0.750/0.657 / 2427 @ 0.842/0.778 / 18847 @ 0.987/0.820 |
| `all_off` undiscounted | 207 @ 0.053/0.464 / 340 @ 0.152/0.524 / 379 @ 0.247/0.512 / 438 @ 0.345/0.514 / 434 @ 0.436/0.498 / 1005 @ 0.527/0.514 / 979 @ 0.648/0.583 / 1006 @ 0.752/0.703 / 2187 @ 0.838/0.797 / 18677 @ 0.985/0.821 |
| `discount_only` discounted | 222 @ 0.053/0.446 / 382 @ 0.147/0.503 / 683 @ 0.248/0.457 / 396 @ 0.347/0.533 / 434 @ 0.436/0.498 / 686 @ 0.539/0.577 / 979 @ 0.648/0.583 / 1006 @ 0.752/0.703 / 2187 @ 0.838/0.797 / 18677 @ 0.985/0.821 |
| `all_on` discounted | 224 @ 0.053/0.451 / 382 @ 0.147/0.503 / 678 @ 0.248/0.459 / 396 @ 0.347/0.535 / 434 @ 0.436/0.498 / 688 @ 0.539/0.577 / 986 @ 0.648/0.579 / 1009 @ 0.751/0.704 / 2190 @ 0.838/0.795 / 18665 @ 0.985/0.821 |

## Where the (c) failure comes from

This is a post-run diagnostic, not a registered step. It was read-only, using
`kri_lines.csv` (per-line counts, `cartouche_only` against `all_off`).

The constraint changed the boundary counts on 16 lines, all of them TLA. On 14 of the 16,
it removed only false boundaries inside the cartouche. Two lines carry the rest:

* **TLA:1980** (harness row id; TLA sentence S885, 28 glyphs) causes the gated +1:

  | Count | Change |
  | --- | --- |
  | Boundaries inside the cartouche | −2 |
  | Total false positives | −1 |
  | False positives outside cartouche spans | **+1** |

  The line's net false positives fell, but one error appeared outside the span. On all
  3,472 other lines, the outside-cartouche error count is unchanged.

  The two post-run diagnoses (2026-10-27, not a registered step) located it. The
  cartouche is [12, 24) (12 glyphs). Gold boundaries {3, 9, 10}. `all_off` predicts
  {3, 9, 10, 12, 13, 23, 25} (false positives 12, 13, 23, 25; 13 and 23 inside);
  `cartouche_only` predicts {3, 9, 10, 12, 24, 25} (false positives 12, 24, 25, all
  outside). The constraint removed 13 and 23 and **introduced 24**, the closing edge. The
  cause is the candidate window: it counted raw glyphs (10), every start from 15 to 23 is
  forbidden, and the only extra candidate was the span that is exactly the cartouche, so
  the 13-glyph group [12, 25) (cartouche plus the following sign) was never offered and
  every path had to cut at 24. The objective's own scorer ranks the legal grouping
  without that cut, {3, 9, 10, 12, 25}, at −122.0077 against the −126.3658 the decoder
  returned. This is an implementation defect; the addendum of 2026-10-27 to the
  pre-registration records the fix.
* **TLA:121** (harness row id; TLA sentence S821) lost a **correct** boundary. Positions
  are zero-based glyph offsets, boundary `b` sits immediately before glyph `b`, and
  spans are half-open. The line's one matched cartouche is [4, 11). The gold groups are
  `nswt-bꞽ.t | 𓍹𓅭𓇳 zꜣ-rꜥw | 𓏏𓏏𓇋𓍺 ttꞽ | ꜥnḫ | ḏ.t`, boundaries {4, 7, 11, 12}: the
  gold **cuts inside the matched pair at 7**, separating the title `zꜣ-rꜥw` (with the
  opening sign) from the name (with the closing sign). `all_off` predicts {4, 5, 7, 12};
  `cartouche_only` predicts {4, 12}. The constraint therefore removed the false boundary
  at 5 and the **correct** boundary at 7, both inside the span (TP −1, FN +1, FP −1,
  inside −2). The missed boundary at 11, on the span's closing edge, is missed in both
  arms and predates the constraint. Because the gold boundary lies inside a matched
  cartouche, the constrained decoder cannot produce it by design; no legal grouping
  scores better than the one chosen. (c) does not gate this, but it is a real loss, and
  it is a consequence of the rule itself, not of an implementation defect.
  (Source: the two post-run diagnoses of 2026-10-27, which re-decoded this line from the
  run commit's code; not a registered step.)

`all_on` and `cartouche_only` have identical per-line segmentation counts (0 lines differ).

## Mechanisms

**Confirmed** (read directly from the run's files):

* The cartouche constraint does what it was written to do on this split:
  * cartouches split: 16 → 0, out of 336;
  * boundaries inside cartouches: 32 → 0;
  * false positives: −30;
  * exact segmentations: +2;
  * boundary F1: 0.925656 → 0.926253.
* (c) failed on one boundary error, on one line (TLA:1980). That line's total false
  positives fell, but one false positive now sits outside every cartouche span. The
  registered rule counts only outside-span errors, so the line counts against the
  constraint.
* On TLA:121, the constraint removed a gold boundary inside a cartouche span.
* The pooled fallback fired at 37 positions in 31 lines (21 BBAW, 16 TLA), every one in
  `all_on`. It lost more than it gained over positions (4 vs 7), and lines tied 4 vs 4.
  Four of the seven losses are one group in one line, BBAW:2621 (`2` → `1/2`, stage count
  3, pooled 118). By source: BBAW +0/−6, TLA +4/−1.
* Three of the four gains (TLA:154#4, 588#1, 1123#1) are case or bracket notation
  variants of the reading the model already gave (`Sšm-nfr` → `sšm-nfr`,
  `ḥm.t-nṯr-Ḥw.t-Ḥr.w` → `ḥm(.t)-nṯr-ḥw.t-ḥr.w`). The scorer counts them as gains
  because it matches exact strings. BBAW:2896#1 is the same case variant in the other
  direction (gold `Sšm-nfr`). It was wrong in both arms.
* The `/k` discount changes no prediction (`discount_only` is identical to `all_off` in
  every count). It raised the Brier score by 0.00012.
* No arm moved any line's stage in the harness.

**Plausible** (consistent with the files, but not shown by them):

* (Moved to the (c) section above, now confirmed by a post-run re-decode, not by the
  run's files: on TLA:1980 the new false boundary is at 24, the cartouche's closing edge;
  on TLA:121 the gold cuts the matched pair at 7.) TLA:121's two gold groups each hold
  one half of the pair, which is the shape of the minority (13 of 1,854) in the corpus
  count of §1.
* The `2` → `1/2` change at BBAW:2621 happens because the numeral group's pooled
  distribution is dominated by a fraction reading from other stages or contexts. The
  pooled model then overrides a stage reading that was correct on a near-singleton count.

**Unresolved:**

* (Resolved after the run by the 2026-10-27 diagnoses: the TLA:1980 error is a decoder
  defect, the candidate window, not an artefact of the gold. See the (c) section.)
* Whether the pooled fallback would come out differently once the transition-smoothing
  defect of §7.5 is fixed.
* Every effect that (e), (e2), (e3) and (f) were meant to detect. Those rules did not run.

## Step 3 gate output (complete, verbatim)

`step3_gates.txt`, all 68 lines, unedited. The last line is the runner's own stop
message, which the step's redirect also captured. The with_reading Brier deltas printed
here are differences of rounded scores; the (g) section above gives the deltas before
rounding.

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
(c) all_on: boundary errors outside cartouches 3300 vs all_off 3299  FAIL  (reported: F1 0.9262527646835415, seg_exact 1818, cartouches split 0 of 336, boundaries inside cartouches 0)
(c) cartouche_only: boundary errors outside cartouches 3300 vs all_off 3299  FAIL  (reported: F1 0.9262527646835415, seg_exact 1818, cartouches split 0 of 336, boundaries inside cartouches 0)
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
FAIL (c) all_on: 3300 > 3299
FAIL (c) cartouche_only: 3300 > 3299
harness: FAIL
STOP at step3-gates (exit 1); see /Users/lediodurmishaj/egyptology-runs/kri-fixes-2026-10-26-attempt1/run_log.txt
```

## Durations

| What | Duration | Kind | Source |
| --- | --- | --- | --- |
| Step 1 (manifest, 1-row dry decode) | 10.7 s | internal | `step1.txt` "total" |
| Step 2 harness, 3,473 rows × 5 arms | 743.9 s total (models 5.3 s; decode 731.5 s, 0.211 s per row) | internal | `step2.txt` |
| Step 2 harness | 21:45:44Z → 21:58:09Z = 12 min 25 s | wall clock | `run_log.txt` |
| Step 3 checker | 21:58:09Z → 21:58:11Z ≈ 2 s | wall clock | `run_log.txt` |
| **Whole run, START step0 to STOP** | **21:45:33Z → 21:58:11Z = 12 min 38 s** | wall clock | `run_log.txt`; the wrapper's own start/stop stamps agree |

## Deviations and operational notes, stated plainly

1. **The stop is not a deviation.** The run stopped at step 3 because a gated rule
   failed, exactly as rule (h) requires. No code, rule, input or threshold was changed,
   and no step was re-run.
2. **Other processes were running.** §5 says to run "with nothing else running". When the
   run was launched, these processes were also running on the Mac:
   * another session's single-file `pytest` (`tests/test_audit_ops.py`) in a different
     worktree;
   * two read-only Codex review tasks;
   * a Streamlit app and a small scanner script in an unrelated project.

   None was a benchmark or a full-corpus job. They can affect durations. Nothing was
   observed to suggest they affected outputs, but that was not tested.
3. **How the runner was launched.** The registered runner was started under `nohup bash
   -c …` with `KRI_RUNS_BASE` and `KRI_STOP_AFTER` explicitly unset. The wrapper also
   wrote start/stop timestamps and the exit code into a scratch directory outside the
   repository. The runner command and its argument were exactly as registered.
4. **No interruption.** The process ran to its STOP without being killed or resumed.
5. **The (c) diagnostic was not registered.** The per-line analysis above is post-run and
   read-only. It changes no verdict.
6. **The §6 listings are incomplete.** §6 asks for the routing-change listing and for the
   step-6/7/8 gate files. Those steps did not run, so they cannot be included.

## Corrections after review (2026-10-27)

Applied after Astra's review of `6b66d34`. None changes a count, a gate decision or the
verdict.

1. **Brier deltas before rounding.** (g) gave with_reading deltas of +0.00363 and
   +0.00391, differences of 5-decimal scores. Computed before rounding they are
   +0.003622854 and +0.003902069 (all positions: +0.003600955 and +0.003878482, which
   rounded as printed). The discount deltas are +0.000117323 / +0.000118036.
2. **BBAW:3313#2 gold, verbatim.** The note had `〈`/`〉` (U+3008/U+3009); the corpus
   and the gate file have U+2329/U+232A. The (b) listing is now generated from the gate
   file.
3. **Whole-line p beside rule (a).** `all_on`: gained 0, lost 1, p = 1;
   `cartouche_only`: no discordant line.
4. **Complete step-3 gate output** is quoted in its own section, unedited, apart from
   these corrections.
5. **TLA:121 described precisely**: cartouche [4, 11), gold boundary at 7 inside the
   matched pair, constraint removes FP 5 and TP 7, FN 11 missed in both arms. TLA:1980 is
   located likewise (new FP at 24, the window defect).

What changed in the code afterwards, and why, is in the 2026-10-27 addendum to
`docs/kri-fixes-preregistration-2026-10-26.md`. No attempt-1 number carries into attempt 2.

## What follows under the pre-registration

These are not actions taken here.

* Rule (h) requires three things before any re-run:
  1. a fix on a new commit;
  2. a dated addendum to `docs/kri-fixes-preregistration-2026-10-26.md`;
  3. a full re-run of §5 into `~/egyptology-runs/kri-fixes-2026-10-26-attempt2`.
* No number from attempt 1 may be reused.
* Attempt 1 stays **FAILED**.
* The (b) outcome of this attempt was DISABLE. Under the no-reuse rule, the next attempt
  decides (b) afresh.
