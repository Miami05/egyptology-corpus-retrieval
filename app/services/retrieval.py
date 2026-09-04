from __future__ import annotations

from typing import Callable, Literal

import pandas as pd

from app.data.normalizer import contains_hieroglyphs, normalize_hieroglyphs, normalize_sign_sequence
from app.data.query import QueryParse, parse_query
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.retrieval.evidence import build_evidence
from app.retrieval.scorer import (
    DEFAULT_WEIGHTS,
    CorpusStats,
    ScoreWeights,
    build_corpus_stats,
    combine_scores,
)
from app.retrieval.tfidf import NgramIndex
from app.services.stage import (
    StageResources,
    choose_stage_by_likelihood,
    infer_stage,
    stage_base_rates,
)


@dataclass(frozen=True)
class SearchIndex:
    """Everything about the corpus that does not depend on the query.

    Built once and reused: document frequencies for the IDF signals and the
    sparse n-gram index for the cosine signal. Rebuilding these per search was
    roughly half the cost of a query.
    """

    stats: CorpusStats
    text_index: NgramIndex

    @property
    def vocabulary(self) -> set[str]:
        """Every token the corpus is indexed under — how `parse_query` tells
        Manuel de Codage from plain ASCII without guessing."""
        return set(self.stats.mdc_frequencies)


def build_search_index(df: pd.DataFrame) -> SearchIndex:
    return SearchIndex(
        stats=build_corpus_stats(df),
        text_index=NgramIndex.build(df["mdc_norm"]),
    )


def retrieve_top_k(
    df: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str = "",
    k: int = 3,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
    query_hieroglyphs_norm: str | None = None,
    index: SearchIndex | None = None,
) -> pd.DataFrame:
    # Every notation goes through one parser, which also decides whether this is a
    # sign query (matched on the sign columns) or a text query (matched on the
    # reading index), and folds the text with the same function the index was built
    # with. The caller may pass the resegmented sign groups (see
    # app.services.segmentation) so that the parallels are matched on corpus-style
    # groups rather than on the paste's spacing.
    parse = parse_query(
        query_mdc,
        vocabulary=index.vocabulary if index is not None else None,
        hieroglyphs_norm=query_hieroglyphs_norm,
    )
    # A hieroglyph query is matched on the sign columns only. Any Latin residue in
    # the same paste (a line number, a stray note) used to leak into the text
    # signals and *lower* an exact sign match — appending " wad" to an exact glyph
    # query dropped it from 1.000 to 0.732. It is deliberately ignored here; the UI
    # says so when it happens.
    query_hieroglyphs_norm = parse.hieroglyphs_norm
    query_mdc_norm = parse.search_key
    query_reading_order_norm = normalize_sign_sequence(query_reading_order)
    # One copy of the frame, not five. The old path built a separate sorted copy per
    # signal and merged them back on three key columns, discarding each sort; the
    # signals are per-row and can simply be assigned as columns.
    merged = df.copy()
    if query_mdc_norm:
        candidates = merged["mdc_norm"].astype(str)
        merged["fuzzy_score"] = [
            fuzz.ratio(query_mdc_norm, value) / 100.0 for value in candidates
        ]
        text_index = (
            index.text_index
            if index is not None and len(index.text_index) == len(merged)
            else NgramIndex.build(candidates)
        )
        merged["tfidf_score"] = text_index.scores(query_mdc_norm)
        merged["exact_bonus"] = (candidates == query_mdc_norm).astype(float)
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
        corpus_stats=index.stats if index is not None else None,
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


def resolve_auto_stage(
    query: str,
    resources_by_stage: Callable[[str | None], StageResources],
) -> tuple[str | None, bool, dict[str, float]]:
    """Resolve "auto" to a concrete stage (or `None`, pooled) for one query.

    The one shared implementation of item A's "auto" rule — `scripts/
    run_expert_paste_eval.py`'s `resolve_stage` and `app/ui/whyptology_app.py`'s
    `resolve_ui_stage` both call this for their `stage_mode == "auto"` /
    `selected == "auto"` case (previously each duplicated the logic below), and
    `retrieve_with_stage`'s own `"auto"` branch below uses it too.

    A hieroglyph paste has no reading of its own to match a stage's rows against,
    so it is resolved by language-identification likelihood instead
    (`app.services.stage.choose_stage_by_likelihood`: segment once with the
    pooled segmenter, then take the stage whose own reading model finds that
    segmentation most likely, per sign — see that function for why segmentation
    is pooled and reading is not). A text (transliteration) query keeps item A
    core's original rule: a first retrieval pass over the pooled resources, then
    `infer_stage` given the pooled frame's own stage base rates (the
    lift-over-base-rate guard documented on `infer_stage`).

    Returns `(stage, inferred, likelihood_scores)`. `likelihood_scores` is
    `choose_stage_by_likelihood`'s per-stage per-sign audit dict for a hieroglyph
    paste, and empty for a text query (no per-stage likelihoods computed there).
    """
    if contains_hieroglyphs(query):
        paste_norm = normalize_hieroglyphs(query)
        stage, scores = choose_stage_by_likelihood(paste_norm, resources_by_stage)
        return stage, stage is not None, scores

    pooled = resources_by_stage(None)
    first_pass = retrieve_top_k(
        pooled.frame,
        query_mdc=query,
        k=10,
        index=pooled.index,
    )
    stage = infer_stage(first_pass, base_rates=stage_base_rates(pooled.frame))
    return stage, stage is not None, {}


@dataclass(frozen=True)
class StageRetrievalResult:
    """The retrieved rows plus how the stage was decided, for the UI to report."""

    results: pd.DataFrame
    stage_used: str | None
    inferred: bool


def retrieve_with_stage(
    df_all: pd.DataFrame,
    resources_by_stage: Callable[[str | None], StageResources],
    query_mdc: str,
    query_reading_order: str = "",
    stage: str | None | Literal["auto"] = None,
    k: int = 3,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
    query_hieroglyphs_norm: str | None = None,
) -> StageRetrievalResult:
    """Retrieve with a declared, absent, or automatically inferred stage.

    `resources_by_stage` resolves a stage (or None, for the pooled corpus) to its
    `StageResources` — normally a small cache keyed by stage, so the same resources
    are not rebuilt per query. `df_all` is accepted for interface symmetry with
    `retrieve_top_k`/the caller's own frame handling but retrieval itself always runs
    against the frame inside the resolved `StageResources`, which is always the
    pooled corpus regardless of `stage` (stage is a preference, not a filter, for
    retrieval — see `app.services.stage`'s module docstring and `StageResources`);
    only the resolved resources' `index.stats` (the IDF document-frequency counts)
    differ by stage, weighting the same pooled candidates rather than excluding any
    of them.

    - `stage` a concrete stage name: retrieve on that stage's resources — the
      pooled candidate pool, weighted by that stage's own token statistics.
    - `stage is None`: retrieve on the pooled resources — today's behaviour exactly,
      since `resources_by_stage(None)` must build on `compatible_frame(df, None)`,
      which is the full frame (so pooled stats too, identically).
    - `stage == "auto"`: `resolve_auto_stage(query_mdc, resources_by_stage)` decides
      the stage — likelihood-based for a hieroglyph paste, label-based
      (`app.services.stage.infer_stage`) for a text query, see that function. When a
      stage is inferred and `query_mdc` is a hieroglyph paste, it is re-segmented
      with the *inferred* stage's own segmenter before the second retrieval pass
      (restricting to one stage's group counts changes which grouping wins — see
      `app.services.segmentation`), even if the caller's own `query_hieroglyphs_norm`
      was computed against the pooled segmenter. When nothing can be inferred, a
      pooled pass at the caller's `k` is returned instead.
    """
    del df_all  # see docstring: retrieval runs on the resolved StageResources' frame
    if stage == "auto":
        inferred_stage, inferred, _likelihood_scores = resolve_auto_stage(
            query_mdc, resources_by_stage
        )
        if not inferred:
            pooled = resources_by_stage(None)
            first_pass = retrieve_top_k(
                pooled.frame,
                query_mdc,
                query_reading_order=query_reading_order,
                k=k,
                weights=weights,
                query_hieroglyphs_norm=query_hieroglyphs_norm,
                index=pooled.index,
            )
            return StageRetrievalResult(
                results=first_pass, stage_used=None, inferred=False
            )
        resources = resources_by_stage(inferred_stage)
        regrouped = query_hieroglyphs_norm
        if contains_hieroglyphs(query_mdc):
            as_pasted = normalize_hieroglyphs(query_mdc).split()
            regrouped = " ".join(resources.segmenter.segment(as_pasted).groups)
        second_pass = retrieve_top_k(
            resources.frame,
            query_mdc,
            query_reading_order=query_reading_order,
            k=k,
            weights=weights,
            query_hieroglyphs_norm=regrouped,
            index=resources.index,
        )
        return StageRetrievalResult(
            results=second_pass, stage_used=inferred_stage, inferred=True
        )

    resources = resources_by_stage(stage)
    results = retrieve_top_k(
        resources.frame,
        query_mdc,
        query_reading_order=query_reading_order,
        k=k,
        weights=weights,
        query_hieroglyphs_norm=query_hieroglyphs_norm,
        index=resources.index,
    )
    return StageRetrievalResult(results=results, stage_used=stage, inferred=False)

