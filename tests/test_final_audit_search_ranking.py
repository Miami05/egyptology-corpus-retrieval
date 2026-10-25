"""Final audit 2026-10-25, search-ranking scope (Opus + Astra, cross-verified).

- search-ranking-1: the strict comparison form folds the yod's encodings
  (`j ı ı͗ i` → `ꞽ`) and `ḳ`/`ṱ` like the search key does, so `ḥm.t=j` meets `ḥm.t =ꞽ`
  again; different consonants (ꜣ/ꜥ, ḥ/h) stay apart (A54).
- search-ranking-2 (Astra): mixed mode compares the candidate *as written* with the
  query as written, so an identical reading with morpheme dots is similarity 1.
- search-ranking-2 (Opus, low): shared tokens are shown as the candidate's own words
  in strict and mixed mode, not as marker-split fragments.
- search-ranking-3: an editor-supplied yod `(.ꞽ)` still vanishes for a loose query
  word in mixed mode (`n.t ḥtp` against `n(.ꞽ).t ḥtp`).
- search-ranking-5: `ḥtp {n}` and `ḥtp n` are two suggestions, as `comparison_key`
  promises.
Everything here is synthetic and runs without the corpus.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.suggestions import (
    QueryForms,
    comparison_key,
    suggest_top_readings,
    unfolded_reading_form,
)


def _frame(*readings: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "transliteration_gold": list(readings),
            "final_score": [1.0] * len(readings),
            "hieroglyphs_norm": [f"g{i}" for i in range(len(readings))],
            "translation": [f"t{i}" for i in range(len(readings))],
        }
    )


def _top(query: str, *readings: str):
    return suggest_top_readings(_frame(*readings), query)


@pytest.mark.parametrize(
    "query, candidate",
    [
        ("ḥm.t=j", "ḥm.t =ꞽ"),
        ("jmn-ḥtp", "ꞽmn-ḥtp"),
        ("imn-ḥtp", "ꞽmn-ḥtp"),
        ("ḳd ḥm", "qd ḥm"),
        ("ḥtp ḏꞽ nswt", "ḥtp ḏı͗ nswt"),
        ("ḥtp ḏj nswt", "ḥtp ḏꞽ nswt"),
        ("wnḫwꞽ", "wnḫwı͗"),
    ],
)
def test_equivalent_yod_and_letter_variants_match_in_strict_mode(query, candidate):
    (suggestion,) = _top(query, candidate)
    assert "same simplified query reading" in suggestion.evidence_summary
    assert suggestion.confidence_score >= 0.9


def test_strict_fold_keeps_different_consonants_apart():
    assert unfolded_reading_form("ꜣḥꜥ") != unfolded_reading_form("ꜥḥꜥ")
    assert unfolded_reading_form("ḥtp") != unfolded_reading_form("htp")
    assert unfolded_reading_form("ḫt") != unfolded_reading_form("ẖt")
    (suggestion,) = _top("ꜣḥꜥ", "ꜥḥꜥ")
    assert suggestion.confidence_score < 0.5


def test_correct_yod_reading_outranks_the_incomplete_one():
    result = _top("ḥm.t=j nfr.t", "ḥm.t nfr.t", "ḥm.t =ꞽ nfr.t")
    assert result[0].candidate_transliteration == "ḥm.t =ꞽ nfr.t"


def test_mixed_identical_reading_with_dots_has_full_char_similarity():
    forms = QueryForms.build("ꜥḥꜥ.n stẖ qnd", "ꜥḥꜥ.n stẖ qnd")
    assert forms.mode == "mixed"
    reading = "ꜥḥꜥ.n stẖ qnd"
    key = comparison_key(reading)
    assert forms.char_similarity(key, key, reading) == pytest.approx(1.0)
    dbg: list[dict] = []
    suggest_top_readings(_frame(reading), reading, debug_signals=dbg)
    assert dbg[0]["signals"]["char_similarity"]["value"] == pytest.approx(1.0)


def test_mixed_editorial_yod_drops_for_a_loose_query_word():
    forms = QueryForms.build("n.t ḥtp", "n.t ḥtp")
    assert forms.mode == "mixed"
    assert forms.candidate("n(.ꞽ).t ḥtp") == forms.query_form
    (suggestion,) = _top("n.t ḥtp", "n(.ꞽ).t ḥtp")
    assert "same simplified query reading" in suggestion.evidence_summary


def test_mixed_editorial_yod_kept_for_a_strict_query_word():
    """Follow-up (Astra): the yod is dropped only inside a word compared loosely.
    `ḥm.t` is typed in Unicode, so `ḥm(.ꞽ).t` is a different spelling of it and must
    not become the identical simplified reading (confidence 0.625 → 0.904)."""
    forms = QueryForms.build("ḥm.t n", "ḥm.t n")
    assert forms.mode == "mixed"
    assert forms.candidate("ḥm(.ꞽ).t n") != forms.query_form
    (suggestion,) = _top("ḥm.t n", "ḥm(.ꞽ).t n")
    assert "same simplified query reading" not in suggestion.evidence_summary
    assert suggestion.confidence_score < 0.9
    # The loose word in the same query still loses its editorial yod.
    forms = QueryForms.build("n.t ḥtp ḥm.t", "n.t ḥtp ḥm.t")
    assert forms.candidate("n(.ꞽ).t ḥtp ḥm.t") == forms.query_form
    assert forms.candidate("n(.ꞽ).t ḥtp ḥm(.ꞽ).t") != forms.query_form


@pytest.mark.parametrize(
    "query, candidate, shown",
    [
        ("ḥm.t=ꞽ", "ḥm.t =ꞽ", "ḥm.t, =ꞽ"),
        ("ꞽrꞽ-pꜥ.t", "(ꞽ)r(.ꞽ)-pꜥ.t", "(ꞽ)r(.ꞽ)-pꜥ.t"),
        ("ḏd mdw", "ḏd-mdw", "ḏd-mdw"),
    ],
)
def test_shared_tokens_are_shown_as_candidate_words(query, candidate, shown):
    (suggestion,) = _top(query, candidate)
    assert f"shared transliteration tokens: {shown};" in suggestion.evidence_summary


def test_superfluous_braces_keep_two_suggestions():
    result = _top("ḥtp", "ḥtp {n}", "ḥtp n")
    assert sorted(s.candidate_transliteration for s in result) == ["ḥtp n", "ḥtp {n}"]
    assert all(s.supporting_example_count == 1 for s in result)
