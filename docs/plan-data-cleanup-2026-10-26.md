# Plan: data cleanup, re-measure, Pyramid Texts admission, KRI test (2026-10-26, rev. 5)

**Status: DRAFT, rev. 5 (2026-10-28). Not approved, not a pre-registration.** Nothing in this
file has been run, and no code or data was changed to write it. Rev. 3 was reviewed by Opus
(`ready_after_small_fixes`) and by Codex gpt-6-astra (`not_ready`, 11 findings, 7 of them
blockers). Rev. 4 answered every one of them. Rev. 4 (commit `5fcc4f8`) was then reviewed by
Opus (`fix_first`, 2 blockers) and by Astra (`fix_first`, 4 blockers). Rev. 5 answers those; the
maps are in the **Revision log** below. Opus confirmed the rev. 3 blockers as fixed; they are
not reopened here.

The start condition has changed since rev. 3. The `audit-fixes-2026-10-25` merge is done and
**the `kri-fixes-2026-10-26` merge is now done too**: main is `51f3757` (commit message
"Merge kri-fixes-2026-10-26: cartouche window unit, pooled fallback default off"), the
measured result is `docs/kri-fixes-results-2026-10-27-attempt5.md` (attempt 5, all steps
passed, rule (b) DISABLE), and it is deployed and live (Ledio ran `~/egyptology-deploy.sh`).
Cleanup starts from that main (§1.0). This plan is a plan, not a pre-registration: part 2
and the part 3 re-measure each get their own pre-registration file, written and committed
before their first run, in the style of `docs/remeasure-preregistration-2026-10-25.md`.
Part 4 has its own status block (§4.0).

Sources read: `docs/audit-2026-10-11.md` (A6–A10, A32–A39, fix order 7–8),
`DATA-LICENSE.md`, `scripts/import_{tla_dataset,aes_relannis,bbaw_egyptian,ramses,ud_egyptian_pc}.py`,
`scripts/migrate_example_ids.py`, `scripts/import_examples.py`, `app/storage/bootstrap.py`,
`app/storage/repo.py` (`upsert_example`), `app/storage/models.py`, `app/ui/review_common.py`
(`attach_db_ids`), `app/ui/whyptology_app.py` (`annotations_unlocked`), `app/data/loader.py`,
`app/services/stage.py`, `scripts/eval_guards.py`, `docs/plan-source-scaffolding-2026-10-11.md`.
Read for rev. 4 (read-only): `scripts/check_standrews_urkiv_gate.py`, `scripts/run_kri_fixes_eval.py`,
`scripts/run_kri_fixes_prereg.sh`, `scripts/verify_release.py`, `scripts/backup_db.sh`,
`scripts/egyptology-deploy.sh`, `scripts/import_examples.py`, `scripts/migrate_example_ids.py`,
`app/core/config.py`, `deploy/systemd/egyptology.service`, `data/benchmarks/release_baseline.json`,
`docs/kri-fixes-results-2026-10-27-attempt5.md`, `docs/kri-official-test-tooling-2026-10-26.md`,
`docs/kri-bfreq-baseline-2026-10-26.md`, `scripts/kri_stats.py`.
Read again for rev. 5 (read-only, rev. 4 text against code): `app/core/config.py`
(`load_dotenv()`, the `database:` announcement and its `origin` wording),
`scripts/egyptology-deploy.sh` (`load_env_file`, the "must not be sourced" comment),
`scripts/run_kri_fixes_eval.py` (`row_id`, `--split-manifest`, the per-line boundary
columns), `scripts/check_overlap.py` (`--examples`, `--private-dir`, `--manifest`),
`scripts/eval_guards.py` (`text_level_test_mask`).

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

## Rev. 4 changes (answering the Astra and Opus reviews of rev. 3; 2026-10-28)

Both reviews were of rev. 3 at main `ac9158a`. Since then `kri-fixes` merged (main `51f3757`)
and the KRI official-test tooling landed on main (`scripts/check_overlap.py`,
`scripts/kri_*.py`, `docs/kri/exclusion-manifest.csv`, the frozen B-freq baseline).

1. **Start condition (Astra 1, Opus 4):** cleanup starts only from a main that contains the
   kri-fixes merge, has its results note committed, and is deployed. Rev. 3 named only the
   audit merge. Attempt 5, the A7 amendment and the existing 0.80 / 0.70 twin-controlled
   floors are cited as the historical references they are (Ground rules, §1.0).
2. **The Urk. IV gate has no `--examples` flag (Astra 2):** `scripts/check_standrews_urkiv_gate.py`
   accepts only `--stage`, `--rank-k` and `--private-dir`, and its `main()` always loads the
   checkout's own `data/processed/examples.csv`. Rev. 4 does not change the script. The gate
   is run from a throwaway measurement worktree whose `examples.csv` is the corpus under test,
   one invocation per mode (`auto`, `declared`), with the corpus bound by sha256 before and
   after and by the printed row and source counts (§2.1a).
3. **Decoder and segmentation are measured (Astra 3):** the competitive sets never call
   `ReadingModel.predict_sequence` or `Segmenter.segment`. Part 2 and the part 3 re-measure now
   include `scripts/run_kri_fixes_eval.py`, on a fixed held-out partition taken from O so that
   the test rows are the same across corpora, with leakage controls and frozen acceptance
   rules (§2.3, §3.3).
4. **Database targeting (Astra 4, Opus 6):** one verified absolute live path
   (`/home/ledio/egyptology/egyptology.db`) is used for backup, counts, reconciliation,
   dry-run and refresh. Backups are `.db.gz`; the exact published file is selected,
   transferred, decompressed outside the repo and integrity-checked before any use. The
   refresh needs zero would-be inserts first (§1.0a, §1.0b, §1.9).
5. **systemd (Astra 5, Opus 7):** `systemctl --user daemon-reload` after every unit or drop-in
   edit (pause and restore), `NeedDaemonReload=no` checked before the restart, no
   `INSTALL_UNITS=1` in the cleanup deploy, and the pause checks repeated after the deploy
   restart (§1.7, §1.9).
6. **Target removal, twins, floors (Astra 6, Opus 9):** the removed-target query ids are
   frozen before any run. Comparisons, the twin invariant and the loss budget use the common
   retained-target set; removed-target queries are a separate table, with the twin fallback
   (`eval_guards.twins_of_target`) named as its own mechanism. The floor denominator is the
   full committed benchmark, exactly as `verify_release.py` computes it (§2.2).
7. **Compute budget and where verification sits (Astra 7, Opus 5):** about 46 h for O + M + N
   at the measured slow rate, the same again for any N′ and for the part 3 re-measure, heavy
   runs from all worktrees serialized, and the local release verification moved before the
   saving pause and before any deploy (§1.8, §2.6, order table).
8. **B-freq and the PDFs (Astra 8, Opus 1, 2, 3):** §4.0 records the PDFs' arrival, the
   exploratory self-test and the freeze deviation, picks the order (the corpus G is the one
   named by the committed declaration; the replacement window is frozen around an official
   run), and says the `kri-official-prep` checker is the §4a checker and must follow its
   rules.
9. **Exclusion manifest (Astra 9, Opus 3, 12):** the self-test passage (entry EX001, hash
   still pending) and every other inspected line go into the manifest for **both**
   endpoints, keyed by KRI reference and text hash, never by corpus row, so removal from the
   corpus does not lift an exclusion. The manifest, complete, is an input to part 3 rule 6 and
   to every confirmation run (§4.0, §3 rule 6, §4d, §4e).
10. **Clustered lines (Astra 10):** the confirmation unit is one independent passage (one
    seeded line per passage). The power floor is recomputed for that unit and for Holm's first
    threshold: 250 passages, not 150 lines (§4e).
11. **Removal only from BBAW and Ramses (Astra 11):** source-specific predicates and an
    assertion that the removed set R contains no other source (§1.2 rule 4, §1.3).
12. **Small corrections (Opus 8, 10, 11, 13):** the gate-code note re-reads at the 1.0 commit;
    the floors that part 2 may touch are named; the paste gate cites A2.2′ as amended by A7;
    the tagged-host SSH precheck; row 0 of the order table is marked done.

## Rev. 5 changes (answering the Opus and Astra reviews of rev. 4; 2026-10-28)

Both reviews were of rev. 4 (`5fcc4f8`, main `51f3757`). Nothing was run, no server was
contacted, and no code was changed to write this revision. "O" = Opus finding, "A" = Astra
finding, numbered in the order of the review.

1. **Rollback (O1, A2; blockers):** new **§1.9a restore procedure** (triggers, service stop,
   SQLite sidecars, restore of the exact snapshot-2 `.db.gz` after a checksum, integrity and
   annotation checks, code rollback by reverting the merge, saving stays paused until the
   restored state passes). §3.4 adds the backup and rollback sequence for part 3.
2. **Config backups (O2, A2; blockers):** §1.7 step 1a: server-local mode-600 copies of every
   file before it is edited, outside the clone, never read by an agent. The restore in §1.9
   step 5 copies them back and checks them.
3. **Live DB binding and dotenv (A1; blocker):** `app/core/config.py` runs `load_dotenv()`, so a
   `.env` file can supply `DATABASE_URL` after systemd and `/proc` look clean. B1 now checks
   every `.env` on the path, and requires the running app's own startup announcement
   (`database: <path> (from default next to the code)`) in the journal. The refresh block no
   longer sources `egyptology.env` (O3).
4. **NC data is Ledio-gated (A3; blocker):** a Ground rule and the §2.1a, §4.0 steps. One
   recorded approval per pre-registered use, naming operator, files and destinations.
5. **Historical exposure (A4; blocker):** a KRI line is confirmation-eligible only if it is
   `new` against G **and** against the historical corpora: O, the DB-only rows H, and the
   removed rows R (§4.0 (b)3, §4a).
6. **G is fixed at the gate-fixture draw (O4):** the circular definition is removed (§4.0 (c),
   §4a, order table). The Case 1 freeze starts at the draw and is time-bounded.
7. **Decoder (A5, A6, O5):** an identity contract through the split manifest and a new
   training manifest (§2.0a, §2.3), D0b (fixed-heldout path equals the default path on O),
   gross loss everywhere and exact integer budgets with a frozen denominator (D1-D3).
8. **Worktree check (A7):** clean for O; exactly one modified file for M and N (§2.1a).
9. **Small (O6, O7):** the allowed merge forms (§1.9 step 0); a stop criterion for the T3
   review (§1.1a).

**Not taken as written, with reasons.**

* *Opus 2, "record each copy's sha256 in `pause_inventory.txt`":* the file is the Mac-side
  record, and a bare hash of a file that holds a short passphrase (Ledio keeps the short key
  knowingly) is a guessing oracle. The hashes stay in a server-local `SHA256SUMS`; only
  `verified: yes/no` is reported back.
* *Astra 3, "a Ledio gate before every NC-data read":* every read would make the six Urk. IV
  gate runs and the paste runs ask six times for something Ledio already approved when he
  approved the pre-registration. The gate is the recorded approval of a named use (operator,
  files, destinations), plus a per-session approval for the KRI custody directory.
* *Astra 4, "a hashed historical exclusion corpus":* a second, standing corpus file would be a
  new artefact to keep consistent. O is recoverable from git at the recorded commit, H comes
  from snapshot 1, and R is in the removal manifest. They are screened as extra invocations of
  the unchanged checker, which gives the same protection without a new file format.
* *Astra 5, "the two planned flags do not supply the mapping":* correct for the harness
  outputs, but `--split-manifest` already exists and carries the composite key in the order
  that `row_id` indexes. The contract uses it and adds only a training manifest (§2.3).

## Revision log

| Date | Rev. | Entry |
|---|---|---|
| 2026-10-26 | 1–3 | Outline, then two Codex gpt-6-astra reviews; change lists above. |
| 2026-10-28 | 4 | Answers the Astra review (verdict `not_ready`, 11 findings) and the Opus review (`ready_after_small_fixes`, 13 findings) of rev. 3. Map below. Draft only: no code, no data. Committed as `5fcc4f8`. |
| **2026-10-28** | **5** | Answers the Opus review (`fix_first`: 2 blockers, 2 should-fix, 3 nits) and the Astra review (`fix_first`: 4 blockers, 3 should-fix) of rev. 4. Map below the rev. 4 map. Draft only: no code, no data, no server. |

**Rev. 4 blocker map (2026-10-28).** "A" = Astra finding (its order in the journal), "O" = Opus
finding (its order). Severity as the reviewer gave it.

| # | Finding | Severity | Fixed in |
|---|---|---|---|
| A1 | Start condition names only the audit merge; kri-fixes must be merged first | blocker | Ground rules; §1.0; order table rows 0, 0b |
| A2 | `--examples` does not exist on the Urk. IV gate; A7 modes unspecified | blocker | §2.1, §2.1a |
| A3 | Decoder / segmentation not covered by the run set | blocker | §2.3, §3.3, order table |
| A4 | Backup / refresh not bound to the live DB; `.db.gz` is not a database | blocker | §1.0a, §1.0b, §1.7 step 2, §1.9 |
| A5 | `daemon-reload`; deploy can reintroduce settings; checks before the refresh | should-fix | §1.7 steps 1.2-1.3 and 5, §1.9 steps 1 and 5, Ground rules |
| A6 | Target-removal rule contradicts the twin invariant; floor denominator | blocker | §2.2 (with §2.4, §2.5) |
| A7 | 4 h estimate; `verify_release.py` after deploy | should-fix | §2.6, §1.8, §1.7, order table |
| A8 | B-freq described as future; PDFs' G status implicit | should-fix | §4.0, §4e |
| A9 | Manifest does not include the self-test; not a dependency of PT admission | blocker | §4.0, §4d, §3 rule 6, §4e |
| A10 | Passage clustering ignored; 150-line floor wrong for Holm | blocker | §4e |
| A11 | Removal not restricted to BBAW / Ramses | should-fix | §1.2 rule 4, §1.3, §1.2 tests |
| O1 | §4 has two incompatible orderings; G undefined | blocker | §4.0, §4a |
| O2 | The kri-official-prep checker is the §4a checker; dev fixture rules | blocker | §4a Timing |
| O3 | Self-test lines already seen; replace 4c | blocker | §4.0, §4c, §4d |
| O4 | Start condition: kri-fixes merged and deployed | should-fix | Ground rules; §1.0 |
| O5 | 15.5 h per run, serialization | should-fix | §2.6, Ground rules |
| O6 | Manual `import_examples.py` has no environment | should-fix | §1.0a, §1.9 steps 2 and 3 |
| O7 | `INSTALL_UNITS=1` during the pause | should-fix | §1.9 step 1, Ground rules |
| O8 | Stale "taken from the audit branch" note | nit | §1.7 preamble, §1.0 |
| O9 | `expected_corpus_sha256` exists; two floor blocks | nit | §1.8, §2.2 |
| O10 | Paste gate wording predates A2.2′ / A7 | nit | §2.5 |
| O11 | Tagged tailnet host; SSH path | nit | §1.0 precheck |
| O12 | Part 3 rule 6 needs the manifest path and sha | nit | §3 rule 6 |
| O13 | Order table row 0 already done | nit | order table |

**Rev. 5 blocker map (2026-10-28).** "O" and "A" as above, numbered by the order of the review
of rev. 4.

| # | Finding | Severity | Fixed in |
|---|---|---|---|
| O1 | No rollback for the live refresh and deploy | blocker | §1.9a (new), §1.7 step 2, §1.9 step 3 |
| O2 | Pause edits remove secrets with no backup of the files | blocker | §1.7 step 1a, §1.9 step 5 |
| O3 | `. egyptology.env` sourced in the refresh block | should-fix | §1.9 step 2 |
| O4 | G is defined by a declaration that depends on the gate on G | should-fix | §4.0 (c), §4a, order table |
| O5 | O not run with `--fixed-heldout`; harness bug looks like corpus dependency | nit | §2.3 (D0b) |
| O6 | Fast-forward merge may be impossible; allowed forms unstated | nit | §1.9 step 0, §1.0 |
| O7 | The T3 20-example read has no pass or stop criterion | nit | §1.1a |
| A1 | Live DB binding ignores `load_dotenv()`; counts do not prove the app's DB | blocker | §1.0a B1 |
| A2 | Rollback incomplete: config backups, sidecars, part 3 sequence | blocker | §1.9a, §1.7 step 1a, §3.4 |
| A3 | NC data access not gated on Ledio | blocker | Ground rules, §2.1a, §4.0 |
| A4 | Historical exposure (removed and DB-only rows) not screened | blocker | §1.0b, §4.0 (b)3-4, §4a |
| A5 | Decoder pairing has no executable identity contract | should-fix | §2.0a, §2.3 |
| A6 | D1/D2 net loss contradicts "gains never offset"; D3 denominator | should-fix | §2.3 |
| A7 | The §2.1a worktree check cannot pass for O | should-fix | §2.1a step 1 |

## Ground rules (all parts)

* **Start condition (rev. 4).** Main must contain the `kri-fixes-2026-10-26` merge (main
  `51f3757` or a descendant), its results note
  `docs/kri-fixes-results-2026-10-27-attempt5.md` must be committed on main, and that main must
  be pushed **and deployed** (Ledio confirms the deploy; the live app then runs the merged
  decoder). A kri-fixes change landing after the cleanup branch is cut would be a mid-run code
  change and ends the run (A2.9 of the 2026-10-25 pre-registration). Historical measurements
  stay what they were: attempt 2 of the 2026-10-25 re-measurement
  (`docs/remeasure-results-2026-10-26-attempt2.md`) and attempt 5 of the kri-fixes series are
  references, never relabelled as post-cleanup results. The rules in force are A7 (the St
  Andrews rank is reported, not gated) and the twin-controlled floors 0.80 / 0.70 already in
  `data/benchmarks/release_baseline.json`.
* **One new branch** `data-cleanup-2026-10-26` cut from that main (§1.0), worktree
  `.claude/worktrees/data-cleanup-2026-10-26`. Pair style: worker → independent verifier
  (Opus + Astra) → lead re-runs the gates, one heavy process at a time. This plan lives on
  `plan-cleanup-2026-10-28`; it is not on the cleanup branch.
* **Heavy runs are serialized across every worktree.** The Mac is shared with the KRI
  official-test tooling, Experiment 3 and any later measurement. At most one heavy process
  (a competitive run, the paired harness, the Urk. IV gate, routing, `verify_release.py`, the
  full suite) runs at a time, whichever worktree it belongs to. Before each one the lead
  records in `$R/queue.txt` what else is running (`ps`) and the start time. A run that was
  interrupted (sleep, signal) is not resumed: it counts as failed and is redone in full, under
  the rules of the 1.7 step 4 amendment. Launches use the pattern of
  `scripts/run_kri_fixes_prereg.sh` (`caffeinate`, no ignored HUP/INT/TERM; its `step0-signals`
  check), because attempt 3 of the kri-fixes series failed for that reason.
* Run outputs go to `$R = ~/egyptology-runs/data-cleanup-2026-10-26/` (outside the repo and
  iCloud; Desktop/Documents are iCloud-synced on this Mac).
* **Measurement worktrees.** Evaluations that cannot take a corpus argument are run from a
  throwaway, detached worktree at the pinned code commit whose `data/processed/examples.csv`
  is replaced by the corpus under test (§2.1a). They live under `$R/meas/`, never under the
  repo, are never committed from, and are removed after the run.
* **Server work is Ledio's.** No agent runs `ssh`, `scp` or any server command. Every server
  step in this plan is a command or check that Ledio runs himself and reports back, names and
  counts only, never secret values. The server is now a tagged tailnet device, so its SSH and
  `systemctl --user` / `journalctl --user` access may differ from the earlier user-owned
  device. §1.0 has a precheck.
* **No `INSTALL_UNITS=1` in this pass.** The cleanup deploy runs `~/egyptology-deploy.sh`
  without it (its default is 0). The repo unit files equal the installed ones since
  2026-10-26 (`deploy/systemd/egyptology.service`, header), and four wanted settings are still
  *not* installed (OnFailure, `STREAMLIT_SERVER_FILE_WATCHER_TYPE=none`, `MemoryMax=6G`, the
  backup unit's `EnvironmentFile=`). Installing them is its own deploy, before §1.0 or after
  §1.9, never inside the pause window: it restarts the service, and changed `Environment=`
  lines would make the §1.7 pause inventory describe a process that is no longer running.
* `data/processed/examples.csv` is **never written by an importer** in this plan. Importers
  write donor files to `$R` only. One new merge script builds *candidate* CSVs, and a
  human-reviewed diff report plus the part 2 measurement come before any of them replaces the
  file.
* **Measure before deploy.** Order: inventory (1.1a) → candidates → report → review → part 2
  pre-registration → part 2 measurement on the candidates → **commit on the branch and local
  release gate (1.8)** → saving pause and snapshot 2 (1.7) → merge, push, deploy (1.9).
  Nothing is deployed on an unmeasured corpus, and no expensive check runs inside the pause
  window.
* Ask Ledio before replacing `examples.csv`, pushing, deploying, running any server command
  that writes, sending any email, or touching `REVIEWER_KEY`. Egyptological questions go to
  the experts, never to Ledio. Current behaviour stays until they answer.
* KRI material never enters the repo, the public corpus, the server, `data/private/` or any
  synced folder. St Andrews rows never enter the repo or the public corpus. On the server
  they exist only as the allowlisted file of §4b.
* **NC-data gate (rev. 5).** Any use of non-commercial data (the St Andrews file in
  `data/private/`, anything under `~/egyptology-private-kri/`) needs **Ledio's recorded
  approval of that named use** before the first access. The approval names the **operator**
  (the lead; workers, adjudicators and reviewers are never given the paths), the **files** (by
  name and sha256), the **purpose** and the **destinations** (`$R` only for logs; aggregates
  only in anything that is committed; nothing leaves the Mac). For the St Andrews rows, one
  approval per pre-registered use is enough, and it is the approval of that pre-registration:
  part 2 lists its six Urk. IV gate invocations and the paste runs with private rows (§2.1a),
  and the §1.8 local gate and the part 3 re-measure each list theirs. A use not on the list
  needs a new approval first. For the KRI directory the approval is **per session**, recorded as
  one line (date, purpose, files) in `~/egyptology-private-kri/access.log`, which is itself
  private. An agent that finds a step needing NC data with no recorded approval stops and
  asks; it never "just reads once".

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

**1.0 Preconditions (rev. 4).** All of these hold before anything below runs, and are recorded
in `$R/env.txt`:

1. **Main.** `git rev-parse main` = `51f3757` or a descendant that contains it; tree clean;
   the kri-fixes results note is committed; the push and the deploy are done (Ledio confirms;
   the deploy log shows the merged commit). Record the main sha, and cut
   `data-cleanup-2026-10-26` from it **only after** that. A later change to main's code
   (including another kri-fixes commit) before 1.8 ends the run. **What counts as a code
   change (rev. 5):** `git diff <the 1.0 sha> main -- app scripts tests requirements*.txt
   deploy data/benchmarks` is non-empty. Docs-only commits on main (this plan, the
   Experiment 3 notes, results notes) do not end the run; they only mean the branch may be
   merged by a merge commit or rebased (§1.9 step 0), never fast-forwarded blindly. The diff
   is re-run and recorded at 1.8 and again at 1.9 step 0.
2. **Corpus O.** `shasum -a 256 data/processed/examples.csv` (this file is **O**; expected
   `44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2`, the sha in
   `release_baseline.json` and in attempt 5; a different sha stops), row count 130,472.
3. **Floors in force.** Copy `data/benchmarks/release_baseline.json` into `$R/` and record its
   sha256. It carries two floor blocks: the top-level legacy block (0.90 / 0.7917, 2026-09-05)
   and `twin_controlled` (0.80 / 0.70, 2026-10-26). `verify_release.py` gates on the second;
   the first is printed, non-gating.
4. **Code that matters, by hash.** sha256 of `scripts/eval_guards.py`,
   `scripts/run_reading_model_eval.py`, `scripts/run_kri_fixes_eval.py`,
   `scripts/check_standrews_urkiv_gate.py`, `scripts/verify_release.py`, and of the source text
   of `configured_setting` and `annotations_unlocked` in `app/ui/whyptology_app.py`
   (re-read at this commit, which is post-kri-fixes; the gate code is on main and kri-fixes
   touched only the UI evidence, not the gate).
5. **Environment.** Python version and `pip freeze`; the venv is `~/venvs/egyptology`
   (Python 3.12).
6. **Server SSH precheck (Ledio; no agent ssh).** The server is now a tagged tailnet device,
   which can change Tailscale SSH and ACL behaviour. Before snapshot 1, Ledio confirms from
   his own machine that `ssh ledio@vela-optiplex-3070` works and that, on the box,
   `systemctl --user status egyptology` and `journalctl --user -u egyptology -n 5` work. If
   either fails, 1.0b waits, and so does everything that needs P (the candidates). The donor
   files (1.1) and the inventory without the P intersection do not need the server.
7. **Nothing else is writing the Mac.** The heavy-run queue (Ground rules) is empty or
   ordered. The `exp3-2026-10-26` branch and its worktrees are not touched by anything here.

Raw inputs must be present in the main checkout's `data/raw/` and are hashed into
`$R/raw_sha256.txt`:

* `tla_earlier/tla_earlier.parquet`, `tla_late/tla_late.parquet`,
  `tla_demotic/tla_demotic.parquet`. Content checksums are verified by
  `python scripts/download_all_sources.py` without `--force`; a mismatch stops.
* `bbaw_egyptian/train.parquet`.
* `aes/files/relANNIS/`.
* The Ramses raw dir.
* The tracked TLA worklist `data/raw/real_examples_worklist.csv`.

**1.0a Live database binding and snapshot protocol (rev. 4; used by 1.0b, 1.7 and 1.9).**
Rev. 3 said "run `scripts/backup_db.sh`, copy the newest backup to `snapshot1.db`" and ran the
refresh without saying which database it touched. Both were unsafe: `backup_db.sh` and
`import_examples.py` fall back to a database *next to the checkout they run in* when
`DATABASE_URL` is unset (`app/core/config.py`: `sqlite:///egyptology.db`, anchored at the
project root), `import_examples.py` calls `create_tables()` even in `--dry-run` (a wrong path
would silently create and "pass" on an empty database), and the backups are published as
`egyptology-<date>[-rNN].db.gz`, which is not a SQLite file. Everything below is therefore
bound to one absolute path.

* **`LIVE_DB` = `/home/ledio/egyptology/egyptology.db`.** The live app and the backup unit use
  it today with no `DATABASE_URL` (the unit sets `WorkingDirectory=/home/ledio/egyptology`,
  the config anchors the default at the clone, and the installed backup unit does not read
  `egyptology.env`). That is a **claim to verify, not to assume**, on every use (step B1).
* **`BACKUPS` = `/home/ledio/egyptology-backups`** (the backup script's default; gzip'd
  snapshots, a `monthly/` folder, hidden `.candidate-*` files that are never published).
* **`R_DB` = `$R/db/`** on the Mac: outside the repo, outside iCloud, never under Desktop or
  Documents.

Steps (Ledio runs B1-B3 on the server and reports; the lead runs B4-B6 on the Mac):

* **B1. Prove the binding (names only).** (a) `DATABASE_URL` is absent from all four places:
  `/home/ledio/egyptology.env`, `systemctl --user cat egyptology` (unit and drop-ins), the
  running process (`tr '\0' '\n' < /proc/$PID/environ | cut -d= -f1 | grep -cx DATABASE_URL`,
  PID from `systemctl --user show egyptology -p MainPID`), and the backup unit
  (`systemctl --user cat egyptology-backup`). Counts only; if any is non-zero, stop and
  re-derive the live path, do not proceed on the assumption. (b) `LIVE_DB` exists and is
  non-empty (`test -s`), and `sqlite3 -readonly "$LIVE_DB" 'SELECT COUNT(*) FROM examples;
  SELECT COUNT(*), MAX(id) FROM annotations;'` returns the live example count and annotation
  `COUNT, MAX(id)`. The three numbers are recorded in `$R/db/live_probe_<step>.txt`.
  (c) **dotenv (rev. 5).** `app/core/config.py` calls `load_dotenv()` before it reads
  `DATABASE_URL`. `python-dotenv`'s `find_dotenv` walks **up** from the directory of the file
  that called it, and `load_dotenv` does not override a variable that is already set. So a
  `.env` file can supply `DATABASE_URL` to the running app while systemd's environment and
  `/proc/<pid>/environ` (which show only what the process started with) stay clean. For each
  of `/home/ledio/egyptology/app/core`, `/home/ledio/egyptology/app`,
  `/home/ledio/egyptology`, `/home/ledio` and `/home`, Ledio reports whether a `.env` exists
  and `grep -cE '^\s*(export\s+)?DATABASE_URL\s*=' <dir>/.env` (a count only, never a
  value). Any non-zero count stops the run: the live path is re-derived from that file.
  (d) **The running app's own announcement.** `config.py` prints one line to stderr at import,
  `database: <path> (from <origin>)`, and `origin` is `DATABASE_URL` whenever the variable was
  set **after** dotenv ran, whatever supplied it. The expected line for the live app is
  `database: /home/ledio/egyptology/egyptology.db (from default next to the code)`. Ledio runs
  `journalctl --user -u egyptology --since <the service's last start> | grep -c '^database:'`
  and sends the matching line; it must be exactly that, once per process start. The words
  `from DATABASE_URL` mean something does supply a URL (dotenv, a drop-in, a secrets file): stop.
  The line only exists after a restart, so for the first use B1 is read after the
  service's most recent start, and a service that has not restarted since the journal rolled
  over is restarted once by Ledio (before the pause, saving still open) to produce it.
  (e) **The open file, where available.** `readlink /proc/$PID/fd/* | grep -c egyptology.db`
  and, if non-zero, that every such link is `LIVE_DB` (a SQLite connection may be closed
  between requests, so no open handle is not a failure; the announcement in (d) is the
  primary evidence and (e) can only add a contradiction). Counts taken from `LIVE_DB` prove
  nothing about the app until (c) and (d) agree.
* **B2. Take the backup with explicit paths.** `/home/ledio/bin/backup_db.sh "$LIVE_DB"
  "$BACKUPS"` (the installed helper that the timer runs, called with both paths so no default
  or environment can redirect it). Required: exit 0; its first output line is
  `backup: database /home/ledio/egyptology/egyptology.db` (string-equal to `LIVE_DB`). The
  newly published file is the one that appears in `ls -1 "$BACKUPS"` after but not before the
  run, matching `egyptology-YYYY-MM-DD(-rNN)?.db.gz`. Any exit 2-5, a `.suspect`,
  `.unverified` or `.corrupt` file, or no new file means **no backup**: stop. An older
  backup is never silently used instead; Ledio decides.
* **B3. Select exactly one file and record it.** Ledio sends the exact file name and runs
  `sha256sum` on it; both go to `$R/db/snapshotN_source.txt`. He copies that single `.gz` to
  `$R_DB` (one file, not a directory or `rsync` of the folder). For snapshot 2 he **also
  keeps a second server-side copy** of that exact `.gz` in the `pause-backup-<date>`
  directory of §1.7 step 1a, because the backup timer's pruning is not under this plan's
  control and §1.9a restores from that file.
* **B4. Verify the copy.** On the Mac: `shasum -a 256` equals the server's; `gzip -t` exits 0.
* **B5. Decompress outside the repo, read-only.** `gunzip -c <file>.db.gz > $R_DB/snapshotN.db`
  (the `.gz` is kept; nothing is decompressed in place or inside any checkout), then
  `chmod 444`. Record `shasum -a 256 snapshotN.db`.
* **B6. Integrity and content checks before first use.** All with `sqlite3 -readonly`:
  `PRAGMA integrity_check;` returns exactly one row, `ok`; `PRAGMA quick_check;` is `ok`;
  `PRAGMA foreign_key_check;` is empty; the tables `examples` and `annotations` exist;
  `SELECT COUNT(*) FROM examples` is at least 130,472 (O) and equals O ∪ H after 1.0b
  reconciliation; `SELECT COUNT(*), MAX(id) FROM annotations` is recorded. **Equality rule:**
  for snapshot 2 (taken with saving paused) the annotation `COUNT, MAX(id)` must equal
  `A_pause` read live in B1; for snapshot 1 (saving open) the live count read at the same
  moment must be at least the snapshot's, and both are recorded. A failure of any check
  stops the run and the file is not used.
* **Every script that opens a snapshot opens it read-only.** `check_annotation_keys.py` takes
  `--db-url` and opens the SQLite file through a `file:<abs path>?mode=ro` URI, never through
  `app.core.config` or `create_tables()`, refuses a path that does not exist, and prints the
  absolute path it opened. `migrate_example_ids.py` (which uses `DATABASE_URL`) is run only
  with `DATABASE_URL=sqlite:////<absolute path of the 444 snapshot>` (four slashes: the
  absolute path starts with one) and without `--yes`; its `database:` line is compared with
  the path.

**1.0b DB reconciliation and protected set P (read-only, on a verified copy of the production DB).**
With Ledio: take and verify snapshot 1 by the protocol of 1.0a (B1-B6), giving
`$R/db/snapshot1.db`. A new read-only script,
`scripts/check_annotation_keys.py --db-url … --csv … --out-dir …`, writes:

1. **Reconciliation of DB vs O** by composite key `(source, source_text_id,
   source_sentence_id)`:
   * `H` = DB keys absent from O (historical extra rows from earlier corpora);
   * `O∖DB` = CSV keys absent from the DB. Expected 0: deploys insert them. Non-zero
     stops the run.
   * DB keys present in O whose `hieroglyphs` or `transliteration_gold` differ from O.
     Listed; non-zero stops the run.

   H is recorded with counts per source and kept apart from everything later. It is
   *not* this pass's removal set and is never deleted here. The text of the H rows is also
   written, read-only, to `$R/db/H_rows.csv` (the columns of `examples.csv`, one row per H
   key) with its sha256: it is one of the historical corpora that §4.0 (b)3 and §4a screen KRI
   lines against, because those rows once belonged to the public corpus and are in no commit
   that this pass will keep.
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
  Astra before continuing. The question each answers is "is the old row correctly paired with
  this donor occurrence?", from the row pair alone, without the assignment tier. **Pass:** both
  say yes for all 20. **Any wrong assignment, from either reviewer, stops the run** and the case
  goes to Ledio, like the other stop classes; no sample is redrawn to get a clean one, and the
  rule for T3 for that source is not widened by anything short of his decision.
* If `benchmark targets ∩ (flagged ∖ P)` is above 5 for any one query set, stop and ask
  Ledio. At 5 or fewer, §2.2 applies.

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
4. **Removal (mode N only), source-specific (rev. 4).** Removal is allowed **only** for
   BBAW and Ramses rows. It happens when the old row's source-specific predicate flags the
   transliteration **and** the key is not in P **and** it is not on the BBAW `_` exception
   list (1.4). The predicates are the importers' own, imported, not copied:
   * **BBAW:** `TRANSLIT_LACUNA_RE` (brackets, `//`) plus the `_` rule of 1.4;
   * **Ramses:** `TRANSLIT_LACUNA_RE` plus the Ramses word rules;
   * **TLA (Earlier, Late, Demotic):** none. TLA has a metadata-only scope in the audit
     table above, so a TLA row is never removed, whatever its transliteration looks like;
   * **AES:** none (the 22 `_` rows wait for Camilla, see "Stays deferred");
   * **any other source** (St Andrews is not in the public file; UD is not in O): none.

   Assertions, checked by the script and again by a test on the committed file (1.8):
   * `sources(R) ⊆ {BBAW, Ramses}`; for every other source `|R| = 0`. A removal candidate in
     any other source stops the run, it is never removed "because the predicate fired";
   * every BBAW/Ramses row that is flagged, not in P and not an exception is removed;
   * every removed row is flagged by its own source's predicate and in neither set;
   * the flagged BBAW/Ramses rows that remain are exactly (flagged ∩ P) ∪ (flagged ∩
     exceptions), each listed with its reason.
5. **Nothing is added.** Donor occurrences unused by O are counted by reason (internal
   duplicate, cross-source dedup at original import, etc.) and listed, not added.
6. **Mode M** (metadata-only control): start from O; apply the allowed updates for rows that
   have an assigned donor, plus the rule of 3a (Ramses `period = unknown` on every Ramses
   row); leave every other column of a donorless row unchanged, *including* flagged rows
   without a donor; remove nothing. M therefore differs from O only in allowed columns.

Tests use synthetic fixtures only:

* an unchanged row stays byte-identical;
* a disallowed column change blocks;
* a flagged BBAW or Ramses row is removed, but a flagged row in P is kept;
* a row that matches the lacuna predicate but belongs to TLA, AES or any other source is
  **kept**, and a candidate removal from such a source stops the run;
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
| sources(R) | ⊆ {BBAW, Ramses}; every other source 0 removed (rule 4) |
| R ∩ benchmark targets (= Q_R) | equal to the 1.1a count; each listed, handled per §2.2 |
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
# $R is already expanded and absolute, so the URL has four slashes; the snapshot is the 444
# copy verified in 1.0a. The script's `database:` line must show this exact path.
DATABASE_URL=sqlite:///$R/db/snapshot1.db $PY scripts/migrate_example_ids.py --new-csv $R/candidate_N.csv
```
(`sqlite:///` + an absolute `$R` = `sqlite:////Users/…`; run without `--yes`.)

Expected:
* `to rename 0`, `ambiguous 0`, `collisions 0`, `csv_duplicates 0`;
* `unmatched` = **H ∪ R exactly**, with H ∩ R = ∅ and H equal to the 1.0b set. The script
  then refuses `--yes`, which is correct: nothing is renamed.

`check_annotation_keys.py` on the candidate must show:
* every chain from 1.0b still `ok` against N (key present, text unchanged);
* **0 annotations on R**.

**1.6 Part 2 runs here** (pre-registration, then measurement on O, M, N, with the decoder and
Urk. IV gate additions of part 2). A failed part 2 stop rule ends part 1 at this point:
nothing is committed or deployed.

**Order of execution (rev. 4).** Rev. 3 put the saving pause *before* the commit and the
suite, which left the expensive checks inside the window and discovered release failures
only after the server steps had started. The order is now:

1. 1.0 → 1.0b → 1.1 → 1.1a → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 (all measuring done);
2. **1.8** commit on the branch, **local** release gate (full suite, paste, full
   `verify_release.py`): all expensive checks, no server involvement, saving still open;
3. **1.7** pause, snapshot 2, P2 check (this is the only part that needs the saving
   window, and it needs no long computation unless N must be rebuilt);
4. **1.9** merge and push (Ledio), deploy, refresh, live check, restore.

The numbering is kept so that the references elsewhere hold; the order above is the order
of work. Nothing is merged to main or pushed before step 3 clears.

**1.7 Production re-check with saving paused (after the local gate of 1.8, immediately before
the merge, push and deploy).** With Ledio, on the server:

**How the gate reads its settings (re-read at the 1.0 commit, which is post-kri-fixes; the
sha256 of the two functions' source is recorded in `$R/env.txt`, and a difference from what is
quoted here stops the run).** `configured_setting(secret_name, env_name)` in
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
   1a. **Back up every file first (rev. 5; before any edit).** The inventory records names, so
      a lost line, its quoting or a whole drop-in could not be put back exactly. For each file
      the inventory found (the env file, the installed unit and each drop-in under
      `~/.config/systemd/user/`, both secrets files, and any `config.toml` that lists
      `secrets.files`) Ledio makes a **server-local** copy:
      `install -d -m 700 /home/ledio/pause-backup-<date>` once, then
      `cp -p <file> /home/ledio/pause-backup-<date>/<flat name>` and `chmod 600` on each copy
      (the flat name is a fixed label such as `env`, `unit`, `dropin-<name>`, `secrets-clone`,
      `secrets-home`). The directory is **outside the clone and outside any synced folder**, the
      copies are never copied to the Mac, never put in `$R`, and never read, printed or `cat`ed
      by an agent or in anything an agent sees. The sha256 of each copy goes into
      `/home/ledio/pause-backup-<date>/SHA256SUMS` **on the server only**. What comes back to
      `$R/pause_inventory.txt` is the file list (labels and original locations) and
      `copies made: yes`, never a hash: a bare hash of a file that holds a short passphrase would
      let anyone with the hash test guesses offline. `sha256sum -c SHA256SUMS` is run once
      before the first edit and must report all `OK`. **No file is edited until that check
      passes.**
   2. **Remove.** Ledio removes the key from **every** place it was found. He also removes or
      empties any `allow_open_annotations`/`ALLOW_OPEN_ANNOTATIONS`. If any edit was to the
      unit file or a drop-in (as opposed to `egyptology.env` or a secrets file), he runs
      `systemctl --user daemon-reload` **before** the restart: a restart alone can keep
      systemd's previously loaded configuration, which would leave the setting in force
      while the file no longer shows it. Then he restarts the service
      (`systemctl --user restart egyptology`).
   3. **Verify the sources** (static): `systemctl --user show egyptology -p NeedDaemonReload`
      prints `NeedDaemonReload=no`; a re-run of the inventory shows 0 occurrences of all
      four names in all places. `/proc/<MainPID>/environ` of the restarted process (PID
      from `systemctl --user show egyptology -p MainPID`) has neither `REVIEWER_KEY` nor
      `ALLOW_OPEN_ANNOTATIONS`. The inventory is of the **installed** unit
      (`systemctl --user cat egyptology`), which is the only one the process obeys; the repo
      unit is not evidence.
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
2. Snapshot 2 by the protocol of 1.0a (B1-B6, explicit `LIVE_DB` and `BACKUPS` paths, the
   exact published `.db.gz`, decompress outside the repo, integrity-check) →
   `$R/db/snapshot2.db`. Its annotation `COUNT(*), MAX(id)` must equal `A_pause` (B6
   equality rule). Snapshot 2 is also the restore point if anything after it goes wrong, and
   **§1.9a is the written procedure for using it**: what triggers it, how the DB and the code are
   put back, and when saving may be switched on again. Each pause takes its own dated
   `pause-backup-<date>` directory (step 1a); a repeated pause (step 4.5) does not reuse an
   older one.
3. Re-run 1.0b and 1.5 on snapshot2 → `P2`, `H2`.
   * If `P2 ∖ P` does not intersect R, the measured N stands unchanged (same sha256 as part
     2), and we go to step 5.
   * If `P2 ∖ P` intersects R (a removal candidate was annotated since snapshot1), the
     measured N is **not** shipped. Go to step 4.
4. **Rebuilt N = a new measurement (no shortcut).** Any rebuild of N, for whatever reason, is
   handled as follows:
   1. **Restore saving** (as 1.9 step 5, including the `daemon-reload` after any unit or
      drop-in edit) for the duration. "The window must not stay open overnight" is about
      the **pause**; the re-measure itself is long (§2.6: about 46 h of wall time for the
      full set) and normally runs with saving **open**.
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
   5. Redo §1.8 (commit and local gate on N′), then start §1.7 again from step 1 (pause,
      verify, snapshot3, P3), with P ∪ P2 as the new P. Because the re-measure takes days
      and annotators keep writing, **a second rebuild is likely**, not exceptional. If P3
      ∖ (P ∪ P2) intersects R again, stop and decide with Ledio, for example a pause kept
      open across the re-measure by agreement with the reviewers, announced in advance.
5. Only then go on to the merge, push and 1.9, with saving still paused. The key is restored
   at the end of 1.9, after the live re-check, from the pre-pause copies of step 1a. Before the
   restore, the live annotation `COUNT(*), MAX(id)` must still equal `A_pause`; any difference
   means a write got through and stops the run. If anything in 1.9 trips a trigger of §1.9a,
   that section is followed instead, and the key stays out until it says otherwise.

**1.8 Commit and local release gate (executed BEFORE 1.7; Ledio approves the commit).** One
commit on `data-cleanup-2026-10-26`, **local only**: not merged, not pushed. It contains:

* `examples.csv` = the measured N, or N′ after an amendment (sha256 equal to the last
  complete part 2 run set);
* `data/benchmarks/release_baseline.json`: **`expected_corpus_rows` and
  `expected_corpus_sha256` are updated** (the sha key already exists since rule 8 of (A); it
  is an update, not an addition) and the `recorded_*` notes say why. **No floor value in
  either block moves in this commit:** neither the top-level legacy block (0.90 / 0.7917,
  non-gating) nor `twin_controlled` (0.80 / 0.70, the gating block). A floor is never relaxed
  to fit N; if N cannot meet it, part 2 has already stopped (§2.2, §2.5). A *rise* of a floor
  after a gain would be a separate, later commit with its own measurement;
* the removal manifest;
* DATA-LICENSE.md indication of changes per source (counts, date, what was removed and why,
  the kept exceptions, what is deferred);
* tests asserting the 1.3 table on the committed file, including `sources(R) ⊆ {BBAW,
  Ramses}`.

**Local release gate (all expensive checks, saving still open, no server).** Run in the
branch checkout, where `data/processed/examples.csv` *is* N, so the scripts that hard-code
that path (`verify_release.py`'s `CORPUS_PATH`, the Urk. IV gate) measure the committed file
with no worktree trick. One heavy process at a time:

1. `shasum -a 256 data/processed/examples.csv` equals the part 2 N sha256 and
   `expected_corpus_sha256`.
2. The full test suite, not skipped.
3. `scripts/verify_release.py --require-corpus-sha256` (full, with its tests). It re-runs the
   twin-controlled and legacy v4 lanes and the paste check. Its numbers must equal the part 2
   N run for the same lanes (a determinism check, as step 8 of the kri-fixes run was), the
   floors must hold, and the verdict must be READY. This is where a release failure is found:
   before the pause, not after.
4. The Urk. IV gate, both modes, in this checkout with `--private-dir` explicit (§2.1a
   command; no swap is needed here): `GATE: PASS` in `auto` and in `declared`. This is a
   **named NC use** (Ground rules): it is on the part 2 pre-registration's list, with the same
   operator, file and destination limits.
5. The 1.3 table tests on the committed file.

Any failure ends the pass here: nothing is merged, pushed, paused or deployed. The only
checks left for the pause window are cheap: the committed `examples.csv` sha256 is still the
gated one (`git diff` since the gate is empty), and the DB counts of 1.7.

**1.9 Server.** The DB never re-seeds (empty-table guard), and deploys run
`import_examples.py`, which is insert-only. Sequence with Ledio, while saving is still
paused (§1.7 has cleared with the final N):

0. **Merge and push (Ledio).** Nothing is merged or pushed before 1.7 clears: if P2 ∖ P hit
   R, N′ replaces N first and §1.8 reruns. **Allowed merge forms (rev. 5).** Main may have
   gained docs-only commits during the multi-day run (this plan, the Experiment 3 notes), so a
   fast-forward may be impossible. A **merge commit**, or a **rebase of the branch followed by
   re-hashing**, is allowed **only if** `git diff <the 1.0 sha> main -- app scripts tests
   requirements*.txt deploy data/benchmarks` is empty (the same test as §1.0 item 1). After the
   merge or rebase, `shasum -a 256 data/processed/examples.csv` on main must equal the gated
   N, and the committed test files must be byte-identical to the 1.8 gate's. If the diff is not
   empty, main's code changed mid-run: the run ends under §1.0 and nothing is pushed. A
   rebase changes commit hashes, so the 1.8 record is updated with the new commit sha and
   the unchanged file hashes, and the cheap checks of 1.8 are repeated; no heavy gate is.
1. **Deploy: `~/egyptology-deploy.sh`, run by Ledio, without `INSTALL_UNITS=1`** (the default
   is 0; the line is not typed). The installed unit files are not touched. The deploy log
   must show `inserted 0`, and may print "unit files differ … review" if the pause edited the
   installed unit; that is expected and is not acted on. A deploy that rolls back or fails
   stops the run (its own recovery notes apply, §1.7 stays paused).
   **After the deploy's restart, repeat §1.7 step 1.3 (static, names only, including
   `NeedDaemonReload=no`) and step 1.4 (the in-app caption, the Workspace message, the
   journal warning since this restart, and `COUNT(*), MAX(id)` = `A_pause`) before going
   on.** The restart is a new process; the pause inventory of §1.7 described the old one.
2. **Dry run, bound to the live database.** Ledio runs this block, once, in a subshell (the
   environment lives only inside it; nothing is echoed):

   ```bash
   (
     export PRIVATE_DATA_DIR="/home/ledio/egyptology-private"
     export ANNOTATIONS_DURABLE=1
     export DATABASE_URL="sqlite:////home/ledio/egyptology/egyptology.db"   # = LIVE_DB, B1
     cd /home/ledio/egyptology                           # import_examples.py reads its CSV by relative path
     /home/ledio/venvs/egyptology/bin/python scripts/import_examples.py --dry-run
   )
   ```

   **Rev. 5: this block does not source `egyptology.env`.** The deploy script says in so many
   words that the file is read literally by systemd and must not be run through a shell
   (`load_env_file` in `scripts/egyptology-deploy.sh`: a `REVIEWER_KEY` passphrase may hold
   spaces, `$` or `&`), and the block has no need of it: B1 proves the service has no
   `DATABASE_URL`, and the three variables above are all the script's imports use. The values
   are fixed strings, not read from the host. If a further variable is genuinely needed, it is
   loaded with the deploy script's non-executing `load_env_file` parser, never `source`, and the
   block is rewritten and reviewed first. A `.env` file in the clone cannot redirect the block,
   because `load_dotenv()` never overrides a variable that is already set (B1 (c)). The explicit
   `DATABASE_URL` is correct only because B1 proved the service has none of its own; if B1
   found one anywhere, this block is rewritten to that path first. Conditions,
   all required before step 3:
   * the `database:` line the script prints on stderr is exactly
     `database: /home/ledio/egyptology/egyptology.db (from DATABASE_URL)` (the path only;
     no credential is ever printed). Anything else stops the run;
   * `LIVE_DB` existed and was non-empty before the run (B1 `test -s`), and its inode is
     unchanged after it (`stat -c '%i'` before and after), so no second database was
     created. The dry run calls `create_tables()`, which is a no-op on the live schema and
     would otherwise create an empty file at a wrong path and report a false pass;
   * `Default sync WOULD insert=0` (the deploy already inserted; a non-zero would-insert
     means the wrong database or a deploy that did not sync: **stop**, do not refresh);
   * `--refresh-existing WOULD create=0`; `update + unchanged` equals the CSV's row count;
   * the refresh-field list is a subset of the **allowlist**: `period`, `grammar_notes`,
     `display_sequence` and the derived fields `example_payload` computes from them, i.e.
     `display_sequence_norm` (plus any other `*_norm` the 1.0 code shows is derived from an
     allowed column, written into the pre-registration). Any other field (e.g.
     `transliteration_norm` changed by normaliser drift since seeding) stops the run, to be
     decided separately.
3. **Refresh**, in the same block typed identically with `--refresh-existing` in place of
   `--dry-run`, and the same `database:` line check. Snapshot 2 (taken after the pause, before
   the deploy) is the restore point; **§1.9a is the procedure**, and its triggers apply from
   the first byte this step writes. The deploy script's own `rollback()` restores code, units
   and the venv after a failed deploy. It does **not** restore database contents, and it does
   not fire at all on a failed refresh or a failed live check after the deploy has succeeded.
4. Re-run `check_annotation_keys.py` on the live DB (read-only URI, the deployed venv, in the
   clone): chains `ok`, 0 annotations on R, H unchanged, the printed path equal to `LIVE_DB`.
5. Check the live annotation `COUNT(*), MAX(id)` = `A_pause` (§1.7 step 5). Then Ledio
   restores every file **from its pre-pause copy** (§1.7 step 1a), not from memory and not
   from the names-only inventory: `cp -p /home/ledio/pause-backup-<date>/<label> <original
   path>` for each place listed in `$R/pause_inventory.txt`, with the mode and owner the
   original had. For each, `sha256sum -c` against the server-local `SHA256SUMS` must say `OK`
   (the restored file equals the pre-pause file). If any restored place is the unit or a
   drop-in, he runs `systemctl --user daemon-reload` first and checks
   `NeedDaemonReload=no`, then restarts. The sidebar then shows the reviewer-key field
   again, and a keyed test session can unlock saving. No test annotation is written. He
   reports `restored: all OK` and `keyed unlock works: yes/no`. **The copies are kept (mode
   700) until that report is in and Ledio has used the app once with the key**; he then
   deletes the directory himself. They are never deleted by an agent and never earlier.

Removed rows stay in the DB, unreachable from the UI (`attach_db_ids` is CSV-driven). If the
FastAPI `/examples/search` is served publicly (A52), deleting the unannotated R rows (never H)
is a separate, backed-up step. Otherwise they are left.

**1.9a Restore procedure (rev. 5). Ledio runs it; no agent connects to the server.** It is
written now so that nobody decides it at 23:00. It covers the DB and the code, and saving stays
paused throughout.

*Triggers (any one):* (1) the refresh exits non-zero, or its `database:` line was not the
exact `LIVE_DB` line; (2) `check_annotation_keys.py` on the live DB is not all `ok`, reports an
annotation on R, changes H, or prints a path other than `LIVE_DB`; (3) the live annotation
`COUNT(*), MAX(id)` differs from `A_pause`; (4) the live `COUNT(*) FROM examples` differs from
snapshot 2's (the refresh updates fields and deletes and inserts nothing, so the count must be
identical, and snapshot 2's equals |O ∪ H|); (5) the post-deploy pause checks or the live app
check fail (no result card, `Read-only mode.` notice, a rolled-back deploy followed by a wrong
corpus); (6) the deploy itself failed and its own rollback ran. In case (6) the DB was not
written (the deploy inserts 0 in this pass), so only the code state is checked (step 6) and
steps 2-5 are skipped unless a DB check also fails.

*Steps:*

1. **Keep saving paused.** Nothing in this section restores the key.
2. **Stop the writers.** `systemctl --user stop egyptology`, and the backup timer too (its name
   from `systemctl --user list-timers`; it would snapshot a half-restored file).
3. **Move the failed database aside; never delete it.** For `LIVE_DB` and each of
   `LIVE_DB-wal` and `LIVE_DB-shm` that exists: `mv <file> <file>.failed-<date>`. Record the
   size and `sha256sum` of the failed file. A leftover `-wal` or `-shm` next to a restored file
   would be replayed onto it, so none may remain under the old names.
4. **Restore the exact snapshot-2 file.** The file name and sha256 are in
   `$R/db/snapshot2_source.txt`, and the file is in `BACKUPS` and in the `pause-backup-<date>`
   directory. First `sha256sum` it and require equality with the recorded value, and
   `gzip -t`. Then `gunzip -c <that .gz> > LIVE_DB`, with `chmod --reference` the failed file
   (the same mode and owner). Nothing else is used: not a newer backup, not a "latest".
5. **Check it before it serves anything**, `sqlite3 -readonly` on `LIVE_DB`: `PRAGMA
   integrity_check` = `ok`, `quick_check` = `ok`, `foreign_key_check` empty; `COUNT(*)` of
   `examples` equals snapshot 2's; annotation `COUNT(*), MAX(id)` equals `A_pause` (the B6
   equality rule; snapshot 2 was taken with saving paused, so no annotation is lost by this
   restore). A failure leaves the `.failed` file and every backup untouched and ends the
   procedure for Ledio to decide with the lead; it is never improvised.
6. **Roll the code back to match, by revert, not rewrite.** The restored DB holds the old
   `period`, `grammar_notes` and `display_sequence` values, while a deployed clone holds the new
   `examples.csv`, so serving them together is an inconsistent state. The default is therefore:
   the lead prepares `git revert -m 1 <merge sha>` on a branch from the pushed main (never in the
   main checkout, no force push), Ledio reviews and pushes it, and runs `~/egyptology-deploy.sh`
   **without** `INSTALL_UNITS`. The deploy restores the old CSV, whose sha256 must equal O's. If
   the failure came **before** the push (the merge was local), nothing is pushed and the
   server code is already the old one; the check is the sha256 only. Leaving the new code on the
   restored DB is allowed only if Ledio decides so in writing, with the reason (for example, a
   failure that touched no row); it is never the default.
7. **Re-verify, then and only then, restore saving.** After the restart: B1 (all of (a) to
   (e), so the restored state is bound to `LIVE_DB` again), the §1.7 step 1.3 and 1.4 checks
   (the pause is still in force and `NeedDaemonReload=no`), and the step 5 checks again on the
   live file. When all pass, the key and the settings are restored from the pre-pause copies
   exactly as §1.9 step 5 says, including the checksum, `daemon-reload` and the keyed-unlock
   check.
8. **After.** The cleanup is a failed pass for the purposes of the plan. The `.failed` files
   and the backups stay until the cause is understood and Ledio agrees. The results note
   records the trigger, the steps taken and the checks passed, counts and names only.
   `$R/db/restore_<date>.txt` keeps the same.

---

## Part 2 — Re-measure on the candidates, before replacement (pre-registration first)

New file `docs/remeasure-preregistration-cleanup-<date>.md`, same structure as 2026-10-25
part (A) and as `docs/kri-fixes-preregistration-2026-10-26.md`. It covers regression only: no
accuracy or independence claim, nothing quoted to experts. Release floors are **descriptive
regression tolerances**, not results.

Rev. 4 adds three things the rev. 3 run set could not do: a way to run the Urk. IV gate on a
candidate corpus (§2.1a), a defined treatment of benchmark targets that part 1 removes, with
twins and floors (§2.2), and a decoder / segmentation measurement (§2.3).

### 2.0 Frozen in the pre-registration before any run

* sha256 of O, M and N, P, H, `$R/exceptions.csv` (benign column list + BBAW `_`
  exceptions), the removal manifest and `donorless_kept.csv`;
* the amendment rule of §1.7 step 4: a rebuilt N′ gets a dated amendment, refreshed
  hashes and the complete run set (O, M, N′). There is no partial re-run;
* the **pinned code commit**: main at §1.0 plus the measurement-code commit of 2.0a, one sha
  for every run of every corpus, with the sha256 of each measured script and `pip freeze`;
* query-file sha256s (the three competitive sets, `expert_paste_queries.csv`, the known-twins
  and cross-edition files) and `release_baseline.json`'s sha256;
* the sampling seed and procedure (routing: `--seed 20261025 --per-stage 200`);
* the list of **corpus-dependent statistics** at that commit. The worker writes this list
  from the code before any run, at minimum:
  1. evidence rows / top-k pool membership;
  2. global IDF and document frequencies;
  3. reading attestation counts and suggestion frequency priors, **including the singleton
     tie counts behind the `/k` confidence discount and the stage-versus-pooled counts behind
     the pooled-fallback eligibility** (the fallback is default off since kri-fixes, but the
     counts are still corpus-dependent and the harness still measures them);
  4. segmentation/boundary-model statistics (C1 sign adjacency, quadrat hints);
  5. stage priors and routing counts;
  6. twin-guard pools;
  7. row order / tie-breaks;
  8. the twin representation of a target that is no longer in the corpus (§2.2: the fallback
     to the benchmark's `expected_key_tokens`);
  9. benchmark answerability (a query's answerability is "at least one corpus row is useful
     with the target removed", `scripts/compute_v4_answerability.py`; removing rows can
     change it);
* **Q_R**, the removed-target query ids, with their sha256 (§2.2);
* the decoder partition H_O, the arms, the identity contract and output paths of 2.0a, and
  every acceptance number of §2.3 **as the integer formulas** (D1 ⌊P/1000⌋, D2 ⌊L/500⌋, D3
  ⌊B/500⌋, with the denominators defined there), gross for D1 and D2;
* **the NC-data uses** (Ground rules): each use of the St Andrews file, named, with operator,
  file sha256 and destinations; Ledio's approval of the pre-registration is that approval;
* the loss-acceptance and stop rules of §2.5.

### 2.0a Measurement code that must exist first (written, tested, reviewed, then frozen)

Both are small, are separate commits with tests on synthetic fixtures only, are reviewed by
Opus and Astra before the pre-registration is committed, and are part of the pinned commit.
They are **not** written in this draft.

1. `scripts/run_kri_fixes_eval.py`: three new flags (§2.3): `--fixed-heldout PATH`,
   `--heldout-out PATH` (written for **every** corpus, not only O; one row per partition row
   with its exclusion reason) and `--train-manifest PATH` (the composite keys of every training
   row). Without any of them the harness's outputs must be byte-identical to today's on a
   fixture, and with `--fixed-heldout` pointing at the partition the default path itself writes,
   the outputs must be byte-identical to the default run (a fixture test; on O it is D0b).
   **Identity contract (rev. 5).** The harness's `row_id` is `source:row_index`, where
   `row_index` is the position in the **test frame**, so it shifts whenever a preceding test row
   is removed, and the position and line outputs carry no text or sentence id. Pairing across
   corpora therefore never uses `row_id` directly. Every run passes `--split-manifest`
   (it already exists: the test frame's `source`, `source_text_id`, `source_sentence_id`, in
   the order `row_index` counts, including rows the decoder skips for a length mismatch), and
   `compare_cleanup_runs.py` maps `row_id` to the composite key through line `row_index` of that
   manifest, per corpus, then pairs by key and `position`. It asserts that the manifest has all
   three key columns, that its length equals the number of distinct `row_id`s plus the skipped
   rows, and that the key set is unique. A fixture test removes one row **before** a test row
   and shows that the pairing still holds. The output paths are always passed explicitly,
   under `$R/decoder/<c>/` (`--positions`, `--lines`, `--summary`, `--calibration`,
   `--split-manifest`, `--heldout-out`, `--train-manifest`); the harness's own defaults, which
   point into the repo, are never used.
2. `scripts/compare_cleanup_runs.py`: an offline comparer that reads per-query results,
   per-position results, twin inventories and the Q_R file; matches everything by composite
   key (never by row position, because positions shift when rows are removed); produces the
   mechanism tables of §2.4 and the tables of §2.2 and §2.3. It runs no evaluation and loads
   no index.

The Urk. IV gate script is deliberately **not** changed (§2.1a).

### 2.1 Runs

Same pinned code, same evaluation code, one session, one heavy process at a time (Ground
rules): O re-run fresh (attempt 2 of the 2026-10-25 series and attempt 5 of kri-fixes are
references, never the baseline), then M, then N. Corpus files live at `$R/corpus/{O,M,N}.csv`
and are hashed before and after every run. `PY=~/venvs/egyptology/bin/python`,
`B=<pinned checkout>/data/benchmarks`, `CORPUS=$R/corpus/<c>.csv`. Every command writes under
`$R/<c>/`. The commands, with the flags each script actually has (checked against
`--help` at 1.0; a missing flag stops the run):

| Set | Command (per corpus `<c>`) |
|---|---|
| paste ×3 modes | `$PY scripts/run_expert_paste_eval.py --examples $CORPUS --queries $B/expert_paste_queries.csv --stage {none,auto,declared} --results $R/<c>/paste_<mode>.csv` |
| Urk. IV gate, both modes | §2.1a (6 invocations in all: 3 corpora × `auto`, `declared`) |
| v4 / held-out 1 / LE-v1, T-auto | `$PY scripts/run_competitive_ambiguity_eval.py --examples $CORPUS --query-path app --useful-rule v4 --benchmark <set> --stage auto --exclude-twins 0.7 --expected-tokens current --results … --failures …` |
| the same, C-auto | as T-auto with `--exclude-twins 0 --expected-tokens current` |
| the same, L-auto | as T-auto with `--exclude-twins 0 --expected-tokens frozen` |
| twin inventory | `$PY scripts/list_benchmark_twins.py --examples $CORPUS --output $R/<c>/known_twins_now.csv` (key-based diff in `compare_cleanup_runs.py`) |
| answerability, v4 | `$PY scripts/compute_v4_answerability.py --examples $CORPUS --useful-rule v4 --out $R/<c>/answerability_v4.csv` |
| routing | `$PY scripts/run_stage_routing_eval.py --examples $CORPUS --seed 20261025 --per-stage 200 --results $R/<c>/routing.csv`; the sample is redrawn because the eligible set changes, and the redraw is pre-specified |
| decoder + segmentation | §2.3 |

The set of competitive runs matches `scripts/run_kri_fixes_prereg.sh` step 7 and
`scripts/verify_release.py`'s own lanes, so the part 2 N numbers and the 1.8 local gate are the
same measurement.

### 2.1a The Urk. IV gate on a candidate corpus (rev. 4)

`scripts/check_standrews_urkiv_gate.py` has no `--examples` flag. Its parser takes `--stage
{none,auto,declared}` (default `auto`), `--rank-k` and `--private-dir`; `main()` loads the
public frame from the module constant `EXAMPLES_PATH` (the checkout's own
`data/processed/examples.csv`) through `load_corpus(private_dir)`, which would accept an
`examples_path` argument that `main()` never passes. Running it with a corpus "pointed at" by a
flag is therefore impossible, and running it in the main checkout would test O for all three
candidates without saying so. The script also runs **one stage mode per invocation**, so the A7
requirement (auto **and** declared) is two invocations per corpus.

**Decision: the script is not changed.** Its sha256 stays equal to the one in the kri-fixes
attempt-5 record, so the gate's own code is not a variable. The corpus is selected by *where
the script runs*:

1. A throwaway worktree per corpus: `git -C <repo> worktree add --detach $R/meas/<c>
   <pinned sha>`, then `cp $R/corpus/<c>.csv $R/meas/<c>/data/processed/examples.csv`.
   The check is **per corpus, and the hash is the authority** (rev. 5: O's copy is
   byte-identical to the pinned checkout's own file, so `git status` is clean for O and a rule
   that required a modified file could not pass):
   * **O:** `git -C $R/meas/O status --porcelain` is **empty** and `git diff --stat` is empty;
     `shasum -a 256 $R/meas/O/data/processed/examples.csv` equals O's frozen sha256 (and the
     checkout's own file at the pinned commit).
   * **M and N:** `git -C $R/meas/<c> status --porcelain` lists **exactly one** path,
     ` M data/processed/examples.csv`, and `git diff --stat` shows that file alone; the sha256
     of the file equals the frozen M or N sha256.

   So every script is byte-identical across O, M and N, and only the corpus differs.
2. `shasum -a 256 $R/meas/<c>/data/processed/examples.csv` is recorded **before and after**
   each invocation and must equal the frozen sha of that corpus both times.
3. Per invocation (cwd = the worktree, so `PROJECT_ROOT` is the worktree; the private
   directory is the one that holds the St Andrews file, passed explicitly):
   `$PY scripts/check_standrews_urkiv_gate.py --private-dir ~/projects/Egyptology-APP/data/private --stage auto`
   and again with `--stage declared`, output to `$R/<c>/urkiv_{auto,declared}.txt`. The
   private file's sha256 is recorded once and is identical for all six runs. **NC gate (rev. 5,
   Ground rules):** this step reads the St Andrews file (`data/private/standrews.csv`, sha256
   recorded) and writes text-bearing logs, so it is **listed in the pre-registration as a
   named use** and runs only after Ledio has approved that pre-registration. Operator: the
   lead, not the worker (the worker is told the command, never the path or the content). Files:
   that one file. Destinations: `$R/<c>/` for the logs, nothing else, no copy, no commit. The
   same listing covers the `run_expert_paste_eval.py` runs that load private rows (the
   `--private-dir` path of the paste lane), and the part 3 re-measure lists its own. An extra
   read (a "quick look" at a log row) is a use not on the list.
4. The corpus identity is checked from the output as well, not only by hashing: the line
   `corpus N rows: {...}` must equal the candidate's row count plus the private row count and
   its per-source counts (for N the BBAW and Ramses counts differ from O's, so the output
   alone distinguishes N; for M the pre/post hash is what distinguishes it from O, since M has
   O's counts).
5. **Pass rule (A7, amending A2.2 and A1 of the 2026-10-25 pre-registration; the single-mode
   command of A1 is superseded):** in **both** modes the output ends `GATE: PASS` and the
   process exits 0, which the script grants only when all 8 paste checks pass with the private
   rows loaded **and** the pinned row `S_urkIV-001_urkIV-001Tr_0003` is present exactly once
   with its expected reading. A missing private directory or zero private rows exits non-zero
   and is "not run", never "passed". The St Andrews rank is **printed and reported, never
   gated**: the number of St Andrews rows in the retrieval pool and the rank (or "not
   retrieved") for O, M and N go into the results note as diagnostics.
6. Custody: the logs can contain St Andrews (CC BY-NC-SA) row text (`row:`, `top 5 overall`).
   They stay in `$R`, outside the repo. The results note quotes only PASS/FAIL, counts and the
   rank, never a row.
7. The worktrees are removed afterwards (`git worktree remove --force`). Nothing in them is
   committed.

The same swap would work for any other script, but only the gate needs it: every other script
in the table takes `--examples`. If a later pass wants the flag, adding it is its own reviewed
commit and the gate is then re-pinned; it is not smuggled into this one.

### 2.2 Benchmark targets in R, twins and floors (rev. 4)

**What the code does.** The competitive harness excludes a benchmark's own target row from
the pool whenever it is in the corpus (`guard.target_positions`), and scores against the
benchmark's `expected_transliteration`, so a removed target does **not** make a query
unscorable. But `eval_guards.twins_of_target` (lines 156-168) builds a target's twin set from
the corpus row's tokens when the row exists and from the benchmark's fallback
(`expected_key_tokens`, the folded `expected_transliteration`) when it does not. A query whose
target part 1 removes therefore gets a **different twin set**, which can gain or lose members
that have nothing to do with R. Rev. 3 said "the twin inventory may only shrink, and only by
ids in R" and, in the same breath, put these queries in a separate table. Both cannot hold. Rev.
4 separates them.

**Definitions, frozen before any run (and re-derived and re-frozen in any N′ amendment):**

* **Q_R** = every benchmark query id, in every file under
  `data/benchmarks/competitive_ambiguity_eval_queries*.csv`, `expert_paste_queries.csv`,
  `expert_review_sheet.csv`, `known_twins_2026-10-12.csv` and `cross_edition_pairs_v1.csv`,
  whose `expected_source_text_id`/`expected_source_sentence_id` key is in the final R (after
  the 1.4 exceptions). Written to `$R/report/target_removed.csv` (set, query id, key, source,
  lacuna kind or stratum) with its sha256. The 1.1a stop rule (more than 5 in any one set)
  still applies before anything is built.
* **C** = the **common retained-target set**: every query not in Q_R. It is identical for O,
  M and N, because the same ids are dropped before aggregation in every arm.
* **Floor population** = the **full committed benchmark**, Q_R included, exactly as
  `verify_release.py` computes it (`expected_queries` unchanged, 20 for v4). The release
  floors are never evaluated on C alone. This keeps the pre-registration, the part 2 N run and
  the §1.8 local gate on one definition.

**Rules:**

1. **Comparisons use C.** The O-versus-N loss and gain counts, the loss budget of §2.5, the
   mechanism classification of §2.4 and the twin-inventory prediction are computed over C,
   by query id, with `compare_cleanup_runs.py` dropping Q_R rows from every arm before it
   counts anything. The per-query CSVs are not edited, and the query files' sha256s stay as
   pinned.
2. **Twin invariant, over C.** Keyed by composite key, not by position: for every query in C
   the twin set in N is a subset of the twin set in O, and the difference is a subset of R.
   A twin in N that is not in O, or a vanished twin outside R, is a hidden dependency: stop.
3. **Q_R is its own table**, never mixed into C's counts. For each id it lists: O's result
   (rank, useful or not, the twin set from the corpus row), N's result, the twin set N derived
   from the **fallback** representation, and the symmetric difference of the two twin sets by
   key. As a diagnostic control it also reports a third twin set computed in N with the target
   tokens **frozen from O's row** (a fixed O-derived target representation, computed offline
   by `compare_cleanup_runs.py` through `TwinGuard`, no evaluation run), so that how much of
   the difference is the representation switch and how much is corpus change is visible.
   No containment prediction is made for Q_R. A change on a Q_R query is traced to the new
   **mechanism 8 (target-representation fallback)** or to mechanisms 1-7 and 9 with numbers.
4. **Q_R losses are visible to the floors, not to the budget.** A Q_R query that is a hit in O
   and a miss in N counts toward the full-benchmark floor test (rule 5) and must be traced
   to a named mechanism with numbers; it does not count against the "at most 2 per set"
   budget of §2.5, because that budget is defined on C. An untraced Q_R loss is an untraced
   loss: stop.
5. **Floor arithmetic, frozen.** `verify_release.py` fails a lane when a value is below its
   floor by more than `FLOOR_EPSILON`, so a value equal to the floor passes. v4 T-auto is
   17/20 = 0.85 top-3 and 0.75 MRR (attempt 2; the same in attempt 5) against
   `twin_controlled` floors 0.80 and 0.70 (`recorded_commit 3e29304`). Top-3 therefore has
   **one query of slack** (16/20 = 0.80 passes, 15/20 fails) and MRR **1.0 of summed
   reciprocal rank** (0.05 × 20). If N costs v4 more than that, the floors fail by
   construction and the run stops; the floors are not edited to fit (§1.8). The held-out and
   LE-v1 sets have no gating floor; they are reported, with the same loss rules.
6. **Which numbers `release_baseline.json` may take from this pass:** only
   `expected_corpus_rows` and `expected_corpus_sha256` (§1.8). The top-level legacy block
   (0.90 / 0.7917) is non-gating and unchanged; the `twin_controlled` block's floor values are
   unchanged.

### 2.3 Decoder and segmentation regression (rev. 4)

**Why.** `scripts/run_kri_fixes_eval.py` states its own reason to exist: the competitive
benchmarks never call `ReadingModel.predict_sequence` or `Segmenter.segment`, and
`scripts/run_reading_model_eval.py` never attaches a pooled model. Cleanup changes what both
are trained on: removing about 2,200 BBAW and Ramses rows changes the stage-restricted counts
that drive singleton ties and the `/k` discount, and the boundary statistics the segmenter is
built from; PT admission (part 3) adds Earlier-stage evidence. The competitive sets cannot see
that, and measuring the decoder on O before the merge says nothing about N. The harness is
re-run on every corpus.

**Held-out comparability: the problem.** The harness's test set comes from
`eval_guards.text_level_test_mask`: every text group (BBAW and TLA rows are single-sentence
groups) is held out when its **ordinal in order of first appearance** is a multiple of 5.
Removing rows from N shifts the ordinal of every later group, so the held-out 20% would be a
*different* sample in N than in O, and nothing could be paired. The split also moves when part
3 appends rows. Re-running the harness as it is would compare unlike with unlike.

**Design (frozen):**

1. **Fixed held-out partition H_O.** The O run writes the full held-out partition **before**
   duplicate and lexicon exclusions (`--heldout-out`, the new flag of 2.0a), as
   `$R/decoder/H_O.csv` (source, text id, sentence id, sign string, and for each row whether it
   survived exclusion in O and, if not, the reason: `exact_duplicate`, `near_duplicate` or
   `lexicon_leak`), with its sha256 recorded. **O is run twice** (about 12 minutes each): first
   in the harness's default mode, which writes H_O and gives D0, then again with
   `--fixed-heldout $R/decoder/H_O.csv`, which is the **O baseline for every comparison**
   (D0b below). M, N and P are compared with O's fixed-mode run, never with the default-mode one.
   H_O's post-exclusion part must reproduce the attempt-5 split manifest, sha256
   `ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba` (3,473 test rows:
   BBAW 1,013, TLA 2,460); a difference stops the run and is investigated before anything is
   compared, since the corpus and the split code are supposed to be unchanged.
2. **Every other corpus** (M, N, and later P) is run with `--fixed-heldout $R/decoder/H_O.csv`:
   the held-out rows are exactly the rows of H_O that exist in that corpus (matched by
   composite key), and **training is every other aligned row**, with whole text groups kept
   on one side (`assert_text_groups_disjoint`). Rows removed by part 1 simply leave the
   partition; rows added later (UD) are train only, because they are in no partition. Each run
   writes its own `--heldout-out` (so each corpus has its own exclusion reasons) and its
   `--train-manifest`; the comparer's leakage check of item 3 reads these two files and the
   split manifest, not the harness's say-so.
3. **Leakage controls**, all applied per corpus to its own training set, exactly as
   `select_test_rows` does today: exact-duplicate sign strings and near-duplicates (overlap
   0.8) are dropped from test (and, as today, **not** moved to training: they are in neither
   manifest), and `--lexicon-exclude-test-sources` keeps its default.
   Held-out rows are asserted absent from training in every run (key intersection of the
   split manifest and the training manifest empty), and the comparer checks it again from the
   two files. A held-out row that is dropped as a
   duplicate in one corpus and kept in another is listed with the reason.
4. **Comparison set C_D** = the held-out rows that survive exclusion in **every** corpus being
   compared (O ∩ M ∩ N for part 2). All paired statistics are over C_D, by composite key and
   position index, with the counts beside every rate. Rows of H_O absent from N because they
   are in R are reported separately ("held-out row removed") and are not scored.
5. **Arms.** The harness's five arms as they are (`all_off`, `pooled_only`, `discount_only`,
   `cartouche_only`, `all_on`), no `--arms` filter, all other flags at their defaults
   (`--split text`, `--test-fraction 0.2`, lexicon on, `--exclude-duplicates`, near-duplicate
   0.8). The **shipped** configuration is `cartouche_only` (pooled fallback default off since
   `97ddff2`, cartouche window in units since `43fbecb`; the `/k` discount moves no
   prediction, so its predictions are the shipped ones). Gates are applied to `cartouche_only`
   and to `all_off`; `pooled_only` and `all_on` are reported because the fallback code stays
   and its counts are corpus-dependent. About 11-12 minutes per corpus at the observed rate.
6. **M** differs from O in `period` and `grammar_notes` only, and the decoder reads neither
   (`app/services/stage.py` uses `language_stage`). Its harness outputs (positions, lines,
   summary, calibration) must be **byte-identical** to O's fixed-mode run (and so, by D0b, to
   O's default-mode run). A difference is a hidden dependency:
   stop.

**Acceptance rules for N against O (frozen; tolerances are engineering budgets, not claims).**
All on C_D, shipped arm `cartouche_only`, paired by composite key and position (the identity
contract of 2.0a), against O's fixed-mode run, counts beside every rate. **Integer arithmetic
only (rev. 5):** every budget above is computed as `⌊numerator / denominator⌋` on integers
(Python `//`, or `Fraction`), the denominators P, L and B are recorded in the results note
beside the budget, and no rate is rounded before it is compared. **Net or gross is not
chosen after seeing results: D1 and D2 are gross.** Rev. 4 said "net loss" for D1 and D2 and
"gains never offset losses" in the same section; the second statement is the project's
rule (§2.5), so D1 and D2 follow it. D3 is the one total, because it counts errors, and its
per-line worsenings are listed. The same rules apply to the same arm at `all_off` for D1-D3,
reported as a control; the gate is on `cartouche_only`.

| Id | Quantity | Rule |
|---|---|---|
| D0 | harness identity | O (default mode) reproduces attempt 5's `all_off` and `cartouche_only` aggregates on its own held-out partition (positions, lines, exact segmentations, boundary TP/FP/FN); a mismatch stops the run before N is read |
| D0b | the fixed-heldout path | O run with `--fixed-heldout H_O.csv` gives positions, lines, summary and calibration **byte-identical** to O's default-mode run. A difference is a bug in the new flag, not a corpus effect; it is fixed (a new reviewed commit, which re-pins the code and restarts the pre-registration) before M, N or P is read |
| D1 | reading-track position accuracy | **gross loss**: W1 = the number of C_D positions that are correct in O and wrong in N (gains do not offset). Gate: W1 ≤ ⌊P / 1000⌋, with P = the number of C_D positions in the shipped arm (identical in O and N by construction). That is 0.10 percentage points. The exact paired sign test is reported, not gating |
| D2 | whole-line exact reads | **gross loss**: W2 = the number of C_D lines with `line_exact` 1 in O and 0 in N. Gate: W2 ≤ ⌊L / 500⌋, L = the number of C_D lines. That is 0.20 percentage points |
| D3 | boundary errors outside cartouches (segmentation track) | E = the sum over C_D lines of `boundary_fp_outside_cartouche + boundary_fn_outside_cartouche` (a count of errors, so it is a total by nature). Gate: E_N ≤ E_O + ⌊B / 500⌋, with **B = the sum over C_D lines of the gold boundaries, `boundary_tp + boundary_fn`** of that line's `cartouche_only` row (gold-side, so identical in O and N). That is 0.20 percentage points of boundaries. Every C_D line whose `seg_exact` goes 1 → 0 is listed and traced to d3 or d5. Boundary F1 reported |
| D4 | cartouche invariants | cartouches split 0 of all, boundaries inside cartouches 0, in `cartouche_only` and `all_on` (these hold by construction of the shipped code, so any non-zero is a hidden dependency) |
| D5 | stage routing inside the harness | lines whose chosen stage differs between O and N are counted and listed, with the attested coverage that moved them; reported, not gated (the routing set of §2.1 gates the router) |
| D6 | calibration (Brier, three confidences) | reported only |
| D7 | traceability | every position that is worse in N is classified by mechanism (below), with the training counts for the gold and the chosen reading in O and in N; one **untraced** worse position means N is not shippable |

**Decoder mechanisms (frozen list; used by D7):** (d1) a removed row carried the gold reading's
attestation, counts before and after named; (d2) a removed row changed a competing reading's
count or a singleton tie, counts named; (d3) the chosen stage changed (D5); (d4) the position
is adjacent to a changed group (Viterbi coupling), with the changed neighbour named; (d5) a
boundary-model statistic changed for a sign pair in the line, before and after named.
"Training counts changed" without the numbers is not a classification. Gains are listed and
never offset losses.

**Stop rules.** D0 or D0b or M's byte-identity failing, any D4 violation, any D7 untraced
position, or D1-D3 over budget: stop, write the report, commit nothing, decide with Ledio.

### 2.4 Predictions

**Prediction 1 (M).** Period and `grammar_notes` are not read by ranking, routing, the
decoder or the benchmark's declared stage (the precomputed `language_stage` column in each
query CSV; `derive_stage_from_period` is not used at load; `app/services/stage.py` reads
`language_stage`). Re-checked against main `51f3757`: kri-fixes changed none of this. So M's
**evaluation outputs** must be byte-identical to O's from the same code: per-query results
CSVs, summary JSONs, the twin inventory and the decoder harness outputs (the latter against O's
fixed-mode run, §2.3), all produced with the same pinned query files and environment. M itself differs from O by construction. Any output
difference means a hidden dependency → stop. `grammar_notes` does feed card citations
(`app/data/source_metadata.py`). That is display only, checked by eye on 5 AES cards.

**Prediction 2 (N).** Every changed query in **C** is classified by mechanism from the frozen
list, with evidence. For mechanism 1, name the removed row and its role (twin or top-k
evidence; a target is in Q_R by definition and handled by §2.2). For mechanisms 2-9, give
before/after values of the statistic and the scores of the swapped candidates. "IDF shift"
without numbers is not a classification. The twin inventory over C may only shrink, and only by
ids in R (§2.2 rule 2). Changes on Q_R follow §2.2 rules 3-4.

### 2.5 Loss acceptance (frozen)

* Hard gates must hold: paste 8/8 in `auto` and in `declared` **with the private rows loaded,
  the pinned row present exactly once, and the St Andrews rank reported but not gated**
  (A2.2′ as amended by A7; the public-only `run_expert_paste_eval.py` runs in the same two
  modes and must also be 8/8); the Urk. IV gate `GATE: PASS` in both modes (§2.1a); routing
  Earlier/Late → Demotic 0/200; v4 T-auto above the `twin_controlled` floors (§2.2 rule 5);
  M byte-identical (Prediction 1); the decoder rules D0-D7 (§2.3).
* Every loss on a query in C must be traced to a named mechanism. One untraced loss means N is
  not shippable.
* A traced loss in C is accepted only if it is mechanism 1 with a removed broken reading, or
  mechanisms 2-9 at no more than 2 losses per set (the budget is defined on C; Q_R follows
  §2.2 rule 4).
* More losses than that → stop. The report is written, nothing is committed, and a decision
  is taken with Ledio.
* Gains are listed and never offset losses.

**Then** 1.8 (commit and local release gate) → 1.7 → 1.9. Only `expected_corpus_rows` and
`expected_corpus_sha256` are updated in `release_baseline.json`; no floor value moves (§1.8).
A code change during the run ends the run (as (A) A2.9/A3).

### 2.6 Effort and compute (rev. 4)

~1 h to write the pre-registration, ~½ day for the results note, ~1 day for the 2.0a code and
its review. **Compute, from observed timings (do not use an estimate):** one corpus's 15
competitive runs took about **11 h 40 min** in attempt 2 of the 2026-10-25 series and about
**2 h** in attempt 1 for byte-identical outputs (see the "Runtime observed 2026-10-26" addendum
in `docs/remeasure-preregistration-2026-10-25.md`); both rev. 3
reviews cite a measured **~15.5 h per corpus run set** on this Mac. Part 2 runs that set for
O, M and N: budget **about 46 h of wall time** (3 × 15.5 h), and plan on it, not on
"overnight".
The decoder harness (about 12 min per corpus, and one extra O run for D0b), the six Urk. IV gate invocations (about one
corpus build each) and routing are inside that figure or small beside it. Any N′ amendment
repeats the **whole** set (§1.7 step 4, no partial re-run), and the part 3 re-measure (§3.3)
needs about the same again. The Mac is serialized across worktrees (Ground rules). Start the
session early, do not schedule a review for the next morning, and accept that an interrupted
run costs another full run. This is also why §1.7 step 4 says a second rebuild is likely:
saving is open for days and annotators keep writing.

---

## Part 3 — Pyramid Texts (UD_Egyptian-PC) admission

**Dependencies (rev. 4).** Part 3 starts only when (a) part 1 is committed, merged and deployed
(order table row 1s); (b) the (B) exclusion manifest `docs/kri/exclusion-manifest.csv` is
**complete** (§4.0: no pending hash, the self-test entry EX001 filled) and its sha256 is
written into the part 3 pre-registration; (c) the 4a negative holdout is drawn (rule 7). If
(b) is not true, rule 6 cannot be evaluated and part 3 waits; parts 1 and 2 do not depend on
it.

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
   exclusion manifest of (B), **as committed at `docs/kri/exclusion-manifest.csv` with the
   sha256 recorded in the part 3 pre-registration**. The check is the manifest route of
   `scripts/check_overlap.py` (canonical hash, KRI reference span, and the §4a predicates
   against the private excluded texts in `~/egyptology-private-kri/excluded-texts.csv`, which
   must hash to the manifest's entries). Exclusions are keyed to the KRI reference and text
   hash, not to a corpus row, so a row that part 1 removed or an edition that left the corpus
   does not lift one. Near-twins of an excluded passage are listed with the entry id. The
   PT-versus-KRI overlap is expected to be nil (Old Kingdom against Ramesside), but the rule
   is the rule, and an incomplete manifest stops part 3 (dependency (b)).
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

**3.3 Re-measure after admission (rev. 4: with the decoder harness).** A second short
pre-registration, same structure as part 2 (including its list of named NC uses, §2.0 and the
Ground rules: the six gate invocations and the private paste runs are approved by Ledio when he
approves it), baseline = the committed part 1 N, re-run fresh
on the same pinned code. Everything in part 2 applies with N as the baseline and the
candidate P (= N plus the admitted rows) as the corpus under test: §2.1 and §2.1a commands
(N → P), §2.2 (Q_R is empty for P because nothing is removed; the twin invariant is over all
queries and extends to "a UD row that twins a benchmark target is listed"), §2.5. The
**decoder and segmentation harness is repeated** (§2.3) with N's partition: the held-out
partition is **still H_O** (`--fixed-heldout`), so UD rows, which are in no partition, are
training only, and the comparison set is the rows kept as test in both N and P. A PT row that
makes a held-out row a near-duplicate removes that row from the comparison and is listed.
Budgets for N → P are tighter than for O → N because the added evidence is small, and are
the same integer formulas with the same denominators (§2.3), gross for D1 and D2: D1 gross
loss ≤ ⌊P / 2000⌋ (0.05 percentage points), D2 gross loss ≤ ⌊L / 2000⌋ (0.05), D3 total error
increase ≤ ⌊B / 1000⌋ (0.10), D0b and D4-D7 unchanged. P, L and B are those of N's comparison
set, recorded beside each budget. The Earlier-stage positions
are reported separately; no gain is claimed. Predictions are classified
by the same frozen list of corpus-dependent statistics, not only "a UD row entered top-k":

* added Earlier rows shift global IDF;
* they shift attestation counts;
* they shift the segmentation/boundary statistics;
* they shift the Earlier stage prior and routing counts.

Each changed query needs a named mechanism with numbers, and the same loss-acceptance rule
applies. Hard gates are unchanged: paste 8/8, Urk. IV gate, Demotic 0/200. The twin
inventory diff lists any UD row that twins a benchmark target (expected 0 after rule 6).

**3.4 Admission deploy and rollback (rev. 5).** Rev. 4 gave part 3 a re-measure but no backup
and no way back. The admission is **append-only** (the old prefix of `examples.csv` is
byte-identical, no annotation can sit on a new id), so its rollback is simpler than part 1's,
and it is written down before the deploy anyway:

1. **Fresh backup first.** Immediately before the merge, Ledio takes a backup by the §1.0a
   protocol (B1 with all of (a)-(e), B2, B3, B4-B6) and records its name and sha256 in
   `$R/db/snapshot_p3_source.txt`. Saving is **not** paused for part 3 (nothing it does can
   collide with an annotation), so this backup is a safety net for integrity, not a restore
   point for annotations written afterwards.
2. **Deploy** `~/egyptology-deploy.sh` without `INSTALL_UNITS`, run by Ledio. The log must show
   `inserted = admitted` (the admission count in the part 3 report), updated 0 and the merged
   commit. Any other count is a trigger.
3. **Live check:** the app renders a result card for a pasted line; the UD credit shows; the
   live `COUNT(*) FROM examples` equals the backup's plus the admitted count; annotation
   `COUNT, MAX(id)` is not lower than before. A trigger is any failure of these, or a deploy
   that rolled back.
4. **Rollback.** (a) A failed deploy: the deploy script's own rollback restores code, units
   and the venv; the DB gained nothing (the sync did not run) or gained only rows that the
   old code ignores (the app is CSV-driven). Ledio confirms the corpus sha256 on the server
   equals N's. (b) A bad admission found afterwards: the lead prepares `git revert -m 1 <merge
   sha>` from the pushed main, Ledio pushes it and runs the deploy. The inserted UD rows stay
   in the DB, unreachable from the UI (`attach_db_ids` is CSV-driven), exactly as the part 1
   removed rows do; the same FastAPI `/examples/search` caveat (A52) applies and is checked
   before the part is called finished. (c) A **corrupt DB** (integrity checks fail) is the one
   case that restores a database: then **saving is paused first** (§1.7 step 1a and 2) and
   §1.9a steps 2-8 are followed with this part's backup in place of snapshot 2. Annotations
   written after that backup are lost by such a restore, which is why the pause comes first
   and why this case is the exception.

Effort: script + tests ½ day; conversion check + review ½ day; docs/credits 2 h; re-measure
about 15.5 h of wall time for P and the same again for the baseline N re-run fresh (about
31 h in all, §2.6), plus ½ day to write up. The earlier "overnight" was wrong. Heavy runs
are serialized across worktrees (Ground rules).

---

## Part 4 — KRI test with Camilla

### 4.0 Status, order and exposure (rev. 4)

Rev. 3 was written before the KRI PDFs arrived and before the official-test tooling existed.
Both have happened, so this block records what is true as of 2026-10-28 and fixes the order.

**(a) What happened, dated.**

* **2026-10-26 about 07:43:** the KRI PDFs were received (scanned images, no text layer; they
  live in `~/egyptology-private-kri/`).
* **2026-10-26 08:37 and 08:40:** the B-freq baseline code was committed and its hash record
  written. That is a freeze **after receipt and before reported content inspection**, not the
  pre-arrival freeze §4e requires. The deviation is recorded in
  `docs/kri-bfreq-baseline-2026-10-26.md`, on the lead's attestation that no KRI text or page
  content was viewed before freezing (not independently verified).
* **2026-10-26:** an **exploratory self-test** ran the app on KRI lines. The passage is
  `KRI II 569 (lines 3-16), Karnak Great Hypostyle Hall` (manifest entry `EX001`, hash still
  pending). The three kri-fixes changes (cartouche constraint, singleton `/k` discount,
  pooled fallback; merged 2026-10-27, main `51f3757`) were made **because of** that
  self-test. Those lines are therefore *seen*, and the code was *tuned on them*.
* **2026-10-26:** the official-test tooling was built on synthetic fixtures only and is on main:
  `scripts/check_overlap.py` with `scripts/kri_overlap.py`, `scripts/kri_declaration.py`,
  `scripts/kri_exclusion_manifest.py`, `scripts/kri_stats.py`, `scripts/run_kri_endpoints.py`,
  `scripts/kri_segment_mapping.py`, the frozen B-freq baseline (`scripts/bfreq_baseline.py`,
  `scripts/build_bfreq_table.py`), the dev fixture `tests/fixtures/overlap_dev_v1.csv`, and
  `docs/kri/exclusion-manifest.csv`. There is **no gate fixture yet**, so the §4a gate has not
  been passed, only the dev fixture.

**(b) Consequences, fixed now.**

1. **Exposure applies to both endpoints.** The B-freq record says endpoint R is "unaffected by
   the late freeze". That is true of the freeze and false of the self-test: a line the app
   was run on, or that the kri-fixes changes were tuned on, cannot confirm anything for
   endpoint R **or** endpoint G. Every self-test line, its whole passage and every other
   edition of it goes into the (B) manifest as an exclusion for both endpoints.
2. **Lines from the current PDFs are exploratory for endpoint G whatever their selection
   date** (the freeze record). A G *confirmation* needs a separately eligible cohort whose
   material arrives after the freeze. For endpoint R, a line from these PDFs is
   confirmation-eligible only if it was never seen in the self-test or in any development
   inspection, and is not excluded by the manifest.
3. **The manifest is a precondition, not an afterthought.** It must be **complete**
   (`scripts/kri_exclusion_manifest.py`: no pending hash, every reference parses as a KRI
   citation, every entry has its text in custody) and committed with its sha256 **before**
   any official run, before the §4a gate fixture's negatives are adjudicated against it, and
   before part 3 rule 6 (which reads it). To complete it, the lead, who alone may open the
   private directory, **and only in a session Ledio has approved and logged in
   `~/egyptology-private-kri/access.log` (Ground rules, NC-data gate; the log line names this
   purpose and the files)**, (i) fills `EX001`'s hash from the passage text (`--text-file`),
   (ii) lists by KRI reference **every other** line, passage or edition inspected in the
   self-test, in the kri-fixes development or in any other development look (from the
   self-test notes and the `~/egyptology-runs/kri-*` logs), and adds an entry for each,
   (iii) adds the other editions, found by the checker's private excluded-text route (pinned
   Jaccard ≥ 0.5, identical fold, containment, shared run, edition links). Only identifiers,
   hashes and aggregates are ever committed; no KRI text enters a tracked file.
4. **Exclusion survives removal.** Entries are keyed to the KRI reference and the canonical
   text hash, never to a corpus row. A corpus row that part 1 removes, or an edition that
   later leaves the corpus, does not lift an exclusion. Rows of O that were retrieved as
   neighbours in the self-test are history, not material: any KRI line equal or near to them
   is caught by the hash and Jaccard routes, not by the row id.
5. **Historical exposure screening (rev. 5).** The manifest keys exclusions by KRI reference
   and hash, but the *overlap* check (the §4a predicates) runs only against the corpus it is
   given. After part 1, a row of O that was removed (R), and any row that only ever lived in
   the DB (H), is in no corpus the checker is given, so a KRI line that resembles such a row
   would be `new` against the cleaned G and look unexposed, although the self-test and the
   kri-fixes development may have retrieved that very row. Rev. 5 therefore adds a
   **historical screening set**, built from public material only and screened by extra
   invocations of the **unchanged** checker (`scripts/check_overlap.py --examples <csv>`, one
   per set; no checker change, so the gate fixtures are not retired):
   * **O**: `examples.csv` at the 1.0 commit, restored from git into `$R/hist/O.csv` with
     its sha256 (130,472 rows, `44543932…f1e2`). In Case 1, G = O, so it is G itself;
   * **H**: `$R/db/H_rows.csv` (§1.0b), with its sha256;
   * **R**: the removed rows, `$R/hist/R_rows.csv`, built from the removal manifest's old
     readings and the O rows, in the columns of `examples.csv`, with its sha256 (R ⊆ O, so
     it is a subset of the first set; it is listed separately so that a later "re-admit"
     decision cannot lose it);
   * **the self-test's retrieved neighbours**: the row keys named in the self-test and kri-fixes
     development logs, looked up in O ∪ H, added to the same set (the lead reads the logs,
     under the NC-data gate, and commits no text).

   A KRI line's label for **eligibility** is the strictest of its runs (`contained` >
   `partial` > `new`): it is confirmation-eligible only if it is `new` against G **and**
   against every historical set. The **gate fixture's labels stay computed against G alone**
   (§4a), because the gate tests the checker, not the exposure. The historical sets' hashes
   are written into the declaration (§4d) beside G's.

**(c) The order (O1; decided, with a rule so it needs no later argument).** Two orderings
existed in rev. 3: the official test after cleanup (G = N plus PT, B-freq rebuilt and amended
twice), or before it (G = O, B-freq as frozen). Neither can be forced, because Camilla's
material is not ours to schedule. The rule is:

* **G is fixed at the gate-fixture draw (rev. 5).** Rev. 4 defined G as the corpus on main when
  the declaration's sha256 is committed, and the declaration can only be committed after the
  gate on G has passed, so G was defined by an event that comes after the gate that needs
  it. Now: **G = `data/processed/examples.csv` at the main commit and sha256 written into the
  gate fixture's header at the moment the fixture is drawn** (§4a Timing 5). From that moment G
  does not move. `declaration.csv` (§4d) must carry **the same** commit and corpus sha; a
  mismatch means re-verification of every label on the new sha by both adjudicators, or
  retirement of the fixture, under the existing rule of §4a. The Case 1 / Case 2 choice is
  made **at the draw**, not at the declaration.
* **Case 1, the fixture is drawn before §1.9's merge:** G = **O** (sha
  `44543932…f1e2`, 130,472 rows) at the post-kri-fixes main commit (`51f3757` or a descendant,
  pinned in the fixture header). B-freq needs no rebuild. From the **draw** (not from the
  declaration, rev. 5) until the official results are committed there is a **replacement
  freeze**: the §1.8 merge and §1.9 deploy do not run, so no cleanup can merge between the draw
  and the declaration. **The freeze is bounded:** Case 1 is chosen only if Camilla's gold for
  at least one confirmation-eligible line is already in hand at the draw, so that the
  declaration can be committed within **7 days** of it. If it is not committed by then, the
  fixture is retired, the freeze lifts, and Case 2 applies; a later draw is a new fixture. (An
  unbounded freeze would let a pending email block the cleanup.) Parts 1-2 may keep measuring
  candidates (they replace nothing) but heavy runs are serialized and the official run goes
  first at its turn. After it, part 1 proceeds, and §1.8 does **not** relabel the official run:
  its labels and results stay those of O, and its record says so. B-freq is rebuilt and
  amended only for a *later* cohort.
* **Case 2, the cleanup is merged first:** G = the then-current main corpus. B-freq is
  rebuilt and `docs/kri-bfreq-baseline-2026-10-26.md` amended with the new corpus and table
  sha256s (item 6 of its list: counts change, the rule, keys, tie-break and surface rule do
  not) **before** the declaration is written: after part 1 if the declaration comes before
  part 3 (G = N), and again after part 3 (G = N plus PT). The KRI test then waits for
  parts 1-3, about 46 h of measurement plus the server steps (§2.6), which is the price of
  this case.
* If no gate fixture has been drawn when §1.8 is ready to merge, Case 2 applies and nothing
  waits. If Camilla's material is already in hand at that point, **prefer Case 1**: it costs no
  rebuild and the test is on the corpus whose B-freq tables are frozen. (It does not need a
  declaration yet: the draw fixes G and starts the bounded freeze.)

### 4a. Overlap checker (scaffolding plan Phase 3): spec now, gate fixture frozen on the gate corpus

**Gate corpus G (rev. 5).** G is **the corpus on main at the moment the gate fixture is drawn**
(§4.0 (c)): `data/processed/examples.csv` at the main commit and sha256 written into the fixture
header at the draw. `declaration.csv` must name the same commit and sha. G is O
(`44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2`) in Case 1, and the
then-current cleaned corpus in Case 2. Rev. 3's "G = `examples.csv` at the part 3 commit" is
withdrawn: it tied the official test to a cleanup that takes days of measurement. The commit
and sha256 go in the fixture header. With `--private-dir`, G also includes `standrews.csv` at a
recorded sha256. If `examples.csv` on main changes again before the official run, both
adjudicators re-verify every label on the new sha (in Case 1 the §4.0 replacement freeze, which
starts at the draw, makes that impossible by design). Any changed label retires the fixture, and a new one is drawn with
a new seed.

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

**Timing (rev. 4).**
1. The predicates, thresholds, strata and seeds are committed (done: `scripts/kri_overlap.py`,
   `scripts/check_overlap.py`, the dev fixture, on main).
2. **The checker is the `kri-official-prep` checker.** `scripts/check_overlap.py` and
   `scripts/kri_overlap.py` on main *are* the §4a checker, not a second one, and they follow
   these rules. Nothing may be changed in them to make a gate row pass (a change retires the
   gate fixture, see Gates below).
3. **Dev fixture first, and committed.** The dev fixture's rows and seeds
   (`tests/fixtures/overlap_dev_v1.csv`, `tests/fixtures/overlap_dev_corpus.csv`; synthetic, 6
   invented corpus rows, 10 labelled lines) are committed on main **before** the checker is
   run on any gate fixture. The gate draws exclude them. Today they are committed; this is
   checked, not assumed, at the time of the gate draw.
4. **Holdout.** The 4a negative UD lines are drawn once, before any part 3 filter runs and
   before the gate fixture is adjudicated, from rule-1/2/4/6-passing candidates built against
   **G**, and frozen in `$R/ud/fixture_holdout.csv` with its sha256. Part 3 rule 7 consumes
   that same file. If part 3's corpus differs from G, rule 7's "would make a holdout line
   non-`new`" test is re-evaluated on the part 3 corpus.
5. **Gate fixture drawn and frozen on G**, whichever corpus G is (§4.0 (c)), **after** the
   manifest is complete and committed (§4.0 (b)). **The draw is the event that fixes G**
   (rev. 5): the main commit and `examples.csv` sha256 go into the fixture header at that
   moment, the Case 1 / Case 2 choice is made and recorded in the header, and in Case 1 the
   replacement freeze starts. The fixture file's sha256 is **committed before the checker is
   first run on it.** The adjudications and the gate come after the draw and do not change G.
6. **Adjudicators are blind to the checker.** Opus and Astra each write their own script that
   calls the pinned repo functions directly (including `scripts.bfreq_baseline.sign_key`, per
   the 2026-10-26 addendum at the end of this plan), and are not given `scripts/check_overlap.py`
   or `scripts/kri_overlap.py` and are not told its results. Their scripts are written in
   sessions that have no read access to those two files. A disagreement drops the row, never
   relabels it.

**Implemented** (on main): `scripts/check_overlap.py --lines FILE --examples … [--private-dir DIR]
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
* **Access (rev. 5):** opening this directory needs Ledio's approval of that session, logged
  as one line in `~/egyptology-private-kri/access.log` (Ground rules, NC-data gate). The lead
  is the only operator; workers, adjudicators and reviewers are never given its path.
* **St Andrews server copy (explicit allowlist):** only `standrews.csv`, by exact filename
  and with its sha256 checked after copy, to the server's `PRIVATE_DATA_DIR`. It is copied
  with a single-file `scp`, never a directory copy or `rsync` of `data/private`. Any other
  file found in the server's private dir is reported to Ledio.
* **Belt and braces:** a loader test that a CSV in a subfolder of the private dir is never
  loaded stays as a guard, even though no KRI file lives there.

### 4c. What to ask Camilla (rev. 4: the PDFs have already arrived; one short email, Ledio sends)

Rev. 3 asked her for passages. The PDFs came first (§4.0 (a)), so the email changes shape.

**Confirm, do not ask for material:** the source and permissions of the PDFs in custody: which
edition and scan they are, whether she is content for them to be used for tests and
screen-shared (not uploaded) in the Zoom session, and any restriction on keeping them in
`~/egyptology-private-kri/`.

**Ask only for what we cannot make ourselves**, for each passage she wants tried (3-5 to
start):

* her gold: the transliteration and her **word division of the glyph input** (the gold groups
  must concatenate to exactly the pasted glyph string) with one reading per group;
* the KRI reference (vol., page, line), and a passage identity (which monument or scene);
* whether her transliteration is diplomatic or normalised;
* later, her blind judgements for endpoint R, once a blind pack exists.

Tell her that the self-test passage (`KRI II 569`, lines 3-16) is already used and will be
exploratory only. Optional: which lines she expects to be hard; whether many more
**independent passages** (§4e needs about 250 per endpoint to confirm anything) could be
supplied later.

### 4d. Run and report (small n, exploratory)

**Declared before any run, per line, in `~/egyptology-private-kri/declaration.csv`** (its
sha256 committed before the first run):

* the input modality;
* the endpoint;
* the stage setting (`--stage auto`);
* the commit;
* the corpus sha, which must equal the gate fixture's G (§4.0 (c)), and the sha256s of the
  historical screening sets (§4.0 (b)5).

There are two pairings:

* **glyph input → reading endpoint:** the tool's top-3 reading suggestions. Success = her
  gold in top 3 (strict key, then folded key, both reported).
* **transliteration input → retrieval endpoint:** similar-text search. Success = a
  supporting passage judged relevant by her, with rank.

A line with both kinds of input gets two declared runs, reported separately. Nothing is
re-declared after results.

Overlap-check every line first, against G **and** against the historical screening sets
(§4.0 (b)5); a line is runnable only if it is `new` in all of them. Ramses risk: KRI is Ramesside, and Ramses is Ramesside Late
Egyptian. Ramses lines are shuffled with no text ids (overlap only by content), and its
transliteration is normalised to the expected grammatical form, so a diplomatic line may
score lower than it should. The overlap report therefore shows the Ramses nearest neighbour
and its score for every line, whatever the label. `contained` / `partial` lines are reported
as "found", never as "read". The tool runs only on `new` lines, with the declared endpoint,
showing supporting sentences with hieroglyphs and source. Report **case by case** ("k of n"),
with no percentages or intervals while n < 30 and no claim to anyone beyond "on these lines".
Zoom pack per scaffolding plan Phase 4.5 (private, local).

**Permanent exclusion (rev. 4).** Exclusion is recorded when a line is *seen*, not when
material arrives: the self-test lines are already in the manifest (§4.0). Every line run in
4d is added to the (B) manifest (reference + canonical hash, with its whole passage as a KRI
vol./page range and every other edition of the same text: other KRI references, a TLA/Ramses
row with pinned Jaccard ≥ 0.5, edition links) **before** its run, because a run is an
inspection. A line run here is exploratory: it is `runnable`, never `confirmation_eligible`,
for **both** endpoints, and can never count toward 4e. `declaration.csv` carries the code
commit and the corpus sha (= G as fixed at the gate-fixture draw, §4.0 (c)); its `validate` output prints the sha256 that is
committed before the first run.

### 4e. If enough independent passages become available (rev. 4: clustering and power)

Protocol (B) of the 2026-10-25 pre-registration was written for one endpoint only:
useful-in-top-3 retrieval, compared against word overlap and BM25. It has no baseline for
glyph → reading. Rev. 3 therefore runs **two separate, endpoint-specific comparisons**.
Each has its own baseline, scoring, analysis unit and power floor, and they are **never
pooled**: no combined rate and no combined test. Rev. 3 also called the unit "one declared line,
clustered by passage" while specifying a line-level exact binomial test and a line-level paired
interval; lines of one passage share vocabulary, formulae and often a scribe, so they are not
independent trials, and "reporting passage sensitivity" does not make them so. Rev. 4 fixes the
design instead of the report.

**Unit of analysis: one independent passage.**

* A **passage** is one continuous KRI text unit (one monument's inscription or scene, as a
  KRI volume / page range). Two editions of one text are **one** passage (the manifest's rule).
  Each declared line carries a `passage_id` in `declaration.csv`.
* **One line per passage per endpoint.** For each endpoint, each confirmation-eligible
  passage contributes exactly **one** declared line, chosen by a seeded draw (seed 20261028;
  eligible lines sorted by KRI reference, then drawn) made **from the declaration alone, before
  any run, before any blind judgement and before any output exists**, and committed with the
  declaration's sha256. The other lines of the passage are not part of the confirmatory
  analysis. A line declared for both inputs is a unit in each endpoint, and a passage's drawn
  line for R and for G are drawn independently.
* Lines are therefore independent units by construction, and the sign test and the paired
  interval below are valid as stated. The all-lines view is **secondary and descriptive**
  (below).

**Shared by both endpoints:**

* the exclusion manifest is committed first, complete (§4.0 (b)), including every 4d line and
  the self-test exclusions, for **both** endpoints;
* exclusion checks: pinned Jaccard ≥ 0.5, identical fold, same text, edition link, the 4a
  checker (only `new` lines enter) and the manifest routes;
* each line's input modality, endpoint, `passage_id`, the pinned commit and the corpus sha
  (= G, §4.0 (c)) are declared up front in the declaration file before any line is run;
* `--stage auto`, one evaluation on a pinned commit and a pinned corpus sha; any change after
  seeing results retires the set (for both endpoints);
* per unit, a binary success for the app and for the baseline; discordant pairs W (app only)
  and L (baseline only); ties dropped from the test and reported; one-sided exact sign test
  P(X ≥ W | X ~ Bin(W+L, ½)) and a **95%** two-sided Newcombe paired interval; both must
  clear (below) for "beats the baseline";
* **Holm** across the two endpoints (family of 2, α = 0.05, exact rational thresholds, as
  `scripts/kri_stats.py` does): the smaller p is compared with 0.025, and only if it is
  rejected the other with 0.05. The interval stays 95% at both steps (conservative at the
  second). An endpoint below its power floor is reported as "uninformative" and still counts
  in the family.

**Endpoint R: transliteration input → retrieval.** (B) unchanged except for the unit and the
power floor above and below:
* success = a useful supporting passage in the top 3, as judged by Camilla, blind to which
  system produced it, with both systems' top 3 shown merged and shuffled;
* primary baseline: word overlap. BM25 is secondary, with per-pool statistics;
* the blind-pack generator and BM25's per-pool statistics are **not built** (tooling note):
  endpoint R cannot be run until they are built, frozen and reviewed.

**Endpoint G: glyph input → reading.** A new comparison, pre-registered as an addendum to (B).
**Status (rev. 4):** the baseline is no longer future work. B-freq is implemented, tested and
frozen (`scripts/bfreq_baseline.py`, `scripts/build_bfreq_table.py`,
`tests/test_bfreq_baseline.py`, the hash record in `docs/kri-bfreq-baseline-2026-10-26.md` with
its rev. 2 and rev. 3 amendments, guarded by `tests/test_kri_bfreq_freeze.py`), and the
app-segment → gold-span mapping is built (`scripts/kri_segment_mapping.py`). It was frozen
**after** the PDFs were received (§4.0 (a)), so **lines drawn from the current PDFs are
exploratory for G regardless of when they are selected**, and no G number from them goes to
experts. A G confirmation needs a separately eligible cohort whose material arrives after the
freeze and the table rebuild below.

* **Unit:** one independent passage, one drawn line (above). A line's groups are her gold word
  division of that line, mapped onto the glyph input (`kri_segment_mapping`).
* **App score:** for each gold group, a hit if her gold reading is in the app's top 3 for
  that group (strict key primary; folded key reported). A group the app's segmentation
  does not produce, or that it merges or splits, counts as a miss for the app. The line
  score `s` = hits / groups.
* **Baseline B-freq (as frozen):** for each gold group, take `signs(group)` (the 4a
  definition, `scripts.bfreq_baseline.sign_key`). Its top 3 = the three most frequent
  `strict_reading_key` values among the word-level (sign group, reading) pairs of the same
  pinned public corpus that carry exactly that sign string. Ties are broken by count, then by
  strict key in code-point order. An unattested sign string gives an empty list, which is a
  miss. B-freq is given the gold segmentation, which favours the baseline; that is stated in
  the report.
* **Binary success per unit:** `s ≥ 0.5`, for both app and baseline. The continuous `s` is
  reported descriptively.
* **Table rebuild, not a rule change.** The B-freq table is frozen against **O**
  (`44543932…f1e2`). It is rebuilt, and the freeze record amended with the new corpus and
  table sha256s, whenever the declared G is not O (§4.0 (c) Case 2): after part 1, and again
  after part 3 if the declaration comes later. The rule, the keys, the tie-break and the
  surface rule do not change; only the counts do. A change to any of them retires the
  baseline, as the freeze record says. Every rebuild is recorded; none is silent.
* **Secondary (descriptive, outside the Holm family):** B-freq restricted to Late Egyptian
  rows; group-level hit counts.

**Power floor, recomputed for this design (rev. 4).** Rev. 3's "about 150 lines" came from a
calculation at one-sided α = 0.05 with lines as units (0.89 at 20% discordance and 0.69 at 30%
for N = 150). Neither holds here: the unit is a passage, and Holm's first step is 0.025.
Calculated for this revision on 2026-10-28 (not committed; the calculation must be re-run
from a committed script using `scripts/kri_stats.exact_sign_test` and
`newcombe_paired_interval` before the pre-registration is written). Assumptions: true paired
margin +0.10, baseline success rate 0.40, discordance 20% or 30%, both gates required (exact
one-sided p < 0.025 and the 95% Newcombe lower bound > 0):

| Independent passages | 100 | 150 | 200 | 250 | 300 | 350 | 400 |
|---|---|---|---|---|---|---|---|
| power, 20% discordance | 0.54 | 0.75 | 0.88 | 0.94 | 0.97 | 0.99 | 0.99 |
| power, 30% discordance | 0.37 | 0.56 | 0.70 | 0.80 | 0.87 | 0.92 | 0.95 |

**The floor is 250 independent passages per endpoint** (power ≥ 0.80 at 30% discordance),
judged separately for R and G. Below it the endpoint is "uninformative": counts only, no
claim of superiority and none of equivalence, still in the Holm family. Lines within a passage
never add to N. Stated plainly: 250 independent KRI passages is a large amount of material,
and if Camilla cannot supply it, confirmation is out of reach and every number stays
descriptive. That is an honest outcome, and it is better than a test that cannot fail.

**Secondary analysis (descriptive, outside Holm):** every confirmation-eligible line, reported
as counts per passage with a passage-clustered summary, and a sign-flip permutation over
passages of the per-passage margins as a diagnostic. It informs nothing that is quoted.

**Tooling amendments required before any 4e material (not made in this draft).** One reviewed
commit with tests, updating `tests/test_kri_tooling_freeze.py`'s hash record in the same
commit with an explicit note: `scripts/kri_declaration.py` gains `passage_id`;
`scripts/run_kri_endpoints.py` performs the seeded one-line-per-passage draw and the
descriptive clustered secondary; `scripts/kri_stats.POWER_FLOOR` becomes 250 and counts
passages. The frozen B-freq files are **not** touched.

Only these comparisons yield a new number for experts, quoted per endpoint with its
baseline named.

---

## Order, dependencies, effort, who (rev. 4)

Heavy runs (any worktree) are serialized. "Compute" is wall time on this Mac from the observed
timings in §2.6.

| # | Step | Depends on | Effort | Needs |
|---|---|---|---|---|
| 0 | Merge + push + deploy audit branch; (A) results reviewed | — | **DONE** (`3465478` merged and deployed; `docs/remeasure-results-2026-10-26-attempt2.md`) | — |
| 0b | Merge + push + deploy `kri-fixes-2026-10-26`; attempt 5 results note | 0 | **DONE** (main `51f3757`, live; `docs/kri-fixes-results-2026-10-27-attempt5.md`) | — |
| 0c | KRI official-test tooling and frozen B-freq on main | — | **DONE** (synthetic fixtures only; no gate fixture yet) | — |
| 4.0 | Complete the (B) exclusion manifest (EX001 hash, every inspected line, other editions); commit its sha256; build the historical screening sets (§4.0 (b)5) | 0c | ½ day | lead (private custody); **Ledio** approves and logs the session |
| 1.0 | Preconditions, hashes, floors recorded, SSH precheck on the tagged host | 0b | 1 h | **Ledio**: SSH check |
| 1.0b | Snapshot 1 by the 1.0a protocol, reconciliation (H), protected set P | 1.0 | 1 h | **Ledio**: server backup |
| 1 | `--donor-output` + inventory 1.1a (stop rules) → merge script → candidates N, M → report | 1.0b | ~1½ days | — |
| 4a | Gate fixture drawn on G, **the draw fixes G and chooses Case 1 or 2** (after manifest complete); holdout drawn before the part 3 filter; checker is the kri-official-prep one | 4.0; holdout: before 3's filter | 1½ days | Opus + Astra adjudicate, blind to the checker |
| 1r | Report review, BBAW `_` strata, exceptions frozen | 1 | ½ day | Opus + Astra; **Ledio** approves |
| 2.0a | `--fixed-heldout` / `--heldout-out` harness flags, `compare_cleanup_runs.py` (reviewed, frozen) | 1r | ~1 day | Opus + Astra |
| 2 | Pre-reg, then O / M / N on candidates: competitive sets, paste ×3, six Urk. IV gate runs, twins, answerability, routing, decoder harness | 1r, 2.0a | 1 h + **about 46 h compute** + ½ day | — |
| 1.8 | Commit on the branch + local release gate (full suite, full `verify_release.py`, gate, paste) | 2 passes | ½ day + the gate's compute | **Ledio** approves the commit |
| 1.7 | Pause saving, snapshot 2 (1.0a), P2; if P2 ∖ P hits R: N′ → repeat 2 and 1.8 | 1.8 | ½ day (N′: +~46 h) | **Ledio**: server env, sudo |
| 1.9 | Merge + push (merge commit or rebase only if the code diff is empty), deploy (no `INSTALL_UNITS`), post-restart pause checks, live-bound dry-run and refresh, live check, restore key from the pre-pause copies; **§1.9a is the way back** | 1.7 clears; no replacement freeze (§4.0 (c)) | ½ day | **Ledio** |
| 3 | UD exporter columns, PT admission (rules 1-7) + its re-measure 3.3 (before its deploy) + backup, deploy and rollback 3.4 | 1.9, 4a holdout, manifest complete | ~2 days + ~31 h compute | **Nederhof**: only if the conversion check fails; **Ledio**: server backup and deploy |
| 4c | Email to Camilla (confirm PDF permissions; ask for gold, passages, identities) | any time | 15 min | **Ledio** sends; **Camilla** supplies |
| 4d | Declaration (same commit and sha as the gate fixture's G), KRI run, Zoom pack | 4a gates, 4.0, her material; Case 1: the fixture is drawn before 1.9's merge and the declaration is committed within 7 days of the draw; Case 2: fixture drawn after 1.9 (G = N) or after 3 (G = N plus PT) | ½ day | **Camilla** |
| 4e | Endpoint R and G on independent passages (250 per endpoint to confirm); tooling amendments first | 4e amendments, ≥ 250 passages per endpoint, not overlapping exclusions; G also needs the B-freq table matching G | 1-2 days + tooling | **Camilla** |

Expert answers that can change this plan:

* Werning: mark damage instead of dropping? This may re-admit A35 rows via the removal
  manifest.
* Camilla: AES editorial marks → the 22 AES `_` rows (#2).
* Nederhof: Old Egyptian as its own stage.

None blocks parts 1–3. Each would be its own later item.

---

## Addendum 2026-10-26: §4a `signs` as implemented (appended; nothing above is edited)

*From the Opus + Astra review of the KRI tooling branch, before any gate fixture or
KRI run.* §4a defines `signs` as "the same definition as `glyph_key` in
`import_ud_egyptian_pc.py`, imported, not re-written". The checker and the frozen
B-freq baseline both use **`scripts.bfreq_baseline.sign_key`**, which is that
imported `glyph_key` applied after the app's `normalize_hieroglyphs` (so a variant
codepoint such as TLA's Z15B matches the corpus's Z2). Both reviewers accepted this as
an explicit protocol amendment: it errs toward finding overlap, and any C2/P3 hit
that needed the normalisation is marked `normalised-only` in the report. **The gate
fixture's independent adjudicators must use `sign_key` too**, or their C2/P3 tables
will disagree with the checker on variant codepoints and rows will be dropped for
that reason alone. Details: `docs/kri-official-test-tooling-2026-10-26.md`.
