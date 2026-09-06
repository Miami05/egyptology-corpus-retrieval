# Item D — proper nouns via TLA lemma identifiers (2026-09-06)

Nederhof's second criticism, in his words: *"proper nouns are not normalised, so 'alternatives'
are one name in different forms."* Item D was pre-registered to measure that and, if it was
there, to fix it by grouping suggestions on a name-normalised key.

**Result in two lines.**

* **It is a null, and the pre-registration's own STOP is what stopped it.** NAME-v1 — a
  30-query set built specifically to provoke the symptom — shows **0 name-duplicate slots** in
  its 90 top-3 slots at baseline. The pre-registration says: *"If the baseline duplicate count
  on NAME-v1 is 0, the symptom is absent from our data and D1 is a null before it is built:
  STOP D1, keep the set, report."* **D1 was not built.** No grouping key changed, no switch was
  added, nothing ships.
* **The symptom Nederhof describes is real in our top-3 — but proper nouns are not its cause.**
  Three slot pairs in NAME-v1 are the same sentence twice. The token that differs is `ḏi̯` vs
  `ḏꞽ` (the verb *rḏi̯* "give", twice) and `ꞽt` vs `ꞽt(ꞽ)` ("father"). **0 of 3 are names.**
  Corpus-wide the ceiling agrees: over all 130,472 rows the name-normalised key merges 128 of
  125,338 distinct readings — **0.10%**.

Worktree `/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/agent-a94cfc4424272ac27`,
branch `worktree-agent-a94cfc4424272ac27`, off `main` at `49f1ee3`. Interpreter
`/Users/lediodurmishaj/venvs/egyptology/bin/python`. Public corpus 130,472 rows. Nothing
committed.

---

## 1. The pre-registration, quoted

From `ROADMAP.md`, "**Item D — proper nouns via TLA lemma identifiers — pre-registered
2026-09-06 night (Opus 5 worker)**":

> **Diagnosis (measured 2026-09-06 night).** Lemma ids exist on all 28,369 TLA rows and 9,822
> AES rows (38,191 = 29% of the corpus; none on BBAW/Ramses); tokens, lemma ids and
> part-of-speech tags align on 37,638 of them (553 AES rows misaligned). 3,560 PROPN lemma ids;
> **606 are spelled ≥ 2 ways, 187 ≥ 3** … 6,314 TLA rows contain a variably spelled name.
> Suggestions are grouped today by `strict_reading_key` (sound string), so two readings
> differing only in a name's spelling are two "alternatives". On v4, held-out 1 and LE-v1 the
> top-3 never repeat one lemma sequence … → the symptom is not visible on the existing
> benchmarks and needs its own set.
>
> **Step 0 — NAME-v1, the name-query set (30 queries).** Built with
> `build_competitive_ambiguity_benchmark.py`'s machinery (twin guard against the WHOLE corpus,
> `--exclude-benchmark` for v4, held-out 1 and LE-v1 — that invariant is not touched), with two
> new *candidacy-only* flags: `--require-propn-variant` (the target row is a TLA/AES row whose
> aligned PROPN token belongs to a lemma with ≥ 2 attested spellings) and
> `--substitute-name-spelling` (the query is the row's simplified transliteration with that
> name token replaced by the lemma's most frequent *other* attested spelling — what a reader who
> knows the name under another spelling would type). `query_type = simplified_transliteration`,
> `expected_lemma_ids` as usual. If fewer than 30 rows survive the guard, report the count and
> proceed with ≥ 20; below 20, STOP and report.
>
> **The symptom metric — name-duplicate slots.** For a query's top-3, the *name-normalised key*
> of a suggestion = `strict_reading_key` with every aligned PROPN token replaced by its lemma id
> (rows without a full token/lemma/upos alignment keep the plain strict key). A slot is a
> duplicate when its key equals an earlier slot's. Report the total over NAME-v1 and, for
> reference, over v4, held-out 1 and LE-v1 (expected 0). **Baseline first, on the pristine
> tree.** If the baseline duplicate count on NAME-v1 is 0, the symptom is absent from our data
> and D1 is a null before it is built: STOP D1, keep the set, report.
>
> **D1 — group suggestions by the name-normalised key.** In `suggest_top_readings`, the grouping
> key becomes the name-normalised key (verbs, nouns and inflections stay distinct — only a
> name's spelling collapses); the displayed reading is the best-scoring row's; the suggestion
> gains `variant_readings` (the other spellings with their counts), rendered in the card as "also
> written …"; support and lemma density are computed over the merged group. Rows without
> alignment behave exactly as today. **No retrieval or ranking-weight change.**
>
> **Decision rule (frozen).** Ship iff on NAME-v1: name-duplicate slots decrease strictly vs the
> baseline, top-3 useful ≥ baseline, MRR ≥ baseline − 0.01; AND v4 (0.9 / 0.7917), held-out 1
> (0.75 / 0.6667), LE-v1 (0.8667 / 0.8167) top-3 useful and MRR not lower; paste 8/8;
> segmentation eval byte-identical … Null allowed.
>
> **D2 (recorded, not in this launch).** … It is a retrieval change and gets its own
> pre-registration iff NAME-v1's baseline shows a *recall* problem (target row absent from the
> top-50 pool for ≥ 5 of the 30 queries) — the baseline run reports that count.

Every number in the diagnosis reproduced exactly before anything was built: 28,369 TLA / 9,822
AES rows with lemma ids, 37,638 aligned, 3,560 PROPN lemma ids, 606 spelled ≥ 2 ways, 187 ≥ 3,
6,314 rows carrying one.

## 2. Step 0 — NAME-v1

Two flags were added to `scripts/build_competitive_ambiguity_benchmark.py`.
`--require-propn-variant` narrows *candidacy* only, exactly like `--pool-size`,
`--exclude-benchmark` and `--stage`: the spelling table and the twin guard are both computed
over the whole 130,472-row corpus, because that is what the eval loads.
`--substitute-name-spelling` touches only the generated query string and refuses to run without
the first flag.

The substitution happens on the row's **whitespace tokens**, not on the folded query, because
that is the only level where the token/lemma/upos alignment holds (the simplified fold splits
`ꜥḥꜥ.n` into `aha n` and the alignment would be off by one from there onwards). The substituted
sentence is then put through the ordinary `simplified_transliteration` recipe, so nothing about
how a query is generated changes except which letters the name contributes.

Command:

```
python scripts/build_competitive_ambiguity_benchmark.py \
  --examples data/processed/examples.csv \
  --output  data/benchmarks/competitive_ambiguity_eval_queries_name_v1.csv \
  --require-propn-variant \
  --substitute-name-spelling \
  --exhaustive-twins \
  --exclude-benchmark data/benchmarks/competitive_ambiguity_eval_queries_v4.csv \
  --exclude-benchmark data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv \
  --exclude-benchmark data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv \
  --id-prefix NAME --limit 30
```

Output, verbatim:

```
Twin detection over the full corpus: 130472 rows, 9495 distinct tokens.
Excluding 70 rows named by data/benchmarks/competitive_ambiguity_eval_queries_v4.csv, data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv, data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv and 2 near-twins of them (overlap >= 0.9).
Proper nouns over the full corpus: 3560 PROPN lemma ids, 606 of them spelled >= 2 ways; 6314 of 130472 rows carry one (candidacy filter --require-propn-variant).
Candidates considered: 130472 rows -> 4335 eligible (skipped 72 excluded by --exclude-benchmark, 124092 without a variably spelled proper noun, 30 too short, 206 without distractors, 1737 with a near-identical twin anywhere in the corpus at overlap >= 0.9)
Name respelling: visible in the generated query for 10 of 30 rows; 20 rows where the simplified fold makes the two spellings identical.
Wrote 30 competitive ambiguity benchmark rows to data/benchmarks/competitive_ambiguity_eval_queries_name_v1.csv
```

Filter by filter, from 130,472 rows: **72** removed as v4 / held-out 1 / LE-v1 targets or their
near-twins, **124,092** removed for carrying no variably spelled proper noun, **30** too short,
**206** with no distractor, **1,737** with a near-identical twin anywhere in the corpus →
**4,335 eligible**, of which the top 30 by number of genuine rivals (one per distinct reading)
were written. **30 rows, so the "< 20 → STOP" clause did not fire.** All 30 targets are TLA
rows; 15 Demotic, 15 Earlier Egyptian.

Each row's `notes` records the substitution. The 30 name lemmas and their respellings:

| id | lemma | written in the row | query says instead |
|---|---|---|---|
| NAME_001 | d7020 | tꜣ-rpy.t | tꜣ-rp.t |
| NAME_002 | dm1577 | ꞽr.t-ḥr-r.r=w | ꞽr.t-ḥr-r=w |
| NAME_003 | 400015 | rꜥw | rꜥ |
| NAME_004 | dm6419 | tymrqws | tmrqws |
| NAME_005 | d3911 | ḥ.t-nn-nsw | ḥ.t-nsw |
| NAME_006 | d1997 | pꜣ-ꞽw-rq | pr-ꞽw-lq |
| NAME_007 | dm1652 | pꜣ-ꞽwꞽw-ḥr | pꜣ-ꞽwꞽw-(n-)ḥr |
| NAME_008, 013, 016 | dm1610 | ḥr-sꜣ-ꜣs.t | ḥr-sy-ꜣs.t |
| NAME_009, 010 | 49460 | wsꞽr | (w)sr(.w) |
| NAME_011 | dm1570 | pꜣ-šr-ꜣs.t | pꜣ-šr-n-ꜣs.t |
| NAME_012 | 171880 | tfn.wt | tfn.t |
| NAME_014, 019, 021, 026 | 107500 | ḥr.w | ḥr |
| NAME_015, 024 | dm1554 | pꜣ-dy-ꜣs.t | pa-tw-ꜣs.t |
| NAME_017 | dm1618 | pa-ḥy | pa-ḥe |
| NAME_018 | dm1896 | pꜣ-dy-ḥr-nḏ-ꞽt=f | pꜣ-dy-ḥr-n-ḏr.ṱ=f |
| NAME_020, 022 | 27360 | ꞽnp.w | ꞽnp(.w) |
| NAME_023 | 271 | ꜣs.t | (ꜣ)s.t |
| NAME_025 | 71660 | mnṯ(.w) | mnṯ.w |
| NAME_027 | 49460 | (w)sr(.w) | wsꞽr |
| NAME_028 | 800001 | wnꞽs | ntr.PL |
| NAME_029 | 127020 | s(ꜣ)ḥ | sꜣḥ |
| NAME_030 | dm1698 | hry=w | hry=(w) |

Two honest weaknesses in the set, neither of which changes the conclusion:

* **The respelling is visible in only 10 of 30 generated queries.** The simplified query fold is
  ASCII and marker-free, so `ḥr.w` and `ḥr` both become `hr`, and `ꞽnp.w`/`ꞽnp(.w)` both become
  `inp`. For those 20 rows the query is what it would have been without the flag. This weakens
  the *query* side (D2's territory) but not the metric: the metric looks at what comes back in
  the top 3, and every one of the 30 targets does carry a variably spelled name, so a rival row
  spelling it the other way is retrievable for all 30.
* **NAME_028's substitution is a corpus tagging artefact.** Lemma 800001 (Unis) has one row in
  which a `nṯr.PL` token is tagged PROPN under that id — 644 `wnꞽs` against 1 `ntr.PL` — so
  "most frequent other spelling" picked noise. NAME_028 is also the set's single failure. The
  builder counts raw surface forms deliberately (normalising them would erase the phenomenon),
  and this is the price.

## 3. The metric, and the proof that it changes nothing else

`name_normalised_reading_key` in `app/services/suggestions.py`: `strict_reading_key` with each
aligned PROPN token replaced by its lemma id; a row with no full token/lemma/upos alignment
falls back to the plain strict key, byte for byte. `scripts/run_competitive_ambiguity_eval.py`
gained `name_duplicate_slots` as **one appended column** (last in the file) and one summary
line, plus one further summary line for D2's trigger. Nothing above them reads either value.

Proved rather than asserted — the three frozen benchmarks were re-run and diffed column by
column against their committed result files:

| committed file | shape | only-in-new columns | shared columns that differ |
|---|---|---|---|
| `ceval_v4_v4_app_auto_results.csv` | 20 × 25 → 20 × 26 | `name_duplicate_slots` | **NONE** |
| `ceval_holdout_v4_app_auto_results.csv` | 20 × 25 → 20 × 26 | `name_duplicate_slots` | **NONE** |
| `ceval_le_v1_app_auto_results.csv` | 30 × 25 → 30 × 26 | `name_duplicate_slots` | **NONE** |

The identification of a suggestion with a corpus row is worth stating, because the metric would
be silently vacuous if it were wrong. A `ReadingSuggestion` carries a reading and a list of
source labels; `suggest_top_readings` puts the *best-scoring row* first in both, so
`(supporting_sources[0], canonical_reading(candidate_transliteration))` pins that row down and
`build_annotation_lookup` returns its `lemma_sequence` and `upos`. §5 measures how often that
lookup actually succeeds.

## 4. Baseline — and the STOP

All four runs `--query-path app --stage auto`, corpus 130,472, each into its own results and
failures file.

| set | queries | top-1 useful | top-3 useful | MRR | failures | **name-duplicate slots** | targets absent from pool |
|---|---|---|---|---|---|---|---|
| **NAME-v1** | 30 | 0.8000 | **0.9667** | **0.8833** | 1 | **0** | 0 |
| v4 | 20 | 0.7000 | 0.9000 | 0.7917 | 2 | **0** | 0 |
| held-out 1 | 20 | 0.6000 | 0.7500 | 0.6667 | 5 | **0** | 0 |
| LE-v1 | 30 | 0.7667 | 0.8667 | 0.8167 | 4 | **0** | 0 |

v4 0.9 / 0.7917, held-out 1 0.75 / 0.6667 and LE-v1 0.8667 / 0.8167 are the committed numbers,
reproduced exactly. NAME-v1 is *easier* than any of them (0.9667 / 0.8833): a query built from a
name-bearing sentence is a high-signal query.

**`name_duplicate_slots: 0` on NAME-v1 fires the pre-registered STOP. D1 was not built.**

NAME-v1 per query: useful rank 1 for 24 queries, rank 2 for NAME_004, 017, 019, 024, 029, and no
useful suggestion in the top 3 for NAME_028 (the corrupted substitution of §2). Name-duplicate
slots are 0 for all 30 individually, not merely in total.

## 5. Is the metric measuring anything?

A metric that reads 0 because it is broken looks exactly like one that reads 0 because the
symptom is absent. Four checks, before the null was accepted.

**Synthetic.** `ḥtp ḏi̯ wsꞽr` and `ḥtp ḏi̯ (w)sr(.w)` with lemma 49460 tagged PROPN both key to
`ḥtp ḏi̯ 49460` — collapsed — while their plain strict keys differ. `sḏm =f` and `sḏm.n =f`
(same lemma, tagged VERB) stay two keys. An unaligned row keys identically to
`strict_reading_key`. Pinned in `tests/test_proper_nouns.py`, 9 tests, all passing.

**Coverage on the real run.** Of NAME-v1's 90 top-3 slots, **56 resolved to an annotated corpus
row** and **32 had their key actually rewritten by a lemma id**. The substitution is firing on
more than a third of all slots, e.g.

```
'sẖ pꜣ-dy-wsꞽr sꜣ sy-sbk'                 -> 'sẖ dm1109 sꜣ dm2711'
'ꞽ:rḫ nmt.ꞽ-m-zꜣ=f mr.n-rꜥw rn =k n ḫm …' -> 'ꞽ:rḫ 854416 401175 rn =k n ḫm …'
'ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnp.w tp.ꞽ-ḏw=f'     -> 'ḥtp-ḏi̯ nswt ḥtp-ḏi̯ 27360 tpꞽ-ḏw=f'
```

**Is a collapse even reachable?** For two slots to merge, both must resolve to annotated rows.
**17 of the 30 queries have ≥ 2 annotated slots**; 43 of the 90 slot pairs have both annotated.
So the metric had ample opportunity — the answer is 0 despite it, not because of a lack of it.
The 34 unresolved slots are BBAW/AES parallels of the same passages, which is why they are
unresolved: they capitalise names (`Nmt.ꞽ-m-zꜣ=f`, `Šw`, `Gbb`) and carry no lemma ids at all.

**Plain duplicates.** Duplicate slots under the *plain strict key* are also 0 on NAME-v1 —
today's grouping key is doing its job; there was no duplicate for the name key to remove.

## 6. What the top-3 does contain — Nederhof's symptom, and its actual cause

Loosening the key to the ASCII, marker-free `loose_reading_form` finds **3 duplicate slots** in
NAME-v1: two slots that are visibly the same sentence twice. All three:

| query | slot A | slot B | the only token that differs |
|---|---|---|---|
| NAME_020 | `ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnp.w` | `ḥtp-ḏꞽ nswt ḥtp-ḏꞽ ꞽnp.w` | `ḏi̯` / `ḏꞽ` — the **verb** *rḏi̯* "give" (twice) |
| NAME_022 | `ḥtp-ḏi̯ nswt ḥtp-ḏi̯ ꞽnp.w` | `ḥtp-ḏꞽ nswt ḥtp-ḏꞽ ꞽnp.w` | the same |
| NAME_029 | `ꞽꜣq ꞽr =k ꞽr bw ẖr(.ꞽ) ꞽt =k ꞽr bw ẖr(.ꞽ) gbb` | `[ꞽꜣq] [ꞽr] =[k] [ꞽr] bw ẖr(.ꞽ) ꞽt(ꞽ) =k ꞽr bw ẖr(.ꞽ) Gbb` | `ꞽt` / `ꞽtꞽ` — the **common noun** *ꞽt(ꞽ)* "father" |

This is the finding. **The complaint is right about the shape and wrong about the cause.** In
NAME_020 and NAME_022 the proper noun in the pair — Anubis — is spelled *identically* in both
slots; what differs is a verb's orthography. In NAME_029 the pair does contain Geb under two
capitalisations, but `strict_reading_key` already lowercases and already drops the editorial
brackets, so after those the residue is `ꞽt` vs `ꞽtꞽ` — again not a name. Substituting lemma
ids for proper nouns would have removed **none** of the three.

## 7. The ceiling, corpus-wide

Independently of any benchmark: over all 130,472 rows, how much can the name-normalised key
merge at all?

```
corpus rows: 130472; rows whose key a PROPN id changes: 11899
distinct strict readings:            125338
distinct name-normalised keys:       125307
name keys that merge >= 2 strict readings: 63 (covering 128 strict readings)
```

**63 merges, covering 128 of 125,338 readings — 0.10% of the corpus's distinct readings.** And
they are mostly readings that *are* a name and nothing else, so both members reaching one top-3
is rarer still:

```
'450077'                <- ['nfr-ḥtp', 'nfr-ḥtpw']
'ḥrw 882893'            <- ['ḥrw wꜣḏ', 'ḥrw wꜣḏw']
'600172'                <- ['ḫꜥi̯', 'ḫꜥꞽ']
'nṯrꞽ =k nṯrꞽ 148520'   <- ['nṯrꞽ =k nṯrꞽ stš', 'nṯrꞽ =k nṯrꞽ stẖ']
'zꞽ 70005 ḥnꜥ kꜣ =f'    <- ['zꞽ ḫntꞽ-ꞽrtdu ḥnꜥ kꜣ =f', 'zꞽ ḫntꞽ-ꞽrtꞽ ḥnꜥ kꜣ =f']
```

The diagnosis's headline number (606 lemmas spelled ≥ 2 ways, 6,314 rows) is about *lemmas*;
this is about *sentences*. A name spelled two ways only produces two competing readings when the
rest of the sentence is otherwise identical, and in a corpus of largely distinct sentences that
almost never happens.

## 8. D2's trigger — and a rule that could not be applied as written

The pre-registration triggers D2 iff "the target row is absent from the top-50 pool for ≥ 5 of
the 30 queries". **That rule cannot be applied literally: `_exclude_expected` removes the target
row from the candidate pool for every query, by construction** — that is what makes this a
competitive-ambiguity benchmark. The target is absent from the pool 30 times out of 30, for a
reason that has nothing to do with recall.

What was measured instead, and reported as the summary line `expected_absent_from_pool`: **the
number of queries whose top-50 pool contains no row that would count as a useful-family answer
at all** — i.e. queries no re-ranking rule could possibly have got right, which is the recall
failure D2 addresses. That count is **0 of 30 on NAME-v1** (and 0 on v4, held-out 1 and LE-v1).
Every NAME-v1 query, including the one failure NAME_028, has a useful row inside the 50 the
re-ranker sees.

**D2 is not triggered** under either reading — the literal one is vacuous, the substituted one
is 0 and 0 < 5.

## 9. Gates

Run on this tree, with the metric and the builder flags in place:

* `python scripts/run_segmentation_eval.py` — **unspaced F1 0.939 / exact 0.579, scrambled
  0.946 / 0.635**, and the unseen-word breakdown identical to the committed one. Byte-identical.
* `python scripts/run_expert_paste_eval.py --stage auto` — **passed 8/8**, and
  `data/benchmarks/expert_paste_eval_results.csv` shows as unmodified in `git status` after the
  run, i.e. byte-identical to the committed file.
* `pytest tests/test_phase2_ranking.py tests/test_adjacency.py tests/test_proper_nouns.py`
  — **40 passed**. `pytest tests/test_phase4_evaluation.py tests/test_pipeline_fuzz.py` —
  **52 passed**.
* v4 / held-out 1 / LE-v1 result files: identical in all 25 existing columns (§3).

These gates were part of D1's decision rule. D1 does not exist, so they are not a decision here
— they are the check that the *measurement* code left the shipped behaviour alone, and it did.

## 10. For Nederhof

His criticism, translated into numbers on our corpus: of the top three readings the tool offers,
how often are two of them the same thing with a name written differently? We built a 30-query
set chosen precisely to make that happen — every target sentence contains a proper noun that the
corpus spells at least two ways (Horus as `ḥr.w` / `ḥr` / `ḥr(.w)`, Osiris as `wsꞽr` /
`(w)sr(.w)`, Anubis as `ꞽnp.w` / `ꞽnp(.w)`, Seth as `stš` / `stẖ`), and the query itself asks
for the name under a spelling the sentence does not use. Across those 30 queries' 90 suggestion
slots, with the proper-noun substitution demonstrably firing on 32 of them, the answer is
**zero**. Three slot pairs *are* the same sentence twice — but what makes them look like two
answers is the verb *rḏi̯* written `ḏi̯` in one edition and `ḏꞽ` in another, and the noun
"father" written `ꞽt` and `ꞽt(ꞽ)`. Corpus-wide, normalising every proper noun to its lemma
identifier would merge 128 of 125,338 distinct readings, one tenth of one percent. So the
criticism identifies a genuine defect in the display — near-identical alternatives crowding the
top three — and correctly identifies the mechanism, orthographic variation between editions;
it is only the *class of word* that is wrong. The lever is edition-level orthographic
normalisation of ordinary vocabulary, not a name lexicon. That is a different pre-registration,
and this one is a null.

## 11. What exists now, and what does not

**Added** (uncommitted, in the worktree):

* `data/benchmarks/competitive_ambiguity_eval_queries_name_v1.csv` — NAME-v1, 30 rows, kept as
  the pre-registration asks.
* `scripts/build_competitive_ambiguity_benchmark.py` — `--require-propn-variant` (candidacy),
  `--substitute-name-spelling` (query text), plus `aligned_tokens`, `propn_spelling_table`,
  `variant_name_token`.
* `app/services/suggestions.py` — `aligned_annotation` and `name_normalised_reading_key`. Pure
  functions. **Nothing in `suggest_top_readings` calls them**; the grouping key is unchanged.
* `scripts/run_competitive_ambiguity_eval.py` — the `name_duplicate_slots` column and summary
  line, the `expected_absent_from_pool` summary line, and the helpers behind them.
* `tests/test_proper_nouns.py` — 9 tests pinning the definitions the null was measured with,
  including one that asserts suggestion grouping is *unchanged*, so that a later name-normalised
  grouping key fails loudly rather than drifting in.

**Not built, because the STOP fired:** D1 itself — the name-normalised grouping key,
`variant_readings` on `ReadingSuggestion`, the "also written …" line in the suggestion card,
support and lemma density over a merged group. The three D1 unit tests named in the launch (two
of which describe `variant_readings`) were not written for the same reason; the surviving key
tests are in `tests/test_proper_nouns.py`. No "after" measurement, no per-query rank changes, no
switch, no default change: there is nothing to switch.
