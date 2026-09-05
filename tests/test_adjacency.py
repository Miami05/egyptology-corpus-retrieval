"""The Experiment 2 bigram definition, and the read-only debug hook it needed.

`app/services/adjacency.py` is measurement code: at step 0 nothing in the ranking
path imports it. These tests pin the definition that was frozen before the run, so a
later reader can see exactly what "bigram count" meant, and pin that passing
`debug_signals` to `suggest_top_readings` leaves its output byte-identical.
"""

from __future__ import annotations

import pandas as pd

from app.services.adjacency import (
    adjacency_score,
    adjacency_tokens,
    bigram_matches,
    count_matches,
    query_bigrams,
)
from app.services.suggestions import suggest_top_readings


def test_plain_query_yields_consecutive_pairs_in_order():
    assert query_bigrams(["a", "b", "c"]) == [("a", "b", 0), ("b", "c", 0)]


def test_repeated_pair_counts_once():
    assert query_bigrams(["a", "b", "a", "b"]) == [("a", "b", 0), ("b", "a", 0)]


def test_placeholder_is_a_spanner_not_a_token():
    # `a _ b` yields the gap-1 pair (a, b) and no pair with `_` in it.
    assert query_bigrams(["a", "_", "b"]) == [("a", "b", 1)]


def test_two_placeholders_in_a_row_earn_nothing():
    assert query_bigrams(["a", "_", "_", "b"]) == []
    assert query_bigrams(["_", "_"]) == []


def test_placeholder_does_not_block_the_pairs_around_it():
    assert query_bigrams(["a", "b", "_", "c", "d"]) == [
        ("a", "b", 0),
        ("c", "d", 0),
        ("b", "c", 1),
    ]


def test_gap_zero_bigram_needs_immediate_adjacency():
    assert bigram_matches(("a", "b", 0), ["x", "a", "b", "y"]) is True
    assert bigram_matches(("a", "b", 0), ["a", "x", "b"]) is False


def test_gap_one_bigram_needs_exactly_one_intervening_token():
    assert bigram_matches(("a", "b", 1), ["a", "x", "b"]) is True
    assert bigram_matches(("a", "b", 1), ["a", "b"]) is False
    assert bigram_matches(("a", "b", 1), ["a", "x", "y", "b"]) is False


def test_count_and_score_are_over_the_query_side_only():
    bigrams = query_bigrams(["a", "b", "c"])
    # A candidate three times as long is not penalised for its surplus words.
    long_candidate = ["z"] * 9 + ["a", "b", "c"] + ["z"] * 9
    assert count_matches(bigrams, long_candidate) == 2
    assert adjacency_score(bigrams, long_candidate) == 1.0
    assert adjacency_score(bigrams, ["a", "b"]) == 0.5


def test_score_is_zero_when_the_query_has_no_eligible_bigram():
    assert adjacency_score(query_bigrams(["a"]), ["a"]) == 0.0
    assert adjacency_score(query_bigrams(["_", "_"]), ["a", "b"]) == 0.0


def test_tokenizer_is_the_rankers_loose_fold():
    # `_` survives the fold as its own token; the loose fold ASCII-folds a reading.
    assert adjacency_tokens("ḏi p _ a mr ḏ") == ["dji", "p", "_", "a", "mr", "dj"]
    # Editorial marks and the morpheme dot split, exactly as the ranker's own
    # token overlap sees them.
    assert adjacency_tokens("nṯr.du ꞽpw") == ["ntjr", "du", "ipw"]


def _tiny_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "transliteration_gold": "ḥtp ḏi̯ nswt",
                "final_score": 0.9,
                "lemma_sequence": "1|htp",
                "source": "t",
                "source_text_id": "T1",
                "source_sentence_id": "S1",
                "translation": "an offering",
            },
            {
                "transliteration_gold": "ḥtp nṯr ꜥꜣ",
                "final_score": 0.7,
                "lemma_sequence": "",
                "source": "t",
                "source_text_id": "T1",
                "source_sentence_id": "S2",
                "translation": "a great god",
            },
        ]
    )


def test_debug_signals_hook_does_not_change_the_suggestions():
    frame = _tiny_frame()
    without = suggest_top_readings(frame, query_mdc="ḥtp ḏi̯ nswt", top_n=3)
    sink: list[dict] = []
    with_hook = suggest_top_readings(
        frame, query_mdc="ḥtp ḏi̯ nswt", top_n=3, debug_signals=sink
    )
    assert with_hook == without
    assert len(sink) == 2


def test_debug_signals_report_the_terms_the_confidence_is_built_from():
    frame = _tiny_frame()
    sink: list[dict] = []
    suggestions = suggest_top_readings(
        frame, query_mdc="ḥtp ḏi̯ nswt", top_n=3, debug_signals=sink
    )
    top = suggestions[0]
    entry = next(
        item
        for item in sink
        if item["candidate_transliteration"] == top.candidate_transliteration
    )
    # The reported terms reconstruct the reported confidence exactly.
    weighted = sum(term["weighted"] for term in entry["signals"].values())
    assert weighted == entry["weighted_sum"]
    assert round(weighted / entry["weight_mass"], 3) == top.confidence_score
    for term in entry["signals"].values():
        assert term["weighted"] == term["weight"] * term["value"]
