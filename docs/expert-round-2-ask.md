# Expert round 2 — five before/after cases for one ranking decision

Prepared 2026-09-05 (roadmap item 4 of the plan for 2026-09-06, done a day early). Five queries where a proposed change to the
ordering rule moves a named suggestion up or down a named number of places. Nothing here
is tuned by the answers; the answers decide one yes/no question, stated at the end.

The before/after suggestion lists are copied verbatim from the evaluation result files
(`data/benchmarks/ceval_v4_v4_app_auto_results.csv` and `…_cfg_c.csv` for the COMP cases,
`data/benchmarks/ceval_holdout_v4_app_auto_results.csv` and `…_cfg_c.csv` for the HOLD
cases). The exact rank each moved suggestion holds before and after was read from
`scripts/inspect_suggestion_boundary.py` under the default and the `cfg_c` presets.

---

## For the reader — what the tool does, and what this round is testing

The tool is a reading-suggestion aid. You give it a string of Ancient Egyptian — pasted
hieroglyphs, or a transliteration — and it searches a corpus of about 130,000 real
sentences for the rows that most resemble what you typed, then shows you its three best
matches, in order, each with the corpus sentences behind it. It never invents a reading:
every suggestion is a sentence that actually exists in the corpus. When the corpus has
nothing close, it says so. The three suggestions are meant to be read top to bottom, so
which one sits in first place, and which three make the cut, is the whole product.

This round tests one change to the rule that decides that order. On five test strings the
change moves a specific suggestion up or down: in one case it lifts a good match from 6th
place into 1st, and in four cases it pushes a match that was near the top further down —
in two of those, out of the top three altogether. Our automatic scoring can see that the
lists changed, but it cannot tell whether the new 1st suggestion is genuinely a better
reading for the string than the one it displaced, or whether the match we demoted was the
one you would actually have wanted. Only someone who reads this material can. That is the
entire ask: for each of the five, look at the two orderings and say which one you would
rather have been shown. There is no right answer we are checking you against — your
judgement *is* the measurement.

The transliteration follows TLA / Berlin conventions (yod written `ꞽ`, `q` not `ḳ`,
suffix pronouns as separate tokens: `ḏd =f`). Brackets such as `⸢…⸣`, `[…]`, `(…)` and
`⸮…?` are the corpus editors' own — damaged, restored, or uncertain signs — not marks the
tool added.

---

## The five cases

Each card shows: the string as it was typed; the edition transliteration of the sentence
that string was drawn from, with its corpus id; the tool's top three **before** and
**after** the change, side by side; and one question.

---

### Case 1 — COMP_001  *(the change pushes a near-identical sentence off the list)*

- **Typed:** `skhr i khft pl nb sn nb b`
- **Edition sentence:** `r sḫr.n =ꞽ ḫft〈.pl〉 ((nb)) n.w ḥr.w m s.t =sn nb m b(w) nb n.tꞽ-ꞽw =sn ꞽm`
  &nbsp;— source `AES_250EAE634B50` / `S250EAE634B50`

| # | Before (current order) | After (proposed order) |
|---|---|---|
| 1 | **★ `r sḫr.n =ꞽ ḫft.pl nb n.w rꜥw m s.t =sn nb m b(w) nb n.tꞽ-ꞽw =sn ꞽm`** (AES) | `ḏi̯ =ꞽ sḫr nḥḥ ḫft ⸮ꞽb? =ꞽ` (BBAW) |
| 2 | `sḫr =ꞽ ḫftꞽ.w =k nb.pl` (BBAW) | `sḫr ꞽ:ꞽri̯ =ꞽ n =sn` (BBAW) |
| 3 | `ḫft sꞽꜣ =sn ḥm =f m nb =sn` (Ramses) | `ḫft sꞽꜣ =sn ḥm =f m nb =sn` (Ramses) |

**★ moved:** the AES row `r sḫr.n =ꞽ ḫft.pl nb n.w rꜥw …` — which is almost word-for-word
the sentence the string came from — goes from **1st to off the list entirely** (below 8th)
under the change.

> **Question.** The reading the change pushed off the list is nearly the same sentence as
> your string; the new 1st suggestion is `ḏi̯ =ꞽ sḫr nḥḥ ḫft ⸮ꞽb? =ꞽ`. Was the displaced
> reading the more useful one to have shown first?&nbsp;&nbsp;( yes / no )

---

### Case 2 — COMP_007  *(the change lifts a matching parallel from 6th to 1st)*

- **Typed:** `skhak i kh i tt im fkh djd`
- **Edition sentence:** `sẖꜣk =ꞽ ẖ.t =ꞽ ḥr n.tt ꞽm =s m fḫ n ḏd nb ḥr-n.tt r =f wḥm.w ḏdd.t.pl`
  &nbsp;— source `AES_F8FA2864100C` / `SF8FA2864100C`

| # | Before (current order) | After (proposed order) |
|---|---|---|
| 1 | `ꜣḫ =ꞽ ꞽm =f` (BBAW) | **★ `ꞽ:fḫ n =k s(ꞽ) zꜣ =k ḥr(.w) ꜥnḫ =k ꞽm =s`** (TLA) |
| 2 | `n sfḫ =ꞽ ꞽm =f ḏ.t` (BBAW) | `sḫꜣ{t}.n =ꞽ smḫ.tn =ꞽ ꞽm =f` (BBAW) |
| 3 | `sḫm =ꞽ ꞽm =f ḏ.t` (BBAW) | `sḫm =ꞽ ꞽm =f ḏ.t` (BBAW) |

**★ moved:** the TLA row `ꞽ:fḫ n =k s(ꞽ) zꜣ =k …` — the corpus parallel that shares the
string's rarer word (`fḫ`) — goes from **6th to 1st**. This is the one case where the
change is a promotion into the top three.

> **Question.** Is the new 1st suggestion `ꞽ:fḫ n =k s(ꞽ) zꜣ =k …` a reading you would
> consider for this string, and more useful than `ꜣḫ =ꞽ ꞽm =f`, which it
> displaced?&nbsp;&nbsp;( yes / no )

---

### Case 3 — COMP_022  *(the change drops an offering-formula parallel out of the top three)*

- **Typed:** `ini pr khrw in pl i ta mh`
- **Edition sentence:** `ꞽni̯.t pr-ḫrw ꞽn nʾ.t.PL =f n.ꞽ.(w)t tꜣ-mḥ.w m ḥ(ꜣ)b rꜥw-nb n (ꞽ)r(.ꞽ-ꞽ)ḫ.t-nswt nfr-nswt`
  &nbsp;— source `TLA_EARLIER_4778` / `S4778`

| # | Before (current order) | After (proposed order) |
|---|---|---|
| 1 | `ꞽn ꞽnꞽ =ꞽ tꜣ-bꜣk.t` (Ramses) | `ꞽn ꞽnꞽ =ꞽ tꜣ-bꜣk.t` (Ramses) |
| 2 | `ꞽn bn ꞽnꞽ =<ꞽ> =sn r pꜣy.ꞽ pr` (Ramses) | `ꞽn bn ꞽnꞽ =<ꞽ> =sn r pꜣy.ꞽ pr` (Ramses) |
| 3 | **★ `ꞽni̯.⸢t⸣ pr.t-ḫrw ꞽn nʾ.t.pl n.ꞽ.wt`** (BBAW) | `wꜣḥ pr-ḫrw ꞽn wt(.ꞽ)` (BBAW) |

**★ moved:** the offering-formula parallel `ꞽni̯.t pr.t-ḫrw ꞽn nʾ.t.pl n.ꞽ.wt` goes from
**3rd to 7th**, so it leaves the top three; `wꜣḥ pr-ḫrw ꞽn wt(.ꞽ)` takes the 3rd slot in
its place. (The top two, both Ramses rows, are unchanged.)

> **Question.** For this string, does the offering-formula parallel
> `ꞽni̯.t pr.t-ḫrw ꞽn nʾ.t.pl n.ꞽ.wt` belong in the top three, ahead of
> `wꜣḥ pr-ḫrw ꞽn wt(.ꞽ)`?&nbsp;&nbsp;( yes / no )

---

### Case 4 — HOLD_010  *(the change drops the parallel with both royal names from 1st)*

- **Typed:** `pri nmt i za mr raw mn du`
- **Edition sentence:** `pri̯ Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ḥr mn.t.du Ꜣs.t ḥfdi̯.w Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ḥr mn.t[.du] [Nb.t-ḥw(.t)]`
  &nbsp;— source `bbaw_egyptian_2018` / `B081971`

| # | Before (current order) | After (proposed order) |
|---|---|---|
| 1 | **★ `pri̯.n Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ꞽm.wtꞽ mn.t.du psḏ.t.du`** (BBAW) | `pri̯ =ꞽ ẖr smꞽ nm.t nṯr` (BBAW) |
| 2 | `Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw pw ꞽns pri̯ m Ꜣs.t` (BBAW) | `ꞽw zꜣ =ꞽ r ꜥḥꜥ ḥr s.t mn ḥr ns.t n ḏ.t zꜣ-Rꜥw Stẖ.y-mr-n-Ꞽmn` (BBAW) |
| 3 | `pri̯.n nmt.ꞽ-m-zꜣ=f mr.n-rꜥw ꞽr p.t m mnṯ(.w)` (TLA) | `ꞽ wnm znf pri̯ m nm.t nn smꜣ =ꞽ ꜥw.t nṯri̯` (BBAW) |

**★ moved:** the parallel that carries **both royal names** and `mn.t.du`,
`pri̯.n Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ꞽm.wtꞽ mn.t.du psḏ.t.du`, goes from **1st to off the list
entirely** (below 8th). Before the change, all three suggestions named the same two kings;
after it, only the 2nd does.

> **Question.** Was the displaced parallel with both royal names,
> `pri̯.n Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ꞽm.wtꞽ mn.t.du psḏ.t.du`, the more useful reading to have
> shown first, ahead of the new 1st `pri̯ =ꞽ ẖr smꞽ nm.t nṯr`?&nbsp;&nbsp;( yes / no )

---

### Case 5 — HOLD_016  *(the change swaps 1st and 3rd inside the top three)*

- **Typed:** `mtw tm nni mdja mtw dji shn khr`
- **Edition sentence:** `mtw =k tm nni̯ n mḏꜣ.w mtw =k ḏi̯.t [n] =f sḥn ḫr mtw =k ḏd n =f bn r(m)ṯ sḥn m-dꞽ pꜣy =ꞽ ḥr.ꞽ`
  &nbsp;— source `bbaw_egyptian_2018` / `B096559`

| # | Before (current order) | After (proposed order) |
|---|---|---|
| 1 | **★ `ḫ⸢r⸣-mdꞽ tm ḫꜣꜥ nnw mḏꜣ Ksꞽ mtw =k ḏi̯.t n =f dꞽw mtw =k ḏi̯.t sḫt =f nꜣ nw.t.pl`** (BBAW) | `mtw =k ⸢tm⸣ nni̯ [⸮Pꜣ-kꜣmn?] [pꜣy] [=ꞽ] sn` (BBAW) |
| 2 | `mtw =k ⸢tm⸣ nni̯ [⸮Pꜣ-kꜣmn?] [pꜣy] [=ꞽ] sn` (BBAW) | `ḫr m-dꞽ tm nni̯ [ꞽṯꜣ] ⸢mw⸣ r pꜣy =f wbꜣ mtw =k smꜣꜥ n =f šdi̯ =f` (BBAW) |
| 3 | `ḫr m-dꞽ tm nni̯ [ꞽṯꜣ] ⸢mw⸣ r pꜣy =f wbꜣ mtw =k smꜣꜥ n =f šdi̯ =f` (BBAW) | **★ `ḫ⸢r⸣-mdꞽ tm ḫꜣꜥ nnw mḏꜣ Ksꞽ mtw =k ḏi̯.t n =f dꞽw mtw =k ḏi̯.t sḫt =f nꜣ nw.t.pl`** (BBAW) |

**★ moved:** the reading `ḫ⸢r⸣-mdꞽ tm ḫꜣꜥ nnw mḏꜣ Ksꞽ mtw =k ḏi̯.t …` goes from **1st to
3rd**; the reading `mtw =k ⸢tm⸣ nni̯ [⸮Pꜣ-kꜣmn?] [pꜣy] [=ꞽ] sn` rises from 2nd to 1st.
All three suggestions stay in the top three — only their order changes.

> **Question.** For this string, which reading do you prefer at 1st place — the current
> `ḫ⸢r⸣-mdꞽ tm ḫꜣꜥ nnw mḏꜣ Ksꞽ mtw =k ḏi̯.t …`, or the proposed
> `mtw =k ⸢tm⸣ nni̯ [⸮Pꜣ-kꜣmn?] [pꜣy] [=ꞽ] sn`?&nbsp;&nbsp;( current / proposed )

---

## How your answers will be used

These five answers decide exactly one thing: **whether the proposed change to the ordering
rule is adopted or dropped.** The change is a single trade-off — it rescues one good match
(Case 2) at the cost of demoting matches in the other four — and our automatic score
cannot say whether that trade is worth making, because to the score a demoted 1st-place
match and a rescued 3rd-place match look the same. Your reading of the five cases is what
settles it: if the rescue in Case 2 is a genuine improvement and the four demotions are
matches you would not have wanted at the top anyway, the change is worth adopting; if the
demotions cost readings you would have wanted first, it is not.

By design, these five answers are used **only** for that yes/no decision. They will not be
used to adjust any weight, threshold, or constant in the tool — the ordering rule and its
one alternative were both written down and frozen before you saw them, precisely so that
your judgement tests the choice rather than being folded back into re-tuning it. If we
later want to tune the tool further, that will need its own fresh, unseen set of cases, not
these. This is the same pre-registration discipline the project applied when it declined to
"fix" the ranking on the strength of a two-example margin.

## Time

Five cases, one tick or one sentence each. It should take **under 15 minutes**.
