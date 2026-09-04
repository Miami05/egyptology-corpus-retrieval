# Licence audit — 2026-09-04

Read-only audit. Nothing in this document has been applied; the "Proposed changes"
section is a list of suggestions, not a changelog. Every claim below is tied to a page
that was actually fetched on 2026-09-04; where a page could not be reached, or where the
official wording does not settle the question, that is said explicitly rather than
filled in from memory.

---

## **Flag: one item could require removing data (do not act on this yet)**

**`data/processed/helsinki_lexicon.csv` is committed to the public repository, is
declared CC BY-SA 4.0 by the `DATA-LICENSE.md` table, and 50,647 of its 97,340 rows
(`source = Ramses`) plus 4,402 mixed rows (`source = AES+Ramses`) are derived from the
Ramses Transliteration Corpus, whose own README licenses it CC BY-NC-SA 4.0.** The
University of Helsinki released its derived word statistics as CC BY 4.0
(<https://github.com/MaReTEgyptologists/TranslitModels>, README: "This work is licensed
under a Creative Commons Attribution 4.0 International License"; same statement in
`Readme.txt` in <https://zenodo.org/records/7991241>). Neither the Helsinki README nor the
Zenodo record mentions the NC term on the Ramses side. If Helsinki's relicensing of the
Ramses-derived half is not valid — and CC BY-NC-SA 4.0 §3(b)(1) plus the compatibility
page say an adaptation of BY-NC-SA material may only be BY-NC-SA — then this project is
redistributing NC-derived data under a non-NC licence in a public repository, and the fix
is to drop the Ramses-derived rows (the import already supports AES-only) or the file.
`DATA-LICENSE.md` already records this as a good-faith reliance; this audit confirms the
underlying conflict is real and is *not* resolved by anything on the official pages. It
needs an email to Heidi Jauhiainen and/or Serge Rosmorduc, not a code change.

**Second, smaller flag:** the Zenodo record for Ramses (record 4954597) states
`license: {"id": "cc-by-4.0"}` in its own metadata (verified via
<https://zenodo.org/api/records/4954597>), while the README inside
`ramses-trl_2021_05_29.zip` states CC BY-NC-SA 4.0. `DATA-LICENSE.md` asserts the Zenodo
field "is wrong and is not what governs". That is a reasonable reading (the more specific,
in-deposit statement by the rights holder), but it is *this project's* conclusion, not
anything an official page says. It should be labelled as such.

---

## Verdict

The project's core licence position is correct and well documented: the public corpus is
an adaptation of CC BY-SA 4.0 material and is properly released CC BY-SA 4.0, the code is
properly kept MIT, and the private-path design for the two NC corpora is the right shape —
CC's own guidance confirms that the NonCommercial term binds every restricted use while
the ShareAlike term binds only public sharing, so serving BY-SA and BY-NC-SA rows side by
side from separate files, each with its own credit line and never merged into one
distributed dataset, is defensible as non-commercial *use* rather than as an unlawful
single adaptation. Four things need correcting rather than rethinking: the Helsinki/Ramses
chain flagged above; the claim that "the TLA" is CC BY-SA (the TLA *website* is not — only
the raw-data publications are); several §3(a) attribution details (the in-app credit links
the TLA homepage instead of the licensed datasets, carries no warranty-disclaimer notice,
gives no indication-of-changes for the NC rows, and labels the NC rows "CC BY-NC-SA 4.0"
while linking to the source rather than to the licence); and an internal contradiction in
`DATA-LICENSE.md`, whose table puts all of `data/` under CC BY-SA 4.0 while its own
lexicon section says CC BY 4.0. Note also that `data/private/` does not currently exist, so
today's deployment serves no NC rows at all.

---

## 1. Sources: claimed vs official licence

| Source | Claimed in repo / app | Official page says | URL checked | Discrepancy |
|---|---|---|---|---|
| TLA, Original Earlier Egyptian sentences, corpus v18, premium | CC BY-SA 4.0; citation quoted in full | "released under CC BY-SA 4.0 International"; citation on the card matches the repo's wording, including "v1.1, 2/16/2024" | <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium> | **No** |
| TLA, Late Egyptian sentences, corpus v19, premium | CC BY-SA 4.0; cited as "Original Late Egyptian sentences, corpus v19, premium", URL `tla-Late_Egyptian_original-v19-premium`, no version/date | CC BY-SA 4.0. Official title is "Late Egyptian sentences, corpus v19, premium"; official citation includes "v1.0, 1/19/2025"; canonical URL is the lowercase `tla-late_egyptian-v19-premium` (the repo's URL 307-redirects there, so it resolves) | <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium>; also listed as "CC BY-SA 4.0 Int." at <https://aaew.bbaw.de/daten-veroeffentlichungen> | **Yes** (cosmetic: wrong title word, stale URL form, missing version/date) |
| "the Thesaurus Linguae Aegyptiae" as such — linked as the corpus's source in `README.md`, `DATA-LICENSE.md` and the in-app credit | "derived from the Thesaurus Linguae Aegyptiae (TLA), released under CC BY-SA 4.0", hyperlinked to `thesaurus-linguae-aegyptiae.de` | The TLA licences page states **no** CC licence for the website's data. Under "Scientific data": "You can copy and quote individual data sets of this website for academic research purposes, but not entire sub-corpora or larger sets (> 10 website pages)." CC BY-SA applies to the separately published raw-data sets, listed at `aaew.bbaw.de/daten-veroeffentlichungen` | <https://thesaurus-linguae-aegyptiae.de/info/licenses> | **Yes** — the licence claim is true of the datasets the project actually used, not of the site it links to |
| TLA Demotic sentences, corpus v18, premium (downloaded, not shipped) | CC BY-SA 4.0 | "CC BY-SA 4.0 Int." | <https://aaew.bbaw.de/daten-veroeffentlichungen> | **No** |
| AES — Ancient Egyptian Sentences (imported from its relANNIS export) | CC BY-SA 4.0 | "All files: CC-BY-SA 4.0" | <https://github.com/simondschweitzer/aes> | **No** |
| AED-TEI (the corpus AES derives from; the URL the in-app credit links for AES) | CC BY-SA 4.0 | "All files: CC-BY-SA 4.0"; DOI 10.5281/zenodo.3580939, `CITATION.cff` present | <https://github.com/simondschweitzer/aed-tei> | **No** |
| `phiwi/bbaw_egyptian` (January 2018 BBAW snapshot) | CC BY-SA 4.0 | Card licence field: "CC BY-SA 4.0 Deed Attribution-ShareAlike 4.0 International"; states the source as the BBAW January 2018 database snapshot published at edoc.bbaw.de | <https://huggingface.co/datasets/phiwi/bbaw_egyptian> | **No** |
| The original BBAW snapshot itself (Richter, Hafemann, Fischer-Elfert, Dils 2018) | CC BY-SA 4.0 (via the HF redistribution) | "Creative Commons - CC BY-SA - Namensnennung - Weitergabe unter gleichen Bedingungen 4.0 International" | <https://edoc.bbaw.de/frontdoor/index/index/docId/2919> (matched by title/authors/year; see "pages I could not reach" for the URN resolver) | **No** — the chain through `phiwi/` checks out |
| Helsinki "Transliteration Model for Egyptian Words" word lists | CC BY 4.0 | "This work is licensed under a Creative Commons Attribution 4.0 International License" (GitHub README and Zenodo `Readme.txt`); Zenodo licence field "Creative Commons Attribution 4.0 International" | <https://github.com/MaReTEgyptologists/TranslitModels>, <https://zenodo.org/records/7991241> | **No at the Helsinki layer** — but see the bold flag for the upstream Ramses conflict |
| Ramses Transliteration Corpus | CC BY-NC-SA 4.0 per its README; "the Zenodo record's 'CC BY 4.0' field is wrong and is not what governs" | Zenodo metadata: `license: cc-by-4.0`; record title "Ramses automated translitteration software", version 2021-06-15. README inside `ramses-trl_2021_05_29.zip`: "# Ramses Transliteration Corpus, V. 2019-09-01 … The corpus is released using the CC-BY-NC-SA Creative Common License … Please acknowledge its use as 'the Ramses transliteration corpus V. 2019-09-01, University of Liege/Projet Ramses'" (deposit also ships `cc-by-nc-sa.png`) | <https://zenodo.org/records/4954597>, <https://zenodo.org/api/records/4954597>, README extracted from the deposit zip | **Yes, and unresolved** — the two official statements contradict each other; the repo's acknowledgement string matches the README exactly |
| St Andrews Corpus of Ancient Egyptian texts | CC BY-NC-SA 4.0, "confirmed by Mark-Jan Nederhof by email 2026-09-02"; in-app credit labels it CC BY-NC-SA 4.0 and links the texts page as its `licence_url` | The page states **no** licence, copyright or terms of use at all — it offers a Java applet, a download package and PDFs, and notes the site is under construction | <https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/> | **Yes** — nothing public backs the label; the email in `docs/permission-requests.md` is the only basis, and the in-app link points at a page with no licence on it |

---

## 2. Is `examples.csv` an adaptation or a collection?

**It is Adapted Material, on two independent grounds, and CC BY-SA 4.0 is therefore
required for the whole file. The project's current claim is correct.**

First, a terminological point that matters: **the 4.0 licences have no "Collection"
definition.** The word "Collection" appears nowhere in the legal code of CC BY-SA 4.0,
CC BY 4.0 or CC BY-NC-SA 4.0 (checked by text search of all three
`legalcode.en` pages). Version 3.0 had that defined term; 4.0 dropped it. §1 of the 4.0
licences defines only **Adapted Material**: "material subject to Copyright and Similar
Rights that is derived from or based upon the Licensed Material and in which the Licensed
Material is translated, altered, arranged, transformed, or otherwise modified in a manner
requiring permission under the Copyright and Similar Rights held by the Licensor"
(<https://creativecommons.org/licenses/by-sa/4.0/legalcode.en>, §1, "Adapted Material").
The adaptation/collection distinction survives only in the FAQ, as guidance
(<https://creativecommons.org/faq/>, "If I create a collection that includes a work
offered under a CC license, which license(s) may I choose for the collection?").

**Ground A — copyright route (§1).** The rows are not reproduced as received. Gardiner
sign codes with Manuel-de-Codage layout operators are mapped to Unicode hieroglyphs and
regrouped so that one sign group corresponds to one transliteration token; the
transliteration is rewritten from each source's convention into a single house convention
(`j`→`ꞽ`, comma→dot, `≡`/`⸗`→`=`, `{,pl}`→`.pl`, case-folding of proper nouns); rows are
re-segmented, deduplicated across four corpora, and extended with derived columns. The FAQ
sets the threshold: "Generally, a modification rises to the level of an adaptation under
copyright law when the modified work is based on the prior work but manifests sufficient
new creativity to be copyrightable, such as a translation of a novel from one language to
another" (<https://creativecommons.org/faq/>, "When is my use considered an adaptation?").
Re-encoding one scholarly transliteration convention into another, and re-aligning sign
groups to tokens, is an editorial judgement of exactly that kind — `DATA-LICENSE.md`
itself reports that the AES conversion reproduces the TLA form for only 85% of shared
sentences, the remaining 15% differing "in editorial judgement". Note the counter-rule the
project stays clear of: §2(a)(4) says "simply making modifications authorized by this
Section 2(a)(4) never produces Adapted Material" — i.e. pure format/medium conversion
would *not* be an adaptation. If the pipeline were only a character-set transcode, Ground A
would be arguable; it is not only that.

**Ground B — sui generis database rights route (§4(b)), which is decisive.** CC BY-SA 4.0
§4(b): "if You include all or a substantial portion of the database contents in a database
in which You have Sui Generis Database Rights, then the database in which You have Sui
Generis Database Rights (but not its individual contents) is Adapted Material, including
for purposes of Section 3(b)". `examples.csv` contains substantially the whole of each
imported TLA export, so it *is* Adapted Material for ShareAlike purposes whether or not
any copyright threshold is met. CC's Data FAQ states the same: "The SA licenses require
you to apply the same or a compatible license to any database you share publicly and in
which you include a substantial portion of the licensed database contents. Note that this
does not require you to ShareAlike any copyright or other rights you have in the
individual contents of the database"
(<https://wiki.creativecommons.org/wiki/Data>, "If my use of a database is restricted by
sui generis database rights, how do I comply with the license?"). That last sentence is
also the clean legal basis for the repo's MIT/CC split: ShareAlike reaches the database,
not the code that builds it.

Even on the most generous "it's just a compilation" reading, the result would not change
for this file, because the FAQ's collection table (below, Q4) forbids putting BY-NC-SA
material into a commercially-licensed collection — which is the very reason the NC corpora
are excluded — and BY-SA material may be included in a BY-SA work either way.

---

## 3. Can CC BY 4.0 and CC0 material go into a CC BY-SA 4.0 dataset?

**Yes for both.**

- **Mechanism.** FAQ, "Can I combine material under different Creative Commons licenses
  in my work?": "It depends. The first question to ask is whether doing so constitutes an
  adaptation. If the combination does not create an adaptation, then you may combine any
  CC-licensed content so long as you provide attribution and comply with the
  NonCommercial restriction if it applies." And for the adaptation case, the FAQ's
  **Adapter's licence chart** (<https://creativecommons.org/faq/>, "If I derive or adapt
  material offered under a Creative Commons license, which CC license(s) can I use?"):
  with an original of **BY**, the adapter's licence **BY-SA** is green (permitted); with an
  original in the **public domain (PD)**, every adapter's licence including BY-SA is green.
- **What CC BY 4.0 then requires.** §3(a)(1)(A) — retain, if supplied: creator
  identification, a copyright notice, a notice referring to the licence, a notice
  referring to the disclaimer of warranties, and a URI or hyperlink to the licensed
  material; §3(a)(1)(B) — "indicate if You modified the Licensed Material and retain an
  indication of any previous modifications"; §3(a)(1)(C) — "indicate the Licensed Material
  is licensed under this Public License, and include the text of, or the URI or hyperlink
  to, this Public License". Plus the crucial compatibility clause, CC BY 4.0 §3(a)(1)
  final paragraph: "If You Share Adapted Material You produce, the Adapter's License You
  apply must not prevent recipients of the Adapted Material from complying with this
  Public License" (<https://creativecommons.org/licenses/by/4.0/legalcode.en>). In practice:
  the BY credit and licence link must survive intact inside the BY-SA file, and the BY-SA
  wrapper must not obscure them. Applying BY-SA to the lexicon is therefore permitted, but
  the file must not be presented as if BY-SA were the *only* licence in play.
- **CC0 1.0.** No conditions attach at all: the affirmer "overtly, fully, permanently,
  irrevocably and unconditionally waives, abandons, and surrenders all of Affirmer's
  Copyright and Related Rights … for any purpose whatsoever"
  (<https://creativecommons.org/publicdomain/zero/1.0/legalcode.en>, §2 "Waiver").
  Attribution is good scholarly practice, not a licence condition. (Relevant if the
  project ever imports the TLA "Lemmata in Wikidata" set, which
  <https://aaew.bbaw.de/daten-veroeffentlichungen> lists as CC0.)

---

## 4. Can CC BY-NC-SA 4.0 material be combined into a CC BY-SA 4.0 dataset?

**No.** Three independent official statements close this off.

1. **The SA clause on the NC side.** CC BY-NC-SA 4.0 §3(b)(1): "The Adapter's License You
   apply must be a Creative Commons license with the same License Elements, this version
   or later, or a BY-NC-SA Compatible License"
   (<https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en>). §1 fixes the
   elements: "The License Elements of this Public License are Attribution, NonCommercial,
   and ShareAlike." CC BY-SA 4.0 lacks the NonCommercial element, so it is not a
   permissible adapter's licence for BY-NC-SA material. Symmetrically, CC BY-SA 4.0
   §3(b)(1) requires the same elements as BY-SA — and §3(b)(3) and §2(a)(5)(C) forbid the
   other direction: "You may not offer or impose any additional or different terms or
   conditions on … Adapted Material that restrict exercise of the rights granted under the
   Adapter's License You apply" / "if doing so restricts exercise of the Licensed Rights by
   any recipient of the Licensed Material". Bolting NC onto BY-SA material is precisely
   such an additional restriction.
2. **The compatibility list.**
   <https://creativecommons.org/share-your-work/licensing-considerations/compatible-licenses/>:
   for BY-SA 4.0 the only permitted adapter's licences are BY-SA 4.0 or later, ported
   BY-SA 4.0+, the Free Art License 1.3, and GPLv3; for BY-NC-SA 4.0, "BY-NC-SA 4.0, or a
   later version of the BY-NC-SA license", ported versions, or a designated BY-NC-SA
   Compatible License — and "Currently, no non-CC licenses have been designated as
   compatible with BY-NC-SA 4.0". The two sets do not intersect, so no single licence can
   cover an adaptation of both.
3. **The FAQ charts.** The Adapter's licence chart marks, for an original under **BY-SA**,
   every adapter's licence dark grey (not permitted) except BY-SA; for an original under
   **BY-NC-SA**, every adapter's licence dark grey except BY-NC-SA. And the collection
   table under "If I create a collection that includes a work offered under a CC license…"
   marks BY-NC / BY-NC-ND / BY-NC-SA originals **permitted only in a "NonCommercial
   Collection (BY-NC, BY-NC-SA, BY-NC-ND)" and not in a "Commercial Collection (BY, BY-SA,
   BY-ND)"** — so the NC rows could not even be pooled into a BY-SA-licensed *collection*,
   let alone an adaptation. The FAQ text adds: "if you want to use a remix for commercial
   purposes, you cannot incorporate material released under one of the NonCommercial
   licenses."

The project's stated reason for the private path — "CC BY-SA 4.0 is a share-alike licence
that cannot carry NC-licensed material without becoming NC itself for the whole file" — is
the right conclusion, reached for the right reason.

---

## 5. Does serving NC rows and BY-SA rows in one running app put the licences in conflict?

**Closest to (a): a permitted non-commercial *use*, plus per-source Sharing of each
corpus under its own terms — not a single unlawful adaptation — provided the design keeps
doing what it does now. But the official sources do not settle every step, and the
uncertain step is named below.**

**Step 1 — which licence elements even apply to a use that isn't distribution.** CC's Data
FAQ is explicit and directly on point: "Under version 4.0, if an NC license has been
applied then any use of the licensed database or its contents that is restricted by
copyright law or sui generis database rights requires compliance with the NC term, even if
the database is not publicly shared. The other license elements (BY, ND, and SA, as
applicable) must be complied with only if your use is so restricted and public sharing is
involved" (<https://wiki.creativecommons.org/wiki/Data>, "How do the different CC license
elements operate for a CC-licensed database?"). So: **NC binds always** — including the
purely local build step, and including a private internal deployment — while **ShareAlike
bites only on public sharing**. This is why the in-memory concatenation is not, by itself,
a licence event.

**Step 2 — but the app does "Share".** "Share" is defined broadly in §1 of all three
licences: "to provide material to the public by any means or process that requires
permission under the Licensed Rights … and to make material available to the public
including in ways that members of the public may access the material from a place and at a
time individually chosen by them." A publicly reachable web app that displays corpus
sentences is Sharing the sentences it displays. For the NC corpora this is permitted:
CC BY-NC-SA 4.0 §2(a)(1) grants the right to "reproduce and Share the Licensed Material,
in whole or in part, for NonCommercial purposes only" and to "produce, reproduce, and
Share Adapted Material for NonCommercial purposes only". Because the private rows are
modified on import (convention handling, `grammar_notes`, normalised columns), what the app
shows is Adapted Material of an NC corpus, so §3(b) applies to *those rows*: the adapter's
licence on them must be BY-NC-SA 4.0. The current credit line does state exactly that,
which is the right call — but see Q6 for what the line is still missing.

**Step 3 — the move that would break it.** Sharing the *union* as one work or one database.
Under §4(b) of both licences, a database containing a substantial portion of each source is
Adapted Material of each source; offering that single database publicly would require it
to be simultaneously CC BY-SA 4.0 (for TLA/AES/BBAW) and CC BY-NC-SA 4.0 (for
Ramses/St Andrews), which Q4 shows is impossible. The present design avoids that: the
combined frame exists only in process memory, is never serialised, never reaches the
database (`ensure_corpus_ready` syncs the public CSV *before* the private rows are
appended), never reaches `scripts/export_reviewed.py`, and never reaches
`app/api/main.py`, which reads `examples.csv` directly and has no knowledge of
`PRIVATE_DATA_DIR`. Verified in this audit: the app has exactly one `st.download_button`
(`app/ui/whyptology_app.py:2339`), and its payload is built from database-backed reviewed
annotations, which private rows cannot enter. Also verified: `data/private/` does not exist
in the working tree today, so the live deployment currently serves no NC rows at all.

**The unsettled step, stated plainly.** Neither the legal code nor the FAQ nor the Data FAQ
says whether serving query results computed over an in-memory union counts as "publicly
sharing" the union. The Data FAQ's operative phrase is "any database you share publicly and
in which you include a substantial portion of the licensed database contents"; whether a
search interface over a merged frame "shares" that frame, or only shares the individual
extracts it returns, is not addressed anywhere I could find on creativecommons.org. The
per-row reading (each row is shared under its own source's terms, with its own credit) is
the reasonable one and is the reading the design is built around — but it is an
interpretation, not a quotation.

**What the private path must keep doing to stay on the safe side**

1. **Never redistribute the private files.** `data/private/` stays gitignored; no branch,
   release artefact, Docker image layer, backup or deploy bundle may contain it. (When the
   home-PC/Docker move happens, check the image build context — a `COPY . .` would ship it.)
2. **No egress path may emit private rows.** Keep private rows out of the database, the
   reviewed-annotations export, `app/api/main.py`, benchmark CSVs, and any future download,
   share-link or "export search results" feature. Any new export must filter on `source`,
   and the existing test coverage in `tests/test_private_corpus.py` should be extended
   whenever a new egress point is added.
3. **Keep the licences separable and visible per row.** Never fold NC sources into the
   CC BY-SA credit sentence; keep a per-row source label so a viewer can tell which terms
   apply to the row in front of them. Never describe the app as offering "a CC BY-SA
   corpus" once NC rows are loaded.
4. **Non-commercial hosting only, and note the reach of NC.** Because the NC term applies
   "even if the database is not publicly shared", it constrains internal use too: no ads,
   no paid tier, no sponsored placement, no use "primarily intended for or directed towards
   commercial advantage or monetary compensation" (BY-NC-SA §1, "NonCommercial") — which
   includes a deployment in service of a commercial employer's business. A research/teaching
   deployment at cost is fine.
5. **Keep removability trivial.** The rows must remain droppable by deleting a directory,
   with no derived artefact (model, index, benchmark, cached parquet) that silently retains
   their content after removal.
6. **No effective technological measures.** FAQ, "Can I use effective technological
   measures (such as DRM) when I share CC-licensed material?" — "No." Note the useful
   companion answer, "Can I share CC-licensed material on password-protected sites?" —
   "Yes. This is not considered to be a prohibited measure, so long as the protection is
   merely limiting who may access the content". So gating the app behind a login, or behind
   a Cloudflare Tunnel, is permitted; wrapping the data in DRM is not.
7. **Keep the paper trail.** Nederhof's email is the *only* evidence of the St Andrews
   terms, since his page states none; keep it archived alongside
   `docs/permission-requests.md`.

---

## 6. Attribution checklist, and the gaps

The conditions, from CC BY-SA 4.0 / CC BY 4.0 / CC BY-NC-SA 4.0 §3(a)(1) (identical
wording in all three) and §3(b)(2) (BY-SA and BY-NC-SA only):

| # | Condition (§) | Required | In `corpus_credit_html` / `PRIVATE_CORPUS_CREDITS` | In `DATA-LICENSE.md` |
|---|---|---|---|---|
| i | creator identification, "in any reasonable manner requested by the Licensor" — §3(a)(1)(A)(i) | yes | Yes for all five sources; the Ramses string matches the acknowledgement its README requests verbatim | Yes, in full, incl. the AES contributor list |
| ii | a copyright notice — §3(a)(1)(A)(ii) | only "if it is supplied by the Licensor" | n/a — none of the sources supplies one | n/a; worth saying so |
| iii | a notice referring to the licence — §3(a)(1)(A)(iii) | yes | Yes (BY-SA deed link; per-source labels for NC) | Yes |
| iv | a notice referring to the **disclaimer of warranties** — §3(a)(1)(A)(iv) | yes | **Missing** — no reference anywhere in the credit line, and the credit line is what a viewer sees | Yes (§5 quoted, with a link to the legal code) |
| v | a URI or hyperlink to the **licensed material** — §3(a)(1)(A)(v) | yes, "to the extent reasonably practicable" | **Partly wrong** — TLA links `thesaurus-linguae-aegyptiae.de` (the website, which is *not* the licensed material and is not CC-licensed) instead of the two Hugging Face datasets; AES links `aed-tei` although the import read the `aes` relANNIS export; BBAW, Ramses and St Andrews links are right | Earlier-Egyptian URL right; Late-Egyptian URL is the stale redirecting form and the title is wrong |
| vi | indicate if You modified it, and retain an indication of previous modifications — §3(a)(1)(B) | yes | Yes for the public block ("Adapted: normalised, re-segmented, transliteration conventions unified, and extended with derived fields — see DATA-LICENSE.md"). **Missing for both NC sources** and **missing for the lexicon**, all three of which are modified on import | Yes, at length, per corpus — the strongest part of the current documentation |
| vii | indicate the material is licensed under this licence, and include the licence text or a URI to it — §3(a)(1)(C) | yes | Yes for BY-SA. **For the NC sources the label says "CC BY-NC-SA 4.0" but the hyperlink goes to the DOI / the St Andrews texts page, not to the licence text** — a reader who clicks to check the licence lands on a page that (for St Andrews) states no licence at all. **For the lexicon, "CC BY 4.0" is plain text with no link to <https://creativecommons.org/licenses/by/4.0/>** | Yes for BY-SA and the NC sources; the lexicon section links the DOI and the GitHub repo but not the BY 4.0 deed |
| viii | ShareAlike: state the adapter's licence and include its text or URI — §3(b)(2) | yes | Yes ("Licensed CC BY-SA 4.0", linked) | Yes |

Two further documentation defects, not §3(a) items:

- **Internal contradiction.** The `DATA-LICENSE.md` table says "Corpus data (`data/`, incl.
  `data/processed/examples.csv`) — **CC BY-SA 4.0**", while the lexicon section says
  `data/processed/helsinki_lexicon.csv` is built from **CC BY 4.0** material. Both files
  live under `data/`. Applying BY-SA to the lexicon is permitted (Q3), but the table as
  written erases the BY-4.0 upstream that must stay visible under CC BY 4.0 §3(a)(1)(C).
- **The "every copy of the data" table omits `data/processed/helsinki_lexicon.csv`,** which
  is committed and is the one file with a different upstream licence.

---

## 7. Everything else on the official pages that touches this project

- **TLA's own citation requirement is separate from the dataset citations.** The licences
  page prescribes a Full citation ("Daniel A. Werning, Peter Dils, in: *Thesaurus Linguae
  Aegyptiae*, Corpus edition 20, Web app version 2.5.2, 20 Aug 2026, ed. by Tonio Sebastian
  Richter & Daniel A. Werning on behalf of the Berlin-Brandenburgische Akademie der
  Wissenschaften and Hans-Werner Fischer-Elfert & Peter Dils on behalf of the Sächsische
  Akademie der Wissenschaften zu Leipzig (accessed: xx.xx.20xx)") and a Short citation
  ("in: *Thesaurus Linguae Aegyptiae* (accessed: xx.xx.20xx)"). These apply to material
  taken from the *web app*. The project took its rows from the raw-data publications, so
  the dataset citations it already uses are the correct ones — but if any TLA web-app page
  is ever quoted (e.g. while checking a reading), that citation form applies, with an
  access date.
- **The website restriction is a live constraint on future work.** "You can copy and quote
  individual data sets of this website for academic research purposes, but not entire
  sub-corpora or larger sets (> 10 website pages)." Scraping the TLA web app — for
  Camilla's Urk. IV text, for instance — would breach this even though the raw-data
  publications are CC BY-SA. The correct route stays the one already chosen: use the
  published datasets, or email Werning ("For individual inquiries regarding the raw data,
  please contact Daniel Werning").
- **"No additional restrictions."** §2(a)(5)(C): "You may not offer or impose any additional
  or different terms or conditions on, or apply any Effective Technological Measures to,
  the Licensed Material if doing so restricts exercise of the Licensed Rights by any
  recipient"; §3(b)(3) repeats it for Adapted Material. Practical consequence: any future
  terms-of-use page for the app must not purport to forbid re-use of the corpus rows, and
  no click-through may condition access to them on extra terms.
- **Effective technological measures / access control.** As in Q5 item 6: DRM is
  prohibited, mere access control is not, and "merely converting material into a different
  format that is difficult to access … does not violate the restriction".
- **Sui generis database rights matter here specifically because the project is hosted in
  the EU.** §1 defines them by reference to "Directive 96/9/EC of the European Parliament
  and of the Council of 11 March 1996 on the legal protection of databases", so they are
  live in Germany. Three consequences: (a) §4(a) affirmatively grants the right "to extract,
  reuse, reproduce, and Share all or a substantial portion of the contents of the database"
  — the bulk import is expressly permitted; (b) §4(b) makes the project's own database
  Adapted Material, which is the strongest basis for the BY-SA claim (Q2); (c) §4(c)
  requires §3(a) compliance whenever a substantial portion is shared — which the committed
  CSV is. In the NC licence, §4(a) is narrowed to "for NonCommercial purposes only", so even
  the local extraction of Ramses/St Andrews into `data/private/` is NC-bound. And per the
  Data FAQ, ShareAlike over a database "does not require you to ShareAlike any copyright or
  other rights you have in the individual contents" — the cleanest statement of why the
  MIT code and the BY-SA data can coexist.
- **The 30-day cure period.** §6(b)(1): rights terminate automatically on breach but
  reinstate "automatically as of the date the violation is cured, provided it is cured
  within 30 days of Your discovery of the violation". Fixing the attribution gaps in Q6
  promptly is therefore fully curative. (The FAQ notes one may still be liable for damages
  for the non-compliant period.)
- **Irrevocability.** FAQ, "What happens if the author decides to revoke the CC license to
  material I am using?" — "The CC licenses are irrevocable." Copies already received stay
  licensed even if a source later changes terms. This cuts both ways and is worth knowing
  for the Helsinki/Ramses question: it does not help if the upstream relicensing was invalid
  in the first place, because a licensor cannot grant more than it holds.
- **No endorsement.** §2(b)(1)/§2(a)(6): nothing may imply that the project is "connected
  with, or sponsored, endorsed, or granted official status by" TLA/BBAW/SAW. The current
  neutral "Corpus data: …" phrasing is fine; keep it that way in any future marketing copy,
  and avoid presenting expert correspondence as institutional endorsement.
- **An editorial caveat from the TLA dataset card, not a licence term, worth repeating in
  the app:** the Earlier Egyptian card states the dataset "is not suitable for
  reconstructing entire ancient source texts" and contains only "fully intact,
  unambiguously readable sentences". That is exactly the kind of limitation the app's
  framing (top-3 reading suggestion from attested spellings, not OCR, not an edition)
  already respects.

---

## Proposed changes (proposals only — not applied)

### `DATA-LICENSE.md`

- Replace "The corpus is derived from the Thesaurus Linguae Aegyptiae (TLA), released under
  CC BY-SA 4.0" with a statement that names the *publications* that carry the licence — the
  Hugging Face raw-data datasets, listed at <https://aaew.bbaw.de/daten-veroeffentlichungen>
  — and add one sentence noting that the TLA **website** is *not* CC BY-SA and permits only
  copying "individual data sets … for academic research purposes, but not entire
  sub-corpora or larger sets (> 10 website pages)", citing
  <https://thesaurus-linguae-aegyptiae.de/info/licenses>.
- Correct the Late Egyptian citation to the official form: title "Late Egyptian sentences,
  corpus v19, premium", add "v1.0, 1/19/2025", and use the canonical URL
  `https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium`
  (the current URL only survives via a 307 redirect).
- Fix the internal contradiction: qualify the licence table so it does not put
  `data/processed/helsinki_lexicon.csv` under CC BY-SA 4.0 without saying that its upstream
  is CC BY 4.0 and that the BY attribution and licence link travel with it; add that file to
  the "Every copy of the data in this repository" table with its own licence column.
- Rewrite the Ramses licence paragraph to present both official statements side by side —
  Zenodo metadata `cc-by-4.0` vs the in-deposit README's CC BY-NC-SA 4.0 — and mark the
  choice of the README as *this project's* conservative reading rather than an established
  fact. Add the Zenodo record's actual title and version ("Ramses automated translitteration
  software", version 2021-06-15) so a reader who opens the DOI is not confused by finding a
  different title from the one cited.
- Record, for St Andrews, that the public page carries **no** licence statement, so the
  CC BY-NC-SA 4.0 designation rests solely on Nederhof's email of 2026-09-02, and point to
  where that email is archived.
- Escalate the Helsinki/Ramses paragraph from a footnote to a clearly marked open licence
  question, with the two facts that make it one (Helsinki states CC BY 4.0 and does not
  mention the NC upstream; CC BY-NC-SA 4.0 §3(b)(1) plus the compatibility page allow only
  BY-NC-SA for adaptations), the row counts at stake (50,647 Ramses-only + 4,402
  AES+Ramses of 97,340), and the two mitigations available (email Jauhiainen/Rosmorduc;
  re-run the import AES-only).
- Add a short "what the licence does *not* cover" note: no copyright notices are supplied
  by any upstream source, so condition §3(a)(1)(A)(ii) is inapplicable — stating this
  prevents the gap being read as an omission.
- Add a §4 (sui generis database rights) paragraph: the project is hosted in the EU, the
  built corpus is Adapted Material under §4(b) regardless of copyright, and per CC's Data
  FAQ ShareAlike reaches the database and not the individual contents — the explicit basis
  for the MIT/CC BY-SA split the file already asserts.
- Add the §6(b) 30-day cure note and a line stating that CC licences are irrevocable, so
  the record shows the project understands both directions.

### In-app credit text (`corpus_credit_html`, `CORPUS_CREDITS`, `PRIVATE_CORPUS_CREDITS`, `LEXICON_CREDIT`)

- Point the TLA hyperlink at the licensed datasets rather than the homepage — e.g. link the
  two Hugging Face dataset pages (or one link to `DATA-LICENSE.md#required-attribution`
  that carries both), since §3(a)(1)(A)(v) asks for a URI to the licensed material.
- Point the AES hyperlink at `https://github.com/simondschweitzer/aes` (what was imported),
  keeping `aed-tei` as the stated derivation.
- Add a warranty-disclaimer reference to the credit line — a clause such as "Provided
  as-is, without warranties (CC BY-SA 4.0 §5)" linked to the legal code — so §3(a)(1)(A)(iv)
  is satisfied where the viewer actually reads it, not only in a repo file.
- Give `PRIVATE_CORPUS_CREDITS` a real licence link: label CC BY-NC-SA 4.0 hyperlinked to
  <https://creativecommons.org/licenses/by-nc-sa/4.0/>, and keep the DOI / texts page as a
  separate "source" link. Today the licence label links to the source, and for St Andrews
  that page states no licence at all.
- Add an indication-of-changes clause to each private credit line (conventions preserved as
  written, provenance recorded in `grammar_notes`, normalised columns added), since
  §3(a)(1)(B) applies to the NC rows too and they are modified on import.
- Adjust the private lines' wording: "not redistributed with this app" is true of the files
  but the app does display the rows publicly, which is "Share" under §1. Something like
  "displayed here under its own licence for non-commercial use; the underlying files are
  not redistributed" is both accurate and still reassuring.
- Hyperlink "CC BY 4.0" in `LEXICON_CREDIT` to <https://creativecommons.org/licenses/by/4.0/>,
  and add a brief indication of changes (Gardiner codes converted to Unicode,
  transliterations converted to this corpus's convention, counts summed across the two
  files).
- Consider naming the Ramses upstream of the lexicon in the lexicon credit itself, since
  those rows are the ones with the unresolved licence question; a reader should be able to
  see the chain without opening `DATA-LICENSE.md`.
- Keep the structural choices exactly as they are: public sources folded into one BY-SA
  sentence, each private source in its own sentence with its own licence, and the footer
  repeated on every page. That design is what makes the Q5 argument available.

### `README.md`

- Mirror the two substantive corrections: that CC BY-SA attaches to the TLA raw-data
  publications rather than to the website, and that `data/` is not uniformly CC BY-SA
  because `helsinki_lexicon.csv` carries a CC BY 4.0 upstream.

---

## Sources fetched successfully on 2026-09-04

- <https://thesaurus-linguae-aegyptiae.de/info/licenses>
- <https://aaew.bbaw.de/daten-veroeffentlichungen>
- <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium>
- <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium>
- <https://huggingface.co/datasets/phiwi/bbaw_egyptian>
- <https://edoc.bbaw.de/frontdoor/index/index/docId/2919>
- <https://github.com/simondschweitzer/aes>
- <https://github.com/simondschweitzer/aed-tei>
- <https://github.com/MaReTEgyptologists/TranslitModels>
- <https://zenodo.org/records/7991241> and its `Readme.txt`
- <https://zenodo.org/records/4954597>, <https://zenodo.org/api/records/4954597>, and
  `ramses-trl/README.md` extracted from `ramses-trl_2021_05_29.zip` in that deposit
- <https://creativecommons.org/licenses/by-sa/4.0/legalcode.en>
- <https://creativecommons.org/licenses/by/4.0/legalcode.en>
- <https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en>
- <https://creativecommons.org/publicdomain/zero/1.0/legalcode.en>
- <https://creativecommons.org/share-your-work/licensing-considerations/compatible-licenses/>
- <https://creativecommons.org/faq/> (including the Adapter's licence chart and the
  collection table, read from the page's HTML because the charts are colour-coded cells
  with no text labels)
- <https://wiki.creativecommons.org/wiki/Data>
- <https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/>

## Pages I could not reach

- <https://nbn-resolving.org/urn:nbn:de:kobv:b4-opus4-29190> — the URN resolver for the
  BBAW January 2018 snapshot returns an Anubis anti-bot challenge page, not the record. I
  reached what is evidently the same publication directly at
  <https://edoc.bbaw.de/frontdoor/index/index/docId/2919> (title, authors and year match
  exactly) and read the licence there, but **I could not verify that this docId is the
  object behind that URN**; treat the identification as strong inference, not proof.
- Nothing else failed. Two dead ends worth noting for the record: the St Andrews texts page
  loaded fine but simply contains no licence statement, and
  `https://thesaurus-linguae-aegyptiae.de/info/licence` (singular) is a 404 — the correct
  path is `/info/licenses`.
