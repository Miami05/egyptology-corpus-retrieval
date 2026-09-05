# v4 answerability and the v5 useful rule

Roadmap item 1 of the plan for 2026-09-05 ("the two v4 misses, the honest way").

The v4 headline numbers are **not** replaced by anything in this document. v4 on the
130,472-row corpus stays 0.90 top-3 useful / 0.79 MRR (all three stage modes, misses
COMP_007 and COMP_014). Everything below is reported *next to* that number.

## Pre-registered rules (written before any run, 2026-09-05)

Both rules were decided and written down before a single line of measuring code ran.
They are reproduced here verbatim as handed over.

### Rule A — answerability

For each v4 query, exclude the expected row exactly as `_exclude_expected` does, then
apply the harness's own `_useful_reason` to EVERY remaining corpus row (same functions,
same per-query `acceptable_token_overlap_threshold` from the benchmark column — 0.26 or
0.34 — not a flat 0.26; the roadmap's "0.26" was shorthand for that column). A query is
*answerable* iff at least one corpus row is useful under the rule. Unanswerable queries
are flagged and excluded from the answerable-only denominator. Report v4 over all 20 AND
over answerable-only, side by side. Answerability under v5 (Rule B) is computed the same
way with the v5 test.

### Rule B — the v5 useful rule ("lemma-first where lemma ids exist")

Decision: yes, adopt lemma-first as a separate v5, never replacing v4.

- Exact canonical-transliteration match → useful (unchanged).
- If the expected row has lemma ids AND the candidate has lemma ids (via
  `_candidate_lemmas`, non-empty): useful iff (|∩| ≥ 2 and lemma_score ≥ 0.4) or
  (|expected_lemma_ids| ≤ 2 and |∩| ≥ 1). The token branch is NOT applied in this case.
  Thresholds are the existing v4 lemma thresholds; no new constant.
- Otherwise (either side lacks lemma ids): the v4 token rule applies unchanged
  (token_score ≥ threshold), then the v4 lemma branches as before (they will be
  vacuous).

Reasoning to record:

- **FOR** — the loose-form token overlap counts ubiquitous grammatical tokens (m, n, k,
  t, w, r, f, hr, im) that occur in most Pyramid-Text sentences, so a 0.26 Jaccard can be
  accidental, whereas shared lemma ids are what a reader means by "the same words";
  lemma ids are also what item D (proper nouns) will build on.
- **AGAINST** — lemma ids exist only for TLA-derived rows, so Ramses/BBAW-text-only/
  Helsinki rows can only ever pass via the token fallback; `_candidate_lemmas` looks
  lemmas up by canonical reading, which merges homographs; personal-name lemmas never
  recur, so name-heavy sentences become nearly unanswerable under v5.
- **Expected effect** — v5 is stricter on TLA candidates, so v5 ≤ v4 is the likely
  direction; that is acceptable and must be reported as is.

### Pre-registered additions (written 2026-09-05, before the runs they describe)

Added by the lead after the first diagnosis pass, and written here before the
corresponding code ran.

**Variant "v4-drift-corrected".** The frozen v4 file predates `fold_plural_marker`, so
12 of its 20 `expected_key_tokens` cells contain a `pl` token that the current fold
cannot produce (`.pl`/`.PL` → `.w`; the index holds `pl` in 1 row of 130,472). The v4
file is **never edited**. A new file
`data/benchmarks/competitive_ambiguity_eval_queries_v4_driftcorrected.csv` is built by
`scripts/build_v4_driftcorrected_benchmark.py`, which recomputes `expected_key_tokens`
as `sorted(_token_set(loose_reading_form(gold)))` — the builder's own functions,
imported from `scripts/build_competitive_ambiguity_benchmark.py`, applied to the current
corpus row — and recomputes `acceptable_token_overlap_threshold` by the builder's own
rule (`0.34 if len(key_tokens) <= 4 else 0.26`). A threshold may only move **up**; a row
whose recomputed threshold would be lower keeps the frozen value and is reported. Every
other column is copied verbatim. v4 and v4-drift-corrected are always reported side by
side, labelled, and the drift-corrected number never replaces the v4 number. Note the
direction of the correction: removing the phantom `pl` **shrinks** the expected token
set, and a smaller expected set can only *raise* a candidate's Jaccard against it (the
same intersection over a smaller union), so the drift-corrected variant is strictly
**more permissive** than v4 and never stricter — which makes its identical score a
stronger null result than a neutral re-measurement, because the variant was given every
chance to score higher on every query and scored exactly the same.

**Harness `--query-path app|legacy`.** The harness does not parse a query the way the
app does. `app/ui/whyptology_app.py` retrieves through stage resources that always carry
a `SearchIndex` (so `parse_query` sees the corpus vocabulary) and then hands
`suggest_top_readings` the *interpreted reading* (`searched.reading or query`). The
harness passes `index=None` whenever no stage resolves — which is every query in
`--stage none`, and any query whose stage inference returns `None` in `auto` — and
always hands `suggest_top_readings` the **raw** query string. `app` mirrors the app on
both counts; `legacy` is the harness's current behaviour and must reproduce today's
0.90 exactly. Both are reported. **From 2026-09-05 on, `app` is the harness default**
— an evaluation should measure the path the app actually takes — and `legacy` is kept
so that every historical number in this repository can be reproduced exactly by passing
`--query-path legacy`. The two are shown side by side in every stage mode below; where
they agree, the default costs nothing.

**Standalone `pl` in a query (candidate app-side fix, not yet applied).** Eight v4 query
inputs (COMP_001, 002, 011, 013, 014, 017, 019, 022) contain a standalone `pl` token.
The corpus fold turns `.pl` into `.w` before the dots are dropped, but a query's
free-standing `pl` has no dot in front of it, so `fold_plural_marker` does not see a
marker and the token survives as `pl` — which matches 1 corpus row. The fix under
consideration is to fold a standalone `pl`/`PL` **token** to `w` in the query fold,
which is exactly what the corpus fold already does for `.pl`, introduces no new
constant, and is symmetric with the corpus side. Expected effect, written before
running: it can only help queries that contain a standalone `pl` (8 of 20 v4 rows, 2 of
6 tokens in COMP_014) and cannot change any query that does not; it may also change the
expert paste results, which is why the paste gate is part of the acceptance criteria.
It is applied only if the held-out validation set and the paste gate both hold.

## What was run

- `scripts/compute_v4_answerability.py --useful-rule v4` → `data/benchmarks/competitive_ambiguity_eval_answerability_v4.csv`
- `scripts/compute_v4_answerability.py --useful-rule v5` → `data/benchmarks/competitive_ambiguity_eval_answerability_v5.csv`
- `scripts/run_competitive_ambiguity_eval.py --benchmark …_v4.csv --useful-rule {v4,v5} --stage {none,auto,declared}`

The answerability script imports the harness's own `useful_decision` rather than
re-implementing it, and precomputes the two expensive pieces (`loose_reading_form`
token set per distinct reading; canonical reading → union of lemma ids) once for the
whole corpus. Its `--verify 200` check re-ran the unrefactored `_useful_reason` on 200
random rows for both rules and found **no disagreement**. One full scan is ~100 s for
20 queries × 130,472 rows.

Scripts added or changed:

- `scripts/compute_v4_answerability.py` (new) — Rule A.
- `scripts/build_v4_driftcorrected_benchmark.py` (new) — the drift-corrected variant.
- `scripts/run_competitive_ambiguity_eval.py` — `useful_decision` split out of
  `_useful_reason` so it can be applied 2.6 million times without re-scanning the
  corpus; new `--useful-rule v4|v5` and `--query-path app|legacy`.
- `scripts/build_competitive_ambiguity_benchmark.py` — new `--exclude-benchmark`,
  `--id-prefix`, `--exhaustive-twins`, and the `exhaustive_best_twin_overlap` function.
- `scripts/inspect_suggestion_boundary.py` (new, Experiment 1) — read-only probe that
  reproduces the harness pipeline with `top_n` raised, so the rank of the first
  *accepted* candidate and its margin behind rank 3 can be read off directly.
- `app/services/suggestions.py` (Experiment 1) — `SUGGESTION_PRESETS`,
  `resolve_suggestion_preset`, the `WHYPTOLOGY_SUGGESTION_PRESET` environment variable,
  and the non-default `carry_forward_idf` switch. With the variable unset the module is
  behaviour-identical to before, which `tests/test_phase2_ranking.py` now pins.

Scoring under `--useful-rule v4` is unchanged: the same code in the same order and the
same CSV columns, verified by reproducing 0.90 / 0.7917 exactly. The printed summary
gains a `query_path` line always and a `useful_rule` line only for a non-v4 rule, so the
*numbers* are byte-identical while the summary block is one line longer than before —
recorded here rather than claimed away.

## Rule A — answerability results

Every one of the 20 v4 queries is **answerable under both rules**. There is no
unanswerable query to flag, so the answerable-only denominator is the same 20 as the
all-queries denominator, and the two columns of the report table are identical. That is
a null result for Rule A, and it is reported as one.

A note on the threshold: the roadmap said "0.26" as shorthand for the per-query
`acceptable_token_overlap_threshold` column. The rule was applied per query from that
column as written — and it turns out the column is a constant 0.26 for all 20 v4 rows,
so the shorthand happened to be exact. No 0.34 row exists in v4.

| id | thr | best token score | best lemma (score, \|∩\|) | useful rows v4 | useful rows v5 | answerable v4 | answerable v5 |
|---|---|---|---|---|---|---|---|
| COMP_001 | 0.26 | 0.833 | 1.00, 3 | 5939 | 4939 | yes | yes |
| COMP_002 | 0.26 | 0.833 | 1.00, 3 | 3943 | 3307 | yes | yes |
| COMP_003 | 0.26 | 0.588 | 1.00, 2 | 8196 | 6406 | yes | yes |
| COMP_004 | 0.26 | 1.000 | 1.00, 4 | 5362 | 4194 | yes | yes |
| COMP_005 | 0.26 | 0.619 | 1.00, 4 | 4233 | 3449 | yes | yes |
| COMP_007 | 0.26 | 0.440 | 1.00, 4 | 4586 | 3832 | yes | yes |
| COMP_008 | 0.26 | 0.500 | 1.00, 4 | 4624 | 3550 | yes | yes |
| COMP_010 | 0.26 | 0.733 | 1.00, 2 | 5480 | 4045 | yes | yes |
| COMP_011 | 0.26 | 0.522 | 1.00, 1 | 3807 | 3145 | yes | yes |
| COMP_012 | 0.26 | 0.571 | 1.00, 1 | 5061 | 3904 | yes | yes |
| COMP_013 | 0.26 | 0.478 | 0.00, 0 | 2794 | 2794 | yes | yes |
| COMP_014 | 0.26 | 0.476 | 1.00, 1 | 4346 | 3421 | yes | yes |
| COMP_016 | 0.26 | 0.588 | 1.00, 3 | 8259 | 6162 | yes | yes |
| COMP_017 | 0.26 | 0.955 | 1.00, 4 | 4517 | 3522 | yes | yes |
| COMP_018 | 0.26 | 1.000 | 1.00, 10 | 3978 | 3171 | yes | yes |
| COMP_019 | 0.26 | 0.550 | 0.00, 0 | 4930 | 4930 | yes | yes |
| COMP_020 | 0.26 | 0.500 | 1.00, 2 | 3572 | 2889 | yes | yes |
| COMP_021 | 0.26 | 0.450 | 1.00, 2 | 4698 | 3535 | yes | yes |
| COMP_022 | 0.26 | 0.708 | 1.00, 3 | 2561 | 2119 | yes | yes |
| COMP_023 | 0.26 | 0.600 | 1.00, 1 | 5407 | 4295 | yes | yes |

The number that matters here is not the yes/no column, it is the **useful-row count**.
The median v4 query has **4,605 useful rows out of 130,471** — 3.5% of the corpus is
"a useful answer" to any given query. v5 removes 18.6% of them on average (median
3,542). COMP_013 and COMP_019 are unchanged because their `expected_lemma_ids` cell is
empty, so v5's lemma-first branch never engages and it falls back to v4 verbatim, exactly
as Rule B specifies.

The two rows the lead named independently were re-checked through the harness's own
`_useful_reason` and both confirm: `TLA_EARLIER_6267`/`S6267` for COMP_007 at token
0.3182, and `TLA_LATE_783`/`S783` for COMP_014 at token 0.2632, both ≥ the 0.26
threshold, which was not lowered anywhere in this work. Under v5 neither of those two
rows is useful (lemma_score 0.2222 and 0.1429, both under 0.4) — v5 is stricter, as
Rule B predicted, and it is stricter precisely on the rows this diagnosis is about.

That density is the real finding of Rule A, and it cuts against the benchmark rather
than for it: with ~4,600 rows counting as a hit, the top-3 useful-family metric is a
weak instrument. Neither COMP_007 nor COMP_014 is a coverage failure. Both are ranking
failures — but see the miss write-ups for what "ranking failure" actually means here.

## The two misses — pipeline trace

The decisive measurement. For each miss the lead named a corpus row that clears the
token threshold with the target excluded. Both were confirmed with the harness's own
`_useful_reason`, and then traced through every stage of the current pipeline. `k`, the
retrieval pool handed to the suggestion layer, is 50 in every case
(`k=min(50, len(retrieval_frame))`).

### COMP_007

Query `skhak i kh i tt im fkh djd`, threshold 0.26. Expected
`sẖꜣk =ꞽ ẖ.t =ꞽ ḥr n.tt ꞽm =s m fḫ n ḏd nb ḥr-n.tt r =f wḥm.w ḏdd.t.pl`
(`AES_F8FA2864100C` / `SF8FA2864100C`).

Named row `TLA_EARLIER_6267` / `S6267` = `ꞽ:fḫ n =k s(ꞽ) zꜣ =k ḥr(.w) ꜥnḫ =k ꞽm =s`.

- **Rule A (v4): useful — yes.** token 0.3182 ≥ 0.26, shared `fkh, hr, i, im, n, s, w`.
  (Rule B (v5): **not** useful — lemma_score 0.2222 < 0.4.)
- **Rule A over the whole corpus: 4,586 useful rows.** Not a coverage gap.

| stage mode | stage used | query path | retrieval rank | rows scored | in top-50 pool | suggestion rank | final top-3 |
|---|---|---|---|---|---|---|---|
| auto | None | legacy | **7** | 29,047 | yes | **6** | no |
| auto | None | app | **7** | 29,047 | yes | **6** | no |
| none | None | legacy | 7 | 29,047 | yes | 6 | no |
| none | None | app | 7 | 29,047 | yes | 6 | no |
| declared | Late Egyptian | legacy | 9 | 29,047 | yes | 7 | no |
| declared | Late Egyptian | app | 9 | 29,047 | yes | 7 | no |

**Finding: retrieval is not the problem — the suggestion re-rank is.** The useful row is
7th out of 29,047 scored rows, comfortably inside the pool of 50 that reaches
`suggest_top_readings`. That layer then reorders and puts it 6th, behind
`ꜣḫ =ꞽ ꞽm =f`, `n sfḫ =ꞽ ꞽm =f ḏ.t`, `sḫm =ꞽ ꞽm =f ḏ.t`, none of which is useful. The
demotion is 7 → 6 in position but 3rd-place → 6th-place in what is reported.

(The precise boundary — the first *accepted* candidate sits at rank 4, 0.005 behind rank
3 — is in "Where the misses are actually lost" below; that is the primary finding. What
follows is a second, independent illustration of the same weighting problem, further
down the list.)

The same pattern shows in the corpus's only other attestation of the target's rarest
word, sẖꜣk: `dwꜣ =k r sẖꜣk =st m ḥbs.pl` (`AES_200F682C90DE` / `S200F682C90DE`). It has
the *highest* IDF-weighted token overlap of any row considered — 0.211 against
0.128–0.138 for the three rows that were returned — and still loses on `final_score`
(0.3036 vs 0.3694) because `fuzzy_score`, a whole-string `fuzz.ratio` weighted 0.35,
rewards the rivals for looking like the query character by character:

| row | fuzzy 0.35 | tfidf 0.18 | overlap 0.10 | idf_overlap 0.40 | final |
|---|---|---|---|---|---|
| `dwꜣ =k r sẖꜣk =st m ḥbs.pl` | 0.490 | 0.272 | 0.077 | **0.211** | 0.3036 |
| `sḫꜣ{t}.n =ꞽ smḫ.tn =ꞽ ꞽm =f` | 0.667 | 0.421 | 0.200 | 0.128 | **0.3694** |
| `sḫm =ꞽ ꞽm =f ḏ.t` | 0.634 | 0.447 | 0.200 | 0.138 | 0.3666 |
| `n sfḫ =ꞽ ꞽm =f ḏ.t` | 0.605 | 0.500 | 0.182 | 0.135 | 0.3627 |

That row would not have scored as a hit anyway (token 0.174, lemma_score 0.286), which
is a separate problem with the metric rather than with the ranker, and it is the
strongest single argument for Rule B: on COMP_007 the v4 rule certifies 4,586 rows as
useful — the first of them `(w)sꞽr wnꞽs m n =k ꞽr.t-ḥr.w ꞽꜥb n =k s(ꞽ) ꞽr rʾ =k`,
useful on `hr, m, n, r, s, t, w`, seven grammatical particles — while refusing the one
row that shares the sentence's rare content word.

### COMP_014

Query `in pl asha ta pl nb hw`, threshold 0.26. Expected
`ꞽn.w.pl =f ꜥšꜣ(.w) m tꜣ.pl nb.w ḥw.tꞽ.pl ḥr ꞽri̯.t mri̯.t.n =f`.

Named row `TLA_LATE_783` / `S783` = `ꞽw nꜣ pn.w.PL ꜥšꜣ m tꜣ sḫ.t`.

- **Rule A (v4): useful — yes.** token 0.2632 ≥ 0.26, shared `asha, m, t, ta, w`.
  (Rule B (v5): **not** useful — lemma_score 0.1429.)
- **Rule A over the whole corpus: 4,346 useful rows.**

| stage mode | stage used | query path | retrieval rank | rows scored | in top-50 pool | suggestion rank | final top-3 |
|---|---|---|---|---|---|---|---|
| auto | None | legacy | **4** | 23,353 | yes | **5** | no |
| auto | None | app | **4** | 23,353 | yes | **5** | no |
| none | None | legacy | 4 | 23,353 | yes | 5 | no |
| none | None | app | 4 | 23,353 | yes | 5 | no |
| declared | Earlier Egyptian | legacy | 4 | 23,353 | yes | 5 | no |
| declared | Earlier Egyptian | app | 4 | 23,353 | yes | 5 | no |

**Same finding, and sharper: retrieval ranks the useful row 4th out of 23,353, and the
suggestion re-rank pushes it to 5th.** What the re-rank promotes above it is
`nꜣ pnw ꜥšꜣ m tꜣ sḫ.t` — *the same sentence, in a spelling without the morpheme dots.*
That row is returned 3rd and scores token overlap 0.2222; its dotted twin, ranked 5th,
scores 0.2632. The pass/fail of COMP_014 turns on 0.041 of Jaccard between two readings
of one sentence, decided entirely by whether the corpus editor wrote `pn.w.PL` or `pnw`:
the dotted spelling folds to the extra tokens `w` and `iw`, which is what carries it over
0.26. **This query does not measure ranking quality at that resolution.**

### One sentence on the roadmap's `n.` / `=` hypothesis

Checked and refuted as the primary cause: the stored query lacks `n.` and `=` by
construction of the benchmark builder (which generates queries from
`loose_reading_form`, dropping the marks before the file is written), and the current
fold preserves the query key intact — `parse_query('skhak i kh i tt im fkh djd')` yields
`search_key='skhak i kh i tt im fkh djd'` and `reading='sḫak i ḫ i tt im fḫ ḏd'`, with ḏ
and ṯ read back correctly by the `ASCII_DIGRAPHS` branch rather than folded away
(`search_fold` alone would give `…fkh did`, and `did` is in 0 corpus rows, but the app
never takes that path).

### Candidate fixes — written down, deliberately NOT applied

Both misses now have a proven mechanism. Neither has a validated fix, and the standing
rule is that an unvalidated fix is worse than a proven diagnosis with none. Recording
the two candidates, with their expected effects, so a later session can test them
against the held-out set rather than against v4.

**Candidate 1 has since been tested** — later the same day, under the pre-registered
protocol in "Experiment 1" at the end of this document. The outcome was **no fix
validated**: the selected configuration moves COMP_007's accepted candidate from rank 4
to rank 1 and rescues two held-out queries, but fails the acceptance criteria (held-out
MRR falls, and v4 loses two queries it currently gets right), so nothing was applied. The
paragraphs below are left exactly as first written; the results are not folded back into
them.

**Candidate 1 — the top-3 boundary is decided against the evaluator's own measure.** Both
misses put an accepted candidate at suggestion rank 4, five and seven thousandths of
confidence behind rank 3, and in both cases that rank-4 candidate has the *highest*
token overlap of the top-4 window (0.273 and 0.333, against 0.150–0.238 and
0.188–0.222 for the three rows above it; further down the list, rank 6 in COMP_007 —
the TLA row S6267 — carries 0.318). Nothing is lost in retrieval and nothing is
lost at the top-50 cutoff. The general mechanism is `SuggestionWeights`: the layer
recomputes its own similarity (`translit_overlap` 0.20, `char_similarity` 0.16,
`exact_or_near` 0.12, `reading_similarity` 0.08) on top of `relative_score` 0.24, so more
than half the mass re-litigates a question retrieval already answered with an
IDF-weighted signal the re-rank does not carry forward; its own docstring warns of
exactly this ("when this layer recomputes too much of its own similarity it can push a
well-retrieved parallel out of the top 3"). The change to test is how `combine_scores`
and the re-rank weigh IDF overlap against plain token overlap and whole-string fuzzy
similarity — **not a number picked because it makes COMP_007 pass**, which is the move
the standing rules forbid. It must be swept on the held-out set, confirmed at 8/8 on the
paste gate, and only then measured on v4, with the confidence margins for both misses
reported before and after.

Two reasons it was not attempted here. First, a margin of 0.005 on a sample of two is
not evidence that any particular reweighting is right; it is evidence that the metric
has no resolution at that scale. Second, the ordering that produces the miss is not
obviously wrong to a reader: at COMP_007 rank 1 `ꜣḫ =ꞽ ꞽm =f` is a perfectly reasonable
suggestion for a query dominated by `i` and `im`. What the trace establishes is *where*
the misses happen, precisely; what it does not establish is that moving them is an
improvement rather than a trade.

**Candidate 2 — a standalone `pl` token in a query. Judged NOT symmetric; not applied.**
The proposal was to fold a free-standing `pl`/`PL` token to `w` in the query fold,
mirroring what the corpus fold does for `.pl`. It is not a mirror. `PLURAL_MARKER_RE` is
`(?:\.w)?\.pl(?![^\W\d_])` — it requires the leading dot, so the corpus fold does *not*
turn a bare `pl` into `w` anywhere. More decisively, there is no separate query fold to
change: `search_fold` is the one function both the query and the corpus index go
through, by design and with a comment saying so. Adding the rule would rewrite the index
keys of every corpus row containing a standalone `pl` as well as the queries, and adding
it on the query side only would introduce precisely the asymmetry the shared function
exists to prevent. The `pl` drift is therefore handled where it belongs — in the
drift-corrected benchmark variant, which recomputes `expected_key_tokens` under the
current fold — and the eight affected query inputs are left as the frozen artefact they
are.

### The held-out validation set (built before any fix; first used by Experiment 1)

`data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv`, 20 queries,
`HOLD_001`–`HOLD_027`. Built with the project's own builder via a new
`--exclude-benchmark` / `--id-prefix` pair rather than a parallel implementation, so the
selection rule, the twin guard and the query generation are bit-for-bit the ones that
produced v4.

The lead asked for "a different random seed". The builder has none — it is fully
deterministic, ranking candidates by how many genuine rivals they have — so that
instruction could not be followed as written. Disjointness was obtained instead by
exclusion: v4's 20 expected rows, **and the 2 corpus rows within the builder's own
duplicate threshold (overlap ≥ 0.9) of one of them**, were removed from candidacy before
selection, using the exhaustive twin test (`--exhaustive-twins`, below) on both sides.
130,472 rows considered → 112,654 eligible (22 excluded here, 1,116 too short, 3,021
without distractors, 13,659 with a near-identical twin). Verified: 0 of the 20 held-out
expected rows appears among v4's. Threshold is 0.26 for all 20; the query types split 9
simplified / 9 partial / 2 reading-order; three rows are Demotic, two Late Egyptian and
one Earlier Egyptian, so the set exercises the stages that item A opened up.

The exhaustive twin guard found one near-duplicate that the capped scan had missed
(13,659 vs 13,658 corpus-wide), but that row was not among the 20 selected either way:
the capped and exhaustive builds produced the **same** held-out set and the same
baseline. Recorded because it is the honest result, not because it mattered here — on v4
the same cap did hide two twins, which is the case that matters.

Its baseline on today's code is recorded in the results table below. Nothing has been
tuned against it, which is the point: it exists so that a future ranking change can be
judged on evidence it has never seen. Experiment 1 (below) is its first use, and it was
used as designed — three configurations named in advance, **selected** on this set, not
swept against it; no constant was moved to improve a held-out score.

### The query path made no difference

`--query-path app` — vocabulary-aware parsing supplied to retrieval, and the interpreted
reading rather than the raw string handed to `suggest_top_readings` — changed **nothing**
for either miss: identical retrieval ranks, identical suggestion ranks, identical top-3,
in all three stage modes. For COMP_014 the interpreted reading is byte-identical to the
raw query. This is a null result and is reported as one; the whole-benchmark effect is in
the results table below.

## Results

All numbers below come from runs made on 2026-09-05 against the working tree at
`2b13fed` **plus the uncommitted changes described in this document** — every run's
`--label` records that. The previously committed
`competitive_ambiguity_eval_results.csv` / `_failures.csv` are stale (a 78k, pre-stage
corpus, listing COMP_008 as the failure); they were not read and not overwritten. Every
run here wrote to its own new file, named
`data/benchmarks/ceval_<benchmark>_<rule>_<path>_<stage>_results.csv`.

### Main table

`--stage auto` unless stated. "18 non-twin" excludes COMP_004 and COMP_017, whose
targets have an exact edition twin in the corpus (see the twin disclosure below).

| benchmark | rule | query path | stage | top-1 useful | top-3 useful | MRR | misses | 18 non-twin: top-1 / top-3 / MRR |
|---|---|---|---|---|---|---|---|---|
| v4 | v4 | legacy | auto | 0.70 | **0.90** | **0.7917** | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4 | v4 | app | auto | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4 | v4 | legacy | none | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4 | v4 | app | none | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4 | v4 | legacy | declared | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4 | v4 | app | declared | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4-drift-corrected | v4 | legacy | auto | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4-drift-corrected | v4 | app | auto | 0.70 | 0.90 | 0.7917 | COMP_007, COMP_014 | 0.7222 / 0.8889 / 0.7963 |
| v4 | **v5** | legacy | auto | 0.65 | **0.80** | **0.7167** | COMP_007, COMP_010, COMP_014, COMP_021 | 0.6667 / 0.7778 / 0.7130 |
| v4 | v5 | app | auto | 0.65 | 0.80 | 0.7167 | COMP_007, COMP_010, COMP_014, COMP_021 | 0.6667 / 0.7778 / 0.7130 |
| v4 | v5 | legacy | none | 0.65 | 0.80 | 0.7167 | COMP_007, COMP_010, COMP_014, COMP_021 | 0.6667 / 0.7778 / 0.7130 |
| v4 | v5 | legacy | declared | 0.65 | 0.80 | 0.7167 | COMP_007, COMP_010, COMP_014, COMP_021 | 0.6667 / 0.7778 / 0.7130 |
| held-out 2026-09-05 | v4 | legacy | auto | 0.60 | 0.75 | 0.6667 | HOLD_001, 002, 005, 014, 026 | (no twin exclusions) |
| held-out 2026-09-05 | v4 | app | auto | 0.60 | 0.75 | 0.6667 | HOLD_001, 002, 005, 014, 026 | (no twin exclusions) |

Answerable-only columns are omitted because they would be identical: **all 20 v4 queries
are answerable under both rules**, so the answerable-only denominator is 20 and every
answerable-only figure equals its all-queries figure.

Readings of that table:

1. **v4 reproduces exactly: 0.90 / MRR 0.7917, misses COMP_007 and COMP_014.** The
   refactor that made `useful_decision` importable and added the two flags is
   behaviour-preserving.
2. **v5 is lower, as Rule B predicted: 0.80 / MRR 0.7167**, and identically so in all
   three stage modes. It costs two queries (COMP_010 and COMP_021 flip from hit to
   miss) and rescues none. This is the pre-registered outcome and it stands as reported;
   v5 does not replace v4 anywhere.
3. **The drift correction changed nothing** — same accuracy, same MRR, same two misses,
   in both query paths. The phantom `pl` is real (12 of 20 rows carried it) but it was
   not what decided any query. A null result, reported as one.
4. **The query path changed nothing, in all three stage modes.** The `none` and
   `declared` rows were added on 2026-09-05 so the equivalence is shown mode by mode
   rather than inferred from `auto`: `--query-path app` and `--query-path legacy` give
   **0 of 20 differing queries** in `none` and **0 of 20** in `declared` — not merely the
   same accuracy, but the same three suggestion strings, in the same order, for every
   query (compared cell by cell on the `suggestions` column of the two results files).
   Together with `auto`, that is **0 of 60**. Making `app` the default therefore costs
   nothing measurable, and `legacy` still reproduces every historical number exactly. The
   harness's parse path was never the cause of anything here; the flag is kept as
   reproducibility work, not as a fix.
5. **The held-out set is harder: 0.75 / MRR 0.6667.** That is the honest baseline for
   any future ranking change, and it is a reminder that 0.90 on v4 is partly a property
   of v4.

### Twin disclosure — v4's 0.90 includes two guaranteed hits

An exhaustive twin scan of the 20 v4 targets (prefix-filtered, no postings cap) finds
two whose sentence exists a second time in the corpus at Jaccard **1.0** on loose tokens:

| id | target | edition twin | overlap |
|---|---|---|---|
| COMP_004 | `ꞽri̯.y =ꞽ ḫr.t.ṱ =k m n.tꞽ nb{.t} n.tꞽ kꜣ.wt ḥr wḫꜣḫ =f` | `bbaw_egyptian_2018` / `B023380` | 1.0000 |
| COMP_017 | `ptrꞽ tw=ꞽ ḥr ḏd n =k pꜣ sḫr.pl n zẖꜣ.w m pꜣy =f rs.w{t} …` | `bbaw_egyptian_2018` / `B005172` | 1.0000 |

The builder's twin guard exists precisely to keep such rows out, but `rivals_for` skips
any token whose postings list exceeds 4,000 entries
(`scripts/build_competitive_ambiguity_benchmark.py`), and a sentence built entirely from
frequent tokens has every one of its postings lists skipped — so the twin is invisible
to it. Excluding the target still leaves its duplicate in the pool, so these two hits are
free. **v4 over the 18 rows without an edition twin is 0.8889 top-3 useful / MRR 0.7963
(v5: 0.7778 / 0.7130).** Both figures are given above; neither replaces the headline.

The held-out set was therefore built with a new `--exhaustive-twins` flag, which uses
`exhaustive_best_twin_overlap` — prefix filtering with no cap, exact by the pigeonhole
bound that a Jaccard-0.9 twin must share one of the target's ⌊0.1·|A|⌋+1 rarest tokens.
The default stays capped so the frozen benchmarks remain reproducible.

### Where the misses are actually lost: the top-3 boundary

Confidence scores as displayed, `--stage auto` (which resolved to no stage for both):

**COMP_007** — the first *useful* candidate is rank **4**, 0.005 behind rank 3:

| rank | confidence | useful | token | lemma | source | reading |
|---|---|---|---|---|---|---|
| 1 | 0.5350 | no | 0.150 | 0.000 | BBAW B029526 | `ꜣḫ =ꞽ ꞽm =f` |
| 2 | 0.5330 | no | 0.238 | 0.000 | BBAW B035161 | `n sfḫ =ꞽ ꞽm =f ḏ.t` |
| 3 | 0.5300 | no | 0.190 | 0.000 | BBAW B031377 | `sḫm =ꞽ ꞽm =f ḏ.t` |
| **4** | **0.5250** | **yes** | 0.273 | 0.000 | BBAW B012327 | `m fḫ ꞽb =k ḥr ḏd.tꞽ =ꞽ n =k` |
| 5 | 0.5250 | no | 0.227 | 0.000 | BBAW B032329 | `sḫꜣ{t}.n =ꞽ smḫ.tn =ꞽ ꞽm =f` |
| **6** | **0.5250** | **yes** | 0.318 | 0.222 | TLA_EARLIER_6267 / S6267 | `ꞽ:fḫ n =k s(ꞽ) zꜣ =k ḥr(.w) ꜥnḫ =k ꞽm =s` |

**COMP_014** — the first useful candidate is rank **4**, 0.007 behind rank 3:

| rank | confidence | useful | token | lemma | source | reading |
|---|---|---|---|---|---|---|
| 1 | 0.5860 | no | 0.200 | 0.000 | Ramses S_train_06349 | `ḥw tꜣ nb` |
| 2 | 0.4840 | no | 0.188 | 0.000 | Ramses S_train_04178 | `ḥw ꜥšꜣ rmṯ.w` |
| 3 | 0.4820 | no | 0.222 | 0.167 | TLA_LATE_1324 / S1324 | `nꜣ pnw ꜥšꜣ m tꜣ sḫ.t` |
| **4** | **0.4750** | **yes** | 0.333 | 0.000 | Ramses S_train_02195 | `ꞽn m tꜣ ḥw.t` |
| **5** | **0.4750** | **yes** | 0.263 | 0.143 | TLA_LATE_783 / S783 | `ꞽw nꜣ pn.w.PL ꜥšꜣ m tꜣ sḫ.t` |

This is the sharpest statement of the failure mode, and it matches an independent
read-only diagnosis line for line (ranks 7→6 and 4→5 for the two named rows, first
passing suggestion at rank 4 in both, 0.525 against 0.535/0.533/0.530, and 0.333 for the
Ramses row):

**Nothing is lost in retrieval, and nothing is lost at the top-50 cutoff. Both misses are
lost at the top-3 boundary, by five and seven thousandths of confidence, to candidates
the evaluator does not accept.** In COMP_007 the accepted candidate at rank 4 also has
the *highest* token overlap of the six (0.273 vs 0.150–0.238 above it); in COMP_014 the
accepted candidate at rank 4 has 0.333 against 0.188–0.222 above it. In both cases the
ranker's ordering is anti-correlated with the evaluator's own token measure over the top
handful — which is the finding, and which is why no fix is applied here on a sample of
two.

### Lemma coverage, and what it means for Rule B

| source | rows with lemma ids | rows |
|---|---|---|
| TLA | 28,369 | 28,369 |
| AES | 9,822 | 9,823 |
| BBAW | 0 | 52,216 |
| Ramses | 0 | 40,064 |
| **total** | **38,191** | **130,472** |

**70.7% of the corpus has no lemma ids at all.** Under v5 those rows fall back to the v4
token rule by construction, so v5 changes the judgement only on TLA/AES candidates — and
the tables above show exactly that: in COMP_007 five of the six boundary candidates are
BBAW or Ramses rows with lemma 0.000, so v5 judges them by the same token rule v4 used.
Two further cautions on the lemma machinery: `_candidate_lemmas` unions lemma ids across
**every** corpus row sharing a candidate's canonical reading, not just the retrieved row,
so homographs are merged; and personal-name lemmas essentially never recur, which makes
name-heavy sentences close to unanswerable under a lemma-first rule. Both were listed in
Rule B's AGAINST column before the runs, and both hold.

### Gates

| gate | result |
|---|---|
| `pytest tests -q` | **429 passed**, 24 warnings, 500.54s |
| `scripts/run_expert_paste_eval.py --stage auto` | **8/8** (temp `--results` path) |

No app code was changed, so neither gate is a before/after comparison — they confirm the
harness and builder changes broke nothing.

**Reading the suite count, and a caveat about running it under load.** The suite is now
**430 tests** (429 above plus one loader test the lead added). The AppTest cases in
`tests/test_frontend_smoke.py` run the Streamlit app in-process with a **240 s timeout**,
which is a wall-clock budget, not a work budget: on a machine already busy they can fail
purely from CPU contention. An independent verifier running four evaluations concurrently
saw **2 of those AppTest cases time out**, and all **19** tests in that file passed on an
idle machine minutes later. A `test_frontend_smoke.py` timeout under load is therefore not
evidence of a regression — re-run the suite on an idle machine before treating one as a
failure. (After Experiment 1 the shared working tree — which by then also carried item
4's St Andrews and sign-function importers — ran **465 passed** in 391 s with no
failures and no timeouts.)

## Experiment 1 — re-rank carries forward the retrieval signal (2026-09-05, pre-registered)

Everything from here to "Results of Experiment 1" was written **before any configuration
was run**. It follows Candidate 1 above, and it obeys the standing rule: no constant is
chosen by looking at v4.

### Mechanism hypothesis

`SuggestionWeights` spends `relative_score` **0.24** — the only term that carries
retrieval's tuned, IDF-weighted verdict — against `translit_overlap` 0.20 +
`char_similarity` 0.16 + `exact_or_near` 0.12 + `reading_similarity` 0.08 = **0.56** of
the mass on similarity this layer **re-computes from scratch**, in plain unweighted form
(token Jaccard, character n-grams, whole-string near-equality). Plain overlap gives `m`,
`n`, `k`, `t`, `w` the same say as a sentence's rare content word; retrieval already
answered that question better, with `idf_overlap_score`, and the re-rank throws the
answer away. The layer's own docstring warns of exactly this ("when this layer recomputes
too much of its own similarity it can push a well-retrieved parallel out of the top 3").

The hypothesis under test: **a boundary miss occurs because the re-rank's own
recomputation outweighs the retrieval signal, so carrying the retrieval signal forward —
or giving it more of the mass — lifts evaluator-accepted parallels into the top 3 without
hurting anything else.** If the hypothesis is wrong, the configurations will fail to beat
the held-out baseline and nothing is applied.

### The three configurations (structural choices, not a swept grid)

Implemented as named presets in `app/services/suggestions.py` (`SUGGESTION_PRESETS`),
selected by the environment variable `WHYPTOLOGY_SUGGESTION_PRESET`, read once at import.
Unset — which is every ordinary run, the app included — means today's behaviour
byte-identical; an unknown name raises rather than silently falling back to the baseline.
No retrieval or scoring code is touched by any of them.

- **CFG-A — carry forward.** The `translit_overlap` signal is no longer recomputed: its
  value is **read** from the `idf_overlap_score` column retrieval already produced for
  the candidate's rows (the group maximum, mirroring how `reading_similarity` takes the
  group maximum). All weights unchanged. Recorded before running: the two quantities are
  not scale-matched — an IDF-weighted Tversky overlap sits lower than plain Jaccard on
  the same pair (in the COMP_007 table above, 0.128–0.211 against token 0.150–0.318) — so
  this is a change of *what the slot carries*, and its effect on the ordering, not a
  like-for-like substitution.
- **CFG-B — redistribute.** `relative_score` absorbs `char_similarity`'s mass:
  0.24 + 0.16 = **0.40**, `char_similarity` **0**, everything else unchanged. No new
  number is introduced — 0.40 is the sum of two weights that already exist. (The
  character-n-gram *value* is still computed, because `exact_or_near` uses its 0.82
  threshold; only its weight goes to zero.)
- **CFG-C — both A and B.**

All three are implementable as described; none had to be dropped.

### Selection rule (written before running)

1. The configuration is chosen on the **held-out set only**
   (`competitive_ambiguity_eval_queries_holdout_2026-09-05.csv`, `--stage auto`,
   `--query-path app`): highest **top-3 useful-family accuracy**, tie-break **MRR**.
2. It must hold the expert paste gate at **8/8 in auto**.
3. If no configuration beats the held-out baseline **0.75 / MRR 0.6667** while holding
   the paste gate, the result is **"no fix validated"** and nothing is applied. That is
   an acceptable outcome and will be reported as the finding.
4. **v4 plays no part in selection.** It is measured **once, after** selection, and
   reported for **all** configurations — including the ones not selected — so that no
   configuration can have been picked for its v4 score.
5. A selected configuration becomes the default only if **all** of the lead's acceptance
   criteria hold: held-out not worse (top-3 ≥ 0.75 **and** MRR ≥ 0.6667), paste **8/8**,
   and v4 **loses no query it currently gets right**. Otherwise the default is left
   untouched and the configuration is recorded as measured but not adopted.

### Secondary readouts, pre-stated

- The confidence margin between the first *accepted* candidate and rank 3 for COMP_007
  and COMP_014, before and after each configuration (baseline: COMP_007
  0.5350/0.5330/0.5300 then 0.5250 accepted at rank 4, margin **0.005**; COMP_014
  0.5860/0.4840/0.4820 then 0.4750 accepted at rank 4, margin **0.007**).
- The v4 queries whose top-3 status changes **in either direction** — rescued and lost
  are both reported, per configuration.

### Runs

Per configuration, in this order: held-out (`--stage auto --query-path app`) →
paste gate (`scripts/run_expert_paste_eval.py --stage auto`) → apply the selection rule →
only then v4 (`--stage auto --query-path app`). Results:
`data/benchmarks/ceval_holdout_v4_app_auto_<CFG>.csv` and
`data/benchmarks/ceval_v4_v4_app_auto_<CFG>.csv`.

### Results of Experiment 1

All runs: 130,472-row corpus, `--stage auto --query-path app`, `--useful-rule v4`, on the
working tree at `2b13fed` plus the uncommitted work described in this document. Held-out
and paste were run first, for all three configurations; the selection rule was applied to
those columns alone; **only then** was v4 run, for all three.

| configuration | held-out top-3 | held-out MRR | held-out misses | paste | v4 top-3 | v4 MRR | v4 misses | COMP_007 first accepted | COMP_014 first accepted |
|---|---|---|---|---|---|---|---|---|---|
| **baseline** (shipped) | 0.75 | **0.6667** | 001, 002, 005, 014, 026 | **8/8** | **0.90** | **0.7917** | COMP_007, COMP_014 | rank 4, 0.5250, **0.0050 behind** rank 3 | rank 4, 0.4750, **0.0070 behind** rank 3 |
| CFG-A carry-forward | 0.75 | 0.6167 | 001, 002, 005, 014, 026 | 8/8 | 0.85 | 0.7667 | COMP_001, COMP_014, COMP_022 | **rank 1**, 0.5150, 0.0060 **ahead** of rank 3 | rank 4, 0.4710, 0.0040 behind |
| CFG-B redistribute | 0.80 | 0.6667 | 001, 005, 014, 026 | 8/8 | 0.85 | 0.7250 | COMP_001, COMP_007, COMP_014 | rank 4, 0.6150, 0.0020 behind | rank 4, 0.5640, 0.0070 behind |
| **CFG-C both** (selected) | **0.85** | 0.6583 | 005, 014, 026 | 8/8 | 0.85 | 0.7750 | COMP_001, COMP_014, COMP_022 | **rank 1**, 0.6060, 0.0040 **ahead** of rank 3 | rank 4, 0.5600, 0.0040 behind |

Confidences are not comparable *between* rows of this table — each configuration
renormalises over its own weight mass — only within a row. The boundary tables behind
every cell were produced by `scripts/inspect_suggestion_boundary.py` (new; read-only,
reproduces the harness pipeline with `top_n` raised to 8), which reproduces the baseline
0.5350/0.5330/0.5300/**0.5250** and 0.5860/0.4840/0.4820/**0.4750** exactly.

**Queries whose top-3 status changed, in both directions** (pre-registered readout):

| configuration | v4 rescued | v4 lost | held-out rescued | held-out lost |
|---|---|---|---|---|
| CFG-A | COMP_007 | COMP_001, COMP_022 | — | — |
| CFG-B | — | COMP_001 | HOLD_002 | — |
| CFG-C | COMP_007 | COMP_001, COMP_022 | HOLD_001, HOLD_002 | — |

### Selection outcome

Applying the pre-registered rule to the held-out column alone: **CFG-C is selected** —
highest held-out top-3 useful-family accuracy (0.85 against 0.80, 0.75, 0.75), no tie, so
the MRR tie-break was not needed, and it holds the expert paste gate at 8/8 in auto.

Applying the lead's acceptance criteria to CFG-C, **two of the three fail**:

| criterion | CFG-C | verdict |
|---|---|---|
| held-out top-3 ≥ 0.75 | 0.85 | pass |
| held-out MRR ≥ 0.6667 | **0.6583** | **fail** |
| paste 8/8 in auto | 8/8 | pass |
| v4 loses no query it currently gets right | **loses COMP_001 and COMP_022** | **fail** |

**The default is therefore left untouched: no fix validated.** `SuggestionWeights` ships
exactly as before; the three configurations exist only as named presets behind
`WHYPTOLOGY_SUGGESTION_PRESET`, which is unset everywhere including the app and the
server. That is the pre-registered outcome for this case and it is reported as the
finding, not worked around.

For completeness, and *not* as a fallback the protocol provides for: **CFG-B is the only
configuration that satisfies both held-out criteria** (0.80 top-3, MRR exactly at the
0.6667 floor) with the paste gate at 8/8 — but it is not the selection under the rule as
written (CFG-C's top-3 is higher), and it fails the v4 criterion too (it loses COMP_001
and rescues nothing on v4). Substituting it for CFG-C after seeing the v4 column would be
choosing a configuration by its benchmark result, which is exactly what the standing rule
forbids. It is recorded here so the lead can decide with the numbers in front of him; it
was not applied.

### Verdict, in plain language

The mechanism hypothesis is **half right, and the half that is right is not worth
shipping as it stands.**

Right: the re-rank really was burying a well-retrieved parallel. Carrying retrieval's
IDF-weighted overlap forward (CFG-A, and CFG-C which contains it) moves COMP_007's
accepted candidate from **rank 4 to rank 1** — the single miss this whole diagnosis was
about — and on the held-out set CFG-C converts two of the five misses (HOLD_001,
HOLD_002) into top-3 hits. The diagnosis pointed at a real defect, and the general,
non-cherry-picked change aimed at it does move the intended cases.

Wrong, or at least unproven: it is a **trade, not an improvement**. The same change costs
COMP_001 and COMP_022 on v4, and on the held-out set it demotes several queries the
baseline had at rank 1 down to rank 2 (HOLD_010, HOLD_016 under CFG-C), which is why its
MRR *falls* to 0.6583 while its top-3 *rises* to 0.85. Read together those two facts say
the change buys coverage at rank 3 by spending precision at rank 1. For a tool whose
output is three suggestions an Egyptologist reads in order, that is not obviously the
better product, and the benchmark cannot settle it: with ~4,600 corpus rows counting as
"useful" for a median query (Rule A above), a top-3 metric has no resolution at this
scale — which is the same reason no fix was applied on 2026-09-04.

What the experiment adds to the record is a *measured* candidate rather than a
speculative one. The next honest step is not another reweighting: it is an evaluation
that can tell a rank-1 demotion from a rank-3 rescue — expert judgement on the queries
that changed, or a metric that scores the whole ordering rather than a hit inside three.
