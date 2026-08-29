"""One-time migration: drop the retrieval_runs search-log table.

The table logged every visitor search verbatim, forever, and was never read by any
code path (verified 2026-08-29). The writes were removed in the Phase 0 commit and
the model in the Phase 2 commit; this script removes the table itself from an
existing database. New databases never create it.

Run against production deliberately, with the production URL:

    DATABASE_URL='postgresql://...' python scripts/drop_retrieval_runs_table.py --yes

Without --yes it only reports whether the table exists and how many rows it holds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.storage.db import DATABASE_URL, engine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Actually drop the table.")
    args = parser.parse_args()

    print(f"database: {DATABASE_URL.split('@')[-1]}")
    if not inspect(engine).has_table("retrieval_runs"):
        print("retrieval_runs does not exist — nothing to do.")
        return
    with engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM retrieval_runs")).scalar()
    print(f"retrieval_runs exists with {count} logged searches.")
    if not args.yes:
        print("Dry run. Re-run with --yes to drop the table (this discards the log).")
        return
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE retrieval_runs"))
    print("Dropped retrieval_runs.")


if __name__ == "__main__":
    main()
