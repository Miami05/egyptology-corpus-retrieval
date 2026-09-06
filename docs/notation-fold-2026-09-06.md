# Item D′ — the weak-consonant notation fold in the suggestion identity key (2026-09-06)

Item D ended with a finding, not a fix: the top-3 really does show the same sentence twice, but
the token that differs is ordinary vocabulary in two editions' orthography (`ḏi̯` / `ḏꞽ`), not a
proper noun. D′ is that follow-up, pre-registered and run tonight.

**Result in two lines.**

* **It ships.** `strict_reading_key` now folds TLA's weak-consonant marker (`i̯` → `ꞽ`, `u̯` → `w`).
  On NAME-v1 the notation-duplicate slots go **2 → 0**; on all four sets top-3 useful and MRR are
  **exactly** their committed values, paste is 8/8, segmentation is byte-identical, and the
  corpus-wide merge count is 25 (> 0, the "it does something" clause).
* **Its whole footprint on the four benchmark sets is three queries.** NAME_020 and NAME_022 lose
  their duplicate third slot and gain a genuinely different reading in its place (the merged
  suggestion's support goes 23 → 30 rows); LE_016's third confidence moves 0.555 → 0.557. Nothing
  else in 100 queries × 25 result columns changes at all — no `exact_rank`, no
  `useful_family_rank`, no other suggestion, no other score.

Worktree `/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/agent-a5611c5cf6a2afd8a`,
branch `worktree-agent-a5611c5cf6a2afd8a`, off `main` at `b4c471d`. Interpreter
`/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus 130,472 rows. Nothing committed.

---

## 1. The pre-registration, quoted

From `ROADMAP.md`, "**D′ — notation fold in the suggestion identity key — pre-registered
2026-09-06 night (Opus 5 worker)**":

> **Diagnosis (measured tonight).** The weak-consonant marker U+032F (`i̯`, `u̯`) sits on 36,547
> corpus tokens (3.4%): TLA 5,960, AES 4,079, BBAW 26,508, Ramses 0; 493 token types are attested
> both with and without it (`rdi̯`/`rdꞽ`, `ḏi̯.t`/`ḏꞽ.t`, `mi̯`/`mꞽ`, `ꞽwi̯.n`/`ꞽwꞽ.n`). The search
> fold and the loose form already equate them (`rdi̯ =f` and `rdꞽ =f` both fold to `rdi f`), so
> retrieval finds both; only `strict_reading_key` keeps them distinct, so two rows that differ only
> in this notation are two suggestion groups — the duplicate pairs item D found (`ḏi̯`/`ḏꞽ`).
> The marker is a notation for the same weak radical, not a different sound, so folding it belongs
> in the identity key.
>
> **Change (the whole of it).** In `strict_reading_key`, after NFC and before the dots are dropped:
> `i̯` → `ꞽ` and `u̯` → `w` (the combining U+032F after `i`/`u`). Nothing else: no search, loose,
> retrieval or ranking-weight change. `ḥ`/`h`, `ꜣ`/`ꜥ`, `ṯ`/`t`, `ḏ`/`d` stay distinct.
>
> **Measurements.** Baseline first on the pristine tree: (a) *notation-duplicate slots* — top-3
> slots on NAME-v1, v4, held-out 1, LE-v1 whose new key equals an earlier slot's (the pairs that
> would merge); (b) corpus-wide, how many of the 125,338 distinct strict keys merge under the new
> key. After the change: the four sets' top-3 useful, MRR, failures, exact-rank columns, with every
> per-query rank change listed; paste 8/8; `run_segmentation_eval.py` byte-identical. Also state
> whether `exact_or_near` fired differently on any query (the key feeds it).
>
> **Decision.** Ship iff no set's top-3 useful or MRR is lower than its committed value (v4 0.9 /
> 0.7917, held-out 1 0.75 / 0.6667, LE-v1 0.8667 / 0.8167, NAME-v1 0.9667 / 0.8833), paste 8/8,
> segmentation byte-identical, and the corpus-wide merge count is > 0 (the change does something).
> Report every exact-metric movement even when the rule passes. Null allowed.
>
> **Tests.** `rdi̯ =f` and `rdꞽ =f` share a key; `ḏi̯.t`/`ḏꞽ.t`; `u̯`→`w`; NFD input; `ḥtp`/`htp`
> still distinct; idempotent; the key of a marker-free reading is unchanged (fixture of 200 corpus
> readings without the marker, byte-identical before/after).

### The diagnosis, re-measured on the pristine tree

| quantity | pre-registration | measured tonight |
|---|---|---|
| tokens carrying U+032F | 36,547 (3.4%) | **36,547** of 1,075,594 (3.4%) |
| by source | TLA 5,960 / AES 4,079 / BBAW 26,508 / Ramses 0 | **identical** |
| token types attested both with and without it | 493 | **538** raw, **554** lowercased |

One discrepancy, stated rather than smoothed over: the type count. My count is of whitespace
tokens over `transliteration_gold` whose fold has an attestation elsewhere in the corpus without
the marker — 538 case-sensitive, 554 after lower-casing (which is what the key does). The
pre-registration's 493 was measured some other way; the direction and the order of magnitude
agree, and nothing in the decision rule depends on it.

One fact the pre-registration did not state and the fold relies on: **the marker occurs only after
`i` (36,322) and `u` (582)** — nowhere else in the corpus — so `i̯`→`ꞽ`, `u̯`→`w` covers every
occurrence and no third case is silently dropped.

## 2. The change

`app/data/normalizer.py` gains `fold_weak_consonant_marker` (and `WEAK_CONSONANT_MARKER_RE`),
beside the plural-marker fold it is the twin of. `app/services/suggestions.py`:

```python
    text = nfc(_safe_str(value)).lower().replace("⸗", "=")
    text = fold_plural_marker(text)
    text = fold_weak_consonant_marker(text)          # item D′
    text = STRICT_DROP_RE.sub("", text)
```

That is the entire behavioural change: one line in `strict_reading_key`, after NFC and the plural
fold, before the editorial marks are dropped. No search fold, no loose form, no retrieval, no
weight. NFC and NFD inputs behave identically because no precomposed codepoint exists for either
letter-plus-marker, so both shapes are the same two codepoints; the fold composes to NFC first
anyway.

`notation_folded_reading_key` (the metric's key: fold, then strict key) is also in
`suggestions.py`. Since the fold shipped it returns exactly what `strict_reading_key` returns —
pinned by a test, so a later change that undid the fold would fail loudly rather than quietly
turning the metric into a tautology.

## 3. The metric, and the proof that it changes nothing else

`scripts/run_competitive_ambiguity_eval.py` gained **one appended column**
`notation_duplicate_slots` and one summary line, on item D's pattern: a slot counts as a duplicate
when its notation-folded key equals that of a slot above it. Unlike item D's name metric it needs
no corpus lookup — the fold is a property of the reading string alone, so it cannot be silently
vacuous through a failed row identification.

Proved, not asserted — the four benchmarks were re-run on the **pristine** key and diffed column
by column against their committed result files:

| committed file | shape | only-in-new columns | shared columns that differ |
|---|---|---|---|
| `ceval_v4_v4_app_auto_results.csv` | 20 × 25 → 20 × 27 | `name_duplicate_slots`, `notation_duplicate_slots` | **NONE** |
| `ceval_holdout_v4_app_auto_results.csv` | 20 × 25 → 20 × 27 | both | **NONE** |
| `ceval_le_v1_app_auto_results.csv` | 30 × 25 → 30 × 27 | both | **NONE** |
| `ceval_name_v1_app_auto_results.csv` | 30 × 26 → 30 × 27 | `notation_duplicate_slots` | **NONE** |

(The first three committed files predate item D, hence two new columns; NAME-v1's already carries
`name_duplicate_slots`.) No committed result file was overwritten: every run in this report wrote
to a scratch path.

## 4. Baseline and after

All eight runs `--query-path app --stage auto`, corpus 130,472 rows, one process at a time.

| set | queries | top-1 useful | top-3 useful | MRR | failures | **notation-duplicate slots** |
|---|---|---|---|---|---|---|
| **NAME-v1** before | 30 | 0.8000 | 0.9667 | 0.8833 | 1 | **2** |
| **NAME-v1** after | 30 | 0.8000 | 0.9667 | 0.8833 | 1 | **0** |
| v4 before / after | 20 | 0.7000 / 0.7000 | 0.9000 / 0.9000 | 0.7917 / 0.7917 | 2 / 2 | 0 / 0 |
| held-out 1 before / after | 20 | 0.6000 / 0.6000 | 0.7500 / 0.7500 | 0.6667 / 0.6667 | 5 / 5 | 0 / 0 |
| LE-v1 before / after | 30 | 0.7667 / 0.7667 | 0.8667 / 0.8667 | 0.8167 / 0.8167 | 4 / 4 | 0 / 0 |

The exact-transliteration columns, reported as the pre-registration demands even though the rule
does not turn on them: `top1_exact_accuracy` 0.0 on every set before and after;
`top3_exact_accuracy` 0.05 on v4 (COMP row) and 0.0 on the other three, **before and after**. No
exact metric moved in either direction. `name_duplicate_slots` stays 0 everywhere and
`expected_absent_from_pool` stays 0 everywhere.

v4 0.9 / 0.7917, held-out 1 0.75 / 0.6667, LE-v1 0.8667 / 0.8167 and NAME-v1 0.9667 / 0.8833 are
the committed numbers, reproduced exactly on both sides of the change.

## 5. Every per-query change

Before/after diffed cell by cell, all 100 queries × 27 columns. **Three queries changed; on none
of them did `exact_rank` or `useful_family_rank` move.** v4 and held-out 1 are byte-identical
throughout.

### NAME_020 and NAME_022 — the duplicate pair item D found, removed

Query `htp dji nswt htp dji inp tp i` (both queries produce the same top-3; the targets are two
different Anubis offering formulae).

| | before | after |
|---|---|---|
| slot 1 | `ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnp.w tp.ꞽ-ḏw=f` — 0.871, 5 rows | unchanged |
| slot 2 | `ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnp.w` — 0.860, **supported by 23 rows** | same reading, 0.860, **supported by 30 rows** |
| slot 3 | `ḥtp-ḏꞽ nswt ḥtp-ḏꞽ ꞽnp.w` — 0.860, 7 rows — *the same reading as slot 2* | `ḥtp-ḏꞽ nswt ḥtp-ḏꞽ wsꞽr` — 0.788, 10 rows — the **Osiris** formula |
| useful-family rank | 1 | 1 |
| exact rank | none | none |
| notation-duplicate slots | 1 | 0 |

This is the mechanism working exactly as designed: the 23-row group and the 7-row group are one
reading in two editions' notation, they merge into one 30-row group whose displayed reading is the
best-scoring row's, and the freed third slot goes to the next distinct reading.

**Reported honestly: the freed slot did not go to a better answer.** The new slot 3 is the Osiris
formula, which is *not* a useful-family match for these two Anubis targets, so
`useful_family_reasons` for slot 3 goes from "useful lemma-family match: 27360, 88040" to "no
useful-family match", and the slot-3 overlap scores fall (token 0.167 → 0.097, lemma 0.667 →
0.333). Since the useful answer was already at rank 1, top-3 useful and MRR are untouched — but
the honest description of the gain is "the third alternative is now a different reading", not "the
third alternative is now right". The other changed columns on these two rows (`confidence_scores`,
`evidence_summaries`, `supporting_sources`) are all slot 3's, plus slot 2's support count.

### LE_016 — one confidence score, from the `u̯` half of the fold

Query `mtw iri ssh tay sha nty iw rdi`; suggestions and their order are identical before and
after; the third confidence moves **0.555 → 0.557**.

Why: slot 3 is `mtw =k sꜣu̯ tꜣy =ꞽ šꜥ.t ꞽri̯ =st n =k mtr`. `char_similarity` is computed on the
*keys* through the ASCII lens, and that lens is blind to `i̯` (`rdi̯` and `rdꞽ` both give `rdi`)
but **not** to `u̯`: `sꜣu̯` used to lens as `sau`, and after the fold the key holds `sꜣw`, which
lenses as `saw` — closer to the query. char_similarity 0.4758 → 0.4894, at weight 0.16, is the
0.002 on the card. Rank unchanged, useful rank 1 unchanged. This is the only place in the four
sets where the fold moved a number without moving a grouping.

### NAME_029 — deliberately *not* fixed

Item D's third duplicate pair (`ꞽt` / `ꞽt(ꞽ)`, "father") is a genuine spelling variant, not a
notation, and the pre-registration excludes it. Its row is byte-identical before and after, and a
test pins `strict_reading_key("ꞽt") != strict_reading_key("ꞽtꞽ")`.

### `exact_or_near` — identical on all 100 queries

The signal is `1.0` when the candidate key equals the query key, else `0.85` when the loose forms
are equal, else `0.65` when `char_ngram_similarity(query_key, candidate_key) ≥ 0.82`. The fold can
only move a candidate's key or the query's, so the check was done as a **superset over the whole
corpus** rather than over the top-50 pools — every one of the 125,623 distinct corpus readings
tested against every one of the 100 queries:

```
readings whose strict key the fold rewrites: 26276 (of 125623 distinct readings)
  … of which the LOOSE form of the key also moves: 543   (only these can move the 0.65 tier)
queries whose own key the fold rewrites: 0                (no benchmark query carries the marker)
queries with at least one candidate whose exact_or_near bonus moves: 0
```

**Zero.** Not "zero in the pools" — zero anywhere in the corpus, so no pool could have contained
one. `exact_or_near` fired identically on every query of all four sets; the 0.85 tier cannot move
at all (it reads the raw loose forms, which the fold never touches), and no candidate's folded key
newly equals or newly differs from a query key. The three movements in §5 come from grouping
(NAME_020/022) and from `char_similarity` (LE_016), not from this signal.

## 6. Corpus-wide

```
distinct strict_reading_key values:                       125338      (matches the expected figure)
distinct keys after the fold:                             125313
folded keys that merge >= 2 distinct strict readings:        25       (covering 50 strict readings)
corpus rows whose strict key the fold rewrites:           26914  of 130472  (20.6%)
distinct readings whose strict key the fold rewrites:     26276  of 125623
```

**25 merges > 0, so the "the change does something" clause is satisfied** — and it is worth being
precise about what "something" means: the fold rewrites a fifth of all corpus keys, but only 25
pairs of *whole readings* become one, because two rows have to be identical in every other respect
to collide. The merged pairs, ten of them verbatim:

```
'ḫꜥꞽ'                <- ['ḫꜥi̯', 'ḫꜥꞽ']
'ꞽrꞽ'                <- ['ꞽri̯', 'ꞽrꞽ']
'ꞽṯꞽ'                <- ['ꞽṯi̯', 'ꞽṯꞽ']
'sṯꞽ-ḥꜣb'            <- ['sṯi̯-ḥꜣb', 'sṯꞽ-ḥꜣb']
'ḥtp-ḏꞽ nswt'        <- ['ḥtp-ḏi̯ nswt', 'ḥtp-ḏꞽ nswt']
'nṯrw ḥtpw hrw'      <- ['nṯrw ḥtpw hru̯', 'nṯrw ḥtpw hrw']
'sw ršw ḥr ꜥḏꜥḏ'     <- ['sw ršu̯ ḥr ꜥḏꜥḏ', 'sw ršw ḥr ꜥḏꜥḏ']
'sntꞽn =ꞽ m ḥr =ꞽ'   <- ['snti̯n =ꞽ m ḥr =ꞽ', 'sntꞽn =ꞽ m ḥr =ꞽ']
'ꞽyꞽn =ꞽ r ꜥḫm ḫt'   <- ['ꞽyi̯n =ꞽ r ꜥḫm ḫt', 'ꞽyꞽn =ꞽ r ꜥḫm ḫt']
'nn zꜣw =ṯn šwt =ꞽ'  <- ['nn zꜣu̯ =ṯn šwt =ꞽ', 'nn zꜣw =ṯn šwt =ꞽ']
```

Both halves of the fold are represented: seven `i̯` pairs and three `u̯` pairs. The longest merged
sentences are the offering formulae — `ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnpw ḫntꞽ-zḥ-nṯr` and its `ḏꞽ` twin,
which is precisely the pair that showed up in NAME_020 and NAME_022's top-3.

For comparison, item D's name-normalised key merged 63 keys covering 128 readings (0.10%); this
one merges 25 covering 50 (0.04%). The difference is that this one's merges are *reachable*: two
copies of the same offering formula in two editions are both in the top-50 pool of any offering
formula query, which is why D′ moves the top-3 and D did not.

## 7. Tests

`tests/test_notation_fold.py` — the pre-registered list, in its order, 8 tests, all passing:

| test | asserts |
|---|---|
| `test_the_same_verb_in_two_notations_is_one_reading` | `rdi̯ =f` and `rdꞽ =f` share a key |
| `test_the_fold_survives_the_dots_and_brackets` | `ḏi̯.t`/`ḏꞽ.t`; `ḥtp-ḏi̯ nswt`/`ḥtp-ḏꞽ nswt`; `(w)di̯` → `wdꞽ` (bracketed letter still kept) |
| `test_u_with_the_marker_folds_to_w` | `hru̯`/`hrw`, `zꜣu̯`/`zꜣw` |
| `test_decomposed_input_folds_like_composed_input` | NFD input, including a sentence whose other letters decompose |
| `test_distinct_consonants_stay_distinct` | `ḥtp` ≠ `htp`, ꜣ≠ꜥ ḥ≠h ḫ≠ẖ ṯ≠t ḏ≠d, **`ꞽt` ≠ `ꞽtꞽ`** |
| `test_the_fold_is_idempotent` | key(key(x)) == key(x), fold(fold(x)) == fold(x) |
| `test_marker_free_readings_key_exactly_as_they_did_before_the_fold` | the 200-reading fixture |
| `test_the_measurement_key_and_the_shipped_key_now_agree` | metric key == shipped key |

The fixture `tests/fixtures/marker_free_readings.json` is 200 corpus readings that contain no
marker, each stamped with the key the **pristine** pipeline produced (NFC, lower, ⸗→=, plural fold,
drop editorial marks — re-run independently of the current code, so this is a genuine before/after
comparison and not the new code agreeing with itself). All 200 key byte-identically after the
fold.

**Two existing test literals had to be updated, and both are the key's own definition changing:**

* `tests/test_phase0_data_integrity.py:144` — `strict_reading_key("(w)di̯") == "wdi̯"` → `"wdꞽ"`.
  The assertion's point (the bracketed `w` survives, only marks vanish) is unchanged.
* `tests/test_proper_nouns.py:54` — item D's expected name key `ḥtp ḏi̯ 49460` → `ḥtp ḏꞽ 49460`.
  The test still asserts what it asserted: two spellings of Osiris collapse, the plain strict key
  does not collapse them.

No test was deleted, weakened or marked xfail.

## 8. Gates

* `run_segmentation_eval.py` — **unspaced F1 0.939 / exact 0.579, scrambled 0.946 / 0.635**
  (as_pasted 0.653 / 0.048), boundary-model prior 0.3097, unseen-word breakdown unchanged.
  Byte-identical to the committed gate. Nothing in segmentation reads the reading key.
* `run_expert_paste_eval.py --stage auto` — **passed 8/8**, and the results written to a scratch
  path diff clean against the committed `expert_paste_eval_results.csv`: 23 shared columns, **none
  differ**.
* pytest, per module / in chunks, **439 passed, 0 failed**:
  `test_phase0_data_integrity` + `test_notation_fold` + `test_normalizer` **55**;
  `test_phase2_ranking` + `test_adjacency` + `test_proper_nouns` **40**;
  `test_phase4_evaluation` + `test_pipeline_fuzz` **52**;
  `test_signs_and_scoring` + `test_scoring_equivalence` + `test_similar_text` + `test_reading_model` **74**;
  `test_query_notations` + `test_composition` + `test_lexicon` + `test_stage` + `test_api` **135**;
  `test_frontend_smoke` + `test_phase5_licence_and_polish` + `test_private_corpus` **83**.
* `git status` after every run: only the five source/test files and the two new files are
  modified. No committed benchmark or results file was touched.

## 9. Decision

The frozen rule: *ship iff no set's top-3 useful or MRR is lower than its committed value, paste
8/8, segmentation byte-identical, and the corpus-wide merge count > 0.*

| clause | value | verdict |
|---|---|---|
| v4 0.9 / 0.7917 | 0.9 / 0.7917 | not lower |
| held-out 1 0.75 / 0.6667 | 0.75 / 0.6667 | not lower |
| LE-v1 0.8667 / 0.8167 | 0.8667 / 0.8167 | not lower |
| NAME-v1 0.9667 / 0.8833 | 0.9667 / 0.8833 | not lower |
| paste | 8/8 | pass |
| segmentation | 0.939 / 0.579, 0.946 / 0.635 | byte-identical |
| corpus-wide merges | 25 (> 0) | pass |

**SHIPS.** The fold is not behind a switch: it is part of the definition of `strict_reading_key`,
as the pre-registration says. The evidence for it is the symptom metric (NAME-v1 2 → 0) and the
demonstration that it costs nothing anywhere else; it is not a metric win, because the metric it
could have won on (top-3 useful) was already right on those two queries at rank 1.

**Blast radius worth knowing.** `canonical_reading`/`strict_reading_key` is also used by
`build_competitive_ambiguity_benchmark.py` (the twin guard and distractor selection),
`compute_v4_answerability.py`, `analyze_competitive_failures.py`, `run_sign_reading_eval.py`,
`run_ambiguous_suggestion_eval.py` and `tune_ranking_weights.py`. The existing benchmarks are
frozen files and were not rebuilt, so none of tonight's numbers depend on that; but a benchmark
**built** after this change would see 25 fewer distinct readings and could pick marginally
different distractors. Anyone rebuilding a set should say so in that set's provenance.

## 10. For Nederhof

Your second criticism was that the alternatives we show are often one word written differently.
Item D tested the proper-noun version of that and found it absent from our data. This is the
version that was actually there. TLA's editions mark a weak radical with a small hook under the
letter — `rḏi̯` "give" — where other editions write `rḏꞽ`; the corpus carries both, 36,547 tokens
with the hook and 554 word types attested both ways. Our search already treated them as one word,
but the key that decides *whether two suggestions are the same reading* did not, so an offering
formula copied in two editions arrived in the top three twice. It now keys as one reading: the
suggestion merges, its support count adds up (23 rows + 7 rows = 30, so the confidence the reader
sees is now backed by all the evidence there is), and the freed slot shows the next genuinely
different reading — in the query we traced, the Osiris version of the formula instead of a second
copy of the Anubis one. Nothing else moved: every benchmark score is identical to the digit, and
letters that really are different letters (ḥ and h, ꜣ and ꜥ, ṯ and t) stay apart, as does a real
spelling variant such as `ꞽt` beside `ꞽtꞽ` for "father". The fix is deliberately narrow — one
notation, not a normalisation of Egyptological orthography.

## 11. What exists now

**Modified** (uncommitted, in the worktree):

* `app/data/normalizer.py` — `WEAK_CONSONANT_MARKER_RE`, `fold_weak_consonant_marker`.
* `app/services/suggestions.py` — the fold inside `strict_reading_key`; the new
  `notation_folded_reading_key`.
* `scripts/run_competitive_ambiguity_eval.py` — `notation_duplicate_slots`: one helper, one
  appended column, one summary line.
* `tests/test_phase0_data_integrity.py`, `tests/test_proper_nouns.py` — the two key literals.

**Added:** `tests/test_notation_fold.py` (8 tests), `tests/fixtures/marker_free_readings.json`
(200 readings + their pre-D′ keys).

**Not done, on purpose:** no `variant_readings` or "also written …" display (that was D1, which is
a null and stays one), no retrieval or weight change, no rebuilt benchmark, nothing committed.
