from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.data.loader import load_examples_csv
from app.services.evaluation import evaluate_benchmark, load_benchmark_csv

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/phase3_eval_queries.csv"
DETAILS_OUTPUT_PATH = "data/benchmarks/phase3_eval_results.csv"
FAILURES_OUTPUT_PATH = "data/benchmarks/phase3_eval_failures.csv"


def main() -> None:
    examples_df = load_examples_csv(EXAMPLES_PATH)
    benchmark_df = load_benchmark_csv(BENCHMARK_PATH)

    summary, details_df = evaluate_benchmark(
        examples_df=examples_df,
        benchmark_df=benchmark_df,
        k=settings.top_k,
    )

    print("Phase 3 evaluation summary:")
    for key, value in summary.items():
        print(f"{key}: {value}")

    Path("data/benchmarks").mkdir(parents=True, exist_ok=True)
    details_df.to_csv(DETAILS_OUTPUT_PATH, index=False)

    if not details_df.empty:
        failures_df = details_df[details_df["top3_hit"] == False].copy()  # noqa: E712
        failures_df.to_csv(FAILURES_OUTPUT_PATH, index=False)
        print(f"Saved detailed results to {DETAILS_OUTPUT_PATH}")
        print(f"Saved failures to {FAILURES_OUTPUT_PATH}")
    else:
        print("No benchmark rows to evaluate yet.")


if __name__ == "__main__":
    main()
