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

---

## Reply to Sophie, 2026-09-01 — the notation feedback

Her trial (first contact, not Camilla's): `aHa.n stX qnd r Dw Aa wr` on a phone and
`ꜥḥꜥ.n stẖ qnd r ḏw ꜣꜥ wr` on the web both returned nothing. She asked which
transliteration school the tool expects, said no Egyptologist types ASCII and that a
phone has no keyboard for it, asked for photo input, said she would try hieroglyphs if
she could find some to copy, and asked what distinguishes this from the new TLA.

Hi Sophie,

Thank you — you found real bugs in twenty minutes, and both failures were ours. Here is
what each one turned out to be.

**Your phone attempt.** You typed a query, tapped the button and nothing happened. That
was a genuine bug and I reproduced it: the query box only sent its contents when it lost
focus, so your tap did two things at once — it committed the text, and it was itself
swallowed. In my test the search did not run even on a second tap. On a phone the tool
was effectively not searchable. The box and the button are now one form and submit
together.

**Your web attempt.** `ꜥḥꜥ.n stẖ qnd r ḏw ꜣꜥ wr` never reached the search either. Our
query cleaner stripped every non-ASCII character before matching, so what was actually
searched was `n st qnd r w wr` — the ꜥ, ḥ, ẖ and ḏ were simply deleted. A properly typed
transliteration was the input the tool handled worst. The query and the corpus are now
normalised by the same function. While fixing it I found a third bug: about a third of
our corpus was invisible to any text search at all. Also fixed.

**Which school.** TLA / Berlin: ꜣ ꜥ ꞽ ḥ ḫ ẖ š q ṯ ḏ, yod written ꞽ, q rather than ḳ, and
suffix pronouns as separate tokens (ḏd =f). That was stated nowhere in the app, which was
my mistake; it is on the page now. And you should not have to use ASCII: it takes Unicode,
Manuel de Codage (`aHa.n stX` — which we advertised but had never actually implemented, so
your phone query was only half-read), plain ASCII, or pasted hieroglyphs, and it shows you
which reading it understood before you trust the result. You were right about the keyboard,
so there is now a tap-to-insert row of ꜣ ꜥ ꞽ ḥ ḫ ẖ š ṯ ḏ ṱ = above the box — no keyboard
switching, and it works on a phone.

**Why you saw no analysis.** The tab you land on was "Sign-by-sign reading", which is
deliberately blank for a transliteration query — there is nothing to decode when you have
already given the reading — and the suggestions sat on the next tab over. A bad default.
The suggestions come first now.

**Your sentence.** It is not in our corpus at all: `qnd` occurs four times in 26,196
sentences and never with `stẖ`, because the Contendings is outside the openly licensed
part of TLA. You will now get the `ꜥḥꜥ.n stẖ ḥr ḏd …` parallels, and where there genuinely
is nothing, a message saying it is absent from the sentences we hold — which is not the
same as unattested in Egyptian. A blank screen was never an acceptable answer.

**A question back, if you don't mind.** The real limit on all of this is data. We use the
openly licensed part of TLA plus the AES sentences — about 26,000 — and your example fell
straight into the gap. You would know this far better than I do: is there anything else
out there that is (a) openly licensed, ideally CC BY or CC BY-SA, and (b) has
transliteration aligned to the text rather than hieroglyphs or translation alone? Project
exports, digital editions, teaching corpora, anything a non-institutional project is
allowed to redistribute. I have written to BBAW and to Mark-Jan Nederhof, but I am
certain I am missing obvious things — even a pointer to the right person to ask would
help.

**Hieroglyphs to copy.** You mentioned you would try some if you could find text to copy.
Two easy sources: TLA's own sentence view gives copyable hieroglyphs, and the Corpus
explorer inside the app shows the hieroglyphic text of every sentence — you can copy a
line from there and paste it straight back into the workspace to see what it makes of it.

**Photos.** You are right that nobody wants to type hieroglyphs, and this is the most
requested thing I have heard. I do not want to promise OCR, though: hieroglyph recognition
is a research problem of its own and I would be shipping something I cannot validate. If a
photo is genuinely the difference between using this and not, tell me and I will look at
what existing detectors can do — with the honest caveat that the output would be
unvalidated.

**How it differs from the new TLA.** TLA is the authority: a published, lemmatised corpus
and dictionary. You go to it to look up what a text says or what a word means, and if you
have an identified text, TLA is the right tool and mine adds nothing. This is a retrieval
layer on top of TLA's open data for the opposite case — you have a string you are *unsure*
about, a sign group or a reading you cannot decide between, and it answers: which readings
are actually attested for this, ranked, with the corpus rows behind each one, including
where they disagree. Nothing is generated; every suggestion is grouped from sentences that
exist and shown with its evidence, and it records your correction when the ranking is
wrong. TLA tells you what is known; this is meant to help with what is undecided. If that
turns out to be a distinction without a practical difference in your work, I would far
rather hear it now than in six months.

I will write when the fixes are live. If you would try it once more then — with a text you
actually care about — and tell me where it gets things wrong, that is the most useful
thing anyone can give me.

Best,
Ledio

### Notes on sending it

- **Do not promise a date.** "I will write when the fixes are live" is the whole commitment.
- The TLA paragraph is the one she will judge. If you disagree with how it is framed,
  rewrite that part in your own words before sending.
- The bugs are stated plainly on purpose. She did real diagnostic work for free; what is
  owed in return is what it actually found, including the part she could not see.
- Do **not** send this until the fixes are actually deployed, or the first two paragraphs
  become a promise rather than a report.
