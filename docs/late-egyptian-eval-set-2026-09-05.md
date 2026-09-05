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

*(filled in below, verbatim, after the build)*

## Results

*(filled in below, after the runs)*
