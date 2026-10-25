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
| `/home/ledio/venvs/egyptology` | the path the unit runs Python from. Since the release-venv deploy (2026-10) a **symlink** to one Python 3.12 venv in `venvs/egyptology-releases/` (≈ 760 MB each); the first such deploy moves the original directory there as `original-<time>` |
| `/home/ledio/venvs/egyptology-releases/` | release venvs, one per dependency change: the one serving and the one it replaced (the rollback target); older ones are removed after a successful deploy |
| `/home/ledio/egyptology-private` | `PRIVATE_DATA_DIR`: non-redistributed CC BY-NC-SA rows (St Andrews). Outside the clone so `git pull` never touches it. Copy files in with `scp`. |
| `/home/ledio/egyptology-backups` | nightly `egyptology-YYYY-MM-DD.db.gz` snapshots, 30-day retention, plus `monthly/` (the first snapshot of every month, kept for ever). Written by the timer below |
| `/home/ledio/egyptology.env` | secrets and per-host settings, `chmod 600`, read by the service, the backup and the deploy script. Template: `deploy/systemd/egyptology.env.example` |
| `/home/ledio/egyptology-deploy.sh` | the one-command update; refreshed from `scripts/egyptology-deploy.sh` by every successful deploy |
| `/home/ledio/egyptology-last-good`, `-last-good-venv`, `-last-good-units/` | what was running when the latest deploy **started**: the commit, the venv directory, and copies of any unit files that deploy replaced (plus `ADDED`, the units it added). Written before anything changes, so they are the right target for a manual rollback even after a failed first deploy |
| `/home/ledio/bin` | operational copies of `scripts/backup_db.sh` and `scripts/warm_streamlit.py`, refreshed from the clone by the deploy script. Outside the clone so a systemd unit never points into a tree an update is rewriting |
| `~/.config/systemd/user/egyptology.service` | the service: Streamlit on `127.0.0.1:8502`, headless, `Restart=on-failure`, enabled; `loginctl enable-linger ledio` keeps it running with nobody logged in. **Versioned in `deploy/systemd/`** (see "The unit files" below) |
| `~/.config/systemd/user/egyptology-backup.{service,timer}` | the nightly backup, 03:30 with `Persistent=true` and up to 5 min of jitter. Versioned in `deploy/systemd/` |
| `~/.config/systemd/user/egyptology-notify@.service` | sends a phone notification when the service or the backup fails. Versioned in `deploy/systemd/` |
| `/home/ledio/egyptology-data/egyptology.db` | the SQLite database: corpus ids and **all annotations**. The only irreplaceable file. Until the move in "Moving the database out of the clone" is done it is still `/home/ledio/egyptology/egyptology.db`, inside the clone |

Public access: `tailscaled` terminates TLS and proxies `/` to `127.0.0.1:8502`
(`tailscale serve`), and Funnel publishes it to the internet. Both were set by the machine
owner or by Ledio with sudo; `ledio` has no sudo.

## Deploying a change

```bash
git push origin main
ssh ledio@vela-optiplex-3070 ./egyptology-deploy.sh
```

In order, the script:

1. refuses to run (touching nothing) if another deploy holds the lock on
   `~/.egyptology-deploy.lock` (a kernel `flock`, taken through the system `python3`: it is
   released when its run exits or dies, and the file is never deleted), then, under that
   lock, if `~/egyptology-deploy.FAILED` exists (an earlier rollback failed; see Rollback), if
   tracked files in the clone are modified, or if `origin` is not a fast-forward of what is
   running. It warns if `DATABASE_URL` is not under `~/egyptology-data`;
2. records what is running now in `~/egyptology-last-good*` (above), before anything changes;
3. `git fetch`es and builds **the target commit's** dependencies into a **new release venv**
   in `~/venvs/egyptology-releases/`, from `requirements.lock` when the commit has one
   (checked against every pin in `requirements.txt`; a stale lock stops the deploy), otherwise
   from `requirements.txt` with every package it does not name held at the version the
   running venv has (a failed `pip freeze` of the running venv stops the deploy rather than
   resolving them afresh; a pip failure in this mode prints a hint to commit a lock or pin
   the package). The live venv is never installed into, so a failing pip leaves the tree,
   the venv and the running service untouched (exit 1). A commit whose dependency files did
   not change reuses the live venv and builds nothing;
4. fast-forwards the tree **with the service still running** (default
   `STOP_BEFORE_UPDATE=0`, no public downtime; the unit's
   `STREAMLIT_SERVER_FILE_WATCHER_TYPE=none` stops the running process reloading what it has
   already loaded, audit A40, but a module or page it has not imported yet is read from the
   new tree if a visitor reaches it between the merge and the stop, corpus import included
   — an accepted risk; `STOP_BEFORE_UPDATE=1` stops it first instead), refreshes
   `/home/ledio/bin` from `scripts/`, installs the unit files **only when `INSTALL_UNITS=1`**
   (otherwise it says when they differ from `deploy/systemd/`), imports the corpus with the
   **new** venv if the commit changed `data/processed/examples.csv` (see below), then stops the
   service, points `~/venvs/egyptology` at the new venv, starts it, waits for
   `/_stcore/health`, and **runs a real paste**
   (`warm_streamlit.py --expect-text 'class="suggestion-card"'`). "Healthy" only proves
   Streamlit answers; a crashing app answers too. The deploy fails unless the paste rendered a
   result card and no exception element;
5. on any failure in step 4 it rolls back automatically (below). On success it removes
   release venvs other than the serving one and the one it replaced, and refreshes
   `~/egyptology-deploy.sh` from the repo copy (the new copy takes effect on the next run).

It prints the commit it is serving and one line per step saying what it did. If it prints
the last 30 log lines instead, the app did not come up — read them. The unit's
`ExecStartPost` warm-up stays non-fatal on purpose (the unit must not flap); the deploy
script is what treats a bad app as a failed deploy. The check looks for the attribute
`class="suggestion-card"` that `whyptology_app.py` writes on every result card; renaming the
class means changing `EXPECT_TEXT` in the deploy script. Not the bare class name: the theme
stylesheet injected on every page contains `.suggestion-card {`, so a page with no result
would pass. Because the expectation is an attribute, the checker accepts it only on a real
start tag in an element that renders HTML: not in a `<style>` block, a comment, a
`<script>`/`<template>`/`<textarea>`, Markdown code (inline, fenced or indented), or markup
shown as plain text. The checker used,
by the deploy and by its rollback, is the **target** commit's `warm_streamlit.py` (on the
old venv during a rollback: a future checker that needs a newer Streamlit would turn a
working rollback into a MANUAL one, which is the safe direction).

**The deploy script is version-controlled.** The canonical copy is
`scripts/egyptology-deploy.sh` in the repo; `/home/ledio/egyptology-deploy.sh` on the box is
an operational copy of it (it is not in `/home/ledio/bin`, which the script rewrites,
precisely because it is the script). A successful deploy refreshes it, but **an old copy
cannot install a new one it does not know about**, so after changing the script itself,
copy it over by hand once:

```bash
scp scripts/egyptology-deploy.sh ledio@vela-optiplex-3070:egyptology-deploy.sh
```

### Rollback

Automatic: if the corpus import, the restart, the health check or the paste check fails
after the files changed, the script **stops the service first** (a failed check can leave the
new app serving; if the stop fails and `systemctl --user is-active` does not say `inactive` or
`failed`, it changes nothing more and goes straight to MANUAL), puts back the unit files it replaced and removes the ones it added
(`daemon-reload`), runs `git reset --hard <the commit that was running>` (ignored files, so
`*.db`, are untouched), points `~/venvs/egyptology` back at the previous venv (kept for
exactly this), starts the service and runs **the same paste check** again, not just the
health URL. Then it prints `ROLLED BACK to <sha>` (exit 1) and deletes the failed commit's
release venv. If the rollback itself fails it prints a `MANUAL:` block (exit 2) and writes it
to `~/egyptology-deploy.FAILED`; **no deploy runs while that file exists**, so a rerun cannot
overwrite the `~/egyptology-last-good*` records the block points at. Follow the block, check
the app, then `rm ~/egyptology-deploy.FAILED`. By hand, for example after a deploy that passed
the check but turned out wrong:

```bash
ssh ledio@vela-optiplex-3070
systemctl --user stop egyptology.service
# Only if that deploy ran with INSTALL_UNITS=1: copy ~/egyptology-last-good-units/*.service
# and *.timer back to ~/.config/systemd/user/, delete the units listed in its ADDED file,
# then: systemctl --user daemon-reload
git -C ~/egyptology reset --hard $(cat ~/egyptology-last-good)
ln -sfn "$(cat ~/egyptology-last-good-venv)" ~/venvs/egyptology
systemctl --user start egyptology.service
```

The `~/egyptology-last-good*` records are rewritten at the start of every deploy, so they
undo **the latest** deploy only; after a no-op deploy they name what is running now. Run the
manual steps before deploying again. A rollback costs another warm-up (about three minutes).
Not covered: a bad data migration. The database is only ever touched by
`import_examples.py` (insert-only), and the nightly backup is the safety net there.

**The full lock (`requirements.lock`, audit A45).** Not committed yet. Generate it from the
venv the server is serving once a deploy has passed, and commit it; from then on every release
venv is that exact set, and only a deliberate lock change upgrades anything:

```bash
ssh ledio@vela-optiplex-3070 '~/venvs/egyptology/bin/pip freeze --exclude-editable' > requirements.lock
```

Until then the deploy holds every package `requirements.txt` does not name at the running
venv's version, which stops a doc-only deploy from upgrading protobuf or tornado underneath
the app, but a rebuilt machine would still resolve them fresh. Each release venv is about
760 MB and at most three exist during a deploy (the box's disk is about 72% full: check
`df -h ~` before the first one).

Since 2026-09-05 the repo copy runs `import_examples.py --dry-run` before the real sync when
the corpus changed, so the deploy log distinguishes "nothing to insert" from "N inserted"
(the dry-run reports both what the default sync would insert and what `--refresh-existing`
would change, and writes nothing). Copy the repo version to the box to pick that up.
Cost of that pass, measured 2026-09-05 on a fully seeded 130,472-row SQLite file: **28 s on
the Mac** (the `--refresh-existing` half is one SELECT per row), so expect roughly a minute on
the box, paid only on corpus-changing deploys. It is cheap *because* the database is local
SQLite — against hosted Postgres the same pass would be 130,472 round trips, the Neon-egress
failure mode; do not carry it over unchanged if `DATABASE_URL` ever points off the machine.

**It takes about three minutes**, nearly all of it the restart: the unit's `ExecStartPost`
warms the stage resource sets before systemd calls the service started, so a deploy that
returns is serving a warm app. Measured no-op deploy 2026-09-05: 2 m 55 s total, health in
2 s once the restart returned. A corpus import adds ~25 s. (Measured before the release-venv
deploy; the service is now down from the `stop` before the venv switch until the check
passes, and the script prints that time as `the service was down for about Ns`. Building a
release venv, only when dependencies changed, happens while the old app still serves. The
extra paste check adds a few seconds. To be measured on the box, as is `MemoryPeak`:
`systemctl --user show egyptology -p MemoryPeak,MemoryMax`.)

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
| `PRIVATE_DATA_DIR` | `/home/ledio/egyptology-private` (in the unit) | where NC rows are read from; empty dir = none. Since 2026-09-05 the files there are served **only to sessions that presented `REVIEWER_KEY`** — see the next section |
| `REVIEWER_KEY` | set by Ledio | passphrase that unlocks annotation saving **and the private NC rows**; unset = annotation saving off for everyone and *nobody* gets the private rows (`ALLOW_OPEN_ANNOTATIONS=1` reopens saving, for local development only) |
| `DATABASE_URL` | unset today; `sqlite:////home/ledio/egyptology-data/egyptology.db` after the move below | unset = `egyptology.db` in the project root (a relative SQLite path is anchored at the project root, not the current folder, since 2026-10); a `postgres://` URL switches engines with no code change. Every process prints `database: <path> (from ...)` to stderr at start, so the journal says which file the app opened. The backup script reads this variable too |
| `NTFY_TOPIC` | set by Ledio in the env file | the ntfy.sh topic the failure notifications go to. It works like a password and the repo is public, so it is only ever in `egyptology.env` |
| `HEALTHCHECK_URL` | set by Ledio in the env file | a Healthchecks (healthchecks.io) heartbeat URL; `backup_db.sh` pings it on success and `<url>/fail` on failure, so a night with no ping raises an alert. A heartbeat only: it does not probe the website |
| `OFFSITE_PRUNE` | unset (= 1) | `0` stops the backup script deleting old files off-site (use once the B2 key cannot delete) |
| `ALLOW_ANNOTATION_DROP` | unset | `1`, for one manual run only, accepts a backup that has fewer annotations than the previous one |
| `INSTALL_UNITS` / `STOP_BEFORE_UPDATE` | deploy script, not the service | `INSTALL_UNITS=1 ~/egyptology-deploy.sh` copies `deploy/systemd/*` into `~/.config/systemd/user`; `STOP_BEFORE_UPDATE=1` stops the service before the file swap (default `0`: it keeps serving until the venv switch) |
| `STREAMLIT_SERVER_FILE_WATCHER_TYPE` | `none` (in the unit) | stops the running app reloading modules when a deploy rewrites the tree |
| `DEFAULT_STAGE` | unset (= `auto`) | `auto` / `all` / a stage name; Auto builds one extra resource set per stage it uses |
| `CORPUS_SOURCES_EXCLUDE` | unset | comma-separated values to drop at load; each token matches a row's `source` **or** its `language_stage` (so `Demotic` drops the TLA Demotic rows, and `Late Egyptian` would drop Ramses too) — how a 1 GB host would stay on the 78k subset |
| `MOVED_TO_URL` | unset | renders the "this app has moved" banner on a superseded deployment |
| `WARM_STAGE_RESOURCES` | `1` (in the unit) | build every stage's resources on the first script run instead of leaving them to the first visitor. Holds all of `STAGES` resident — measured peak RSS 3.0 GB — so only a host with the memory sets it |

## Private rows (St Andrews) — reviewer-key gate

The St Andrews rows are CC BY-NC-SA 4.0 and licensed to this project alone; the files
must not be redistributed and the rows must not be on a public URL. Until 2026-09-05
the only thing keeping them off it was that `/home/ledio/egyptology-private` was
empty. That is not a mechanism, it is an omission — so the rows are now gated on the
reviewer key, and the empty directory is no longer load-bearing.

**How it works.** The app boots on the public frame and only the public frame
(`load_public_corpus`). A session that has presented `REVIEWER_KEY` in the sidebar gets
`session_corpus` = public + private instead, which has its **own `corpus_signature`**,
so every `st.cache_resource` loader below it — `load_search_index`, `load_sign_index`,
the two Similar-text n-gram indexes, `load_stage_resources`, the reading model, the
segmenter — builds a *second*, keyed set the first time that session needs it. The gate
is therefore the frame, not a filter on the output: an unkeyed session never holds a
handle to any object built from a private row, so there is no surface that can leak one
by having been forgotten. The key lives in `st.session_state` only — never in the URL,
never logged, never in the database — so a `?q=` link a reviewer copies out of their
address bar opens public-only for whoever follows it. A "Lock this session" button in
the same sidebar expander puts a session back to public-only without a reload.

It fails closed in every direction: with `REVIEWER_KEY` unset the private rows are not
loaded for anyone, however full the directory is (the sidebar says so, in one line, so
a copied-but-invisible CSV does not read as a broken import); a wrong key leaves the
session exactly as public as it was; and if the key check or the private CSV raises,
the session gets the public frame. The failure mode is "a reviewer sees less", never
"the public sees more". The credit line follows the same frame, so the CC BY-NC-SA
attribution appears exactly in the sessions that hold NC rows.

**Order matters — set the key BEFORE the CSV arrives.** On the server:

```bash
# 1. On the server: fill the existing REVIEWER_KEY= line in the env file (chmod 600)
#    — no space after the "=", no quotes, one line, not a second one — and restart.
#    The unit is a *user* service: no sudo.
ssh ledio@vela-optiplex-3070
nano ~/egyptology.env                      # REVIEWER_KEY=<the passphrase>
systemctl --user restart egyptology.service   # returns after the ~150 s warm-up
exit
# Confirm the app is up and the sidebar shows the "Reviewer access" expander.

# 2. Only then, from the laptop, copy the rows in and restart once more:
scp data/private/standrews.csv ledio@vela-optiplex-3070:egyptology-private/
ssh ledio@vela-optiplex-3070 'systemctl --user restart egyptology.service'
```

**Status 2026-09-06 00:25 — done and confirmed.** `standrews.csv` (4.7 MB, 7,659 rows) is
in `/home/ledio/egyptology-private/`, `REVIEWER_KEY` is set, and both views were checked on
the live URL: a public session shows **130,472** records, sources AES / BBAW / Ramses / TLA,
CC BY-SA credit only; Ledio's keyed session shows **138,131** records with St Andrews in the
Source list and the NC credit line. systemd strips leading/trailing whitespace from values in
the env file, so a stray space after `=` does not break the comparison, but a passphrase
should still be a long phrase — it is what stands between the public URL and the NC rows.

Copying the CSV first would put 7,659 NC rows on a host whose gate is not yet armed.
The gate would still hold — no key configured means no private rows for anyone — but
there is no reason to run the window.

**Rotation.** Edit the `REVIEWER_KEY=` line in `/home/ledio/egyptology.env`,
`systemctl --user restart egyptology.service`, and send the new passphrase to the reviewers. Open
sessions are lost on restart, which is what rotation is for. Nothing else changes; the
CSV stays where it is.

**Choosing the key, and what guards it (audit 2026-10-11, A18/A19/A20/A58).** Generate it,
do not invent it: `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'` (32
characters; anything under 20 random characters is too short for a public URL). Any
Unicode is accepted; the comparison is on UTF-8 bytes. The guard (`KeyAttemptGuard` in
`app/ui/review_common.py`) has two layers, both in memory, cleared by a restart:

- **Per session, exponential backoff.** After 5 wrong keys inside 15 minutes *that
  session* must wait 30 s, doubling with each further failure up to 15 min; while it
  waits its key is not even compared. Other sessions, including real reviewers, are
  not affected.
- **Process-wide, slow-down only.** A guesser gets a fresh session per connection, so
  above 20 failures from all sessions inside 15 minutes every attempt (right or wrong,
  from any session) is delayed 0.25 s per excess failure, capped at 5 s. It never
  refuses: a real reviewer is at most 5 s slower.

Neither layer caps how many attempts run at once — N parallel connections still get
roughly N / 5 guesses a second — so **the key's length is the real protection**: use
the generated 32-character key above, never a short or memorable one.

Logging is counts only, never the typed value: a success is `reviewer-key: unlock ok`,
a failure `reviewer-key: failed unlock attempt (S recent failures in this session, G in
all sessions; slowed D s)`, so `journalctl --user -u egyptology.service | grep
reviewer-key` shows guessing. An empty submission is not counted.

**Saving fails closed.** An empty `REVIEWER_KEY` switches annotation saving off for
everyone (it used to leave saving open to any visitor): the sidebar says so, and the log
warns once per process when `ANNOTATIONS_DURABLE` is on. Only local development opts back
in, with `ALLOW_OPEN_ANNOTATIONS=1`; never set that on a public host.

**What it costs, measured on the developer's Mac 2026-09-05** (130,472 public rows +
the real 7,659-row `standrews.csv`): the keyed resource set is **+1,033 MB (1.01 GB)**
resident on top of the public one and takes **19.3 s** to build — the concat 0.18 s and
+50 MB, the pooled stage resources 10.2 s and +524 MB, the Similar-text sign index
1.2 s and +92 MB, the Similar-text translation index 4.6 s and +353 MB. The last two
are lazy, so a reviewer who never opens Similar text pays +575 MB, not +1,033 MB. Peak
RSS with both full sets resident was 2.73 GB in that measurement process. Against the
3.0 GB peak recorded below and the Streamlit process's 2.37 GB after the 2026-09-05
deploy, the worst case on the 23 GB box is roughly 3.4–4.0 GB. It is paid once per
process, not per reviewer, and only after the first reviewer unlocks.

## What the service needs, measured 2026-09-04, warm-up added 2026-09-05

130,472 rows load in 9 s; pooled resources build in ~30 s on this CPU; the first
hieroglyph paste in Auto mode builds the three stage resource sets and then everything is
cached. **That three-stage cold build is now ~30 s, not ~60 s** — re-measured on the
developer's Mac 2026-09-05 after item 3 made the stage sets share the pooled per-row token
tables (see "Warming that cold build" below); the 60 s here was the 2026-09-04 figure,
before that change. Peak RSS with all four sets resident: **3.0 GB**, of 23 GB — the
1.9 GB first written here was an estimate and is low.

**The Similar text page adds up to +522 MB, and only when someone opens it** (ROADMAP item
E, 2026-09-05). Its two n-gram indexes are separate `st.cache_resource` loaders
(`load_sign_ngram_index`, `load_translation_ngram_index`), so a visitor who never opens the
page allocates neither. Measured on the developer's Mac on the 130,472-row corpus: the sign
index costs 1.27 s to build and **+66 MB**, the translation index 4.66 s and **+456 MB** —
the expensive one, because a German or English sentence has far more distinct character
4-grams than a folded transliteration. Both are per process, not per session. On the 23 GB
server that is fine on top of the 3.0 GB above; a 1 GB container must not open that page.

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
(summation order), which never changes any top-1000 ordering. The FastAPI endpoint in
`app/api/main.py` now gets the `SearchIndex` too (2026-09-05): it builds the frame and
index once behind an `lru_cache` (`load_corpus`) and passes `index=` to `retrieve_top_k`,
so a warm request went from **8.4 s to 0.15 s** on the Mac (it previously reloaded the
130,472-row CSV on *every* request and took the scalar retrieval path; the verifier's split
of the old path was roughly half each — CSV load 3.9 s, scalar retrieval 4.2 s — and the
change removes both). Both the Streamlit and API paths are now fast.

The API is **not** exposed on the live URL and must not be (no Funnel/Serve route, no
`--host 0.0.0.0`) unless that is a deliberate decision: it has no authentication and no
rate limit. Since the 2026-10-11 audit (A52) each response does carry a `licence` block
and an `attribution` list naming the corpus of every returned row, and `query_mdc` is
capped at 500 characters.

### Warming that cold build

The warm-up builds the **public** resource set only. `scripts/warm_streamlit.py` opens
an ordinary, unkeyed session, and the app's module scope hands `warm_stage_resources`
the public frame rather than the session frame — so a keyed reviewer's rerun cannot
turn the warm-up into a warm-up of the private set, which process-global
`st.cache_resource` would then keep resident for the life of the service. A reviewer's
first search after a restart therefore pays the keyed build (see the reviewer-key gate
section above); a visitor's does not.

The visitor no longer pays it. Measured on the box 2026-09-05:

| | before | after |
|---|---|---|
| first hieroglyph paste after a restart | ~60 s (the build) | **5.3 s** |
| the same paste after item 3's speed-up (box, 2026-09-05 evening, at 3d38721) | — | **2.6 s** (two runs, both 2.6 s; the "< 5 s" gate is met) |
| page load, no search | — | 1.9 s |
| the cold build itself (server, box) | on the visitor's first paste | 165 s inside `ExecStartPost`, before systemd calls the service started |
| the three concrete stage sets (Mac, 2026-09-05) | — | **~30 s total** (~9–11 s each: Earlier 9.5–10.0 s, Late 10.4–11.1 s, Demotic 9.2–9.4 s), reusing the pooled index |

The box's 165 s row and the Mac's ~30 s row are **different machines and different scopes**
and are kept side by side, not merged: the 165 s is the whole `ExecStartPost` warm-up on the
OptiPlex (CSV load + pooled build + all four sets + a real paste over the websocket), measured
2026-09-05; the ~30 s is just the three concrete `build_stage_resources` calls on the Mac,
each reusing the pooled `SearchIndex` exactly as `load_stage_resources` does, re-measured
2026-09-05 after item 3. **The server number should be re-measured after the next deploy** —
item 3's pooled-token-table sharing, which halved the Mac figure, had not landed on the box
when the 165 s was taken.

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
The unit is versioned in `deploy/systemd/egyptology.service`; the lines in it that were
reconstructed rather than copied from the box are listed under "The unit files" below.

**The warm-up is also a smoke test (audit A11).** When the app's code is broken Streamlit
does not fail the run: it draws the traceback as an `exception` element and then reports
`script_finished` / `FINISHED_SUCCESSFULLY`, which is what the old warm-up printed for an
app that raised on every visit. `warm_streamlit.py` now fails (exit 1) when an exception
element arrives (warning-style ones are ignored), and with `--expect-text TEXT` also when no
markdown/html/text element contains that text; the deploy script uses
`--expect-text suggestion-card`. `[client] showErrorDetails = "none"` in
`.streamlit/config.toml` hides tracebacks from the public (the browser shows a generic
message; the real traceback is in `journalctl --user -u egyptology.service`, and in the
terminal when developing locally), and the exception element is still sent, so detection
keeps working.

## Annotations and backups

Annotations live in `egyptology.db`. The corpus table is regenerable from the CSV
(`ensure_corpus_ready` seeds an empty table on first boot and never re-imports over live
annotations — do not remove that guard); the annotations table is not.
`scripts/export_reviewed.py` writes the reviewed annotations to CSV and is the manual
fallback.

`scripts/backup_db.sh` takes the snapshot: `sqlite3 … ".backup"` (the online backup API —
never `cp`, which can catch a half-written page on a live database and you find out at
restore time) into a hidden candidate file, then `PRAGMA integrity_check` **on the copy**,
then gzip, then a content check, and only then publishes it as
`egyptology-<date>.db.gz`, then the monthly copy, then retention. A second run on the same
day publishes `egyptology-<date>-r02.db.gz` (and so on): an accepted snapshot is never
overwritten. Revision numbers compare as numbers (`-r100` is newer than `-r99`) and are never
reused: each is one above every revision of that day in the folder, kept copies included.
Only one run at a time: a run holds a kernel `flock` on `BACKUP_DIR/.backup.lock` from
before the snapshot to exit, a second run (the timer overlapping a manual one) waits up to
`LOCK_WAIT` seconds (default 900) and then exits 5 having written nothing. The kernel drops
the lock when its run dies, so there is nothing stale to take over, and the file is never
deleted. rsync/rclone run with the descriptor closed, so a helper they leave behind cannot
keep holding the lock. It exits non-zero if the check is not `ok`,
keeping the bad file for inspection, so a failed night shows as a `failed` unit rather than
a silently missing backup. A Python fallback using the same API runs where `sqlite3` is
absent — which the box was until 2026-09-05. It opens the database read-only through a
percent-encoded `file:` URI, so a `#` or `%` in the file name names that file.

**The content check (audit A13).** `integrity_check` proves the file is a sound database,
not that the annotations are still in it: a bad migration or a wrong `DELETE` gives a
healthy file with an empty table, and 30 days later retention would age the last good copy
out, on the box and in B2. So after gzip the script runs `gzip -t`, decompresses the
**compressed copy** (what a restore would use) and counts `examples` and `annotations`, and
compares with the **newest accepted snapshot**, today's included (so a same-day rerun after a
deletion cannot pass by comparing with yesterday), dailies and `monthly/` alike (so a
baseline survives even when every daily has aged out):

- **fewer annotations: exit 3.** The copy is kept as
  `egyptology-<date>.db.gz.suspect` (a name retention does not match), both counts are
  printed, and *nothing else happens*: no retention, no monthly copy, no off-site copy, so
  every older good snapshot stays. The unit shows `failed` and the notification fires. The
  next night compares with the last *good* snapshot again, so it keeps failing until a
  human decides. If the deletion was deliberate, run once with
  `ALLOW_ANNOTATION_DROP=1 ~/bin/backup_db.sh`. Delete the `.suspect` file by hand when it
  has been looked at.
- **examples: exit 3 only if the count fell to 0**; any other drop prints a warning (a
  deliberate corpus shrink is legitimate).
- **the newest accepted snapshot cannot be read: exit 4**, fail closed. The copy is kept as
  `<name>.db.gz.unverified` and nothing else happens (no retention, no off-site copy). Check
  that file; if it is damaged, rename it to `<name>.bad` and run again.
- **no snapshot at all, but earlier ones were published here** (the folder has a
  `.has-snapshots` marker): also exit 4, because an emptied folder is not a first backup.
- a genuine first backup (no snapshot, no marker): the comparison is skipped and the script
  says so.

The check costs a decompress and two counts: +0.15 s on a 28 MB database (1.27 s to 1.42 s
without a previous snapshot, 1.58 s with one, measured on the Mac); expect about 1 s on the
box's 63 MB file and about 63 MB of scratch space in `$TMPDIR`.

**The long tail.** The first good snapshot of each month is copied to
`~/egyptology-backups/monthly/egyptology-YYYY-MM.db.gz` and kept for ever (about 14–22 MB
each, roughly 0.25 GB a year). Retention only looks at the top level of the folder, so it
never touches `monthly/`, and the off-site prune is `--max-depth 1` for the same reason.
Off-site, every run sends today's file and then **reconciles every retained daily and every
monthly file** with the destination (`rclone copy`, never `sync`; `--checksum` makes a file
already there a no-op), so a night or a month boundary whose upload failed heals on the next
run. Nothing in that step deletes anything off-site. If a B2 lifecycle rule expires the
dailies, give it at least `RETENTION_DAYS` (30), or the reconcile re-uploads what it expired.

**Off-site deletes.** The script's `rclone delete --min-age` prune is now non-fatal, and
`OFFSITE_PRUNE=0` turns it off. The safer end state, which needs Ledio (never through
chat): a second B2 application key for the bucket **without `deleteFiles`**, `rclone config`
with that key and `hard_delete` false, a lifecycle rule on the bucket that expires the daily
files, and B2 Object Lock if the bucket allows it. Then neither the box nor a bad
`RETENTION_DAYS` can wipe the off-site copies. Keep the old key until the new one is proven.

**Heartbeat.** With `HEALTHCHECK_URL` set (a Healthchecks heartbeat check, in `egyptology.env`) the
script pings it on success and `<url>/fail` on any failure, so a night where the timer never
fired also raises an alert, which `OnFailure=` cannot catch.

**Rehearse a restore once a month** from the off-site copy: `rclone copy`, `gzip -t`,
decompress, then run the counting snippet under "Restore". Matching counts are the point.

**Future option, not needed now: restic** (BSD-2-Clause). It could replace the custom
retention, upload and verification with deduplicated, encrypted snapshots and
`restic check`. The SQLite online snapshot and the annotation-count comparison would stay
either way: restic cannot tell a healthy file from one whose annotations were deleted.

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

The deploy script now runs `scripts/import_examples.py` itself when the update changed
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
# (After the move below, the live file is ~/egyptology-data/egyptology.db.)
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

## Alerts (audit A42)

Three layers, because each one misses something the next catches:

| What | Catches | Misses |
|---|---|---|
| `OnFailure=egyptology-notify@%n.service` on the service and the backup unit; the notify unit posts to `https://ntfy.sh/$NTFY_TOPIC` | the service ending in `failed` (after `Restart=` gave up, by default 5 starts in 10 s), a failed or `exit 3` backup | a single crash that `Restart=on-failure` recovered; Tailscale or Funnel being off; the timer never firing |
| `HEALTHCHECK_URL` heartbeat from `backup_db.sh` | a night with no backup at all, a box that was off | anything about the website |
| an HTTP monitor that probes `https://vela-optiplex-3070.taile0409f.ts.net/_stcore/health` from **another** machine, e.g. Uptime Kuma (MIT, self-hosted) on a different box, or UptimeRobot. Not set up yet. Healthchecks cannot do this: it only receives heartbeats, it never probes a site | the public site being unreachable for any reason | the app serving errors (the deploy's paste check covers deploys, not later breakage) |

The notification text carries only the unit name and the host name. Test the channel with
`systemctl --user start egyptology-notify@test.service`.

## The unit files (audit A46)

`deploy/systemd/` holds `deploy/systemd/egyptology.service`,
`deploy/systemd/egyptology-backup.service`, `deploy/systemd/egyptology-backup.timer`,
`deploy/systemd/egyptology-notify@.service` and `deploy/systemd/egyptology.env.example`, so a
reinstall of the box no longer depends on guessing `OFFSITE_TARGET`, the 600 s start timeout
or the warm-up line. **They were reconstructed from this document, not copied from the box**,
and every guessed line is marked `# GUESSED:` in the file. Before installing them, diff each
against the live one and fix the repo copy where the live one is right:

```bash
ssh ledio@vela-optiplex-3070 'cat ~/.config/systemd/user/egyptology.service' | diff - deploy/systemd/egyptology.service
```

The guesses, in one place: no `After=`/`Wants=` lines (a user unit cannot wait for
`network-online.target`); the exact `ExecStart` flags and the `python -m streamlit` form;
the warm-up `--timeout 500`; `RestartSec` left at the default; `MemoryMax=6G` (measured peak
3.0 GB, about 4.5 GB worst case with a keyed session and Similar text; it kills the app at the
limit instead of letting it starve Vaultwarden and Nextcloud, and needs memory delegation to
the user manager, so check `systemctl --user show egyptology -p MemoryMax`); the backup
service having no `TimeoutStartSec`; the timer's `RandomizedDelaySec=300` spelling; the notify
command line. `systemd-analyze verify` was not available where these were written.

The deploy script installs them only with `INSTALL_UNITS=1` (copy, `daemon-reload`); without
it, it just says when they differ. Run `systemctl --user enable --now egyptology-backup.timer`
if the timer was not already enabled, and `systemctl --user list-timers` afterwards.

## Moving the database out of the clone (audit A43)

The SQLite file is the one irreplaceable thing here and it sits inside the git clone: a
`rm -rf ~/egyptology && git clone …` to "fix a messy checkout" would delete every annotation
since the last 03:30 backup. Since this change a relative `DATABASE_URL` is resolved against
the project root (not the folder a command is run from), and every process prints which file
it opened, so a script run from the home folder can no longer silently create a second,
empty database. Moving the file out of the clone is a manual step, in a quiet window, in
this order:

```bash
ssh ledio@vela-optiplex-3070
systemctl --user stop egyptology.service
mkdir -p ~/egyptology-data
# Counting snippet from "Restore" on the old file first (note examples and annotations).
mv ~/egyptology/egyptology.db* ~/egyptology-data/      # includes any -wal / -shm files
# Run the same counting snippet on ~/egyptology-data/egyptology.db: the numbers must match.
# Only NOW add the line below to ~/egyptology.env. Before the move it would make the app
# create and seed a fresh, empty database.
#   DATABASE_URL=sqlite:////home/ledio/egyptology-data/egyptology.db
systemctl --user start egyptology.service
journalctl --user -u egyptology.service | grep 'database:'   # shows the new path
```

Keep a copy of the old file for a week. `backup_db.sh` and the deploy script's corpus import
read `DATABASE_URL` from the same env file, so all three agree on the path.

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

With no `REVIEWER_KEY` set, annotation saving is off. To try the annotation form
locally, run `ALLOW_OPEN_ANNOTATIONS=1 streamlit run app/ui/whyptology_app.py` (never on a public host).

To rebuild the environment, use 3.12 explicitly:

```bash
python3.12 -m venv ~/venvs/egyptology
~/venvs/egyptology/bin/pip install -r requirements-dev.txt watchdog
```

`requirements.txt` is what the server installs (the app only); `requirements-dev.txt` adds
pytest, `datasets` (only for regenerating `data/raw`) and a pinned `hieropy` (the St Andrews
importer and its tests; GPL, so it stays out of `requirements.txt` and the application).
Only top-level packages are pinned in `requirements.txt`; the server deploy builds from
`requirements.lock` once one is committed (see "Rollback"). On a laptop,
`showErrorDetails = "none"` in `.streamlit/config.toml` means a crash shows a generic
message in the browser and the traceback only in the terminal.

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
