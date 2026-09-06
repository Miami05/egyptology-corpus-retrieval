# Corpus data licence and attribution

**The code in this repository and the corpus data under `data/` are under different
licences. Read this before publishing, redistributing or deploying publicly.**

| What | Licence |
|---|---|
| Source code (`app/`, `scripts/`, `tests/`) | MIT — see `LICENSE` |
| Corpus data (`data/`, incl. `data/processed/examples.csv`) | **CC BY-SA 4.0** — see below.[^lexicon] [^signfunctions] |
| `app/ui/static/GentiumPlus-Translit.woff2` | SIL Open Font License 1.1 — see `app/ui/static/GentiumPlus-OFL.txt` |

[^lexicon]: **Exception:** `data/processed/helsinki_lexicon.csv` is built from CC BY
4.0 material (part of it, in turn, from the Ramses corpus — see "Sign-reading lexicon"
below) and is wrapped in CC BY-SA 4.0 here, which CC BY 4.0 §3(a)(1) permits, but the
upstream CC BY 4.0 attribution and licence link must travel with it and are not
superseded by this table. See "Every copy of the data in this repository" below for
its own row. The Ramses-derived half of the lexicon is covered by the same CC BY-SA
4.0 grant described under "Fifth corpus: Ramses" below, so the lexicon file stays
public without qualification on that count.

[^signfunctions]: **Second exception:** `data/processed/sign_functions.csv` is
**CC BY 4.0, credited to Mark-Jan Nederhof**, and is *not* wrapped in CC BY-SA here.
He granted the underlying XML under "whatever license you prefer" on 2026-09-04 and we
chose the more permissive of the two so the table can be reused freely; CC BY 4.0 is
one-way compatible with the CC BY-SA corpus it sits beside. See "Sign functions of the
Unicode 5.2 hieroglyphs" below.

## Why the data is not MIT

The corpus is derived from raw-data publications of the Thesaurus Linguae Aegyptiae
(TLA) project, each released under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) and listed at
<https://aaew.bbaw.de/daten-veroeffentlichungen> — the two actually imported are cited
below. **The TLA *website*, `thesaurus-linguae-aegyptiae.de`, is not itself under a CC
licence.** Its licences page states: "You can copy and quote individual data sets of
this website for academic research purposes, but not entire sub-corpora or larger sets
(> 10 website pages)"
(<https://thesaurus-linguae-aegyptiae.de/info/licenses>). CC BY-SA 4.0 attaches to the
raw-data publications this project actually used, not to the web app.

CC BY-SA is a *share-alike* licence: an adapted version of the data must be released
under the same licence. `data/processed/examples.csv` is an adaptation of TLA data, so
it is CC BY-SA 4.0 and **cannot** be relicensed as MIT. Applying MIT to the whole
repository would misstate the terms of someone else's work.

The share-alike obligation attaches to the *data*, not to the code that processes it.
The code stays MIT.

No upstream source in this file supplies a copyright notice, so condition
§3(a)(1)(A)(ii) ("a copyright notice, if it is supplied by the Licensor") is
inapplicable throughout — that is a statement of fact about the sources, not an
omission on this project's part.

## Required attribution

CC BY-SA 4.0 requires attribution, a licence notice, and an indication of changes.
The dataset's own citation recommendation is:

> Thesaurus Linguae Aegyptiae, Original Earlier Egyptian sentences, corpus v18,
> premium,
> <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium>,
> v1.1, 2/16/2024, ed. by Tonio Sebastian Richter & Daniel A. Werning on behalf of the
> Berlin-Brandenburgische Akademie der Wissenschaften and Hans-Werner Fischer-Elfert &
> Peter Dils on behalf of the Sächsische Akademie der Wissenschaften zu Leipzig.

Licensed under CC BY-SA 4.0. This is the licensed *publication*; see above for why the
TLA website itself is not.

The corpus also contains the **Late Egyptian** TLA corpus, whose official citation is:

> Thesaurus Linguae Aegyptiae, Late Egyptian sentences, corpus v19, premium,
> <https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-late_egyptian-v19-premium>,
> v1.0, 1/19/2025, ed. by Tonio Sebastian Richter & Daniel A. Werning on behalf of the
> Berlin-Brandenburgische Akademie der Wissenschaften and Hans-Werner Fischer-Elfert &
> Peter Dils on behalf of the Sächsische Akademie der Wissenschaften zu Leipzig.

Licensed under CC BY-SA 4.0. (The dataset card's title omits "Original" and its URL is
lower-case `tla-late_egyptian-v19-premium`; the mixed-case form used before 2026-09-04
only worked via a 307 redirect.)

```bibtex
@misc{tlaEarlierEgyptianOriginalV18premium,
 editor = {{Berlin-Brandenburgische Akademie der Wissenschaften} and {Sächsische Akademie der Wissenschaften zu Leipzig} and Richter, Tonio Sebastian and Werning, Daniel A. and Hans-Werner Fischer-Elfert and Peter Dils},
 year = {2024},
 title = {Thesaurus Linguae Aegyptiae, Original Earlier Egyptian sentences, corpus v18, premium},
 url = {https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium},
 location = {Berlin},
 organization = {{Berlin-Brandenburgische Akademie der Wissenschaften} and {Sächsische Akademie der Wissenschaften zu Leipzig}},
}
```

## Indication of changes (required by CC BY-SA 4.0 §3(a)(1)(B))

`data/processed/examples.csv` is **not** verbatim TLA data. The TLA sentences were
transformed by `scripts/import_tla_dataset.py` and `scripts/build_examples_from_real.py`
as follows:

- Selected a subset of sentences and reshaped them into one row per sentence with the
  column schema in `app/data/schema.py`.
- Added normalised columns (`*_norm`) produced by `app/data/normalizer.py`: case
  folding, whitespace collapsing, and stripping of editorial markup, used for matching.
- Derived additional fields not present in the source, including `sign_sequence`,
  `formula_type`, `deity`, `recipient`, `offering_items`, `formula_slot` and
  `aesthetic_arrangement_flag`.
- Added project-local identifiers (`source_text_id`, `source_sentence_id`) and a
  `source_ref` pointing back to the originating row in the downloaded parquet.
- `review_status` and any annotations recorded through the app are this project's own
  editorial additions and are not part of the TLA data.

- **Merged two TLA corpora** (2026-08-30): the Earlier Egyptian corpus (12,772 rows)
  and the Late Egyptian corpus (3,601 rows, after dropping 5 sentences already
  present verbatim), giving 16,373 rows. Rows carry their originating corpus in
  `language_stage` and an id prefix (`TLA_EARLIER_*` / `TLA_LATE_*`).
- **Unified the suffix-pronoun marker.** The Earlier corpus writes it `=` (11,671
  occurrences), the Late corpus `⸗` (4,390). They denote the same morpheme. All
  imported rows now use `=`. Without this the same sentence read `n =tn` or `n ⸗tn`
  depending only on which corpus attested that spelling more often — an artefact of
  merging, not of the language.

Translations in the corpus are the German translations from TLA.

## Third corpus: AES (Ancient Egyptian Sentences)

`data/processed/examples.csv` also contains sentences from the **AES corpus**, imported
from its relANNIS export by `scripts/import_aes_relannis.py`:

> AES — Ancient Egyptian Sentences. Derived from
> [AED-TEI](https://github.com/simondschweitzer/aed-tei), based on the *Teilauszug der
> Datenbank des Vorhabens "Strukturen und Transformationen des Wortschatzes der
> ägyptischen Sprache"* (Jan. 2018), with contributions by Burkhard Backes, Susanne
> Beck, Anke Blöbaum, Angela Böhme, Marc Brose, Adelheid Burkhardt, Roberto A. Díaz
> Hernández, Peter Dils, Roland Enmarch, Frank Feder, Heinz Felber, Silke Grallert,
> Stefan Grunert, Ingelore Hafemann, Anne Herzberg, John M. Iskander, Ines Köhler,
> Maxim Kupreyev, Renata Landgrafova, Verena Lepper, Lutz Popko, Alexander Schütze,
> Simon Schweitzer, Stephan Seidlmayer, Gunnar Sperveslage, Susanne Töpfer, Doris
> Topmann and Anja Weber.

Licensed CC BY-SA 4.0. Each imported row records its originating subcorpus, editor and
findspot in `grammar_notes`, and its AES text and sentence identifiers in `source_ref`.

### Changes made to the AES data

- **Only fully aligned sentences were taken.** A sentence is imported only when every
  word carries both a transliteration and a Unicode hieroglyphic writing; sentences
  with partial coverage are discarded, not patched. 14,824 of 101,796 qualify.
- **Transliteration rewritten into the convention already used by this corpus.** AES
  writes the yod as `j`, the morpheme separator as a comma, the suffix marker as `≡`,
  plural and dual as `,pl` / `,du`, and capitalises proper nouns; the TLA rows use
  `ꞽ`, `.`, `=`, `.PL` / `.DU` and lower case. Validated against the 1,342 sentences
  present in both corpora: the conversion reproduces the TLA form exactly for 85% and
  **disagrees on a letter in none**. The remaining 15% differ only in editorial
  judgement between the two editions and were left as AES has them.
- **Periods kept coarse.** AES dates documents as "OK & FIP", "MK & SIP", "NK",
  "TIP - Roman times"; these are expanded to readable labels but not narrowed to a
  single period, because the source does not claim one.
- **Language stage left unclaimed** (`Unspecified (AES)`): AES does not state one per
  sentence and deriving it from a coarse era label would be a guess.
- Sentences already present from a TLA corpus were dropped (5,001 of them).

## Fourth corpus: the BBAW 2018 snapshot (`phiwi/bbaw_egyptian`)

`data/processed/examples.csv` also contains 5,369 sentences imported by
`scripts/import_bbaw_egyptian.py` from the Hugging Face dataset `phiwi/bbaw_egyptian`
(<https://huggingface.co/datasets/phiwi/bbaw_egyptian>), licensed CC BY-SA 4.0:
> Teilauszug der Datenbank des Vorhabens *"Strukturen und Transformationen des
> Wortschatzes der ägyptischen Sprache"*, Berlin-Brandenburgische Akademie der
> Wissenschaften, January 2018, as published in AED-TEI
> (<https://github.com/simondschweitzer/aed-tei>, Simon Schweitzer et al.) and
> redistributed as `phiwi/bbaw_egyptian`. Same contributors as the AES corpus above.

Each imported row records `source = BBAW`, `source_text_id = bbaw_egyptian_2018` and
the dataset's row index as `source_sentence_id` (`B004065`), because the export carries
no identifiers of its own; `source_ref` names the dataset. Licensed CC BY-SA 4.0.

### Changes made to the BBAW data

- **Hieroglyphs converted from Manuel de Codage sign codes to Unicode.** The export
  writes Gardiner codes with layout operators (`D54 *Z7 -M17 *N35`); each code is
  mapped to its Unicode Egyptian Hieroglyph by name, layout operators and editorial
  brackets are dropped, and the words are regrouped so one space-separated group
  corresponds to one transliteration token. Codes with no Unicode codepoint (`Ff1`,
  `Ff100`, `R8A`, numerals) are kept as `<g>CODE</g>` placeholder markup.
- **Transliteration conventions aligned with the rest of the corpus:** the yod `j`
  becomes `ꞽ` (`J` → `Ꞽ` in capitalised names), as for AES, so that a word reads the
  same whichever corpus it came from; the comma morpheme separator becomes a dot
  (`sḫ,tj` → `sḫ.tꞽ`), `{,pl}` / `{,du}` become `.pl` / `.du`, and `≡` becomes `=`.
  Only the letter `j` is touched — `i̯` and `y` are other letters and stay. Everything
  else — brackets, restorations, capitalisation — is verbatim.
- **Only fully aligned sentences were kept.** Of 35,503 rows with hieroglyphs, 22,927
  yield exactly one sign group per transliteration token. Dropped, not patched: 9,121
  with a lacuna (`//`), 612 with an unreadable sign (`"?"`, `"⸮"`), 2,842 whose group
  and token counts differ, 1 with an empty group. A further 3,911 duplicated another
  row of the export and 13,646 were already present in this corpus (matched on a
  yod- and case-insensitive reading, or on identical signs), and one sentence whose
  whole reading is the interjection `ꞽ` was dropped because no transliteration query
  can reach it. The 65,226 rows without hieroglyphs
  are not imported by default (`--include-text-only` exists for them).
- **Metadata not claimed.** The export states no period, genre or language stage per
  sentence, so those columns read `unknown` / `Unspecified (BBAW)` rather than a guess.

## Fifth corpus: the Ramses Transliteration Corpus (`source = Ramses`)

`data/processed/examples.csv` does not yet contain Ramses rows — they are withheld for
a modelling reason unrelated to licensing (see the roadmap notes) — but the licence
position for them is settled and recorded here so the import can proceed without a
further licence review.

> the Ramses transliteration corpus V. 2019-09-01, University of Liège/Projet Ramses

Rosmorduc, S. / Université de Liège, Projet Ramsès.
<https://doi.org/10.5281/zenodo.4954597>.

**Two official statements disagree about the licence, and neither is this project's
own reading of the situation — they are simply what the two official pages say:**

- The Zenodo record's own metadata field states `license: {"id": "cc-by-4.0"}`
  (<https://zenodo.org/api/records/4954597>). The deposit itself is titled "Ramses
  automated translitteration software", version 2021-06-15.
- The README inside the deposited zip (`ramses-trl_2021_05_29.zip`) states: "The
  corpus is released using the CC-BY-NC-SA Creative Common License … Please
  acknowledge its use as 'the Ramses transliteration corpus V. 2019-09-01, University
  of Liège/Projet Ramses'" (the deposit also ships `cc-by-nc-sa.png`).

**For this project, that disagreement is now settled directly rather than by picking
between the two statements.** The rights holders (Projet Ramses / Université de
Liège) replied by email on 2026-09-04 — archived in `docs/permission-requests.md` as
"Reply from Projet Ramses, 2026-09-04". Asked whether they would grant the corpus
under CC BY-SA 4.0 for this project's use, they answered: **"Yes, no problem for
us!"** They separately confirmed the pre-existing private, non-commercial arrangement
with: "Perfect. Green light from our side."

**Ramses rows may therefore enter `data/processed/examples.csv` under CC BY-SA 4.0,
with the attribution above.** The non-commercial handling described under
"Non-commercial corpora kept out of this repository" below no longer applies to
Ramses — it now applies only to St Andrews.

**Convention caveat:** the Ramses transliteration is *normalised to the expected
grammatical form*, not the attested spelling on the object — record that on import in
`grammar_notes` and do not treat it as a diplomatic transcription.

## Sign-reading lexicon: the Helsinki "Transliteration Model" word lists (CC BY 4.0)

`data/processed/helsinki_lexicon.csv` is built by `scripts/import_helsinki_lexicon.py`
from two files published by the University of Helsinki:

> Jauhiainen, Heidi & Jauhiainen, Tommi (2023). *Transliteration Model for Egyptian
> Words.* University of Helsinki, Department of Digital Humanities (funded by the Kone
> Foundation). Zenodo, <https://doi.org/10.5281/zenodo.7991241>;
> <https://github.com/MaReTEgyptologists/TranslitModels> (`AESModel.json`,
> `RamsesTrainingSetModel.json`). Licensed **CC BY 4.0**.

They tabulate, for every hieroglyphic word in two corpora, the transliterations it
carries and how often. The underlying corpora, which must be credited with them:

- **AES** — Schweitzer, S., *Ancient Egyptian Sentences*, <https://github.com/simondschweitzer/aes>
  (BBAW, CC BY-SA 4.0).
- **Ramses Transliteration Corpus v. 2019-09-01** — Rosmorduc, S. / Université de Liège,
  Projet Ramsès, <https://doi.org/10.5281/zenodo.4954597>. Its own README licenses the
  corpus CC BY-NC-SA 4.0 and the University of Helsinki released these derived word
  statistics as CC BY 4.0; on 2026-09-04 Projet Ramses granted this project the corpus
  under **CC BY-SA 4.0** by email ("Yes, no problem for us!", archived in
  `docs/permission-requests.md`), which covers the Ramses-derived rows here
  (`source` = `Ramses`, 50,647 rows, plus 4,402 `AES+Ramses`). The lexicon file therefore
  stays public in full.

The app uses the lexicon only for sign groups this corpus does not attest, labels every
such reading as "lexicon N× — no sentence in this corpus", and never counts it as an
attestation of this corpus.

### Changes made to the lexicon data

- Gardiner codes converted to Unicode signs (codes without a codepoint kept as
  `<g>CODE</g>` placeholders), then normalised like the corpus.
- Transliterations converted from Manuel de Codage ASCII to the corpus's Unicode
  convention. The two files write the yod differently and were converted with their
  own rules: AES `y` → ꞽ (its `i` is the weak radical), Ramses `i`/`j` → ꞽ (its `y` is
  the double reed). Capitalised proper names lower-cased after conversion.
- Counts for the same (group, reading) summed across the two files, with the
  contributing source(s) recorded per row.

## Non-commercial corpora kept out of this repository

One further corpus is in use but is **never** part of `data/processed/examples.csv`
and is **never committed**: it is permitted for non-commercial use only, and CC BY-SA
4.0 is a share-alike licence that cannot carry NC-licensed material without becoming
NC itself for the whole file. Keeping it in the public, CC BY-SA corpus would misstate
its licence. Instead it is read at runtime from a private, gitignored directory
(`PRIVATE_DATA_DIR`, default `data/private/` — see
`app/data/loader.py:load_private_examples` and `app/ui/whyptology_app.py`) and is
concatenated onto the public corpus only *after* it has been synced to the database, so
it is never inserted into the database, never appears in `scripts/export_reviewed.py`
or the reviewed-annotations export, and is never served by `app/api/main.py` (which
loads `examples.csv` directly and has no knowledge of this directory). The app credits
it with its own licence line in `corpus_credit_html` — never folded into the CC BY-SA
sentence above — so a viewer never mistakes an NC row for share-alike data.

Since 2026-09-05 these rows are additionally **served only to sessions that have
presented the reviewer key** (`REVIEWER_KEY`): the app boots on the public frame, and a
session gets public + private only after unlocking, with its own indexes built from it
(see `private_rows_unlocked` / `session_corpus` in `app/ui/whyptology_app.py` and the
"reviewer-key gate" section of `DEPLOYMENT.md`). An ordinary visitor to the public URL
never receives a private row, whatever is in the directory.

(The Ramses Transliteration Corpus used to be documented here too. It moved to "Fifth
corpus: the Ramses Transliteration Corpus" above on 2026-09-04, once its rights
holders granted CC BY-SA 4.0 directly for this project's use.)

### St Andrews Corpus of Ancient Egyptian texts (`source = StAndrews`)

> St Andrews Corpus of Ancient Egyptian texts, Mark-Jan Nederhof

<https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/> (the citation URL he asked for).
**The public page itself carries no licence, copyright or terms-of-use statement at
all** — it offers a Java applet, a download package and PDFs, and notes the site is
under construction. The **CC BY-NC-SA 4.0** designation used here rests entirely on
Mark-Jan Nederhof's email of 2026-09-02, in which he confirmed those terms after first
giving informal permission "to use the St Andrews corpus for non-commercial purposes"
(archived in `docs/permission-requests.md`, Email 3) — there is no public statement to
point to instead. Used with his permission for non-commercial purposes and not
redistributed with this app.

**Convention caveat:** the St Andrews corpus follows **Hannig's transliteration
conventions**: no `z`/`s` distinction and no dot before the feminine `.t`. These are
left exactly as written on import rather than guessed at — a wrong dot or a silently
merged `z`/`s` in a gold column would be worse than a known absence (see the plan notes
on the `z`→`s` fold, which stays a `search_fold`-only measure and never touches the
strict reading key). Measured on import: one `z` in the whole archive, and the yod is
written `j` (9,432 occurrences against 7 bare `i`) — the opposite of the Ramses
corpus, which writes it `i`.

**Imported by `scripts/import_standrews.py`, 2026-09-05**, from the archive under
`data/raw/standrews/corpus/` (gitignored) to `data/private/standrews.csv`
(gitignored). **7,659 rows** — one per body block of his "lite" transliteration files,
his own sentence division — drawn from 94 texts and 102 transliteration witnesses,
55 of which have a hieroglyphic tier. 531 blocks with no reading (translation-only
headings) and 13 with no searchable reading are dropped.

Changes made to his data, all of them recorded here because CC BY-NC-SA 4.0 §3(a)(1)(B)
requires it:

- His Manuel de Codage-style ASCII is converted to the corpus's TLA convention
  (`A a j i H x X S T D` → `ꜣ ꜥ ꞽ ꞽ ḥ ḫ ẖ š ṯ ḏ`). Nothing else is folded: `y`, `z`,
  and the editorial apparatus `{}` `[]` `()` are kept exactly as he wrote them.
- Suffix pronouns are tokenised on his own `=` (`Dd=f` → `ḏd =f`), because the corpus
  writes the suffix pronoun as a token of its own and `search_fold` splits on `=` for
  that reason. No character is added, removed or altered — only whitespace at a
  boundary he already marks.
- The `^` proper-name marker and the `<no>…</no>` ditto marks are markup, not
  readings, and are dropped; `<note>…</note>` footnotes are moved to
  `variant_writing_note`; his coordinate labels are recorded in `source_ref`.
- `language_stage`, `genre` and `period` are **empty**: nothing in the archive
  declares them, and a guess in one of those columns would be read as his.

**No sign-to-reading alignment is taken from this corpus.** The `hieroglyphs` column
is empty on every one of the 7,659 rows. The two tiers share only a line anchor, and
inside a line his RES hieroglyphic encoding is grouped by *quadrat*, not by word, so
no token-for-token pairing is derivable; on the 1,710 lines that have both tiers the
group and reading counts agree 50 times, and hand-checking showed the agreement to be
a coincidence that pairs the wrong signs with the wrong readings. Rows are therefore
transliteration-only, exactly like the BBAW and Ramses text-only rows. 135 rows whose
sentence *is* a whole printed line carry that line's Unicode glyphs in the display-only
`display_sequence` column, and the per-line rendering (via `hieropy` 0.1.9, Nederhof's
own GPL package) is kept beside the raw archive in
`data/raw/standrews/standrews_lines.csv`, also gitignored.

## Sign functions of the Unicode 5.2 hieroglyphs (CC BY 4.0)

`data/processed/sign_functions.csv` is built by `scripts/import_sign_functions.py`
from two XML files published by Mark-Jan Nederhof at
<https://mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/> (`signuse.xml`, the sign
functions behind Nederhof & Rahman 2015; `signunicode.xml`, the codepoints). It holds
**1,444 function entries covering 780 of the 1,071 signs in his Unicode 5.2 list** (the
other 291 signs carry no function element): logogram, determinative, logogram-or-
determinative, phonogram, phonetic determinative, phonogram-or-phonetic-determinative
and typographic, with the transliteration and gloss where the class carries one.

> Sign functions: Mark-Jan Nederhof, sign-function list for the Unicode 5.2
> hieroglyphs, <https://mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/>. Used with
> permission; published here under **CC BY 4.0**.

**This is a separate grant from the text corpus above, and a much wider one.** On
**2026-09-04** Nederhof wrote, of this file: *"You can use the XML file with functions
under whatever license you prefer. I would be glad if they can be of help."* (archived
verbatim in `docs/permission-requests.md`). We chose **CC BY 4.0**, which is compatible
with the CC BY-SA corpus beside it, and told him so in Email 6, offering to change it on
one line from him. Unlike the text corpus, this table **is** redistributed with the
repository; the original XML is not (`data/raw/standrews/unicode/` is gitignored).

Changes made to the data: Gardiner sign ids joined to their Unicode codepoint and
character; the function element name mapped to his own class names from the prose at
the head of `signuse.xml`; transliterations converted from his ASCII to the corpus
convention with the same table `import_standrews.py` uses; `period`, `texttype`,
`plural`, `dual`, `numeral`, `certain` and the consonantal `root` folded into one
`qualifier` column; his `<example>` attestations (RES quadrats, not functions) not
carried. Every row repeats the attribution in a `source_note` column.

Scope caveat, summarising his mail: the file covers **Unicode 5.2 only**. He notes that
UniKemet also lists functions, with newer terminology ("classifiers" for
determinatives), but that its functions often come from the single token used to
confirm a sign's existence and so are incomplete; he suggests the Thot Sign List
(<https://thotsignlist.org/>) for comparison. Both are cross-checks here, never
sources of truth.

### This project's supplement to it (`sign_functions_supplement.csv`, CC BY-SA 4.0)

`data/processed/sign_functions_supplement.csv` holds **thirteen rows covering eleven
signs**, written by this project on **2026-09-06** for item C. They are not Nederhof's
and are not covered by his grant: his list is Unicode 5.2 only, and the signs most
frequent in *this* corpus that it does not reach are exactly the ones a sign-function
model most needs — Z7 𓏲 alone is 36k corpus tokens, Z2 𓏥 32k. The rows are Z7 𓏲
phonogram *w*; Z2 𓏥, Z3 𓏪, Z3A 𓏫 typographic (plural strokes); V31A 𓎢 phonogram *k*;
N35A 𓈗 phonogram *mw* and determinative (water); N17 𓇿 logogram *tꜣ* and determinative
(land); Z6 𓏱 determinative (death, enemy); U7 𓌻 phonogram *mr*; Aa15 𓐝 phonogram *m*;
D6 𓁻 determinative (actions of the eye).

Source: the **Gardiner sign list** (A. H. Gardiner, *Egyptian Grammar*, 3rd ed., Sign
List) — standard reference facts about what these signs do, restated in the column
shape of the table beside them, with transliterations in this corpus's TLA convention.
Licence: **CC BY-SA 4.0**, this project's own work, like the corpus it is built for.

> Sign-function supplement: Egyptology-APP, 2026-09-06, after the Gardiner sign list.
> CC BY-SA 4.0.

Every row carries `source_note = "project supplement"`, so a reader of the merged
inventory can always tell which half a class came from; the file is separate from
`sign_functions.csv` for the same reason, and the two never name the same sign.
`app/services/sign_functions.py` loads both and folds the seven function labels into
five classes plus `unk`. Note that Nederhof writes the Gardiner variants lower-case
(`Z3a`, `V31a`, `N35a`) and the supplement upper-case; nothing joins on that column.

## Every copy of the data in this repository

CC BY-SA 4.0 applies to each of these, not only to `examples.csv`:

| File | What it is | Licence |
|---|---|---|
| `data/processed/examples.csv` | the built corpus | CC BY-SA 4.0 |
| `data/raw/real_examples_worklist.csv` | an earlier full copy of the same source rows | CC BY-SA 4.0 |
| `data/processed/reviewed_annotations_export.csv` | corpus text plus this project's annotations | CC BY-SA 4.0 |
| `data/benchmarks/*.csv` | queries and expectations derived from corpus readings | CC BY-SA 4.0 |
| `data/processed/helsinki_lexicon.csv` | sign-group → reading counts (see "Sign-reading lexicon" above) | CC BY 4.0 upstream, wrapped **CC BY-SA 4.0** here[^lexicon] |
| `data/processed/sign_functions.csv` | sign → function inventory (see "Sign functions" above) | **CC BY 4.0**, Mark-Jan Nederhof — *not* CC BY-SA[^signfunctions] |
| `data/processed/sign_functions_supplement.csv` | 13 rows for 11 signs Nederhof's Unicode 5.2 list does not cover (see "This project's supplement" above) | CC BY-SA 4.0, this project, after the Gardiner sign list |

Exports produced by the app and by `scripts/export_reviewed.py` carry a `licence`
column repeating the attribution, because a file that leaves the repository loses
sight of this one.

The **Similar text** page (ROADMAP item E, 2026-09-05) changes nothing on this page. It
reads `hieroglyphs`/`hieroglyphs_norm` and `translation`, which are columns of the same
corpus rows under the same per-source licences the workspace already displays, adds no new
source, and shows the same attribution footer on every result. Its two frozen files —
`data/benchmarks/cross_edition_pairs_v1.csv` (corpus transliterations, quoted verbatim)
and `data/benchmarks/similar_text_eval_v1_results.csv` (ranks and scores only) — are
covered by the `data/benchmarks/*.csv` row above: **CC BY-SA 4.0**. Nothing a visitor types
into that page is stored anywhere.

## Sui generis database rights (§4)

This project is hosted in the EU, where Directive 96/9/EC gives a database maker its
own, copyright-independent right over substantial extraction and re-use — CC BY-SA
4.0 §4 defines "Sui Generis Database Rights" by reference to it. Three consequences
follow directly from the licence text:

- **§4(a)** affirmatively grants the right "to extract, reuse, reproduce, and Share
  all or a substantial portion of the contents of the database" — the bulk import
  performed by the `scripts/import_*` scripts is expressly permitted, not merely
  tolerated.
- **§4(b)** makes `examples.csv` itself Adapted Material — "if You include all or a
  substantial portion of the database contents in a database in which You have Sui
  Generis Database Rights, then the database … (but not its individual contents) is
  Adapted Material, including for purposes of Section 3(b)" — regardless of whether
  any single row clears the copyright threshold for an adaptation. This is the
  clearest basis for releasing `examples.csv` as CC BY-SA 4.0.
- **§4(c)** requires §3(a) attribution whenever a substantial portion is shared, which
  the committed CSV is. Per CC's Data FAQ
  (<https://wiki.creativecommons.org/wiki/Data>), ShareAlike over a database "does not
  require you to ShareAlike any copyright or other rights you have in the individual
  contents" — the basis on which this repository's code stays MIT while the data it
  builds is CC BY-SA 4.0.

## Warranty disclaimer (CC BY-SA 4.0 §5)

Unless otherwise separately undertaken, the licensor offers the licensed material
as-is and makes no representations or warranties of any kind concerning it. Where
disclaimers of warranties are not allowed in full or in part, this disclaimer may not
apply. The full text is at
<https://creativecommons.org/licenses/by-sa/4.0/legalcode>.

## Termination, cure and irrevocability (§6)

§6(a) terminates a recipient's rights automatically on a licence violation. §6(b)(1)
reinstates them "automatically as of the date the violation is cured, provided it is
cured within 30 days of Your discovery of the violation" — so an attribution gap of
the kind this file exists to prevent is fully curable if fixed promptly once noticed,
though liability for the non-compliant period can still attach. Separately, CC
licences are irrevocable: a source that later changes its terms cannot reach back and
relicense copies already received under the original terms. (This does not rescue a
relicensing that was invalid from the start, because a licensor cannot grant rights it
never held — see the Helsinki/Ramses discussion above, now resolved for this project
by direct permission rather than by that principle.)

## If you deploy this publicly

Attribution must reach the person viewing the data, not only this file. The app
displays the attribution in the sidebar. Do not remove it, and do not present the
corpus as this project's own work.

The Demotic dataset referenced in `scripts/download_all_sources.py`
(`tla-demotic-v18-premium`) is also CC BY-SA 4.0. It is downloaded but is **not** part
of `examples.csv`: it carries no hieroglyphic writings (0 of 13,383 rows), so it
cannot support the sign-based reading this tool provides. If you build it in, add its
citation here too.
