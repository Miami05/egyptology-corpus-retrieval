# What Mark-Jan Nederhof will see credited to him

Written 2026-09-05, when the St Andrews importer landed (roadmap item 4). The roadmap
line asked for an "attribution screenshot to him"; a screenshot has to be taken from
the running app on the server, so this file is the text of what that screenshot will
show, ready to check before it is sent. Nothing here is a promise about the future:
every string below is either copied from the code that renders it or from
`DATA-LICENSE.md`.

Two distinct things of his are used, under two different grants. They must not be
conflated in the mail to him.

| | St Andrews text corpus | Sign-function XML |
|---|---|---|
| Grant | mail of **2026-09-02**, CC BY-NC-SA 4.0 | mail of **2026-09-04**, "whatever license you prefer" |
| Our licence | CC BY-NC-SA 4.0 (his) | **CC BY 4.0**, our choice under his grant |
| Where it lives | `data/private/standrews.csv`, gitignored | `data/processed/sign_functions.csv`, committed |
| Redistributed? | **No.** Local/server only, never in the repo, never in an export, never in the public corpus | Yes — it is in the public repository |
| Rows | 7,659 sentences from 94 texts / 102 witnesses | 1,444 function entries covering 780 of the 1,071 Unicode 5.2 signs |

---

## 1. The in-app credit line for a St Andrews row

Rendered by `_private_source_credit_html("StAndrews")` in
`app/ui/whyptology_app.py`, from the `PRIVATE_CORPUS_CREDITS["StAndrews"]` entry.
It appears in the **sidebar** and in the **footer of every page**
(`render_attribution_footer`), whenever at least one St Andrews row is in the loaded
frame — so on the server, where the private CSV is present, it is on every page.

Exactly, with "source" and the licence name as links:

> St Andrews Corpus of Ancient Egyptian texts, Mark-Jan Nederhof — licensed
> [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
> ([source](https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/)). Adapted: Hannig
> transliteration conventions preserved as written; provenance recorded in
> grammar_notes; normalised columns added. Displayed here under its own licence for
> non-commercial use; the underlying files are not redistributed.

It is deliberately **not** folded into the CC BY-SA sentence that credits TLA, AES,
BBAW and Ramses: that sentence is a licence claim, and his rows are under a different
licence entirely.

### One change the importer now makes that this line does not yet mention

`scripts/import_standrews.py` also (a) tokenises suffix pronouns on his own `=`, so
`Dd=f` is stored `ḏd =f` like every other corpus row, and (b) drops the `^`
proper-name marker, which is markup rather than a letter. Both are described in
`DATA-LICENSE.md`. Suggested replacement for the `changes` string in
`PRIVATE_CORPUS_CREDITS["StAndrews"]` (`app/ui/whyptology_app.py`), for whoever owns
that file next — this file does not edit it:

```
"changes": (
    "Hannig transliteration conventions preserved as written (no z/s distinction, "
    "no .t dot); suffix pronouns tokenised on the author's own '='; the '^' "
    "proper-name marker dropped; provenance recorded in grammar_notes; "
    "normalised columns added"
),
```

### What a single row carries

Every row repeats the attribution in its own data, so it survives being read out of
context:

- `source` = `StAndrews`
- `source_ref` = `https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/ urkIV-001 (urkIV-001Tr) line 2`
  — the citation URL he asked for in his mail of 2026-09-02, then the text, the
  witness file and his own line label.
- `grammar_notes` = `St Andrews corpus, Hannig transliteration conventions (no z/s
  distinction, no dot before the feminine .t), left as written; suffix pronouns
  tokenised on the author's own '='. Witness: Nederhof. Follows Urkunden der 18.
  Dynastie 1.`

---

## 2. The `DATA-LICENSE.md` entry

`DATA-LICENSE.md` § "St Andrews Corpus of Ancient Egyptian texts (`source =
StAndrews`)" is the long form: it names him, gives the citation URL, states plainly
that **his site carries no licence statement at all** and that the CC BY-NC-SA 4.0
designation rests entirely on his mail of 2026-09-02, records the Hannig convention
caveat, and says the files are not redistributed. As of today it also names the
importer, the row counts, and the fact that no word-level sign alignment was taken
from the archive.

## 3. The sign-function table

`data/processed/sign_functions.csv` — 1,444 entries, one per function element of his
`signuse.xml`, joined to the Unicode codepoints in his `signunicode.xml`. Every row
carries the credit in a `source_note` column, so it cannot be separated from the data:

> Mark-Jan Nederhof, sign-function list (Unicode 5.2 set),
> https://mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/ — used under his written
> grant of 2026-09-04; published here CC BY 4.0

`DATA-LICENSE.md` § "Sign functions of the Unicode 5.2 hieroglyphs" carries the same
credit in full, quotes his grant, and records that we chose CC BY 4.0 under it and
will change it on one line from him. It is not wired into the app yet — it is
a-priori knowledge for item C — so no in-app credit line exists for it today. **When
it is wired in, a credit line must be added at the same time**, because CC BY 4.0
makes attribution a condition of use exactly as the Helsinki lexicon's does
(`LEXICON_CREDIT` in `app/ui/whyptology_app.py` is the pattern to copy).

---

## For the screenshot

On the server, with `data/private/standrews.csv` in `PRIVATE_DATA_DIR`, open any
page and capture the footer (or the sidebar credit block). The St Andrews sentence
renders only when St Andrews rows are actually loaded, so a screenshot from a
deployment without the private file will not show it — check the sentence is there
before sending.
