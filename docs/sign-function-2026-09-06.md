# Item C — sign-function segmentation and reading (2026-09-06)

Nederhof's third criticism: the resegmentation lattice is a unigram over attested
sign groups and knows nothing about what a sign *does*. Camilla's core want: readings
where the corpus has no parallel. Two pre-registered steps, each with its own decision
rule. **One ships, one is a null.**

**Result in two lines.**

* **C1 ships.** An adjacent-glyph boundary bigram with function-class back-off,
  `SegmentationWeights.boundary_model = 1.0`. Held-out unspaced boundary F1
  **0.923 → 0.939**, exact **0.539 → 0.579**; scrambled **0.937 → 0.946**. On real St
  Andrews input the end-to-end unspaced reading token F1 goes **0.591 → 0.603**. The
  error class the diagnosis named — a boundary cut *inside* a gold group the training
  split never saw — falls **1,793 → 1,431**.
* **C2 is a null.** Reading an unattested group sign by sign from the sign-function
  tables produces the gold reading in **12.2%** of the cases it covers, even letting an
  oracle pick from the whole candidate list; the glyph-similarity fallback it would
  have replaced is right **28.4%** of the time. The code ships switched off.

Worktree off `main` at `3513d19`. Interpreter
`/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus 130,472 rows.

---

## 1. The pre-registration, quoted

From `ROADMAP.md`, "### Item C — sign-function segmentation and reading —
pre-registered 2026-09-06 (Opus 5 worker)":

> **C1 — boundary model with function-class back-off, inside the lattice.**
>
> 1. Classes: fold Nederhof's labels to {phon, log, det, phondet, typ}; "logogram or
>    determinative" → {log, det}; "phonogram or phonetic determinative" → {phon,
>    phondet}; uncovered → {unk}. `P(c | sign)` uniform over the sign's classes.
>    Training data = the segmentation eval's training split (seed 7); **dev = the last
>    10% of that shuffled training split**, test = the eval's test split, untouched for
>    selection.
> 2. Boundary statistics from training streams: per adjacent sign pair (a, b) counts of
>    boundary / no boundary; per class pair (c1, c2) expected counts under the soft
>    class assignment; global prior. Estimate `P(boundary | a, b) = (n_b(a,b) + α ·
>    P_class) / (n(a,b) + α)` with `P_class = Σ P(c1|a) P(c2|b) P(boundary | c1, c2)`
>    (additive smoothing 0.5 toward the global prior), **α = 1, fixed, not tuned**.
>    Unseen pair → `P_class` alone.
> 3. Lattice term, exact under the semi-Markov DP: `λ_b · [ log P(boundary | s_{i-1},
>    s_i) at every placed boundary i > 0 + Σ log P(no boundary | s_{k-1}, s_k) over the
>    internal positions k of every span ]`. All other terms unchanged; **κ (6.0),
>    lexicon weight (0.2), quadrat_crossed (1.0) are not re-tuned**.
> 4. Selection: `λ_b ∈ {0.25, 0.5, 1.0, 2.0}` by highest **dev** unspaced F1 subject to
>    paste 8/8 (auto). Ablation at the chosen λ_b: sign-bigram only (no class back-off:
>    unseen pair → global prior) — this isolates what the function table itself
>    contributed.
> 5. Decision: ship (default = chosen λ_b) iff **test unspaced F1 > 0.923 strictly**,
>    scrambled F1 ≥ 0.937, paste 8/8, and the item B St Andrews reading token F1
>    (unspaced) is not more than 0.010 below 0.591. Otherwise `λ_b = 0.0` (code
>    present, off), null reported.
>
> **C2 — function-composed readings for unattested groups.** […] 4. Decision: ship iff
> composed accuracy on the positions it covers is **strictly higher** than fallback on
> the same positions, with **≥ 200** such positions, and `acc_ambiguous_context` at the
> largest size is not lower than the pristine baseline the worker records first.
> Otherwise the source kind stays in the code but disabled (`use_composed=False`), null
> reported. **PASTE_008** […] must still pass.

C2 was **amended by the lead on 2026-09-06** before any measurement under the amended
form; the amendment and what had already been run under the frozen form are set out in
§5.

---

## 2. Baselines, recorded on the pristine tree before any change

| measurement | command | result |
|---|---|---|
| segmentation, unspaced | `run_segmentation_eval.py` | P 0.931 R 0.915 **F1 0.923** exact 0.539 |
| segmentation, scrambled | same | P 0.928 R 0.946 **F1 0.937** exact 0.599 |
| segmentation, as pasted | same | P 0.612 R 0.700 F1 0.653 exact 0.048 |
| reading, largest size | `run_reading_model_eval.py --exclude-duplicates --sizes 0` | `acc_ambiguous_context` **0.8803**, `acc_fallback` **0.2835**, `fallback_predictions` **1485**, `unseen_signs` **9445** |
| St Andrews, unspaced, hints on | `run_format_hint_eval_standrews.py --constant 1.0` | P 0.568 R 0.617 **F1 0.591** exact 0.026 |

All three match the pre-registration's expected values exactly (0.923/0.539,
0.937/0.599, 0.591). Split sizes: train 53,553 / test 5,482 rows (5,298 sentences
scored); reading eval 59,504 aligned sentences, 47,603 train / 11,019 test.

---

## 3. The sign-function inventory (step 1)

`app/services/sign_functions.py`, one loader `load_sign_functions()`, returning per
sign a folded class set and its ordered rows.

**The five-class fold.** Nederhof's seven labels; a label naming two possibilities
folds to both, and the uncertainty stays soft rather than being resolved by fiat:

| Nederhof's label | classes |
|---|---|
| logogram | `{log}` |
| determinative | `{det}` |
| logogram or determinative | `{log, det}` |
| phonogram | `{phon}` |
| phonetic determinative | `{phondet}` |
| phonogram or phonetic determinative | `{phon, phondet}` |
| typographic | `{typ}` |
| *(sign in neither table)* | `{unk}` |

`P(class | sign)` is uniform over the set: the tables carry no frequencies and
inventing them would be tuning dressed as data.

**The supplement**, `data/processed/sign_functions_supplement.csv`, exactly the lead's
table: **13 rows over 11 signs**, every row `source_note = "project supplement"`. Z7
𓏲 phonogram *w*; Z2 𓏥, Z3 𓏪, Z3A 𓏫 typographic (plural strokes); V31A 𓎢 phonogram
*k*; N35A 𓈗 phonogram *mw* + determinative (water); N17 𓇿 logogram *tꜣ* +
determinative (land); Z6 𓏱 determinative (death, enemy); U7 𓌻 phonogram *mr*; Aa15
𓐝 phonogram *m*; D6 𓁻 determinative (actions of the eye). Every codepoint was checked
against Nederhof's own `signunicode.xml` and all eleven agree. None of the eleven is a
sign his table already covers.

One notational point for the record: Nederhof writes the Gardiner variants lower-case
(`Z3a`, `V31a`, `N35a`), the supplement upper-case as the pre-registration named them.
Nothing joins on that column — every lookup is by the Unicode character — so the two
conventions sit side by side without colliding.

**Licence.** `DATA-LICENSE.md` gains a section, "This project's supplement to it
(`sign_functions_supplement.csv`, CC BY-SA 4.0)", and a row in the per-file table. The
supplement is **not** Nederhof's and is not covered by his grant: source is the
Gardiner sign list, licence CC BY-SA 4.0, this project's own work.

**Tests.** `tests/test_sign_functions.py`, 12 cases: the fold is total over every label
in either shipped table and shaped as above; `class_distribution` is uniform and sums
to 1; an uncovered sign and a TLA `<g>` placeholder give `{unk}`; an absent table
degrades to `{unk}` rather than raising; the supplement is byte-for-byte the
pre-registered thirteen rows (retyped in the test, so the CSV is checked against the
decision and not against itself); its codepoint column matches its characters; it adds
only signs Nederhof does not cover; Nederhof's rows keep their attribution.

---

## 4. C1 — the boundary model

`app/services/boundary_model.py`. Statistics are read off a fitted `ReadingModel`
rather than a DataFrame — a group's token count gives its internal (no-boundary)
adjacencies and `sign_context`, whose keys are (previous group, group) pairs, gives the
boundary ones. They are the same training rows, and it means every caller that can
build a `Segmenter` can build this.

On the whole training split: **42,842 distinct adjacent sign pairs, global
P(boundary) = 0.3097.**

### 4.1 The λ_b sweep, on dev

Dev = the last 10% of the shuffled training split, fitted on the first 90%. Twins were
excluded by the rule `split()` already applies between train and test: **438 of the
5,356 dev rows were removed** because their exact sign string also occurs in the
fitting rows, leaving 4,918 rows / 4,746 scored sentences. The test split was not
looked at during selection.

| λ_b | dev unspaced F1 / exact | dev scrambled F1 / exact | expert paste gate |
|---|---|---|---|
| 0 (off) | 0.921 / 0.548 | 0.937 / 0.608 | 8/8 |
| 0.25 | 0.928 / 0.560 | 0.940 / 0.618 | 8/8 |
| 0.5 | 0.932 / 0.572 | 0.942 / 0.628 | 8/8 |
| **1.0** | **0.937 / 0.582** | 0.945 / 0.642 | **8/8 ← chosen** |
| 2.0 | 0.936 / 0.576 | 0.944 / 0.636 | **7/8 — fails PASTE_005** |

1.0 is both the dev argmax and the largest candidate that keeps the gate, so criterion
and constraint agree. At 2.0 the boundary bigram outvotes the corpus evidence on
PASTE_005 and reads 𓈖𓏏𓈖𓏥 as the once-attested `(ꞽ)ntn` instead of the 3,039× + 19×
split `n =tn` — the same failure shape item B saw at its own 2.0.

### 4.2 Held-out test at λ_b = 1.0, and the ablation

5,298 sentences, 40,468 gold groups of which 4,320 (10.7%) are unattested in training.

| | unspaced F1 / exact | scrambled F1 / exact |
|---|---|---|
| baseline (λ_b = 0) | 0.923 / 0.539 | 0.937 / 0.599 |
| **λ_b = 1.0, class back-off ON (shipped)** | **0.939 / 0.579** | **0.946 / 0.635** |
| λ_b = 1.0, class back-off OFF (ablation) | 0.938 / 0.578 | 0.946 / 0.635 |

### 4.3 Boundary errors by whether the gold group was attested

The aggregate F1 must not hide whether the unseen-word problem moved. Unspaced input,
same 5,298 sentences. "Attested" here means attested as a whole group in the **corpus**
training split (`ReadingModel.sign_reading`); the Helsinki lexicon's groups are not
counted, so this is the same population the diagnosis used.

| | missed, between two attested | missed, touching an unattested | spurious, inside an attested | **spurious, inside an unattested** |
|---|---|---|---|---|
| baseline (λ_b = 0) | 2,638 | 351 | 601 | **1,793** |
| λ_b = 1.0, back-off ON | 2,028 | 287 | 559 | **1,431** |
| λ_b = 1.0, back-off OFF | 2,037 | 291 | 555 | **1,428** |

Scrambled input, same three rows: missed 1,728 / 177, 1,384 / 165, 1,386 / 168;
spurious 658 / 1,934, 610 / 1,708, 609 / 1,714.

The targeted error class moves: **−362 spurious cuts inside an unseen gold group
(−20.2%)**, alongside −610 missed boundaries between two attested ones. The class
back-off changes neither (1,431 vs 1,428).

A note on comparing these to the pre-registration's diagnosis, which reported 7,029
spurious and 6,351-inside-unattested: that diagnosis was measured with the segmenter's
lexicon groups switched off, deliberately, as an upper bound. These numbers are from
the shipped configuration, lexicon on, which is why the absolute counts are about a
third of the size. The proportion is the same story: 75% of the baseline's spurious
cuts fall inside a gold group never seen whole.

### 4.4 Real input: St Andrews

1,701 lines with glyphs and a reading, memorisation guard passed (1 line dropped, 0 of
the rest in the public corpus), reading measured end to end.

| shape / arm | baseline (λ_b = 0) | λ_b = 1.0 |
|---|---|---|
| unspaced, hints on | F1 **0.591** | F1 **0.603** |
| unspaced, hints off | F1 0.587 | F1 0.598 |
| as rendered, hints on | F1 0.581 | F1 0.581 |
| as rendered, hints off | F1 0.577 | F1 0.578 |

The quadrat hints keep their own effect on top of the boundary model (unspaced paired
delta +0.0048, 142 lines better / 47 worse), so the two terms are not substituting for
one another.

### 4.5 Decision C1.5

| condition | required | measured | |
|---|---|---|---|
| test unspaced F1 | > 0.923 strictly | **0.939** | ✅ |
| test scrambled F1 | ≥ 0.937 | **0.946** | ✅ |
| expert paste gate | 8/8 auto | **8/8** | ✅ |
| St Andrews unspaced token F1 | ≥ 0.581 | **0.603** | ✅ |

**Ship. `SegmentationWeights.boundary_model = 1.0` is the default.** The sweep, the
held-out numbers and the ablation are recorded in that field's comment.

### 4.6 What Nederhof's table contributed — the ablation paragraph

**Almost nothing measurable, and the honest reading is that the gain is the sign bigram
alone.** At the same λ_b, removing the function-class back-off entirely — so an unseen
adjacent sign pair falls to the global boundary rate of 0.3097 instead of to a
class-conditional estimate — costs **0.001 unspaced F1** (0.939 → 0.938) and 0.001
exact, and changes the scrambled scores not at all. On the error class the table was
supposed to help with, spurious cuts inside an unseen gold group, the ablation is
*marginally better* (1,428 vs 1,431). Of the +0.016 F1 that item C1 buys, the adjacent-
sign bigram contributes ≈ +0.015 and the sign-function table ≈ +0.001.

Two reasons, both measurable in the data rather than inferred. First, **98.2% of the
adjacent sign pairs in held-out text were already seen in training**, so the back-off
level is consulted for fewer than 2% of positions; with α = 1 it is also outvoted by
the pair's own counts everywhere it *is* consulted more than once. Second, **only 14.9%
of corpus sign tokens have a single function class**, so `P(c | sign)` is a broad
distribution and `P(boundary | c1, c2)` averages toward the global prior — which is
what the ablation replaces it with. The table is not wrong; it is being asked a
question the corpus can already answer.

That is worth saying plainly to Nederhof, because his criticism was correct about the
*model* and this measurement locates where the fix actually came from. Knowing what a
sign does turned out to matter far less than knowing which signs are seen next to each
other — on a 130k-row corpus. On a small or unfamiliar corpus, where the 98.2% pair
coverage would collapse, the class back-off is the term that would carry the load, and
it is in the code and tested for exactly that reason.

---

## 5. C2 — composed readings: a null result

### 5.1 The amendment, and what had already run when it arrived

The lead amended C2 mid-implementation. **What had already been run under the frozen
rules, kept and reported here:** the composition engine, its wiring into
`predict_sequence_scored`, its tests, and one measurement — `run_reading_model_eval.py
--exclude-duplicates --composed --sizes 5000`, which reported composed accuracy
**0.0305** over 459 positions and, on the 331 positions where the pristine model used
its fallback, **fallback 0.2659 vs composed 0.0332 (−0.2326)**. A diagnostic dump of
those 331 positions was also taken. Both used the reading eval's held-out rows at the
5,000-sentence size; both predate the amendment and the "dev only" instruction that
came with it. **No post-amendment diagnostic touched a held-out test row.** Those two
runs also predate the constant-shadowing bug described below, so they measure what they
say they measure — the frozen rules, unfiltered — and their verdict (composed 0.033 vs
fallback 0.266) is the same verdict the amended Stage 1 reaches.

The amended rules: standalone rows only (`group` column empty); drop rows Nederhof
hedges (`certain=false`) and rows qualified plural / dual / numeral, ignore `period`
and `texttype`; **abstain** on a group holding any sign the tables do not describe
standalone, rather than silently dropping that sign; deduplicate before the cap of 24.

**Rows the filters exclude, of 1,457 in the two tables:** 94 scoped to a sign
combination, 9 numeral, 7 `certain=false` — **110 excluded, 1,347 kept**, and 779 of
791 signs keep at least one standalone row. (The 6 `plural` and 2 `dual` rows all also
carry a `group`, so they are inside the 94.)

### 5.2 Stage 1 — can composition generate the right reading at all?

`scripts/run_composition_dev_eval.py`. Dev = the last 10% of the reading eval's own
training rows (4,761 sentences; 0 twins removed — that split is positional, not
shuffled, and the tail happens to share no exact sign string with the fitting rows),
fitted on the first 90%. Gold word boundaries, so this measures composition and not
segmentation. **778 positions** the corpus and the Helsinki lexicon both fail to read.

| rules | coverage | oracle recall, exact / lenient | top-1 exact | candidates mean / median |
|---|---|---|---|---|
| as pre-registered (amended filters) | 0.6632 (516/778) | 0.0581 / 0.0930 | 0.0058 | 12.5 / 8 |
| + revision 1, phonetic complement | 0.6632 | 0.1008 / 0.1570 | 0.0174 | 14.3 / 12 |
| + revision 2, optional logogram | 0.6632 | **0.1221 / 0.1764** | **0.0349** | 19.3 / 24 |
| the same, cap raised 24 → 500 *(diagnostic)* | 0.6632 | 0.1880 / 0.2655 | 0.0349 | 89.4 / 36 |

"Oracle recall" is the share of *covered* positions whose gold reading appears anywhere
among the candidates — the ceiling no scoring change can beat. "Lenient" is item B's
fold (NFC, lowercase, delete `. ( ) [ ] { } ⸢ ⸣`). The shipped-configuration row and 400
worked dev examples are frozen in `data/benchmarks/composition_dev_eval.csv` and
`data/benchmarks/composition_dev_examples.csv` (corpus-derived, so CC BY-SA 4.0 under
the existing `data/benchmarks/*.csv` row in DATA-LICENSE.md).

**Two revisions, both made on dev, both named after the failure pattern they answer:**

* **Revision 1, phonetic complement.** Egyptian writes a multiliteral together with
  uniliterals repeating its consonants: 𓄤𓆑𓂋 is *nfr*, not *nfrfr*; 𓈖𓏌 is *nw*, not
  *nnw*. The frozen rule suppressed a repetition only for the `phonogram or phonetic
  determinative` class, but complements are ordinarily plain `phonogram` rows, so every
  such spelling composed with doubled consonants — the single commonest error in the
  dev dump. A phonogram may now also contribute nothing when the multiliteral to its
  left already contains its consonants, or when they open a longer value the next sign
  could contribute. The skip is an extra choice, never a replacement, so a genuine
  gemination (ꜥm + ꜥm → *ꜥmꜥm*) stays reachable. **+0.043 oracle recall.**
* **Revision 2, optional logogram.** Y1 𓏛, the book roll, is a classifier but carries a
  logogram row (*dmḏ*), so every group ending in it composed with "dmḏ" glued on;
  A1 𓀀 did the same with "=ꞽ". A `logogram` row may now contribute nothing too,
  exactly as `logogram or determinative` already could. **+0.021 oracle recall.**

**One bug found and fixed mid-measurement, reported because it invalidated a run.**
Introducing named enumeration modes, I defined a constant `PHONDET` that shadowed the
class constant of the same name imported from `sign_functions`, which silenced every
`phonogram or phonetic determinative` row. The first pass of the revision measurements
was affected; it was re-run after the rename to `MODE_*` and the table above is the
corrected run. (The v1 row was measured before the shadowing existed and is unchanged
by it.)

### 5.3 Decision C2.4 — null, and Stage 2 is not run

The glyph-similarity fallback these readings would have replaced scores **0.2835** on
the comparable held-out positions. Composition's ceiling — an oracle allowed to pick
the right answer out of the entire candidate list — is **0.1221** at the shipped cap
and **0.1880** with the cap raised twenty-fold. Its own top choice is right **3.5%** of
the time.

Stage 2 was therefore not run, as the amendment permits: no scoring, re-weighting or
decoding change can lift a top-1 above a ceiling that is itself below the incumbent's
accuracy. Under rule C2.4 **the source kind stays in the code, disabled**
(`USE_COMPOSED_BY_DEFAULT = False`). The full paste gate is 8/8.

**PASTE_008 specifically.** It ships passing because the shipped decode never calls the
composition at all. It would also pass with the switch forced on: its two groups are
𓀂𓀅 and 𓀇𓀈, and composition **abstains on both** — 𓀅 has no standalone row in either
table (amended rule 3), and 𓀇𓀈 is two determinatives, so every path composes to the
empty string. The honest empty result the row exists to protect is preserved either
way, which is worth knowing before anyone reconsiders the switch.

**One line on the eligibility gap the lead asked for.** Ledio's preliminary count was
813 held-out positions lacking a corpus or lexicon reading whose signs all had
unrestricted table entries with at least one value-bearing sign; my Stage 1 measured
516 covered of 778 on the **dev** cut, which is a different and much smaller population
(dev is 4,761 sentences against the test split's 11,901, and the held-out equivalent of
"unreadable" is 1,653 positions), so the two are not directly comparable and the gap is
a population difference rather than a disagreement — the 200-position floor and the
decision rules were not affected either way.

### 5.3a Paired diagnostic on the same positions (lead, 2026-09-06 evening; requested by Ledio)

§5.3 compared composition's dev oracle recall (0.122) with the fallback's held-out accuracy
(0.2835) — two different populations. The comparison was re-done on the **same dev positions
with the same fitted model** (fit 42,842 sentences, dev 4,761, test 11,901 untouched):

| | count |
|---|---|
| dev positions with no corpus and no lexicon reading | 778 |
| … composition produces ≥ 1 candidate | 516 |
| … baseline actually uses the glyph-similarity fallback | 726 |
| **paired: composition covers AND baseline falls back** | **489** |

| on the 489 paired positions | exact | lenient fold |
|---|---|---|
| fallback accuracy | **0.3476** (170) | 0.3558 (174) |
| composition oracle recall (gold anywhere in the list) | **0.1186** (58) | 0.1697 (83) |
| composition top-1 | 0.0327 (16) | — |

The fallback is right almost three times as often as composition's *ceiling* on exactly the
positions where both apply, so the §5.3 conclusion stands, now paired: candidate generation
must improve before any scoring change can help on this sample. (The fallback's dev accuracy,
0.39 over all 726 of its positions, is higher than its held-out 0.2835 — the unpaired comparison
had understated the gap, not overstated it.) Held-out test untouched; 200-position floor
unchanged. Script: the lead's `c2_paired.py` run on 2026-09-06, output quoted verbatim.

### 5.4 Why it fails, for the record

The dev dump makes the reason concrete, and it is structural rather than a matter of
tuning. A per-sign function inventory answers "what can this sign stand for", but a
transliteration is not the concatenation of its signs' values:

* **Orthography.** Phonetic complements are written and not transliterated (revision 1
  recovers some of this, and only some: the corpus writes complements in patterns the
  tables cannot predict from the two signs alone).
* **Morphology.** The gold is TLA transliteration with its dots, brackets and plural
  marks — `ḫꜣ.PL`, `mḥ.tꞽ`, `b(w)-nfr`, `ꜥn.t.PL`. Nothing in a sign inventory supplies
  a `.PL` or a restored `(w)`. The lenient fold recovers part of this and lifts oracle
  recall from 0.122 to 0.176, which measures how much of the failure is notation and
  how much is substance: most of it is substance.
* **Convention.** Nederhof writes the yod `j`; converted, some rows land on `y` and some
  on `ꞽ`, so both spellings appear as separate candidates and the corpus's own ordering
  cannot always separate them.

What would have to change before this is worth revisiting: matching Nederhof's RES sign
*combinations* against corpus sign groups (which would restore the 94 excluded rows and
the group-scoped readings that are exactly the multi-sign knowledge missing here), and
a morphological layer that can propose TLA's written morphology. Neither is a
reweighting of what exists.

---

### 5.5 Miss classification — what would reopening C2 actually need? (lead, 2026-09-06 night)

Ledio asked whether the two reopening preconditions (combination matching, a morphology layer)
were worth building. Before building either, the 431 paired misses (489 − 58 oracle hits, dev
cut, same fitted model) were sorted by cause and each cause turned into a ceiling:

| cause | misses | share |
|---|---|---|
| the needed values all exist among the group's signs but the composition rule never assembles the gold reading (not even at cap 500) | 217 | 50.3% |
| a needed consonant is absent from every table value of the group's signs | 111 | 25.8% |
| the gold reading is generated but falls outside the cap of 24 (recovered at 500) | 44 | 10.2% |
| a Nederhof combination row (86 of 94 parseable) would supply it | 34 | 7.9% |
| differs from a candidate only under the lenient fold (written morphology) | 25 | 5.8% |

| oracle ceiling on the same 489 positions | value | fallback |
|---|---|---|
| as shipped | 0.1186 | 0.3476 |
| + morphology layer | 0.1697 | |
| + combination matching | 0.1881 | |
| + cap 500 | 0.2086 | |
| + combination + morphology | 0.2393 | |
| + combination + morphology + cap 500 | 0.3292 | |
| + a generator that assembles every reachable reading (theoretical) | 0.7730 | |

**Verdict: the two preconditions are not sufficient, even together and even with the cap
lifted (0.329 < 0.348).** The dominant cause is the assembly rule: half the misses have every
needed value present and the fixed left-to-right, silent-or-value rule still never produces the
gold. Examples (group | gold | first candidates): `𓅘𓎛𓇓𓏲𓆱𓏥 | nḥs | ḥw, ḥwḫt, ḥswt…` (the first
sign's value is dropped), `𓈖𓉔𓐛𓅱𓀁 | nhm | nmw, nw, nꞽmw, nhmw` (the reading is reachable
but a `w` is appended from a sign that is silent here), `𓉲𓀀𓏥 | sḥ.w | ḥꜣb, ḥꜣb=ꞽ, =ꞽ, sḥ`
(the classifier 𓀀 is read as =ꞽ), `𓄞𓂧𓇋𓇋𓈒𓏥 | šd.t | ꞽ, ꞽꞽ, ḏrt` (𓄞 contributes nothing).
Missing values (26%) include `𓃀𓅯𓄿 | bꜣy`, `𓇋𓎛𓉐𓏏 | ꞽḥw`, `𓄟𓋴𓏲𓏫 | msy` — signs whose
table rows lack the value the corpus uses (3 of the 111 are rows whose gold is `?`).
Reopening C2 therefore means a **generator redesign** (which signs may be silent, value ordering,
classifier handling, complements), measured by the same two-stage method, plus more table
values — not the two preconditions. C2 stays parked; D comes first. Script: the lead's
`c2_miss_classes.py`, dev only, held-out untouched.

## 6. UI

Two changes, no others.

1. **Composed readings are labelled.** In the workspace table a composed reading's
   Evidence cell reads "read sign by sign from the sign-function list — not attested",
   and the support line gains "*n* read sign by sign". `ReadingPrediction.is_borrowed`
   was added and the UI's fallback count now uses it, so a composed reading is counted
   as borrowed and the "✓ every sign group is attested" badge can never appear over
   one. Because C2 ships off, none of this is reachable in the app today; it is wired
   and tested so that turning the switch on cannot make a guess look attested.
2. **`crossed_quadrats` is shown.** The regrouping caption now names the boundaries the
   segmenter placed inside a quadrat the paste's own layout controls joined: "cut inside
   *n* quadrats your layout joined". Only ever non-empty for a paste from a
   layout-aware editor.

---

## 7. Gates on the worktree

| gate | command | result |
|---|---|---|
| full test suite | `pytest -q` | **640 passed, 3 skipped** |
| expert paste | `run_expert_paste_eval.py --stage auto` | **8/8** |
| v4 | `run_competitive_ambiguity_eval.py --benchmark …_v4.csv --query-path app --stage auto` | top-3 useful **0.90**, MRR **0.7917**, 2 failures — **byte-identical** to `ceval_v4_v4_app_auto_results.csv` (`diff` empty) |
| held-out 1 | `… …_holdout_2026-09-05.csv …` | top-3 useful **0.75**, MRR **0.6667**, 5 failures — **byte-identical** to `ceval_holdout_v4_app_auto_results.csv` (`diff` empty) |
| LE-v1 | `… …_le_v1.csv …` | top-3 useful **0.8667**, MRR **0.8167**, 4 failures — **byte-identical** to `ceval_le_v1_app_auto_results.csv` (`diff` empty) |
| segmentation, after | `run_segmentation_eval.py` | unspaced 0.939 / 0.579, scrambled 0.946 / 0.635 |
| reading, after | `run_reading_model_eval.py --exclude-duplicates --sizes 0` | `acc_ambiguous_context` 0.8803, `acc_fallback` 0.2835, `fallback_predictions` 1485, `unseen_signs` 9445 — **every field identical to the baseline** (the reading eval scores gold sign groups, so C1 cannot touch it, and C2 is off) |
| St Andrews, after | `run_format_hint_eval_standrews.py --constant 1.0` | unspaced hints-on F1 0.603 |
| St Andrews / Urk. IV | `check_standrews_urkiv_gate.py` | keyed corpus **138,131 rows** (StAndrews 7,659), expert paste checks **8/8**, PASTE_001 retrieval pool 27,917, 0 St Andrews rows in the pool, done in 69.5 s |

LE-v1 ran 14:31 to 14:40, about nine and a half minutes of wall clock for roughly nine
minutes of CPU — the whole benchmark suite is simply slow (the eval's resident set
reaches ~2.7 GB and it rebuilds stage resources per stage). All three benchmarks came
back exactly as the pre-registration predicted, on the ground that none of them
contains a glyph query and C1 only changes how a glyph paste is segmented.

Two tests were re-scoped rather than left to fail, both for the same reason and both
recorded in the code:

* `tests/test_quadrat_hints.py`'s no-op proof builds its segmenter with
  `boundary_model=0.0`. It re-implements the **pre-item-C** objective as a reference,
  so its fixture must hold the weights of that moment; item C1's own no-op proof lives
  in `tests/test_boundary_model.py` and does the same job for the new term.
* Two cases in `tests/test_segmentation.py` that pin the Good-Turing singleton discount
  switch the boundary term off. In those hand-built fixtures the two groups whose
  boundary is at issue only ever appear as one-group sentences, so the pair straddling
  the disputed cut is never once observed across a boundary and the bigram, correctly,
  has no evidence for cutting there. The real corpus has no such hole and the same case
  is checked on it by the paste gate — PASTE_005 is the identical 𓈖𓏏𓈖𓏥 decision and
  passes at the shipped weight.

---

## 8. What shipped, what stayed off

**Shipped**

* `data/processed/sign_functions_supplement.csv` — 13 rows, 11 signs, CC BY-SA 4.0,
  documented in `DATA-LICENSE.md`.
* `app/services/sign_functions.py` — the loader, the five-class fold, the standalone-row
  filter.
* `app/services/boundary_model.py` and `SegmentationWeights.boundary_model = 1.0` — the
  C1 term, on.
* The `crossed_quadrats` caption.

**Present but off**

* `app/services/composition.py` and the `composed` source kind —
  `USE_COMPOSED_BY_DEFAULT = False`, per rule C2.4.
* `SegmentationWeights.boundary_model` can be set to 0.0 to recover the pre-item-C
  objective bit for bit, and a test proves it on 500 scrambled corpus rows.

**Not touched**

* κ (6.0), the singleton discount (0.39), the lexicon weight (0.2), `quadrat_crossed`
  (1.0) — none re-tuned, as pre-registered.
* Retrieval and ranking: no change.
* The lattice's pasted-space restriction (`len(span) > 1 and any(i < b < j for b in
  hints)`) — left alone, as instructed; it is a separate pre-registered experiment.
