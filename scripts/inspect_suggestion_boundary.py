"""Print the top-N suggestion boundary for named benchmark queries.

The evaluation harness records only the top 3, but the interesting number in the
2026-09-05 diagnosis is the rank of the first *accepted* candidate — rank 4 for both
v4 misses — and its confidence margin behind rank 3. This script reproduces the
harness's pipeline exactly (it imports the harness's own stage handling, query path
and `_useful_reason`) with `top_n` raised, so the boundary can be read off directly.

It changes nothing and writes nothing: a read-only probe.

    python scripts/inspect_suggestion_boundary.py --ids COMP_007,COMP_014
    WHYPTOLOGY_SUGGESTION_PRESET=cfg_a python scripts/inspect_suggestion_boundary.py \
        --ids COMP_007,COMP_014

The re-rank configuration is whatever `WHYPTOLOGY_SUGGESTION_PRESET` selects (see
app/services/suggestions.py and docs/v4-answerability-and-v5-rule.md, Experiment 1);
it is printed with the results so a pasted table can never lose its label.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.data.query import parse_query  # noqa: E402
from app.services.retrieval import retrieve_top_k  # noqa: E402
from app.services.stage import (  # noqa: E402
    build_stage_resources,
    infer_stage,
    normalize_stage,
    stage_base_rates,
)
from app.services.suggestions import (  # noqa: E402
    SUGGESTION_PRESET_ENV,
    suggest_top_readings,
)
from scripts.run_competitive_ambiguity_eval import (  # noqa: E402
    _exclude_expected,
    _load_benchmark,
    _tokens,
    _useful_reason,
)

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/competitive_ambiguity_eval_queries_v4.csv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--benchmark", default=BENCHMARK_PATH)
    parser.add_argument("--ids", default="", help="Comma-separated benchmark_ids; empty = all.")
    parser.add_argument("--stage", choices=["none", "auto", "declared"], default="auto")
    parser.add_argument("--query-path", choices=["app", "legacy"], default="app")
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--useful-rule", choices=["v4", "v5"], default="v4")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    wanted = {value.strip() for value in args.ids.split(",") if value.strip()}
    examples_df = load_examples_csv(args.examples)
    benchmark_df = _load_benchmark(args.benchmark)
    pooled_base_rates = stage_base_rates(examples_df)

    preset = os.environ.get(SUGGESTION_PRESET_ENV, "") or "default"
    print(f"suggestion_preset: {preset}")
    print(f"stage_mode: {args.stage}  query_path: {args.query_path}  top_n: {args.top_n}")

    for _, bench_row in benchmark_df.iterrows():
        benchmark_id = str(bench_row["benchmark_id"])
        if wanted and benchmark_id not in wanted:
            continue
        candidate_pool = _exclude_expected(examples_df, bench_row)
        query_input = str(bench_row["query_input"])
        query_reading_order = (
            query_input if bench_row["query_type"] == "normalized_reading_order" else ""
        )

        pooled_cache: list[object] = []

        def pooled() -> object:
            if not pooled_cache:
                pooled_cache.append(build_stage_resources(candidate_pool, None))
            return pooled_cache[0]

        stage: str | None = None
        if args.stage == "declared":
            stage = normalize_stage(bench_row.get("language_stage", ""))
        elif args.stage == "auto":
            first_pass = retrieve_top_k(
                candidate_pool,
                query_mdc=query_input,
                query_reading_order=query_reading_order,
                k=10,
                index=pooled().index if args.query_path == "app" else None,
            )
            stage = infer_stage(first_pass, base_rates=pooled_base_rates)

        if stage is None and args.query_path == "legacy":
            retrieval_frame = candidate_pool
            retrieval_index = None
        elif stage is None:
            retrieval_frame = pooled().frame
            retrieval_index = pooled().index
        else:
            pooled_resources = pooled()
            stage_resources = build_stage_resources(
                candidate_pool,
                stage,
                pooled_reading_model=pooled_resources.reading_model,
                pooled_index=pooled_resources.index,
            )
            retrieval_frame = stage_resources.frame
            retrieval_index = stage_resources.index

        retrieval_results = retrieve_top_k(
            retrieval_frame,
            query_mdc=query_input,
            query_reading_order=query_reading_order,
            k=min(50, len(retrieval_frame)),
            index=retrieval_index,
        )
        suggestion_query = query_input
        if args.query_path == "app":
            searched = parse_query(
                query_input,
                vocabulary=retrieval_index.vocabulary if retrieval_index is not None else None,
            )
            suggestion_query = searched.reading or query_input

        suggestions = suggest_top_readings(
            retrieval_results,
            query_mdc=suggestion_query,
            query_reading_order=query_reading_order,
            top_n=args.top_n,
        )
        expected = str(bench_row["expected_transliteration"])
        expected_key_tokens = _tokens(bench_row["expected_key_tokens"])
        expected_lemma_ids = _tokens(bench_row["expected_lemma_ids"])
        token_threshold = float(bench_row["acceptable_token_overlap_threshold"])

        print()
        print(f"### {benchmark_id}  stage_used={stage or 'None'}  threshold={token_threshold}")
        print("| rank | confidence | useful | token | lemma | source | reading |")
        print("|---|---|---|---|---|---|---|")
        first_useful_rank = None
        for rank, suggestion in enumerate(suggestions, start=1):
            useful, _reason, token_score, lemma_score = _useful_reason(
                suggestion.candidate_transliteration,
                candidate_pool=candidate_pool,
                expected=expected,
                expected_key_tokens=expected_key_tokens,
                expected_lemma_ids=expected_lemma_ids,
                token_threshold=token_threshold,
                rule=args.useful_rule,
            )
            if useful and first_useful_rank is None:
                first_useful_rank = rank
            source = suggestion.supporting_sources[0] if suggestion.supporting_sources else ""
            print(
                f"| {rank} | {suggestion.confidence_score:.4f} | "
                f"{'yes' if useful else 'no'} | {token_score:.3f} | {lemma_score:.3f} | "
                f"{source} | `{suggestion.candidate_transliteration}` |"
            )
        if first_useful_rank is None:
            print(f"first accepted candidate: none in top {args.top_n}")
        else:
            rank3 = suggestions[2].confidence_score if len(suggestions) >= 3 else float("nan")
            accepted = suggestions[first_useful_rank - 1].confidence_score
            print(
                f"first accepted candidate: rank {first_useful_rank} at {accepted:.4f}; "
                f"rank 3 at {rank3:.4f}; margin {rank3 - accepted:+.4f}"
            )


if __name__ == "__main__":
    main()
