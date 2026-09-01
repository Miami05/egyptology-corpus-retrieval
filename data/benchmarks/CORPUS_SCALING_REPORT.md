# Corpus scaling: 100 → 300 real TLA rows

Question: **does more real corpus data improve contextual reading suggestions?**

Answer: **yes**, but the size of the gain depends entirely on which benchmark you
trust, and one of the benchmarks was measuring the wrong thing.

Source corpus: `data/raw/tla_earlier/tla_earlier.parquet` (12,773 rows available).
The 300-row import is a strict superset of the 100-row import with identical IDs,
so the same benchmark queries can be replayed against both.

---

## 1. Headline result (trustworthy)

Same 20 queries, no near-duplicate twins in the corpus, only the corpus size changes:

| corpus rows | top-1 exact | top-3 exact | top-1 useful-family | top-3 useful-family | MRR | failures |
|---|---|---|---|---|---|---|
| 100 | 0.00 | 0.00 | 0.20 | 0.30 | 0.250 | 14 / 20 |
| 300 | 0.05 | 0.05 | 0.25 | **0.55** | 0.375 | 9 / 20 |

**Top-3 useful-family accuracy rose from 0.30 to 0.55 (+25 points) purely from
tripling the corpus.** This is the defensible version of the claim.

Benchmark: `snapshots/corpus_100/competitive_v2_queries.csv` (built on the 100-row
corpus, so every expected row exists in both corpora).

## 2. Current standing on the widest pool

A fresh benchmark drawn from all 300 rows (harder and more varied queries):

| corpus rows | top-1 exact | top-3 exact | top-1 useful-family | top-3 useful-family | MRR | failures |
|---|---|---|---|---|---|---|
| 300 | 0.00 | 0.00 | 0.25 | 0.65 | 0.408 | 7 / 20 |

Exact reproduction of an unseen sentence remains near zero. That is expected: the
tool is not meant to guess a sentence it has never seen, it is meant to surface the
right *reading family*. Useful-family accuracy is the metric that matches the goal.

## 3. Why the original benchmark overstated the gain

Replaying the **original** 100-row benchmark gave a much flatter picture:

| corpus rows | top-1 exact | top-3 exact | top-1 useful-family | top-3 useful-family | failures |
|---|---|---|---|---|---|
| 100 | 0.10 | 0.10 | 0.75 | 0.75 | 5 / 20 |
| 300 | 0.15 | 0.15 | 0.80 | 0.80 | 4 / 20 |

0.75 → 0.80 looks like a weak result, but 0.75 was already close to the ceiling of
that benchmark, so there was little room to improve.

Worse, **rebuilding that benchmark on 300 rows produced a meaningless 0.85 / 1.00
with zero failures.** Cause: the old builder ranked candidate rows by *highest*
token overlap with any other row, so at 300 rows all 20 slots were filled by
sentences that have a **word-identical duplicate** elsewhere in the corpus.
Excluding the target row still leaves its twin, so the expected reading is returned
for free. It measured deduplication, not disambiguation.

The artifact scales with data, which is the dangerous part:

| corpus rows | rows with a near-identical twin (overlap ≥ 0.9) |
|---|---|
| 100 | 2 |
| 300 | 37 |

Fix applied in `scripts/build_competitive_ambiguity_benchmark.py`:

- exclude rows whose closest rival is at or above `--max-twin-overlap` (default 0.9);
- rank by *number of competing rows* rather than closest single match, so selected
  cases have genuine rivals;
- keep one benchmark row per distinct reading (the old output repeated the same
  sentence in four slots).

**Do not quote the 0.85 / 1.00 figure.** It is an evaluation bug, not a result.

> **Correction (2026-08-29): the fix above is incomplete.** The twin-overlap guard
> runs inside the builder's candidate pool (`--pool-size`, default 2,000 rows), but
> the eval runner loads the **full** corpus and excludes only the one expected row.
> A near-identical twin outside the builder pool is invisible to the guard and present
> at eval time — the same artifact, through a window the fix did not cover, and it
> still scales with corpus size. Measured on 2026-08-29 with the builder's own metric
> (loose-form token Jaccard ≥ 0.9) over all 12,772 rows: **11 of the 20 competitive
> items have a twin outside the pool — 7 of them at 1.00, 4 string-identical.** The
> ambiguous benchmark has no guard at all (`df.head(20)`) and 10 of its 20 items have
> twins. Until the guard is re-run against the same corpus the eval loads (see
> ROADMAP.md, Phase 4), treat current benchmark numbers as an upper bound rather than
> a measurement, and version the benchmark file rather than overwriting it — a re-run
> re-selects all 20 items and breaks comparability with every number in this report.

> **Resolved (2026-08-30).** The guard now runs against the full corpus using an
> inverted token index (29 s, not hours), and the rebuilt benchmark is versioned
> rather than overwritten:
>
> | | v1 (`competitive_ambiguity_eval_queries.csv`) | v2 (`…_v2.csv`) |
> |---|---|---|
> | items with a twin ≥ 0.9 anywhere in the corpus | **11 of 20** (6 identical) | **0 of 20** |
> | top-1 useful family | 0.55 | **0.55** |
> | top-3 useful family | 0.75 | **0.70** |
> | MRR | 0.64 | **0.60** |
>
> **v2 is the reportable number from now on.** The builder also gained a signal
> floor: a generated query of one ubiquitous token (`z`, in thousands of rows) asks
> the ranker to choose between thousands of equally-matching sentences, so such rows
> are dropped rather than scored — v1 shipped three of them. v1 is kept in the repo
> so every figure quoted above stays reproducible, and
> `tests/test_phase4_evaluation.py` asserts both properties: that v2 has no twins and
> that v1 still does.
>
> The honest reading of this table: removing 11 contaminated items cost about
> 5 points of top-3 and 4 of MRR. Less than feared, but the earlier numbers were
> still measuring partly memorisation, and only v2 can be quoted.

## 4. Two other evals that are not accuracy measures

- `run_ambiguous_suggestion_eval` reports 1.00 across the board because the expected
  row is **left in the corpus**. It is a retrieval sanity check and now prints a
  warning saying so. Not reportable as accuracy.
- The stored `suggestion_eval_results.csv` claimed **100% top-1 on 100 rows**. That is
  not reproducible with the current code: re-running the identical 100-row corpus today
  gives **0.02**. The old number came from an earlier pipeline that injected the query's
  own reading as candidate #1, making the gold answer rank 1 by construction. Regenerated
  honestly, leave-one-out exact reproduction of a held-out sentence is:

  | corpus rows | top-1 | top-3 |
  |---|---|---|
  | 100 | 0.02 | 0.02 |
  | 300 | 0.10 | 0.10 |

  Still a 5× gain from more data, on the strictest possible task.

## 5. Failure analysis — the bottleneck has moved

`scripts/analyze_competitive_failures.py` separates *"no parallel exists"* (import more
data) from *"the parallel exists but ranked too low"* (improve scoring):

| category | @100 rows (14 failures) | @300 rows (7 failures) |
|---|---|---|
| query genuinely too short | 8 | 3 |
| ranking issue (useful parallel exists, ranked > 3) | 3 | 3 |
| threshold marginal | 2 | 1 |
| corpus gap (nothing useful to find) | 1 | **0** |

**At 300 rows there are zero corpus gaps.** For every substantive failure a useful
parallel is already sitting in the corpus — retrieval just ranks it too low:

| query | expected | rank of first useful parallel |
|---|---|---|
| `w awpl sn awtpl sn n` | `ꞽw ꞽꜣ(w).PL =sn ꞽꜣw.t.PL =sn n kꜣp.t.PL =f` | 5 |
| `skhnti wsr wr pl` | `sḫnti̯ wsꞽr s.t =f r wr.PL ꞽm.ꞽ.w tꜣ-ḏsr` | 11 |
| `shdj ma grh` | `sḥḏ ꞽr =k mꜣ =n t(w)t.w(ꞽ)n grḥ` | 21 |

This reorders the roadmap: **ranking work (Step 4) now buys more than another import
(Step 1).** Three of the remaining failures need only a top-5 → top-3 improvement.

Short queries (2 tokens, e.g. `a ph`, `baa mn`) are a separate matter. They are
genuinely underspecified, and the honest product behaviour is a low-confidence answer
with visible alternatives, not a hit.

---

## Reproducing

```bash
# import + build (limit sets corpus size)
.venv/bin/python -m scripts.import_tla_dataset \
    --input data/raw/tla_earlier/tla_earlier.parquet --limit 300
.venv/bin/python -m scripts.build_examples_from_real
.venv/bin/python -m scripts.import_examples

# replay one frozen benchmark against different corpus sizes
.venv/bin/python -m scripts.run_competitive_ambiguity_eval \
    --examples data/processed/examples.csv \
    --benchmark data/benchmarks/snapshots/corpus_100/competitive_v2_queries.csv \
    --label "v2 benchmark, corpus=300"

# classify what is left
.venv/bin/python -m scripts.analyze_competitive_failures
```

`data/benchmarks/snapshots/corpus_100/` holds the frozen 100-row corpus, DB and
results, so this comparison stays reproducible after further imports.

Note: the venv was missing `six`, `typing_extensions` and `pytz`, which broke pandas
and SQLAlchemy; repaired via `pip install -r requirements.txt`. Importing `sklearn`
still hangs, but nothing in the live retrieval path imports it — only the unused
stray file `app/retrieval/tfidf 2.py` does.

---

# Ranking work (after the 300-row scaling)

The failure analysis said ranking, not data, was the bottleneck. Two changes followed.

## 6. Thirty percent of the weight mass was unreachable

`combine_scores` mixed eleven signals, but six of them — deity, formula type,
formula slot, offering overlap, recipient and aesthetic arrangement — read columns
that are **empty for all 300 rows**. Their combined weight of 0.30 was silently
lost, so a perfect text match could only reach about 0.60, and confidence values
were not comparable between queries.

The score is now renormalised over the signals that actually discriminate for the
query at hand. A signal that is zero for every candidate (an empty metadata column,
or reading-order overlap when the user gave no reading order) is dropped and the
remaining weights are rescaled. The same offering-formula query that scored 0.551
now scores 0.727, and the weights live in a named `ScoreWeights` object.

## 7. IDF-weighted token overlap

Plain Jaccard gave `n`, `k`, `f` and `m` the same say as `ḫnt.ꞽ` or `sḫnti̯`, so
grammatical particles drowned out the tokens that actually identify a parallel.
A document-frequency-weighted overlap now makes rare shared tokens decide the
ranking.

## 8. Weights tuned on a held-out split

Because the benchmark's useful-family metric is itself partly token and lemma
overlap, tuning against the reported queries would have optimised the metric rather
than the tool — the same mistake as the duplicate-twin leak, in subtler form. So an
80-query benchmark was split by index into 40 tune and 40 holdout queries, 55 weight
configurations were swept on the tune half only, and the winner was scored **once**
on the holdout half:

| holdout (40 queries) | top-1 useful | top-3 useful | MRR |
|---|---|---|---|
| previous weights | 0.525 | 0.675 | 0.592 |
| tuned weights | **0.550** | **0.725** | **0.617** |

Chosen weights: `fuzzy=0.35, tfidf=0.18, overlap=0.10, idf_overlap=0.40`. The search
picked IDF overlap as the single heaviest signal, which matches the reasoning above.

Honest caveat: 40 queries means one query is 2.5 points, so +5 points is two queries.
The direction is consistent across all three metrics and on a genuinely held-out
split, but it is suggestive rather than conclusive. Widen the benchmark before
quoting a precise figure.

On the canonical 20-query benchmark, top-3 useful-family went 0.65 → 0.75 and
failures 7 → 5 — but that set overlaps the tuning pool, so the holdout table above
is the reportable result.

What actually moved, per failure:

| query | useful parallel rank before | after |
|---|---|---|
| `w awpl sn awtpl sn n` | 5 | **now in top 3, passes** |
| `skhnti wsr wr pl` | 11 | 10 |
| `shdj ma grh` | 21 | 24 |

So IDF weighting rescues near-misses and does little for distant ones; one case got
marginally worse. Remaining failures: 2 ranking, 2 queries too short, 1 marginal
threshold. Still zero corpus gaps.

Next lever: `analyze_competitive_failures.py` measures *retrieval* rank, while the
eval measures *suggestion* rank, and `suggest_top_readings` re-orders by its own
grouped confidence. `baa mn` now has a useful parallel at retrieval rank 3 yet still
fails, which suggests the suggestion layer can undo good retrieval ordering. That is
worth investigating before further weight tuning.

## 9. A crash fixed along the way

pyarrow 25.0.0 segfaults inside `convert_column` when Streamlit re-serialises the
corpus table on a rerun. It survived the first render and killed the process on the
second, which is what happens the moment a user touches a filter. pyarrow was not
pinned — it arrived as a transitive Streamlit dependency. It is now pinned to
21.0.0 in requirements.txt.

## 10. Environment

The project was moved from the iCloud-synced `~/Desktop` to `~/dev/Egyptology-APP`
and the virtualenv was rebuilt. `import sklearn`, which used to hang indefinitely,
now completes in 17 seconds — confirming iCloud on-demand file fetching was the
cause, along with the evicted venv files and the `" 2"` conflict copies.

---

# 11. The "suggestion layer" lever did not exist

The previous section suspected that `suggest_top_readings` was undoing good retrieval
ordering: it re-ranks with its own eight-signal blend in which retrieval contributes
only 0.36 (`relative_score` 0.24 + `mean_score` 0.12), and the query `baa mn` had a
useful parallel at retrieval rank 3 yet still failed.

That hypothesis was **wrong**, and testing it is what showed so.

`SuggestionWeights` was made configurable and the tuner extended to a second stage:
25 suggestion-layer configurations swept on the tune split, then scored once on the
holdout. On the tune split the best configuration looked like a gain (top-1 0.375 ->
0.400, MRR 0.4917 -> 0.5083). **None of it transferred:**

| holdout (40 queries) | top-1 | top-3 | MRR |
|---|---|---|---|
| current weights | 0.55 | 0.725 | **0.6167** |
| retuned suggestion layer | 0.55 | 0.725 | 0.6125 |

So the retuned weights were **not** applied. This is the second time the held-out
split has rejected something that looked good in-sample.

Inspecting `baa mn` directly explains why there was nothing to win. The suggestion
layer returns retrieval's #2, #1 and #4 — mild reordering, not distortion. The real
situation is that no candidate is any good: the whole ranked list scores between
0.154 and 0.207, which is noise. The "useful parallel at rank 3" was an artifact of
the useful-family rule, which counts a single shared lemma as useful when the expected
reading has two or fewer lemmas.

Two things follow:

- The remaining failures are genuinely underspecified queries, not misranked ones.
  `baa mn` is two tokens; no ranking function recovers `ꞽw bꜥꜥ =f n mn.t` from that.
- The useful-family metric is **more permissive than it looks**. The single-shared-lemma
  rule for short readings inflates "a useful parallel exists", which in turn inflated
  the earlier claim that failures were fixable by ranking. Tightening that rule would
  lower the reported accuracy and make it more honest.

The `SuggestionWeights` refactor was kept: with the default weights its mass is exactly
1.0, so the normalisation is a no-op and every eval number is unchanged. It makes the
layer tunable for when the corpus is larger.

# 12. Is Camilla's objection answered? Not yet — and here is the measurement

Camilla's point: OCR and sign recognition are solved; the bottleneck is predicting the
most likely *reading*, because signs are multivalent. Two measurements say the project
does not yet demonstrate this.

**The corpus contains almost no genuine multivalence.** Hieroglyphs and transliteration
are token-aligned in all 300 sentences, so the sign -> reading map is directly countable:

| | count |
|---|---|
| distinct sign groups | 880 |
| with more than one literal reading | 47 |
| with more than one reading after collapsing editorial brackets | 25 |
| purely orthographic/editorial variation | 22 |

And most of the surviving 25 are still not multivalence — they are present/absent plural
or feminine endings (`hr w` / `hr`, `nfr` / `nfr t`, `nb t` / `nb`) or transcription
variants (`zp` / `sp`, `rdi` / `rdji`). Genuinely different words written with one sign
amount to a handful: 𓇓𓅱 as `sw` ("he") or `nswt` ("king"), 𓂢𓂢 as `rmn` or `qꜥḥ`,
𓂞 as `ḏi̯` or `mi`. That is under 1% of sign groups.

**The tool cannot be queried by signs at all.** This is the more serious gap. Taking a
row that is *in* the corpus and querying with its own hieroglyphs:

```
glyphs : 𓊵𓏙 𓇓𓏏 𓊵𓏙 𓃢 𓏃𓊹𓉱
gold   : ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnp.w ḫnt.ꞽ-zḥ-nṯr
suggestions: ꞽ ṯḥn-ꞽdb.w tp(.ꞽ)-ꞽmꜣm=f  (confidence 0.016), ḥr.w ḏr, ḏ(d)-mdw
correct reading returned: False
```

Cause: `normalize_mdc` reduces the glyph string to `''`. Retrieval only ever indexes
`mdc_norm`, which is derived from the transliteration, and the parquet importer sets
`sign_sequence` to the transliteration too (`import_tla_dataset.py:392`). The
`hieroglyphs` column is stored and displayed but **never searched**.

So the current tool answers "given a transliteration, show me attested parallel
readings". Camilla's bottleneck is "given signs, which reading is most likely" — and at
that moment an Egyptologist has signs, not a transliteration. The mechanism, evidence
display and expert-correction loop are all real and working; the input the argument
depends on is not yet accepted.

## What would actually answer the objection

1. **Index the hieroglyphs.** Normalise glyph strings instead of discarding them, index
   them alongside `mdc_norm`, and add a sign-sequence input mode. The data is already
   token-aligned, so this is the highest-value change available and needs no new corpus.
2. **Ship a sign -> readings view.** For a selected sign group, list every attested
   reading with counts and example sentences. That *visualises* multivalence and is the
   artifact an Egyptologist can judge.
3. **Scale the corpus.** Only 300 of 12,773 available sentences are loaded (2.3%). More
   data means more attested multivalent cases; the current 47 are too few to argue from.
4. **Separate editorial variation from multivalence** everywhere, using the loose reading
   form, so claims about ambiguity are not inflated by bracket noise.
5. **Tighten the useful-family rule** (see section 11) so the headline accuracy is not
   propped up by single-lemma coincidences.
6. **Then** collect expert-curated ambiguous cases. They are only worth an
   Egyptologist's time once sign input exists.

---

# 13. Sign input: the tool now answers the question it was built for

Section 12 showed the blocking gap — querying with hieroglyphs was impossible because
`normalize_mdc` deletes those codepoints, so the query became `''`. That is fixed.

**What changed**

- `normalize_hieroglyphs` and `contains_hieroglyphs` in `app/data/normalizer.py`. The
  old pattern `[^a-z0-9:_\-\s]` stripped everything outside ASCII, and hieroglyphs live
  at U+13000-U+1342F. Whitespace is preserved because it separates sign groups, and
  those groups align one-to-one with transliteration tokens.
- `hieroglyphs_norm`, a searchable sign key on every row (`app/data/loader.py`).
- Three sign signals in the scorer — `glyph_overlap`, `glyph_idf_overlap`,
  `glyph_exact` — reusing the IDF weighting so a rare sign counts more than a common
  determinative.
- `retrieve_top_k` detects the script and routes the query to the sign columns.
  The renormalisation from section 6 does the rest: for a sign query the
  transliteration signals are all zero and get dropped, so the score comes purely
  from sign evidence, and one weight set serves both input modes.
- The workspace shows which index a query will hit, so a mis-detected query does not
  look like a broken search.

**Result — sign sequence in, reading out, leave-one-out over all 300 sentences**

The target row is removed from the corpus, the query is its hieroglyphs alone, and the
tool must propose a reading from sign parallels:

| metric | before | after |
|---|---|---|
| top-3 useful reading | impossible (empty query) | **0.603** |
| top-1 useful reading | impossible | 0.490 |
| exact reading recovered | impossible | 0.100 |
| MRR (useful) | – | 0.541 |

Reproduce with `python -m scripts.run_sign_reading_eval`.

This is the first measurement in the project that speaks directly to Camilla's
objection, because it is the only one where the input is what an Egyptologist actually
holds: signs, not a transliteration. Roughly three sentences in five get a genuinely
useful reading in the top three from sign evidence alone.

The transliteration benchmark is unchanged (top-3 useful-family 0.75, 5 failures), so
sign support was added without disturbing the existing path.

# 14. Sign readings page

`app/services/signs.py` builds the sign -> readings index and a new "Sign readings"
page renders it: pick a sign group, see every attested reading with its share of
instances and the sentences behind each one.

It separates the two things a naive count conflates:

| | count |
|---|---|
| sign groups | 770 |
| more than one literal reading | 39 |
| genuinely multivalent (after collapsing editorial brackets) | 22 |
| editorial variants only | 17 |

Real cases it surfaces: 𓇓𓅱 read as `sw` ("he", 7×) or `nswt` ("king", 1×); 𓊨𓁹 as
`(w)sr(.w)` (5×) or `(w)sꞽr` (4×); 𓇋𓏲 as `ꞽw` (8×) or `sw` (1×). This is the artifact
an Egyptologist can judge, and it is honest about how thin the evidence still is —
22 ambiguous signs is a demonstration, not a corpus-scale argument. Scaling past the
current 2.3% of available sentences remains the main lever.

---

# 15. Full corpus (12,772 sentences) and a second approach

## Scaling reveals the multivalence the small corpus hid

At 300 sentences multivalence looked like a marginal phenomenon. It is not — it was a
sampling artefact:

| sentences | sign groups | genuinely multivalent | editorial-only | share of sign instances that are ambiguous |
|---|---|---|---|---|
| 300 | 770 | 22 | 17 | 10.9% |
| 500 | 1,146 | 39 | 20 | 17.5% |
| 1,000 | 1,953 | 95 | 31 | 22.5% |
| 2,000 | 3,208 | 185 | 59 | 30.9% |
| 5,000 | 6,224 | 400 | 120 | 45.3% |
| **12,772** | 12,076 | **961** | 250 | **53.5%** |

Genuine multivalence grew 44x (22 -> 961) while editorial variation grew only 15x, so
the ratio of signal to bracket-noise *improves* with scale. **At full corpus size, more
than half of all sign instances are written with a sign that has more than one attested
reading.** That is the quantified version of Camilla's objection, and it is now
measurable in this project rather than asserted.

## A second approach: sign-level contextual decoding

Sentence retrieval answers "which sentences look like this one", which only helps when a
close parallel exists. The objection is narrower: *this* sign has several readings, so
which applies here. That is sequence labelling over signs, not document similarity, so
`app/services/reading_model.py` models it directly:

```
score(reading | sign, previous) = log P(reading | sign)              how this sign is read
                               + log P(reading | previous reading)   reading context
                               + log P(reading | previous sign)      sign context
```

Viterbi decodes the jointly best reading sequence. Every probability is a smoothed count
from real sentences, a sign never seen is reported rather than guessed at, and each
prediction carries its alternatives with attestation shares — so a scholar can see what
was rejected and why.

**Evaluation** (`scripts/run_reading_model_eval.py`), train/test split by sentence, and
because the corpus is formulaic, held-out sentences whose exact sign string also occurs
in training are dropped (`--exclude-duplicates`; 703 of 2,392 at full scale). Accuracy
over all signs is uninformative — most signs have one reading and every method gets them
right — so the headline is accuracy on **ambiguous** signs:

| sentences | ambiguous sign types | most-frequent baseline | context model | gain | unseen signs |
|---|---|---|---|---|---|
| 300 | 28 | 0.870 | 0.899 | +2.9 | 43.6% |
| 1,000 | 106 | 0.838 | 0.863 | +2.4 | 34.3% |
| 5,000 | 450 | 0.864 | 0.878 | +1.5 | 22.0% |
| **11,959** | **1,021** | 0.856 | **0.891** | **+3.5** | 16.1% |

Two things this shows. Context genuinely resolves multivalence — the gain over a
frequency-only baseline is positive at every corpus size, so it is not noise. And
scaling mainly buys **coverage**: signs the model has never seen fall from 43.6% to
16.1%, which is the difference between a demo and a usable tool.

Honest limits: the most-frequent baseline is already 0.856 because reading distributions
are skewed, so the context model adds 3.5 points rather than transforming the task; and
16% of signs still cannot be read by any count-based method.

## Sentence retrieval at full scale

| | 300 sentences | 12,772 sentences | 12,772, twins excluded |
|---|---|---|---|
| sign query -> top-3 useful reading | 0.603 | 0.873 | **0.830** |
| sign query -> exact reading | 0.100 | 0.343 | **0.080** |

The exact-match column is the cautionary one. It looks like a 3.4x improvement until
duplicate sign strings are excluded, at which point it drops to 0.080 — the apparent
gain was memorising a twin. Useful-reading accuracy survives the same test (0.830), so
that is the number to quote. `--exclude-duplicates` was added to this eval too.

The transliteration benchmark also improved with scale: top-1 useful-family 0.25 -> 0.55
and MRR 0.45 -> 0.63, with top-3 steady at 0.75.

## Performance

No optimisation was needed, which was worth measuring before assuming: at 12,772 rows a
query takes 0.42s, corpus load 0.3s, reading-model training 0.2s, and decoding is
instantaneous. The one real bottleneck was benchmark *construction*, which compares every
row with every other; it now scans a capped pool (`--pool-size`, default 2000) instead of
running for hours.

## Tests

`tests/` now covers the parts where correctness is not obvious by inspection: the
hieroglyph normaliser (including a test that pins the original ASCII-stripping defect),
the decoder (including that context can override frequency, that misaligned rows are
skipped rather than guessed, and that unseen signs are reported), the sign index
(genuine multivalence vs editorial variants), and score renormalisation (empty metadata
columns must not dilute a perfect match). 29 tests, all passing.

## Where this leaves Camilla's objection

It is now answered with measurements rather than intent:

- More than half of all sign instances in the corpus are genuinely multivalent (961 sign
  types), so the problem is real and quantified.
- Given signs alone, the tool proposes a useful reading in the top 3 for **83%** of
  held-out sentences with no duplicate to lean on.
- On the signs where a reading choice is actually being made, contextual decoding is
  right **89%** of the time, beating a frequency-only baseline by 3.5 points.
- Every prediction shows its alternatives, attestation counts and corpus parallels, and
  an expert can accept, edit, reject or flag it.

Remaining honest gaps: 16% of signs are unattested and unreadable by this method; the
corpus is one language stage from one source; and no expert-curated ambiguity set exists
yet. That last one is now worth an Egyptologist's time, because the tool finally accepts
the input they hold.

---

# 16. Two targeted improvements: one failed, one worked

Both were implemented and measured on held-out sentences with duplicate sign strings
excluded, so the results below are comparable to section 15.

## 16.1 Right-hand sign context — no measurable gain

Reasoning for trying it: Egyptian writes determinatives *after* the phonetic signs, and
the determinative is often what fixes which word is meant, so a model looking only left
should be missing the most informative neighbour. `P(reading | following sign)` was added
as a fourth term.

Measured effect on ambiguous signs, same model with the term switched off vs on:

| sentences | frequency only | left context | + right context | right-context gain |
|---|---|---|---|---|
| 300 | 0.870 | 0.899 | 0.899 | +0.000 |
| 500 | 0.839 | 0.869 | 0.876 | +0.007 |
| 1,000 | 0.838 | 0.863 | 0.863 | +0.000 |
| 2,000 | 0.857 | 0.893 | 0.892 | −0.001 |
| 5,000 | 0.864 | 0.878 | 0.882 | +0.005 |
| 11,959 | 0.856 | 0.892 | 0.894 | +0.002 |

**The prediction was wrong.** The gain is indistinguishable from noise, and at full
corpus size +0.002 is about twelve sign instances out of 6,151.

The reason emerged from writing the test for it: **Viterbi already propagates information
from the right** through the reading-bigram chain. If reading `x` is never followed by
reading `e` and `y` always is, then the best whole path for a sequence ending in `e`
already prefers `y`, with no next-sign term involved. A dedicated test now pins this
behaviour (`test_viterbi_already_propagates_information_from_the_right`), and a second
test constructs the narrow case where the following *sign* genuinely adds something —
two different following signs that happen to share the same reading, so the reading chain
cannot separate them.

The term is kept because it is cheap, tested and may matter on a corpus with sparser
reading sequences, but it is documented in the module as **not** a source of the model's
accuracy. It should not be claimed as an improvement.

## 16.2 Fallback for unattested sign groups — large coverage gain, weak precision

A sign group absent from the corpus previously produced nothing at all. Since an unseen
*group* is usually built from individually common glyphs, the model now finds the attested
group with the highest glyph overlap and borrows its readings, flagged as a fallback and
carrying the similarity score.

Precision/coverage tradeoff, measured on 1,689 held-out sentences:

| overlap threshold | fallback precision | share of all signs newly readable |
|---|---|---|
| 0.34 | 24.9% | 15.9% |
| **0.50 (default)** | **25.3%** | **15.5%** |
| 0.67 | 32.6% | 8.3% |
| 0.80 | 33.7% | 4.8% |

Effect on coverage — the share of sign instances for which any reading can be offered:

| sentences | coverage before | coverage with fallback | fallback accuracy |
|---|---|---|---|
| 300 | 56.4% | 82.3% | 0.158 |
| 1,000 | 65.7% | 93.3% | 0.178 |
| 5,000 | 78.0% | 98.6% | 0.226 |
| **11,959** | **83.9%** | **99.4%** | **0.254** |

So the 16% unreadable gap is essentially closed, but the readings filling it are correct
about a quarter of the time against roughly 89% for attested groups. That is only
defensible because they are labelled: the sign-by-sign table shows
`inferred from 𓏃𓏏𓊹 (50% glyph match)` instead of an attestation count, and the page
states the accuracy difference outright. Presented as confident predictions they would be
misleading; presented as leads with their evidence visible they are useful.

Note also that fallback accuracy *rises* with corpus size (0.158 → 0.254), because a
larger corpus offers closer neighbours to borrow from.

## What to claim, precisely

- Ambiguous-sign reading accuracy is **0.89**, and the honest comparison is against a
  frequency-only baseline at **0.856** — a gain of about 3.5 points, from the reading and
  left-sign context terms. Not from right-hand context.
- Coverage is **99.4%** of sign instances, of which **83.9%** rest on direct attestation
  and the remainder are flagged inferences correct about a quarter of the time.
- 37 tests cover this, including tests that pin both the successful behaviour and the
  negative result.

# 17. v2 and v3 retired as reportable numbers (2026-09-01)

Two things changed on 2026-09-01, and each one alone would have ended the comparability
of the v2/v3 competitive benchmarks. Their per-query results are kept for the record,
but **neither set may be quoted as accuracy from this date**.

**(i) The search fold changed.** Query and index are now reduced by one function,
`search_fold`, and the yod is folded rather than deleted: `ꞽ`, `j` and `i` all become
`i`. The v2/v3 benchmark files store `query_input` and `expected_key_tokens`
*pre-folded in the old space* — `m n k r` for `m(ꞽ) n =k ꞽr(.t)-ḥr.w`, with every yod
already gone. Replaying them against the new index compares two different alphabets,
so any movement in their numbers after this date measures the mismatch, not the tool.

**(ii) The searchable corpus changed twice in one day.**
- 9,823 AES rows became reachable by transliteration query. They had always been in
  `examples.csv`, but the index was built from a column they ship empty, so a third
  of the corpus was invisible to text search. The AES fix added competition to every
  v2/v3 query without those queries having been drawn from it.
- Rows from `phiwi/bbaw_egyptian` (CC BY-SA 4.0; BBAW January-2018 snapshot) are being
  added — 35,503 rows with word-aligned hieroglyphs, deduplicated against the existing
  corpus. That is a different corpus again, and the one v4 must be drawn from.

For the record, the last v2/v3 replays *before* the fold change (after the AES fix)
were: v2 top-1 useful 0.60 / top-3 0.80 / MRR 0.683 / 4 failures; v3 0.75 / 0.90 /
0.808 / 2. Those are the final numbers of that lineage.

## v4 — to be cut on the final corpus

Build **after** the bbaw_egyptian import has landed and the fold change is in, never
before: a benchmark drawn from a corpus that is about to change is the mistake §3
documents. Use the twin-exclusion builder exactly as for v2/v3:

```bash
python scripts/build_competitive_ambiguity_benchmark.py \
  --output data/benchmarks/competitive_ambiguity_eval_queries_v4.csv
python scripts/verify_release.py \
  --benchmark data/benchmarks/competitive_ambiguity_eval_queries_v4.csv
```

Record the builder's "skipped with a near-identical twin" count alongside the result;
§3 explains why that number is part of the evidence.

| v4 (final corpus) | value |
|---|---|
| corpus rows | _pending_ |
| queries | _pending_ |
| skipped: near-identical twin | _pending_ |
| top-1 useful-family | _pending_ |
| top-3 useful-family (**the reportable number**) | _pending_ |
| MRR | _pending_ |
| failures | _pending_ |

Until that table is filled in, the honest statement is: *"the tool has no current
reportable accuracy figure; v2/v3 were retired on 2026-09-01 when the fold and the
corpus changed."*
