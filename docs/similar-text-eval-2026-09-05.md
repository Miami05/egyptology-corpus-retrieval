# Similar-text search across annotation tiers — can one improve on edit distance?

ROADMAP item E, 2026-09-05. Nederhof's fourth mail rescoped E from "let users upload
texts" to "similar-text search across the annotation tiers, with his research question
answered by measurement": is an edit-distance re-rank better than an n-gram cosine, and
does combining tiers beat either?

This document is written in two passes. Everything under **Pre-registered** was written
and committed *before* any pair was built or any number was measured (commit
`pre-registration`, see the git log of this file). Everything under **Results** was
written afterwards and may not silently change a pre-registered rule; where reality
forced a deviation it is listed under **Deviations from the pre-registration**.

---

## Pre-registered

### 1. What a pair is

A *cross-edition pair* is two corpus rows from **different `source` values** that are the
same sentence in two editions. We do not have a gold list of such pairs, so they are
constructed, and the construction rule is fixed here before it is run:

1. Both rows have a non-empty `transliteration_gold`.
2. Reduce each to its **loose token set**:
   `set(app.services.suggestions.loose_reading_form(transliteration_gold).split())`.
   `loose_reading_form` runs `normalize_transliteration` (which folds `ꞽ`, `j`, `ı` and
   ASCII `i` all to `i`) and then `normalize_mdc`. The brief asks for a Ramses `i` → `ꞽ`
   mapping "where the fold does not already" do it — the fold already does it, on both
   sides, and the build script asserts this on real Ramses and TLA strings rather than
   assuming it. If the assertion fails the script stops.
3. Both rows have at least **5 loose tokens**. A two-token fragment can reach any Jaccard
   by accident and is not a sentence; this also keeps the candidate generator's postings
   lists sane.
4. **Jaccard of the two token sets is in the band `[0.5, 0.9)`.**
   - `>= 0.9` is excluded on purpose: 13,659 corpus rows already have a `>= 0.9` loose
     twin (BBAW is an edition of many TLA sentences). Those are near-copies; every method
     would find them and every method would look perfect. Including them would measure
     nothing. **They are excluded and this is said out loud here.**
   - `< 0.5` is excluded because below it we can no longer claim the two rows are the
     same sentence rather than two sentences sharing a formula.
5. The two rows come from different `source` values (Ramses / TLA / BBAW / AES).

### 2. How the candidates are found (no O(n²) scan)

The same prefix-filter theorem the competitive-ambiguity builder uses, imported, not
copied: `scripts.build_competitive_ambiguity_benchmark.twin_probe_count(size, t)` returns
`floor((1-t)·size) + 1`, the number of a row's **rarest** tokens that must be probed
because a partner at Jaccard `>= t` can miss at most `floor((1-t)·|A|)` of them.

We apply it on **both** sides (the standard all-pairs prefix–prefix filter) rather than
only on the probe side:

- order every token globally by `(document frequency ascending, token ascending)`;
- each row's *prefix* is its `twin_probe_count(|A|, 0.5)` earliest tokens under that order;
- index only prefixes; probe only prefixes.

This is exact. If `J(A,B) >= t` then `|A∩B| >= t·max(|A|,|B|)`, so the globally-earliest
shared token has at most `|A| - ceil(t|A|) = twin_probe_count(|A|,t) - 1` tokens of `A`
before it and therefore lies in `A`'s prefix, and symmetrically in `B`'s. Indexing
prefixes only (rather than full postings, as the builder's `exhaustive_best_twin_overlap`
does) is what keeps this affordable at `t = 0.5`: a very frequent token is last in the
global order, so it is in almost no row's prefix and carries an almost empty postings
list. **There is no postings cap** — the 4,000-postings cap that hid two v4 twins is not
reintroduced here. The size bound `t·|A| <= |B| <= |A|/t` prunes further.

### 3. Selection, cap and stratification

- Every unordered candidate pair in the band is collected.
- **At most one pair per corpus row**, so the 300 pairs are 600 distinct rows and no row's
  idiosyncrasy is counted twice.
- Selection is greedy and deterministic, no random seed: candidates are grouped by
  unordered source pair; within a group they are sorted by `(-jaccard, source_a,
  source_text_id_a, source_sentence_id_a, source_text_id_b, source_sentence_id_b)`; the
  groups are then visited round-robin, each contributing its next unused pair, until
  **300** pairs are selected or no group has one left. Round-robin is what "stratified as
  evenly as the data allows" means here: a group with fewer pairs than its even share
  simply runs out and the remaining groups keep going.
- Frozen to `data/benchmarks/cross_edition_pairs_v1.csv`.

### 4. The circularity, stated before the numbers exist

**The pairs are found by transliteration-token overlap. Any method that scores
transliteration overlap is therefore being tested on a set selected to contain exactly
what it measures.** Consequences, agreed in advance:

- The transliteration-tier numbers (T1, T2, T3) are an **upper bound**, not a win. T3
  (loose-token Jaccard) is the most circular of all — it is the pair-construction
  statistic itself — and is reported as a reference line, not as a competitor.
- The **glyph tier** (G1, G2) and the **translation tier** (L1) are the honest tiers: the
  pair set knows nothing about the sign sequence or the translation, so a glyph or
  translation method that finds the partner has found it on evidence the selection did not
  supply. They are evaluated only on the pairs where **both** rows carry the field.
- The comparison the question actually asks — *edit distance vs n-gram cosine* — is a
  comparison of two methods on the **same** pair set, so the selection bias applies
  equally to both and cannot by itself decide T2 > T1 or G2 > G1.

### 5. Ten hand-checked pairs

Ten pairs will be printed in full (both transliterations, both sources) and judged by
reading them: *is this really the same sentence in two editions?* The verdict, including
any pair that is not, is written into this document whatever it says.

---

### 6. The methods (fixed before running)

Task, per pair, per direction: take one row's text in a tier, exclude that row itself,
score **every** corpus row, and record the rank of the partner edition. Both directions
(A→B and B→A) are always reported separately.

| id | tier | method |
|----|------|--------|
| T1 | transliteration | char 2–4-gram cosine over `mdc_norm` — today's `app.retrieval.tfidf.NgramIndex`, the same object `build_search_index` builds. **The baseline.** |
| T2 | transliteration | edit-distance re-rank of T1's top 50, by `rapidfuzz.distance.Levenshtein.normalized_similarity` over `mdc_norm`. The tail below rank 50 keeps T1's order, so T2 can only reorder the top 50. |
| T3 | transliteration | loose-token Jaccard over the folded token sets — the pair-construction statistic. Reference line, see §4. |
| G1 | signs | sign 1–3-gram cosine over `hieroglyphs_norm`, on the same `NgramIndex` class with a sign analyzer. The analyzer takes the **sign code points** (each hieroglyph codepoint, and each `<g>ID</g>` placeholder codepoint, is one sign), discards the group/whitespace boundaries, and emits 1-, 2- and 3-grams of that sequence. Group boundaries are discarded deliberately: two editions of the same sentence group signs into quadrats differently, and that is not a difference we want to punish. |
| G2 | signs | edit-distance re-rank of G1's top 50, `Levenshtein.normalized_similarity` over the sign-code-point string. |
| L1 | translation | char 2–4-gram cosine over `translation`, same analyzer as T1. **Only** on pairs whose two translations are in the same language, decided by source: TLA and AES are German, BBAW is English, Ramses has no translation. A German–English pair is not an evaluable translation pair and is excluded from L1's n. |
| C1 | combined | reciprocal rank fusion, `k = 60`, over the tiers available for that pair: `score(row) = sum over tiers 1/(60 + rank_tier(row))`. |
| C2 | combined | mean of the min–max normalised per-row scores of the available tiers. |

Which per-tier method feeds C1/C2 is fixed here: **T1 for transliteration, G1 for signs,
L1 for translation** — the cosine tier, not the re-ranked one, so that the combination is
not silently carrying the T2/G2 result.

Ranking pool: all 130,472 corpus rows for every method; the query row itself is removed.
Rows with an empty field score 0 and simply lose. Ties are broken by corpus row order
(`numpy.argsort(..., kind="stable")`), the same order the app would show.

### 7. Metrics and the pre-registered reading

Per method × tier × direction × source pair, and pooled: **MRR**, **recall@1**,
**recall@3**, **recall@10**, and **n** (how many pairs that tier could be evaluated on).

> **Pre-registered reading.** "Edit distance improves on n-gram cosine" is declared true
> if and only if **T2 > T1 in MRR in both directions** and **G2 > G1 in MRR in both
> directions**. A split verdict (one tier yes, one no; or one direction only) is reported
> as a split verdict, not rounded into a win. The per-source-pair table is reported
> whatever the pooled number says, because **Ramses↔TLA is the hard case** — different
> yod (`i` vs `ꞽ`), different plural marker (`.PL` vs `.w`), MdC vs Unicode conventions —
> and a pooled average that hides a Ramses↔TLA failure is not an answer to Nederhof.

Also pre-registered: **peak RSS is printed** and must stay under 6 GB; one corpus load per
process.

### 8. What the feature will then use

The UI page ranks by the method this measurement favours per tier (T1 or T2; G1 or G2;
L1), and says so in a caption on the page with the measured MRR. That is decided by the
table, not chosen afterwards.

---

## Results

*(written after the run; see the sections below)*
