# Held-out misses — pipeline trace (2026-09-05; item 3 of the plan for 2026-09-06)

**Diagnosis only.** No code, no constant, no committed benchmark file was changed.
This traces the five held-out misses the way `docs/v4-answerability-and-v5-rule.md`
traced the two v4 misses (COMP_007, COMP_014). It reuses the existing tools:
`scripts/compute_v4_answerability.py` (Rule A), `scripts/analyze_competitive_failures.py`
(retrieval rank), and `scripts/inspect_suggestion_boundary.py` (top-3 boundary, default
and `cfg_c` presets). Every number is quoted exactly as the scripts printed it, on the
130,472-row corpus at `3d38721`.

## The five misses

Default configuration (`ceval_holdout_v4_app_auto_results.csv`, 15/20): **HOLD_001,
HOLD_002, HOLD_005, HOLD_014, HOLD_026**. CFG-C (`ceval_holdout_v4_app_auto_cfg_c.csv`,
17/20) rescues HOLD_001 and HOLD_002 and still misses HOLD_005, HOLD_014, HOLD_026.

All five targets are `bbaw_egyptian_2018` (Pyramid-Text / Old-Egyptian style) rows with
**no lemma ids** and **no declared `language_stage`**; `--stage auto` inferred **None**
(pooled) for every one, and `ceval_holdout_v4_legacy_auto_results.csv` is byte-identical
to the app-path file for all five — so the query path and the stage layer are not in
play for any of them (see steps 4–5).

## Classification table

| id | answerable? useful rows (best token) | retrieval rank of best useful row / of scored | in top-50 pool | first accepted suggestion rank / conf / margin behind rank 3 (default) | CFG-C first accepted | stage | query-fold | classification |
|---|---|---|---|---|---|---|---|---|
| HOLD_001 | yes, **1633** (0.4583) | **3** / 28,589 | yes | **4** / 0.5790 / 0.0110 behind | **rank 3**, 0.6630, 0.0000 (rescued) | auto→None; target unstaged | clean | re-rank boundary loss (margin 0.011) |
| HOLD_002 | yes, **2309** (0.5000) | **3** / 9,759 | yes | **4** / 0.4990 / 0.0040 behind | **rank 3**, 0.6010, 0.0000 (rescued) | auto→None; target unstaged | clean | re-rank boundary loss (margin 0.004) |
| HOLD_005 | yes, **1868** (0.4583) | **13** / 25,818 | yes | **8** / 0.5060 / 0.0250 behind | none in top 10 (worse) | auto→None; target unstaged | clean | re-rank boundary loss + retrieval-depth (margin 0.025, retrieval rank 13) |
| HOLD_014 | yes, **1010** (0.4286) | **7** / 25,830 | yes | **4** / 0.5130 / 0.0290 behind | rank 7, 0.5690, 0.0400 behind (worse) | auto→None; target unstaged | clean | re-rank boundary loss (margin 0.029) |
| HOLD_026 | yes, **813** (0.4062) | **6** / 42,046 | yes | **4** / 0.5390 / 0.0070 behind | rank 6, 0.6020, 0.0220 behind (worse) | auto→None; target unstaged | clean | re-rank boundary loss (margin 0.007) |

Margins are `rank3_conf − accepted_conf` (positive = the accepted candidate sits that
far *behind* rank 3), printed by `inspect_suggestion_boundary.py --top-n 10`.

## Per-miss trace

### HOLD_001 — `i mw ppy im im msi ppy pn` (simplified), target `bbaw B090486`

1. **Answerable — yes. 1,633 useful rows** in the corpus with the target excluded
   (best token 0.4583, `bbaw B093162`). Not a coverage gap.
2. **Retrieval: best useful row at rank 3 of 28,589 scored rows** (`B087342`,
   `[ꞽw]r Ppy pn msꞽ Ppy pn n Nṯr-dwꜣ.w(ꞽ)`, token 0.318). Well inside the top-50 pool.
   Not a retrieval loss.
3. **Boundary (default): first accepted at suggestion rank 4, 0.5790, 0.0110 behind
   rank 3** (0.5900). The rank-4 accepted row (`B087342`, token 0.318) has the highest
   token overlap of the top-4 window (0.174 / 0.182 / 0.190 above it). **CFG-C: rank 3,
   0.6630, margin 0.0000 — rescued.**
4. Stage: auto→None; the target carries no declared stage; legacy==app. Declared/none
   would not change the rank.
5. Query form: all 8 query tokens (6 distinct: `i im mw msi pn ppy`) are present in the
   target loose-token set; nothing lost, no spurious token. Clean.

**re-rank boundary loss.**

### HOLD_002 — `dji p _ a mr dj` (partial), target `bbaw B084307`

1. **Answerable — yes. 2,309 useful rows** (best token 0.5000, `bbaw B084718`).
2. **Retrieval: best useful row at rank 3 of 9,759 scored** (`TLA_EARLIER_11745`,
   `ḏꞽ z(my).t ꜥ =s r =f`, token 0.316). In pool.
3. **Boundary (default): first accepted at rank 4, 0.4990, 0.0040 behind rank 3**
   (0.5030) — the tightest margin of the five, in the same band as COMP_014's 0.007.
   The accepted rank-4 row (token 0.316) again out-scores the three above it
   (0.176 / 0.222 / 0.200). **CFG-C: rank 3, 0.6010, margin 0.0000 — rescued.**
4. Stage: auto→None; unstaged target; legacy==app.
5. Query form: all 6 query tokens present in target; clean.

**re-rank boundary loss.**

### HOLD_005 — `nn qd _ _ i rdi wah skhr` (partial), target `bbaw B002748`

1. **Answerable — yes. 1,868 useful rows** (best token 0.4583,
   `RAMSES S_train_040144`).
2. **Retrieval: best useful row at rank 13 of 25,818 scored** (`B032068`,
   `nn sḫm sḫr r{r}m.pl ꞽm =ꞽ`, token 0.300). Inside the top-50 pool but the deepest of
   the five in retrieval — this is the one miss with a real retrieval-depth component.
3. **Boundary (default): first accepted at suggestion rank 8, 0.5060, 0.0250 behind
   rank 3** (0.5310). The re-rank actually *lifts* the useful row from retrieval rank 13
   to suggestion rank 8, but not far enough. **CFG-C: the useful row falls out of the top
   10 entirely — CFG-C makes this one worse, not better.**
4. Stage: auto→None; unstaged target; legacy==app.
5. Query form: all 8 query tokens present in target; clean.

**re-rank boundary loss with a retrieval-depth contribution** — the useful parallel is
both weaker (best token 0.300) and deeper (retrieval rank 13) than in the other four.

### HOLD_014 — `dji ppy pn djba du ipw rdji nfr za ntjr aa` (partial), target `bbaw B080968`

1. **Answerable — yes. 1,010 useful rows** (best token 0.4286, `bbaw B084923`) — the
   second-smallest useful pool of the five, but still 1,010 rows. Not a coverage gap.
2. **Retrieval: best useful row at rank 7 of 25,830 scored** (`B082324`,
   `Ppy pn [p]w n(.ꞽ) nṯr+ =f +nʾ.tꞽ`). In pool.
3. **Boundary (default): first accepted at rank 4, 0.5130, 0.0290 behind rank 3**
   (0.5420) — the widest default margin of the five. The accepted rank-4 row (`B084811`,
   **token 0.424**) has by far the highest token overlap of the window, against
   0.167 / 0.214 / 0.207 above it: the ranker's order is sharply anti-correlated with the
   evaluator's token measure here. **CFG-C: rank 7, 0.5690, 0.0400 behind — worse**; the
   token-0.424 row `B084811` is demoted out of CFG-C's top 10 and a different useful row
   (`B089767`, token 0.367) becomes the first accepted at rank 7.
4. Stage: auto→None; unstaged target; legacy==app.
5. Query form: all 11 query tokens present in target; clean.

**re-rank boundary loss.**

### HOLD_026 — `wn i wkha kh djd nha md ink iw khpr hap` (partial), target `bbaw B095221`

1. **Answerable — yes. 813 useful rows** (best token 0.4062,
   `TLA_DEMOTIC S01FF48CAD677`) — the smallest useful pool of the five, still 813 rows.
2. **Retrieval: best useful row at rank 6 of 42,046 scored** (`B095428`,
   `ḫr ꞽr pꜣy =k ḏd m-ꞽri̯ nni̯ …`, token 0.270). In pool.
3. **Boundary (default): first accepted at rank 4, 0.5390, 0.0070 behind rank 3**
   (0.5460) — the accepted row (`B093864`, token 0.265) loses to three rows at
   0.226 / 0.258 / 0.250; the top-3 here are two Ramses rows and one Demotic row, none
   useful, all just under the 0.26 line. **CFG-C: rank 6, 0.6020, 0.0220 behind —
   worse.**
4. Stage: auto→None; unstaged target; legacy==app.
5. Query form: all 11 query tokens present in target; clean.

**re-rank boundary loss.**

## Cross-cutting

**What the five share with COMP_007 / COMP_014.** All five are the same failure mode:
the useful parallel is retrieved into the pool (retrieval rank 3, 3, 13, 7, 6 — every one
inside top-50), and the loss happens in the suggestion re-rank at the top-3 cut, exactly
as for the two v4 misses (COMP_007 retrieval rank 7, COMP_014 rank 4). As with the v4
pair, the first *accepted* candidate lands at suggestion rank 4 in four of the five
(HOLD_005 at rank 8), and in every case that accepted candidate carries the **highest
token overlap of its window** while sitting *behind* rows the evaluator rejects — the
re-rank order is anti-correlated with the evaluator's own token measure at the boundary,
the identical finding the COMP_007/014 trace reported. Three of the five margins —
HOLD_002 0.004, HOLD_026 0.007, HOLD_001 0.011 — sit in or next to the 0.005–0.007 band
of COMP_007/014.

**What differs.** (a) The margins are more spread: HOLD_005 (0.025) and HOLD_014 (0.029)
are several times wider than the hairline COMP band, so not every held-out miss is a
5-thousandths coin-flip. (b) HOLD_005 is the one case with a genuine retrieval-depth
component — its best useful parallel is both the weakest (best token 0.300) and the
deepest (retrieval rank 13) — though it is still a boundary loss, not a retrieval loss,
because the row does reach the pool and surfaces at suggestion rank 8. (c) All five
targets are BBAW Pyramid-Text rows with **no lemma ids** (lemma 0.000 on every candidate
in every table), so v5's lemma-first rule cannot engage and the whole boundary is decided
on token + fuzzy signals alone. (d) Query-fold is **clean for all five** — every query
token appears in the target's loose-token set, with no dropped or spurious token — unlike
COMP_007, whose trace turned on the dropped `n.` / `=`.

**More "retrieval" or more "boundary"?** Overwhelmingly **boundary**: 5/5 have a useful
row inside the top-50 pool and lose it in the re-rank, not in candidate generation.
HOLD_005 is the only one leaning toward retrieval (rank 13), and even it is a boundary
loss. None is a coverage gap (813–2,309 useful rows each), none is a stage misinference
(auto→None is correct for unstaged BBAW targets; legacy==app), none is a query-fold loss.

**CFG-C is visibly a trade on this set, and that is the point.** It rescues HOLD_001 and
HOLD_002 by moving each to **exactly suggestion rank 3 at margin 0.000** — and for the
three it does *not* rescue it pushes the accepted candidate **further out**: HOLD_014
rank 4→7 (margin 0.029→0.040), HOLD_026 rank 4→6 (0.007→0.022), HOLD_005 rank 8→beyond
top-10. So CFG-C buys back two rank-4 near-misses at the cost of demoting the useful
parallels of the other three. This is the rank-1-demotion-vs-rank-3-rescue ambiguity in
miniature: top-3 count scores CFG-C higher (0.85 vs 0.75) while MRR scores it lower
(0.6583 vs 0.6667), and the two disagree *because a top-3 hit-count cannot see a
promotion of one query paid for by the demotion of another.*

**What instrument would separate a rank-1 demotion from a rank-3 rescue (described, not
built).** A metric or adjudication that scores the **whole ordering**, not a hit inside
three. Concretely: for every query whose first-accepted rank *moves* under a candidate
change — in either direction — record the signed rank-delta of the first accepted useful
candidate (default → change), then have an Egyptologist judge, on that small changed set,
whether each newly-top-3 parallel is actually a better reading than the rank-1/rank-2 row
it displaced. Expert adjudication is required because the benchmark itself cannot settle
it: with ~4,600 corpus rows counting "useful" for a median query, the useful-family test
has no resolution at the boundary, and a rank-weighted score (MRR, or an nDCG-style
measure over the accepted useful candidate) only reweights the same weak labels. The
roadmap's item (4) before/after set (COMP_001, COMP_007, COMP_022, HOLD_010, HOLD_016) is
exactly such a changed-query list; the finding here is that the held-out rescues
(HOLD_001, HOLD_002) and the held-out demotions (HOLD_005, HOLD_014, HOLD_026) should be
adjudicated in the same instrument, so the trade is priced by a human and not by a metric
that can only see one side of it. **No fix is proposed here; diagnosis only.**

## Tools and reproduction

- `scripts/compute_v4_answerability.py --benchmark
  data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv
  --useful-rule v4 --out <scratch>/holdout_answerability_v4.csv` — all 20 held-out
  queries answerable under v4; the five misses have 1,633 / 2,309 / 1,868 / 1,010 / 813
  useful rows.
- `scripts/analyze_competitive_failures.py --failures <holdout failures built by
  filtering the default results file> --output <scratch>` — retrieval ranks 3 / 3 / 13 /
  7 / 6. Run through a scratch copy that adds print-only lines for "of N scored" and
  top-50 membership (no change to its rank or classification logic). Its own category
  column labels HOLD_001/002 `threshold_too_strict` only because their useful row sits at
  retrieval rank exactly 3 (its `ranking_issue` test is rank > 3); the boundary tables
  show both are re-rank losses, rescued by CFG-C.
- `scripts/inspect_suggestion_boundary.py --benchmark <holdout> --ids
  HOLD_001,HOLD_002,HOLD_005,HOLD_014,HOLD_026 --stage auto --query-path app --top-n 10`,
  once with the default preset and once with `WHYPTOLOGY_SUGGESTION_PRESET=cfg_c`.

**Script flags added: none.** `inspect_suggestion_boundary.py` already exposes
`--benchmark` (it reads HOLD_ ids without modification); `compute_v4_answerability.py`
already exposes `--benchmark`/`--out`; `analyze_competitive_failures.py` already exposes
`--failures`/`--output`. The only code touched was a **scratch copy** of the analyze
script (under the session scratchpad, not the repo), carrying two extra `print`
statements and nothing else.
