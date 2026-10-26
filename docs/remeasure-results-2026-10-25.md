# Post-fix regression run (A), **attempt 1** — results, 2026-10-25/26

Run of part (A) of `docs/remeasure-preregistration-2026-10-25.md` (rev. 2.1 + A6).
Nothing in the code, the benchmarks or the rules was changed during the run. The run was
**not** carried out exactly as written: see the protocol deviation below.

**This note was corrected on 2026-10-26** after an independent review (Astra) of its
mechanism claims. The corrections change explanations, labels and sourcing only — no
measured number and no verdict was changed. Attempt 2 is a separate note.

**Verdict: NOT SHIPPABLE as measured — rule A2.2 (Urk. IV / St Andrews half) FAILED.**
Every other rule that has a pass condition passed (A2.1, A2.3, A2.5, A2.6). Under A2.9 this
attempt is a failed attempt: the failure needs a fix on a new commit, a dated addendum to
the pre-registration, and a full re-run of (A) on the new pinned commit, with this
directory kept as `…-attempt1`. Step 11 (release floors) was **not run** (it requires every
A2 rule to pass).

**Protocol deviation (stated, not excused).** A2.9 says: on any failure, **stop**.
Steps 5–9 were run anyway, after A2.2 had already failed, on the lead's instruction to
record the failure and continue with steps that do not depend on it. That is a deviation
from A2.9, not a reading of it. Everything measured in steps 5–9 is therefore
**diagnostic only**: it is kept to give the next attempt a complete picture, it is not a
(A) result, and it does not reduce what attempt 2 has to re-run.

All result files of this attempt are in
`R = ~/egyptology-runs/remeasure-2026-10-25-attempt1` (outside the repo and iCloud; it was
written as `~/egyptology-runs/remeasure-2026-10-25` during the run and renamed before
attempt 2, as A2.9 requires). Private St Andrews rows were read from
`~/projects/Egyptology-APP/data/private` and never copied; the gate log stays in `$R`.

## Step 0 — pinned state (recorded before step 1)

| Item | Value | File in `$R` |
| --- | --- | --- |
| Commit | `478929ed7ef0d4ce83efc786d262638542ec690b` (branch `audit-fixes-2026-10-25`), tree clean | `commit.txt` |
| Fix branches | `fix1-eval`, `fix1-services`, `fix1-ui-pipeline`, `fix1-ops` all ancestors of HEAD | — |
| Corpus | `data/processed/examples.csv`, **130,472 rows**, sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` | `corpus_sha256.txt` |
| Environment | Python 3.12.13, `~/venvs/egyptology`; `pip freeze` recorded | `env.txt` |
| Flags | `--help` of all seven scripts shows every flag A1 uses | — |
| Routing script | `scripts/run_stage_routing_eval.py` present, with `tests/test_run_stage_routing_eval.py` | — |

## Step 1 — full pytest suite

Run once by the lead on 478929e before this run: **1459 passed, 7 skipped, 0 failed**
(10 min 28 s). Not re-run here (A3 says "once"). The lead also measured paste auto 8/8.

**Sourcing:** this figure and that timing are **reported by the lead; no raw transcript
was retained in `$R`**. Nothing in the attempt-1 directory reproduces them. Attempt 2 runs
the suite itself and keeps the full output in `$R/pytest.txt`.

## Rules, one by one

| Rule | Result | Numbers | Source in `$R` |
| --- | --- | --- | --- |
| A2.1 Paste | **PASS** | auto 8/8, declared 8/8; none 3/8 (reported; was 3/8) | `paste_{auto,declared,none}.txt/.csv` |
| A2.2 Urk. IV gate | **FAIL** | pastes PASS (see below); St Andrews pinned row **not retrieved** | `urkiv_standrews_auto.txt` (+ paste files) |
| A2.3 Stage routing | **PASS** | Earlier → Demotic 0/200, Late → Demotic 0/200 | `routing_summary.txt`, `routing.csv` |
| A2.4 Margin not tuned | **RECORDED** (no pass rule) | margin still 1e-9; app vs the **normalised A2.4 replay** differs 1/400 (app coverage), 20/400 (own-row coverage) — comparisons with the replay, not isolated policy effects | `routing_summary.txt`, `routing.csv` |
| A2.5 No unexplained loss | **PASS** | 0 queries lost committed → L on v4, held-out 1, LE-v1; 0 lost L → C; paste changes all traced | `{v4,holdout,le_v1}_{L,C}_auto.csv` |
| A2.6 Twin effect only where twins are | **PASS** | every C → T change is on a query with a twin; inventory unchanged | `twin_compare.txt`, `twin_changes.csv`, `known_twins_now.csv` |
| A2.7 App vs word overlap | **REPORTED** (no verdict) | pooled T-auto 58/70 vs overlap 59/70, BM25 62/70 | `{v4,holdout,le_v1}_T_auto.csv` |
| A2.8 Release floors | **NOT RUN** | A2.2 failed, so step 11 was skipped | — |
| Release check (A1) | **NOT RUN** | part of step 11 | — |

### A2.1 Paste — PASS

`run_expert_paste_eval.py --queries data/benchmarks/expert_paste_queries.csv`, 130,472 rows:
auto **8/8**, declared **8/8**, none **3/8** (PASTE_001–005 read `rmṯ nb` instead of
`r(m)ṯ(.t) nb.t` without a stage, exactly as before the fixes).

Paste changes against the committed `data/benchmarks/expert_paste_eval_results.csv`
(an auto run) — no pass/fail changed; every changed field is traced:

| Paste(s) | Change | Fix and mechanism |
| --- | --- | --- |
| 001–006, 008 | Demotic no longer in the per-stage likelihoods | A3 stage guard: Demotic has no own aligned hieroglyph rows, so it is not scored |
| 001–007 | top confidence lower (e.g. 0.626 → 0.313, 0.642 → 0.425) | A21: confidence is per-candidate absolute, the 0.4–0.5 floor is gone |
| 008 | stage Demotic → Earlier Egyptian; per-sign log-likelihood of the **chosen** stage −7.962 → −10.541 | A3 (Demotic skipped) + A53 (an unreadable group now pays a penalty instead of a free emission); both remaining stages read nothing, equal coverage 0, Earlier wins on ℓ by 0.152 > 1e-9 — the A2.4 rule |
| 007 (`ẖnm`, NFD) | top suggestion `ḫnm =tw` → `ẖnm-ms` | A54: a Unicode query is matched with strict per-token Unicode, so the exact `ẖ` reading outranks the loose `ḫ` one |

PASTE_008's full likelihood dicts, so the two numbers are not confused: committed
`Earlier Egyptian=-8.143; Late Egyptian=-8.295; Demotic=-7.962` (chosen: **Demotic**,
−7.962; −8.143 is the **Earlier**-model score, not the chosen one); this run
`Earlier Egyptian=-10.541; Late Egyptian=-10.693` (chosen: **Earlier**, −10.541).

Mechanisms are read off the result rows and the fix descriptions; they were not
instrumented one fix at a time.

### A2.2 Urk. IV / St Andrews gate — FAIL

`check_standrews_urkiv_gate.py --private-dir ~/projects/Egyptology-APP/data/private --stage auto`
(exit 1, 71 s):

* Private rows loaded: **7,659** from the resolved directory (corpus 138,131 rows), so the
  St Andrews half **was run** (not "not run").
* PASTE_001–004 pass in auto (`paste_auto.txt`) and declared (`paste_declared.txt`) on the
  public corpus, and all **8/8** pastes still pass with the private rows loaded.
* The pinned St Andrews row (`S_urkIV-001_urkIV-001Tr_0003`) exists once with the expected
  reading, but the hieroglyph paste PASTE_001, routed to Earlier Egyptian, retrieves a pool
  of 27,917 rows containing **0 St Andrews rows**: the row is "not retrieved".
  Script verdict: `GATE: FAIL (S_urkIV-001_urkIV-001Tr_0003 not retrieved)`.

What was found about the cause (read-only, nothing changed): all 7,659 private rows have
an empty `hieroglyphs` column (St Andrews uses Hannig conventions with no derivable sign
alignment), and `retrieve_top_k` keeps, for a hieroglyph query, only rows with sign
evidence (`glyph_overlap_score`, `glyph_idf_overlap_score` or `glyph_exact_bonus` > 0,
`app/services/retrieval.py:165–179`). That filter dates from f75b807 (2026-08-29), and the
gate's retrieval call is the same as on `main`; what is new is that the script now pins
one row and exits non-zero (A5 change 1, final eval, `aa4bbad`). So this is the gate
measuring something the hieroglyph-paste path has never been able to do, rather than a
regression from tonight's fixes.

**Resolved on 2026-10-26** (added in this correction, after an independent review). The
criterion is unreachable by construction, and the historical record confirms the
hieroglyph paste never retrieved a St Andrews row: `docs/sign-function-2026-09-06.md`
(~486) records the same gate as green with "PASTE_001 retrieval pool 27,917, **0 St
Andrews rows in the pool**", and `docs/format-hints-2026-09-06.md` (~421) shows a green
gate that is 8/8 pastes only. "rank 1 among St Andrews rows" entered the pre-registration
at `a39efe9`, was kept at `f4ee069` and became a non-zero exit at `aa4bbad`. The
pre-registration addendum **A7 (2026-10-26)** amends A2.2 accordingly: the rank is
reported, not gated; the pinned row's presence and reading still gate. **This attempt
stays FAILED under A2.2 as written**; A7 applies to attempt 2 onward.

### A2.3 Stage routing — PASS

`run_stage_routing_eval.py --seed 20261025 --per-stage 200` (exit 0, 108 s). Eligible
after dedup: Earlier 9,885, Late 31,310; pool 130,045 rows (427 held out). The script
draws from each stage's own eligible pool (Earlier first, then Late, one generator) and
prints that reading of A2.3.

| True \ chosen | Earlier | Late | Demotic | None |
| --- | --- | --- | --- | --- |
| Earlier (200) | 178 | 21 | **0** | 1 |
| Late (200) | 13 | 187 | **0** | 0 |

Abstentions 1/400. Reading accuracy on 2,620 aligned tokens: chosen stage's model 0.8790,
true stage's model 0.8821. A3's 47/200 and 24/200 came from another sample and pool and
are an unpaired reference only.

### A2.4 and the A6 differences — recorded, not fixed

The margin is still 1e-9 (`app/services/stage.py:582`); nothing was tuned.

**What the two figures below compare.** The script's "A2.4 recomputation" is a **replay
on the normalised sign string**: it calls `choose_stage_by_likelihood(normalize_hieroglyphs(
query), …)` directly, while the app is called with the raw `hieroglyphs` value through
`resolve_auto_stage` (`scripts/run_stage_routing_eval.py:195–213`). So **1/400** and
**20/400** are differences between the app and that normalised replay. They are *not*
isolated measurements of the decision policy: a difference can come from the input the
two calls are given, from the coverage definition, or from the policy, and only the
20/400 figure is attributable to a definition (A6.2) with any confidence.

* **App vs the replay with the app's own coverage: 1/400 differ** — one paste, TLA row
  `TLA_EARLIER_3918` / `S3918`. **CONFIRMED mechanism, and it is not the decision policy.**
  That row's raw `hieroglyphs` value is `<g>D94</g><g>R3W</g>`: Gardiner-code markup with
  no character in the Unicode Egyptian Hieroglyphs block, so `contains_hieroglyphs(raw)` is
  **false** and `resolve_auto_stage` (`app/services/retrieval.py:220`) takes its
  **text-query branch** — a pooled first-pass retrieval followed by `infer_stage` — instead
  of the hieroglyph router. That branch returns no stage here and, by design, an **empty**
  likelihood dict ("empty for a text query", same docstring), which is why this row's
  `score_*` columns in `routing.csv` are blank: the CSV writes the *app's* scores, not the
  replay's. The replay, given the normalised string, scored Earlier and Late (coverage 0
  each) and resolved to Earlier. (Earlier was not wrong about the row, which is Earlier
  Egyptian; the app simply abstained.) Not instrumented further.
* **A6.1 (no abstention at zero coverage with one eligible stage):** confirmed in the code
  (a single ranked candidate is returned whatever its coverage). Measured incidence in
  this sample: **0/400** — 399 pastes had two scored stages (Earlier, Late), 1 had none;
  no paste had exactly one.
* **A6.2 (coverage counts unlabelled AES rows):** app coverage differs from the
  own-aligned-row coverage in **215/400** pastes, and the app's choice differs from A2.4
  as written (own-row coverage) in **20/400**: 10 chosen Earlier where own-row coverage
  gives Late, 9 chosen Late where it gives Earlier, plus the 1 abstention above. Neither
  difference sends anything to Demotic.

### A2.5 No unexplained loss (legacy pool) — PASS

Committed history = `data/benchmarks/ceval_{v4_v4,holdout_v4,le_v1}_app_auto_results.csv`
(v4 0.90 / MRR 0.7917, held-out 1 0.75 / 0.6667, LE-v1 0.8667 / 0.8167).

| Set | Committed | L-auto (frozen tokens) | C-auto (current tokens) | Lost committed → L | Lost L → C |
| --- | --- | --- | --- | --- | --- |
| v4 (20) | 0.90 / 0.7917 | 0.90 / 0.8000 | 0.90 / 0.8000 | none | none |
| held-out 1 (20) | 0.75 / 0.6667 | 0.75 / 0.6750 | 0.75 / 0.6667 | none | none |
| LE-v1 (30) | 0.8667 / 0.8167 | 0.8667 / 0.8000 | 0.8667 / 0.8000 | none | none |

(top-3 useful / MRR.) The misses are the same queries as before: v4 COMP_007, COMP_014;
held-out HOLD_001, 002, 005, 014, 026; LE-v1 LE_008, 014, 034, 044. No gains either.

Rank changes inside the top 3 (not losses, listed so the MRR moves are explained):

| Query | Rank | Fix and mechanism |
| --- | --- | --- |
| COMP_022 | 3 → 2 (committed → L) | **A21 is ruled out** (see below). Mechanism **plausible, not isolated**: the two candidates' *relative* confidences changed because their retrieval signals changed — A51 (per-stage IDF on the Late Egyptian subset's own row count) and/or A17 and the other `normalizer.py` search-key folds, which change corpus document frequencies |
| HOLD_008 | 3 → 2 (committed → L) | A17: the row `{wn} ={ꞽ} 〈wn〉 Ppy pn …` no longer matches on its superfluous `{…}` text and drops out of the top 3 |
| HOLD_008 | 2 → 3 (L → C) | A17 + A55 token mode: the current expected tokens drop the `{=ꞽ}` token, so candidate 2's overlap falls 0.263 → 0.211, below the threshold; the third row is still useful |
| LE_005 | 1 → 2 (committed → L) | the two top rows were tied at confidence 0.561; the row sharing the rare word `qbḥ` now ranks first. Most likely A51 (Late Egyptian IDF on the stage subset's own row count gives rare content words their weight back); the useful row is second. Mechanism inferred, not isolated |

**Why A21 cannot be the COMP_022 mechanism.** The per-candidate absolute-evidence factor
is applied at `app/services/suggestions.py:1063–1067`, *after* `rows.sort(...)` at
:1055–1061 and after the `rows[:top_n]` slice. The sort key is the **relative**
confidence; the code comment at :1047 states this. A21 therefore rescales the displayed
numbers (0.555 → 0.273 / 0.302) and can never reorder candidates. The sort key, including
its alphabetical tie-break, is unchanged from the merge-base `27c1a7b`. Since the
displayed order changed, the two *relative* confidences must themselves have changed —
and for this ASCII query they are read off retrieval (`translit_overlap` from
`idf_overlap_score`, plus `relative_score`/`mean_score` from `final_score`), not off the
suggestion layer's string handling. A54 is inert here (no Egyptological letters in the
query) and A17 does not change either candidate's comparison key (neither contains
`{…}`). Which retrieval-side fix moved the numbers — A51's stage-subset IDF, the folds'
effect on document frequencies, or both — was **not isolated**: separating them needs an
instrumented re-run, which this attempt did not do.

**COMP_011 (v4): stage_used Late Egyptian → pooled — corrected mechanism.** The earlier
attribution to A3/A53 was wrong. COMP_011's query (`akh pl sn ti pl iri sn mrr pl sn ta
djr hka`) is **ASCII transliteration**, so it never reaches the hieroglyph coverage-first
router: the harness's `--stage auto` branch does a pooled first-pass `retrieve_top_k` and
then `infer_stage` (`scripts/run_competitive_ambiguity_eval.py:881–891`); it never calls
`resolve_auto_stage` or `choose_stage_by_likelihood` (0 occurrences in that file), and the
app's own `resolve_auto_stage` takes the likelihood router only `if contains_hieroglyphs(
query)` (`app/services/retrieval.py:220`). `infer_stage` itself is **byte-identical**
between `27c1a7b` and HEAD. "pooled" here is `stage_used == ""`, i.e. `infer_stage`
returned `None`.
*Mechanism: path CONFIRMED, trigger PLAUSIBLE.* Confirmed: the pooled first pass returned
a different top-10 whose labelled-stage mix no longer clears `infer_stage`'s share/lift
guards. Plausible, not isolated: the search-key folds moved that neighbourhood — the new
rank-2 suggestion is `hp =sn pw n mrr{.t} =sn` (BBAW B016189), whose evidence summary
names the shared token `mrr{.t}`, a match only possible once A17 deletes `{…}` from the
search key; it is the only `mrr{` row in the corpus and was absent from the committed
top 3. Which fold flipped the guard was not instrumented.

Other changes: shown suggestion lists changed committed → L in v4 9 queries, held-out 5,
LE-v1 2 (the rank changes above included); the others keep their useful rank.

### Mechanism status of every change above

**UNEXPLAINED top-3 losses: zero** — no query that the committed run answered within the
top 3 fails to do so in L or C. That is the A2.5 pass condition and it is met. Separately,
the *explanations* for the changes that did happen are of three different qualities:

| Status | Changes |
| --- | --- |
| **CONFIRMED** (traced in code or data) | PASTE_001–006, 008 Demotic dropped from the likelihoods (A3 stage guard); PASTE_001–007 confidence rescaled (A21, `suggestions.py:1063–1067`); PASTE_007 `ḫnm =tw` → `ẖnm-ms` (A54 strict per-token Unicode on an NFD query); HOLD_008 3 → 2 committed → L (A17: the `{…}` row no longer matches on its superfluous text); HOLD_008 2 → 3 L → C (A55 token mode drops `{=ꞽ}`, overlap 0.263 → 0.211); COMP_011 is routed by `infer_stage`, not the coverage router |
| **PLAUSIBLE** (consistent, not isolated) | COMP_022 3 → 2 (retrieval signals changed: A51 and/or the search-key folds); LE_005 1 → 2 (A51, Late Egyptian IDF restoring weight to the rare word `qbḥ`); COMP_011's specific trigger (A17's `{…}` deletion changing the first pass); PASTE_008's stage flip attributing the ℓ change to A53's unreadable-group penalty |
| **UNRESOLVED** | Which of A51 and the folds moved COMP_022's retrieval numbers; which fold flipped COMP_011's `infer_stage` guard. Both need an instrumented re-run and neither moves a query out of the top 3 |

No change in any of the three rows is an unexplained **loss**; the UNRESOLVED row is about
attribution between named fixes, not about unaccounted behaviour.

### A2.6 Twin effect only where twins are — PASS

`list_benchmark_twins.py` wrote 817 twin rows, **byte-identical** to the committed
`data/benchmarks/known_twins_2026-10-12.csv` (`known_twins_diff.txt` empty), so the
committed inventory decides. `compare_twin_scores.py` (exit 0) accepted all three pairs and
lists C → T changes only on queries with twins:

**This list covers useful-rank and suggestion changes only** — it is what
`compare_twin_scores.py` writes to `twin_changes.csv`:

* v4: COMP_001 (useful rank 1 → miss), COMP_004, COMP_017, COMP_018 (suggestions only);
  twin queries are COMP_001, 002, 004, 010, 017, 018, 022.
* held-out 1: HOLD_022, HOLD_025 (suggestions only); twins HOLD_017, 022, 023, 025.
* LE-v1: LE_020, 023, 028, 040 (suggestions only); twins LE_001, 020, 023, 028, 040.

Other C → T outcome changes, found by diffing the C-auto and T-auto result CSVs column by
column (they are not in `twin_changes.csv`, which does not track these fields). **A2.6
still passes: every one of them is on a query with `twins_removed > 0`.**

| Query | Field | C-auto → T-auto | Twins removed |
| --- | --- | --- | --- |
| COMP_018 | `exact_rank`, `top3_exact_hit` | 2 → not found, True → False | 2 |
| COMP_017 | `overlap_baseline_useful_rank`, `bm25_baseline_useful_rank` | 1 → 2 (both) | 1 |
| COMP_010 | `overlap_baseline_suggestions` | baseline list changed; app rank 2 unchanged | 1 |
| HOLD_017 | `stage_used`, `confidence_scores` | pooled (`""`) → Earlier Egyptian; 0.376/0.288/0.296 → 0.376/0.289/0.298 | 8 |
| LE_020, LE_023 | baseline useful ranks / `overlap_baseline_suggestions` | see `twin_compare.txt` | 2 each |

HOLD_017 is the only one where the **app's** stage choice moves: removing 8 twins changes
the pooled first pass, so `infer_stage` now clears its guards for Earlier Egyptian where
it previously abstained. Its useful rank is 1 before and after.

Changes on clean queries (`twins_removed == 0`): **0**. The `twin_exclusion` column
differs on every row — that is the control setting itself (0 vs 0.7), not an outcome.

Twin-controlled numbers (T-auto / T-declared / T-none, top-3 useful, MRR): v4 0.85 / 0.75,
0.85 / 0.7417, 0.85 / 0.7417; held-out 1 0.75 / 0.6667 in all three modes; LE-v1 0.8667 /
0.80, 0.8667 / 0.7833, 0.8667 / 0.80.

### A2.7 App vs word overlap — reported, no verdict

Pooled T-auto over the 70 queries (v4 20 + held-out 1 20 + LE-v1 30), top-3 useful:

| | Top-3 useful | Margin (app − baseline) | App only | Baseline only | Both | Neither |
| --- | --- | --- | --- | --- | --- | --- |
| App | 58/70 (0.8286) | — | — | — | — | — |
| Word overlap (primary) | 59/70 (0.8429) | **−0.0143** | 6 | 7 | 52 | 5 |
| BM25 (secondary) | 62/70 (0.8857) | −0.0571 | 3 | 7 | 55 | 5 |

Per set (T-auto): v4 app 0.85 vs overlap 0.95, BM25 0.90; held-out 1 0.75 vs 0.70, 0.85;
LE-v1 0.8667 vs 0.8667, 0.90.

Caveats, as A2.7 requires:

* These are development sets the ranking was tuned on.
* The queries are generated from corpus rows, not hieroglyph reading by an Egyptologist.
* Twin control at 0.7 does not remove all cross-edition copies.
* **BM25 asymmetry:** the harness builds BM25 IDF and average length on the full corpus,
  including the target and twins removed from the pool, while the app ranks the reduced
  pool. BM25 margins are approximate and secondary.

On these sets the app does not beat word overlap. **No number in this note is an
independent accuracy figure** and none may be quoted to experts (A4); that needs (B).

### A2.8 Release floors and the release check — NOT RUN

Step 11 runs only if every A2 rule passed. A2.2 failed, so `release_baseline.json` was not
changed and `verify_release.py --skip-tests` was not run (with the current baseline, which
has no `twin_controlled` block, it would report NOT READY without `--allow-legacy-gate`
anyway). For the next attempt, the floors rule 8 would give from this run's v4 T-auto are
0.85 − 0.05 = 0.80 and 0.75 − 0.05 = 0.70; they are **not** committed.

## Run log

| Step | Command | Exit | Time | Source of the time |
| --- | --- | --- | --- | --- |
| 0 | record sha / hash / env, row count, `--help` checks | — | 23:59 (start) | file mtimes in `$R` |
| 1 | pytest (lead, before the run) | 0 | 10 min 28 s | **reported by the lead; no raw transcript retained** |
| 2 | `list_benchmark_twins.py` | 0 | 11 s | **reported by the lead; no raw transcript retained** |
| 3 | paste auto / declared / none | 0 / 0 / 1 (3/8 expected) | 56 s / 34 s / 21 s | **reported by the lead; no raw transcript retained** (the `paste_*.txt` files carry no duration) |
| 4 | Urk. IV St Andrews gate | **1 (FAIL)** | **71.1 s** (script-internal) | `urkiv_standrews_auto.txt`, last line `done in 71.1s` |
| 5–7 | 15 competitive runs (T×3, C, L per set) | all 0 | 00:04 → 02:03 | `competitive_progress.log` timestamps |
| 8 | `compare_twin_scores.py` | 0 | seconds (not timed) | — |
| 9 | stage routing | 0 | **107.7 s** script-internal / **110 s** wall | `routing_summary.txt` (`done in 107.7s`) and `routing_exit.txt` (`routing exit 0 secs 110`) |
| 10 | this note | — | — | — |
| 11 | floors + `verify_release.py` | not run | — | — |

The earlier "74 s" for step 4 had no source and is withdrawn: the only recorded figure is
the script's own 71.1 s, and no wall-clock measurement of that step was kept.

Wall time of steps 0–9: 23:59 → 02:06 (about 2 h 7 min, from `$R` file mtimes), plus the
lead's reported 10.5-minute pytest. One heavy process at a time throughout.

## Attempts

| Attempt | Directory | Outcome |
| --- | --- | --- |
| 1 | `~/egyptology-runs/remeasure-2026-10-25-attempt1` (written as `…-2026-10-25`, renamed before attempt 2) | **A2.2 FAIL** (St Andrews row not retrieved); all other pass rules PASS. Stays FAILED: the A7 amendment (2026-10-26) applies to attempt 2 onward and does not relabel this attempt |
