"""Tests for language-stage awareness (item A).

`normalize_stage`/`stage_compatible`/`compatible_frame`/`infer_stage` are pure
functions over a `language_stage` column and are tested as truth tables and frame
sizes. `build_stage_resources` is tested end to end: the reading model is stage-
restricted (a sign group attested only in a different, *known* stage must not be
offered as a reading when a stage is declared, but must be when it is not — today's
pooled behaviour) while the segmenter is always pooled (see its own tests below).

Item A part 3 adds `choose_stage_by_likelihood` (language identification for a
hieroglyph paste by per-sign log-likelihood from each stage's own reading model,
tested end to end the same way `build_stage_resources` is: synthetic corpora built
through the real constructors, not mocks). `derive_stage_from_period` stays — it is
still the rule the v4 benchmark's `language_stage` column is built with — but is no
longer consulted by `compatible_frame`/`infer_stage`/`stage_base_rates`: an earlier
iteration wired it in there too and reverted it, see that function's docstring.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.stage import (
    STAGES,
    build_stage_resources,
    choose_stage_by_likelihood,
    compatible_frame,
    derive_stage_from_period,
    infer_stage,
    normalize_stage,
    stage_base_rates,
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


# ---------- stage_base_rates ----------


def test_stage_base_rates_shares_of_labelled_rows():
    df = _synthetic_frame()  # 2 Earlier, 1 Late, 1 Demotic, 3 unspecified/blank
    rates = stage_base_rates(df)
    assert rates == pytest.approx(
        {"Earlier Egyptian": 0.5, "Late Egyptian": 0.25, "Demotic": 0.25}
    )


def test_stage_base_rates_empty_when_no_stage_column_or_no_labelled_rows():
    assert stage_base_rates(pd.DataFrame({"row_id": [0, 1]})) == {}
    assert stage_base_rates(_result_frame(["Unspecified (AES)"] * 3)) == {}


# ---------- infer_stage: the lift check (a stage's retrieved share vs. its base rate) ----------


def test_infer_stage_lift_check_off_by_default():
    # share-only behaviour is unchanged when base_rates is omitted (the default).
    result = _result_frame(
        ["Late Egyptian", "Late Egyptian", "Late Egyptian", "Earlier Egyptian"]
    )
    assert infer_stage(result) == "Late Egyptian"


def test_infer_stage_lift_check_blocks_a_merely_more_common_stage():
    # Late Egyptian clears min_labelled (4) and min_share (0.75 >= 0.7), but its
    # base rate (0.6, e.g. Ramses makes it far more common among labelled rows)
    # means the retrieved share is barely above the prior: lift = 0.75/0.6 = 1.25,
    # below the default min_lift=1.5, so the stage is not inferred.
    result = _result_frame(
        ["Late Egyptian", "Late Egyptian", "Late Egyptian", "Earlier Egyptian"]
    )
    base_rates = {"Late Egyptian": 0.6, "Earlier Egyptian": 0.4}
    assert infer_stage(result, base_rates=base_rates) is None


def test_infer_stage_lift_check_passes_a_genuinely_decisive_stage():
    # Same retrieved share (0.75) but a low base rate (0.2): lift = 0.75/0.2 = 3.75,
    # comfortably above min_lift, so the stage is inferred.
    result = _result_frame(
        ["Late Egyptian", "Late Egyptian", "Late Egyptian", "Earlier Egyptian"]
    )
    base_rates = {"Late Egyptian": 0.2, "Earlier Egyptian": 0.8}
    assert infer_stage(result, base_rates=base_rates) == "Late Egyptian"


def test_infer_stage_lift_check_custom_min_lift():
    result = _result_frame(
        ["Late Egyptian", "Late Egyptian", "Late Egyptian", "Earlier Egyptian"]
    )
    base_rates = {"Late Egyptian": 0.6, "Earlier Egyptian": 0.4}
    # lift is exactly 1.25 here; a caller asking for less than that clears it.
    assert infer_stage(result, base_rates=base_rates, min_lift=1.2) == "Late Egyptian"
    assert infer_stage(result, base_rates=base_rates, min_lift=1.3) is None


def test_infer_stage_lift_check_fails_closed_on_an_unknown_base_rate():
    # The winning stage has no entry in base_rates at all (e.g. it never appears
    # among the pooled frame's labelled rows) -- cannot compute a lift, so decline.
    result = _result_frame(
        ["Demotic", "Demotic", "Demotic", "Earlier Egyptian"]
    )
    assert infer_stage(result, base_rates={"Earlier Egyptian": 0.5}) is None


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
    # The reading model is stage-restricted: the Late-Egyptian-only group is not
    # a candidate reading here at all.
    assert "A" in resources.reading_model.sign_reading
    assert "B" not in resources.reading_model.sign_reading
    assert resources.reading_model.candidates_for("B") == []
    # The segmenter is NOT stage-restricted -- it is always built from the pooled
    # frame (segment pooled, read by stage), so it knows "B" as a real sign group
    # even though this stage would never offer a reading for it.
    assert resources.segmenter.is_known("A")
    assert resources.segmenter.is_known("B")


def test_build_stage_resources_stage_recorded_on_the_result():
    df = _stage_corpus()
    assert build_stage_resources(df, None).stage is None
    # "Late Egyptian" (not "Demotic"): compatible_frame must not be empty here, since
    # an empty corpus subset is a real corpus impossibility (every stage has
    # unspecified rows too) and is out of scope for this fixture.
    assert build_stage_resources(df, "Late Egyptian").stage == "Late Egyptian"


# ---------- build_stage_resources: the segmenter is always pooled ----------


def test_build_stage_resources_lexicon_weight_factor_is_always_one():
    # No subsetting ever touches the segmenter's own group counts any more (it
    # is always built from the pooled frame), so there is no shrinking mass to
    # scale lexicon_weight against -- the factor is always exactly 1.0, and the
    # weights are never rewritten away from the caller's own.
    df = _stage_corpus()
    for target in (None, "Earlier Egyptian", "Late Egyptian"):
        resources = build_stage_resources(df, target)
        assert resources.lexicon_weight_factor == 1.0
        assert resources.segmenter.weights.lexicon_weight == pytest.approx(0.2)


def test_build_stage_resources_segmenter_is_identical_in_behaviour_across_stages():
    # "Segment pooled, read by stage": every stage's segmenter is built from the
    # same pooled reading model, so segmenting the same glyph stream through any
    # stage's resources gives the same groups.
    df = _stage_corpus()
    stream = ["A", "B"]
    none_groups = build_stage_resources(df, None).segmenter.segment(stream).groups
    ee_groups = build_stage_resources(df, "Earlier Egyptian").segmenter.segment(stream).groups
    le_groups = build_stage_resources(df, "Late Egyptian").segmenter.segment(stream).groups
    assert none_groups == ee_groups == le_groups == ["A", "B"]


def test_build_stage_resources_pooled_reading_model_reused_when_given():
    # A caller that already built (and cached) the target=None StageResources can
    # pass its reading_model in, so a concrete-stage build does not re-fit the
    # whole pooled corpus a second time just to build a segmenter.
    df = _stage_corpus()
    pooled = build_stage_resources(df, None)
    resources = build_stage_resources(
        df, "Earlier Egyptian", pooled_reading_model=pooled.reading_model
    )
    assert resources.segmenter.is_known("A")
    assert resources.segmenter.is_known("B")
    # And it is not silently ignored: without it, the fallback (fit from df
    # itself) gives an equal-behaving but distinct segmenter -- the test above
    # already covers behavioural equivalence, this just confirms the shortcut
    # doesn't change what "A"/"B" resolve to.
    without = build_stage_resources(df, "Earlier Egyptian")
    assert without.segmenter.is_known("A") and without.segmenter.is_known("B")


# ---------- derive_stage_from_period ----------


@pytest.mark.parametrize(
    "source_text_id,period,expected",
    [
        # TLA prefix wins outright, even with a period that would say otherwise.
        ("TLA_EARLIER_042", "Ptolemaic", "Earlier Egyptian"),
        ("TLA_LATE_007", "", "Late Egyptian"),
        ("TLA_DEMOTIC_A1B2", "unknown", "Demotic"),
        # No TLA prefix: period keywords, single-stage agreement resolves.
        ("AES_1", "Old Kingdom", "Earlier Egyptian"),
        ("AES_2", "Middle Kingdom / Second Intermediate Period", "Earlier Egyptian"),
        ("BBAW_1", "New Kingdom", "Late Egyptian"),
        ("BBAW_2", "Third Intermediate Period", "Late Egyptian"),
        ("AES_3", "Ptolemaic", "Demotic"),
        ("AES_4", "Roman", "Demotic"),
        # Keywords disagree (spans two stages) -> None, not a guess.
        ("AES_5", "Third Intermediate Period to Roman", None),
        # No keyword match, or nothing to go on -> None.
        ("AES_6", "unknown", None),
        ("AES_7", "", None),
        ("AES_8", None, None),
        (None, None, None),
    ],
)
def test_derive_stage_from_period(source_text_id, period, expected):
    assert derive_stage_from_period(source_text_id, period) == expected


def test_derive_stage_from_period_not_consulted_by_compatible_frame():
    # A regression guard for the revert: an AES row with no language_stage but a
    # datable period must stay compatible with every stage (the old, pooled-
    # unless-declared-otherwise behaviour), not be excluded by a period
    # derivation -- compatible_frame/infer_stage/stage_base_rates only ever look
    # at the raw language_stage column now.
    df = pd.DataFrame(
        {
            "language_stage": ["Earlier Egyptian", ""],
            "source_text_id": ["TLA_EARLIER_1", "AES_1"],
            "period": ["", "New Kingdom"],  # would derive Late Egyptian if used
        }
    )
    assert len(compatible_frame(df, "Earlier Egyptian")) == 2
    assert len(compatible_frame(df, "Late Egyptian")) == 1
    rates = stage_base_rates(df)
    assert rates == pytest.approx({"Earlier Egyptian": 1.0})


# ---------- choose_stage_by_likelihood ----------


def _likelihood_corpus() -> pd.DataFrame:
    """Two stages with disjoint, repeated sign groups, plus a text-only Demotic
    stage with no hieroglyphs at all (zero aligned rows -> a degenerate reading
    model, exactly like this corpus's real Demotic rows)."""
    rows = []
    for i in range(4):
        rows.append(
            {
                "hieroglyphs_norm": "𓆓𓂧 𓀀",
                "transliteration_gold": "ḏd =f",
                "language_stage": "Earlier Egyptian",
                "source_text_id": f"EE_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "dd =f",
            }
        )
    for i in range(4):
        rows.append(
            {
                "hieroglyphs_norm": "𓈖𓏏𓈖 𓅓",
                "transliteration_gold": "n m",
                "language_stage": "Late Egyptian",
                "source_text_id": f"LE_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "n m",
            }
        )
    for i in range(2):
        rows.append(
            {
                "hieroglyphs_norm": "",
                "transliteration_gold": "ḏd",
                "language_stage": "Demotic",
                "source_text_id": f"D_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "dd",
            }
        )
    return pd.DataFrame(rows)


def _likelihood_resources_by_stage(df: pd.DataFrame):
    cache: dict[str | None, object] = {}

    def get(stage: str | None):
        if stage not in cache:
            cache[stage] = build_stage_resources(df, stage, use_lexicon=False)
        return cache[stage]

    return get


def test_choose_stage_by_likelihood_prefers_the_stage_that_saw_the_paste():
    df = _likelihood_corpus()
    resources_by_stage = _likelihood_resources_by_stage(df)
    # Exactly the Earlier Egyptian stage's own attested groups.
    stage, scores = choose_stage_by_likelihood("𓆓𓂧 𓀀", resources_by_stage)
    assert stage == "Earlier Egyptian"
    assert scores["Earlier Egyptian"] > scores["Late Egyptian"]


def test_choose_stage_by_likelihood_is_not_swayed_by_a_bigger_unrelated_corpus():
    # The regression this function exists to fix: a stage with a much larger
    # corpus must not win purely on size when it has never seen the paste's own
    # groups. Late Egyptian here is 10x Earlier Egyptian's row count, but every
    # one of those extra rows is a group unrelated to the paste -- reading-model
    # terms are each a probability conditioned on ONE sign group's own local
    # count (see ReadingModel._emission), not on the corpus total, so a bigger
    # corpus elsewhere confers no advantage.
    rows = []
    for i in range(3):
        rows.append(
            {
                "hieroglyphs_norm": "𓆓𓂧 𓀀",
                "transliteration_gold": "ḏd =f",
                "language_stage": "Earlier Egyptian",
                "source_text_id": f"EE_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "dd =f",
            }
        )
    for i in range(30):  # 10x the rows, none of them this paste's groups
        rows.append(
            {
                "hieroglyphs_norm": "𓈖𓏏𓈖 𓅓",
                "transliteration_gold": "n m",
                "language_stage": "Late Egyptian",
                "source_text_id": f"LE_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "n m",
            }
        )
    # One unlabelled row so Demotic's compatible_frame is not literally empty
    # (see _likelihood_corpus's docstring / the tie test above for why).
    rows.append(
        {
            "hieroglyphs_norm": "𓁐",
            "transliteration_gold": "z",
            "language_stage": "",
            "source_text_id": "UNSPEC_0",
            "source_sentence_id": "S0",
            "mdc_norm": "z",
        }
    )
    df = pd.DataFrame(rows)
    resources_by_stage = _likelihood_resources_by_stage(df)
    stage, scores = choose_stage_by_likelihood("𓆓𓂧 𓀀", resources_by_stage)
    assert stage == "Earlier Egyptian"
    assert scores["Earlier Egyptian"] > scores["Late Egyptian"]


def test_choose_stage_by_likelihood_excludes_a_stage_with_zero_aligned_rows():
    df = _likelihood_corpus()
    resources_by_stage = _likelihood_resources_by_stage(df)
    stage, scores = choose_stage_by_likelihood("𓆓𓂧 𓀀", resources_by_stage)
    # Demotic here is text-only (no hieroglyphs at all), like the real corpus's
    # Demotic rows -- its reading model is degenerate and must not be scored.
    assert "Demotic" not in scores
    assert stage != "Demotic"


def test_choose_stage_by_likelihood_ties_fall_back_to_none():
    # Two stages built from byte-identical row content (just different labels)
    # score identically -- a tie must not be trusted to pick one over the other.
    rows = []
    for label in ("Earlier Egyptian", "Late Egyptian"):
        for i in range(3):
            rows.append(
                {
                    "hieroglyphs_norm": "𓆓𓂧 𓀀",
                    "transliteration_gold": "ḏd =f",
                    "language_stage": label,
                    "source_text_id": f"{label}_{i}",
                    "source_sentence_id": "S0",
                    "mdc_norm": "dd =f",
                }
            )
    # One unlabelled row, compatible with (and so identically added to) every
    # stage's frame -- keeps Demotic's frame non-empty (an entirely empty
    # corpus subset is a real-world impossibility here; every stage always has
    # unspecified rows too, see the module docstring) without breaking the
    # Earlier/Late symmetry this test relies on.
    rows.append(
        {
            "hieroglyphs_norm": "𓁐",
            "transliteration_gold": "z",
            "language_stage": "",
            "source_text_id": "UNSPEC_0",
            "source_sentence_id": "S0",
            "mdc_norm": "z",
        }
    )
    df = pd.DataFrame(rows)
    resources_by_stage = _likelihood_resources_by_stage(df)
    stage, scores = choose_stage_by_likelihood("𓆓𓂧 𓀀", resources_by_stage)
    assert scores["Earlier Egyptian"] == pytest.approx(scores["Late Egyptian"])
    assert stage is None


def test_choose_stage_by_likelihood_empty_paste_returns_none_and_no_scores():
    df = _likelihood_corpus()
    resources_by_stage = _likelihood_resources_by_stage(df)
    assert choose_stage_by_likelihood("", resources_by_stage) == (None, {})
