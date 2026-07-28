from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.storage.bootstrap import create_tables, upsert_examples

DATA_PATH = "data/processed/examples.csv"


def main() -> None:
    df = load_examples_csv(DATA_PATH)

    create_tables()
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
