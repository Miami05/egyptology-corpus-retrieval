# C1c — lift the pasted-space veto only when the spaces are known to be quadrats (2026-09-06)

The follow-up C1b's §6 asked for, run on top of items B, C and the C1b switch. C1b left a
contradiction on the table: the same veto that *protects* boundary recall on scrambled corpus
spacing *destroys* reading accuracy on real quadrat spacing. C1c does not re-run that
experiment; it asks the question underneath it — **when does a pasted space mean a word
boundary, and when does it only mean the end of a quadrat?** — and lets the answer decide.

**Result in two lines.**

* **It ships.** The veto is lifted for one call, and only when `quadrat_hints` finds at least
  one layout control in the paste. St Andrews as-rendered reading token F1 **0.5814 → 0.6017**
  (+0.0203, 590 lines better / 145 worse / 966 unchanged, paired on the same 1,701 lines).
* **Everything else is byte-identical, as pre-registered.** The segmentation eval output, all
  eight expert-paste rows, and the v4 / held-out 1 / LE-v1 result files. Nothing without layout
  controls can reach the new branch, and no corpus benchmark has any.

Worktree `/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/agent-a82435272bad7f8a7`,
branch `worktree-agent-a82435272bad7f8a7`, off `main` at `fe5c77b` (items B, C, C1b and the C2
diagnostic in). Interpreter `/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus
130,472 rows.

---

## 1. The pre-registration, quoted

From `ROADMAP.md`, "**C1c — lift the veto only when the spaces are known to be quadrats —
pre-registered 2026-09-06 evening (lead, from the C1b contradiction; runs after the C2 paired
diagnostic)**":

> C1b showed the veto costs +0.021 as-rendered token F1 on real quadrat-spaced input while the
> scramble benchmark (spurious spaces inside attested groups) says it protects recall. The two
> inputs differ in what a space *means*. Rule: `unattested_may_cross_hints` is switched on per
> paste **iff the paste carries at least one quadrat hint** (`quadrat_hints(query)` returns a
> non-empty `no_cut` set — i.e. layout controls are present, so its spaces separate quadrats,
> not words); otherwise today's veto stands. No new constants; the switch is a property of the
> input. Predictions, written before the run: scrambled and unspaced eval results
> **byte-identical** (no controls in the corpus); PASTE_001–004, 006–008 byte-identical (no
> controls); PASTE_005 (controls present, every group attested) unchanged in groups and reading;
> St Andrews as-rendered token F1 rises from 0.581 (expected ≈ 0.602 as in C1b), unspaced
> identical at 0.603; v4 / held-out 1 / LE-v1 byte-identical. Decision: ship iff St Andrews
> as-rendered token F1 > 0.581 strictly, every "byte-identical" prediction holds, paste 8/8, and
> the as-rendered improved/worsened line counts favour improvement. Report the per-shape St
> Andrews table and the unseen-word breakdown for the as-rendered shape if the harness can
> produce it; otherwise say so. Null allowed. This is not a re-run of C1b: C1b's rule and its
> null stand; C1c asks a different question (when do spaces mean quadrats?).

## 2. The change

One place, `app/services/segmentation.py::segment_paste`, +30 lines, 26 of them comment:

```python
    if use_format_hints:
        groups, no_cut = quadrat_hints(query)
        if no_cut and not segmenter.weights.unattested_may_cross_hints:
            lifted = copy(segmenter)
            lifted.weights = segmenter.weights.replace(unattested_may_cross_hints=True)
            return lifted.segment(groups, no_cut=no_cut), groups
        return segmenter.segment(groups, no_cut=no_cut), groups
    groups = normalize_hieroglyphs(query).split()
    return segmenter.segment(groups), groups
```

No new constants, no new weight, and `SegmentationWeights.unattested_may_cross_hints` keeps its
default `False` — C1b's rule and its null are untouched. Three properties of this shape matter:

* **Nothing is refitted.** `copy` is a shallow copy, so the group counts, the lexicon set, the
  fitted boundary model and the log-probability cache are the *same objects*; only the frozen
  weights dataclass is replaced. A paste costs what it cost before.
* **The caller's segmenter is never mutated.** The app caches one `Segmenter` per corpus and the
  eval harnesses share one between arms; a mutate-and-restore would have leaked across those.
* **`Segmenter.segment` is unchanged.** `scripts/run_segmentation_eval.py` calls it directly,
  never through `segment_paste`, and passes no `no_cut` — so that script cannot see C1c at all.
  §3 proves this rather than asserting it.

The guard `and not segmenter.weights.unattested_may_cross_hints` keeps the C1b eval switches
(`--unattested-may-cross-hints`) meaning exactly what they meant: if the flag is already on
globally, C1c does nothing extra.

## 3. Prediction 1 — the segmentation eval is byte-identical

`python scripts/run_segmentation_eval.py` (test split, 53,553 training rows, 5,482 test rows,
5,298 with two or more groups):

```
[default] SegmentationWeights(hint_kept=0.5, hint_crossed=1.0, unattested_per_glyph=6.0, singleton_discount=0.39, lexicon_weight=0.2, quadrat_crossed=1.0, boundary_model=1.0, unattested_may_cross_hints=False)
  unspaced   n= 5298  P=0.943  R=0.934  F1=0.939  exact=0.579
  scrambled  n= 5298  P=0.935  R=0.956  F1=0.946  exact=0.635
  as_pasted  n= 5298  P=0.612  R=0.700  F1=0.653  exact=0.048
  boundary errors by whether the gold group was attested in training:
    unspaced   gold groups 40,468 (4,320 unattested, 10.7%)
      missed    2,315  =  2,028 between two attested groups +    287 touching an unattested one
      spurious  1,990  =    559 inside an attested gold group +  1,431 inside an unattested one
    scrambled  gold groups 40,468 (4,320 unattested, 10.7%)
      missed    1,549  =  1,384 between two attested groups +    165 touching an unattested one
      spurious  2,318  =    610 inside an attested gold group +  1,708 inside an unattested one
```

**Held.** unspaced 0.939 / 0.579 and scrambled 0.946 / 0.635 are the committed numbers, and the
unseen-word breakdown is the same table C1b printed for "veto in place". Proved rather than
eyeballed: the same command was run with the change stashed out (pristine `fe5c77b`) and the two
captured outputs diffed —

```
diff segeval_main.txt segeval_c1c.txt   ->  no output (byte-identical)
```

## 4. Prediction 2 — the expert pastes

`python scripts/run_expert_paste_eval.py --stage auto`, run once on the changed tree and once
with the change stashed out, writing to two files and diffing them.

```
passed 8/8            (both runs)
MD5 (paste_main.csv) = 1f2349fa30865288065786f3865b656d
MD5 (paste_c1c.csv)  = 1f2349fa30865288065786f3865b656d
```

**Held, and more strongly than predicted.** The prediction reserved PASTE_005 (the only paste
carrying controls) for a "groups and reading unchanged" check while the other seven were to be
byte-identical; in fact **all 23 columns of all 8 rows are identical**, PASTE_005 included —
checked column by column with pandas, not only as a file diff:

```
columns equal: True — 23 columns, 8 rows
columns that differ: NONE
```

Which pastes could have moved is not a guess. Scanning the benchmark with `quadrat_hints`:

| row | layout controls | `no_cut` |
|---|---|---|
| PASTE_001, 002, 003, 004, 006, 007, 008 | 0 | ∅ — the new branch is unreachable |
| PASTE_005 | 11 | {1, 2, 4, 5, 7, 8, 9, 11, 12, 13, 15} — the branch fires |

So PASTE_005 is the one row where C1c is live, and it comes out identical:
`𓆓𓂧 𓆑 𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏥 𓂋𓍿𓀀𓏥 𓎟𓏏` → `ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t`, 50 parallels, top
suggestion `ḏd =ꞽ n =tn` at confidence 0.626. That is the structural reason C1b already gave:
every group in the correct analysis of Sethe's Urk. IV 1 is attested in this corpus, thousands
of times over, so the lattice never needed an unattested span to reach the right answer — and
the veto only ever applied to unattested spans. The gate confirms C1c does no harm here; it
cannot be evidence that C1c helps.

## 5. Prediction 3 — St Andrews, the number the decision rests on

`python scripts/run_format_hint_eval_standrews.py --constant 1.0`, 1,702 lines with glyphs and a
reading, memorisation guard drops 1 (urkIV-024 line 2-8, the single sign 𓅱, which the TLA rows
also carry), **1,701 evaluated, 0 of them in the public corpus**. Fold: NFC, lowercase, delete
`. ( ) [ ] { } ⸢ ⸣`.

```
shape        arm            q  lines       P      R     F1  exact  |grp-tok|
----------------------------------------------------------------------------
as_rendered  hints_off   0.00   1701   0.526  0.640  0.578  0.028      3.119
as_rendered  hints_on    1.00   1701   0.571  0.635  0.602  0.028      2.158
unspaced     hints_off   0.00   1701   0.574  0.624  0.598  0.027      1.995
unspaced     hints_on    1.00   1701   0.583  0.625  0.603  0.027      1.861

paired deltas (hints_on - hints_off), per shape:
  as_rendered  dF1 +0.0239  dexact +0.0006  d|grp-tok| -0.9607  improved 632  worsened 156  unchanged 913
  unspaced     dF1 +0.0048  dexact +0.0000  d|grp-tok| -0.1340  improved 142  worsened 47  unchanged 1512
```

**Held on every clause.** As-rendered hints-on token F1 **0.602**, exactly the value C1b measured
with the veto lifted *globally*, up from the shipped **0.581**. Unspaced is **0.603 / 0.598**,
the committed pair, to three decimals — as it must be: removing the spaces leaves one group, so
there are no hints for an unattested span to cross, controls or no controls. As-rendered
hints-off is **0.578**, also unchanged, because that arm deletes the controls and so never
computes a `no_cut` set.

### The paired comparison the harness cannot print

The table's improved/worsened counts compare hints-on with hints-off, which mixes C1c together
with item B's quadrat penalty. The number the decision rule actually names — C1c against the
shipped configuration, same arm, same shape — needed a small paired script (one process, one
fitted model and boundary model shared, only `segment_paste`'s branch differing):

```
lines evaluated: 1,701
as_rendered / hints_on, shipped veto : P 0.5328  R 0.6397  F1 0.5814  exact 0.0270  |grp-tok| 2.9753
as_rendered / hints_on, C1c          : P 0.5714  R 0.6354  F1 0.6017  exact 0.0282  |grp-tok| 2.1581
paired per line (C1c - veto): improved 590  worsened 145  unchanged 966
lines carrying at least one quadrat hint: 1,695 of 1,701
```

**F1 0.5814 → 0.6017, +0.0203, improved 590 ≫ worsened 145.** The shape of the gain is worth
noting: precision rises 0.533 → 0.571 while recall barely moves (0.640 → 0.635), and the mean
gap between groups proposed and gold tokens falls **2.975 → 2.158**. The lattice was
over-splitting — shattering words it could not attest into their quadrats — and C1c stops it,
without going on to merge things it should not.

1,695 of the 1,701 lines carry at least one control, which is why the conditional rule reproduces
the global lift almost exactly (C1b: 0.602, 592 / 145; C1c: 0.6017, 590 / 145). On this corpus
the two rules nearly coincide; they differ everywhere else, which is the point.

### The unseen-word breakdown, and why there isn't one

**The harness cannot produce it for the as-rendered shape, so this part of the pre-registration
is reported as not producible rather than as a result.** The breakdown in §3 classifies *gold
boundaries* by whether the gold group either side was attested in training. St Andrews has no
gold word-level grouping at all: in `standrews_lines.csv` the spaces separate quadrats, and the
only gold available is the `transliteration` column (line 1 of urkIV-001 has 12 quadrats and 5
readings). There is nothing to classify boundaries against, which is why the harness scores
end-to-end reading tokens in the first place. The nearest available proxy is `|grp-tok|` above,
and it moves in the expected direction by a lot.

## 6. Prediction 4 — the three retrieval benchmarks

Each run alone, on the changed tree, into temporary result and failure files, then diffed against
the committed CSV.

| benchmark | top-3 useful | MRR | failures | diff vs committed |
|---|---|---|---|---|
| v4 (`…_queries_v4.csv`) | **0.90** | **0.7917** | 2 | **byte-identical** |
| held-out 1 (`…_holdout_2026-09-05.csv`) | **0.75** | **0.6667** | 5 | **byte-identical** |
| LE-v1 (`…_le_v1.csv`) | **0.8667** | **0.8167** | 4 | **byte-identical** |

Command in each case:
`run_competitive_ambiguity_eval.py --benchmark <file> --query-path app --stage auto --results <tmp> --failures <tmp>`.

**Held.** This was predictable and was checked cheaply first as well: none of the seven
`competitive_ambiguity_eval_queries*.csv` files contains a single character in U+13430–U+1345F,
so `quadrat_hints` returns an empty `no_cut` for every query in them and `retrieval.py`'s
`segment_paste` call takes the unchanged branch. The runs confirm the reasoning end to end.

## 7. Tests

`tests/test_quadrat_conditional_veto.py`, 8 tests, all passing:

* **A paste without controls is identical to the pre-C1c path** — 400 corpus rows sampled at
  `random_state=7` with the segmentation eval's own scramble (seed 7), compared field by field
  (groups, score, crossed hints, inserted boundaries, unattested groups, crossed quadrats)
  against a locally written copy of the old two-line `segment_paste`, so the new code is not
  proved identical to itself. Every one of those pastes is asserted to carry an empty `no_cut`.
* **`use_format_hints=False` cannot enter the branch either** — the arm the St Andrews harness
  calls `hints_off`.
* **The positive control**, on a toy corpus where `AB` and `C` are attested and `ABC` is not, and
  the paste splits `ABC` across a space: with a joiner control present the lattice keeps the
  unseen word whole (`[ABC]`, score −0.03, one crossed hint); with the identical paste minus the
  control it cannot reach that analysis at any price and shatters the word into single glyphs.
* **`Segmenter.segment` is untouched** — the eval's own two calls (`segment(["".join(gold)])`
  and `segment(scrambled)`) on 300 corpus rows never produce a crossing unattested span, and the
  toy paste segmented through `segment` directly keeps the veto even when handed its `no_cut`.
* **No mutation** — the caller's `Segmenter` keeps its weights object and its log-probability
  cache across a lifted call.

Full suite, run in five chunks because a single-shot run exhausts the 16 GB Mac: 93 + 113
(3 skipped) + 159 + 120 + 171 = **656 passed, 3 skipped, 0 failed**. That is C1b's total of
648 passed plus this experiment's 8 new tests; the 3 skips are the same ones C1b had (the
St Andrews import test runs here because the gitignored data file was symlinked in for §5).

### One gate deliberately not run

`scripts/check_standrews_urkiv_gate.py` (the keyed 138,131-row corpus check) was **skipped**.
It hard-codes `data/private/` inside the tree it runs from, and this worker is instructed never
to write into `data/private/`; it is also not one of the gates the pre-registration named. It
should be run by whoever merges this, on a tree where the private rows are already in place —
C1c can only change a paste that carries layout controls, and PASTE_001, the query that gate
measures, carries none (§4), so no movement is expected there.

## 8. Decision

**Ship.** Every clause of the frozen rule is met:

| condition | required | measured |
|---|---|---|
| St Andrews as-rendered token F1 | > 0.581 strictly | **0.6017** |
| as-rendered improved > worsened lines | yes | **590 / 145** |
| expert paste gate | 8/8 | **8/8**, all 23 columns identical to pristine main |
| segmentation eval | byte-identical | **byte-identical**, output diffed against pristine main |
| v4 / held-out 1 / LE-v1 | byte-identical | **byte-identical** to the committed CSVs |

`SegmentationWeights.unattested_may_cross_hints` stays `False` by default; C1b's null stands
unchanged. What ships is the *rule about the input*, not a new weight.

## 9. For Nederhof

This is his format controls doing work of a kind the layout encoding was not designed for. The
controls in a RES-derived paste say which signs share a quadrat — a statement about the page.
But saying "these signs share a quadrat" also says, of every space in that paste, that it is a
*quadrat* boundary and not necessarily a word boundary. That second, implicit statement is the
one C1c uses. Without it, all a segmenter can assume of a pasted space is that it might separate
two words, and it must therefore refuse to hypothesise an unattested run of signs that swallows
one — otherwise it will cheerfully glue unrelated words together, which is exactly what the
scrambled corpus benchmark punishes. With the controls present, that refusal has no basis:
Egyptian words routinely span several quadrats, so on the 1,701 St Andrews lines the correct
span crosses a space by construction, and because this is Hannig-convention Urkunden material
against a TLA-normalised corpus, the correct span is frequently one this corpus has never
attested. The veto was blocking the right answer and nothing else. Lifting it only for pastes
that carry controls raises end-to-end reading token F1 on that archive from 0.5814 to 0.6017 and
cuts the over-segmentation gap by more than a quadrat per line, while leaving every corpus
benchmark bit for bit unchanged. The layout information does not tell the lattice what a word
is; it tells the lattice what the spaces are *not*, and that is enough to let an unseen word
survive.

## 10. Files

* `app/services/segmentation.py` — the conditional lift in `segment_paste`, and a note on the
  flag saying the default stays `False`.
* `tests/test_quadrat_conditional_veto.py` — the eight tests above.
* This report.

No eval script, weight, constant or benchmark file was changed.
