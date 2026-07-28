from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import canonical_reading, suggest_top_readings

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/ambiguous_reading_eval_queries.csv"
RESULTS_PATH = "data/benchmarks/ambiguous_suggestion_eval_results.csv"
FAILURES_PATH = "data/benchmarks/ambiguous_suggestion_eval_failures.csv"

REQUIRED_COLUMNS = [
    "benchmark_id",
    "query_input",
    "query_type",
    "expected_transliteration",
    "expected_source_text_id",
    "expected_source_sentence_id",
    "notes",
]


def _rank_expected(expected: str, candidates: list[str]) -> int | None:
    expected_key = canonical_reading(expected)
    for rank, candidate in enumerate(candidates, start=1):
        if canonical_reading(candidate) == expected_key:
            return rank
    return None


def _load_benchmark() -> pd.DataFrame:
    path = Path(BENCHMARK_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"{BENCHMARK_PATH} not found. Run scripts.build_ambiguous_benchmark first."
        )
    df = pd.read_csv(path).fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing ambiguous benchmark columns: {missing}")
    return df


def main() -> None:
    examples_df = load_examples_csv(EXAMPLES_PATH)
    benchmark_df = _load_benchmark()

    rows: list[dict[str, object]] = []
    top1_hits = 0
    top3_hits = 0
    reciprocal_rank_sum = 0.0

    for _, bench_row in benchmark_df.iterrows():
        query_input = str(bench_row["query_input"])
        query_reading_order = (
            query_input
            if bench_row["query_type"] == "normalized_reading_order"
            else ""
        )
        retrieval_results = retrieve_top_k(
            examples_df,
            query_mdc=query_input,
            query_reading_order=query_reading_order,
            k=min(50, len(examples_df)),
        )
        suggestions = suggest_top_readings(
            retrieval_results,
            query_mdc=query_input,
            query_reading_order=query_reading_order,
            top_n=3,
            include_query_candidate=False,
        )
        candidates = [suggestion.candidate_transliteration for suggestion in suggestions]
        rank = _rank_expected(str(bench_row["expected_transliteration"]), candidates)
        top1_hit = rank == 1
        top3_hit = rank is not None and rank <= 3
        if top1_hit:
            top1_hits += 1
        if top3_hit:
            top3_hits += 1
        if rank is not None:
            reciprocal_rank_sum += 1.0 / rank

        rows.append(
            {
                "benchmark_id": bench_row["benchmark_id"],
                "query_input": query_input,
                "query_type": bench_row["query_type"],
                "expected_transliteration": bench_row["expected_transliteration"],
                "expected_source_text_id": bench_row["expected_source_text_id"],
                "expected_source_sentence_id": bench_row["expected_source_sentence_id"],
                "rank_of_expected": rank if rank is not None else "",
                "top1_hit": bool(top1_hit),
                "top3_hit": bool(top3_hit),
                "suggestions": " || ".join(candidates),
                "confidence_scores": " || ".join(
                    f"{suggestion.confidence_score:.3f}" for suggestion in suggestions
                ),
                "evidence_summaries": " || ".join(
                    suggestion.evidence_summary for suggestion in suggestions
                ),
                "supporting_sources": " || ".join(
                    "; ".join(suggestion.supporting_sources)
                    for suggestion in suggestions
                ),
                "notes": bench_row["notes"],
            }
        )

    results_df = pd.DataFrame(rows)
    total = len(results_df)
    failures = (
        int((~results_df["top3_hit"]).sum()) if not results_df.empty else 0
    )
    summary = {
        "total_queries": total,
        "top1_accuracy": round(top1_hits / total, 4) if total else 0.0,
        "top3_accuracy": round(top3_hits / total, 4) if total else 0.0,
        "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
        "failures": failures,
    }

    print("Ambiguous suggestion evaluation summary:")
    print("evaluation_mode: include_self (the expected row stays in the corpus)")
    print(
        "NOTE: this is a retrieval sanity check, not a disambiguation score. Because "
        "the expected row is still searchable, near-perfect accuracy is the expected "
        "result and does not measure generalisation. Use the competitive ambiguity "
        "benchmark, which excludes the target row, for reportable accuracy."
    )
    for key, value in summary.items():
        print(f"{key}: {value}")

    Path("data/benchmarks").mkdir(parents=True, exist_ok=True)
    results_df.to_csv(RESULTS_PATH, index=False)
    failures_df = (
        results_df[results_df["top3_hit"] == False].copy()  # noqa: E712
        if not results_df.empty
        else pd.DataFrame()
    )
    failures_df.to_csv(FAILURES_PATH, index=False)
    print(f"Saved ambiguous suggestion results to {RESULTS_PATH}")
    print(f"Saved ambiguous suggestion failures to {FAILURES_PATH}")


if __name__ == "__main__":
    main()
