# C1b — the pasted-space restriction (2026-09-06)

Ledio's proposal, run on top of the shipped item C lattice. One question: the lattice
refuses to propose an *unattested* multi-sign span that crosses one of the paste's own
spaces, which makes a correct unseen word impossible whenever the paste split it. Now
that C1's boundary model gives the lattice an opinion about spans it has never seen,
does lifting that veto help?

**Result in two lines.**

* **Null on the pre-registered criterion. It does not ship.** Scrambled held-out
  boundary F1 falls **0.946 → 0.944** (exact **0.635 → 0.617**) with the veto lifted,
  and the rule required a strict rise. `SegmentationWeights.unattested_may_cross_hints`
  is in the code, **default `False`** — today's behaviour, proved byte-identical.
* **But the one real-input measurement says the opposite, and clearly.** On 1,701 St
  Andrews lines whose spaces are true quadrat boundaries, lifting the veto raises the
  as-rendered reading token F1 **0.581 → 0.602** — 592 lines better, 145 worse. The
  synthetic scramble and the real paste disagree about this change; §6 says why, and
  that is the finding worth keeping.

Worktree off `main` at `26906f7`. Interpreter
`/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus 130,472 rows;
59,504 of them carry a non-empty normalised sign string and are what the segmentation
eval splits (90/10, seed 7, test twins of training strings excluded).

---

## 1. The pre-registration, quoted

From `ROADMAP.md`, "**C1b — the pasted-space restriction, pre-registered 2026-09-06
(Ledio's proposal; runs after the C report, separate launch)**":

> Today the lattice refuses to propose an unattested multi-sign span that crosses a
> pasted space (`segmentation.py`: "only propose an unattested span as a whole pasted
> group or a single glyph"). That protects against merging unrelated words but makes a
> correct unseen word *impossible* when the paste split it; once C1's boundary model
> exists the lattice has evidence to judge such spans. Experiment: allow unattested
> spans to cross pasted spaces, keeping the soft crossing penalty (`hint_crossed`) and
> `MAX_GROUP_GLYPHS` unchanged, on top of the best C1 configuration (or the pristine
> lattice if C1 was null). Measured on **scrambled** input, where pastes have spaces
> (unspaced input has no hints, so it must come out identical — that is the no-op
> check). Dev first, then one test run. Decision: ship iff scrambled test F1 rises
> above the C1 value, unspaced is byte-identical, paste 8/8 (PASTE_001–005 are exactly
> the wrongly-spaced pastes this could help or hurt), and the St Andrews as-rendered
> token F1 (quadrat spaces are pasted spaces there) does not fall by more than 0.010.
> Report the unseen-word breakdown as in C1. Null allowed. Two questions, answered
> separately: does boundary evidence improve the choices (C1); does relaxing the
> restriction make previously impossible correct choices available (C1b).

The thresholds as instantiated at C1's shipped values: scrambled test F1 **> 0.946**
strictly, St Andrews as-rendered token F1 **≥ 0.571** (0.581 − 0.010).

## 2. The change

`SegmentationWeights.unattested_may_cross_hints: bool = False`. The rule in
`Segmenter.segment` becomes conditional:

```python
if (
    not w.unattested_may_cross_hints
    and len(span) > 1
    and any(i < b < j for b in hints)
):
    continue
```

Nothing else moved. With the flag on, a crossing unattested span still pays
`hint_crossed` (1.0) per crossed hint and κ = `unattested_per_glyph` (6.0) per glyph,
and `MAX_GROUP_GLYPHS` (10) is unchanged: **the flag adds candidates to the lattice,
it does not rescore anything**. `log_prob` still returns `None` for such a span, so it
is never granted a probability.

## 3. The no-op proof, and the unspaced identity

500 corpus rows (`random_state=7`) with their spacing scrambled by the eval's own
`scramble` (seed 7, P_drop 0.3, P_add 0.2), 481 of them multi-group. Segmentations and
scores dumped on pristine `main`, then again on the changed tree with the flag off:

```
MD5 (baseline_main.jsonl) = 47822fd21fede8b926f25be83133bb71
MD5 (flag_off.jsonl)      = 47822fd21fede8b926f25be83133bb71
```

Byte-identical, groups and scores. `tests/test_pasted_space_restriction.py` carries the
same proof permanently against an independently written reference DP that hard-codes
the veto, so the new code cannot be proved identical to itself.

**Unspaced input has no hints, so it cannot see the flag.** On the same 481 rows, 0 of
the unspaced segmentations differ (groups or score) between flag off and flag on. The
held-out eval says the same at scale: unspaced **P 0.943 / R 0.934 / F1 0.939 / exact
0.579** on both arms, digit for digit, and its unseen-word breakdown is identical too.
With the flag on, 22 of the 481 *scrambled* rows change — the flag is live.

## 4. Scrambled input: dev, then one test run

Dev = the last 10% of the shuffled training split, twins excluded (48,197 fitting rows,
4,918 dev rows, 4,746 with two or more groups). `scripts/run_segmentation_eval.py --dev
--cross-hints`, both arms in one process with the counts and the scramble seed shared.

```
[restriction_on__cross_False]
  unspaced   n= 4746  P=0.940  R=0.933  F1=0.937  exact=0.582
  scrambled  n= 4746  P=0.933  R=0.957  F1=0.945  exact=0.642
  as_pasted  n= 4746  P=0.611  R=0.699  F1=0.652  exact=0.050
[restriction_off__cross_True]
  unspaced   n= 4746  P=0.940  R=0.933  F1=0.937  exact=0.582
  scrambled  n= 4746  P=0.937  R=0.949  F1=0.943  exact=0.624
  as_pasted  n= 4746  P=0.611  R=0.699  F1=0.652  exact=0.050
```

The off arm reproduces C1's dev numbers exactly (0.937 / 0.582 unspaced).

Then the single test run, `scripts/run_segmentation_eval.py --cross-hints` (53,553
training rows, 5,482 test rows, 5,298 with two or more groups):

```
[restriction_on__cross_False]
  unspaced   n= 5298  P=0.943  R=0.934  F1=0.939  exact=0.579
  scrambled  n= 5298  P=0.935  R=0.956  F1=0.946  exact=0.635
  as_pasted  n= 5298  P=0.612  R=0.700  F1=0.653  exact=0.048
[restriction_off__cross_True]
  unspaced   n= 5298  P=0.943  R=0.934  F1=0.939  exact=0.579
  scrambled  n= 5298  P=0.941  R=0.948  F1=0.944  exact=0.617
  as_pasted  n= 5298  P=0.612  R=0.700  F1=0.653  exact=0.048
```

**Scrambled test F1 0.946 → 0.944.** The rule required a strict rise; this is a fall.

### The unseen-word breakdown

Test split, scrambled input (gold groups 40,468, of which 4,320 — 10.7% — the training
split never saw as whole groups):

| | veto in place | veto lifted |
|---|---|---|
| missed boundaries | **1,549** = 1,384 between two attested + 165 touching an unattested | **1,836** = 1,598 between two attested + 238 touching an unattested |
| spurious boundaries | **2,318** = 610 inside an attested gold group + 1,708 inside an unattested one | **2,094** = 595 inside an attested gold group + 1,499 inside an unattested one |

Dev, scrambled (gold groups 35,915, 4,173 unattested, 11.6%):

| | veto in place | veto lifted |
|---|---|---|
| missed | **1,344** = 1,193 + 151 | **1,606** = 1,378 + 228 |
| spurious | **2,137** = 550 + 1,587 | **1,975** = 545 + 1,430 |

Unspaced (identical on both arms), test: missed 2,315 = 2,028 + 287; spurious 1,990 =
559 + 1,431. Dev: missed 2,074 = 1,790 + 284; spurious 1,861 = 510 + 1,351.

The trade is exactly the one the veto was written to prevent, and it is a bad trade
here: the error class C1b targeted does fall — cuts *inside* an unattested gold group
drop **1,708 → 1,499** on test, the largest single movement in the table — but the
lattice pays for it by merging across **287 more real boundaries** (1,549 → 1,836),
209 of them between two groups the training split had actually attested. Precision
rises 0.935 → 0.941, recall falls 0.956 → 0.948, and F1 falls with it.

Per sentence on the scrambled test split: the flag changed the segmentation of **444 of
5,298 sentences (8.4%)** — 35 became exactly right, **129 stopped being exactly right**,
280 were wrong both ways; by sentence boundary F1, 157 better and 255 worse.

## 5. The gates

* **Expert pastes, `--stage auto`, flag on: 8/8.** Flag off: 8/8. The two runs are
  identical on every column — groups, reading, borrowed/unreadable counts, parallels,
  top suggestion, confidence, inferred stage — on all eight rows.

```
[PASS] PASTE_001  Urk. IV 1 (expert trial 2026-08-29)   ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
[PASS] PASTE_002  Urk. IV 1 grouped by word             ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
[PASS] PASTE_003  Urk. IV 1 unspaced                    ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
[PASS] PASTE_004  Urk. IV 1 with TLA spacing            ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
[PASS] PASTE_005  Layout-aware editor export            ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t
[PASS] PASTE_006  Line number and note attached         ḏd =f ḏd =ꞽ
[PASS] PASTE_007  Decomposed transliteration            (text query)
[PASS] PASTE_008  Unattested sign sequence              0 borrowed, 2 unreadable
passed 8/8
```

* **pytest, run per chunk because the 16 GB Mac kills a single-shot suite:** 93 + 113
  (3 skipped) + 159 + 112 + 171 = **648 passed, 3 skipped, 0 failed**. That is the
  item-C total of 639 passed plus this experiment's 8 new tests plus one test that had
  been skipping: the St Andrews import test runs here because the gitignored data file
  was symlinked in for §6, hence 4 skips → 3.
* The v4 / held-out / LE-v1 byte-identity gates were **not run**: they are required
  only if the change ships, and it does not. Nothing in the default configuration
  changed, and the no-op proof in §3 covers that claim directly.

## 6. What it did to the five wrongly spaced pastes — and to real quadrat input

**On PASTE_001–005 the change did nothing whatever.** Every one of those five spacings
of Sethe's Urk. IV 1 comes out as `𓆓𓂧 𓆑 𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏥 𓂋𓍿𓀀𓏥 𓎟𓏏` with the veto in
place and with it lifted, and the readings, stage inference and retrieved parallels are
identical too. The reason is structural rather than lucky: every group in the correct
analysis of that line is attested in the corpus, often thousands of times, so the
lattice never needed an unattested span to reach the right answer — and the veto only
ever applied to unattested spans. The gate could not have moved, in either direction.
It is worth saying plainly that this is a **weakness of the gate as evidence for C1b**,
not a success of the change: the pre-registration expected these five rows to be where
the change would show, and they are the five rows where it provably cannot.

Where it does show is the one input in this project whose spaces are real, foreign
spaces: the 1,701 St Andrews lines, where a space separates **quadrats**, not words.
`scripts/run_format_hint_eval_standrews.py --constant 1.0`, both arms, the shape that
matters being *as rendered* (quadrat spaces present):

```
                                    P      R     F1  exact  |grp-tok|
as_rendered  hints_off  veto        0.526  0.640  0.578  0.028   3.119
as_rendered  hints_on   veto        0.533  0.640  0.581  0.027   2.975
as_rendered  hints_off  lifted      0.564  0.635  0.597  0.029   2.290
as_rendered  hints_on   lifted      0.572  0.635  0.602  0.028   2.156
unspaced     hints_off  veto        0.574  0.624  0.598  0.027   1.995
unspaced     hints_on   veto        0.583  0.625  0.603  0.027   1.861
unspaced     hints_off  lifted      0.574  0.624  0.598  0.027   1.995
unspaced     hints_on   lifted      0.583  0.625  0.603  0.027   1.861
```

Unspaced is identical to four decimals on both arms, as it must be. As rendered, the
token F1 goes **0.581 → 0.602** (+0.021, twice the size of everything item B and item C
bought on this file put together), the mean gap between the number of groups proposed
and the number of gold tokens falls **2.975 → 2.156**, and line by line **592 lines
improve, 145 worsen**, 964 are unchanged (the segmentation is untouched on 901 of the
1,701). The pre-registration's St Andrews condition — not more than 0.010 below 0.581 —
is met with room to spare, in the wrong direction for a null.

**Why the two measurements disagree.** The scramble inserts its spurious boundaries
*inside gold groups*, and gold groups are usually attested — so the lattice could
already merge across those spurious spaces, because the merged span was an attested
group and the veto never applied. What the veto blocked on scrambled input was almost
entirely the *harmful* merge: an unattested run of signs swallowing a genuine boundary.
Lift it and you get exactly the 287 extra missed boundaries above. On St Andrews the
situation is reversed: a word routinely spans several quadrats, so the correct span
crosses a space by construction, and because the text is Hannig-convention Urkunden
material the correct span is frequently *not* attested in this TLA corpus. There the
veto was blocking the correct answer and nothing else, which is precisely the failure
Ledio's proposal named.

So the honest summary is that the experiment answered its question on the wrong
distribution. The scrambled benchmark is a model of *noisy word spacing*; the
restriction's cost is paid on *quadrat spacing*. The decision rule was written on the
scrambled number and the scrambled number fell, so the flag ships off — but the case
for a follow-up is now measured rather than argued: make the restriction conditional on
what the spaces mean (layout controls present, or spaces far denser than the corpus's
own group length), rather than on whether the span is attested. That is a new
pre-registration, not a tweak to this one.

## 7. Decision

**Null. `unattested_may_cross_hints` stays `False`.** Scrambled test F1 0.944 is not
strictly above C1's 0.946, and that condition alone settles it; the other three
conditions were met (unspaced byte-identical, paste 8/8, St Andrews as-rendered 0.602 ≥
0.571). The flag, its tests and the two eval switches stay in the tree so the follow-up
in §6 costs nothing to start.

## 8. Files

* `app/services/segmentation.py` — the flag and the conditional veto.
* `tests/test_pasted_space_restriction.py` — 8 tests: default off, the byte-identity
  proof against an independent reference DP, unspaced insensitivity, the corpus-level
  claim that the flag only ever buys a crossing unattested span, and a toy-corpus
  positive control that the span is unreachable off and chosen on.
* `scripts/run_segmentation_eval.py` — `--cross-hints` (both arms, one process).
* `scripts/run_expert_paste_eval.py`, `scripts/run_format_hint_eval_standrews.py` —
  `--unattested-may-cross-hints`.
