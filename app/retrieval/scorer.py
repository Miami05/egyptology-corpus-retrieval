from __future__ import annotations

from dataclasses import dataclass, replace
from math import log

import numpy as np
import pandas as pd
from rapidfuzz import process
from rapidfuzz.distance import LCSseq

# The tokenizer and the precomputed per-row token structures live in
# app.retrieval.tokens (see that module's docstring for why). Re-exported here
# because `tokenize_query` has always been part of this module's surface —
# app.services.suggestions and the tests import it from here.
from app.retrieval.tokens import (  # noqa: F401
    TOKEN_SPLIT_RE,
    ScoringTables,
    TokenTable,
    TokenWeights,
    encode_groups,
    tokenize_query,
)


@dataclass(frozen=True)
class ScoreWeights:
    """Relative weight of each ranking signal.

    Absolute values do not matter: `combine_scores` renormalises over the signals
    that actually carry information for a given query, so the final score always
    spans a comparable range. That matters because several metadata signals below
    are empty for large parts of the corpus, and previously their weight was
    silently lost, capping a perfect text match at roughly 0.60.
    """

    # Live-signal weights chosen by scripts/tune_ranking_weights.py: swept on a
    # 40-query tune split, then scored once on a disjoint 40-query holdout, where
    # they beat the previous values (top-3 useful-family 0.675 -> 0.725, MRR
    # 0.592 -> 0.617). IDF overlap carries the most weight because rare shared
    # tokens identify a parallel far better than ubiquitous particles do.
    fuzzy: float = 0.35
    tfidf: float = 0.18
    overlap: float = 0.10
    idf_overlap: float = 0.40
    exact: float = 0.10
    reading_order: float = 0.10
    # Sign-based signals. They are zero for a transliteration query and the
    # transliteration signals are zero for a sign query, and combine_scores drops
    # whichever set is inactive, so one weight set serves both input modes.
    #
    # glyph_order is the one order-sensitive glyph signal: before it existed every
    # surviving signal was set-based, so reordered offering formulas scored
    # identically (14 verified permutation-collision groups) and a query repeated
    # three times scored 1.0 against a single occurrence. It is the normalised
    # longest-common-subsequence of sign *groups*, divided by the query's group
    # count — order-aware and repetition-aware, but indifferent to how much longer
    # the candidate sentence is (surplus length is idf_overlap's job).
    glyph_overlap: float = 0.15
    glyph_idf_overlap: float = 0.40
    glyph_order: float = 0.25
    glyph_exact: float = 0.20
    # Not a signal weight: how much a candidate's surplus tokens reduce the IDF
    # overlap (see idf_overlap_score). 1.0 is symmetric Jaccard. Deliberately absent
    # from WEIGHT_COLUMNS, which only lists signal weights — and unlike those it can
    # NOT be swept through tune_ranking_weights' cache, because it changes the
    # idf_overlap_score column itself rather than reweighting cached columns.
    #
    # Only applied to queries of >= 3 content tokens (effective_surplus_penalty);
    # shorter queries keep plain Jaccard. How this was chosen, in order:
    # 1. 0.3 swept on the tune half of the 80-query benchmark (top-1 useful 0.600 ->
    #    0.650, top-3 0.775 -> 0.825, MRR 0.688 -> 0.738, with the suggestion
    #    layer's surplus_penalty=0.3; flat across 0.2-0.5).
    # 2. Held-out half: identical to baseline, no gain, no regression.
    # 3. Applied unconditionally it cost the frozen 20-query benchmark one top-1
    #    (0.55 -> 0.50): every demoted query had 1-2 tokens, where the query IS a
    #    complete short reading and the tight match should win. The length condition
    #    came from that observation — the frozen set has therefore been looked at
    #    twice and must not arbitrate any further tweak to this mechanism.
    # 4. Conditional: tune gains fully kept, holdout flat, frozen exactly baseline.
    idf_surplus_penalty: float = 0.3

    def replace(self, **changes: float) -> ScoreWeights:
        return replace(self, **changes)


# Maps each weight field to the scored column it applies to.
WEIGHT_COLUMNS: dict[str, str] = {
    "fuzzy": "fuzzy_score",
    "tfidf": "tfidf_score",
    "overlap": "overlap_score",
    "idf_overlap": "idf_overlap_score",
    "exact": "exact_bonus",
    "reading_order": "reading_order_overlap",
    "glyph_overlap": "glyph_overlap_score",
    "glyph_idf_overlap": "glyph_idf_overlap_score",
    "glyph_order": "glyph_order_score",
    "glyph_exact": "glyph_exact_bonus",
}

DEFAULT_WEIGHTS = ScoreWeights()

# The deity/formula/offering/recipient/aesthetic metadata signals that used to live
# here (0.30 of the weight) were removed on 2026-08-29: their source columns are
# empty for all 12,772 corpus rows, so the signals never activated and were dropped
# by the renormalisation on every query — 250 lines of unreachable code, several of
# them buggy. Git history has the implementation if metadata columns are ever
# populated; reintroduce them only together with data and a benchmark that can see
# them.


def effective_surplus_penalty(query: str, penalty: float) -> float:
    """Apply the surplus penalty only to queries long enough to be fragments.

    A 1-2 token query is very often a complete short reading in its own right (`sr`,
    `wns`), and there the tight candidate `sr(.w)` should beat a long sentence that
    merely contains it — symmetric Jaccard is correct. Only from three content
    tokens up is the query overwhelmingly a fragment of a longer sentence, which is
    when candidate length stops being evidence against a match. Below the threshold
    this returns 1.0, which reproduces plain Jaccard exactly.
    """
    return penalty if len(tokenize_query(query)) >= 3 else 1.0


def token_overlap_score(
    query: str,
    candidate: str,
    candidate_surplus_penalty: float = 1.0,
) -> float:
    """Unweighted token overlap; see idf_overlap_score for the penalty semantics.

    The default keeps this symmetric Jaccard, which is right for comparing two
    complete readings (evidence labels, reading-order overlap). Pass a lower
    penalty only where the query is a fragment and the candidate a full sentence.
    """
    q_tokens = set(tokenize_query(query))
    c_tokens = set(tokenize_query(candidate))
    if not q_tokens or not c_tokens:
        return 0.0
    shared = len(q_tokens & c_tokens)
    denominator = (
        shared
        + len(q_tokens - c_tokens)
        + candidate_surplus_penalty * len(c_tokens - q_tokens)
    )
    if denominator <= 0:
        return 0.0
    return shared / denominator


@dataclass(frozen=True)
class CorpusStats:
    """Query-independent statistics, computed once per corpus."""

    mdc_frequencies: dict[str, int]
    glyph_frequencies: dict[str, int]


def build_corpus_stats(df: pd.DataFrame) -> CorpusStats:
    return CorpusStats(
        mdc_frequencies=document_frequencies(df["mdc_norm"]),
        glyph_frequencies=(
            document_frequencies(df["hieroglyphs_norm"])
            if "hieroglyphs_norm" in df.columns
            else {}
        ),
    )


def document_frequencies(values: pd.Series) -> dict[str, int]:
    """How many corpus rows each token appears in."""
    frequencies: dict[str, int] = {}
    for value in values:
        for token in set(tokenize_query(value)):
            frequencies[token] = frequencies.get(token, 0) + 1
    return frequencies


def idf_overlap_score(
    query: str,
    candidate: str,
    frequencies: dict[str, int],
    corpus_size: int,
    candidate_surplus_penalty: float = 1.0,
) -> float:
    """Token overlap weighted by how rare each shared token is.

    Plain Jaccard gives `n`, `k`, `f`, `m` the same say as `ḫnt.ꞽ` or `sḫnti̯`, so a
    query's distinctive tokens get drowned out by grammatical particles that appear
    in most rows. Weighting each token by inverse document frequency makes the rare,
    identifying tokens decide the ranking.

    `candidate_surplus_penalty` controls how much a candidate's *extra* tokens count
    against it (a Tversky index: 1.0 is symmetric Jaccard, 0.0 is pure query
    coverage). The query is usually a fragment of a sentence, so the candidates worth
    finding are longer than the query by construction — under Jaccard a trivial
    one-token corpus row that matches one query token outscores the real parallel
    that contains the whole query, because the parallel's own length inflates the
    union. Every unmatched *query* token still costs full weight either way.
    """
    q_tokens = set(tokenize_query(query))
    c_tokens = set(tokenize_query(candidate))
    if not q_tokens or not c_tokens:
        return 0.0

    def weight(token: str) -> float:
        # +1 smoothing keeps an unseen query token finite; a token in every row
        # contributes almost nothing.
        return log((corpus_size + 1) / (frequencies.get(token, 0) + 1)) + 1.0

    shared_weight = sum(weight(token) for token in q_tokens & c_tokens)
    query_only_weight = sum(weight(token) for token in q_tokens - c_tokens)
    candidate_only_weight = sum(weight(token) for token in c_tokens - q_tokens)
    denominator = (
        shared_weight
        + query_only_weight
        + candidate_surplus_penalty * candidate_only_weight
    )
    if denominator <= 0:
        return 0.0
    return shared_weight / denominator


def combine_scores(
    df: pd.DataFrame,
    query_mdc_norm: str,
    query_reading_order_norm: str = "",
    weights: ScoreWeights = DEFAULT_WEIGHTS,
    query_hieroglyphs_norm: str = "",
    corpus_stats: "CorpusStats | None" = None,
    tables: "ScoringTables | None" = None,
    signals: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Score every candidate row against the query.

    `corpus_stats` carries the query-independent half of the work (document
    frequencies per column). Recomputing it per query re-tokenised the whole corpus
    two or three times for every search; it only changes when the corpus does.

    `tables` carries the rest of it: the corpus's token *sets* and IDF weights,
    precomputed once per resource set (`app.retrieval.tokens.ScoringTables`). With
    it, the four set-based signals below become sparse mat-vecs instead of a Python
    loop over every corpus row — the difference between ~5 s and ~0.1 s of this
    function on the 130k-row corpus. It is used only if it was built from this exact
    frame (`ScoringTables.matches`, checked on the row labels); otherwise, and when
    it is absent, the scalar reference path below runs unchanged. The two agree
    exactly on the overlap signals and to ~1e-16 on the IDF ones (a different
    summation order for the same weights) — see `tests/test_scoring_equivalence.py`.

    `signals` are the per-row columns the caller has already computed (the fuzzy,
    cosine and exact signals, which `retrieve_top_k` derives from the query's own
    parse). They are assigned onto this function's own copy of the frame, so the
    caller does not have to make a second one just to carry them here.
    """
    out = df.copy()
    for column, values in (signals or {}).items():
        out[column] = values
    fast = tables if tables is not None and tables.matches(out) else None
    if "fuzzy_score" not in out.columns:
        out["fuzzy_score"] = 0.0
    if "tfidf_score" not in out.columns:
        out["tfidf_score"] = 0.0
    if "exact_bonus" not in out.columns:
        out["exact_bonus"] = 0.0
    corpus_size = len(out)
    text_penalty = effective_surplus_penalty(
        query_mdc_norm, weights.idf_surplus_penalty
    )
    if fast is not None:
        query_tokens = set(tokenize_query(query_mdc_norm))
        out["overlap_score"] = fast.text.overlap_scores(query_tokens)
        out["idf_overlap_score"] = fast.text_weights.idf_overlap_scores(
            fast.text, query_tokens, candidate_surplus_penalty=text_penalty
        )
    else:
        out["overlap_score"] = out["mdc_norm"].map(
            lambda value: token_overlap_score(query_mdc_norm, value)
        )
        frequencies = (
            corpus_stats.mdc_frequencies
            if corpus_stats is not None
            else document_frequencies(out["mdc_norm"])
        )
        out["idf_overlap_score"] = out["mdc_norm"].map(
            lambda value: idf_overlap_score(
                query_mdc_norm,
                value,
                frequencies,
                corpus_size,
                candidate_surplus_penalty=text_penalty,
            )
        )

    # Sign-sequence matching, used when the query is written in hieroglyphs.
    if query_hieroglyphs_norm and "hieroglyphs_norm" in out.columns:
        glyph_penalty = effective_surplus_penalty(
            query_hieroglyphs_norm, weights.idf_surplus_penalty
        )
        glyph_fast = fast.glyph if fast is not None else None
        # The order-aware signal needs the corpus's sign-group encoding; without a
        # usable one (see `encode_groups`) the whole glyph block falls back.
        query_encoded = (
            encode_groups(glyph_fast, query_hieroglyphs_norm)
            if glyph_fast is not None
            else None
        )
        if glyph_fast is not None and query_encoded is not None:
            glyph_tokens = set(tokenize_query(query_hieroglyphs_norm))
            out["glyph_overlap_score"] = glyph_fast.overlap_scores(glyph_tokens)
            out["glyph_idf_overlap_score"] = fast.glyph_weights.idf_overlap_scores(
                glyph_fast, glyph_tokens, candidate_surplus_penalty=glyph_penalty
            )
            out["glyph_exact_bonus"] = glyph_fast.exact_matches(
                query_hieroglyphs_norm, strip=True
            )
            query_groups = len(query_encoded)
            if query_groups and corpus_size:
                similarity = process.cdist(
                    [query_encoded],
                    glyph_fast.encoded,
                    scorer=LCSseq.similarity,
                    workers=1,
                )[0]
                out["glyph_order_score"] = (
                    similarity.astype(np.float64) / query_groups
                )
            else:
                out["glyph_order_score"] = 0.0
        else:
            glyph_frequencies = (
                corpus_stats.glyph_frequencies
                if corpus_stats is not None
                else document_frequencies(out["hieroglyphs_norm"])
            )
            out["glyph_overlap_score"] = out["hieroglyphs_norm"].map(
                lambda value: token_overlap_score(query_hieroglyphs_norm, value)
            )
            out["glyph_idf_overlap_score"] = out["hieroglyphs_norm"].map(
                lambda value: idf_overlap_score(
                    query_hieroglyphs_norm,
                    value,
                    glyph_frequencies,
                    corpus_size,
                    candidate_surplus_penalty=glyph_penalty,
                )
            )
            out["glyph_exact_bonus"] = out["hieroglyphs_norm"].map(
                lambda value: (
                    1.0 if str(value).strip() == query_hieroglyphs_norm else 0.0
                )
            )
            # Order-aware signal: LCS over sign-group sequences, normalised by the
            # query's group count. Groups are mapped to single characters so
            # rapidfuzz can run the sequence match at C speed across all rows.
            encoding: dict[str, str] = {}

            def encode(text: str) -> str:
                return "".join(
                    encoding.setdefault(group, chr(0x20000 + len(encoding)))
                    for group in str(text).split()
                )

            scalar_encoded = encode(query_hieroglyphs_norm)
            query_groups = len(scalar_encoded)
            out["glyph_order_score"] = out["hieroglyphs_norm"].map(
                lambda value: (
                    LCSseq.similarity(scalar_encoded, encode(value)) / query_groups
                    if query_groups
                    else 0.0
                )
            )
    else:
        out["glyph_overlap_score"] = 0.0
        out["glyph_idf_overlap_score"] = 0.0
        out["glyph_order_score"] = 0.0
        out["glyph_exact_bonus"] = 0.0
    if query_reading_order_norm:
        out["reading_order_overlap"] = out["normalized_reading_order_norm"].map(
            lambda value: token_overlap_score(query_reading_order_norm, value)
        )
    else:
        # The map below returned a constant 0.0 for every row when there is no
        # reading-order query — which is the usual case, and cost a full Python
        # pass over the corpus to produce a column of zeros.
        out["reading_order_overlap"] = 0.0
    # Renormalise over the signals that actually discriminate for this query. A
    # signal that is zero for every candidate — an empty metadata column, or the
    # reading-order overlap when the user supplied no reading order — tells us
    # nothing, so letting it keep its share of the weight would just compress every
    # score toward zero and make confidences incomparable between queries.
    active: dict[str, float] = {}
    for field, column in WEIGHT_COLUMNS.items():
        weight = getattr(weights, field)
        if weight <= 0 or column not in out.columns:
            continue
        if float(out[column].abs().max() or 0.0) <= 0.0:
            continue
        active[column] = weight

    total_weight = sum(active.values())
    if total_weight <= 0:
        out["final_score"] = 0.0
    else:
        score = pd.Series(0.0, index=out.index)
        for column, weight in active.items():
            score = score + (weight / total_weight) * out[column]
        out["final_score"] = score
    # Stable sort: for short queries thousands of rows tie at 0.0, and the default
    # quicksort made everything past the last positive score — and therefore the
    # tail of the visible results — depend on the input order of the frame.
    return out.sort_values("final_score", ascending=False, kind="mergesort")
