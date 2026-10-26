# Post-fix regression run (A), **attempt 2** — results, 2026-10-26

Run of part (A) of `docs/remeasure-preregistration-2026-10-25.md` (rev. 2.1 + A6 + the
dated addendum **A7**, 2026-10-26). Attempt 1 failed rule A2.2 on a criterion that was
unreachable by construction; A7 corrected the specification and this is the full re-run
A2.9 requires. Nothing in the code, the benchmarks or the rules was changed during the
run.

**Verdict: every A2 rule with a pass condition PASSED** (A2.1, A2.2′, A2.3, A2.5, A2.6).
A2.4 and A2.7 are recorded/reported and have no pass rule. Step 11 (release floors and
the release check) therefore ran.

**No number in this note is an independent accuracy figure and none may be quoted to
experts** (pre-registration A4). These are development sets the ranking was tuned on.
That needs part (B).

## How this attempt relates to attempt 1

Attempt 1 (`docs/remeasure-results-2026-10-25.md`, directory
`~/egyptology-runs/remeasure-2026-10-25-attempt1`) stays **FAILED**. A7 applies to attempt
2 onward and does not relabel it. The amended rule is A2.2′: 8/8 pastes in **both** auto
and declared with the private rows loaded, plus the pinned row present exactly once with
its expected folded reading; the St Andrews **rank is reported, not gated**, because no St
Andrews row can enter a hieroglyph paste's retrieval pool (every St Andrews row has an
empty `hieroglyphs` column, and `retrieve_top_k` drops rows with no shared sign evidence —
`app/services/retrieval.py:165–179`).

**Every per-query result file in this attempt is byte-identical to attempt 1's** — all 15
competitive CSVs, the three paste CSVs, `routing.csv`, `twin_metrics.csv`,
`twin_changes.csv` and `known_twins_now.csv`. Attempt 2 adds what attempt 1 lacked: the
pytest transcript, the gate in declared mode, a per-step run log, and step 11.

## Operational event: interruption and resume (disclosed, not a protocol deviation)

The session hosting the run shut down at about **08:11** and killed the process at step
`le_v1_T_auto` (START logged 08:11:18, no END, 0-byte `.txt`, no CSV written). Every
earlier step had completed with its expected exit code (0, except paste `--stage none`,
whose exit 1 is by design and non-gating).

Before resuming: the worktree was re-checked (HEAD still `3e29304`, tree clean) and the
corpus sha256 re-verified against `corpus_sha256.txt`. The partial `le_v1_T_auto.txt` was
deleted, the interruption and the resume were logged in `run_log.txt`, and the run
continued from `le_v1_T_auto` at **08:26:42**. Finished steps were not re-run.

This is **not** a deviation under A2.9: A2.9 governs what happens when a *rule* fails, and
no rule failed. Same commit, same inputs, same commands; the killed step produced no
output that was kept. It is recorded here because a run that stops and restarts should say
so.

## Step 0 — pinned state

The commit and corpus sha256 were checked before step 1 (contemporaneous). The record
count was verified later: the original step-0 file recorded `wc -l` physical lines, and the
130,472-record figure was added afterwards (see below). The corpus itself has the correct
count and hash; only the timing of the record-count check differs from A0.

| Item | Value | File in `$R` |
| --- | --- | --- |
| Commit | `3e29304b3d806dc4029795206c49af816fe2ab31` (branch `audit-fixes-2026-10-25`), tree clean | `commit.txt` |
| Fix branches | `fix1-eval`, `fix1-services`, `fix1-ui-pipeline`, `fix1-ops` all ancestors of HEAD | `step0_preconditions.txt` |
| Corpus | `data/processed/examples.csv`, **130,472 rows**, sha256 `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2` | `corpus_sha256.txt` |
| Environment | Python 3.12.13, `~/venvs/egyptology`; `pip freeze` recorded | `env.txt` |
| Flags | `--help` of all seven scripts captured in full | `step0_preconditions.txt` |

The 130,472 figure is the CSV **record** count (verified with `pandas.read_csv` and with
`load_examples_csv`). `wc -l` reports 131,092 physical lines (131,091 data lines, excluding the header) because some fields contain
newlines; a note to that effect was appended to `step0_preconditions.txt`. The gate's
`corpus 138,131 rows` = 130,472 public + 7,659 private, which agrees.

All result files are in `R = ~/egyptology-runs/remeasure-2026-10-25` (outside the repo and
iCloud). Private St Andrews rows were read from `~/projects/Egyptology-APP/data/private`
and never copied; the gate logs stay in `$R`.

## Step 1 — full pytest suite

Run as step 1 of this attempt, **full output kept**: **1466 passed, 7 skipped, 0 failed,
2 warnings**, 543.69 s reported by pytest (553 s wall).

| | Value | Source |
| --- | --- | --- |
| Transcript | `$R/pytest.txt` | the run itself |
| Internal duration | 543.69 s | pytest's own summary line |
| Wall duration | 553 s | `run_log.txt` |

1466 = attempt 1's 1459 plus the 7 tests added with the A7 amendment.

## Rules, one by one

| Rule | Result | Numbers | Source in `$R` |
| --- | --- | --- | --- |
| A2.1 Paste | **PASS** | auto 8/8, declared 8/8; none 3/8 (reported) | `paste_{auto,declared,none}.txt/.csv` |
| A2.2′ Urk. IV gate (A7) | **PASS** | `GATE: PASS` in auto and declared; 7,659 private rows, corpus 138,131; pinned row present once with its reading; rank reported as "not retrieved" | `urkiv_standrews_{auto,declared}.txt` |
| A2.3 Stage routing | **PASS** | Earlier → Demotic 0/200, Late → Demotic 0/200 | `routing_summary.txt`, `routing.csv` |
| A2.4 Margin not tuned | **RECORDED** (no pass rule) | margin still 1e-9; app vs the normalised A2.4 replay differs 1/400 (app coverage), 20/400 (own-row coverage) | `routing_summary.txt`, `routing.csv` |
| A2.5 No unexplained loss | **PASS** | 0 queries lost committed → L and 0 lost L → C on all three sets | `{v4,holdout,le_v1}_{L,C}_auto.csv` |
| A2.6 Twin effect only where twins are | **PASS** | every C → T change is on a query with `twins_removed > 0`; inventory byte-identical | `twin_compare.txt`, `twin_changes.csv`, `known_twins_diff.txt` |
| A2.7 App vs word overlap | **REPORTED** (no verdict) | pooled T-auto 58/70 app vs 59/70 overlap, 62/70 BM25 | `{v4,holdout,le_v1}_T_auto.csv` |
| A2.8 Release floors | **RAN** | `twin_controlled` block added: floors 0.80 / 0.70 from measured 0.85 / 0.75 | `data/benchmarks/release_baseline.json` |
| Release check (A1) | see §A2.8 below | `verify_release.py --skip-tests` | `verify_release.txt` |

### A2.1 Paste — PASS

`run_expert_paste_eval.py --queries data/benchmarks/expert_paste_queries.csv`, 130,472
rows: auto **8/8**, declared **8/8**, none **3/8** (PASTE_001–005 read `rmṯ nb` instead of
`r(m)ṯ(.t) nb.t` without a stage, as before the fixes; `none` exits 1 by design and that
is not a rule failure — A2.1 reports `none`, it does not gate on it).

Paste changes against the committed `data/benchmarks/expert_paste_eval_results.csv` (an
auto run) — no pass/fail changed. All three paste CSVs are byte-identical to attempt 1, so
these are attempt 1's changes re-measured, with the mechanism labels Astra's review
produced:

| Paste(s) | Change | Mechanism | Status |
| --- | --- | --- | --- |
| 001–006, 008 | Demotic no longer in the per-stage likelihoods | A3 stage guard: Demotic has no own aligned hieroglyph rows, so it is not scored | **CONFIRMED** |
| 001–007 | top confidence lower (e.g. 0.626 → 0.313, 0.642 → 0.425) | A21: confidence is per-candidate absolute, the 0.4–0.5 floor is gone (`app/services/suggestions.py:1063–1067`) | **CONFIRMED** |
| 008 | stage Demotic → Earlier Egyptian; per-sign log-likelihood of the **chosen** stage −7.962 → −10.541 | A3 (Demotic skipped) + A53 (an unreadable group pays a penalty instead of a free emission); both remaining stages read nothing, equal coverage 0, Earlier wins on ℓ by 0.152 > 1e-9 | path CONFIRMED, A53 attribution **PLAUSIBLE** |
| 007 (`ẖnm`, NFD) | top suggestion `ḫnm =tw` → `ẖnm-ms` | A54: a Unicode query is matched with strict per-token Unicode, so the exact `ẖ` reading outranks the loose `ḫ` one | **CONFIRMED** |

PASTE_008's full likelihood dicts, so the two numbers are not confused: committed
`Earlier Egyptian=-8.143; Late Egyptian=-8.295; Demotic=-7.962` (chosen: **Demotic**,
−7.962; −8.143 is the **Earlier**-model score, not the chosen one); this run
`Earlier Egyptian=-10.541; Late Egyptian=-10.693` (chosen: **Earlier**, −10.541).

### A2.2′ Urk. IV / St Andrews gate (A7) — PASS

`check_standrews_urkiv_gate.py --private-dir ~/projects/Egyptology-APP/data/private`, run
in **both** modes as A7's command block requires:

| Mode | Exit | Verdict | Internal duration | File |
| --- | --- | --- | --- | --- |
| `--stage auto` | 0 | `GATE: PASS` | 66.3 s (69 s wall) | `urkiv_standrews_auto.txt` |
| `--stage declared` | 0 | `GATE: PASS` | 46.5 s (48 s wall) | `urkiv_standrews_declared.txt` |

Both modes: private rows loaded **7,659** from the resolved directory (corpus 138,131
rows, `{'BBAW': 52216, 'Ramses': 40064, 'TLA': 28369, 'AES': 9823, 'StAndrews': 7659}`), so
the St Andrews half **was run**; the pinned row `S_urkIV-001_urkIV-001Tr_0003` is present
exactly once and carries its expected folded reading (`check_gate_row` passed, no FAIL);
expert paste checks **8/8**.

**Reported, not gated (A7.3):** PASTE_001 routes to Earlier Egyptian and retrieves a pool
of 27,917 rows of 138,131 containing **0 St Andrews rows**, so the printed line is
`rank among St Andrews rows: not retrieved (reported, not gated — A7)` in both modes. That
is the expected reading of the corpus as it stands, for the reason A7 records, and the
historical gate measured the same thing (`docs/sign-function-2026-09-06.md` ~486: "PASTE_001
retrieval pool 27,917, 0 St Andrews rows in the pool"). **No gold-transliteration query
was substituted** to make the paste gate pass; A7 forbids it, and the query run was
PASTE_001's hieroglyphs exactly as in the benchmark file.

### A2.3 Stage routing — PASS

`run_stage_routing_eval.py --seed 20261025 --per-stage 200` (exit 0; 2333.4 s internal,
2335 s wall). Eligible after dedup: Earlier 9,885, Late 31,310; pool 130,045 rows (427 held
out). `routing.csv` is byte-identical to attempt 1.

| True \ chosen | Earlier | Late | Demotic | None |
| --- | --- | --- | --- | --- |
| Earlier (200) | 178 | 21 | **0** | 1 |
| Late (200) | 13 | 187 | **0** | 0 |

Abstentions 1/400. Reading accuracy on 2,620 aligned tokens: chosen stage's model 0.8790
(2303/2620), true stage's model 0.8821 (2311/2620). A3's historical 47/200 and 24/200 came
from another sample and pool and are an unpaired reference only.

### A2.4 and the A6 differences — recorded, not fixed

The margin is still 1e-9 (`app/services/stage.py:582`); nothing was tuned.

**What the two figures below compare.** The script's "A2.4 recomputation" is a **replay on
the normalised sign string**: it calls `choose_stage_by_likelihood(normalize_hieroglyphs(
query), …)` directly, while the app is called with the raw `hieroglyphs` value through
`resolve_auto_stage` (`scripts/run_stage_routing_eval.py:195–213`). So **1/400** and
**20/400** are differences between the app and that normalised replay — not isolated
measurements of the decision policy. A difference can come from the input the two calls
are given, from the coverage definition, or from the policy.

* **App vs the replay with the app's own coverage: 1/400 differ** — one paste, TLA row
  `TLA_EARLIER_3918` / `S3918`. **CONFIRMED, and it is not the decision policy.** That
  row's raw `hieroglyphs` value is `<g>D94</g><g>R3W</g>`: Gardiner-code markup with no
  character in the Unicode Egyptian Hieroglyphs block, so `contains_hieroglyphs(raw)` is
  **false** and `resolve_auto_stage` (`app/services/retrieval.py:220`) takes its
  **text-query branch** — a pooled first-pass retrieval followed by `infer_stage` — instead
  of the hieroglyph router. That branch returns no stage here and, by design, an **empty**
  likelihood dict, which is why this row's `score_*` columns in `routing.csv` are blank:
  the CSV writes the *app's* scores, not the replay's. The replay, given the normalised
  string, scored Earlier and Late (coverage 0 each) and resolved to Earlier. The app
  abstained; the row is in fact Earlier Egyptian.
* **A6.1 (no abstention at zero coverage with one eligible stage):** confirmed in the code
  (a single ranked candidate is returned whatever its coverage). Measured incidence in this
  sample: **0/400** — 399 pastes had two scored stages, 1 had none, none had exactly one.
* **A6.2 (coverage counts unlabelled AES rows):** app coverage differs from the
  own-aligned-row coverage in **215/400** pastes, and the app's choice differs from A2.4 as
  written in **20/400**: 10 chosen Earlier where own-row coverage gives Late, 9 chosen Late
  where it gives Earlier, plus the 1 abstention above. Neither difference sends anything to
  Demotic.

### A2.5 No unexplained loss (legacy pool) — PASS

Committed history = `data/benchmarks/ceval_{v4_v4,holdout_v4,le_v1}_app_auto_results.csv`
(v4 0.90 / MRR 0.7917, held-out 1 0.75 / 0.6667, LE-v1 0.8667 / 0.8167).

| Set | Committed | L-auto (frozen tokens) | C-auto (current tokens) | Lost committed → L | Lost L → C |
| --- | --- | --- | --- | --- | --- |
| v4 (20) | 0.90 / 0.7917 | **0.90 / 0.8000** | **0.90 / 0.8000** | **none** | **none** |
| held-out 1 (20) | 0.75 / 0.6667 | **0.75 / 0.6750** | **0.75 / 0.6667** | **none** | **none** |
| LE-v1 (30) | 0.8667 / 0.8167 | **0.8667 / 0.8000** | **0.8667 / 0.8000** | **none** | **none** |

(top-3 useful / MRR; failures 2, 5, 4.) The misses are the same queries as before: v4
COMP_007, COMP_014; held-out HOLD_001, 002, 005, 014, 026; LE-v1 LE_008, 014, 034, 044. No
gains either.

Rank changes inside the top 3 — not losses, listed so the MRR moves are accounted for:

| Query | Rank | Mechanism | Status |
| --- | --- | --- | --- |
| COMP_022 | 3 → 2 (committed → L) | **Not A21.** The relative confidences themselves changed, because this ASCII query's `translit_overlap` and `relative_score` are read off retrieval — A51 (per-stage IDF on the Late Egyptian subset's own row count) and/or the `normalizer.py` search-key folds changing corpus document frequencies | **PLAUSIBLE**, not isolated |
| HOLD_008 | 3 → 2 (committed → L) | A17: the row `{wn} ={ꞽ} 〈wn〉 Ppy pn …` no longer matches on its superfluous `{…}` text and drops out of the top 3 | **CONFIRMED** |
| HOLD_008 | 2 → 3 (L → C) | A17 + A55 token mode: the current expected tokens drop the `{=ꞽ}` token, so candidate 2's overlap falls 0.263 → 0.211, below the threshold; the third row is still useful | **CONFIRMED** |
| LE_005 | 1 → 2 (committed → L) | the two top rows were tied at confidence 0.561; the row sharing the rare word `qbḥ` now ranks first. Most likely A51 (Late Egyptian IDF on the stage subset's own row count gives rare content words their weight back); the useful row is second | **PLAUSIBLE**, not isolated |

**Why A21 cannot be the COMP_022 mechanism.** The per-candidate absolute-evidence factor is
applied at `app/services/suggestions.py:1063–1067`, *after* `rows.sort(...)` at :1055–1061
and after the `rows[:top_n]` slice; the sort key is the **relative** confidence and the code
comment at :1047 says so. A21 therefore rescales displayed numbers (0.555 → 0.273 / 0.302)
and can never reorder. The sort key, tie-break included, is unchanged from the merge-base
`27c1a7b`. A54 is inert here (no Egyptological letters in the query) and A17 does not change
either candidate's comparison key (neither contains `{…}`).

**COMP_011 (v4): `stage_used` Late Egyptian → pooled, rank unchanged.** It is **not**
A3/A53. COMP_011's query is ASCII transliteration, so it never reaches the hieroglyph
coverage-first router: the harness's `--stage auto` branch does a pooled first-pass
`retrieve_top_k` and then `infer_stage` (`scripts/run_competitive_ambiguity_eval.py:881–891`;
`resolve_auto_stage` and `choose_stage_by_likelihood` appear 0 times in that file), and the
app's own `resolve_auto_stage` takes the likelihood router only `if contains_hieroglyphs(
query)` (`app/services/retrieval.py:220`). `infer_stage` is **byte-identical** between
`27c1a7b` and HEAD. "pooled" is `stage_used == ""`, i.e. `infer_stage` returned `None`.
*Path CONFIRMED; trigger PLAUSIBLE:* the pooled first pass returned a different top-10
whose labelled-stage mix no longer clears `infer_stage`'s share/lift guards. The new rank-2
suggestion `hp =sn pw n mrr{.t} =sn` (BBAW B016189) matches on the token `mrr{.t}`, which is
possible only once A17 deletes `{…}` from the search key; it is the only `mrr{` row in the
corpus and was absent from the committed top 3. Which fold flipped the guard was not
instrumented.

Shown suggestion lists changed committed → L in v4 9 queries, held-out 5, LE-v1 2 (the rank
changes above included); the others keep their useful rank.

**Mechanism status, summarised**

| Status | Changes |
| --- | --- |
| **CONFIRMED** (traced in code or data) | PASTE_001–006, 008 Demotic dropped from the likelihoods; PASTE_001–007 confidence rescaled (A21); PASTE_007 `ḫnm =tw` → `ẖnm-ms` (A54); HOLD_008 3 → 2 (A17) and 2 → 3 (A55 token mode); COMP_011 routed by `infer_stage`, not the coverage router |
| **PLAUSIBLE** (consistent, not isolated) | COMP_022 3 → 2 (retrieval signals: A51 and/or the search-key folds); LE_005 1 → 2 (A51); COMP_011's specific trigger (A17); PASTE_008's ℓ change attributed to A53 |
| **UNRESOLVED** | Which of A51 and the folds moved COMP_022's retrieval numbers; which fold flipped COMP_011's `infer_stage` guard. Both need an instrumented re-run; neither moves a query out of the top 3 |

**UNEXPLAINED top-3 losses: zero.** That is the A2.5 pass condition and it is met. The
UNRESOLVED row is about attribution between named fixes, not unaccounted behaviour.

### A2.6 Twin effect only where twins are — PASS

`list_benchmark_twins.py` wrote 817 twin rows, **byte-identical** to the committed
`data/benchmarks/known_twins_2026-10-12.csv` (`known_twins_diff.txt` is empty), so the
committed inventory decides. `compare_twin_scores.py` (exit 0, 1 s) accepted all three
pairs.

Useful-rank and suggestion changes (what `twin_changes.csv` records), all on twin queries:

* v4: COMP_001 (useful rank 1 → miss), COMP_004, COMP_017, COMP_018 (suggestions only);
  twin queries are COMP_001, 002, 004, 010, 017, 018, 022.
* held-out 1: HOLD_022, HOLD_025 (suggestions only); twins HOLD_017, 022, 023, 025.
* LE-v1: LE_020, 023, 028, 040 (suggestions only); twins LE_001, 020, 023, 028, 040.

Other C → T outcome changes, found by diffing the C-auto and T-auto CSVs column by column
(they are not in `twin_changes.csv`, which does not track these fields). Every one is on a
query with `twins_removed > 0`:

| Query | Field | C-auto → T-auto | Twins removed |
| --- | --- | --- | --- |
| COMP_018 | `exact_rank`, `top3_exact_hit` | 2 → not found, True → False | 2 |
| COMP_017 | `overlap_baseline_useful_rank`, `bm25_baseline_useful_rank` | 1 → 2 (both) | 1 |
| COMP_010 | `overlap_baseline_suggestions` | baseline list changed; app rank 2 unchanged | 1 |
| HOLD_017 | `stage_used`, `confidence_scores` | pooled (`""`) → Earlier Egyptian; 0.376/0.288/0.296 → 0.376/0.289/0.298 | 8 |
| LE_020, LE_023 | baseline useful ranks / `overlap_baseline_suggestions` | see `twin_compare.txt` | 2 each |

HOLD_017 is the only one where the **app's** stage choice moves: removing 8 twins changes
the pooled first pass, so `infer_stage` now clears its guards for Earlier Egyptian where it
previously abstained. Its useful rank is 1 before and after.

Changes on clean queries (`twins_removed == 0`): **0**, checked across all 36 shared
outcome columns on all 70 queries. The `twin_exclusion` column differs on every row — that
is the control setting itself (0 vs 0.7), not an outcome.

Twin-controlled numbers (T-auto / T-declared / T-none, top-3 useful / MRR):

| Set | T-auto | T-declared | T-none |
| --- | --- | --- | --- |
| v4 (20) | 0.85 / 0.75 | 0.85 / 0.7417 | 0.85 / 0.7417 |
| held-out 1 (20) | 0.75 / 0.6667 | 0.75 / 0.6667 | 0.75 / 0.6667 |
| LE-v1 (30) | 0.8667 / 0.80 | 0.8667 / 0.7833 | 0.8667 / 0.80 |

### A2.7 App vs word overlap — reported, no verdict

Pooled T-auto over the 70 queries (v4 20 + held-out 1 20 + LE-v1 30), top-3 useful:

| | Top-3 useful | Margin (app − baseline) | App only | Baseline only | Both | Neither |
| --- | --- | --- | --- | --- | --- | --- |
| App | 58/70 (0.8286) | — | — | — | — | — |
| Word overlap (primary) | 59/70 (0.8429) | **−0.0143** | 6 | 7 | 52 | 5 |
| BM25 (secondary) | 62/70 (0.8857) | **−0.0571** | 3 | 7 | 55 | 5 |

Per set (T-auto): v4 app 0.85 vs overlap 0.95, BM25 0.90; held-out 1 0.75 vs 0.70, 0.85;
LE-v1 0.8667 vs 0.8667, 0.90.

Caveats, as A2.7 requires:

* These are development sets the ranking was tuned on.
* The queries are generated from corpus rows, not hieroglyph reading by an Egyptologist.
* Twin control at 0.7 does not remove all cross-edition copies.
* **BM25 asymmetry:** the harness builds BM25 IDF and average length on the full corpus,
  including the target and twins removed from the pool, while the app ranks the reduced
  pool. BM25 margins are approximate and secondary.

On these sets the app does not beat word overlap. No number here is an independent accuracy
figure and none may be quoted to experts (A4); that needs (B).

### A2.8 Release floors and the release check

Every A2 rule passed, so step 11 ran. One commit changing only
`data/benchmarks/release_baseline.json` adds the `twin_controlled` block rule 8 specifies:

| Key | Value | Derivation |
| --- | --- | --- |
| `exclude_twins` | 0.7 | rule 8 |
| `expected_tokens` | `current` | rule 8 |
| `top3_useful_floor` | **0.80** | measured v4 T-auto 0.85 − 0.05 |
| `mrr_floor` | **0.70** | measured v4 T-auto MRR 0.75 − 0.05 |
| `expected_corpus_sha256` | `44543932…df1e2` | step 0 |

Both floors are inside the `[0.01, 1]` clamp. The code is byte-identical to the pinned
attempt-2 commit, so the measured numbers stand. These are **regression tolerances, not
validation** — nothing here is quotable to experts.

**Release check** — `verify_release.py --skip-tests` on the floors commit (exit **0**,
9,631 s wall; `verify_release.txt`). Verdict **READY**, gating on the twin-controlled
pool:

```
│ corpus rows      130472   (baseline 130472)
│ corpus sha256    44543932…df1e2   (baseline 44543932…df1e2)
│ gate pool        TWIN-CONTROLLED pool gates (--exclude-twins 0.7 --expected-tokens current)
│ top-3 useful     0.85   floor 0.8   <- the reportable number
│ MRR              0.75   floor 0.7
│ benchmark fails  3
│ legacy pool      top-3 0.9  MRR 0.8  (floors 0.9 / 0.7917)  NON-GATING, twins in
│ expert pastes    8/8 passed   floor 8/8
│ verdict          READY
```

**Determinism check (A1 requires it, a difference would stop the run).** Each run
`verify_release.py` makes itself reproduces the matching step-3/step-5 run exactly on the
printed top-3 useful, MRR and failure count:

| `verify_release.py` run | Its numbers | Matching step | Step's numbers | Same? |
| --- | --- | --- | --- | --- |
| legacy (v4 L-auto) | 0.90 / 0.80 / 2 failures | step 5 `v4_L_auto` | 0.90 / 0.80 / 2 | **yes** |
| twin-controlled (v4 T-auto) | 0.85 / 0.75 / 3 failures | step 5 `v4_T_auto` | 0.85 / 0.75 / 3 | **yes** |
| expert paste | 8/8 | step 3 `paste_auto` | 8/8 | **yes** |

It also re-derived PASTE_008's likelihoods as `Earlier Egyptian=-10.541; Late
Egyptian=-10.693`, the same as step 3.

"READY" here means the build clears its own regression tolerances. It is **not** an
accuracy claim and is not quotable to experts.

## Run log

Full per-step start, end, exit code and wall time: `$R/run_log.txt`.

| Step | What | Exit | Duration | Source |
| --- | --- | --- | --- | --- |
| 0 | A0 checks, sha / hash / env, all `--help` | 0 | 5 s | `run_log.txt` |
| 1 | full pytest | 0 | 543.69 s internal / 553 s wall | `pytest.txt`, `run_log.txt` |
| 2 | `list_benchmark_twins.py` + diff | 0 | 11 s | `run_log.txt` |
| 3 | paste auto / declared / none | 0 / 0 / **1** (3/8 by design) | 52 s / 30 s / 19 s | `run_log.txt` |
| 4 | Urk. IV gate auto / declared | 0 / 0 | 66.3 s / 46.5 s internal (69 s / 48 s wall) | gate `.txt` files, `run_log.txt` |
| 5–7 | 15 competitive runs (T×3, C, L per set) | all 0 | 02:37:06 → 14:19:03 incl. the 08:11–08:26 interruption | `run_log.txt` |
| 8 | `compare_twin_scores.py` | 0 | 1 s | `run_log.txt` |
| 9 | stage routing | 0 | 2333.4 s internal / 2335 s wall | `routing_summary.txt`, `run_log.txt` |
| 10 | this note | — | — | — |
| 11 | floors commit + `verify_release.py --skip-tests` | **0** (READY) | 9,631 s wall | `verify_release.txt`, `run_log.txt` |

Wall time of steps 0–9: **02:23:19 → 14:57:59**, about 12 h 35 min, including roughly 15
minutes of dead time across the interruption. Step 11 ran 15:15:26 → 17:55:57 (2 h 41 min),
so the whole attempt spans about **15 h 33 min** of wall clock.

**On the durations: this attempt was far slower than attempt 1 for identical work.**
Attempt 1 ran all 15 competitive runs in about 2 hours; attempt 2 took about 11 h 40 min
for the same 15 runs, with individual steps varying by more than an order of magnitude
(`holdout_T_none` 11,742 s here against roughly 5 minutes in attempt 1; `le_v1_L_auto`
11,782 s). The outputs are byte-identical, so the slowdown is not a code or data difference. Machine
contention or thermal throttling is suspected; the cause was not measured. It is recorded because the
pre-registration's "expected" column (~6–7 min per run) no longer describes what a run
costs on this machine.

## Attempts

| Attempt | Directory | Outcome |
| --- | --- | --- |
| 1 | `~/egyptology-runs/remeasure-2026-10-25-attempt1` | **A2.2 FAIL** (pinned St Andrews row not retrieved). Stays failed: A7 applies to attempt 2 onward and does not relabel it. Steps 5–9 were run past the failure on the lead's instruction — a protocol deviation from A2.9, and those measurements are diagnostic only. Notes: `docs/remeasure-results-2026-10-25.md` |
| 2 | `~/egyptology-runs/remeasure-2026-10-25` | **All A2 pass rules PASS** under rev. 2.1 + A6 + A7. Interrupted at `le_v1_T_auto` by a session shutdown and resumed on the same commit with the finished steps kept; no rule failed. This note |
