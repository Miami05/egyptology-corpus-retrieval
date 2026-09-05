"""Measure similar-text search across the annotation tiers (ROADMAP item E).

Answers Nederhof's question — "can one improve on edit distance?" — on the frozen
cross-edition pair set built by `scripts/build_cross_edition_pairs.py`. The methods, the
metrics and the reading of the result are pre-registered in
`docs/similar-text-eval-2026-09-05.md` §6-§7 and were committed before this script ran.

The task, per pair and per direction: take one edition's text in one tier, exclude that
row itself, score all 130,472 corpus rows, and record the rank of the partner edition.

    python scripts/run_similar_text_eval.py

One corpus load per process, peak RSS printed at the end.
"""

from __future__ import annotations

import argparse
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.retrieval.tfidf import NgramIndex  # noqa: E402
from app.services.similar_text import (  # noqa: E402
    RERANK_DEPTH,
    TIER_SIGNS,
    TIER_TRANSLATION,
    TIER_TRANSLITERATION,
    build_sign_ngram_index,
    build_translation_ngram_index,
    cosine_ranking,
    edit_reranked,
    reciprocal_rank_fusion,
    score_mean,
    sign_code_points,
)
from app.services.suggestions import loose_reading_form  # noqa: E402

DATA_PATH = PROJECT_ROOT / "data/processed/examples.csv"
PAIRS_PATH = PROJECT_ROOT / "data/benchmarks/cross_edition_pairs_v1.csv"
RESULTS_PATH = PROJECT_ROOT / "data/benchmarks/similar_text_eval_v1_results.csv"

RRF_K = 60

METHOD_TIER = {
    "T1": TIER_TRANSLITERATION,
    "T2": TIER_TRANSLITERATION,
    "T3": TIER_TRANSLITERATION,
    "G1": TIER_SIGNS,
    "G2": TIER_SIGNS,
    "L1": TIER_TRANSLATION,
    "C1": "combined",
    "C2": "combined",
}
METHOD_LABEL = {
    "T1": "char 2-4-gram cosine, transliteration",
    "T2": f"edit-distance re-rank of T1 top-{RERANK_DEPTH}",
    "T3": "loose-token Jaccard (pair-construction statistic)",
    "G1": "sign 1-3-gram cosine, hieroglyphs",
    "G2": f"edit-distance re-rank of G1 top-{RERANK_DEPTH}",
    "L1": "char 2-4-gram cosine, translation",
    "C1": f"reciprocal rank fusion (k={RRF_K}) of T1/G1/L1",
    "C2": "mean of min-max normalised T1/G1/L1 scores",
}


def peak_rss_gb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024**3) if sys.platform == "darwin" else peak / (1024**2)


class LooseTokenIndex:
    """Binary token matrix over the *loose* forms, for the T3 Jaccard.

    Built here rather than reusing `app.retrieval.tokens.TokenTable` because T3 has to be
    the pair-construction statistic exactly: `loose_reading_form(...).split()`, the same
    call `scripts/build_cross_edition_pairs.py` makes. `TokenTable` tokenises `mdc_norm`
    and also splits on `:` and `-`, which is right for the app and wrong for reproducing
    the number the pairs were selected on.
    """

    def __init__(self, values: pd.Series) -> None:
        vocabulary: dict[str, int] = {}
        indices: list[int] = []
        indptr = [0]
        sizes: list[int] = []
        for value in values:
            columns = {
                vocabulary.setdefault(token, len(vocabulary))
                for token in loose_reading_form(value).split()
            }
            indices.extend(sorted(columns))
            sizes.append(len(columns))
            indptr.append(len(indices))
        self.vocabulary = vocabulary
        self.sizes = np.asarray(sizes, dtype=np.float64)
        self.matrix = sparse.csr_matrix(
            (
                np.ones(len(indices), dtype=np.float64),
                np.asarray(indices, dtype=np.int32),
                np.asarray(indptr, dtype=np.int32),
            ),
            shape=(len(sizes), max(len(vocabulary), 1)),
        )

    def jaccard(self, query_text: str) -> np.ndarray:
        tokens = {
            self.vocabulary[token]
            for token in loose_reading_form(query_text).split()
            if token in self.vocabulary
        }
        query_size = len(set(loose_reading_form(query_text).split()))
        if query_size == 0:
            return np.zeros(self.matrix.shape[0], dtype=np.float64)
        vector = np.zeros(self.matrix.shape[1], dtype=np.float64)
        for column in tokens:
            vector[column] = 1.0
        shared = self.matrix @ vector
        denominator = query_size + self.sizes - shared
        scores = np.zeros_like(shared)
        usable = denominator > 0
        scores[usable] = shared[usable] / denominator[usable]
        return scores


def rank_of(order: np.ndarray, position: int) -> int:
    """1-based rank of a corpus position in an ordering."""
    return int(np.flatnonzero(order == position)[0]) + 1


def summarise(records: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    grouped = records.groupby(group_columns, dropna=False)
    out = grouped.agg(
        n=("rank", "size"),
        mrr=("reciprocal_rank", "mean"),
        r_at_1=("rank", lambda s: float((s <= 1).mean())),
        r_at_3=("rank", lambda s: float((s <= 3).mean())),
        r_at_10=("rank", lambda s: float((s <= 10).mean())),
    ).reset_index()
    return out


def markdown_table(frame: pd.DataFrame, float_columns: list[str]) -> str:
    display = frame.copy()
    for column in float_columns:
        display[column] = display[column].map(lambda v: f"{v:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    divider = "|" + "|".join("---" for _ in display.columns) + "|"
    body = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in display.itertuples(index=False)
    ]
    return "\n".join([header, divider, *body])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--pairs", default=str(PAIRS_PATH))
    parser.add_argument("--out", default=str(RESULTS_PATH))
    parser.add_argument("--limit", type=int, default=0, help="evaluate only the first N pairs")
    args = parser.parse_args()

    started = time.perf_counter()
    df = load_examples_csv(args.data)
    print(f"corpus: {len(df):,} rows in {time.perf_counter() - started:.1f}s", flush=True)

    pairs = pd.read_csv(args.pairs, dtype={"a_text_id": str, "b_text_id": str})
    # An empty `translation_language` cell arrives as NaN, and `str(nan)` is the truthy
    # string "nan" — which silently sent every German/English pair into the L1 tier it is
    # explicitly excluded from. Normalise once, here, rather than at each use.
    pairs["translation_language"] = pairs["translation_language"].fillna("").astype(str)
    if args.limit:
        pairs = pairs.head(args.limit)
    print(f"pairs:  {len(pairs)} from {args.pairs}", flush=True)

    # The pair file stores positions into the frozen corpus CSV; verify rather than trust.
    for side in ("a", "b"):
        positions = pairs[f"{side}_position"].to_numpy()
        stored = pairs[f"{side}_sentence_id"].astype(str).to_numpy()
        actual = df.iloc[positions]["source_sentence_id"].astype(str).to_numpy()
        if not (stored == actual).all():
            raise SystemExit(
                f"pair file's {side}_position no longer points at the same rows as the corpus"
            )
    print("pair positions verified against the corpus", flush=True)

    build_times: dict[str, float] = {}
    rss_before = peak_rss_gb()

    started = time.perf_counter()
    translit_index = NgramIndex.build(df["mdc_norm"])
    build_times["transliteration n-gram index"] = time.perf_counter() - started
    started = time.perf_counter()
    sign_index = build_sign_ngram_index(df)
    build_times["sign n-gram index"] = time.perf_counter() - started
    started = time.perf_counter()
    translation_index = build_translation_ngram_index(df)
    build_times["translation n-gram index"] = time.perf_counter() - started
    started = time.perf_counter()
    loose_index = LooseTokenIndex(df["transliteration_gold"])
    build_times["loose-token index (T3)"] = time.perf_counter() - started
    for name, seconds in build_times.items():
        print(f"built {name} in {seconds:.1f}s", flush=True)
    print(f"RSS after indexes: {peak_rss_gb():.2f} GB (was {rss_before:.2f} GB)", flush=True)

    mdc_texts = df["mdc_norm"].astype(str).to_numpy()
    glyph_texts = df["hieroglyphs_norm"].astype(str).to_numpy()
    sign_strings = np.array([sign_code_points(value) for value in glyph_texts], dtype=object)
    translation_texts = df["translation"].astype(str).to_numpy()
    n_rows = len(df)

    records: list[dict[str, object]] = []
    started = time.perf_counter()
    for count, pair in enumerate(pairs.itertuples(index=False), start=1):
        for direction, (query_side, target_side) in (
            ("a_to_b", ("a", "b")),
            ("b_to_a", ("b", "a")),
        ):
            query_position = int(getattr(pair, f"{query_side}_position"))
            target_position = int(getattr(pair, f"{target_side}_position"))

            tier_orders: list[np.ndarray] = []
            tier_scores: list[np.ndarray] = []
            method_ranks: dict[str, int] = {}

            # --- transliteration tier (always available: both rows have one) -----
            t1_scores = translit_index.scores(mdc_texts[query_position])
            t1_order = cosine_ranking(t1_scores, exclude=query_position)
            method_ranks["T1"] = rank_of(t1_order, target_position)
            t2_order, _ = edit_reranked(
                t1_order, mdc_texts[query_position], mdc_texts, depth=RERANK_DEPTH
            )
            method_ranks["T2"] = rank_of(t2_order, target_position)
            t3_scores = loose_index.jaccard(
                df.iloc[query_position]["transliteration_gold"]
            )
            method_ranks["T3"] = rank_of(
                cosine_ranking(t3_scores, exclude=query_position), target_position
            )
            tier_orders.append(t1_order)
            tier_scores.append(t1_scores)

            # --- sign tier (only where both rows carry hieroglyphs) --------------
            if glyph_texts[query_position].strip() and glyph_texts[target_position].strip():
                g1_scores = sign_index.scores(glyph_texts[query_position])
                g1_order = cosine_ranking(g1_scores, exclude=query_position)
                method_ranks["G1"] = rank_of(g1_order, target_position)
                g2_order, _ = edit_reranked(
                    g1_order, sign_strings[query_position], sign_strings, depth=RERANK_DEPTH
                )
                method_ranks["G2"] = rank_of(g2_order, target_position)
                tier_orders.append(g1_order)
                tier_scores.append(g1_scores)

            # --- translation tier (both present AND the same language) -----------
            same_language = str(getattr(pair, "translation_language") or "")
            if (
                same_language
                and translation_texts[query_position].strip()
                and translation_texts[target_position].strip()
            ):
                l1_scores = translation_index.scores(translation_texts[query_position])
                l1_order = cosine_ranking(l1_scores, exclude=query_position)
                method_ranks["L1"] = rank_of(l1_order, target_position)
                tier_orders.append(l1_order)
                tier_scores.append(l1_scores)

            # --- combinations over the tiers available for this pair -------------
            if len(tier_orders) > 1:
                fused = reciprocal_rank_fusion(tier_orders, n_rows, k=RRF_K)
                method_ranks["C1"] = rank_of(
                    cosine_ranking(fused, exclude=query_position), target_position
                )
                averaged = score_mean(tier_scores)
                method_ranks["C2"] = rank_of(
                    cosine_ranking(averaged, exclude=query_position), target_position
                )

            for method, rank in method_ranks.items():
                records.append(
                    {
                        "pair_id": pair.pair_id,
                        "source_pair": pair.source_pair,
                        "jaccard": pair.jaccard,
                        "direction": direction,
                        "query_source": getattr(pair, f"{query_side}_source"),
                        "target_source": getattr(pair, f"{target_side}_source"),
                        "method": method,
                        "tier": METHOD_TIER[method],
                        "n_tiers_available": len(tier_orders),
                        "rank": rank,
                        "reciprocal_rank": 1.0 / rank,
                    }
                )
        if count % 25 == 0:
            print(
                f"  {count}/{len(pairs)} pairs, {time.perf_counter() - started:.0f}s",
                flush=True,
            )

    results = pd.DataFrame(records)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out, index=False)
    print(f"\nwrote {len(results):,} result rows -> {args.out}\n", flush=True)

    order = ["T1", "T2", "T3", "G1", "G2", "L1", "C1", "C2"]

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame["method"] = pd.Categorical(frame["method"], categories=order, ordered=True)
        sort_columns = [c for c in ("method", "direction", "source_pair") if c in frame.columns]
        return frame.sort_values(sort_columns).reset_index(drop=True)

    print("=== per method, per direction (pooled over source pairs) ===")
    by_direction = ordered(summarise(results, ["method", "tier", "direction"]))
    print(markdown_table(by_direction, ["mrr", "r_at_1", "r_at_3", "r_at_10"]))

    print("\n=== per method, both directions pooled ===")
    pooled = ordered(summarise(results, ["method", "tier"]))
    print(markdown_table(pooled, ["mrr", "r_at_1", "r_at_3", "r_at_10"]))

    print("\n=== per method, per source pair (both directions pooled) ===")
    by_source = ordered(summarise(results, ["method", "tier", "source_pair"]))
    print(markdown_table(by_source, ["mrr", "r_at_1", "r_at_3", "r_at_10"]))

    # Like-for-like. The pooled table above compares methods measured on different
    # numbers of cases — T1 on all 600, G1 on 360, L1 on 96, C1/C2 on whatever had two
    # tiers — so "C2 0.754 beats T1 0.721" would be an artefact of which pairs each one
    # was allowed to answer. Restricting every method to one method's own cases is the
    # only comparison that means anything.
    case_key = results.set_index(["pair_id", "direction"]).index
    for anchor, title in (
        ("C1", "the cases where at least two tiers were available (C1/C2 vs the tiers alone)"),
        ("G1", "the cases where the sign tier was evaluable"),
        ("L1", "the cases where the translation tier was evaluable"),
    ):
        cases = set(
            map(tuple, results[results["method"] == anchor][["pair_id", "direction"]].values.tolist())
        )
        subset = results[case_key.isin(cases)]
        print(f"\n=== like-for-like: {title} ===")
        print(markdown_table(ordered(summarise(subset, ["method", "tier"])), ["mrr", "r_at_1", "r_at_3", "r_at_10"]))

    print("\n=== the pre-registered reading ===")
    mrr = {
        (row.method, row.direction): row.mrr
        for row in by_direction.itertuples(index=False)
    }
    verdicts = []
    for better, baseline in (("T2", "T1"), ("G2", "G1")):
        for direction in ("a_to_b", "b_to_a"):
            left, right = mrr.get((better, direction)), mrr.get((baseline, direction))
            if left is None or right is None:
                verdicts.append((better, baseline, direction, None, None, "not evaluable"))
                continue
            verdicts.append(
                (
                    better,
                    baseline,
                    direction,
                    left,
                    right,
                    "improves" if left > right else ("ties" if left == right else "does not improve"),
                )
            )
    for better, baseline, direction, left, right, verdict in verdicts:
        left_text = "n/a" if left is None else f"{left:.4f}"
        right_text = "n/a" if right is None else f"{right:.4f}"
        print(f"  {better} vs {baseline}, {direction}: {left_text} vs {right_text} -> {verdict}")
    all_improve = all(v[5] == "improves" for v in verdicts)
    print(
        "\nVERDICT: edit distance "
        + ("improves on" if all_improve else "does NOT improve on")
        + " n-gram cosine under the pre-registered rule "
        "(T2 > T1 and G2 > G1 in MRR in both directions)."
    )

    print("\n=== tier coverage ===")
    total_cases = 2 * len(pairs)
    for tier, method in (("transliteration", "T1"), ("signs", "G1"), ("translation", "L1")):
        subset = results[results["method"] == method]
        by_source = ", ".join(
            f"{label} {count}"
            for label, count in sorted(subset["source_pair"].value_counts().items())
        )
        print(
            f"  {tier}: evaluable on {len(subset)} of {total_cases} (pair, direction) "
            f"cases — {by_source or 'none'}"
        )

    print(f"\npeak RSS {peak_rss_gb():.2f} GB")


if __name__ == "__main__":
    main()
