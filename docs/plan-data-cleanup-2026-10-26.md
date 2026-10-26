# Plan: data cleanup, re-measure, Pyramid Texts admission, KRI test (2026-10-26, rev. 3)

Approved in outline by Ledio 2026-10-26 ~01:00, to start **after** `audit-fixes-2026-10-25` is
merged into main, pushed and deployed. Written without running anything (a pre-registered
regression run had the Mac overnight). This is a plan, not a pre-registration: part 2 and the
part 3 re-measure each get their own pre-registration file, written and committed before their
first run, in the style of `docs/remeasure-preregistration-2026-10-25.md`.

Sources read: `docs/audit-2026-10-11.md` (A6–A10, A32–A39, fix order 7–8),
`DATA-LICENSE.md`, `scripts/import_{tla_dataset,aes_relannis,bbaw_egyptian,ramses,ud_egyptian_pc}.py`,
`scripts/migrate_example_ids.py`, `scripts/import_examples.py`, `app/storage/bootstrap.py`,
`app/storage/repo.py` (`upsert_example`), `app/storage/models.py`, `app/ui/review_common.py`
(`attach_db_ids`), `app/ui/whyptology_app.py` (`annotations_unlocked`), `app/data/loader.py`,
`app/services/stage.py`, `scripts/eval_guards.py`, `docs/plan-source-scaffolding-2026-10-11.md`.

## Rev. 2 changes (answering the Codex gpt-6-astra review, verdict `not_ready`)

1. **Donor matching (blocker 1):** new step 1.1a measures matched/ambiguous/missing counts
   before any candidate exists and has stop rules. Importers get a `--donor-output` mode that
   writes *every* mapped row with raw-row provenance, before any dedup (BBAW/Ramses dedup
   internally even with `--existing ''`; TLA's composite-key dedup runs before its output is
   written). Matching order is provenance → worklist → text fallback restricted by
   subcorpus. Ambiguity is checked on both sides, each donor occurrence is used at most once,
   and conflicting metadata stops the run (§1.1, §1.2).
2. **Annotation protection (blocker 2):** a protected-key set **P** is fixed before the
   candidate is built, and every gate is written as "flagged and not in P". Each annotation is
   checked along annotation → DB id → composite key → unchanged text. The check is repeated
   against production right before replacement, with saving paused by unsetting `REVIEWER_KEY`
   (writes then fail closed) (§1.0b, §1.2, §1.8).
3. **Overlap gates (blocker 3):** fixtures with expected labels set independently are frozen
   before `check_overlap.py` is written. Labels separate whole-row containment from shared
   tokens/trigrams. There is no tuning on the gate fixtures (§4a).
4. **Sequencing (blocker 4):** part 2 now runs on the *candidates* before `examples.csv` is
   replaced or anything is deployed. Candidates, exceptions, the benchmark-target rule,
   sampling, loss acceptance and stop rules are frozen in the pre-registration. Causal
   classification covers every corpus-dependent statistic. Floors are descriptive regression
   tolerances only. The part 3 predictions are widened the same way.
5. **KRI endpoints (blocker 5):** input modality and endpoint are declared per line before
   any run. Every exploratory line, plus its passage and its other editions, is permanently
   excluded from (B) (§4d–4e).
6. **DB proof (should-fix 6):** the DB is reconciled against O first. Historical extra rows
   (H) are kept apart from the newly removed keys (R). The refresh allowlist includes the
   derived `*_norm` fields (§1.0b, §1.7, §1.9).
7. **BBAW `_` (should-fix 7):** predefined review strata are covered in full. Exceptions are
   resolved before removal, and there is a full removal manifest that also lists the kept
   annotation exceptions (§1.4).
8. **M control (should-fix 8):** M is defined exactly. Byte-identity applies to the pinned
   evaluation outputs, not to M. O is re-run on the same evaluation code (part 2).
9. **PT (should-fix 9):** structured fields are kept, witness selection is deterministic,
   and the plan says how repeated readings are handled. Conversion validation has a defined
   denominator and normalisation, and zero pairs counts as a fail. One pinned loose-token
   Jaccard is used everywhere (part 3).
10. **KRI custody (should-fix 10):** KRI material lives in `~/egyptology-private-kri/`, outside
    the checkout, the corpus roots and iCloud. Allowed backup destinations are listed. The
    St Andrews server copy follows an explicit file allowlist (§4b).

## Rev. 3 changes (answering the second Codex gpt-6-astra review of rev. 2)

1. **Pausing saves really pauses them (blocker 1):** `configured_setting()`
   (`app/ui/whyptology_app.py`) reads Streamlit secrets *first* and the environment only
   when the secret is empty. That applies to both `reviewer_key`/`REVIEWER_KEY` and
   `allow_open_annotations`/`ALLOW_OPEN_ANNOTATIONS`. Unsetting the env var alone therefore
   proves nothing. §1.7 now checks every source by key name only: the env file, the unit and
   its drop-ins, the running process's environment, and both secrets files. Before
   snapshot 2 it then **verifies in the running app** that saving is refused: the sidebar
   caption, the journal warning, and an annotation row count that must be unchanged from
   the pause to the restore.
2. **A rebuilt N is a new measurement (blocker 2):** any rebuild of N (for example to
   protect new annotations P2) is a dated pre-registration amendment. It needs refreshed
   manifests and sha256s and the complete part 2 run set (O, M, N′ in one session) before
   replacement. The rev. 2 rule "re-run only if outputs change" is removed. Saving is
   restored while the re-measure runs, and §1.7 then starts again from step 1 (§1.7 step 4).
3. **Overlap fixtures (blocker 3):** the gate corpus is named (`examples.csv` at the part 3
   commit, sha in the fixture header). The predicates are defined exactly (Jaccard bands,
   containment in each direction, a 3-word run, sign trigrams), with precedence
   `contained` > `partial` > `new`. Labels come from those predicates, never from a stratum
   name or a UD status. UD `overlap_partial` mostly means *whole-reading containment*, so
   it is labelled by predicate and is usually `contained`. Edited sentences are kept only
   if their measured Jaccard lands in the `partial` band. Negative UD lines are drawn
   *before* part 3 and held out of admission (part 3 rule 7). Two adjudicators check every
   label independently. A row they disagree on is dropped and replaced in seed order, never
   relabelled (§4a).
4. **KRI confirmation per endpoint (blocker 4):** §4e pre-registers two separate
   comparisons that are never pooled:
   * retrieval: (B) unchanged, app vs word overlap, BM25 secondary;
   * glyph → reading: app vs a defined baseline, the most frequent attested reading per
     sign group in the same pinned corpus.

   Each has its own scoring, its own one-unit-per-line analysis, its own power floor and a
   Holm correction across the two. The reading endpoint can count toward confirmation only
   after its baseline has been committed and frozen with tests, before any material arrives
   (§4e).
5. **UD structure and ordering (should-fix 5):** today `import_ud_egyptian_pc.py` folds
   spell/section/king/edition into one `citation` string. A small exporter change adds
   them as separate columns (plus split and file line). Part 3 rule 3 now has a total
   cross-section order (natural-sorted spell, then section, then the witness order, then a
   unique file position). A reading admitted in an earlier group blocks the same strict
   reading in every later group (part 3).
6. **Ramses period for donorless rows (should-fix 6):** Ramses `period = unknown` is now a
   deterministic per-source rule. It applies to every Ramses row in M and N, with or without
   a donor, because the source carries no dates (A10). The `{unknown}` gate therefore holds
   by construction. A donorless TLA row kept unchanged is gated as an explicit, listed
   exception, never silently (§1.2 rule 3a, §1.3).

## Ground rules (all parts)

* **One new branch** `data-cleanup-2026-10-26` cut from main after the merge, worktree
  `.claude/worktrees/data-cleanup-2026-10-26`. Pair style: worker → independent verifier
  (Opus + Astra) → lead re-runs the gates, one heavy process at a time.
* Run outputs go to `$R = ~/egyptology-runs/data-cleanup-2026-10-26/` (outside the repo and
  iCloud; Desktop/Documents are iCloud-synced on this Mac).
* `data/processed/examples.csv` is **never written by an importer** in this plan. Importers
  write donor files to `$R` only. One new merge script builds *candidate* CSVs, and a
  human-reviewed diff report plus the part 2 measurement come before any of them replaces the
  file.
* **Measure before deploy.** Order: inventory (1.1a) → candidates → report → review → part 2
  pre-registration → part 2 measurement on the candidates → commit → server. Nothing is
  deployed on an unmeasured corpus.
* Ask Ledio before replacing `examples.csv`, pushing, deploying, running any server command
  that writes, sending any email, or touching `REVIEWER_KEY`. Egyptological questions go to
  the experts, never to Ledio. Current behaviour stays until they answer.
* KRI material never enters the repo, the public corpus, the server, `data/private/` or any
  synced folder. St Andrews rows never enter the repo or the public corpus. On the server
  they exist only as the allowlisted file of §4b.

---

## Part 1 — Data cleanup pass

### What the data should carry afterwards

| Audit | Fix in the importer (already merged) | Effect on committed rows |
|---|---|---|
| A10 | Ramses `period = unknown` | 40,064 Ramses rows: `New Kingdom` → `unknown` |
| A33 | TLA date range + editors kept in `grammar_notes` (`TLA date: …; editors: …`) | TLA rows gain those notes where the parquet has them |
| A34 | undated → `unknown` (not the stage); "Roman Period" now runs to 642 CE | ~710 undated Demotic rows `Demotic` → `unknown`; the late-Roman/Byzantine `Undated range (…)` rows → `Roman Period` |
| A35 | transliteration-lacuna rule (`//` in a word, empty brackets, `_`) for BBAW and Ramses, text-only rows included | rows removed: documented counts 24 BBAW (bracket/`//`) + 133 Ramses = 157 (the "~154" in the brief; the recount in 1.1a decides) **plus 2,065 BBAW `_` rows** (see 1.4), minus the protected set P |
| A32 (decided part) | AES text name and upstream text id in `grammar_notes`; `source_text_id` **stays the content hash** (benchmarks and annotations hold it) | AES rows gain `AES text: …; upstream text id: …` |
| A39 | docs | DATA-LICENSE.md and comments updated with the real counts |

**Stays deferred (said so in DATA-LICENSE.md and the report):**

* A36, duplicate policy: it changes attestation counts for every source and needs its own
  decision and benchmark rerun.
* A38, Helsinki lexicon regeneration.
* Batch-2 item #2, AES editorial marks (awaiting Camilla). This also covers the **22 AES rows
  with an `_` gap**, because whether AES `_` is a gap or an editorial mark is her question.
* A37, switching TLA Earlier/Late to `--stable-ids`. It is a pure rename and is never mixed
  with content changes in one pass.

**Open expert input that touches A35:** Email 12 asked Werning whether damage should be
*marked* instead of the sentence excluded. Removal goes ahead under the current documented
rule. The removal manifest (1.4) is kept, so a later "mark, don't drop" decision can re-admit
those rows.

### Steps

**1.0 Preconditions.** Main = the merged audit branch, tree clean, and the regression (A)
results note exists. Record in `$R/env.txt`:

* commit;
* `shasum -a 256 data/processed/examples.csv` (this file is **O**);
* row count (130,472);
* Python version and `pip freeze`.

Raw inputs must be present in the main checkout's `data/raw/` and are hashed into
`$R/raw_sha256.txt`:

* `tla_earlier/tla_earlier.parquet`, `tla_late/tla_late.parquet`,
  `tla_demotic/tla_demotic.parquet`. Content checksums are verified by
  `python scripts/download_all_sources.py` without `--force`; a mismatch stops.
* `bbaw_egyptian/train.parquet`.
* `aes/files/relANNIS/`.
* The Ramses raw dir.
* The tracked TLA worklist `data/raw/real_examples_worklist.csv`.

**1.0b DB reconciliation and protected set P (read-only, on a copy of the production DB).**
With Ledio: run `scripts/backup_db.sh` on the server, then copy the newest backup to
`$R/db/snapshot1.db` (never into the repo). A new read-only script,
`scripts/check_annotation_keys.py --db-url … --csv … --out-dir …`, writes:

1. **Reconciliation of DB vs O** by composite key `(source, source_text_id,
   source_sentence_id)`:
   * `H` = DB keys absent from O (historical extra rows from earlier corpora);
   * `O∖DB` = CSV keys absent from the DB. Expected 0: deploys insert them. Non-zero
     stops the run.
   * DB keys present in O whose `hieroglyphs` or `transliteration_gold` differ from O.
     Listed; non-zero stops the run.

   H is recorded with counts per source and kept apart from everything later. It is
   *not* this pass's removal set and is never deleted here.
2. **Annotation chain.** For every annotation the chain is annotation → `example_id` →
   `examples.id` → composite key → that key's row in O. The row's `hieroglyphs` and
   `transliteration_gold` must equal the DB row's text. Outcomes per annotation: `ok`,
   `key in H` (annotation on a historical row; listed, not touched), or `text mismatch`
   (stops). This matters because `attach_db_ids` joins on keys only, so a key whose text
   changed would silently move an annotation to different text.
3. **P** = every composite key in O carrying at least one annotation. Saved as
   `$R/protected_keys_snapshot1.csv` with sha256. P is an *input* to candidate
   construction (1.2), fixed before the first candidate is built.

**1.1 Donor files (importer change + fresh runs).** The only importer change is a new
`--donor-output PATH` flag on each importer. It writes **every mapped row before any
dedup**, meaning neither the internal composite-key/reading dedup nor the dedup against
`--existing`. It adds provenance columns:

* `donor_raw_ref`: parquet row index for TLA and BBAW; relANNIS document + sentence node for
  AES; file + line for Ramses;
* `donor_seq`;
* `donor_subcorpus`.

The `--donor-output` file is written straight after mapping. Default flags must leave the
normal output byte-identical (a test on a fixture), and `--donor-output` refuses the
`examples.csv` path. This is needed because today BBAW/Ramses `deduplicate()` drops internal
duplicates even with `--existing ''`, and TLA drops repeated composite keys in its row loop.
So the current outputs cannot supply every occurrence the old corpus holds.

```bash
PY=~/venvs/egyptology/bin/python; R=~/egyptology-runs/data-cleanup-2026-10-26; RAW=~/projects/Egyptology-APP/data/raw
$PY scripts/import_tla_dataset.py --input $RAW/tla_earlier/tla_earlier.parquet --limit 1000000 \
    --language-stage "Earlier Egyptian" --id-prefix TLA_EARLIER --existing '' \
    --output $R/fresh/tla_earlier.csv --donor-output $R/donor/tla_earlier.csv
#   … same for tla_late (TLA_LATE), tla_demotic (--script-type Demotic --language-stage Demotic),
#   aes (--relannis), bbaw (--include-text-only), ramses (--raw-dir); each with --donor-output.
```

`--limit` must exceed the dataset size, because the TLA default is 100. Each script's
`--help` is checked first; a missing flag stops the run, and nothing is improvised. Importer
stdout, including drop counts, is saved to `$R/fresh/*.log`.

**1.1a Matching inventory: the first measurement, no candidate yet.**
`scripts/cleanup_merge_corpus.py --inventory-only` runs the matching of 1.2 and writes
`$R/inventory/`. It contains counts per source and per tier, and full lists for every
non-trivial class:

| Class | Meaning |
|---|---|
| `T1 key+text` | composite key reproduced by the donor *and* identical text. Only for sources whose ids are upstream or content-derived (AES content hash, others as established from the importer code and listed in the inventory header); positional generated ids never qualify for T1 |
| `T1 conflict` | same key, different text → **stop** |
| `T2 provenance` | TLA Earlier via the worklist: old row ↔ worklist row ↔ raw parquet row, *if* the worklist carries a raw reference (established here; if not, recorded and TLA Earlier uses T3) |
| `T3 text, unique` | same source **and same subcorpus** (TLA: the parquet file = id prefix; Ramses: split file; BBAW/AES: the one input), identical `hieroglyphs` + `transliteration_gold`, exactly one old row and one donor occurrence for that text |
| `T3 group, interchangeable` | k old rows and ≥ k donor occurrences with that text, and all candidate donors agree on every allowed column → assigned 1:1 in `donor_seq` order; no donor occurrence used twice |
| `T3 group, conflicting` | candidate donors disagree on an allowed column (e.g. two `period`s) → **stop** |
| `T3 group, short` | k old rows but fewer than k donor occurrences → the surplus old rows count as missing; never filled by reusing a donor |
| `missing, flagged` | no donor, lacuna predicate flags it → a removal candidate (unless in P) |
| `missing, unflagged` | no donor, not flagged → **stop** (unexplained) |
| `benchmark targets ∩ (flagged ∖ P)` | key set intersection with every `expected_source_text_id/sentence_id` in `data/benchmarks/*queries*.csv`, `expert_review_sheet.csv`, `known_twins_2026-10-12.csv`, `cross_edition_pairs_v1.csv` |

**Stop rules (decided now):**

* Any `T1 conflict`, `T3 group, conflicting` or `missing, unflagged` > 0 stops the run before
  a candidate is built. The rows are listed, and Ledio chooses per class. The only
  pre-approved resolution is "leave the row unchanged as donorless".
* A source whose T3 share is above 5% gets 20 seeded examples read independently by Opus and
  Astra before continuing.
* If `benchmark targets ∩ (flagged ∖ P)` is above 5 for any one query set, stop and ask
  Ledio. At 5 or fewer, the rule in part 2 applies.

**1.2 Merge script (new).** `scripts/cleanup_merge_corpus.py --old O --donor SOURCE=PATH …
--protected $R/protected_keys_snapshot1.csv --exceptions $R/exceptions.csv --mode {N,M}
--output … --report-dir …`. It refuses `--output` = `data/processed/examples.csv`. The
rules, per old row, in old order:

1. The donor comes from the 1.1a assignment only (T1 → T2 → T3), and each donor occurrence
   is used at most once (asserted).
2. **Ids always come from the old row**, so they are stable by construction.
3. Only allowed columns may change:
   * TLA → `period`, `grammar_notes`;
   * Ramses → `period`;
   * AES → `grammar_notes`;
   * BBAW → none, plus `display_sequence` on text-only rows if the A35 fix set it.

   `grammar_notes` changes are append-only: the old text is kept as a prefix. Any other
   column difference between an old row and its donor is **reported, not applied**. It
   blocks the run unless that (source, column, kind) is on the benign list in
   `$R/exceptions.csv`. That list is frozen in the part 2 pre-registration, not decided after
   results.

   **3a. Per-source rules that need no donor (rev. 3).** Ramses `period` is set by rule,
   not copied from a donor. **Every** Ramses row in M and N gets `period = unknown`: rows
   with a donor, donorless rows, and flagged rows kept because they are in P or on the
   exception list. This is the A10 fix itself (the Ramses source carries no dates), so it
   applies to all rows and needs no per-row evidence. No other column is set by rule. TLA
   `period`/`grammar_notes` and AES `grammar_notes` need the donor's parquet/relANNIS
   values. A donorless TLA or AES row (possible only via the pre-approved "leave unchanged"
   resolution of 1.1a) therefore stays byte-identical. It is written to
   `$R/report/donorless_kept.csv` (key, source, current `period`, the reason it has no
   donor), and that file is frozen in the part 2 pre-registration as the explicit exception
   list for the 1.3 period gates.
4. **Removal (mode N only)** happens when the fixed lacuna predicate flags the old row's
   transliteration **and** the key is not in P **and** it is not on the BBAW `_` exception
   list (1.4). The predicate is the importers' own `TRANSLIT_LACUNA_RE` plus the Ramses word
   rules, imported, not copied. AES rows are never removed in this pass. Checks:
   * every row that is flagged, not in P and not an exception is removed;
   * every removed row is flagged and in neither set;
   * the flagged rows that remain are exactly (flagged ∩ P) ∪ (flagged ∩ exceptions), each
     listed with its reason.
5. **Nothing is added.** Donor occurrences unused by O are counted by reason (internal
   duplicate, cross-source dedup at original import, etc.) and listed, not added.
6. **Mode M** (metadata-only control): start from O; apply the allowed updates for rows that
   have an assigned donor, plus the rule of 3a (Ramses `period = unknown` on every Ramses
   row); leave every other column of a donorless row unchanged, *including* flagged rows
   without a donor; remove nothing. M therefore differs from O only in allowed columns.

Tests use synthetic fixtures only:

* an unchanged row stays byte-identical;
* a disallowed column change blocks;
* a flagged row is removed, but a flagged row in P is kept;
* an unflagged missing row stops;
* a conflicting donor group stops;
* a short group never reuses a donor;
* a donorless Ramses row (plain, in P, and on the exception list) gets `period = unknown`
  in both modes, while a donorless TLA row stays byte-identical and is listed in
  `donorless_kept.csv`;
* an id is never taken from a donor;
* the script refuses to overwrite examples.csv.

**1.3 Diff report (`$R/report/`).** Per source: unchanged; changed (by column); removed (by
lacuna kind); kept-flagged (by reason: P, exception); donor-only (not added). For each
(source, change kind) there are 20 random examples (seed 20261026), old vs new. Pass/fail
checks are printed at the top:

| Check | Pass |
|---|---|
| N rows = 130,472 − \|R\|; M rows = 130,472; columns and order identical to O | exact |
| ids: every candidate row's composite key exists in O, unique | 0 new, 0 duplicate |
| non-allowed column changes not on the frozen benign list | 0 |
| R ∩ P | 0 |
| R ∩ benchmark targets | equal to the 1.1a count; each listed (handled per part 2) |
| Ramses `period` value set, over **all** Ramses rows in M and N (donor, donorless, kept-flagged) | `{unknown}`, no exceptions (rule 3a) |
| TLA `period` equal to a language-stage name; `Undated range` | 0 outside `donorless_kept.csv`; any `Undated range` left (dates outside −4000…642) listed one by one. Rows on `donorless_kept.csv` are counted and listed in their own line of the report, never merged into the pass count |
| `donorless_kept.csv` | equal to the 1.1a donorless set Ledio approved; sha256 equal to the pre-registered one |
| BBAW/Ramses rows matching the lacuna predicate in N | exactly the kept-flagged list (P ∪ exceptions), none other |

**1.4 Review, BBAW `_` strata, removal manifest.** Opus and Astra each read the report
independently (not the lead's conclusions). Ledio sees the summary table and approves.
The 2,065 BBAW `_` rows are the big item: DATA-LICENSE says BBAW uses `_` for a lost sign
(827/867 `[_]` rows have `//` in the glyphs). The review strata are fixed *before* the report
is read:

| Stratum | Definition | Review |
|---|---|---|
| S1 bracketed | `_` only inside `[…]` | 20 seeded |
| S2 bare token | a standalone `_` token | 20 seeded |
| S3 embedded | `_` inside a word (`x_y`) | all if ≤ 40, else 40 seeded |
| S4 unusual | `_` at a line edge, repeated `__`, mixed with `//` or `⸢⸣`, or anything matching none of S1–S3 | all |
| ×T text-only | each of S1–S4 restricted to rows without glyphs | all if ≤ 20 per stratum, else 20 seeded |

The question each reviewer answers: "is `_` here a lost sign?" A row where either reviewer
says no goes to `$R/exceptions.csv` with a reason and stays. A stratum where more than 2 of
its reviewed rows are exceptions is held back in full, and only that stratum's rows stay.
Exceptions are resolved before the candidate is rebuilt, never after part 2 results.

The **removal manifest** `$R/report/removal_manifest.csv` has one line for every flagged row:
key, source, stratum or lacuna kind, old reading, rule hit, decision (`removed` /
`kept: annotated (P)` / `kept: exception <reason>`). It is committed with 1.8 as the
re-admission list for a "mark, don't drop" answer.

**1.5 Annotation proof on the candidate (read-only, snapshot1).**

```bash
DATABASE_URL=sqlite:///$R/db/snapshot1.db $PY scripts/migrate_example_ids.py --new-csv $R/candidate_N.csv
```

Expected:
* `to rename 0`, `ambiguous 0`, `collisions 0`, `csv_duplicates 0`;
* `unmatched` = **H ∪ R exactly**, with H ∩ R = ∅ and H equal to the 1.0b set. The script
  then refuses `--yes`, which is correct: nothing is renamed.

`check_annotation_keys.py` on the candidate must show:
* every chain from 1.0b still `ok` against N (key present, text unchanged);
* **0 annotations on R**.

**1.6 Part 2 runs here** (pre-registration, then measurement on O, M, N). A failed part 2
stop rule ends part 1 at this point: nothing is committed or deployed.

**1.7 Production re-check with saving paused (immediately before replacement).** With Ledio,
on the server:

**How the gate reads its settings (from the code at 1.0; re-read it then, because this is
taken from the audit branch).** `configured_setting(secret_name, env_name)` in
`app/ui/whyptology_app.py` returns `st.secrets[secret_name]` when that is non-empty, and
falls back to `os.getenv(env_name)` only otherwise. Two settings decide saving:

* `configured_reviewer_key()` = `configured_setting("reviewer_key", "REVIEWER_KEY")`;
* `open_annotations_allowed()` = `configured_setting("allow_open_annotations",
  "ALLOW_OPEN_ANNOTATIONS")` ∈ {1, true, yes}.

`annotations_unlocked()` returns `open_annotations_allowed()` when the key is empty, and the
session's unlock flag otherwise. The only annotation write is `save_annotation(...)` in the
Workspace form, behind `if not annotations_unlocked(): return`. The FastAPI app has no
write endpoint. Saving is off for everyone exactly when **both** settings are empty or false
**in both sources**. Removing an env var while `reviewer_key` sits in a secrets file changes
nothing.

Streamlit reads secrets from `<cwd>/.streamlit/secrets.toml` (the unit's
`WorkingDirectory=/home/ledio/egyptology`, so `/home/ledio/egyptology/.streamlit/secrets.toml`)
and from `~/.streamlit/secrets.toml` (`/home/ledio/.streamlit/secrets.toml`). It also reads
any extra path listed under `secrets.files` in either `.streamlit/config.toml`. The
environment comes from `/home/ledio/egyptology.env` (EnvironmentFile) and from the unit's
`Environment=` lines and drop-ins (`systemctl --user cat egyptology`).

**Rule for every check below:** commands print key **names** and counts, never values
(`grep -cE '^\s*(reviewer_key|allow_open_annotations)\s*='`, or
`tr '\0' '\n' < /proc/$PID/environ | cut -d= -f1 | grep -cx REVIEWER_KEY`). No secret value
is ever printed or copied into `$R` or into any file Claude handles.

With Ledio, on the server:

1. **Pause annotation writes.**
   1. **Inventory.** For each of the four places (the env file, unit + drop-ins, both
      secrets files, and any `secrets.files` path), record in `$R/pause_inventory.txt`
      whether `reviewer_key`/`REVIEWER_KEY` and
      `allow_open_annotations`/`ALLOW_OPEN_ANNOTATIONS` are present. Record names and
      locations only, so the restore in 1.9 puts the key back exactly where it was.
   2. **Remove.** Ledio removes the key from **every** place it was found. He also removes or
      empties any `allow_open_annotations`/`ALLOW_OPEN_ANNOTATIONS`. Then he restarts the
      service (`systemctl --user restart egyptology`).
   3. **Verify the sources** (static): a re-run of the inventory shows 0 occurrences of all
      four names in all places. `/proc/<MainPID>/environ` of the restarted process (PID
      from `systemctl --user show egyptology -p MainPID`) has neither `REVIEWER_KEY` nor
      `ALLOW_OPEN_ANNOTATIONS`.
   4. **Verify in the running app** (behavioural; required, because a source the inventory
      missed would show up only here):
      * open the live app as an ordinary visitor. The sidebar shows *"Annotation saving is
        switched off: no reviewer key is configured."* That text is rendered only when
        `configured_reviewer_key()` is empty **and** `open_annotations_allowed()` is false,
        both read through `configured_setting`, so secrets included. It shows no
        reviewer-key field;
      * open one example's Workspace. It shows *"Saving is switched off on this
        deployment."* and no Save button;
      * `journalctl --user -u egyptology --since <restart>` contains the one-per-process
        warning *"annotations: ANNOTATIONS_DURABLE is on but REVIEWER_KEY is not set and
        ALLOW_OPEN_ANNOTATIONS is off, so annotation saving is switched off for everyone."*
        It is emitted on the first page render after the restart;
      * record `SELECT COUNT(*), MAX(id) FROM annotations` on the live DB as `A_pause`
        (read-only `sqlite3 -readonly`).

      Any check that fails stops here. Nothing is snapshotted until all four pass.
   Side effect: keyed sessions lose the St Andrews rows for the window. Ledio announces
   this to reviewers.
2. `scripts/backup_db.sh` → copy to `$R/db/snapshot2.db`. Its annotation `COUNT(*), MAX(id)`
   must equal `A_pause`.
3. Re-run 1.0b and 1.5 on snapshot2 → `P2`, `H2`.
   * If `P2 ∖ P` does not intersect R, the measured N stands unchanged (same sha256 as part
     2), and we go to step 5.
   * If `P2 ∖ P` intersects R (a removal candidate was annotated since snapshot1), the
     measured N is **not** shipped. Go to step 4.
4. **Rebuilt N = a new measurement (no shortcut).** Any rebuild of N, for whatever reason, is
   handled as follows:
   1. **Restore saving** (as 1.9 step 5) for the duration. The window must not stay open
      overnight.
   2. Write a dated **pre-registration amendment** (an appended section in the part 2 file,
      committed before any run). It states the reason and the new inputs:
      * `protected_keys_snapshot2.csv` = P ∪ P2, with sha256;
      * the regenerated removal manifest and `donorless_kept.csv`;
      * the unchanged `exceptions.csv` sha256;
      * the new sha256 of N′ (M does not depend on P, but its sha256 is re-recorded);
      * the commit.

      The loss-acceptance and stop rules are not changed.
   3. Rebuild N′ deterministically (`--protected` = P ∪ P2), then redo 1.3, the 1.4 manifest
      check and 1.5 in full.
   4. Run the **complete part 2 run set**: O, M, N′, every set, in one session, on the same
      code. This happens even if no per-query output is expected to move. The results note
      gains an amendment section, and N′ ships only if it passes the frozen rules.
   5. Start §1.7 again from step 1 (pause, verify, snapshot3, P3), with P ∪ P2 as the new
      P. If a second rebuild is needed, stop and decide with Ledio, for example a pause
      kept open across the re-measure by agreement with the reviewers.
5. Only then go on to 1.8 and 1.9, with saving still paused. The key is restored at the end
   of 1.9, after the live re-check. Before the restore, the live annotation
   `COUNT(*), MAX(id)` must still equal `A_pause`; any difference means a write got through
   and stops the run.

**1.8 Commit (Ledio approves).** One commit containing:

* `examples.csv` = the measured N, or N′ after an amendment (sha256 equal to the last
  complete part 2 run set);
* `release_baseline.json` corpus fields (`expected_corpus_rows`, plus
  `expected_corpus_sha256` if rule 8 of (A) added it); floors are changed only per part 2;
* the removal manifest;
* DATA-LICENSE.md indication of changes per source (counts, date, what was removed and why,
  the kept exceptions, what is deferred);
* tests asserting the 1.3 table on the committed file.

Full suite + paste 8/8 Auto before merging.

**1.9 Server.** The DB never re-seeds (empty-table guard), and deploys run
`import_examples.py`, which is insert-only. Sequence with Ledio, while saving is still paused:

1. Deploy. The deploy log must show `inserted 0`.
2. `import_examples.py --dry-run`. The refresh-field list must be a subset of the
   **allowlist**: `period`, `grammar_notes`, `display_sequence` and the derived fields
   `example_payload` computes from them, i.e. `display_sequence_norm` (plus any other `*_norm`
   the 1.0 code shows is derived from an allowed column, written into the pre-registration).
   Any other field (e.g. `transliteration_norm` changed by normaliser drift since seeding)
   stops the run, to be decided separately.
3. `import_examples.py --refresh-existing`.
4. Re-run `check_annotation_keys.py` on the live DB: chains `ok`, 0 annotations on R, H
   unchanged.
5. Check the live annotation `COUNT(*), MAX(id)` = `A_pause` (§1.7 step 5). Then Ledio
   restores the key to exactly the places listed in `$R/pause_inventory.txt` (and any
   `allow_open_annotations` setting that was there) and restarts. The sidebar then shows the
   reviewer-key field again, and a keyed test session can unlock saving. No test annotation
   is written.

Removed rows stay in the DB, unreachable from the UI (`attach_db_ids` is CSV-driven). If the
FastAPI `/examples/search` is served publicly (A52), deleting the unannotated R rows (never H)
is a separate, backed-up step. Otherwise they are left.

---

## Part 2 — Re-measure on the candidates, before replacement (pre-registration first)

New file `docs/remeasure-preregistration-cleanup-<date>.md`, same structure as 2026-10-25
part (A). It covers regression only: no accuracy or independence claim, nothing quoted to
experts. Release floors are **descriptive regression tolerances**, not results.

**Frozen in the pre-registration before any run:**

* sha256 of O, M and N, P, H, `$R/exceptions.csv` (benign column list + BBAW `_`
  exceptions), the removal manifest and `donorless_kept.csv`;
* the amendment rule of §1.7 step 4: a rebuilt N′ gets a dated amendment, refreshed
  hashes and the complete run set (O, M, N′). There is no partial re-run;
* query-file sha256s, code commit and `pip freeze`;
* the sampling seed and procedure (routing);
* the list of **corpus-dependent statistics** at that commit. The worker writes this list
  from the code before any run, at minimum:
  1. evidence rows / top-k pool membership;
  2. global IDF and document frequencies;
  3. reading attestation counts and suggestion frequency priors;
  4. segmentation/boundary-model statistics (C1 sign adjacency, quadrat hints);
  5. stage priors and routing counts;
  6. twin-guard pools;
  7. row order / tie-breaks.
* the benchmark-target rule: a target in R stays removed (A35 applies to all rows). Its
  query is reported in a separate "target removed" table, kept out of the O-vs-N comparison
  but listed by id. If there are more than 5 such queries in any one set, part 1 has already
  stopped at 1.1a.
* the loss-acceptance and stop rules below.

**Runs (same code commit, same evaluation code, run in one session, one heavy process at a
time):** O re-run fresh (the 2026-10-25 (A) run is only a reference), then M, then N. The
commands are those of (A) A1, with `--examples` pointing at the corpus under test. The sets:

* paste ×3 modes;
* the Urk. IV gate;
* v4 / held-out 1 / LE-v1, each with T-auto, C-auto and L-auto;
* the twin inventory;
* routing (same seed and procedure; the sample is redrawn because the eligible set changes,
  and the redraw is pre-specified).

**Prediction 1 (M).** Period and `grammar_notes` are not read by ranking, routing or the
benchmark's declared stage (the precomputed `language_stage` column in each query CSV;
`derive_stage_from_period` is not used at load). So M's **evaluation outputs** must be
byte-identical to O's from the same code: per-query results CSVs, summary JSONs and twin
inventory, all produced with the same pinned query files and environment. M itself differs
from O by construction. Any output difference means a hidden dependency → stop.
`grammar_notes` does feed card citations (`app/data/source_metadata.py`). That is display
only, checked by eye on 5 AES cards.

**Prediction 2 (N).** Every changed query is classified by mechanism from the frozen
list, with evidence. For mechanism 1, name the removed row and its role (target, twin or
top-k evidence). For mechanisms 2–7, give before/after values of the statistic and the
scores of the swapped candidates. "IDF shift" without numbers is not a classification.
The twin inventory may only shrink, and only by ids in R.

**Loss acceptance (frozen):**

* Hard gates must hold: paste 8/8 auto and declared; Urk. IV gate pass; routing
  Earlier/Late → Demotic 0/200.
* Every loss must be traced to a named mechanism. One untraced loss means N is not
  shippable.
* A traced loss is accepted only if it is mechanism 1 with a removed broken reading, or
  mechanisms 2–7 at no more than 2 losses per set.
* More losses than that → stop. The report is written, nothing is committed, and a decision
  is taken with Ledio.
* Gains are listed and never offset losses.

**Then** 1.7 → 1.8 → 1.9. The release floors are updated per (A) rule 8 if N moved them, and
`verify_release.py --skip-tests` is run. A code change during the run ends the run (as (A)
A2.9/A3).

Effort: ~1 h to write, ~4 h compute overnight (three corpora), ~½ day results note.

---

## Part 3 — Pyramid Texts (UD_Egyptian-PC) admission

Input: `data/processed/ud_egyptian_pc_candidates.csv` **rebuilt against the post-cleanup
corpus** (`import_ud_egyptian_pc.py --raw-dir … --output $R/ud/candidates.csv --examples
data/processed/examples.csv`). Nothing joins without passing all rules. The filter is a new
script `scripts/admit_ud_rows.py`, which writes a candidate CSV and a report and never writes
examples.csv.

**Exporter change first (rev. 3).** Today `build_row()` in `import_ud_egyptian_pc.py` reads
`spell`, `section`, `king` and `edition` from the sentence metadata. It keeps them only
inside the free-text `citation` string and inside `source_text_id = UDPC_PT{spell}_{king}`,
and it does not record the split file or line. Parsing them back out of `citation` is
fragile, because the format differs between Sethe and other editions. The change appends
these columns to `EXTRA_COLUMNS`:

* `ud_spell`, `ud_section`, `ud_witness` (the `# king` value) and `ud_edition`, verbatim
  from the metadata;
* `ud_split` (`train`/`dev`/`test`);
* `ud_file_line` (the 1-based line of the sentence's `# sent_id` in its `.conllu` file).

Every existing column stays byte-identical, which a fixture test checks. A row whose
metadata lacks spell, section, witness or edition gets the empty string, and rule 3
handles that explicitly. `admit_ud_rows.py` reads only these columns, never `citation`.

**Pinned similarity.** Every Jaccard in this plan (part 3 rule 2, §4a, (B)) is
`scripts/eval_guards.py: jaccard` over `corpus_token_sets`: tokens =
`_token_set(loose_reading_form(transliteration))`. It is imported, never re-implemented. The
commit sha is recorded in each report.

### Admission rules (all must hold)

1. **New on all four checks:** `overlap_status == unmatched_by_current_rules` (covers strict
   reading, folded reading, shared TLA id, partial containment) **and** `glyph_overlap ==
   False` (spacing-insensitive signs) **and** `lemma_overlap == False` (lemma-id sequence).
2. **Cross-edition check vs TLA PT rows.** The TLA HF rows carry no ids, so the check is by
   content: no corpus row (any source) may have pinned Jaccard ≥ 0.5, the same threshold as
   (B). Excluded rows are listed with their nearest corpus row.
3. **One per spell section, deterministic, with a total order.** Candidates are grouped by
   (`ud_spell`, `ud_section`). Each group admits at most one row, because A36 (duplicate
   policy) is undecided. A row with an empty `ud_spell` or `ud_section` is not admitted in
   this pass and is listed as `missing structure`.

   **Natural key.** For a spell or section value v, the key is (leading integer of v, or
   +∞ if none; the rest of v as a Unicode code-point string). For example
   `213 < 213A < 214 < 1004`.

   **Total order over all candidate rows,** used for both "first group" and "first row":
   1. natural key of `ud_spell`;
   2. natural key of `ud_section`;
   3. witness in the fixed order W < T < P < M < N, then any other witness by code point;
   4. `ud_edition` by code point;
   5. `ud_split` in the order train < dev < test;
   6. `ud_file_line` as an integer.

   (`ud_split`, `ud_file_line`) is unique per sentence, so the order is total. Groups are
   processed in the order of their first row. Within a group, the representative is the
   first row in this order that passes rules 1, 2, 4, 6 and 7 **and** whose strict reading
   key (`strict_reading_key`) has not already been admitted by an earlier group.

   **Repeated readings** (`repeated_in_candidates == True`) are not excluded wholesale. In
   the same group they compete under the order above. Across groups, a strict reading enters
   at most once: in the first group, in the total order, whose representative it is. Every
   later row with that key is listed as `repeat of <key>, admitted in <spell>/<section>`.
   The admission report lists every repeated key with all of its groups.
4. **Fully aligned:** `aligned == True`, `glyphs_incomplete == False`, `alignment_issue`
   empty, `has_lacuna == False`. No unknown-sign row (`UC_No`, `Lost`, `...`, unencoded
   code points) enters, not even text-only, in this pass.
5. **Citation and structure kept:**
   * `source = UD_Egyptian-PC`;
   * `source_text_id = UDPC_PT<spell>_<witness>`, as the importer already writes it (rev. 3
     aligns the plan to the code; a different id scheme would be its own decision);
   * `source_sentence_id = <ud sent_id>` (upstream, stable);
   * `source_ref` = `PT <spell> §<section> (<king>; <edition> ed.)` + `UD v2.18`.

   `grammar_notes` carries the fields in one fixed, parseable form:
   `Old Egyptian (Pyramid Texts); spell: <n>; section: <s>; witness: <king/pyramid>;
   edition: <e>`. The admission report keeps them as separate columns. No schema change.
6. **Not a benchmark target or near-twin** (pinned Jaccard ≥ 0.5) of any query in the
   exclusion manifest of (B).
7. **Not held out for the overlap gate (rev. 3).** The 4a negative UD lines are drawn from
   the rule-1/2/4/6-passing candidates **before** this filter runs. They go in
   `$R/ud/fixture_holdout.csv` (`ud_sent_id`, strict key, sha256), which is frozen in the part 3
   pre-registration. The filter excludes every holdout row. It also excludes every
   candidate that would make a holdout line non-`new` in the final corpus under **any** §4a
   predicate (C1–C4, P1–P3). Each exclusion is listed with its reason. A holdout row's (spell, section)
   group may still admit a different row that passes this rule.

**Conversion check before admission** (validates the Tübingen → TLA table on real data):

* **Pairs** = every candidate excluded as `duplicate_tla_id` where both the UD row and the
  matched corpus row have a non-empty reading.
* **Denominator** = all such pairs, including any the converter fails on (a conversion
  failure counts as a disagreement).
* **Editorial normalisation**, applied to both sides before comparison and frozen here:
  remove `[ ] ⸢ ⸣ 〈 〉 { } ( ) ? !`, `...`/`…`, and collapse whitespace. Nothing else.
* **Pass:** pairs ≥ 1, ≥ 85% identical strict key, and **no letter disagreement** after
  normalisation (the AES import's bar). **Zero pairs = fail** (nothing was validated).
* **Fail** → stop and ask Nederhof.

**Stage label:** `language_stage = Earlier Egyptian`, `period = Old Kingdom`. Reason: the app
knows three stages, and `normalize_stage("Old Egyptian")` returns None. That would make the
rows stage-less evidence for Late and Demotic pastes too, and invisible to the stage guard.
TLA files Old Egyptian under "Earlier Egyptian", so this matches the existing rows. Whether
to split Old Egyptian later is a question for Nederhof (one line in the next email), not a
code default.

**Attribution:**

* add the UD credit (DATA-LICENSE.md text, already drafted there) to `CORPUS_CREDITS`, the
  per-row export licence column (A30 mapping) and the credit test;
* move the DATA-LICENSE section from "not in examples.csv" to a corpus section with counts
  and changes;
* update the "Every copy" table.

**Append + ids:** rows are appended at the end, and no existing row changes (checked: the old
prefix is byte-identical). There is no annotation impact (new ids only). The deploy shows
`inserted = admitted`. As in part 1, the re-measure below runs on the candidate *before* it
replaces examples.csv or is deployed.

**Re-measure after admission:** a second short pre-registration, same structure as part 2,
baseline = the committed part 1 N, re-run fresh on the same code. Predictions are classified
by the same frozen list of corpus-dependent statistics, not only "a UD row entered top-k":

* added Earlier rows shift global IDF;
* they shift attestation counts;
* they shift the segmentation/boundary statistics;
* they shift the Earlier stage prior and routing counts.

Each changed query needs a named mechanism with numbers, and the same loss-acceptance rule
applies. Hard gates are unchanged: paste 8/8, Urk. IV gate, Demotic 0/200. The twin
inventory diff lists any UD row that twins a benchmark target (expected 0 after rule 6).

Effort: script + tests ½ day; conversion check + review ½ day; docs/credits 2 h; re-measure
overnight + ½ day.

---

## Part 4 — KRI test with Camilla

### 4a. Overlap checker (scaffolding plan Phase 3): spec now, gate fixture frozen on the gate corpus

**Gate corpus G (rev. 3).** The gate runs against `data/processed/examples.csv` **at the part
3 commit**: the cleaned N plus the admitted UD rows. That is the corpus 4d runs on. Its
commit and sha256 go in the fixture header. With `--private-dir`, G also includes
`standrews.csv` at a recorded sha256. If `examples.csv` changes again before 4d, both
adjudicators re-verify every label on the new sha. Any changed label retires the fixture,
and a new one is drawn with a new seed.

**Predicates (fixed now; thresholds are part of the spec).** For a line q and a corpus row
r ∈ G:

* `fold` = `app/data/normalizer.py: search_fold`;
* `skey` = `app/services/suggestions.py: strict_reading_key`;
* `J` = the pinned Jaccard (`scripts/eval_guards.py: jaccard` over
  `_token_set(loose_reading_form(·))`);
* `signs` = the sign string with every space, layout control and placeholder removed (the
  same definition as `glyph_key` in `import_ud_egyptian_pc.py`, imported, not re-written);
* "word-bounded x in y" means ` fold(x) ` is a substring of ` fold(y) `, padded with spaces.

| Id | Predicate (∃ r ∈ G such that …) | Evidence type |
|---|---|---|
| C1 | `skey(q) = skey(r)` or `fold(q) = fold(r)`, both non-empty | identical reading |
| C2 | `signs(q) = signs(r)`, both with ≥ 2 signs | identical signs |
| C3 | `J(q, r) ≥ 0.70` | near-identical tokens |
| C4 | q has ≥ 3 folded words and is word-bounded inside r | q contained in r |
| P1 | `0.50 ≤ J(q, r) < 0.70` | shared tokens |
| P2 | q and r share a contiguous run of ≥ 3 folded words. This includes r (≥ 3 words) word-bounded inside q, i.e. the second branch of UD's `overlap_partial` | shared word run |
| P3 | with T(x) = the set of contiguous sign trigrams of `signs(x)` (both ≥ 3 signs), `|T(q) ∩ T(r)| / |T(q)| ≥ 0.50` | shared sign trigrams |

**Label** = `contained` if any C holds, otherwise `partial` if any P holds, otherwise `new`.
The precedence is fixed. The report prints every predicate that fired, with the r key and
the J value, so `partial` via P2/P3 is never presented as containment.

**How UD statuses map (and why rev. 2 was wrong).** UD's `overlap_partial` covers two
cases. The UD reading may lie inside a corpus row: that is **C4, so `contained`**. Or a
corpus row of ≥ 3 words may lie inside the UD reading: that is P2, so `partial` unless
some C holds. `duplicate_tla_id` usually gives C1/C3 but need not, because of conversion
differences. UD statuses therefore only spread the draw. A fixture label is always
computed from the predicates against G.

**Fixture strata** (file `tests/fixtures/overlap_gate_v1.csv`, public material only; seeds
fixed in the spec):

| Stratum | n | Draw | Kept only if (verified on G) |
|---|---|---|---|
| Ramses positives | 20 | random Ramses **test**-split lines whose key + text is a row of G | C1 holds → `contained` |
| Edited real sentences | 10 | seeded G sentences (mixed sources) with 10–16 distinct loose tokens. Exactly 3 tokens are replaced by hand with words absent from that sentence. With n tokens, J ≈ (n−3)/(n+3), which lies in [0.54, 0.68] for n = 10–16; the measured value decides | no C1–C4 for any r ∈ G **and** P1 holds against the source sentence → `partial`. A failing edit is discarded and the next seeded sentence is taken; a sentence is never re-edited to fit |
| UD spread | 15 | 5 each from UD `duplicate_tla_id`, `overlap_partial`, `unmatched_by_current_rules`, drawn only from UD rows **not admitted** in part 3 (an admitted row is trivially C1) | the label is whatever the predicates give; both adjudicators must agree |
| Negatives | 10 | from `$R/ud/fixture_holdout.csv`: 20 lines (10 + 10 reserve, in seed order) drawn from rule-1/2/4/6-passing UD candidates **before** the part 3 filter, then held out of admission by part 3 rule 7 | no C and no P against G → `new`. A failing line is replaced from the reserve in order; if the reserve runs out, stop and report |
| Threshold edges | synthetic | unit tests with hand-built token sets at exact rational J = 0.49/0.50/0.69/0.70, 2- vs 3-word runs, trigram share 0.49/0.50, containment of q in r vs r in q, 2- vs 3-word q for C4 | the label follows the table above by construction |

**Independent verification of every label.** Opus and Astra each work alone. Each writes
their own short script that calls the pinned repo functions above directly, never
`check_overlap.py` (it does not exist yet, and is never shown to them). For every fixture
row and every predicate they compute: true/false, the witnessing r key and max J. They add
`grep` spot checks of the witnessing row. A row is kept only if:

* the two per-predicate tables agree exactly; and
* the resulting label equals the stratum's intended label (Ramses `contained`, edited
  `partial`, negatives `new`; UD spread has no intended label).

Otherwise the row is dropped and the next seeded row is taken. No row is ever relabelled to
fit. The fixture stores, per row: stratum, expected label, the predicates that fired, the
witness key, max J and the G sha. Its sha256 is committed before the checker is first run
on it.

Camilla's Ahmose/Urk. IV line is a separate private fixture (its label is already
established: recoverable with St Andrews): `contained` with the private dir, ≥ `partial`
without. That is checked against the same predicates.

**Timing.**
1. The predicates, thresholds, strata and seeds are committed now, with the plan
   implementation.
2. The holdout draw happens before the part 3 filter runs and is frozen in the part 3
   pre-registration.
3. Gate fixture rows and labels are drawn and frozen after the part 3 commit.
4. Checker code may be written in parallel, but only against a **dev fixture**. Its rows
   are drawn with different seeds and listed, and the gate draws exclude them.

**Implement** `scripts/check_overlap.py --lines FILE --examples … [--private-dir DIR]
[--manifest FILE] --output FILE`. It computes exactly C1–C4 and P1–P3 with the pinned
functions, plus the yod ꞽ/j/i and spacing-before-`=` folds the tool uses. A fold beyond
`search_fold` is reported as its own evidence type and never changes a C/P result. It also
checks the (B) exclusion manifest and, with `--private-dir`, the St Andrews rows.

**Gates (on G's sha):** every fixture row gets its expected label. **No tuning on the gate
fixture.** If a gate fails, the checker is fixed against the dev fixture. The failed gate
fixture is retired to dev, and a new gate fixture is drawn, verified and frozen with a new
seed before re-testing. Changing any threshold or predicate also retires the fixture.

### 4b. Custody

* **Location:** KRI PDFs and anything derived from them (her lines, queries, results, Zoom
  pack) live in `~/egyptology-private-kri/`. That is a dedicated directory **outside** the
  checkout, outside every corpus root (`data/`, `data/private/`, any `PRIVATE_DATA_DIR`)
  and outside iCloud (not under Desktop or Documents). Created with mode `700`.
  `PRIVATE_DATA_DIR` must never point at it. The check script takes it only as an explicit
  `--lines` path.
* **Allowed copies:** this Mac's local disk, plus Ledio's local Time Machine disk if he uses
  one.
* **Forbidden copies:** iCloud Drive, Dropbox/Google Drive/OneDrive, git (any repo or
  branch), the server, Claude artifacts or cloud docs, email attachments other than replies
  to Camilla, and Zoom cloud recording. The Zoom pack is screen-shared from local disk, not
  uploaded.
* **Commits:** only aggregates, counts and sha256s, never a KRI line.
* **St Andrews server copy (explicit allowlist):** only `standrews.csv`, by exact filename
  and with its sha256 checked after copy, to the server's `PRIVATE_DATA_DIR`. It is copied
  with a single-file `scp`, never a directory copy or `rsync` of `data/private`. Any other
  file found in the server's private dir is reported to Ledio.
* **Belt and braces:** a loader test that a CSV in a subfolder of the private dir is never
  loaded stays as a guard, even though no KRI file lives there.

### 4c. What to ask Camilla (one short email, Ledio sends)

Ask for 3–5 passages she wants tried. Per line:

* her transliteration (input and gold);
* the hieroglyphs (Unicode, MdC/JSesh, or a page image);
* the KRI reference (vol., page, line);
* whether her transliteration is diplomatic or normalised.

Optional: which lines she expects to be hard; whether ≥ 100 lines could be supplied later
(for 4e).

### 4d. Run and report (small n, exploratory)

**Declared before any run, per line, in `~/egyptology-private-kri/declaration.csv`** (its
sha256 committed before the first run):

* the input modality;
* the endpoint;
* the stage setting (`--stage auto`);
* the commit;
* the corpus sha.

There are two pairings:

* **glyph input → reading endpoint:** the tool's top-3 reading suggestions. Success = her
  gold in top 3 (strict key, then folded key, both reported).
* **transliteration input → retrieval endpoint:** similar-text search. Success = a
  supporting passage judged relevant by her, with rank.

A line with both kinds of input gets two declared runs, reported separately. Nothing is
re-declared after results.

Overlap-check every line first. Ramses risk: KRI is Ramesside, and Ramses is Ramesside Late
Egyptian. Ramses lines are shuffled with no text ids (overlap only by content), and its
transliteration is normalised to the expected grammatical form, so a diplomatic line may
score lower than it should. The overlap report therefore shows the Ramses nearest neighbour
and its score for every line, whatever the label. `contained` / `partial` lines are reported
as "found", never as "read". The tool runs only on `new` lines, with the declared endpoint,
showing supporting sentences with hieroglyphs and source. Report **case by case** ("k of n"),
with no percentages or intervals while n < 30 and no claim to anyone beyond "on these lines".
Zoom pack per scaffolding plan Phase 4.5 (private, local).

**Permanent exclusion:** every line seen here, its whole passage (KRI vol./page range), and
every other edition of the same text (other KRI references, a TLA/Ramses row with pinned
Jaccard ≥ 0.5, edition links) go into the (B) exclusion manifest as sha256 + reference the
day the material arrives. They can never count toward 4e.

### 4e. If ≥ 100 new lines become available

Protocol (B) of the 2026-10-25 pre-registration was written for one endpoint only:
useful-in-top-3 retrieval, compared against word overlap and BM25. It has no baseline for
glyph → reading. Rev. 3 therefore runs **two separate, endpoint-specific comparisons**.
Each has its own baseline, scoring, analysis unit and power floor, and they are **never
pooled**: no combined rate and no combined test. A line declared for both inputs is one
unit in each endpoint and is analysed separately in each. Shared by both:

* the exclusion manifest is committed first, including the 4d exclusions;
* exclusion checks: pinned Jaccard ≥ 0.5, identical fold, same text, edition link, and the
  4a checker (only `new` lines enter);
* each line's input modality and endpoint are declared up front in the declaration file
  (same pairing as 4d), before any line is run;
* `--stage auto`, one evaluation on a pinned commit and a pinned corpus sha; any change after
  seeing results retires the set (for both endpoints);
* the test and effect shape of (B): per line, a binary success for the app and for the
  baseline; discordant pairs W/L; one-sided exact sign test p < 0.05 **and** a 95% Newcombe
  paired interval with lower bound > 0, both required;
* **Holm** correction across the two endpoints (family of 2, α = 0.05). An endpoint below
  its power floor is reported as "uninformative" and still counts in the family.

**Endpoint R: transliteration input → retrieval.** This is (B) unchanged:
* unit = one declared line, clustered by passage;
* success = a useful supporting passage in the top 3, as judged by Camilla. She is blind
  to which system produced it, and both systems' top 3 are shown merged and shuffled;
* primary baseline: word overlap. BM25 is secondary, with per-pool statistics;
* power floor: about 150 lines of **this endpoint**.

**Endpoint G: glyph input → reading.** This is a new comparison. It is pre-registered as an
addendum to (B), committed before any 4e material arrives.

* **Unit:** one declared line. A line's groups are her gold word division of that line,
  mapped onto the glyph input. Lines are clustered by passage.
* **App score:** for each gold group, a hit if her gold reading is in the app's top 3 for
  that group (strict key primary; folded key reported). A group the app's segmentation
  does not produce, or that it merges or splits, counts as a miss for the app. The line
  score `s` = hits / groups.
* **Baseline B-freq (defined now):** for each gold group, take `signs(group)` (the 4a
  definition). Its top 3 = the three most frequent `strict_reading_key` values among the
  word-level (sign group, reading) pairs of the same pinned public corpus that carry
  exactly that sign string. The pairs come from the same word alignment the app's reading
  model is built from (no stage filter, no context). Ties are broken by count, then by
  strict key in code-point order. An unattested sign string gives an empty list, which is a
  miss. B-freq is given the gold segmentation, which favours the baseline; that is stated
  in the report.
* **Binary success per line:** `s ≥ 0.5`, for both app and baseline. The continuous `s` is
  reported descriptively for every line.
* **Secondary (descriptive, outside the Holm family):**
  * B-freq restricted to Late Egyptian rows;
  * the group-level hit counts.
* **Precondition:** G can be part of a confirmation only if B-freq is implemented,
  unit-tested on synthetic fixtures and committed with its sha256 **before** any 4e material
  arrives. Otherwise G is reported as exploratory, and no G number goes to experts.
* **Power floor:** about 150 lines of this endpoint, judged separately from R.

Only these comparisons yield a new number for experts, quoted per endpoint with its
baseline named.

---

## Order, dependencies, effort, who

| # | Step | Depends on | Effort | Needs |
|---|---|---|---|---|
| 0 | Merge + push + deploy audit branch; (A) results reviewed | — | morning | **Ledio** present |
| 1.0b | DB snapshot1, reconciliation (H), protected set P | 0 | 1 h | **Ledio**: server backup |
| 1 | `--donor-output` + inventory 1.1a (stop rules) → merge script → candidates N, M → report | 1.0b | ~1½ days | — |
| 4a | Predicate spec + seeds now; checker on a dev fixture in parallel; holdout drawn before the part 3 filter; gate fixture drawn, adjudicated and frozen on G (part 3 commit), then gates | spec: 0; holdout: before 3's filter; gate: 3 committed | 1½ days | Opus + Astra adjudicate |
| 1r | Report review, BBAW `_` strata, exceptions frozen | 1 | ½ day | Opus + Astra; **Ledio** approves |
| 2 | Pre-reg + regression O / M / N on candidates | 1r | 1 h + overnight + ½ day | — |
| 1s | Pause saving, snapshot2 re-check, commit, deploy, refresh, live check, restore key | 2 passes | ½ day | **Ledio**: server env, sudo |
| 3 | UD exporter columns, PT admission (rules 1–7) + its re-measure (before its deploy) | 1s, 4a holdout | ~2 days | **Nederhof**: only if conversion check fails |
| 4c | Email to Camilla | any time | 15 min | **Ledio** sends; **Camilla** supplies passages |
| 4d | Declarations, KRI run, Zoom pack | 4a gates, 3, her material | ½ day | **Camilla** |
| 4e | Endpoint R (B unchanged) and endpoint G (B-freq baseline, committed before material) | ≥ 100 lines, not overlapping 4d exclusions; G also needs B-freq frozen | 1–2 days (+½ day B-freq) | **Camilla** |

Expert answers that can change this plan:

* Werning: mark damage instead of dropping? This may re-admit A35 rows via the removal
  manifest.
* Camilla: AES editorial marks → the 22 AES `_` rows (#2).
* Nederhof: Old Egyptian as its own stage.

None blocks parts 1–3. Each would be its own later item.
