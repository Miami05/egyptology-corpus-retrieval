# Plan: source scaffolding — checks before the Zoom with Camilla (2026-10-11)

Prompted by Camilla's reply to Email 8 (draft answer: Email 11 in `docs/outreach-messages.md`).
Her objection, in one line: *give me the hieroglyphs and the source, so I have something
real to go from.* This plan checks everything that objection touches, in order, before
any code changes. Each step says what is checked, how, and what counts as pass or fail.
Nothing here is a fix yet; fixes are decided after the checks.

## What is already known (measured 2026-10-11)

| Source | Rows | Without hieroglyphs | What `source_ref` records |
|---|---|---|---|
| AES | 9,823 | 0% | text + sentence id (linkable) |
| TLA | 28,369 | 42% | `tla_earlier.parquet#row=N` (a row in our file, not a text) |
| BBAW | 52,216 | 90% | dataset name only, same on every row |
| Ramses | 40,064 | 30% | `ramses-trl … train line N` (anonymous line) |

- The TLA Hugging Face releases carry no text id at all (features: hieroglyphs,
  transliteration, lemmatization, UPOS, glossing, translation, dateNotBefore, dateNotAfter).
- Ramses rows include **all** of Rosmorduc's split: 37,830 train, 872 val, **1,362 test**.
- Ramses licence is settled (CC BY-SA grant, 2026-09-04, `DATA-LICENSE.md`).

---

## Phase 0 — Today, before anything technical

1. **Send Email 11**, then the reviewer key by a separate channel. Pass: she replies
   "unlocked".
2. **Read Rosmorduc 2020** (the article on automatic transliteration of Late Egyptian built
   on `ramses-trl`). Note: what baseline he compares against, his test-set accuracy, and
   whether a most-frequent-reading baseline is reported. Output: a short note in this file.
3. **Fix a stale line:** `DATA-LICENSE.md` says examples.csv "does not yet contain Ramses
   rows"; it holds 40,064. Doc-only change.

## Phase 1 — Provenance: can each sentence be traced to a text?

Goal: for every source, know whether a real text reference exists *upstream* and was
dropped, or never existed.

| Step | Check | How | Pass |
|---|---|---|---|
| 1a | AES links work | open 10 random AES `source_ref`s on the AES/TLA site | 10/10 open the right sentence |
| 1b | TLA can be re-linked | take 20 random TLA rows, search the exact transliteration on the TLA web interface; does a unique text come back? | ≥ 18/20 unique hits → re-linking is feasible |
| 1c | BBAW can be re-linked | the `phiwi/bbaw_egyptian` set comes from AED-TEI, which has text ids; match 20 random rows by exact transliteration + translation | ≥ 18/20 unique hits |
| 1d | Ramses has any mapping | check Zenodo 4954597, the Ramsès site and the zip for any line → text table; if none, ask Liège in the next mail | a table exists, or a recorded "no" |
| 1e | St Andrews | confirm its rows carry text + line (private corpus, reviewer-only) | ref names text and line |

Decision after Phase 1: for each source, either **re-link** (a script, later) or
**label honestly** in the UI ("source text not recorded in this corpus").

## Phase 2 — Hieroglyphs: missing at source, or lost on import?

| Step | Check | How | Pass |
|---|---|---|---|
| 2a | TLA: 42% without | count empty `hieroglyphs` in the raw parquet vs processed rows | raw count = processed count (nothing lost) |
| 2b | BBAW: 90% without | same comparison against `train.parquet` | same |
| 2c | Ramses: 30% without | compare against `src-*.txt` (Gardiner codes) — are the codes there but not converted to Unicode? | if codes exist, conversion is a fixable loss |
| 2d | UI | for 5 real queries, how many of the top 3 suggestions show hieroglyphs? | baseline number recorded |

Any "lost on import" is a bug to fix first; "missing at source" becomes a ranking or
display question (prefer or mark rows with hieroglyphs).

## Phase 3 — Overlap checker: is a test passage already in the corpus?

1. **Build** a script: input lines of transliteration, output for each line the closest
   corpus sentence, a similarity score, and a label `in corpus` / `partly` / `new`.
   It normalises conventions (yod `ꞽ`/`j`/`i`, spacing before `=`) with the same fold the
   tool uses.
2. **Gate tests** (must pass before trusting it):
   - Camilla's Ahmose line → `in corpus` (St Andrews, with the key) or `partly`.
   - A sentence invented by editing 3 words of a real one → `partly`.
   - 20 random Ramses **test** lines → `in corpus` (they are, see above).
3. **Contamination question for Rosmorduc:** decide whether to build a corpus variant
   without Ramses test lines, so the tool can be compared with his published numbers
   fairly. Do not quote any comparison before that.

## Phase 4 — Kitchen (KRI) test set, with Camilla

1. Receive the PDFs. Store them under `data/private/` (gitignored), never in the repo or
   on the server. They are for private testing only.
2. Ask her for 3–5 passages she wants tried, **with her transliteration** (that is both the
   input and the gold answer).
3. Run the Phase 3 checker on each line; keep only `new` lines as the real test, report
   `in corpus` lines separately as "found", not "read".
4. Run the tool; for each line record top 3, whether the gold is among them, and the
   supporting sentences **with hieroglyphs and source**.
5. **Zoom pack:** one page per passage: hieroglyphs, her transliteration, the tool's
   suggestion, the evidence sentences with their sources. Pass: every item on the page
   is something she can check without asking what it means.

## Phase 5 — A rule for anything sent to an expert

Before sending, every case must have: hieroglyphs, the edition / text reference, a
translation, and one clear question. No test-generated strings, no internal ids. One ask
per email. (Adds to the lesson already in the learning journal: show reviewers the
input, never the internal key.)

---

## Order and size

Phase 0 today. Phases 1 and 2 are read-only checks, about a day together. Phase 3 is
the first code (half a day plus gates). Phase 4 waits for Camilla's PDFs and passages.
The Zoom is offered only after Phase 4 step 3.

---

## Results of Phases 1 and 2 (run 2026-10-11, read-only, 9 checks, seed 11)

Full agent outputs: workflow run `wf_8b3bb391-2aa`; scratch scripts under the session
scratchpad `checks/<step>/` (not kept in the repo).

| Step | Verdict | Finding |
|---|---|---|
| 1a AES | inconclusive (data: pass) | 10/10 sampled refs resolve to the right sentence in AED-TEI on GitHub, which also carries text title + line count (e.g. "Eb 857-877, 105,3"). TLA website now sits behind a bot-check wall, so its `/sentence/<id>` link is unverified: open 2-3 by hand. |
| 1b TLA | fail | No ids in the HF releases, website search not automatable. Via AES ids (2-of-3 key rule): ~8.3k Earlier/Late rows can get a TLA sentence id, ~0.4k a text id only; ~3.5k ambiguous, ~3k unmatched. Demotic (~12k): no source for ids. |
| 1c BBAW | pass | 18/20 unique; whole corpus 89.6% re-link to one AED-TEI sentence (90.2% at text level). ~5.1k rows stay unlinked. |
| 1d Ramses | fail | No mapping anywhere, and the lines are shuffled, so the source text cannot be recovered. Ask Liège (sentence drafted below). |
| 1e St Andrews | pass (data), UI gap | 100% name text + witness, 93.6% also a line; but the app shows the reference only in the Source tab for the top match. |
| 2a TLA glyphs | pass | Nothing lost. All 11,996 empty rows are Demotic (another script, no hieroglyphs exist). Hieroglyphic/hieratic TLA coverage is 100% (16,373/16,373). |
| 2b BBAW glyphs | pass | Nothing lost on kept rows. Source is 65% empty; the importer's deliberate drops (lacunae, alignment mismatches, ~15k duplicates of TLA/AES) raise it to 90%. |
| 2c Ramses glyphs | pass (design choice) | All 12,127 empty rows *have* Gardiner codes; they are blanked by the alignment gate (10,068 group/word count mismatches, 2,059 lacunae). A display-only glyph column could fill ~7.0k. `<g>Ff1</g>` placeholders (Ramses-internal codes with no Unicode sign) sit in 10,358 rows and are shown raw. |
| 2d UI | baseline recorded | 5 real queries, 15 suggestion cards: **0/15 show hieroglyphs on the card, 0/15 show a source an Egyptologist could look up.** |

### What this means

- **No import bug lost hieroglyphs.** The gaps are Demotic (correctly empty), BBAW's source,
  and the Ramses alignment gate (a choice that can be complemented by a display-only column).
- **The real gap is display:** the cards show neither signs nor source, even when both exist.
  That is the single most visible fix for Camilla.
- **Re-linkable:** AES (all), BBAW (~90%), TLA Earlier/Late (~half). **Not re-linkable:** Ramses,
  TLA Demotic: label "source text not recorded in this corpus".

### Fix list (ordered, nothing done yet)

1. Card shows the supporting row's hieroglyphs, or "no hieroglyphs recorded in this source".
2. Card shows a real citation where one exists (AES now; St Andrews text + line for reviewers),
   and "source text not recorded" instead of a parquet row / "train line N" / dataset name.
3. Re-link script for BBAW (AED-TEI) and TLA Earlier/Late (via AES ids); spot-check 20 by hand.
4. Ramses display-only glyph column (~7k rows); render `<g>Ff…</g>` as a neutral box, not raw markup.
5. Report TLA Demotic separately in coverage numbers and docs.
6. Mail Liège: "Could you share, for the Ramses transliteration corpus V. 2019-09-01 (Zenodo
   4954597), a table mapping each line of the train/val/test/ctest/htest files to its Ramses
   Online text identifier, so that we can cite every example back to its source text?"
7. Small: the AES import changes case in places (`.PL`→`.pl`, `Nb.t`→`nb.t`); check whether intended.
