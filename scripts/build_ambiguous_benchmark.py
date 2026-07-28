from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.suggestions import loose_reading_form

EXAMPLES_PATH = "data/processed/examples.csv"
OUTPUT_PATH = "data/benchmarks/ambiguous_reading_eval_queries.csv"


def _tokens(value: object) -> list[str]:
    return [token for token in str(value).split() if token.strip()]


def _drop_endings(value: str) -> str:
    tokens = _tokens(value)
    simplified: list[str] = []
    for token in tokens:
        if len(token) > 4 and token.endswith(("t", "w", "j", "y")):
            simplified.append(token[:-1])
        else:
            simplified.append(token)
    return " ".join(simplified)


def _partial(value: str) -> str:
    tokens = _tokens(value)
    if len(tokens) <= 2:
        return " ".join(tokens[:1]) or value
    keep = max(2, min(len(tokens) - 1, round(len(tokens) * 0.65)))
    return " ".join(tokens[:keep])


def _make_query(row: pd.Series, row_num: int) -> tuple[str, str, str]:
    simplified = loose_reading_form(row["transliteration_gold"])
    simplified = re.sub(r"\bpl\b", "", simplified)
    simplified = re.sub(r"\s+", " ", simplified).strip()
    query_type = [
        "simplified_transliteration",
        "partial_transliteration",
        "normalized_reading_order",
    ][(row_num - 1) % 3]
    if query_type == "partial_transliteration":
        query_input = _partial(_drop_endings(simplified))
        notes = "Simplified transliteration with final portion removed."
    elif query_type == "normalized_reading_order":
        query_input = str(row["normalized_reading_order"]).strip() or simplified
        notes = "Local normalized reading-order key from the imported row."
    else:
        query_input = _drop_endings(simplified)
        notes = "Editorial markers, dots, parentheses, and equals signs removed."
    return query_input, query_type, notes


def main() -> None:
    df = load_examples_csv(EXAMPLES_PATH)
    rows: list[dict[str, str]] = []
    for row_num, (_, row) in enumerate(df.head(20).iterrows(), start=1):
        query_input, query_type, notes = _make_query(row, row_num)
        rows.append(
            {
                "benchmark_id": f"AMB_{row_num:03d}",
                "query_input": query_input,
                "query_type": query_type,
                "expected_transliteration": row["transliteration_gold"],
                "expected_source_text_id": row["source_text_id"],
                "expected_source_sentence_id": row["source_sentence_id"],
                "notes": notes,
            }
        )

    output_path = Path(OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"Wrote {len(rows)} ambiguous benchmark rows to {output_path}")


if __name__ == "__main__":
    main()
