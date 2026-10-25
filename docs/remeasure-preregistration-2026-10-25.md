# Re-measurement after the 2026-10-25 audit fixes — pre-registration

Written **before** any number was measured on the fixed code. No evaluation, benchmark or
full test suite was run to write it, and no per-query result of any set was opened. Every
rule below is fixed now; a rule changed after the first run is a new pre-registration
(an addendum with its own date), never an edit of this one.

Answers audit section 6 ("Before quoting any accuracy number again: twin-guard v4 at a
lower threshold, report the baseline beside it, and freeze a new test set nobody looks
at") and the open TODO(A3 margin) in `app/services/stage.py`.

## What changed since the last measured numbers

All of these may move results, in either direction:

| Change | Audit |
| --- | --- |
| Search-key folds: capital H̱, substitute letters ʿ ȝ ỉ, `{…}` superfluous text, u̯, `(.w)` plural, ASCII `(i)`, fractions | A14, A16, A17, A47–A50 |
| Per-stage IDF uses the stage subset's own row count | A51 |
| Stage guard (skip a stage with no own aligned rows) + coverage-first auto-stage, attested readings only | A3, A53 |
| Per-candidate absolute confidence (no 0.4–0.5 floor) | A21 |
| Attested sign groups longer than 10 signs kept whole | A22 |
| Strict/loose per-token Unicode matching, `query_raw` | A54 |
| Twin guard at 0.7 at eval time; overlap and BM25 baselines printed beside the app | A4, A23 |

The search-key folds change loose tokens, so they can also change which corpus rows count as
twins. The twin inventory is therefore re-checked first (step 2 of the run order).

The numbers they replace, all measured on the legacy pool (only the target row removed),
`--stage auto --query-path app`, 130,472 rows:

| Set | Quoted | Recorded in |
| --- | --- | --- |
| v4 | 0.90 top-3 useful / MRR 0.7917 (0.89 over 18 rows with no twin at 0.9) | `release_baseline.json`, `ceval_v4_v4_app_auto_results.csv` |
| held-out 1 (2026-09-05) | 0.75 / MRR 0.67 | `ceval_holdout_v4_app_auto_results.csv` |
| LE-v1 | 0.8667 in all three modes (auto MRR 0.8167) | `ceval_le_v1_app_{auto,declared,none}_results.csv` |
| expert paste | 8/8 auto and declared, 3/8 pooled | `expert_paste_eval_results.csv` |
| Urk. IV / St Andrews gate | PASTE_001–004 pass; St Andrews row rank 1 among St Andrews rows | memory `st-andrews-hannig-conventions` |
| stage routing (A3, scratch run) | Earlier → Demotic 47/200, Late → Demotic 24/200 | audit A3 |

## Preconditions (checked before step 1, else nothing runs)

* `fix1-eval`, `fix1-services`, `fix1-ui-pipeline` and `fix1-ops` are merged into
  `audit-fixes-2026-10-25`; the tree is clean; the commit sha is written at the top of the
  results note. All runs use that one commit.
* Public corpus is **130,472 rows** (`release_baseline.json` `expected_corpus_rows`). A
  different count stops the run.
* Interpreter `~/venvs/egyptology/bin/python` (Python 3.12, outside iCloud).
* Three scripts the run needs do not exist yet. They are written to the spec in this
  document, committed, and checked on synthetic input only **before** step 1:
  `scripts/run_stage_routing_eval.py`, `scripts/build_frozen_test_set.py`,
  `scripts/report_test_set.py`.

## 1. Commands

```bash
PY=~/venvs/egyptology/bin/python
B=data/benchmarks
R=~/egyptology-runs/remeasure-2026-10-25        # outside the repo and outside iCloud
T=~/projects/Egyptology-APP/data/private/test-set   # gitignored; release owner only
mkdir -p $R
CE="$PY scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v4"
```

**Competitive sets.** For each set `S` with file `F`:
v4 = `$B/competitive_ambiguity_eval_queries_v4.csv`,
holdout = `$B/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv`,
le_v1 = `$B/competitive_ambiguity_eval_queries_le_v1.csv`. Five runs per set:

```bash
# T: twin-controlled, the new headline, all three stage modes
for M in auto declared none; do
  $CE --benchmark $F --stage $M --exclude-twins 0.7 --expected-tokens current \
      --label "$S T $M" --results $R/${S}_T_$M.csv --failures $R/${S}_T_${M}_fail.csv
done
# C: legacy pool, current tokens (bridge between L and T)
$CE --benchmark $F --stage auto --exclude-twins 0 --expected-tokens current \
    --label "$S C auto" --results $R/${S}_C_auto.csv --failures $R/${S}_C_auto_fail.csv
# L: legacy pool, frozen tokens: the only run comparable with the quoted history
$CE --benchmark $F --stage auto --exclude-twins 0 --expected-tokens frozen \
    --label "$S L auto" --results $R/${S}_L_auto.csv --failures $R/${S}_L_auto_fail.csv
```

v4 only, side report (never replaces a v4-rule number):

```bash
$PY scripts/run_competitive_ambiguity_eval.py --query-path app --useful-rule v5 \
    --benchmark $B/competitive_ambiguity_eval_queries_v4.csv --stage auto \
    --exclude-twins 0.7 --expected-tokens current \
    --results $R/v4_T_auto_v5.csv --failures $R/v4_T_auto_v5_fail.csv
```

**Word-overlap baseline beside each.** Every competitive run prints the word-overlap and
BM25 baselines on the same pool (`margin_over_overlap_baseline_*`,
`margin_over_bm25_baseline_*`); no separate command. The twin effect per set:

```bash
$PY scripts/compare_twin_scores.py \
  --pair v4 $R/v4_C_auto.csv $R/v4_T_auto.csv \
  --pair holdout $R/holdout_C_auto.csv $R/holdout_T_auto.csv \
  --pair le_v1 $R/le_v1_C_auto.csv $R/le_v1_T_auto.csv \
  --metrics-output $R/twin_metrics.csv --changes-output $R/twin_changes.csv
```

**Expert paste set** (8 rows; PASTE_001–004 are Camilla's Urk. IV 1 line in four spacings):

```bash
for M in auto declared none; do
  $PY scripts/run_expert_paste_eval.py --stage $M --results $R/paste_$M.csv
done
```

**Urk. IV / Camilla gate.** PASTE_001–004 above, plus the St Andrews check with the private
rows present (main checkout only, where `data/private/standrews.csv` exists):

```bash
PRIVATE_DATA_DIR=~/projects/Egyptology-APP/data/private \
  $PY scripts/check_standrews_urkiv_gate.py --stage auto > $R/urkiv_standrews_auto.txt
```

**Reading-model eval** (defaults: text split, duplicate and 0.8 near-duplicate exclusion,
lexicon test rows from Ramses and AES removed). Its built-in most-frequent-reading row is
the baseline:

```bash
$PY scripts/run_reading_model_eval.py --sizes 0 --results $R/rm_lex.csv \
    --errors $R/rm_lex_err.csv --by-source-results $R/rm_lex_src.csv
$PY scripts/run_reading_model_eval.py --sizes 0 --no-lexicon --results $R/rm_nolex.csv \
    --errors $R/rm_nolex_err.csv --by-source-results $R/rm_nolex_src.csv
```

**Sign-reading eval** (defaults: duplicate exclusion, near-duplicates ≥ 0.8 and same-text
rows removed from the pool; 400 targets taken every k-th over all targets):

```bash
$PY scripts/run_sign_reading_eval.py --stride-sample 400 \
    --results $R/sign_reading.csv --failures $R/sign_reading_fail.csv
```

It has no fixed baseline; that is stated with its number.

**Held-out stage routing** (A3's measurement, repeated):

```bash
$PY scripts/run_stage_routing_eval.py --seed 20261025 --per-stage 200 \
    --results $R/routing.csv > $R/routing_summary.txt
```

Spec for the script: sample with `numpy.random.default_rng(20261025)` 200 rows per stage
from rows with aligned hieroglyphs: Earlier = TLA Earlier Egyptian (12,772 available),
Late = Ramses + TLA Late Egyptian (27,937 + 3,601). Demotic has **0** hieroglyph rows, so
no Demotic pastes exist; it is still a candidate the router could pick. Remove the 400
sampled rows **and every row with the same normalised sign string** from the corpus,
build the stage resources once, and call `choose_stage_by_likelihood` (with `coverage`) on
each sampled sign string. Write per paste: true stage, chosen stage or None, per-stage
score and attested coverage, top-two score gap. Print a confusion table (true Earlier/Late ×
chosen Earlier/Late/Demotic/None) and sign-reading accuracy with the chosen stage's model
against the true stage's model (A3's 0.618 vs 0.719). Split A = the first 100 per stage in
seeded order, split B = the other 100, for the margin rule in section 3.

**Release check** (after the floors in section 3 are written into `release_baseline.json`):
`$PY scripts/verify_release.py`.

**Frozen test set**: see section 4.

## 2. Primary metric per set, twins, which rows count

| Set | Primary | Rows that count | Also reported |
| --- | --- | --- | --- |
| v4 (dev) | top-3 useful, T auto, v4 rule | all 20; pool without twins at 0.7 or same folded reading | MRR; declared, none; C and L; overlap and BM25 margins; v5 rule; clean subset |
| held-out 1 (dev) | top-3 useful, T auto | all 20 | as v4, no v5 |
| LE-v1 (diagnostic, Late Eg.) | top-3 useful, T auto | all 30 | as held-out |
| expert paste | passed/total, auto | 8 | declared, none |
| Urk. IV gate | PASTE_001–004 pass; St Andrews row rank among St Andrews rows | 4 + 1 | rank overall |
| reading model | accuracy on ambiguous signs, lexicon **off** | held-out text split after duplicate exclusion | lexicon on (per source, never as held-out), most-frequent baseline, unseen-group coverage |
| sign reading | top-3 useful | the stride sample after duplicate exclusion | top-1 exact, top-1 useful |
| stage routing | Earlier → wrong stage, Late → wrong stage, out of 200 each | 400 | → Demotic, → None, reading accuracy chosen vs true model |
| frozen test set | top-3 useful, T auto, Wilson 95% | 200 | MRR, overlap and BM25 margins |

**Twins (threshold 0.7).** A twin is a corpus row other than the target with word overlap
(Jaccard on loose tokens) ≥ 0.7, or the same notation-folded reading. In T runs every twin
is removed from that query's pool; the query itself stays in. The clean subset is the
queries with no twin in the inventory: today v4 13 of 20 (twins at COMP_001, 002, 004, 010,
017, 018, 022), held-out 16 of 20 (HOLD_017, 022, 023, 025), LE-v1 25 of 30 (LE_001, 020,
023, 028, 040), per `known_twins_2026-10-12.csv`. If step 2 changes the inventory, the new
inventory decides, and the change is reported. The old "0.89 over 18 non-twin rows" (0.9
guard) is superseded and not quoted again.

## 3. Pass/fail rules (decided now)

1. **Paste:** 8/8 in `--stage auto` **and** `--stage declared`. Pooled (`none`) is reported
   only (it was 3/8).
2. **Urk. IV gate:** PASTE_001–004 pass in auto and declared, and with the private rows
   present the St Andrews row for Camilla's line is still **rank 1 among St Andrews rows**
   and the 8 pastes still pass. If the private file is not on the machine, the St Andrews
   half is reported as "not run", never as passed.
3. **Stage routing (A3):** Earlier → Demotic and Late → Demotic must both be **0/200**
   (Demotic has no aligned hieroglyph rows, so the guard makes it unselectable; anything
   above 0 is a bug and stops the run). Total wrong-stage routing must be **below 47/200
   for Earlier and below 24/200 for Late**, so the fix did not just relabel the errors as
   Late or Earlier. None (abstain) is counted separately; above 100/200 for either stage
   is reported as a failure of auto mode even if rules above pass.
4. **A3 abstention margin:** on split A choose the smallest gap m in {1e-9, 0.05, 0.1,
   0.2, 0.3, 0.5} (log-likelihood per sign) at which wrong-stage routing is ≤ 5% (≤ 10 of
   200) with abstention ≤ 25%; report it on split B. If no m qualifies, the 1e-9 guard
   stays and that is said. m is set in `stage.py` only after this, with near-tie tests.
5. **No unexplained loss, legacy pool:** on v4, held-out 1 and LE-v1, every query that the
   committed results answered (useful rank ≤ 3) and the new **L** run does not is traced to
   a named fix (Axx) with a one-line mechanism before shipping. One untraced loss = not
   shippable. Gains are reported and never offset a loss.
6. **Twin effect only where twins are:** between **C** and **T** only queries that have a
   twin may change. Any change on a clean-subset query is a harness bug; stop. Losses on
   twin queries are the expected A4 correction and are reported, not explained away.
7. **Baseline margin, development sets:** pooling the 70 T-auto queries of v4, held-out 1
   and LE-v1, the app beats the word-overlap baseline only if its top-3 useful margin is
   **≥ +0.10** (7 queries). Otherwise the results note and every expert message say plainly:
   "on our development sets the tool is not clearly better than plain word overlap
   (+x.xx)". Same statement for BM25 with its own margin.
8. **Reading model and sign reading:** report-only. Their defaults changed (A24, A56), so
   no older number is comparable and none is printed beside them. If the context model
   does not beat most-frequent on ambiguous signs with the lexicon off, that is the
   headline of that section.
9. **Floors after measuring:** `release_baseline.json` gets a `twin_controlled` block
   (`exclude_twins` 0.7, `expected_tokens` current) with `top3_useful_floor` and
   `mrr_floor` = the measured v4 T-auto values minus 0.05 (one query), and
   `margin_floors.margin_over_overlap_baseline_top3` = 0.0. Nothing else is tuned between
   runs; a failed rule means stop, fix, new addendum, re-run everything.

## 4. Frozen test set (A25)

* **Size and sampling:** n = 200, seed **20261025**, stratified by public-corpus source.
  Floor of 20 per stratum, the other 80 by corpus share (largest remainder, from today's
  row counts):

  | Stratum | Corpus rows | Queries |
  | --- | --- | --- |
  | BBAW (unspecified) | 52,216 | 52 |
  | Ramses (Late Eg.) | 40,064 | 45 |
  | TLA Earlier Egyptian | 12,772 | 28 |
  | TLA Demotic | 11,996 | 27 |
  | AES (unspecified) | 9,823 | 26 |
  | TLA Late Egyptian | 3,601 | 22 |

  St Andrews rows are private and stay out. If a stratum's eligible pool is too small, its
  shortfall goes to the others by the same largest-remainder rule, and is recorded.
* **Builder:** `scripts/build_frozen_test_set.py`, reusing the competitive builder's
  eligibility (≥ 2 tokens, ≥ 1 rival, query-signal rule), one row per distinct reading,
  the three-way query-type rotation, `--exhaustive-twins --max-twin-overlap 0.7` plus the
  same-folded-reading rule, and **random** selection inside each stratum (no ranking by
  rivals). Disjoint from every target and every 0.7 twin of a target of v4,
  v4_driftcorrected, held-out 1, LE-v1 and NAME-v1. It prints counts only, never a query.

  ```bash
  $PY scripts/build_frozen_test_set.py --seed 20261025 --n 200 \
      --output $T/test_set_2026-10-25.csv --record $B/test_set_2026-10-25.record.json
  ```
* **Custody:** the queries file and every result of it live only in
  `~/projects/Egyptology-APP/data/private/test-set/` (gitignored; a subdirectory, because
  top-level CSVs in `data/private/` are loaded as corpus rows). Committed instead: the
  record JSON (seed, arguments, corpus rows, per-stratum counts, sha256 of the file). Ledio
  is the release owner and the only reader. Coding agents do not open that directory.
  Every use is a line in `$T/access_log.txt` (date, commit, who, why).
* **Evaluated once,** as the last step, after every other number above is final and
  written down:

  ```bash
  $CE --benchmark $T/test_set_2026-10-25.csv --stage auto --exclude-twins 0.7 \
      --expected-tokens current --results $T/runs/first_results.csv \
      --failures $T/runs/first_failures.csv > $T/runs/first_stdout.txt 2>&1
  $PY scripts/report_test_set.py $T/runs/first_results.csv
  ```

  `report_test_set.py` prints aggregates only: n, top-3 useful with Wilson 95% interval,
  MRR, margins over the overlap and BM25 baselines, the counts of queries only the app or
  only the baseline answered, and a one-sided exact sign-test p. **The app "beats word
  overlap" on the test set only if the margin is ≥ +0.05 and p < 0.05**; otherwise it is
  reported as not distinguishable. No per-query failure analysis until after that first
  report; what is allowed afterwards is decided then. A set used to choose between
  configurations is retired.

## 5. What we quote to experts afterwards (Camilla, Nederhof)

**Will quote**, each with corpus size, pool (twin-controlled at 0.7), stage mode and n:
* v4, held-out 1 and LE-v1 T-auto top-3 useful and MRR, **labelled development sets**,
  with the overlap and BM25 baselines on the same line, and rule 7's verdict as written.
* The frozen test-set top-3 with its Wilson interval and the section 4 baseline verdict, once.
* Paste 8/8 as what it is: 8 hand-built pastes, 4 of them Camilla's one line.
* Stage-routing confusion counts before and after.
* Reading-model ambiguous-sign accuracy with the lexicon **off**, beside most-frequent.
* An explicit correction: the earlier 0.90 / 0.89 / 0.75 / 0.8667 were legacy-pool numbers
  that included edition-copy hits (A4) and had no baseline beside them (A23).

**Will not quote:** any legacy-pool number as current; a number without mode, pool and n;
lexicon-on reading accuracy as a held-out result (A24); "beats the baseline" when rule 7
or the test-set rule fails; any test-set query or example; any claim that Urk. IV is
covered (it is not in the public corpus; the St Andrews row is reviewer-only); the v5
number as a replacement for the v4-rule number.

## 6. Run order (one heavy process at a time)

The Mac kills parallel heavy runs, so every step waits for the previous one to exit. No
other eval, Streamlit server or test run on the machine meanwhile. Durations: LE-v1 took
about 9.5 min per run (2026-09-06, about 19 s per query); the others are scaled from that
or unknown, and the real times are recorded.

| Step | What | Runs | Expected |
| --- | --- | --- | --- |
| 1 | Full pytest suite | 1 | unknown, record it |
| 2 | `list_benchmark_twins.py --output $R/known_twins_now.csv`; diff against the committed inventory | 1 | under 5 min (exhaustive scan was 29 s at 31k) |
| 3 | Expert paste auto, declared, none | 3 | a few min each |
| 4 | Urk. IV St Andrews check (main checkout) | 1 | unknown (+1.0 GB keyed corpus) |
| 5 | v4: T auto/declared/none, C, L, v5 side report | 6 | about 6–7 min each |
| 6 | held-out 1: T ×3, C, L | 5 | about 6–7 min each |
| 7 | LE-v1: T ×3, C, L | 5 | about 9.5 min each |
| 8 | `compare_twin_scores.py` | 1 | seconds |
| 9 | Stage routing | 1 | unknown (one stage-resource build + 400 pastes) |
| 10 | Reading model, lexicon on then off | 2 | unknown |
| 11 | Sign reading, stride 400 | 1 | unknown |
| 12 | Write the results note; set floors (rule 9); `verify_release.py` | 1 | ~10 min |
| 13 | Build the frozen test set, commit the record | 1 | under 10 min |
| 14 | Test set, once; `report_test_set.py` | 1 | about 60 min (200 × ~19 s) |

Steps 1–12 total roughly 3–4 hours of wall clock. The results go in
`docs/remeasure-results-2026-10-25.md`, quoting this file's rule numbers pass or fail.
