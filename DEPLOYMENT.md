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

**A push does not reliably reload imported modules.** Observed 2026-07-30: after
pushing a commit that changed both `whyptology_app.py` and `app/retrieval/scorer.py`,
the live app showed the new sidebar labels but ranked with the old scorer — the main
script is re-executed per rerun, while `app/` modules stay cached in the running
process from `sys.modules`. It looks exactly like "my fix didn't work". After any
push that touches code under `app/`, hit *Manage app → Reboot* and then verify the
changed behaviour on the live app, not just that the deploy "went through".

## Making annotations survive (required for real review work)

**Status on 2026-09-01: the live app does NOT keep annotations.** Its `DATABASE_URL`
secret points at `sqlite:///egyptology.db`, a file inside the Streamlit Cloud container.
That container is recreated on every reboot and every redeploy (one happened today), so
an expert's correction is accepted, shown as saved, and gone at the next restart. The
app now says so in a banner and disables saving while this is true; the banner goes away
the moment the steps below are done. Check at any time with:

```bash
~/venvs/egyptology/bin/python scripts/check_database.py   # exit 0 durable, 1 ephemeral, 2 unreachable
```

### What went wrong with Neon, so it does not happen again

The intended store is a Neon free-tier Postgres (US East). It exceeded its **monthly
data-transfer (egress) quota** on 2026-08-20 and again on 2026-08-30, after which Neon
refuses every connection with `You have exceeded the data transfer quota`. The cause was
one query: `attach_db_ids` used to download *every column of every corpus row* on each
boot just to build a three-column → id map. That is fixed — `ExampleRepo.list_example_keys`
selects four columns and a regression test (`tests/test_storage_seeding.py`) fails if a
boot-time path ever pulls full rows again. The one remaining full-table read is in
`scripts/migrate_example_ids.py`, a hand-run maintenance script, not the app.

The quota resets with Neon's monthly billing cycle. With the fix in place, normal use is
tiny: a boot reads ~55k × 4 short columns (a few MB), and every other query is per row.

**The `neondb_owner` password was pasted into a chat transcript on 2026-08-30. Rotate it
before reusing the project** — step 1 below.

### Steps — only the account owner can do these

1. **Rotate the password.** Neon console → project → *Roles* → `neondb_owner` → *Reset
   password*. Copy the new connection string it shows. Nothing in the repo needs to
   change; the secret lives only in Streamlit.
2. **Confirm the quota has reset.** Neon console → *Usage* → data transfer. If it is
   still over, wait for the cycle date or use an alternative (below). From a laptop:
   `DATABASE_URL="postgres://…" ~/venvs/egyptology/bin/python scripts/check_database.py`
   must print `reachable: yes`.
3. **Set the secret.** Streamlit Cloud → *Manage app* → *Settings* → *Secrets*:

   ```toml
   DATABASE_URL = "postgres://neondb_owner:NEW_PASSWORD@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require"
   ```

   Prefer the **direct** endpoint over `-pooler` (the app keeps its own small pool;
   `db.py` disables prepared statements so either works). Paste `postgres://` as given —
   it is rewritten to the SQLAlchemy dialect on load.
4. **Reboot** (*Manage app* → ⋮ → *Reboot app*). Wait the ~1 minute Streamlit needs for
   a secret to propagate *before* testing — an annotation saved too early lands in the
   still-running SQLite container and vanishes on reboot, which looks exactly like a
   broken Postgres setup when nothing is wrong.
5. **First boot seeds the corpus.** `ensure_corpus_ready` finds an empty `examples`
   table and bulk-inserts every row in one transaction, 2,000 rows per statement. On
   local SQLite the 26,196-row corpus seeds in **1.7 s**; the ~55k-row corpus after the
   BBAW import is a few seconds. Against Neon expect **tens of seconds, under a minute**
   — roughly 28 statements plus one commit, dominated by the transatlantic round trips.
   The first page load will spin for that long, once. The seed is atomic on purpose: a
   half-seeded table would satisfy the empty-table guard forever and silently leave rows
   missing.
6. **Verify.** Save an annotation in the workspace, *Reboot*, and check it is still
   listed under **Reviews**. Or run `scripts/check_database.py` with the production URL
   from a laptop: `verdict : DURABLE` and a non-zero `annotations` count.

A quick way to tell which engine served a saved annotation: the review-card timestamp.
Postgres `timestamptz` renders with an offset (`20:10:11.598071+00:00`); SQLite has none.

### If Neon stays over quota

Any hosted Postgres works — the code only needs a URL. The thing to check on a free tier
is the **egress** allowance, because that, not storage, is what this app consumed:

- **Supabase** (free): 500 MB storage, ~5 GB egress/month, US East available. Use the
  *Session* pooler URL or the direct one; `db.py` handles both. The `postgres://` string
  pastes straight in.
- **Neon paid Launch tier**: removes the egress cap; the cheapest fix if you want to keep
  the existing project and its region.
- **Turso / libSQL**: a hosted SQLite; would need the `sqlalchemy-libsql` dialect and has
  not been tried here — listed only so it is not re-researched from scratch.

Whatever the provider: it must be **US East**, because the app runs on Streamlit Cloud in
the US and every query is app→database. Picking Europe because you are in Europe adds a
transatlantic hop to each of them.

### How the code handles it

- `app/storage/db.py` rewrites `postgres://` to `postgresql+psycopg://` (SQLAlchemy
  rejects the bare `postgres` dialect name — the single most common cause of a baffling
  first-deploy crash), enables `pool_pre_ping` because hosted Postgres suspends idle
  connections, and sets a 10 s connect timeout so a dead endpoint degrades to read-only
  instead of freezing the app.
- `app/storage/bootstrap.py` seeds in bulk when, and only when, the corpus table is
  empty. The empty-table guard stops a redeploy from re-importing over live annotations
  — do not remove it. `sync_new_examples` adds rows a grown corpus is missing without
  touching existing ids.
- `app/ui/review_common.attach_db_ids` builds the id map from the four-column select.
- Nothing changes for local development: with no `DATABASE_URL`, it stays on SQLite.

Keep `DATABASE_URL` out of the repo. `.env` is gitignored; production reads it from the
Secrets box only.

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
