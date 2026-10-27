# B-freq: the frozen glyph → reading baseline for the KRI test (2026-10-26)

Branch `kri-baseline-2026-10-26`, cut from `3e29304`.
Rev. 2, after the independent review of 2026-10-26 (verdict `fix_first`).

## What this is, and why it had to be frozen first

`docs/plan-data-cleanup-2026-10-26.md` rev. 3 (§4e) splits the KRI confirmation into
two endpoint-specific comparisons that are never pooled. Endpoint **R**
(transliteration input → retrieval) already had a baseline from protocol (B) of the
2026-10-25 pre-registration: word overlap, with BM25 secondary. Endpoint **G** (glyph
input → reading) had none. Without one, "the app got *k* of *n* readings right" is a
number with nothing to compare it to, and a baseline invented after seeing the results
is not a baseline at all.

§4e therefore defines one — **B-freq** — and makes it a precondition:

> **Precondition:** G can be part of a confirmation only if B-freq is implemented,
> unit-tested on synthetic fixtures and committed with its sha256 **before** any 4e
> material arrives. Otherwise G is reported as exploratory, and no G number goes to
> experts.

This document is the freeze record. **Read the freeze statement below before quoting
any endpoint-G number: the precondition as written was not met.**

## The exact rule

For one sign group:

1. **Sign-group key.** `app.data.normalizer.normalize_hieroglyphs`, then
   `scripts.import_ud_egyptian_pc.glyph_key` — the §4a `signs` definition (every
   space, layout control and placeholder removed), imported, not re-written.
2. **Candidates.** Every `strict_reading_key` value attested for *exactly* that sign
   string among the word-level (sign group, reading) pairs of the pinned public
   corpus, with its count.
3. **Ranking.** By count, descending.
4. **Tie-break.** Equal counts break by `strict_reading_key` ascending in Unicode
   code-point order. This implements the tie-break supplied with the task (count,
   then strict key by code point); it is restated here, in `TIE_BREAK_RULE` and in
   every generated header because a reader rebuilding the table has only those to go
   on. `tests/test_bfreq_baseline.py` asserts the whole table is identical when the
   corpus rows are reversed.
5. **What is offered.** Not the identity key — **an attested surface spelling** of
   it: the most frequent attested surface spelling carrying that reading identity in
   the same corpus, ties broken by the spelling ascending in Unicode code-point
   order (`SURFACE_RULE`). See *The folded-scorer fix* below for why this is
   load-bearing rather than cosmetic.
6. **Answer.** The top 3.
7. **Unattested sign string → the empty list**, which the scorer counts as a miss.
   There is no fallback of any kind: no glyph-similarity borrowing
   (`nearest_known_group`), no Helsinki lexicon, no sign-function composition, no
   smoothing. The baseline must be able to lose on its own terms, and it must never
   quietly borrow the app's machinery.

No context (no Viterbi, no bigrams, no neighbouring signs) and no stage filter in the
primary table. The Late-Egyptian restriction is §4e's **secondary, descriptive**
table, outside the Holm family.

### Where the pairs come from

`iter_word_pairs` mirrors `app.services.reading_model.ReadingModel.fit` exactly:
groups from `hieroglyphs_norm` split on whitespace, readings from
`transliteration_gold` split on whitespace, and a row contributes nothing unless the
two line up one-to-one. §4e requires "the same word alignment the app's reading model
is built from", so this is pinned by a test against `ReadingModel` itself — the pair
multiset and the three row counters (`sentences_seen`, `sentences_skipped`,
`sentences_text_only`) must match. If the app's alignment changes, that test fails
rather than the two sides silently diverging.

### What is shared with the app, and why

Only the *keys*, never the prediction, and only so that the comparison turns on
reading Egyptian rather than on a notation mismatch:

| | function | why |
|---|---|---|
| sign group | `normalize_hieroglyphs` → `glyph_key` | §4a `signs`. The app's normalisation runs first so a gold group pasted with a variant codepoint (Z15B U+133FC against the corpus's Z2 U+133E5 — the mismatch in Camilla's first trial) still finds the group the corpus attests. Bare `glyph_key` does not fold those; a test pins that it does not, and that `sign_key` does. |
| reading identity | `app.services.suggestions.strict_reading_key` | §4d: "strict key primary". Consonants stay distinct (ꜣ ≠ ꜥ, ḫ ≠ ẖ), per Nederhof's round-2 answer; TLA's `i̯`/`u̯` notation folds to `ꞽ`/`w` (item D′), so one reading in two editions' conventions is one table entry. |
| reported secondary | `app.data.normalizer.search_fold` | §4d: "folded key reported". Never primary — it merges ꜣ/ꜥ and ḫ/ẖ, which Nederhof rejected as an identity. |

### The folded-scorer fix (rev. 2)

The first version offered the identity key itself. That made the **secondary folded
scorer asymmetric**, and the review's repro is exact:

| | string offered | `search_fold` of it |
|---|---|---|
| gold | `n(.ꞽ).t` | `nt` |
| app | `n(.ꞽ).t` (a spelling) | `nt` → **hit** |
| B-freq, rev. 1 | `nꞽt` (the identity key) | `nit` → **miss** |

The strict key has already dropped the editorial apparatus; the ASCII fold treats a
stripped key and an unstripped spelling differently. On identical material — the same
word, from the same corpus — the app scored 1 and B-freq 0, for a reason that has
nothing to do with reading Egyptian.

B-freq now offers an attested spelling, as the app does, so both sides fold the same
kind of string. **Under the primary strict key nothing moves**: the spelling is chosen
from the words carrying that identity, so `strict_reading_key(surface)` is the identity
again. Both properties are pinned end to end by
`test_the_folded_scorer_does_not_punish_the_baseline_for_offering_a_key` and
`test_the_strict_scorer_is_unchanged_by_offering_spellings`. The table column was
renamed `example_reading` → `surface_reading` to record that the value stopped being
decoration; the data in it is byte-identical (verified: restoring the old header line
reproduces the rev. 1 sha256 exactly).

## Scoring (§4e, endpoint G) — one function for both sides

`score_line` is the only scorer; `score_pair` scores the app and B-freq in one call;
`score_endpoint_g` is the per-line entry point that reports the gold groups *before*
scoring either side.

* **Unit:** one declared line. Groups = Camilla's gold word division of that line.
* **Hit:** the gold reading's key is among that side's top 3 for that group.
* **Line score:** `s = hits / groups`.
* **Binary success:** `s ≥ 0.5` (inclusive), for app and baseline alike.
* **A group the app's segmentation does not produce, or that it merges or splits,**
  is passed as `None` and is a miss for the app.
* **A gold group whose reading has an empty key** is a miss for both sides, so
  neither is rewarded for an unreadable gold.

**B-freq is given the gold segmentation.** That favours the baseline — it never has
to find the word boundaries the app has to find. §4e says so and the report must
repeat it.

### Declared in advance: gold groups B-freq cannot key

`inspect_gold_groups()` classifies every gold group of a line — `scorable`,
`placeholder_only`, `no_signs` — and `score_endpoint_g()` produces that report
**before** either side is scored. The declared treatment
(`PLACEHOLDER_GOLD_TREATMENT`, frozen in code):

> A gold group whose signs are all internal `<g>` markup placeholders, or which
> carries no signs at all, has no sign key: B-freq cannot answer it and the app can.
> Such groups **stay in the denominator** and are scored as misses for the baseline.
> They are **counted and reported before scoring**, and **no difficult group is
> excluded after predictions are seen**.

### Not built yet: mapping app segments onto gold spans

The scorer is shared, but **no evaluator maps app segments onto gold spans**. §4e's
app score needs exactly that: which app segment answers which gold group, and how
merges, splits and repeated groups are handled (all three are misses for the app, but
something has to detect them). `score_endpoint_g` takes that mapping's output as an
argument; the mapping itself must be built, tested and frozen **before any scoring
run**. Until it exists, no endpoint-G number can be produced at all.

## The frozen artefacts

| | |
|---|---|
| **Freeze commit (rev. 1 code)** | `61fc30b98fa1bc9fd8e66e283027ebf401200527`, 2026-10-26 08:37:08 +01:00 |
| **Hash record (rev. 1 doc)** | `0f74f83be9619fc2ffdfb598fdff1e0d0b54e404`, 2026-10-26 08:40:24 +01:00 |
| **Rev. 2 (this document + the folded-scorer fix)** | same day, after the independent review, before any scoring run |
| `scripts/bfreq_baseline.py` | sha256 `9c7f1efe608e1320b8f9d5efe8ba6970943e1260a7b54ae2fc87a46a8793761f` |
| `scripts/build_bfreq_table.py` | sha256 `2fec0a2db86b7fc4b346a3d136d286e6422facaf61bcc94404badfb50f9fcf80` |
| `tests/test_bfreq_baseline.py` | sha256 `89b818f640a8cd5d1d2a8bb0a9fade4b54c0a3bf3add3253ece10f266932ea91` |
| **Combined dependency digest** | `94874bb29079688ac8ee6fc183a6af0a4b9117b72709d1415f76ebf16b0f7215` |
| **Corpus** | `data/processed/examples.csv` at `3e29304`, 130,472 rows, sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` |

**The dependency digest** covers `inspect.getsource` of every app function B-freq
imports rather than re-implements, because those decide what it answers while leaving
its own files untouched: `normalize_hieroglyphs`, `normalize_transliteration`,
`normalize_mdc`, `search_fold`, `fold_plural_marker`, `fold_weak_consonant_marker`,
`fold_letter_variants`, `strict_reading_key`, `ReadingModel.fit`, `glyph_key`,
`is_hieroglyph`. Source hashing cannot see the module-level tables and regexes those
read (`SIGN_VARIANTS`, the sign classes, the folds), so twelve **golden key vectors**
in `tests/test_kri_bfreq_freeze.py` pin the behaviour as well. Drift in either layer
fails the suite and requires an explicit amendment here, in the same commit.

### The table

Output directory `~/egyptology-baselines/kri-bfreq-2026-10-26/`. Built in 4.9 s,
253 MB peak RSS, from the code and corpus above.

| File | sha256 | size |
|---|---|---|
| `bfreq_table_all.csv` | `2b342dc4d3a4b9f0c0913fc71ac053719c037a7ab0bbd371e0e3fefa556360e1` | 3.0 MB, 66,889 rows |
| `bfreq_table_late_egyptian.csv` | `67cbb90280160ba0736ded11c86014ce81d5ff84445031baf5f806a05ba3718c` | 1.5 MB, 33,841 rows |
| `bfreq_header.json` / `.txt` | written by the same run | corpus sha256, code commit, row counts, tie-break rule, surface rule, declared treatment, each table's sha256 |

Columns: `sign_key, rank, reading_key, count, surface_reading`. Rows are sorted by
sign key in code-point order, then rank, and the writer pins `\n` line endings, so two
runs on the same corpus are byte-identical (tested).

*(Rev. 1 hashes, superseded: `5ea0b3cb…` and `82940e6d…`. Only the final column's
**name** changed; every data byte is identical, which was verified by restoring the old
header line and reproducing `5ea0b3cb…` exactly.)*

**Why the table is not committed.** Two reasons, both deliberate. It is 4.5 MB of
*derived* corpus data, and derived corpus data inherits the corpus's CC BY-SA
share-alike (see `DATA-LICENSE.md`); putting it in the code tree would blur the
MIT-code / CC-BY-SA-data line this repo keeps clean. And it is a deterministic
function of things that *are* committed — the code, the corpus sha256, the tie-break
and surface rules — so anyone can rebuild it in five seconds and compare hashes:

```bash
~/venvs/egyptology/bin/python scripts/build_bfreq_table.py \
    --examples data/processed/examples.csv \
    --out-dir ~/egyptology-baselines/kri-bfreq-2026-10-26
```

The freeze is carried by this document plus the git commits, not by the file's
location.

## Measured shape of the baseline (public corpus, 2026-10-26)

| | all | Late Egyptian |
|---|---|---|
| corpus rows read | 130,472 | 130,472 |
| rows used (aligned, with signs) | 59,504 | 31,538 |
| rows text-only (no hieroglyphs) | 70,968 | 12,127 |
| rows misaligned (signs ≠ words) | **0** | 0 |
| word pairs counted | 412,823 | 223,864 |
| word pairs dropped | 7,896 | 6,571 |
| distinct sign groups | 58,227 | 29,413 |
| groups with exactly one attested reading | 51,421 (88%) | 25,890 (88%) |
| groups with more than 3 readings | 816 | 385 |

Two things worth knowing before the numbers are read:

* **The dropped pairs are all placeholder-only groups.** All 7,896 (393 distinct) are
  groups whose every sign is a `<g>GARDINER_ID</g>` placeholder — a sign with no
  Unicode codepoint, which the §4a `signs` definition deletes, leaving an empty key.
  B-freq cannot answer such a group and scores it a miss; the app can read them,
  because `hieroglyphs_norm` keeps the placeholder as a glyph.

  **This asymmetry is harmless only while the input policy holds** — that gold groups
  are supplied as Unicode hieroglyphs (typed, pasted or transcribed from the page
  images), which cannot carry this project's internal placeholders. The policy is a
  condition, not a guarantee, so it is not relied on: every line's gold groups are
  classified and counted by `inspect_gold_groups()` **before** scoring, under the
  treatment declared above, and any placeholder-only or sign-less gold group is
  reported with its index, stays in the denominator, and is never removed afterwards.
* **88% of sign groups are attested with exactly one reading.** B-freq's "top 3" is a
  single reading for most groups, and empty for any group the corpus has never seen.
  That is the baseline's real weakness and the app's real opportunity — it is also why
  §4e gives B-freq the gold segmentation, to keep the handicap on the side that would
  otherwise be accused of a rigged comparison.

## Tests

`tests/test_bfreq_baseline.py` — 39 tests. `tests/test_kri_bfreq_freeze.py` — 23
tests. **All 62 pass.** Synthetic fixtures only; no test reads the real corpus.

| Required | Test |
|---|---|
| most-frequent choice | `test_most_frequent_reading_wins_and_the_ranking_is_by_count`, `test_counts_are_per_word_not_per_row` |
| tie-break determinism | `test_ties_break_by_code_point_not_by_insertion_order`, `test_the_whole_table_is_independent_of_row_order`, `test_the_build_script_is_byte_reproducible` |
| fold equivalence | `test_sign_group_key_applies_the_app_variant_fold`, `test_sign_group_key_ignores_layout_controls_and_placeholders`, `test_reading_identity_is_the_app_suggestion_key_so_notation_variants_merge`, `test_the_strict_key_still_keeps_different_consonants_apart`, `test_the_word_alignment_is_the_reading_models_own` |
| folded-scorer symmetry (rev. 2) | `test_the_folded_scorer_does_not_punish_the_baseline_for_offering_a_key`, `test_the_strict_scorer_is_unchanged_by_offering_spellings` |
| unseen group | `test_an_unattested_group_gives_an_explicit_no_reading`, `test_an_unattested_group_is_a_miss_and_never_borrows_from_the_app`, `test_a_group_with_no_signs_at_all_is_a_miss_not_a_crash` |
| gold-group report before scoring (rev. 2) | `test_gold_groups_are_classified_before_scoring`, `test_an_unkeyable_gold_group_stays_in_the_denominator_as_a_baseline_miss`, `test_score_endpoint_g_reports_before_it_scores_and_refuses_a_mismatch` |
| Late-Egyptian-restricted variant | `test_the_late_egyptian_table_sees_only_late_egyptian_rows`, `test_the_restriction_counts_skipped_rows_only_within_the_stage` |
| scorer symmetry (one function for both sides) | `test_app_and_baseline_are_scored_by_the_same_function`, `test_the_baseline_is_scored_from_the_table_through_the_same_scorer`, plus `test_the_line_score_is_hits_over_groups_with_success_at_one_half`, `test_only_the_top_three_count`, `test_a_group_the_app_did_not_produce_is_a_miss` |
| never reads a KRI path | `test_a_kri_or_private_path_is_refused`, `test_the_guard_never_touches_the_custody_directory`, `test_the_builder_opens_only_the_files_it_was_given`, `test_the_guard_does_not_trip_on_this_branch_or_the_public_corpus` |
| drift (rev. 2) | `test_the_pinned_dependencies_have_not_drifted`, `test_the_golden_key_vectors_still_hold`, `test_every_pinned_dependency_is_one_b_freq_actually_uses` |

The custody guard (`assert_public_path`) is **lexical**: `os.path.abspath` normalises
without touching the filesystem, so clearing or refusing a custody path never stats,
lists or opens it. A guard that had to look inside the directory to clear a path would
undercut the very claim this file makes. It refuses any path with a component
`egyptology-private-kri` or `kri`, and the component *pair* `data/private`. The pair
form is deliberate: a first draft refused any `private` component and the test suite
caught that macOS puts every temporary directory under `/private/var/folders/…`. It is
a tripwire against the pre-registered custody location, not a secret scanner — it
knows where a file sits, not what it holds.

## Freeze statement — and the deviation from §4e

§4e requires the freeze **before the material arrives**, not before it is viewed. That
is not what happened, and the deviation is recorded here plainly rather than papered
over.

> Code was committed at 08:37:08 +01:00 and the hash record at 08:40:24, after the KRI
> PDFs were received around 07:43. According to the lead's attestation, no KRI text or
> page content was viewed or used before freezing; handling was transfer, hashing and
> a structural format check (scanned images, no text layer). This was not
> independently verified. This is a freeze after receipt and before reported content
> inspection, not the pre-arrival freeze §4e requires. Consequence: endpoint G on
> lines drawn from these PDFs is exploratory under §4e and yields no confirmation
> number for experts; endpoint R is unaffected. A G confirmation needs a separately
> eligible future cohort whose material arrives after this freeze.

Two notes on the wording:

* **"Unopened" means the content was not viewed.** Hashing reads every byte of a file,
  so "unopened" cannot be literal. What is attested is that no transliteration, no
  reading and no page content was looked at or used — the bytes were moved and
  digested, not read.
* The agent that wrote this file was **forbidden to verify** the custody facts, since
  verifying them would have meant touching the very directory the rule protects. They
  are the lead's attestation, labelled as such. Independently of that, the build
  itself reads `data/processed/examples.csv` and nothing else outside its own output
  directory, which `test_the_builder_opens_only_the_files_it_was_given` asserts by
  recording every file opened.

**Rev. 2 amendment.** The folded-scorer fix, the gold-group report and this document
were made the same day, after an independent review and **before any scoring run** —
no endpoint-G number existed when they were made, so nothing was tuned on a result.
The primary strict-key behaviour is unchanged by the amendment (pinned by test); only
the secondary folded scorer changed, from a broken comparison to a valid one. The
amendment does not alter the §4e status above: these PDFs stay exploratory either way.

If any part of the rule, the keys, the tie-break, the surface rule or the scorer
changes after this point, the baseline is retired and re-frozen, exactly as §4e's "any
change after seeing results retires the set" requires.

## Still to be done before any endpoint-G run

1. **Build the app-segment → gold-span mapping** (merges, splits, repeated groups),
   test it, and freeze it. Nothing can be scored without it.
2. Commit the declaration file's sha256 first
   (`~/egyptology-private-kri/declaration.csv`): each line's input modality and
   endpoint, declared before any run (§4d).
3. Commit the §4e exclusion manifest, including every 4d line, its passage and every
   other edition of the same text.
4. Draw a **separately eligible cohort** for any G *confirmation*: material that
   arrives after this freeze. Lines from the present PDFs are exploratory.
5. Power floor ≈ 150 endpoint-G lines, judged separately from endpoint R, with Holm
   across the family of two. Below it, G is "uninformative" and still counts in the
   family.
6. Rebuild the table and amend this document with the new corpus and table sha256s if
   `examples.csv` changes first (part 1 cleanup and part 3 PT admission both change
   it). The rule, the keys, the tie-break and the surface rule do not change; only the
   counts do.

## Amendment 2026-10-26 (rev. 3): repeated gold groups, and the mapping is built

*Appended after the Opus + Astra review of the KRI tooling branch
(`kri-official-prep-2026-10-26`), before any KRI scoring run and before any
endpoint-G number existed. Nothing above is edited; this section supersedes the
parenthetical noted below.*

**Repeated gold groups are not misses.** "Not built yet" above lists "merges, splits
and repeated groups" and says "(all three are misses for the app …)". For repeated
groups that parenthetical is superseded. §4e lists as misses only a group the app
"does not produce, or that it merges or splits", and this record's own scoring section
says the same. B-freq scores every repeat on its own, so penalising a correctly
aligned repeat would treat the two sides differently and cost the app a group for a
line that repeats a word. The hazard the phrase named — a string-keyed mapping pairing
a gold group with the wrong segment, or one segment answering two groups — is removed
by construction: the mapping aligns by character offset. The frozen rule, verbatim
from `scripts/kri_segment_mapping.py` (`REPEATED_GROUP_RULE`):

> Repeated identical gold groups are told apart by their character offsets: each occurrence is answered by the app segment at its own position, and no app segment answers two gold groups. Repeats are counted and reported per line, never scored as misses for being repeats.

**Step 1 of "Still to be done" is done.** The app-segment → gold-span mapping is
built (`scripts/kri_segment_mapping.py`) and tested, and its sha256 — with those of
the overlap checker, the manifest and declaration tooling, the statistics and the
driver — is recorded in `docs/kri-official-test-tooling-2026-10-26.md` and enforced
by `tests/test_kri_tooling_freeze.py`.

This amendment changes no B-freq rule, key, tie-break, surface rule, scorer or table;
the frozen files and their sha256s above are unchanged.
