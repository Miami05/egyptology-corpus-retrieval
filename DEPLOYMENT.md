# Deployment

Live app: <https://vela-optiplex-3070.taile0409f.ts.net/>
Host: a Dell OptiPlex 3070 (Ubuntu 24.04, 4 cores, 23 GB RAM) owned by a friend, reached
over Tailscale; our copy runs under the Linux user `ledio` and nothing outside
`/home/ledio` is ours to touch. **Streamlit Community Cloud was retired on 2026-09-04**:
the corpus grew to 130,472 rows that day and no longer fits its 1 GB. Whatever still
answers at the old `streamlit.app` address is unmaintained.

## Layout on the server

| Path | What |
|---|---|
| `/home/ledio/egyptology` | clone of `main`; the app runs from here |
| `/home/ledio/venvs/egyptology` | Python 3.12 virtualenv (≈ 760 MB) |
| `/home/ledio/egyptology-private` | `PRIVATE_DATA_DIR`: non-redistributed CC BY-NC-SA rows (St Andrews). Outside the clone so `git pull` never touches it. Copy files in with `scp`. |
| `/home/ledio/egyptology-backups` | destination for database dumps (job still to be written, see below) |
| `/home/ledio/egyptology.env` | secrets and per-host settings, `chmod 600`, read by the service |
| `/home/ledio/egyptology-deploy.sh` | the one-command update |
| `~/.config/systemd/user/egyptology.service` | the service: Streamlit on `127.0.0.1:8502`, headless, `Restart=on-failure`, enabled; `loginctl enable-linger ledio` keeps it running with nobody logged in |
| `/home/ledio/egyptology/egyptology.db` | the SQLite database: corpus ids and **all annotations**. The only irreplaceable file. |

Public access: `tailscaled` terminates TLS and proxies `/` to `127.0.0.1:8502`
(`tailscale serve`), and Funnel publishes it to the internet. Both were set by the machine
owner or by Ledio with sudo; `ledio` has no sudo.

## Deploying a change

```bash
git push origin main
ssh ledio@vela-optiplex-3070 ./egyptology-deploy.sh
```

The script does `git pull --ff-only`, `pip install -r requirements.txt`, restarts the
service and waits for `/_stcore/health`; it prints the commit it is serving. If it prints
the last 30 log lines instead, the app did not come up — read them. Useful afterwards:

```bash
ssh ledio@vela-optiplex-3070 'systemctl --user status egyptology.service; journalctl --user -u egyptology.service -n 50 --no-pager'
```

Verify behaviour on the live URL after any push that touches `app/`; a healthy port proves
only that Streamlit answers.

## Settings (`/home/ledio/egyptology.env`, or Streamlit secrets on any other host)

Every knob is read by `configured_setting()` in `whyptology_app.py`: Streamlit secrets
first, then the environment. Set per host, never in code.

| Variable | Server value | Meaning |
|---|---|---|
| `ANNOTATIONS_DURABLE` | `1` (in the unit) | SQLite on a real disk persists; turns off the "not stored durably" warning and the read-only gating |
| `PRIVATE_DATA_DIR` | `/home/ledio/egyptology-private` (in the unit) | where NC rows are read from; empty dir = none |
| `REVIEWER_KEY` | set by Ledio | passphrase that unlocks annotation saving; unset = anyone may save |
| `DATABASE_URL` | unset | unset = SQLite next to the code; a `postgres://` URL switches engines with no code change |
| `DEFAULT_STAGE` | unset (= `auto`) | `auto` / `all` / a stage name; Auto builds one extra resource set per stage it uses |
| `CORPUS_SOURCES_EXCLUDE` | unset | comma-separated `source` values to drop at load — how a 1 GB host would stay on the 78k subset |
| `MOVED_TO_URL` | unset | renders the "this app has moved" banner on a superseded deployment |

## What the service needs, measured 2026-09-04

130,472 rows load in 9 s; pooled resources build in ~30 s on this CPU; the first
hieroglyph paste in Auto mode builds the three stage resource sets (~60 s cold) and then
everything is cached; peak RSS with all sets ≈ 1.9 GB. A transliteration query is ~1 s on
this corpus (the fuzzy loop; rapidfuzz batch call pending). Follow-up: warm the stage sets
at startup so the first visitor does not wait.

## Annotations and backups

Annotations live in `egyptology.db`. The corpus table is regenerable from the CSV
(`ensure_corpus_ready` seeds an empty table on first boot and never re-imports over live
annotations — do not remove that guard); the annotations table is not. **Still to do:** a
nightly copy of `egyptology.db` into `egyptology-backups/` and from there off the machine,
30-day retention, and one restore test before any expert records corrections. Until then
the database is as safe as one disk. `scripts/export_reviewed.py` writes the reviewed
annotations to CSV and is the manual fallback.

New corpus rows get ids at boot via the empty-table guard only on a fresh database; on an
existing one run `scripts/import_examples.py` after a corpus change so the new rows are
linked (the deploy script does not do this yet).

## What needs sudo (the owner, or Ledio with the password)

Anything outside `/home/ledio`: `tailscale serve` / `funnel` changes, new ports, system
packages, adding `ledio` to `docker` (not asked for — root-equivalent on a box that runs
Vaultwarden and Nextcloud). Everything else is `ledio`'s.

## How the code handles databases

- `app/storage/db.py` rewrites `postgres://` to `postgresql+psycopg://`, enables
  `pool_pre_ping`, and sets a 10 s connect timeout so a dead endpoint degrades to
  read-only instead of freezing the app.
- `app/storage/bootstrap.py` seeds in bulk only when the corpus table is empty;
  `sync_new_examples` adds rows a grown corpus is missing without touching existing ids.
- `app/ui/review_common.attach_db_ids` builds the id map from a four-column select — the
  full-row download it replaced is what exhausted the Neon free tier's transfer quota in
  August 2026 (`tests/test_storage_seeding.py` guards against it coming back).
- Private rows are concatenated only after the database step and never get an id.

## History

- **Streamlit Community Cloud** (2026-07-28 → 2026-09-04) served `main` from GitHub with
  the Neon Postgres below; a push re-executed the main script but not `app/` modules, so
  every code change needed *Manage app → Reboot*. Retired when the corpus outgrew 1 GB.
- **Neon** (free tier, US East) held the annotations for the Cloud deployment. Its monthly
  egress quota was exhausted twice in August by the boot-time full-row download, and the
  `neondb_owner` password was pasted into a chat on 2026-08-30. The server does not use
  Neon; export anything still there with `scripts/export_reviewed.py` before closing the
  project, and rotate or delete the role.
- **Hugging Face Spaces** was evaluated (2026-09-01/02) and dropped: Docker Spaces require
  a PRO account since July 2026, and the server made the question moot.

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
