"""Batch 2 (ranking), audit items 6 and 13 (2026-10-25).

Item 6: the optional reading-order field is a sign *sequence*, but it was scored and
labelled with the set-based `token_overlap_score`, so `A B` and `B A` were "the same
normalized reading order". It now uses the order-sensitive `reading_order_score`,
and "same" means equal token sequences.

Item 13: `choose_stage_by_likelihood` segmented the normalised paste, which has its
layout controls deleted, while decoding segments the raw paste with `segment_paste`
(controls read as quadrat hints). The stage is now chosen on the groups that are
decoded.

Both changes must leave every other query exactly as it was: a query without a
reading order (#6) and a paste without format controls (#13). The last test of each
section proves that over a fixed sample.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import app.retrieval.scorer as scorer
import app.services.suggestions as suggestions
from app.data.normalizer import normalize_hieroglyphs
from app.retrieval.scorer import (
    build_corpus_stats,
    combine_scores,
    reading_order_score,
    token_overlap_score,
)
from app.services.retrieval import resolve_auto_stage
from app.services.segmentation import segment_paste
from app.services.stage import choose_stage_by_likelihood
from app.services.suggestions import suggest_top_readings
from tests.test_audit_services import _random_pool, _row
from tests.test_quadrat_conditional_veto import (
    A,
    B,
    C,
    WITH_CONTROLS,
    WITHOUT_CONTROLS,
    toy,  # noqa: F401  (pytest fixture)
)
from tests.test_scoring_equivalence import corpus, tables_for
from tests.test_stage import _likelihood_corpus, _likelihood_resources_by_stage

# ---------- item 6: reading order is a sequence ----------


def test_reading_order_score_is_one_only_for_the_same_sequence():
    assert reading_order_score("A1 B2 C3", "a1 b2 c3") == 1.0
    # The set measure cannot see order; the sequence measure must.
    assert token_overlap_score("A1 B2", "B2 A1") == 1.0
    assert reading_order_score("A1 B2", "B2 A1") == pytest.approx(0.5)
    # A repeat and a surplus token both cost something.
    assert reading_order_score("A1 B2", "A1 A1 B2") == pytest.approx(2 / 3)
    assert reading_order_score("A1 B2", "A1 B2 C3") == pytest.approx(2 / 3)
    assert reading_order_score("", "A1") == 0.0
    assert reading_order_score("A1", "") == 0.0


def test_combine_scores_ranks_the_same_order_above_a_permutation():
    df = pd.DataFrame(
        [
            {"mdc_norm": "x", "hieroglyphs_norm": "", "normalized_reading_order_norm": reading}
            for reading in ["B2 A1 C3", "A1 B2 C3"]
        ]
    )
    scored = combine_scores(df, query_mdc_norm="", query_reading_order_norm="A1 B2 C3")
    by_reading = scored.set_index("normalized_reading_order_norm")
    assert by_reading.loc["A1 B2 C3", "reading_order_overlap"] == 1.0
    assert by_reading.loc["B2 A1 C3", "reading_order_overlap"] < 1.0
    assert scored["normalized_reading_order_norm"].iloc[0] == "A1 B2 C3"


def _pool_with_readings(readings: list[str]) -> pd.DataFrame:
    rows = []
    for index, reading in enumerate(readings):
        rows.append(
            {
                **_row(f"rd{index}", 0.5),
                "normalized_reading_order": reading,
                "source_text_id": f"t{index}",
            }
        )
    return pd.DataFrame(rows)


def test_a_permuted_reading_order_is_not_labelled_the_same():
    pool = _pool_with_readings(["B2 A1"])
    [suggestion] = suggest_top_readings(pool, query_mdc="rd0", query_reading_order="A1 B2")
    assert "same normalized reading order" not in suggestion.evidence_summary
    assert "similar normalized reading order" in suggestion.evidence_summary

    pool = _pool_with_readings(["A1 B2"])
    [suggestion] = suggest_top_readings(pool, query_mdc="rd0", query_reading_order="A1 B2")
    assert "same normalized reading order" in suggestion.evidence_summary


def test_a_permuted_reading_order_loses_reading_similarity():
    pool = _pool_with_readings(["B2 A1", "A1 B2"])
    debug: list[dict] = []
    suggest_top_readings(
        pool, query_mdc="", query_reading_order="A1 B2", debug_signals=debug
    )
    by_reading = {
        entry["candidate_transliteration"]: entry["signals"]["reading_similarity"]["value"]
        for entry in debug
    }
    assert by_reading["rd1"] == 1.0
    assert by_reading["rd0"] < 1.0


@pytest.mark.parametrize(
    ("query_mdc", "query_glyphs"),
    [("htp dji nswt", ""), ("nb", ""), ("", "A1 B2 C3"), ("htp dji nswt", "A1 B2"), ("", "")],
)
def test_combine_scores_without_a_reading_order_is_unchanged(
    monkeypatch, query_mdc: str, query_glyphs: str
):
    df = corpus()
    stats = build_corpus_stats(df)
    kwargs = dict(
        query_mdc_norm=query_mdc,
        query_hieroglyphs_norm=query_glyphs,
        corpus_stats=stats,
        tables=tables_for(df),
    )
    new = combine_scores(df, **kwargs)
    monkeypatch.setattr(scorer, "reading_order_score", token_overlap_score)
    old = combine_scores(df, **kwargs)
    pd.testing.assert_frame_equal(new, old)


def test_suggestions_without_a_reading_order_are_unchanged(monkeypatch):
    rng = random.Random(6)
    samples = []
    while len(samples) < 120:
        frame, kwargs = _random_pool(rng)
        kwargs.pop("query_reading_order", None)
        samples.append((frame, kwargs))

    def run():
        out = []
        for frame, kwargs in samples:
            debug: list[dict] = []
            result = suggest_top_readings(frame, debug_signals=debug, **kwargs)
            out.append((repr(result), repr(debug)))
        return out

    new = run()
    monkeypatch.setattr(suggestions, "reading_order_score", token_overlap_score)
    assert run() == new


# ---------- item 13: stage choice segments the paste the way decoding does ----------


class _RecordingModel:
    """A reading model that records the groups it is asked to read."""

    sentences_seen = 1

    def __init__(self) -> None:
        self.seen: list[list[str]] = []

    def predict_sequence_scored(self, groups, use_lexicon=False):
        self.seen.append(list(groups))
        return [], -float(len(groups))


def _recording_resources(segmenter):
    model = _RecordingModel()
    resources = SimpleNamespace(
        segmenter=segmenter, reading_model=model, own_aligned_rows=1
    )
    return (lambda stage: resources), model


def test_auto_stage_reads_the_layout_aware_segmentation(toy):  # noqa: F811
    resources_by_stage, model = _recording_resources(toy)
    resolve_auto_stage(WITH_CONTROLS, resources_by_stage)
    decoded, _ = segment_paste(WITH_CONTROLS, toy)
    assert decoded.groups == [f"{A}{B}{C}"]
    assert model.seen
    assert all(groups == decoded.groups for groups in model.seen)


def test_choose_stage_by_likelihood_takes_the_raw_paste(toy):  # noqa: F811
    resources_by_stage, model = _recording_resources(toy)
    choose_stage_by_likelihood(WITH_CONTROLS, resources_by_stage)
    assert model.seen and all(groups == [f"{A}{B}{C}"] for groups in model.seen)
    # The same signs without controls keep the old, control-free segmentation.
    model.seen.clear()
    choose_stage_by_likelihood(WITHOUT_CONTROLS, resources_by_stage)
    old = toy.segment(normalize_hieroglyphs(WITHOUT_CONTROLS).split()).groups
    assert model.seen and all(groups == old for groups in model.seen)


@pytest.mark.parametrize(
    "paste",
    [
        "𓆓𓂧 𓀀",
        "𓆓 𓂧 𓀀",
        "𓈖𓏏𓈖 𓅓",
        "𓆓𓂧𓀀 𓈖",
        "𓅓 𓆓𓂧 𓀀 𓈖𓏏𓈖",
        "  𓀀   𓆓𓂧 ",
    ],
)
def test_pastes_without_controls_choose_exactly_as_before(paste: str, monkeypatch):
    """For a control-free paste the new path must segment, score and choose exactly
    as the old one did: `segmenter.segment(paste.split())` on the normalised paste."""
    df = _likelihood_corpus()
    resources_by_stage = _likelihood_resources_by_stage(df)
    pooled = resources_by_stage(None)
    old_groups = pooled.segmenter.segment(normalize_hieroglyphs(paste).split()).groups

    recorded: list[list[str]] = []

    def recording(stage):
        resources = resources_by_stage(stage)
        model = resources.reading_model
        if stage is None:
            return resources

        class Wrapped:
            sentences_seen = model.sentences_seen

            def predict_sequence_scored(self, groups, use_lexicon=False):
                recorded.append(list(groups))
                return model.predict_sequence_scored(groups, use_lexicon=use_lexicon)

        return SimpleNamespace(
            segmenter=resources.segmenter,
            reading_model=Wrapped(),
            own_aligned_rows=resources.own_aligned_rows,
        )

    stage_raw, scores_raw = choose_stage_by_likelihood(paste, recording)
    assert recorded and all(groups == old_groups for groups in recorded)
    # The old function, literally: its two segmentation lines patched back in.
    import app.services.segmentation as segmentation_module

    def old_segment_paste(query, segmenter, use_format_hints=True):
        groups_as_pasted = normalize_hieroglyphs(query).split()
        return segmenter.segment(groups_as_pasted), groups_as_pasted

    monkeypatch.setattr(segmentation_module, "segment_paste", old_segment_paste)
    stage_norm, scores_norm = choose_stage_by_likelihood(paste, resources_by_stage)
    monkeypatch.undo()
    assert stage_raw == stage_norm
    assert scores_raw.keys() == scores_norm.keys()
    assert np.allclose(list(scores_raw.values()), list(scores_norm.values()), rtol=0, atol=0)


# ---------- review follow-up (Opus + Astra) ----------


def test_choose_stage_by_likelihood_honours_use_format_hints(toy):  # noqa: F811
    """Opus review: `--no-format-hints` decodes without hints, so the stage must be
    chosen on that same hint-free segmentation, not the hint-aware one."""
    hint_free, _ = segment_paste(WITH_CONTROLS, toy, use_format_hints=False)
    hint_aware, _ = segment_paste(WITH_CONTROLS, toy)
    assert hint_free.groups != hint_aware.groups  # the toy paste must tell them apart

    resources_by_stage, model = _recording_resources(toy)
    choose_stage_by_likelihood(WITH_CONTROLS, resources_by_stage, use_format_hints=False)
    assert model.seen and all(groups == hint_free.groups for groups in model.seen)

    model.seen.clear()
    resolve_auto_stage(WITH_CONTROLS, resources_by_stage, use_format_hints=False)
    assert model.seen and all(groups == hint_free.groups for groups in model.seen)


@pytest.mark.parametrize("no_format_hints", [False, True])
def test_expert_eval_auto_stage_follows_the_format_hints_switch(toy, no_format_hints):  # noqa: F811
    from scripts.run_expert_paste_eval import resolve_stage

    resources_by_stage, model = _recording_resources(toy)
    row = pd.Series({"query_input": WITH_CONTROLS})
    resolve_stage("auto", row, resources_by_stage, use_format_hints=not no_format_hints)
    decoded, _ = segment_paste(WITH_CONTROLS, toy, use_format_hints=not no_format_hints)
    assert model.seen and all(groups == decoded.groups for groups in model.seen)


def _tie_fallback_setup(monkeypatch, segmenter):
    """`retrieve_with_stage(stage="auto")` with the stage choice forced to a tie, and
    `retrieve_top_k` recording the sign groups it is asked to match on."""
    import app.services.retrieval as retrieval

    calls: list[str | None] = []
    monkeypatch.setattr(
        retrieval, "resolve_auto_stage", lambda *args, **kwargs: (None, False, {})
    )

    def recording_retrieve(frame, query_mdc, **kwargs):
        calls.append(kwargs.get("query_hieroglyphs_norm"))
        return pd.DataFrame()

    monkeypatch.setattr(retrieval, "retrieve_top_k", recording_retrieve)
    pooled = SimpleNamespace(frame=pd.DataFrame(), index=None, segmenter=segmenter)
    return retrieval, (lambda stage: pooled), calls


def test_auto_stage_tie_fallback_retrieves_on_the_layout_aware_groups(
    monkeypatch, toy  # noqa: F811
):
    """Astra review: on a tie the fallback retrieved on the pasted spacing (`AB C`)
    while the stage choice and decoding used the layout-aware `ABC`."""
    retrieval, resources_by_stage, calls = _tie_fallback_setup(monkeypatch, toy)
    retrieval.retrieve_with_stage(
        pd.DataFrame(), resources_by_stage, WITH_CONTROLS, stage="auto"
    )
    decoded, _ = segment_paste(WITH_CONTROLS, toy)
    assert calls == [" ".join(decoded.groups)] == [f"{A}{B}{C}"]

    # With hints off the fallback keeps the old behaviour (no regrouping).
    calls.clear()
    retrieval.retrieve_with_stage(
        pd.DataFrame(),
        resources_by_stage,
        WITH_CONTROLS,
        stage="auto",
        use_format_hints=False,
    )
    assert calls == [None]


@pytest.mark.parametrize(
    "query",
    [
        WITHOUT_CONTROLS,
        "𓆓𓂧 𓀀",
        "𓆓 𓂧 𓀀",
        "𓈖𓏏𓈖 𓅓",
        "𓅓 𓆓𓂧 𓀀 𓈖𓏏𓈖",
        "ḏd =f",
        "dd mdw",
    ],
)
def test_auto_stage_tie_fallback_is_unchanged_without_controls(
    monkeypatch, toy, query  # noqa: F811
):
    """A query with no format controls takes the fallback exactly as before: the
    caller's `query_hieroglyphs_norm` (here `None`) is passed through untouched."""
    retrieval, resources_by_stage, calls = _tie_fallback_setup(monkeypatch, toy)
    retrieval.retrieve_with_stage(pd.DataFrame(), resources_by_stage, query, stage="auto")
    assert calls == [None]
    calls.clear()
    retrieval.retrieve_with_stage(
        pd.DataFrame(), resources_by_stage, query, stage="auto", query_hieroglyphs_norm="X"
    )
    assert calls == ["X"]
