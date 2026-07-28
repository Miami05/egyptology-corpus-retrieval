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
2. Copy the connection string. It looks like:
   `postgres://user:password@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
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

Save an annotation in **Reviews**, then use *Manage app → Reboot*. If the annotation
is still listed after the reboot, persistence is live. Before this change, it would
not have been.

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

### Testing responsive layout

Streamlit stores the sidebar open/closed state in **browser storage**, and that
overrides `initial_sidebar_state`. Testing on an origin where you have already toggled
the sidebar will mislead you. Use a fresh origin — `127.0.0.1:8501` rather than
`localhost:8501` — or clear site data first.

## Licensing before going public

The repo is private. Before making it or the app public, read `DATA-LICENSE.md`: the
corpus is CC BY-SA 4.0 (share-alike) and cannot be redistributed under the MIT licence
that covers the code. The required attribution is rendered in the app sidebar and must
stay there.
