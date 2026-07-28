from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INPUT_PATH = "data/raw/real_examples_worklist.csv"

MIN_REQUIRED_FIELDS = [
    "source",
    "source_text_id",
    "source_sentence_id",
    "genre",
    "period",
    "mdc",
    "sign_sequence",
    "transliteration_gold",
]


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def main() -> None:
    df = pd.read_csv(INPUT_PATH).fillna("")

    print(f"Total rows in worklist: {len(df)}")
    print()

    complete = 0
    incomplete = 0

    for row_num, (_, row) in enumerate(df.iterrows(), start=1):
        missing = [
            field for field in MIN_REQUIRED_FIELDS if not _safe_str(row.get(field, ""))
        ]

        if missing:
            incomplete += 1
            print(
                f"Row {row_num}: INCOMPLETE | "
                f"source={row.get('source', '')} "
                f"text_id={row.get('source_text_id', '')} "
                f"sentence_id={row.get('source_sentence_id', '')} "
                f"missing={missing}"
            )
        else:
            complete += 1
            print(
                f"Row {row_num}: COMPLETE | "
                f"source={row.get('source', '')} "
                f"text_id={row.get('source_text_id', '')} "
                f"sentence_id={row.get('source_sentence_id', '')}"
            )

    print()
    print(f"Complete rows: {complete}")
    print(f"Incomplete rows: {incomplete}")


if __name__ == "__main__":
    main()
