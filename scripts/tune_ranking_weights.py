"""Tune ranking weights on a tune split and report on a held-out split.

Why the split matters: the benchmark's useful-family metric is partly defined by
token and lemma overlap, and the ranker uses overlap signals too. Sweeping weights
against the same queries we then report would optimise the metric rather than the
tool, exactly the way the near-duplicate leak did. So the benchmark is split by
index, weights are chosen using only the tune half, and the headline number comes
from the holdout half, scored once.

Speed: the per-signal columns (fuzzy, tfidf, overlap, idf overlap, ...) do not
depend on the weights, so they are computed once per query and cached. Evaluating a
weight configuration is then a weighted sum over cached columns.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.retrieval.scorer import DEFAULT_WEIGHTS, WEIGHT_COLUMNS, ScoreWeights
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import (
    DEFAULT_SUGGESTION_WEIGHTS,
    SuggestionWeights,
    canonical_reading,
    loose_reading_form,
    suggest_top_readings,
)

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/competitive_ambiguity_eval_queries.csv"
OUTPUT_PATH = "data/benchmarks/ranking_weight_tuning.csv"

# Signals that are always dead on the current corpus are not worth sweeping; they
# are kept in the weight object so a richer corpus can switch them back on.
TUNABLE = ["fuzzy", "tfidf", "overlap", "idf_overlap", "exact", "reading_order"]


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


def build_query_cache(
    examples_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
) -> list[dict]:
    """Score every candidate once per query and keep the signal columns."""
    cache: list[dict] = []
    signal_columns = list(WEIGHT_COLUMNS.values())

    for _, bench in benchmark_df.iterrows():
        expected_key = (
            str(bench["expected_source_text_id"]),
            str(bench["expected_source_sentence_id"]),
        )
        pool = examples_df[
            ~(
                (examples_df["source_text_id"].astype(str) == expected_key[0])
                & (examples_df["source_sentence_id"].astype(str) == expected_key[1])
            )
        ].copy()

        query = str(bench["query_input"])
        reading_order = (
            query if bench["query_type"] == "normalized_reading_order" else ""
        )
        # k = whole pool so re-ranking can move any candidate into the top 3.
        scored = retrieve_top_k(
            pool,
            query_mdc=query,
            query_reading_order=reading_order,
            k=len(pool),
        )

        # Canonical reading -> lemma ids, so the useful-family test does not rescan
        # the pool for every candidate of every weight configuration.
        lemma_by_reading: dict[str, set[str]] = {}
        for _, row in pool.iterrows():
            key = canonical_reading(row["transliteration_gold"])
            lemma_by_reading.setdefault(key, set()).update(
                _lemma_ids(row["lemma_sequence"])
            )

        cache.append(
            {
                "benchmark_id": bench["benchmark_id"],
                "query": query,
                "reading_order": reading_order,
                "scored": scored,
                "signal_columns": [c for c in signal_columns if c in scored.columns],
                "expected": str(bench["expected_transliteration"]),
                "expected_key_tokens": _tokens(bench["expected_key_tokens"]),
                "expected_lemma_ids": _tokens(bench["expected_lemma_ids"]),
                "threshold": float(bench["acceptable_token_overlap_threshold"]),
                "lemma_by_reading": lemma_by_reading,
            }
        )
    return cache


def _rescore(entry: dict, weights: ScoreWeights) -> pd.DataFrame:
    """Recompute final_score from cached signals, mirroring combine_scores."""
    scored = entry["scored"]
    active: dict[str, float] = {}
    for field, column in WEIGHT_COLUMNS.items():
        weight = getattr(weights, field)
        if weight <= 0 or column not in entry["signal_columns"]:
            continue
        if float(scored[column].abs().max() or 0.0) <= 0.0:
            continue
        active[column] = weight

    total = sum(active.values())
    out = scored.copy()
    if total <= 0:
        out["final_score"] = 0.0
    else:
        score = pd.Series(0.0, index=out.index)
        for column, weight in active.items():
            score = score + (weight / total) * out[column]
        out["final_score"] = score
    return out.sort_values("final_score", ascending=False)


def _is_useful(entry: dict, candidate: str) -> bool:
    """The eval's useful-family rule, using the precomputed lemma map."""
    if canonical_reading(candidate) == canonical_reading(entry["expected"]):
        return True
    expected_tokens = entry["expected_key_tokens"]
    expected_lemmas = entry["expected_lemma_ids"]
    candidate_tokens = _tokens(loose_reading_form(candidate))
    if _overlap(expected_tokens, candidate_tokens) >= entry["threshold"]:
        return True
    candidate_lemmas = entry["lemma_by_reading"].get(canonical_reading(candidate), set())
    shared = expected_lemmas & candidate_lemmas
    lemma_score = (
        len(shared) / min(len(expected_lemmas), len(candidate_lemmas))
        if expected_lemmas and candidate_lemmas
        else 0.0
    )
    if len(shared) >= 2 and lemma_score >= 0.4:
        return True
    if len(expected_lemmas) <= 2 and len(shared) >= 1:
        return True
    return False


def evaluate(
    cache: list[dict],
    weights: ScoreWeights,
    suggestion_weights: SuggestionWeights = DEFAULT_SUGGESTION_WEIGHTS,
) -> dict:
    top1 = 0
    top3 = 0
    reciprocal = 0.0
    for entry in cache:
        ranked = _rescore(entry, weights)
        suggestions = suggest_top_readings(
            ranked.head(min(50, len(ranked))),
            query_mdc=entry["query"],
            query_reading_order=entry["reading_order"],
            top_n=3,
            weights=suggestion_weights,
        )
        useful_rank = None
        for rank, suggestion in enumerate(suggestions, start=1):
            if _is_useful(entry, suggestion.candidate_transliteration):
                useful_rank = rank
                break
        if useful_rank == 1:
            top1 += 1
        if useful_rank is not None and useful_rank <= 3:
            top3 += 1
        if useful_rank is not None:
            reciprocal += 1.0 / useful_rank
    total = len(cache) or 1
    return {
        "queries": len(cache),
        "top1_useful": round(top1 / total, 4),
        "top3_useful": round(top3 / total, 4),
        "mrr": round(reciprocal / total, 4),
    }


def candidate_configs() -> list[tuple[str, ScoreWeights]]:
    """A small, explicit search space over the signals that are live."""
    configs: list[tuple[str, ScoreWeights]] = [
        ("baseline (current defaults)", DEFAULT_WEIGHTS),
    ]
    grid = {
        "fuzzy": [0.10, 0.22, 0.35],
        "tfidf": [0.10, 0.18, 0.30],
        "overlap": [0.10, 0.25],
        "idf_overlap": [0.0, 0.20, 0.40],
    }
    for fuzzy, tfidf, overlap, idf in itertools.product(
        grid["fuzzy"], grid["tfidf"], grid["overlap"], grid["idf_overlap"]
    ):
        weights = DEFAULT_WEIGHTS.replace(
            fuzzy=fuzzy, tfidf=tfidf, overlap=overlap, idf_overlap=idf
        )
        label = f"fuzzy={fuzzy} tfidf={tfidf} overlap={overlap} idf={idf}"
        configs.append((label, weights))
    return configs


def suggestion_configs() -> list[tuple[str, SuggestionWeights]]:
    """Sweep how much the suggestion layer trusts retrieval.

    The default gives retrieval only 0.36 of the mass (relative_score 0.24 +
    mean_score 0.12) and recomputes the rest as its own similarity, which can push a
    well-retrieved parallel out of the top 3. These configurations shift weight back
    toward retrieval evidence and toward attestation rather than string similarity.
    """
    configs: list[tuple[str, SuggestionWeights]] = [
        ("suggestion baseline", DEFAULT_SUGGESTION_WEIGHTS),
    ]
    for relative in [0.35, 0.50, 0.65]:
        for translit in [0.10, 0.20]:
            for char in [0.05, 0.16]:
                for support in [0.05, 0.15]:
                    weights = DEFAULT_SUGGESTION_WEIGHTS.replace(
                        relative_score=relative,
                        translit_overlap=translit,
                        char_similarity=char,
                        support=support,
                        # mean_score penalises readings attested several times at
                        # mixed quality, which is backwards for a corpus-evidence
                        # tool, and lemma_density just re-rewards popularity.
                        mean_score=0.0,
                        lemma_density=0.0,
                    )
                    label = (
                        f"rel={relative} translit={translit} char={char} "
                        f"support={support} mean=0 lemma=0"
                    )
                    configs.append((label, weights))
    return configs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--benchmark", default=BENCHMARK_PATH)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()

    examples_df = load_examples_csv(args.examples)
    benchmark_df = pd.read_csv(args.benchmark).fillna("")

    # Deterministic split: even rows tune, odd rows are held out.
    tune_df = benchmark_df.iloc[::2].reset_index(drop=True)
    holdout_df = benchmark_df.iloc[1::2].reset_index(drop=True)
    print(
        f"Benchmark {len(benchmark_df)} queries -> tune {len(tune_df)}, "
        f"holdout {len(holdout_df)}"
    )

    print("Caching per-query signals (the slow part, done once)...")
    tune_cache = build_query_cache(examples_df, tune_df)
    holdout_cache = build_query_cache(examples_df, holdout_df)

    configs = candidate_configs()
    print(f"Evaluating {len(configs)} weight configurations on the tune split...")
    rows: list[dict] = []
    for label, weights in configs:
        result = evaluate(tune_cache, weights)
        rows.append({"config": label, "split": "tune", **result})

    tuning = pd.DataFrame(rows)
    # Rank by top-3 useful-family, then MRR, then top-1 as tie-breakers.
    tuning = tuning.sort_values(
        ["top3_useful", "mrr", "top1_useful"], ascending=False
    ).reset_index(drop=True)

    print("\nBest 8 configurations on the tune split:")
    print(tuning.head(8).to_string(index=False))

    best_label = tuning.iloc[0]["config"]
    best_weights = dict(configs)[best_label]
    baseline = DEFAULT_WEIGHTS

    # Stage two: with retrieval weights fixed, tune the suggestion layer that
    # decides which grouped readings actually reach the top 3.
    sugg_configs = suggestion_configs()
    print(
        f"\nEvaluating {len(sugg_configs)} suggestion-layer configurations "
        "on the tune split..."
    )
    sugg_rows: list[dict] = []
    for label, sugg_weights in sugg_configs:
        result = evaluate(tune_cache, best_weights, sugg_weights)
        sugg_rows.append({"config": f"[suggest] {label}", "split": "tune", **result})
    sugg_table = pd.DataFrame(sugg_rows).sort_values(
        ["top3_useful", "mrr", "top1_useful"], ascending=False
    ).reset_index(drop=True)
    print("\nBest 6 suggestion-layer configurations on the tune split:")
    print(sugg_table.head(6).to_string(index=False))
    rows.extend(sugg_rows)

    best_sugg_label = sugg_table.iloc[0]["config"].removeprefix("[suggest] ")
    best_sugg = dict(sugg_configs)[best_sugg_label]

    print("\n--- Held-out split, scored once ---")
    holdout_baseline = evaluate(holdout_cache, baseline, DEFAULT_SUGGESTION_WEIGHTS)
    holdout_retrieval = evaluate(holdout_cache, best_weights, DEFAULT_SUGGESTION_WEIGHTS)
    holdout_both = evaluate(holdout_cache, best_weights, best_sugg)
    print(f"baseline both layers      : {holdout_baseline}")
    print(f"tuned retrieval only      : {holdout_retrieval}")
    print(f"tuned retrieval+suggestion: {holdout_both}")
    print(f"\nretrieval config : {best_label}")
    print(f"suggestion config: {best_sugg_label}")

    rows.append({"config": "baseline both layers", "split": "holdout", **holdout_baseline})
    rows.append({"config": f"tuned retrieval: {best_label}", "split": "holdout", **holdout_retrieval})
    rows.append(
        {
            "config": f"tuned both: {best_label} + {best_sugg_label}",
            "split": "holdout",
            **holdout_both,
        }
    )
    holdout_best = holdout_both

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"\nSaved tuning table to {output_path}")

    improved = (
        holdout_best["top3_useful"] > holdout_baseline["top3_useful"]
        or (
            holdout_best["top3_useful"] == holdout_baseline["top3_useful"]
            and holdout_best["mrr"] > holdout_baseline["mrr"]
        )
    )
    print(
        "\nHOLDOUT VERDICT: tuned weights "
        + ("improve on" if improved else "do NOT improve on")
        + " the baseline."
    )
    if improved:
        print("Apply by editing ScoreWeights defaults in app/retrieval/scorer.py:")
        for field in TUNABLE:
            print(f"    {field}: {getattr(best_weights, field)}")
        print("and SuggestionWeights defaults in app/services/suggestions.py:")
        for field in [
            "relative_score",
            "mean_score",
            "translit_overlap",
            "char_similarity",
            "exact_or_near",
            "reading_similarity",
            "support",
            "lemma_density",
        ]:
            print(f"    {field}: {getattr(best_sugg, field)}")


if __name__ == "__main__":
    main()
