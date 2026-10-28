# Pre-registration — transition smoothing in the reading model (FINAL, 2026-10-28)

**STATUS: FINAL, NOT RUN.** This is the single document the run is approved against. It
consolidates `docs/plan-transition-smoothing-2026-10-26.md` (the draft, §§1–7) and its
Revision 1 (R1–R6) and Revision 2 (R7–R9), both from Opus + Astra review rounds, into one
self-contained text with every constant, split, arm, metric, selection rule and pass rule
fixed. **It supersedes the draft and both revisions**; where they disagreed or left a
choice open, the conservative option was taken and §10 lists each such case. Nothing here
is a result.

What has and has not been looked at before this was written. No arm has been decoded on
any real data. The only real-corpus computation is the split itself: the row counts and the
sha256 of the three manifests of §4 (the test manifest, and the dev manifest at each of the
two draw rates), computed to pin them. Estimator behaviour has been seen on toy corpora in
unit tests only (`tests/test_transition_smoothing.py`), including one 300-sentence synthetic
corpus used as a golden for "the default is unchanged". This is an untouched confirmatory
registration for the test split.

No KRI or St Andrews material appears here, and none is read by the run: the only data input
of the harness is `data/processed/examples.csv`, and the runner stops at step 0 if a private
data directory is configured or present. (The draft's rule (b), the Urk. IV gate, read the
private St Andrews rows; it is withdrawn from this run, see §7 and §10.)

The experiment code is at the commit named in the approval: `app/services/reading_model.py`
(the schemes), `app/services/stage.py` (the router's explicit `smoothing="off"`),
`scripts/run_transition_smoothing_eval.py` (the harness),
`scripts/check_transition_smoothing_gates.py` (the rules as exit codes),
`scripts/run_transition_smoothing_prereg.sh` (the commands of §8).

---

## 1. The defect

`ReadingModel._transition` estimates P(reading | previous reading) by add-k over the
*observed* successor set:

```python
def _transition(self, previous_reading, reading):
    counts = self.reading_bigram.get(previous_reading, Counter())
    total = sum(counts.values())
    if total == 0:
        return log(SMOOTHING)
    vocabulary = max(len(counts), 1)
    return log((counts.get(reading, 0) + SMOOTHING) / (total + SMOOTHING * vocabulary))
```

`SMOOTHING = 0.1`. The vocabulary term is `len(counts)`, the number of distinct successors
the context has been seen with. Write c(h, r) for the count of reading r in context h,
N(h) = Σ_r c(h, r) and V_obs(h) = |{r : c(h, r) > 0}|.

**For any context with exactly one distinct successor, V_obs(h) = 1, whatever its count N:**

```
(N + 0.1) / (N + 0.1 · 1) = 1.0        for every N ≥ 1
```

so its observed successor is free (0.0 nats) and every other successor costs
log(0.1 / (N + 0.1)). A context seen once (N = 1) is the extreme case (every other successor
≈ −2.398 nats). A well-attested reading with, say, 34 attestations over 20 successors charges
its *most frequent* successor (n + 0.1) / (34 + 2.0), i.e. −1.27 nats at n = 10, and cannot
match a singleton's free transition. So Viterbi can pay a penalty at one position to reach a
reading whose own context is V_obs = 1, and be repaid at the next position. A context with
V_obs(h) ≥ 2 is not degenerate in this sense, though its normaliser still shrinks with
V_obs. Every report of the defect is broken down by N(h) in the bands **N = 1, N = 2–3,
N ≥ 4**.

Backing off to the pooled model does not fix it (a singleton bigram is usually a singleton in
the pooled model too), so a pooled-only arm is not among the candidates.

**The same estimator appears five times.** Three are in scope; the other two are not touched
by any arm:

| Function | Context | In scope |
| --- | --- | --- |
| `_transition` | previous reading → reading | yes, the primary target |
| `_sign_context` | (previous sign, sign) → reading | yes |
| `_next_sign_context` | (sign, next sign) → reading | yes |
| `_emission` | sign → reading | **no**: unchanged in every arm |
| `_lexicon_emission` | lexicon spelling → reading | **no**: unchanged in every arm |

At each position the candidates are limited to the readings the sign actually has, so a
degenerate emission estimator does not make the transition fix unmeasurable. Moving
`_emission` is a different experiment (it needs the stage-routing work first).

---

## 2. What changes, and what does not

* **Only the three in-scope estimators change, and only in the arms below.** The shipped
  decoder is the baseline arm `off`, which is today's code byte for byte.
* **Not tuned here, and named so it cannot drift:** `SMOOTHING = 0.1`,
  `UNREADABLE_EMISSION` (≈ −2.40, derived from `SMOOTHING`, set by audit A53 fix round 1),
  `transition_weight = 0.6`, `sign_context_weight = 0.8`, `next_sign_weight = 0.8`,
  `emission_weight = 1.0`, the pooled-fallback constants and the cartouche rule (every arm
  runs with the shipped defaults: pooled fallback **off**, cartouche constraint **on**,
  lexicon **on**, composed readings **off**), and the segmentation weights. The candidates
  change how probability mass is *normalised*, not the pseudocount. Any proposal that moves
  `SMOOTHING` reopens A53 and needs its own pre-registration.
* **Stage routing is computed with the `off` estimator in every arm (R2).**
  `choose_stage_by_likelihood` ranks stages on the full Viterbi path score from
  `ReadingModel.predict_sequence_scored`, which contains exactly the terms every arm
  changes, and it relies on each term being normalised by its own local count "so it does not
  grow with corpus size", a property a backoff to a corpus-wide unigram breaks. So in every
  arm the stage is chosen **once, by the `off` estimator**, and the arm changes only the final
  decode under that stage. `choose_stage_by_likelihood` takes an explicit
  `smoothing="off"` that is independent of the decoder's default scheme.
  Consequences, all part of this registration:
  * the stage a row is decoded under is identical in every arm; any difference is a harness
    fault and a hard FAIL of rule (f′);
  * for diagnosis only, the per-stage likelihoods each arm's estimator *would* produce, and
    the stage it would then choose, are computed besides (`hyp_stage`, `hyp_scores`,
    `hyp_coverage` in the lines file) and listed;
  * a shipped arm would ship with routing still on the `off` estimator. Moving routing to a
    new estimator is a separate pre-registration with `run_stage_routing_eval` as its gate.
* **Segmentation reads `sign_reading` counts only**, so the re-segmented line, and with it
  every boundary score, cannot differ between arms; the harness writes them per arm anyway
  and rule (e) gates on them (an inequality would be a harness fault).
* **The switch.** The decoder takes `smoothing` (`predict_sequence`,
  `predict_sequence_scored`); `None` means `TRANSITION_SMOOTHING_BY_DEFAULT`, which is
  `"off"` unless the environment variable `EGYPTOLOGY_TRANSITION_SMOOTHING` names a scheme.
  The variable exists so the product-path gates (expert paste, competitive sets,
  release check) can be run under the primary arm without a code change; it is never set in
  production, an unknown value raises at import, and the harness and the full test suite are
  run with it unset (the harness refuses to start otherwise).

---

## 3. Candidate schemes

Shared definitions, for the **model being decoded** (fitted on the training partition only,
and on the stage's compatible rows when it is a stage model):

* **Support R.** The set of distinct non-empty readings appearing anywhere in the model's
  counts: `sign_reading`, `reading_bigram` keys and successors, and the two sign-context
  tables, **excluding `''` and the BOUNDARY marker**. |R| is its size. A candidate reading
  not in R (a lexicon-only reading, a composed reading, anything else) is **out of
  vocabulary (OOV)** and is scored through the OOV bucket, never dropped.
* **Unigram (the terminating level).** c(r) = Σ over signs of `sign_reading[sign][r]`,
  N_tot = Σ_r c(r), k = `SMOOTHING` = 0.1:

  ```
  P_uni(r) = (c(r) + k) / (N_tot + k · (|R| + 1))
  ```

  the `+1` being one OOV bucket. Every OOV reading gets `k / (N_tot + k · (|R| + 1))`, the
  same formula with c(r) = 0; the bucket is a single pseudo-type, so the claim "sums to 1" is
  over R plus that one bucket. Never zero.
* **The unreadable sentinel `''` is outside all of this.** A transition **into** `''` (and a
  sign-context term with reading `''`) keeps the `off` formula, and a transition **out of**
  `''` is a context with N = 0, so it keeps `log(SMOOTHING)`. `UNREADABLE_EMISSION` is
  unchanged. Under a unigram backoff a path through an unreadable group would otherwise
  become far more expensive, which would move the A53 balance.
* **Unseen contexts.** A context with N(h) = 0 keeps `log(SMOOTHING)` in every arm. Only
  contexts with N(h) ≥ 1 change.
* **Sentence edges are not changed by any arm (R3, R8).** The model does hold counts for the
  BOUNDARY marker (`fit` counts the first reading of a sentence in `reading_bigram[BOUNDARY]`,
  and the edge keys of the two sign-context tables), so these contexts have N ≥ 1 and would
  otherwise be smoothed. They are not: a transition out of BOUNDARY (position 0), a sign
  context whose previous sign is BOUNDARY (position 0) and a next-sign context whose next sign
  is BOUNDARY (the last position) keep the add-k value in every arm, exactly as R3 says
  ("BOUNDARY included keeps the current value") and as the R8 population needs (position 0
  has the BOUNDARY context, which no arm changes). BOUNDARY is excluded from the support R.
  A unit test asserts the equality for every such key in every mode. A smoothed arm therefore
  changes only transitions between two real readings and sign contexts between two real signs.
* **Lower-order distribution, per function.**
  * `_transition` (h = previous reading): `P_lower(r) = P_uni(r)`.
  * `_sign_context` (h = previous sign, sign) and `_next_sign_context` (h = sign, next
    sign): `P_lower(r) = P_sign(r | s)`, where s is the **current sign** (the second element
    of the first key, the first element of the second), itself interpolated by Witten–Bell
    with the unigram:

    ```
    P_sign(r | s) = λ_s · c(s, r)/N(s) + (1 − λ_s) · P_uni(r),   λ_s = N(s) / (N(s) + V_obs(s))
    ```

    where c(s, r) and N(s) are `sign_reading` counts. A sign with N(s) = 0 gives
    `P_sign = P_uni`. (Unigram reading frequency is the wrong lower order for a sign
    context: the natural backoff is P(reading | sign).)

### C2 — Witten–Bell interpolation

For N(h) ≥ 1:

```
P(r | h) = λ(h) · c(h, r)/N(h) + (1 − λ(h)) · P_lower(r),     λ(h) = N(h) / (N(h) + V_obs(h))
```

There is nothing to tune: λ is derived from the counts. A context seen once with one
successor gets λ = 1/2, so that successor scores **0.5 + 0.5 · P_lower(r)**, not 1.0: the
degenerate free transition cannot occur because P_lower(r) < 1. A context seen 34 times over
20 successors gets λ ≈ 0.63 and keeps most of its own evidence.

### C3 — interpolated absolute discounting

For N(h) ≥ 1:

```
P(r | h) = max(c(h, r) − d, 0) / N(h) + (d · V_obs(h) / N(h)) · P_lower_C3(r | h)
```

* **d (Ney):** `d = n₁ / (n₁ + 2·n₂)`, where n₁ and n₂ are the numbers of **bigram types**
  (h, r), pairs and not contexts, with count exactly 1 and exactly 2 in that function's table
  of the fitted model. One d per function per fitted model, derived from the model's own
  counts at first use and written to the run log (`dev_smoothing_report.json` /
  `test_smoothing_report.json`). **Fallback:** if n₁ + 2·n₂ = 0, or d is not in the open
  interval (0, 1) (which includes d = 1, i.e. n₂ = 0), then d = 0.5, and the report marks
  `fallback: true`.
* **Lower order, two levels, terminating.** `P_lower_C3(r | h)` is the **pooled** model's C3
  estimate for the same h when the pooled model has N_pooled(h) ≥ 1, computed with the pooled
  model's own d and with the function's P_lower taken from the pooled model; otherwise
  (N_pooled(h) = 0, or no pooled model is attached) it is the function's P_lower from the
  decoded model. The pooled level never recurses into another pooled level, so the chain ends
  at P_uni. When the model being decoded *is* the pooled model, the first level is skipped.
  The pooled model is included only as the *lower* order; the earlier finding stands that
  pooled alone does not help. Vocabulary note: for a stage model whose pooled level applies,
  the distribution sums to 1 over the **pooled** model's R plus the OOV bucket (R_stage ⊆
  R_pooled); this is what the unit tests check.

### Arms (final)

| Arm | `_transition` | `_sign_context`, `_next_sign_context` |
| --- | --- | --- |
| `off` | add-k (today's code) | add-k |
| `c2_transition_only` | Witten–Bell | add-k |
| `c2` | Witten–Bell | Witten–Bell |
| `c3` | absolute discounting | absolute discounting |

**C1 (add-k over a fixed |R|) is dropped before any run.** With |R| in the tens of thousands
the transition term swamps the emission term at the fixed weights, |R| is corpus-size
dependent, and the failure is predictable from arithmetic; the weights are not re-tuned in
this experiment. It is listed so the exclusion is on the record. `c2_plus_emission` is
defined (C2 on `_emission` as well) and **not run**; it needs the stage-routing work first.

---

## 4. Data, splits and the dev draw

**Corpus.** `data/processed/examples.csv`, sha256
`44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2`, 130,472 rows. Sources
BBAW, Ramses, TLA, AES. No private, KRI or St Andrews row is in it. `scripts/eval_guards.py`
sha256 `17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950` and
`scripts/run_reading_model_eval.py` sha256
`373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5` are pinned at step 0.

**Test split.** `scripts.run_reading_model_eval.select_test_rows`, called with
`test_fraction = 0.2`, `exclude_duplicates = True`, `near_duplicate_overlap = 0.8`,
`lexicon_on = True`, `lexicon_exclude_sources = {"Ramses", "AES"}`, `split_by = "text"`
(the CLI defaults of the earlier harnesses, restated so they cannot drift). Whole texts are
held out (AES text id; Ramses by Rosmorduc's official split); TLA and BBAW rows have no text
identity and are split by sentence, a limitation the script prints. Exact duplicates and
sign-group Jaccard ≥ 0.8 near-duplicates are dropped from test; the lexicon-leaking sources
(Ramses, AES) leave the test split while staying in training.

| | |
| --- | --- |
| aligned sentences | 59,504 |
| train / test | 52,210 / 3,473 |
| dropped from test | 829 exact duplicates, 202 near-duplicates, 2,790 lexicon-leaking rows |
| test source mix | BBAW 1,013, TLA 2,460 |
| test manifest sha256 (source, text id, sentence id, sign string of every test row) | `ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba` |

The test manifest is the identity of every test row; step 1 regenerates it and a mismatch
stops the run. It is the same split, byte for byte, as the earlier KRI-fixes registration.

**Dev draw (R4).**

* Seed `20261026`, a single `numpy.random.default_rng(20261026)` used for the draw only.
* The draw is from the **training partition** of the test split above (after that split is
  made), stratified by `source` at **10%** per source. Units are `eval_guards.text_group_keys`:
  an AES text is one unit and is drawn **whole**; every other row (TLA, BBAW, and Ramses, whose
  rows carry no text identity beyond the official split) is its own unit, a **single
  sentence**. Per source, in sorted source order, the unit keys are sorted and
  `max(1, int(rate · n + 0.5))` of them are taken without replacement from the one generator
  (`rng.choice(n, size=take, replace=False)`), so the draw is a function of corpus, rate and
  seed, and not of row order.
* **Hygiene, inherited from the test split, with R4's rule for the leaking sources.** With the
  lexicon on, drawn rows of Ramses and AES are removed from dev and **stay in the training
  partition**, i.e. they go back into `fit` (R4: "stay in training-minus-dev"); they are
  counted as "leaking" below. Then all comparisons are against `fit` = the training partition
  minus the drawn rows that are dev candidates: first dev candidates whose exact sign string
  occurs in `fit` (counted, dropped), then rows at sign-group Jaccard ≥ 0.8 to a `fit` row.
  The counts dropped at each step are written to the manifests and the dev-counts files. A
  drawn TLA or BBAW row that hygiene drops as a duplicate leaves the experiment: it is in
  neither dev nor `fit`, as a dropped test row is in neither test nor train, so a dev row can
  never have a twin among the rows its model is fitted on. Models in the dev stage are fitted
  on `fit` only.
* **Manifests, pinned.** The dev rows after hygiene are written to a manifest
  (`source, source_text_id, source_sentence_id, hieroglyphs_norm`) whose sha256 is pinned
  here, **before any dev decode**, for both draw rates the registration can use:

| Draw rate | Drawn rows | Dropped: exact / near / leaking | Dev rows (BBAW, TLA) | `fit` rows | Dev manifest sha256 |
| --- | --- | --- | --- | --- | --- |
| 10% | 5,072 | 291 / 59 / 3,332 | 1,390 (409, 981) | 50,470 | `52415842fbb209d955b5d28d48011f462cb5a0d756400c1f8e2d76f191263344` |
| 20% | 10,024 | 563 / 101 / 6,545 | 2,815 (823, 1,992) | 48,731 | `11dfe145090bb6a3ee4d846f428b595a8fba79787662193d9a20677b3328a0b3` |

("Leaking" rows are drawn Ramses and AES rows moved back into `fit`, not lost: `fit` = 52,210
train rows − dev rows − exact − near drops. Dev rows are listed as BBAW, TLA. The numbers are
those of the 2026-10-28 revision; the earlier ones, with leaking rows leaving the experiment,
are withdrawn.)

* **Minimum counts, checked before any arm is decoded.** The dev set must have **≥ 2,000 dev
  positions** in total and **≥ 100 dev positions in the R5 population** (gold previous reading
  with V_obs = 1 in the routed stage's `_transition` table, §6), the latter needing the dev
  models and the `off` routing of the dev rows (no arm decodes). If either is missed at 10%,
  the draw rate becomes **20%** once, same seed, and the models are refitted on that draw's
  `fit`. If still missed, the experiment **stops** (exit 4, "not runnable at this corpus
  size"); no other remedy. The step taken is recorded in `dev_counts.json`.

The dev rows come out as TLA and BBAW only (Ramses and AES are drawn, then moved back to
training under the lexicon-hygiene rule), which is also the source mix of the test split.

---

## 5. The dev stage and the selection rule (R4, R7)

**Every choice among the candidates is made here and only here**: which arm leaves dev, and
nothing else (the definitions of §3 are fixed in this document, not chosen on dev). Nothing
about C1, |R|, P_lower or d is open on dev.

**Unit of scoring.** A dev position is scored exactly as in §6 (reading track, gold
grouping). acc(a) = correct positions / all positions, pooled over every dev row and all
sources.

**Bootstrap, fixed.** Resampling units are dev groups: `text_group_keys` (an AES text would
be one group; every TLA and BBAW sentence is its own). `10,000` resamples with replacement:
the index matrix is `numpy.random.default_rng(20261026).integers(0, G, size=(10000, G),
dtype=numpy.int32)` over the groups sorted by key, drawn **once** in the checker (a separate
generator from the draw's) and the **same** matrix reused for every comparison. In each
resample the difference is Σ correct_a − Σ correct_b over the resampled groups' positions,
divided by the number of resampled positions (a ratio of sums, not a mean of per-group
accuracies). The 95% CI is the percentile interval, the 2.5th and 97.5th percentiles
(`numpy.percentile`, linear interpolation) of the 10,000 differences.

**Selection (paired differences only).**

1. **Eligibility versus `off`.** For each arm a in {`c2_transition_only`, `c2`, `c3`},
   Δ_a = correct(a) − correct(`off`) on the full dev set (a point estimate, no resampling).
   a is **eligible** iff Δ_a > 0, strictly: at least one more correct dev position than
   `off`. The dev stage only selects; the confirmatory CI requirement is rule (c′) on test.
2. If no arm is eligible, there is **no primary arm**, the test split is **not opened**, and
   the result is "no candidate survived dev".
3. **Best arm** b = the eligible arm with the largest Δ. An exact tie in Δ is broken by the
   simplicity order, simplest first.
4. **Simplicity order, fixed:** `c2_transition_only` < `c2` < `c3` (`c2` before `c3`: C2 has
   no estimated constant and no pooled level; C3 adds d and the pooled lower order).
5. **Primary arm, deterministic.** Walk the eligible arms in simplicity order; the primary
   arm is the **first** eligible arm a for which the lower bound of the paired 95% CI of
   acc(b) − acc(a) is **≤ 0** (a is not distinguishably worse than the best). b itself always
   qualifies, so whenever at least one arm is eligible **exactly one** primary arm results.
   `c2_transition_only` is therefore primary when it is eligible and not distinguishably worse
   than the best; otherwise the C2/C3 choice is made by the same rule.

**Recorded before the test split is touched.** `scripts/check_transition_smoothing_gates.py
dev` writes `dev_record.json`: every Δ_a, every paired CI used in the walk, the eligible set,
b, the primary arm, the dev manifest sha256, the draw rate and the minimum counts, and the
commit the dev phase ran at. The record is **committed as the only change** to the branch,
at `docs/transition-smoothing-dev-record-2026-10-28.json`, **before** the test phase starts.
The test phase refuses to start unless that file is present at `HEAD`, names a primary arm,
carries the pinned manifest sha256 for its draw rate, and `git diff --name-only` between the
dev-phase commit and `HEAD` is exactly that one path (`preflight`). The primary arm used for
the test gates is read from the committed file.

**The test run is confirmatory for the primary arm only.** The other arms are decoded and
reported for the record, but no other arm can be shipped from this run, whatever its test
numbers. A test-split number may not change any choice; if the primary arm fails a gate on
test, the result is "it failed" and does not go back to dev.

---

## 6. Scoring and the mechanism population (R8)

* **Accuracy is scored on the reading track only.** Rules (c′), (d′) and §5 score the decoder
  on the row's **gold** sign grouping: one prediction per gold group, prediction k aligned to
  gold position k by index, correct iff `prediction.predicted == gold_reading` (exact string
  equality, no extra folding). A split, merged or unmatched prediction cannot occur on this
  track; the harness raises on `len(predictions) != len(gold_groups)` for every row and arm,
  and that is a harness fault (exit 3), never scored. Rows whose sign and reading counts differ
  are skipped, as in the earlier harnesses.
* **Segmentation-track words are never used for accuracy.** The re-segmented line (the row's
  signs with the spaces removed, segmented by the pooled-model segmenter) feeds only rule (e)
  and the stage router. No reading accuracy over the re-segmented line is reported.
* **Population (R5 (d′), made exact).** Member positions are gold positions i ≥ 1 of a row
  (position 0 has the BOUNDARY context, which no arm changes, §3) whose gold previous reading
  h = gold_reading[i − 1] satisfies V_obs(h) = 1 in the `_transition` table of the fitted
  model **of the stage the row was routed to** (the `off` routing, identical in every arm; the
  pooled model when no stage was chosen). h = `''` is excluded (R3 leaves transitions out of
  `''` unchanged). **Membership never depends on any arm's prediction.** Members are reported
  in the bands N(h) = 1, 2–3, ≥ 4. The **secondary diagnostic**, never gated, is the same
  report for contexts with V_obs(h) = 2 and N(h) ≤ 3.
* **What is reported per member.** For every arm, the pair (correct at i, correct at i − 1),
  both on the reading track, plus 2×2 paired counts against `off` at i and at i − 1
  separately. The i − 1 tallies are over **members**, not distinct positions: when two
  consecutive positions are both members, the shared position is counted once as a
  predecessor and once as a member, and the report gives the number of such overlaps. The
  diagnostic "the arm's own path passes through a V_obs = 1 context" is computed from the
  arm's decoded reading at i − 1 and reported as a count of members together with n and as
  a share of members (`count/n (share)`). **Low-n guard:** a band
  with fewer than 30 positions is reported and is never used for a claim in either direction.
* **Per-position attribution (§3 of the draft).** Each position row carries the baseline and
  arm transition log-probabilities of the chosen reading and of a runner-up, from the
  decoded previous reading: `t_chosen_off`, `t_chosen_arm`, `t_runner_off`, `t_runner_arm`,
  where the runner-up is the best-attested candidate of the group's evidence other than the
  chosen reading. A win or loss can be attributed instead of asserted.

---

## 7. Pass rules

Hard gates first; a FAIL stops the run, is recorded, and is handled by the retry rule.

**Retry rule.** A hard-gate FAIL may be re-run on a new commit **only to fix a harness or
procedural fault** (a crash, a wrong path, a violated hygiene assertion). The fix may not
change any estimator, P_lower, d, arm, constant, split, primary arm or threshold, and the
re-run is a complete re-run of its phase: no subset re-runs, no reuse of a number from a
failed attempt. A re-run never authorises tuning against a test set that has already been
seen; if the primary arm fails a gate on test, the result is "it failed".

Rules (a), (e) and (g′) apply to the primary arm, with the product-path steps run under
`EGYPTOLOGY_TRANSITION_SMOOTHING=<primary>`.

**(a) Expert paste gate — hard.** 8/8 in `--stage auto` and 8/8 in `--stage declared`, and
`--stage none` unchanged at its by-design 3/8, with the same per-paste outcome as attempt 2
of the 2026-10-25 re-measurement (`~/egyptology-runs/remeasure-2026-10-25/paste_none.csv`).

**(b) Urk. IV / St Andrews gate — withdrawn from this run.** It reads the private St Andrews
rows (`--private-dir`), which this run does not read (no KRI or St Andrews data anywhere; the
runner's step 0 refuses a configured or present private directory). Nothing in this experiment
licenses shipping on its own: the gate is a separate step for whoever ships, on the product
path under the primary arm, outside this registration. The letter is kept so that the other
rules keep theirs.

**(c′) Overall test accuracy — hard, the primary result.** PASS iff the **lower bound of the
paired bootstrap 95% CI** of acc(primary) − acc(`off`) is **> 0**: 10,000 resamples over test
groups (§5 definition: each TLA/BBAW sentence its own group), a fresh
`default_rng(20261026)`, percentile interval, ratio of sums. The point estimate alone is not
enough. Paired per-position counts (primary-better / `off`-better / unchanged) are reported
beside it, per source as well; all four arms are reported with the same interval.

**(d′) Mechanism positions — reported.** The population and tallies of §6, for every arm. The
claim rule stands: the arms that fix the defect are expected to reduce the share of
V_obs = 1 paths Viterbi selects. If accuracy on these positions does not improve while (c′)
passes, the result is reported as "a change the mechanism argument predicted, with no measured
benefit at the positions it targets", not as a win. A band under 30 positions is reported and
never used for a claim.

**(e) Boundary errors — hard.** `boundary_errors(primary) ≤ boundary_errors(off)` on the test
split (false-positive plus false-negative boundaries of the re-segmented lines). Precision,
recall, F1 and exact-segmentation count are reported beside it for every arm. Because the
segmenter reads `sign_reading` counts only, equality is expected; a difference is a harness
fault.

**(f′) Stage routing — hard.** Under §2 routing uses the `off` estimator in every arm, so the
stage a row is decoded under must equal `off`'s on **every line of the test split** (any
difference FAILs), and the **expert pastes** must be routed identically with and without the
candidate (`stage_used`, `stage_inferred` and the printed per-stage likelihoods of
`paste_auto.csv`, run under the primary arm, equal those of `paste_auto_off.csv`, run with the
default). Reported beside it, **line by line**, every test line where an arm's hypothetical
estimator would choose a different stage than `off`, with row id, `off` stage and scores and
coverage, and the hypothetical stage and scores and coverage. A run that reports a count
without the list fails this rule.

**(g′) Competitive sets — hard, sanity only.** `release_baseline.json`'s floors apply **only to
the configuration that file specifies**: v4 (`competitive_ambiguity_eval_queries_v4.csv`),
`--stage auto --query-path app`, legacy pool floors **0.90 / 0.7917**, and twin-controlled pool
(`--exclude-twins 0.7 --expected-tokens current`) floors **0.80 / 0.70**. Every other
comparison is a **frozen per-set comparison** against attempt 2 of the 2026-10-25
re-measurement (`docs/remeasure-results-2026-10-26-attempt2.md`; its run directory is `BASE`
in the runner), per query, with stage, token mode and pool pinned per row and **0 top-3
answers lost**:

| Set | Pool | Tokens | Stage | Attempt-2 top-3 / MRR |
| --- | --- | --- | --- | --- |
| v4 | twins 0.7 (T) | current | auto | 0.85 / 0.75 (also the floor check) |
| v4 | legacy, historical (L) | frozen | auto | 0.90 / 0.80 (also the legacy floor check) |
| held-out 1 | legacy (C) | current | auto | 0.75 / 0.6667 |
| held-out 1 | twins 0.7 (T) | current | auto | 0.75 / 0.6667 |
| LE-v1 | legacy (C) | current | auto | 0.8667 / 0.80 |
| LE-v1 | twins 0.7 (T) | current | auto | 0.8667 / 0.80 |

(Held-out 1's measured 0.75 / 0.6667 is already below the v4 floors, so applying those floors
to it would fail an unchanged decoder.) The release check (`verify_release.py`) is run under
the primary arm and must reproduce the v4 L, v4 T and paste runs of steps 4 and 6 exactly.
**The results note must say in these words that these sets do not exercise the decoder:
passing is not evidence for the change, it only detects collateral damage.**

**(h) Calibration — reported, never gated.** Reliability bins and Brier score of the shipped
`confidence` of the chosen reading, per arm, over all positions and over positions with a
reading. There is no pre-registered target.

**(i) Runtime — reported.** Per-arm decode wall time, the `off` routing, each arm's diagnostic
routing, the model fits and the time to derive the discount tables. None should be
measurable; if one is, it is recorded.

**What must not regress, in one place:** paste 8/8 auto and declared and `none` unchanged at
3/8; the CI of overall test accuracy (lower bound > 0); boundary errors; the
stage each line is decoded under; competitive floors with 0 top-3 answers lost. Plus two that
are not numbers: the A53 unreadable-emission constant stays where it is, and `off` must
reproduce today's output exactly (a golden-hash unit test of 60 decodes made with the code
before the schemes existed, the verbatim-formula test of every scoring term, and the
harness's own `off` arm being the shipped `predict_sequence`).

---

## 8. Exact commands

The commands are `scripts/run_transition_smoothing_prereg.sh`, reproduced verbatim below.
`tests/test_check_transition_smoothing_gates.py` fails if the two differ. Run it with
**bash**, in the worktree, one heavy process at a time, with nothing else running, **in two
phases**:

```
cd /Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/transition-smoothing-2026-10-28
bash scripts/run_transition_smoothing_prereg.sh dev  APPROVED_SHA
# commit $R/dev_record.json as docs/transition-smoothing-dev-record-2026-10-28.json, nothing else
bash scripts/run_transition_smoothing_prereg.sh test APPROVED_SHA2
```

`APPROVED_SHA` is the full 40-character id of the commit the approver signed off on for the
dev phase; `APPROVED_SHA2` is the id of the commit that adds the dev record (and nothing
else). Each is the one extra input of its phase, and without a phase and exactly one 40-hex
argument the runner exits 2 before allocating an attempt directory. The runner enters the
worktree itself and asserts the toplevel, the branch, that `HEAD` **is** the approved
commit, a clean tree, that the switch variable is unset, and that no private data directory is
configured or present. The attempt directories are
`~/egyptology-runs/transition-smoothing-2026-10-28-dev-attemptN` and `…-test-attemptN`,
fresh each time and never overwritten. If the dev record names no primary arm, the dev phase
ends the experiment: the test phase's preflight refuses to start. The registered run sets
neither `TS_RUNS_BASE` nor `TS_STOP_AFTER`.

```bash
#!/usr/bin/env bash
# The exact command list of docs/transition-smoothing-preregistration-2026-10-28.md section 8.
# Run it twice, in this order, one phase at a time:
#   bash scripts/run_transition_smoothing_prereg.sh dev  APPROVED_SHA
#   (commit $R/dev_record.json as docs/transition-smoothing-dev-record-2026-10-28.json - the
#    ONLY change - then take the new commit's full id as the second APPROVED_SHA)
#   bash scripts/run_transition_smoothing_prereg.sh test APPROVED_SHA
# APPROVED_SHA is the full 40-character commit id the approver signed off on for that phase.
# Step 0 stops unless HEAD is exactly that commit (a different clean commit on the branch,
# with different code, must not be able to run as the registered one).
# (bash, not zsh: zsh does not word-split, and this file is the registered commands).
# tests/test_check_transition_smoothing_gates.py checks that section 8 reproduces this file
# verbatim.
#
# Two environment variables exist ONLY to prove the first steps run before the registered
# run (a dry check into a scratch directory). The registered run sets neither:
#   TS_RUNS_BASE   parent directory of the attempt directory (default ~/egyptology-runs)
#   TS_STOP_AFTER  stop cleanly after this step number (default: run every step)
set -euo pipefail

if [ "$#" -ne 2 ] || ! [[ "$1" =~ ^(dev|test)$ ]] || ! [[ "$2" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: bash scripts/run_transition_smoothing_prereg.sh dev|test APPROVED_SHA (the full 40-hex commit id)" >&2
  exit 2
fi
PHASE=$1
APPROVED_SHA=$2

WT=/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/transition-smoothing-2026-10-28
BRANCH=transition-smoothing-2026-10-28
PY=/Users/lediodurmishaj/venvs/egyptology/bin/python
BASE=$HOME/egyptology-runs/remeasure-2026-10-25     # attempt 2 of the 2026-10-25 run
B=data/benchmarks
RECORD=docs/transition-smoothing-dev-record-2026-10-28.json
TEST_MANIFEST_SHA=ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba
DEV_MANIFEST_SHA_R10=52415842fbb209d955b5d28d48011f462cb5a0d756400c1f8e2d76f191263344
DEV_MANIFEST_SHA_R20=11dfe145090bb6a3ee4d846f428b595a8fba79787662193d9a20677b3328a0b3
RUNS=${TS_RUNS_BASE:-$HOME/egyptology-runs}
STOP_AFTER=${TS_STOP_AFTER:-}
SWITCH=EGYPTOLOGY_TRANSITION_SMOOTHING

# A fresh attempt directory, never an existing one: evidence is never overwritten.
N=1
while [ -e "$RUNS/transition-smoothing-2026-10-28-$PHASE-attempt$N" ]; do N=$((N + 1)); done
R=$RUNS/transition-smoothing-2026-10-28-$PHASE-attempt$N
mkdir -p "$RUNS"
mkdir "$R"
echo "attempt directory: $R"

log() { echo "$(date -u +%FT%TZ) $*" >> "$R/run_log.txt"; }
# Every step goes through run: a non-zero exit is logged and STOPS the run (rule h).
run() {
  local label=$1
  shift
  log "START $label"
  local code=0
  "$@" || code=$?
  log "END $label exit=$code"
  if [ "$code" -ne 0 ]; then
    log "STOP at $label (rule h): fix a harness or procedural fault on a new commit, addendum, re-run the phase"
    echo "STOP at $label (exit $code); see $R/run_log.txt" >&2
    exit "$code"
  fi
}
done_after() {
  if [ "$STOP_AFTER" = "$1" ]; then
    log "stopped after step $1 (TS_STOP_AFTER; not a registered run)"
    echo "stopped after step $1 (TS_STOP_AFTER)"
    exit 0
  fi
}

# Step 0 - the right worktree, branch and a clean tree; pin everything.
cd "$WT"
run step0-toplevel test "$(git rev-parse --show-toplevel)" = "$WT"
run step0-branch test "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH"
echo "$APPROVED_SHA" > "$R/approved_commit.txt"
run step0-approved-commit test "$(git rev-parse HEAD)" = "$APPROVED_SHA"
run step0-clean test -z "$(git status --porcelain)"
# The default decoder scheme must be add-k: a switch set in the launching shell would make
# the baseline arm something else.
run step0-switch-unset test -z "${!SWITCH:-}"
# No private data of any kind: no keyed directory in the environment, none in the worktree.
run step0-no-private-env test -z "${PRIVATE_DATA_DIR:-}"
run step0-no-private-dir test ! -e data/private
if [ "$PHASE" = test ]; then
  run step0-attempt2-dir test -d "$BASE"
fi
# The deploy tests trap HUP/INT/TERM; a signal ignored at launch (nohup, `cmd &`) cannot be
# trapped again, so those tests would fail for the launcher, not the code.
run step0-signals "$PY" -c "import signal, sys; sys.exit(any(signal.getsignal(s) == signal.SIG_IGN for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)))"
git rev-parse HEAD > "$R/commit.txt"
shasum -a 256 data/processed/examples.csv scripts/eval_guards.py \
  scripts/run_reading_model_eval.py scripts/run_kri_fixes_eval.py \
  scripts/check_kri_fixes_gates.py scripts/run_transition_smoothing_eval.py \
  scripts/check_transition_smoothing_gates.py scripts/run_transition_smoothing_prereg.sh \
  app/services/reading_model.py app/services/stage.py > "$R/shas.txt"
printf '%s\n' \
  "44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2  data/processed/examples.csv" \
  "17977c1e4f9a10f8a5067bb4bb5d3f2ffe4b280048ed2e8b465877cde45c0950  scripts/eval_guards.py" \
  "373f2efb001cb2431ea54c9666159bc2cdcc96d0d7f9673d8cb88c8f70d312b5  scripts/run_reading_model_eval.py" \
  > "$R/pinned_shas.txt"
run step0-pinned-shas shasum -a 256 -c "$R/pinned_shas.txt"
"$PY" --version > "$R/env.txt"
"$PY" -m pip freeze >> "$R/env.txt"
done_after 0

# Step 1 - the split manifests, checked by content (section 2 and R4).
printf '%s\n' \
  "$TEST_MANIFEST_SHA  $R/manifests/split_manifest.csv" \
  "$DEV_MANIFEST_SHA_R10  $R/manifests/dev_manifest_r10.csv" \
  "$DEV_MANIFEST_SHA_R20  $R/manifests/dev_manifest_r20.csv" > "$R/manifest_sha.txt"
run step1-manifests "$PY" scripts/run_transition_smoothing_eval.py \
  --phase manifests --out-dir "$R/manifests" > "$R/step1.txt" 2>&1
run step1-manifest-sha shasum -a 256 -c "$R/manifest_sha.txt"
if [ "$PHASE" = test ]; then
  # The dev record is committed, names a primary arm, and is the only change since the dev run.
  run step1-preflight "$PY" scripts/check_transition_smoothing_gates.py preflight \
    --record "$RECORD" > "$R/step1_preflight.txt" 2>&1
  run step1-primary-arm "$PY" scripts/check_transition_smoothing_gates.py primary \
    --record "$RECORD" > "$R/primary_arm.txt"
  PRIMARY=$(cat "$R/primary_arm.txt")
fi
done_after 1

if [ "$PHASE" = dev ]; then
  # Step 2 - the dev stage: minimum counts first, then all four arms on the dev rows.
  run step2-dev-harness env -u "$SWITCH" -u PRIVATE_DATA_DIR "$PY" \
    scripts/run_transition_smoothing_eval.py --phase dev --out-dir "$R" > "$R/step2.txt" 2>&1

  # Step 3 - the dev manifest is the pinned one for its rate; R7 selects the primary arm.
  run step3-dev-manifest "$PY" scripts/check_transition_smoothing_gates.py dev-manifest \
    --run-dir "$R" > "$R/step3_manifest.txt" 2>&1
  run step3-dev-selection "$PY" scripts/check_transition_smoothing_gates.py dev \
    --run-dir "$R" > "$R/step3_selection.txt" 2>&1

  log "DEV PHASE DONE: commit $R/dev_record.json as $RECORD, then run the test phase"
  echo "dev phase done; selection in $R/step3_selection.txt, record in $R/dev_record.json"
  echo "next: commit it as $RECORD (nothing else), then run the test phase at that commit"
  exit 0
fi

# Step 2 - the test split, all four arms (every arm decodes under off's routing).
run step2-harness env -u "$SWITCH" -u PRIVATE_DATA_DIR "$PY" \
  scripts/run_transition_smoothing_eval.py --phase test --out-dir "$R" > "$R/step2.txt" 2>&1

# Step 3 - rules (c'), (d'), (e), (f'), (h), (i).
run step3-gates "$PY" scripts/check_transition_smoothing_gates.py harness --run-dir "$R" \
  --record "$RECORD" > "$R/step3_gates.txt" 2>&1

# Step 4 - rules (a) and (f') on the expert pastes: the primary arm, and the default beside it.
for M in auto declared none; do
  run "step4-paste-$M" env "$SWITCH=$PRIMARY" "$PY" scripts/run_expert_paste_eval.py \
    --queries "$B/expert_paste_queries.csv" --stage "$M" \
    --results "$R/paste_$M.csv" > "$R/paste_$M.txt" 2>&1
done
run step4-paste-auto-default env -u "$SWITCH" "$PY" scripts/run_expert_paste_eval.py \
  --queries "$B/expert_paste_queries.csv" --stage auto \
  --results "$R/paste_auto_off.csv" > "$R/paste_auto_off.txt" 2>&1
run step4-paste-check "$PY" scripts/check_transition_smoothing_gates.py paste --run-dir "$R" \
  --baseline-dir "$BASE" > "$R/step4_gates.txt" 2>&1

# Step 5 - none. Rule (b), the Urk. IV / St Andrews gate, is withdrawn from this run: it
# reads private rows, and this run reads only data/processed/examples.csv. The numbering of
# steps 6-8 is kept.

# Step 6 - rule (g'), the competitive sanity check, per query against attempt 2.
CE=("$PY" scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4)
for RUN in v4:T v4:L holdout:T holdout:C le_v1:T le_v1:C; do
  S=${RUN%%:*}
  M=${RUN##*:}
  case $S in
    v4)      F=$B/competitive_ambiguity_eval_queries_v4.csv ;;
    holdout) F=$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv ;;
    le_v1)   F=$B/competitive_ambiguity_eval_queries_le_v1.csv ;;
  esac
  case $M in
    T) ARGS=(--exclude-twins 0.7 --expected-tokens current) ;;
    C) ARGS=(--exclude-twins 0 --expected-tokens current) ;;
    L) ARGS=(--exclude-twins 0 --expected-tokens frozen) ;;
  esac
  run "step6-$S-$M" env "$SWITCH=$PRIMARY" "${CE[@]}" --benchmark "$F" --stage auto \
    "${ARGS[@]}" --results "$R/${S}_${M}_auto.csv" \
    --failures "$R/${S}_${M}_auto_fail.csv" > "$R/${S}_${M}_auto.txt" 2>&1
done
run step6-competitive-check "$PY" scripts/check_transition_smoothing_gates.py competitive \
  --run-dir "$R" --baseline-dir "$BASE" > "$R/step6_gates.txt" 2>&1

# Step 7 - the release check under the primary arm (no pytest here: step 8 runs it once),
# then determinism: its own v4 L, v4 T and paste runs must reproduce steps 6 and 4 exactly.
run step7-verify env "$SWITCH=$PRIMARY" "$PY" scripts/verify_release.py --skip-tests \
  > "$R/verify_release.txt" 2>&1
run step7-verify-check "$PY" scripts/check_transition_smoothing_gates.py verify --run-dir "$R" \
  > "$R/step7_gates.txt" 2>&1

# Step 8 - the full test suite, once, output kept, with the shipped default (the switch unset).
run step8-pytest env -u "$SWITCH" "$PY" -m pytest -q > "$R/pytest.txt" 2>&1

log "ALL STEPS PASSED"
echo "all steps passed; results in $R"
```

`--benchmark` is always explicit: the competitive harness's own default is the contaminated
v1 set.

## 9. What the results note must contain, and what a pass would license

The note is a dated file, `docs/transition-smoothing-results-2026-10-28.md` (or the date of
the run). It must contain:

* both attempt directories, both approved commits (`approved_commit.txt`, equal to
  `commit.txt`), every sha from step 0 and step 1, and the dev record;
* the dev stage in full: the draw rate used and whether the 20% step was taken, the minimum
  counts, every Δ_a, every CI of the walk, the eligible set, b and the primary arm, and every
  elimination with the dev numbers that caused it; and "no candidate survived dev" in those
  words if that was the outcome (in which case there is no test phase);
* each rule (a)–(i) marked PASS, FAIL or REPORTED, with the integer counts it was decided on,
  the per-source counts beside every aggregate, and the step-3, -4, -6 and -7 gate files
  quoted;
* for (d′), the full band tables for every arm, with the N < 30 guard applied in words;
* the full (f′) hypothetical-routing listing;
* the fit-time Ney discounts and `|R|` of every model (`test_smoothing_report.json`), and the
  fallbacks taken;
* the sentence that the competitive sets do not exercise the decoder (rule (g′));
* a verdict in one line.

The note also says that the test split is, besides, **not an independent held-out
validation** in one respect inherited from the earlier harnesses: the run uses the Helsinki
lexicon, as the app does, and the evaluation scripts mark BBAW's lexicon-assisted numbers as
not held-out (`LEXICON_TAINTED_SOURCES`); every aggregate is therefore also written per
source.

**What a passing run would license:** shipping the primary arm as the estimator for
`_transition` (and, if the primary arm is `c2` or `c3`, `_sign_context` and
`_next_sign_context`), described as a smoothing correction measured on the reading-model test
split, with the paired counts and the CI quoted beside the headline number, and routing still
on the `off` estimator.

**What it would not license:** any claim about `_emission` or about the stage router; any
claim about the private self-test that prompted the experiment (a handful of positions, not a
measurement); any re-tuning of the decoder weights; any statement that the tool's *retrieval*
quality improved (the competitive sets cannot see this change); and the shipping of any arm
other than the primary one.

## 10. Choices closed in this consolidation, known limits and the run's cost

**Where the revisions left a choice open, and what was fixed (conservative option each time).**

1. **Dev manifests.** R4 required the dev manifest sha256 to be recorded before any dev
   decode; both candidate rates (10%, 20%) are pinned in §4, so the one permitted step to 20%
   cannot be taken with an unpinned manifest.
2. **Draw units.** "Ramses by its official split's text grouping" does not exist as a grouping
   (every Ramses row has its own hashed text id; the official split is a train/val/test
   label), so the units are `eval_guards.text_group_keys`: AES whole texts, everything else
   single sentences. Moot for the dev set itself, since Ramses and AES rows leave it under the
   lexicon hygiene, but fixed for the draw's random stream. Draw size per source:
   `max(1, int(rate · n + 0.5))` over sorted unit keys, sources in sorted order.
3. **What happens to dev rows hygiene drops (R4).** As R4 says: drawn Ramses and AES rows
   leave dev and stay in training (they are put back into `fit` before the duplicate checks,
   so the dev models see the same Ramses/AES rows as the test models do, apart from the
   drawn-and-dropped duplicates). Drawn TLA and BBAW rows that are exact or near duplicates of
   a `fit` row leave the experiment altogether (the mirror of `select_test_rows`, where a
   dropped test row is in neither test nor train), which is what guarantees that no dev row
   has a twin among the rows its model is fitted on. An earlier draft of this document sent
   the leaking rows out of the experiment as well; the Opus and Astra reviews of that draft
   found that this contradicted R4 and had no hygiene benefit for those rows, and the
   manifest shas of §4 were re-pinned.
4. **Commit between dev and test.** R4 requires the primary arm to be committed before the
   test split is touched; a single uninterrupted runner cannot do that, so the runner has two
   phases and the checker enforces that the committed dev record is the only change between
   them.
5. **Bootstrap.** R7 fixed the resampling unit, the ratio of sums and the percentile rule;
   fixed here besides: groups are `text_group_keys`, sorted by key; the index matrix is one
   `integers(0, G, size=(10000, G), dtype=int32)` draw; the same matrix is used for every
   comparison.
6. **Support R and counts.** R excludes `''` and BOUNDARY (and no arm changes a BOUNDARY
   context, §3); c(r) is the `sign_reading` count;
   a reading outside R scores `k / (N_tot + k(|R|+1))` each (the "bucket" is a pseudo-type;
   sums to 1 over R plus the bucket).
7. **C3's two levels** are specified for every function (§3), including the case of no pooled
   model and of the pooled context being unseen; positions that would read from the pooled
   model (pooled fallback, off by default) score with the pooled model throughout, as the
   decoder already does.
8. **"Runner-up reading" (draft §3.4)** is the best-attested candidate other than the chosen
   one, because the Viterbi lattice does not expose a second-best path.
9. **Which competitive runs gate (R5 (g′)).** The table of R5 lists legacy-pool rows with
   *current* tokens; those are the C runs of the 2026-10-25 re-measurement, not the L (frozen
   token) runs, so held-out and LE-v1 are run as T and C. v4 is run as T and L (the two
   configurations `release_baseline.json` has floors for) and is also compared per query to
   attempt 2. Nothing is compared against the later KRI-fixes runs.
10. **How (a) and (g′) see the primary arm.** Through `EGYPTOLOGY_TRANSITION_SMOOTHING`,
    set for steps 4–7 only; the router ignores it (§2), so the pastes' routing is a real
    end-to-end check of rule (f′). The default-scheme paste run is made beside it for the
    comparison.
11. **`--stage none` in rule (a)** is checked per paste against attempt 2, not just as a
    count.
12. **Gated and reported.** (c′), (e), (f′), (a), (g′) are gated on the primary arm (or on
    every arm, for the routing identity); (d′), (h), (i) and the per-arm numbers of the
    other arms are reported.
13. **Dev positions by source.** The dev set contains TLA and BBAW only (§4); the dev minimum
    counts are on that set.
14. **The 20% step is automatic** (made by the harness from the counts), logged in
    `dev_counts.json`, and checked against the pinned manifest of its rate.
15. **`(e)` is expected to hold with equality** because segmentation does not read the
    transition tables; it is gated anyway.
16. **Rule (b) withdrawn; sentence edges unchanged; guards (2026-10-28 review round).** Rule
    (b), the Urk. IV gate, is dropped (it reads private St Andrews rows, §7), and so is the
    runner's step 5; the runner instead refuses a configured or present private directory.
    The BOUNDARY contexts keep add-k in every arm (§3). The committed dev record's `primary`,
    `best` and `eligible` are re-derived from its own numbers at preflight and must match, and
    the harness and the dev checker refuse to write into an existing output file. The
    own-path V_obs = 1 diagnostic is printed as `count/n (share)`.

**Known limits.** The router gets the gold-spaced paste, so its spaces act as hints (the
earlier harnesses state the same limit); this experiment does not change routing, so it is
unaffected beyond the diagnostic. TLA and BBAW have no text identity: their "groups" are
sentences, so the paired bootstrap treats sentences of one text as independent. The test
split is the one the earlier registrations used, and it has been decoded before by other
experiments, though never with these arms. A positive result is a measurement on this split,
not a validation on independent material.

**Cost.** From the logs of the 2026-10-27 KRI-fixes attempt 5 on this machine (harness
16 min for five arms, competitive runs 6.5 to 11 min each, release check 14.5 min, pytest 10
min), expected: **dev phase ≈ 15–30 min** (about 1 min of model fitting, doubled if the 20%
step is taken; routing and four arms over ~1,400 rows; a few seconds of bootstrap); **test
phase ≈ 2–2.5 h**: step 2 ≈ 25–45 min (four arms and three diagnostic routings per row),
step 4 ≈ 4 min, step 5 none (withdrawn), step 6 ≈ 50 min, step 7 ≈ 15 min, step 8 ≈ 10–11 min. The
heavy steps (6 and 8) are the product-path checks and the full suite; the question the
experiment asks is answered by steps 2–3, in the first hour.

## 11. Revision log

* 2026-10-26 draft, Revision 1 (review round, Opus + Astra), Revision 2 (Astra re-check):
  `docs/plan-transition-smoothing-2026-10-26.md`, **superseded by this document**.
* 2026-10-28, review round (Opus + Astra, both `fix_first`): the three blockers and the minor
  findings are applied, see §10 items 3 and 16, §3 and §4: sentence edges unchanged,
  R4's leaking-rows rule restored with new dev manifest shas, rule (b) withdrawn, preflight
  re-derivation, no-overwrite guards. The approved commit changes with this revision.
* 2026-10-28: this consolidation. Items R1–R9 are all carried in §§1–7; the choices in §10
  are the only places where it goes beyond them.
