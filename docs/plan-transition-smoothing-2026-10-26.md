# DRAFT pre-registration — transition smoothing in the reading model (2026-10-26)

**STATUS: DRAFT. NOT RUN. NOT APPROVED.** Nothing in this document has been measured. It is
written to be reviewed by Opus and Astra before a single arm is executed, and it must be
committed in its reviewed, final form — with every constant, split and pass rule fixed —
before any run. Numbers quoted below are arithmetic from the current source or figures
copied from documents that are cited; none of them is a result.

No KRI material appears here. The defect was found while reading a private self-test, but
everything this document pre-registers is measured on the public corpus and on the existing
reading-model split.

Sources read: `app/services/reading_model.py` (this branch),
`docs/kri-selftest-fixes-2026-10-26.md` §1 "What is still wrong" and §5 item 6, and
`docs/kri-fixes-preregistration-2026-10-26.md` §§1–4 (worktree
`.claude/worktrees/kri-fixes-2026-10-26`, read only).

---

## 1. The defect

`ReadingModel._transition` estimates P(reading | previous reading) with add-k over the
*observed* successor set:

```python
def _transition(self, previous_reading: str, reading: str) -> float:
    counts = self.reading_bigram.get(previous_reading, Counter())
    total = sum(counts.values())
    if total == 0:
        return log(SMOOTHING)
    vocabulary = max(len(counts), 1)
    return log((counts.get(reading, 0) + SMOOTHING) / (total + SMOOTHING * vocabulary))
```

`SMOOTHING = 0.1`. The denominator's vocabulary term is `len(counts)` — the number of
distinct successors this context has actually been seen with — so it is itself a function of
how little data the context has.

For a previous reading seen **exactly once**, `total = 1` and `vocabulary = 1`:

* its one observed successor scores `(1 + 0.1) / (1 + 0.1 · 1) = 1.1 / 1.1` = **exactly 1.0**,
  i.e. `log` = 0.0 nats, a free transition;
* every other successor scores `0.1 / 1.1` ≈ 0.0909, i.e. ≈ −2.398 nats.

A well-attested reading cannot match that unless one successor takes nearly all of its mass.
A reading with, say, 34 attestations over 20 distinct successors charges its *most frequent*
successor `(n + 0.1) / (34 + 2.0)`: −1.27 nats at n = 10, −0.58 at n = 20, and it only
approaches the singleton's free transition as n approaches 34, i.e. as the context becomes
deterministic in its own right. So Viterbi
can pay a penalty at one position to reach a once-seen reading and be repaid, with interest,
at the next. `docs/kri-selftest-fixes-2026-10-26.md` §1 traces exactly this: at the position
itself the pooled scoring prefers the common reading by about 1.5 nats, and the decoder gives
that back at the following position.

**Backing off to the pooled model does not fix it.** A singleton bigram is usually a
singleton in the pooled model too, so the pooled estimate is degenerate in the same way
(stated in the fixes doc, and the reason a pooled-only arm is not among the candidates
below).

**The same estimator appears five times**, and the defect is a property of the estimator, not
of the call site:

| Function | Context | In scope? |
| --- | --- | --- |
| `_transition` | previous reading → reading | **yes**, the primary target |
| `_sign_context` | (previous sign, sign) → reading | **yes** |
| `_next_sign_context` | (sign, next sign) → reading | **yes** |
| `_emission` | sign → reading | **separate arm only** (see §3) |
| `_lexicon_emission` | lexicon spelling → reading | **separate arm only** (see §3) |

`_emission` is held apart because it feeds the per-stage likelihoods that
`choose_stage_by_likelihood` routes on, and through them the expert paste gate and every
`--stage auto` number in the repository. A change there is a change to stage routing, which
is a different experiment with a different blast radius.

### What must not move with it

`UNREADABLE_EMISSION = log(SMOOTHING / (SMOOTHING + 1.0))` ≈ −2.40 is derived from
`SMOOTHING` and was set deliberately by audit A53 fix round 1. **Every candidate below keeps
`SMOOTHING = 0.1` and keeps `UNREADABLE_EMISSION` at its current value.** The candidates
change how probability mass is *normalised*, not the pseudocount. Any proposal that moves
`SMOOTHING` reopens A53 and needs its own pre-registration.

---

## 2. Candidate schemes

Three, all parameter-light, all applied through **one shared helper** so the three in-scope
functions cannot drift apart. The baseline arm is the code exactly as it stands.

Write c(h, r) for the count of reading r in context h, N(h) = Σ_r c(h, r), and
V_obs(h) = |{r : c(h, r) > 0}|.

### C1 — add-k over a fixed vocabulary

```
P(r | h) = (c(h, r) + k) / (N(h) + k · |R|)
```

with k = `SMOOTHING` = 0.1 and |R| the model's **global reading vocabulary** (the number of
distinct readings in `sign_reading`), fixed per model and independent of h.

*Why it would work:* the normaliser no longer shrinks when the context is rare, so a
once-seen context is correctly diffuse. With |R| in the tens of thousands, a singleton
context's observed successor lands near 1.1 / (1 + 0.1·|R|), far below 1.0.

*Risk, stated in advance:* with |R| large, **every** transition becomes a large negative
number and the transition term may be swamped by, or may swamp, the emission term at the
fixed `transition_weight = 0.6` / `sign_context_weight = 0.8` / `next_sign_weight = 0.8`.
The weights are **not** re-tuned in this experiment (see §4); if C1 fails only because of
scale, that is a result, and re-weighting is a separate pre-registration.

### C2 — Witten–Bell interpolation with a lower-order distribution

```
λ(h) = N(h) / (N(h) + V_obs(h))
P(r | h) = λ(h) · c(h, r)/N(h) + (1 − λ(h)) · P_lower(r)
```

`P_lower` is the model's **unigram reading distribution** (reading frequency over the fitted
corpus), itself add-k smoothed over |R| so it is never zero.

*Why it would work:* λ is derived from the counts, so there is nothing to tune. A context
seen once with one successor gets λ = 1/2, so at most half the mass sits on that successor —
the degenerate 1.0 cannot occur. A context seen 34 times over 20 successors gets λ ≈ 0.63 and
keeps most of its own evidence.

### C3 — absolute discounting with interpolated backoff

```
P(r | h) = max(c(h, r) − d, 0)/N(h) + (d · V_obs(h) / N(h)) · P_lower(r)
```

with d estimated by the Ney formula d = n₁ / (n₁ + 2n₂) over the model's own bigram count-of-
counts (n₁, n₂ = contexts-with-successors seen once, twice), **computed at fit time and
recorded in the run log**, not chosen by hand. `P_lower` is a two-level chain: the pooled
model's distribution for the same context where it has one, otherwise the unigram
distribution, mixed by the same formula.

*Why it would work:* it removes a fixed amount of mass from every observed count, so a count
of 1 is discounted hardest in relative terms, which is the exact case at issue. The pooled
level is included only as the *lower* order — the fixes doc is right that pooled alone does
not help, and nothing here claims otherwise.

### Arms

`off` (current code), `c1`, `c2`, `c3`, plus `c2_transition_only` (C2 applied to
`_transition` alone, the other two functions untouched) to separate the transition effect
from the sign-context effect. If the dev stage (§4) eliminates a candidate, its arm is
dropped before the test run and the elimination is recorded with the dev numbers that caused
it.

An **emission arm** (`c2_plus_emission`) is defined but **not run here**: it is listed so the
decision to exclude it is on the record, and it needs the stage-routing work of
`docs/kri-selftest-fixes-2026-10-26.md` §5 item 7 first.

---

## 3. Harness

`scripts/run_kri_fixes_eval.py` on branch `kri-fixes-2026-10-26` — the paired on/off
reading-model harness, extended with the arms above. It is the only measurement in this
repository that can see a decoder change: the competitive sets (v4, held-out, LE-v1) never
call `ReadingModel.predict_sequence` or `Segmenter.segment`, and
`scripts/run_reading_model_eval.py` attaches no pooled model.

Requirements on the extension, all to be satisfied **before** the run:

1. The arm table grows a smoothing field; `off` must reproduce the current behaviour
   byte-for-byte. A test asserts that `off` output equals the pre-change harness output on a
   pinned sample.
2. Decodes are memoised on what determines them (the harness already does this for routing
   and pooled fallback); a smoothing scheme is one more key, so N arms cost N decodes, not
   N × routings.
3. `tests/test_kri_fixes_eval.py` keeps its training/test hygiene assertions: every model,
   pooled or stage-restricted, is fitted on the training partition only.
4. Per-position output gains the baseline and arm transition scores for the chosen and the
   runner-up reading, so a win or loss can be attributed rather than asserted.

This experiment can only be run after the KRI-fixes branch has merged (or on a branch taken
from it); the pre-registration committed before the run names the exact base commit.

---

## 4. Split rule — and why it is stricter than the KRI one

`docs/kri-fixes-preregistration-2026-10-26.md` §1 could take its constants as given because
they were reasoned from a traced failure and fitted on nothing. **This experiment is
different: a smoothing scheme is a choice among alternatives, and choosing is tuning.** So
the split rule here is stricter.

**Dev.** A development set is drawn from the **training** partition only: whole texts, a
seeded draw of 10% of training texts, seed and procedure fixed in this document before the
draw, written to a manifest whose sha256 is recorded. During dev work, models are fitted on
training-minus-dev. **Every** choice is made here and only here:

* which of C1 / C2 / C3 survive;
* |R|'s exact definition for C1;
* `P_lower`'s exact definition for C2 and C3;
* d's count-of-counts estimator for C3;
* any arm that is dropped.

**Test.** The split `scripts/run_reading_model_eval.py` already defines —
`select_test_rows(..., split_by="text")`, every other argument at that function's defaults —
reached through `run_kri_fixes_eval.py`, which calls it rather than defining a split of its
own, and pinned by the content sha of the manifest its `--split-manifest` flag writes,
exactly as the KRI pre-registration §2 pins it. Step 0 regenerates the manifest and a
mismatch stops the run. It is
**looked at once**, for the surviving arms, after the dev stage is closed and its choices are
committed. A test-split number may not change any choice. If a surviving arm fails on test,
the result is "it failed"; it does not go back to dev and return.

**Hygiene the final document must restate:** the lexicon-leaking sources (Ramses, AES) leave
the test split while staying in training; exact duplicates and Jaccard ≥ 0.8 near-duplicates
are dropped; TLA and BBAW rows have no text identity and are split by sentence, a limitation
the existing script already prints.

**Not tuned here, and named so it cannot drift:** `SMOOTHING` (0.1),
`UNREADABLE_EMISSION`, `transition_weight` (0.6), `sign_context_weight` (0.8),
`next_sign_weight` (0.8), the pooled-fallback constants, the cartouche rule, and the
segmentation weights.

---

## 5. Pass rules (to be fixed before the run)

Hard gates first; a FAIL stops the run, is recorded, and is fixed on a new commit with a
dated addendum and a complete re-run — the A2.9 rule of
`docs/remeasure-preregistration-2026-10-25.md`. No subset re-runs, no reuse of a number from
a failed attempt.

**(a) Expert paste gate — hard.** 8/8 in `auto` and 8/8 in `declared`, and `--stage none`
unchanged at its by-design 3/8. Every segmentation and reading change in this project has had
to clear this.

**(b) Urk. IV / St Andrews gate — hard.** `GATE: PASS` in both modes in a keyed session
(`PRIVATE_DATA_DIR`), with the pinned row present once with its folded reading, as in the
2026-10-26 attempt-2 run.

**(c) Overall reading accuracy on the test split — hard, and the primary result.**
`acc_all(arm) ≥ acc_all(off)`, reported with paired per-position counts (arm-better /
off-better / unchanged) and a paired bootstrap CI over texts. Unlike the KRI measurement this
has a large denominator (3,473 test rows at the identity recorded in the KRI pre-registration),
so it is gated and not merely reported.

**(d) Singleton-context positions — the mechanism check.** Positions whose decoded reading has
a previous-reading context attested exactly once in the fitted model. Report the count, the
accuracy on them for every arm, and the paired counts. **Pre-registered expectation:** the
arms that fix the defect reduce the share of such readings that Viterbi selects. If accuracy
on these positions does not improve while (c) passes, the fix must be reported as "a change
the mechanism argument predicted, with no measured benefit at the positions it targets", not
as a win. If the count is below 30 the same low-n guard as KRI rule (b2) applies: reported,
not gated, no claim of improvement in either direction.

**(e) Boundary errors — hard.** `boundary_errors(arm) ≤ boundary_errors(off)` on the test
split. Boundary precision / recall / F1 and exact-segmentation count reported beside it.

**(f) Stage routing — disclosure, no threshold.** Every line whose chosen stage changes is
listed individually with row id, stage off, stage on and the per-stage attested coverage from
both. A run that reports a count without the list fails this rule.

**(g) Competitive sets — hard, but sanity only.** v4, held-out and LE-v1, legacy and
twin-controlled, at or above `release_baseline.json`'s floors (top-3 useful 0.80, MRR 0.70)
with **0** top-3 answers lost against the attempt-2 numbers in
`docs/remeasure-results-2026-10-26-attempt2.md`. The results note must say in these words
that these sets do not exercise the decoder: passing is not evidence for the change, it only
detects collateral damage. Budget for it honestly — the 2026-10-26 addendum to
`docs/remeasure-preregistration-2026-10-25.md` records 15 such runs taking between ~2 h and
~11 h 40 min on this Mac for identical work.

**(h) Calibration — reported, never gated.** Reliability bins and Brier score for the chosen
reading's confidence, per arm. There is no pre-registered target for what a confidence should
read, and inventing one after seeing the bins is the thing this document exists to prevent.

**(i) Runtime — reported.** Per-arm fit and decode wall time. C1 adds a vocabulary size, C2 a
unigram table, C3 a count-of-counts pass; none should be measurable, and if one is, it is
recorded.

### What must not regress, in one place

Paste 8/8 auto and declared; the Urk. IV gate; overall test accuracy; boundary errors;
competitive floors with 0 top-3 answers lost. Plus two that are not numbers: the A53
unreadable-emission constant stays where it is, and `off` must reproduce today's output
exactly.

---

## 6. What a passing run would and would not license

**Would:** shipping the winning scheme as the estimator for `_transition`, `_sign_context`
and `_next_sign_context`, described as a smoothing correction measured on the reading-model
test split, with the paired counts and the CI quoted beside the headline number.

**Would not:** any claim about `_emission` or the stage router; any claim about the private
self-test that prompted this (n ≈ 4 positions, not a measurement); any re-tuning of the
decoder weights; and any statement that the tool's *retrieval* quality improved — the
competitive sets cannot see this change.

---

## 7. Open questions for the Opus + Astra review

1. Is holding `_emission` out the right call, or does leaving a degenerate emission estimator
   in place make the transition fix unmeasurable?
2. C1's scale risk (§2): is the fixed-|R| normaliser testable at all without re-tuning
   `transition_weight`, or should C1 be dropped in favour of C2/C3 before any run?
3. Is a 10% seeded dev draw from training enough to choose among three schemes, or should the
   dev stage use its own holdout from a different source mix?
4. Rule (d) asks the mechanism to show itself. Is the singleton-context definition
   (previous-reading context attested exactly once) the right population, or should it be
   contexts below some count threshold?
5. Should `c2_transition_only` be the shipping candidate by default, on the grounds that it is
   the smallest change that addresses the traced failure?

---

## Revision 1 — review round (Opus + Astra), 2026-10-26

**Still a DRAFT. Still NOT RUN and NOT APPROVED.** This document is treated as append-only:
the text above is left exactly as reviewed, and this revision **supersedes** it wherever
the two disagree. Each item below names the section it replaces. A later approval must
point at this revision, not at §§1–7 alone. Nothing here is a result; every number below
is either arithmetic or a constant fixed in advance.

Where the two reviews disagreed on a judgement call, the more conservative option was
taken; each such case is marked **(conservative choice)**.

### R1. The defect, restated (replaces §1 "For a previous reading seen exactly once")

The degeneracy is not specific to contexts seen once. For **any** context h with exactly
one distinct successor (V_obs(h) = 1), whatever its count N(h):

```
(N + 0.1) / (N + 0.1 · 1) = 1.0   for every N ≥ 1
```

so the observed successor is free (0.0 nats) and every other successor costs
log(0.1 / (N + 0.1)). The defect is therefore **V_obs(h) = 1**, and every report of it is
broken down by N(h) in the bands **N = 1, N = 2–3, N ≥ 4**. A context with V_obs(h) ≥ 2 is
not degenerate in this sense, though its normaliser still shrinks with V_obs.

### R2. Stage routing is changed by every arm (replaces the §1 paragraph on `_emission`)

The §1 premise that only `_emission` feeds stage routing is **wrong**.
`choose_stage_by_likelihood` (`app/services/stage.py`) ranks stages on the full Viterbi path
score from `ReadingModel.predict_sequence_scored`, which includes the transition term and
both sign-context terms, i.e. exactly the terms every arm changes. Its docstring also relies
on each term being normalised by its own local count, "so it does not grow with corpus
size"; a backoff to a corpus-wide unigram distribution breaks that property and would bias
routing by corpus size, which is the Late Egyptian failure that docstring describes.

**Rule (conservative choice; Opus offered this or a hard gate, Astra asked for disclosure
plus per-stage likelihoods):** in every arm, stage routing is computed with the **`off`
estimator**. The arms change only the final decode, after the stage is chosen. Consequences,
all pre-registered:

* the routing decision must be **identical** to `off` on every line in every arm; any
  difference is a harness defect and a hard FAIL of rule (f′) below;
* in addition, for diagnosis only, the per-stage likelihoods each arm's estimator *would*
  produce are computed and reported beside the `off` ones and the per-stage coverage, so the
  routing effect of each estimator is on the record for a later routing experiment;
* a shipped arm would ship with routing still on the `off` estimator. Moving routing to a new
  estimator is a separate pre-registration (with `run_stage_routing_eval` as its gate).

### R3. Candidates (replaces §2 C1, C2, C3 and "Arms")

**C1 is dropped before any run (conservative choice).** Opus: with |R| in the tens of
thousands the transition term swamps the emission term at the fixed weights, and |R| is
corpus-size dependent, so the failure is predictable. Astra would keep it as a dev candidate
with fixed weights. Dropping it reduces the number of arms chosen among on dev and removes an
arm whose failure is predictable from arithmetic. It is listed here so the exclusion is on
the record.

Shared definitions, fixed now, for the **stage model being decoded** (fitted on the training
partition only):

* **Support.** R is the set of distinct non-empty readings appearing anywhere in the fitted
  model's counts (`sign_reading`, `reading_bigram` keys and successors, and the two sign-
  context tables). A candidate reading not in R — a lexicon-only reading, a composed reading,
  anything else — is **out of vocabulary (OOV)** and is scored through the OOV bucket below,
  never dropped.
* **Unigram (terminating level).** With c(r) the reading's count and N_tot = Σ c(r):
  `P_uni(r) = (c(r) + k) / (N_tot + k · (|R| + 1))`, k = `SMOOTHING` = 0.1, the `+1` being one
  OOV bucket; every OOV reading gets `k / (N_tot + k · (|R| + 1))`. Never zero.
* **The unreadable sentinel `''` is outside all of this.** In every arm, a transition
  **into** `''` and a transition **out of** `''` keep the value the current code gives them
  (the `off` formula), and `UNREADABLE_EMISSION` is unchanged. Under a unigram backoff a path
  through an unreadable group would otherwise become far more expensive, which would move
  the A53 balance and the PASTE_008-type comparison.
* **Unseen contexts.** In every arm, a context with N(h) = 0 (BOUNDARY included) keeps the
  current value `log(SMOOTHING)`. Only contexts with N(h) ≥ 1 change.
* **Lower-order distribution, per function.**
  * `_transition` (h = previous reading): `P_lower(r) = P_uni(r)`.
  * `_sign_context` (h = previous sign, sign) and `_next_sign_context` (h = sign, next sign):
    `P_lower(r) = P_sign(r | sign)`, the current sign's reading distribution, itself
    interpolated by Witten–Bell with the unigram:
    `P_sign(r | s) = λ_s · c(s, r)/N(s) + (1 − λ_s) · P_uni(r)`, λ_s = N(s)/(N(s) + V_obs(s));
    a sign with N(s) = 0 gives `P_sign = P_uni`. (Unigram reading frequency is the wrong
    lower order for a sign context: the natural backoff is P(reading | sign).)

**C2 — Witten–Bell.** For N(h) ≥ 1:
`P(r | h) = λ(h) · c(h, r)/N(h) + (1 − λ(h)) · P_lower(r)`, λ(h) = N(h)/(N(h) + V_obs(h)).
Correction of §2: a context seen once with one successor gets λ = 1/2, so that successor
scores **0.5 + 0.5 · P_lower(r)**, not "at most half" — slightly more than half. The
degenerate 1.0 still cannot occur, because P_lower(r) < 1.

**C3 — absolute discounting, interpolated.** For N(h) ≥ 1:
`P(r | h) = max(c(h, r) − d, 0)/N(h) + (d · V_obs(h)/N(h)) · P_lower_C3(r | h)`.

* **d (Ney):** `d = n₁ / (n₁ + 2·n₂)`, where n₁ and n₂ are the numbers of **bigram types**
  (h, r) — pairs, not contexts — with count exactly 1 and exactly 2 in that function's table
  of the fitted model (correction of §2's wording). One d per function per fitted model,
  computed at fit time and written to the run log. **Fallback:** if n₁ + 2·n₂ = 0, or d is
  not in the open interval (0, 1), d = 0.5, and the fallback is logged.
* **Lower order, two levels, terminating:** `P_lower_C3(r | h)` is the **pooled** model's C3
  estimate for the same h when the pooled model has N_pooled(h) ≥ 1, computed with the pooled
  model's own d and with the function's P_lower above taken from the pooled model; otherwise
  (pooled N(h) = 0) it is the function's P_lower from the stage model. The pooled level never
  recurses into another pooled level, so the chain ends at P_uni. When the model being
  decoded *is* the pooled model, the first level is skipped.

**Arms (final):** `off`, `c2`, `c3`, `c2_transition_only` (C2 on `_transition` alone; the
two sign-context functions keep the `off` formula). `c2_plus_emission` stays defined and
not run (§2). The §7 question 1 answer stands as revised: holding `_emission` out is right,
but not for the §1 reason (see R2); at each position the candidates are limited to readings
the sign actually has, so a degenerate emission estimator does not make the transition fix
unmeasurable.

### R4. Dev stage (replaces §4 "Dev" and fixes §4 "Test")

* **Seed:** `20261026`, a single `numpy.random.default_rng(20261026)` used for the draw only.
* **Draw:** from the **training** partition of the test split below (after that split is
  made), stratified by `source` at **10%** per source, so the dev source mix equals the
  training source mix. Sources with a text identity (AES by text id, Ramses by its official
  split's text grouping, St Andrews is not in the public corpus and is not used) are drawn as
  **whole texts**; TLA and BBAW, which have no text identity, are drawn as **single
  sentences**, the same stated limitation the test split has.
* **Hygiene, inherited from the test split:** dev rows from the lexicon-leaking sources
  (Ramses, AES) are removed from dev **when the lexicon is on** (they stay in
  training-minus-dev), exactly as `select_test_rows` does for test; dev rows whose exact sign
  string occurs in training-minus-dev, and rows with sign-group Jaccard ≥ 0.8 to a
  training-minus-dev row, are dropped. The counts dropped at each step are reported.
* **Manifest:** the dev row ids, with the seed and this procedure, are written to a manifest
  whose sha256 is recorded in the final pre-registration before any dev decode.
* **Minimum counts, checked before any dev decode:** ≥ 2,000 dev positions in total and
  ≥ 100 dev positions in the R5 population (V_obs = 1 by gold previous reading). If either is
  missed, the draw rate becomes **20%** once, same seed, recorded. If still missed, the
  experiment **stops** and is reported as not runnable at this corpus size; no other remedy.
* **Selection metric:** overall dev reading accuracy (positions, all sources pooled), with a
  paired bootstrap 95% CI per arm against every other arm (10,000 resamples over dev texts —
  TLA/BBAW sentences each their own group — seed `20261026`).
* **Exactly one primary arm leaves dev.** It is the arm with the highest dev accuracy,
  **except** that `c2_transition_only` is the primary arm whenever its dev accuracy lies
  within the paired 95% CI of the best arm (the smallest change that addresses the traced
  failure wins ties; both reviews asked for this as a pre-registered tie-break, not as a
  default after the fact). If no arm's dev accuracy exceeds `off`'s, there is no primary
  arm, the test split is **not** opened, and the result is "no candidate survived dev".
* The primary arm, the dev numbers that chose it and every elimination are committed
  **before** the test split is touched.

**Test (fixes §4 "Test").** `select_test_rows` has no defaults for most arguments, so they
are named here: `test_fraction = 0.2`, `exclude_duplicates = True`,
`near_duplicate_overlap = 0.8`, `lexicon_on = True`, `lexicon_exclude_sources = {"Ramses",
"AES"}`, `split_by = "text"` — the CLI defaults of `run_kri_fixes_eval.py` /
`run_reading_model_eval.py` at the time of writing, restated so they cannot drift. The
manifest sha256 pin of §4 stands.

**The test run is confirmatory for the primary arm only.** The other arms are decoded and
reported for the record, but no other arm can be shipped from this run, whatever its test
numbers.

### R5. Pass rules (replaces §5 rules (c), (d), (f), (g) and clarifies the retry rule)

**Retry rule (clarifies §5 intro).** A hard-gate FAIL may be re-run on a new commit only to
fix a **harness or procedural fault** (a crash, a wrong path, a violated hygiene assertion).
The fix may not change any estimator, P_lower, d, arm, constant, split, primary arm or
threshold. A re-run never authorises tuning against a test set that has already been seen;
if the primary arm fails a gate on test, the result is "it failed".

**(c′) Overall test accuracy — hard, primary.** PASS iff the **lower bound of the paired
bootstrap 95% CI** of acc(primary) − acc(`off`) is **> 0** (10,000 resamples over test texts,
TLA/BBAW sentences each their own group, seed `20261026`). The point estimate alone is not
enough **(conservative choice**: Opus asked for the gate to be a statement about the CI;
requiring the CI to exclude zero, rather than merely to sit around it, is the stricter
reading). Paired per-position counts (primary-better / `off`-better / unchanged) are
reported beside it.

**(d′) Mechanism positions — reported; the claim rule of §5 (d) stands.** The population is
fixed **by the gold data, not by any arm's decode**, so it is the same set of positions for
every arm: test positions i ≥ 1 whose **gold** previous reading h has V_obs(h) = 1 in the
fitted training model, reported in the bands N(h) = 1, 2–3, ≥ 4. For each arm: accuracy at
position i **and** at its predecessor i − 1 (the suspect transition can reward a wrong
reading at the preceding position), with paired counts against `off` at both. Reported
separately, as a diagnostic only: the share of positions where the arm's own decoded path
passes through a V_obs = 1 context. Secondary diagnostic, pre-declared, never gated: the
same report for contexts with V_obs(h) = 2 and N(h) ≤ 3. Low-n guard: a band with fewer than
30 positions is reported and never used for a claim in either direction.

**(e) Boundary errors** — unchanged.

**(f′) Stage routing — hard.** Under R2 routing uses the `off` estimator in every arm, so the
chosen stage must equal `off`'s on every line of the test split and of the expert pastes;
any difference FAILs. Reported beside it: the per-stage likelihoods each arm's estimator
would produce, and the per-stage attested coverage, line by line where the hypothetical
choice would differ.

**(g′) Competitive sets — hard, sanity only.** `release_baseline.json`'s floors apply **only
to the configuration that file specifies**: v4 (`competitive_ambiguity_eval_queries_v4.csv`),
`--stage auto --query-path app`, legacy pool floors 0.90 / 0.7917, and twin-controlled pool
(`--exclude-twins 0.7 --expected-tokens current`) floors 0.80 / 0.70. Every other comparison
is a **frozen per-set comparison** against the attempt-2 numbers in
`docs/remeasure-results-2026-10-26-attempt2.md`, with stage, token mode and pool pinned per
row and **0 top-3 answers lost**:

| Set | Pool | Tokens | Stage | Attempt-2 top-3 / MRR |
| --- | --- | --- | --- | --- |
| held-out 1 | legacy | current | auto | 0.75 / 0.6667 |
| held-out 1 | twins 0.7 | current | auto | 0.75 / 0.6667 |
| LE-v1 | legacy | current | auto | 0.8667 / 0.8000 |
| LE-v1 | twins 0.7 | current | auto | 0.8667 / 0.80 |

(Held-out 1's measured 0.75 / 0.6667 is already below the v4 floors, so applying those floors
to it would fail an unchanged decoder; that is why §5 (g) is replaced.) The §5 (g) sentence
that these sets do not exercise the decoder stays mandatory in the results note.

Rules (a), (b), (e), (h) and (i) of §5 stand unchanged.

### R6. Answers to the §7 questions, as adopted

1. Hold `_emission` out — yes, for the reason in R3, with routing separated per R2.
2. Drop C1 before any run — R3 **(conservative choice)**.
3. 10% stratified by source, with the minimum counts and the one-step 20% fallback of R4.
4. Gold-defined V_obs = 1 contexts in N bands, primary; V_obs = 2, N ≤ 3 secondary — R5 (d′).
5. Not a default after the fact: the pre-registered tie-break of R4 makes
   `c2_transition_only` primary when it is within the dev CI of the best arm.
