"""Tests for language-stage awareness (item A).

`normalize_stage`/`stage_compatible`/`compatible_frame`/`infer_stage` are pure
functions over a `language_stage` column and are tested as truth tables and frame
sizes. `build_stage_resources` is tested end to end: a sign group attested only in a
different, *known* stage must not be offered as a reading when a stage is declared,
but must be offered when it is not (today's pooled behaviour).
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.stage import (
    STAGES,
    build_stage_resources,
    compatible_frame,
    infer_stage,
    normalize_stage,
    stage_compatible,
)


# ---------- normalize_stage ----------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Earlier Egyptian", "Earlier Egyptian"),
        ("Late Egyptian", "Late Egyptian"),
        ("Demotic", "Demotic"),
        ("Unspecified (AES)", None),
        ("Unspecified (BBAW)", None),
        ("", None),
        ("   ", None),
        (None, None),
        (float("nan"), None),
        ("Middle Kingdom", None),  # unknown value, not one of STAGES
        (" Earlier Egyptian ", "Earlier Egyptian"),  # exact match only, no fold
    ],
)
def test_normalize_stage(value, expected):
    assert normalize_stage(value) == expected


def test_normalize_stage_covers_every_declared_stage():
    for stage in STAGES:
        assert normalize_stage(stage) == stage


# ---------- stage_compatible ----------


@pytest.mark.parametrize(
    "row_stage,target,expected",
    [
        # target is None: everything is compatible, regardless of the row's stage.
        ("Earlier Egyptian", None, True),
        ("Late Egyptian", None, True),
        ("Unspecified (AES)", None, True),
        ("", None, True),
        # row has no known stage: compatible with any target.
        ("Unspecified (AES)", "Earlier Egyptian", True),
        ("Unspecified (BBAW)", "Late Egyptian", True),
        ("", "Demotic", True),
        (None, "Earlier Egyptian", True),
        # row's stage matches the target.
        ("Earlier Egyptian", "Earlier Egyptian", True),
        ("Demotic", "Demotic", True),
        # row's stage is known and differs from the target.
        ("Late Egyptian", "Earlier Egyptian", False),
        ("Earlier Egyptian", "Demotic", False),
        ("Demotic", "Late Egyptian", False),
    ],
)
def test_stage_compatible_truth_table(row_stage, target, expected):
    assert stage_compatible(row_stage, target) is expected


# ---------- compatible_frame ----------


def _synthetic_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "language_stage": [
                "Earlier Egyptian",
                "Earlier Egyptian",
                "Late Egyptian",
                "Demotic",
                "Unspecified (AES)",
                "Unspecified (BBAW)",
                "",
            ],
            "row_id": list(range(7)),
        }
    )


def test_compatible_frame_target_none_returns_everything():
    df = _synthetic_frame()
    out = compatible_frame(df, None)
    assert len(out) == len(df)
    assert out is df  # no copy needed when nothing is excluded


def test_compatible_frame_sizes_per_target():
    df = _synthetic_frame()
    # 2 Earlier Egyptian + 3 unspecified/blank rows are compatible with "Earlier
    # Egyptian"; Late Egyptian and Demotic rows (known, different stages) are not.
    assert len(compatible_frame(df, "Earlier Egyptian")) == 5
    assert len(compatible_frame(df, "Late Egyptian")) == 4
    assert len(compatible_frame(df, "Demotic")) == 4


def test_compatible_frame_missing_column_is_treated_as_unspecified():
    df = pd.DataFrame({"row_id": [0, 1, 2]})
    assert len(compatible_frame(df, "Earlier Egyptian")) == 3


# ---------- infer_stage ----------


def _result_frame(stages: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"language_stage": stages})


def test_infer_stage_needs_minimum_labelled_rows():
    # Only 2 labelled rows, both the same stage: below min_labelled=3, so no guess.
    result = _result_frame(["Late Egyptian", "Late Egyptian", "Unspecified (AES)"])
    assert infer_stage(result) is None


def test_infer_stage_needs_a_decisive_majority():
    # 3 labelled rows, 2/3 = 0.667 < the default min_share=0.7.
    result = _result_frame(["Late Egyptian", "Late Egyptian", "Earlier Egyptian"])
    assert infer_stage(result) is None


def test_infer_stage_returns_the_decisive_majority_stage():
    # 4 labelled rows, 3/4 = 0.75 >= 0.7.
    result = _result_frame(
        ["Late Egyptian", "Late Egyptian", "Late Egyptian", "Earlier Egyptian"]
    )
    assert infer_stage(result) == "Late Egyptian"


def test_infer_stage_ignores_unlabelled_rows_when_counting_share():
    # Unspecified rows do not count toward min_labelled or dilute the share.
    result = _result_frame(
        ["Demotic", "Demotic", "Demotic", "Unspecified (AES)", "Unspecified (BBAW)"]
    )
    assert infer_stage(result) == "Demotic"


def test_infer_stage_empty_or_all_unlabelled_returns_none():
    assert infer_stage(pd.DataFrame({"language_stage": []})) is None
    assert infer_stage(_result_frame(["Unspecified (AES)"] * 5)) is None


def test_infer_stage_missing_column_returns_none():
    assert infer_stage(pd.DataFrame({"row_id": [0, 1, 2]})) is None


def test_infer_stage_custom_thresholds():
    result = _result_frame(["Demotic", "Demotic", "Earlier Egyptian"])
    assert infer_stage(result, min_labelled=3, min_share=0.9) is None
    assert infer_stage(result, min_labelled=3, min_share=0.6) == "Demotic"
    assert infer_stage(result, min_labelled=4, min_share=0.6) is None


# ---------- build_stage_resources: end to end ----------


def _stage_corpus() -> pd.DataFrame:
    """A sign group ('B') attested only in a Late Egyptian row.

    'A' is attested only in an Earlier Egyptian row, so the two groups are disjoint
    evidence for two different, known stages — exactly the situation item A exists
    to fix (a Late Egyptian row must not train a reading offered for a declared
    Earlier Egyptian paste).
    """
    return pd.DataFrame(
        [
            {
                "hieroglyphs_norm": "A",
                "transliteration_gold": "x",
                "language_stage": "Earlier Egyptian",
                "source_text_id": "T0",
                "source_sentence_id": "S0",
                "mdc_norm": "x",
            },
            {
                "hieroglyphs_norm": "B",
                "transliteration_gold": "y",
                "language_stage": "Late Egyptian",
                "source_text_id": "T1",
                "source_sentence_id": "S1",
                "mdc_norm": "y",
            },
        ]
    )


def test_build_stage_resources_target_none_is_pooled():
    df = _stage_corpus()
    resources = build_stage_resources(df, None)
    assert len(resources.frame) == 2
    assert "A" in resources.reading_model.sign_reading
    assert "B" in resources.reading_model.sign_reading
    assert resources.segmenter.is_known("A")
    assert resources.segmenter.is_known("B")


def test_build_stage_resources_declared_stage_excludes_other_known_stages():
    df = _stage_corpus()
    resources = build_stage_resources(df, "Earlier Egyptian")
    assert len(resources.frame) == 1
    # The Late-Egyptian-only group is not attested in this stage's resources at all:
    # not a candidate reading, and not a span the segmenter will propose.
    assert "A" in resources.reading_model.sign_reading
    assert "B" not in resources.reading_model.sign_reading
    assert resources.reading_model.candidates_for("B") == []
    assert resources.segmenter.is_known("A")
    assert not resources.segmenter.is_known("B")


def test_build_stage_resources_stage_recorded_on_the_result():
    df = _stage_corpus()
    assert build_stage_resources(df, None).stage is None
    # "Late Egyptian" (not "Demotic"): compatible_frame must not be empty here, since
    # an empty corpus subset is a real corpus impossibility (every stage has
    # unspecified rows too) and is out of scope for this fixture.
    assert build_stage_resources(df, "Late Egyptian").stage == "Late Egyptian"
