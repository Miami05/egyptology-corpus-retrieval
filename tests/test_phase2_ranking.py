"""Phase 2 — ranking and suggestion correctness.

Each test pins a defect verified in the 2026-08-29 audit: order-blind glyph ranking
(permutation collisions, free repetition), the suggestion layer dividing by weight
that could never fire, the always-three-suggestions behaviour, the empty-string
degeneracy, Latin residue double-scoring a glyph query, duplicate rows inflating
support, and the reverse-alphabetical tie-break.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.retrieval.scorer import DEFAULT_WEIGHTS, combine_scores
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import suggest_top_readings


def frame(rows: list[dict]) -> pd.DataFrame:
    """Minimal corpus frame with every column the retrieval stack touches."""
    defaults = {
        "source": "test",
        "mdc_norm": "",
        "hieroglyphs_norm": "",
        "transliteration_gold": "",
        "translation": "",
        "lemma_sequence": "",
        "normalized_reading_order_norm": "",
        "normalized_reading_order": "",
    }
    out = []
    for index, row in enumerate(rows):
        merged = {
            **defaults,
            "source_text_id": f"T{index}",
            "source_sentence_id": f"S{index}",
            **row,
        }
        out.append(merged)
    return pd.DataFrame(out)


# ---------- order sensitivity ----------


def test_repetition_no_longer_scores_free():
    """A query of three identical groups used to score 1.0 against one occurrence."""
    df = frame(
        [
            {"hieroglyphs_norm": "E", "transliteration_gold": "ꜥḥꜥ"},
            {"hieroglyphs_norm": "E E E", "transliteration_gold": "ꜥḥꜥ ꜥḥꜥ ꜥḥꜥ"},
        ]
    )
    scored = combine_scores(df, query_mdc_norm="", query_hieroglyphs_norm="E E E")
    by_glyphs = scored.set_index("hieroglyphs_norm")
    assert by_glyphs.loc["E E E", "final_score"] > by_glyphs.loc["E", "final_score"]
    assert by_glyphs.loc["E", "glyph_order_score"] == pytest.approx(1 / 3)


def test_group_order_separates_otherwise_identical_sets():
    df = frame(
        [
            {"hieroglyphs_norm": "A B C D", "transliteration_gold": "a b c d"},
            {"hieroglyphs_norm": "D C B A", "transliteration_gold": "d c b a"},
        ]
    )
    scored = combine_scores(df, query_mdc_norm="", query_hieroglyphs_norm="A B D C")
    scores = scored.set_index("hieroglyphs_norm")["glyph_order_score"]
    # Three of four query groups follow the first row's order, only two the reversed one.
    assert scores["A B C D"] == pytest.approx(3 / 4)
    assert scores["D C B A"] < scores["A B C D"]


def test_ranking_is_deterministic_and_stable():
    df = frame(
        [{"hieroglyphs_norm": f"X{i}", "transliteration_gold": f"x{i}"} for i in range(30)]
        + [{"hieroglyphs_norm": "Q", "transliteration_gold": "q"}]
    )
    first = retrieve_top_k(df, query_mdc="", k=10, query_hieroglyphs_norm="Q")
    second = retrieve_top_k(df, query_mdc="", k=10, query_hieroglyphs_norm="Q")
    assert first["source_text_id"].tolist() == second["source_text_id"].tolist()


# ---------- honest empty state ----------


def test_no_shared_evidence_returns_empty_not_k_rows():
    df = frame(
        [
            {"hieroglyphs_norm": "A B", "transliteration_gold": "a b"},
            {"hieroglyphs_norm": "C D", "transliteration_gold": "c d"},
        ]
    )
    result = retrieve_top_k(df, query_mdc="", k=3, query_hieroglyphs_norm="Z9 Z8")
    assert result.empty
    assert suggest_top_readings(result, query_mdc="", query_hieroglyphs="Z9 Z8") == []


def test_text_query_with_no_shared_tokens_returns_empty():
    df = frame([{"mdc_norm": "htp dji nswt", "transliteration_gold": "ḥtp-ḏi̯-nswt"}])
    result = retrieve_top_k(df, query_mdc="zzz qqq www", k=3)
    assert result.empty


def test_partial_evidence_still_returns_results():
    df = frame([{"mdc_norm": "htp dji nswt", "transliteration_gold": "ḥtp-ḏi̯-nswt"}])
    result = retrieve_top_k(df, query_mdc="htp", k=3)
    assert len(result) == 1


# ---------- degeneracies the audit found ----------


def test_row_without_transliteration_is_not_a_universal_match():
    """fuzz.ratio('', '') is 100 and the cosine of two empty vectors is 1.0; a row
    with an empty mdc_norm must not top every hieroglyph query on that account."""
    df = frame(
        [
            {"mdc_norm": "", "hieroglyphs_norm": "M N", "transliteration_gold": "m n"},
            {"hieroglyphs_norm": "Q R", "transliteration_gold": "q r", "mdc_norm": "q r"},
        ]
    )
    result = retrieve_top_k(df, query_mdc="", k=3, query_hieroglyphs_norm="Q R")
    assert result.iloc[0]["hieroglyphs_norm"] == "Q R"
    assert (result["hieroglyphs_norm"] == "M N").sum() == 0  # no shared evidence


def test_latin_residue_does_not_change_a_glyph_ranking():
    """Appending a stray Latin word to an exact glyph query dropped it 1.000 → 0.732."""
    df = frame(
        [
            {"hieroglyphs_norm": "𓊵𓏙 𓇓𓏏", "mdc_norm": "htp nswt", "transliteration_gold": "ḥtp nswt"},
            {"hieroglyphs_norm": "𓊵𓏙 𓅓", "mdc_norm": "htp m", "transliteration_gold": "ḥtp m"},
        ]
    )
    clean = retrieve_top_k(df, query_mdc="𓊵𓏙 𓇓𓏏", k=2)
    noisy = retrieve_top_k(df, query_mdc="𓊵𓏙 𓇓𓏏 wad", k=2)
    assert clean.iloc[0]["hieroglyphs_norm"] == noisy.iloc[0]["hieroglyphs_norm"]
    assert clean.iloc[0]["final_score"] == pytest.approx(noisy.iloc[0]["final_score"])


# ---------- suggestion layer ----------


def suggestion_pool(rows: list[dict], query_glyphs: str) -> pd.DataFrame:
    return retrieve_top_k(frame(rows), query_mdc="", k=50, query_hieroglyphs_norm=query_glyphs)


def test_exact_glyph_match_gets_high_confidence():
    """The old fixed denominator capped every glyph confidence at ~0.38."""
    pool = suggestion_pool(
        [
            {"hieroglyphs_norm": "𓊵𓏙 𓇓𓏏", "transliteration_gold": "ḥtp nswt", "lemma_sequence": "1|a 2|b"},
            {"hieroglyphs_norm": "𓊵𓏙 𓅓", "transliteration_gold": "ḥtp m"},
        ],
        "𓊵𓏙 𓇓𓏏",
    )
    suggestions = suggest_top_readings(pool, query_mdc="", query_hieroglyphs="𓊵𓏙 𓇓𓏏")
    assert suggestions[0].candidate_transliteration == "ḥtp nswt"
    assert suggestions[0].confidence_score >= 0.8
    assert "same sign groups as the query" in suggestions[0].evidence_summary


def test_duplicate_rows_count_as_one_attestation():
    row = {"hieroglyphs_norm": "𓊵𓏙", "transliteration_gold": "ḥtp", "translation": "x"}
    pool = suggestion_pool([row, dict(row), dict(row)], "𓊵𓏙")
    suggestions = suggest_top_readings(pool, query_mdc="", query_hieroglyphs="𓊵𓏙")
    assert suggestions[0].supporting_example_count == 1


def test_ties_break_alphabetically_ascending():
    rows = [
        {"hieroglyphs_norm": "𓊵𓏙 𓇓𓏏", "transliteration_gold": "zz-tie"},
        {"hieroglyphs_norm": "𓊵𓏙 𓇓𓏏", "transliteration_gold": "aa-tie"},
    ]
    pool = suggestion_pool(rows, "𓊵𓏙 𓇓𓏏")
    suggestions = suggest_top_readings(pool, query_mdc="", query_hieroglyphs="𓊵𓏙 𓇓𓏏")
    assert [s.candidate_transliteration for s in suggestions] == ["aa-tie", "zz-tie"]


def test_transliteration_queries_still_use_the_text_signals():
    pool = retrieve_top_k(
        frame(
            [
                {"mdc_norm": "htp dji nswt", "transliteration_gold": "ḥtp-ḏi̯-nswt"},
                {"mdc_norm": "htp m pr", "transliteration_gold": "ḥtp m pr"},
            ]
        ),
        query_mdc="htp dji nswt",
        k=50,
    )
    suggestions = suggest_top_readings(pool, query_mdc="htp dji nswt")
    assert suggestions[0].candidate_transliteration == "ḥtp-ḏi̯-nswt"
    assert suggestions[0].confidence_score >= 0.8


# ---------- evidence line ----------


def test_glyph_hit_evidence_names_the_sign_signals():
    df = frame([{"hieroglyphs_norm": "𓊵𓏙 𓇓𓏏", "transliteration_gold": "ḥtp nswt"}])
    result = retrieve_top_k(df, query_mdc="", k=1, query_hieroglyphs_norm="𓊵𓏙 𓇓𓏏")
    evidence = result.iloc[0]["evidence"]
    assert "sign" in evidence
    assert "fuzzy=0.00" not in evidence


# ---------- the audit's real-corpus regression fixtures ----------


@pytest.fixture(scope="module")
def corpus_df():
    from app.data.loader import load_examples_csv

    return load_examples_csv("data/processed/examples.csv")


def test_permutation_collision_rows_no_longer_tie(corpus_df):
    """Rows 1105 and 4763 hold the same sign-group multiset in different orders.
    For a third, unattested order they used to score identically."""
    a = str(corpus_df.iloc[1105]["hieroglyphs_norm"]).split()
    b = str(corpus_df.iloc[4763]["hieroglyphs_norm"]).split()
    assert sorted(a) == sorted(b) and a != b, "fixture rows changed — pick new ones"
    third_order = " ".join(a[1:] + a[:1])  # a rotation: attested nowhere
    scored = combine_scores(
        corpus_df, query_mdc_norm="", query_hieroglyphs_norm=third_order
    )
    scores = scored.loc[[1105, 4763], "final_score"]
    assert scores.loc[1105] != scores.loc[4763]


def test_junk_query_returns_no_parallel_on_the_real_corpus(corpus_df):
    result = retrieve_top_k(
        corpus_df, query_mdc="", k=3, query_hieroglyphs_norm="𓀀𓀁𓀂𓀃𓀄"
    )
    # One unattested five-glyph blob shares no *group* with anything.
    assert result.empty
    assert suggest_top_readings(result, query_mdc="", query_hieroglyphs="𓀀𓀁𓀂𓀃𓀄") == []
