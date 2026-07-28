from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INPUT_PATH = "data/processed/examples.csv"
OUTPUT_PATH = "data/benchmarks/phase3_eval_queries.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    df = pd.read_csv(INPUT_PATH).fillna("")
    if df.empty:
        print("examples.csv is empty. Build real examples first.")
        return

    subset = df.head(args.limit).copy()
    benchmark_rows = []
    for row_num, (_, row) in enumerate(subset.iterrows(), start=1):
        benchmark_rows.append(
            {
                "benchmark_id": f"BM_{row_num:03d}",
                "query_mdc": row["mdc"],
                "query_normalized_reading_order": row["normalized_reading_order"],
                "expected_source": row["source"],
                "expected_source_text_id": row["source_text_id"],
                "expected_source_sentence_id": row["source_sentence_id"],
                "notes": "",
            }
        )
    out = pd.DataFrame(benchmark_rows)
    Path("data/benchmarks").mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(out)} benchmark rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
