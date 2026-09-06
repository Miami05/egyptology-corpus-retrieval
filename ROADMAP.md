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

## Nederhof's reply — 2026-09-02

Mark-Jan Nederhof answered the 30 August email. Four criticisms, each checked against the
corpus, and a permission with a condition:

1. **`.PL` is treated as distinct from `.w`.** True: TLA writes `sr.PL` (1,973 rows), AES
   and BBAW write `sr.pl`/`sr.w`; the fold gives `srpl` vs `srw`, so a search for `sr.w`
   misses every `.PL` row and the suggestions show `nṯr.PL` / `nṯr.w` as two readings.
   181 stems occur both ways in the corpus. Same class of bug as the yod.
2. **Proper nouns are not normalised**, so "alternatives" are one name in different forms.
   True; partly fixable with variant-marker normalisation, fully only with lemma IDs.
3. **Segmentation is often wrong** and should come from a model of how the writing system
   works (determinatives close words, phonetic complements follow their sign). He saw the
   pre-lexicon build (unspaced F1 0.854; now 0.931), but the point stands: the lattice is
   a unigram over attested groups and knows nothing about sign function.
4. **We delete the Unicode format controls** (U+13430–1345F). They carry the quadrat
   structure of a paste — the segmentation hint we are missing. Keep them as hints for the
   segmenter; strip them only for matching.

**Permission:** "happy for you to use the St Andrews corpus for non-commercial purposes",
informally, by email; no licence on the pages. Non-commercial and informal means the St
Andrews rows can **never enter `data/processed/examples.csv` or the public repository**
(CC BY-SA cannot carry NC material). They live in a separate, non-redistributed file
loaded at runtime, labelled "used with permission of Mark-Jan Nederhof, non-commercial,
not redistributable", each row cited to him and to the edition. Confirmed the same day in
his second mail: **CC BY-NC-SA 4.0** ("sounds about right"), and the intended handling
("sounds perfect"). He also stated his corpus follows Hannig's conventions (no z/s
distinction, no dot before the feminine t), pointed to Rosmorduc's automatic-transliteration
papers and his own sign-function research, and asked whether the site is academic
research. Reply drafted as Email 3 in `docs/permission-requests.md`.

## Plan for 2026-09-02 (revised after Nederhof's reply)

In this order; each step measured before the next starts.

1. **Plural marker.** Fold `.PL`/`.pl` to `.w` in `search_fold` and in
   `strict_reading_key` (his argument: for masculine nouns they are the same thing).
   Test: `sr.PL`, `sr.pl`, `sr.w` share a token; a query `sr.w` returns `.PL` rows;
   suggestions no longer list them as two readings. Re-run v4 and record.
2. **St Andrews importer** (`scripts/import_st_andrews.py`): `corpus.xml` → `texts/*.xml`
   → `resources/*Hi.xml` (RES/MdC → Unicode via the existing Gardiner mapper) +
   `*Tr.txt` (`;`-separated transliteration/translation blocks, Hannig ASCII → TLA via a
   per-source table verified on 𓀀 𓂋 𓇋 first). Urkunden/edition citations as ids.
   Output to a **private path outside the repo** (gitignored `data/private/`), loaded by
   the app when present. Own attribution in the UI footer and DATA-LICENSE ("used with
   permission…"). Stauder 2013 §7.2 datings as an attributed `period_source` column.
   Email his clarification question the same day; do not wait for the answer to build.
3. **Format controls as hints.** Before normalisation, read U+13430–1345F joiners in a
   paste as quadrat boundaries and pass them to the segmenter as (weak) hints; keep
   deleting them for matching. Measure on the expert-paste set and the segmentation eval
   with a `--no-format-hints` switch.
4. **Loader: text-only is a state, not a misalignment**, and the **memory diet, cheap
   half** (dead columns, categorical dtypes, sparse vectors, no per-query copy).
   Baseline: 31,565 rows → 622 MB / 0.32 s; 78,453 → 1,110 MB / 1.01 s; cap 1 GB.
5. **Import the text-only BBAW rows (46,888 net-new) and TLA Demotic (13,383)**,
   filterable by stage, Demotic kept out of sign statistics; re-run v4 at the new size,
   segmentation, `verify_release.py`.
6. **Hosting → Hugging Face Spaces** (16 GB; sleeps after ~48 h idle). Repo side: Space
   README metadata + sync Action; user side: Space, token, secrets. Redirect note on
   the Streamlit URL. Annotations still need Neon on either host.
7. **Neon** (user-only): rotate the leaked password, check quota, set `DATABASE_URL`,
   verify `DURABLE`.
8. **Email Liège / Rosmorduc** for a CC BY-SA grant on Ramses (mention the Helsinki
   lexicon already in use under Helsinki's CC BY release).

Research items opened by his mail, not scheduled: proper-noun normalisation beyond
markers (needs lemma IDs); a segmentation model with sign-function knowledge
(determinatives, phonetic complements, quadrat structure).

Not planned: photo/OCR input (wait for Sophie), machine translation of any kind.

## Plan evaluated 2026-09-02 — five agents read the code before anything was built

Each item of the plan above was checked against the repository and, where it mattered,
against the live sources. What changed:

**Order.** `1 fold → 4 loader + memory → 5 imports → 2 St Andrews → 3 format hints`.
Items 6 (HF Spaces) deferred, 7 (Neon) today, 8 (email Liège) today.

1. **`.PL` → `.w` fold — confirmed, ~2–3 h.** Corpus counts: `.PL` 2,842 tokens (TLA),
   `.pl` 4,873 (AES/BBAW), 277 stems attested both ways (not 181). Trap: **1,127 tokens
   are written `.w.PL`/`.w.pl`** (`sr.w.PL`), so a naive replace makes `srww`; the regex
   must be `(?:\.w)?\.pl(?![^\W\d_])` → `.w`, applied in `normalize_transliteration`
   (after lowercasing, before the yod rule) and in `strict_reading_key` before the dots
   are dropped. `.PL.t` never occurs. Camilla's gate is untouched (no plural in it).
   **The feminine `.t` is already ignored on both keys** (dots deleted), so Hannig `nbt`
   already matches Berlin `nb.t`. **z/s:** 271 variant groups across sources (`zꜣ` 634 /
   `sꜣ` 239), but genuinely distinct lemmas would merge (`zꞽ` "man" / `sꞽ` "she", `ꞽz`
   "tomb" / `ꞽs` particle) — fold z→s in `search_fold` only, as a separate measured step
   after v4 is re-run on the plural fold alone; never in the strict key. Must run before
   the BBAW import because `dedup_key` uses `search_fold` (65 near-duplicates otherwise).
2. **St Andrews importer — bigger than planned, ~13 h, and one thing the roadmap got
   wrong.** Verified on the live files: `corpus.xml` lives at `texts/corpus/corpus.xml`,
   ~94 texts, not all with hieroglyphs (Sinuhe is translit+English only). `*Hi.xml` is
   **RES, not MdC** (`insert[s](I10,D46)-I9-…`, `cartouche(...)`, `[rotate=270]`), one
   `<segment>` per Sethe line; a ~60-line sign-sequence tokenizer is needed, the BBAW MdC
   parser does not apply, the Gardiner→Unicode table does. `*Tr.txt` is the "lite"
   format: phrases separated by blank lines, `;` between transliteration and translation,
   `<N>` line anchors *inside* words, `^` before names, HTML entities. **Alignment is at
   the manuscript-line level, and phrases cross lines** — PhilologEg aligns at display
   time. So the importer cannot produce word-aligned rows without an aligner (2–5 days,
   research). Import two honest shapes: phrase rows (translit + English, no glyphs) and
   line rows (glyphs + the translit between anchors, flagged "line-level"). Camilla's
   paste is retrievable from the line rows: coord 2 decodes to `𓆓𓂧 𓆑 𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏤𓏤𓏤 …`.
   Hannig→TLA: `A a j H x X S T D` → `ꜣ ꜥ ꞽ ḥ ḫ ẖ š ṯ ḏ`; `y` stays; `s` and undotted
   `t` **left as written** (a wrong dot in a gold column is worse than a known absence).
   Loading: the global "Licensed CC BY-SA 4.0" sentence in `corpus_credit_html` would
   mislabel NC rows — credits must become per-source. Private rows are concatenated
   **after** `ensure_corpus_ready`/`attach_db_ids`, so they never enter the DB, the
   exports or the API. Delivery to the deployed app: a **private Hugging Face dataset
   repo + read-only token in a secret + `hf_hub_download` at boot**, host-agnostic; the
   Space repo itself is public and hub-sync deletes out-of-band files.
3. **Format-control hints — last, and it cannot be measured on current data.** Exactly
   one deletion site (`normalizer.py:183`); corpus has **0** controls, all raw sources
   have 0, the segmentation eval has 0, and the only test row with controls (PASTE_005)
   has joiners *inside* a word, so a hard "no cut inside a quadrat" rule drops the gate
   to 7/8. Suffix pronouns (`=f`, `=tn`) share quadrats with the preceding sign, so the
   hint is soft at best. BBAW's MdC `:`/`*` operators (22.5% of within-word adjacencies)
   can be emitted as U+13430/13431 for an **upper-bound** measurement; realistic input
   arrives only with St Andrews RES. Display with quadrat layout needs Nederhof's
   hierojax (GPL JS) in an iframe per card — defer.
4. **Memory — the plan's diagnosis was wrong about where the bytes are.** Measured:
   `document_vectors` (one `Counter` of char n-grams per row) is **216 MB at 31k and
   584 MB at 78k**; everything else is flat (lexicon 59, reading model 92, sign index
   55, frame 105→232). Dropping the 9 dead columns saves **4 MB** (empty cells share one
   `""` object; `memory_usage(deep=True)` overstates). **Categorical dtypes save 0 MB**
   (the C parser already interns) **and break the explorer** (`fillna("")` raises on a
   Categorical) — dropped from the plan. The real fix is a **sparse CSR matrix**
   (sklearn `CountVectorizer(analyzer="char", ngram_range=(2,4))`, L2-normalised; cosine
   as one matmul): −520 MB and 0.4 s → 0.011 s. Simulated 78k rows with CSR + streamlit
   imported: **816 MB** — fits under 1 GB with ~180 MB headroom; +Demotic +St Andrews
   ≈ 900 MB, nominal; Ramses does not fit. Text-only state: `loader.py:81-85` `not s`
   → count as `text_only_rows`; `ReadingModel.sentences_skipped` needs the same split;
   `example_payload` in bootstrap indexes dead columns directly (KeyError if dropped).
5. **Imports.** BBAW text-only reproduces 46,888 net-new; `--append` also writes
   `bbaw_rows.csv` (do not commit). Demotic parquet has **no hieroglyphs column at all**;
   `import_tla_dataset.py` needs `--script-type Demotic`, a Roman Period range (dates run
   to +250), `--limit` raised from 100, and an append/dedup path. "Kept out of sign
   statistics" is automatic (no glyphs → never fitted) but Demotic tokens **do** enter
   `mdc_frequencies` and change IDF for every query; the workspace has no stage filter,
   only the explorer does — a score mask, not a filtered frame (filtering rebuilds all
   vectors per query). Re-runs at 78k: v4 ≈ 1 min, `verify_release.py` ≈ 5–6 min.
6. **HF Spaces — premise gone, defer.** Verified 2026-09-02: `sdk: streamlit` was
   deprecated 2025-04-30 (Docker template now); **Docker/Gradio Spaces need a PRO account
   ($9/month) since July 2026** — free accounts get static Spaces and ZeroGPU Gradio
   only. CPU Basic is still 2 vCPU / 16 GB, sleeps after 48 h. Nothing in the app breaks
   there (env-var secrets, `REVIEWER_KEY` name, port 8501, user 1000). Decision is a
   spending one and is not needed until something beyond item 5 has to ship.
   DEPLOYMENT.md lines 128–171 are stale on these facts.
7. **Neon — runbook correct, no code change.** Egress fix verified in `list_example_keys`
   + regression test; no real credential in git history (placeholders only), so rotation
   is the whole remedy. `check_database.py` prints `UNREACHABLE` while the quota is
   still exhausted — that is the signal to wait.

## Final plan, week of 2026-09-02 (hosting decision: home server, not Hugging Face)

Decided 2026-09-02 after the evaluation above. Ledio wants both Ramses (~71k Late
Egyptian rows) and St Andrews (~14k Middle Egyptian); together they exceed Streamlit
Cloud's 1 GB and HF Docker Spaces now cost PRO. A small always-on PC at home behind a
Cloudflare Tunnel replaces both: no sleep, RAM is whatever the PC has, private data files
sit in a folder on the machine, Neon stays the database.

**Ramses needs no permission email.** The Ramses Transliteration Corpus v2019-09-01
(Zenodo 10.5281/zenodo.4954597) is released CC BY-NC-SA 4.0 (the README in the zip
governs; the Zenodo field saying CC BY 4.0 is wrong). Non-commercial use with attribution
is granted by the licence itself. What it forbids is entering the public CC BY-SA CSV or
repo, so it goes to the same private, non-redistributed path as St Andrews with its own
credit line. A short courtesy mail to Rosmorduc / Liège asking for a CC BY-SA grant is
worth sending (Email 4 in `docs/permission-requests.md`) but blocks nothing.
Ramses is word-aligned (Gardiner codes with `_` word separators + transliteration), uses
`j` for the yod, and its transliteration is *normalised to the expected grammatical form*,
not the actual spelling — record that in `grammar_notes` and DATA-LICENSE.

| Day | Work | Gate |
|---|---|---|
| Wed 09-02 | Send Nederhof Email 3. `.PL`/`.w` fold (`(?:\.w)?\.pl` → `.w` in `normalize_transliteration` + `strict_reading_key`, tests). Neon: rotate password, set `DATABASE_URL`, reboot (user). Download Ramses zip and St Andrews raw files into gitignored `data/raw/`. | suite green, v4 re-run recorded, `check_database.py` → DURABLE |
| Thu 09-03 | Loader: text-only state (`alignment_report`, `sentences_skipped` split, Sign-readings caption). Sparse CSR index replacing per-row Counters; no per-query `df.copy()`; drop dead columns with `example_payload` made tolerant. Measure RSS at 31k and on the 78k dry-run frame. | 78k frame < 900 MB in a plain process; query < 0.4 s |
| Fri 09-04 | Import BBAW text-only (46,888) and Demotic (importer: `--script-type Demotic`, Roman Period range, `--limit`, append/dedup, credit). Re-run v4, segmentation eval, `verify_release.py`. Push; Streamlit Cloud still hosts this size. | v4 ≥ 0.95 top-3 useful, gates 8/8 |
| Sat 09-05 | **Server.** PC: Ubuntu Server, Docker, `cloudflared` tunnel to a domain (or Tailscale Funnel). Repo: `Dockerfile`, `compose.yaml` (restart: unless-stopped, `DATABASE_URL`, `REVIEWER_KEY`, `PRIVATE_DATA_DIR` env), `.dockerignore`, a `deploy.sh` that pulls and rebuilds. Deploy the Friday corpus. Streamlit Cloud gets a "moved to …" banner via a secret; Sophie's link keeps working. | app answers on the new URL over HTTPS; annotations persist across a container restart |
| Sun 09-06 | **Private data path.** `data/private/` gitignored + `git ls-files` test; loader reads any CSVs there and concatenates *after* `ensure_corpus_ready`/`attach_db_ids` (never into the DB/exports); per-source credit lines replacing the global CC BY-SA sentence; DATA-LICENSE section. **Ramses importer** → `data/private/ramses.csv` (Gardiner→Unicode via the BBAW mapper, `_` = word boundary, `j`→`ꞽ`, `source=Ramses`). Load on the server, measure RSS, re-run evals on Late Egyptian queries. | Ramses rows searchable with the NC label; public CSV unchanged; suite green with the private folder empty |
| Mon–Wed 09-07..09 | **St Andrews importer** (~13 h): corpus walk, RES sign-sequence tokenizer, lite Tr.txt parser, Hannig→TLA table checked on 𓀀 𓂋 𓇋, phrase rows + line rows, Stauder §7.2 as `period_source`. Then screenshot the attribution to Nederhof. | Camilla's Urk. IV 1 line retrieves top-1 from the St Andrews line rows |
| after | Format-control hints, measured first as the BBAW upper bound, then on St Andrews RES. Ramses-based Late Egyptian evaluation set. z→s in `search_fold` as its own measured step. | |

### After the server: the four answers to Nederhof, in order of effort

Once hosting is no longer the constraint, the remaining work is the model, not the data.
Each item ends in a number that can be sent to him.

- **A. Language-stage aware evidence (Ledio's idea, 2026-09-02; cheap, ~1 day).** Late
  Egyptian, Middle Egyptian and Demotic spell differently; the segmenter's group counts
  and the suggestion ranking currently pool all stages. Every row already carries
  `language_stage`, so: (i) show the stage of each piece of evidence in the result card;
  (ii) let the user restrict the workspace search to a stage (as a **score mask**, not a
  filtered frame — filtering rebuilds all vectors per query); (iii)try per-stage group
  counts in the segmenter for pastes where the user has declared a stage. Measure on the
  v4 benchmark split by stage, and on the Ramses-derived Late Egyptian set. Nobody asked
  for this; it addresses the same root cause as his proper-noun and segmentation points.
- **B. Format controls as weak segmenter hints (~½ day + measurement).** Keep U+13430–1345F,
  pass quadrat boundaries as a soft penalty on cuts inside a quadrat. Measure the BBAW
  upper bound first (its MdC `:`/`*` operators are 22.5% of within-word adjacencies), then
  on St Andrews RES once imported. Report the number to him either way; a null result is
  a real answer to the open question he posed.
- **C. Sign-function segmentation (~1 week, the actual criticism).** Replace the bare
  unigram over attested groups with a lattice that knows sign *class*: determinatives
  close a word, phonetic complements attach to the preceding sign, logograms stand alone.
  Inputs available without new permissions: Gardiner class from the sign code (already
  parsed in `build_gardiner_table`), the Helsinki spelling lexicon, and the corpus's own
  group statistics. Thot Sign List would be ideal (sign → attested functions) but its
  licence is unstated — one email if this becomes the bottleneck. Gate: Camilla's line
  from all four spacings, expert paste 8/8, unspaced F1 above 0.931.
- **D. Proper nouns / lemma identifiers (~2–3 days).** His second criticism. Variant-marker
  normalisation is partial; TLA lemma IDs are the real fix and are present in the source
  exports. Group name variants under one lemma in the suggestion list.

Then, and this matters more than any of the four: **put it back in front of the experts.**
Camilla offered to retest on a text we have not seen; Sophie's link now works; Nederhof
asked to see the attribution. Annotation persistence (Neon, Wednesday) has to be real
before any of them records a correction.

**Before Saturday (user side):** confirm the PC has ≥ 8 GB RAM and can stay on; install
Ubuntu Server if it is not Linux yet; a domain (≈ €10/yr) plus a free Cloudflare account,
or a Tailscale account; the Neon password rotated so the new server gets a clean URL.

**Emails.** Needed for data: none beyond Nederhof's reply (his files are already
fetchable; his permission is given). Optional: Rosmorduc / Liège (Email 4, courtesy + BY-SA
ask); a follow-up to Werning at BBAW only if no reply by mid-September (not needed for data,
the text-only rows come from the open export). Later leads, not now: Thot Sign List
(licence unknown; would serve the sign-function model Nederhof described), MORTEXVAR,
EgyptianTranslation authors (English).

Superseded by this section: items 6 (HF Spaces) and 8 (email Liège as a precondition)
of the 2026-09-02 plan.

## Nederhof's third mail, 2026-09-02 — what it settles, what it changes

His reply to Email 3 (same day). Checked against his files and tools before touching the
plan; the raw Urk. IV 1 files (`urkIV-001.xml`, `urkIV-001Hi.xml`, `urkIV-001Tr.txt`,
`align/AhmoseSonEbana.xml`) were fetched and read.

**Settled.**
- Licence: "sounds fine". Citation URL he wants used:
  `https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/`. Goes into the per-source
  credit line and DATA-LICENSE alongside his name, CC BY-NC-SA 4.0 and the Sethe/Breasted
  citation from each text's `<collection>` element.
- **Word alignment is not in the data — confirmed by him, and by the files.** Alignment
  is line numbers + `<N>` anchors + the `align/*.xml` precedence files (Urk. IV 1's is
  353 bytes: ten `<prec1/prec2 id1 id2>` segment pairs, nothing finer) + a run-time
  automatic aligner whose output PhilologEg discards. So the two-shape import (phrase
  rows: translit + English; line rows: glyphs + the translit between anchors, flagged
  line-level) is the correct design, not a fallback. Urk. IV 1: 67 RES segments, 160
  phrases. The per-word alignment stays a research item; his 2008b paper and W15-4810
  are the method if it is ever attempted, and he is putting students on exactly that.
- **He calls the corpus RES, not MdC.** The roadmap already said so (item 2 above).

**Changed.**
1. **The RES tokenizer is deleted from the St Andrews importer.** `hieropy` 0.1.9
   (PyPI, 2026-08-28, his own package, GPL-3.0) converts RES to Unicode: tested on all 67
   Urk. IV 1 segments, 67/67 converted, output uses U+13430 (vertical joiner), 13431
   (horizontal), 13433 (insert), 13434, 13437/13438 (begin/end segment). Camilla's line
   comes out as `𓆓𓐳𓂧𓆑𓆓𓐳𓂧𓀀𓈖𓏏𓐰𓈖𓐰𓏤𓐱𓏤𓐱𓏤…` — the insertion in `insert[s](I10,D46)`
   is preserved as U+13433. Estimate for item 2 drops from ~13 h to ~8 h (the lite
   `Tr.txt` parser, the anchor logic and the Hannig→TLA table remain).
   Constraints: (a) **GPL-3.0** — hieropy runs only in the offline import script that
   writes `data/private/standrews.csv`; it never enters `requirements.txt` or the app
   process, so the MIT app and the CC BY-SA data are untouched (converted glyph strings
   are data, not a derivative of the converter). Keep the script under `scripts/private/`
   or outside the repo, and say in its header that it needs `pip install hieropy`.
   (b) `import hieropy` pulls in `tkinter` for its editor; the Homebrew Python 3.12 has no
   Tk. Either `brew install python-tk@3.12` or stub `tkinter`, `tkinterweb`, `tkhtmlview`
   in `sys.modules` before the import (the stub was enough for the 67-segment test).
   (c) Dependencies are heavy (scipy, shapely, pypdfium2, reportlab, fonttools, Pillow):
   one more reason it stays out of the deployed image.
2. **Format-control hints (item B) get real input immediately, not "only after St
   Andrews".** Every St Andrews line row will carry the controls hieropy emits, so the
   measurement runs on his corpus first and the BBAW upper bound becomes the second
   number, not the first. hieropy's `MdcUniConverter` can also turn the BBAW MdC
   `:`/`*` into controls, replacing the hand-written emitter planned for the upper bound.
   Both measurements go in the report to him he asked for.
3. **Sign-function segmentation (item C) has a published model to build on, not to
   invent.** W15-4810 (Nederhof & Rahman, FSMNLP 2015) is exactly item C: sign
   *functions* (phonogram, logogram, determinative, phonetic determinative,
   typographical) as the intermediate layer between signs and letters; N-gram over
   functions interpolated 9:1 with an HMM over function classes; trained on Westcar
   (2,669 words), tested on Shipwrecked Sailor (1,004 words); F1 86.0 baseline → **95.0**.
   Its a-priori knowledge is his annotated sign list (functions of the 1,071 Unicode
   signs, XML at `egyptian/unicode/`), which is the role the roadmap assigned to the
   Thot Sign List. Two consequences: ask him for the sign list's licence (Email 5), and
   design C as "his function lattice fed by our 31k-row group statistics and the
   Helsinki lexicon", which is also the collaboration he offers. His stated weak spot,
   honorific transposition, is where the corpus rows help.
4. **His question — aligned data for segmentation/transliteration — is answerable from
   the survey already done** (memory `open-data-sources-surveyed`). Email 5 lists: TLA
   HF exports, AES, `phiwi/bbaw_egyptian`, AED-TEI, Ramses, Helsinki lexicons, with
   sizes, licences and the one caveat that matters to him: all are word-level by
   whitespace, none is sign-function annotated, and the whitespace alignment is exactly
   where this tool's own errors come from (Camilla's trial). Offer the v4 benchmark and
   expert-paste set as test material.
5. **His idea — "find similar phrases", by edit distance over transcription,
   transliteration or translation — is a new item E, and it is mostly already built.**
   The workspace retrieval *is* phrase similarity over transliteration (char 2–4-gram
   cosine, becoming a sparse CSR index on Thursday). What is missing: the same index over
   the **hieroglyph sequence** (sign n-grams, the corpus has glyphs) and over the
   **translation**, an edit-distance re-rank of the top-k, a result view that shows the
   matched parallel with its source instead of a reading suggestion, and — the part he
   actually wants — **a user's own texts** as an additional private corpus (upload a
   Tr.txt-style file, indexed in session or under the reviewer key, never persisted
   publicly). Cost after the CSR index lands: ~1–2 days. It is the first feature an
   expert has asked for unprompted, and it needs no new data or permission.
   **Thursday's CSR index must be built field-generic** (one function: column → matrix)
   so E is a second call, not a rewrite. E is scheduled after the server, before C.

**Plan deltas (table "Final plan, week of 2026-09-02").**
- Wed 09-02: **not done yet** — the `.PL`→`.w` fold is absent from `normalizer.py`,
  no Ramses/St Andrews raw files are in `data/raw/`. Add: send Email 5 (below).
- Thu 09-03: CSR index takes a column name; measure on `transliteration` first.
- Mon–Wed 09-07..09: St Andrews importer ~8 h with hieropy (private script), then run the
  format-control measurement on the line rows the same week.
- After the server: **E (phrase finder, 1–2 days) → A (stage-aware evidence) → B (format
  controls, St Andrews first) → C (sign-function lattice on his model) → D (lemma IDs).**

**Diagnosis of the repository, 2026-09-02 (before any of today's work).**
- `pytest`: 261 passed in 69 s; tree clean after the run (the benchmark-dirtying fix holds).
- `check_database.py` locally: SQLite, reachable, **26,196 examples vs 31,565 in the CSV**.
  The 5,369 BBAW rows added 2026-09-01 are not in the DB, so in the app they get no `id`
  and the annotation form says "not linked to the project database". Cause: boot calls
  only `ensure_corpus_ready` (empty-table guard, seeds once); `sync_new_examples` exists
  and is cheap (one four-column key SELECT + bulk insert) but is only reached through
  `scripts/import_examples.py`. **Neon has the same gap unless that script was run
  against it.** Fix: run `scripts/import_examples.py` against Neon right after the
  password rotation today, and make `deploy.sh` (Saturday) run it on every deploy; do
  not add it to boot — it would double the key download that caused the egress outage.
- Five stale agent worktrees under `.claude/worktrees/` (~275 MB), branches
  `feat/bbaw-import`, `feat/ui-fixes`, `fix/fold-yod`, `fix/persistence`,
  `worktree-agent-*`: all merged into `main`, zero uncommitted changes. Safe to remove
  with `git worktree remove <path>` and `git branch -d <name>`.
- Last night's roadmap and Email 3/4 edits are still uncommitted.
- `DEPLOYMENT.md` 128–171 still describes HF Spaces as free (known, unchanged).

## Time budget, 2026-09-02 — the whole plan in working days

Effort is focused working days. Two calendar readings: the plan's own pace (one slot per
day) and a spare-time pace (two or three sessions a week), which is the honest one.

**Week 1 — data and hosting (6 days).**

| Slot | Work | Effort |
|---|---|---|
| Wed 09-02 | `.PL`→`.w` fold; Neon rotation + `scripts/import_examples.py` sync; raw downloads (Ramses, St Andrews); send Email 5 | ½ day |
| Thu 09-03 | Loader text-only state; sparse CSR index, **field-generic** (column → matrix) | 1 day |
| Fri 09-04 | BBAW text-only + Demotic imports; v4, segmentation eval, `verify_release.py` | 1 day |
| Sat 09-05 | Home server: Docker, tunnel, `deploy.sh` (runs the DB sync every deploy) | 1 day |
| Sun 09-06 | Private data path, per-source credits, Ramses importer | 1 day |
| Mon–Tue 09-07/08 | St Andrews importer with hieropy (~8 h), then the format-control measurement on his line rows | 1½ days |

**Week 2 onward — the model, in the new order (10–12 days).**

| Item | Work | Effort |
|---|---|---|
| E | Phrase finder: glyph + translation index on the CSR machinery, edit-distance re-rank, parallel-view result card, user's own texts as a private in-session corpus | 1–2 days |
| **Expert round** | Put E and the persisted annotations in front of Camilla (unseen text), Sophie, Nederhof (attribution screenshot + phrase finder). Waiting time, not effort; runs in parallel with C | 0 |
| A | Stage-aware evidence, stage score mask, per-stage group counts; measure v4 by stage | 1 day |
| B | Format controls as soft quadrat hints; St Andrews number first, BBAW upper bound second; send both to Nederhof | 1 day |
| C | Sign-function lattice on Nederhof & Rahman 2015: his function classes, our group statistics, Helsinki lexicon. Gates unchanged (Camilla's line from all four spacings, expert paste 8/8, unspaced F1 > 0.931) | 5 days, research; +2–3 if his sign list is not reusable and a Gardiner-class substitute must be built |
| D | Proper nouns via TLA lemma IDs | 2–3 days |

**Totals.** 16–18 working days. At the plan's pace: data week done 2026-09-08, model items
done around **2026-09-25**. At spare-time pace: data week ends mid-September, model items
run to **late October**. The expert round is scheduled directly after E so their answers
arrive while C is still being built, not after D.

**What moves the date.** (1) C is the only research item; the estimate assumes his sign
list is available — the licence question is in Email 5. (2) The server day depends on the
PC, domain and Neon rotation being ready beforehand (user-side list above). (3) Every
import re-runs v4 (~1 min at 78k) and `verify_release.py` (~5–6 min); budgeted, not a risk.

## Database decision, 2026-09-02 — PostgreSQL on the home server, Neon retired

Ledio's point, once the server exists: run PostgreSQL there instead of Neon. The code is
ready for it — `DATABASE_URL` is normalised to `postgresql+psycopg://` in `db.py` and the
driver is pinned in `requirements.txt` — so this is a `compose.yaml` service and an env
var, not code. The server is also meant to host other projects, which shapes the layout.

**What it removes.**
- The Neon egress quota and the outage class it caused; the "download every boot" worry
  behind `attach_db_ids` becomes a local socket read.
- **Wednesday's Neon rotation is dropped.** Neon only needs to survive until Saturday's
  migration; whatever annotations it holds are exported then. If it is over quota on
  Saturday, `reviewed_annotations_export.csv` plus the local SQLite are the fallback.
- The `EPHEMERAL` state for the deployed app: annotations live in a Docker volume.

**What it adds (Saturday, ~½ day on top of the server slot).**
- `compose.yaml`: `postgres:16` service with a named volume, `POSTGRES_DB=egyptology`, the
  app's `DATABASE_URL=postgresql://…@postgres:5432/egyptology`; `deploy.sh` runs
  `scripts/import_examples.py` (sync) after each pull.
- Migration: `ensure_corpus_ready` seeds the empty table from the CSV on first boot;
  annotations come across via `export_reviewed.py` from Neon → the existing seed path, or
  `pg_dump -t annotations` if Neon is reachable.
- **Backups become ours.** The corpus is regenerable from the CSV; the annotations are
  the only irreplaceable table. Nightly `pg_dump` of the database to a folder that is
  synced off the machine (any cloud drive, or `rclone` to object storage), 30-day retention,
  and one restore test before the expert round. Without this the home server is *less*
  durable than Neon, not more.
- Neon stays only as the Streamlit Cloud database until the "moved to …" banner goes up,
  then the account is closed.

**Hosting other projects on the same PC.** One `cloudflared` tunnel with one ingress rule
per hostname (`egypt.<domain>`, `<other>.<domain>`), each pointing at its own container
port — no reverse proxy needed for the tunnel case; if Tailscale Funnel is chosen
instead, Caddy in front does the same. One shared PostgreSQL container, one database and
one role per project, so a runaway query in another project cannot lock this one's
tables. One compose stack per project in its own folder, each with its own `deploy.sh`;
a shared `backups/` job dumps every database. RAM budget: this app ~1 GB at 78k rows,
Postgres ~200 MB, the rest is the other projects' — the "≥ 8 GB" prerequisite stands.

**Plan deltas.** Wed 09-02 loses the Neon rotation (−¼ day). Sat 09-05 gains Postgres,
migration and the backup job (+½ day). Time budget unchanged in total: still 16–18 days.
DEPLOYMENT.md sections "Making annotations survive" and "What went wrong with Neon" become
history once the server runs; rewrite them Saturday evening, not before.

## Plan re-checked 2026-09-04 — content stands, calendar slides two days

Checked against the repository on Friday 2026-09-04: no commit since 2026-09-01; the
`.PL`→`.w` fold is not in `normalizer.py`; no CSR index, no `text_only_rows`, no
`data/private/`, no Dockerfile; Ramses and St Andrews raw files are not in `data/raw/`;
Email 5 is still marked DRAFT; the five merged worktrees are still there. Corpus 31,565
rows (TLA 16,373 · AES 9,823 · BBAW 5,369); `pytest` 261 passed in 65 s; `hieropy` is in
the local venv only, not in `requirements.txt` (as required). Nothing in the evaluation,
the Nederhof deltas or the database decision is contradicted by the code. What changes is
the dates, and one ordering rule.

**Ordering rule.** The imports (78k rows) must not be pushed to Streamlit Cloud before the
CSR index exists: per-row Counters are 584 MB at 78k and the app would exceed 1 GB. So
`fold → CSR + loader → imports` is a dependency, not a preference. The server is
independent of all three and can take whichever day the PC, domain and Cloudflare account
are ready.

**Re-dated table (same slots, same gates, effort unchanged at 16–18 days).**

| Slot | Work | Gate |
|---|---|---|
| Fri 09-04 | `.PL`→`.w` fold + tests, v4 re-run recorded; send Email 5; download Ramses zip and St Andrews raw files into `data/raw/`; remove the five merged worktrees | suite green, v4 number written down |
| Sat 09-05 | **Server, if the PC is ready** (Docker, `postgres:16` in `compose.yaml`, tunnel, `deploy.sh` running `scripts/import_examples.py` each deploy, nightly `pg_dump`). If not ready: do the Sun/Mon slot instead and the server takes the next free day | app on HTTPS; annotation survives a container restart |
| Sun 09-06 | Loader text-only state; **field-generic** sparse CSR index (column → matrix); drop dead columns with `example_payload` tolerant; measure RSS at 31k and 78k | 78k frame < 900 MB; query < 0.4 s |
| Mon 09-07 | BBAW text-only (46,888) + Demotic imports; v4, segmentation eval, `verify_release.py`; push | v4 ≥ 0.95 top-3 useful, gates 8/8 |
| Tue 09-08 | Private data path + per-source credits + DATA-LICENSE; Ramses importer to `data/private/ramses.csv` | NC rows searchable with label; public CSV unchanged |
| Wed–Thu 09-09/10 | St Andrews importer with hieropy (~8 h, private script), then the format-control measurement on his line rows | Camilla's Urk. IV 1 line top-1 from the line rows |
| after | E → A → B → C → D as in the third-mail section; expert round straight after E | |

At one slot per day the data week now ends 2026-09-10 and the model items around
2026-09-27; at spare-time pace, late October, as before. The Wed 09-02 row of the earlier
table (Neon rotation) and the "Neon stays the database" sentence are superseded by the
database decision above; this table is the current one.

**Still unchanged and still true.** Neon is left alone until migration day (export
`reviewed_annotations_export.csv` first; if Neon is over quota, that file plus the local
SQLite are the fallback). The 5,369 BBAW rows stay unlinked in the deployed app until the
server's first `deploy.sh` runs the sync. `DEPLOYMENT.md` 128–171 (HF Spaces as free) is
rewritten on server day, not before. The 09-02 roadmap and Email 3–5 edits are uncommitted.

**Fri 09-04, done.** `.PL`→`.w` fold shipped: `fold_plural_marker` in `normalizer.py`,
called in `normalize_transliteration` (after lowercasing, before the yod rule) and in
`strict_reading_key` (before the dots are dropped); 6 new tests, suite 267 green. v4
measured on the pre-fold and post-fold code the same hour: top-3 useful 0.95 → 0.95,
MRR 0.800 → 0.808, the one failure (COMP_008) is the same both times; expert paste 8/8
both times. The three eval result CSVs in `data/benchmarks/` had been stale since before
the v4 cut (they listed five failures); they now reflect the current code. `search_fold`
inherits the fold, so `dedup_key` in the BBAW importer now treats `.PL`/`.pl`/`.w.PL`
variants as one row — which is what the Monday import needs. Nine merged branches and the
five worktrees removed; only `main` remains.

**Fri 09-04, raw data landed (gitignored).** Ramses: Zenodo 4954597 →
`data/raw/ramses/ramses-trl/` (VERSION `2019-09-01`; the zip is named 2021-05-29, same
data). README: "released using the CC-BY-NC-SA Creative Common License… acknowledge as
'the Ramses transliteration corpus V. 2019-09-01, University of Liege/Projet Ramses'".
`data/src-*.txt` = Gardiner codes per line, with Ramses-only codes (`Ff1`, `Ff100`,
`SHADED2`, `LACUNA`); `data/tgt-*.txt` = **MdC ASCII transliteration, one character per
token, `_` as word boundary, yod as `i` not `j`** (correction to the plan above: `A a i
H x X S T D` → `ꜣ ꜥ ꞽ ḥ ḫ ẖ š ṯ ḏ`, the same table as St Andrews minus the `j`). Splits:
train 66,693 · val 1,841 · test 2,729 · ctest 2,428 · htest 301 = 74k lines. The 106 MB
`network.h5` was not downloaded. St Andrews: `data/raw/standrews/corpus/` mirrors his
layout — `corpus.xml`, `texts/<Name>.xml` (94), `resources/<Name>Hi.xml` (53 texts with
glyphs, 41 without), `resources/<Name>Tr*.txt` (101), `align/*.xml` (18); 3.3 MB, zero
404s. Still open for today: send Email 5 (user-side).

**Follow-up (found 2026-09-04 while measuring the CSR index): vectorise the fuzzy signal.**
With the cosine step at ~10 ms, the per-query cost of `retrieve_top_k` at 78k is
dominated by the remaining Python loops: `fuzz.ratio(query, value)` over every row in
`app/services/retrieval.py` and the per-row work in `combine_scores`. rapidfuzz already
ships a batch call, `rapidfuzz.process.cdist([query], candidates, scorer=fuzz.ratio,
workers=-1)`, which runs the whole column in C++ and returns one array — same scores,
one call, no new dependency. Gate: `fuzzy_score` identical for every row (assert equality
on the full corpus for a handful of queries, like the CSR equivalence test), v4 and paste
gate unchanged. ~½ h; do it with the phrase finder (item E), whose glyph and translation
indexes make the same per-query loop three times as expensive otherwise.

**Fri 09-04, evening — the Sunday slot done two days early.** Two Sonnet workers in
isolated worktrees, reviewed and merged (8155ab7, d5d2e39). (1) Text-only row state:
`AlignmentReport.text_only_rows`, `ReadingModel.sentences_text_only`, neutral caption on
the Sign readings page; the current corpus reports 0 / 0. (2) Sparse CSR n-gram index:
`NgramIndex` in `app/retrieval/tfidf.py`, field-generic (`build(series)`, `scores(text)`),
scores equal to the old cosine to 1e-9 on the whole corpus. Measured, plain process, after
20 queries: 31k 473 → 389 MB; 78k dry run 811 → 562 MB (index object 453 → 67 MB; the
predicted −520 MB was a deep-memory overestimate, the ~75 MB residue is allocator arena
retention from the Python analyzer). Scoring step 178 → 10 ms at 78k; whole
`retrieve_top_k` ~170 ms at 31k, now dominated by the fuzzy loop (follow-up above). Gates
on the merged tree: 275 tests, v4 0.95 / MRR 0.8083 / 1 failure, paste 8/8, eval CSVs
byte-identical. Smoke test through the app's own load-and-search path: `nṯr.PL` and
`nṯr.w` return the same three parallels; a synthetic glyph-less row is found by a
transliteration query and never by a glyph query. Monday's import is unblocked.

**Fri 09-04, night — item 3 half-shipped, and the benchmark caught something.**
BBAW text-only import merged (1e20634): 46,847 net-new (predicted 46,888; the 41-row
gap is the plural fold catching more near-twins in `dedup_key`). Corpus **78,412 rows**
(TLA 16,373 · AES 9,823 · BBAW 52,216, of which 46,845 text-only). Gates on the real 78k
corpus: 275 tests, v4 0.95 top-3 useful / **MRR 0.8083 → 0.8417** / 1 failure, paste 8/8,
segmentation eval unchanged (unspaced F1 0.920, as text-only rows never reach the
segmenter), RSS 574 MB with the index built. `test_shipped_corpus_is_fully_aligned` now
checks text-only rows against the empty-glyph count instead of asserting zero;
`data/processed/bbaw_rows.csv` gitignored.

**Demotic: importer merged, rows withheld.** `import_tla_dataset.py` gained
`--script-type`, a Roman Period range (−30..395; the parquet's dates actually run to
+475, so later rows fall to "Undated range"), and `--existing/--append` dedup mirroring
the BBAW importer, with 4 new period tests (33cd6cd). The source has 13,383 rows, no
hieroglyphs column, 12,026 net-new against 31,565. **Appending them dropped v4 from 0.95
to 0.90 top-3 useful (MRR 0.7917, failures 1 → 2):** on COMP_004 (`sr rn hw`) a Demotic
row (`TLA_DEMOTIC_A8089BC19E9B`) reaches rank 3 and pushes the Middle Egyptian target
out. Cause as predicted: Demotic transliteration tokens enter `mdc_frequencies` and shift
the IDF for every query, and nothing tells the ranker that a Demotic row is a poor
parallel for a Middle Egyptian paste. This is item A's problem, so the rows go live
*with* item A — per-stage IDF (or excluding other stages from `build_corpus_stats` for a
declared stage) plus the stage mask — and the v4 re-run with Demotic in becomes A's own
before/after number. Reproduce the import against the 78k corpus with:
`import_tla_dataset.py --input data/raw/tla_demotic/tla_demotic.parquet --output
data/raw/tla_demotic_worklist.csv --limit 20000 --language-stage Demotic --id-prefix
TLA_DEMOTIC --script-type Demotic --stable-ids --existing data/processed/examples.csv
--append`. Nothing was tuned to recover the number.

**Deployment note.** Streamlit Cloud gets the 78k corpus on this push (~780 MB with
Streamlit). The 46,847 new rows have no DB id there until `scripts/import_examples.py`
runs against Neon, which is deliberately not done at boot; the annotation form says so.

## Item 4 landed 2026-09-04 — and the gates said no to Ramses going live

**Merged.** Private data path (9711d9d, test fix 320f50d): `PRIVATE_DATA_DIR` (default
`data/private/`, gitignored) rows are concatenated only after `attach_db_ids`, so they
never get an id or reach the database, exports or API; `corpus_credit_html` is per-source
with a non-BY-SA line for Ramses and St Andrews; DATA-LICENSE has the NC section; a
`git ls-files`/`check-ignore` test guards the promise. Ramses importer (709b5f0):
per-row alignment gating on `src-sep` group count = word count → 36,476 aligned rows,
14,665 text-only (glyphs dropped, no display), 22,357 dropped for lacunae in the
transliteration; MdC ASCII → TLA convention, `+` markup stripped, `l` kept for foreign
names; 40,064 net-new after dedup (1.8% overlap with the public corpus). Written to
`data/private/ramses.csv` locally (21 MB, never committed). Suite: **312 tests**.
`tests/conftest.py` now pins `PRIVATE_DATA_DIR` to an empty directory for the whole
suite — without that, a lexicon test passed on a laptop without Ramses and failed on one
with it. Tests that want private rows use the `private_app` fixture.

**Measured with Ramses concatenated (118,476 rows), via `--examples` on the eval scripts:**

| Gate | public 78k | public + Ramses |
|---|---|---|
| v4 top-3 useful | 0.95 | **0.90** (COMP_007, COMP_014 fail) |
| v4 MRR | 0.8417 | 0.80 |
| expert paste | 8/8 | **3/8 — PASTE_001–005, every Urk. IV 1 variant, fail** |
| RSS after index, bare process | 574 MB | 872 MB (peak 1.38 GB in the smoke script) |
| `retrieve_top_k`, one query | ~170 ms | ~1,100 ms |

Camilla's line stops reading correctly because Ramses contributes 36k *aligned* rows of
Late Egyptian with **normalised** transliteration, more than the public corpus's 31.5k
aligned rows, and they take over the sign→reading and group statistics. Retrieval
itself looks reasonable (the Horus-and-Seth query returns Ramses rows of the same story;
`nṯr.w` gains `nb nṯr.w`), but a Late Egyptian row now enters Camilla's top 3.

**Decision.** Ramses rows are **withheld**, exactly like Demotic: the importer and the
private path ship, the CSV sits on disk, nothing loads it in production until item A.
This changes item A's scope: stage awareness must cover (i) IDF / `build_corpus_stats`,
(ii) the **ReadingModel and segmenter group counts** — private or other-stage rows must
not train sign readings for a Middle Egyptian paste, and Ramses' normalised
transliteration may belong in retrieval only, never in the reading model — and (iii) the
result-card stage label and score mask. The Ramses and Demotic re-runs are A's
before/after numbers. Also now a prerequisite for any 100k+ corpus: the rapidfuzz batch
call (1.1 s per query is not shippable). A cheap interim worth measuring first in A:
load private rows into the *retrieval* frame only, excluded from `build_corpus_stats`,
the ReadingModel and the sign index.

**Licence audit** (`docs/licence-audit-2026-09-04.md`, Opus agent, official pages only).
Two flags that need decisions, not code: (1) **`data/processed/helsinki_lexicon.csv`
(committed, declared CC BY-SA) has 50,647 of 97,340 rows with `source = Ramses`** (+4,402
`AES+Ramses`); Helsinki states CC BY 4.0, but CC BY-NC-SA §3(b)(1) allows only BY-NC-SA
for adaptations of NC material, so Helsinki's CC BY claim on those rows is doubtful and
our redistribution of them rests on it. Options: email Helsinki (Jauhiainen) and Liège
(Rosmorduc) for clarification; meanwhile split the lexicon — non-Ramses rows stay public,
Ramses-derived rows move to `data/private/` — after measuring the paste gate at lexicon
weight 0.2 with the split. (2) Zenodo's field for record 4954597 says CC BY 4.0, the
README says CC BY-NC-SA; treating it as NC is the safe reading and stays, labelled as our
conservative choice. Confirmed clean: TLA raw data v18, AES, AED-TEI,
`phiwi/bbaw_egyptian`, the BBAW 2018 edoc publication. Corrections proposed, not applied:
the TLA *website* is not CC BY-SA — only the raw-data publications are — so credits must
link the dataset publications, not the homepage; the Late Egyptian citation has the wrong
title and a stale URL; in-app credits lack the warranty disclaimer, licence-text links and
indication of changes (§3(a)); St Andrews' page states no licence, so the CC BY-NC-SA label
rests on his email — archive it. `examples.csv` is Adapted Material (§4(b) database
rights), so BY-SA on it is correct; the CC 4.0 legal code has no "collection" concept at
all — that lives only in the FAQ. Serving NC rows beside BY-SA rows from separate files is
a permitted non-commercial use provided the union is never shared as one database; seven
safe-side rules are in the report.

**Fri 09-04, late afternoon — licence work closed out.** Projet Ramses / Liège replied to
Email 4: the private NC arrangement is approved *and* the corpus is granted **CC BY-SA 4.0
for this project** ("Yes, no problem for us!"; archived in `docs/permission-requests.md`).
Consequences, all merged (88bdc17): Ramses moves into the public CC BY-SA credit sentence
with the README's attribution string; St Andrews is the only NC source left; the Helsinki
lexicon's Ramses-derived rows are covered by the grant, so the planned public/private
lexicon split was cancelled before it changed anything. The audit's wording corrections
are applied: TLA credit links the licensed dataset publications, not the website; warranty
disclaimer and licence-text links; indication of changes on every credit; Late Egyptian
citation corrected; DATA-LICENSE gains a Ramses section, database-rights (§4) and
cure/irrevocability (§6) notes. Still true: Ramses rows stay out of the live app until
item A (paste gate 3/8 with them loaded) — when A passes they go into `examples.csv`
directly, no private file needed. Test note: the private-corpus id test now compares
values with `check_dtype=False`, because a fresh local DB yields int64 ids and a stale one
float64 with gaps; both are legitimate.

## Item A core landed 2026-09-04 (13af7b3) — first honest numbers, two principled follow-ups

`app/services/stage.py` (`normalize_stage`, `stage_compatible`, `compatible_frame`,
`infer_stage`, `StageResources`, `build_stage_resources`), `retrieve_with_stage` (declared /
None / two-pass auto), `--stage none|auto|declared` on both eval scripts, `language_stage`
column on the paste queries. Design: unspecified rows (AES, BBAW — 62k) are compatible with
every stage; per-stage resources are the pooled constructors run on the compatible subset.
**Gate (a) exact:** P × none reproduces v4 0.95 / MRR 0.8417 / 1 failure and paste 8/8
byte-for-byte (the one v4 failure is COMP_007; earlier prose said COMP_008 — a typo, the
unmodified script fails COMP_007 too). Suite 353.

| corpus | mode | v4 top-3 | MRR | paste |
|---|---|---|---|---|
| P 78k | none / auto / declared | 0.95 / 0.95 / 0.95 | 0.842 / 0.875 / 0.90 | 8/8 / 8/8 / **7/8** |
| P+Ramses 118k | none / auto / declared | 0.90 / 0.90 / 0.90 | 0.80 / 0.80 / 0.875 | 3/8 / 3/8 / **7/8** |
| P+Ramses+Demotic 131k | none / auto / declared | 0.90 / 0.90 / 0.90 | 0.79 / 0.80 / 0.875 | 3/8 / 3/8 / **7/8** |

Declared stage rescues four of the five Urk. IV pastes Ramses breaks, and MRR rises. Two
measured shortfalls, neither tuned around: (1) **PASTE_003 (unspaced) fails in declared mode
even on P alone** — restricting to Earlier Egyptian shrinks the segmenter's group counts by
14–32% while `lexicon_weight=0.2` stays calibrated to the pooled corpus, so the lexicon's
merged group beats the correct three-way split (log-prob −14.16 vs −14.61; the docstring's
own failure mode for 0.39, reproduced at 0.2 under subsetting). Fix: scale the effective
lexicon weight by subset mass / pooled mass (factor 1.0 at target=None, so pooled behaviour
is unchanged by construction). (2) **COMP_014's target is an AES row with no stage**, so
`declared` degenerates to pooled and Ramses pollution persists; and **auto is size-biased**
(Ramses makes Late Egyptian 3× more frequent among labelled rows). Fix: a `language_stage`
column on the v4 CSV filled by a documented rule (TLA prefix, else the target's `period`),
and a lift-over-base-rate requirement (≥ 1.5) in `infer_stage`. Segmentation eval: P 0.920,
P+R 0.923 unspaced F1 (no stage flag there). Memory: all four stage sets cached at once at
131k ≈ 1.9 GB — the UI must build stage resources lazily. Latency unchanged (~1.1 s/query at
131k; rapidfuzz cdist still pending).

## Server, 2026-09-04 — our deployment lives on the friend's OptiPlex

Read-only Opus diagnosis first (report kept in the scratchpad, not the repo: it describes
someone else's machine). Box: Ubuntu 24.04 x86_64, 23 GB RAM, 4 cores, 114 GB disk 72% full,
27 days uptime, desktop that does not sleep. The friend runs Home Assistant, Vaultwarden,
Nextcloud, Pi-hole, Caddy and more in 13 Docker containers; `ledio` has no sudo and is not
in the docker group (root-equivalent on that box, so not asked for). His own hand-started
copy of the app ran under his user on 0.0.0.0:8501 with no service unit, exposed via
Tailscale Serve + Funnel (public). Decision (Ledio, "ledio folder only, change nothing
else"): **no Docker, no Postgres** — a clone at `/home/ledio/egyptology`, venv
`/home/ledio/venvs/egyptology` (python3.12, 756 MB), private NC data in
`/home/ledio/egyptology-private` (outside the clone), a `systemctl --user` unit
`egyptology.service` on **127.0.0.1:8502** (headless, Restart=on-failure, enabled,
secrets via `EnvironmentFile=/home/ledio/egyptology.env`, SQLite by default), and
`/home/ledio/egyptology-deploy.sh` (git pull --ff-only, pip, restart, health wait).
Verified on the box: 78,412 rows load in 6.8 s, SQLite bootstraps (66 MB), index in 4 s,
Horus-and-Seth query returns the same parallels, peak RSS 690 MB. Ledio ran the two sudo
steps: `loginctl enable-linger ledio` and re-pointed Serve `/` → 127.0.0.1:8502. The
`serve` command dropped Funnel (URL became tailnet-only); `tailscale funnel --bg
--https=443 http://127.0.0.1:8502` restores public access. The friend's 8501 copy is left
running; stopping it is his call. Streamlit Cloud still hosts the public corpus until the
"moved" banner goes up; the server is where Ramses/Demotic will go live after item A.

## Item A follow-up landed 2026-09-04 night (dda12fc) — the expert gate clears in declared mode

Three principled changes, no constant chosen against a benchmark: (1) the segmenter's
effective lexicon weight is `0.2 × subset mass / pooled mass` (factor exactly 1.0 at
target=None; Earlier Egyptian on P+R gets 0.0905); (2) the v4 CSV carries a
`language_stage` column filled by a documented rule (TLA prefix, else the target's `period`
when every keyword agrees; 15 of 20 rows resolved, 5 blank); (3) `infer_stage` requires
lift ≥ 1.5 over the stage's base rate among labelled rows, which removes Ramses' bulk bias.
UI (2ffd7a2): stage selectbox (Auto default), `?stage=` deep links, "Stage inferred: …"
captions, stage label on every evidence row, pooled resources reused for "All", per-stage
resources built lazily. Deployment knobs (18b02da): `ANNOTATIONS_DURABLE`, `DEFAULT_STAGE`,
`MOVED_TO_URL`. Suite 404.

| corpus | paste none / auto / declared | v4 top-3 none / auto / declared | v4 top-1 declared | MRR declared |
|---|---|---|---|---|
| P 78k | 8/8 / 8/8 / 7/8 | 0.95 / 0.95 / 0.90 | 0.85 (from 0.75) | 0.875 |
| P+Ramses 118k | 3/8 / 3/8 / **8/8** | 0.90 / 0.90 / 0.90 | 0.85 | 0.875 |
| P+Ramses+Demotic 131k | 3/8 / 3/8 / **8/8** | 0.90 / 0.90 / 0.90 | 0.85 | 0.875 |

**What clears:** with all corpora loaded and the stage declared, Camilla's line reads
correctly in all variants — the gate item A existed for. **What does not, and why:**
(i) v4 declared 0.90 = COMP_007 (pre-existing, stage-independent) + COMP_014, whose two
useful-family parallels are Late Egyptian formula rows (`TLA_LATE_783`, `_1324`) that a
*correct* Earlier Egyptian declaration excludes — formulae cross stages, so retrieval
should treat stage as a preference, not a filter (the reading model is right to filter);
reaching 0.95 there would need a penalty constant picked against the benchmark, which is
refused — report both numbers instead. (ii) P declared 7/8: PASTE_003's subset factor
(0.886) does not shrink enough to flip the cut (−14.61 vs −14.28 nats). (iii) **Auto with
Ramses loaded is 3/8**: inference reads labels off the pooled top-10, and 52,248 of the
62,039 unspecified rows have `period = unknown`, so nothing clears and it falls back to
pooled. Auto is the server's default, so **Ramses and Demotic stay withheld** until Auto
holds 8/8.

**Part 3 (running):** for hieroglyph pastes, choose the stage by model likelihood — read the
paste under each stage's resources and take the stage under which the sign sequence is most
probable per sign (argmax, no threshold; Demotic excluded as it has no aligned rows; ties →
pooled). Label-based inference stays for text queries. Plus the period rule applied at load
so the ~10k datable unspecified rows gain a derived stage. Gate: P+R(+D) × auto paste 8/8.
Server: our deployment runs dda12fc; Funnel restored by Ledio; Cloud to receive
`default_stage="all"` and `moved_to_url`.

## Item A closed 2026-09-04 night (0ae0f95 + this commit) — 130,472 rows live

**Part 3 result.** Segment pooled, read by stage: `groups_ok` was true in all 72 cells, so
the segmenter is built from the whole corpus (lexicon factor back to 1.0, the mass-scaling
code deleted) and only the reading model, index and frame are stage-restricted. Auto scores
a hieroglyph paste under each stage's reading model alone — normalised conditional
probabilities, lexicon off, per sign — and takes the argmax; the raw-count segmentation
term that favoured the bigger corpus is out of the comparison. Per-paste likelihoods on
P+R: Earlier −3.233 / Late −3.347 / Demotic −3.685 for every Urk. IV variant → Earlier
Egyptian, correct. Gates: P × none byte-identical; **P × auto 8/8, P+R × auto 8/8,
P+R+D × auto 8/8; declared 8/8 everywhere** (including the former P × declared miss, fixed
for free by the pooled segmenter). The period-derived stage was removed: the earlier
attribution of a v4 drop to it was a misdiagnosis — the drop comes from the v4 CSV's own
stage column once any declared-mode filter applies.

**Loaded.** Ramses appended to `examples.csv` under the CC BY-SA grant (78,412 → 118,476,
40,064 net-new, 921 already present), then Demotic (→ 130,472, 11,996 net-new, 49 already
present). `data/private/ramses.csv` deleted so rows are not loaded twice; the private path
now serves St Andrews only. Sources: BBAW 52,216 · Ramses 40,064 · TLA 28,369 (16,373 +
11,996 Demotic) · AES 9,823. Stages: Unspecified 62,039 · Late Egyptian 43,665 · Earlier
Egyptian 12,772 · Demotic 11,996. Alignment: misaligned 0, text-only 70,968, usable 59,504.

**Numbers on the final corpus** (evals now default to `--stage auto`, the app's default):

| mode | paste | v4 top-3 | top-1 | MRR | failures |
|---|---|---|---|---|---|
| auto | **8/8** | 0.90 | 0.70 | 0.80 | COMP_007, COMP_014 |
| declared | 8/8 | 0.90 | 0.85 | 0.875 | COMP_007, COMP_014 |
| none (pooled, "All" in the UI) | 3/8 | 0.90 | 0.70 | 0.79 | COMP_007, COMP_014 |

Segmentation eval: unspaced F1 0.923 (was 0.920), exact 0.539, trained on 53,553 rows.
v4's citable 0.95 belongs to the 78k corpus; on 130k it is 0.90 in every mode, for the two
reasons recorded above — traded for +52k rows and stage awareness, not tuned. Suite 424 →
tests updated for the design: the trial-sentence tests read with the Earlier Egyptian model
over the pooled segmenter; the Horus-and-Seth notation tests accept Ramses' edition of the
same sentence (Seth `stḫ`, and `ꜥḥꜥ.n ꜣs.t (ḥr) qnd …`) as parallels. New deployment knob
`corpus_sources_exclude` / `CORPUS_SOURCES_EXCLUDE`: Streamlit Cloud must set
`"Ramses,Demotic"` (131k no longer fits 1 GB) plus `default_stage="all"` and
`moved_to_url`; the server loads everything.

**Open after A.** "All" mode now reads Middle Egyptian pastes wrong when the whole corpus
votes — it is honest to keep it, and the caption says what it does, but the default is
Auto for a reason. Stage-as-preference in retrieval (recovers COMP_014 without tuning).
Auto for *text* queries still uses label inference (base-rate lift), which works less well
than the likelihood chooser; a text analogue (score the transliteration under per-stage
token models) is the natural next step. Cold build of three stage sets on a 131k corpus
≈ 21 s and ~1.9 GB if all cached — lazy on the server, excluded on Cloud.

## Hosting decision closed 2026-09-04 — Streamlit Cloud retired, server is the host

Ledio's call after item A: the corpus (130,472 rows) no longer fits Cloud's 1 GB and the
server works, so Cloud is retired rather than kept alive on a subset. DEPLOYMENT.md is now
the server runbook (layout under `/home/ledio`, service, deploy script, settings table,
what needs sudo, history of Cloud/Neon/HF). README points at the new URL. The
`corpus_sources_exclude` / `default_stage` / `moved_to_url` knobs stay in the code — they
cost nothing and describe any future small host — but no Cloud secrets are needed.

**Still to be done, in order** (no runs tonight):
1. Warm the per-stage resource sets at service start (first Auto paste is ~60 s cold).
2. Nightly `egyptology.db` copy to `egyptology-backups/` and off the machine; one restore
   test before the expert round. Have `deploy.sh` run `scripts/import_examples.py` so new
   corpus rows get ids on the existing database.
3. Git LFS for `data/processed/examples.csv` (65 MB; GitHub warns above 50 MB).
4. Stage as a *preference* in retrieval (recovers COMP_014 without tuning).
5. St Andrews importer (hieropy, private script) → `/home/ledio/egyptology-private/`;
   gate: Camilla's line top-1 from his line rows; attribution screenshot to Nederhof.
6. E, phrase finder, with the rapidfuzz batch call. Then the expert round.
7. Late Egyptian evaluation set from Ramses. B, C, D as planned.
8. Neon: export any remaining annotations with `scripts/export_reviewed.py`, rotate/delete
   the role, close the project. Delete or leave the Cloud app (unmaintained either way).
Ledio's side: Email 5 to Nederhof (sign-list licence → C); set `REVIEWER_KEY` in
`/home/ledio/egyptology.env` before experts annotate; pick an off-machine backup target.

## Stage as a preference in retrieval — landed 2026-09-04 night

Candidates and the n-gram index are always the pooled corpus; only `CorpusStats` (IDF) and
the reading model are stage-restricted; segmenter pooled; sign index pooled (nothing read
the stage one). No constant added. `run_competitive_ambiguity_eval.py` now retrieves through
`build_stage_resources`/`retrieve_with_stage` like the app instead of filtering its own
candidate pool — the previous declared/auto figures (top-1 0.85, MRR 0.875) were artifacts
of that filter and are withdrawn. **On the 130k corpus v4 is 0.90 top-3 / 0.70 top-1 /
MRR 0.7917 in none, auto and declared alike**; paste stays 8/8 in auto and declared. COMP_014
in declared mode now returns its Late Egyptian formula parallels (Ramses `ḥw tꜣ nb` 0.200,
`TLA_LATE_1324` 0.222, Ramses `ḥw ꜥšꜣ rmṯ.w` 0.188 token overlap) instead of four unrelated
AES rows — a real retrieval improvement that does not clear the benchmark's frozen 0.26 bar,
which we do not move. Effect of un-filtering: 4 of the 10 Earlier-Egyptian-declared queries
now show Late Egyptian/Demotic rows in their top 3 (10 of 30 slots), all stage-labelled in
the UI. The stage-restricted IDF has no measurable effect on v4; a stronger preference would
need a constant and is not built. Cost: a declared query ~0.5 s → ~1.35 s (pooled candidate
pool); every mode now costs the same, and the rapidfuzz batch call is the remedy. Suite 429.
**Honest closing numbers for 2026-09-04:** corpus 31,565 → 130,472; expert paste 8/8 in the
app's default mode; v4 0.95 (78k) → 0.90 (130k), two misses, both diagnosed, nothing tuned.
If 20/20 is wanted the legitimate routes are diagnosing COMP_007 and deciding *before* looking
at results whether a v5 benchmark with a different overlap rule is justified, reporting both.

## Nederhof's fourth mail (reply to Email 5), 2026-09-04 — C unblocked, E rescoped

Archived in `docs/permission-requests.md`; Email 6 drafted there.
- **Item C: his sign-function XML may be used "under whatever license you prefer."** We take
  it as CC BY 4.0 with attribution (compatible with the CC BY-SA corpus). The +2–3-day
  contingency on C is dropped; C is 5 days. Scope note: the file covers the Unicode 5.2
  sign set; UniKemet lists functions with newer terminology ("classifiers") but drawn from
  single attested tokens, so it is a cross-check, as is the Thot Sign List; our own 59k
  aligned rows supply the frequency side.
- **Item E rescoped.** He did *not* ask for user-uploaded texts. E becomes: similar-text
  search across annotation tiers — sign sequence (glyph n-grams on the CSR machinery),
  transliteration (today's index), translation, and lemma ids once D lands — with his
  research question, "can one improve on edit distance?", answered by measurement:
  edit-distance re-rank vs n-gram cosine vs tier-combined scores on parallel pairs we can
  construct from the corpus (same sentence in two editions — Ramses/TLA Horus-and-Seth
  rows are a ready-made test set). Effort stays 1–2 days; the upload feature is gone.
- He will retest once new functionality is added; he declines real user queries as test
  material (classic partition instead); students' projects run to ~April 2027, so the
  segmentation harness is a slow-burn offer, not a deliverable.
- Ledio's side: send Email 6 (draft ready); nothing else is asked of him.

## Plan for 2026-09-05 — start here

State at close of 2026-09-04: corpus 130,472 rows live on the server (0a25254); item A and
stage-as-preference merged; expert paste 8/8 in the app's default mode; v4 0.90 / MRR 0.79
in every mode (COMP_007, COMP_014); suite 429; Nederhof's sign-function XML usable; Email 6
drafted. Nothing is running.

| # | Work | Gate / output | Effort |
|---|---|---|---|
| 0 | **Ledio:** send Email 6; set `REVIEWER_KEY` in `/home/ledio/egyptology.env`; name a backup destination | — | 15 min |
| 1 | **The two v4 misses, the honest way.** Rule stated *before* running: for every v4 query compute the best achievable useful-family overlap in the corpus with the target excluded; a query with no row ≥ 0.26 is *unanswerable by construction* and is flagged, not scored against us. Then: COMP_007 (`sẖꜣk =ꞽ ẖ.t =ꞽ ḥr n.tt …`, best found 0.15–0.24, lemma overlap 0) — answerable or not? If answerable, diagnose the ranking (simplified-notation fold of the query is the first suspect: `skhak i kh i tt im fkh djd` has lost `n.` and `=`). COMP_014 — parallels found at 0.19–0.22; decide, on principle and before looking at any result, whether "useful" should be defined by lemma overlap where lemma ids exist (→ a pre-registered **v5** rule); report v4 and v5 side by side, never replace v4. ✅ | a written reason per miss; v4 over answerable queries; v5 if pre-registered | ½ day |
| 2 | **Server hardening.** Warm the three stage resource sets at service start (`ExecStartPost` or a warm-up call); nightly copy of `egyptology.db` to `egyptology-backups/` and off the machine (target from Ledio), 30-day retention, one restore test; `deploy.sh` runs `scripts/import_examples.py` after a corpus change; Git LFS for `examples.csv` (65 MB) | first paste after restart < 5 s; a restored copy opens; LFS pull works on the box | ½ day |
| 3 | **rapidfuzz batch call** (`process.cdist` in `retrieve_top_k`) — every mode now scores the pooled corpus, ~1.3 s/query | `fuzzy_score` identical on the whole corpus for 5 queries; v4/paste unchanged; query < 0.5 s | ½ h |
| 4 | **St Andrews importer** (hieropy, private script, → `/home/ledio/egyptology-private/standrews.csv`); also fetch Nederhof's sign-function XML into `data/raw/standrews/unicode/` and commit a converted table under CC BY 4.0 credited to him (DATA-LICENSE line) — prep for C | Camilla's Urk. IV 1 line top-1 from his line rows; attribution screenshot to him | 1 day |
| 5 | **E, rescoped:** similar text across tiers — glyph n-grams, transliteration, translation, lemma ids when D lands — on the CSR machinery; edit-distance re-rank vs n-gram cosine vs tier-combined, measured on same-sentence pairs across editions (Ramses/TLA Horus-and-Seth rows are a ready test set); result card shows the matched parallel per tier. No upload feature. Then tell Nederhof → **expert round** (Camilla on an unseen text, Sophie, Nederhof) | a number per method on the cross-edition pairs; Email 7 | 1–2 days |
| 6 | Late Egyptian evaluation set from Ramses (measures the new stages) | frozen set + first numbers | ½ day |
| 7 | B — format controls as soft segmenter hints, St Andrews first, BBAW upper bound second | two numbers to Nederhof, null result allowed | 1 day |
| 8 | C — sign-function lattice on Nederhof & Rahman 2015 with his XML + our group statistics + Helsinki lexicon; UniKemet/Thot as cross-checks only | Camilla's line from all spacings; paste 8/8; unspaced F1 > 0.923 | 5 days |
| 9 | D — proper nouns via TLA lemma ids | variant names grouped under one lemma | 2–3 days |
| 10 | Housekeeping: Neon export/rotate/close; delete or ignore the Cloud app; DEPLOYMENT.md follow-ups | — | ½ day |

### Item 1 — done 2026-09-05

Full write-up: **`docs/v4-answerability-and-v5-rule.md`** (pre-registered rules, both
traces, every table). Headline numbers, all measured today on the 130,472-row corpus at
`2b13fed` + the uncommitted work described there:

- **v4 is unchanged and reproduces exactly: 0.90 top-3 useful / MRR 0.7917, `--stage auto`.**
- **Rule A (answerability): all 20 v4 queries are answerable** with the target excluded —
  the median query has 4,605 useful rows in the corpus. So the answerable-only number
  equals the all-queries number, and neither miss is a coverage gap.
- **Both misses are lost at the top-3 boundary, not in retrieval.** COMP_007: the useful
  row `TLA_EARLIER_6267`/`S6267` is retrieval rank 7 of 29,047 and suggestion rank 6; the
  first *accepted* suggestion is rank 4 at confidence 0.5250 against 0.5350/0.5330/0.5300
  — a 0.005 margin. COMP_014: `TLA_LATE_783`/`S783` is retrieval rank 4 of 23,353 and
  suggestion rank 5; first accepted suggestion rank 4 at 0.4750 against 0.4820 — 0.007.
  In both, the rank-4 accepted row has the highest token overlap of the top-4 window
  (S6267 itself, at rank 6, carries 0.318).
- **Rule B (v5, lemma-first where lemma ids exist): 0.80 / MRR 0.7167**, identical in all
  three stage modes; costs COMP_010 and COMP_021, rescues none. Pre-registered, reported
  beside v4, never replacing it. 70.7% of the corpus has no lemma ids (BBAW 0/52,216,
  Ramses 0/40,064), so v5 only ever re-judges TLA/AES candidates.
- **Two null results, reported as such:** the drift-corrected benchmark variant
  (`…_v4_driftcorrected.csv`, 12 of 20 rows carried a phantom `pl` token predating
  `fold_plural_marker`) scores identically to v4; and `--query-path app`, which mirrors
  the app's vocabulary-aware parsing and interpreted-reading hand-off, changes no query's
  top-3 at all. **`app` is the harness default from 2026-09-05 on** — an evaluation
  should measure the path the app actually takes — and `--query-path legacy` reproduces
  every historical number exactly; the two agree in all three stage modes.
- **Disclosure: v4's 0.90 includes two guaranteed hits.** An exhaustive twin scan shows
  COMP_004 and COMP_017 each have a Jaccard-1.0 BBAW edition twin that the builder's
  4,000-entry postings cap hid. **v4 over the 18 non-twin rows is 0.8889 / MRR 0.7963**
  (v5: 0.7778 / 0.7130).
- **New held-out validation set** for the fix that was *not* made:
  `competitive_ambiguity_eval_queries_holdout_2026-09-05.csv`, 20 queries, disjoint from
  v4 and its twins, built with the new `--exhaustive-twins` guard. Baseline today
  **0.75 / MRR 0.6667**. Nothing has been tuned against it.
- **No ranking or normalisation fix was applied**, deliberately: a 0.005 margin on a
  sample of two is not evidence for any particular reweighting, and the standing rules
  put an unvalidated fix below a proven diagnosis. The candidate change and its
  acceptance criteria are written down in the doc. The `pl` query-fold fix was rejected
  as not symmetric — `search_fold` is one shared function and `PLURAL_MARKER_RE` requires
  the leading dot.
- **Experiment 1 (pre-registered, run 2026-09-05): no fix validated, and the default is
  untouched.** Three structural re-rank configurations were written down before running —
  CFG-A carries retrieval's IDF overlap forward into the re-rank instead of recomputing a
  plain one, CFG-B gives `char_similarity`'s 0.16 to `relative_score` (0.40, no new
  number), CFG-C both — selected on the **held-out set only**, paste gate 8/8 required,
  v4 measured once afterwards for all three. Held-out: CFG-C 0.85/0.6583, CFG-B
  0.80/0.6667, CFG-A 0.75/0.6167 against baseline 0.75/0.6667; all three hold paste 8/8.
  CFG-C is the selection, and **fails two of the three acceptance criteria** — held-out
  MRR 0.6583 < 0.6667, and on v4 it loses COMP_001 and COMP_022 (0.85/0.7750) — so
  nothing was applied.
- **What it did establish:** the diagnosis was right about the mechanism — CFG-A/CFG-C
  move COMP_007's accepted candidate from **rank 4 to rank 1** and rescue HOLD_001 and
  HOLD_002 — but the change is a **trade, not an improvement**: it buys top-3 coverage by
  demoting rank-1 hits (MRR falls while top-3 rises). The next step is an evaluation that
  can tell a rank-1 demotion from a rank-3 rescue, not another reweighting. The three
  configurations live on as presets behind `WHYPTOLOGY_SUGGESTION_PRESET`, unset
  everywhere including the app and the server.
- Gates: `pytest tests -q` **429 passed** at the time of the write-up; Experiment 1 adds
  four tests that pin the unchanged default (the shared working tree, which by then also
  carried item 4's importers, ran **465 passed** in 391 s, no failures). Expert paste
  **8/8** in auto, in every configuration.

### Items 2, 3, 4 — done 2026-09-05; day closed

Every item today was executed by one agent and re-derived by a second, fresh agent before
being accepted; the verifier reports are summarised in the docs named below.

- **Item 2, server hardening — done (DEPLOYMENT.md).** First hieroglyph paste after a
  restart **60 s → 5.3 s** (a real paste driven over the Streamlit websocket from
  `ExecStartPost`; a helper process cannot fill `st.cache_resource`). Nightly
  `egyptology-backup.timer` 03:33: sqlite3 `.backup`, `integrity_check`, gzip, 30-day
  retention, restore test that wrote and read back an annotation on the copy; **off-site
  to Backblaze B2** via rclone since 15:12 (first upload 22 MB). Deploy script re-imports
  the corpus when the CSV changed. **The live DB was 52,060 rows behind the CSV** — 40 % of
  the corpus could not be annotated — fixed by one hand-run `import_examples.py`
  (`Inserted=52060, total=130472`). Peak RSS is **3.0 GB**, not 1.9. Ledio is in `sudo`
  (password), so `git-lfs` and `sqlite3` are installed on the box. Git LFS: tracked in
  `.gitattributes`, converts on the next commit.
- **Item 3, query latency — done, merged from its worktree.** Warm Auto-mode query
  **2.92 s → 0.42 s CPU** (Mac), paste 1.50 → 0.19 s. Per-row token sets, IDF weights and
  sign-group encodings built once per resource set (`app/retrieval/tokens.py`), fuzzy
  score one `process.cdist`, stage sets share the pooled tables (+60 MB, not +3×). Scores
  bit-identical in 8/10 columns; the two IDF columns differ by ≤ 1 ulp from summation
  order, which flips only exact ties beyond rank 8,900. The FastAPI path still takes the
  scalar route. Rapidfuzz alone was worth 27 ms; the roadmap's "½ h, cdist" framing was
  wrong about where the time went.
- **Item 4, St Andrews — done, private (DATA-LICENSE.md, docs/standrews-attribution.md).**
  `data/private/standrews.csv`: **7,659 rows** from 94 texts / 102 witnesses, verbatim
  Hannig transliteration (yod `j`, one `z`, no `.t`), TLA transcode + `=` split only.
  **`hieroglyphs` is empty on every row**: RES's top level is the quadrat, not the word;
  the Ramses-style count gate matched 50/1,710 lines and hand-checks showed those pairings
  systematically wrong from the first multi-reading quadrat on. The 1,710 line-level
  renderings are parked in `data/raw/standrews/standrews_lines.csv` — the first test set
  for item C. Urk. IV 1: his edition splits Camilla's line in two rows and writes `=ṯn`;
  as text his row is rank 1 among St Andrews rows, rank 2 overall; a glyph paste can never
  reach a St Andrews row. Paste gate 8/8 with private rows present. **Nederhof's
  sign-function table** `data/processed/sign_functions.csv`: 1,444 entries covering 780 of
  the 1,071 Unicode 5.2 signs, CC BY 4.0, deterministic rebuild. **Server trapdoor:** the
  unit sets `PRIVATE_DATA_DIR`; the directory being empty is the only thing keeping NC rows
  off the public URL — settle access control before copying the CSV there.
- **Merged-tree gates, 2026-09-05 15:20:** paste **8/8** auto; v4 **0.90 / 0.7917**,
  misses COMP_007, COMP_014; held-out **0.75 / 0.6667**; `pytest tests -q` **490 passed**.
- Also today: corpus loader pins six sparse text columns to `str` (the boot-time
  `DtypeWarning` was per-chunk type guessing); memory notes and learning journal updated.

**Plan for 2026-09-06.** (0) Ledio: send Email 6; set `REVIEWER_KEY`; `passwd` on the box.
(1) Commit + push today's tree (one commit; the LFS conversion rides on it), deploy, live
paste, re-measure first-paste-after-restart (expect < 5 s now). (2) Follow-up batch, one
agent + one verifier: `verify_release.py` gets an explicit benchmark and an accuracy floor
from a committed baseline; concrete-stage loader already reuses pooled resources (item 3)
— re-measure the cold build; `_evidence_summary` wording ("shared lemma ids" is candidate
metadata, not a query match); deploy distinguishes insert from refresh (`--dry-run`); pin
`scipy`; FastAPI path gets the `SearchIndex`. (3) Trace the five held-out misses the way
the v4 misses were traced (answerable? rank at each stage?) — diagnosis only. (4) Expert
round ask, small and concrete: five queries (COMP_001, COMP_007, COMP_022, HOLD_010,
HOLD_016) where CFG-C moves a named candidate a named number of ranks, before/after lists
already computed — the one instrument that separates a rank-1 demotion from a rank-3
rescue. Then item 6 (Late Egyptian set), E, B, C, D as planned.

About 13 working days after tomorrow's item 1. Standing rules: no constant is chosen by
looking at a benchmark result; every benchmark change is a pre-registered rule reported next
to the old number; the paste gate must stay 8/8 in Auto on every merge; the server is
updated with `./egyptology-deploy.sh` after every push, and the live URL is checked.

## Plan for 2026-09-06 — items 1–4 done on 2026-09-05 evening

Ledio asked for tomorrow's three open items to be done the same evening. Three workers ran
in parallel (Opus 4.8; one in its own worktree), each re-derived by a fresh Opus 5 verifier
before acceptance. State at the start: 3d38721 committed, pushed and deployed; the box
answered a warm hieroglyph paste in **2.6 s** (was 5.3 s before item 3), so item (1)'s
"< 5 s" gate is met.

- **(2) Follow-up batch — done** (worktree commit deee9d2, merged here). `verify_release.py`
  reads a committed baseline (`data/benchmarks/release_baseline.json`: benchmark v4, `--stage
  auto --query-path app`, floors 0.90 / 0.7917 / 8/8, corpus rows 130,472) and is NOT READY
  below it; the floor check is a pure function with 16 corpus-free tests. Concrete-stage cold
  build re-measured on the Mac: **30.5 s for all three** (Earlier 10.0, Late 11.1, Demotic
  9.4), down from ~60 s, thanks to item 3's shared token tables — DEPLOYMENT.md updated, the
  server row kept until re-measured there. Evidence line now says "lemma IDs common to this
  reading's rows" instead of "shared lemma IDs" (it was never a query match). `import_examples.py
  --dry-run` reports what the sync and the refresh would change without writing, through the
  same diff code the real paths use; the canonical deploy script now lives at
  `scripts/egyptology-deploy.sh` (server copy + a dry-run pass before the real sync) — **the
  server still runs its old copy until Ledio approves the scp** (DEPLOYMENT.md has the
  command). `scipy==1.18.0` pinned (imported directly). FastAPI endpoint builds the frame and
  `SearchIndex` once: warm request **8.4 s → 0.15 s**. Suite **506 passed, 3 skipped**
  (Ramses raw files gitignored); paste 8/8; v4 0.90 / 0.7917, misses COMP_007, COMP_014.
- **(3) Held-out misses traced — done, diagnosis only**
  (`docs/holdout-misses-trace-2026-09-05.md`). All five (HOLD_001, 002, 005, 014, 026) are
  answerable (813–2,309 useful rows each) and all five are **re-rank boundary losses**: the
  useful row is in the top-50 pool (retrieval ranks 3, 3, 13, 7, 6), the first accepted
  suggestion sits at rank 4 (HOLD_005: 8), margins 0.004–0.029. Stage inference, query path
  and fold are clean for all five. CFG-C rescues HOLD_001/002 to **exactly rank 3** and pushes
  the other three further out (4→7, 4→6, 8→>10) — the top-3/MRR disagreement in miniature.
  Seven of seven traced misses now share one mechanism: shared-vocabulary lookalikes outrank
  the qualifying phrase by a few thousandths.
- **(4) Expert round 2 ask — done** (`docs/expert-round-2-ask.md`, offline page
  `data/benchmarks/expert_round_2.html` from `scripts/build_expert_round_2_page.py`, Email 7
  drafted in `docs/outreach-messages.md` for Camilla with short variants for Sophie and
  Nederhof). Five cases, one question each: COMP_007 6→1 (the rescue); COMP_001 1→off list;
  COMP_022 3→7; HOLD_010 1→off list (the roadmap's "1→2" understated it — the first *useful*
  row is at 2, but the best parallel with both royal names leaves the top 8); HOLD_016 1→3.
  Nothing sent.
- **Twin-guard bug (reported by Ledio, confirmed, fixed).** `int((1.0 - 0.9) * 10)` is 0 in
  floating point, so the exhaustive twin scan probed one rarest token too few whenever
  (1−t)·|A| was a whole number; a ten-token row missed a nine-token twin at exactly Jaccard
  0.90. `twin_probe_count()` now does the arithmetic on exact rationals and is used at both
  scan sites; regression tests added (the exact case, boundary sizes, brute-force equivalence
  on random corpora). Re-scan with the fix: **v4 still has exactly two twins** (COMP_004,
  COMP_017; targets matched on text id *and* sentence id — TLA sentence ids repeat across text
  ids) and **held-out 1 has none** (HOLD_001 and HOLD_017 are 20-token boundary rows, now
  probed with three tokens). Today's disclosure numbers stand.

### Experiment 2 — pre-registered 2026-09-05 evening, runs after the deploy (Opus 5 worker)

Question: do useful readings keep more of the query's *consecutive* words than the lookalikes
that outrank them, and does rewarding that fix the boundary losses without demoting rank-1
hits? Frozen before running:

0. **Pre-check, the kill switch (no ranker code).** For each of the seven traced misses, count
   the distinct query bigrams (two consecutive query tokens) that also occur consecutively in
   each top-6 candidate. A `_` placeholder only spans (`a _ b` → a,b checked as adjacent across
   one token); any bigram containing `_` earns nothing; query side only, a longer candidate is
   never penalised. Alongside the bigram counts, print the ranker's OWN per-term score
   breakdown (query token overlap, character similarity, relative score, IDF carry-over if
   any) for the same top-6 rows — the traces' `token` column is the *evaluator's* overlap with
   the target sentence, not a ranker term, so which term loses the boundary has not yet been
   shown with numbers. Pass iff in **≥ 4 of 7** the useful candidate's count is **strictly**
   greater than every candidate ranked above it (ties = not beaten). Fail → stop, write a null
   pre-check; it rejects this bigram measure, not word order in general.
1. **Build held-out 2 and held-out 3** (20 each) with the fixed twin guard, disjoint from v4,
   held-out 1 and each other; exclusion also removes rows sharing a TLA/AES/Ramses
   `source_text_id` with any existing target and, for BBAW (one text id for 52k rows), a fixed
   window of neighbouring sequential sentence ids around each target (window fixed before
   building; the build log reports rows removed per rule). Held-out 2 = selection set (once it
   picks a winner its score is not confirmation). Held-out 3 = sealed until the final claim.
2. **Adjacency bonus vs the unchanged default ranker** (not vs CFG-C). Formula and three
   candidate weights written down first. Selection by rule on held-out 2 only: top-3 and MRR
   both ≥ baseline, rank-1 hit count not lower, and at least one of top-3 / MRR strictly
   higher; among qualifiers, highest MRR. None → null result.
3. **Report** on v4, held-out 1, held-out 2: top-3 useful, MRR, and a per-query signed rank
   change of the first useful candidate. Paste 8/8 required.
4. **Confirm before promoting.** Open held-out 3 once, for the selected configuration only:
   pass iff top-3 and MRR ≥ the default's numbers there and the rank-1 count is not lower.
   Only then does it become the app default and the expert "after" column is regenerated.
   Fail → default stays, failed confirmation reported, held-out 3 spent.

Deferred: symmetric `.n` / `=` marker preservation in `search_fold` — exploratory, separate
(only COMP_007 shows fold evidence). Lemma overlap is reported per candidate, never scored
(queries carry no lemma ids; 70.7 % of rows have none, so a bonus would be a TLA-source bias).

**Plan for 2026-09-06 (revised).** (0) Ledio: send Email 6 and Email 7 (with the ask sheet or
page attached); set `REVIEWER_KEY`; `passwd` on the box; approve
`scp scripts/egyptology-deploy.sh ledio@vela-optiplex-3070:egyptology-deploy.sh`. (1) Experiment
2 as above, its own worktree, `opus5-worker` + fresh verifier. (2) Item 6 (Late Egyptian set
from Ramses), then E, B, C, D as planned. Standing rules unchanged.

### Experiment 2 — result: the pre-check failed 0/7, the experiment stopped at step 0

Run 2026-09-05 late evening (Opus 5 worker, worktree, merged as a null result;
`docs/experiment-2-adjacency-2026-09-05.md`, raw output
`data/benchmarks/experiment2_step0_precheck.txt`). The probe reproduced the harness digit for
digit on all seven traces (COMP_007 0.5350 / 0.5330 / 0.5300 / 0.5250 etc.). Bigram counts of
ranks 1..k, useful row last: COMP_007 `[0,0,0,0]`, COMP_014 `[0,0,0,0]`, HOLD_001 `[1,1,2,2]`,
HOLD_002 `[0,1,0,0]`, HOLD_005 none in top 6, HOLD_014 `[1,1,2,2]`, HOLD_026 `[0,0,0,0]`.
**Beaten in 0 of 7** (rule: ≥ 4). In four misses no top-6 candidate keeps a single consecutive
query pair, so an additive bonus would be identically zero across the window; in the two where
it is alive the useful row ties the row it must overtake. Two structural reasons: the builder's
`simplified`/`partial` queries drop stop tokens, destroying consecutiveness by construction, and
the loose fold splits compound names, so exact-token adjacency is stricter than it sounds.
**This rejects the bigram measure, not word order in general.** Per the frozen protocol the
ranker was not changed and held-out 2 / 3 were not built.

**What step 0 did establish — the ranker's own per-term breakdown, shown for the first time:**
`exact_or_near` (0.12) is 0.0 for every candidate of all seven misses and `reading_similarity`
(0.08) never fires, so 0.20 of the nominal weight is dead at the boundary; `relative_score` +
`mean_score` are nearly flat across the top 6 (0.82–1.00 of pool max). The boundary is decided
between `translit_overlap` (0.20) and `char_similarity` (0.16), and **the useful row usually
wins the overlap term and loses on character similarity**: COMP_007's rank-4 row leads
`translit_overlap` by 0.078 and trails `char_similarity` by 0.080; same shape in HOLD_014;
COMP_014, HOLD_001, HOLD_002 lose both, HOLD_026 wins char and loses overlap. This is a sharper
statement of Experiment 1's mechanism and points at `char_similarity`'s role (the term CFG-B
zeroed) rather than at a missing word-order signal. It is an observation read off the same
seven misses, so it cannot be tested on them; it is NOT a proposal, and no third reweighting is
scheduled. The instrument that settles the boundary remains the expert round (Email 7).

**St Andrews access control — decision pending (Ledio).** The private CSV exists only on the
Mac; the server's `PRIVATE_DATA_DIR` is empty and that emptiness is the only thing keeping NC
rows off the public URL. Before it is copied there, choose: (i) private rows visible only behind
the reviewer key on the public instance (~½ day, smaller change), or (ii) a second, private
instance that loads them and a public one that never does. Schedule before item B, which tests
format controls on St Andrews first; item C uses the parked `standrews_lines.csv`.

Decisions: (a) held-out 2 and held-out 3 are built **before** any future ranking experiment,
with the exclusion rules pre-registered above, not before; (b) any such experiment first
re-reads this breakdown and the expert answers; (c) tomorrow proceeds to item 6, then E, then
the wider expert round, then B, C, D. Suite after the merge: 527 passed (the 12 new tests pin
the bigram definition and that `debug_signals` leaves suggestions byte-identical).

## Items 6 and E — done 2026-09-05 evening (Opus 5 workers, worktrees, fresh verifiers)

- **Item 6, Late Egyptian evaluation set LE-v1 — done** (`docs/late-egyptian-eval-set-2026-09-05.md`,
  `data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv`, frozen). Pre-registered, then
  built with the builder's rules plus a `--stage` pool filter (twin detection stays whole-corpus),
  `--exhaustive-twins`, v4 and held-out 1 excluded, 30 rows. **All 30 targets are Ramses** — the
  deterministic rival-count rule put Ramses (92 % of the 43,665-row Late Egyptian pool) on top and
  the rule was not changed afterwards; so LE-v1 measures Ramses Late Egyptian, not TLA's. 15
  simplified / 15 partial / 0 reading-order (Ramses has no `normalized_reading_order`; the 14
  empty queries were dropped). Zero twins, zero overlap with v4 or held-out 1; no `_`, MdC or
  ASCII-yod leakage (import_ramses.py already stores TLA-style yod). **Numbers, 130,472 rows,
  `--query-path app`:** none 0.8667 top-3 / 0.8000 MRR / 22 rank-1; **auto 0.8667 / 0.8167 / 23**;
  declared 0.8667 / 0.8000 / 22; misses LE_008, LE_014, LE_034, LE_044 in every mode; all 30
  answerable (median 1,567 useful rows). Auto inferred Late Egyptian on 16/30 (all correct),
  abstained on 14, wrong on 0. Only LE_001 and LE_005 move across modes: auto's lead over `none`
  is LE_005 (it inferred Late Egyptian and promoted the useful row 2→1), its lead over
  `declared` is LE_001 (it abstained and avoided the loss declaring caused). Reading: the stage machinery neither
  helps nor hurts Ramses queries at the top-3 level; the misses are three-quarters within 0.03 of
  the usefulness threshold; the 14 abstentions are probably the `lift ≥ 1.5` gate (inferred
  from the code, not isolated by a run). Builder gains a `language_stage` column (without it `--stage declared`
  silently degenerates to pooled). Suite 535.
- **Item E, similar-text search across tiers — done** (`docs/similar-text-eval-2026-09-05.md`,
  `data/benchmarks/cross_edition_pairs_v1.csv`, `similar_text_eval_v1_results.csv`,
  `app/services/similar_text.py`, new **Similar text** page). Pre-registered pair rule: two rows
  from different sources, loose-token Jaccard in [0.5, 0.9), ≥ 0.9 near-copies dropped (1,538),
  300 pairs, 50 per source pair, deterministic, byte-identical on re-run. Hand-check of ten: 8
  same sentence, 1 partial (sentence boundary), 1 false (short function-word clause) — ~10 %
  noise, an upper bound on any method. **Nederhof's question, "can one improve on edit distance?",
  answered on 600 directed queries:** transliteration T1 n-gram cosine MRR 0.718 / 0.723 vs T2
  edit-distance re-rank 0.708 / 0.723 → **no improvement**; signs G1 0.726 / 0.741 vs G2 0.745 /
  0.748 → small improvement; pre-registered rule (both tiers, both directions) → **edit distance
  does NOT improve on n-gram cosine**. Translation L1 0.628 / 0.626 on the 48 AES↔TLA pairs (the
  only same-language pairs; BBAW is English, Ramses has none). Tier combination is a wash on
  like-for-like cases (T1 0.751 vs C2 0.754). Stated limits: pairs were selected by
  transliteration overlap, so T3 token-Jaccard (0.80) is the selection statistic, not a result;
  selected pairs sit at the easy end of the band (mean Jaccard 0.858); the predicted hard case
  Ramses↔TLA is easy (T1 0.789) because the fold unifies yods and `.PL`, the real hard case is
  AES↔Ramses (T1 0.477, different stage). **The page** ranks by what measured best — T1 for
  transliteration, G2 for signs, L1 for translation — and its caption says so with the MRR; ten
  parallel cards with per-tier scores and a "why it matched" line; no upload, nothing stored; the
  two extra indexes build lazily (signs 1.3 s / +66 MB, translation 4.7 s / +456 MB). Workspace
  ranking path untouched. Suite 549, paste 8/8.
- Deviations recorded in each doc: the two-source ambition of LE-v1 not met; tier auto-detection
  got a vocabulary test so `htp dj nswt` is not mistaken for a translation; the Ramses yod mapping
  was unnecessary.

**Next: the St Andrews reviewer gate** (decision taken 2026-09-05 evening, option (i)), then
Ledio's one email round with the key (Emails 6/7 + "E is live, here is the measured answer"), then
B, C, D.

## St Andrews reviewer-key gate — done 2026-09-05 night (option (i), adversarially verified)

The private CC BY-NC-SA rows now load **only into sessions that have presented `REVIEWER_KEY`**.
The app boots on the public frame; a keyed session gets public + private under its own
`corpus_signature`, so every cached loader (search index, sign index, both Similar-text
indexes, stage resources, reading model, segmenter) builds a second, lazily built set for
keyed sessions — the frame is the gate, not a filter, so no surface can leak by being
forgotten. Fails closed on every path (no key configured, empty or whitespace key, wrong or
prefix key, forced session flag, key-check exception, malformed private CSV → public rows,
logged). Key lives in `st.session_state` only; the `?q=` share link carries no key; the
warm-up is handed the public frame. Comparison is `secrets.compare_digest`. Keyed set costs
**+1.0 GB RSS / 16 s** on the Mac (+0.57 GB without Similar text), built on first unlock.

**Adversarial verification (fresh Opus 5 agent):** 65 automated routes — every page, `?q=` /
`?stage=` / `?view=` with private-only strings, the Corpus explorer search box, Source
dropdown and last page, Sign readings' 7,048 options, the Reviews download bytes, all three
Similar-text tiers, cache cross-talk after a keyed build (17 routes re-run in the same process
plus direct re-fetch of all ten cached loaders under the public key), signature collision, key
comparison edge cases, exceptions, logging under DEBUG, all DB tables before/after, the FastAPI
endpoint, the export and warm-up scripts, module scope — **0 leaks to an unkeyed session.**
One same-session defect found and fixed before merge: after "Lock this session" the workspace
kept painting results computed while keyed, with the NC credit line gone; locking now clears
every cached search/browse key (regression test). Test tracer signs moved to code points
absent from the Helsinki lexicon as well as the corpus (they were present in the lexicon, a
false-failure risk). Verdict: **safe to deploy with the private CSV on the server.**

Operational order (DEPLOYMENT.md): Ledio sets `REVIEWER_KEY` in `/home/ledio/egyptology.env`
and restarts the service **first**; only then
`scp data/private/standrews.csv ledio@vela-optiplex-3070:egyptology-private/`. Key is one
shared secret for the reviewers; rotate by editing the line, restarting, resending. Notes
left open: `CORPUS_SOURCES_EXCLUDE` does not apply to private rows (the frame is the gate,
not that knob); with the key unset the sidebar tells every visitor that private files are
present (one bit, misconfigured state only).

**Next: Ledio's email round** (Emails 6/7 + "E is live, here is the measured answer" + the
key), then B, C, D.

### Close of 2026-09-05 (written 2026-09-06 00:30) — everything live, gate confirmed end to end

Box at **00c78b7**: the gate plus two sidebar CSS fixes found by Ledio on the live page (the
expander header and the key field were light-on-light inside the dark sidebar). Ledio set
`REVIEWER_KEY`, copied `standrews.csv` to the box and restarted; the public view was verified
from outside at **130,472** records / four sources / CC BY-SA only, and his keyed session shows
**138,131** with St Andrews and the NC credit. He chose to keep a short passphrase for now, told
of the guessability risk; rotation is one line and a restart. DEPLOYMENT.md's gate instructions
corrected (user unit, no sudo; fill the existing line, don't append a second). Tailscale on the
Mac had stopped at midnight and cost one deploy attempt; the public URL (Funnel) was unaffected.

**Done today, all merged, verified by a fresh agent, and deployed:** items 1–6 and E of the
plan table, Experiment 1 (trade, not a fix), Experiment 2 (null at the pre-check, 0/7; the
per-term breakdown it exposed is in its doc), the twin-guard float bug, the expert-round ask
with Email 7, the follow-up batch of six, and the reviewer-key gate. Suite **582 passed**;
v4 0.90 / 0.7917, held-out 1 0.75 / 0.6667, LE-v1 0.8667 / 0.8167 — none moved.

**Plan for 2026-09-06 (final).** (0) Ledio: send Email 6 (Nederhof, with the ask folded in) and
Email 7 (Camilla, Sophie) with `expert_round_2.html` + `expert-round-2-ask.md` attached, plus the
key by separate message to whoever should unlock; `passwd` on the box. (1) B — format controls
as soft segmenter hints, St Andrews first, BBAW upper bound (1 day, null allowed). (2) C — the
sign-function lattice on Nederhof's table (5 days; gate: Camilla's line from any spacing, paste
8/8, unspaced F1 > 0.923). (3) D — proper nouns via TLA lemma ids (2–3 days). (4) Housekeeping
(Neon close, Cloud app, DEPLOYMENT.md follow-ups). Expert answers to the five cases decide the
CFG-C question when they arrive; held-out 2/3 are built only if a ranking experiment is planned.
Standing rules unchanged.

### Item B — format controls as weak segmenter hints — pre-registered 2026-09-06 (Opus 5 worker)

Written before any run. Worktree off `main` at 36d8c38, 130,472-row public corpus, project
interpreter. Nederhof's fourth criticism: we delete U+13430–1345F, which carry the quadrat
structure of a paste. Question: read as "these signs share a quadrat", used as a **soft**
penalty against cutting inside a quadrat, do they improve segmentation on (a) real St Andrews
RES-derived input and (b) a BBAW upper bound? A null result is a real answer and is allowed.

**Diagnosis (measured 2026-09-06 before writing this).** `data/processed/examples.csv` has 0
format controls and 0 glyph layout operators (the TLA `mdc` column's `:` is the ꞽ: prefix, not
layout). Raw `data/raw/bbaw_egyptian/train.parquet`: 35,503 glyph rows, **19,140** with `:`/`*`;
42.5% of within-word adjacencies are joined by `:`/`*` (the earlier 22.5% figure is superseded).
`data/raw/standrews/standrews_lines.csv`: 1,710 lines, **1,698** carry controls (13430 ×12,733,
13431 ×8,481, 13437/13438 ×1,355 each, 13433 ×374 …); spaces there separate **quadrats**, not
words (line 1: 12 quadrats, 5 readings), the `transliteration` column is already TLA-folded, and
no word-level gold grouping exists → the St Andrews metric must be end-to-end reading. PASTE_005
has horizontal joiners between *every* sign of each wrongly chunked piece (`𓆓𓂧𓆑`), so a hard
"no cut inside a quadrat" rule fails the gate; the penalty must lose to the corpus evidence
(𓆑 → =f 3,878/3,907). Benchmarks v4, held-out 1 and LE-v1 contain **no** controls, so their
numbers must come out byte-identical.

**Frozen design.**
1. `app/data/normalizer.py`: `quadrat_hints(value) -> (groups_as_pasted, no_cut)`. `no_cut` =
   glyph-stream boundary indices (same indexing as `glyph_stream`: b means "a group ends before
   glyph b") that fall between two signs joined by a **joiner** U+13430–13436 or U+13439–1343B,
   or strictly inside a **segment** 13437…13438 or an **enclosure** 1343C…1343F. Mirror (13440),
   blanks and damage marks (13441–13455) carry no adjacency information → no hint. Invariant,
   tested on the 8 pastes, all 1,710 St Andrews lines and the pipeline fuzz: `groups_as_pasted
   == normalize_hieroglyphs(value).split()` exactly.
2. `SegmentationWeights.quadrat_crossed` (nats), penalty per boundary the segmentation places
   at a `no_cut` position. `Segmenter.segment(groups, no_cut=frozenset())` and
   `score_segmentation` apply it; `Segmentation.crossed_quadrats` lists them. Empty set → the
   objective is unchanged, so every existing test and number stays identical.
3. One helper `segment_paste(query, segmenter, use_format_hints=True)` replaces the five
   `normalize_hieroglyphs(q).split()` → `segment` sites (`whyptology_app.py:424`,
   `retrieval.py:294`, `run_expert_paste_eval.py:119`, `bench_query_latency.py:98`,
   `check_standrews_urkiv_gate.py:122`); the manual-edit site at `whyptology_app.py:2025` is
   left alone. `run_expert_paste_eval.py` gains `--no-format-hints`. No ranking or retrieval
   code changes; no UI beyond the wiring.
4. **BBAW upper bound** (`scripts/run_format_hint_eval_bbaw.py`): raw rows accepted by
   `import_bbaw_egyptian.parse_glyph_field` + the importer's alignment filter, with `:`/`*`
   present. Emit U+13430 for a `:` token, U+13431 for `*`, nothing for `-`; gold = the
   importer's word groups. Rows must be **removed from the training frame** by normalised glyph
   string (memorisation guard, as in `run_segmentation_eval.split`). Fixed seed 7 split: dev 50%
   / test 50%. Inputs: unspaced + controls vs unspaced with controls deleted (= today). Metric:
   boundary P/R/F1 + exact, the segmentation eval's own. Print hint precision (share of
   control-marked adjacencies inside a gold group; ~1.0 by construction — that is why this is an
   upper bound). **Constant selection**: `quadrat_crossed ∈ {0.25, 0.5, 1.0, 2.0}` by highest
   unspaced F1 on the **dev** half, subject to paste 8/8 (auto) as a hard constraint; report on
   the test half only. Standing rule respected: no benchmark number picks the constant.
5. **St Andrews, the real input** (`scripts/run_format_hint_eval_standrews.py`, data
   gitignored, script committed): resources on the **public** corpus only; assert no line's
   normalised glyph string occurs in it. Two shapes per line: *as rendered* (quadrat spaces +
   controls) and *unspaced* (spaces removed, controls kept); each with hints off vs on. Metric:
   predicted reading tokens vs the line's `transliteration`, both through one lenient fold fixed
   now — NFC, lowercase, delete `. ( ) [ ] { } ⸢ ⸣`, nothing else (ṯ/t and yod differences count
   as misses on both arms equally) — multiset token P/R/F1, exact-line rate, and |groups −
   tokens| mean; paired deltas with lines improved / worsened / unchanged. Print Camilla's line
   (`urkIV-001`, line 2) both ways.
6. **Decision rule.** Hints ship ON (default = the selected constant) iff on St Andrews the
   unspaced-shape token F1 delta is > 0 **and** improved lines > worsened lines **and** every
   gate holds. Otherwise the code ships with `quadrat_crossed = 0.0` (present, off) and the null
   result is reported. BBAW is informative only and never decides.
7. **Gates on the merged tree**: pytest green; paste 8/8 auto; v4 results byte-identical to
   the committed file (0.90 / 0.7917); held-out 1 0.75 / 0.6667; LE-v1 0.8667 / 0.8167;
   `run_segmentation_eval.py` default numbers unchanged. PASTE_005 must pass at the chosen
   constant.
8. **Report** `docs/format-hints-2026-09-06.md` with numbers exactly as printed, the two numbers
   for Nederhof, and this section's close-out. Then C.

STOP conditions for the worker: the invariant in (1) fails on any line; < 500 eligible BBAW
rows; a gate fails at every candidate constant; any step needs ranking/retrieval changes; or
wall clock > 3 h. Stop that step, finish the rest, report.

**Result 2026-09-06: hints ship ON at `quadrat_crossed = 1.0`** (`docs/format-hints-2026-09-06.md`,
`data/benchmarks/format_hints/`). No stop condition fired. The invariant held on all 8
pastes, all 1,710 St Andrews lines and a 400-case seeded fuzz (`hypothesis` is not
installed, so the fuzz is a seeded `random`, not a strategy); the empty-`no_cut` no-op is
proved against a re-implementation of the old objective on 500 scrambled corpus rows.
**BBAW upper bound**, 11,386 eligible rows, hint precision exactly 1.0, seed-7 dev/test
5,693/5,693, memorisation guard removing 10,246 of 130,472 training rows: unspaced
boundary F1 **0.784 → 0.940** on test (exact 0.541 → 0.631). Constant chosen by the
pre-registered rule — best dev F1 was 2.0 (0.9485) and it **fails PASTE_005** exactly as
predicted (7/8), so 1.0 is the highest candidate keeping the gate at 8/8 (0.5 and 0.25
also pass). **St Andrews, the real input**, 1,701 lines (one dropped by the memorisation
guard — `urkIV-024` line 2-8 is the single sign 𓅱, which the TLA rows also carry, so the
pre-registered bare assert was turned into the drop-and-name rule `run_segmentation_eval`
uses): unspaced token F1 **0.587 → 0.591** (+0.0046, improved 195 / worsened 69 /
unchanged 1,437), as-rendered **0.577 → 0.581** (+0.0038, 178/56), group-vs-token gap
−0.17 on both shapes; the decision rule's three conditions are all met. On Camilla's line
the hints make one real correction, `𓈖𓏏 𓈖` → `𓈖 𓏏𓈖`, i.e. `n.t n` → `n =tn`, the very
place the first expert trial flagged. **Gates:** suite **594 passed, 4 skipped** in a
clean checkout, **595 passed, 3 skipped** with the gitignored `standrews_lines.csv`
reachable (the all-1,710-lines invariant test skips without it); expert
paste **8/8** auto; v4 **0.90 / 0.7917**, held-out 1 **0.75 / 0.6667** and LE-v1
**0.8667 / 0.8167**, each byte-identical to a re-run of the same command on the pristine
`bb3aa80` tree; segmentation eval unchanged (unspaced F1 0.923 / exact 0.539);
`check_standrews_urkiv_gate.py` 8/8 on the keyed 138,131-row corpus. One thing found on
the way: the committed `ceval_v4_v4_app_auto_results.csv` and
`ceval_holdout_v4_app_auto_results.csv` are stale in their `evidence_summaries` column
only ("shared lemma IDs:" → "lemma IDs common to this reading's rows:", changed by
deee9d2, before item B); every rank, flag and score matches, and item B changes no byte
of either. A bug in the BBAW control synthesiser (a joiner emitted in front of a token
that appends no sign) was found and fixed mid-step: precision 0.9992 → 1.0, the ranking
of the four constants unchanged. Not done, deliberately: no ranking or retrieval change,
and the workspace does not yet *show* `Segmentation.crossed_quadrats` — the obvious next
small UI step. **Next: C.**

**Lead close-out 2026-09-06 (Fable):** worker diff reviewed line by line (hint indexing, penalty
placement, empty-set no-op, five call sites); the verbatim St Andrews line (CC BY-NC-SA) was
removed from `data/benchmarks/format_hints/standrews.md` and the report before commit — only
the described correction stays. Merged-tree gates re-run by the lead: `verify_release.py`
READY (598 passed; v4 0.9 / 0.7917; paste 8/8), held-out 1 0.75 / 0.6667, LE-v1 0.8667 /
0.8167, segmentation eval 0.923 / 0.539 — all equal to the worker's. The two stale result
files were refreshed in their own commit (6046b74; only `evidence_summaries` wording moved).
Pushed and deployed: box 36d8c38 → 6046b74, healthy after ~2 s. **Item B closed. Next: C.**

### Item C — sign-function segmentation and reading — pre-registered 2026-09-06 (Opus 5 worker)

Written before any run. Worktree off `main` at HEAD (item B merged, 6046b74+). Nederhof's third
criticism: the lattice is a unigram over attested groups and knows nothing about sign
function. Camilla's core want: readings where the corpus has no parallel. Two measurable
steps, each with its own decision rule; a null on either is a real answer and is reported.

**Diagnosis (measured 2026-09-06, unspaced input, eval split seed 7, segmenter without lexicon
groups so the unattested share is an upper bound).** Test 5,298 sentences, 35,170 gold
boundaries: **7,029 spurious vs 3,407 missed**. Of the spurious, **6,351 fall inside a gold
group the training split never saw whole** (10.7% of gold groups are unattested and cause 90%
of false boundaries): the lattice cuts an unseen word into seen fragments. Adjacent sign pairs
seen in training: 98.2%; a bare sign-bigram "majority boundary" rule alone is right 90.6% of
the time on seen pairs — weaker than the lattice (F1 0.923) but it generalises to unattested
groups, which the unigram cannot. Nederhof's table covers **87.0%** of corpus sign tokens (680
of 2,084 distinct training signs) but only **14.9%** of tokens have a single function class, so
class must be soft. Most frequent uncovered signs: Z7 𓏲 (36k), Z2 𓏥 (32k), V31A 𓎢, Z3A 𓏫,
Z3 𓏪, N35A 𓈗, N17 𓇿, Z6 𓏱, U7 𓌻, Aa15 𓐝, D6 𓁻, plus TLA placeholder signs. The reading
model's glyph-similarity fallback was last measured at **acc 0.2537** on unseen groups
(11,959-sentence corpus); no 130k number exists yet — the worker measures the baseline on the
pristine tree first. v4, held-out 1 and LE-v1 contain **no** glyph queries → byte-identical.

**Supplement table, written by the lead now (not tuned), `data/processed/sign_functions_
supplement.csv`, CC BY-SA, source "Gardiner sign list", column `source_note = 'project
supplement'` so it is never confused with Nederhof's CC BY 4.0 rows:** Z7 𓏲 phonogram `w`;
Z2 𓏥, Z3 𓏪, Z3A 𓏫 typographic (plural strokes); V31A 𓎢 phonogram `k`; N35A 𓈗 phonogram `mw`
and determinative (water); N17 𓇿 logogram `tꜣ` and determinative (land); Z6 𓏱 determinative
(death, enemy); U7 𓌻 phonogram `mr`; Aa15 𓐝 phonogram `m`; D6 𓁻 determinative (actions of the
eye). Placeholder signs (TLA `<g>` codes) and every other uncovered sign get class `unk`.

**C1 — boundary model with function-class back-off, inside the lattice.**
1. Classes: fold Nederhof's labels to {phon, log, det, phondet, typ}; "logogram or
   determinative" → {log, det}; "phonogram or phonetic determinative" → {phon, phondet};
   uncovered → {unk}. `P(c | sign)` uniform over the sign's classes. Training data = the
   segmentation eval's training split (seed 7); **dev = the last 10% of that shuffled training
   split**, test = the eval's test split, untouched for selection.
2. Boundary statistics from training streams: per adjacent sign pair (a, b) counts of boundary /
   no boundary; per class pair (c1, c2) expected counts under the soft class assignment;
   global prior. Estimate `P(boundary | a, b) = (n_b(a,b) + α · P_class) / (n(a,b) + α)` with
   `P_class = Σ P(c1|a) P(c2|b) P(boundary | c1, c2)` (additive smoothing 0.5 toward the
   global prior), **α = 1, fixed, not tuned**. Unseen pair → `P_class` alone.
3. Lattice term, exact under the semi-Markov DP: `λ_b · [ log P(boundary | s_{i-1}, s_i) at
   every placed boundary i > 0  +  Σ log P(no boundary | s_{k-1}, s_k) over the internal
   positions k of every span ]`. All other terms unchanged; **κ (6.0), lexicon weight (0.2),
   quadrat_crossed (1.0) are not re-tuned**.
4. Selection: `λ_b ∈ {0.25, 0.5, 1.0, 2.0}` by highest **dev** unspaced F1 subject to paste
   8/8 (auto). Ablation at the chosen λ_b: sign-bigram only (no class back-off: unseen pair →
   global prior) — this isolates what the function table itself contributed.
5. Decision: ship (default = chosen λ_b) iff **test unspaced F1 > 0.923 strictly**, scrambled
   F1 ≥ 0.937, paste 8/8, and the item B St Andrews reading token F1 (unspaced) is not more
   than 0.010 below 0.591. Otherwise `λ_b = 0.0` (code present, off), null reported.

**C2 — function-composed readings for unattested groups.**
1. New source kind `composed` in `predict_sequence_scored`, consulted after corpus and lexicon
   and **before** the glyph-similarity fallback, only when composition yields ≥ 1 candidate;
   otherwise fallback as today. Marked on `ReadingPrediction` (`is_composed`), counted as
   *borrowed* for every gate that counts fallbacks, confidence capped like a fallback, and
   labelled in the UI "read sign by sign from the sign-function list — not attested".
2. Composition rule, frozen: walk the group's signs left to right, using Nederhof's rows plus
   the supplement. phonogram `v` → append `v`; logogram `v` → append `v`; "logogram or
   determinative" `v` → append `v` OR nothing; "phonogram or phonetic determinative" `v` →
   nothing if `v`'s consonants are a suffix of the reading so far, else append `v`; phonetic
   determinative → nothing; determinative, typographic → nothing. Candidates = the product of
   choices, **cap 24 per group** (entries ordered by the corpus's own `P(value | sign)` where
   the single sign is attested alone with that value, else table order). Empty string → no
   candidate. Candidate score = Σ over contributing signs of `log P(value | sign)` from the
   corpus where available, else `log(1 / entries of the sign)`; emission = that score
   normalised over the candidates; transition/context terms as for lexicon groups.
3. Metric: extend `run_reading_model_eval.py` with `composed` totals and a **paired**
   comparison on the positions where the pristine model used fallback: accuracy of fallback
   vs composed on exactly those positions (exact match, the eval's own rule; the lenient fold
   of item B reported alongside). Largest corpus size, `--exclude-duplicates`.
4. Decision: ship iff composed accuracy on the positions it covers is **strictly higher** than
   fallback on the same positions, with **≥ 200** such positions, and `acc_ambiguous_context`
   at the largest size is not lower than the pristine baseline the worker records first.
   Otherwise the source kind stays in the code but disabled (`use_composed=False`), null
   reported. **PASTE_008** (unattested signs, honest empty result) must still pass; if a
   composed reading makes the gate fail, STOP C2 — do not change the gate or the paste row.

**Gates on the merged tree:** pytest green; paste 8/8 auto; v4 0.90 / 0.7917, held-out 1
0.75 / 0.6667, LE-v1 0.8667 / 0.8167 all byte-identical; segmentation eval reported before and
after; reading eval before and after; St Andrews token F1 (item B script) before and after.
**Report** `docs/sign-function-2026-09-06.md`, numbers exactly as printed, one paragraph for
Nederhof (his table's contribution, from the C1 ablation), close-out here. UI: label composed
readings; show item B's `crossed_quadrats` in the workspace caption (one small step).

STOP conditions: C1 exceeds 0.923 at no λ_b → C1 null, continue to C2; C2 covers < 200
positions → C2 null; any gate fails; any retrieval/ranking change needed; wall clock > 6 h in
one launch → report state for a second launch. Never commit, never touch the server.

**Result 2026-09-06 (Opus 5 worker):** **C1 ships, C2 is a null.** Report:
`docs/sign-function-2026-09-06.md`. Baselines on the pristine tree matched the
pre-registration exactly (segmentation 0.923/0.539 and 0.937/0.599; St Andrews unspaced
token F1 0.591; reading at the largest size `acc_ambiguous_context` 0.8803,
`acc_fallback` 0.2835, `fallback_predictions` 1485, `unseen_signs` 9445).

*Step 1.* `data/processed/sign_functions_supplement.csv` — the lead's 13 rows over 11
signs, every codepoint verified against Nederhof's `signunicode.xml`, `source_note =
"project supplement"`, CC BY-SA 4.0 with its own DATA-LICENSE section. One loader
`app/services/sign_functions.py:load_sign_functions()` folds both tables to the five
classes + `unk`; 12 unit tests.

*C1.* `app/services/boundary_model.py`, α = 1 as frozen, statistics read off the fitted
`ReadingModel` (42,842 adjacent sign pairs, prior P(boundary) 0.3097). Dev sweep (last
10% of the shuffled training split, 438 twins removed, 4,746 sentences): unspaced F1
0.921 (off) → 0.928 → 0.932 → **0.937 at λ_b = 1.0** → 0.936 at 2.0; the gate is 8/8 at
0.25/0.5/1.0 and **7/8 at 2.0** (PASTE_005 reads 𓈖𓏏𓈖𓏥 as `(ꞽ)ntn`), so the dev argmax
and the constraint agree on 1.0. **Held-out test: unspaced 0.923/0.539 → 0.939/0.579,
scrambled 0.937/0.599 → 0.946/0.635.** St Andrews unspaced token F1 **0.591 → 0.603**.
Every C1.5 condition met → shipped, `SegmentationWeights.boundary_model = 1.0`.
Unseen-word breakdown, unspaced, baseline → shipped: spurious cuts *inside an
unattested gold group* **1,793 → 1,431 (−20.2%)**, inside an attested one 601 → 559;
missed between two attested 2,638 → 2,028, touching an unattested 351 → 287.
**Ablation** (sign bigram only, unseen pair → global prior) at the same λ_b: 0.938/0.578
and the same error breakdown (1,428 spurious inside unattested). So of the +0.016 F1
the adjacent-sign bigram gives ≈ +0.015 and **Nederhof's function table ≈ +0.001** —
because 98.2% of held-out adjacent pairs were already seen and only 14.9% of sign
tokens have a single class. His criticism was right about the model; the fix came from
sign adjacency, not from sign function, on a corpus this size.

*C2 (amended by the lead mid-implementation; the pre-amendment 5,000-sentence run is
kept in the report).* Amended filters exclude 110 of 1,457 table rows (94 group-scoped,
9 numeral, 7 `certain=false`); 779 of 791 signs keep a standalone row. Stage 1 on dev
only (4,761 sentences, 778 positions neither corpus nor lexicon can read): coverage
0.6632 (516). Oracle recall exact/lenient — as pre-registered 0.0581/0.0930; + dev
revision 1 (phonetic complement) 0.1008/0.1570; + revision 2 (optional logogram)
**0.1221/0.1764**; with the cap raised 24 → 500, 0.1880/0.2655. Top-1 exact **0.0349**.
Against the fallback's **0.2835** the ceiling is below the incumbent's accuracy, so
**Stage 2 was not run** and C2 is a null: `USE_COMPOSED_BY_DEFAULT = False`, code
present and tested. Cause is structural, not tuning — phonetic complements and TLA's
written morphology (`.PL`, `(w)`) are not derivable from a per-sign inventory; the
lenient fold recovers only 0.122 → 0.176 of it. Revisiting needs RES sign-combination
matching (which would restore the 94 excluded rows) and a morphological layer.

*Gates on the worktree:* pytest 640 passed / 3 skipped; paste 8/8 auto; segmentation
and St Andrews as above; reading eval identical to baseline in every field; **v4
(0.90 / 0.7917), held-out 1 (0.75 / 0.6667) and LE-v1 (0.8667 / 0.8167) all
byte-identical** to the committed result files (`diff` empty on each);
`check_standrews_urkiv_gate.py` green (keyed 138,131 rows, paste 8/8).
Two tests were re-scoped, not weakened:
item B's no-op proof and the two singleton-discount cases now pin their own term with
`boundary_model=0.0`, because they re-implement the pre-item-C objective and their
hand-built fixtures never show the disputed pair across a boundary; the real case is
covered by PASTE_005. Not touched: κ, the singleton discount, the lexicon weight,
`quadrat_crossed`, retrieval/ranking, and the lattice's pasted-space restriction.

**C2 — preconditions for reopening (decided 2026-09-06, Ledio + lead).** C2 stays off and is NOT
re-run as it stands: its generation ceiling (oracle recall 0.122 on dev, 0.188 with the cap at
500) is below the incumbent fallback's accuracy (0.2835), so no scoring or decoding change can
help. It is reopened only when both of these exist, each a separate measured item:
1. **Sign-combination matching.** Nederhof's table has 94 rows whose reading belongs to a
   combination of signs (A1 with plural strokes → `rḥw` "men"). The conservative rules excluded
   them because his RES combination notation cannot yet be matched against a corpus sign group.
   That is exactly the multi-sign knowledge composition was missing.
2. **A morphology layer.** The gold readings carry written morphology — plural marks, restored
   letters (`.PL`, `(w)`), dots and brackets. A per-sign inventory can never produce those;
   something has to propose them.
Until then, item D (proper nouns via TLA lemma identifiers, Nederhof's second criticism) comes
first: its data is already in the corpus. Revisit C2 only if an expert says unattested-word
readings matter more than the name problem. Code and tests stay in place, so reopening costs
nothing extra.
