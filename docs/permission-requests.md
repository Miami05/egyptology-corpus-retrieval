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
