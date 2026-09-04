# Two permission requests

Both ask for data the project cannot use without permission. Send them separately —
different people, different material, independent outcomes.

---

## Email 1 — Dr Mark-Jan Nederhof (St Andrews Corpus)

**Would give you:** Urkunden IV, including Urk. IV 1 (the text of the expert trial),
and English translations for the texts he has edited.

**Address:** not published in plain text — it is shown as an image on his homepage,
<https://mjn.host.cs.st-andrews.ac.uk/>. Open that page and read it off, or use the
St Andrews staff directory. School of Computer Science, University of St Andrews,
North Haugh, St Andrews, Fife KY16 9SX.

**Subject:** Permission to include St Andrews Corpus texts in an open Egyptology tool

Dear Dr Nederhof,

I am building an open, non-commercial research tool that suggests readings for Ancient
Egyptian sign sequences by finding real parallels in a corpus. It is not OCR and not
machine translation: every suggestion is grouped from sentences that actually exist in
the corpus and is shown with its evidence — the attested sign groups, how often each
reading occurs, and the source rows behind it. Where nothing is attested, it says so
rather than guessing.

It is live at https://egyptology-corpus-retrieval.streamlit.app and currently holds
26,196 sentences from the Thesaurus Linguae Aegyptiae corpora and the AES corpus, both
CC BY-SA 4.0 and both credited in the application itself and in the repository's data
licence file.

An Egyptologist who trialled it worked on Urk. IV 1, the autobiography of Ahmose son of
Abana, and pointed me to your edition of that text. Two parts of the St Andrews Corpus
would help the tool considerably:

1. Urkunden IV. It is absent from every openly licensed corpus I have been able to
   find, and it is the sort of material specialists reach for first.
2. Your English translations. Every translation currently in the corpus is German, as
   both sources are Berlin and Leipzig projects. English would make the tool usable for
   a much wider readership.

Would you be willing to license those texts — hieroglyphs, transliteration and English
translation — under CC BY-SA 4.0, or any terms you prefer that permit redistribution
with attribution? You and the St Andrews Corpus would be credited in the application
and in the data licence file alongside the existing TLA and AES credits, with a record
of exactly what was taken and any normalisation applied.

For completeness: I did look at the Unicode conversions at nederhof.github.io/hierojax.
They carry the hieroglyphs but no transliteration, and the repository is GPL-3.0, which
is why I am asking about the underlying corpus rather than simply using those files.

I would be glad to work to whatever format and attribution you prefer, and to show you
the tool first if that would be useful.

With thanks and best wishes,

Ledio Durmishaj
l.durmishaj@apelos.de

---

## Email 2 — Thesaurus Linguae Aegyptiae / BBAW

**Would give you:** possibly Urk. IV, and access to more of the full corpus. The
"premium" sets already in use are 12,773 of TLA's 55,026 sentences — filtered to the
fully intact, unambiguously readable ones.

**Address:** no direct address is published. Use the contact form at
<https://aaew.bbaw.de/kontakt>, or telephone +49 (0)30 20370-478 (BBAW, Unter den
Linden 8, 10117 Berlin). Their data page asks projects using their raw data to contact
the research coordinator and names Daniel Werning for raw corpus data, so addressing it
to him via the form is appropriate.

**Subject:** Open Egyptology tool using the TLA corpora — two questions about data

Dear colleagues,

Your data publications page asks that projects using TLA raw data make themselves
known, so I am writing to do that, and to ask two questions.

I have built an open, non-commercial research tool that suggests readings for Ancient
Egyptian sign sequences from real corpus parallels, showing the evidence behind each
suggestion and stating plainly when nothing is attested. It is live at
https://egyptology-corpus-retrieval.streamlit.app.

It uses the tla-Earlier_Egyptian_original-v18-premium and tla-late_egyptian-v19-premium
datasets, together with the AES corpus. TLA is credited in the application sidebar, in
a footer on every page, in the repository's data licence file, and in a licence column
carried by every exported file, with the adaptations made to the data recorded
(normalisation, re-segmentation, and unification of the suffix-pronoun marker between
the two corpora).

My two questions:

1. Urkunden IV. An Egyptologist trialling the tool worked on Urk. IV 1, the
   autobiography of Ahmose son of Abana. It is in the TLA corpus but not in the
   published premium datasets. Is there any prospect of Urkunden IV appearing in an
   openly licensed release, or of obtaining it for this use?
2. The wider corpus. The premium sets are, as I understand it, the fully intact and
   unambiguously readable subset. Damaged and ambiguous sentences are exactly the cases
   where a reader most wants help, so a larger release would be valuable — is more of
   the corpus available, or planned?

I am happy to describe the project in more detail, to adjust the attribution in any way
you would prefer, or to share what the tool produces on your data.

With thanks for making the corpus openly available at all — it is what made the project
possible.

Ledio Durmishaj
l.durmishaj@apelos.de

---

## Notes

- Both name a licence explicitly, so the recipient can agree without working out what
  agreeing would mean.
- Both mention that an Egyptologist has already trialled the tool. That is the most
  persuasive line in either message: the request is not hypothetical.
- If either is granted, the import path is already built — parameterised importers,
  automatic alignment reporting, a validated method for reconciling transliteration
  conventions, deduplication, and a regression test that the trial sentence must still
  read correctly before any new corpus ships.

---

## Email 3 — Reply to Dr Nederhof's second message (2026-09-02)

**Context:** his second mail of 2026-09-02 answered our follow-up. He confirmed CC BY-NC-SA
4.0 ("sounds about right") and the intended use ("sounds perfect"), warned that his corpus
follows Hannig's conventions (no z/s distinction, no "." before the feminine t), pointed to
Rosmorduc's work and his own ongoing research on sign functions, defended keeping the
Unicode format controls, and asked whether the site is academic research and (he gathers)
non-commercial.

**Subject:** Re: Permission to include St Andrews Corpus texts in an open Egyptology tool

*(Final version as sent by Ledio, 2026-09-02.)*

Dear Mark-Jan,

Thank you for the permission, for confirming CC BY-NC-SA 4.0, and for taking the time to
look so closely. Here is how I will handle each point.

Licence and handling. The St Andrews texts will be kept in a separate file that is not
part of the public repository and will not be offered for download. In the application,
each row will be labelled with the corpus name, your name, "used with permission,"
CC BY-NC-SA 4.0, and the relevant edition citation where available. The data licence
file will also state that this material is not covered by the CC BY-SA licence that
applies to the rest of the corpus. If you would prefer a particular citation format,
such as the corpus URL or a publication, please let me know and I will use it.

Your question: the website is noncommercial. Its purpose and audience are academic. It
is a research and teaching aid, and the design decisions so far have come from the
Egyptologists who have tested it. However, I am not attached to a university; I am a
software developer building it in my own time. If your work on sign functions ever
needs an implementation partner or a test bed, I would be very glad to contribute and
to make the tool available for evaluation by its users.

Normalisation. You are right that not every difference can be bridged automatically,
and I do not intend to rewrite your text. My rule with the other sources is to preserve
each source's own form for display and convert only genuine notational differences for
matching. For your corpus, the z/s merger and the undotted feminine t are not merely
notation, but information that is absent, so I will preserve them exactly as you wrote
them. The search will treat s/z and "nb.t"/"nbt" as equivalent only for matching
purposes, in the same way it already treats j, i and y as one letter.

One structural question: the Hi and Tr files pair hieroglyphs and transliteration at
the level of Sethe's lines, while phrases in the Tr file can run across line boundaries.
The reading suggestions need word level alignment, with one sign group per
transliterated word. Does the word level alignment displayed by PhilologEg exist in the
data, or only at display time? If it exists only at display time, I will import the
texts first as line level parallels: searchable and cited, but not used for reading
suggestions, since proper alignment is a research problem of its own. Likewise, if
there is a written description of the conventions used in the Tr files, including the
<N> and <@N> anchors and the dots in verbal endings, a pointer would save me from
guessing.

Segmentation. Your diagnosis is exactly right. The current segmenter is a unigram
lattice over attested sign groups, so it does not know whether a sign is acting as a
determinative, phonetic complement, or logogram. I will read Rosmorduc's papers on
automatic transliteration, and I would be grateful for a reference to the related
research you are involved in.

Format controls. I have changed my mind on this. A pasted query will keep its controls
as quadrat boundaries. Whether that measurably helps word segmentation is something I
can test using the segmentation benchmark, and I will send you the result even if the
answer is no. None of the sources I currently hold contains those controls, so your
files would be the first corpus in the project to preserve them.

I will write again once your texts are imported correctly, so that you can see the
attribution as it appears.

With thanks and best wishes,

Ledio Durmishaj
l.durmishaj@apelos.de

---

## Email 4 — Serge Rosmorduc / Université de Liège (Ramses Transliteration Corpus) — OPTIONAL

**Why optional:** the corpus (Zenodo 10.5281/zenodo.4954597) is CC BY-NC-SA 4.0 per its
README, which already permits our non-commercial use with attribution. This mail is a
courtesy notice plus a request for a CC BY-SA grant that would let the rows go public.
**Addressees (checked 2026-09-02):** To: `ramses@ulg.ac.be` — the official contact on
Ramses Online (ramses.ulg.ac.be/site/contact; Service d'égyptologie, Place du XX-Août 7,
B-4000 Liège). Cc: Stéphane Polis, project director at ULiège — `S.Polis@uliege.be` (read off the
ULiège directory sheet by Ledio, 2026-09-02). Serge Rosmorduc (Cnam, computing side, author
of the Zenodo record 4954597 and gitlab.cnam.fr/rosmorse/ramses-trl) publishes no email
on his lab page, GitHub or qenherkhopeshef.org; the project address reaches him, or ask
Polis to forward. Zenodo shows the record as CC BY 4.0, version 2021-06-15; the README in
the zip says CC BY-NC-SA — mention that discrepancy in the mail (it is one more reason to
ask for a clear grant).

**Subject:** Ramses Transliteration Corpus in a non-commercial Egyptology tool — notice and a licence question

Dear Dr Rosmorduc, dear colleagues in Liège,

I am writing to let you know how I am using the Ramses Transliteration Corpus
(v2019-09-01, Zenodo 10.5281/zenodo.4954597), and to ask one question about its licence.

I build a non-commercial, open-source research tool that suggests readings for Ancient
Egyptian sign sequences by finding attested parallels in a corpus and showing the
evidence behind each suggestion. It is live at https://egyptology-corpus-retrieval.streamlit.app
and currently holds about 31,000 sentences from the Thesaurus Linguae Aegyptiae, the AES
corpus and the BBAW export, all CC BY-SA 4.0. Late Egyptian is its weakest period, and
your corpus is the only substantial machine-readable source for it. Two Egyptologists who
trialled the tool both landed in exactly that gap.

Under the CC BY-NC-SA 4.0 terms in your README I intend to load the Ramses sentences into
the application as a separately labelled, non-redistributed dataset: each row credited to
the Ramses Project and to you, the licence shown, and the file kept out of the public
repository so that the CC BY-SA corpus and your NC material are never mixed. The README's
note that the transliteration is normalised to the expected grammatical form will be
stated in the interface. Please tell me if any of this is not what you intended.

One small point I should mention: the Zenodo record lists the licence as CC BY 4.0,
while the README inside the archive states CC BY-NC-SA 4.0. I am treating the README as
authoritative, and the non-commercial arrangement above follows from that.

My question: would the project consider granting the corpus, or the parts of it you
choose, under CC BY-SA 4.0 for this use? That would let the rows join the public dataset
and be redistributed with attribution, which the Helsinki group's CC BY 4.0 release of
their Ramses-trained lexicon (which the tool already uses, credited to Helsinki and to you)
suggests may be acceptable. If not, the arrangement above stands and I am grateful for
the corpus as it is.

With thanks and best regards,

Ledio Durmishaj
l.durmishaj@apelos.de

---

## Email 5 — Reply to Dr Nederhof's third message (2026-09-02) — DRAFT, to send

**Context:** his third mail of 2026-09-02 (reply to Email 3). Licensing "sounds fine";
citation URL `https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/`; word-level alignment
confirmed *not* present in the data (line numbers, anchors, precedence files, run-time
auto-alignment whose output is discarded); papers 2009b (concepts), 2008b and W15-4810
(segmentation/alignment); student projects on W15-4810 next year, possible collaboration;
**asks us for aligned datasets** for training/testing segmentation and automatic
transliteration (he knows Rosmorduc's); RES ≠ MdC ≠ Unicode, convert with HieroJax or
hieropy; **proposes a "similar phrases" finder** (edit distance over transcription,
transliteration or translation, incl. the user's own past translations).

Facts checked before drafting: hieropy 0.1.9 converts all 67 Urk. IV 1 segments with
format controls; the align file for Urk. IV 1 is ten segment pairs; the dataset figures
below are from the 2026-09-01 survey (memory `open-data-sources-surveyed`).

**Subject:** Re: Permission to include St Andrews Corpus texts in an open Egyptology tool

Dear Mark-Jan,

Thank you. I will cite the corpus with that URL, together with your name, the licence
and the edition given in each text's manifest.

Alignment: that matches what I found in the files, so I will import the texts as they
are: phrases (transliteration and translation) and Sethe lines (hieroglyphs with the
transliteration between the anchors), each cited, and I will not derive word alignments
from them. I tried hieropy on the Urk. IV 1 hieroglyphic file this morning: all 67
segments converted, and the output keeps the insertion and joiner controls, which is
exactly what I need for the segmentation test I mentioned. I will use it in the import
script (it stays out of the application itself because of the licence difference).

Aligned data. Everything I know of that pairs hieroglyphs with transliteration at the
word level is below. The caveats first, because they matter for your purpose: in all of
them the alignment is one sign group per whitespace-separated word, none is annotated
with sign functions, and the word boundaries are the editors', not the scribes'.
Transliteration conventions differ between them (Berlin ꞽ and .t against j and no dot).

- Thesaurus Linguae Aegyptiae exports on Hugging Face (thesaurus-linguae-aegyptiae/*),
  CC BY-SA 4.0: Earlier Egyptian v18 and Late Egyptian v19 with Unicode hieroglyphs
  word-spaced against the transliteration; the Demotic set has no hieroglyphs. I hold
  16,373 aligned sentences from these.
- AES, Ancient Egyptian Sentences (BBAW), CC BY-SA 4.0, relANNIS export: 9,823 aligned
  sentences in my corpus.
- phiwi/bbaw_egyptian on Hugging Face, CC BY-SA 4.0: 100,736 rows from the January 2018
  BBAW snapshot, 35,503 with hieroglyphs as MdC codes, one group per word; German
  translations.
- AED-TEI (Simon Schweitzer; Zenodo 3580939), CC BY-SA 4.0: the TEI stand-off source
  behind AES and bbaw_egyptian, 11,000+ texts with separate hieroglyph files, plus a
  dictionary of 30,000+ lemmas. Largest and cleanest of the Middle Egyptian sources.
- Ramses Transliteration Corpus v2019-09-01 (Rosmorduc; Zenodo 4954597), CC BY-NC-SA
  4.0 per its README: about 71,000 Late Egyptian sentences, Gardiner codes with word
  separators, transliteration normalised to the expected grammatical form rather than
  the actual spelling. You know this one.
- Helsinki "TranslitModels" (Zenodo 7991241), CC BY 4.0: not models but three
  spelling→reading lexicons with frequencies, 43,416 spellings from AES and 48,914 from
  the Ramses training set. Useful as a lookup table or as test material.

I have not found anything with sign-level function annotation apart from your own
Westcar and Shipwrecked Sailor material. If a test set of real user queries is useful
to you, I can share the evaluation sets I use (attested sentences with their readings,
and the pasted lines the two Egyptologists tested with), all from CC BY-SA sources.

Your phrase-search idea is close to what the tool already does at its core: the current
search ranks corpus sentences by character n-gram similarity of the transliteration,
and the result is a list of attested parallels with their source. Extending it in the
three directions you describe is straightforward: the same index over the sign
sequence and over the translation, an edit-distance re-ranking of the best candidates,
and, the part I think you actually want, letting a user add their own transliterated
texts as a private corpus that is searched alongside the published one. I will build
that once the current infrastructure work is done this month, and I would value your
testing it on a text you are working on.

Two small questions. First, the sign list your 2015 paper builds on, the XML with the
functions of the Unicode signs at egyptian/unicode/: is it available for reuse, and
under what terms? It would be the a-priori knowledge for the sign-function segmenter I
am planning, and I would rather build on your list than on a worse one. Second, if your
students work on segmentation or alignment next year and a corpus of 30,000 aligned
sentences with a test harness helps them, I am glad to provide it and to compare
results.

With thanks and best wishes,

Ledio Durmishaj
l.durmishaj@apelos.de

## Reply from Projet Ramses / Université de Liège — received 2026-09-04

Answer to Email 4 (courtesy note + CC BY-SA request). Quoted verbatim, personal greeting
omitted; this is the archived basis for the Ramses licence statement in DATA-LICENSE.md.

> Many thanks for your message!
>
> [on loading the Ramses sentences as a separately labelled, non-redistributed dataset
> under the README's CC BY-NC-SA 4.0 terms, credited to the Ramses Project, licence shown,
> file kept out of the public repository, normalisation caveat stated in the interface:]
> Perfect. Green light from our side.
>
> [on the Zenodo record saying CC BY 4.0 while the README says CC BY-NC-SA 4.0, and the
> question whether the project would grant the corpus, or the parts of it we choose, under
> CC BY-SA 4.0 for this use, so the rows can join the public dataset with attribution:]
> Yes, no problem for us! Thanks for clarifying the question in advance with us.
> All the best with your project!

**What this settles.** (1) The private NC arrangement is explicitly approved. (2) For this
project, the Ramses Transliteration Corpus (v2019-09-01, Zenodo 10.5281/zenodo.4954597) is
granted under **CC BY-SA 4.0**, so Ramses rows may enter `data/processed/examples.csv` and
be redistributed with the attribution "the Ramses transliteration corpus V. 2019-09-01,
University of Liege/Projet Ramses". (3) The Helsinki lexicon's Ramses-derived rows are
covered by the same grant; no email to Helsinki is needed on that point.
**What it does not change.** Ramses rows stay out of the live app until item A: with them
loaded, the expert paste gate falls 8/8 → 3/8 and v4 0.95 → 0.90 (roadmap, 2026-09-04).
That is a modelling constraint, not a licence one.


## Reply from Dr Nederhof to Email 5 — received 2026-09-04 (his fourth mail)

Archived verbatim; this is the basis for using his sign-function XML file.

> Dear Ledio,
>
> Apologies for delays. The semester is about to start.
>
> Many thanks for the detailed listing of corpora that pair hieroglyphs with
> transliterations. I will pass this on to my students, with the suggestion that they
> start with AED-TEI, which sounds like the "easiest" to work with assuming the standard
> readings of signs.
>
> Also thanks for the offer of real user queries, but I would start with partition of the
> corpora into training and testing sets and do evaluation the traditional way.
>
> I'm looking forward to testing your website again once new functionality has been added.
>
> To be clear, I was not proposing that your website should allow users to add their own
> transliterated texts. But I am intrigued by the problem of finding similar (Egyptian)
> text in a corpus, especially if one has several tiers of annotation. Traditional edit
> distance may be effective to some extent, but could one improve upon that?
>
> You can use the XML file with functions under whatever license you prefer. I would be
> glad if they can be of help.
>
> The UniKemet database of Unicode also lists functions, with newer terminology (e.g.
> "determinatives" they now call "classifiers"). But it should be taken with a grain of
> salt. The listed functions often belong to the _single_ token they identified in order
> to confirm existence of a sign, omitting many other functions that that same sign can
> have.
>
> My XML file only includes Unicode 5.2. My intention is to extend it to include the
> extended set from Unicode 16. But this may require reinterpreting manually the limited
> sign functions currently in UniKemet, and this would not be trivial. I would then
> probably also consult the Thot Sign List ( https://thotsignlist.org/ ) for comparison.
>
> Thanks also for the offer to provide a test harness for segmentation. I should point out
> that these are all-year projects, running until about April 2027, so it might take my
> students a while to produce their first prototype.
>
> Best regards,
>   Mark-Jan

**What this settles.** (1) His sign-function XML (`egyptian/unicode/` on his site, Unicode
5.2 sign set) may be used under any licence we choose → we will publish our copy as
**CC BY 4.0, attributed to Mark-Jan Nederhof**, alongside the CC BY-SA corpus (BY is
compatible). Item C's licence risk is gone. (2) Item E is rescoped: no user-uploaded texts;
"similar text across several tiers of annotation", and the research question "can one
improve on edit distance?". (3) He will retest once new functionality is up. (4) He
declines real user queries as test material; classic train/test partition instead.
(5) Second opinions for sign functions: UniKemet (newer terms — "classifiers" for
determinatives; functions drawn from single attested tokens, so incomplete) and the Thot
Sign List for comparison. Students' projects run to ~April 2027.

## Email 6 — Reply to Dr Nederhof's fourth message — DRAFT

**Subject:** Re: Permission to include St Andrews Corpus texts in an open Egyptology tool

Dear Mark-Jan,

Thank you — and no apology needed; I know what the start of a semester looks like.

The sign-function file is exactly what the segmentation work was waiting for. I will
include it under CC BY 4.0, credited to you by name with a link to your Unicode page,
next to the CC BY-SA corpus; if you would prefer different wording or a different licence,
one line from you is enough and I will change it. Thank you also for the warning about
UniKemet's functions coming from single attested tokens — I will treat it and the Thot
Sign List as cross-checks, not as sources of truth, and stay with the Unicode 5.2 set your
file covers.

Understood on the similar-text question: no user uploads, and the interesting problem is
similarity across tiers — sign sequence, transliteration, translation and, once lemma
identifiers are wired in, lemmas — and whether something beats plain edit distance. That is
what I will build next, and I will report what the numbers say either way.

Understood too that your students will evaluate on a corpus partition rather than on user
queries; the offer stands if it is ever useful, and AED-TEI is a good place for them to
start.

I will write when the new functionality is up so you can test again.

With best regards,
Ledio Durmishaj
