"""List the known near-twins of every competitive-ambiguity benchmark target (audit A4, A55).

For each target a twin is a corpus row that is not the target but has word overlap
(Jaccard on loose-form tokens) of at least the threshold with it, or the same
notation-folded reading: another edition of the same sentence, which hands the
expected reading over for free once only the target row is removed from the pool.

    python scripts/list_benchmark_twins.py

writes `data/benchmarks/known_twins_2026-10-12.csv`, the allow-list that
`tests/test_audit_eval.py` compares against, so a new twin (a benchmark regenerated, a
corpus source added) or a vanished one fails a test instead of silently moving a score.
It only reads the corpus and the benchmark files.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from scripts.eval_guards import DEFAULT_TWIN_THRESHOLD, TwinGuard

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_GLOB = "data/benchmarks/competitive_ambiguity_eval_queries*.csv"
OUTPUT_PATH = "data/benchmarks/known_twins_2026-10-12.csv"

COLUMNS = [
    "benchmark_file",
    "benchmark_id",
    "twin_source",
    "twin_text_id",
    "twin_sentence_id",
    "overlap",
    "folded_identical",
    "threshold_bucket",
]


def bucket_for(overlap: float, folded_identical: bool) -> str:
    if overlap >= 0.9:
        return ">=0.9"
    if overlap >= 0.7:
        return "0.7-0.9"
    return "folded_only" if folded_identical else "below_0.7"


def twin_records(
    examples_df: pd.DataFrame,
    guard: TwinGuard,
    benchmark_df: pd.DataFrame,
    benchmark_file: str,
    threshold: float = DEFAULT_TWIN_THRESHOLD,
) -> list[dict[str, object]]:
    """One record per (benchmark target, twin row)."""
    sources = [str(value) for value in examples_df["source"]]
    text_ids = [str(value) for value in examples_df["source_text_id"]]
    sentence_ids = [str(value) for value in examples_df["source_sentence_id"]]
    records: list[dict[str, object]] = []
    for _, bench_row in benchmark_df.iterrows():
        for position, overlap, folded in guard.twins(bench_row, threshold):
            records.append(
                {
                    "benchmark_file": benchmark_file,
                    "benchmark_id": bench_row["benchmark_id"],
                    "twin_source": sources[position],
                    "twin_text_id": text_ids[position],
                    "twin_sentence_id": sentence_ids[position],
                    "overlap": round(overlap, 4),
                    "folded_identical": folded,
                    "threshold_bucket": bucket_for(overlap, folded),
                }
            )
    return records


def summarise(records: pd.DataFrame, benchmark_df: pd.DataFrame) -> dict[str, int]:
    """Targets with a twin at >=0.7 (or folded-identical) and at >=0.9."""
    return {
        "queries": len(benchmark_df),
        "targets_with_twin_0.7": int(records["benchmark_id"].nunique()) if len(records) else 0,
        "targets_with_twin_0.9": (
            int(records.loc[records["overlap"] >= 0.9, "benchmark_id"].nunique())
            if len(records)
            else 0
        ),
    }


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--benchmarks", default=BENCHMARK_GLOB, help="Glob of benchmark CSVs.")
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.add_argument("--threshold", type=float, default=DEFAULT_TWIN_THRESHOLD)
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> None:
    args = _parse_args(argv)
    examples_df = load_examples_csv(args.examples)
    guard = TwinGuard(examples_df)
    all_records: list[dict[str, object]] = []
    for path in sorted(glob.glob(args.benchmarks)):
        benchmark_df = pd.read_csv(path).fillna("")
        records = twin_records(
            examples_df, guard, benchmark_df, Path(path).name, args.threshold
        )
        all_records.extend(records)
        counts = summarise(pd.DataFrame(records, columns=COLUMNS), benchmark_df)
        print(f"{Path(path).name}: {counts}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_records, columns=COLUMNS).to_csv(output, index=False)
    print(f"Wrote {len(all_records)} twin rows to {output}")


if __name__ == "__main__":
    main()
