# Experiment 3 (notation-faithful search, F-a) — results, attempt 1, 2026-10-28

Branch `exp3-2026-10-26`. Rules: `ROADMAP.md`, section "Experiment 3 — the notation-faithful search
key — pre-registered 2026-09-07", its re-scope addendum of 2026-10-26 and the dated 2026-10-27
notes. No rule is changed here. This note applies them to one run (the only run). Held-out 3 is
sealed: it was not opened, read, hashed or run against.

**Outcome: F-a is SELECTED** by the frozen rule on held-out 2 faithful, in both pools. The
selection rests on 20 queries, of which two move (see section 4). NAME-v1 faithful moves the
other way (section 3; it is outside the selection rule, and it is reported because a reader
deciding on step 4 should see it). Next step: the one-time held-out 3 confirmation (step 4),
**not run**.

## 1. Run identity

| Item | Value |
|---|---|
| Run directory | `/Users/lediodurmishaj/egyptology-runs/exp3-2026-10-27-attempt1` |
| Run log | started 2026-10-27T16:50:52Z, `ALL STEPS RAN` at 2026-10-28T00:12:55Z (UTC, `run_log.txt`) |
| base arm | `e2a9596316ba9d0aa3457eb648a4892712bd1b0a` (main `51f3757` merged into the experiment branch; `EXP3_FA_DEFAULT = False`, `base/switch.txt`: "off") |
| fa arm | `b4844a1e1dd5875e93dde7c9173435a2bfd765b8` (child of base, one changed line, `EXP3_FA_DEFAULT = True`; `fa/switch.txt`: "ON") |
| Corpus | `data/processed/examples.csv`, 130,472 rows, sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` (same in both arms, equal to the `release_baseline.json` hash) |
| Python | 3.12.13 (`env.txt`) |
| Flags (both arms) | `run_competitive_ambiguity_eval.py --query-path app --useful-rule v4 --stage auto --expected-tokens current`; pool C `--exclude-twins 0`, pool T `--exclude-twins 0.7` |
| sha256 `gates_mechanical.txt` | `724b09ba6dc53bd6c2f9eef90391fc903bb95545bab8bdafc189b9a26894d9df` |
| sha256 `routing_diff.txt` | `a2f0941f00dc30672d7a0b971e1580522325d5b7f8b756999d36746f9bdf4607` |
| sha256 `run_log.txt` | `d499f77879ecbd1162cb2fccd72a9874a797038841f01de2b6c3d7fcfb123644` |
| sha256 `base/sha256.txt` (manifest of 78 files) | `b794ca9800d6684dd1f9566f8857383646a04d08509ff43d1a88a4b9c4e5e52d` |
| sha256 `fa/sha256.txt` (manifest of 79 files) | `62aea23b108c1e471e5ab632e4479b8087c48e3118e3c3a19cfcc75bce0763fa` |

The three top-level files and both per-arm manifests were re-checked with `shasum -a 256 -c`
when this note was written: every file reports OK. Every number below was recomputed from the
per-query result CSVs (`useful_family_rank`: top-3 useful = rank 1 to 3; MRR = mean of 1/rank
with a miss counted as 0; rank-1 count = rank 1) and agrees with the run's own summary lines
(`top3_useful_family_accuracy`, `mrr`, `top1_useful_family_accuracy`, `total_queries`) in all 20
result files per arm. Useful ranks in the data are 1, 2, 3 or blank, because the harness keeps
three suggestions; `-` below means "no useful candidate in the top 3".

Held-out 2: built by the step-1 recipe (20 rows; `data/benchmarks/exp3_heldout_build_log.txt`;
row-, twin- and BBAW-window-disjoint from every earlier set). The diagnostic counts of shared AES
texts and nearby Ramses lines against every earlier set are 0, but the frozen rule itself does not
make the set text-disjoint for AES and Ramses (2026-10-27 note). Its faithful column folds back to
the stored query on 20/20, with no ASCII residue token and no character-aligned token.

## 2. Mechanical gates (`gates_mechanical.txt`)

| Gate | Result |
|---|---|
| Step 0 output identical between the arms (reads no ranker code) | pass: `step0.csv`, `step0_log.txt` and the five faithful benchmark files are the same |
| Corpus sha256 equal in both arms | pass (hash in section 1) |
| Stored folded-ASCII queries, per-query results identical in every column, all five sets, C and T | pass: 10 of 10 files IDENTICAL (section 3 shows the same numbers for both arms on every stored row) |
| Segmentation output byte-identical | pass: IDENTICAL |
| `run_expert_paste_eval.py` 8/8, auto and declared, both arms | pass: base auto 8/8, base declared 8/8, fa auto 8/8, fa declared 8/8 |
| `verify_release.py --skip-tests`, fa arm | pass: verdict READY (twin-controlled v4 top-3 0.85 against floor 0.80, MRR 0.75 against floor 0.70, expert pastes 8/8, corpus sha256 equal to the baseline's; the legacy pool 0.9 / 0.8 is shown as non-gating) |

No gate failed. The stored-query identity gate is the evidence that, in this run, F-a leaves the
plain-ASCII queries on today's code path.

## 3. Results per set, pool and query form

Metric cells: top-3 useful (count/queries = share) / MRR / rank-1 count. Pool C = legacy pool
(`--exclude-twins 0`), pool T = twin-controlled (`--exclude-twins 0.7`); both use
`--expected-tokens current`. "Top-3 gained" = no useful candidate in the top 3 under base and one
under fa (lost is the reverse); rank-1 gained and lost likewise for rank 1. The faithful base is
not the stored-query result: the stored queries run in A54 loose mode, the faithful ones in mixed
or strict mode (ROADMAP addendum, "Baselines"), so the two base rows of a set differ. The stored
rows reproduce the numbers the addendum lists (v4 C 0.90 / 0.80 / 14, T 0.85 / 0.75 / 13;
held-out 1 0.75 / 0.6667 / 12; LE-v1 0.8667 / 0.80 / 22; NAME-v1 0.9667 / 0.8833 / 24, now
measured in both pools).

### v4

| Pool | Query form | base: top-3 useful / MRR / rank-1 | fa: top-3 useful / MRR / rank-1 | top-3 gained | top-3 lost | rank-1 gained | rank-1 lost |
|---|---|---|---|---|---|---|---|
| C | stored | 18/20 = 0.9000 / 0.8000 / 14 | 18/20 = 0.9000 / 0.8000 / 14 | none | none | none | none |
| T | stored | 17/20 = 0.8500 / 0.7500 / 13 | 17/20 = 0.8500 / 0.7500 / 13 | none | none | none | none |
| C | faithful | 19/20 = 0.9500 / 0.8333 / 15 | 20/20 = 1.0000 / 0.9417 / 18 | COMP_007 | none | COMP_007, COMP_008, COMP_020, COMP_022 | COMP_013 |
| T | faithful | 18/20 = 0.9000 / 0.7583 / 13 | 20/20 = 1.0000 / 0.9167 / 17 | COMP_001, COMP_007 | none | COMP_001, COMP_004, COMP_007, COMP_008, COMP_020, COMP_022 | COMP_013, COMP_017 |

Faithful, pool C, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): COMP_007 (- → 1), COMP_008 (3 → 1), COMP_013 (1 → 3), COMP_020 (2 → 1), COMP_022 (3 → 1).

Faithful, pool T, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): COMP_001 (- → 1), COMP_004 (2 → 1), COMP_007 (- → 1), COMP_008 (3 → 1), COMP_013 (1 → 3), COMP_017 (1 → 2), COMP_020 (2 → 1), COMP_022 (3 → 1).

### held-out 1

| Pool | Query form | base: top-3 useful / MRR / rank-1 | fa: top-3 useful / MRR / rank-1 | top-3 gained | top-3 lost | rank-1 gained | rank-1 lost |
|---|---|---|---|---|---|---|---|
| C | stored | 15/20 = 0.7500 / 0.6667 / 12 | 15/20 = 0.7500 / 0.6667 / 12 | none | none | none | none |
| T | stored | 15/20 = 0.7500 / 0.6667 / 12 | 15/20 = 0.7500 / 0.6667 / 12 | none | none | none | none |
| C | faithful | 18/20 = 0.9000 / 0.7500 / 13 | 18/20 = 0.9000 / 0.8167 / 15 | HOLD_014 | HOLD_002 | HOLD_014, HOLD_019 | none |
| T | faithful | 18/20 = 0.9000 / 0.7500 / 13 | 18/20 = 0.9000 / 0.8167 / 15 | HOLD_014 | HOLD_002 | HOLD_014, HOLD_019 | none |

Faithful, pool C, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): HOLD_002 (3 → -), HOLD_014 (- → 1), HOLD_019 (2 → 1), HOLD_026 (3 → 2).

Faithful, pool T, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): HOLD_002 (3 → -), HOLD_014 (- → 1), HOLD_019 (2 → 1), HOLD_026 (3 → 2).

### LE-v1

| Pool | Query form | base: top-3 useful / MRR / rank-1 | fa: top-3 useful / MRR / rank-1 | top-3 gained | top-3 lost | rank-1 gained | rank-1 lost |
|---|---|---|---|---|---|---|---|
| C | stored | 26/30 = 0.8667 / 0.8000 / 22 | 26/30 = 0.8667 / 0.8000 / 22 | none | none | none | none |
| T | stored | 26/30 = 0.8667 / 0.8000 / 22 | 26/30 = 0.8667 / 0.8000 / 22 | none | none | none | none |
| C | faithful | 26/30 = 0.8667 / 0.7833 / 21 | 27/30 = 0.9000 / 0.8611 / 25 | LE_008, LE_034 | LE_043 | LE_001, LE_004, LE_008, LE_017, LE_022 | LE_013 |
| T | faithful | 26/30 = 0.8667 / 0.7833 / 21 | 27/30 = 0.9000 / 0.8611 / 25 | LE_008, LE_034 | LE_043 | LE_001, LE_004, LE_008, LE_017, LE_022 | LE_013 |

Faithful, pool C, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): LE_001 (2 → 1), LE_004 (2 → 1), LE_008 (- → 1), LE_013 (1 → 2), LE_017 (2 → 1), LE_022 (2 → 1), LE_034 (- → 3), LE_043 (2 → -).

Faithful, pool T, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): LE_001 (2 → 1), LE_004 (2 → 1), LE_008 (- → 1), LE_013 (1 → 2), LE_017 (2 → 1), LE_022 (2 → 1), LE_034 (- → 3), LE_043 (2 → -).

### NAME-v1

| Pool | Query form | base: top-3 useful / MRR / rank-1 | fa: top-3 useful / MRR / rank-1 | top-3 gained | top-3 lost | rank-1 gained | rank-1 lost |
|---|---|---|---|---|---|---|---|
| C | stored | 29/30 = 0.9667 / 0.8833 / 24 | 29/30 = 0.9667 / 0.8833 / 24 | none | none | none | none |
| T | stored | 29/30 = 0.9667 / 0.8833 / 24 | 29/30 = 0.9667 / 0.8833 / 24 | none | none | none | none |
| C | faithful | 30/30 = 1.0000 / 0.8722 / 23 | 28/30 = 0.9333 / 0.8667 / 24 | none | NAME_005, NAME_017 | NAME_018, NAME_019, NAME_024 | NAME_011, NAME_017 |
| T | faithful | 29/30 = 0.9667 / 0.8611 / 23 | 27/30 = 0.9000 / 0.8500 / 24 | none | NAME_005, NAME_017 | NAME_018, NAME_019, NAME_024 | NAME_011, NAME_017 |

Faithful, pool C, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): NAME_005 (3 → -), NAME_011 (1 → 2), NAME_017 (1 → -), NAME_018 (2 → 1), NAME_019 (2 → 1), NAME_024 (2 → 1), NAME_028 (3 → 2).

Faithful, pool T, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): NAME_005 (3 → -), NAME_011 (1 → 2), NAME_017 (1 → -), NAME_018 (2 → 1), NAME_019 (2 → 1), NAME_024 (2 → 1).

### held-out 2

| Pool | Query form | base: top-3 useful / MRR / rank-1 | fa: top-3 useful / MRR / rank-1 | top-3 gained | top-3 lost | rank-1 gained | rank-1 lost |
|---|---|---|---|---|---|---|---|
| C | stored | 19/20 = 0.9500 / 0.8667 / 16 | 19/20 = 0.9500 / 0.8667 / 16 | none | none | none | none |
| T | stored | 19/20 = 0.9500 / 0.8667 / 16 | 19/20 = 0.9500 / 0.8667 / 16 | none | none | none | none |
| C | faithful | 18/20 = 0.9000 / 0.8500 / 16 | 19/20 = 0.9500 / 0.9250 / 18 | HOLD2_014 | none | HOLD2_014, HOLD2_020 | none |
| T | faithful | 18/20 = 0.9000 / 0.8500 / 16 | 19/20 = 0.9500 / 0.9250 / 18 | HOLD2_014 | none | HOLD2_014, HOLD2_020 | none |

Faithful, pool C, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): HOLD2_014 (- → 1), HOLD2_020 (2 → 1).

Faithful, pool T, queries whose first useful rank changed (base → fa; `-` = no useful candidate in the top 3): HOLD2_014 (- → 1), HOLD2_020 (2 → 1).

## 4. Selection (frozen rule, held-out 2 faithful, both pools)

Rule (ROADMAP addendum 2026-10-26, "Selection", kept by the 2026-10-27 notes): on held-out 2
faithful, F-a against today's code on the same faithful queries, in **both** pools: top-3 useful
and MRR at least the baseline, rank-1 count not lower, at least one strictly higher. Otherwise null.

| Pool | | top-3 useful | MRR | rank-1 count |
|---|---|---|---|---|
| C | base | 18/20 = 0.9000 | 0.8500 | 16 |
| C | fa | 19/20 = 0.9500 | 0.9250 | 18 |
| C | rule | 0.9500 >= 0.9000 yes | 0.9250 >= 0.8500 yes | 18 >= 16 yes |
| T | base | 18/20 = 0.9000 | 0.8500 | 16 |
| T | fa | 19/20 = 0.9500 | 0.9250 | 18 |
| T | rule | 0.9500 >= 0.9000 yes | 0.9250 >= 0.8500 yes | 18 >= 16 yes |

All three metrics are not lower, and all three are strictly higher, in C and in T. **F-a: SELECTED.**

What moved (identical in both pools): HOLD2_014 has no useful candidate in the top 3 under base
and a useful one at rank 1 under fa; HOLD2_020 goes from rank 2 to rank 1. No held-out 2 query got
worse. The MRR gain is exactly these two (1/20 for the first, 0.5/20 for the second: 0.075). One
query is worth 0.05 of top-3 accuracy, so the selection is carried by two queries of 20. Neither
HOLD2_014 nor HOLD2_020 is among the routing differences in section 6, so the selection is not
mixed with a stage effect. The stored (folded-ASCII) held-out 2 queries are identical between the
arms (0.9500 / 0.8667 / 16 in both pools), as the gate requires.

## 5. Residue and repaired queries (secondary analysis; selection and step 4 use all queries)

Faithful queries, the residue and repaired ids of the addendum removed (v4 COMP_001, 002, 011,
012, 013, 014, 017, 018, 019, 021, 022 leaves 9; held-out 1 HOLD_008, 026 leaves 18). LE-v1,
NAME-v1 and held-out 2 have no residue, so their numbers in section 3 are already the residue-free
numbers.

| Set | Pool | base: top-3 / MRR / rank-1 | fa: top-3 / MRR / rank-1 |
|---|---|---|---|
| v4 (9 of 20) | C | 8/9 = 0.8889 / 0.7593 / 6 | 9/9 = 1.0000 / 1.0000 / 9 |
| v4 (9 of 20) | T | 8/9 = 0.8889 / 0.7037 / 5 | 9/9 = 1.0000 / 1.0000 / 9 |
| held-out 1 (18 of 20) | C | 16/18 = 0.8889 / 0.7593 / 12 | 16/18 = 0.8889 / 0.8241 / 14 |
| held-out 1 (18 of 20) | T | 16/18 = 0.8889 / 0.7593 / 12 | 16/18 = 0.8889 / 0.8241 / 14 |

The v4 direction survives without the stale `pl` residue. Of the v4 changes in section 3, COMP_004
(T), COMP_007, COMP_008 and COMP_020 are residue-free queries; COMP_001, COMP_013, COMP_017 and
COMP_022 are residue queries, where the addendum warns that the residue token itself can change
the pool in F-a without any notation effect.

## 6. Routing difference (`routing_diff.txt`)

The `stage_used` column is kept for every faithful query in both arms. Queries whose routing
differs between base and fa (`-` = no stage; `a->b` = base stage to fa stage):

| Set | Pool | Count | Queries |
|---|---|---|---|
| v4 | C | 6/20 | COMP_010 (Earlier Egyptian->-), COMP_013 (-->Earlier Egyptian), COMP_016 (-->Earlier Egyptian), COMP_017 (-->Late Egyptian), COMP_019 (Late Egyptian->-), COMP_022 (Late Egyptian->-) |
| v4 | T | 6/20 | the same six |
| held-out 1 | C | 6/20 | HOLD_004 (Earlier Egyptian->-), HOLD_010 (-->Earlier Egyptian), HOLD_013 (Late Egyptian->-), HOLD_016 (-->Late Egyptian), HOLD_019 (-->Earlier Egyptian), HOLD_023 (-->Earlier Egyptian) |
| held-out 1 | T | 7/20 | the six above plus HOLD_017 (Earlier Egyptian->-) |
| LE-v1 | C | 4/30 | LE_011 (Late Egyptian->-), LE_028 (-->Late Egyptian), LE_034 (-->Late Egyptian), LE_038 (-->Late Egyptian) |
| LE-v1 | T | 4/30 | the same four |
| NAME-v1 | C | 5/30 | NAME_001 (-->Demotic), NAME_005 (-->Demotic), NAME_009 (-->Earlier Egyptian), NAME_010 (Earlier Egyptian->-), NAME_028 (-->Earlier Egyptian) |
| NAME-v1 | T | 5/30 | the same five |
| held-out 2 | C | 6/20 | HOLD2_001 (-->Late Egyptian), HOLD2_004 (Earlier Egyptian->-), HOLD2_007 (-->Late Egyptian), HOLD2_013 (-->Late Egyptian), HOLD2_028 (Late Egyptian->-), HOLD2_029 (-->Late Egyptian) |
| held-out 2 | T | 6/20 | the same six |

A routing change mixes a stage effect into the F-a effect, and these files cannot separate the
two (each arm ran the whole pipeline once with the same flags). Where a query's useful rank changed
and its routing also changed (section 3 move lists against the table above):

- v4: COMP_013, COMP_022 (C and T), COMP_017 (T only moved);
- held-out 1: HOLD_019;
- LE-v1: LE_034;
- NAME-v1: NAME_005 (lost its top-3 place), NAME_028 (C only moved);
- held-out 2: none. The six rerouted held-out 2 queries have an unchanged useful rank in both pools.

The stored queries are identical in every column, `stage_used` included (gate, section 2), so
routing differences exist only for faithful queries.

## 7. Rows that reached fa's top results with no shared faithful token

Promised by the 2026-10-27 note ("the report lists rows admitted to F-a's pool by fuzzy or TF-IDF
alone with zero faithful token overlap"). Method: for every faithful query of the five sets in both
pools, each of fa's three suggested readings was compared with the query text. Both sides were
split with `unfolded_reading_form` (the faithful key, `app/services/suggestions.py`), and a
suggestion counts as sharing a faithful token when at least one resulting word is equal. This was
computed by a scratch script from the committed result files; it is not part of the repository.

**Result: none.** The five sets hold 120 faithful queries (20 + 20 + 30 + 30 + 20), run in two
pools, three slots each: 720 slots. Not one of them lacks a shared faithful word; the list is
empty. The base arm also shows 0 of 720 by the same test, so the test does not separate the arms.
The distribution of shared words per slot separates them a little: fa has 695 slots with three or
more shared words, 25 with two and none with one; base has 657, 61 and 2 with exactly one.

Limits of this listing, stated so it is not over-read. (a) The harness keeps the top three
suggestions only, so it says nothing about rows that entered the retrieval pool by fuzzy or TF-IDF
scores and then lost in the re-rank; that pool-level listing cannot be rebuilt from these files and
would need a re-run. (b) "Shares a faithful word" is any equal word, function words (`n`, `m`,
`nb`, `ꞽw`) included, so it is a weak test of relevance. (c) It is made at the level of the
suggested reading, and one suggestion can merge several corpus rows.

## 8. Token re-split caveat

F-a also re-splits tokens (2026-10-27 note). The faithful key is the `unfolded_reading_form` piece
on both sides, so `ꜥḥꜥ.n sḏm=f` is keyed `ꜥḥꜥ n sḏm f` where today's search key is `ahan sdjm f`. Part
of any F-a effect in section 3 can therefore come from re-segmentation (`.n`, `=f`, hyphens, the
treatment of editorial text and markers), not from the ꜣ/ꜥ, ḫ/ẖ, ḥ/h distinction. This run has
no arm that separates the two (F-b was not run, and there is no arm that re-splits tokens
without also keeping the letters apart), so no gain or loss above is attributed to notation alone. The same applies to the ASCII-only
words of a Unicode query, which F-a compares by their faithful form in the re-rank (addendum;
97 of the 100 faithful queries in the first four sets have such words, per the addendum), and to the
reading of `pl` residue words in v4 (section 5).

## 9. Other observations, outside the selection rule

- **NAME-v1 faithful gets worse under fa** (both pools): top-3 useful 30/30 -> 28/30 in C and
  29/30 -> 27/30 in T, MRR 0.8722 -> 0.8667 (C) and 0.8611 -> 0.8500 (T), rank-1 count 23 -> 24 in
  both. NAME_005 and NAME_017 lose their top-3 place (NAME_017 from rank 1), NAME_011 slips from 1
  to 2, NAME_018, NAME_019 and NAME_024 rise from 2 to 1. The selection rule does not use NAME-v1,
  and step 4 as frozen does not either, but a set of the same shape as NAME-v1 would not pass the
  step-4 test (top-3 and MRR at least the baseline in C and T). Whether that is a name effect or a
  re-split effect is not separated here.
- **Held-out 1 faithful:** one top-3 loss (HOLD_002, 3 -> -) against one gain (HOLD_014, - -> 1);
  MRR 0.7500 -> 0.8167 and rank-1 count 13 -> 15 in both pools.
- **LE-v1 faithful:** two gains (LE_008, LE_034), one loss (LE_043, 2 -> -); top-3 26/30 -> 27/30,
  MRR 0.7833 -> 0.8611, rank-1 21 -> 25 in both pools.
- **v4 faithful:** top-3 19/20 -> 20/20 (C) and 18/20 -> 20/20 (T), MRR 0.8333 -> 0.9417 and
  0.7583 -> 0.9167, rank-1 15 -> 18 and 13 -> 17; losses of rank 1 at COMP_013 (both pools) and
  COMP_017 (T).
- Pools C and T give the same metrics and the same move lists on held-out 1, LE-v1 and held-out 2
  faithful. They differ on v4 (T adds COMP_001, 004, 017 to the moves) and on NAME-v1 (base and fa
  both score lower in T), as section 3 shows.
- The faithful variants are derived from each query's expected reading, so they are cleaner
  notation than a typed query would be; the benchmark cannot say how F-a behaves on a user's
  mixed or partly ASCII input (those stay on today's path by definition).

## 10. Decision and next step

Applying the frozen rule exactly: **SELECTED** (held-out 2 faithful, pool C and pool T:
top-3 useful 0.9000 -> 0.9500, MRR 0.8500 -> 0.9250, rank-1 count 16 -> 18, in both).

The next step is the **one-time held-out 3 confirmation** (step 4): F-a only, both pools, the same
pinned `$CE` lines, passing iff top-3 useful and MRR are at least the baseline and the rank-1 count
is not lower in C **and** in T (no strict improvement required; held-out 3 informs no tuning; a fail
spends it). It has **not been run** and held-out 3 stays sealed until it is. Nothing is promoted by
this note: the branch default is still `EXP3_FA_DEFAULT = False` (`e2a9596`; the fa commit
`b4844a1` exists only on `exp3-fa-arm-2026-10-26`), the README notation table is unchanged, and
nothing goes to Nederhof until step 4 has been run and passed.
