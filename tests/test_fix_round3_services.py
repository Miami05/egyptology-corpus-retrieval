"""Fix round 3 (2026-10-25), services: Astra's re-review of fix round 2.

- A54: query words and candidate words are paired by a maximum matching, so a
  candidate word that fits both a loose and a strict query token never takes the
  loose one when that leaves the strict one unmet.
- A54: the competitive-ambiguity evaluator passes the typed query as `query_raw`,
  like the app and both inspect scripts.
- A17 (nit): a superfluous `{…}` span across a space joins what survives on either
  side into one word, as `drop_superfluous_text` does.
Everything here is synthetic and runs without the corpus.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from app.data.normalizer import drop_superfluous_text, superfluous_kept_words
from app.services.suggestions import QueryForms, suggest_top_readings

ROOT = Path(__file__).resolve().parents[1]


def _row(translit: str, score: float) -> dict:
    return {
        "transliteration_gold": translit,
        "final_score": score,
        "hieroglyphs_norm": "𓊵 𓏏 𓊪",
        "translation": "x",
        "source": "AES",
        "source_text_id": f"t{translit}",
        "source_sentence_id": "s",
    }


def _by_reading(result):
    return {s.candidate_transliteration: s for s in result}


def test_a54_a_positional_loose_match_is_reassigned_to_free_the_strict_token():
    forms = QueryForms.build("aha ꜥḥꜥ n", "aha ꜥḥꜥ n")
    assert forms.mode == "mixed"
    # `ꜥḥꜥ` (first word) fits the positional loose `aha` and the strict `ꜥḥꜥ`; the
    # last word `ꜣḥꜥ` fits only `aha`. Only the matching meets all three tokens.
    assert sorted(forms.candidate("ꜥḥꜥ n ꜣḥꜥ").split()) == sorted(forms.query_form.split())
    assert "ꜥḥꜥ" not in forms.candidate("ꜣḥꜥ n ꜣḥꜥ").split()


def test_a54_the_wrong_consonant_no_longer_ties_or_sorts_first():
    # Astra's repro: both used to get identical signals and 0.435 confidence.
    frame = pd.DataFrame([_row("ꜣḥꜥ n ꜣḥꜥ", 0.8), _row("ꜥḥꜥ n ꜣḥꜥ", 0.8)])
    result = suggest_top_readings(frame, "aha ꜥḥꜥ n")
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ꜥḥꜥ n ꜣḥꜥ"
    assert by["ꜥḥꜥ n ꜣḥꜥ"].confidence_score > by["ꜣḥꜥ n ꜣḥꜥ"].confidence_score


def test_a54_the_evaluator_passes_the_raw_query():
    script = ROOT / "scripts/run_competitive_ambiguity_eval.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", "")) == "suggest_top_readings"
    ]
    assert calls
    for call in calls:
        keywords = {kw.arg: kw.value for kw in call.keywords}
        assert isinstance(keywords.get("query_raw"), ast.Name)
        assert keywords["query_raw"].id == "query_input"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("h{a b}tp ḏi", ["htp", "", "ḏi"]),
        ("a{b  c}d e", ["ad", "", "e"]),
        ("ḥtp {n nswt}", ["ḥtp", "", ""]),
        ("{a b} {{c d}}", ["", "", "c", "d"]),
    ],
)
def test_a17_a_deleted_span_across_a_space_joins_the_survivors(text, expected):
    kept = superfluous_kept_words(text)
    assert kept == expected
    assert len(kept) == len(text.split())
    assert [w for w in kept if w] == drop_superfluous_text(text).split()


def test_a17_a_split_word_no_longer_outranks_the_real_reading():
    # Astra's repro: `h{a b}tp ḏi` became `h tp ḏi` and ranked `h tp ḏi` at 0.904.
    frame = pd.DataFrame([_row("h tp ḏi", 0.8), _row("ḥtp ḏi", 0.8)])
    result = suggest_top_readings(frame, "h{a b}tp ḏi")
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ḥtp ḏi"
    assert by["ḥtp ḏi"].confidence_score > by["h tp ḏi"].confidence_score
