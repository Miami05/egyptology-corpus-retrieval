# Route 1 — cross-edition queries: a sealed benchmark (pre-registration)

**DRAFT. NOT APPROVED.** Written 2026-10-28 on branch `route1-xed-benchmark-2026-10-28` (from main
`8f4cf70`). Nothing here has been run against the ranker. Until a reviewer approves it, the sealed
file below is a candidate and may be deleted and rebuilt; after approval it is frozen (section 8).

## 0. The question this instrument asks

Many sentences exist twice in the corpus, entered by two projects (TLA, Ramses, BBAW, AES), each with
its own transliteration conventions. A reader who types a line the way *one* project wrote it is a
realistic "different typist" for the *other* project's row. Route 1 asks: **when the query is edition
A's transliteration, typed as A wrote it, and edition B's row of the same sentence is in the corpus
(A's own row and A's near-copies are not), does the reading-suggestion layer put B's reading, or a
row that counts as useful against B, in the top 3?**

The existing benchmarks (v4, held-out 1/2/3, LE-v1, NAME-v1) answer a different question: they
*remove* the target and ask whether the suggestion layer can still say something useful about a
sentence that is not in the corpus. Route 1 keeps the answer in the corpus and takes away the query's
own source. It measures notation tolerance in retrieval and ranking, not generalisation to unseen
sentences. The two must not be quoted as if they were one number.

## 1. What a query is

* **Text:** the transliteration of **one side of a frozen pair**, taken verbatim from the corpus cell
  `transliteration_gold` (the pair file stores it as `a_transliteration` / `b_transliteration`; the
  builder checks it still equals the corpus cell). No fold, no simplification, no truncation, no
  reordering: it is what the other project's typist would have typed. `query_type` is a new value,
  `cross_edition_transliteration` (the harness only special-cases `normalized_reading_order`).
  Because the stored query already is the faithful one, there is a single query column and no folded
  variant, so every arm (baseline, F-a, anything later) receives the identical string.
* **Which side is the query:** decided **once, before any exclusion**, by a seeded shuffle inside each
  source pair: the pair ids of a source pair are sorted, shuffled with
  `random.Random(f"{seed}|{source_pair}")`, and the first half (rounded down) is typed as side A, the
  rest as side B. Seed **20261028**. Exclusions therefore cannot move another pair's direction.
* **One direction per pair, not both. Why:** the two directions of a pair are the same sentence
  counted twice; they share rows, vocabulary and any text-level quirk, so 600 queries from 300 pairs
  would look like n = 600 and have n ≈ 300 of information, and a paired comparison across arms would
  see correlated outcomes as independent. One direction keeps n honest. The cost: any one source's
  direction-specific weakness (for example Ramses-as-query) is estimated from ~25 queries per source
  pair, so the report shows both directions separately but the pre-registered decision uses pooled
  numbers only (section 9).
* **Which side was favoured:** neither. The pair file orders sides by source name (TLA is side A 148
  times, Ramses side B 149 times), so "always query from A" would silently make Ramses the permanent
  target and TLA the permanent typist. The shuffle gives, over the 295 queries, AES 76 / BBAW 72 /
  Ramses 74 / TLA 73 as query source and 73 / 73 / 73 / 76 as answer source.

## 2. What the target is, and what counts as a hit

* **Target row = the other side of the pair.** `expected_transliteration`, `expected_source_text_id`,
  `expected_source_sentence_id`, `expected_key_tokens` (sorted loose tokens of that row),
  `expected_lemma_ids` (its `lemma_sequence` ids, when it has any) and the threshold (0.34 if the
  target has at most 4 key tokens, else 0.26: the competitive builder's own rule) all come from it.
  `language_stage` is the target row's own corpus cell (the same rule the builder uses for
  held-out 2/3), so `--stage declared` declares the stage of the answer's edition.
* **Useful hit = the harness's `--useful-rule v4`, unchanged, scored with `--expected-tokens
  current`:** a top-3 suggestion is useful when it is the target's reading (canonical/notation-folded
  equal), or its loose-token Jaccard with the target is at least the row's threshold, or the lemma
  branches of v4 fire. Rank = the first useful slot of the three. No new definition is introduced.
* **Secondary, reported always:** the harness's `exact_rank` (the target's own reading, notation-folded,
  is one of the three suggestions). This is the strict reading of "found edition B" and is what the
  useful rule cannot overstate: v4's token branch accepts any suggestion sharing about a quarter of the
  target's tokens, which for a pair at Jaccard 0.5 to 0.9 with its query is easy once the query is
  matched at all. A change that moves "useful" but not "exact" is reported as such.
* **Baselines:** the harness prints the overlap and BM25 baselines for the same pool. They run on the
  same query text and will be strong here (section 10, circularity); they are reported, not gated on.

## 3. How the query's own row and its near-twins are hidden (leave-one-out)

For every query the builder freezes a column `hidden_row_keys` (space-separated
`source_text_id|source_sentence_id`): the **query's own row** plus every corpus row with loose-token
Jaccard **>= 0.7** with it or with the same notation-folded reading (the audit's twin line and
`eval_guards.twins_of_target`, exhaustive, no postings cap), **minus the target row** even when the
target is itself a twin of the query (pairs live in the Jaccard band 0.5 to 0.9, so about half of them
are). Over the 295 queries 163 hide at least one twin besides the query row (median 2 keys, maximum
82, a BBAW formula).

**What the existing harness does not support.** `_exclude_expected` always removes the *expected* row
and, with `--exclude-twins`, the expected row's twins. For this benchmark that is exactly backwards: it
would delete the answer and leave the query's own row (an exact match of the query text) in the pool,
which is the free-hit leak that made v1 and the first twin-picking benchmarks meaningless. There is no
way to name "also remove these keys" or "do not remove the expected row". Section 6 specifies the
minimal change. **It is not implemented in this commit and nothing was run.**

Hiding is frozen in the file rather than recomputed at evaluation time, so the sealed file is
self-contained and a later corpus change cannot quietly change which rows were hidden. A hidden key
that the corpus no longer has is a no-op.

## 4. Which pairs are eligible

Start from the 300 frozen pairs (`cross_edition_pairs_v1.csv`, sha256 recorded in the build log;
50 per source pair, 600 distinct rows, built for item E and **never used for the reading-suggestion
benchmark**). A pair is dropped, counted under the **first** rule that applies:

1. a row's `(source_text_id, source_sentence_id)` is missing from the corpus;
2. ... or is not unique;
3. a row's transliteration differs from the one frozen in the pair file;
4. a row is in the data-cleanup removal manifest with `decision == removed`;
5. a row is the target of any committed benchmark;
6. a row is a near-twin (Jaccard >= 0.9) of such a target;
7. a row shares a TLA/AES/Ramses `source_text_id` with such a target;
8. a row is a BBAW row within +-20 sentence numbers of such a target (rules 5 to 8 are Experiment 3's
   held-out exclusions, `same_text_exclusions` imported from the competitive builder, not copied);
9. the query side has fewer than 5 loose tokens on the current corpus.

"Any committed benchmark" is discovered, not listed: every `data/benchmarks/*.csv` with both
`expected_source_text_id` and `expected_source_sentence_id` columns (47 files today: the query sets
v1 to v4, v4 drift-corrected, held-out 1, **held-out 2, the sealed held-out 3**, LE-v1, NAME-v1, and
their result/failure files, which repeat the same targets). Only those two id columns are read; no
query text is. Their union is 204 distinct rows, all found in the corpus.

**Cleanup removal list.** The brief named `~/egyptology-runs/data-cleanup-2026-10-26/report/removal_manifest.csv`.
That path does not exist yet (the plan creates it at its step 1.4). The builder reads
`.../build_N/removal_manifest.csv` (candidate N after the exception review: 1,289 lines `removed`, 933
`kept`). The earlier `pre_review/build_N/removal_manifest.csv` marks all 2,222 flagged rows as removed.
**Result: none of the 600 pair rows is among the 1,289 removed rows (so no pair is dropped for it), and
only one is among the 2,222 flagged.** The sealed set does not depend on how step 1.4 ends.

## 5. Sample size

Result of the build, not a target: **300 pairs in, 295 queries out** (>= 100 required; the builder
refuses to write fewer and a smaller usable set would mean the pair file or manifest had changed under
us).

| source pair | pairs | queries | A2B / B2A |
|---|---|---|---|
| AES<->BBAW | 50 | 49 | 25 / 24 |
| AES<->Ramses | 50 | 50 | 25 / 25 |
| AES<->TLA | 50 | 50 | 25 / 25 |
| BBAW<->Ramses | 50 | 47 | 24 / 23 |
| BBAW<->TLA | 50 | 49 | 25 / 24 |
| Ramses<->TLA | 50 | 50 | 25 / 25 |

Exclusions: 5 pairs. `benchmark_target_row` 1 (BBAW<->TLA), `bbaw_window_of_benchmark_target` 4
(AES<->BBAW 1, BBAW<->Ramses 3), every other rule 0. All 295 are kept (no trimming to a round number:
the set is not scarce and trimming would be a free choice).

Why >= 100, and why 295 is comfortable. The unit is the query, the decision is a paired comparison of
two arms on the same queries (top-3 useful, a 0/1 per query). With an *assumed* discordance rate of 10 % (the
two arms disagree on one query in ten; a planning number, not a measured one), the smallest
top-3 difference detectable with 80 % power at alpha 0.05 is about 5 percentage points at n = 295,
about 7 at n = 150 (one direction) and about 9 at n = 100. A set of 20 (v4, held-out 3) detects
nothing below ~20 points, which is why those sets can only gate regressions. Per source pair
(n ~ 50) the instrument resolves only gaps of ~12 points, so source-pair rows are descriptive.

## 6. The harness change this needs (specified, NOT implemented)

Two optional benchmark columns, so a file describes its own semantics (a forgotten flag could not
silently turn this into the wrong measurement) and every existing file runs byte-identically:

* `expected_in_pool` = `1`: do not remove the expected row from the candidate pool
  (`_exclude_expected(..., keep_expected=True)`), and do not add it to the baselines' excluded set.
* `hidden_row_keys`: space-separated `text_id|sentence_id`; their corpus positions (via
  `guard.positions`) are removed from the pool, added to `excluded_positions` for the overlap/BM25
  baselines and `candidate_lemmas_fast`, and **never the expected row** (assert: an `expected_in_pool`
  row whose expected position is hidden is a malformed benchmark, stop).

Sketch, in `main`'s loop: `keep = str(bench_row.get("expected_in_pool", "")).strip() == "1"`;
`hidden = [p for item in str(bench_row.get("hidden_row_keys", "")).split() for p in
guard.positions.get(tuple(item.split("|", 1)), ())]`; the pool is `_exclude_expected(examples_df,
bench_row, extra_positions=twin_positions + hidden, keep_expected=keep)`; baselines'
`excluded_positions = ({} if keep else target_positions) | twin_positions | hidden`. Appended result
columns: `expected_in_pool`, `hidden_rows_removed`; one summary line counting `expected_in_pool`
queries. `--exclude-twins` keeps its meaning, applied to the expected row's twins (never the expected
row), so it still composes. Acceptance tests (written with the change, not here): all existing sets'
result CSVs byte-identical with the new code (v4, held-out 1/2, LE-v1, NAME-v1), a synthetic set where
the query's own row is removed and the answer stays, and the assertion above.

## 7. Pools, seeds, runs

* **Pools, as in Experiment 3 and both reported every time:** **C** (legacy pool) = `--exclude-twins 0`:
  everything except the hidden rows; the answer's other editions that are not twins of the query stay
  (79 of the 295 queries have such a copy left in C). **T** (twin-controlled) = `--exclude-twins 0.7`:
  additionally removes the answer's own near-twins (Jaccard >= 0.7 or folded-identical), so the target
  is the only edition of its sentence in the pool.
* **Other flags:** `--benchmark <the sealed file>` (always passed: the default file is the contaminated
  v1), `--query-path app`, `--useful-rule v4`, `--stage auto`, `--expected-tokens current`. A
  `--stage declared` run is informational (146 of the 295 rows carry a blank stage, as the corpus
  states).
* **Seeds:** one, **20261028**, used only for the direction assignment. The builder has no other
  randomness; the ranker and harness are deterministic. Re-running the builder must reproduce the
  file byte for byte (`--verify` does this in memory, it passed on 2026-10-28).

## 8. Sealing

* The file is `data/benchmarks/competitive_ambiguity_eval_queries_xed_route1_2026-10-28_SEALED.csv`,
  built once by `scripts/build_route1_xed_benchmark.py`. **sha256
  `f2c3b3bddd3bf03cfbe00db9f5bf47746c9234f77264931b3769d94823acd80d`** (also in
  `data/benchmarks/route1_xed_build_log_2026-10-28.txt`, with the hashes of the pair file, the corpus
  and the manifest, and the counts above). The builder refuses to overwrite it.
* While building, only counts were printed. No query or answer text was displayed or inspected; the
  one non-count looked at was how many queries have fewer than five whitespace-separated words as
  typed (39; the loose-token floor of 5 splits hyphenated compounds, so they pass it).
* Nobody runs the harness on this file, opens its rows, or looks at any result until a use has been
  **pre-registered in writing** (section 9) and approved. The build log never lists queries; neither
  will any result summary printed before then.
* No dry run on it either. If the harness change needs a smoke test or a ceiling check, that is done on
  a **separate development set** built from other candidates of the item E band (182,843 distinct
  cross-source pairs in the band; the 300 used rows are excluded), never on this file.
* A mistake in the *file* found after approval (not a bad score) is fixed by building a new
  versioned file and recording the old one as void, never by editing it.

## 9. Use: one final decision, then spent

The sealed file may be opened **once, for one named decision**, whose rule is written in that use's
own pre-registration before opening (as held-out 3 was for Experiment 3 step 4). After that run, in
both pools, it is spent: it may still be re-read for reporting that decision, never to choose a second
thing, tune, or screen a new arm.

Metrics, per pool C and T, pooled over all queries (n = 295 unless the harness change finds more
missing rows):

* **top-3 useful** (count and share), **MRR** of the first useful slot (0 when none in the top 3, as
  the harness computes it), and **rank-1 useful count**;
* secondary: top-3 exact and `exact_rank` of the target's reading; the overlap and BM25 baselines; the
  per-query signed change of the first useful rank between arms; breakdowns by source pair and by
  direction (descriptive).

Default shape of a decision rule, to be confirmed or replaced in the use's own document: **non-regression
plus a strict gain**, in both pools, in the manner of Experiment 3 step 4 (top-3 useful and MRR of the
treatment not below the baseline, rank-1 count not lower, at least one strictly higher, in C and in T).
A single pool passing is not a pass.

## 10. Stated limitations (before any number exists)

* **Circularity.** The pairs were found by loose-token overlap (item E, section 4 of its
  pre-registration), so any method scoring transliteration overlap is tested on a set chosen to
  contain what it measures. Expect the overlap baselines to score near the ceiling. This set cannot
  say how good the suggestions are in absolute terms; it can detect a **regression or a gain in
  notation tolerance** between two arms. If the baseline's top-3 useful is >= 0.95 in both pools, the
  set cannot resolve an improvement and is a non-regression gate only; the use's document says so
  before the run, not after.
* **Easy hits.** v4's token branch is lenient (section 2), hence the always-reported `exact_rank`.
* **Third editions.** Pool C keeps other editions of the answer that are not twins of the query, so a
  "useful" hit may be a different copy of B's sentence; pool T removes them and answers that.
* **Correlated queries.** Pairs from one AES text, or neighbouring BBAW sentences, are not excluded
  from each other (only from the older benchmarks), so the effective n is somewhat below 295.
* **Stage.** `declared` stage is the answer row's; 146 rows have none.
* **Notation of the query is the other edition's, not a human's.** A real "different typist" also
  mistypes; this measures systematic convention differences only.

## 11. Open questions for review

1. Is the removal manifest path (`build_N`, not the planned `report/`) the right one, and should rows
   merely *flagged* but kept (933) also drop their pairs? Today that would change one pair at most.
2. Approve the two-column harness change (section 6), and the hiding line 0.7 (alternative: 0.9, which
   hides fewer copies and lets more through in pool C).
3. One direction per pair (this draft) versus both directions reported separately with pair-level
   clustering in the analysis.
4. Pool T keeps the answer row as the only edition: should pool C hide B's non-twin editions too? (This
   draft says no, so C keeps its "legacy pool" meaning.)
5. Build the development set (section 8) before approving, so the harness change and the ceiling
   question are settled off this file?
6. What single decision is this set reserved for? Without it section 9's rule is a template.
