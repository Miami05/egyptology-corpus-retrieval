# Messages: back to Camilla, and inviting others to try the tool

---

## 1. Email — Dr Camilla Di Biase-Dyson (follow-up to the trial)

**Subject:** Whyptology — your trial errors, traced and fixed

Dear Camilla,

Thank you for the trial. It was more useful than anything I could have tested myself,
and I wanted to tell you what came of it.

Every error you found traced to one cause, and it was not the reading model. The tool
treated the spacing of your paste as the segmentation — so `𓆑` was read together with
the wrong `𓆓𓂧`, and `𓀀` was cut off from `𓂋𓍿` and read as a suffix pronoun. Two
smaller things sat on top: your plural strokes are U+133FC where the corpus writes
U+133E5, and the corpus writes suffix pronouns as separate tokens.

Your line now reads

    ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t

from your exact paste, from a word-by-word grouping, and from the text with no spaces
at all — every group attested, nothing guessed. The tool now regroups the signs against
the corpus, shows you where it disagreed with your spacing, and lets you correct the
grouping by hand.

Two corrections to things I had assumed. The A1 prior was not wrong — 595 of 601
standalone `𓀀` in the corpus are `=ꞽ`; the error was the grouping. And `=ṯn` was not a
coverage gap: your spelling `𓏏𓈖𓏥` is attested, as `=tn`.

Where it is still weak, in case you would rather know before looking: Urk. IV itself is
not in the corpus — it is in no openly licensed corpus I could find, and I have written
to Mark-Jan Nederhof and to the TLA in Berlin to ask. The corpus has grown from 12,772
to 26,196 sentences and New Kingdom material from 9 sentences to 5,629, but Dynasty 18
proper is still thin. Translations are German throughout, as both sources are Berlin and
Leipzig projects.

If you have the time, I would value a second look — ideally on a text I have not seen,
since yours has become a regression test and can no longer surprise me. Reading,
searching and the sign-by-sign analysis all work; saving corrections does not persist
yet, so please do not spend effort on annotations.

https://egyptology-corpus-retrieval.streamlit.app

With thanks again,

Ledio Durmishaj

---

## 2. LinkedIn message (short — adapt per person)

Hi [Name],

I've built a small open tool for reading Ancient Egyptian: you paste hieroglyphs and it
suggests readings from real parallels in a 26,000-sentence corpus, showing the evidence
behind each one. It doesn't generate anything — where the corpus is silent, it says so.

An Egyptologist trialled it recently and her feedback fixed several real problems, so
I'm keen to get it in front of a few more people who actually read this material.

If you have five minutes, I'd genuinely value your reaction — especially where it gets
things wrong:
https://egyptology-corpus-retrieval.streamlit.app

No obligation at all, and thank you either way.

Ledio

### Notes on sending it

- **Replace the second paragraph** with one sentence about why *this* person. "I saw
  your work on X" beats anything generic, and it's the difference between a message
  that gets a reply and one that doesn't.
- **Ask for criticism, not praise.** "Especially where it gets things wrong" is the ask
  most likely to get a real answer, and it's the feedback worth having.
- Keep it this short. If they're interested they'll click; if they're not, length will
  not persuade them.
