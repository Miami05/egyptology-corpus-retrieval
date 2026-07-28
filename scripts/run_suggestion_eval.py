from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.data.normalizer import normalize_mdc, normalize_transliteration
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import suggest_top_readings

EXAMPLES_PATH = "data/processed/examples.csv"
DETAILS_OUTPUT_PATH = "data/benchmarks/suggestion_eval_results.csv"
FAILURES_OUTPUT_PATH = "data/benchmarks/suggestion_eval_failures.csv"


def _row_key(row: pd.Series) -> tuple[str, str, str]:
    return (
        str(row["source"]),
        str(row["source_text_id"]),
        str(row["source_sentence_id"]),
    )


def _exclude_row(df: pd.DataFrame, target: pd.Series) -> pd.DataFrame:
    target_key = _row_key(target)
    mask = df.apply(lambda row: _row_key(row) != target_key, axis=1)
    return df.loc[mask, :].copy()


def _rank_gold(gold: str, candidates: list[str]) -> int | None:
    gold_norm = _canonical(gold)
    for index, candidate in enumerate(candidates, start=1):
        if _canonical(candidate) == gold_norm:
            return index
    return None


def _canonical(value: object) -> str:
    return normalize_mdc(normalize_transliteration(str(value)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Number of rows to evaluate. Default 0 evaluates every imported row.",
    )
    parser.add_argument(
        "--include-self",
        action="store_true",
        help="Evaluate against the full corpus instead of leave-one-out rows.",
    )
    parser.add_argument(
        "--examples",
        default=EXAMPLES_PATH,
        help="Corpus CSV to evaluate, so different corpus sizes can be compared.",
    )
    parser.add_argument(
        "--details",
        default=DETAILS_OUTPUT_PATH,
        help="Where to write per-query details.",
    )
    parser.add_argument(
        "--failures",
        default=FAILURES_OUTPUT_PATH,
        help="Where to write failing rows.",
    )
    args = parser.parse_args()

    examples_df = load_examples_csv(args.examples)
    test_df = examples_df.head(args.limit).copy() if args.limit else examples_df.copy()

    rows: list[dict] = []
    top1_hits = 0
    top3_hits = 0
    reciprocal_rank_sum = 0.0

    for row_num, (_, test_row) in enumerate(test_df.iterrows(), start=1):
        corpus_df = examples_df if args.include_self else _exclude_row(examples_df, test_row)
        if corpus_df.empty:
            retrieval_results = pd.DataFrame()
            suggestions = []
        else:
            retrieval_results = retrieve_top_k(
                corpus_df,
                query_mdc=str(test_row["mdc"]),
                query_reading_order=str(test_row["normalized_reading_order"]),
                k=min(50, len(corpus_df)),
            )
            suggestions = suggest_top_readings(
                retrieval_results,
                query_mdc=str(test_row["mdc"]),
                query_reading_order=str(test_row["normalized_reading_order"]),
                top_n=3,
            )

        candidates = [suggestion.candidate_transliteration for suggestion in suggestions]
        rank = _rank_gold(str(test_row["transliteration_gold"]), candidates)
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
                "test_id": f"SUG_{row_num:03d}",
                "source": test_row["source"],
                "source_text_id": test_row["source_text_id"],
                "source_sentence_id": test_row["source_sentence_id"],
                "query_mdc": test_row["mdc"],
                "gold_transliteration": test_row["transliteration_gold"],
                "gold_canonical": _canonical(test_row["transliteration_gold"]),
                "rank_of_gold": rank if rank is not None else "",
                "top1_hit": bool(top1_hit),
                "top3_hit": bool(top3_hit),
                "suggestions": " || ".join(candidates),
                "suggestion_canonicals": " || ".join(
                    _canonical(candidate) for candidate in candidates
                ),
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
                "evaluation_mode": "include_self" if args.include_self else "leave_one_out",
            }
        )

    details_df = pd.DataFrame(rows)
    total = len(details_df)
    summary = {
        "total_queries": total,
        "top1_accuracy": round(top1_hits / total, 4) if total else 0.0,
        "top3_accuracy": round(top3_hits / total, 4) if total else 0.0,
        "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
        "failures": int((~details_df["top3_hit"]).sum()) if total else 0,
    }

    print("Suggestion evaluation summary:")
    print(f"corpus_rows: {len(examples_df)}")
    print(f"evaluation_mode: {'include_self' if args.include_self else 'leave_one_out'}")
    for key, value in summary.items():
        print(f"{key}: {value}")

    details_path = Path(args.details)
    failures_path = Path(args.failures)
    details_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    details_df.to_csv(details_path, index=False)
    failures_df = (
        details_df[details_df["top3_hit"] == False].copy()  # noqa: E712
        if not details_df.empty
        else pd.DataFrame()
    )
    failures_df.to_csv(failures_path, index=False)
    print(f"Saved suggestion details to {details_path}")
    print(f"Saved suggestion failures to {failures_path}")


if __name__ == "__main__":
    main()
