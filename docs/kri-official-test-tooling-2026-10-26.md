# Tooling for the official (pre-registered) KRI test — 2026-10-26

Branch `kri-official-prep-2026-10-26`, cut from `ac9158a` and merged with the frozen
B-freq baseline branch `kri-baseline-2026-10-26`.

This is the machinery `docs/plan-data-cleanup-2026-10-26.md` §4 asks for, built
before any of Camilla's readings arrive, so that nothing has to be invented once
results are in sight. Everything here was written and tested against **synthetic**
fixtures: no file in this branch has read `~/egyptology-private-kri/`, the KRI PDFs,
the real corpus or any non-redistributable data.

Nothing here produces an endpoint-G *confirmation* number. The B-freq freeze record
(`docs/kri-bfreq-baseline-2026-10-26.md`) explains why, and the rule is enforced in
code — see **Eligibility** below.

---

## What exists

| File | What it is |
|---|---|
| `scripts/kri_overlap.py` | §4a's predicates C1–C4 / P1–P3, the label precedence, the evidence types |
| `scripts/check_overlap.py` | the §4a command line, the custody boundary, and the dev/gate fixture runner |
| `tests/fixtures/overlap_dev_corpus.csv`, `tests/fixtures/overlap_dev_v1.csv` | the synthetic **dev** fixture (6 invented corpus rows, 10 labelled lines, including the exact J = 0.50 and J = 0.70 edges) |
| `scripts/kri_segment_mapping.py` | the app-segment → gold-span mapping endpoint G could not be scored without |
| `scripts/kri_declaration.py` | the §4d declaration: schema, validator, empty-template generator |
| `scripts/kri_exclusion_manifest.py` | the (B) exclusion manifest: sha256 + reference, never text |
| `docs/kri/exclusion-manifest.csv` | the manifest itself, with its first entry (the self-test passage, by reference) |
| `scripts/kri_stats.py` | the exact sign test, the Newcombe paired interval, Holm, the power floor |
| `scripts/run_kri_endpoints.py` | the driver that ties all of it together and writes the run's outputs |
| `tests/test_kri_overlap.py`, `tests/test_kri_segment_mapping.py`, `tests/test_kri_declaration.py`, `tests/test_kri_exclusion_manifest.py`, `tests/test_kri_stats.py`, `tests/test_run_kri_endpoints.py` | synthetic fixtures only (counts after the 2026-10-26 review round are in **Review round** below) |
| `tests/test_kri_tooling_freeze.py` | keeps the tooling's sha256 record below honest, as `test_kri_bfreq_freeze.py` does for B-freq |

The frozen B-freq files (`scripts/bfreq_baseline.py`, `scripts/build_bfreq_table.py`,
`tests/test_bfreq_baseline.py`) are **not touched**; `tests/test_kri_bfreq_freeze.py`
still passes (23 tests), so the freeze record's hashes still hold.

---

## How to run it

### 0. The one lines file

Both scripts read the **same** private lines file,
`~/egyptology-private-kri/lines.csv`, with the columns
`line_id, kri_reference, glyph_input, gold_groups, gold_reading, query_transliteration`
(`scripts.kri_overlap.LINES_FILE_COLUMNS`):

* `kri_reference` — `KRI <vol> <page> (line n)`; required for a confirmation line,
  since exclusion by reference needs it;
* `glyph_input` — what is pasted into the app, as received;
* `gold_groups` — Camilla's word division, as glyph groups separated by spaces; they
  must concatenate to exactly `glyph_input` (checked before anything runs);
* `gold_reading` — one reading per gold group;
* `query_transliteration` — endpoint R's input.

The overlap checker checks two views of every line — the gold reading over the glyph
input (what endpoint G reads) and the query transliteration (what endpoint R searches
with) — and labels the line by the more severe.

### 1. Overlap-check the lines (§4a, §4d)

```bash
~/venvs/egyptology/bin/python -I scripts/check_overlap.py \
    --lines ~/egyptology-private-kri/lines.csv \
    --examples data/processed/examples.csv \
    --manifest docs/kri/exclusion-manifest.csv \
    --excluded-texts ~/egyptology-private-kri/excluded-texts.csv \
    --output ~/egyptology-private-kri/overlap-report.csv
```

`--lines` and `--excluded-texts` are the arguments that may point into custody. The
report holds line ids, labels, the predicates that fired, corpus witnesses, manifest
entry ids, word offsets and Jaccard values — never a line (a P2 hit says how many
three-word runs are shared and at which word offsets of the line, never which words).
`--private-dir DIR` adds `standrews.csv` to the gate corpus G and records its sha256.

The sidecar `overlap-report.csv.json` binds the report to its inputs: the sha256 of
the lines file, the corpus, the private corpus, the manifest, the excluded texts, the
checker's own code, and the report itself, plus whether the manifest is complete. The
driver refuses a report whose sidecar does not match what it is given.

A line is **runnable** if it is labelled `new`. It is **confirmation-eligible** only
if, in addition, no manifest entry covers it by any of three routes: the canonical
hash of one of its texts; its `kri_reference` inside an entry's KRI span; or the §4a
predicates (pinned Jaccard ≥ 0.5, identical fold, containment, shared word run,
shared sign trigrams) firing against the entry's private excluded text. That last
route is what catches a subsection of an excluded passage, a near-twin, and another
edition. `contained` and `partial` lines are reported as "found", never as "read".

`excluded-texts.csv` (custody only: `entry_id, transliteration, hieroglyphs`) holds
the text of each manifest entry. Each row must hash to its entry's committed sha256,
so the private comparison text is bound to the committed manifest. The manifest is
**complete** only when no hash is pending, every `line`/`passage` reference parses as
a KRI citation, and every entry has its text; only a complete manifest can back a
confirmation run.

### 2. Declare the runs, before running anything (§4d)

```bash
~/venvs/egyptology/bin/python -I scripts/kri_declaration.py template --output /tmp/declaration.csv
# fill it in, move it to ~/egyptology-private-kri/declaration.csv, then:
~/venvs/egyptology/bin/python -I scripts/kri_declaration.py validate \
    --declaration ~/egyptology-private-kri/declaration.csv
```

`validate` prints the sha256 that §4d says must be **committed before the first
run**. One row per declared run: a line with both kinds of input is two rows (glyph
input → endpoint G, transliteration → endpoint R). One commit and one corpus sha for
the whole file; `--stage auto` throughout; no Egyptian text in any field.

### 3. Record the exclusions (§4d, §4e)

```bash
~/venvs/egyptology/bin/python -I scripts/kri_exclusion_manifest.py add \
    --manifest docs/kri/exclusion-manifest.csv --scope passage \
    --reference "KRI <vol> <page> (lines a-b), <monument>" \
    --source "KRI PDFs received 2026-10-26" --note "<why>" \
    --text-file ~/egyptology-private-kri/<file>.txt \
    --hash-basis canonical_transliteration

~/venvs/egyptology/bin/python -I scripts/kri_exclusion_manifest.py validate \
    --manifest docs/kri/exclusion-manifest.csv
```

The text file is read, hashed in place and dropped: the manifest records the digest
and the citation. Keep the same text, by entry id, in
`~/egyptology-private-kri/excluded-texts.csv` for the near-match checks; the
reference must begin with a KRI citation (`KRI II 569 (lines 3–16), …`) for
`validate --strict` to pass. The hash is taken over a canonical form (`strict_reading_key`, or
the §4a sign key), so two editions of one passage are one exclusion. `validate`
refuses any entry whose reference, source or note carries hieroglyphs or
Egyptological letters — that is how a line would otherwise leak into git.

### 4. Run the endpoints (§4d, §4e)

```bash
~/venvs/egyptology/bin/python -I scripts/run_kri_endpoints.py \
    --declaration ~/egyptology-private-kri/declaration.csv \
    --lines ~/egyptology-private-kri/lines.csv \
    --overlap-report ~/egyptology-private-kri/overlap-report.csv \
    --examples data/processed/examples.csv \
    --bfreq-table ~/egyptology-baselines/kri-bfreq-2026-10-26/bfreq_table_all.csv \
    --judgements ~/egyptology-private-kri/judgements.csv \
    [--private-dir ~/egyptology-private-kri/standrews] \
    [--excluded-texts ~/egyptology-private-kri/excluded-texts.csv] \
    --out ~/egyptology-private-kri/run-<date>
```

`--private-dir` and `--excluded-texts` must be exactly what step 1 was given (or
both absent when step 1 had neither): the report's sidecar records their sha256s and
the driver refuses a report whose digests differ (review round 2).

`--lines` is the same file as in step 1 (see step 0). The **judgements** file
carries `line_id, app_success, baseline_success` (and optionally `bm25_success`) —
endpoint R's binary outcomes from Camilla's blind judging, which no script can
produce. Each value must be one of `1/0/yes/no/true/false`; anything else, an empty
cell included, is refused before scoring rather than read as a failure.

The driver stops rather than improvises. **It refuses to run at all** if:

* the declaration is invalid, `--examples` is not the declared corpus sha256, or HEAD
  is not the declared commit;
* the overlap report's sidecar does not match the lines file, the corpus, the
  private corpus (`--private-dir`), the excluded texts (`--excluded-texts`), the
  checker code and the source of every project function it imports, or the report
  itself; or a declared line is missing from the report or
  not labelled `new` (the label is checked, not only the `runnable` flag);
* a **confirmation** line is covered by a manifest entry, has no parseable
  `kri_reference`, or the report was made without a complete manifest, or against a
  different manifest than `--manifest`;
* a declared record is missing or duplicated, an endpoint-R line has no judgement,
  a judgement is malformed or duplicated, a G line has no glyph input, a different number of gold groups and gold
  readings, or a gold division that is not its glyph input — all checked **before
  the app is called once**, so no output exists that could tempt a second evaluation;
* the B-freq table's `bfreq_header.json` does not tie it to the declared corpus, top
  3 and the frozen B-freq code; and, for a confirmation, its sha256 is not the one
  recorded (or last amended) in the freeze record;
* a confirmation line is declared together with an experimental override
  (`--build-bfreq`, `--no-lexicon`, `--top-k` other than 3).

The statistics use **confirmation lines only**. Exploratory lines are reported as
descriptive counts (k of n, W/L/ties) and never enter a p-value, an interval, the Holm
family or a `beats_baseline` flag. Below 30 confirmation lines only k of n is written —
no percentage, margin, interval or p-value. Below the power floor of 150 the endpoint
is "uninformative" and `beats_baseline` is false. **No verdict field is written** for
a run with any failed line (an unjudged endpoint-R line) or in an experimental
configuration; the counts are still written, and the exit code is 1 for a failed line.

If the app's own output drops or changes signs of a correctly divided line, the app
did not produce those groups: the line is scored with every group a miss for the
app, flagged `app_sign_mismatch`, and counted in the secondary outputs.

Secondary outputs (descriptive, outside the Holm family): G group-level hit counts,
G against B-freq restricted to Late Egyptian (`bfreq_table_late_egyptian.csv` from the
same build, sha-checked against its header), and R against BM25 when the judgements
carry `bm25_success`.

Outputs: `endpoint_g_lines.csv`, `endpoint_r_lines.csv`, `summary.json`,
`summary.md`; ids, counts and numbers only, but KRI-derived, so they live in custody.

**Not built**, and therefore not part of any run yet:

* **endpoint R's blind pack** — both systems' top 3 for each line, merged and
  shuffled, for Camilla to judge. The driver only ingests the judgements. Until a
  pack generator is built, frozen and reviewed, endpoint R cannot be run;
* **BM25's per-pool statistics** (§4e) — only BM25's paired counts are reported;
* **clustering by passage** (§4e "clustered by passage") — the sign test treats lines
  as independent units.

How the two endpoint-R statements fit (review round 2): an endpoint-R line with no
judgement is refused in preflight, before any endpoint-G prediction runs, so no
output exists. The driver's unjudged branch remains only as a defensive fallback: it
would record the line as *unjudged* (never as a loss) and make the run incomplete.

### 5. The dev fixture gate (any time)

```bash
~/venvs/egyptology/bin/python -I scripts/check_overlap.py \
    --fixture tests/fixtures/overlap_dev_v1.csv \
    --examples tests/fixtures/overlap_dev_corpus.csv
```

---

## The gate fixture: a documented command, not a built artefact

§4a's timing is explicit: the predicates and thresholds are committed now (they are),
the holdout is drawn before the part-3 filter runs, and **the gate fixture is drawn,
adjudicated and frozen after the part-3 commit**, on the gate corpus G
(`data/processed/examples.csv` at that commit, plus `standrews.csv` with
`--private-dir`). The cleanup and the Pyramid Texts admission both change that file,
so a fixture drawn today would be retired before it was ever used. Nothing of it is
built here beyond the mechanism and the synthetic dev fixture.

When part 3 is committed, the gate fixture is built like this:

1. Draw the strata §4a's table fixes — 20 Ramses positives, 10 edited real sentences,
   15 UD spread rows (5 each from `duplicate_tla_id`, `overlap_partial`,
   `unmatched_by_current_rules`, among rows **not** admitted in part 3), 10 negatives
   from `$R/ud/fixture_holdout.csv` in seed order — with the seeds fixed in the plan,
   excluding every row used in the dev fixture.
2. Have Opus and Astra each verify every predicate of every row **alone**, with their
   own scripts calling the pinned repo functions directly, never `check_overlap.py`.
   For C2 and P3, `signs` is **`scripts.bfreq_baseline.sign_key`** (`glyph_key` after
   `normalize_hieroglyphs`), not bare `glyph_key` — see decision 1 below. An
   adjudicator using bare `glyph_key` would disagree with the checker on variant
   codepoints, and gate rows would be dropped for that reason alone.
   Keep a row only where the two per-predicate tables agree exactly and the label is
   the stratum's intended one. Never relabel a row to fit; take the next seeded row.
3. Write `tests/fixtures/overlap_gate_v1.csv` with the columns the runner expects
   (`stratum, line_id, transliteration, hieroglyphs, expected_label,
   expected_predicates, witness_key, max_jaccard, corpus_sha, private_sha`), filling
   `corpus_sha` with G's sha256, and commit its own sha256 **before** the checker is
   first run on it.
4. Run the gate:

   ```bash
   ~/venvs/egyptology/bin/python -I scripts/check_overlap.py \
       --fixture tests/fixtures/overlap_gate_v1.csv \
       --examples data/processed/examples.csv \
       [--private-dir data/private]
   ```

   The runner refuses to score the fixture against any corpus but the one its
   `corpus_sha` records, because §4a retires a fixture whose corpus changed.

**No tuning on the gate fixture.** A failure is fixed against the dev fixture; the
failed gate fixture is retired to dev and a new one is drawn with a new seed.

Camilla's Ahmose / Urk. IV line is a separate private fixture (`contained` with the
private dir, at least `partial` without), checked against the same predicates.

---

## Eligibility: what these PDFs can and cannot support

From the B-freq freeze record, enforced by `scripts/kri_declaration.py`:

> Code was committed at 08:37:08 +01:00 and the hash record at 08:40:24, after the KRI
> PDFs were received around 07:43. … This is a freeze after receipt and before
> reported content inspection, not the pre-arrival freeze §4e requires. Consequence:
> endpoint G on lines drawn from these PDFs is exploratory under §4e and yields no
> confirmation number for experts; endpoint R is unaffected.

So: a declaration row with `endpoint = G` and `material_received` on or before
`2026-10-26` **cannot** be declared `confirmation`; the validator refuses it and says
why. A G confirmation needs a separately eligible cohort whose material arrives after
the freeze. Endpoint R is unaffected — its baseline is protocol (B), not B-freq.

Below about 150 lines of an endpoint, that endpoint is reported "uninformative" and
still counts in the Holm family of two. Below 30 lines, §4d's wording applies: case
by case, "k of n", no percentages, no intervals, no claim beyond "on these lines".

---

## What still needs Camilla

1. **Her passages** (§4c): 3–5 to start with, each with her transliteration (input and
   gold), the hieroglyphs, the KRI reference, and whether her transliteration is
   diplomatic or normalised. Without the hieroglyphs there is no endpoint-G input;
   without her gold word division there are no gold groups to score against.
2. **Her gold word division per line**, as glyph groups. The mapping aligns the app's
   segmentation to it by character offset, so the groups must concatenate to exactly
   the glyph input.
3. **Her blind relevance judgements** for endpoint R: both systems' top 3 shown
   merged and shuffled, one binary per side per line. No script can produce these,
   and the driver records an unjudged line as unjudged rather than as a loss.
4. **Whether ≥ 100 further lines could be supplied**, for §4e — and, for a G
   confirmation, lines whose material arrives after the freeze.

---

## Decisions taken where the spec was ambiguous

Each of these is also stated in the code that implements it.

1. **§4a `signs`.** §4a says "the same definition as `glyph_key` … imported, not
   re-written". The checker imports exactly that function, but through
   `scripts.bfreq_baseline.sign_key`, which runs the app's `normalize_hieroglyphs`
   first — as the frozen B-freq baseline already does. Bare `glyph_key` would not fold
   a variant codepoint (TLA's Z15B against the corpus's Z2 — the mismatch in Camilla's
   first trial), so a line the tool has already seen could be labelled `new`. The
   error that matters here is the missed overlap. Any C2/P3 hit that needed the
   normalisation is marked `normalised-only` in the evidence, so the deviation is
   visible in every report.
2. **§4a's extra folds.** "the yod ꞽ/j/i and spacing-before-`=` folds the tool uses"
   turn out to be inside `search_fold` already; a test pins that, so losing either
   would fail the suite. `extra_fold` therefore adds only a whitespace collapse, and
   anything it alone sees is reported as the separate `EXTRA_FOLD` evidence type,
   which never changes a label.
3. **Repeated identical gold groups.** The B-freq freeze record lists "repeated
   groups" beside merges and splits as a miss for the app; §4e itself lists only "does
   not produce, merges or splits"; and the mapping is required to align by character
   offset. Offsets make repetition unambiguous, so the hazard the phrase names (a
   string-keyed mapping pairing the wrong segment, or consuming one segment twice) is
   removed by construction — the mapping guarantees one-to-one consumption. A
   correctly aligned repeat is therefore **not** punished; every repeat is counted and
   reported per line (`repeated_sign_strings`). The rule is frozen in
   `REPEATED_GROUP_RULE`; changing it is a code change and a re-freeze.
4. **Alignment keeps placeholders.** §4a's `signs` deletes TLA's `<g>…</g>`
   placeholders, which is right for B-freq's lookup (it cannot key such a group) and
   wrong for an alignment, where deleting a character would give a placeholder-only
   gold group a zero-length span and shift every later group. Lookup uses `signs`;
   alignment uses `normalize_hieroglyphs` with spaces removed.
5. **"The app's top 3 for that group"** is a frozen operational definition in the
   order of the app's own sign table: the chosen (Viterbi) reading first, then that
   group's remaining candidates in frequency order, truncated to three. The UI lists
   more alternatives than three, so this is not a copy of the screen; it is the first
   three of the order a reader of the app sees. Candidates come from
   `most_common(5)`, so ties follow corpus row order, fixed once the corpus sha is
   pinned.
6. **Input errors are refused; app errors are misses** (revised in the review
   round). A gold division that is not its glyph input is a data-entry error and is
   refused before the app is called once. If the app's own output then drops or
   changes signs, the app did not produce those groups — §4e's miss — and the line is
   scored with every group a miss for the app, flagged `app_sign_mismatch`.
7. **Endpoint R with no judgements** is `n = 0`, `p = 1`, uninformative — and still a
   member of the Holm family of two, exactly as §4e says an underpowered endpoint is.
   *Partial* judgements do not quietly shrink n: a missing judgement makes the run
   incomplete, and an incomplete run gets no verdict.
8. **Newcombe method 10 with phi's continuity correction** (corrected in the review
   round): when `ad − bc > 0` the correlation's numerator is `max(ad − bc − n/2, 0)`.
   The first version lacked it, so its intervals were too narrow. Published worked
   values are now pinned in `tests/test_kri_stats.py`.
9. **Exploratory execution is separate from permanent exclusion.** Every line seen
   in §4d goes into the (B) manifest *and* is run there, exploratorily. So an excluded
   `new` line is `runnable`; it is never `confirmation_eligible`.

---

## What the lead must still do

* **Fill the manifest's pending hash.** `docs/kri/exclusion-manifest.csv` holds one
  entry — the exploratory self-test passage, `KRI II 569 (lines 3–16), Karnak Great
  Hypostyle Hall` — by reference only, with `sha256 = to-be-filled-by-the-lead`.
  Nothing in this branch opened the passage, so nothing here could hash it. Fill it
  with `--text-file` once the text is at hand, and add the rest of §4d's permanent
  exclusions (every line seen, its whole passage, and every other edition of the same
  text) the day material arrives.
* **Create the declaration** from the template, validate it, and **commit its sha256
  before the first run**.
* **Send §4c's email** and obtain the gold word divisions and the blind judgements.
* **Draw and freeze the gate fixture** after the part-3 commit, with two independent
  adjudicators, per the recipe above. There is no gate fixture yet, so the §4a gate
  has not been passed — only the dev fixture has.
* **Rebuild the B-freq table** and amend the freeze record's corpus/table sha256s if
  `examples.csv` changes (part 1 and part 3 both change it). The rule, the keys, the
  tie-break and the surface rule do not change; only the counts do.
* **Decide nothing from an exploratory G number.** No G number from the 2026-10-26
  PDFs goes to experts.

---

## Review round 2026-10-26 (Opus + Astra) — what changed

Two independent reviews (Opus: `merge_after_small_fixes`; Astra, gpt-6-astra high:
`do_not_merge`) were applied in full before any KRI material was run. Where they
disagreed on a judgement call the more conservative option was taken; the commit
message lists each item. In short:

* **Newcombe interval**: phi's continuity correction added (method 10 proper); the
  published worked values are pinned.
* **Exact Holm**: exact p-values against exact thresholds, strict `<` as the
  pre-registration words it.
* **Eligibility**: only eligible confirmation lines enter the test, the interval, the
  Holm family and the flags; exploratory lines are descriptive counts.
* **No text leaks**: P2 reports counts and word offsets, never words; declaration and
  manifest errors name rows and fields, never contents.
* **Overlap gate**: one shared lines file; both views of a line checked; the report
  bound to its inputs by a sidecar; the label checked, not only `runnable`.
* **Exclusions**: by hash, by KRI reference and by the §4a predicates against private
  excluded texts bound to the committed hashes; confirmation needs a complete
  manifest; exploratory execution separated from permanent exclusion.
* **Configuration**: the B-freq table tied to its header (corpus, top 3, frozen code)
  and, for a confirmation, to the freeze record's sha256; experimental overrides
  refused for confirmation lines and never given a verdict.
* **Records**: everything checked before the app runs; a gold division that is not
  its glyph input refused; app-side sign loss scored as misses; malformed or duplicate
  records refused; an incomplete run gets no verdict.
* **Small n**: counts only below 30 lines; `beats_baseline` false below the power
  floor.
* **Secondaries**: Late-Egyptian B-freq and group-level hits for G, BM25 counts for R;
  the blind pack, BM25 per-pool statistics and passage clustering are listed above as
  not built.
* **Freeze**: the tooling's sha256s are recorded below; the repeated-group rule is
  appended as a dated amendment to the B-freq record; §4a's `signs = sign_key` is
  appended to the plan for the gate adjudicators.

## Review round 2 2026-10-26 (Astra re-check) — what changed

* **Provenance**: the driver checks the sidecar's `private_sha256` and
  `excluded_texts_sha256` against the `--private-dir` and `--excluded-texts` it is
  given; a report made with other (or without those) inputs is stale and refused.
* **Checker fingerprint**: `checker_sha256` now also covers the source of every
  project function and module constant the checker modules import, closed
  transitively (`check_overlap.dependency_sources`: the app's `search_fold`,
  `strict_reading_key`, `loose_reading_form`, the §4a `sign_key`, the tokeniser, the
  Jaccard, …), so a change to the normalisation or tokenisation invalidates old
  reports.
* **Edition links**: every KRI span in a reference is parsed (`parse_kri_spans`), not
  only the leading one. An `edition` entry relates references, by further KRI spans
  or by naming the excluded entry's id; a line in any span of a linked group is
  excluded by every entry in it, so a second edition of an excluded passage is never
  confirmation-eligible. `validate --strict` refuses an edition entry that relates no
  references, and any validation refuses one that names a missing entry id.
* **No raw fields in messages**: manifest validation names an entry by its position
  (`entry N`) only; a rejected entry's id, reference and other fields are never
  printed. The manifest header is not echoed either.
* **Missing judgements**: refused in preflight, before any endpoint-G prediction.

Re-frozen: the three changed files have new rows appended below. No KRI scoring run
is recorded in this document before these rows (endpoint R's blind pack is still not
built); the lead confirms that before the first declaration.

## The frozen tooling

Recorded at the review-round commit, before any KRI scoring run. Enforced by
`tests/test_kri_tooling_freeze.py`: a change to any of these files fails the suite
until a new row for it is **appended** here (the last row per file is the one in
force), with a note on whether any KRI result had been seen.

| File | sha256 |
|---|---|
| `scripts/check_overlap.py` | sha256 `34c4452eaf71aef794edeb0ff9f2166473a3033492007b29b08b43a4e8d62778` |
| `scripts/kri_declaration.py` | sha256 `a489b6cc9433a22f23e764bd093a5e09abf6e8b6afb0c51ee1185882193bdeb4` |
| `scripts/kri_exclusion_manifest.py` | sha256 `ecfb2a78d42ab1fc6dad598459414f968dbe8f07eeee8c209c4ac9485a06b9b8` |
| `scripts/kri_overlap.py` | sha256 `72e1141b2bb865ee4f133edea8057b456a965c4ae7258b7895f3551f16ac71a1` |
| `scripts/kri_segment_mapping.py` | sha256 `6c9e7d1358ed19954806226d524e6a83a17be48dcf97c708a5d590e12f1a5833` |
| `scripts/kri_stats.py` | sha256 `5f8e5e06380eb17374897b53523601d34326738ff57b379fca2ff8d3416123ca` |
| `scripts/run_kri_endpoints.py` | sha256 `f29835c91c6950967678960175b2fbde0e911f1a9523ce8f3166ad5cc39b5b3b` |
| `scripts/check_overlap.py` | sha256 `3b4f40897700ea9d7d46610cd320fcc894e58eed4c4141e2902a5b96f7ba0632` |
| `scripts/kri_exclusion_manifest.py` | sha256 `65f55246ed9f9ff164aad85da7850e3d7031108914c5e8422d7b1e8dc3ba5da0` |
| `scripts/run_kri_endpoints.py` | sha256 `185b9f9c15637f16e264cae77ae530c98d7676ad52529bad37c434c87c7afe52` |
