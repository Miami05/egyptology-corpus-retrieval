# App fixes from the KRI self-test (2026-10-26)

The KRI self-test of 2026-10-26 was exploratory, non-expert and **not** the pre-registered KRI
test of `docs/plan-data-cleanup-2026-10-26.md` §4d/§4e. Nothing in it is a measurement. What it
did produce is three concrete defects, reproducible without the material, and this document
records what was changed, what was only written down, and what still has to be measured under
pre-registration before any of it is called an improvement.

The material itself is copyrighted and private. **No line, sign string or derived text from it
appears here, in any test, or in any committed file.** Every test added for these fixes uses
synthetic fixtures or public-corpus signs; the per-line figures below are counts only.

Worktree `.claude/worktrees/kri-fixes-2026-10-26`, branch `kri-fixes-2026-10-26`, off `main` at
`3465478`. Interpreter `/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus
`data/processed/examples.csv`, 130,472 rows, sha256 `44543932…` — the same corpus the self-test
ran on, so the before/after counts are comparable.

---

## 1. Stage-emptied evidence shown as a confident reading

### The problem

A stage's reading model is trained on `compatible_frame(df, stage)`, which is right — a
cross-stage spelling must not be offered as this stage's reading. But the filter can *empty* a
group's evidence while leaving the group formally attested. One single sign in the self-test is
attested 37× in the public corpus, 34× of them under one reading whose every row is Late
Egyptian. Restricted to Earlier Egyptian the model keeps three readings attested once each, ties
them at 0.3333, and the tie-break presents an editorial fragment (a bracketed foreign-name
reading) as top-1 with `was_seen=True`, `attested_count=3`. Nothing in the output said the
evidence had been thrown away rather than weighed, and nothing said the three candidates were
tied.

Auto chose Earlier Egyptian for those lines on log-likelihood margins of 0.21–0.85. **The stage
router's decision rule is not touched here** — changing it needs its own pre-registration (the
open A3 margin TODO in `app/services/stage.py`). This fix is only about the evidence a group is
read from once a stage has been chosen.

### What changed

**(a) Pooled evidence for a group the stage filter emptied.**
`ReadingModel.uses_pooled_evidence(group)` (`app/services/reading_model.py`) fires when all
three hold:

| constant | value | why |
|---|---|---|
| `POOLED_FALLBACK_MAX_STAGE_COUNT` | 3 | at most a handful of stage attestations, so every surviving reading is a near-singleton and cannot rank the others |
| `POOLED_FALLBACK_MIN_POOLED_COUNT` | 20 | the pooled evidence must not itself be thin |
| `POOLED_FALLBACK_MIN_RATIO` | 10.0 | an order of magnitude: a group merely *rarer* in this stage is left alone |

The traced case clears all three with little room to spare (3 / 37 / 12.3×), which is intended:
these are deliberately conservative constants chosen so the rule fires where the filter has
plainly removed the evidence, not where it has thinned it. **They are not measured.** See §5.

Two scoping decisions, both conservative:

* A group the stage attests **zero** times is deliberately *not* covered. It already has a
  documented chain of its own — external lexicon, then composed, then the glyph-similarity
  borrow — and every step of it is flagged as not seen here. Widening the rule to those groups
  would change what `was_seen` means.
* `build_stage_resources` attaches the pooled model it already builds for the segmenter
  (`ReadingModel.attach_pooled`), so no extra fit is done, and attaching a model to itself (the
  `target=None` case) is a no-op.

When the rule fires, the position is scored by the **pooled model throughout** — emission *and*
the three context terms — not by the pooled emission alone. Borrowing only the emission does not
work: the stage's context tables were emptied by the same filter, so they charge every pooled
reading the unseen-reading rate and the stage's own singletons win the position straight back.
`tests/test_reading_model.py` pins this. The pooled counts are a superset of any stage's, so
every term is defined for every reading either model knows.

The prediction is marked: `ReadingPrediction.used_pooled_evidence` and `stage_attested_count`,
and the UI says "all stages: this reading N×; this group M× — the chosen stage attests it only
K×", plus a panel note and a count in the support line.

**The stage router is unaffected by construction**: `choose_stage_by_likelihood` decodes with
`use_pooled_fallback=False`, so its per-stage likelihoods and its decision are bit-for-bit what
they were. `tests/test_stage.py` pins that too.

**(b) A tie on singleton evidence is not a confident reading.**
`ReadingPrediction.tied_singleton_readings` lists the readings that tie for best-attested when
that attestation is a single occurrence each; `is_singleton_tie` is the predicate. `confidence`
divides the share by the number of tied readings, so a three-way singleton tie reports 0.11
instead of 0.33 and no singleton tie can report more than 0.25. The UI shows the tie explicitly
(a `≟` badge, a warning, and the tied readings listed under the sign-by-sign table) rather than
printing one of them as though the corpus had chosen it.

**(b′) `confidence` is now about the reading that was *chosen*.**
It previously reported the best candidate's share whatever the decoder picked — the same
mismatch Astra #5 corrected in the evidence *text* and left in the *number*. Fixing (a) made it
actively misleading: once the pooled counts arrived, a reading attested once in a group attested
37 times was reported at 0.92. It is now the chosen reading's own share (0.0 when the chosen
reading is not among the candidates listed). Nothing in `app/` or `scripts/` read this property
before, so this changes no benchmark.

### What is still wrong, and is not fixed here

On the four self-test positions the rule fires on, **the decode still chooses the editorial
fragment**, now at confidence 0.027 beside a 92%-attested alternative instead of a tied 0.33.
Traced to the end: at the position itself the pooled scoring prefers the common reading by 1.5
nats, and Viterbi gives that back at the *next* position, because the reading-bigram transition
out of a reading seen exactly once has denominator 1 and therefore scores its one observed
successor at probability ≈ 1.0, while a reading with 34 attestations and a wide successor
distribution scores any particular successor far lower. Scoring that transition with the pooled
model does not help — the singleton bigram is a singleton there too.

That is a smoothing defect in `_transition`/`_sign_context`/`_next_sign_context`, not a stage
problem, and correcting it changes the decoder for every query. It needs its own experiment and
pre-registration. What ships here makes the evidence the reader sees correct and the chosen
reading's weakness visible; it does **not** claim to have fixed the ranking.

---

## 2. Notation flips with the stage (documented only, no code change)

The same group came back `dꞽ.n n =k` under Late Egyptian and `ḏi̯.n n =k` under Earlier
Egyptian. Under the strict identity key those are different readings, so the stage choice alone
can flip a hit to a miss in any key-based scoring — on material routed by margins as small as
0.02 log-likelihood units.

**`d` and `ḏ` are not folded, and nothing in the code changed.** Whether these are the same
reading is an Egyptological question, not a scoring convenience: Nederhof's round-2 reply
already rejected the plain-ASCII fold for exactly this kind of distinction (`ꜣ`/`ꜥ`, `ḫ`/`ẖ`
stay distinct; `i`/`j`/`y` may merge — see `docs/expert-round-2-nederhof-2026-09-06.md`). The
existing D′ fold (`app/data/normalizer.py`'s `normalize_notation`) folds the weak-consonant
marker `i̯`→`ꞽ`, `u̯`→`w`, which is a notation difference; `d` vs `ḏ` is a consonant.

Two actions follow, neither of them code:

1. **Ask the experts.** The question for Camilla and Nederhof: on Ramesside monumental material,
   is `dꞽ` vs `ḏi̯` for this group a notational variant of one reading, or two readings? Add it
   to the next outreach round (`docs/outreach-messages.md`).
2. **Endpoint G must report both scores.** The pre-registered endpoint G of
   `docs/plan-data-cleanup-2026-10-26.md` must report the **folded** score beside the **strict**
   one, for every run, and say which it is quoting. A single number there is not interpretable
   while this is open, because the strict/folded gap is produced by the stage router rather than
   by the reading model.

---

## 3. Cartouche split, with the name silently lost

### The problem

The segmenter cut a royal cartouche into four groups. The two pieces carrying a cartouche sign
came back unseen with no reading at all — no corpus group, no lexicon entry, no borrow — and the
king's name left the line reading with nothing marking the loss. The cartouche signs were being
treated as ordinary glyphs to be grouped, not as brackets.

### What the corpus says

Checked before choosing a rule, on `data/processed/examples.csv` (130,472 rows):

| | count |
|---|---|
| rows containing V011A (U+13379) or V011B (U+1337A) | 1,305 |
| sign groups containing a **matched** V011A…V011B pair | 1,841 |
| sign groups containing only one half of a pair | 13 |
| rows that split a cartouche across two groups | 5 |
| groups with the two signs out of order | 0 |

So "a cartouche is one sign group" is what the data supports, at 99.3% of the groups that
contain either sign. The rule follows the data rather than an a-priori typographic intuition.

### What changed

`app/data/normalizer.py` gains `cartouche_spans(stream)`, which returns the outermost matched
`(start, end)` spans in a glyph stream. An unmatched half contributes nothing — the same rule
`quadrat_hints` already applies to the Unicode enclosure *controls* (U+1343C/U+1343D), which
continue to work exactly as before through the measured `quadrat_crossed` penalty. This addition
is about the cartouche written as **signs**, which survive normalisation and reach the segmenter.

`Segmenter.segment` turns those spans into a **hard constraint**: no group may start at a
boundary strictly inside a cartouche, which — the groups being contiguous — also means none may
end there. It is a constraint rather than a weight because the pieces of a royal name are
usually common attested groups while the name as a whole is not, so no penalty short of a veto
survives the arithmetic. Two guards keep the lattice feasible:

* the whole cartouche span is always offered as a candidate start, even when it is longer than
  `MAX_GROUP_GLYPHS`;
* a span that is exactly a cartouche is exempt from the `unattested_may_cross_hints` veto, since
  a paste routinely spaces a royal name by quadrat and the name is routinely unattested. It
  still pays `hint_crossed` per crossed space and κ per glyph.

`tests/test_segmentation.py` pins both the new behaviour and, with `cartouche_spans`
monkeypatched to report nothing, that it is this constraint and nothing else in the objective
that keeps the name together.

**An unseen group is never dropped silently.** `ReadingPrediction.has_reading` and
`.display_reading` put the placeholder (`NO_READING_MARK`, `∅`) in the prediction itself rather
than leaving each renderer to decide. `app/ui/whyptology_app.py`'s `assembled_reading` now takes
it from there, so a group nothing could read keeps its place in the line and the reader sees
where knowledge ends. `scripts/run_expert_paste_eval.py` deliberately keeps its own join: its
reading string is compared against the benchmark's `expected_reading` column, and changing it
would change what that gate measures.

---

## 4. Effect, measured where it is cheap to measure

**Expert paste gate (`scripts/run_expert_paste_eval.py --stage auto`): 8/8, unchanged.** The
results file is **byte-identical** with the two behaviour changes switched off and on (compared
by running the eval with `cartouche_spans` returning `[]` and `uses_pooled_evidence` returning
`False`). Neither rule can fire on those eight pastes: none contains a cartouche sign, and none
of their groups meets the pooled-fallback conditions.

*Noted in passing, unrelated to this branch:* the committed
`data/benchmarks/expert_paste_eval_results.csv` is stale relative to `main` — re-running the
gate on unmodified `main` already changes its `stage_likelihoods`, `top_suggestion` and
`top_confidence` columns. Not regenerated here, and not committed.

**Self-test lines, re-run locally on the same corpus, counts only** (the material stays private;
the before run reproduces the self-test report's table exactly):

| | before | after |
|---|---|---|
| sign groups over the 10 lines | 129 | 120 |
| groups unseen with no reading | 8 | 3 |
| groups with a borrowed (flagged) reading | 5 | 7 |
| groups whose readings tie on singleton evidence | 4 | 0 |
| groups read from pooled evidence, marked | 0 | 4 |
| groups containing a cartouche sign | 9 | 6 |
| …of those, with no reading at all | 6 | 1 |
| lines whose segmentation changed | — | 3 |
| lines whose reading changed | — | 3 |
| groups on the 7 unchanged lines whose chosen reading moved | — | 0 |
| stage chosen per line | — | identical on all 10 |

All three changed lines are the nomen lines whose cartouche was being split; each loses three
groups (four pieces become one) and gains a flagged borrowed reading for the name. The one
cartouche still unread is on the line the self-test graded "very low" confidence, hatched
throughout — it is now a single group reported as `∅` rather than two pieces that vanished.

**Tests run** (specific files, one process at a time, no full suite):

* `tests/test_reading_model.py tests/test_segmentation.py tests/test_stage.py
  tests/test_normalizer.py tests/test_batch2_evidence_ui.py tests/test_audit_ui.py
  tests/test_whyptology_app_stage.py tests/test_frontend_smoke.py` — 302 passed
* `tests/test_pipeline_fuzz.py tests/test_audit_pipeline.py tests/test_audit_services.py
  tests/test_fix_round1_services.py tests/test_fix_round2_services.py
  tests/test_fix_round3_services.py tests/test_final_audit_search_ranking.py
  tests/test_sign_functions.py` — 217 passed, 3 skipped
* `tests/test_boundary_model.py tests/test_quadrat_hints.py
  tests/test_quadrat_conditional_veto.py tests/test_pasted_space_restriction.py
  tests/test_composition.py tests/test_lexicon.py tests/test_notation_fold.py` — 85 passed,
  1 skipped

---

## 5. What needs a pre-registered measurement before release

None of this is released on the evidence above. The expert paste gate is a hard constraint, not
a measurement, and ten non-expert lines are not one either.

1. **The three pooled-fallback constants (3 / 20 / 10×).** They are reasoned, not fitted. Sweep
   them on the held-out reading evaluation (`scripts/run_reading_model_eval.py`), per stage,
   with the criterion and the candidate grid pre-registered, twins removed. Report accuracy on
   the positions the rule fires on *and* on everything else, since the rule must not move
   positions it was not meant to touch.
2. **The segmentation constraint.** Re-run `scripts/run_segmentation_eval.py` on the held-out
   split, unspaced and scrambled, and `scripts/run_format_hint_eval_standrews.py`. The corpus's
   13 half-pair groups and 5 split-cartouche rows are the only places where the constraint can
   hurt, so the expected result is "no change outside them"; that has to be shown, not assumed.
   The St Andrews run needs `PRIVATE_DATA_DIR` and so belongs to a keyed session.
3. **The whole v4 / held-out / LE-v1 set**, under `docs/remeasure-preregistration-2026-10-25.md`
   rules, before the release floors are quoted again. Expected to be unchanged — no benchmark
   query carries a cartouche sign or meets the pooled-fallback conditions — but "expected
   unchanged" is a prediction to be checked, not a result.
4. **Endpoint G reported folded *and* strict** (§2), with the convention stated in the run.
5. **The transition smoothing** described at the end of §1. A once-seen reading-bigram scoring
   its single successor at ≈ 1.0 is what keeps the wrong reading on top even after the evidence
   is corrected. This is a decoder change affecting every query; it needs its own experiment,
   its own pre-registration, and the expert paste gate as a hard constraint.
6. **The stage router itself** (`choose_stage_by_likelihood`): margins of 0.02–0.09 on this
   material are not a decision, and the A3 abstention margin is still unset. Untouched here on
   purpose.
