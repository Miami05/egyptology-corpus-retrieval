"""Classify competitive-ambiguity failures so each one points at a concrete fix.

For every failing benchmark query this asks two separate questions:

1. Does a useful parallel exist in the corpus at all?
2. If it exists, where did retrieval rank it?

Those two answers separate a *corpus gap* (nothing to find yet, so import more
rows) from a *ranking problem* (the right parallel is present but ranked too low,
so improve scoring). Without the split, both look identical in the results CSV.
"""

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
from app.services.suggestions import canonical_reading, loose_reading_form

EXAMPLES_PATH = "data/processed/examples.csv"
FAILURES_PATH = "data/benchmarks/competitive_ambiguity_eval_failures.csv"
OUTPUT_PATH = "data/benchmarks/competitive_ambiguity_failure_analysis.csv"

# A query this short carries too little signal for any corpus to disambiguate.
SHORT_QUERY_TOKENS = 2
# Treat a near-miss on the useful-family threshold as a scoring-threshold issue
# rather than a genuine miss.
NEAR_MISS_MARGIN = 0.06

STOP_TOKENS = {"m", "n", "r", "s", "f", "k", "t", "w", "pw", "hr"}


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


def _is_useful(
    candidate_tokens: set[str],
    candidate_lemmas: set[str],
    expected_key_tokens: set[str],
    expected_lemma_ids: set[str],
    token_threshold: float,
) -> tuple[bool, float]:
    """Mirror the eval's useful-family rule so ranks stay comparable."""
    token_score = _overlap(expected_key_tokens, candidate_tokens)
    lemma_intersection = expected_lemma_ids & candidate_lemmas
    lemma_score = (
        len(lemma_intersection) / min(len(expected_lemma_ids), len(candidate_lemmas))
        if expected_lemma_ids and candidate_lemmas
        else 0.0
    )
    if token_score >= token_threshold:
        return True, token_score
    if len(lemma_intersection) >= 2 and lemma_score >= 0.4:
        return True, token_score
    if len(expected_lemma_ids) <= 2 and len(lemma_intersection) >= 1:
        return True, token_score
    return False, token_score


def _classify(
    query_tokens: set[str],
    best_available_score: float,
    useful_exists: bool,
    retrieval_rank: int | None,
    token_threshold: float,
) -> tuple[str, str]:
    content_tokens = query_tokens - STOP_TOKENS
    if len(query_tokens) <= SHORT_QUERY_TOKENS or not content_tokens:
        return (
            "query_too_short",
            "Query carries too few content tokens to identify any reading; "
            "expected behaviour is a low-confidence answer, not a hit.",
        )
    if useful_exists and retrieval_rank is not None and retrieval_rank > 3:
        return (
            "ranking_issue",
            f"A useful parallel exists and retrieval found it at rank {retrieval_rank}, "
            "but it fell outside the top 3. Fix by improving scoring, not by adding data.",
        )
    if useful_exists and retrieval_rank is None:
        return (
            "retrieval_miss",
            "A useful parallel exists in the corpus but retrieval never returned it. "
            "Candidate generation is dropping it before ranking.",
        )
    if best_available_score >= token_threshold - NEAR_MISS_MARGIN:
        return (
            "threshold_too_strict",
            f"Closest parallel scores {best_available_score:.3f} against a threshold of "
            f"{token_threshold:.2f}; a marginal call rather than a real miss.",
        )
    return (
        "corpus_gap",
        "No row in the corpus passes the useful-family test, so there is nothing to "
        "retrieve. Fix by importing more rows in this text family.",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH, help="Corpus CSV that was searched.")
    parser.add_argument("--failures", default=FAILURES_PATH, help="Failures CSV from the eval.")
    parser.add_argument("--output", default=OUTPUT_PATH, help="Where to write the analysis.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    failures_path = Path(args.failures)
    if not failures_path.exists() or failures_path.stat().st_size == 0:
        print(f"No failures file to analyse at {failures_path}")
        return

    failures = pd.read_csv(failures_path).fillna("")
    if failures.empty:
        print("No failures to analyse.")
        return

    examples_df = load_examples_csv(args.examples)
    examples_df = examples_df.assign(
        _tokens=examples_df["transliteration_gold"].map(
            lambda value: _tokens(loose_reading_form(value))
        ),
        _lemmas=examples_df["lemma_sequence"].map(_lemma_ids),
        _canonical=examples_df["transliteration_gold"].map(canonical_reading),
    )

    rows: list[dict[str, object]] = []
    for _, fail in failures.iterrows():
        expected_key = (
            str(fail["expected_source_text_id"]),
            str(fail["expected_source_sentence_id"]),
        )
        pool = examples_df[
            ~(
                (examples_df["source_text_id"].astype(str) == expected_key[0])
                & (examples_df["source_sentence_id"].astype(str) == expected_key[1])
            )
        ].copy()

        query_input = str(fail["query_input"])
        expected_key_tokens = _tokens(fail["expected_key_tokens"])
        expected_lemma_ids = _tokens(fail["expected_lemma_ids"])
        token_threshold = float(fail["acceptable_token_overlap_threshold"])

        # Question 1: does any useful parallel exist in the corpus?
        useful_readings: set[str] = set()
        best_available_score = 0.0
        best_available_reading = ""
        for _, row in pool.iterrows():
            useful, token_score = _is_useful(
                row["_tokens"],
                row["_lemmas"],
                expected_key_tokens,
                expected_lemma_ids,
                token_threshold,
            )
            if token_score > best_available_score:
                best_available_score = token_score
                best_available_reading = row["transliteration_gold"]
            if useful:
                useful_readings.add(row["_canonical"])

        # Question 2: if so, where does retrieval rank the first useful one?
        retrieval_rank: int | None = None
        if useful_readings:
            query_reading_order = (
                query_input if fail["query_type"] == "normalized_reading_order" else ""
            )
            ranked = retrieve_top_k(
                pool,
                query_mdc=query_input,
                query_reading_order=query_reading_order,
                k=len(pool),
            )
            seen: list[str] = []
            for _, row in ranked.iterrows():
                reading = canonical_reading(row["transliteration_gold"])
                if reading in seen:
                    continue
                seen.append(reading)
                if reading in useful_readings:
                    retrieval_rank = len(seen)
                    break

        category, explanation = _classify(
            query_tokens=_tokens(query_input),
            best_available_score=best_available_score,
            useful_exists=bool(useful_readings),
            retrieval_rank=retrieval_rank,
            token_threshold=token_threshold,
        )

        rows.append(
            {
                "benchmark_id": fail["benchmark_id"],
                "query_input": query_input,
                "query_type": fail["query_type"],
                "query_token_count": len(_tokens(query_input)),
                "expected_transliteration": fail["expected_transliteration"],
                "failure_category": category,
                "explanation": explanation,
                "useful_parallel_exists": bool(useful_readings),
                "useful_parallel_count": len(useful_readings),
                "first_useful_retrieval_rank": retrieval_rank if retrieval_rank else "",
                "best_available_token_overlap": round(best_available_score, 3),
                "acceptable_token_overlap_threshold": token_threshold,
                "closest_corpus_reading": best_available_reading,
                "top3_suggestions": fail.get("suggestions", ""),
            }
        )

    analysis = pd.DataFrame(rows)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    analysis.to_csv(output_path, index=False)

    print(f"Analysed {len(analysis)} failures from {failures_path}")
    print()
    print("Failure categories:")
    for category, count in analysis["failure_category"].value_counts().items():
        print(f"  {count:>2}  {category}")
    print()
    actionable = analysis[analysis["failure_category"].isin(["ranking_issue", "retrieval_miss"])]
    print(
        f"Fixable by better ranking: {len(actionable)} | "
        f"needs more corpus data: {int((analysis['failure_category'] == 'corpus_gap').sum())} | "
        f"query genuinely underspecified: "
        f"{int((analysis['failure_category'] == 'query_too_short').sum())}"
    )
    print(f"Saved analysis to {output_path}")


if __name__ == "__main__":
    main()
