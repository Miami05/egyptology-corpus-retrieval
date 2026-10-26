"""Batch 2 (evidence-ui): Astra's 2026-10-25 items #1, #3, #4, #5, #8, #12.

One section per item. Only the #1 end-to-end check drives the real app (AppTest on
the full corpus); everything else calls the extracted helpers directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import app.ui.whyptology_app as app_module
from app.services.reading_model import ReadingPrediction, train_reading_model
from app.services.signs import build_sign_index
from app.ui.review_common import HISTORY_COLUMNS, annotation_history_to_df

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(PROJECT_ROOT / "app" / "ui" / "whyptology_app.py")


def corpus(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"hieroglyphs_norm": glyphs, "transliteration_gold": reading}
            for glyphs, reading in rows
        ]
    )


def prediction(**fields) -> ReadingPrediction:
    defaults = dict(
        sign="A",
        predicted="x",
        candidates=[],
        attested_count=0,
        is_ambiguous=False,
        was_seen=True,
    )
    defaults.update(fields)
    return ReadingPrediction(**defaults)


# ---------- #3: the Analysis tab places annotations only on aligned rows ----------


def test_misaligned_lemma_and_pos_are_withheld_not_shifted():
    # The shape of AES_C74508573C9D: an empty annotation slot joined as "" and lost
    # to .split(), so the POS list is one short and every later tag slides left.
    row = pd.Series(
        {
            "transliteration_gold": "ḏd =f +nfr sꞽ",
            "lemma_sequence": "185810 10050 81970",
            "upos": "VERB PRON unknown",
            "glossing": "",
            "hieroglyphs": "",
        }
    )
    table = app_module.token_analysis(row)
    assert list(table["Reading"]) == ["ḏd", "=f", "+nfr", "sꞽ"]
    assert set(table["Part of speech"]) == {""}
    assert set(table["Lemma"]) == {""}
    assert table.attrs["withheld"] == ["Lemma", "Part of speech"]


def test_aligned_row_keeps_every_column():
    row = pd.Series(
        {
            "transliteration_gold": "ḥtp wsꞽr",
            "lemma_sequence": "111230|ḥtp 49460|wsꞽr",
            "upos": "NOUN PROPN",
            "glossing": "offering Osiris",
            "hieroglyphs": "𓊵𓏏𓊪 𓊨𓁹",
        }
    )
    table = app_module.token_analysis(row)
    assert list(table["Part of speech"]) == ["NOUN", "PROPN"]
    assert list(table["Lemma"]) == ["ḥtp", "wsꞽr"]
    assert list(table["Sign"]) == ["𓊵𓏏𓊪", "𓊨𓁹"]
    assert list(table["Glossing"]) == ["offering", "Osiris"]
    assert table.attrs["withheld"] == []


def test_signs_and_glossing_are_judged_on_their_own_counts():
    row = pd.Series(
        {
            "transliteration_gold": "ḥtp wsꞽr",
            "lemma_sequence": "",
            "upos": "",
            "glossing": "offering",
            "hieroglyphs": "𓊵𓏏𓊪𓊨𓁹",
        }
    )
    table = app_module.token_analysis(row)
    assert set(table["Sign"]) == {""}
    assert set(table["Glossing"]) == {""}
    # No lemma/POS at all is "no annotation", not "withheld".
    assert table.attrs["withheld"] == ["Sign", "Glossing"]


# ---------- #5: the chosen reading's own count, beside the group's ----------


def _context_model():
    # tests/test_reading_model.py's fixture: A is 'x' three times, 'y' twice, and
    # 'y' always follows P — so after P context chooses the minority reading.
    return train_reading_model(
        corpus(
            [
                ("Q A", "q x"),
                ("Q A", "q x"),
                ("Q A", "q x"),
                ("P A", "p y"),
                ("P A", "p y"),
            ]
        )
    )


def test_prediction_carries_the_chosen_readings_own_count():
    predictions = _context_model().predict_sequence(["P", "A"])
    chosen = predictions[1]
    assert chosen.predicted == "y"
    assert chosen.attested_count == 5
    assert chosen.reading_count == 2


def test_evidence_cell_names_both_counts():
    model = _context_model()
    chosen = model.predict_sequence(["P", "A"])[1]
    assert (
        app_module.prediction_evidence(chosen, model)
        == "this reading 2×; this group 5×"
    )


def test_lexicon_evidence_names_both_counts():
    p = prediction(
        was_seen=False, lexicon_count=7, reading_count=3, lexicon_source="AES"
    )
    assert app_module.prediction_evidence(p, None).startswith(
        "lexicon: this reading 3×; this group 7× (AES)"
    )


# ---------- #8: an unreadable group keeps its place in the reading ----------


def test_unreadable_group_stays_visible_in_the_assembled_reading():
    predictions = [
        prediction(predicted="ḏd"),
        prediction(predicted="", was_seen=False),
        prediction(predicted="=f"),
    ]
    assert app_module.assembled_reading(predictions) == "ḏd ∅ =f"


# ---------- #12: the history shows every editable field ----------


def test_history_keeps_earlier_uncertainty_and_grammar_notes():
    def revision(id_, uncertainty, grammar):
        return SimpleNamespace(
            id=id_,
            status="edited",
            transliteration="ḏd =f",
            uncertainty_note=uncertainty,
            grammar_note=grammar,
            display_sequence="𓆓𓂧 𓆑",
            normalized_reading_order="ḏd =f",
            alt_transliterations="ḏd =f | ḏd.f",
            variant_writing_note="",
            morphology_note="",
            syntax_note="",
            aesthetic_arrangement_flag=False,
            created_at=datetime(2026, 10, 25, tzinfo=UTC),
        )

    history = annotation_history_to_df(
        [revision(2, "", ""), revision(1, "final sign damaged", "sḏm=f form")]
    )
    for column in (
        "uncertainty_note",
        "grammar_note",
        "display_sequence",
        "alt_transliterations",
    ):
        assert column in HISTORY_COLUMNS
        assert column in history.columns
    assert list(history["uncertainty_note"]) == ["", "final sign damaged"]
    assert list(history["grammar_note"]) == ["", "sḏm=f form"]
    assert list(history.columns) == HISTORY_COLUMNS
    assert list(annotation_history_to_df([]).columns) == HISTORY_COLUMNS


# ---------- #4: the explorer no longer calls ḫ/ẖ an editorial variant ----------


def test_search_fold_grouping_is_kept_but_not_called_editorial():
    from app.services.signs import SEARCH_FOLD_LABEL

    # Grouping unchanged (label-only fix): stḫ and stẖ still merge in the search
    # form, which is exactly why "editorial variants" was the wrong name.
    index = build_sign_index(
        corpus([("𓁣𓅆", "stḫ"), ("𓁣𓅆", "stẖ"), ("𓁣𓅆", "Stẖ")])
    )
    entry = index["𓁣𓅆"]
    assert entry.literal_count == 3
    assert entry.distinct_count == 1

    source = Path(APP_PATH).read_text(encoding="utf-8")
    assert "drops editorial variants" not in source
    assert "distinct after collapsing editorial marks" not in source
    assert "editorial" not in SEARCH_FOLD_LABEL
    assert "{SEARCH_FOLD_LABEL}" in source


# ---------- #1: an edited grouping reaches retrieval and suggestions ----------


def test_grouping_edit_may_only_move_boundaries():
    groups = ["𓆓𓂧𓆑"]
    assert app_module.validate_edited_grouping("𓆓𓂧 𓆑", groups) == (
        ["𓆓𓂧", "𓆑"],
        "",
    )
    added, why = app_module.validate_edited_grouping("𓆓𓂧 𓆑𓆑", groups)
    assert added is None and "Only the spaces" in why
    dropped, why = app_module.validate_edited_grouping("𓆓 𓆑", groups)
    assert dropped is None and "Only the spaces" in why
    reordered, _ = app_module.validate_edited_grouping("𓆑 𓆓𓂧", groups)
    assert reordered is None
    empty, why = app_module.validate_edited_grouping("   ", groups)
    assert empty is None and why


def _grouping_input(app):
    return [t for t in app.text_input if t.label.startswith("Sign groups")][0]


def test_applied_grouping_reruns_the_search_with_those_groups(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("REVIEWER_KEY", raising=False)
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.query_params["stage"] = "all"
    app.run()
    app.text_area[0].set_value("𓆓𓂧𓆑").run()
    reading_order_box = lambda: [  # noqa: E731
        t for t in app.text_input if t.label == "Normalized reading order"
    ][0]
    reading_order_box().set_value("ḏd =f").run()
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run()
    assert not app.exception, app.exception
    assert app.session_state["whyptology_last_reading_order"] == "ḏd =f"
    proposal = list(app.session_state["whyptology_segments"])
    edited = ["𓆓𓂧", "𓆑"] if proposal != ["𓆓𓂧", "𓆑"] else ["𓆓𓂧𓆑"]

    # An edit that drops a sign is refused: warning, nothing to apply.
    _grouping_input(app).set_value("𓆓𓂧").run()
    assert not [b for b in app.button if b.label == "Apply grouping"]
    assert any("Only the spaces" in w.value for w in app.warning)

    # The reading-order box edited after the search must not leak into the rerun
    # (Opus nit): the applied grouping re-searches the inputs it was edited for.
    reading_order_box().set_value("something else").run()
    _grouping_input(app).set_value(" ".join(edited)).run()
    [b for b in app.button if b.label == "Apply grouping"][0].click().run()
    assert not app.exception, app.exception
    # The search ran again with the expert's groups, not the lattice's: the stored
    # grouping is what retrieval and the suggestions were given.
    assert list(app.session_state["whyptology_segments"]) == edited
    assert app.session_state["whyptology_last_parse"].hieroglyphs_norm == " ".join(edited)
    assert app.session_state["whyptology_last_query"] == "𓆓𓂧𓆑"
    assert app.session_state["whyptology_last_reading_order"] == "ḏd =f"
    assert _grouping_input(app).value == " ".join(edited)
    assert not [b for b in app.button if b.label == "Apply grouping"]


# ---------- KRI self-test: provenance first, the tie appended ----------
#
# A first draft of the tie note returned before the fallback/lexicon branches, so a
# borrowed or lexicon reading whose candidates happened to tie was described only as
# a tie — the reader lost the one thing they most need to know, which is where the
# reading came from. Each provenance is checked with a tie on it.

TIE = ["x", "y"]


def test_tie_is_appended_to_a_corpus_reading_not_substituted_for_it():
    p = prediction(
        predicted="x", reading_count=1, attested_count=2, tied_singleton_readings=TIE
    )
    evidence = app_module.prediction_evidence(p, None)
    assert evidence.startswith("this reading 1×; this group 2×")
    assert "tied in attestation counts with y" in evidence


def test_tie_is_appended_to_a_borrowed_reading_which_still_says_it_is_borrowed():
    p = prediction(
        predicted="x",
        was_seen=False,
        fallback_from="AB",
        fallback_similarity=0.6,
        tied_singleton_readings=TIE,
    )
    evidence = app_module.prediction_evidence(p, None)
    assert evidence.startswith("inferred from")
    assert "60% glyph match" in evidence
    assert "tied in attestation counts with y" in evidence


def test_tie_is_appended_to_a_lexicon_reading_which_still_says_it_is_lexicon():
    p = prediction(
        predicted="x",
        was_seen=False,
        lexicon_count=2,
        reading_count=1,
        lexicon_source="AES",
        tied_singleton_readings=TIE,
    )
    evidence = app_module.prediction_evidence(p, None)
    assert evidence.startswith("lexicon: this reading 1×; this group 2× (AES)")
    assert "tied in attestation counts with y" in evidence


def test_tie_wording_does_not_call_the_choice_arbitrary():
    # The attestation counts rank none of them, but the context scores did choose.
    p = prediction(
        predicted="x", reading_count=1, attested_count=2, tied_singleton_readings=TIE
    )
    evidence = app_module.prediction_evidence(p, None)
    assert "arbitrary" not in evidence
    assert "the context scores chose between them" in evidence


def test_pooled_evidence_names_both_the_pooled_and_the_stage_count():
    p = prediction(
        predicted="x",
        reading_count=34,
        attested_count=37,
        used_pooled_evidence=True,
        stage_attested_count=3,
    )
    assert app_module.prediction_evidence(p, None) == (
        "all stages: this reading 34×; this group 37× — the chosen stage attests "
        "it only 3×"
    )
