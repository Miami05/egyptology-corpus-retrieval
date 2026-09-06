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

---

## Email 7 — expert round 2 (five before/after cases)

Draft, not sent. The ask sheet is `docs/expert-round-2-ask.md` (and, if built, the page
`data/benchmarks/expert_round_2.html`). Send whichever form the recipient prefers — the
five cases and the five questions are identical in both.

### To Camilla

**Subject:** One ranking decision, five cases — 15 minutes, if you have them

Dear Camilla,

Your trial last time changed the shape of this project. The core criticism — that a tool
guessing readings out of a model was the wrong thing to build — is why it is now a
retrieval tool: it does not generate anything, it finds the closest real sentences in the
corpus and shows you the evidence, and where the corpus is silent it says so. I would not
have got there without your first look.

I have hit a decision I cannot make from the numbers, and it is exactly the kind of thing
only a reader can settle. I have a small change to the rule that orders the three
suggestions. On five test strings it moves one suggestion up or down: in one case it
lifts a matching parallel from 6th place to 1st; in four cases it pushes a match
that was near the top further down, twice out of the top three. My automatic score cannot
tell whether that is an improvement or a loss — to it, a demoted 1st-place match and a
rescued 3rd-place match count the same. Your judgement can.

The ask is five short questions, one per case, a tick or a sentence each — under fifteen
minutes. Each case shows the string, the two orderings side by side, and asks which one
you would rather have been shown. There is no answer I am checking you against; your
reading is the measurement, and I have frozen the two orderings in advance so it can only
decide this one yes/no question and nothing else.

The cases are attached / at the link below. No obligation, and thank you either way — and
separately, if you ever have a text you have not shown me, a fresh trial remains the most
useful thing anyone can give this.

With thanks again,

Ledio

### Two-line variant — Sophie

Hi Sophie — following the notation feedback you gave, I have one ordering decision I can only
settle by asking someone who reads this material: five strings, five quick questions (a
tick or a sentence each, under 15 minutes), each showing two orderings of the tool's three
suggestions and asking which you would rather have seen. The sheet is attached / at the
link; no obligation, and thank you either way.

### Two-line variant — Nederhof

Dear Mark-Jan — two quick things: your sign-function table is now built into the public
repository under CC BY 4.0 with the credit line to you (I can send the screenshot), and the
St Andrews rows are imported privately under your CC BY-NC-SA grant — kept local and never
redistributed, per `docs/standrews-attribution.md`. Separately, if you have fifteen
minutes, I would value your read on five before/after ranking cases (sheet attached / at
the link): five strings, five quick questions, asking which of two orderings of the three
suggestions is the better one to show.

### Notes on sending it

- **Do not send anything until it is ready to send.** The page and sheet must be built and
  attached, and Camilla's version should only go out once she can actually open the cases.
- The Camilla version's second sentence is the one that matters — it credits her
  criticism as the cause of the corpus-based framing, which is the honest record. Keep it.
- Nederhof gets the attribution news first and the ask second, on purpose: the credit and
  the private-import confirmation are owed regardless of whether he does the round.
- All three are attachment-or-link: the five questions are identical across the ask sheet
  and the HTML page, so send whichever form each person will find easier.

## Email 8 — the live-site round (2026-09-06): new address, reviewer key, the five cases

Supersedes Emails 6 and 7 as the thing actually sent. One mail per person; the reviewer
key goes in a **separate** message (text message or a second email), never in the same mail
as the address and never in this file.

### To Mark-Jan Nederhof

**Subject:** Re: Permission to include St Andrews Corpus texts in an open Egyptology tool — it is live

Dear Mark-Jan,

Thank you again — and no apology needed; I know what the start of a semester looks like.

The tool has moved to its own server: https://vela-optiplex-3070.taile0409f.ts.net/
The old Streamlit Cloud address is retired. The public corpus there is now 130,472
sentences (TLA, AES, BBAW and, under the CC BY-SA grant Liège gave this project, Ramses).

Your sign-function file is built in under CC BY 4.0, credited to you by name with a link
to your Unicode page, next to the corpus credits in the footer (1,444 entries covering 780
of the 1,071 Unicode 5.2 signs). If you would prefer different wording or a different
licence, one line from you is enough. Thank you also for the warning about UniKemet's
functions coming from single attested tokens; I will treat it and the Thot Sign List as
cross-checks, not as sources of truth.

The St Andrews rows are imported privately under your CC BY-NC-SA grant, exactly as
agreed: they live only on the server and are served only to a session that has entered a
reviewer key. Nobody visiting the public address sees them, and they are in no export,
share link or repository. I am sending you the key in a separate message. In the sidebar,
open "Reviewer access", paste the key and press Unlock; the record count then rises to
138,131 and a CC BY-NC-SA credit line for the St Andrews Corpus appears in the footer.
The same key also lets you save annotations. Please do not pass the key on; anyone else
who needs it can ask me.

Your similar-text request is live as well: a "Similar text" page that searches across
tiers (sign sequence, transliteration, translation) and shows the matched parallel per
tier. As promised, the number either way: on same-sentence pairs across editions, edit
distance did not beat n-gram cosine on transliteration, and gave a small gain on signs
only. No uploads, as you asked.

Next on my list is your format-control point: I will try the U+13430–1345F controls as
weak quadrat hints in segmentation, starting with the St Andrews texts, and report the
result whether it helps or not.

Separately, if you have fifteen minutes: I would value your read on five before/after
ranking cases. Five strings, five quick questions, each asking which of two orderings of
the tool's three suggestions is the better one to show. The cases are in the attached
file expert_round_2.html; it opens in any browser, needs no internet connection, and a
reply by email with your five answers is all I need.

With best regards,
Ledio Durmishaj

### To Camilla

**Subject:** Your Urk. IV line now reads correctly — and the tool is live at a new address

Dear Camilla,

First, the result you were waiting for. Your trial line, the opening of Ahmose son of
Ibana, pasted exactly as you pasted it, now reads

    ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t

with no fallbacks and no unattested group, against your ḏd=f ḏd=j n=ṯn rmṯ(.t) nb.t. The
only differences are conventions, not readings: the corpus writes yod as ꞽ and separates
suffix pronouns with a space, and it gives =tn because that spelling is what the openly
licensed TLA sentences attest (18 times) for your 𓏏𓈖 group. The four or five errors you
counted came from one cause: the tool trusted the spaces in your paste as sign groups and
never moved a glyph across one, so 𓆑 stayed glued to the wrong ḏd and 𓀀 was cut off from
its noun. It now segments from the corpus instead. The same line reads correctly from
four different spacings (yours, word by word, no spaces, TLA's), and that has been a
release gate since: nothing ships if your line stops reading.

Your trial also changed what the tool is. You said the hard step is not recognising signs
but choosing the reading, since one sign has several values. So it does not generate
readings out of a language model. For each sign group it picks the reading the corpus
actually attests most often, shows you the real sentences that support it, and where the
corpus has nothing it says so instead of guessing. That was my answer to your criticism,
not something you asked for in those words, so I would rather you judged it than took my
word: is this the step you meant, or did you have something else in mind?

It now runs on its own server: https://vela-optiplex-3070.taile0409f.ts.net/
The old address is retired. The public corpus is 130,472 sentences (TLA, AES, BBAW and
Ramses), and a language-stage selector lets you restrict or let the tool infer the stage.

You are not the only Egyptologist looking at it. Dr Mark-Jan Nederhof of the University
of St Andrews reviewed the tool in early September and is testing it as well; his
observations on notation normalisation and segmentation have set two of the next steps,
and he has made his St Andrews Corpus and his sign-function table available to the
project. I mention this so that you know your assessment will sit alongside a second
specialist reading rather than stand alone.

Two things sit behind a reviewer key, which I am sending you in a separate message.
First, saving annotations: your corrections now persist, so if you mark a reading wrong
it stays recorded. Second, Dr Nederhof has allowed his St Andrews Corpus, which
includes the Urkunden IV texts, into the tool for reviewers only (it is CC BY-NC-SA, so it
cannot be shown publicly). In the sidebar, open "Reviewer access", paste the key and press
Unlock; the record count rises to 138,131 and the St Andrews credit appears in the
footer. With the key, your own line appears as a parallel in his edition (ḏd =ꞽ n =ṯn
rmṯ nbt, with the =ṯn you expected), and the tool can be tested on Urk. IV directly.
Please keep the key to yourself; the licence is to this project alone.

I have also hit a decision I cannot make from the numbers, and it is exactly the kind of
thing only a reader can settle. A small change to the rule that orders the three
suggestions moves one suggestion up or down on five test strings: in one case it lifts a
matching parallel from 6th place to 1st; in four cases it pushes a match that was near
the top further down, twice out of the top three. My automatic score cannot tell whether
that is an improvement or a loss. Your judgement can.

The ask is five short questions, one per case, a tick or a sentence each, under fifteen
minutes. Each case shows the string, the two orderings side by side, and asks which one
you would rather have been shown. The two orderings were frozen in advance, so your answer
decides only this one question. The cases are in the attached file expert_round_2.html;
it opens in any browser, needs no internet connection, and a reply by email with your five
answers is all I need.

No obligation, and thank you either way. And separately, if you ever have a text you have
not shown me, a fresh trial remains the most useful thing anyone can give this: it is the
one test that shows where the tool still falls short.

With thanks again,
Ledio

### To Sophie — LinkedIn, two messages (she is a LinkedIn contact, not an email one)

LinkedIn does not accept an .html attachment, so she gets the PDF: `expert_round_2.pdf`
(built 2026-09-06 with headless Chrome from a print variant of the page: the repo's
GentiumPlus-Translit font embedded so ꜣ ꜥ ꞽ render, the answer bar and buttons hidden,
one case per page). Copy on the Desktop.

**Message 1 (with the PDF attached):**

Hi Sophie,

Everything you found in your test is fixed and live, and the tool has moved to its own
server: https://vela-optiplex-3070.taile0409f.ts.net/ (the old link no longer works).

What changed: 130,472 sentences now (TLA, AES, BBAW and the Ramses Late Egyptian
corpus); it accepts Unicode, Manuel de Codage, plain ASCII or pasted hieroglyphs and
shows which reading it understood; a tap-to-insert row of ꜣ ꜥ ꞽ ḥ ḫ ẖ š ṯ ḏ above the box
for phones; and a "Similar text" page for parallels. Your Horus-and-Seth sentence is in
there now: both your original queries, phone and web, return ꜥḥꜥ.n stḫ (ḥr) qnd r-ḏrw ꜥꜣ
wr as the first suggestion, even though you typed stẖ and the edition writes stḫ.

I am sending you a reviewer key in a separate message. In the sidebar, open "Reviewer
access", paste it and press Unlock. Your annotations are then saved, and you see about
7,700 extra sentences from the St Andrews Corpus, which its author has licensed to this
project for reviewers only, so please don't pass the key on.

One favour, if you have 15 minutes: the attached PDF has five strings, each with two
orderings of the tool's three suggestions. For each, just tell me which ordering you
would rather have seen, case number plus Yes or No, in a reply here. No obligation, and
thank you either way.

Ledio

**Message 2 (sent separately, key only, never in this file):**

Reviewer key for the tool: [key]. Sidebar → "Reviewer access" → paste → Unlock. It is
one shared key for the three reviewers, so please keep it to yourself. Tell me if it is
not accepted.

### Notes on sending it

- Attach `data/benchmarks/expert_round_2.html` to the two emails (a copy was put on the
  Desktop on 2026-09-06); Sophie gets `expert_round_2.pdf` on LinkedIn instead. It is self-contained: no external scripts or fonts, so it renders offline
  and inside webmail previews. `docs/expert-round-2-ask.md` carries the same five cases as
  plain text if anyone prefers that.
- The key goes by a separate channel. Ask them to reply "unlocked" once it works so you
  know the gate behaves on their side.
- Nederhof gets the attribution and private-import confirmation first, the ask last, on
  purpose: those are owed regardless of whether he does the round.
