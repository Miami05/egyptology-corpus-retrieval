# Whyptology

A corpus-based reading-suggestion tool for Ancient Egyptian. Given a transliteration
(Unicode, Manuel de Codage or plain ASCII) or a sign sequence, it finds real parallels
in a 130,472-sentence corpus (TLA Earlier Egyptian, Late Egyptian and Demotic, the AES corpus,
the BBAW 2018 corpus and the Ramses Transliteration Corpus; Predynastic to Roman), ranks the readings those parallels attest, shows the evidence
behind each one, and records expert corrections.

**It is not OCR and it is not machine translation.** Every suggestion is grouped from
sentences that actually exist in the corpus, and every one is shown with the evidence
that produced it — shared transliteration tokens, shared lemma IDs, shared context, and
the specific corpus rows it came from. Nothing is generated.

Live app: <https://vela-optiplex-3070.taile0409f.ts.net/> (self-hosted since 2026-09-04; the earlier Streamlit Community Cloud address is retired)

## What it does

| Page | Purpose |
|---|---|
| Reading workspace | Enter a reading; get the top 3 suggestions with scores and evidence, plus a sign-by-sign predicted reading with an editable sign grouping |
| Corpus explorer | Search and page through the corpus by reading (in any notation), translation or text ID |
| Sign readings | Which signs are genuinely multivalent, and how the reading model chooses between readings |
| Projects / Reviews | Corpus composition by period, and the record of expert annotations |

## The sign-reading lexicon

`data/processed/helsinki_lexicon.csv` (built by `scripts/import_helsinki_lexicon.py`) holds
84,532 hieroglyphic spellings with every transliteration attested for them in the AES and
Ramses corpora, and how often — the University of Helsinki "Transliteration Model" word
lists, CC BY 4.0. 53,457 of those spellings never occur in our corpus, 41,508 of them
Late Egyptian. The reading model consults it **only** for a sign group this corpus does
not attest, after the corpus and before guessing from a similar group; the segmenter
accepts its groups as cut points at singleton weight. Every such reading is labelled
"lexicon N× — no sentence in this corpus" and gets its own badge (◇), because it is an
attested count from elsewhere, not a parallel we can show. The two source files write the
yod differently (AES `y`, Ramses `i`/`j`) and are converted with their own rules — see
DATA-LICENSE.md, which also records the Ramses provenance caveat.

## Typing a query is a form, on purpose

The query box and the search button are one `st.form`. A bare `st.text_area` only
sends its value when it loses focus, so tapping the button blurred the box, committed
the text, triggered a rerun — and the click that caused it was swallowed. Verified in a
browser against the old build: text typed, button tapped *twice*, suggestions still
reading "Run a query…". The front-end smoke suite could not see it, because AppTest
commits a widget value in its own run and never reproduces that race.

Consequences to keep in mind before rearranging the workspace:

- A form takes no ordinary `st.button`, so the character palette keys are
  `st.form_submit_button`s.
- A widget **inside** a form ignores `st.session_state` writes from outside it.
- A callback cannot reliably read a form widget's freshly submitted value. The palette
  therefore *queues* a character and the script body appends it to the submitted text,
  bumping the nonce in the widget's key — a widget only accepts `value=` under a key it
  has not seen before.

## What you can type

The corpus follows **TLA / Berlin conventions** — `ꜣ ꜥ ꞽ ḥ ḫ ẖ š q ṯ ḏ`, yod written
`ꞽ`, `q` rather than `ḳ`, and suffix pronouns as separate tokens (`ḏd =f`). You do not
have to type it that way: `app/data/query.py` reads all four notations below and
reduces them to the one key the corpus is indexed under, then shows you which reading
it understood.

| You type | Notation |
|---|---|
| `ꜥḥꜥ.n stẖ qnd` | Unicode, TLA conventions |
| `aHa.n stX qnd` | Manuel de Codage, as JSesh writes it (`A a i H x X S T D`) |
| `aha.n stkh qnd` | plain ASCII, no special keys |
| `𓊢𓂝𓈖 𓋴𓏏𓅆` | Unicode hieroglyphs (matched on signs, not on text) |

Manuel de Codage is told from plain ASCII by evidence, not by a rule about capital
letters: both readings are folded and whichever yields more tokens the corpus actually
contains wins. The same evidence rule settles the ASCII digraphs: since the yod now
folds to `i` (so `ꞽ`, `j` and `i` are one letter to the search — `ꞽri̯.n`, `irin` and
`jrj.n` all match), `dji` could be ḏi̯ or d + yod + i, and the corpus decides. `.`, `=`
and `⸗` are optional — `ḏd=f`, `ḏd =f` and `ḏdf` all match.

Until 2026-09-01 only the third row worked. The query was cleaned with `normalize_mdc`,
which **deletes** every Egyptological letter rather than folding it, so
`ꜥḥꜥ.n stẖ qnd` reached the search as `n st qnd`; "MdC" named a scheme that was never
implemented; and the index was built from a `mdc` column that all 9,823 AES rows ship
empty, which made 37% of the corpus unreachable by any transliteration query. One
function, `search_fold`, now defines the key on both sides.

The scoring combines exact, fuzzy and TF-IDF retrieval (`app/retrieval/`) with a
sign-level reading model (`app/services/reading_model.py`) fed by a resegmentation
lattice (`app/services/segmentation.py`) that treats pasted spaces as hints.

## Layout

```
app/
  api/         FastAPI search endpoint (NOT deployed — local use only)
  core/        settings from environment
  data/        CSV loader, normaliser, schema
  retrieval/   exact / fuzzy / tf-idf matching, scorer, evidence
  services/    retrieval, suggestions, reading model, signs, annotations, evaluation
  storage/     SQLAlchemy models, repositories, bootstrap
  ui/          Streamlit front ends (whyptology_app.py is the deployed one)
data/
  processed/   examples.csv — the built corpus (committed)
  raw/         downloaded sources (gitignored, ~465MB, regenerable)
  benchmarks/  evaluation sets and results (see CORPUS_SCALING_REPORT.md §17 for
               which numbers are quotable — v2/v3 were retired on 2026-09-01; v4 is
               cut on the final corpus)
scripts/       importers, corpus builders, benchmark and evaluation runners
```

The database is **not** committed. `app/storage/bootstrap.py` creates the schema and
seeds it from `data/processed/examples.csv` on first boot, which is what gives each row
the stable id annotations attach to. It only seeds when the corpus table is empty — that
guard is what stops a redeploy from overwriting live annotations.

## Running it

```bash
python3.12 -m venv ~/venvs/egyptology          # 3.12: the pins have no 3.14 wheels
~/venvs/egyptology/bin/pip install -r requirements.txt
~/venvs/egyptology/bin/python -m streamlit run app/ui/whyptology_app.py
```

Keep the virtualenv **outside** the project directory if the project lives under an
iCloud-synced folder — iCloud evicts package file contents, which breaks pandas and
scikit-learn in ways that look like dependency bugs.

Tests: `pytest tests/ -q`

Evaluation:

```bash
python scripts/run_expert_paste_eval.py          # real hieroglyph pastes, exits non-zero on regression
python scripts/run_competitive_ambiguity_eval.py \
  --benchmark data/benchmarks/competitive_ambiguity_eval_queries_v4.csv
python scripts/verify_release.py   # tests + both evaluations, one summary, non-zero on failure
```

The competitive benchmark is the reportable one: its rows are guaranteed to have no
near-identical twin anywhere in the corpus, so excluding the target does not hand the
answer back. **v2 and v3 were retired on 2026-09-01** — the search fold changed (yod now
folds to `i`) and the searchable corpus changed twice the same day — so their numbers
no longer describe this tool; see `data/benchmarks/CORPUS_SCALING_REPORT.md` §17. v4 was
cut on the 78,412-row corpus, where it scores 0.95 top-3 useful. Since Ramses and Demotic
joined (2026-09-04, 130,472 rows) the evaluations run in the app's default *Auto* language-
stage mode (`--stage auto`; `none` and `declared` are also available): expert paste 8/8, v4
0.90 top-3 useful / MRR 0.80 (declared: MRR 0.875). The two v4 misses are one pre-existing
(COMP_007) and one whose useful parallels are Late Egyptian formula rows that a stage
restriction sets aside (COMP_014); neither number was tuned. Every evaluation writes to a
temporary path when run through
`verify_release.py` or the test suite, so a release check never dirties `data/benchmarks`.

Annotation saving can be limited to reviewers by setting `reviewer_key` in Streamlit
secrets (or the `REVIEWER_KEY` environment variable). With no key set the app is
fully open, which is the default for local use. If the database is unreachable the
app drops to read-only: searching, sign-by-sign readings and the corpus explorer keep
working, and a banner explains that annotations are unavailable.

## Known limitations

An external expert trial (Urk. IV 1, August 2026) exposed the current weak points —
each is understood and scheduled in [ROADMAP.md](ROADMAP.md):

- ~~Sign groups are split on whitespace~~ — fixed (Phase 1): the paste's spaces are
  now hints. A lattice regroups the signs against the corpus's attested groups
  (boundary F1 0.86 on held-out sentences vs 0.67 for trusting the spaces), shows
  where it disagreed with the paste, and lets you edit the grouping.
- ~~`<g>…</g>` markup breaks glyph/reading alignment~~ — fixed (Phase 0): markup for
  signs without a Unicode codepoint is now one placeholder glyph, so all 26,196
  rows are aligned and used; the loader reports the count on every start.
- ~~No Unicode variant folding~~ — fixed (Phase 0): text is NFC-normalised and the
  plural-strokes variants U+133E5/U+133FC fold together. Other visually identical
  pairs can be added to `SIGN_VARIANTS` in `app/data/normalizer.py` as they are found.

See [DEPLOYMENT.md](DEPLOYMENT.md) for hosting, the database step that makes annotations
persist, the transliteration font, and the responsive-testing gotcha.

## Licences — read before publishing

This repository is **not** under a single licence.

| What | Licence |
|---|---|
| Source code | MIT — [LICENSE](LICENSE) |
| Corpus data under `data/` | **CC BY-SA 4.0**, with one exception — see below and [DATA-LICENSE.md](DATA-LICENSE.md) |
| `app/ui/static/GentiumPlus-Translit.woff2` | SIL OFL 1.1 — `app/ui/static/GentiumPlus-OFL.txt` |

The corpus is derived from raw-data publications of the [Thesaurus Linguae
Aegyptiae](https://aaew.bbaw.de/daten-veroeffentlichungen) (TLA) project, each released
under CC BY-SA 4.0. **The TLA *website* itself is not under a CC licence** — it permits
only copying individual data sets "for academic research purposes, but not entire
sub-corpora or larger sets" (see
[its licences page](https://thesaurus-linguae-aegyptiae.de/info/licenses)); CC BY-SA 4.0
attaches to the separately published datasets this project actually uses, not to the
web app. Share-alike means the derived data cannot be relicensed as MIT, attribution is
required, and the changes made to it must be stated — all of which is recorded in
[DATA-LICENSE.md](DATA-LICENSE.md). The attribution shown in the app sidebar **and in
the footer of every page** is a licence condition, not decoration, and every CSV the
app or `scripts/export_reviewed.py` writes carries a `licence` column so the notice
travels with the data.

`data/` is **not uniformly** CC BY-SA 4.0: `data/processed/helsinki_lexicon.csv` is
built from CC BY 4.0 material and is wrapped in CC BY-SA 4.0 here (which CC BY 4.0
permits), but its own upstream attribution and licence link still travel with it — see
DATA-LICENSE.md for the exact terms.
