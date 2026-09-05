"""ROADMAP item 3 (2026-09-05): the fast scoring path must score identically.

`app.retrieval.tokens` replaced four per-row Python loops in `combine_scores` with
precomputed corpus structures and sparse mat-vecs, and `retrieve_top_k`'s scalar
`fuzz.ratio` loop with one batched `process.cdist` call. That was a performance
change only — no signal, weight or formula was touched — so what has to be locked
down is that the two paths *agree*, on the score and on the ranking.

The reference is the scalar implementation itself: `token_overlap_score`,
`idf_overlap_score` and the scalar branch of `combine_scores` are still in
`app.retrieval.scorer` and still run whenever no `ScoringTables` is supplied (a
caller with a frame the tables were not built from, and every test that constructs
a `SearchIndex` by hand). So each test below runs the same query through both.

The one documented inexactness: the IDF signals sum the same per-token weights in
a different order (ascending vocabulary column, rather than Python `set` iteration
order), which rounds the identical sum differently in the last bit or two. The
overlap signals are integer arithmetic and are bit-identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from rapidfuzz import fuzz, process

from app.retrieval.scorer import (
    ScoringTables,
    build_corpus_stats,
    combine_scores,
    document_frequencies,
    effective_surplus_penalty,
    idf_overlap_score,
    token_overlap_score,
    tokenize_query,
)
from app.retrieval.tokens import TokenTable, TokenWeights, encode_groups

# Score columns whose value must be reproduced bit for bit, and those whose
# summation order changes (see the module docstring).
EXACT_COLUMNS = [
    "fuzzy_score",
    "tfidf_score",
    "exact_bonus",
    "overlap_score",
    "glyph_overlap_score",
    "glyph_order_score",
    "glyph_exact_bonus",
    "reading_order_overlap",
]
REORDERED_SUM_COLUMNS = ["idf_overlap_score", "glyph_idf_overlap_score"]


def corpus() -> pd.DataFrame:
    """A small corpus that exercises every branch of the scoring code.

    Deliberately includes an empty row, a row that repeats a token, rows sharing
    rare and common tokens, a row whose text needs stripping, and a duplicate — the
    shapes that made the scalar path's guards necessary in the first place.
    """
    rows = [
        ("htp dji nswt wsir nb ddw", "A1 B2 C3 D4", "htp dji nswt"),
        ("htp dji nswt", "A1 B2", "htp dji"),
        ("nswt bity nb tawy", "B2 C3 E5", "nswt bity"),
        ("", "", ""),
        ("n k rare rare token", "F6", "n k"),
        ("  spaced  text  ", "  A1  ", "spaced"),
        ("htp dji nswt wsir nb ddw", "A1 B2 C3 D4", "htp dji nswt"),
        ("nb", "D4 D4 A1", "nb"),
        ("wsir nb ddw m htp", "C3 A1 D4 B2 F6", "wsir"),
        ("dji n =f anx", "G7 H8", "dji"),
    ]
    return pd.DataFrame(
        [
            {
                "source": "test",
                "source_text_id": f"T{index}",
                "source_sentence_id": f"S{index}",
                "mdc_norm": mdc,
                "hieroglyphs_norm": glyphs,
                "normalized_reading_order_norm": reading,
                "normalized_reading_order": reading,
                "transliteration_gold": mdc,
                "translation": "",
                "lemma_sequence": "",
            }
            for index, (mdc, glyphs, reading) in enumerate(rows)
        ]
    )


def tables_for(df: pd.DataFrame) -> ScoringTables:
    stats = build_corpus_stats(df)
    return ScoringTables.build(df, stats.mdc_frequencies, stats.glyph_frequencies)


# ---------- the two set signals, against their scalar reference ----------


@pytest.mark.parametrize(
    "query",
    ["htp dji nswt", "nb", "", "unseen tokens only", "htp dji nswt wsir nb ddw"],
)
def test_overlap_scores_are_bit_identical(query: str) -> None:
    df = corpus()
    table = TokenTable.build(df["mdc_norm"])
    fast = table.overlap_scores(set(tokenize_query(query)))
    reference = np.array(
        [token_overlap_score(query, value) for value in df["mdc_norm"]]
    )
    assert np.array_equal(fast, reference)


@pytest.mark.parametrize("penalty", [1.0, 0.3])
def test_overlap_scores_honour_the_surplus_penalty(penalty: float) -> None:
    df = corpus()
    table = TokenTable.build(df["mdc_norm"])
    query = "htp dji nswt"
    fast = table.overlap_scores(set(tokenize_query(query)), penalty)
    reference = np.array(
        [
            token_overlap_score(query, value, candidate_surplus_penalty=penalty)
            for value in df["mdc_norm"]
        ]
    )
    assert np.array_equal(fast, reference)


@pytest.mark.parametrize(
    "query", ["htp dji nswt", "nb", "", "unseen tokens only", "rare token"]
)
def test_idf_overlap_matches_the_scalar_reference(query: str) -> None:
    df = corpus()
    table = TokenTable.build(df["mdc_norm"])
    frequencies = document_frequencies(df["mdc_norm"])
    size = len(df)
    penalty = effective_surplus_penalty(query, 0.3)
    weights = TokenWeights.build(table, frequencies, size)
    fast = weights.idf_overlap_scores(
        table, set(tokenize_query(query)), candidate_surplus_penalty=penalty
    )
    reference = np.array(
        [
            idf_overlap_score(
                query, value, frequencies, size, candidate_surplus_penalty=penalty
            )
            for value in df["mdc_norm"]
        ]
    )
    # Same weights, same formula, different summation order — see the module
    # docstring. The tolerance is a few ulps of a score in [0, 1], not a licence
    # to drift: the ranking assertion below is the one that matters.
    assert np.allclose(fast, reference, rtol=0.0, atol=1e-12)
    assert np.array_equal(np.argsort(-fast, kind="mergesort"),
                          np.argsort(-reference, kind="mergesort"))
    # A row with no shared token must be exactly zero, not nearly zero: the
    # honest-empty-state guard in `retrieve_top_k` tests `> 0.0`.
    zero = reference == 0.0
    assert np.array_equal(fast[zero], reference[zero])


def test_idf_weights_are_stage_specific_but_the_table_is_shared() -> None:
    """The corpus's token sets do not depend on the stage; its IDF weights do."""
    df = corpus()
    table = TokenTable.build(df["mdc_norm"])
    everything = TokenWeights.build(table, document_frequencies(df["mdc_norm"]), len(df))
    subset = TokenWeights.build(
        table, document_frequencies(df["mdc_norm"].head(3)), len(df)
    )
    assert not np.array_equal(everything.weights, subset.weights)
    query = {"htp", "nswt"}
    reference = np.array(
        [
            idf_overlap_score(
                "htp nswt", value, document_frequencies(df["mdc_norm"].head(3)), len(df)
            )
            for value in df["mdc_norm"]
        ]
    )
    assert np.allclose(
        subset.idf_overlap_scores(table, query), reference, rtol=0.0, atol=1e-12
    )


# ---------- the glyph order signal ----------


def test_group_encoding_is_a_bijection_so_lcs_is_unchanged() -> None:
    """The corpus-wide group->character map scores like the per-query one.

    LCS similarity depends only on which symbols compare equal, so any bijective
    encoding gives the same answer — which is what lets the encoding be built once
    for the corpus instead of once per query.
    """
    from rapidfuzz.distance import LCSseq

    df = corpus()
    table = TokenTable.build(df["hieroglyphs_norm"], encode_groups=True)
    query = "A1 B2 C3"
    query_encoded = encode_groups(table, query)
    assert query_encoded is not None

    per_query: dict[str, str] = {}

    def encode(text: str) -> str:
        return "".join(
            per_query.setdefault(group, chr(0x20000 + len(per_query)))
            for group in str(text).split()
        )

    reference_query = encode(query)
    for position, value in enumerate(df["hieroglyphs_norm"]):
        assert LCSseq.similarity(query_encoded, table.encoded[position]) == (
            LCSseq.similarity(reference_query, encode(value))
        )


# ---------- the batched fuzzy call ----------


def test_batched_fuzzy_matches_the_scalar_loop() -> None:
    df = corpus()
    query = "htp dji nswt"
    candidates = df["mdc_norm"].astype(str)
    reference = np.array([fuzz.ratio(query, value) / 100.0 for value in candidates])
    batched = (
        process.cdist(
            [query], candidates, scorer=fuzz.ratio, dtype=np.float64, workers=1
        )[0]
        / 100.0
    )
    assert np.array_equal(batched, reference)


# ---------- the whole of combine_scores ----------


@pytest.mark.parametrize(
    ("query_mdc", "query_glyphs", "reading_order"),
    [
        ("htp dji nswt", "", ""),
        ("nb", "", ""),
        ("", "A1 B2 C3", ""),
        ("htp dji nswt", "A1 B2", "htp dji"),
        ("", "", ""),
        ("nothing here matches", "", ""),
    ],
)
def test_combine_scores_agrees_with_the_scalar_path(
    query_mdc: str, query_glyphs: str, reading_order: str
) -> None:
    df = corpus()
    stats = build_corpus_stats(df)
    reference = combine_scores(
        df,
        query_mdc_norm=query_mdc,
        query_reading_order_norm=reading_order,
        query_hieroglyphs_norm=query_glyphs,
        corpus_stats=stats,
    )
    fast = combine_scores(
        df,
        query_mdc_norm=query_mdc,
        query_reading_order_norm=reading_order,
        query_hieroglyphs_norm=query_glyphs,
        corpus_stats=stats,
        tables=tables_for(df),
    )
    for column in EXACT_COLUMNS:
        assert np.array_equal(
            fast[column].to_numpy(), reference[column].to_numpy()
        ), column
    for column in REORDERED_SUM_COLUMNS:
        assert np.allclose(
            fast[column].to_numpy(),
            reference[column].to_numpy(),
            rtol=0.0,
            atol=1e-12,
        ), column
    assert np.allclose(
        fast["final_score"].to_numpy(),
        reference["final_score"].to_numpy(),
        rtol=0.0,
        atol=1e-12,
    )
    # The ranking — which is what a user sees — must be identical, row for row.
    assert list(fast.index) == list(reference.index)


@pytest.mark.parametrize(
    ("query", "glyphs"),
    [("htp dji nswt", None), ("nb", None), ("wsir nb ddw", None)],
)
def test_retrieve_top_k_ranks_the_same_with_and_without_the_tables(
    query: str, glyphs: str | None
) -> None:
    """The whole retrieval path, fast vs scalar, on the same index.

    Only `tables` differs between the two indexes, so the document frequencies,
    the n-gram index and the query parse (which reads the index's vocabulary) are
    identical and any difference is the fast path's alone.
    """
    from app.services.retrieval import SearchIndex, build_search_index, retrieve_top_k

    df = corpus()
    index = build_search_index(df)
    assert index.tables is not None
    scalar = SearchIndex(stats=index.stats, text_index=index.text_index, tables=None)

    fast_top = retrieve_top_k(
        df, query, k=5, query_hieroglyphs_norm=glyphs, index=index
    )
    scalar_top = retrieve_top_k(
        df, query, k=5, query_hieroglyphs_norm=glyphs, index=scalar
    )
    assert list(fast_top.index) == list(scalar_top.index)
    for column in EXACT_COLUMNS:
        assert np.array_equal(
            fast_top[column].to_numpy(), scalar_top[column].to_numpy()
        ), column
    assert np.allclose(
        fast_top["final_score"].to_numpy(),
        scalar_top["final_score"].to_numpy(),
        rtol=0.0,
        atol=1e-12,
    )


def test_tables_built_from_another_frame_are_ignored() -> None:
    """A mismatched `ScoringTables` must not be trusted: the rows are positional.

    Scoring a filtered or reordered frame with tables built from a different one
    would silently attach the wrong row's tokens to every score, so the check is on
    the row labels, not just the length.
    """
    df = corpus()
    shuffled = df.iloc[::-1]
    reference = combine_scores(shuffled, query_mdc_norm="htp dji nswt")
    with_wrong_tables = combine_scores(
        shuffled, query_mdc_norm="htp dji nswt", tables=tables_for(df)
    )
    assert np.array_equal(
        with_wrong_tables["overlap_score"].to_numpy(),
        reference["overlap_score"].to_numpy(),
    )
    assert list(with_wrong_tables.index) == list(reference.index)
