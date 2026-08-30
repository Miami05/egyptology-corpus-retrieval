# Whyptology

A corpus-based reading-suggestion tool for Ancient Egyptian. Given a transliteration,
Manuel de Codage, or a sign sequence, it finds real parallels in a 12,772-sentence
corpus, ranks the readings those parallels attest, shows the evidence behind each one,
and records expert corrections.

**It is not OCR and it is not machine translation.** Every suggestion is grouped from
sentences that actually exist in the corpus, and every one is shown with the evidence
that produced it — shared transliteration tokens, shared lemma IDs, shared context, and
the specific corpus rows it came from. Nothing is generated.

Live app: <https://egyptology-corpus-retrieval.streamlit.app>

## What it does

| Page | Purpose |
|---|---|
| Reading workspace | Enter a reading; get the top 3 suggestions with scores and evidence, plus a sign-by-sign predicted reading with an editable sign grouping |
| Corpus explorer | Search and page through the corpus by reading, translation, text ID or MdC key |
| Sign readings | Which signs are genuinely multivalent, and how the reading model chooses between readings |
| Projects / Reviews | Corpus composition by period, and the record of expert annotations |

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
  benchmarks/  evaluation sets and results
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
  signs without a Unicode codepoint is now one placeholder glyph, so all 12,772
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
| Corpus data under `data/` | **CC BY-SA 4.0** — [DATA-LICENSE.md](DATA-LICENSE.md) |
| `app/ui/static/GentiumPlus-Translit.woff2` | SIL OFL 1.1 — `app/ui/static/GentiumPlus-OFL.txt` |

The corpus is derived from the [Thesaurus Linguae
Aegyptiae](https://thesaurus-linguae-aegyptiae.de) (CC BY-SA 4.0). Share-alike means the
derived data cannot be relicensed as MIT, attribution is required, and the changes made
to it must be stated — all of which is recorded in
[DATA-LICENSE.md](DATA-LICENSE.md). The attribution shown in the app sidebar is a
licence condition, not decoration.
