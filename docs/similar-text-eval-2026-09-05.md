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

Built by `scripts/build_cross_edition_pairs.py` and measured by
`scripts/run_similar_text_eval.py` on 2026-09-05, corpus 130,472 rows. Both scripts are
deterministic; re-running the builder produced a byte-identical CSV, and re-running the
evaluation reproduced every number below.

### The pair set

`data/benchmarks/cross_edition_pairs_v1.csv` — 300 pairs, 600 distinct corpus rows.

Candidate generation found **182,843** distinct cross-source pairs in the band `[0.5, 0.9)`
in **180 s** at **0.63 GB** peak RSS, and separately found and discarded **1,538**
near-copy pairs at Jaccard `>= 0.9`. Eligible rows (>= 5 loose tokens): 107,637 of 130,472.

| source pair | candidates in band | selected |
|---|---|---|
| AES↔BBAW | 19,048 | 50 |
| AES↔Ramses | 7,405 | 50 |
| AES↔TLA | 9,751 | 50 |
| BBAW↔Ramses | 42,261 | 50 |
| BBAW↔TLA | 78,355 | 50 |
| Ramses↔TLA | 26,023 | 50 |

(An earlier run of the builder reported 497,269 and 9,192 here. Those were emission counts,
not pair counts: two rows that are the same sentence share most of their prefix, and the
candidate loop reached each pair once per shared prefix token. Caught by the synthetic-frame
test in `tests/test_similar_text.py`, which expected one near-copy and was told five. The
selected pair file is **byte-identical** either way — the greedy selection already skipped a
pair whose rows were used — so no measured number below is affected; only these two totals
were wrong.)

Every source pair had far more than 50 candidates, so the round-robin gave all six an
equal share: the stratification is exactly even, not "as even as the data allows".

Field coverage of the selected pairs — this is what each tier can be measured on:

| both rows have… | pairs | which source pairs |
|---|---|---|
| hieroglyphs | 180 of 300 | AES↔TLA 49, AES↔BBAW 44, Ramses↔TLA 41, AES↔Ramses 38, BBAW↔TLA 6, BBAW↔Ramses 2 |
| a same-language translation | 48 of 300 | AES↔TLA 48 only |

**The translation tier is measurable on AES↔TLA and nothing else**, because TLA and AES
translate into German and BBAW into English, and Ramses has no translation at all. That is
a fact about the corpus, not a choice made here, and it is the single biggest limitation
of this evaluation: L1's 96 (pair, direction) cases are all one source pair.

A second limitation, visible only after the build: the selected pairs' Jaccard is
0.714–0.895, **mean 0.858**, clustered just under the exclusion line. That follows from
the pre-registered `-jaccard` sort ("most confidently the same sentence first"), which was
fixed before the numbers existed and is therefore kept — but it means these 300 pairs are
the *easy* end of the band, and a set drawn from the middle of it would be harder. Stated,
not fixed after the fact.

### The ten hand-checked pairs

Printed in full by the builder (`--hand-check 10`), spread across all six source pairs.
Verdict pair by pair, from reading them:

| pair | source pair | J | same sentence? |
|---|---|---|---|
| XED_001 | AES↔BBAW | 0.895 | **Partly.** Both carry the Aten didactic name + `ḏi̯ ꜥnḫ ḏ.t nḥḥ`; BBAW's row wraps it in an oath (`ꜥnḫ ꞽt(ꞽ)=ꞽ …`) that AES's does not. Same text, different sentence boundary. |
| XED_002 | AES↔Ramses | 0.889 | Yes. `nꜥi̯ pw ꞽri̯.n ḥm=f m-ḫd` / `nꜥꞽ.t pw ꞽrꞽ.n ḥm=f m ḫd` — the Piye stela, two editions. |
| XED_003 | AES↔TLA | 0.889 | Yes. Identical but for `ꞽmn-m-ḥꜣ.t` / `ꞽnmn-m-ḥꜣ.t` (a typo in one edition). |
| XED_004 | BBAW↔Ramses | 0.889 | Yes. `bw smn wr ḥr tꜣy=sn ꞽsb.t` / `bw smn.n wr ḥr tꜣy.sn ꞽsb.t`. |
| XED_005 | BBAW↔TLA | 0.895 | Yes. The same Pyramid-Text line; one witness has `n wnꞽs`, the other `n =k` — a real textual variant, which is exactly what a cross-edition pair should look like. |
| XED_006 | Ramses↔TLA | 0.889 | Yes. `ḏd nꜣ nṯr.PL-ꜥꜣ.PL wr.PL šꜣꜥ.PL-ḫpr` / `ḏd nꜣ nṯr.w ꜥꜣ.w wr.w <n> šꜣꜥ ḫpr` — same sentence, different word division. |
| XED_151 | AES↔BBAW | 0.875 | Yes. Same prescription, BBAW's row drops the repeated `qꜣw`; identical translations. |
| XED_152 | AES↔Ramses | 0.750 | **No.** `ꞽw pꜣ mnꞽꜣ.w ḥr ḏd n=f` ("the herdsman said to him") vs `ꞽw=f (ḥr) ḏd n=w` ("he said to them"). Same construction, different subject and different object — two different sentences. |
| XED_153 | AES↔TLA | 0.857 | Yes. Identical but for a leading `ꞽw`; identical translations. |
| XED_154 | BBAW↔Ramses | 0.875 | Yes, though it is a royal name (`Ḥr.w Kꜣ-nḫt-ḫꜥ-m-Wꜣs.t`), not a sentence — the same string, divided into words differently. |

**Verdict: 8 of 10 are plainly the same sentence in two editions, 1 (XED_001) is the same
text cut at a different sentence boundary, and 1 (XED_152) is a false pair** — two short,
wholly formulaic Late Egyptian clauses that share every grammatical word and no content.
So roughly one pair in ten is noise, and the failure mode is short sentences built only
from function words. That noise floor should be read into every number below: a method
cannot score better than the pair set is right.

### The measurement

3,340 result rows in `data/benchmarks/similar_text_eval_v1_results.csv`. Peak RSS
**1.15 GB** (limit 6 GB), one corpus load. Index builds: transliteration 2.7 s, signs
1.3 s, translation 4.5 s, loose-token 1.5 s; all 600 queries in 45 s.

#### Per method, per direction (pooled over source pairs)

| method | tier | direction | n | MRR | R@1 | R@3 | R@10 |
|---|---|---|---|---|---|---|---|
| T1 | transliteration | a→b | 300 | 0.718 | 0.590 | 0.830 | 0.907 |
| T1 | transliteration | b→a | 300 | 0.723 | 0.613 | 0.793 | 0.917 |
| T2 | transliteration | a→b | 300 | 0.708 | 0.590 | 0.803 | 0.890 |
| T2 | transliteration | b→a | 300 | 0.723 | 0.630 | 0.777 | 0.893 |
| T3 | transliteration | a→b | 300 | 0.781 | 0.660 | 0.873 | 0.977 |
| T3 | transliteration | b→a | 300 | 0.825 | 0.723 | 0.910 | 0.977 |
| G1 | signs | a→b | 180 | 0.726 | 0.650 | 0.772 | 0.844 |
| G1 | signs | b→a | 180 | 0.741 | 0.667 | 0.783 | 0.856 |
| G2 | signs | a→b | 180 | 0.745 | 0.667 | 0.789 | 0.867 |
| G2 | signs | b→a | 180 | 0.748 | 0.661 | 0.794 | 0.883 |
| L1 | translation | a→b | 48 | 0.628 | 0.562 | 0.688 | 0.750 |
| L1 | translation | b→a | 48 | 0.626 | 0.562 | 0.646 | 0.750 |
| C1 | combined | a→b | 181 | 0.729 | 0.624 | 0.801 | 0.917 |
| C1 | combined | b→a | 181 | 0.754 | 0.663 | 0.807 | 0.923 |
| C2 | combined | a→b | 181 | 0.738 | 0.624 | 0.807 | 0.923 |
| C2 | combined | b→a | 181 | 0.769 | 0.680 | 0.818 | 0.939 |

#### Per method, both directions pooled

| method | tier | n | MRR | R@1 | R@3 | R@10 |
|---|---|---|---|---|---|---|
| T1 | transliteration | 600 | 0.721 | 0.602 | 0.812 | 0.912 |
| T2 | transliteration | 600 | 0.715 | 0.610 | 0.790 | 0.892 |
| T3 | transliteration | 600 | 0.803 | 0.692 | 0.892 | 0.977 |
| G1 | signs | 360 | 0.733 | 0.658 | 0.778 | 0.850 |
| G2 | signs | 360 | 0.747 | 0.664 | 0.792 | 0.875 |
| L1 | translation | 96 | 0.627 | 0.562 | 0.667 | 0.750 |
| C1 | combined | 362 | 0.742 | 0.644 | 0.804 | 0.920 |
| C2 | combined | 362 | 0.754 | 0.652 | 0.812 | 0.931 |

**These rows are not comparable to each other**: each method answered a different number
of cases. The like-for-like table below is the one to read for C1/C2.

#### Like-for-like: the 181 pairs (362 cases) where at least two tiers existed

| method | tier | n | MRR | R@1 | R@3 | R@10 |
|---|---|---|---|---|---|---|
| T1 | transliteration | 362 | 0.751 | 0.646 | 0.815 | 0.925 |
| T2 | transliteration | 362 | 0.745 | 0.657 | 0.801 | 0.895 |
| T3 | transliteration | 362 | 0.820 | 0.718 | 0.887 | 0.981 |
| G1 | signs | 360 | 0.733 | 0.658 | 0.778 | 0.850 |
| G2 | signs | 360 | 0.747 | 0.664 | 0.792 | 0.875 |
| L1 | translation | 96 | 0.627 | 0.562 | 0.667 | 0.750 |
| C1 | combined | 362 | 0.742 | 0.644 | 0.804 | 0.920 |
| C2 | combined | 362 | 0.754 | 0.652 | 0.812 | 0.931 |

On the same cases, **combining tiers is a wash**: C2 beats T1 alone by 0.003 MRR and C1
loses to it by 0.009. The only thing the combination reliably buys is a little recall at
depth 10 (C2 0.931 vs T1 0.925). The pooled table's apparent "C2 0.754 > T1 0.721" was an
artefact of C1/C2 only being asked the easier, better-annotated 181 pairs.

#### Per method, per source pair (both directions pooled)

| method | tier | source pair | n | MRR | R@1 | R@3 | R@10 |
|---|---|---|---|---|---|---|---|
| T1 | transliteration | AES↔BBAW | 100 | 0.824 | 0.750 | 0.870 | 0.980 |
| T1 | transliteration | AES↔Ramses | 100 | 0.477 | 0.300 | 0.600 | 0.750 |
| T1 | transliteration | AES↔TLA | 100 | 0.802 | 0.730 | 0.820 | 0.950 |
| T1 | transliteration | BBAW↔Ramses | 100 | 0.749 | 0.580 | 0.920 | 0.980 |
| T1 | transliteration | BBAW↔TLA | 100 | 0.685 | 0.550 | 0.810 | 0.890 |
| T1 | transliteration | Ramses↔TLA | 100 | 0.789 | 0.700 | 0.850 | 0.920 |
| T2 | transliteration | AES↔BBAW | 100 | 0.797 | 0.720 | 0.830 | 0.970 |
| T2 | transliteration | AES↔Ramses | 100 | 0.470 | 0.330 | 0.580 | 0.650 |
| T2 | transliteration | AES↔TLA | 100 | 0.753 | 0.670 | 0.780 | 0.950 |
| T2 | transliteration | BBAW↔Ramses | 100 | 0.773 | 0.620 | 0.940 | 0.980 |
| T2 | transliteration | BBAW↔TLA | 100 | 0.683 | 0.570 | 0.760 | 0.870 |
| T2 | transliteration | Ramses↔TLA | 100 | 0.816 | 0.750 | 0.850 | 0.930 |
| T3 | transliteration | AES↔BBAW | 100 | 0.843 | 0.760 | 0.890 | 1.000 |
| T3 | transliteration | AES↔Ramses | 100 | 0.642 | 0.440 | 0.810 | 0.950 |
| T3 | transliteration | AES↔TLA | 100 | 0.857 | 0.790 | 0.880 | 0.980 |
| T3 | transliteration | BBAW↔Ramses | 100 | 0.827 | 0.680 | 0.980 | 1.000 |
| T3 | transliteration | BBAW↔TLA | 100 | 0.772 | 0.670 | 0.850 | 0.960 |
| T3 | transliteration | Ramses↔TLA | 100 | 0.880 | 0.810 | 0.940 | 0.970 |
| G1 | signs | AES↔BBAW | 88 | 0.824 | 0.750 | 0.864 | 0.955 |
| G1 | signs | AES↔Ramses | 76 | 0.501 | 0.408 | 0.566 | 0.618 |
| G1 | signs | AES↔TLA | 98 | 0.702 | 0.602 | 0.765 | 0.888 |
| G1 | signs | BBAW↔Ramses | 4 | 0.505 | 0.500 | 0.500 | 0.500 |
| G1 | signs | BBAW↔TLA | 12 | 0.839 | 0.750 | 0.917 | 0.917 |
| G1 | signs | Ramses↔TLA | 82 | 0.883 | 0.854 | 0.890 | 0.915 |
| G2 | signs | AES↔BBAW | 88 | 0.835 | 0.761 | 0.864 | 0.966 |
| G2 | signs | AES↔Ramses | 76 | 0.505 | 0.408 | 0.553 | 0.645 |
| G2 | signs | AES↔TLA | 98 | 0.736 | 0.612 | 0.816 | 0.939 |
| G2 | signs | BBAW↔Ramses | 4 | 0.505 | 0.500 | 0.500 | 0.500 |
| G2 | signs | BBAW↔TLA | 12 | 0.801 | 0.750 | 0.833 | 0.833 |
| G2 | signs | Ramses↔TLA | 82 | 0.893 | 0.854 | 0.915 | 0.939 |
| L1 | translation | AES↔TLA | 96 | 0.627 | 0.562 | 0.667 | 0.750 |
| C1 | combined | AES↔BBAW | 88 | 0.835 | 0.773 | 0.852 | 0.966 |
| C1 | combined | AES↔Ramses | 76 | 0.513 | 0.342 | 0.645 | 0.763 |
| C1 | combined | AES↔TLA | 100 | 0.723 | 0.620 | 0.790 | 0.960 |
| C1 | combined | BBAW↔Ramses | 4 | 0.344 | 0.000 | 0.500 | 1.000 |
| C1 | combined | BBAW↔TLA | 12 | 0.847 | 0.750 | 0.917 | 1.000 |
| C1 | combined | Ramses↔TLA | 82 | 0.880 | 0.829 | 0.915 | 0.951 |
| C2 | combined | AES↔BBAW | 88 | 0.830 | 0.761 | 0.852 | 0.966 |
| C2 | combined | AES↔Ramses | 76 | 0.541 | 0.368 | 0.658 | 0.803 |
| C2 | combined | AES↔TLA | 100 | 0.734 | 0.620 | 0.790 | 0.970 |
| C2 | combined | BBAW↔Ramses | 4 | 0.625 | 0.250 | 1.000 | 1.000 |
| C2 | combined | BBAW↔TLA | 12 | 0.854 | 0.750 | 0.917 | 1.000 |
| C2 | combined | Ramses↔TLA | 82 | 0.884 | 0.841 | 0.915 | 0.951 |

The pre-registration named **Ramses↔TLA** as the hard case, on the reasoning that the yod,
the plural marker and the MdC conventions differ. **That prediction was wrong**: Ramses↔TLA
is among the *easiest* source pairs (T1 0.789, G1 0.883, G2 0.893 — the best sign score of
any pair), because `normalize_transliteration` already folds all three yods together and
`fold_plural_marker` already folds `.PL` to `.w`. The hard case is **AES↔Ramses**
(T1 0.477, G1 0.501): AES is Earlier Egyptian literary and Ramses is Late Egyptian, so the
two editions of "the same" sentence differ in language stage as well as in convention, and
these are the pairs with the lowest Jaccard in the set (mean 0.769 against 0.858 overall).
Naming a hard case in advance and being wrong about it is the point of naming it in
advance.

### The pre-registered reading

```
T2 vs T1, a→b: 0.7076 vs 0.7185 -> does not improve
T2 vs T1, b→a: 0.7230 vs 0.7234 -> does not improve
G2 vs G1, a→b: 0.7454 vs 0.7260 -> improves
G2 vs G1, b→a: 0.7485 vs 0.7406 -> improves
```

> **VERDICT: no. Edit distance does not improve on n-gram cosine** under the rule fixed in
> §7 (T2 > T1 *and* G2 > G1 in MRR in both directions).

It is a split verdict and is reported as one, not rounded into a win either way:

* **On transliteration the edit-distance re-rank makes things slightly worse.** T2 loses
  0.011 MRR one way and 0.0004 the other, and loses recall at every depth (R@3 0.790 vs
  0.812, R@10 0.892 vs 0.892→0.890/0.893). It gains a little R@1 (0.610 vs 0.602): the
  re-rank does sharpen the very top when the right row is already near it, and blunts
  everything else, because a normalised Levenshtein over a whole sentence is dominated by
  length and by the editorial apparatus that the two editions do not share.
* **On sign sequences it helps, consistently and in both directions** (+0.019 and +0.008
  MRR, R@10 0.875 vs 0.850). Signs are a short alphabet with no editorial apparatus and no
  spelling variation to speak of, which is the setting a plain edit distance is good at.
* The reference line T3, plain loose-token Jaccard, is the best transliteration method by a
  wide margin (0.803 vs 0.721) — **and it is the statistic the pairs were selected on, so
  this number must not be read as a result.** It is what §4 warned about, arriving exactly
  where it was predicted to arrive.
* Combining tiers, measured like-for-like, does not beat the transliteration cosine alone.

The answer to Nederhof, in one sentence: *on 300 cross-edition pairs from this corpus, an
edit-distance re-rank of an n-gram cosine is worth a little on the sign sequence and
nothing (slightly less than nothing) on the transliteration, and fusing the tiers does not
beat the transliteration cosine on the cases where fusion was possible.*

### What the feature uses, and what it cost

Following §8, the "Similar text" page ranks each tier by the method the table favours:

| tier | method used | measured MRR (n) |
|---|---|---|
| transliteration | **T1**, char 2–4-gram cosine | 0.721 (600) |
| signs | **G2**, edit-distance re-rank of the sign-n-gram cosine top-50 | 0.747 (360) |
| translation | **L1**, char 2–4-gram cosine | 0.627 (96) |

T3 is *not* used, despite being the best transliteration number, precisely because it is
the pair-construction statistic and its score here is not evidence.

The two new indexes are built lazily behind `st.cache_resource`, so a visitor who never
opens the page pays nothing. Measured on the developer's Mac, 130,472 rows, on top of a
513 MB corpus-loaded process:

| index | build | added RSS | query |
|---|---|---|---|
| signs (`hieroglyphs_norm`, sign 1–3-grams) | 1.27 s | +66 MB | 7 ms |
| translation (`translation`, char 2–4-grams) | 4.66 s | +456 MB | 38 ms |
| (existing transliteration index, for scale) | 2.76 s | +102 MB | ~10 ms |

The translation index is the expensive one — German and English sentences are long, so
there are far more distinct character 4-grams than in a folded transliteration. +522 MB for
both, against a 3.0 GB peak on a 23 GB box, and only if someone opens the page.

### Deviations from the pre-registration

1. **`detect_tier` has an extra step the sketch did not have** (`app/services/similar_text.py`).
   The rule as written — "Latin text with spaces and no Egyptological letters and no MdC
   digraphs → translation" — sends `htp dj nswt` to the translation tier, which is the most
   likely thing a reader of this app types. So a step was inserted before it: if at least
   half the folded words are in the corpus's own transliteration vocabulary, the input is a
   transliteration. The original rule still runs when that test does not fire (and when no
   vocabulary is supplied). This is a change to a rule that was written down, so it is
   recorded here rather than in a comment; it affects the UI only and no measured number.
2. **The yod mapping asked for in the brief was not needed** and is not applied. The check
   is in `assert_yod_folds_together`, which fails the build if that ever changes.
3. `find_candidate_pairs` emits each pair once from its lower position instead of keeping a
   set of seen pairs. Same pairs, no memory blow-up. Not a rule change.
