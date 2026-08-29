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


def retrieve_top_k(
    df: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str = "",
    k: int = 3,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
    query_hieroglyphs_norm: str | None = None,
) -> pd.DataFrame:
    # A query written in hieroglyphs must be matched against the sign columns:
    # normalize_mdc strips those codepoints, so treating it as transliteration
    # would leave an empty query that matches nothing. The caller may pass the
    # resegmented sign groups (see app.services.segmentation) so that the parallels
    # are matched on corpus-style groups rather than on the paste's spacing.
    if query_hieroglyphs_norm is None:
        query_hieroglyphs_norm = (
            normalize_hieroglyphs(query_mdc) if contains_hieroglyphs(query_mdc) else ""
        )
    # A hieroglyph query is matched on the sign columns only. Any Latin residue in
    # the same paste (a line number, a stray note) used to leak into the text
    # signals and *lower* an exact sign match — appending " wad" to an exact glyph
    # query dropped it from 1.000 to 0.732. It is deliberately ignored here; the UI
    # says so when it happens.
    query_mdc_norm = "" if query_hieroglyphs_norm else normalize_mdc(query_mdc)
    query_reading_order_norm = normalize_sign_sequence(query_reading_order)
    merged = df.copy()
    if query_mdc_norm:
        exact_df = exact_match_candidates(df, query_mdc_norm)
        fuzzy_df = fuzzy_candidate(df, query_mdc_norm)
        tfidf_df = tfidf_candidates(df, query_mdc_norm)
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
        merged["exact_bonus"] = [
            1.0 if key in exact_keys else 0.0
            for key in zip(
                merged["source"], merged["source_text_id"], merged["source_sentence_id"]
            )
        ]
    else:
        # No usable text query. Without this guard an empty string is a perfect
        # match for an empty candidate: fuzz.ratio("", "") is 100 and the cosine of
        # two empty n-gram vectors is 1.0, so the first corpus row ever imported
        # without a transliteration would top every hieroglyph query.
        merged["fuzzy_score"] = 0.0
        merged["tfidf_score"] = 0.0
        merged["exact_bonus"] = 0.0
    scored = combine_scores(
        merged,
        query_mdc_norm=query_mdc_norm,
        query_reading_order_norm=query_reading_order_norm,
        weights=weights,
        query_hieroglyphs_norm=query_hieroglyphs_norm,
    )
    # Honest empty state: a row with no shared evidence at all must not be shown as
    # a "parallel" just because k rows were requested. The floor is on raw evidence
    # (shared tokens or sign groups), not on final_score, which is renormalised per
    # query and therefore not comparable across queries.
    if query_hieroglyphs_norm:
        has_evidence = (
            (scored["glyph_overlap_score"] > 0.0)
            | (scored["glyph_idf_overlap_score"] > 0.0)
            | (scored["glyph_exact_bonus"] > 0.0)
        )
    else:
        has_evidence = (
            (scored["overlap_score"] > 0.0)
            | (scored["idf_overlap_score"] > 0.0)
            | (scored["exact_bonus"] > 0.0)
            | (scored["fuzzy_score"] >= 0.6)
            | (scored["tfidf_score"] >= 0.5)
        )
    scored = scored[has_evidence]
    top = scored.head(k).copy()
    if top.empty:
        top["evidence"] = pd.Series(dtype=str)
        return top
    top["evidence"] = top.apply(build_evidence, axis=1)
    return top

