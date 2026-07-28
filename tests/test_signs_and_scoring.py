"""Tests for the sign index and for score renormalisation.

Both encode lessons from bugs found in this project: multivalence counts were inflated
by editorial bracket variants, and 30% of the ranking weight sat on empty columns.
"""

from __future__ import annotations

import pandas as pd

from app.retrieval.scorer import (
    DEFAULT_WEIGHTS,
    combine_scores,
    document_frequencies,
    idf_overlap_score,
    token_overlap_score,
)
from app.services.signs import build_sign_index, multivalence_summary, ranked_multivalent


def sign_corpus(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "hieroglyphs_norm": signs,
                "transliteration_gold": readings,
                "source_text_id": f"T{i}",
                "source_sentence_id": f"S{i}",
                "translation": "",
                "period": "Old Kingdom",
                "lemma_sequence": "",
            }
            for i, (signs, readings) in enumerate(rows)
        ]
    )


# ---------- sign index ----------


def test_editorial_variants_are_not_counted_as_multivalence():
    """`n.t` and `n(.ꞽ).t` are one reading bracketed differently, not two readings."""
    index = build_sign_index(sign_corpus([("A", "n.t"), ("A", "n(.ꞽ).t")]))
    entry = index["A"]
    assert entry.literal_count == 2
    assert entry.distinct_count == 1
    assert entry.is_multivalent is False
    assert entry.editorial_variants_only == 1


def test_genuinely_different_readings_are_multivalent():
    index = build_sign_index(sign_corpus([("A", "sw"), ("A", "nswt")]))
    assert index["A"].is_multivalent is True
    assert index["A"].distinct_count == 2


def test_summary_separates_genuine_from_editorial():
    index = build_sign_index(
        sign_corpus(
            [
                ("A", "sw"),
                ("A", "nswt"),
                ("B", "n.t"),
                ("B", "n(.ꞽ).t"),
                ("C", "z"),
            ]
        )
    )
    summary = multivalence_summary(index)
    assert summary["sign_groups"] == 3
    assert summary["literal_multi"] == 2
    assert summary["genuinely_multivalent"] == 1
    assert summary["editorial_only"] == 1


def test_misaligned_rows_are_skipped():
    index = build_sign_index(sign_corpus([("A B", "x")]))
    assert index == {}


def test_examples_are_captured_per_reading():
    index = build_sign_index(sign_corpus([("A", "sw"), ("A", "nswt")]))
    assert set(index["A"].examples) == {"sw", "nswt"}
    assert index["A"].examples["sw"][0]["source_text_id"] == "T0"


def test_ranked_multivalent_orders_by_attestation():
    index = build_sign_index(
        sign_corpus(
            [("A", "x"), ("A", "y"), ("A", "x"), ("B", "p"), ("B", "q")]
        )
    )
    ranked = ranked_multivalent(index)
    assert [entry.sign for entry in ranked] == ["A", "B"]


# ---------- scoring ----------


def test_idf_overlap_prefers_rare_shared_tokens():
    """A shared rare token must outrank a shared ubiquitous one."""
    corpus = pd.Series(["n k rare", "n k common", "n k other", "n k thing"])
    frequencies = document_frequencies(corpus)
    size = len(corpus)
    rare_match = idf_overlap_score("n k rare", "n k rare", frequencies, size)
    common_only = idf_overlap_score("n k rare", "n k other", frequencies, size)
    assert rare_match > common_only

    # Plain Jaccard cannot express that difference as sharply.
    assert token_overlap_score("n k rare", "n k other") == 0.5


def scoring_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "mdc_norm": "htp dji nswt",
                "normalized_reading_order_norm": "",
                "hieroglyphs_norm": "A B C",
                "deity_norm": "",
                "formula_type_norm": "",
                "formula_slot_norm": "",
                "offering_items_norm": "",
                "recipient_norm": "",
                "aesthetic_arrangement_flag_bool": False,
                "fuzzy_score": 1.0,
                "tfidf_score": 1.0,
            },
            {
                "mdc_norm": "something else",
                "normalized_reading_order_norm": "",
                "hieroglyphs_norm": "X Y Z",
                "deity_norm": "",
                "formula_type_norm": "",
                "formula_slot_norm": "",
                "offering_items_norm": "",
                "recipient_norm": "",
                "aesthetic_arrangement_flag_bool": False,
                "fuzzy_score": 0.0,
                "tfidf_score": 0.0,
            },
        ]
    )


def test_empty_metadata_columns_do_not_dilute_the_score():
    """A perfect match must approach 1.0 even when metadata signals are empty.

    Before renormalisation those empty columns kept 30% of the weight, capping a
    perfect textual match near 0.6 and making confidences incomparable.
    """
    scored = combine_scores(scoring_frame(), query_mdc_norm="htp dji nswt")
    best = scored.iloc[0]
    assert best["mdc_norm"] == "htp dji nswt"
    assert best["final_score"] > 0.9


def test_sign_query_scores_from_sign_evidence_only():
    scored = combine_scores(
        scoring_frame(),
        query_mdc_norm="",
        query_hieroglyphs_norm="A B C",
    )
    best = scored.iloc[0]
    assert best["hieroglyphs_norm"] == "A B C"
    assert best["glyph_exact_bonus"] == 1.0
    assert best["final_score"] > 0.9


def test_scores_are_zero_when_no_signal_is_active():
    scored = combine_scores(scoring_frame().assign(fuzzy_score=0.0, tfidf_score=0.0),
                            query_mdc_norm="")
    assert scored["final_score"].max() == 0.0


def test_weights_object_is_immutable_and_replaceable():
    changed = DEFAULT_WEIGHTS.replace(fuzzy=0.99)
    assert changed.fuzzy == 0.99
    assert DEFAULT_WEIGHTS.fuzzy != 0.99
