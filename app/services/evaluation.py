from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.retrieval import retrieve_top_k

BENCHMARK_REQUIRED_COLUMNS = [
    "benchmark_id",
    "query_mdc",
    "query_normalized_reading_order",
    "expected_source",
    "expected_source_text_id",
    "expected_source_sentence_id",
]


def load_benchmark_csv(path: str) -> pd.DataFrame:
    benchmark_path = Path(path)
    if not benchmark_path.exists():
        return pd.DataFrame(columns=pd.Index(BENCHMARK_REQUIRED_COLUMNS + ["notes"]))
    df = pd.read_csv(benchmark_path).fillna("")
    missing = [col for col in BENCHMARK_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing benchmark columns: {missing}")
    return df


def evaluate_benchmark(
    examples_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    k: int = 3,
) -> tuple[dict, pd.DataFrame]:
    if benchmark_df.empty:
        return {
            "total_queries": 0,
            "top1": 0.0,
            "top3": 0.0,
            "mrr": 0.0,
            "failures": 0,
        }, pd.DataFrame()
    rows: list[dict] = []
    top1_hits = 0
    top3_hits = 0
    reciprocal_rank_sum = 0.0
    for _, bench_row in benchmark_df.iterrows():
        results = retrieve_top_k(
            examples_df,
            query_mdc=str(bench_row["query_mdc"]),
            query_reading_order=str(bench_row["query_normalized_reading_order"]),
            k=k,
        )
        expected_key = (
            str(bench_row["expected_source"]),
            str(bench_row["expected_source_text_id"]),
            str(bench_row["expected_source_sentence_id"]),
        )
        returned_keys = [
            (
                str(row["source"]),
                str(row["source_text_id"]),
                str(row["source_sentence_id"]),
            )
            for _, row in results.iterrows()
        ]
        returned_scores = (
            [float(score) for score in results["final_score"].tolist()]
            if not results.empty
            else []
        )
        expected_rank = None
        for i, key in enumerate(returned_keys, start=1):
            if key == expected_key:
                expected_rank = i
                break
        top1_hit = expected_rank == 1
        top3_hit = expected_rank is not None and expected_rank <= k
        if top1_hit:
            top1_hits += 1
        if top3_hit:
            top3_hits += 1
        if expected_rank is not None:
            reciprocal_rank_sum += 1.0 / expected_rank
        rows.append(
            {
                "benchmark_id": bench_row["benchmark_id"],
                "query_mdc": bench_row["query_mdc"],
                "query_normalized_reading_order": bench_row[
                    "query_normalized_reading_order"
                ],
                "expected_source": expected_key[0],
                "expected_source_text_id": expected_key[1],
                "expected_source_sentence_id": expected_key[2],
                "expected_rank": expected_rank if expected_rank is not None else "",
                "top1_hit": bool(top1_hit),
                "top3_hit": bool(top3_hit),
                "returned_keys": " || ".join(
                    [f"{a}/{b}/{c}" for a, b, c in returned_keys]
                ),
                "returned_scores": " || ".join(
                    [f"{score:.4f}" for score in returned_scores]
                ),
            }
        )
    details_df = pd.DataFrame(rows)
    total = len(details_df)
    failures = int((~details_df["top3_hit"]).sum()) if not details_df.empty else 0
    summary = {
        "total_queries": total,
        "top1": round(top1_hits / total, 4) if total else 0.0,
        "top3": round(top3_hits / total, 4) if total else 0.0,
        "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
        "failures": failures,
    }
    return summary, details_df
