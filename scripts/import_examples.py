from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.storage.bootstrap import (
    create_tables,
    diff_new_examples,
    sync_new_examples,
    upsert_examples,
)

DATA_PATH = "data/processed/examples.csv"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync data/processed/examples.csv into the database. By default only "
            "rows the database does not have are inserted, which is what growing "
            "the corpus needs and costs a handful of queries. Use --refresh-existing "
            "when the content of rows already present has changed; that path issues "
            "a query per row."
        )
    )
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Report what the default sync would insert AND what --refresh-existing "
            "would change, then exit without writing anything. Lets a deploy log "
            "distinguish 'nothing to insert' from 'N inserted' before it commits."
        ),
    )
    args = parser.parse_args()

    df = load_examples_csv(DATA_PATH)
    create_tables()

    if args.dry_run:
        sync_diff = diff_new_examples(df)
        print(
            f"[dry-run] Default sync WOULD insert={sync_diff['inserted']}, "
            f"already present={sync_diff['already_present']}, total={sync_diff['total']}"
        )

        refresh_diff = upsert_examples(df, dry_run=True)
        print(
            f"[dry-run] --refresh-existing WOULD create={refresh_diff['created']}, "
            f"update={refresh_diff['updated']}, unchanged={refresh_diff['unchanged']}"
        )
        field_changes = refresh_diff["field_changes"]
        if field_changes:
            print("[dry-run] fields that would be refreshed on existing rows:")
            for field, count in sorted(field_changes.items(), key=lambda item: -item[1]):
                print(f"  {field}: {count} rows")
        print("[dry-run] no rows were written.")
        return

    if not args.refresh_existing:
        stats = sync_new_examples(df)
        print(
            f"Sync finished. Inserted={stats['inserted']}, "
            f"already present={stats['already_present']}, total={stats['total']}"
        )
        return

    stats = upsert_examples(df)

    print(
        f"Import finished. Created={stats['created']}, "
        f"updated={stats['updated']}, unchanged={stats['unchanged']}"
    )

    field_changes = stats["field_changes"]
    if field_changes:
        print("Refreshed fields on existing rows (annotations preserved):")
        for field, count in sorted(field_changes.items(), key=lambda item: -item[1]):
            print(f"  {field}: {count} rows")


if __name__ == "__main__":
    main()
