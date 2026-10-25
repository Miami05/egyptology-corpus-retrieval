# Re-measurement after the 2026-10-25 audit fixes — pre-registration, rev. 2

Written **before** any number was measured on the fixed code. No evaluation, benchmark or
full test suite was run to write it, and no per-query result was opened. Rev. 1 (a39efe9)
was rated not ready by an independent review (Codex gpt-6-astra); this revision replaces it.
A rule changed after the first run of (A) is a dated addendum, never an edit of this file.

**Rev. 2.1 (2026-10-25, final eval, before any run of (A); no number measured).** Corrections
so (A) runs as written, no rule loosened: the competitive block now sets `S`/`F` itself (it
used them unassigned); the release check is compared with L-auto and T-auto, the runs
`verify_release.py` actually makes, not the C-auto the old wording could pick; rule 8 clamps floors to
[0.01, 1] because `verify_release.py` rejects a floor of 0; the Urk. IV gate is measured on
one pinned row and exits non-zero unless it passes; the routing script also reports A2.4's
own-aligned-row coverage beside the app's (A2.4's "any difference is written down").

The document has two parts with different purposes:

* **(A) Post-fix regression run — tonight.** Shows that nothing broke and explains every
  change. It makes **no** accuracy or independence claim to experts.
* **(B) Confirmation on new material — later.** The only route to a new accuracy number
  for experts. **Until (B) exists, no new accuracy number is quoted to experts.**

Why no test set is built from the corpus tonight (rev. 1 §4 is withdrawn): development and
tuning have touched more of the corpus than can be listed — v1–v3, v4, v4_driftcorrected,
held-out 1, LE-v1, NAME-v1, the paste, composition, sign-reading and reading-model evals,
the A3 routing sample, and a historical 80-query tuning set in `tune_ranking_weights.py`
whose rows were not kept. A corpus sample therefore cannot be certified untouched, and
Jaccard ≥ 0.7 plus identical folded reading does not catch cross-edition BBAW/TLA copies
at 0.5–0.7 overlap.

## What changed since the last measured numbers

| Change | Audit |
| --- | --- |
| Search-key folds: capital H̱, substitute letters ʿ ȝ ỉ, `{…}`, u̯, `(.w)`, ASCII `(i)`, fractions | A14, A16, A17, A47–A50 |
| Per-stage IDF uses the stage subset's own row count | A51 |
| Stage guard (skip a stage with no own aligned rows) + coverage-first auto-stage | A3, A53 |
| Per-candidate absolute confidence (no 0.4–0.5 floor) | A21 |
| Attested sign groups longer than 10 signs kept whole | A22 |
| Strict/loose per-token Unicode matching, `query_raw` | A54 |
| Twin guard at eval time; overlap and BM25 baselines printed beside the app | A4, A23 |

Numbers they replace (legacy pool, `--stage auto --query-path app`, 130,472 rows): v4 0.90 /
MRR 0.7917; held-out 1 0.75 / 0.67; LE-v1 0.8667 (auto MRR 0.8167); paste 8/8 auto and
declared, 3/8 none; Urk. IV gate pass; A3 scratch routing Earlier → Demotic 47/200,
Late → Demotic 24/200. These were development-set numbers and are not re-quoted.

---

# (A) Post-fix regression run (tonight)

## A0. Preconditions (all checked before step 1, else nothing runs)

* **One pinned commit:** every fix branch (`fix1-eval`, `fix1-services`, `fix1-ui-pipeline`,
  `fix1-ops`) is merged into `audit-fixes-2026-10-25`, the script changes in A5 are
  committed, the tree is clean, and the worktree is checked out at that commit. Every step
  runs on it. A code change after step 1 ends the run; a new commit means a new full run.
* Recorded at the top of the results note before step 1: commit sha, `shasum -a 256` of
  `data/processed/examples.csv`, `pip freeze`, Python version.
* Public corpus = **130,472 rows** and the sha256 above; both are enforced by
  `verify_release.py` (A5) and checked by hand in step 0. A mismatch stops the run.
* Each script's `--help` shows every flag used below (`--benchmark`, `--exclude-twins`,
  `--expected-tokens`, `--private-dir`, …). A missing flag stops the run; nothing is
  improvised.
* `scripts/run_stage_routing_eval.py` exists, written to A2.3 and checked on synthetic
  input only.

## A1. Commands

```bash
PY=~/venvs/egyptology/bin/python
B=data/benchmarks
R=~/egyptology-runs/remeasure-2026-10-25        # outside the repo and outside iCloud
PRIV=~/projects/Egyptology-APP/data/private      # main checkout; holds standrews.csv
mkdir -p "$R"
git rev-parse HEAD > "$R/commit.txt"; git status --porcelain >> "$R/commit.txt"
shasum -a 256 data/processed/examples.csv > "$R/corpus_sha256.txt"
$PY --version > "$R/env.txt"; $PY -m pip freeze >> "$R/env.txt"
CE="$PY scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4"
```

**Competitive sets** — `--benchmark` always explicit (the harness default is the
contaminated v1). `S` names the set and `F` its query file:

```bash
for S in v4 holdout le_v1; do
  case $S in
    v4)      F=$B/competitive_ambiguity_eval_queries_v4.csv ;;
    holdout) F=$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv ;;
    le_v1)   F=$B/competitive_ambiguity_eval_queries_le_v1.csv ;;
  esac
  for M in auto declared none; do                     # T: twin-controlled at 0.7
    $CE --benchmark $F --stage $M --exclude-twins 0.7 --expected-tokens current \
        --results $R/${S}_T_$M.csv --failures $R/${S}_T_${M}_fail.csv > $R/${S}_T_$M.txt 2>&1
  done
  $CE --benchmark $F --stage auto --exclude-twins 0 --expected-tokens current \
      --results $R/${S}_C_auto.csv --failures $R/${S}_C_auto_fail.csv > $R/${S}_C_auto.txt 2>&1
  $CE --benchmark $F --stage auto --exclude-twins 0 --expected-tokens frozen \
      --results $R/${S}_L_auto.csv --failures $R/${S}_L_auto_fail.csv > $R/${S}_L_auto.txt 2>&1
done
```

L = legacy pool, frozen tokens (only run comparable with the committed history);
C = legacy pool, current tokens; T = twin-controlled. Then:

```bash
$PY scripts/compare_twin_scores.py \
  --pair v4 $R/v4_C_auto.csv $R/v4_T_auto.csv \
  --pair holdout $R/holdout_C_auto.csv $R/holdout_T_auto.csv \
  --pair le_v1 $R/le_v1_C_auto.csv $R/le_v1_T_auto.csv \
  --metrics-output $R/twin_metrics.csv --changes-output $R/twin_changes.csv
$PY scripts/list_benchmark_twins.py --output $R/known_twins_now.csv   # diff vs committed inventory
```

**Expert paste** (queries file explicit):

```bash
for M in auto declared none; do
  $PY scripts/run_expert_paste_eval.py --queries $B/expert_paste_queries.csv \
      --stage $M --results $R/paste_$M.csv > $R/paste_$M.txt 2>&1
done
```

**Urk. IV / St Andrews gate** (needs `--private-dir`, A5 change 1):

```bash
$PY scripts/check_standrews_urkiv_gate.py --private-dir "$PRIV" --stage auto \
    > $R/urkiv_standrews_auto.txt 2>&1
```

**Stage routing:** `$PY scripts/run_stage_routing_eval.py --seed 20261025 --per-stage 200
--results $R/routing.csv > $R/routing_summary.txt 2>&1`.

**Release check:** `$PY scripts/verify_release.py --skip-tests > $R/verify_release.txt 2>&1`
(pytest already ran in step 1). Its legacy competitive run is always v4 **L-auto** (it
passes `expected_tokens` frozen, `LEGACY_RUN`, whatever the harness default); once the
rule-8 `twin_controlled` block exists it also runs v4 **T-auto**; its paste run is
paste-auto. Each must reproduce the matching step-5/step-3 run exactly on the printed
top-3 useful, MRR and failure count (its per-query CSVs are temporary, so the comparison is
on the printed aggregates) — a difference is a determinism bug and stops.

## A2. Rules (decided now)

1. **Paste:** 8/8 in auto **and** declared. `none` reported only (was 3/8).
2. **Urk. IV gate:** PASTE_001–004 pass in auto and declared; with the private rows loaded
   (the script prints the resolved directory and a private row count > 0) the St Andrews
   row for Camilla's line is rank 1 among St Andrews rows and the 8 pastes still pass. If
   the private rows are not loaded, the St Andrews half is "not run", never "passed".
3. **Stage routing.** Pass rule: Earlier → Demotic and Late → Demotic are **0/200** each;
   anything above 0 is a bug and stops the run. Reported only: full confusion table
   (Earlier/Late × Earlier/Late/Demotic/None), abstentions, and reading accuracy with the
   chosen vs the true stage's model. A3's 47/24 came from a different sample and pool, so
   it is an unpaired reference, not a baseline.
   *Sample (exact):* eligible = public rows with non-empty normalised hieroglyphs whose
   `language_stage` is Earlier Egyptian (TLA) or Late Egyptian (Ramses + TLA); keep one row
   per normalised sign string (the first in sort order); sort by
   (`source`, `source_text_id`, `source_sentence_id`); `rng = numpy.random.default_rng(20261025)`;
   draw Earlier then Late with `rng.choice(len(eligible), 200, replace=False)`. Fewer than
   200 eligible stops the run. Removed from the pool before building stage resources once:
   the sampled rows, every row with the same normalised sign string, and every row sharing
   a `source_text_id` with a sampled row. The script prints aggregates only and writes
   per-paste rows (true stage, choice, per-stage coverage and score) to `routing.csv`.
4. **A3 margin is not tuned tonight.** The 1e-9 guard stays. Decision function, to be
   checked against the merged code (any difference is written down, not fixed tonight):
   candidates = stages that pass both guards; for each, `c` = number of segmented sign
   groups with an attested reading in that stage's own aligned rows (an integer) and
   `ℓ` = per-sign Viterbi log-likelihood, lexicon off. 0 candidates → None. 1 candidate →
   that stage if `c > 0`, else None. ≥ 2: order by (`c` desc, `ℓ` desc); if `c₁ > c₂` the
   first wins and no margin applies; if `c₁ = c₂`, gap `g = ℓ₁ − ℓ₂` and the router
   abstains (None) iff `g ≤ m` (equality abstains); `m = 1e-9` now. Choosing a larger `m`
   later is a development step: equal-coverage cases only, splits grouped by
   `source_text_id`, its own commit, followed by a new regression run; it is never
   evidence for experts.
5. **No unexplained loss (legacy pool):** on v4, held-out 1 and LE-v1, every query the
   committed `ceval_*_app_auto_results.csv` answered (useful rank ≤ 3) that L does not is
   traced to a named fix (Axx) with a one-line mechanism. One untraced loss = not shippable.
   Gains are listed and never offset a loss. The same tracing applies to L → C (token
   change) and to any paste change.
6. **Twin effect only where twins are:** between C and T only queries with a twin in the
   step-2 inventory may change. A change on a clean query is a harness bug; stop. If the
   inventory changed (folds change loose tokens), the new one decides and the diff is listed.
7. **App vs word overlap, reported, no verdict to experts:** pooled T-auto top-3 useful
   over the 70 queries, margin over word overlap (primary) and BM25 (secondary), with the
   counts app-only / baseline-only. Caveats printed with it: these are development sets
   the ranking was tuned on; queries are generated from corpus rows, not hieroglyph reading
   by an Egyptologist; twin control at 0.7 does not remove all cross-edition copies.
   **BM25 asymmetry (known, stated):** the harness builds BM25 IDF and average length on
   the full corpus, including the target and twins removed from the pool, while the app
   ranks the reduced pool. BM25 margins are therefore approximate and secondary.
8. **Release floors** are regression tolerances, not validation. After the results note
   is written, one commit changing only `release_baseline.json` adds a `twin_controlled`
   block (`exclude_twins` 0.7, `expected_tokens` current) with `top3_useful_floor` =
   measured v4 T-auto − 0.05 (one query in 20) and a separate `mrr_floor` = measured MRR −
   0.05 (a tolerance, not a query count), both clamped to [0.01, 1] (`verify_release.py`
rejects a floor of 0), plus
   `expected_corpus_sha256`. Code is byte-identical to the pinned commit, so the numbers
   stand; `verify_release.py` is then re-run once on that commit.
9. **On any failure:** stop, record it, fix on a new commit, write a dated addendum, and
   re-run all of (A) on the new pinned commit. Every attempt's `$R` directory is kept
   (renamed `…-attemptN`) and listed in the results note. No subset re-runs.

## A3. Run order (one heavy process at a time; nothing else running)

| Step | What | Expected |
| --- | --- | --- |
| 0 | A0 checks, record sha / hash / env | minutes |
| 1 | Full pytest suite, once | record it |
| 2 | `list_benchmark_twins.py`, diff | < 5 min |
| 3 | Paste auto, declared, none | a few min each |
| 4 | Urk. IV St Andrews gate | unknown (+1.0 GB keyed corpus) |
| 5–7 | v4, held-out 1, LE-v1: T ×3, C, L | ~6–7 min each (LE-v1 ~9.5) |
| 8 | `compare_twin_scores.py` | seconds |
| 9 | Stage routing | unknown |
| 10 | Results note `docs/remeasure-results-2026-10-25.md`, rule by rule | — |
| 11 | Floors commit (rule 8); `verify_release.py --skip-tests` | ~10 min |

Reading-model and sign-reading evals are not part of (A); their defaults changed (A24,
A56) and their numbers are not quoted until re-designed.

## A4. What (A) allows us to say

To experts: "the fixes are in; paste 8/8; no Demotic mis-routing; every change on our
development sets is explained." **Not** to experts: any top-3, MRR or baseline margin from
(A); any legacy-pool number as current; any Urk. IV coverage claim (it is not in the public
corpus); an explicit correction is owed that 0.90 / 0.89 / 0.75 / 0.8667 were legacy-pool
development numbers including edition-copy hits (A4) with no baseline beside them (A23).

## A5. Script changes the lead makes before (A)

1. `check_standrews_urkiv_gate.py` ignores `PRIVATE_DATA_DIR` (it uses the script-relative
   `PRIVATE_DIR`). Add `parser.add_argument("--private-dir", default=os.environ.get("PRIVATE_DATA_DIR") or str(PRIVATE_DIR))`,
   pass it to `load_corpus`, print the resolved path and private row count, exit non-zero
   if the count is 0.
2. `verify_release.py`: fail (not just print) when `corpus_rows != expected_corpus_rows`
   or the sha256 of `examples.csv` differs from `expected_corpus_sha256`; when a
   `twin_controlled` block exists, also run the competitive eval with its flags and check
   its floors. It still runs the competitive and paste evals itself (duplicates of steps
   3 and 5); `--skip-tests` avoids the duplicate pytest.
3. `run_stage_routing_eval.py`: new, to rule A2.3.

---

# (B) Confirmation on new material (later)

**Material.** Text never in the corpus or any development set, e.g. passages Camilla
supplies from KRI, or another demonstrably new source. Each item is checked before use
against the corpus and every set in the manifest: word overlap (Jaccard on loose tokens)
≥ 0.5, identical folded reading, same `source_text_id`, or a known edition link
(`data/processed/source_metadata_oraec_bbaw_link_candidates.csv`, any shared text/edition
reference) excludes it. The check output (counts and excluded ids) is committed.

**Exclusion manifest** (committed before any query is built): v1–v3, v4,
v4_driftcorrected, held-out 1, LE-v1, NAME-v1, expert paste, composition, sign-reading and
reading-model eval samples, the A3 and A2.3 routing samples, and the whole corpus as a
stand-in for the lost `tune_ranking_weights.py` 80-query set — grouped by text and
edition, not by row.

**Unit and estimand.** One query per sentence; queries of one passage form a cluster. The
estimand is the unweighted top-3 useful rate on this material in `--stage auto`,
twin-controlled pool, about this material only (no stratum weighting, no generalisation to
the corpus). Per-passage results are reported as a sensitivity check.

**Paired test (fixed now).** Primary comparison: app vs word overlap; BM25 secondary,
computed with **per-pool** statistics (IDF and average length on the same reduced pool the
app sees). Per query, both are scored useful-in-top-3 or not. Discordant pairs: W (app only)
and L (baseline only); ties (both or neither) are dropped from the test and reported.
Test: one-sided exact sign test, `P(X ≥ W | X ~ Bin(W+L, 0.5)) < 0.05`. Effect: paired
margin (W − L)/N with a 95% Newcombe (score, paired) interval. "Beats word overlap" only
if p < 0.05 **and** the interval's lower bound > 0.

**Power note** (assumed true margin +0.10; discordance = share of queries where exactly one
side is useful): N = 100 → power ~0.62 at 20% discordance, ~0.59 at 30%; N = 150 → 0.89 /
0.69; N = 200 → 0.95 / 0.83. Below about 150 queries a null result is uninformative and is
reported as such, not as "no difference".

**Custody and retirement.** Queries and results live outside the repo (gitignored private
directory, created with `mkdir -p` before any redirect); committed: the manifest, the
overlap-check output, a sha256 of the query file and the aggregate report. One evaluation,
on a pinned commit. Any code, weight or rule change made after seeing any result of it
retires the set; a retired set is never re-used for a claim. Every attempt, including
retired ones and failures, is preserved and disclosed with the number quoted.

**Until (B) has run, no new accuracy number is quoted to experts.**
