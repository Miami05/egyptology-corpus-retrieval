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
