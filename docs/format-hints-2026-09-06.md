# Item B — format controls as weak segmenter hints (2026-09-06)

Nederhof's fourth criticism: the pipeline deletes U+13430–1345F, the Unicode format
controls that carry the quadrat structure of a paste. This is the answer, measured.

**Result in one line: the hints help, a little, and they ship on.** `quadrat_crossed
= 1.0` nats per boundary the segmentation places inside a quadrat. On real St Andrews
input the unspaced-shape token F1 goes from **0.587 to 0.591** (+0.0046; 195 lines
better, 69 worse, 1,437 unchanged). On the BBAW upper bound — where the controls are
synthesised from the same annotation that defines the gold words, so hint precision is
**1.0 by construction** — unspaced boundary F1 goes from **0.784 to 0.940** on the
held-out test half. Every existing number is unchanged, byte for byte.

Worktree off `main` at `bb3aa80`. Interpreter
`/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus 130,472 rows.

---

## 1. The pre-registration, quoted

From `ROADMAP.md`, "### Item B — format controls as weak segmenter hints —
pre-registered 2026-09-06 (Opus 5 worker)":

> **Frozen design.**
>
> 1. `app/data/normalizer.py`: `quadrat_hints(value) -> (groups_as_pasted, no_cut)`.
>    `no_cut` = glyph-stream boundary indices (same indexing as `glyph_stream`: b
>    means "a group ends before glyph b") that fall between two signs joined by a
>    **joiner** U+13430–13436 or U+13439–1343B, or strictly inside a **segment**
>    13437…13438 or an **enclosure** 1343C…1343F. Mirror (13440), blanks and damage
>    marks (13441–13455) carry no adjacency information → no hint. Invariant, tested
>    on the 8 pastes, all 1,710 St Andrews lines and the pipeline fuzz:
>    `groups_as_pasted == normalize_hieroglyphs(value).split()` exactly.
> 2. `SegmentationWeights.quadrat_crossed` (nats), penalty per boundary the
>    segmentation places at a `no_cut` position. `Segmenter.segment(groups,
>    no_cut=frozenset())` and `score_segmentation` apply it;
>    `Segmentation.crossed_quadrats` lists them. Empty set → the objective is
>    unchanged, so every existing test and number stays identical.
> 3. One helper `segment_paste(query, segmenter, use_format_hints=True)` replaces the
>    five `normalize_hieroglyphs(q).split()` → `segment` sites (`whyptology_app.py:424`,
>    `retrieval.py:294`, `run_expert_paste_eval.py:119`, `bench_query_latency.py:98`,
>    `check_standrews_urkiv_gate.py:122`); the manual-edit site at
>    `whyptology_app.py:2025` is left alone. `run_expert_paste_eval.py` gains
>    `--no-format-hints`. No ranking or retrieval code changes; no UI beyond the wiring.
> 4. **BBAW upper bound** (`scripts/run_format_hint_eval_bbaw.py`): raw rows accepted
>    by `import_bbaw_egyptian.parse_glyph_field` + the importer's alignment filter,
>    with `:`/`*` present. Emit U+13430 for a `:` token, U+13431 for `*`, nothing for
>    `-`; gold = the importer's word groups. Rows must be **removed from the training
>    frame** by normalised glyph string (memorisation guard, as in
>    `run_segmentation_eval.split`). Fixed seed 7 split: dev 50% / test 50%. Inputs:
>    unspaced + controls vs unspaced with controls deleted (= today). Metric: boundary
>    P/R/F1 + exact, the segmentation eval's own. Print hint precision (share of
>    control-marked adjacencies inside a gold group; ~1.0 by construction — that is why
>    this is an upper bound). **Constant selection**: `quadrat_crossed ∈ {0.25, 0.5,
>    1.0, 2.0}` by highest unspaced F1 on the **dev** half, subject to paste 8/8 (auto)
>    as a hard constraint; report on the test half only. Standing rule respected: no
>    benchmark number picks the constant.
> 5. **St Andrews, the real input** (`scripts/run_format_hint_eval_standrews.py`, data
>    gitignored, script committed): resources on the **public** corpus only; assert no
>    line's normalised glyph string occurs in it. Two shapes per line: *as rendered*
>    (quadrat spaces + controls) and *unspaced* (spaces removed, controls kept); each
>    with hints off vs on. Metric: predicted reading tokens vs the line's
>    `transliteration`, both through one lenient fold fixed now — NFC, lowercase,
>    delete `. ( ) [ ] { } ⸢ ⸣`, nothing else (ṯ/t and yod differences count as misses
>    on both arms equally) — multiset token P/R/F1, exact-line rate, and
>    |groups − tokens| mean; paired deltas with lines improved / worsened / unchanged.
>    Print Camilla's line (`urkIV-001`, line 2) both ways.
> 6. **Decision rule.** Hints ship ON (default = the selected constant) iff on St
>    Andrews the unspaced-shape token F1 delta is > 0 **and** improved lines > worsened
>    lines **and** every gate holds. Otherwise the code ships with
>    `quadrat_crossed = 0.0` (present, off) and the null result is reported. BBAW is
>    informative only and never decides.
> 7. **Gates on the merged tree**: pytest green; paste 8/8 auto; v4 results
>    byte-identical to the committed file (0.90 / 0.7917); held-out 1 0.75 / 0.6667;
>    LE-v1 0.8667 / 0.8167; `run_segmentation_eval.py` default numbers unchanged.
>    PASTE_005 must pass at the chosen constant.
> 8. **Report** `docs/format-hints-2026-09-06.md` with numbers exactly as printed, the
>    two numbers for Nederhof, and this section's close-out. Then C.
>
> STOP conditions for the worker: the invariant in (1) fails on any line; < 500
> eligible BBAW rows; a gate fails at every candidate constant; any step needs
> ranking/retrieval changes; or wall clock > 3 h. Stop that step, finish the rest,
> report.

No stop condition fired.

---

## 2. Rule 1 — reading the controls (`quadrat_hints`)

`app/data/normalizer.py` gains `quadrat_hints(value) -> (groups_as_pasted, no_cut)`.

The hard part is that positions must index the **normalised** sign stream, and
`normalize_hieroglyphs` reorganises the string before the controls would be counted:
`<g>…</g>` markup collapses to one placeholder codepoint, editorial brackets and
intra-group noise are deleted, and only then does anything non-glyph become a space.
So the extractor runs a second copy of that pipeline —
`_normalize_keeping_controls` — that is identical step for step except that the
format controls are treated as *group content* instead of being deleted. Stripping
the controls out of its result must give `normalize_hieroglyphs` back exactly; that
is the invariant.

Semantics, exactly as pre-registered:

| controls | reading | hint |
| --- | --- | --- |
| U+13430–13436, U+13439–1343B | joiners (vertical, horizontal, insert at top/bottom/middle, overlay) | the one boundary between the sign before and the sign after |
| U+13437 … U+13438 | begin/end segment | every boundary strictly inside |
| U+1343C … U+1343D, U+1343E … U+1343F | begin/end (walled) enclosure | every boundary strictly inside |
| U+13440 | mirror horizontally | none |
| U+13441–U+13446 | blanks, lost-sign shapes | none |
| U+13447–U+13455 | damage modifiers | none |

Two decisions the pre-registration left to the implementation, both recorded here:

* a joiner whose neighbour on either side is a **group-separating space** contributes
  nothing (it is not joining two signs of one quadrat, and marking a boundary the
  paste itself drew would put the two hint systems in direct conflict);
* an **unmatched** opener or closer contributes nothing.

### The invariant

`tests/test_quadrat_hints.py`, all green:

```
expert pastes:        8 values,     0 invariant failures, 1 with hints, 11 no_cut positions
standrews hieroglyphs: 1,710 values, 0 invariant failures, 1,695 with hints, 21,983 no_cut positions
seeded fuzz:          400 generated values (signs, all 38 controls, spaces, brackets,
                      <g> markup, bare Gardiner tokens), 0 failures
```

`hypothesis` is not a dependency of this project, so the fuzz case is a seeded
`random.Random(19)` generator rather than a hypothesis strategy — the one deviation
from the wording of step 1 of the task, and it was not a pre-registered rule.

PASTE_005, the layout-aware editor export, is the interesting case and has its own
test: the hints mark **every** within-group boundary and **no** group boundary, which
is exactly why a hard "never cut inside a quadrat" rule would fail the gate and a soft
penalty must be able to lose.

## 3. Rule 2 — the segmenter

`SegmentationWeights.quadrat_crossed`; `Segmenter.segment(groups, no_cut=frozenset())`
and `score_segmentation(groups, hints, no_cut=frozenset())` charge it once per
boundary the segmentation *places at* a `no_cut` position; `Segmentation.crossed_quadrats`
lists those positions (the mirror image of `crossed_hints`).

The no-op is proved, not asserted: `test_empty_no_cut_is_byte_identical_to_the_old_objective`
re-implements the pre-item-B objective inside the test file and checks 500 corpus rows
with scrambled spacing (seed 7) segment identically — 431 rows with ≥ 2 gold groups
checked, 0 differences.

## 4. Rule 3 — the wiring

`segment_paste(query, segmenter, use_format_hints=True)` in
`app/services/segmentation.py` returns `(segmentation, groups_as_pasted)` and now
serves all five sites: `app/ui/whyptology_app.py`, `app/services/retrieval.py`,
`scripts/run_expert_paste_eval.py`, `scripts/bench_query_latency.py`,
`scripts/check_standrews_urkiv_gate.py`. The manual-edit site at
`whyptology_app.py:2025` is untouched, as instructed. `run_expert_paste_eval.py` gains
`--no-format-hints` and `--quadrat-crossed`. No ranking or retrieval logic changed.

## 5. Rule 4 — the BBAW upper bound

`scripts/run_format_hint_eval_bbaw.py`, output in
`data/benchmarks/format_hints/bbaw_upper_bound.{csv,md}`.

```
eligible BBAW rows (importer-accepted, with ':' or '*'): 11,386
hint precision: 1.0000 (64,021/64,021 control-marked boundaries fall strictly inside a gold word)
split seed 7: dev 5,693 rows / test 5,693 rows
training frame 120,226 of 130,472 rows (10,246 removed by the memorisation guard)

config                 shape              half       n       P      R     F1  exact
-----------------------------------------------------------------------------------
controls_deleted       unspaced           dev     5693   0.750  0.815  0.781  0.547
as_pasted              as_pasted          dev     5693   1.000  1.000  1.000  1.000
controls_deleted       unspaced           test    5693   0.753  0.819  0.784  0.541
as_pasted              as_pasted          test    5693   1.000  1.000  1.000  1.000
hints_0.25             unspaced+controls  dev     5693   0.948  0.934  0.941  0.639
hints_0.25             unspaced+controls  test    5693   0.946  0.930  0.938  0.625
hints_0.5              unspaced+controls  dev     5693   0.949  0.934  0.941  0.642
hints_0.5              unspaced+controls  test    5693   0.947  0.930  0.938  0.628
hints_1.0              unspaced+controls  dev     5693   0.952  0.934  0.943  0.645
hints_1.0              unspaced+controls  test    5693   0.949  0.930  0.940  0.631
hints_2.0              unspaced+controls  dev     5693   0.963  0.935  0.949  0.654
hints_2.0              unspaced+controls  test    5693   0.960  0.931  0.945  0.643

best unspaced F1 on dev: quadrat_crossed=2.0 (F1 0.9485)
```

`as_pasted` here is the importer's own word grouping handed back unchanged, i.e. F1
1.000 by definition; it is printed only so the table reads clearly, and it is not a
result.

**A bug found and fixed mid-run, honestly recorded.** The first version of the
synthesiser emitted the joiner as soon as it saw a `:`/`*` prefix, including on tokens
whose only piece was a stray the importer discards — leaving the joiner dangling in
front of the next word and claiming an adjacency the annotation never made. Hint
precision came out **0.9992 (64,035/64,086)**, 44 rows affected. The joiner is now
held back until a sign is actually appended, precision is exactly **1.0**, and the
whole table above is from the corrected re-run. The ranking of the four constants was
identical before and after the fix.

### Constant selection

Pre-registered rule: highest unspaced F1 on **dev**, subject to expert paste 8/8 in
`--stage auto` as a hard constraint. The gate was run at all four candidates, hints on:

```
quadrat_crossed=2.0   passed 7/8   [FAIL] PASTE_005  Layout-aware editor export
quadrat_crossed=1.0   passed 8/8
quadrat_crossed=0.5   passed 8/8
quadrat_crossed=0.25  passed 8/8
```

2.0 has the best dev F1 (0.9485) and is **rejected**: PASTE_005 joins every sign of
each wrongly chunked piece, so at 2.0 the quadrat structure outvotes the corpus
evidence (𓆑 → `=f`, 3,878/3,907) and the paste is read as one long group. This is
exactly the failure the pre-registration predicted before the run.

**Selected: `quadrat_crossed = 1.0`** — the highest-scoring candidate that keeps the
gate. Test-half numbers at that constant, reported for the first time here:
**F1 0.940, exact 0.631**, against **F1 0.784, exact 0.541** with the controls deleted.

## 6. Rule 5 — St Andrews, the real input

`scripts/run_format_hint_eval_standrews.py`, output in
`data/benchmarks/format_hints/standrews.{csv,md}`. Resources are built on the public
CC BY-SA corpus only; the NC data never enters it.

```
St Andrews lines with glyphs and a reading: 1,702
public corpus 130,472 rows, sources ['AES', 'BBAW', 'Ramses', 'TLA']
memorisation guard: dropping urkIV-024 line 2-8 ('𓅱') — already in the public corpus
memorisation guard: 1 line(s) dropped, 1,701 evaluated, 0 of them in the public corpus

shape        arm            q  lines       P      R     F1  exact  |grp-tok|
----------------------------------------------------------------------------
as_rendered  hints_off   0.00   1701   0.524  0.642  0.577  0.025      3.319
as_rendered  hints_on    1.00   1701   0.531  0.640  0.581  0.025      3.145
unspaced     hints_off   0.00   1701   0.559  0.617  0.587  0.027      2.357
unspaced     hints_on    1.00   1701   0.568  0.617  0.591  0.026      2.188

paired deltas (hints_on - hints_off), per shape:
  as_rendered  dF1 +0.0038  dexact +0.0000  d|grp-tok| -0.1740  improved 178  worsened 56  unchanged 1467
  unspaced     dF1 +0.0046  dexact -0.0005  d|grp-tok| -0.1699  improved 195  worsened 69  unchanged 1437
```

**Deviation from the pre-registration, recorded.** Step 5 says "assert no line's
normalised glyph string occurs in it". One does: `urkIV-024` line 2-8 is the single
sign 𓅱, which the TLA rows also carry on its own. A bare assertion would have stopped
the step over one trivial line, so the guard does what
`run_segmentation_eval.split` does with the same problem — it **drops** the offending
line, names it in the output, and then asserts that none remain. 1,701 of 1,702 lines
are evaluated.

Reading the numbers honestly: these are *low* absolute scores (F1 ≈ 0.59), and they
should be. The fold is deliberately weak, St Andrews writes Hannig conventions (yod as
`j`, different ṯ/t practice) against a TLA-convention corpus, and the mean gap between
predicted groups and gold tokens is still over two per line. What is measured here is
not "how well does the tool read Nederhof's texts" but "does the layout information
move the reading in the right direction", and it does: better on both shapes, roughly
three lines improved for every one made worse, and the group/token gap closes by about
0.17 groups per line on both shapes.

The exact-line rate is flat (as rendered) or one line worse (unspaced). At F1 ≈ 0.59
almost no line is read perfectly either way — 0.026 of 1,701 lines — so that column has
no resolution and should not be read as evidence in either direction.

### Camilla's line (urkIV-001, line 2)

On Camilla's line (`urkIV-001`, line 2, St Andrews rendering) the hints make one real
correction on the as-rendered shape: the groups `𓈖𓏏 𓈖` become `𓈖 𓏏𓈖`, so the reading
`n.t n` becomes `n =tn` — the exact place the first expert trial flagged. The line's token
F1 does not move (the fold counts multisets and the line is wrong elsewhere: the `𓏤𓏤𓏤`
fillers read as `3`, `ꞽwꜥ.kw` split, the numeral `7` lost); on the unspaced shape the
hints change nothing on this line. The full per-shape printout is in the script's stdout
and is not committed: the St Andrews glyph groups and gold reading are CC BY-NC-SA and
stay out of this CC BY-SA data directory.

On the as-rendered shape the hints make **one real correction**: `𓈖𓏏 𓈖` → `𓈖 𓏏𓈖`,
which turns the reading `n.t n` into `n =tn` — Camilla's own reading of exactly the
place the first expert trial flagged. The token F1 does not move because the fold
counts multisets and the line is wrong in several other places (the `𓏤𓏤𓏤` fillers
read as `3`, `ꞽwꜥ.kw` split, the numeral `7` lost). On the unspaced shape the hints
change nothing on this line.

Note that this is the St Andrews *quadrat-split* rendering of the line, not the
expert's own paste; PASTE_001–005 are the expert's, and they pass 8/8.

The lead settled the licence question on 2026-09-06: the verbatim St Andrews line (Nederhof's
quadrat rendering and gold reading, CC BY-NC-SA) is not committed; only the described change is.

## 7. Rule 6 — the decision

The rule: ship ON iff the St Andrews **unspaced** token F1 delta > 0 **and** improved >
worsened **and** every gate holds.

| condition | measured | verdict |
| --- | --- | --- |
| unspaced ΔF1 > 0 | +0.0046 (0.587 → 0.591) | met |
| improved > worsened | 195 > 69 | met |
| every gate holds | section 8 | met |

**Shipped: `SegmentationWeights.quadrat_crossed = 1.0`, hints on by default.** The
constant is documented in `SegmentationWeights` with the same shape as
`unattested_per_glyph` and `lexicon_weight` before it: the sweep table, the date, and
the script that produced it.

## 8. Rule 7 — gates

Every number below is quoted exactly as printed.

**Full suite** — `python -m pytest -q`:

```
594 passed, 4 skipped, 2 warnings in 347.99s (0:05:47)
```

Two runs, both green, and the difference is worth stating. With
`data/raw/standrews/standrews_lines.csv` reachable (it is gitignored, so it exists only
in the main checkout; it was symlinked into this worktree while the St Andrews step ran)
the all-1,710-lines invariant test runs and the suite is **595 passed, 3 skipped**. In a
clean checkout without that file it skips, giving the 594/4 above. Both numbers are from
this tree; nothing else differs.

**Expert pastes** — `python scripts/run_expert_paste_eval.py --stage auto` (defaults,
so hints on at 1.0):

```
[PASS] PASTE_001  Urk. IV 1 (expert trial 2026-08-29)  [stage=Earlier Egyptian inferred]
[PASS] PASTE_002  Urk. IV 1 grouped by word  [stage=Earlier Egyptian inferred]
[PASS] PASTE_003  Urk. IV 1 unspaced  [stage=Earlier Egyptian inferred]
[PASS] PASTE_004  Urk. IV 1 with TLA spacing  [stage=Earlier Egyptian inferred]
[PASS] PASTE_005  Layout-aware editor export  [stage=Earlier Egyptian inferred]
[PASS] PASTE_006  Line number and note attached  [stage=Earlier Egyptian inferred]
[PASS] PASTE_007  Decomposed transliteration  [stage=(none)]
[PASS] PASTE_008  Unattested sign sequence  [stage=Demotic inferred]
passed 8/8
```

**v4** — `python scripts/run_competitive_ambiguity_eval.py --benchmark
data/benchmarks/competitive_ambiguity_eval_queries_v4.csv --query-path app --stage auto`:

```
corpus_rows: 130472
total_queries: 20
top3_useful_family_accuracy: 0.9
mrr: 0.7917
failures: 2
stages_used: {'': 13, 'Earlier Egyptian': 4, 'Late Egyptian': 3}
```

**The v4 byte-identity check, and one thing it turned up.** Diffed against the
committed `data/benchmarks/ceval_v4_v4_app_auto_results.csv`, the two files agree on
24 of 25 columns for all 20 rows — every rank, hit flag, score and suggestion. They
differ on `evidence_summaries` in 14 rows, and only in the wording of one phrase:

```
old:  ... ; shared lemma IDs: 10030, 10100, ...
new:  ... ; lemma IDs common to this reading's rows: 10030, 10100, ...
```

That string was changed in `app/services/suggestions.py` by commit **deee9d2**
("Follow-up batch (2026-09-06 item 2)"), which is already in the base tree at
`bb3aa80`; the committed results file was last written at `3d38721`. So the drift
predates item B. To prove that rather than assert it, the working tree was stashed
back to the pristine base, the same command was re-run, and the two runs were diffed:

```
diff <item B v4 results> <pristine bb3aa80 v4 results>  -> BYTE-IDENTICAL
diff <item B v4 failures> <pristine bb3aa80 v4 failures> -> BYTE-IDENTICAL
```

**Item B changes no byte of the v4 output.** The stale committed file should be
refreshed by whoever merges deee9d2's effects; that is not this item's change to make.

**Held-out 1** — same command with
`competitive_ambiguity_eval_queries_holdout_2026-09-05.csv`:

```
corpus_rows: 130472
total_queries: 20
top3_useful_family_accuracy: 0.75
mrr: 0.6667
failures: 5
```

Byte-identical to the pristine-base run of the same command.

**LE-v1** — same command with `competitive_ambiguity_eval_queries_le_v1.csv`:

```
corpus_rows: 130472
total_queries: 30
top3_useful_family_accuracy: 0.8667
mrr: 0.8167
failures: 4
```

Byte-identical both to the pristine-base run of the same command and to the committed
`data/benchmarks/ceval_le_v1_app_auto_results.csv`.

**Segmentation eval** — `python scripts/run_segmentation_eval.py`:

```
train 53553 rows; test 5482 rows (twins of training strings excluded)

[default] SegmentationWeights(hint_kept=0.5, hint_crossed=1.0, unattested_per_glyph=6.0, singleton_discount=0.39, lexicon_weight=0.2, quadrat_crossed=1.0)
  unspaced   n= 5298  P=0.931  R=0.915  F1=0.923  exact=0.539
  scrambled  n= 5298  P=0.928  R=0.946  F1=0.937  exact=0.599
  as_pasted  n= 5298  P=0.612  R=0.700  F1=0.653  exact=0.048
```

Identical to the pristine-base run (only the repr of the weights differs, because it
now prints `quadrat_crossed=1.0`). This corpus carries no format controls, so the
script never produces a `no_cut` position and the objective it exercises is the old
one.

**St Andrews reviewer gate** — `python scripts/check_standrews_urkiv_gate.py`:

```
corpus 138,131 rows: {'BBAW': 52216, 'Ramses': 40064, 'TLA': 28369, 'AES': 9823, 'StAndrews': 7659}

expert paste checks (stage=auto): 8/8
  [PASS] PASTE_001  ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
  [PASS] PASTE_002  ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
  [PASS] PASTE_003  ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
  [PASS] PASTE_004  ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
  [PASS] PASTE_005  ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
  [PASS] PASTE_006  ḏd =f ḏd =ꞽ
  [PASS] PASTE_007
  [PASS] PASTE_008
```

It runs with the private CC BY-NC-SA rows present (they are on this machine and were
read, never written). 8/8 with the keyed 138,131-row corpus. PASTE_001 carries no
format controls, so `quadrat_hints` returns an empty `no_cut` for it and item B cannot
have moved this script's retrieval result.

## 9. The two sentences for Nederhof

> On your fourth point — that we throw away the quadrat controls — we now read them
> instead of deleting them: U+13430–1345F are turned into soft "these signs share a
> quadrat, do not cut here" hints for the segmenter, at a cost of 1.0 nat per boundary
> that crosses one, and on 1,701 lines of your own St Andrews corpus that lifts the
> end-to-end reading token F1 from 0.587 to 0.591, improving 195 lines and worsening 69.
>
> The ceiling is much higher than that gain suggests: on 11,386 BBAW rows whose Manuel
> de Codage field marks its own quadrats — perfect hints by construction, so an upper
> bound and not a result — the same mechanism lifts unspaced boundary F1 from 0.784 to
> 0.940 on a held-out half, which says the remaining distance is in how faithfully a
> real RES rendering's quadrats correspond to word boundaries, not in the segmenter.

## 10. What shipped, what did not

Shipped:

* `quadrat_hints` in `app/data/normalizer.py`, with the invariant tested on the 8
  pastes, all 1,710 St Andrews lines and a seeded fuzz;
* `quadrat_crossed = 1.0` in `SegmentationWeights`, `no_cut` in `Segmenter.segment` and
  `score_segmentation`, `crossed_quadrats` on `Segmentation`;
* `segment_paste`, wired into all five call sites; `--no-format-hints` and
  `--quadrat-crossed` on `run_expert_paste_eval.py`;
* two evaluation scripts and their outputs under `data/benchmarks/format_hints/`;
* `tests/test_quadrat_hints.py` (16 tests).

Not done, deliberately:

* no ranking or retrieval change of any kind;
* no UI beyond the wiring — the workspace does not yet *show* `crossed_quadrats`, which
  is the obvious next small step and was not in scope;
* `whyptology_app.py:2025` (the manual sign-group edit) still takes the user's edit at
  face value, as instructed;
* the committed v4/held-out/LE results CSVs were not refreshed, even though the v4 one
  is stale for an unrelated reason (see section 8).

Deviations from the wording of the task, all recorded above: the fuzz case is seeded
`random` rather than `hypothesis` (not installed); the St Andrews memorisation guard
drops one line instead of asserting; and a bug in the BBAW control synthesiser was
found and fixed mid-step, with both the before and after precision reported.
