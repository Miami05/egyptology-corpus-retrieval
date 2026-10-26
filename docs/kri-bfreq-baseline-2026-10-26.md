# B-freq: the frozen glyph → reading baseline for the KRI test (2026-10-26)

Branch `kri-baseline-2026-10-26`, cut from `3e29304`.

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

This document is the freeze record.

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
   code-point order. (§4e says only "ties are broken by count"; without a second key
   the table would depend on corpus row order. The rule is fixed here and printed in
   every header. `tests/test_bfreq_baseline.py` asserts the whole table is identical
   when the corpus rows are reversed.)
5. **Answer.** The top 3.
6. **Unattested sign string → the empty list**, which the scorer counts as a miss.
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

## Scoring (§4e, endpoint G) — one function for both sides

`score_line` is the only scorer, and `score_pair` scores the app and B-freq in one
call so a second scoring path cannot appear:

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

## The frozen artefacts

| | |
|---|---|
| **Code commit** | `61fc30b98fa1bc9fd8e66e283027ebf401200527` (clean tree) |
| `scripts/bfreq_baseline.py` | sha256 `c4b225e781d0b246a7a246b8e20f0238d59315652988e6c862836f16217c1896` |
| `scripts/build_bfreq_table.py` | sha256 `4aad3024ea5a78b972c2064ee5d1efb42cc74c1264fc99f0ba7a3e683b9a7f32` |
| `tests/test_bfreq_baseline.py` | sha256 `16eab6d0c0d583fffbeb98368c95377d941d8255e0430c74a13f7bea3481ecbb` |
| **Corpus** | `data/processed/examples.csv` at `3e29304`, 130,472 rows, sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` |

### The table

Built 2026-10-26 07:37 UTC, in 4.9 s, 253 MB peak RSS, from the commit and corpus
above. Output directory `~/egyptology-baselines/kri-bfreq-2026-10-26/`.

| File | sha256 | size |
|---|---|---|
| `bfreq_table_all.csv` | `5ea0b3cbfb0ebfee141ccde810b543c7683335f84c3944d27ec29ea0ed1c3f6b` | 3.0 MB, 66,889 rows |
| `bfreq_table_late_egyptian.csv` | `82940e6d7c41925fc5d2591ea24349bb313e9f9bcf87e74d5311f271e92daae4` | 1.5 MB, 33,841 rows |
| `bfreq_header.json` / `.txt` | written by the same run | corpus sha256, code commit, row counts, tie-break rule, each table's sha256 |

Columns: `sign_key, rank, reading_key, count, example_reading`. `example_reading` is
the commonest surface spelling carrying that key — for the report only, never used in
scoring. Rows are sorted by sign key in code-point order, then rank, and the writer
pins `\n` line endings, so two runs on the same corpus are byte-identical (tested).

**Why the table is not committed.** Two reasons, both deliberate. It is 4.5 MB of
*derived* corpus data, and derived corpus data inherits the corpus's CC BY-SA
share-alike (see `DATA-LICENSE.md`); putting it in the code tree would blur the
MIT-code / CC-BY-SA-data line this repo keeps clean. And it is a deterministic
function of three things that *are* committed — the code commit, the corpus sha256
and the tie-break rule — so anyone can rebuild it in five seconds and compare hashes:

```bash
~/venvs/egyptology/bin/python scripts/build_bfreq_table.py \
    --examples data/processed/examples.csv \
    --out-dir ~/egyptology-baselines/kri-bfreq-2026-10-26
```

The freeze is carried by this document plus the git commit, not by the file's
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
  B-freq therefore cannot answer such a group, and would score it a miss. The app can
  read them, because `hieroglyphs_norm` keeps the placeholder as a glyph. This does
  not bias the KRI comparison: Camilla's glyph input is pasted or typed Unicode, which
  cannot contain this project's internal placeholders, so no *gold* group will be
  placeholder-only. It is recorded here so the asymmetry is on the table rather than
  discovered later.
* **88% of sign groups are attested with exactly one reading.** B-freq's "top 3" is a
  single reading for most groups, and empty for any group the corpus has never seen.
  That is the baseline's real weakness and the app's real opportunity — it is also why
  §4e gives B-freq the gold segmentation, to keep the handicap on the side that would
  otherwise be accused of a rigged comparison.

## Tests

`tests/test_bfreq_baseline.py`, 34 tests, **all passing**, synthetic fixtures only —
no test reads the real corpus. Coverage required by the task, with the test that
carries each:

| Required | Test |
|---|---|
| most-frequent choice | `test_most_frequent_reading_wins_and_the_ranking_is_by_count`, `test_counts_are_per_word_not_per_row` |
| tie-break determinism | `test_ties_break_by_code_point_not_by_insertion_order`, `test_the_whole_table_is_independent_of_row_order`, `test_the_build_script_is_byte_reproducible` |
| fold equivalence | `test_sign_group_key_applies_the_app_variant_fold`, `test_sign_group_key_ignores_layout_controls_and_placeholders`, `test_reading_identity_is_the_app_suggestion_key_so_notation_variants_merge`, `test_the_strict_key_still_keeps_different_consonants_apart`, `test_the_word_alignment_is_the_reading_models_own` |
| unseen group | `test_an_unattested_group_gives_an_explicit_no_reading`, `test_an_unattested_group_is_a_miss_and_never_borrows_from_the_app`, `test_a_group_with_no_signs_at_all_is_a_miss_not_a_crash` |
| Late-Egyptian-restricted variant | `test_the_late_egyptian_table_sees_only_late_egyptian_rows`, `test_the_restriction_counts_skipped_rows_only_within_the_stage` |
| scorer symmetry (one function for both sides) | `test_app_and_baseline_are_scored_by_the_same_function`, `test_the_baseline_is_scored_from_the_table_through_the_same_scorer`, plus `test_the_line_score_is_hits_over_groups_with_success_at_one_half`, `test_only_the_top_three_count`, `test_a_group_the_app_did_not_produce_is_a_miss` |
| never reads a KRI path | `test_a_kri_or_private_path_is_refused`, `test_the_guard_never_touches_the_custody_directory`, `test_the_builder_opens_only_the_files_it_was_given`, `test_the_guard_does_not_trip_on_this_branch_or_the_public_corpus` |

The custody guard (`assert_public_path`) is **lexical**: `os.path.abspath` normalises
without touching the filesystem, so clearing or refusing a custody path never stats,
lists or opens it. A guard that had to look inside the directory to clear a path would
undercut the very claim this file makes. It refuses any path with a component
`egyptology-private-kri` or `kri`, and the component *pair* `data/private`. The pair
form is deliberate: a first draft refused any `private` component and the test suite
caught that macOS puts every temporary directory under `/private/var/folders/…`. It is
a tripwire against the pre-registered custody location, not a secret scanner — it
knows where a file sits, not what it holds.

## Freeze statement

**B-freq was implemented, unit-tested and committed before any KRI content was
opened.** Commit `61fc30b` was made at 2026-10-26 08:37:08 +01:00.

The sequence, stated precisely because the margin matters:

* The KRI files arrived 2026-10-26 at about 07:43 local time — that is, **before** this
  commit. They were moved unopened into `~/egyptology-private-kri/` (§4b custody) with
  sha256 manifests, and only their *format* was inspected: scanned page images with no
  text layer. No transliteration, no reading and no line of KRI content was read.
* This baseline was then built and committed. Neither the agent that wrote it nor any
  process it ran opened, listed, read or stat'ed the custody directory; the build reads
  `data/processed/examples.csv` and nothing else outside its own output directory, which
  `test_the_builder_opens_only_the_files_it_was_given` asserts by recording every file
  opened.

Arrival is therefore earlier than the freeze; *opening* is not. §4e's precondition is
about what has been seen, and nothing had been. The custody facts in the first bullet
(unopened move, manifests, image-only format) are the lead's attestation and are
recorded here as such — the agent that wrote this file was forbidden to verify them,
because verifying them would have meant touching the very directory the rule protects.

If any part of the rule, the keys, the tie-break or the scorer changes after this
point, the baseline is retired and endpoint G reverts to exploratory, exactly as §4e's
"any change after seeing results retires the set" requires.

## Still to be decided when 4e material exists

Nothing in this file depends on it, but the lead should note:

* The declaration file (`~/egyptology-private-kri/declaration.csv`) fixes each line's
  input modality and endpoint before any run, and its sha256 is committed first (§4d).
* The §4e exclusion manifest, including every 4d line and its passage, is committed
  before the first endpoint-G run.
* The power floor is about 150 endpoint-G lines, judged separately from endpoint R,
  with Holm across the family of two. Below it, G is reported "uninformative" and still
  counts in the family.
* `bfreq_table_all.csv` is rebuilt — and this document amended with the new corpus
  sha256 and table sha256 — if `examples.csv` changes before the run (part 1 cleanup
  and the part 3 PT admission both change it). The rule, the keys and the tie-break do
  not change; only the counts do.
