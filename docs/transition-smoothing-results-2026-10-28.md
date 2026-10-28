# Transition smoothing in the reading model: results (2026-10-28)

**Verdict: NULL. Smoothing is not shipped; the default add-k estimator stays.** The primary arm
`c2_transition_only` failed the hard rule (c') on the test split (lower bound of the paired 95%
CI of acc - acc(off) is -0.00124, not > 0). Per the frozen registration (section 7, retry rule),
a primary-arm failure on test is "it failed": it does not go back to dev and is not re-run on the
same split, because the failure is substantive and not a harness or procedural fault.

Frozen document: `docs/transition-smoothing-preregistration-2026-10-28.md` (section numbers
below refer to it). Branch `transition-smoothing-2026-10-28`.

## 1. Run identity

| Item | Value |
| --- | --- |
| Dev attempt directory | `/Users/lediodurmishaj/egyptology-runs/transition-smoothing-2026-10-28-dev-attempt1` |
| Test attempt directory | `/Users/lediodurmishaj/egyptology-runs/transition-smoothing-2026-10-28-test-attempt1` |
| Dev phase approved commit (= `commit.txt`) | `2ea833aadf1e9e591721fa4c0cead29f0345c0c2` |
| Dev record commit (only change: `docs/transition-smoothing-dev-record-2026-10-28.json`) | `83fa4f5ce5805a007cb26b036dac62f90e001b26` |
| Test phase approved commit (= `commit.txt`) | `83fa4f5ce5805a007cb26b036dac62f90e001b26` |
| Test manifest sha256 (`split_manifest.csv`) | `ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba` |
| Dev manifest sha256, draw rate 0.10 (used) | `52415842fbb209d955b5d28d48011f462cb5a0d756400c1f8e2d76f191263344` |
| Dev manifest sha256, draw rate 0.20 (pinned, not used) | `11dfe145090bb6a3ee4d846f428b595a8fba79787662193d9a20677b3328a0b3` |
| Corpus `data/processed/examples.csv` sha256 | `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` |
| `scripts/eval_guards.py` | `17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950` |
| `scripts/run_reading_model_eval.py` | `373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5` |
| `scripts/run_kri_fixes_eval.py` | `79033a49b6e4263ff85ad1d4fed266eb9956577000003f40a689cae5a4b219eb` |
| `scripts/check_kri_fixes_gates.py` | `5349e9cfae59d83f9684ba254ad8d65ba671f3af8ce1b14ac045269a293dab14` |
| `scripts/run_transition_smoothing_eval.py` | `c66ebd32a1484c819379e605692f95c9fc4d9e61f83e10992959ace2ac7adcf6` |
| `scripts/check_transition_smoothing_gates.py` | `e8dafcffd54776dfc9280a9ad3ca65c88c57c941b8f840d44ac49a42802ba38a` |
| `scripts/run_transition_smoothing_prereg.sh` | `165ba705db1f891557df9b5b5406607090ef1ebe3950c1cb71cc5ab37933767a` |
| `app/services/reading_model.py` | `12a95ebef4899c620035597d7e1d17f861364b33b7a8a8d308cf4c4d687955d5` |
| `app/services/stage.py` | `eab6a3b10ae307af0b59ce93f4a084a1e374d88580066cc96dfe226bad520f62` |
| Python | 3.12.13 (venv pins in each attempt's `env.txt`) |

The shas above are those of the test attempt's `shas.txt`; the dev attempt's `shas.txt` and
`pinned_shas.txt` are identical for the files that both list. The test run's step-1 preflight passed
(primary arm read from the committed dev record: `c2_transition_only`; the only file changed between
the dev-phase commit and HEAD was the dev record). Step 1 reported 59,504 aligned sentences, 52,210
train and 3,473 test (BBAW 1,013, TLA 2,460); from the test candidates 829 exact duplicates, 202
near-duplicates and 2,790 lexicon-leaking rows were dropped.

Run log of the test attempt: steps 0, 1 and 2 exited 0 (step 2, the four-arm decode, took 1,382.7 s
in total, 08:44:38 to 09:07:42 UTC); step 3 (gates) exited 1 at 09:07:44 UTC. The log's closing line
is the runner's generic rule-(h) text ("fix a harness or procedural fault on a new commit, addendum,
re-run the phase"). It is printed for any non-zero step and does not mean a fault occurred here:
the gate checker's own output is `FAIL (c') c2_transition_only: lower bound of the paired 95% CI of
acc - acc(off) is -0.00124, not > 0`, and every integrity check that could signal a fault passed
(rule (e) holds with equality as expected, the decoded stage equals off's on every line, preflight
passed).

## 2. Dev stage (section 5)

Draw rate 0.10; the 0.20 step was not needed (minimums met). Dev draw: 5,072 rows drawn, 291 exact
duplicates, 59 near-duplicates and 3,332 lexicon-leaking rows dropped; 1,390 dev rows (BBAW 409, TLA
981); 50,470 fit rows. Minimum counts: 10,363 dev positions (>= 2,000), 376 members of the R5 mechanism
population (>= 100): `dev-manifest: PASS`.

| Arm | Correct | Acc | Delta vs off (positions) | Eligible (Delta > 0) |
| --- | --- | --- | --- | --- |
| off | 7,795 | 0.75220 | +0 | no |
| c2_transition_only | 7,820 | 0.75461 | +25 | yes |
| c2 | 7,792 | 0.75191 | -3 | no |
| c3 | 7,788 | 0.75152 | -7 | no |

Eliminations: `c2` (Delta -3) and `c3` (Delta -7) were not eligible because eligibility requires
Delta > 0 strictly. The eligible set was therefore `['c2_transition_only']`, best arm b =
`c2_transition_only`; the walk compared it with itself (difference +0.00000, CI [+0.00000, +0.00000])
and it qualified: **primary arm `c2_transition_only`**. Dev result: PASS (the dev stage only selects;
the confirmatory CI requirement is rule (c') on test). Bootstrap: 10,000 resamples, seed 20261026.

Dev paired counts versus off (from `dev_summary.csv`): c2_transition_only 94 better / 69 worse /
10,200 unchanged (BBAW 40/37, TLA 54/32); c2 100/103; c3 100/107. Dev boundary F1 was 0.9282 for
every arm (boundary errors 1,285 each).

## 3. Test gate results (step 3, `step3_gates.txt`)

Test positions: 25,808 in 3,473 groups (each TLA/BBAW sentence its own group); primary arm
`c2_transition_only`.

| Rule | Status | Counts it was decided on |
| --- | --- | --- |
| (a) Expert paste gate | NOT RUN | step 4 never started (stopped at step 3) |
| (b) Urk. IV / St Andrews | WITHDRAWN | removed from this registration before the run (section 7 and 10, item 16): it reads private St Andrews rows, which this run does not read |
| (c') Overall test accuracy | **FAIL** | primary: 19,780 / 25,808 correct (acc 0.76643) vs off 19,775 (0.76624); diff +0.00019 (+5 positions); paired 95% CI [-0.00124, +0.00168]; better 177 / off-better 172 / unchanged 25,459. Lower bound is not > 0 |
| (d') Mechanism positions | REPORTED | section 3.2 |
| (e) Boundary errors | PASS | 3,300 for primary and off (fp 1,695, fn 1,605); equal, as expected |
| (f') Stage routing | line-level part holds; paste part NOT RUN | every arm decoded under off's stage on every test line: yes; 194 would-route-differently lines for the primary (listed in section 3.4); the expert-paste identity check was step 4 and did not run |
| (g') Competitive sets | NOT RUN | step 6 never started |
| (h) Calibration | REPORTED | Brier: off 0.19219, c2_transition_only 0.1924, c2 0.19243, c3 0.19185; reliability bins in `test_calibration.csv` in the attempt directory |
| (i) Runtime | REPORTED | decode: off 47.5 s, c2_transition_only 46.8 s, c2 47.9 s, c3 52.4 s; fit_all_models 5.3 s; routing (off) 292.5 s, hypothetical routing c2_transition_only 289.4 s, c2 291.3 s, c3 300.5 s; discount tables derived in 0.31 s. Nothing measurable |

### 3.1 (c') all four arms and per source

| Arm | Correct / 25,808 | Acc | Diff vs off | 95% CI (paired) | Better / off-better / unchanged | BBAW correct / 9,252 (better/worse) | TLA correct / 16,556 (better/worse) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off | 19,775 | 0.76624 | | | | 6,847 | 12,928 |
| c2_transition_only (PRIMARY) | 19,780 | 0.76643 | +0.00019 (+5) | [-0.00124, +0.00168] | 177 / 172 / 25,459 | 6,855 (75/67) | 12,925 (102/105) |
| c2 (record only) | 19,713 | 0.76383 | -0.00240 (-62) | [-0.00410, -0.00071] | 195 / 257 / 25,356 | 6,836 (82/93) | 12,877 (113/164) |
| c3 (record only) | 19,729 | 0.76445 | -0.00178 (-46) | [-0.00344, -0.00008] | 209 / 255 / 25,344 | 6,833 (79/93) | 12,896 (130/162) |

Per-source accuracy of the primary: BBAW 0.7409 vs off 0.7401 (+8 positions), TLA 0.7807 vs off
0.7809 (-3 positions). Only the primary arm is confirmatory; c2 and c3 are shown for the record and
cannot be shipped from this run whatever their numbers (section 5). BBAW's lexicon-assisted
numbers are not held-out (`LEXICON_TAINTED_SOURCES`): the run uses the Helsinki lexicon as the app
does, so this test split is not an independent held-out validation in that respect, and every aggregate
is also written per source. Lines exactly right: off 844/3,473, c2_transition_only 831, c2 827, c3 830.

### 3.2 (d') mechanism positions

Population: positions whose gold previous reading has V_obs = 1 in the fitted `_transition` table, in bands by N of that context.

No band is under 30 positions (the smallest, N >= 4, has n = 105), so the N < 30 guard does not bite here. The single-digit paired counts are still noise-sized and no claim rests on any one band.

| Arm | Band (N of previous reading) | n | correct at i (off) | correct at i-1 (off) | paired at i (+/-) | paired at i-1 (+/-) | own-path V=1 share | overlaps |
|---|---|---|---|---|---|---|---|---|
| off | all | 989 | 756 (756) | 436 (436) | +0/-0 | +0/-0 | 516/989 (0.522) | 51 |
| off | 1 | 724 | 544 (544) | 274 (274) | +0/-0 | +0/-0 | 339/724 (0.468) | 33 |
| off | 2-3 | 160 | 119 (119) | 90 (90) | +0/-0 | +0/-0 | 99/160 (0.619) | 14 |
| off | 4+ | 105 | 93 (93) | 72 (72) | +0/-0 | +0/-0 | 78/105 (0.743) | 4 |
| c2_transition_only | all | 989 | 755 (756) | 416 (436) | +11/-12 | +2/-22 | 490/989 (0.495) | 51 |
| c2_transition_only | 1 | 724 | 543 (544) | 255 (274) | +8/-9 | +0/-19 | 314/724 (0.434) | 33 |
| c2_transition_only | 2-3 | 160 | 119 (119) | 88 (90) | +2/-2 | +0/-2 | 97/160 (0.606) | 14 |
| c2_transition_only | 4+ | 105 | 93 (93) | 73 (72) | +1/-1 | +2/-1 | 79/105 (0.752) | 4 |
| c2 | all | 989 | 753 (756) | 414 (436) | +11/-14 | +2/-24 | 487/989 (0.492) | 51 |
| c2 | 1 | 724 | 541 (544) | 253 (274) | +8/-11 | +0/-21 | 311/724 (0.430) | 33 |
| c2 | 2-3 | 160 | 119 (119) | 88 (90) | +2/-2 | +0/-2 | 97/160 (0.606) | 14 |
| c2 | 4+ | 105 | 93 (93) | 73 (72) | +1/-1 | +2/-1 | 79/105 (0.752) | 4 |
| c3 | all | 989 | 754 (756) | 417 (436) | +15/-17 | +3/-22 | 490/989 (0.495) | 51 |
| c3 | 1 | 724 | 542 (544) | 257 (274) | +11/-13 | +1/-18 | 315/724 (0.435) | 33 |
| c3 | 2-3 | 160 | 118 (119) | 88 (90) | +2/-3 | +0/-2 | 97/160 (0.606) | 14 |
| c3 | 4+ | 105 | 94 (93) | 72 (72) | +2/-1 | +2/-2 | 78/105 (0.743) | 4 |

Secondary diagnostic (REPORTED, never gated): gold previous reading V_obs = 2, N <= 3

| Arm | Band (N of previous reading) | n | correct at i (off) | correct at i-1 (off) | paired at i (+/-) | paired at i-1 (+/-) | own-path V=1 share | overlaps |
|---|---|---|---|---|---|---|---|---|
| off | all | 519 | 396 (396) | 248 (248) | +0/-0 | +0/-0 | 31/519 (0.060) | 7 |
| c2_transition_only | all | 519 | 399 (396) | 242 (248) | +6/-3 | +4/-10 | 25/519 (0.048) | 7 |
| c2 | all | 519 | 398 (396) | 238 (248) | +6/-4 | +4/-14 | 24/519 (0.046) | 7 |
| c3 | all | 519 | 395 (396) | 240 (248) | +5/-6 | +5/-13 | 25/519 (0.048) | 7 |

For the primary arm, the "own-path V=1" column (the checker's count of positions where the arm's own
Viterbi path used a V_obs = 1 previous reading) fell from 516/989 (0.522) under off to
490/989 (0.495). Correct readings at position i: 755 vs off 756 (paired +11/-12). Correct readings
at i-1 (the previous position): 416 vs off 436 (paired +2/-22), the loss concentrated in the N = 1
band (+0/-19). So the correction did what the mechanism argument predicted (fewer V_obs = 1 paths),
but at i-1 the moved paths cost 22 correct readings for 2 gained. By the claim rule of section 7 (d'), this is
reported as a change the mechanism argument predicted with no measured benefit at the positions it
targets.

### 3.3 (e) Boundary errors, every arm (PASS for the primary)

Every arm: boundary errors 3,300 (fp 1,695, fn 1,605), precision 0.9244, recall 0.9281, F1 0.9263,
exact segmentation 1,818/3,473. Identical across arms, as expected because the segmenter reads
`sign_reading` counts only.

### 3.4 (f') hypothetical-routing listing (reported, no threshold)

All three arms were decoded under off's stage on every test line (the gate part of (f') that ran). The
lines below are those where the arm's own estimator would have chosen a different stage than off, as
printed by the checker; the per-line off and hypothetical scores and coverages are in
`step3_gates.txt` in the test attempt directory (they are not repeated here to keep the note
readable). Totals: c2_transition_only 194 (131 off-E, 63 off-L), c2 202 (134/68), c3 220 (162/58);
every difference is an Earlier Egyptian / Late Egyptian swap.

**c2_transition_only** (194 lines; id, off stage > hypothetical stage; E = Earlier Egyptian, L = Late Egyptian):

TLA:10 E>L, TLA:28 E>L, TLA:35 E>L, TLA:50 E>L, TLA:54 E>L, TLA:61 E>L, TLA:114 E>L, TLA:154 L>E, TLA:162 L>E, TLA:169 L>E, TLA:190 E>L, TLA:195 L>E, TLA:277 L>E, TLA:296 L>E, TLA:298 L>E, TLA:299 E>L, TLA:309 E>L, TLA:331 E>L, TLA:361 E>L, TLA:377 E>L, TLA:380 E>L, TLA:403 L>E, TLA:404 E>L, TLA:424 E>L, TLA:431 E>L, TLA:438 E>L, TLA:442 E>L, TLA:471 E>L, TLA:492 L>E, TLA:499 L>E, TLA:588 L>E, TLA:590 E>L, TLA:601 E>L, TLA:622 E>L, TLA:630 L>E, TLA:631 L>E, TLA:665 L>E, TLA:686 E>L, TLA:735 E>L, TLA:738 E>L, TLA:765 E>L, TLA:786 L>E, TLA:819 E>L, TLA:864 E>L, TLA:866 E>L, TLA:877 E>L, TLA:889 E>L, TLA:894 E>L, TLA:924 E>L, TLA:927 L>E, TLA:1004 L>E, TLA:1072 E>L, TLA:1073 L>E, TLA:1077 L>E, TLA:1092 L>E, TLA:1160 L>E, TLA:1196 L>E, TLA:1203 L>E, TLA:1209 E>L, TLA:1309 L>E, TLA:1324 E>L, TLA:1328 E>L, TLA:1329 L>E, TLA:1444 E>L, TLA:1453 E>L, TLA:1454 E>L, TLA:1455 E>L, TLA:1462 L>E, TLA:1504 E>L, TLA:1553 E>L, TLA:1586 L>E, TLA:1623 E>L, TLA:1646 L>E, TLA:1650 E>L, TLA:1669 E>L, TLA:1685 E>L, TLA:1694 E>L, TLA:1701 L>E, TLA:1723 E>L, TLA:1777 E>L, TLA:1799 E>L, TLA:1814 E>L, TLA:1815 E>L, TLA:1836 E>L, TLA:1837 E>L, TLA:1886 E>L, TLA:1918 E>L, TLA:1962 E>L, TLA:1998 E>L, TLA:2004 E>L, TLA:2030 E>L, TLA:2116 E>L, TLA:2117 E>L, TLA:2119 E>L, TLA:2122 E>L, TLA:2373 L>E, TLA:2402 E>L, TLA:2414 E>L, TLA:2417 E>L, BBAW:2468 E>L, BBAW:2470 L>E, BBAW:2481 L>E, BBAW:2533 L>E, BBAW:2534 E>L, BBAW:2544 L>E, BBAW:2548 E>L, BBAW:2549 E>L, BBAW:2551 E>L, BBAW:2552 L>E, BBAW:2561 E>L, BBAW:2578 E>L, BBAW:2587 E>L, BBAW:2610 E>L, BBAW:2624 L>E, BBAW:2626 E>L, BBAW:2642 L>E, BBAW:2651 L>E, BBAW:2663 E>L, BBAW:2670 E>L, BBAW:2696 E>L, BBAW:2705 L>E, BBAW:2716 E>L, BBAW:2718 E>L, BBAW:2725 L>E, BBAW:2742 E>L, BBAW:2744 E>L, BBAW:2745 E>L, BBAW:2749 E>L, BBAW:2761 E>L, BBAW:2762 E>L, BBAW:2765 E>L, BBAW:2775 E>L, BBAW:2781 E>L, BBAW:2783 E>L, BBAW:2792 L>E, BBAW:2800 E>L, BBAW:2817 E>L, BBAW:2819 E>L, BBAW:2821 E>L, BBAW:2830 E>L, BBAW:2831 L>E, BBAW:2847 E>L, BBAW:2848 L>E, BBAW:2851 L>E, BBAW:2854 E>L, BBAW:2862 E>L, BBAW:2867 E>L, BBAW:2895 L>E, BBAW:2912 E>L, BBAW:2916 E>L, BBAW:2917 L>E, BBAW:2948 E>L, BBAW:2966 E>L, BBAW:2967 E>L, BBAW:2974 E>L, BBAW:3025 E>L, BBAW:3029 L>E, BBAW:3034 E>L, BBAW:3084 L>E, BBAW:3088 E>L, BBAW:3090 E>L, BBAW:3101 E>L, BBAW:3102 E>L, BBAW:3166 E>L, BBAW:3174 E>L, BBAW:3177 L>E, BBAW:3179 L>E, BBAW:3181 L>E, BBAW:3189 E>L, BBAW:3192 E>L, BBAW:3203 L>E, BBAW:3210 E>L, BBAW:3232 L>E, BBAW:3240 E>L, BBAW:3265 L>E, BBAW:3268 E>L, BBAW:3276 E>L, BBAW:3293 L>E, BBAW:3300 E>L, BBAW:3305 E>L, BBAW:3307 E>L, BBAW:3321 L>E, BBAW:3332 E>L, BBAW:3343 L>E, BBAW:3348 L>E, BBAW:3365 L>E, BBAW:3382 L>E, BBAW:3389 L>E, BBAW:3391 L>E, BBAW:3394 E>L, BBAW:3405 E>L, BBAW:3448 E>L, BBAW:3455 L>E, BBAW:3468 E>L

**c2** (202 lines; id, off stage > hypothetical stage; E = Earlier Egyptian, L = Late Egyptian):

TLA:10 E>L, TLA:28 E>L, TLA:35 E>L, TLA:50 E>L, TLA:54 E>L, TLA:61 E>L, TLA:114 E>L, TLA:154 L>E, TLA:162 L>E, TLA:169 L>E, TLA:190 E>L, TLA:195 L>E, TLA:277 L>E, TLA:296 L>E, TLA:298 L>E, TLA:299 E>L, TLA:309 E>L, TLA:331 E>L, TLA:361 E>L, TLA:377 E>L, TLA:380 E>L, TLA:403 L>E, TLA:404 E>L, TLA:424 E>L, TLA:431 E>L, TLA:438 E>L, TLA:442 E>L, TLA:471 E>L, TLA:492 L>E, TLA:499 L>E, TLA:588 L>E, TLA:590 E>L, TLA:601 E>L, TLA:622 E>L, TLA:630 L>E, TLA:631 L>E, TLA:645 E>L, TLA:665 L>E, TLA:686 E>L, TLA:735 E>L, TLA:738 E>L, TLA:765 E>L, TLA:786 L>E, TLA:819 E>L, TLA:864 E>L, TLA:877 E>L, TLA:889 E>L, TLA:894 E>L, TLA:924 E>L, TLA:927 L>E, TLA:1004 L>E, TLA:1072 E>L, TLA:1073 L>E, TLA:1077 L>E, TLA:1092 L>E, TLA:1123 L>E, TLA:1160 L>E, TLA:1196 L>E, TLA:1203 L>E, TLA:1209 E>L, TLA:1309 L>E, TLA:1324 E>L, TLA:1328 E>L, TLA:1329 L>E, TLA:1444 E>L, TLA:1453 E>L, TLA:1454 E>L, TLA:1455 E>L, TLA:1462 L>E, TLA:1504 E>L, TLA:1521 L>E, TLA:1553 E>L, TLA:1586 L>E, TLA:1623 E>L, TLA:1646 L>E, TLA:1650 E>L, TLA:1661 L>E, TLA:1669 E>L, TLA:1685 E>L, TLA:1694 E>L, TLA:1701 L>E, TLA:1710 E>L, TLA:1723 E>L, TLA:1777 E>L, TLA:1799 E>L, TLA:1814 E>L, TLA:1815 E>L, TLA:1836 E>L, TLA:1837 E>L, TLA:1886 E>L, TLA:1918 E>L, TLA:1962 E>L, TLA:1998 E>L, TLA:2004 E>L, TLA:2030 E>L, TLA:2116 E>L, TLA:2117 E>L, TLA:2119 E>L, TLA:2122 E>L, TLA:2270 L>E, TLA:2373 L>E, TLA:2402 E>L, TLA:2414 E>L, TLA:2417 E>L, BBAW:2468 E>L, BBAW:2470 L>E, BBAW:2481 L>E, BBAW:2533 L>E, BBAW:2534 E>L, BBAW:2544 L>E, BBAW:2548 E>L, BBAW:2549 E>L, BBAW:2551 E>L, BBAW:2552 L>E, BBAW:2561 E>L, BBAW:2578 E>L, BBAW:2587 E>L, BBAW:2610 E>L, BBAW:2624 L>E, BBAW:2626 E>L, BBAW:2642 L>E, BBAW:2651 L>E, BBAW:2663 E>L, BBAW:2670 E>L, BBAW:2696 E>L, BBAW:2705 L>E, BBAW:2716 E>L, BBAW:2718 E>L, BBAW:2725 L>E, BBAW:2742 E>L, BBAW:2744 E>L, BBAW:2745 E>L, BBAW:2749 E>L, BBAW:2761 E>L, BBAW:2765 E>L, BBAW:2775 E>L, BBAW:2781 E>L, BBAW:2783 E>L, BBAW:2792 L>E, BBAW:2800 E>L, BBAW:2817 E>L, BBAW:2819 E>L, BBAW:2821 E>L, BBAW:2830 E>L, BBAW:2831 L>E, BBAW:2847 E>L, BBAW:2848 L>E, BBAW:2851 L>E, BBAW:2854 E>L, BBAW:2862 E>L, BBAW:2867 E>L, BBAW:2895 L>E, BBAW:2912 E>L, BBAW:2916 E>L, BBAW:2917 L>E, BBAW:2948 E>L, BBAW:2966 E>L, BBAW:2967 E>L, BBAW:2974 E>L, BBAW:3025 E>L, BBAW:3029 L>E, BBAW:3034 E>L, BBAW:3076 E>L, BBAW:3084 L>E, BBAW:3090 E>L, BBAW:3101 E>L, BBAW:3102 E>L, BBAW:3148 E>L, BBAW:3166 E>L, BBAW:3174 E>L, BBAW:3177 L>E, BBAW:3179 L>E, BBAW:3181 L>E, BBAW:3189 E>L, BBAW:3203 L>E, BBAW:3210 E>L, BBAW:3232 L>E, BBAW:3240 E>L, BBAW:3265 L>E, BBAW:3268 E>L, BBAW:3273 E>L, BBAW:3276 E>L, BBAW:3293 L>E, BBAW:3296 E>L, BBAW:3300 E>L, BBAW:3305 E>L, BBAW:3307 E>L, BBAW:3321 L>E, BBAW:3332 E>L, BBAW:3343 L>E, BBAW:3348 L>E, BBAW:3365 L>E, BBAW:3382 L>E, BBAW:3389 L>E, BBAW:3391 L>E, BBAW:3394 E>L, BBAW:3405 E>L, BBAW:3432 E>L, BBAW:3434 L>E, BBAW:3448 E>L, BBAW:3455 L>E, BBAW:3468 E>L

**c3** (220 lines; id, off stage > hypothetical stage; E = Earlier Egyptian, L = Late Egyptian):

TLA:28 E>L, TLA:35 E>L, TLA:47 E>L, TLA:50 E>L, TLA:54 E>L, TLA:61 E>L, TLA:106 L>E, TLA:114 E>L, TLA:154 L>E, TLA:162 L>E, TLA:169 L>E, TLA:190 E>L, TLA:202 L>E, TLA:262 E>L, TLA:277 L>E, TLA:296 L>E, TLA:299 E>L, TLA:331 E>L, TLA:361 E>L, TLA:363 E>L, TLA:377 E>L, TLA:380 E>L, TLA:403 L>E, TLA:404 E>L, TLA:424 E>L, TLA:429 E>L, TLA:431 E>L, TLA:438 E>L, TLA:442 E>L, TLA:471 E>L, TLA:474 E>L, TLA:492 L>E, TLA:499 L>E, TLA:588 L>E, TLA:590 E>L, TLA:620 E>L, TLA:622 E>L, TLA:626 E>L, TLA:630 L>E, TLA:645 E>L, TLA:653 L>E, TLA:665 L>E, TLA:686 E>L, TLA:765 E>L, TLA:770 L>E, TLA:786 L>E, TLA:792 E>L, TLA:819 E>L, TLA:821 E>L, TLA:824 L>E, TLA:843 L>E, TLA:853 E>L, TLA:858 E>L, TLA:864 E>L, TLA:877 E>L, TLA:889 E>L, TLA:894 E>L, TLA:924 E>L, TLA:927 L>E, TLA:945 E>L, TLA:950 E>L, TLA:960 E>L, TLA:1004 L>E, TLA:1072 E>L, TLA:1073 L>E, TLA:1077 L>E, TLA:1091 E>L, TLA:1092 L>E, TLA:1096 L>E, TLA:1100 E>L, TLA:1114 E>L, TLA:1123 L>E, TLA:1150 L>E, TLA:1160 L>E, TLA:1186 E>L, TLA:1196 L>E, TLA:1203 L>E, TLA:1209 E>L, TLA:1247 L>E, TLA:1307 E>L, TLA:1309 L>E, TLA:1317 E>L, TLA:1324 E>L, TLA:1329 L>E, TLA:1333 E>L, TLA:1381 E>L, TLA:1444 E>L, TLA:1452 E>L, TLA:1453 E>L, TLA:1454 E>L, TLA:1455 E>L, TLA:1514 E>L, TLA:1521 L>E, TLA:1530 E>L, TLA:1546 E>L, TLA:1553 E>L, TLA:1646 L>E, TLA:1650 E>L, TLA:1661 L>E, TLA:1669 E>L, TLA:1685 E>L, TLA:1694 E>L, TLA:1701 L>E, TLA:1710 E>L, TLA:1723 E>L, TLA:1755 E>L, TLA:1776 E>L, TLA:1777 E>L, TLA:1799 E>L, TLA:1814 E>L, TLA:1815 E>L, TLA:1837 E>L, TLA:1886 E>L, TLA:1888 L>E, TLA:1918 E>L, TLA:1955 E>L, TLA:1998 E>L, TLA:2004 E>L, TLA:2030 E>L, TLA:2080 L>E, TLA:2116 E>L, TLA:2117 E>L, TLA:2119 E>L, TLA:2122 E>L, TLA:2226 E>L, TLA:2232 E>L, TLA:2336 E>L, TLA:2373 L>E, TLA:2402 E>L, TLA:2414 E>L, TLA:2417 E>L, BBAW:2467 E>L, BBAW:2468 E>L, BBAW:2470 L>E, BBAW:2488 E>L, BBAW:2534 E>L, BBAW:2548 E>L, BBAW:2549 E>L, BBAW:2551 E>L, BBAW:2564 E>L, BBAW:2569 E>L, BBAW:2576 E>L, BBAW:2578 E>L, BBAW:2587 E>L, BBAW:2610 E>L, BBAW:2611 E>L, BBAW:2612 L>E, BBAW:2626 E>L, BBAW:2651 L>E, BBAW:2659 E>L, BBAW:2663 E>L, BBAW:2670 E>L, BBAW:2687 E>L, BBAW:2696 E>L, BBAW:2711 E>L, BBAW:2716 E>L, BBAW:2718 E>L, BBAW:2742 E>L, BBAW:2744 E>L, BBAW:2761 E>L, BBAW:2762 E>L, BBAW:2763 E>L, BBAW:2765 E>L, BBAW:2766 E>L, BBAW:2775 E>L, BBAW:2781 E>L, BBAW:2792 L>E, BBAW:2800 E>L, BBAW:2817 E>L, BBAW:2818 E>L, BBAW:2819 E>L, BBAW:2821 E>L, BBAW:2826 E>L, BBAW:2830 E>L, BBAW:2831 L>E, BBAW:2846 E>L, BBAW:2847 E>L, BBAW:2851 L>E, BBAW:2855 E>L, BBAW:2856 E>L, BBAW:2862 E>L, BBAW:2867 E>L, BBAW:2895 L>E, BBAW:2912 E>L, BBAW:2916 E>L, BBAW:2966 E>L, BBAW:3025 E>L, BBAW:3026 E>L, BBAW:3034 E>L, BBAW:3084 L>E, BBAW:3088 E>L, BBAW:3101 E>L, BBAW:3102 E>L, BBAW:3148 E>L, BBAW:3168 E>L, BBAW:3174 E>L, BBAW:3177 L>E, BBAW:3179 L>E, BBAW:3189 E>L, BBAW:3192 E>L, BBAW:3195 E>L, BBAW:3210 E>L, BBAW:3232 L>E, BBAW:3238 E>L, BBAW:3265 L>E, BBAW:3266 E>L, BBAW:3276 E>L, BBAW:3277 E>L, BBAW:3287 E>L, BBAW:3293 L>E, BBAW:3343 L>E, BBAW:3348 L>E, BBAW:3352 E>L, BBAW:3389 L>E, BBAW:3391 L>E, BBAW:3405 E>L, BBAW:3434 L>E, BBAW:3442 E>L, BBAW:3449 E>L, BBAW:3455 L>E

### 3.5 Fit-time discounts and |R| (`test_smoothing_report.json`)

All fits are on the 52,210 train rows. Ney discount d per table; no fallback was taken in any model
(every fallback flag False). The primary arm (Witten-Bell) uses no d; the table is the record for c3.

| Model | \|R\| | N (unigram total) | d transition | d sign_context | d next_sign_context |
| --- | --- | --- | --- | --- | --- |
| pooled | 23,495 | 370,878 | 0.7279 | 0.8070 | 0.8075 |
| Earlier Egyptian | 17,398 | 152,689 | 0.7455 | 0.8096 | 0.8099 |
| Late Egyptian | 19,288 | 314,908 | 0.7333 | 0.8103 | 0.8115 |
| Demotic | 12,794 | 96,719 | 0.7659 | 0.8194 | 0.8231 |

## 4. Why the later steps did not run

The runner executes the registered steps in order and stops at the first non-zero exit. Step 3 (the
gates) exited 1 on the hard gate (c'), so steps 4 (expert pastes, rules (a) and (f') paste part), 6
(competitive sanity check, rule (g')), 7 (release check and determinism) and 8 (full test suite) were
not started. Step 5 does not exist in this registration (rule (b) withdrawn). This is the registered
behaviour: hard gates first, a FAIL stops the run. None of those steps could have turned a (c') FAIL
into a pass, and by the retry rule no re-run is allowed to fix a substantive failure. Consequently
rules (a), (g') and the paste part of (f'), and the release/determinism and test-suite checks, have no
result from this run. Rule (g') in any case would only have been a sanity check: **the competitive
sets do not exercise the decoder, so passing them is not evidence for the change, it only detects
collateral damage.**

## 5. What this licenses

Nothing is shipped. The default add-k estimator for `_transition`, `_sign_context` and
`_next_sign_context` is unchanged, routing is unchanged, and the switch stays default off. The
candidate schemes remain in `app/services/reading_model.py` behind the off-by-default switch; this
result does not by itself remove them. No claim is made about `_emission`, the stage router,
the private self-test that prompted the experiment, decoder weight re-tuning, or retrieval quality.
Rule (b), the Urk. IV / St Andrews gate, was withdrawn from this registration and is not evaluated
here.

## 6. Interpretation

The defect of section 1 is real: a context with exactly one distinct successor gets a degenerate
normaliser under add-k, and 989 test positions (of 25,808) have a gold previous reading in exactly
that situation, with off's own Viterbi path using a V_obs = 1 previous reading at 516 of them (0.522). Witten-Bell smoothing on the transition table does change that behaviour (own-path share
0.522 to 0.495) but fixing the pathology does not move accuracy measurably on this corpus: the
primary arm gained 5 positions out of 25,808 (+0.02 percentage points, CI [-0.12, +0.17] points),
with 177 positions improved and 172 worsened, i.e. a coin flip at the scale of the data. The +25
positions (+0.24 points) that earned it the primary slot on dev did not replicate, which is what one
expects from taking the best of three arms on a 10,363-position sample (the selection can pick up
noise); the test result is the confirmatory number. Where the correction moved the path at the
previous position, it lost more than it won (+2/-22 at i-1), so the extra mass given to unseen
successors is not obviously better than the sharp (if over-confident) add-k estimate for these
contexts. The broader schemes c2 and c3 were worse than the default, with CIs excluding zero (-62 and
-46 positions), consistent with smoothing the sign-context tables as well being a net loss at the
current weights; the decoder weights were fixed in advance and were deliberately not re-tuned. This
note does not claim to know why the effect is flat; it only records that it is, and that a larger
sample or re-weighted decoder would be a new registration, not a continuation of this one.

## 7. Files

Test attempt directory: `step3_gates.txt` (full gate output including per-line routing scores),
`test_summary.csv`, `test_smoothing_report.json`, `test_calibration.csv`, `test_positions.csv`,
`test_lines.csv`, `run_log.txt`. Dev attempt directory: `dev_record.json` (committed as
`docs/transition-smoothing-dev-record-2026-10-28.json`), `step3_selection.txt`, `dev_summary.csv`,
`dev_counts.json`. These directories live outside the repository and are not committed.
