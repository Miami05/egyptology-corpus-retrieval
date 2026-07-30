# Deployment

Live app: <https://egyptology-corpus-retrieval.streamlit.app>
Host: Streamlit Community Cloud, from `main` of `Miami05/egyptology-corpus-retrieval`.

## Settings that matter

| Setting | Value | Why |
|---|---|---|
| Main file path | `app/ui/whyptology_app.py` | Not `app/api/main.py` — that is the FastAPI service and is **not** deployed. |
| Python version | **3.12** | `numpy==2.3.2` and `pyarrow==21.0.0` have no wheels for 3.14. Set under *Advanced settings*. |
| Secrets | TOML, see below | Streamlit also exports top-level secrets as environment variables, which is why `os.getenv` in `app/core/config.py` works unchanged. |

```toml
APP_NAME = "Whyptology"
TOP_K = 3
```

## Making annotations survive (required for real review work)

**Without this step, every annotation is lost when the app sleeps or redeploys.**
Streamlit Cloud containers have no persistent disk, so the SQLite file is temporary.
The corpus itself is fine — it re-seeds from the committed CSV on boot — but expert
annotations are irreplaceable, and they are what the Reviews workflow exists to record.

The code is already Postgres-ready. It needs one thing: a database URL.

1. Create a free Postgres database. [Neon](https://neon.tech) has a free tier that
   suits this (project → get the connection string). Supabase or Render work too.
   *You have to do this step — it needs an account, and account creation is yours.*
   When creating the Neon project: pick a **US East** region. The latency that matters
   is app-to-database, and the app runs on Streamlit Cloud in the US — choosing an EU
   region because you are in Europe adds a transatlantic hop to every query and helps
   nobody. Leave Neon Auth off; this app does not use it.
2. Copy the connection string. Prefer the **direct** endpoint over the pooled one —
   the `-pooler` host runs PgBouncer in transaction mode, and the app keeps its own
   small SQLAlchemy pool so it gains nothing from Neon's:

   ```
   ep-xxx-123456.us-east-2.aws.neon.tech          <- direct, prefer this
   ep-xxx-123456-pooler.us-east-2.aws.neon.tech   <- pooled
   ```

   Either will work: `db.py` sets `prepare_threshold=None`, which disables psycopg's
   automatic prepared statements. Under a transaction-mode pooler those statement
   names collide or disappear between statements, causing intermittent "prepared
   statement already exists" failures that only appear under load.
3. In Streamlit Cloud: **Manage app → Settings → Secrets**, add the line below and
   save. Paste the string exactly as the provider gave it — `postgres://` is handled.

   ```toml
   DATABASE_URL = "postgres://user:password@host/dbname?sslmode=require"
   ```
4. The app restarts, creates its tables, and bulk-seeds the 12,772 corpus rows on
   first boot (about a second against a warm database). Annotations then persist
   across sleeps and redeploys.

Keep `DATABASE_URL` out of the repo. `.env` is gitignored; production reads it from
the Secrets box only.

### Verifying it worked

Save an annotation via the workspace, then *Manage app → Reboot*. If it is still
listed under **Reviews** afterwards, persistence is live.

**Wait for the secret to propagate before testing.** Streamlit says changes take about
a minute, and it is not a formality: testing too early writes the annotation into the
still-running SQLite container, the reboot then discards it, and the result looks
exactly like a failed Postgres setup when nothing is wrong. Confirmed this way once —
the annotation "vanished" purely because it had never reached Postgres.

A quick way to tell which engine actually served a saved annotation: look at the
timestamp on the review card. Postgres `timestamptz` renders with an offset
(`20:10:11.598071+00:00`); SQLite has none (`20:01:10.391991`).

### How the code handles it

- `app/storage/db.py` rewrites `postgres://` to `postgresql+psycopg://` (SQLAlchemy
  rejects the bare `postgres` dialect name — this is the single most common cause of a
  baffling crash on first deploy), and enables `pool_pre_ping` because hosted Postgres
  suspends idle connections.
- `app/storage/bootstrap.py` seeds in bulk when, and only when, the corpus table is
  empty. The empty-table guard is what stops a redeploy from re-importing over live
  annotations — do not remove it.
- Nothing changes for local development: with no `DATABASE_URL`, it stays on SQLite.

## Local development

The virtualenv lives **outside** the project on purpose — `~/Desktop` is
iCloud-synced, and iCloud evicts package files, which breaks pandas and sklearn in
ways that look like dependency bugs.

```bash
egy         # activate ~/venvs/egyptology + cd here (defined in ~/.zshrc)
egy-test    # pytest tests/ -q
egy-run     # streamlit run app/ui/whyptology_app.py
```

To rebuild the environment, use 3.12 explicitly:

```bash
python3.12 -m venv ~/venvs/egyptology
~/venvs/egyptology/bin/pip install -r requirements.txt watchdog
```

### The transliteration font

Egyptological characters — the yod `ꞽ` (U+A7BD) and the combining marks under `ḏi̯` —
have no glyph in Georgia or Streamlit's Source Sans, and Georgia maps U+A7BD to a
*blank* glyph, which counts as "present" and stops the browser falling back. So the
font has to be first in the stack, not a fallback.

`app/ui/static/GentiumPlus-Translit.woff2` is Gentium Plus (SIL OFL) subset to the 88
characters the corpus transliterations actually use — 8.4KB. It is **embedded as a
base64 data URI** by `translit_font_face()` in `whyptology_app.py`, not served as a
static file. Serving it failed in production: Streamlit Cloud puts an auth redirect in
front of `/app/static/` for private apps, so the request returned an HTML login page
with HTTP 200 and the font silently fell back to boxes while working on localhost.

To rebuild it after the corpus gains new characters:

```bash
# 1. Collect the characters the corpus actually uses
python - <<'PY'
import pandas as pd
df = pd.read_csv('data/processed/examples.csv', low_memory=False)
cols = ['transliteration_gold','transliteration_norm','alt_transliterations',
        'sign_sequence','display_sequence','normalized_reading_order']
chars = {c for col in cols if col in df.columns
         for v in df[col].dropna().astype(str) for c in v
         if ord(c) >= 0x20 and not 0x13000 <= ord(c) <= 0x143FF}
open('/tmp/translit_chars.txt','w').write(''.join(sorted(chars)))
PY

# 2. Subset. --layout-features must keep mark/mkmk or diacritics stop being
#    positioned under their base letter, which is the whole point.
pyftsubset /path/to/GentiumPlus-Regular.ttf \
  --output-file=app/ui/static/GentiumPlus-Translit.woff2 --flavor=woff2 \
  --text-file=/tmp/translit_chars.txt \
  --layout-features+=ccmp,mark,mkmk,kern --no-hinting --desubroutinize
```

Full font from <https://software.sil.org/gentium/>. Keep `GentiumPlus-OFL.txt`
alongside it — the licence requires it.

#### The two font faces, and the check to run after rebuilding

`translit_font_face()` emits **two** `@font-face` rules from that one file:

| Family | unicode-range | Used for |
|---|---|---|
| `EgyptologicalText` | none (everything) | transliteration only — a base letter and its combining mark must come from one font or the cluster splits |
| `EgyptologicalLatin` | four codepoints | goes in front of the UI sans, so ꜣ ꜥ ꞽ ʾ survive in text Streamlit renders itself |

`EgyptologicalLatin` used to be a version-pinned subset from `fonts.gstatic.com`. That
URL stopped carrying the yod, and because **a `unicode-range` is a claim, not a
request**, the browser did not fall back — it drew the empty box from the font that had
promised the character. Every string Streamlit renders itself (expander labels,
captions, `st.markdown`) showed `⯑` for ꞽ, while hand-written HTML that names a font was
fine, so a reading rendered perfectly with a box in the evidence line right beneath it.
Both faces now come from the file in this repo. Do not repoint either at a CDN.

After rebuilding the subset, re-run this — it prints what the file actually covers, and
`RANGE_LIMITED_CODEPOINTS` must not name anything missing from the first list:

```bash
~/venvs/egyptology/bin/python - <<'PY'
from fontTools.ttLib import TTFont
cps = set()
for t in TTFont('app/ui/static/GentiumPlus-Translit.woff2')['cmap'].tables:
    cps |= set(t.cmap.keys())
for lo, hi, label in [(0xA720, 0xA7FF, 'Latin Ext-D'), (0x02B0, 0x02FF, 'modifiers'),
                      (0x0300, 0x036F, 'combining marks')]:
    got = sorted(c for c in cps if lo <= c <= hi)
    print(label, ':', ' '.join(f'U+{c:04X}({chr(c)})' for c in got) or 'none')
PY
```

The range-limited face is only safe because none of those four characters ever carries a
combining mark in the corpus — if one did, its base would come from one font and its
mark from another, which is the bug that started all of this. Re-check with:

```bash
~/venvs/egyptology/bin/python - <<'PY'
import pandas as pd, unicodedata
df = pd.read_csv('data/processed/examples.csv', low_memory=False)
targets = {0xA723, 0xA725, 0xA7BD, 0x02BE}
cols = [c for c in ['transliteration_gold', 'transliteration_norm', 'alt_transliterations',
                    'normalized_reading_order', 'display_sequence'] if c in df.columns]
bad = [(v, i) for c in cols for v in df[c].dropna().astype(str)
       for i, ch in enumerate(v[:-1])
       if ord(ch) in targets and unicodedata.combining(v[i + 1])]
print(f'{len(bad)} clusters — must be 0, else give that element EgyptologicalText')
PY
```

**A note on `st.dataframe`:** it renders on a canvas via glide-data-grid and ignores
CSS `font-family`, so Egyptological characters always box there. That is why the corpus
explorer table is hand-rendered HTML with pagination instead of a dataframe.

### Testing responsive layout

Streamlit stores the sidebar open/closed state in **browser storage**, and that
overrides `initial_sidebar_state`. Testing on an origin where you have already toggled
the sidebar will mislead you. Use a fresh origin — `127.0.0.1:8501` rather than
`localhost:8501` — or clear site data first.

## Licensing — the repo and the app are both public

Checked 2026-07-30: the GitHub repo is **public**, and *Settings → Sharing* is set to
**"This app is public and searchable"** — so the app needs no viewer invitation, and it
can be indexed by search engines and listed in Streamlit's Explore gallery.

That makes `DATA-LICENSE.md` binding rather than advisory. The corpus is CC BY-SA 4.0
(share-alike) and cannot be redistributed under the MIT licence that covers the code.
The conditions that publication triggers are met, and each one has to stay met:

- **Attribution** — rendered in the app sidebar on every page, and not decorative: it is
  a licence condition. Do not remove it.
- **State the changes** — the same credit says "normalised, re-segmented and extended
  with derived fields", with the detail in `DATA-LICENSE.md`.
- **No relicensing** — `LICENSE` covers code only; `data/` stays CC BY-SA. Keep the
  split that `README.md` documents.

Before turning sharing back to private, note that the font workaround in this file
depends on it: Streamlit Cloud gates `/app/static/` behind the auth redirect for private
apps, which is why the font is embedded rather than served.
