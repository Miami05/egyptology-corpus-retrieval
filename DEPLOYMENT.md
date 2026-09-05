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
| `/home/ledio/egyptology-backups` | nightly `egyptology-YYYY-MM-DD.db.gz` snapshots, 30-day retention. Written by the timer below |
| `/home/ledio/egyptology.env` | secrets and per-host settings, `chmod 600`, read by the service |
| `/home/ledio/egyptology-deploy.sh` | the one-command update |
| `/home/ledio/bin` | operational copies of `scripts/backup_db.sh` and `scripts/warm_streamlit.py`, refreshed from the clone by the deploy script. Outside the clone so a systemd unit never points into a tree a pull is rewriting |
| `~/.config/systemd/user/egyptology.service` | the service: Streamlit on `127.0.0.1:8502`, headless, `Restart=on-failure`, enabled; `loginctl enable-linger ledio` keeps it running with nobody logged in |
| `~/.config/systemd/user/egyptology-backup.{service,timer}` | the nightly backup, 03:30 with `Persistent=true` and up to 5 min of jitter |
| `/home/ledio/egyptology/egyptology.db` | the SQLite database: corpus ids and **all annotations**. The only irreplaceable file. |

Public access: `tailscaled` terminates TLS and proxies `/` to `127.0.0.1:8502`
(`tailscale serve`), and Funnel publishes it to the internet. Both were set by the machine
owner or by Ledio with sudo; `ledio` has no sudo.

## Deploying a change

```bash
git push origin main
ssh ledio@vela-optiplex-3070 ./egyptology-deploy.sh
```

The script does `git pull --ff-only`, `pip install -r requirements.txt`, refreshes
`/home/ledio/bin` from `scripts/`, imports the corpus **if the pull changed
`data/processed/examples.csv`** (see below), restarts the service and waits for
`/_stcore/health`; it prints the commit it is serving and one line per step saying what it
did. If it prints the last 30 log lines instead, the app did not come up — read them.

**It takes about three minutes**, nearly all of it the restart: the unit's `ExecStartPost`
warms the stage resource sets before systemd calls the service started, so a deploy that
returns is serving a warm app. Measured no-op deploy 2026-09-05: 2 m 55 s total, health in
2 s once the restart returned. A corpus import adds ~25 s.

Useful afterwards:

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
| `WARM_STAGE_RESOURCES` | `1` (in the unit) | build every stage's resources on the first script run instead of leaving them to the first visitor. Holds all of `STAGES` resident — measured peak RSS 3.0 GB — so only a host with the memory sets it |

## What the service needs, measured 2026-09-04, warm-up added 2026-09-05

130,472 rows load in 9 s; pooled resources build in ~30 s on this CPU; the first
hieroglyph paste in Auto mode builds the three stage resource sets (~60 s cold) and then
everything is cached. Peak RSS with all four sets resident: **3.0 GB**, of 23 GB — the
1.9 GB first written here was an estimate and is low.

Query latency, **measured on the developer's Mac, 2026-09-05** (ROADMAP item 3 — the
server's slower CPU has not been re-measured since, so scale, do not copy): a warm
transliteration query in Auto mode, end to end through the app's own path (stage
resolution, both retrieval passes, suggestions) went from **2.92 s to 0.42 s** median CPU
time on the 130,472-row corpus, and a warm hieroglyph paste from 1.50 s to 0.19 s. The
work that moved is corpus-side and query-independent — per-row token sets, IDF weights and
the sign-group encoding are now built once per resource set (`app/retrieval/tokens.py`)
instead of per query, and the fuzzy signal is one batched `rapidfuzz.process.cdist` call
instead of 130,472 scalar ones. Build cost for all four stage sets rose 0.6 s in total
(they share the token structures, which are a function of the pooled frame alone) and
resident memory **+60 MB** across the four sets. Scores are bit-identical in 8 of 10
signal columns; the two IDF columns differ by at most one double-precision rounding step
(summation order), which never changes any top-1000 ordering. Note the FastAPI endpoint
in `app/api/main.py` calls `retrieve_top_k` without a `SearchIndex` and so still takes the
slow scalar path (~3 s); only the Streamlit path is fast.

### Warming that cold build

The visitor no longer pays it. Measured on the box 2026-09-05:

| | before | after |
|---|---|---|
| first hieroglyph paste after a restart | ~60 s (the build) | **5.3 s** |
| page load, no search | — | 1.9 s |
| the cold build itself | on the visitor's first paste | 165 s inside `ExecStartPost`, before systemd calls the service started |

5.3 s misses the ½-day plan's "< 5 s" gate by 0.3 s. The remainder is not the warm-up:
a declared-stage query and an "All (no stage)" query cost the same 5.7–6.1 s as Auto, so
stage inference is not what is left — the fuzzy scoring loop is, which is exactly what the
rapidfuzz `process.cdist` item targets. Re-measure after it lands.

**How it works, and why it is not an `ExecStartPost` that imports the builders.** Every
expensive object lives in `st.cache_resource`, a cache *inside the running Streamlit
process*. A helper process that called the same builders would fill its own cache and exit,
warming the OS page cache and nothing else. Streamlit also has no HTTP route that runs the
script — `/_stcore/health` answers from the web layer and `GET /` serves the static bundle;
a session, and so a script run, begins only when a client opens the `/_stcore/stream`
websocket. So the unit runs `scripts/warm_streamlit.py`, which is that client: `tornado`
(already a Streamlit dependency) plus Streamlit's own protobufs, no new package. It opens
one session and asks for a rerun carrying `?q=` — the app's shareable-search link — so the
run performs a real paste over the same code a visitor runs. Its `--query` is expert paste
query 1 (`PASTE_001`), and it is also the way the numbers above were taken:

```bash
ssh ledio@vela-optiplex-3070 \
  '/home/ledio/venvs/egyptology/bin/python /home/ledio/bin/warm_streamlit.py \
     --url http://127.0.0.1:8502 --query "𓆓𓂧 𓆑𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏼 𓂋𓍿 𓀀 𓏼𓎟𓏏"'
# warm-up: script finished (FINISHED_SUCCESSFULLY) in 5.3s
```

`WARM_STAGE_RESOURCES=1` is the second half and does not depend on the `?q=` link staying:
`warm_stage_resources()` in `whyptology_app.py` builds `None` plus each of `STAGES`
explicitly on every script run — free after the first, since those are cache lookups. It
still needs a session to run in, which is what the warm-up client provides.

Two guards on the unit, both deliberate: `ExecStartPost=-…` (leading dash) so a warm-up
that fails never marks the app failed, and `TimeoutStartSec=600`, because systemd's default
90 s is shorter than the load plus the build and would kill a healthy service mid-warm.

## Annotations and backups

Annotations live in `egyptology.db`. The corpus table is regenerable from the CSV
(`ensure_corpus_ready` seeds an empty table on first boot and never re-imports over live
annotations — do not remove that guard); the annotations table is not.
`scripts/export_reviewed.py` writes the reviewed annotations to CSV and is the manual
fallback.

`scripts/backup_db.sh` takes the snapshot: `sqlite3 … ".backup"` (the online backup API —
never `cp`, which can catch a half-written page on a live database and you find out at
restore time), then `PRAGMA integrity_check` **on the copy**, then gzip, then retention.
It exits non-zero if the check is not `ok`, keeping the bad file for inspection, so a
failed night shows as a `failed` unit rather than a silently missing backup. A Python
fallback using the same API runs where `sqlite3` is absent — which the box was until
2026-09-05.

`egyptology-backup.timer` runs it at 03:30 with `Persistent=true`, so a night the box spent
asleep is caught up at the next boot instead of skipped. First run 2026-09-05: 63 MB
database → **13.9 MB** gzipped, `integrity_check ok`, 2.9 s.

```bash
systemctl --user list-timers egyptology-backup.timer   # when it next runs
systemctl --user start egyptology-backup.service       # run it now
journalctl --user -u egyptology-backup.service -n 20   # what it did
```

**Off the machine: Backblaze B2 via rclone** (decided and **live since 2026-09-05 15:12**:
first upload `egyptology-2026-09-05.db.gz`, 22 MB, listed in the bucket; the timer fires
nightly at 03:33 and every run ends with `offsite copy done` or fails loudly). `OFFSITE_TARGET` in
`~/.config/systemd/user/egyptology-backup.service` names where the day's file goes; empty
means on-box only and the script says so on every run (`this snapshot exists only on this
disk`) rather than passing quietly. The script accepts either an `rsync` destination
(`user@host:/path/`, a mounted share) or an rclone remote (`b2:bucket/path` — a bare name
before the first colon), and applies the same `RETENTION_DAYS` off-site so the bucket
cannot grow forever. Why B2 and not a pull to Ledio's Mac: the Mac is asleep at 03:30
most nights and the annotations are the one irreplaceable file; B2's free tier (10 GB) holds
30 days of ~14 MB archives many times over, and rclone is a static binary that needs no
sudo.

Setup, once, by Ledio (the key never goes through a chat or a command line):

```bash
# on the box; rclone is at ~/bin/rclone (curl'd from downloads.rclone.org, v1.75.1)
ssh -t ledio@vela-optiplex-3070 '~/bin/rclone config'
#   n → name b2 → type b2 → account = B2 keyID → key = applicationKey → hard_delete true
ssh ledio@vela-optiplex-3070 '~/bin/rclone lsd b2:'        # must list the bucket
# then set  Environment=OFFSITE_TARGET=b2:egyptology-backups-ledio  in the unit,
systemctl --user daemon-reload && systemctl --user start egyptology-backup.service
~/bin/rclone ls b2:egyptology-backups-ledio                  # today's file is there
```

Bucket `egyptology-backups-ledio`, private, default encryption on; application key
`optiplex-backup` scoped to that one bucket, read + write. Restore from off-site is
`rclone copy b2:egyptology-backups-ledio/egyptology-<date>.db.gz .` followed by the
Restore steps below.

**One-off on 2026-09-05:** the live database was 52,060 rows behind the CSV (78,412 of
130,472 linked) because the deploy script only learned to import today and the guard
above never re-imports on an existing database. Ledio ran `scripts/import_examples.py`
by hand (`Inserted=52060, already present=78412, total=130472`, 24 s); the table now holds
130,472 rows and every corpus row can be annotated.

The deploy script now runs `scripts/import_examples.py` itself when the pull changed
`data/processed/examples.csv`, before the restart, with the same environment the service
reads. This matters because new CSV rows get database ids at boot only on a *fresh*
database — the empty-table guard above — so on an existing one they stay unlinked and a
reviewer who opens such a row is told it is "not linked to the project database" and cannot
save. `sync_new_examples` inserts only the missing rows and touches no existing one
(~25 s for 52k rows), so it is safe on every corpus change and cheap when there is nothing
to do.

### Restore

Snapshots are ordinary SQLite files. Nothing is overwritten below; do the counts before
deciding to swap anything in.

```bash
ssh ledio@vela-optiplex-3070
TMP=$(mktemp -d)
gzip -dc ~/egyptology-backups/egyptology-2026-09-05.db.gz > "$TMP/restored.db"

# Does it open, and does it hold what the live database holds?
cd ~/egyptology
for DB in ~/egyptology/egyptology.db "$TMP/restored.db"; do
  DATABASE_URL="sqlite:///$DB" ~/venvs/egyptology/bin/python - "$DB" <<'PY'
import sys
from sqlalchemy import func, select
from app.storage.db import SessionLocal
from app.storage.models import Annotation, Example
with SessionLocal() as session:
    print(sys.argv[1],
          "examples=", session.execute(select(func.count()).select_from(Example)).scalar_one(),
          "annotations=", session.execute(select(func.count()).select_from(Annotation)).scalar_one())
PY
done

# To actually put it back: stop, keep the old file, move the copy in, start.
systemctl --user stop egyptology.service
mv ~/egyptology/egyptology.db ~/egyptology/egyptology.db.replaced-$(date +%F)
cp "$TMP/restored.db" ~/egyptology/egyptology.db
systemctl --user start egyptology.service
```

Verified 2026-09-05 on the 2026-09-05 snapshot: `examples=78412 annotations=0` on both,
identical `sum(id)` over `examples`, same three tables. Because the live annotations table
is empty, matching counts alone would not have shown that a restored copy can *carry*
annotations, so one was written into the temporary copy through `AnnotationRepo` and read
back (`count_annotated_examples() == 1`); the live database was confirmed still at 0 and
the copy deleted.

## What needs sudo (the owner, or Ledio with the password)

Anything outside `/home/ledio`: `tailscale serve` / `funnel` changes, new ports, system
packages, adding `ledio` to `docker` (not asked for — root-equivalent on a box that runs
Vaultwarden and Nextcloud). Everything else is `ledio`'s.

Installed this way on 2026-09-05: `sqlite3` 3.45.1 (the backup script's snapshot and
integrity check) and `git-lfs` 3.4.1 (for the deferred `examples.csv` conversion — nothing
uses it yet, and it is **not** installed on the Mac).

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
