# A Late Egyptian evaluation set (LE-v1) and its first numbers

Roadmap item 6 of the plan for 2026-09-05: *"Late Egyptian evaluation set from Ramses
(measures the new stages) — frozen set + first numbers."*

## Why this set exists

Item A built the language-stage machinery (`app/services/stage.py`,
`--stage none|auto|declared`) because Ramses' 40,064 Late Egyptian rows, once loaded,
outvoted the evidence an Earlier Egyptian paste needed. The machinery was then measured
on v4 and on held-out 1 — and **both of those sets are almost entirely Earlier Egyptian /
BBAW / AES targets**. v4 has 0 Ramses targets; held-out 1 has 2. So neither set can tell
us whether the stage machinery helps, hurts, or does nothing *for a Late Egyptian query*,
which is the case it was built for.

LE-v1 is that missing set. It is a **frozen** benchmark: written once, its numbers
reported next to it, never tuned against. v4, held-out 1 and `release_baseline.json` are
untouched by this work.

---

## Pre-registered

Everything in this section was written down **before** the builder flag was implemented,
before the set was built, and before any evaluation was run. It is the contract this
document is then held to.

### 1. The candidate pool and the selection rule

- **Pool** = corpus rows whose `language_stage` cell is exactly `Late Egyptian`. On the
  live 130,472-row corpus that is **43,665 rows: Ramses 40,064 + TLA 3,601**. (The other
  86,807 rows are `Earlier Egyptian` 12,772, `Demotic` 11,996, `Unspecified (BBAW)`
  52,216, `Unspecified (AES)` 9,823.)
- **Selection** uses `scripts/build_competitive_ambiguity_benchmark.py` unchanged in
  every rule that decides *which* rows are eligible and *which* are picked — rivals count
  at overlap ≥ 0.16, exclusion of any row with a near-identical twin anywhere in the
  corpus at overlap ≥ 0.9, ranking by number of genuine rivals, one row per distinct
  canonical reading, the single-ubiquitous-token signal filter. No parallel
  implementation; the same script that produced v4 and held-out 1.
- **Flags:** `--exhaustive-twins` (the prefix-filtered, uncapped twin guard — the one
  that would have caught v4's COMP_004/COMP_017), `--exclude-benchmark` against **both**
  v4 *and* held-out 1, `--id-prefix LE`, `--limit 30`, `--pool-size 0` (all rows
  considered).
- **30 rows, not 20**, because the pool has two sources with different conventions
  (Ramses and TLA Late Egyptian) and the set should have room for both.
- `--exclude-benchmark` currently accepts one file. It is **extended to be repeatable**
  (`--exclude-benchmark A --exclude-benchmark B`), each file's expected rows *and* their
  near-twins removed from candidacy exactly as today, with a test. A single
  `--exclude-benchmark` invocation must behave byte-for-byte as it does now.

### 2. The builder's stage filter

A new `--stage` flag on the builder. Its contract, stated in advance:

- It filters the **candidate pool only** — rows whose `language_stage` cell does not
  equal the flag's value are skipped as candidates and counted in the builder log under
  their own heading.
- **Twin detection still runs against the WHOLE corpus**, exactly as `--exclude-benchmark`
  and `--pool-size` already do. A Late Egyptian row with an Earlier Egyptian or BBAW
  edition twin must still be thrown out: the eval loads the whole corpus, so the guard
  must see the whole corpus.
- Default is unset → no filtering → the builder's behaviour is unchanged for every
  existing caller.
- The exact string is matched against the corpus cell (`--stage "Late Egyptian"`), not a
  normalised or derived stage. The corpus column is the authority here.

### 3. The output CSV carries `language_stage`

The builder emits one extra column, `language_stage`, holding the selected corpus row's
own `language_stage` cell. `--stage declared` in the eval harness reads exactly this
column (`bench_row.get("language_stage", "")` → `normalize_stage`), so without it the
`declared` run would silently declare nothing and would be indistinguishable from a
pooled run — which would make one third of this experiment vacuous.

Provenance note, stated up front so it is not mistaken for v4's: v4's `language_stage`
column was *derived* post hoc by `derive_v4_declared_stage` (TLA id prefix, else `period`
keywords). LE-v1's comes straight from the corpus column. For this set the two agree by
construction — every selected row is `Late Egyptian` by the pool definition, and the TLA
prefix rule maps `TLA_LATE_*` to the same value — so no interpretation is added.

### 4. Query generation: unchanged, and checked for leakage

The builder's three query types (`simplified_transliteration`,
`partial_transliteration`, `normalized_reading_order`, assigned round-robin by selection
order) are used exactly as v4 used them, with yod handled by the existing
`loose_reading_form` fold and no Ramses-specific special case.

**To be verified and reported before the numbers, whatever the answer:** that the
generated query text for a Ramses row does not leak the `_` word-boundary marker or MdC
ASCII digraphs (`A`, `a` for ꜥ, `H`, `x`, `X`, `T`, `D`, `S`, `q`, uppercase `I`) that the
raw Ramses files use. If it does leak, that is reported as a finding and the set is built
anyway — the set measures the pipeline as it is, not as we would like it.

### 5. The evaluation

`scripts/run_competitive_ambiguity_eval.py --query-path app` (the app's real path, the
harness default since 2026-09-05) against LE-v1, in **all three stage modes**, one
process at a time, target row excluded by the harness's own `_exclude_expected`:

```
--stage none      -> data/benchmarks/ceval_le_v1_app_none_results.csv
--stage auto      -> data/benchmarks/ceval_le_v1_app_auto_results.csv
--stage declared  -> data/benchmarks/ceval_le_v1_app_declared_results.csv
```

Useful rule: **v4** (the frozen rule). v5 is not run here; this set is about stages, not
about the useful definition.

### 6. Answerability

Rule A from `docs/v4-answerability-and-v5-rule.md` — *exclude the expected row, apply the
harness's own useful test to every remaining corpus row with that row's own
`acceptable_token_overlap_threshold`; a query is answerable iff at least one corpus row is
useful* — applied to LE-v1 by pointing `scripts/compute_v4_answerability.py` at it
(`--benchmark`, `--out`). The script already takes both flags and reads only columns the
builder writes, so no change is expected; if it turns out to hard-code v4, the change is
minimal and recorded.

### 7. The reportable numbers

- top-3 useful-family accuracy and MRR, **per stage mode** (`none`, `auto`, `declared`);
- rank-1 (top-1 useful) count per mode;
- the misses by benchmark id per mode, with their `useful_family_reasons`;
- the per-query `stage_used` under `auto`, and **how many auto inferences matched the
  target's declared stage** (which is `Late Egyptian` for every row of this set, so this
  is a clean measure of the inference's accuracy on Late Egyptian material);
- answerability counts under Rule A.

### 8. Hypothesis

**None is registered.** No prediction is made about which stage mode wins, so that
whatever comes out is read as it is rather than against an expectation formed here.

### 9. What this run may not do

No constant is moved, no weight tuned, no threshold adjusted, in response to anything
LE-v1 says. `data/benchmarks/competitive_ambiguity_eval_queries_v4.csv`,
`..._holdout_2026-09-05.csv` and `release_baseline.json` are not edited. No fix is
proposed in the Results section — a diagnosis is the next session's work, on this
evidence.

---

## Build log

Command:

```
python scripts/build_competitive_ambiguity_benchmark.py \
  --examples data/processed/examples.csv \
  --output  data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv \
  --stage "Late Egyptian" \
  --exhaustive-twins \
  --exclude-benchmark data/benchmarks/competitive_ambiguity_eval_queries_v4.csv \
  --exclude-benchmark data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv \
  --id-prefix LE \
  --limit 30
```

Output, verbatim:

```
Twin detection over the full corpus: 130472 rows, 9495 distinct tokens.
Excluding 40 rows named by data/benchmarks/competitive_ambiguity_eval_queries_v4.csv, data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv and 2 near-twins of them (overlap >= 0.9).
Restricting candidates to language_stage == 'Late Egyptian' (43665 of 130472 corpus rows); twin detection stays whole-corpus.
Candidates considered: 130472 rows -> 39428 eligible (skipped 42 excluded by --exclude-benchmark, 86770 outside language_stage 'Late Egyptian', 217 too short, 916 without distractors, 3099 with a near-identical twin anywhere in the corpus at overlap >= 0.9)
Dropped 14 selected rows whose generated query was a single ubiquitous token (no retrievable signal).
Wrote 30 competitive ambiguity benchmark rows to data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv
```

Read that as: of the 130,472 corpus rows, 86,770 are not Late Egyptian and 42 are spent by
v4 or held-out 1 (40 named rows + 2 near-twins of them); of the remaining Late Egyptian
candidates, 217 have fewer than two tokens, 916 have no rival at overlap ≥ 0.16, and
**3,099 have a near-identical twin somewhere in the whole corpus** and are thrown out —
7.1% of the Late Egyptian pool, against 10.5% (13,659/130,472) corpus-wide for held-out 1.
39,428 rows remain eligible; the 30 with the most genuine rivals, one per distinct
canonical reading, are the set. Ids run `LE_001`–`LE_044` with gaps, because 14 of the
selected surplus were dropped on the signal filter (below).

### Twin cross-check, LE-v1 vs v4 vs held-out 1

Exhaustive (prefix-filtered, uncapped) scan of every LE-v1 target against all 130,472
rows, plus target-row disjointness across the three sets:

```
LE-v1 targets found in the corpus: 30/30
LE-v1 targets with an edition twin at Jaccard >= 0.9 anywhere in the 130,472-row corpus: 0
LE-v1 ∩ v4 target rows: 0
LE-v1 ∩ held-out 1 target rows: 0
v4 ∩ held-out 1 target rows (unchanged control): 0
closest LE-v1 target to any v4 target: Jaccard 0.4400 (LE_029 vs COMP_003)
closest LE-v1 target to any held-out 1 target: Jaccard 0.6190 (LE_002 vs HOLD_025)
```

**Zero twins.** LE-v1 carries none of the free hits v4 carries (COMP_004 and COMP_017 at
Jaccard 1.0), so its numbers need no "non-twin" companion column. The closest a LE-v1
target comes to any row of the other two sets is 0.619 — well below the 0.9 duplicate
threshold, and a different sentence.

### Leakage check (pre-registered item 3) — nothing leaks

```
query_input cells containing the Ramses '_' word boundary: 0/30
expected_key_tokens cells containing '_': 0/30
query_input character set: ' abdfghijkmnpqrstwy'
characters outside [a-z0-9 ]: []
MdC ASCII uppercase markers (A H X T D S I ...) present: []
expected_transliteration (raw gold) character set: ' ()-.4<=>?bdfghkmnpqrstwyšḏḥḫṯẖꜣꜥꞽ'
bare ASCII 'i' anywhere in the raw Ramses gold of this set: 0 of 30 rows
```

The reason is that `scripts/import_ramses.py` already did the conversion at import time:
the Ramses rows in `examples.csv` are stored in the corpus's own TLA/Berlin
transliteration, with yod as `ꞽ` (not the raw files' `i`) and no `_`. So the query text a
Ramses row produces is folded by exactly the same `loose_reading_form` path as a TLA row,
and `loose_reading_form('ꞽw') = 'iw'` whichever source the `ꞽw` came from. There is no
Ramses-specific handling anywhere in the query generation, and none is needed. The
lowercase digraphs visible in the queries (`sh`, `kh`, `dj`, and `a` for both ꜣ and ꜥ) are
the project's own fold, not MdC residue — a TLA row folds to the same shapes.

### Two properties of this set that were not designed and must be stated

1. **All 30 targets are Ramses; none is TLA Late Egyptian.** The pool was
   Ramses 40,064 + TLA 3,601, and the pre-registration said 30 rows so there would be
   "room for both". There was room; the deterministic selection rule — rank by number of
   genuine rivals — simply put 30 Ramses rows on top, which is unsurprising when Ramses
   is 92% of the pool and consists largely of formulaic administrative letters with many
   near-relatives. The rule was **not** changed afterwards to force TLA rows in. So
   LE-v1 measures *Ramses* Late Egyptian, and the two-source ambition in the
   pre-registration was not met.
2. **No target carries lemma ids** (0 of 30 have a non-empty `lemma_sequence`; Ramses
   ships none). Both lemma branches of the v4 useful rule are therefore vacuous for every
   query, and scoring reduces to the token-overlap test at threshold 0.26 — the same
   threshold for all 30 rows. A consequence worth recording: the pre-registered v5
   lemma-first rule would score **identically** to v4 on this set by construction, which
   is why running it here would have been meaningless. 13 of 30 targets have hieroglyphs;
   the other 17 are text-only.

Query types came out 15 simplified / 15 partial / **0 reading-order**. That is the same
14 rows the log reports dropping on the signal filter: `normalized_reading_order` is empty
for all 40,064 Ramses rows, so every reading-order slot that landed on a Ramses row
generated an empty query and was discarded. The type generation was left unchanged as
pre-registered; the effect is recorded, not worked around.

## Results

All numbers below were measured on 2026-09-05 against the 130,472-row corpus at
`08d61d2`, plus the two builder flags this document adds. `--query-path app` (the app's
real path, the harness default), useful rule **v4**, 30 queries, target row excluded by
the harness's own `_exclude_expected`. Three runs, one process at a time:

```
python scripts/run_competitive_ambiguity_eval.py \
  --benchmark data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv \
  --query-path app --stage {none,auto,declared} \
  --results  data/benchmarks/ceval_le_v1_app_{none,auto,declared}_results.csv \
  --failures data/benchmarks/ceval_le_v1_app_{none,auto,declared}_failures.csv
```

### Main table

| stage mode | top-1 useful (rank-1 count) | **top-3 useful** | **MRR** | top-3 exact | misses |
|---|---|---|---|---|---|
| `none` | 0.7333 (22/30) | **0.8667** | **0.8000** | 0.0 | LE_008, LE_014, LE_034, LE_044 |
| `auto` | **0.7667 (23/30)** | **0.8667** | **0.8167** | 0.0 | LE_008, LE_014, LE_034, LE_044 |
| `declared` | 0.7333 (22/30) | **0.8667** | **0.8000** | 0.0 | LE_008, LE_014, LE_034, LE_044 |

Rank distribution of the useful-family hit (`-` = not in the top 3):

| mode | rank 1 | rank 2 | rank 3 | miss |
|---|---|---|---|---|
| `none` | 22 | 4 | 0 | 4 |
| `auto` | 23 | 3 | 0 | 4 |
| `declared` | 22 | 4 | 0 | 4 |

No twin exclusions are needed: LE-v1 contains no target with an edition twin, so unlike
v4 there is no second "non-twin" column and no hit in this table is free.

`top3_exact_accuracy` is **0.0 in all three modes**. That is expected rather than
alarming and is not a new result: these are long Ramses letter-sentences, the target row
itself is excluded, and no other row in the corpus carries the identical reading — which
is exactly what the twin guard guarantees. Only the useful-family numbers are meaningful
on this set.

### Where the three modes actually differ

The three modes are **not** producing the same ranking — `none` and `declared` return a
different top-3 on **9 of 30** queries (LE_001, LE_005, LE_008, LE_013, LE_016, LE_023,
LE_025, LE_026, LE_031); `none` and `auto` differ on 6; `auto` and `declared` on 3. The
stage machinery is doing something on most of this set. It just almost never changes
whether a useful row lands in the top 3. **Exactly two queries change rank at all:**

| id | `none` | `auto` | `declared` | what `auto` inferred |
|---|---|---|---|---|
| LE_001 | 1 | 1 | **2** | *(nothing — fell back to pooled)* |
| LE_005 | **2** | 1 | 1 | Late Egyptian |

Everything in the table above follows from those two rows. `auto` is ahead of both other
modes because it collected LE_005's gain (it did infer Late Egyptian there, so it behaved
like `declared`) *and* avoided LE_001's loss (it inferred nothing there, so it behaved
like `none`). Its one-place lead is one query wide, on n=30, and should be read as such.

### Auto-mode stage inference

Every LE-v1 target's declared stage is `Late Egyptian`, so this is a clean read on the
inference itself.

| `auto` inferred | queries | matches the target's declared stage |
|---|---|---|
| Late Egyptian | 16 | yes |
| *(nothing — pooled fallback)* | 14 | n/a |
| any other stage | **0** | — |

- **16/30 auto inferences match the target's declared stage; 0/30 are wrong.** When
  `infer_stage` commits on Late Egyptian material, it commits correctly — every single
  time on this set. There is no Earlier Egyptian or Demotic misfire anywhere in the 30.
- **14/30 abstain.** They fall through to pooled retrieval. The likely cause, read from
  the code and not isolated by any run here, is the `lift ≥ 1.5` requirement over the
  stage's base rate among labelled rows (added in the item A follow-up to remove Ramses'
  bulk bias); a `min_lift=None` comparison would confirm it and was not run. So on Late Egyptian text
  queries, auto is *conservative*, not *inaccurate* — a different failure shape from the
  one item A was fixing.
- The abstentions are not concentrated among the misses: of the 4 misses, 2 had a stage
  inferred (LE_008, LE_014) and 2 did not (LE_034, LE_044).

For completeness: `declared` used `Late Egyptian` on 30/30 (it reads the benchmark
column), and `none` used no stage on 30/30, as designed.

### Answerability (Rule A)

`scripts/compute_v4_answerability.py --benchmark …_le_v1.csv --useful-rule v4 --out
data/benchmarks/competitive_ambiguity_eval_answerability_le_v1.csv`. The script needed
**no change** — it already takes `--benchmark` and `--out` and reads only columns the
builder writes, so the "if it hard-codes v4 columns, extend minimally" branch of the
pre-registration was not taken. Its `--verify 200` cross-check against the unrefactored
`_useful_reason` reported no disagreement.

| | count |
|---|---|
| answerable under Rule A | **30 / 30** |
| unanswerable | 0 |
| useful rows in the corpus per query | min 644, median 1,568 (1567.5), max 4,106 |
| best achievable token overlap per query | min 0.4138, median 0.5000, max 0.8889 |
| queries with any lemma-id intersection anywhere in the corpus | 0 |

So the answerable-only denominator is 30 and every answerable-only figure equals its
all-queries figure — the same situation as v4. **All four misses are answerable with
room to spare**, well above their 0.26 threshold:

| miss | useful rows in the corpus | best achievable token overlap | best row |
|---|---|---|---|
| LE_008 | 2,901 | 0.4500 | `RAMSES_803FB6311058/S_train_061011` |
| LE_014 | 1,282 | 0.5455 | `bbaw_egyptian_2018/B095368` |
| LE_034 | 789 | 0.4194 | `RAMSES_B63B82DCD93D/S_train_003114` |
| LE_044 | 1,639 | 0.5238 | `RAMSES_75CAE808679E/S_train_064958` |

### The misses

The same four in every mode. All twelve suggestions per mode were scored
`no useful-family match`; the number after each is that suggestion's token overlap with
the expected key tokens, against a 0.26 threshold.

**LE_008** (`partial_transliteration`, `RAMSES_643F3174384A/S_val_000565`, auto inferred
Late Egyptian) — query `iw iri shmi rdi rmtj sha wpw na`, expected
`ꞽw m ꞽrꞽ šmꞽ.t r rdꞽ.t n =f rmṯ.w n šꜣ wpw-ḥr nꜣ rmṯ.w mtr ꞽ.wn m-dꞽ =f ꜥn`.
Best of the three: 0.231 (`ꞽn bw ꞽrꞽ =tw šdꞽ rmṯ m-dꞽ nꜣ n pꜣ ẖꜥ`), then 0.190
(`m-ꞽri̯ šmi̯ ⸢ꞽ⸣y ꞽw`) and 0.182 (`ꞽw bw ꞽrꞽ shꜣ wp.t`). 0.029 short of the threshold.

**LE_014** (`partial_transliteration`, `RAMSES_D7CC486CBC72/S_train_014710`, auto inferred
Late Egyptian) — query `imy di tw pa htr wn pri tay`. Best 0.250
(`m-ḏr wn pꜣ ḥtr n ꞽmn-ms m-dꞽ =k`), then 0.200 and 0.190. **0.010 short.**

**LE_034** (`simplified_transliteration`, `RAMSES_6D1BCA97204A/S_train_003824`, auto
inferred nothing) — query `ir rmtj nb ssh nb nty hab swaw`. Best 0.250
(`ꞽr rmṯ nb nty m tꜣ r-ḏrw =f`), then 0.241 (`ꞽr nb nty nkt nb qꞽ nb nty (ḥr) ḫpr m-dꞽ
rmṯ`) and 0.214. **0.010 short**, with all three suggestions between 0.214 and 0.250.

**LE_044** (`partial_transliteration`, `RAMSES_A3783D49495E/S_train_048900`, auto inferred
nothing) — query `khpr ba hm aa mrr sw mw hw`. Best 0.208
(`ḫpr sdbꞽ =f r šnt sw sfḫ kꜣ m mrr sw`), then 0.130 and 0.091. The only genuinely
distant miss of the four.

Three of the four are near-misses of the *scoring rule*, not retrieval blanks: LE_014 and
LE_034 are within 0.010 of their threshold, LE_008 within 0.029. Whether that says
something about the 0.26 constant is not decided here — no constant is moved on this
evidence, and this set is frozen.

### What the numbers say

**On Late Egyptian material the stage machinery neither helps nor hurts the headline: all
three modes score 0.8667 top-3 useful, and the same four queries miss in every mode.**
It is visibly *active* — `none` and `declared` disagree on the top-3 for 9 of 30 queries
— but that activity reshuffles rows that were already useful or already useless, and
changes the graded outcome for exactly two queries. Whatever item A bought, it is not
visible as a top-3 gain on Late Egyptian queries; what it bought was the Earlier Egyptian
paste gate, and this set is evidence that the cost on the other side is approximately
nil, not that there is a gain here.

**The graded differences run in `auto`'s favour, one from inferring and one from
abstaining.** Against `none`, the only rank change is LE_005, where `auto` *inferred* Late
Egyptian and promoted the useful row from 2 to 1; against `declared`, the only change is
LE_001, where `auto` *abstained* and avoided the loss that declaring caused. `auto` leads on
MRR (0.8167 vs 0.8000) and rank-1 count (23 vs 22)
because it declined to infer a stage on LE_001 — where declaring the correct stage
demotes the useful row from rank 1 to rank 2 — while still inferring one on LE_005, where
it promotes. A conservative inference layer beating an always-correct declaration is a
result about the *retrieval weighting*, not about the inference: declaring `Late
Egyptian` on all 30 rows, which is by definition the right answer for all 30, scores no
better than declaring nothing.

**The inference itself is accurate but quiet: 16/30 correct, 0/30 wrong, 14/30 abstain.**
On this material the `lift ≥ 1.5` gate is the probable binding constraint (inferred from the
code, not isolated by a run), and whatever holds the 14 back fails safe. That
is worth knowing before anyone tunes it, and it is the sharpest single fact this set
produced — it could not have been measured on v4 or held-out 1, which between them carry
2 Ramses targets.

No fix is proposed here, and nothing in the pipeline was changed in response to any of
the above. LE-v1 is frozen as of this commit.

### Scope and limits of this set, restated

- It measures **Ramses** Late Egyptian only (30/30 targets), not TLA Late Egyptian.
- It measures the **token-overlap** useful rule only — no target carries lemma ids, so v5
  would score identically and the lemma branches never fire.
- It has **no reading-order queries** (15 simplified / 15 partial), because Ramses rows
  carry no `normalized_reading_order`.
- Its 0.8667 is **not** comparable to v4's 0.90 or held-out 1's 0.75 as a "better" or
  "worse": different targets, different sources, different query mix, and LE-v1 alone has
  no twin-inflated hits.

### After verification (2026-09-05)

An independent verifier reproduced the set (byte-identical), all three evaluations (all 25
columns identical), the twin check and the answerability file, and flagged three prose
points, corrected above: the bolded "abstaining rather than inferring" sentence was true
only against `declared` (against `none` the gain is LE_005, where auto inferred); the
`lift ≥ 1.5` attribution is inferred from the code, not measured; the median is 1,568.
Also noted: the builder's `language_stage` column goes through `normalize_stage` (identity
for the three named stages, `""` for Unspecified) rather than copying the corpus cell
verbatim — no effect on LE-v1, disclosed for a future non-LE build.
