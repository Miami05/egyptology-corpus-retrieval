"""Experiment 2, step 0 — the pre-check (kill switch). Read-only.

For each named benchmark query this reproduces the harness pipeline exactly (the
same stage handling, the same `--query-path` branch, the same `_useful_reason`),
raises `top_n`, and prints for every candidate:

* the ranker's **own** per-term breakdown (each live signal's weight, raw value and
  weighted contribution, the weight mass, the confidence) — read out of
  `suggest_top_readings` through its `debug_signals` observation hook, not
  recomputed here;
* whether the candidate is useful under the harness's own `_useful_reason`;
* the query-bigram count of `app.services.adjacency`.

It changes nothing and writes nothing but its report. Several benchmark files can
be given at once so the 130k-row corpus is loaded a single time.

    python scripts/inspect_adjacency_precheck.py \
        --case data/benchmarks/competitive_ambiguity_eval_queries_v4.csv:COMP_007,COMP_014 \
        --case data/benchmarks/..._holdout_2026-09-05.csv:HOLD_001,HOLD_002
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
from app.services.adjacency import (  # noqa: E402
    adjacency_tokens,
    count_matches,
    query_bigrams,
)
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

SIGNAL_ORDER = [
    "relative_score",
    "mean_score",
    "translit_overlap",
    "char_similarity",
    "exact_or_near",
    "reading_similarity",
    "support",
    "lemma_density",
    "glyph_similarity",
    "glyph_exact",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="benchmark_csv_path:ID1,ID2 — repeatable.",
    )
    parser.add_argument("--stage", choices=["none", "auto", "declared"], default="auto")
    parser.add_argument("--query-path", choices=["app", "legacy"], default="app")
    parser.add_argument("--top-n", type=int, default=6)
    parser.add_argument("--useful-rule", choices=["v4", "v5"], default="v4")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    examples_df = load_examples_csv(args.examples)
    pooled_base_rates = stage_base_rates(examples_df)

    preset = os.environ.get(SUGGESTION_PRESET_ENV, "") or "default"
    print(f"corpus_rows: {len(examples_df)}")
    print(f"suggestion_preset: {preset}")
    print(f"stage_mode: {args.stage}  query_path: {args.query_path}  top_n: {args.top_n}")
    print("tokenizer: tokenize_query(loose_reading_form(text))  [app.services.adjacency]")

    summary: list[tuple[str, object, list[int], object]] = []

    for case in args.case:
        benchmark_path, _, id_blob = case.partition(":")
        wanted = [value.strip() for value in id_blob.split(",") if value.strip()]
        benchmark_df = _load_benchmark(benchmark_path)
        print()
        print(f"===== benchmark: {benchmark_path}")

        for _, bench_row in benchmark_df.iterrows():
            benchmark_id = str(bench_row["benchmark_id"])
            if wanted and benchmark_id not in wanted:
                continue
            candidate_pool = _exclude_expected(examples_df, bench_row)
            query_input = str(bench_row["query_input"])
            query_reading_order = (
                query_input
                if bench_row["query_type"] == "normalized_reading_order"
                else ""
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
                    vocabulary=(
                        retrieval_index.vocabulary if retrieval_index is not None else None
                    ),
                )
                suggestion_query = searched.reading or query_input

            debug: list[dict] = []
            suggestions = suggest_top_readings(
                retrieval_results,
                query_mdc=suggestion_query,
                query_reading_order=query_reading_order,
                top_n=args.top_n,
                debug_signals=debug,
            )
            by_candidate = {
                (entry["candidate_transliteration"], entry["confidence_score"]): entry
                for entry in debug
            }

            expected = str(bench_row["expected_transliteration"])
            expected_key_tokens = _tokens(bench_row["expected_key_tokens"])
            expected_lemma_ids = _tokens(bench_row["expected_lemma_ids"])
            token_threshold = float(bench_row["acceptable_token_overlap_threshold"])

            # The bigram side. The query token sequence is the one the ranker
            # itself was handed (`suggestion_query`), folded and tokenised by
            # app.services.adjacency.
            q_tokens = adjacency_tokens(suggestion_query)
            bigrams = query_bigrams(q_tokens)

            print()
            print(
                f"### {benchmark_id}  stage_used={stage or 'None'}  "
                f"threshold={token_threshold}"
            )
            print(f"query_input: {query_input!r}")
            print(f"suggestion_query: {suggestion_query!r}")
            print(f"query_tokens: {q_tokens}")
            print(
                f"eligible query bigrams ({len(bigrams)}): "
                + ", ".join(
                    f"({left},{right}{'' if gap == 0 else ',gap1'})"
                    for left, right, gap in bigrams
                )
            )

            header = (
                "| rank | conf | useful | bigrams | ev_token | ev_lemma | "
                + " | ".join(SIGNAL_ORDER)
                + " | mass | reading |"
            )
            print(header)
            print("|" + "---|" * (header.count("|") - 1))

            counts: list[int] = []
            first_useful_rank: int | None = None
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
                candidate_tokens = adjacency_tokens(
                    suggestion.candidate_transliteration
                )
                matched = count_matches(bigrams, candidate_tokens)
                counts.append(matched)

                entry = by_candidate.get(
                    (
                        suggestion.candidate_transliteration,
                        suggestion.confidence_score,
                    )
                )
                cells = []
                for name in SIGNAL_ORDER:
                    if entry is None or name not in entry["signals"]:
                        cells.append("-")
                        continue
                    term = entry["signals"][name]
                    cells.append(
                        f"{term['weight']:.2f}x{term['value']:.4f}={term['weighted']:.4f}"
                    )
                mass = f"{entry['weight_mass']:.2f}" if entry else "-"
                print(
                    f"| {rank} | {suggestion.confidence_score:.4f} | "
                    f"{'YES' if useful else 'no'} | {matched} | "
                    f"{token_score:.3f} | {lemma_score:.3f} | "
                    + " | ".join(cells)
                    + f" | {mass} | `{suggestion.candidate_transliteration}` |"
                )

            if first_useful_rank is None:
                print(f"first useful candidate: none in top {args.top_n}")
                summary.append((benchmark_id, None, counts, None))
            else:
                above = counts[: first_useful_rank - 1]
                beaten = all(counts[first_useful_rank - 1] > value for value in above)
                print(
                    f"first useful candidate: rank {first_useful_rank}, "
                    f"bigrams {counts[first_useful_rank - 1]}; "
                    f"ranks above: {above}; beaten: {'yes' if beaten else 'no'}"
                )
                summary.append((benchmark_id, first_useful_rank, counts, beaten))

    print()
    print("===== PRE-CHECK SUMMARY")
    print("| id | first-useful rank | bigram counts ranks 1..k | beaten |")
    print("|---|---|---|---|")
    passes = 0
    for benchmark_id, rank, counts, beaten in summary:
        if rank is None:
            print(f"| {benchmark_id} | none in top {args.top_n} | {counts} | n/a |")
            continue
        if beaten:
            passes += 1
        print(
            f"| {benchmark_id} | {rank} | {counts[:rank]} | "
            f"{'yes' if beaten else 'no'} |"
        )
    verdict = "PASS" if passes >= 4 else "FAIL"
    print(f"pre-check: {verdict} {passes}/{len(summary)} (rule: >= 4 of 7 beaten)")


if __name__ == "__main__":
    main()
