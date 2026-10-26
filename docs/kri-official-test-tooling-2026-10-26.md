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
| `tests/test_kri_overlap.py`, `tests/test_kri_segment_mapping.py`, `tests/test_kri_declaration.py`, `tests/test_kri_exclusion_manifest.py`, `tests/test_kri_stats.py`, `tests/test_run_kri_endpoints.py` | 136 tests (29 + 22 + 23 + 25 + 22 + 15), synthetic fixtures only |

The frozen B-freq files (`scripts/bfreq_baseline.py`, `scripts/build_bfreq_table.py`,
`tests/test_bfreq_baseline.py`) are **not touched**; `tests/test_kri_bfreq_freeze.py`
still passes (23 tests), so the freeze record's hashes still hold.

---

## How to run it

### 1. Overlap-check the lines (§4a, §4d)

```bash
~/venvs/egyptology/bin/python -I scripts/check_overlap.py \
    --lines ~/egyptology-private-kri/lines.csv \
    --examples data/processed/examples.csv \
    --manifest docs/kri/exclusion-manifest.csv \
    --output ~/egyptology-private-kri/overlap-report.csv
```

`--lines` is the one argument that may point into custody. The report holds line
ids, labels, the predicates that fired, corpus witnesses and Jaccard values — never a
line. `--private-dir DIR` adds `standrews.csv` to the gate corpus G and records its
sha256.

A line is run only if it is labelled `new` **and** the manifest does not already
exclude it. `contained` and `partial` lines are reported as "found", never as "read".

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
and the citation. The hash is taken over a canonical form (`strict_reading_key`, or
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
    --out ~/egyptology-private-kri/run-<date>
```

The private **lines** file carries, per line: `line_id`, `glyph_input` (what is
pasted into the app, as received), `gold_groups` (Camilla's word division, as glyph
groups separated by spaces), `gold_reading` (one reading per gold group) and
`query_transliteration` (endpoint R's input). The **judgements** file carries
`line_id, app_success, baseline_success` — endpoint R's binary outcomes from
Camilla's blind judging, which no script can produce.

The driver stops rather than improvises. It refuses to run at all if the
declaration is invalid, if `--examples` is not the declared corpus sha256, if HEAD is
not the declared commit, or if any declared line is missing from the overlap report
or is not runnable. It records — and fails the run on — any line whose app output is
not the same sign string as its gold division, and any endpoint-R line with no
judgement. Outputs: `endpoint_g_lines.csv`, `endpoint_r_lines.csv`, `summary.json`,
`summary.md`; ids, counts and numbers only, but KRI-derived, so they live in custody.

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
5. **"The app's top 3 for that group"** is frozen as what the app's own sign table
   shows: the chosen (Viterbi) reading first, then that group's remaining candidates
   in frequency order. Measuring anything else would measure a view no reader sees.
6. **A mis-assembled line is a failure, not a zero.** If the app's output is not the
   same sign string as the gold division, the driver records the line with its reason
   and fails the run. Scoring it would compare two different lines.
7. **Endpoint R with no judgements** is `n = 0`, `p = 1`, uninformative — and still a
   member of the Holm family of two, exactly as §4e says an underpowered endpoint is.

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
