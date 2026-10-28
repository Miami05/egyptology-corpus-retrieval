# Experiment 3 (notation-faithful search, F-a) — step 4, held-out 3 confirmation, 2026-10-28

Branch `exp3-2026-10-26`. Rules: `ROADMAP.md`, section "Experiment 3 — the notation-faithful search
key — pre-registered 2026-09-07", its re-scope addendum of 2026-10-26, the dated 2026-10-27 notes and
the 2026-10-28 note that pinned the step-4 runner. No rule is changed here. This note applies the
frozen step-4 rule to the one run that opened held-out 3. The selection run is in
`docs/exp3-results-2026-10-28-attempt1.md`.

**Outcome: the confirmation FAILED, in both pools.** F-a did not meet the frozen condition on held-out
3 faithful: top-3 useful ties (16 = 16), but MRR falls (0.7333 -> 0.7167) and the rank-1 count falls
(14 -> 13). **F-a is not promoted. The default stays off (`EXP3_FA_DEFAULT = False`). Held-out 3 is
spent.** Experiment 3 is closed with F-a off.

## 1. Run identity

| Item | Value |
|---|---|
| Run directory | `/Users/lediodurmishaj/egyptology-runs/exp3-step4-2026-10-28-attempt1` |
| Run log | `run_log.txt`: first step 2026-10-28T06:59:20Z, `ALL STEPS RAN` at 2026-10-28T08:00:56Z (UTC); every step `exit=0` except `gate_step4 exit=1 (0 PASS, 1 FAIL, 2 unjudgeable)` |
| Runner commit | `3d50630ed452e27cf38462cf4fbd2f7a59cb8774` (`runner_commit.txt`), the commit that pinned `scripts/run_exp3_step4.sh` and `scripts/check_exp3_step4.py` |
| Runner sha256 | `run_exp3_step4.sh` `47a8e5554168c23fb5afbe0454a66e7c5069737206bedf65057437460c3f5889`; `check_exp3_step4.py` `bf18cfc2c15093fdbbfbc311998e8f1975c0d4432bd7819caf7e52bd663ede43` (`runner_sha256.txt`) |
| base arm | `e2a9596316ba9d0aa3457eb648a4892712bd1b0a` (`base/commit.txt`; switch off, `base/switch.txt`), the same commit as the selection run |
| fa arm | `b4844a1e1dd5875e93dde7c9173435a2bfd765b8` (`fa/commit.txt`; switch ON, `fa/switch.txt`), the same commit as the selection run |
| Held-out 3 | `data/benchmarks/competitive_ambiguity_eval_queries_holdout3_2026-10-27_SEALED.csv`, sha256 `c80100cf93e64a0649f0616eca795aac469dbef1a74b9ca51107bd6f16d2d838`. Verified three ways before any query ran (`base/ho3_sha_check.txt`, `fa/ho3_sha_check.txt`, `ho3_sha256_from_build_log.txt`): the build log's recorded value, the value pinned in the runner and the file in each arm's worktree are all the same. Recomputed on the branch file when this note was written: the same value |
| Faithful held-out 3 file | built once per arm by `scripts/exp3_faithful_benchmark_file.py`; fold-back holds on 20/20; sha256 `c649220e6c1508cbeb1161ce8b174add2aff10fe19d14ba4608dbd06d6b53de6`, identical in both arms |
| Corpus | `data/processed/examples.csv`, 130,472 rows, sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` in both arms (`base/corpus_sha256.txt`, `fa/corpus_sha256.txt`, `step4_info.txt`); equal to the selection run's corpus |
| Python | 3.12.13 (`env.txt`) |
| Flags (both arms) | `run_competitive_ambiguity_eval.py --query-path app --useful-rule v4 --stage auto --expected-tokens current`; pool C `--exclude-twins 0`, pool T `--exclude-twins 0.7`; identical to the selection run |
| sha256 `gate_step4.txt` | `005ffbfd2c7a9c45f68d1e1b5a907b9f13c3162336576818064000f5310c8efb` |
| sha256 `step4_info.txt` | `c8ee570857c1466a935bc9cfe2cd8fdd1a1a50cddc89910f9eaf3ec2f321f711` |
| sha256 `run_log.txt` | `3097e44d8e02e44536efae3d79a7349f112b88c8758767f2341daa62192e17f3` |
| sha256 `runner_sha256.txt` | `35752b1d7476d3ff5416adb118978f39440e48ea21519e7ca1fbabc5402df6eb` |
| Manifests | `base/sha256.txt` and `fa/sha256.txt` (20 files each) |

`shasum -a 256 -c` was run on `sha256_top.txt` and on both per-arm manifests when this note was
written: every file reports OK. The per-query numbers in sections 2 and 3 were recomputed from the
four faithful result CSVs (`useful_family_rank`: top-3 useful = rank 1 to 3, MRR = mean of 1/rank
with a miss as 0, rank-1 count = rank 1) and agree with the checker's `gate_step4.txt` and with the
harness's own summary lines. Ranks in the data are 1, 2, 3 or blank (the harness keeps three
suggestions); `-` below means "no useful candidate in the top 3". Held-out 3 was first opened,
read, hashed and run against by this run only.

## 2. The gate (`gate_step4.txt`, held-out 3 faithful)

Frozen rule (ROADMAP Experiment 3 addendum, "Selection" and the confirmation step, and the 2026-10-28 restatement): pass iff in
BOTH pools F-a top-3 useful >= base, MRR >= base and rank-1 count >= base. No strict improvement is
required.

| Pool | | top-3 useful | MRR | rank-1 count | verdict |
|---|---|---|---|---|---|
| C (`--exclude-twins 0`) | base | 16/20 = 0.8000 | 0.7333 (11/15) | 14 | |
| C | fa | 16/20 = 0.8000 | 0.7167 (43/60) | 13 | |
| C | rule | 16 >= 16 ok | 0.7167 >= 0.7333 FAILS | 13 >= 14 FAILS | **POOL C: FAIL** |
| T (`--exclude-twins 0.7`) | base | 16/20 = 0.8000 | 0.7333 (11/15) | 14 | |
| T | fa | 16/20 = 0.8000 | 0.7167 (43/60) | 13 | |
| T | rule | 16 >= 16 ok | 0.7167 >= 0.7333 FAILS | 13 >= 14 FAILS | **POOL T: FAIL** |
| | | | | | **STEP4 OVERALL: FAIL** |

"Strictly better somewhere" (informational in the checker): no. Pools C and T give the same metrics
and the same move list on held-out 3 (the build log excluded near-twins of the targets when the set
was built; this note does not analyse why the two pools agree).

## 3. Per-query moves, held-out 3 faithful, base against fa (ids and ranks only)

Queries whose first useful rank changed (base -> fa; `-` = no useful candidate in the top 3). The
list is identical in pool C and pool T.

| Query | base rank | fa rank | effect |
|---|---|---|---|
| HOLD3_001 | - | 2 | top-3 gained |
| HOLD3_019 | - | 2 | top-3 gained |
| HOLD3_005 | 3 | - | top-3 lost |
| HOLD3_017 | 1 | - | top-3 lost, rank-1 lost |

The other 16 queries have the same useful rank in both arms. Top-3 useful: two gained, two lost, net
zero (16 = 16). Rank-1: none gained (both gains land at rank 2), one lost (HOLD3_017): 14 -> 13.
MRR: +0.5 (HOLD3_001) +0.5 (HOLD3_019) -1/3 (HOLD3_005) -1 (HOLD3_017) = -1/3 over 20 queries, so
44/3 / 20 = 0.7333 falls to 43/3 / 20 = 0.7167, as the gate shows.

Routing (`stage_used`, faithful). The stage differs between the arms for six queries, the same six
in both pools: HOLD3_011 (Late Egyptian -> -), HOLD3_014 (- -> Late Egyptian), HOLD3_019 (- ->
Earlier Egyptian), HOLD3_020 (- -> Earlier Egyptian), HOLD3_022 (- -> Earlier Egyptian), HOLD3_026
(Late Egyptian -> -). Of the four moved queries only HOLD3_019 is among them, so its move (- -> 2)
mixes a stage effect into the F-a effect; HOLD3_001, HOLD3_005 and HOLD3_017 have the same routing in
both arms (all three: no stage). The five other rerouted queries keep their useful rank (HOLD3_011,
014, 020, 026 rank 1 in both arms; HOLD3_022 `-` in both). These files cannot separate a stage effect
from the F-a effect (each arm ran the whole pipeline once).

Composition of held-out 3 (build log, `data/benchmarks/exp3_heldout_build_log.txt`): 20 rows; query
types: 9 simplified, 9 partial, 2 normalized reading order; sources: BBAW 12, Ramses 4, TLA 3, AES 1;
stages: blank 13, Late Egyptian 4, Demotic 3. Disjointness checked after the build: 0 shared rows, 0
shared `source_text_id`, 0 BBAW rows within +-20 sentences, of every earlier set and of held-out 2
(diagnostics for AES and Ramses text overlap also 0).

## 4. Stored-query identity (informational, not part of the rule)

`step4_info.txt`: the stored (folded-ASCII) held-out 3 queries give **IDENTICAL** per-query results
between the arms in both pools (`holdout3_stored_C.csv` and `holdout3_stored_T.csv`; the sha256 of
the stored-C result file is `b1a926266162886ec8d7722dfc40cd1b877f1d93dca4c436855e83bf480a7804` in both
arms). As in the selection run, F-a leaves plain-ASCII queries on today's code path. Stored-query
numbers, identical in both arms: pool C top-3 useful 16/20 = 0.8000, MRR 0.6833, rank-1 12; pool T
0.8000, 0.6583, 11. The faithful base (0.8000 / 0.7333 / 14) is higher than the stored base: the two
forms run in different query modes (ROADMAP addendum, "Baselines"), so they are not the same
baseline.

## 5. Frozen consequence

Applying the rule as written (ROADMAP Experiment 3 section and addendum; the 2026-10-28 note):

- The failed confirmation is **reported** (this note).
- **F-a is NOT promoted.** `EXP3_FA_DEFAULT` stays `False` on this branch and on `main`; the fa
  commit `b4844a1` stays on `exp3-fa-arm-2026-10-26` only. The README notation table is unchanged.
- Nothing about Experiment 3 goes to Nederhof as a confirmed result: the pre-registration said
  nothing goes to him until step 4 has been run and passed, and it did not pass.
- **Held-out 3 is spent.** It informs no tuning, no re-run and no rule change; it cannot serve as an
  unseen set again.
- No re-runs, no rule changes. The `WHYPTOLOGY_EXP3_FA` environment override in
  `app/services/faithful.py` is to be removed when the branch is merged (it is not removed in this
  commit).

## 6. Experiment 3 overall, honestly

What the experiment found, all on faithful queries (queries rewritten in the notation of the
expected reading), F-a against today's code:

- **Held-out 2 (the selection set, 20 queries): F-a selected**, in both pools: top-3 useful 0.9000 ->
  0.9500, MRR 0.8500 -> 0.9250, rank-1 16 -> 18. Two queries carry it (HOLD2_014 `- -> 1`,
  HOLD2_020 `2 -> 1`).
- **Gains on the sets already used for step 0 (v4, held-out 1, LE-v1), none unseen:** v4 top-3
  19/20 -> 20/20 (C) and 18/20 -> 20/20 (T), MRR 0.8333 -> 0.9417 and 0.7583 -> 0.9167; held-out 1
  top-3 18/20 both, MRR 0.7500 -> 0.8167, rank-1 13 -> 15; LE-v1 top-3 26/30 -> 27/30, MRR 0.7833 ->
  0.8611, rank-1 21 -> 25. Part of the v4 change comes from queries carrying a stale `pl` residue
  token (selection note, section 5).
- **NAME-v1 regressed:** top-3 30/30 -> 28/30 (C) and 29/30 -> 27/30 (T), MRR 0.8722 -> 0.8667 and
  0.8611 -> 0.8500. It was outside the selection rule and was recorded as a risk for step 4.
- **Held-out 3 (one-time confirmation, unseen, 20 queries): failed.** Top-3 unchanged, MRR and the
  rank-1 count lower, in both pools (sections 2 and 3). The net movement is small (four queries of
  20 move; one rank-1 and 1/3 of a reciprocal-rank point separate the arms) and it carries no
  significance on 20 queries, but the frozen rule is a threshold, not a significance test, and it
  was not met.

The reading that fits all of it: on the sets where F-a looked good, either the sets had been looked
at (step 0) or the selection rested on two queries of 20; on the one set that was both unseen and
decisive, the effect did not replicate, and the one earlier set shaped like a name search (NAME-v1)
had already gone the wrong way. The data do not show that F-a helps. They do not show that it harms
by a measurable margin either; they show that a gain, if any, is not robust enough to ship under the
pre-registered rule.

**Token re-split caveat (applies to every number above, gains and losses).** F-a also re-splits
tokens: the faithful key is the `unfolded_reading_form` piece on both sides, so `ꜥḥꜥ.n sḏm=f` is
keyed `ꜥḥꜥ n sḏm f` where today's key is `ahan sdjm f`. Any F-a effect in this experiment can come
from that re-segmentation (`.n`, `=f`, hyphens, editorial text, markers) as much as from keeping
ꜣ/ꜥ, ḫ/ẖ and ḥ/h apart. No arm of this experiment separates the two (F-b was not run, and no arm
re-splits tokens while still folding the letters), so neither the held-out 2 gain nor the held-out 3
loss is attributed to notation. This experiment therefore says nothing for or against Nederhof's
point that ꜣ/ꜥ and ḫ/ẖ should stay distinct as a matter of correctness; it only says that, in this
implementation and on these sets, doing so as F-a does not clear the ranking bar.

## 7. What a future attempt would need

Nothing in this experiment is re-tested on held-out 3. A future attempt would need:

1. **A new pre-registration**, written and committed before any run, with its own selection rule and
   confirmation rule. It would have to state its treatment of the points this experiment left open:
   the re-split confound, name-shaped queries (NAME-v1-like sets inside the selection rule, not only
   as a disclosed risk), and what counts as a meaningful margin on sets of 20.
2. **New unseen sets.** Held-out 2 was used for selection and held-out 3 is spent, and v4, held-out 1,
   LE-v1 and NAME-v1 have all been looked at. A new selection set and a new confirmation set would
   have to be built by the frozen recipe (row-, twin- and window-disjoint from every set above,
   including held-out 2 and 3) and sealed until used. Larger sets would give the test more power than
   20 queries.
3. **An arm that separates re-segmentation from notation** (for example a re-split-only
   configuration, or F-b), so that any gain or loss can be assigned to one cause; otherwise the
   result cannot be attributed to the ꜣ/ꜥ, ḫ/ẖ, ḥ/h distinction.
4. **The step-0 checks, the mechanical gates and the pinned runner pattern**, which worked as
   intended in both runs: stored-query identity, segmentation identity, paste 8/8, corpus sha256,
   commit pins, the held-out sha check and the sealed-file discipline.

This note does not recommend running it; whether to open a new attempt is Ledio's decision with the
expert round (route Egyptology questions to the experts).
