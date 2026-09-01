"""Say, in one line, whether saved annotations will survive a restart.

    ~/venvs/egyptology/bin/python scripts/check_database.py

Reads DATABASE_URL the way the app does (environment, then .env) and reports the
engine, whether it answers, how many corpus rows and annotations it holds, and a
verdict: DURABLE (hosted Postgres) or EPHEMERAL (SQLite — fine on a laptop, but inside
a Streamlit Cloud container the file is recreated on every reboot and redeploy, so
every annotation is silently lost). Creates nothing: no tables, no rows.

Exit codes: 0 durable, 1 ephemeral, 2 unreachable — so a deploy check can gate on it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, inspect, select, text  # noqa: E402

from app.storage.db import DATABASE_URL, IS_SQLITE, engine  # noqa: E402
from app.storage.models import Annotation, Example  # noqa: E402

# Streamlit Community Cloud sets these; locally they are absent. Used only to make the
# SQLite verdict more specific — SQLite is ephemeral on a hosting platform and merely
# local on a laptop.
HOSTED_MARKERS = ("STREAMLIT_SHARING_MODE", "STREAMLIT_SERVER_HEADLESS", "HOSTNAME")


def redacted(url: str) -> str:
    """The URL without credentials: host and database only."""
    if "@" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://…@{rest.split('@', 1)[1]}"
    return url


def main() -> int:
    kind = "sqlite" if IS_SQLITE else "postgres"
    print(f"engine   : {kind}")
    print(f"url      : {redacted(DATABASE_URL)}")

    # SQLite creates its file on first connect, and this script promises to create
    # nothing — so a missing file is reported without touching it.
    if IS_SQLITE:
        path = DATABASE_URL.replace("sqlite:///", "", 1)
        if path and path != ":memory:" and not Path(path).exists():
            print(f"reachable: no database file yet at {path} (nothing created)")
            print("verdict  : EPHEMERAL — SQLite, and not even seeded yet.")
            return 1

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            tables = set(inspect(connection).get_table_names())
            examples = (
                connection.execute(select(func.count()).select_from(Example)).scalar_one()
                if "examples" in tables
                else 0
            )
            annotations = (
                connection.execute(select(func.count()).select_from(Annotation)).scalar_one()
                if "annotations" in tables
                else 0
            )
    except Exception as exc:  # noqa: BLE001 - the whole point is to report it
        print(f"reachable: no — {type(exc).__name__}: {str(exc).splitlines()[0][:160]}")
        print("verdict  : UNREACHABLE")
        return 2

    print("reachable: yes")
    print(f"tables   : {'examples' if 'examples' in tables else '(no examples table yet)'}"
          f"{', annotations' if 'annotations' in tables else ''}")
    print(f"examples : {examples:,}")
    print(f"annotations: {annotations:,}")

    if IS_SQLITE:
        hosted = any(os.getenv(marker) for marker in HOSTED_MARKERS)
        where = "inside a hosting container" if hosted else "on this machine"
        print(
            f"verdict  : EPHEMERAL — SQLite file {where}. On Streamlit Cloud the file is "
            "recreated on every reboot and redeploy; annotations saved there are lost."
        )
        return 1
    print("verdict  : DURABLE — hosted Postgres; annotations survive restarts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
