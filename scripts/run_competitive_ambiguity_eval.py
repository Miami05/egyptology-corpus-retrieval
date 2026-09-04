from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.retrieval import retrieve_top_k
from app.services.stage import compatible_frame, infer_stage
from app.services.suggestions import canonical_reading, loose_reading_form, suggest_top_readings

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/competitive_ambiguity_eval_queries.csv"
RESULTS_PATH = "data/benchmarks/competitive_ambiguity_eval_results.csv"
FAILURES_PATH = "data/benchmarks/competitive_ambiguity_eval_failures.csv"

# expected_source_text_id prefix -> declared language_stage (item A, --stage declared).
# Anything else (an id with no recognised prefix, or blank) declares no stage.
DECLARED_STAGE_PREFIXES: list[tuple[str, str]] = [
    ("TLA_EARLIER_", "Earlier Egyptian"),
    ("TLA_LATE_", "Late Egyptian"),
    ("TLA_DEMOTIC_", "Demotic"),
]


def _declared_stage(expected_source_text_id: object) -> str | None:
    text = str(expected_source_text_id)
    for prefix, stage in DECLARED_STAGE_PREFIXES:
        if text.startswith(prefix):
            return stage
    return None


REQUIRED_COLUMNS = [
    "benchmark_id",
    "query_input",
    "query_type",
    "expected_transliteration",
    "expected_source_text_id",
    "expected_source_sentence_id",
    "expected_key_tokens",
    "expected_lemma_ids",
    "acceptable_token_overlap_threshold",
    "notes",
]


def _row_key(row: pd.Series) -> tuple[str, str]:
    return str(row["source_text_id"]), str(row["source_sentence_id"])


def _exclude_expected(examples_df: pd.DataFrame, bench_row: pd.Series) -> pd.DataFrame:
    expected_key = (
        str(bench_row["expected_source_text_id"]),
        str(bench_row["expected_source_sentence_id"]),
    )
    mask = examples_df.apply(lambda row: _row_key(row) != expected_key, axis=1)
    return examples_df.loc[mask, :].copy()


def _tokens(value: object) -> set[str]:
    return {token for token in str(value).split() if token.strip()}


def _lemma_ids(value: object) -> set[str]:
    ids: set[str] = set()
    for part in str(value).split():
        lemma_id = part.split("|", 1)[0].strip()
        if lemma_id:
            ids.add(lemma_id)
    return ids


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _candidate_lemmas(
    examples_df: pd.DataFrame,
    candidate_transliteration: str,
) -> set[str]:
    candidate_key = canonical_reading(candidate_transliteration)
    matches = examples_df[
        examples_df["transliteration_gold"].map(canonical_reading) == candidate_key
    ]
    ids: set[str] = set()
    for value in matches["lemma_sequence"].tolist():
        ids |= _lemma_ids(value)
    return ids


def _useful_reason(
    candidate: str,
    candidate_pool: pd.DataFrame,
    expected: str,
    expected_key_tokens: set[str],
    expected_lemma_ids: set[str],
    token_threshold: float,
) -> tuple[bool, str, float, float]:
    if canonical_reading(candidate) == canonical_reading(expected):
        return True, "exact expected transliteration", 1.0, 1.0

    candidate_tokens = _tokens(loose_reading_form(candidate))
    token_score = _overlap(expected_key_tokens, candidate_tokens)
    candidate_lemmas = _candidate_lemmas(candidate_pool, candidate)
    lemma_intersection = expected_lemma_ids & candidate_lemmas
    lemma_score = (
        len(lemma_intersection) / min(len(expected_lemma_ids), len(candidate_lemmas))
        if expected_lemma_ids and candidate_lemmas
        else 0.0
    )

    if token_score >= token_threshold:
        shared = ", ".join(sorted(expected_key_tokens & candidate_tokens)[:8])
        return True, f"useful token-family match: {shared}", token_score, lemma_score

    if len(lemma_intersection) >= 2 and lemma_score >= 0.4:
        shared = ", ".join(sorted(lemma_intersection)[:8])
        return True, f"useful lemma-family match: {shared}", token_score, lemma_score

    if len(expected_lemma_ids) <= 2 and len(lemma_intersection) >= 1:
        shared = ", ".join(sorted(lemma_intersection)[:8])
        return True, f"useful short lemma-family match: {shared}", token_score, lemma_score

    return False, "no useful-family match", token_score, lemma_score


def _load_benchmark(benchmark_path: str = BENCHMARK_PATH) -> pd.DataFrame:
    path = Path(benchmark_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{benchmark_path} not found. Run scripts.build_competitive_ambiguity_benchmark first."
        )
    df = pd.read_csv(path).fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing competitive benchmark columns: {missing}")
    return df


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the competitive ambiguity benchmark. Paths are configurable so the "
            "same frozen benchmark can be replayed against different corpus sizes."
        )
    )
    parser.add_argument("--examples", default=EXAMPLES_PATH, help="Corpus CSV to search.")
    parser.add_argument("--benchmark", default=BENCHMARK_PATH, help="Benchmark queries CSV.")
    parser.add_argument("--results", default=RESULTS_PATH, help="Where to write per-query results.")
    parser.add_argument("--failures", default=FAILURES_PATH, help="Where to write failing rows.")
    parser.add_argument(
        "--label",
        default="",
        help="Optional run label printed with the summary (e.g. 'corpus=300').",
    )
    parser.add_argument(
        "--stage",
        choices=["none", "auto", "declared"],
        default="none",
        help=(
            "Language-stage handling (item A). 'none' (default) reproduces today's "
            "pooled retrieval exactly. 'declared' restricts the candidate pool to "
            "rows compatible with the stage implied by expected_source_text_id's "
            "prefix (TLA_EARLIER_/TLA_LATE_/TLA_DEMOTIC_). 'auto' infers the stage "
            "per query from a first retrieval pass over the pooled pool."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    examples_df = load_examples_csv(args.examples)
    benchmark_df = _load_benchmark(args.benchmark)

    rows: list[dict[str, object]] = []
    top1_exact_hits = 0
    top3_exact_hits = 0
    top1_useful_hits = 0
    top3_useful_hits = 0
    reciprocal_rank_sum = 0.0

    stages_used: list[str] = []
    for _, bench_row in benchmark_df.iterrows():
        candidate_pool = _exclude_expected(examples_df, bench_row)
        query_input = str(bench_row["query_input"])
        query_reading_order = (
            query_input
            if bench_row["query_type"] == "normalized_reading_order"
            else ""
        )

        # Item A: which rows may stand as evidence for this query. 'none' leaves
        # candidate_pool untouched, so that mode reproduces today's numbers exactly.
        stage: str | None = None
        if args.stage == "declared":
            stage = _declared_stage(bench_row["expected_source_text_id"])
        elif args.stage == "auto":
            first_pass = retrieve_top_k(
                candidate_pool,
                query_mdc=query_input,
                query_reading_order=query_reading_order,
                k=10,
            )
            stage = infer_stage(first_pass)
        stages_used.append(stage or "")
        if stage is not None:
            candidate_pool = compatible_frame(candidate_pool, stage)

        retrieval_results = retrieve_top_k(
            candidate_pool,
            query_mdc=query_input,
            query_reading_order=query_reading_order,
            k=min(50, len(candidate_pool)),
        )
        suggestions = suggest_top_readings(
            retrieval_results,
            query_mdc=query_input,
            query_reading_order=query_reading_order,
            top_n=3,
        )
        candidates = [suggestion.candidate_transliteration for suggestion in suggestions]
        expected = str(bench_row["expected_transliteration"])
        expected_key_tokens = _tokens(bench_row["expected_key_tokens"])
        expected_lemma_ids = _tokens(bench_row["expected_lemma_ids"])
        token_threshold = float(bench_row["acceptable_token_overlap_threshold"])

        exact_rank = None
        useful_rank = None
        useful_reasons: list[str] = []
        token_scores: list[str] = []
        lemma_scores: list[str] = []
        for rank, candidate in enumerate(candidates, start=1):
            if exact_rank is None and canonical_reading(candidate) == canonical_reading(expected):
                exact_rank = rank
            useful, reason, token_score, lemma_score = _useful_reason(
                candidate,
                candidate_pool=candidate_pool,
                expected=expected,
                expected_key_tokens=expected_key_tokens,
                expected_lemma_ids=expected_lemma_ids,
                token_threshold=token_threshold,
            )
            useful_reasons.append(reason)
            token_scores.append(f"{token_score:.3f}")
            lemma_scores.append(f"{lemma_score:.3f}")
            if useful and useful_rank is None:
                useful_rank = rank

        if exact_rank == 1:
            top1_exact_hits += 1
        if exact_rank is not None and exact_rank <= 3:
            top3_exact_hits += 1
        if useful_rank == 1:
            top1_useful_hits += 1
        if useful_rank is not None and useful_rank <= 3:
            top3_useful_hits += 1
        if useful_rank is not None:
            reciprocal_rank_sum += 1.0 / useful_rank

        rows.append(
            {
                "benchmark_id": bench_row["benchmark_id"],
                "query_input": query_input,
                "query_type": bench_row["query_type"],
                "expected_transliteration": expected,
                "expected_source_text_id": bench_row["expected_source_text_id"],
                "expected_source_sentence_id": bench_row["expected_source_sentence_id"],
                "expected_key_tokens": bench_row["expected_key_tokens"],
                "expected_lemma_ids": bench_row["expected_lemma_ids"],
                "acceptable_token_overlap_threshold": token_threshold,
                "stage_mode": args.stage,
                "stage_used": stage or "",
                "exact_rank": exact_rank if exact_rank is not None else "",
                "useful_family_rank": useful_rank if useful_rank is not None else "",
                "top1_exact_hit": exact_rank == 1,
                "top3_exact_hit": exact_rank is not None and exact_rank <= 3,
                "top1_useful_family_hit": useful_rank == 1,
                "top3_useful_family_hit": useful_rank is not None and useful_rank <= 3,
                "suggestions": " || ".join(candidates),
                "confidence_scores": " || ".join(
                    f"{suggestion.confidence_score:.3f}" for suggestion in suggestions
                ),
                "evidence_summaries": " || ".join(
                    suggestion.evidence_summary for suggestion in suggestions
                ),
                "useful_family_reasons": " || ".join(useful_reasons),
                "expected_token_overlap_scores": " || ".join(token_scores),
                "expected_lemma_overlap_scores": " || ".join(lemma_scores),
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
        int((~results_df["top3_useful_family_hit"]).sum())
        if not results_df.empty
        else 0
    )
    summary = {
        "corpus_rows": len(examples_df),
        "total_queries": total,
        "stage_mode": args.stage,
        "top1_exact_accuracy": round(top1_exact_hits / total, 4) if total else 0.0,
        "top3_exact_accuracy": round(top3_exact_hits / total, 4) if total else 0.0,
        "top1_useful_family_accuracy": round(top1_useful_hits / total, 4) if total else 0.0,
        "top3_useful_family_accuracy": round(top3_useful_hits / total, 4) if total else 0.0,
        "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
        "failures": failures,
    }
    if args.stage != "none":
        summary["stages_used"] = dict(pd.Series(stages_used).value_counts())

    heading = "Competitive ambiguity evaluation summary"
    if args.label:
        heading = f"{heading} [{args.label}]"
    print(f"{heading}:")
    for key, value in summary.items():
        print(f"{key}: {value}")

    results_path = Path(args.results)
    failures_path = Path(args.failures)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(results_path, index=False)
    failures_df = (
        results_df[results_df["top3_useful_family_hit"] == False].copy()  # noqa: E712
        if not results_df.empty
        else pd.DataFrame()
    )
    failures_df.to_csv(failures_path, index=False)
    print(f"Saved competitive ambiguity results to {results_path}")
    print(f"Saved competitive ambiguity failures to {failures_path}")


if __name__ == "__main__":
    main()
