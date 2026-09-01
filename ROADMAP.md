# Roadmap

Written 2026-08-29, after the first trial by an external Egyptologist: the opening of
the biography of Ahmose son of Ibana (Sethe, Urkunden IV, 1), pasted as Unicode
hieroglyphs. The tool produced 4–5 errors on one line; a general-purpose chatbot made 2
on the same input. Every error was reproduced locally and traced to a mechanism, a full
audit of the codebase followed, and then a second, independent verification pass
re-measured every number in the first draft of this file. Where the verification
overturned a claim, the corrected figure is given and the original is noted.

The phases are ordered so each one makes the next measurable: the model retrains on
whatever Phase 0 lets it see, the segmentation work in Phase 1 depends on those
recovered rows, and the evaluation work in Phase 4 locks the earlier phases in place.

## What the trial exposed

Query (with the paste's own spacing): `𓆓𓂧 𓆑𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏼 𓂋𓍿 𓀀 𓏼𓎟𓏏`

| | reading |
|---|---|
| tool returned | `ḏd ḏdf =ꞽ n n.t r(m)ṯ =ꞽ nb.t` |
| correct (corpus convention) | `ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t` — "he says: I speak to you, all mankind" |

The corpus writes suffix pronouns as separate `=x` tokens (10,567 tokens start with
`=`), so the target output is `ḏd =f`, not `ḏd=f`.

**The key verified finding: the whole line is recoverable from the current corpus with
zero fallbacks.** Segmented the way TLA segments —
`𓆓𓂧 𓆑 𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏥 𓂋𓍿𓀀𓏥 𓎟𓏏` — the model returns
`ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t` with every group attested (`𓆑`→`=f` 3,878/3,907;
`𓀀`→`=ꞽ` 595/601; `𓏏𓈖𓏥`→`=tn` 18×). This is not a coverage gap. It is a
segmentation problem end to end.

Traced causes, in order of damage:

1. **Segmentation trusts whitespace.** Sign groups are `normalize_hieroglyphs(query).split()`,
   so the paste's accidental spacing became the analysis. *(Correction: the first draft
   said `𓂋𓍿𓀀` is attested 26× as r(m)ṯ. 26 is the number of rows containing that
   substring; as an exact group it is attested once. The fix is the same — split
   `𓆑𓆓𓂧` into `𓆑 | 𓆓𓂧` and merge `𓂋𓍿 𓀀 𓏥` — but the evidence is the
   massively attested short groups, not the long one.)*
2. **The unattested-group fallback is order-blind** (glyph-set Jaccard), so *f-ḏd-d*
   borrowed the snake-word *ḏdf* at 0.75 similarity. Its tie-break iterates a `set`,
   so the reported source group differs between runs.
3. **Standalone A1 reads `=ꞽ` on a 0.99 prior.** *(Correction: this prior is right.
   595 of 601 standalone A1 groups in the corpus are `=ꞽ`. The error was that
   whitespace detached A1 from `𓂋𓍿`; once segmentation is fixed there is nothing to
   demote.)*
4. **No Unicode variant folding**: the paste's plural strokes are U+133FC, the corpus
   mostly uses U+133E5 (1,763× vs 7×) — visually identical, never matched.
5. **Coverage** — *(Correction: largely withdrawn.)* Urk. IV is not in the subset, but
   `=ṯn` written `𓏏𓈖𓏥` **is** attested 18× (as `=tn`, TLA's Late Egyptian
   convention). The only remaining gap is a transliteration-convention difference
   (`=tn` vs `=ṯn`), not a spelling gap.

## Phase 0 — Data integrity — DONE 2026-08-29

Everything downstream retrains on this, so it goes first. Also includes one 10-minute
production fix that does not belong anywhere else.

- [x] **Stop shredding `<g>…</g>` markup** in `app/data/normalizer.py:14-16,39`. TLA
      encodes signs without Unicode codepoints as inline markup; `NON_HIEROGLYPH_RE`
      turns every character of it into a space. Verified damage, in two layers:
      - **813 rows (6.4%) skipped** by the reading model (`reading_model.py:124`) and
        sign index (`signs.py:80`) — 787 from `<g>`, 26 from variation selectors
        (U+FE00/FE02) splitting a group mid-way.
      - **981 further rows are *not* skipped but train truncated groups**: 1,929 `<g>`
        tags sit inside a multi-glyph token (e.g. `𓅓<g>D77</g>`), so `𓅓` silently
        learns the reading of *m*+D77. This is larger than the skip count and was
        missed by the first audit.
      - 5 sign-index keys are literally `<g>E198</g>` etc. because `signs.py:78` falls
        back to raw `hieroglyphs` when the normalised string is empty.

      Simulated fixes: one placeholder token per `<g>…</g>` → skipped rows 813 → 39;
      deleting the markup outright → 378 (worse — standalone `<g>` tokens vanish and
      shift alignment). Use a placeholder, keep it out of glyph-set similarity (or 586
      distinct sign IDs collapse into one "glyph"), absorb variation selectors into
      the preceding glyph, and report the residual count at load instead of a silent
      `continue`.
- [x] **NFC-normalise before folding.** No `unicodedata` import exists in the repo.
      150 `transliteration_gold` rows are non-NFC (all decomposed `h`+U+0331 vs 1,256
      precomposed `ẖ`); 0 in hieroglyphs/mdc; 21 in translation. Impact on matching is
      small (3 distinct tokens merge), but the order matters: `normalize_transliteration`
      (`normalizer.py:70`) only recognises precomposed `ẖ`, so a decomposed `ẖnm`
      currently folds to `hnm` instead of `khnm`. NFC must run first. (`i̯` has no
      precomposed form and correctly stays decomposed.)
- [x] **Fold variant codepoints; strip format controls.** Sign-equivalence table for
      Z2/Z15A/Z15B plural strokes (U+133E5 1,763× / U+133FB 30× / U+133FC 7× /
      U+133FD 7×), V014/V015, and friends. `HIEROGLYPH_RE` (`normalizer.py:12`)
      currently *keeps* quadrat joiners U+13430–1345F inside a group; the corpus
      contains zero, so a paste from a layout-aware editor can never match — strip
      them from queries, and treat a query consisting only of format controls as
      empty rather than as a glyph query with empty groups.
- [x] **Repair the lossy transliteration fold — with two keys, not one.**
      `canonical_reading` (`suggestions.py:80-81`) = `normalize_mdc(normalize_transliteration(…))`
      maps ꜣ/ꜥ→a, ḥ→h, ḫ/ẖ→kh, and `normalize_mdc` (`normalizer.py:55`) deletes ꞽ, `=`,
      `.`, `(`, `)`. 256 sentence-level keys merge ≥2 distinct readings (confirmed)
      — but most of those are *editorial* variants the fold exists to merge
      (`nḫt`/`nḫtꞽ`, brackets: 1,092 pairs; dots: 234). The genuinely harmful merges
      are ꜣ↔ꜥ (85 pairs), ḥ↔h (`hr`≡`ḥr`, 986 tokens), ḫ↔ẖ, ṯ↔t, ḏ↔d, and `=`
      deletion (`n`≡`=n`; `=ꞽ` folds to the empty key `''`). 683 token merges survive
      after stripping only brackets/punctuation — that is the real consonant loss.
      Design: a **strict key** that is injective on the consonant skeleton (never
      merges those pairs, never deletes ꞽ or `=`) for grouping and support counts, and
      a **loose display key** that still absorbs brackets and dots. Retune suggestion
      weights and re-run the benchmark in the same change — support counts shift.
- [x] ~~Stop lower-casing MdC~~ — **withdrawn.** The `mdc` column contains 0 uppercase
      letters; it is an importer-generated ASCII fold, not real MdC, so case carries no
      information on the corpus side. Stopping the lower-casing would break user-typed
      `Htp` against the all-lowercase column. Revisit only if a real MdC column is
      ever imported.
- [x] **Fix the reading-model cache key.** `load_reading_model` (`whyptology_app.py:140-148`)
      is keyed by `len(df)` and re-parses the CSV from disk (0.49 s) instead of using
      the loaded frame. A same-row-count re-import keeps a stale model. Key on a
      content hash and pass the frame in.
- [x] **Delete the search log** (moved here from Phase 3 because it is a 10-minute
      production fix). `retrieval_runs` is written on every search
      (`whyptology_app.py:675-684`, `repo.py:208-210`: 1 INSERT + 1 SELECT, raw
      query, no cap, no length limit) and **is never read anywhere** in app/, scripts/,
      or tests/. Remove the two `log_retrieval` calls; drop the table in a later
      migration. Not "retention" — deletion.

Done when: the loader reports the residual misaligned-row count (target ≤ 39, each one
listed), no row trains a truncated group, a variant-codepoint query matches its
canonical twin, and the strict key never merges two readings that differ in a
consonant, ꞽ, or `=`.

**Result (2026-08-29):** misaligned rows **813 → 0** — better than the ≤ 39 target,
because `⟦⟧` editorial brackets are deleted rather than spaced and a bare Gardiner
token (`V31Aa`) is treated like markup. Placeholders are deterministic PUA codepoints
(hash + probe; 3 hash collisions resolved, 587 distinct IDs). The reading model now
trains on 12,772/12,772 sentences (was 11,959); the loader attaches an
`AlignmentReport` and logs it. `canonical_reading` is now the strict key; the loose
form is kept for display/ASCII matching. Competitive benchmark unchanged
(0.05/0.10/0.55/0.75); deduplicated sign-reading eval (400 queries) top-1 exact
0.080 → 0.085, top-1 useful 0.748 → 0.768 — no regression, a small lift from the
recovered rows. On the trial paste the variant fold alone turned `n n.t` into
`n =tn`; the remaining errors are segmentation (Phase 1). 25 tests added in
`tests/test_phase0_data_integrity.py`; suite 75/75. *(The first draft said "0 dropped rows" and "no two distinct
readings share a key" — the first is not achievable without inspecting ~39 source rows,
and the second would defeat the display fold's purpose.)*

## Phase 1 — Segmentation and the reading model — DONE 2026-08-29

- [x] **Resegmentation lattice: spaces are hints, not truth.** Dynamic programming over
      spans where attested groups form arcs; unattested spans carry a penalty; the
      Viterbi score arbitrates. An unspaced paste currently collapses to one 16-glyph
      unattested group and returns an empty reading marked `unreadable`.

      **Central design risk, verified:** `_emission` (`reading_model.py:157-162`)
      gives log P = 0.0 to any group attested once with one reading, and applies no
      support penalty. So on the cleanly grouped query, `𓈖𓏏𓈖𓏥` (attested 1×
      as `(ꞽ)ntn`) beats the split `𓈖 | 𓏏𓈖𓏥` (2,772× and 18×) — the output gets
      *worse*: `ḏdf ḏd (ꞽ)ntn r(m)ṯ nb.t`. A lattice whose arcs are "attested groups"
      will systematically prefer long singleton groups over well-attested splits on a
      formulaic corpus unless arc weight includes attestation count (e.g. smoothed
      log-count or a Dirichlet prior). Build this in from the start.
- [x] **Order-aware fallback similarity** in `ReadingModel.nearest_known_group`
      (`reading_model.py:197-217`): glyph bigrams or sequence overlap rather than set
      Jaccard; re-measure the 0.5 threshold; make the tie-break deterministic (sort
      the candidate set — it currently iterates a `set`, so output depends on
      `PYTHONHASHSEED`). *Demoted from High to Medium:* on Camilla's line the fix is
      split-preferring segmentation (`𓆓𓂧`+`𓆑`), not a better fallback; `𓆓𓂧𓆑` vs
      `𓆓𓂧𓆑𓏛` is a legitimately close, order-consistent match that bigrams would
      not reject.
- [x] ~~Classifier vs. suffix pronoun for A1~~ — **reframed.** The 0.99 prior for
      standalone `𓀀`→`=ꞽ` is correct for this corpus. Do not demote it. The
      classifier case is handled by the lattice preferring the attested merge
      `𓂋𓍿𓀀𓏥` when the neighbouring spans support it. Keep as a regression case,
      not a modelling task.
- [x] **Segmentation editor in the UI**: show detected groups as chips the user can
      split and merge, document that spaces are hints, show the runner-up segmentation
      when scores are close. `tests/test_normalizer.py:25-28` pins whitespace-as-boundary
      and must be rewritten deliberately, not "fixed" when it fails.

Done when: the messy paste, the cleanly grouped paste, and the unspaced paste all read
`ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t` with every group attested and zero fallbacks — the
current model already produces exactly this given TLA-style segmentation, so the
target is proven reachable. *(The first draft's target `ḏd=f ḏd=ꞽ` is not the corpus's
token format, and its claim that `=ṯn` must be disclosed as unattested was wrong.)*

**Result (2026-08-29):** `app/services/segmentation.py` — a semi-Markov lattice over
attested sign groups with a Good-Turing-discounted unigram group model (count of 1 →
0.39), the user's spaces as weak hints (+0.5 kept / −1.0 crossed), and a 6-nat-per-glyph
cost for unattested spans. Measured by `scripts/run_segmentation_eval.py` on 845
held-out sentences (twins excluded): boundary **F1 0.856 unspaced / 0.866 scrambled,
exact-sentence 31% / 33%**, against 0.669 / 6% for trusting the paste's spaces. The
singleton discount decides the `(ꞽ)ntn` case as predicted but moves the aggregate by
< 0.003; the unattested-span penalty is the weight that matters (sweep in the code).
The trial paste, the by-word grouping and the fully unspaced string all read
`ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t` with zero fallbacks — pinned as three tests on the
real corpus. Fallback similarity is now ½ glyph-set + ½ glyph-bigram Jaccard with a
0.4 threshold (precision 27.8% → 29.5%, coverage 99.5% → 97.7%; table in the code).
Workspace: chips for the proposed groups, an editable spacing field that overrides
them, a note saying where the paste was regrouped, and the as-pasted reading as
runner-up when within 8 nats. Corpus parallels are retrieved on the regrouped signs.
Suite 93/93.

## Phase 2 — Ranking and suggestions — DONE 2026-08-29

- [x] **Order-sensitive glyph signal** in `app/retrieval/scorer.py`. Confirmed: every
      surviving glyph signal is set-based (`:309-311` Jaccard, `:315-323` Tversky,
      `:324-326` whole-string equality); `fuzzy.py:9` and `tfidf.py:38` read only
      `mdc_norm`, which is `""` for glyph input. **14** permutation-collision groups
      (first draft said 9; 24 if multiplicity is also ignored). Nuance: twins tie only
      when the query is a *third*, unattested order — then the exact column is
      all-zero, dropped at `:376`, and its 0.20 weight renormalised away. Repetition
      confirmed: `𓊢𓂝 𓊢𓂝 𓊢𓂝` scores the single-group row at 1.000. Also the two
      glyph set signals disagree about candidate length (Jaccard vs surplus-penalised
      Tversky). Fix: token-level sequence similarity over sign *groups*
      (`token_sort`/LCS), **not** `fuzz.ratio` on the raw codepoint string, which
      ignores group boundaries and over-rewards shared prefixes. Keep rows 1105/4763
      and the 3× repetition as regression fixtures.
- [x] **Renormalise the suggestion layer — and retune in the same change.** For glyph
      input **56%** of the weight mass is structurally zero (`translit_overlap` 0.20,
      `char_similarity` 0.16, `exact_or_near` 0.12, plus `reading_similarity` 0.08
      whenever there is no reading order; `suggestions.py:37-44, :271-280`). *Correction
      to the first draft:* the effect is **compression, not collapse** — a perfect glyph
      match gets confidence 0.376, top-1 confidence over 40 glyph queries spans
      0.282–0.374, and the ordering is mostly intact (support+lemma flipped the top-1
      in 13/100 leave-one-out queries, never when the exact row was present).
      `lemma_density` (`:240-243`) is `min(rows_with_lemma,5)/5` — effectively a second
      support count. Naive renormalisation raises support's share from 8% to 18%, the
      opposite of the intent; retune weights together with the strict key from Phase 0.
- [x] **Honest empty state.** `retrieve_top_k` (`retrieval.py:73`) always returns k
      rows; a junk query `𓀀 𓀁 𓀂 𓀃 𓀄` yields three cards at 0.273/0.231/0.231. Floor
      on **raw evidence** (shared sign groups ≥ n, or glyph IDF before renormalisation),
      not on `final_score`, which is renormalised per query and not comparable across
      queries. Surface glyph signals in `evidence.py:42-44` — glyph hits currently print
      `fuzzy=0.00 | tfidf=0.00 | token overlap=0.00`. Also: for a glyph query 12,763 rows
      tie at 0 and `sort_values` is not stable, so ranks past the last positive score
      (and suggestions 2–3 for short queries) are arbitrary — use a stable sort.
- [x] **Delete the dead metadata block instead of debugging it.** *(Replaces the first
      draft's "bug sweep".)* `deity_norm`, `offering_items_norm`, `formula_type_norm`
      are empty for all 12,772 rows, so `deity/formula_type/formula_slot/offering/
      recipient/aesthetic` — 0.30 of the weight — never activate and are always
      dropped at `:376`. The hyphenated-key bug, the ASCII-vs-transliteration bug, and
      the `aesthetic_bonus` 0.03×0.03 are all real but unreachable. NaN poisoning is
      latent (needs an all-NaN column, which the loader's `fillna` prevents). `+=`
      then `break` at `:240` is not a bug. The synthetic query candidate
      (`suggestions.py:313-331`) is behind `include_query_candidate`, False at every
      call site — dead. Reverse-alphabetical tie-break (`:350-357`) is real and common
      because confidence is rounded to 3 dp before sorting. Delete the block or
      populate the columns; fix the tie-break.
- [x] **New (missed by the first audit):**
      - Mixed glyph + Latin input is silently double-scored: `contains_hieroglyphs`
        routes to glyph mode while `normalize_mdc` keeps the Latin remainder, so both
        signal sets fire (appending ` wad` to an exact glyph query dropped it from
        1.000 to 0.732). Warn or strip.
      - Empty-vs-empty degeneracy: `fuzz.ratio("","")=100`, cosine of two empty strings
        = 1.0, and `exact_match_candidates` matches `mdc_norm == ""`. Safe today only
        because 0 rows have empty `mdc_norm`; the first imported row without a
        transliteration becomes a universal 1.0 hit for every glyph query. Guard it.
      - `mean_score` (`suggestions.py:225`) uses raw `final_score` while
        `relative_score` is pool-normalised — the two mix scales.
      - Duplicate corpus rows count as support twice (once in `support`, again in
        `lemma_density`).
      - `top_k` plumbing: button label uses `settings.top_k` (`whyptology_app.py:648`),
        results show `head(max(top_k,5))` (`:664-666`), suggestions hardcode `top_n=3`
        (`:673`), UI pool is 25 while every eval script uses 50 — so support counts
        and `relative_score` differ between what was tuned and what ships.
      - The Tversky surplus penalty (commit `7cd0256`) also applies to
        `glyph_idf_overlap_score` (0.50 of glyph mass) for ≥3 sign *groups*; its effect
        on glyph ranking has never been measured — the only glyph eval predates it.

Done when: rows 1105/4763 no longer tie for a third-order query, the 3× repetition
scores below the exact match, a junk query returns "no attested parallel", and the
**sign-reading eval with duplicate strings removed** shows no regression. *(The first
draft said "re-run the frozen evals" — those are transliteration-only and cannot see a
glyph change. The sign eval's two result files disagree, top-1 exact 0.342 vs 0.080
after dedup; only the deduplicated number can arbitrate.)*

**Result (2026-08-29):**
- Order signal: `glyph_order_score` = LCS over sign-group sequences / query length
  (rapidfuzz at C speed via a group→char encoding), weight 0.25 of the glyph mass.
  The permutation fixture (rows 1105/4763) no longer ties for a third order; a 3×
  repetition scores 1/3, not 1.0. Stable sort ends the arbitrary zero-score tail.
- Suggestion layer renormalises over structurally live signals (mirroring
  `combine_scores`) and glyph queries get their own similarity/exactness signals in
  the vacated slots: an exact glyph match now scores ~0.9 instead of 0.376.
  `mean_score` is pool-normalised; identical duplicate rows count as one attestation;
  ties break alphabetically ascending.
- Honest empty state: retrieval floors on raw evidence (shared sign groups / shared
  tokens), returns empty instead of k rows, and the UI says "no attested parallel".
  The evidence line now names the glyph signals (`sign IDF overlap · sign order`)
  instead of printing `fuzzy=0.00`.
- The dead metadata block (deity/formula/offering/recipient/aesthetic — 0.30 of the
  weight on columns empty for all 12,772 rows) is deleted, not debugged.
- New degeneracies fixed: Latin residue in a glyph paste is ignored for matching
  (was: dropped an exact match 1.000 → 0.732, now flagged in the UI); a row with an
  empty transliteration can no longer become a universal fuzzy/tfidf match; the
  suggestion layer receives the *resegmented* grouping, so both layers reason about
  one segmentation; UI pool is 50 to match the eval scripts; suggestions honour
  `top_k`.
- Measured: deduplicated sign-reading eval (400 leave-one-out glyph queries)
  top-1 useful 0.768 → **0.803**, top-3 useful 0.833 → **0.850**, MRR 0.797 → 0.823,
  top-1 exact 0.085 → 0.088. Competitive (transliteration) benchmark: useful-family
  0.55/0.75 unchanged, MRR 0.633 → 0.642; one already-contaminated top-3 exact hit
  (COMP_020) moved below rank 3 under the normalised mean — accepted, since that
  metric is spent (11/20 twins) and both live metrics are flat-to-up.
- Also in this change: `RetrievalRun` model removed;
  `scripts/drop_retrieval_runs_table.py` drops the production table (dry-run by
  default, `--yes` to execute). Suite 120/120 plus a 300-query fuzz harness
  (`tests/test_pipeline_fuzz.py`) covering hostile and corpus-derived inputs with
  determinism checks.

## Phase 3 — Performance and the free-tier database — DONE 2026-08-30

Measured against a local SQLite bootstrap; the production URL was not touched.

- [x] **Cache the interactive hot spots.** `build_sign_index` is called bare at
      `whyptology_app.py:1233` — 0.41 s `iterrows` per Signs-page widget change. Theme
      CSS is read from disk every rerun (`:135`). `load_corpus` is `st.cache_data`
      (`:151`): the pickled frame is **11.1 MB** (first draft: 7.9), `pickle.loads`
      costs 26 ms per rerun, and each concurrent session holds a **~28 MB** copy —
      the real cost is memory, not CPU. Retrieval never mutates `df` in place, so
      `cache_resource` is safe today; leave a comment saying so.
- [x] **Cut database round-trips.** Verified counts per rerun: Workspace **10**
      SELECTs (`load_annotation_state` in `review_common.py:104-115` calls
      `get_latest_for_example` + `list_for_example`; `repo.py:167-169` implements
      "latest" by re-running the full history query — the same SELECT twice per row,
      re-fired on every keystroke in a note field). Home and Projects: **2** queries
      each — `list_all_annotations` (`repo.py:171-184`) pulls **every annotation ever
      written**, no LIMIT, to compute "latest" in Python; this is the query that grows
      without bound. Reviews: **4** (the export CSV is built twice, eagerly,
      `review_common.py:192-195`). Fix: one batched `WHERE example_id IN (...)` with
      SQL `DISTINCT ON`/window for latest; lazy download. **Do not TTL-cache** the
      annotation reads: after a save the reviewer's own annotation would show as
      missing until the TTL expires, unless every save path calls `.clear()`.
- [x] **Gate the annotation write path — name the mechanism.** No auth; any visitor
      inserts 11 unbounded `Text` fields (`whyptology_app.py:532-559`); `status` is
      free text and the FK is not enforced on SQLite. Streamlit exposes no visitor IP
      and session-state counters reset on refresh, so "rate-limit" has nothing to key
      on. Realistic options: a shared reviewer secret in `st.secrets` entered once per
      session, or an "expert mode" toggle that reveals the form. Cap field lengths at
      the model. (The search log is deleted in Phase 0.)
- [x] **Precompute the query-independent half of search.** A search takes **0.40 s**
      end to end. `tfidf.py:36-41` is misnamed — it computes plain char-n-gram cosine
      with no IDF — and rebuilds all 12,772 Counters per query (~50% of time).
      `document_frequencies` runs at `scorer.py:291` always and `:308` for glyph
      queries (so "twice" holds only for glyph input). `tokenize_query` ran **63,862**
      times in one query (~5× per row). **5** full copies of the 48 MB frame
      (`fuzzy.py:8`, `tfidf.py:37`, `retrieval.py:37`, `exact.py:8`, `scorer.py:281`)
      and **3** sorts (first draft: 2), the first two discarded on merge. The
      `exact_bonus` `apply(axis=1)` (`retrieval.py:57-65`) is 10% of search time for
      a boolean `exact.py` already computed. `st.rerun()` after search (`:685`) makes
      every search cost two full reruns. Precompute Counters, token sets and document
      frequencies once in `load_corpus` (check RSS first — 12,772 Counters is tens of
      MB); eliminate the copies and dead sorts, which is the cheaper, bigger win.
- [x] **Degraded read-only mode — split `load_corpus` first.** Zero `except` clauses
      around DB calls (only `try/finally` session closes). Because `ensure_corpus_ready`
      runs *inside* the cached `load_corpus` (`:151-158`), an unreachable database
      raises `OperationalError` at module level (`:1477`) and kills **every** page,
      including Corpus and Signs which need no DB. `db.py` sets `pool_pre_ping`,
      `pool_size=5`, `pool_recycle=300` but no `connect_timeout` — a hung Neon endpoint
      blocks forever rather than failing. Split CSV load from DB bootstrap, wrap the DB
      half, set a connect timeout, banner on failure. Wrapping without splitting would
      cache a frame with no `id` column and every later save would fail with the
      misleading "run import_examples" error at `:534`.
- [x] **Memory budget.** One process is **270 MB** RSS after corpus + DB + reading
      model + sign index, before Streamlit's own ~100–150 MB; plus 28 MB per session
      and 5 × 48 MB transient copies per search. Two or three simultaneous searches
      can plausibly exceed the 1 GB Community Cloud container. The copy elimination
      above and `cache_resource` are the fix; measure before and after.
- [x] Residual per-rerun reads after commit `65ec840`: `list_all_annotations` full
      history on Home/Projects/Reviews; `list_examples_by_ids` fetching all 41 columns
      twice on Reviews; the legacy `streamlit_app.py` still uses the old full-download
      path if anyone runs it against production (so its deletion in Phase 5 is also a
      Phase 3 item). Cross-container first-seed race: both see `count == 0`, second
      hits `uq_examples_source_text_sentence` and crashes at boot — only possible on a
      brand-new empty DB; note, don't prioritise.

Done when: a Workspace rerun issues ≤1 DB query, the Signs page responds instantly to
the selectbox, a search completes in well under 0.2 s, and killing the DB yields a
banner on the Workspace and a fully working Corpus/Signs page.

**Result (2026-08-30):**

| | before | after |
|---|---|---|
| Workspace rerun, 5 parallels | 10 queries | **1** |
| Workspace rerun, 50 parallels | 100 queries | **1** |
| Home / Projects (per sidebar click) | 2 each, full-table scan | **1** each, `count`/`distinct` |
| Reviews page | 4 queries + CSV built twice | **3**, export built on demand |
| Text search | 293 ms | **95 ms** |
| Corpus frame per session | ~28 MB copy each | shared (`cache_resource`) |

- **Round trips.** `get_latest_for_example` is one `LIMIT 1` query (it used to re-run
  the full history query, so every visible row cost two); `load_annotation_states`
  fetches every visible parallel's history in a single `IN (...)`; Home and Projects
  use `count(distinct)` / `distinct` instead of pulling every annotation ever
  written; `list_latest_annotations_only` selects the newest ids in SQL.
- **Caching.** Corpus in `cache_resource` (one shared frame, no per-session pickle);
  theme CSS, sign index and the new search index cached per corpus signature. The
  post-search `st.rerun()` is gone — every search used to cost two full script runs.
- **Precomputation.** `SearchIndex` holds document frequencies and character n-gram
  vectors, built once (0.22 s, ~60 MB) instead of per query; the tokenizer is
  `lru_cache`d (one search called it ~64,000 times); retrieval makes **one** frame
  copy instead of five and no wasted sorts. Verified identical rankings and scores
  with and without the index.
- **Write gating.** Optional shared reviewer passphrase (`reviewer_key` in Streamlit
  secrets or `REVIEWER_KEY`); with none configured the app stays fully open, so
  local development is unchanged. All annotation fields are clipped to 2,000
  characters, empty readings are rejected, and a failed save shows a message instead
  of a traceback.
- **Degraded read-only mode.** `load_corpus` is split into a database-free CSV load
  and a separate id-attachment step, and the DB helpers raise `DatabaseUnavailable`.
  Verified end to end against an unreachable database: **all six pages render**, the
  banner appears, and a search still returns `ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t`.
  Previously an outage raised inside the cached loader at import time and took down
  every page, including the ones that need no database. `connect_timeout=10` stops a
  black-holed endpoint from hanging the script thread.
- Suite 138/138 (18 new Phase 3 tests); competitive benchmark unchanged
  (0.05/0.05/0.55/0.75, MRR 0.6417); 311-query fuzz harness still deterministic.

## Phase 4 — Evaluation and tests — DONE 2026-08-30

- [x] **A benchmark of real pastes.** Confirmed: all 45 benchmark queries across three
      files contain 0 hieroglyph codepoints; the only glyph eval
      (`run_sign_reading_eval.py`) uses corpus `hieroglyphs` verbatim, i.e. TLA
      spacing. Add Urk. IV 1 three ways (messy paste, cleanly grouped, unspaced) with
      expected `ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t`, plus glyph pastes from PDFs and
      other tools.
- [x] **Close the twin-leak window — it is more than half the benchmark.** Measured
      with the builder's own metric (loose-token Jaccard ≥ 0.9) over all 12,772 rows:
      **11 of 20** competitive items have a twin outside the 2,000-row pool
      (`build_competitive_ambiguity_benchmark.py:44-51,138-144,176-178`) — 7 at 1.00,
      4 string-identical; all 20 targets sit at index ≤ 1,949 so the guard saw none of
      them. `build_ambiguous_benchmark.py:67` has **no guard at all** (`df.head(20)`);
      10 of its 20 items have twins. The guard is O(n²) `iterrows` (~163 M comparisons
      at full size — hours); build a token inverted index or block by length first.
      Re-running re-selects all 20 items and breaks comparability with every number in
      `CORPUS_SCALING_REPORT.md` — **version the benchmark file**, don't overwrite.
      `run_sign_reading_eval.py:75-97` already has an `--exclude-duplicates` pattern
      to reuse.
- [x] **Stable importer IDs — by content hash, with a production migration.**
      `import_tla_dataset.py:360-362,421` builds `TLA_EARLIER_{n}` from output
      position; `--limit` default 100 at `:450`. Corrections: the dedupe at `:425-431`
      can never fire (its key contains the generated ID); only the empty-transliteration
      skip shifts IDs, and 0 rows hit it today; the 12,773 → 12,772 drop happens later
      in `build_examples_from_real.py:97-99` (`TLA_EARLIER_2390`, a one-sign name).
      **The raw parquet has no TLA sentence ID** — columns are hieroglyphs,
      transliteration, lemmatization, UPOS, glossing, translation, two dates — so
      "use the TLA ID" is not an option; hash **all** columns (4 benchmark targets have
      string-identical twins, so hashing text alone collides). `source_ref`
      (`…parquet#row=N`, `:369`) survives skips and can seed the hash. Changing IDs
      invalidates `expected_source_text_id` in 4 benchmark files,
      `expert_review_sheet.csv`, `tests/test_frontend_smoke.py:108,115-116`, and —
      critically — **the `examples` table already seeded in Neon**, whose `annotations`
      attach by DB `id`; bootstrap seeds only when empty, so prod keeps old IDs while
      the CSV changes. Write the migration before changing the importer.
- [x] **Tests for what actually broke.** Suite: 52 passed in 7.4 s wall / 4.1 s CPU.
      No `conftest.py`. No test for non-TLA spacing, variant codepoints, or
      `suggest_top_readings`; the only ranking test is
      `test_idf_overlap_prefers_rare_shared_tokens`. `test_normalizer.py:25-28` pins
      the current whitespace behaviour and must be rewritten in Phase 1. Add the
      Phase 2 regression fixtures (rows 1105/4763, 3× repetition, junk query).
- [x] **Clear the dead weight and the stale results.** `scripts/run_eval.py:4` imports
      `evaluate_leave_one_out`, which no longer exists — ImportError. `phase3_eval_queries.csv`
      expects text ID `MORHQGR3SNBI3KHAF6YOW5WLL4`, 0 occurrences in the corpus, yet the
      committed `phase3_eval_results.csv` shows hits — stale numbers published in the
      repo. `run_ambiguous_suggestion_eval.py` never excludes the target (its own note
      at `:138`); its committed results file is likewise misleading. `tuning_benchmark_80.csv`
      has zero references anywhere; `scorer.py:56`'s "80-query benchmark" comment points
      at nothing. **New:** `scripts/download_all_sources.py:4` imports `datasets`, which
      is in neither `requirements.txt` nor the venv — the corpus is *not* regenerable
      from a clean clone as README claims. Delete or regenerate each; add `datasets`.

Done when: a fresh clone can re-run every quoted number, no committed results file
shows a number the current corpus cannot reproduce, and the eval suite contains at
least one query the pipeline didn't generate for itself.

**Result (2026-08-30):**

- **The twin leak is closed and quantified.** Rival detection now runs against the
  **whole corpus** via an inverted token index — 29 seconds, not the hours the O(n²)
  scan would have taken — and the rebuilt benchmark is **versioned, not overwritten**
  (`competitive_ambiguity_eval_queries_v2.csv`).

  | | v1 (shipped) | v2 |
  |---|---|---|
  | items with a twin ≥ 0.9 anywhere in the corpus | **11 / 20** (6 identical) | **0 / 20** |
  | top-1 useful family | 0.55 | 0.55 |
  | top-3 useful family | 0.75 | **0.70** |
  | MRR | 0.64 | **0.60** |

  v1 is kept so the numbers already quoted in `CORPUS_SCALING_REPORT.md` stay
  reproducible; a test asserts that v2 has no twins *and* that v1 still does.
  The builder also gained a **signal floor**: a query of one ubiquitous token (`z`)
  is unanswerable by construction, and v1 shipped three such rows.
- **A benchmark of real pastes** — `data/benchmarks/expert_paste_queries.csv` plus
  `scripts/run_expert_paste_eval.py`, which exits non-zero on any regression.
  Eight queries the pipeline did not generate for itself: the expert's paste
  verbatim, the same line grouped by word, unspaced, and TLA-spaced; a layout-editor
  export with real U+13431 quadrat joiners; a paste with a line number attached; a
  genuinely NFD transliteration; and signs the corpus does not contain. **8/8 pass**,
  and this is now the first benchmark that could ever have caught the trial's
  failure class.
- **Stable importer ids.** `content_id()` hashes every source column (not just the
  transliteration — four rows are string-identical there) into
  `TLA_EARLIER_<hash>`, behind `--stable-ids`. Verified: ids are unchanged between
  `--limit 50` and `--limit 200`, and a test shows a skipped upstream row renumbering
  every positional id while content ids stay put. **Not switched on for the shipped
  corpus**: renaming ids would orphan every annotation in the production database,
  so `scripts/migrate_example_ids.py` does the rename in place (matching rows by
  content, refusing to run unless the mapping is one-to-one) and must be run first.
- **Dead weight removed**: `run_eval.py` (crashed on import), the whole phase-3
  chain (`run_phase3_eval.py` + its queries, which expected ids from the retired
  importer and scored zero forever), and the committed result files that published
  numbers the current corpus cannot reproduce (`phase3_eval_results.csv`,
  `ambiguous_suggestion_eval_results.csv`) and the orphaned `tuning_benchmark_80.csv`.
  The ambiguous eval now opens with **"SANITY CHECK — not an accuracy measurement"**.
  `datasets` added to requirements, so "regenerable corpus" is true from a clean
  clone.
- **`tests/conftest.py`** added: imports resolved only by accident before, via
  `tests/__init__.py` happening to put the root on the path.
- Suite **161/161** (23 new).

## Phase 5 — Product and licence polish — DONE 2026-08-30

- [x] **Delete `app/ui/streamlit_app.py`** (512 lines, 0 mentions of TLA/BY-SA, 0
      cache calls). *Correction:* do not move its benchmark tab — it is the only
      consumer of the phase-3 chain that scores zero, and the only caller of
      `app/services/evaluation.evaluate_benchmark`, which can go with it.
- [x] **Attribution in every distribution.** Confirmed: the CSV export
      (`review_common.py:192-195`, `export_reviewed.py:81-83`) includes
      `transliteration_gold` and `translation` — TLA-licensed text, not just user
      annotations — with no notice. **Three more copies the first draft missed:** the
      committed `data/processed/reviewed_annotations_export.csv`; the committed (and
      iCloud-evicted, 0 B on disk) `data/raw/real_examples_worklist.csv` — a full
      12,773-row second copy of CC BY-SA data that `DATA-LICENSE.md` does not name;
      and `DATA-LICENSE.md:9` names a font file (`GentiumPlus-Regular.subset.woff2`)
      that does not exist (real: `GentiumPlus-Translit.woff2`). The sidebar credit
      links to TLA and the deed but not to the modification record (`DATA-LICENSE.md`)
      — §3(a) wants that reachable; also add the warranty-disclaimer pointer
      (§3(a)(1)(A)(iv)). Sidebar is `initial_sidebar_state="auto"` (`:74`) and there is
      no footer anywhere; Streamlit has no footer slot, so the credit must be appended
      to every `render_*`. A comment line in the CSV breaks `pd.read_csv` for
      consumers — prefer a `licence` column or a README in a zip.
- [x] **UI paper cuts — two withdrawn.** Confirmed: the explorer renders the same rows
      twice (HTML table `:1097-1102`, then cards `:1112-1135`); the ✓ badge at
      `:724-735` is unconditional while the fallback warning appears only below `:760`;
      the `top_k` mismatch (see Phase 2 — it is in the search handler, not the tabs).
      **Withdrawn:** "word-by-word table shifts pairs after `<g>` markup" — the table
      splits the *raw* string, which is 100% aligned (0 mismatched rows); markup is
      merely displayed literally. **Withdrawn:** "corpus page number outlives its
      bounds" — reproduced with `AppTest`: Streamlit re-keys the `number_input` when
      `max_value` changes and resets to page 1; no bug. Also: `st.markdown(f"**{…}**")`
      at `:874-890,:962` renders corpus text as Markdown unescaped — not XSS (Streamlit
      sanitises), but a `*` or `_` in a translation mangles the display.
- [x] **Urkunden IV — needs a new data source, not stable IDs.** *Correction:* the
      Hugging Face parquet the importer reads has **no text/title/ID column** and
      contains **9** New-Kingdom-dated rows out of 12,773; searching for Ahmose son of
      Ibana (`ꞽꜥḥ-ms`, `ꞽbꜣn`, `ḏd =f ḏd =ꞽ`, "Ahmose"/"Ibana") returns 0 hits.
      `data/raw/aes` holds the AES corpus after all — see the Phase 5 correction; the
  earlier "empty directory" reading was iCloud eviction, not a missing download.
      Importing Urk. IV means a new source (TLA/AES export, or M.-J. Nederhof's
      sign-aligned St Andrews corpus — the very PDF Camilla linked in her trial
      document), a new importer, and an updated `DATA-LICENSE.md` citation. Size:
      Large, and independent of Phase 4's ID work. Treat as its own project after
      Phases 0–4.
- [x] **Docs.** README says `data/raw` is "~465 MB, regenerable"; actual is 4.2 MB,
      `.gitignore` says 600 MB, and regeneration fails on the missing `datasets`
      dependency. Reconcile after Phase 4.

Done when: one entrypoint, attribution travels with every copy of the data including
the two committed CSVs, and the docs describe the repo that exists.

**Result (2026-08-30):**

- **One entry point.** `app/ui/streamlit_app.py` deleted — 512 lines that rendered no
  TLA attribution at all, a licence-noncompliant second front door in a public repo.
  `app/services/evaluation.py` went with it (its only remaining consumer). A test
  asserts nothing imports either.
- **The licence now travels with the data.** `LICENCE_NOTICE` is attached as a
  `licence` **column** (a `#` comment header would break `pd.read_csv` for whoever
  receives the file) to both export paths — the in-app download and
  `scripts/export_reviewed.py` — and to the committed
  `reviewed_annotations_export.csv`. It names the attribution, the licence and its
  URL, the link to the original, the fact of adaptation, and the §5 warranty
  position.
- **Attribution reaches the viewer on every page.** The sidebar credit is collapsed
  by default on a phone, so a mobile reader could have browsed the whole corpus
  without seeing whose work it is. A footer now renders on all six pages; a test
  checks each one.
- **`DATA-LICENSE.md` corrected and completed**: the font filename matched no file on
  disk (`GentiumPlus-Regular.subset.woff2` → `GentiumPlus-Translit.woff2`); every
  copy of corpus data in the repo is now listed, not just `examples.csv`; the §5
  warranty disclaimer is stated.
- **Paper cuts.** The ✓ badge was unconditional — it claimed every sign group was
  attested even when readings had been borrowed or nothing could be read; it is now
  ✓ / ~ / ! with a tooltip. The corpus explorer rendered `filtered.head(30)` as cards
  *below* a paginated table, so page 5 showed page 1's cards; the card view now
  follows the current page and is collapsed by default.
- **Urk. IV — feasibility re-checked, and a correction.** The audit reported
  `data/raw/aes` as an empty directory. It is not: it holds the **AES corpus**
  (Ancient Egyptian Sentences, 100,000+ sentences, CC BY-SA 4.0, with Unicode
  hieroglyphic encodings and AED lemma IDs). The earlier reading was an artifact of
  iCloud having evicted the file contents — the same environment problem that caused
  the move to `~/Projects`. README's "~465 MB" for `data/raw` is likewise correct.

  However, Ahmose son of Ibana is **not** in the 16 AES subcorpora present here
  (the historical-biographical one included is `bbawhistbiospzt`, Late Period), so
  the conclusion stands for a different reason: Urk. IV needs a source the repo does
  not have. **Importing AES itself is the natural next project** — it would multiply
  the corpus roughly eightfold and is exactly the coverage problem an expert keeps
  hitting — but it needs its own importer, schema mapping and licence citation, so it
  is out of scope for a polish phase.
- Suite **177/177** (16 new).

## Pre-release test pass — 2026-08-30

Run after all six phases, before the second expert trial. Everything below is
reproducible from the repo.

**Automated.** Suite 178/178. Expert-paste eval 8/8. Fuzz harness widened to
**1,011 queries × 2 runs (fresh seed), zero failures, fully deterministic.**
48 concurrent searches over the shared corpus frame agree with serial results and leak
no columns into it. All six pages render with the database unreachable. Interactive
checks on every page (Signs selectbox, Corpus search + pagination, Reviews filter,
Home metrics). Annotation round-trip: save → persisted → shown as latest → listed on
Reviews; reviewer gate hides saving when a key is configured.

**One real bug found and fixed** (`8f1ff45`): after Phase 3 removed the post-search
`st.rerun()`, the tabs kept reading `results` / `suggestions` / `top_row` captured
*before* the search wrote them. Sign-by-sign still worked (it re-reads the query), but
Suggested readings, Corpus parallels, Analysis and Source text stayed on their
placeholders until a **second** click. Confirmed on the live site before fixing;
confirmed fixed on the live site after (auto-redeployed 10:09). A frontend test now
asserts every tab is populated after one click. This is exactly the class of bug an
expert trial would have hit first.

**New expert-style trials on texts the tool was never tuned on** —
`data/benchmarks/new_expert_style_trials.csv`: five real sentences from the Old
Kingdom, First and Second Intermediate Periods and Middle Kingdom, spacing scrambled
the way a paste is. **27 of 33 tokens correct, every group attested, zero borrowed
readings.** Two lines perfect (an Osiris–Unas offering line and a Middle Kingdom
sentence, both from unspaced or mis-spaced input). The three imperfect readings are
not errors: in each the tool chose the *majority* attested reading of a group whose
editors themselves disagree (`𓁷𓄣` → `ḥr(.ꞽ)-ꞽb` 9× vs the gold's split; `𓆑𓏭` →
`=fꞽ` 70× vs `=f` 3×; `𓍿𓈖` → `=ṯn` 90× vs `ṯn(ꞽ)` 6×) and showed the alternatives.
A separate **held-out** run (target row removed from the model) on four more sentences
read a fully unspaced Old Kingdom offering formula 9/9 and reported once-attested
spellings as unreadable rather than guessing — the honest behaviour.

**Ready for the second trial.** Known, documented limits an expert may hit:
once-attested spellings held out of the corpus read as unreadable (by design); Urk. IV
and most Dynasty 18 material are not in this corpus (see the AES note under Phase 5).

## Both known limits closed — 2026-08-30

The two limits documented before the second trial are no longer open.

**Coverage.** `tla_late.parquet` was already downloaded and never imported: 3,606 rows,
every one with hieroglyphs, 2,993 in the New Kingdom. Imported as a second corpus
(3,601 after dropping 5 sentences already present): **12,772 → 16,373 rows, New
Kingdom 9 → 2,998.**

AES was evaluated first and rejected on evidence: 101,796 sentences but **only 23
contain any hieroglyph** — its "mdc" field is ASCII transliteration, not sign codes —
so it cannot support the sign-based reading this tool exists for. The Demotic parquet
has no hieroglyphs at all. This corrects the Phase 5 note, which assumed AES would be
usable once found.

Three things the merge required, each a small instance of a Phase 0 lesson:
- **Suffix marker unified.** Earlier writes `=`, Late writes the Leiden `⸗`. Merged
  untouched, the same sentence read `n =tn` or `n ⸗tn` depending only on which corpus
  attested that spelling more often. Declared in `DATA-LICENSE.md` per §3(a)(1)(B),
  with the Late Egyptian citation.
- **Nested `<g><g>ID</g></g>`** unwrapped, and a non-glyph run *directly between two
  signs* (a stray Latin letter, a doubled parenthesis) deleted rather than spaced.
  Those were the only 3 misalignments in the new corpus; the merged corpus is
  **16,373/16,373 aligned**.
- **Importer parameterised** (`--language-stage`, `--id-prefix`) so one schema serves
  several TLA corpora without mislabelling a stage or colliding on ids.

**What the New Kingdom rows actually are.** Of the 2,998 New Kingdom rows, **55 fall
in the Dynasty-18 window and 2,938 are Ramesside (Dyn. 19–20)**; with the 9 already
present, the merged corpus holds **64 Dynasty-18-dated sentences**. So "New Kingdom
9 → 2,998" is true but must not be read as "Camilla's period is now covered": Urk. IV
is early Dynasty 18 and in Middle Egyptian, while the new material is largely later
and in Late Egyptian. It still helps her — recurring phrases like `ḏd =ꞽ n =tn` now
have New Kingdom parallels — but Dynasty 18 proper remains thin.

**Honest measurement.** On the *same* 20 questions the score is **unchanged** —
top-1 useful 0.55, top-3 0.70, MRR 0.60 on both corpus sizes. The added material is a
different language stage: it neither helps nor hurts Earlier Egyptian questions. A v3
benchmark rebuilt on the new corpus scores 0.70/0.85/0.758, but that is a *different,
easier sample* and must not be quoted as an improvement. The gain is coverage, and it
is large where it matters: New Kingdom parallels for the trial line **0 → 8**, for
`ḏd =ꞽ n =tn` **0 → 9**, for a New Kingdom phrase **1 → 17**.

**Unattested groups are no longer a dead end.** `related_attested_groups` reports which
attested groups share an unreadable group's signs, with readings and counts, in the
Evidence column and under the warning — for example `𓆞𓊖𓊜𓎱𓏤 is not attested. Groups in
the corpus sharing its signs: 𓊖𓏏𓏤 = nʾ.t (22×) · 𓉺𓏤𓊖 = ꞽwn.w (1×)`. It proposes
nothing; it reports what the corpus holds, which is the line between evidence and
invention.

**Database sync.** `scripts/import_examples.py` gained a fast path — read existing keys
in one query, bulk-insert only what is missing. Growing the corpus cost **5 queries
instead of 16,373**; the per-row upsert stays behind `--refresh-existing`.

Suite **190/190**; expert paste eval 8/8; the trial line still reads correctly from all
five spacings with zero borrowed readings.

> **Production note:** the deployed database holds the original 12,772 rows. The app
> works unchanged — the new rows are searchable and readable — but annotations cannot
> be attached to them until the sync is run once against production:
> `DATABASE_URL='postgresql://…' python scripts/import_examples.py`

## Dynasty 18 coverage — the JSON was hiding the corpus (2026-08-30)

The Phase 5 note said AES was unusable: 101,796 sentences, 23 with a hieroglyph. That
was true of the **JSON export** and wrong about the corpus. The same download ships a
**relANNIS export** carrying a `hiero_unicode` annotation the JSON drops — **241,414
tokens of it**. Read from there, AES yields **14,824 sentences whose hieroglyphs align
one-to-one with their transliteration**, including `bbawamarna`, which is Dynasty 18.

`scripts/import_aes_relannis.py` imports it. After dropping 5,001 sentences already
present from TLA, **9,823 rows were added: 16,373 → 26,196, all 26,196 aligned.**
New Kingdom rows **2,998 → 5,629**, including **494 Amarna** sentences.

**The transliteration had to be converted, and the conversion was validated rather
than assumed.** AES writes the yod `j` where TLA writes `ꞽ`, the morpheme separator as
a comma, the suffix marker `≡`, plural `,pl`, and capitalises proper nouns. Left alone,
the sign model would read `=j` and `=ꞽ` as two different readings of the same sign.
1,342 sentences occur in **both** corpora independently, which makes a test set: the
conversion reproduces the TLA form exactly for **85%** of them and **disagrees on a
letter in none**. The remaining 15% differ only in editorial judgement between two
editions (`bš(ꜣ)` vs `bšꜣ`, `ḥtp-ḏi̯-nswt` vs `ḥtp-ḏi̯ nswt`) and were left as AES has
them. Declared in `DATA-LICENSE.md`, with the AES/AED-TEI citation and its ~30 editors.

Also kept honest: periods stay coarse (`Old Kingdom / First Intermediate Period`)
because AES does not claim a single one, and `language_stage` is left
`Unspecified (AES)` rather than guessed from an era label.

**Regression:** the trial line still reads `ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t` from all
four spacings with zero borrowed readings; expert paste eval 8/8; suite 195/195.

**Still honest about the limit:** Amarna is *late* Dynasty 18 and Urk. IV is *early*
Dynasty 18 in Middle Egyptian. The gap is much smaller than it was — 494 Dynasty-18
sentences where there were 64 — but Ahmose son of Ibana's own text is still not in the
corpus, and no source we hold contains it.

## Checked and clean

For the record, the verification pass re-confirmed: no SQL injection (SQLAlchemy Core/ORM
with bound parameters throughout `repo.py`); no XSS (every user- or corpus-derived value
inside `unsafe_allow_html=True` passes through `html.escape` — ten blocks checked); no
secrets in any of the 14 commits (only placeholder URLs; `.env` never tracked);
100% glyph/reading alignment in the raw CSV (0 mismatched rows — every misalignment is
introduced by the normaliser); the FastAPI app in `app/api` is not deployed (it re-reads
the CSV per request and has no auth — harmless while undeployed, a footgun if exposed);
`session_state` does not grow; the in-process bootstrap is race-free; test suite 52/52
in 4.1 s CPU.

## 2026-09-01 — state of play after the second expert trial

A second Egyptologist (Sophie) tried the tool on a phone and on the web with the same
sentence in two notations and got nothing both times. Everything below traces back to
that message.

**Fixed and live** (`egyptology-corpus-retrieval.streamlit.app`, commit `e0532ab`):

- The query fold deleted every Egyptological letter (`ꜥḥꜥ.n stẖ` reached the search as
  `n st`); the index was built from a column all 9,823 AES rows ship empty (37% of the
  corpus unreachable); "MdC" named a scheme that was never implemented; and a bare text
  area only sends its value on blur, so one tap on the search button did nothing.
  One fold (`search_fold`) on both sides, one parser (`app/data/query.py`) for
  hieroglyphs / Unicode / MdC / ASCII, decided by corpus evidence; the box and the
  button are one form. The yod (`ꞽ`/`j`/`i`) is one letter to the search.
- 5,369 aligned sentences from `phiwi/bbaw_egyptian` (CC BY-SA 4.0), converted from
  Gardiner codes and to TLA convention → **31,565 rows**.
- The Helsinki AES+Ramses lexicon (CC BY 4.0, 84,532 spellings) as a labelled fallback
  for groups this corpus never attests, and as segmenter cut points at weight 0.2:
  unseen-group accuracy 0.287 → 0.346, unspaced segmentation F1 0.854 → 0.931,
  expert-paste gate 8/8.
- Ten UI fixes (example queries, `?q=` deep links, live heading, ephemeral-storage
  gating, copy-able glyphs, quiet palette, translation label, short tabs, credits,
  Unicode evidence tokens). v4 benchmark on the final corpus: top-3 useful **0.95**.
- 261 tests; `scripts/verify_release.py` is the one-command gate.

**Measured but not done — the row count question.** The BBAW export has 100,736 rows;
65,226 have no hieroglyphs. After dedup **46,888** of those would be new. They would
serve transliteration search only. At 78,453 rows: query 0.32 s → 1.01 s, and peak
memory **622 MB → 1,110 MB** in a fresh process — over Streamlit Community Cloud's 1 GB.
So the import is one command (`--include-text-only`, dry-run done) but cannot ship on
the current host without a memory diet, or at all without a bigger one.

**Still true:** annotations are wiped on every reboot (the `DATABASE_URL` secret still
points at container SQLite — runbook in DEPLOYMENT.md, user-only steps). Late Egyptian
is 14% of the corpus and no open source exists for it except the Ramses corpus
(CC BY-NC-SA, one email to Liège). Middle Kingdom literary text exists machine-readably
at St Andrews (unlicensed; Nederhof emailed 2026-09-01).

## Plan for 2026-09-02

In this order; each step has its own measurement and none is started before the
previous one is verified.

1. **Memory diet, cheap half** — drop the nine dead columns at load, categorical dtypes
   for source/period/stage, sparse document vectors (scikit-learn is a dependency), no
   `df.copy()` per query. Target: 78k rows under ~800 MB peak and a query under 0.6 s.
   Measure with the fresh-process script from 2026-09-01 (in the session notes), before
   and after, at 31,565 and at 78,453 rows.
2. **Loader: "no hieroglyphs" is text-only, not misaligned.** The alignment report must
   keep counting only rows that *have* signs and don't line up; a text-only row is a
   different, legitimate state. Add the count of text-only rows to the report and a test.
3. **Import the text-only BBAW rows** (`--include-text-only --append`), and the 13,383
   TLA Demotic rows the same way, with `language_stage` set so both are filterable and
   the Demotic never mixes into hieroglyphic sign statistics. Re-run v4 (queries stay
   valid; numbers will move — record them as v4 at 78k, not as a new version), the
   segmentation eval, and `verify_release.py`.
4. **Hosting decision: Hugging Face Spaces** (free CPU basic: 2 vCPU, 16 GB; Streamlit
   SDK; the corpora already live on HF). Prepare in-repo: Space README metadata,
   `app_file`, a GitHub Action mirroring `main` to the Space. User-side: create the
   Space and a write token. Known cost: free Spaces sleep after ~48 h idle and cold-start
   in ~1–2 min — either accept, keep-alive, or the cheapest paid tier. Keep the
   Streamlit URL alive with a one-line redirect for the people who already have it.
   Annotations still need a remote DB on either host.
5. **Neon** (user-only): rotate the leaked `neondb_owner` password, confirm the quota
   reset, set `DATABASE_URL`, reboot, verify with `scripts/check_database.py`.
6. **When Nederhof answers**: importer for the St Andrews files (`corpus.xml` →
   `texts/*.xml` → `resources/*Hi.xml` + `*Tr.txt`), with its own Hannig → TLA
   convention table verified on 𓀀 𓂋 𓇋 before trusting it; Urkunden citations as ids;
   Stauder 2013 §7.2 datings as an *attributed* `period_source` column, never
   overwriting TLA periods.
7. **Email Liège / Rosmorduc** for a CC BY-SA grant on the Ramses corpus, mentioning that
   the Helsinki lexicon derived from it is already in use under Helsinki's CC BY release.

Not planned: photo/OCR input (wait for Sophie's answer), machine translation of any kind.
