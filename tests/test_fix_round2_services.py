"""Fix round 2 (2026-10-25), services: Opus and Astra reviews of fix round 1.

Each test names the finding it pins: A54 (a loose and a strict query word that fold
alike, the inspect scripts' caller contract), A17 (braces spanning a space in a mixed
query, the comparison key, the loader fallback), A53 (borrowed readings do not count
as coverage; coverage is reported) and A21 (the UI says what the bar means).
Everything here is synthetic and runs without the corpus.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.loader import _normalize_corpus_frame
from app.data.normalizer import drop_superfluous_text, search_fold, superfluous_kept_words
from app.services.reading_model import ReadingModel, train_reading_model
from app.services.stage import STAGES, choose_stage_by_likelihood
from app.services.suggestions import QueryForms, comparison_key, suggest_top_readings

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


# --------------------------------------------------------------------------- #
# A54: a loose and a strict query word that fold to the same spelling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("query", ["aha ꜥḥꜥ", "ꜥḥꜥ aha"])
def test_a54_a_loose_word_cannot_erase_a_strict_one(query):
    # Astra's repro: equal retrieval scores, and the wrong reading used to tie the
    # right one at 0.390 and sort first.
    frame = pd.DataFrame([_row("ꜣḥꜥ ꜣḥꜥ", 0.8), _row("ꜥḥꜥ ꜥḥꜥ", 0.8)])
    result = suggest_top_readings(frame, query)
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ꜥḥꜥ ꜥḥꜥ"
    assert "same simplified query reading" in by["ꜥḥꜥ ꜥḥꜥ"].evidence_summary
    assert by["ꜥḥꜥ ꜥḥꜥ"].confidence_score > by["ꜣḥꜥ ꜣḥꜥ"].confidence_score + 0.3


def test_a54_htp_and_hetep_typed_together_are_told_apart():
    frame = pd.DataFrame([_row("htp htp", 0.8), _row("ḥtp ḥtp", 0.8)])
    result = suggest_top_readings(frame, "htp ḥtp")
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ḥtp ḥtp"
    assert by["ḥtp ḥtp"].confidence_score > by["htp htp"].confidence_score


def test_a54_each_query_token_keeps_its_own_constraint():
    forms = QueryForms.build("aha ꜥḥꜥ", "aha ꜥḥꜥ")
    assert forms.mode == "mixed"
    assert forms.tokens == (("aha", True), ("ꜥḥꜥ", False))
    assert forms.candidate("ꜥḥꜥ ꜥḥꜥ") == forms.query_form
    assert forms.candidate("ꜣḥꜥ ꜣḥꜥ") == "aha aha"
    # Unaligned: the unclaimed loose token is still found further along.
    assert set(forms.candidate("nb ꜥḥꜥ ꜥḥꜥ").split()) == {"nb", "ꜥḥꜥ", "aha"}


@pytest.mark.parametrize(
    "script", ["scripts/inspect_suggestion_boundary.py", "scripts/inspect_adjacency_precheck.py"]
)
def test_a54_inspect_scripts_pass_the_raw_query(script):
    tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
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


# --------------------------------------------------------------------------- #
# A17: superfluous text never comes back as evidence
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ḥtp {n nswt}", ["ḥtp", "", ""]),
        ("{a{b}c} d", ["", "d"]),
        ("{{šꜥ{f}.t}}", ["šꜥ.t"]),
        ("{a b} {{c d}}", ["", "", "c", "d"]),
        ("nb{.t} ḏd.n={f}", ["nb", "ḏd.n="]),
    ],
)
def test_a17_kept_words_follow_drop_superfluous_text(text, expected):
    kept = superfluous_kept_words(text)
    assert kept == expected
    assert " ".join(w for w in kept if w).split() == drop_superfluous_text(text).split()


def test_a17_a_brace_spanning_a_space_is_deleted_in_a_mixed_query():
    # Astra's repro, mixed form: `htp` typed in ASCII so the query is per-word.
    frame = pd.DataFrame([_row("ḥtp n nswt ḏi", 0.8), _row("ḥtp ḏi", 0.8)])
    result = suggest_top_readings(frame, "htp {n nswt} ḏi")
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ḥtp ḏi"
    assert "same simplified query reading" in by["ḥtp ḏi"].evidence_summary
    assert "simplified query reading" not in by["ḥtp n nswt ḏi"].evidence_summary
    assert by["ḥtp n nswt ḏi"].confidence_score < 0.5


def test_a17_the_exact_key_does_not_bring_braced_text_back():
    # Astra's repro (`ḥtp {n nswt}`, mixed: `{n` and `nswt}` are ASCII words) ...
    frame = pd.DataFrame([_row("ḥtp n nswt", 0.8), _row("ḥtp", 0.8)])
    result = suggest_top_readings(frame, "ḥtp {n nswt}")
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ḥtp"
    assert by["ḥtp n nswt"].confidence_score < 0.5
    # ... and a wholly Unicode (strict) query, which never reaches QueryForms' mixed
    # path: there the grouping key used to keep the braced words for exactness.
    frame = pd.DataFrame([_row("ḥtp ḏd ḥnꜥ", 0.8), _row("ḥtp", 0.8)])
    result = suggest_top_readings(frame, "ḥtp {ḏd ḥnꜥ}")
    by = _by_reading(result)
    assert result[0].candidate_transliteration == "ḥtp"
    assert "same normalized query reading" in by["ḥtp"].evidence_summary
    assert "same normalized" not in by["ḥtp ḏd ḥnꜥ"].evidence_summary
    assert by["ḥtp ḏd ḥnꜥ"].confidence_score < 0.5
    assert comparison_key("ḥtp {ḏd ḥnꜥ}") == comparison_key("ḥtp") == "ḥtp"


def test_a17_loader_falls_back_to_stored_mdc_only_without_a_reading():
    frame = pd.DataFrame(
        {
            "source": ["BBAW", "BBAW"],
            "transliteration_gold": ["{m} ={tn}", ""],
            "mdc": ["m tn", "nfr"],
        }
    )
    out = _normalize_corpus_frame(frame)
    # Wholly superfluous reading: nothing to search, the stored text stays out.
    assert out["mdc_norm"].tolist() == ["", search_fold("nfr")]


# --------------------------------------------------------------------------- #
# A53: only attested readings count as coverage, and coverage is reported
# --------------------------------------------------------------------------- #


def _trained(rows: list[tuple[str, str]]) -> ReadingModel:
    return train_reading_model(
        pd.DataFrame(
            {
                "hieroglyphs_norm": [r[0] for r in rows],
                "transliteration_gold": [r[1] for r in rows],
            }
        )
    )


def _fake_resources(models: dict[str | None, ReadingModel]):
    class _Identity:
        def segment(self, groups):
            return SimpleNamespace(groups=list(groups))

    def get(stage):
        model = models.get(stage)
        if model is None:
            return SimpleNamespace(
                segmenter=_Identity(), reading_model=ReadingModel(), own_aligned_rows=0
            )
        return SimpleNamespace(segmenter=_Identity(), reading_model=model, own_aligned_rows=1)

    return get


def test_a53_a_borrowed_reading_is_not_coverage():
    # Both stages attest the first group. The second group is unattested in both;
    # the larger model borrows a reading for it from a similar-looking group, the
    # smaller one leaves it unread. A borrowed guess must not decide the language.
    borrower = _trained([("𓀀", f"a{k}") for k in range(30)] + [("𓀀𓁐𓃀", "z")])
    confident = _trained([("𓀀", "a")] * 30)
    earlier, late = STAGES[0], STAGES[1]
    paste = "𓀀 𓀀𓁐𓃀𓃁"
    predictions, _ = borrower.predict_sequence_scored(paste.split(), use_lexicon=False)
    assert predictions[1].is_borrowed and predictions[1].predicted
    coverage: dict[str, int] = {}
    stage, scores = choose_stage_by_likelihood(
        paste,
        _fake_resources({None: borrower, earlier: borrower, late: confident}),
        coverage=coverage,
    )
    assert coverage == {earlier: 1, late: 1}
    assert scores[late] > scores[earlier]
    assert stage == late


def test_a53_coverage_is_optional_and_reported_for_every_scored_stage():
    knows = _trained([("𓀀 𓁐", f"a{k} b{k}") for k in range(30)])
    ignorant = _trained([("𓃀 𓃁", "x y")])
    earlier, late = STAGES[0], STAGES[1]
    resources = _fake_resources({None: knows, earlier: knows, late: ignorant})
    coverage: dict[str, int] = {}
    with_cov = choose_stage_by_likelihood("𓀀 𓁐", resources, coverage=coverage)
    assert with_cov == choose_stage_by_likelihood("𓀀 𓁐", resources)
    assert coverage == {earlier: 2, late: 0}
    assert set(coverage) == set(with_cov[1])


# --------------------------------------------------------------------------- #
# A21: the UI says the bar is each reading's own strength
# --------------------------------------------------------------------------- #


def test_a21_the_suggestions_panel_explains_the_bar():
    tree = ast.parse((ROOT / "app" / "ui" / "whyptology_app.py").read_text(encoding="utf-8"))
    captions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") == "caption"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "SUGGESTION_RANKING_CAPTION"
    ]
    assert len(captions) == 1
    (text,) = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "SUGGESTION_RANKING_CAPTION" for t in node.targets)
    ]
    assert "own match strength" in ast.literal_eval(text)
