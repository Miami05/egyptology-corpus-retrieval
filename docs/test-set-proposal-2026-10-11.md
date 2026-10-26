# Proposal: freezing an untouched test set (2026-10-11)

Status: **proposal with four decisions taken; audit finding A25 stays OPEN.** Nothing
described here has been built. No test set has been generated,
`data/benchmarks/release_baseline.json` is unchanged, and no script was added for it.
This document is preparation, not the fix: development-set numbers still control
release decisions until the set exists, its custody is in place and the release report
uses it. Only then can A25 be closed.

## Decisions (2026-10-25)

Taken by the project owner; they replace the matching open questions below.

1. **Size: n = 200.**
2. **Sampling: stratified and seeded** (strata and rules in "Sampling").
3. **Custody: outside version control, in `data/private/`** (gitignored), in its own
   subdirectory, e.g. `data/private/test-set/`, never as a top-level CSV there:
   `load_private_examples` loads every `*.csv` directly in `data/private/` as corpus
   rows, so a queries file at that level would be served as corpus text.
4. **No per-query failure analysis until after the first report.** The first release
   report on the set uses aggregate numbers only; whether and how per-query analysis
   is allowed afterwards (and whether that retires the set) is decided then.
5. **When it is built:** in the later re-measure step, together with the twin-controlled
   re-measurement, not now.

## Purpose and status of the existing sets

The release gate (`scripts/verify_release.py`) scores `competitive_ambiguity_eval_queries_v4.csv`,
a 20-query set that everyone has read, whose borderline margins are as small as 0.005,
and whose scores include free edition-copy hits (finding A4: 7 of its 20 targets have a
twin in the corpus at word overlap 0.7 or more, 2 of them at 0.9 or more). The
"held-out" set of 2026-09-05 was used to choose configurations, so it is not held out
any more. Until a real test set exists the sets should be called what they are.

| Set | Queries | What it is |
| --- | --- | --- |
| v4, v4_driftcorrected | 20 | development set (and, today, the release gate) |
| holdout 2026-09-05 | 20 | development set, used to pick configurations |
| LE-v1 | 30 | diagnostic set (Late Egyptian) |
| NAME-v1 | 30 | diagnostic set (proper-noun spellings) |
| v1, v2, v3 | 20 each | retired, kept only so quoted numbers reproduce |
| **test set (this proposal)** | 200 | **does not exist yet** |

None of the existing sets is a test set, and none should be described as one in the
README or in a release note.

## Size

Decided: **n = 200 queries** (the proposal's figure; 100 was the absolute minimum).

The reason is how little a 20-query set can say. One query is five points, so 0.85 and
0.90 cannot be told apart. The 95% interval around an accuracy of 0.8 (Wilson):

| Queries | Interval | Half-width |
| --- | --- | --- |
| 20 | 0.58 to 0.92 | about 0.17 |
| 100 | 0.71 to 0.87 | about 0.078 |
| 200 | 0.74 to 0.85 | about 0.055 |
| 300 | 0.75 to 0.84 | about 0.045 |

What matters at release time is mostly a paired question: did this change lose queries
the previous build answered? For a paired comparison (McNemar, normal approximation,
80% power, 5% two-sided) the queries needed depend on how many queries flip either way.
With 10% of queries flipping (b + c = 10%):

| Regression to detect | Queries needed |
| --- | --- |
| 10 points | about 76 |
| 7 points | about 158 |
| 5 points | about 312 |

So n = 200 reliably catches a regression of about 6 points (about 8 points if 15% of
queries flip), n = 100 only about 9 points. If catching a 5-point loss matters, the
size should be 300. Both numbers are listed in the open questions.

## Sampling

The existing sets are not samples. `build_competitive_ambiguity_benchmark.py` ranks its
candidates by number of rivals and takes the top of the list, so every set so far is
biased toward the most contested, rival-rich sentences. A test set must be a random
sample of what a user could plausibly ask, not the hardest cases.

* **Pool.** The builder's eligibility rules, unchanged: at least two tokens, at least
  one rival, passes the query-signal rule. Pool sizes are large (the LE-v1 build
  logged 39,428 eligible Late Egyptian rows; NAME-v1 4,335), so a sample is feasible
  with room to spare.
* **Seeded random stratified sample, no ranking by rivals.** Strata are the corpus
  sources as the public corpus has them: BBAW (stage unspecified), Ramses (Late
  Egyptian), TLA Earlier Egyptian, TLA Demotic, AES (stage unspecified) and TLA Late
  Egyptian. St Andrews rows are private and stay out.
* **Quotas.** A floor of 20 queries per stratum (so a per-stratum number is at least
  roughly interpretable) and the rest in proportion to the share of the corpus that
  users query, which is a judgement call (open questions). Equal quotas and corpus
  share give very different test sets: BBAW is 52,216 of 130,472 rows, TLA Late
  Egyptian 3,601.
* **Query types.** The builder's three-way rotation (simplified, partial,
  reading-order) so all three input forms are covered in equal measure.
* **Seed.** Chosen and committed before the set is generated. The seed, the builder
  arguments and the corpus row count are recorded; the queries are not (see Custody).
* **One row per distinct reading,** as the builder already does, so a formula that
  recurs a thousand times does not fill ten slots.

## Twin guard

Finding A4 is the reason this section exists: a test set that contains twins measures
duplicate lookup. The guard has three layers, all whole-corpus and exhaustive:

1. **At build time:** the builder with `--exhaustive-twins` and `--max-twin-overlap 0.7`
   (the default 0.9 and the 4,000-entry postings cap both let twins through; see
   `exhaustive_best_twin_overlap`). A row also fails if any other row has the same
   notation-folded reading.
2. **Disjointness:** no test target, and no twin of one (word overlap 0.7 or more, or
   the same folded reading), is a target or a twin of a target of v4, the held-out set,
   LE-v1 or NAME-v1, and none is a corpus row used in tuning. Otherwise a regression on
   the test set could be explained by what the development sets taught the ranker.
3. **At eval time:** `run_competitive_ambiguity_eval.py --exclude-twins 0.7`, which
   removes every twin of the target from the pool, so a twin that appears in a later
   corpus does not silently hand over the answer.

The check is re-run on every corpus change, not once. Ramses joined the corpus after
earlier sets were built and created twins that nobody had checked for; the corpus row
count is already recorded in `release_baseline.json` (`expected_corpus_rows`) and the
test set's record would carry the same field, with a mismatch meaning "re-run the twin
guard before using this set".

## Custody (who may look)

The value of a test set is that nobody has tuned to it. In this repository that is hard
to protect, because every teammate and every coding agent can read every file.

* The **queries file and the per-query results are not committed.** Decided location:
  a subdirectory of the gitignored `data/private/` (e.g. `data/private/test-set/`;
  not a top-level CSV there, see Decisions). Gitignored keeps the file out of git and
  out of every clone and push; it does not stop a process on the same machine from
  reading it, so coding agents are instructed not to open that subdirectory, and the
  release owner is the only person who reads it.
* Committed instead: the **sha256** of the queries file, the builder arguments, the
  seed and the corpus row count. That is enough to prove which set a number came from
  and to rebuild the set if the file is lost and the corpus is unchanged.
* `verify_release.py` gets a **`--test-set` mode** that prints aggregate numbers only:
  top-3, MRR, the margin over the word-overlap baseline, each with a Wilson interval.
  No failure CSV, no per-query ids, no suggestions.
* Every use is appended to an **access log** (date, commit, who, why).
* **Retirement.** A set that has been looked at per query, or used to choose between two
  configurations, is retired and replaced by a new sample with a new seed. Looking is
  one-way, so this rule has to be applied when it happens, not afterwards.
* Per-query failure analysis on the test set is **not permitted until after the first
  report** (decided); what is allowed afterwards is decided then.

## Reporting and floors

`release_baseline.json` sets each floor to exactly the last recorded score, so one
borderline query blocks a release (0.90 becomes 0.85) while a change that is overfitted
to the 40 queries everyone has studied passes. Replace "floor = last score" with one of:

* the **lower Wilson bound**, or
* an **allowed number of lost queries** against the recorded run, with that number
  fixed in advance by a one-sided sign test over the queries that flipped. For
  example, if 20 of 200 queries flip, a build is blocked when 15 or more of the 20 are
  losses (a chance of about 2% if losses and gains were equally likely); 14 would be
  about 6%. The exact rule is set before the first use, from the flip rate between two
  builds measured on the development sets.

And require a **positive margin over the word-overlap baseline** (finding A23): the
audit found the useful rule loose enough that plain word overlap comes close to the
app on v4, so a floor on the absolute number does not show whether the ranker adds
anything. The eval now prints that margin (`margin_over_overlap_baseline_top3`), but
no margin has been recorded yet: measuring it on v4 or the held-out set is a new
measurement and has to be pre-registered first.

## Costs and risks

* **Creation:** about two person-hours (seed, build, twin and disjointness checks,
  record) and roughly 25 minutes of eval per run on the current corpus.
* **Leak risk.** A test set stored in the repo is readable by every agent and teammate
  and will leak. Keeping it outside the repo costs convenience: CI cannot run it and
  only the custodian can.
* **Drift.** The corpus grows. New sources bring editions of old sentences, so the twin
  guard has to be re-run per release, and a set can become unusable after a corpus
  change and need rebuilding.
* **Judgement.** Stratum quotas decide what the number means; any choice favours some
  kind of user over another.
* **Honest limits.** 200 queries narrow the interval to about 5 points either way; they
  do not remove the weakness of the useful rule itself (a candidate counts at token
  overlap 0.26, so the test set inherits that unless the rule changes).

## Open questions

Size (200), sampling (stratified, seeded), custody location (`data/private/`
subdirectory) and the failure-analysis rule up to the first report are decided (see
Decisions). Still open:

1. ~~Size~~ decided: 200.
2. **Quotas:** weight strata by corpus share, by share of expected user queries, or
   equally above the floor of 20? Should Late Egyptian (Ramses and TLA) and Demotic be
   weighted up?
3. **Custodian:** who is the single release owner? (Location decided: a
   `data/private/` subdirectory.)
4. **Failure analysis after the first report:** allowed at all, and does it retire the
   set? (Before the first report: not allowed, decided.)
5. **Floors:** lower Wilson bound or allowed number of lost queries, and who signs off
   the number?
6. **The useful rule:** keep the frozen v4 rule for the test set (comparable with
   history) or use the stricter rule reported alongside it (token overlap 0.5 after
   dropping one-letter particles, or lemma match)?
