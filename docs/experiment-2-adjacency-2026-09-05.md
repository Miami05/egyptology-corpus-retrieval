# Experiment 2 — does word order separate the useful reading from the lookalike?

Run in a separate worktree off `main` at `94db27b`, 130,472-row corpus, project
interpreter `~/venvs/egyptology/bin/python`. Every number below is quoted exactly as a
script printed it. Nothing here is deployed and nothing is pushed.

## Pre-registered

Copied verbatim from `ROADMAP.md`, section "### Experiment 2 — pre-registered
2026-09-05 evening, runs after the deploy (Opus 5 worker)", **before any run**.

> Question: do useful readings keep more of the query's *consecutive* words than the
> lookalikes that outrank them, and does rewarding that fix the boundary losses without
> demoting rank-1 hits? Frozen before running:
>
> 0. **Pre-check, the kill switch (no ranker code).** For each of the seven traced misses,
>    count the distinct query bigrams (two consecutive query tokens) that also occur
>    consecutively in each top-6 candidate. A `_` placeholder only spans (`a _ b` → a,b
>    checked as adjacent across one token); any bigram containing `_` earns nothing; query
>    side only, a longer candidate is never penalised. Alongside the bigram counts, print
>    the ranker's OWN per-term score breakdown (query token overlap, character similarity,
>    relative score, IDF carry-over if any) for the same top-6 rows — the traces' `token`
>    column is the *evaluator's* overlap with the target sentence, not a ranker term, so
>    which term loses the boundary has not yet been shown with numbers. Pass iff in **≥ 4
>    of 7** the useful candidate's count is **strictly** greater than every candidate
>    ranked above it (ties = not beaten). Fail → stop, write a null pre-check; it rejects
>    this bigram measure, not word order in general.
> 1. **Build held-out 2 and held-out 3** (20 each) with the fixed twin guard, disjoint
>    from v4, held-out 1 and each other; exclusion also removes rows sharing a
>    TLA/AES/Ramses `source_text_id` with any existing target and, for BBAW (one text id
>    for 52k rows), a fixed window of neighbouring sequential sentence ids around each
>    target (window fixed before building; the build log reports rows removed per rule).
>    Held-out 2 = selection set (once it picks a winner its score is not confirmation).
>    Held-out 3 = sealed until the final claim.
> 2. **Adjacency bonus vs the unchanged default ranker** (not vs CFG-C). Formula and three
>    candidate weights written down first. Selection by rule on held-out 2 only: top-3 and
>    MRR both ≥ baseline, rank-1 hit count not lower, and at least one of top-3 / MRR
>    strictly higher; among qualifiers, highest MRR. None → null result.
> 3. **Report** on v4, held-out 1, held-out 2: top-3 useful, MRR, and a per-query signed
>    rank change of the first useful candidate. Paste 8/8 required.
> 4. **Confirm before promoting.** Open held-out 3 once, for the selected configuration
>    only: pass iff top-3 and MRR ≥ the default's numbers there and the rank-1 count is
>    not lower. Only then does it become the app default and the expert "after" column is
>    regenerated. Fail → default stays, failed confirmation reported, held-out 3 spent.

The lead's execution brief fixed the remaining free choices before any run as well, and
they are recorded here so nothing can be read as chosen after a result:

- The seven traced misses are **COMP_007, COMP_014** (v4) and **HOLD_001, HOLD_002,
  HOLD_005, HOLD_014, HOLD_026** (held-out 1).
- The BBAW neighbour window is **±20** sequential sentence ids.
- The three adjacency weights are **`adj_a` = 0.08, `adj_b` = 0.16, `adj_c` = 0.24**.
- Held-out 2 is the selection set; held-out 3 stays sealed until step 4.

## Step 0 — the pre-check (kill switch)

### The bigram definition as implemented

`app/services/adjacency.py`, a pure module that **nothing in the ranking path imports at
step 0** — so the measurement that decides whether the experiment continues cannot have
changed a single suggestion.

- **Tokenizer**: `tokenize_query(loose_reading_form(text))`. That is the ranker's own
  pair — `suggest_top_readings` uses exactly these two functions for the loose branch of
  its `translit_overlap` term (`token_overlap_score(query_loose, candidate_loose, …)`),
  and `_evidence_summary` uses them for its shared-token list. The loose ASCII fold is
  the branch that can match an ASCII benchmark query against a Unicode corpus reading at
  all. `tokenize_query` splits on whitespace, `:` and `-`, so a `_` survives as its own
  token and can be recognised as the placeholder.
- **Query side**: the query string the *ranker* was handed, i.e. `searched.reading or
  query_input` under `--query-path app`, folded and tokenised as above.
- **Eligible query bigrams**: the distinct ordered pairs of consecutive query tokens.
  `_` is not a token but a spanner — from `a _ b` the pair `(a, b)` is eligible and
  matches when the candidate contains `a X b` for exactly one intervening token `X`. A
  pair whose two members include `_` earns nothing, so `_ _` and `a _ _ b` contribute 0.
- **Match**: a gap-0 bigram matches when the candidate token sequence has `a` immediately
  followed by `b`; a gap-1 bigram when it has `a X b`. Repeated occurrences count once.
- **Count**: number of distinct eligible query bigrams that match. Query side only —
  candidate length never penalises.

### The ranker's own terms

`suggest_top_readings` gained a `debug_signals: list[dict] | None = None` observation
hook: when a list is passed it receives, per candidate group, each live signal's weight,
raw value and weighted contribution, plus the weight mass and the confidence. Nothing is
read back from it and no branch depends on it; with the default `None` not one statement
of the ranking path changes. This was necessary because the per-term breakdown was not
exposed anywhere, and the traces' `token` column is the *evaluator's* overlap with the
target sentence, not a ranker term.

Probe: `scripts/inspect_adjacency_precheck.py` (read-only; reproduces the harness
pipeline — same stage handling, same `--query-path` branch, the harness's own
`_useful_reason` — with `--top-n 6`, and takes several benchmark files in one corpus
load).

### Command

```
python scripts/inspect_adjacency_precheck.py \
    --case data/benchmarks/competitive_ambiguity_eval_queries_v4.csv:COMP_007,COMP_014 \
    --case data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv:HOLD_001,HOLD_002,HOLD_005,HOLD_014,HOLD_026 \
    --top-n 6
```

`corpus_rows: 130472`, `suggestion_preset: default`, `stage_mode: auto  query_path: app
top_n: 6`. Full raw output kept verbatim at
`data/benchmarks/experiment2_step0_precheck.txt`.

**The probe reproduces the harness.** Its confidences are the published boundary numbers
of the two earlier traces, digit for digit: COMP_007 0.5350 / 0.5330 / 0.5300 / **0.5250**
accepted at rank 4; COMP_014 0.5860 / 0.4840 / 0.4820 / **0.4750**; HOLD_001 rank 4 at
0.5790 behind rank 3's 0.5900; HOLD_002 0.4990 behind 0.5030; HOLD_014 0.5130 behind
0.5420; HOLD_026 0.5390 behind 0.5460; HOLD_005 no useful candidate inside the top 6
(its first useful sits at rank 8). So the table below is measured on the same orderings
the diagnosis described, not on a re-implementation of them.

### The pre-check table

| id | first-useful rank | bigram counts ranks 1..k | beaten |
|---|---|---|---|
| COMP_007 | 4 | [0, 0, 0, 0] | no |
| COMP_014 | 4 | [0, 0, 0, 0] | no |
| HOLD_001 | 4 | [1, 1, 2, 2] | no |
| HOLD_002 | 4 | [0, 1, 0, 0] | no |
| HOLD_005 | none in top 6 | [0, 0, 0, 0, 0, 0] | n/a |
| HOLD_014 | 4 | [1, 1, 2, 2] | no |
| HOLD_026 | 4 | [0, 0, 0, 0] | no |

```
pre-check: FAIL 0/7 (rule: >= 4 of 7 beaten)
```

### Verdict: FAIL 0/7. The experiment stops here.

The pre-registered rule required the first useful candidate's bigram count to be
**strictly** greater than every candidate ranked above it in at least 4 of 7 misses. It
is strictly greater in **none**. Under the frozen protocol that is the kill switch:
no ranker change is made, held-out 2 and held-out 3 are **not built**, and steps 1-4 are
not run. Whether to build them is the lead's call, separately.

What the null actually says, stated carefully: it rejects **this bigram measure on these
seven cases**. It does not show that word order is irrelevant to Egyptological parallel
search. Three distinct things went wrong, and they are different problems:

1. **In four of the seven the measure is dead — every candidate scores 0.** COMP_007,
   COMP_014, HOLD_002 (three of four candidates) and HOLD_026 have no candidate in the
   top 6 that keeps a single consecutive query pair. A bonus proportional to matched
   bigrams would have been identically 0 for every candidate in those windows and could
   not have reordered them at all. That is the sharpest part of the result: for more than
   half the traced misses this term has no resolution whatsoever.
2. **Where it is alive it does not discriminate — it ties.** HOLD_001 and HOLD_014 are
   the two cases with real bigram signal, and in both the useful rank-4 candidate scores
   **2** while the rank-3 candidate it needs to overtake also scores **2** (ranks 1 and 2
   score 1). A tie is explicitly "not beaten" under the rule, and it is worth being blunt
   about why: an additive bonus would move both rows by the same amount and leave the
   ordering exactly as it is. The measure sees something real here — the useful row does
   carry more of the query's word order than the top two — and still cannot pay for the
   one rank that matters.
3. **HOLD_005 has no useful candidate in the window at all**, so the rule is inapplicable
   rather than failed; it is reported as n/a and counted in the denominator of 7, which
   is the strict reading of "≥ 4 of 7".

Two structural reasons this measure was always going to be thin here, both visible in the
per-term tables and neither of them a reason to reject word order in general:

- **The queries are not word order.** Every one of the seven is a builder-generated
  `simplified` or `partial` query: `_competitive_query` takes the target's loose tokens,
  strips light endings, drops stop tokens (`_content_tokens` removes m, n, r, s, f, k, t,
  w, pw, hr) and then keeps a *prefix*. Removing interior tokens destroys adjacency by
  construction — `in pl asha ta pl nb hw` is COMP_014's target with its particles pulled
  out, so the pairs it asks about are pairs that never stood next to each other in any
  sentence. The measure is being asked to find consecutive-word evidence in a query from
  which consecutiveness has already been removed.
- **The corpus writes the same words differently.** The candidate side is Unicode
  transliteration with morpheme dots and editorial brackets; the loose fold turns
  `Ppy Nfr-kꜣ-Rꜥw` into four tokens and `nṯr.du` into two, so an "adjacent" pair in the
  reading is frequently not adjacent after tokenisation. Exact-token adjacency is
  therefore a much stricter test on this data than it sounds.

### What the per-term breakdown shows (the second thing step 0 was for)

Independently of the bigram result, the pre-check answers the question the earlier traces
could not: **which ranker term actually decides the boundary.** The `token` column in the
two trace documents is the *evaluator's* Jaccard against the excluded target sentence,
not a ranker input; these are the ranker's own terms, read straight out of
`suggest_top_readings`.

The pattern is the same in all seven, and it is not the one the wording of Experiment 1
suggested. In every window `relative_score` (0.24) and `mean_score` (0.12) together carry
**0.31-0.36 of a ~0.50-0.63 confidence**, and they are nearly flat across the window
because every candidate in a top-6 sits at 0.82-1.00 of the pool maximum. `exact_or_near`
(0.12) is **0.0000 for every candidate of all seven misses** — no candidate is a near
reading of the query — and `reading_similarity` (0.08) never fires either, so 0.20 of the
nominal weight mass is structurally dead and the live mass is 0.92 throughout. The whole
boundary is therefore decided by the two remaining live similarity terms,
`translit_overlap` (0.20) and `char_similarity` (0.16), against an almost-constant
retrieval-score backdrop.

And there the useful row is usually **winning the term that is meant to reward it**:

| miss | first-useful rank | its translit_overlap | best translit_overlap above it | its char_similarity | best char_similarity above it |
|---|---|---|---|---|---|
| COMP_007 | 4 | **0.3409** | 0.2632 | 0.4383 | 0.5179 |
| COMP_014 | 4 | **0.4545** | 0.5000 | 0.3114 | 0.4336 |
| HOLD_001 | 4 | 0.3846 | 0.5797 | 0.5884 | 0.6278 |
| HOLD_002 | 4 | 0.2564 | 0.2899 | 0.3234 | 0.3972 |
| HOLD_014 | 4 | **0.4348** | 0.3053 | 0.4350 | 0.5040 |
| HOLD_026 | 4 | 0.3497 | 0.3906 | **0.4911** | 0.4560 |

The useful candidate loses `char_similarity` in five of six, by 0.02-0.19 — and
`char_similarity` is a whole-string character-n-gram cosine, which rewards a candidate
for *looking like the query as a string of letters*, length included. COMP_007's rank-4
row wins `translit_overlap` by 0.078 and still loses the query by 0.005 because it is
0.080 behind on `char_similarity`, at 0.16 weight. HOLD_014's rank-4 row wins
`translit_overlap` by 0.129 and loses on the same term. This is a sharper, and better
evidenced, version of Experiment 1's mechanism claim: the term that buries these rows is
**`char_similarity`**, not the absence of a word-order signal — and CFG-B, the
Experiment-1 preset that zeroes `char_similarity`, is exactly the change that rescued
HOLD_002 without any of CFG-A's carry-forward. That is an observation for the lead, not a
proposal: it is read off the same seven misses the whole diagnosis has now been through
several times, so it cannot be tested on them.

### Scope of what was changed in the repository

- `app/services/adjacency.py` — new, pure, **imported by nothing in the ranking path**.
- `app/services/suggestions.py` — the `debug_signals` observation hook only (default
  `None`; no branch depends on it).
- `scripts/inspect_adjacency_precheck.py` — new read-only probe.
- `tests/test_adjacency.py` — pins the bigram definition and pins that passing
  `debug_signals` leaves the suggestions byte-identical.
- `data/benchmarks/experiment2_step0_precheck.txt` — the raw run output.

No preset, weight, threshold, benchmark file or default was touched. `SuggestionWeights`
ships exactly as it did at `94db27b`.

