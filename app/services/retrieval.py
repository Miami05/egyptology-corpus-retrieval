from __future__ import annotations

import pandas as pd

from app.data.normalizer import (
    contains_hieroglyphs,
    normalize_hieroglyphs,
    normalize_mdc,
    normalize_sign_sequence,
)
from app.retrieval.evidence import build_evidence
from app.retrieval.exact import exact_match_candidates
from app.retrieval.fuzzy import fuzzy_candidate
from app.retrieval.scorer import DEFAULT_WEIGHTS, ScoreWeights, combine_scores
from app.retrieval.tfidf import tfidf_candidates
from app.storage.repo import RetrievalRunRepo


def retrieve_top_k(
    df: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str = "",
    k: int = 3,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
) -> pd.DataFrame:
    # A query written in hieroglyphs must be matched against the sign columns:
    # normalize_mdc strips those codepoints, so treating it as transliteration
    # would leave an empty query that matches nothing.
    query_hieroglyphs_norm = (
        normalize_hieroglyphs(query_mdc) if contains_hieroglyphs(query_mdc) else ""
    )
    query_mdc_norm = normalize_mdc(query_mdc)
    query_reading_order_norm = normalize_sign_sequence(query_reading_order)
    exact_df = exact_match_candidates(df, query_mdc_norm)
    fuzzy_df = fuzzy_candidate(df, query_mdc_norm)
    tfidf_df = tfidf_candidates(df, query_mdc_norm)
    merged = df.copy()
    merged = merged.merge(
        fuzzy_df[["source", "source_text_id", "source_sentence_id", "fuzzy_score"]],
        on=["source", "source_text_id", "source_sentence_id"],
        how="left",
    )
    merged = merged.merge(
        tfidf_df[["source", "source_text_id", "source_sentence_id", "tfidf_score"]],
        on=["source", "source_text_id", "source_sentence_id"],
        how="left",
    )
    merged["fuzzy_score"] = merged["fuzzy_score"].fillna(0.0)
    merged["tfidf_score"] = merged["tfidf_score"].fillna(0.0)
    exact_keys = set(
        zip(
            exact_df["source"],
            exact_df["source_text_id"],
            exact_df["source_sentence_id"],
        )
    )
    merged["exact_bonus"] = merged.apply(
        lambda row: (
            1.0
            if (row["source"], row["source_text_id"], row["source_sentence_id"])
            in exact_keys
            else 0.0
        ),
        axis=1,
    )
    scored = combine_scores(
        merged,
        query_mdc_norm=query_mdc_norm,
        query_reading_order_norm=query_reading_order_norm,
        weights=weights,
        query_hieroglyphs_norm=query_hieroglyphs_norm,
    )
    top = scored.head(k).copy()
    top["evidence"] = top.apply(build_evidence, axis=1)
    return top


def log_retrieval(
    session_repo: RetrievalRunRepo,
    query_mdc: str,
    query_reading_order: str,
    top_df: pd.DataFrame,
) -> None:
    ids = ",".join(map(str, top_df["id"].tolist())) if "id" in top_df.columns else ""
    scores = ",".join(f"{score:.4f}" for score in top_df["final_score"].tolist())
    session_repo.log_run(
        query_mdc=query_mdc,
        query_mdc_norm=normalize_mdc(query_mdc),
        query_reading_order=query_reading_order,
        query_reading_order_norm=normalize_sign_sequence(query_reading_order),
        top_example_ids=ids,
        top_scores=scores,
    )
