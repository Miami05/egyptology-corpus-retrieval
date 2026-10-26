"""Unit tests for the paired on/off harness (scripts/run_kri_fixes_eval.py).

A measurement harness that is wrong is worse than no harness, because its output
looks like evidence. Everything here is a synthetic fixture built through the real
constructors: the point is that each feature's switch really does switch that feature
and nothing else, that no test row reaches a model, and that the aggregates count what
they say they count.
"""

from __future__ import annotations

import pandas as pd
import pytest

import app.services.segmentation as segmentation_module
from app.data.normalizer import cartouche_spans
from scripts.run_kri_fixes_eval import (
    ARMS,
    Arm,
    boundaries,
    build_resources,
    calibration_rows,
    cartouche_constraint,
    confidence_of,
    evaluate,
    legacy_confidence,
    ratio,
    sign_test_p,
    summarise,
)

# Synthetic fixtures still have to be made of real hieroglyphs: `segment_paste`
# normalises its input, and `normalize_hieroglyphs` deletes anything that is not a
# sign — a paste of ASCII letters reaches the stage router as an empty string and is
# never routed at all. These are ordinary public-corpus signs standing in for words.
SIGN_A = "𓂋"
SIGN_B = "𓆑"
SIGN_E = "𓄿"
SIGN_H = "𓆓"
SIGN_Z = "𓃀"

CARTOUCHE_OPEN = "\U00013379"
CARTOUCHE_CLOSE = "\U0001337A"
NAME = CARTOUCHE_OPEN + "𓃹𓈖" + CARTOUCHE_CLOSE


def rows(specs: list[tuple[str, str, str]]) -> pd.DataFrame:
    """(signs, readings, stage) triples -> a corpus frame the real loaders accept."""
    return pd.DataFrame(
        [
            {
                "hieroglyphs_norm": signs,
                "transliteration_gold": readings,
                "language_stage": stage,
                "source": "TEST",
                "source_text_id": f"T{i}",
                "source_sentence_id": f"S{i}",
                "mdc_norm": readings,
            }
            for i, (signs, readings, stage) in enumerate(specs)
        ]
    )


# ---------- the switches ----------


def test_cartouche_constraint_context_manager_restores_the_real_function():
    original = segmentation_module.cartouche_spans
    with cartouche_constraint(False):
        assert segmentation_module.cartouche_spans(NAME) == []
    assert segmentation_module.cartouche_spans is original
    assert segmentation_module.cartouche_spans(NAME) == cartouche_spans(NAME)


def test_cartouche_constraint_enabled_changes_nothing():
    original = segmentation_module.cartouche_spans
    with cartouche_constraint(True):
        assert segmentation_module.cartouche_spans is original
    assert segmentation_module.cartouche_spans is original


def test_cartouche_constraint_restores_the_function_after_an_exception():
    original = segmentation_module.cartouche_spans
    with pytest.raises(ValueError):
        with cartouche_constraint(False):
            raise ValueError("boom")
    assert segmentation_module.cartouche_spans is original


def test_confidence_switch_is_the_discount_and_only_the_discount():
    from app.services.reading_model import train_reading_model

    model = train_reading_model(rows([(SIGN_A, "x", ""), (SIGN_A, "y", ""), (SIGN_A, "z", "")]))
    prediction = model.predict_sequence([SIGN_A])[0]
    assert prediction.is_singleton_tie is True
    assert confidence_of(prediction, discount=False) == pytest.approx(1 / 3)
    assert confidence_of(prediction, discount=True) == pytest.approx(1 / 9)


def test_confidence_switch_agrees_where_there_is_no_tie():
    from app.services.reading_model import train_reading_model

    model = train_reading_model(rows([(SIGN_A, "x", ""), (SIGN_A, "x", ""), (SIGN_A, "y", "")]))
    prediction = model.predict_sequence([SIGN_A])[0]
    assert confidence_of(prediction, discount=False) == confidence_of(
        prediction, discount=True
    )


# ---------- resources are built from the training partition only ----------


def test_resources_never_see_a_row_outside_the_training_frame():
    train = rows([(SIGN_A, "x", "Earlier Egyptian")] * 3)
    resources = build_resources(train, lexicon_on=False)
    assert SIGN_A in resources.pooled.sign_reading
    # A group that exists only in the held-out part of the corpus must be unknown to
    # every model the harness built, pooled one included.
    assert SIGN_Z not in resources.pooled.sign_reading
    for stage_model in resources.by_stage.values():
        assert SIGN_Z not in stage_model.sign_reading


def test_each_stage_model_carries_the_pooled_model_from_the_same_training_frame():
    train = rows(
        [(SIGN_A, "x", "Earlier Egyptian")] * 2 + [(SIGN_B, "y", "Late Egyptian")] * 2
    )
    resources = build_resources(train, lexicon_on=False)
    earlier = resources.by_stage["Earlier Egyptian"]
    assert earlier.pooled is resources.pooled
    # Read by stage: the Late Egyptian group is not a candidate reading here...
    assert SIGN_B not in earlier.sign_reading
    # ...but the pooled model it may fall back to does know it.
    assert SIGN_B in resources.pooled.sign_reading


def test_the_segmenter_is_built_from_the_pooled_model_for_every_stage():
    train = rows(
        [(SIGN_A, "x", "Earlier Egyptian")] * 2 + [(SIGN_B, "y", "Late Egyptian")] * 2
    )
    resources = build_resources(train, lexicon_on=False)
    assert resources.segmenter.is_known(SIGN_A)
    assert resources.segmenter.is_known(SIGN_B)
    for stage in resources.by_stage:
        assert resources.stage_resources(stage).segmenter is resources.segmenter


def test_stage_resources_report_their_own_aligned_row_count():
    train = rows(
        [(SIGN_A, "x", "Earlier Egyptian")] * 3 + [(SIGN_B, "y", "Late Egyptian")] * 1
    )
    resources = build_resources(train, lexicon_on=False)
    assert resources.stage_resources("Earlier Egyptian").own_aligned_rows == 3
    assert resources.stage_resources("Late Egyptian").own_aligned_rows == 1
    assert resources.stage_resources("Demotic").own_aligned_rows == 0
    assert resources.stage_resources(None).own_aligned_rows is None


# ---------- boundaries ----------


def test_boundaries_marks_the_end_of_every_group_but_the_last():
    assert boundaries(["AB", "C", "DE"]) == {2, 3}
    assert boundaries(["ABCDE"]) == set()
    assert boundaries([]) == set()


# ---------- evaluate ----------


def _firing_corpus() -> pd.DataFrame:
    """'H' read 'haw' 34x in Late Egyptian rows, once each three ways in Earlier ones.

    The traced shape: restricted to Earlier Egyptian the group keeps three readings
    attested once apiece, so the pooled fallback fires there and nowhere else. SIGN_E is
    an Earlier-Egyptian-only group, present so a line containing it routes to Earlier
    Egyptian on attested coverage — without it the router sends 'H' to the stage that
    actually attests it and the fallback can never be exercised.
    """
    return rows(
        [(SIGN_H, "haw", "Late Egyptian")] * 34
        + [
            (f"{SIGN_E} {SIGN_H}", "e hy", "Earlier Egyptian"),
            (f"{SIGN_E} {SIGN_H}", "e wsht", "Earlier Egyptian"),
            (f"{SIGN_E} {SIGN_H}", "e thr", "Earlier Egyptian"),
        ]
    )


def test_evaluate_marks_firing_positions_only_in_the_pooled_arms():
    train = _firing_corpus()
    resources = build_resources(train, lexicon_on=False)
    test = rows([(f"{SIGN_E} {SIGN_H}", "e haw", "Earlier Egyptian")])
    arms = (
        Arm("all_off", pooled=False, discount=False, cartouche=False),
        Arm("pooled_only", pooled=True, discount=False, cartouche=False),
    )
    positions, lines = evaluate(test, resources, arms)
    assert {row["stage"] for row in lines} == {"Earlier Egyptian"}
    by_arm = {(row["arm"], row["position"]): row for row in positions}
    # Whether THIS arm fired is per arm...
    assert by_arm[("all_off", 1)]["used_pooled_evidence"] == 0
    assert by_arm[("pooled_only", 1)]["used_pooled_evidence"] == 1
    assert by_arm[("pooled_only", 1)]["stage_attested_count"] == 3
    assert by_arm[("pooled_only", 1)]["attested_count"] == 37
    # ...but the cohort is per POSITION and the same in every arm (review fix,
    # 2026-10-26): all_off is scored on the very positions the fallback fires on.
    assert by_arm[("all_off", 1)]["class"] == "firing"
    assert by_arm[("pooled_only", 1)]["class"] == "firing"
    # Position 0 never fires, but it sits beside one that does, in both arms.
    assert by_arm[("pooled_only", 0)]["class"] == "neighbour"
    assert by_arm[("all_off", 0)]["class"] == "neighbour"
    assert {row["arm"] for row in lines} == {"all_off", "pooled_only"}


def test_rule_b_can_fail_once_cohorts_are_shared():
    """The pre-fix harness gave all_off an empty firing cohort, so acc_firing(all_off)
    was 0/0 -> 0.0 and `on >= off` could never fail. On shared cohorts it is a real
    paired comparison: here all_off reads the gold, so the pooled arm is worse."""
    train = _firing_corpus()
    resources = build_resources(train, lexicon_on=False)
    # The gold is one of the stage's own singleton readings, which all_off picks by
    # tie-break and the pooled fallback overrides with 'haw'.
    off_reading = resources.by_stage["Earlier Egyptian"].predict_sequence(
        [SIGN_E, SIGN_H], use_pooled_fallback=False
    )[1].predicted
    assert off_reading != "haw"
    test = rows([(f"{SIGN_E} {SIGN_H}", f"e {off_reading}", "Earlier Egyptian")])
    arms = (
        Arm("all_off", pooled=False, discount=False, cartouche=False),
        Arm("pooled_only", pooled=True, discount=False, cartouche=False),
    )
    positions, lines = evaluate(test, resources, arms)
    summary, _ = summarise(pd.DataFrame(positions), pd.DataFrame(lines))
    by_arm = {r["arm"]: r for r in summary if r["scope"] == "all"}
    assert by_arm["all_off"]["firing_positions"] == 1
    assert by_arm["all_off"]["acc_firing"] == 1.0
    assert by_arm["pooled_only"]["acc_firing"] == 0.0
    assert by_arm["pooled_only"]["firing_worse"] == 1
    assert by_arm["pooled_only"]["firing_better"] == 0


def test_evaluate_emits_one_position_row_per_group_per_arm():
    train = rows([(f"{SIGN_A} {SIGN_B}", "x y", "")] * 4)
    resources = build_resources(train, lexicon_on=False)
    test = rows([(f"{SIGN_A} {SIGN_B}", "x y", "")])
    positions, lines = evaluate(test, resources, ARMS)
    assert len(positions) == 2 * len(ARMS)
    assert len(lines) == len(ARMS)
    assert all(row["n_positions"] == 2 for row in lines)


def test_evaluate_skips_a_misaligned_row_rather_than_scoring_it():
    train = rows([(f"{SIGN_A} {SIGN_B}", "x y", "")] * 4)
    resources = build_resources(train, lexicon_on=False)
    test = rows([(f"{SIGN_A} {SIGN_B} {SIGN_Z}", "x y", "")])
    positions, lines = evaluate(test, resources, ARMS)
    assert positions == []
    assert lines == []


def test_evaluate_counts_a_split_cartouche_only_when_the_constraint_is_off():
    train = pd.concat(
        [
            rows([(f"{CARTOUCHE_OPEN} 𓃹 𓈖 {CARTOUCHE_CLOSE}", "o w n c", "")] * 40),
            rows([("𓋹 𓍑", "a b", "")] * 40),
        ],
        ignore_index=True,
    )
    resources = build_resources(train, lexicon_on=False)
    test = rows([(NAME, "wnjs", "")])
    arms = (
        Arm("all_off", pooled=False, discount=False, cartouche=False),
        Arm("cartouche_only", pooled=False, discount=False, cartouche=True),
    )
    _positions, lines = evaluate(test, resources, arms)
    by_arm = {row["arm"]: row for row in lines}
    assert by_arm["all_off"]["cartouches"] == 1
    assert by_arm["cartouche_only"]["cartouches"] == 1
    assert by_arm["all_off"]["cartouches_split"] == 1
    assert by_arm["cartouche_only"]["cartouches_split"] == 0
    # One cartouche, cut in several places: the span count and the boundary count are
    # different numbers and are reported under different names (review nit).
    assert by_arm["all_off"]["boundaries_inside_cartouches"] > 1
    assert by_arm["cartouche_only"]["boundaries_inside_cartouches"] == 0


# ---------- summarise ----------


def _summary_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    def pos(arm, position, correct, predicted, cohort, source="TLA", row_id="r"):
        return dict(arm=arm, row_id=row_id, source=source, position=position,
                    correct=correct, predicted=predicted, confidence=0.5,
                    confidence_legacy=0.5, confidence_undiscounted=0.5,
                    confidence_discounted=0.5, **{"class": cohort})

    positions = pd.DataFrame(
        [
            # baseline: position 0 wrong, position 1 right. Cohorts are per position
            # and identical in both arms.
            pos("all_off", 0, 0, "a", "firing"),
            pos("all_off", 1, 1, "b", "neighbour"),
            # treatment: position 0 fixed, position 1 broken
            pos("all_on", 0, 1, "z", "firing"),
            pos("all_on", 1, 0, "q", "neighbour"),
        ]
    )

    def line(arm, stage, line_exact, fp):
        return dict(arm=arm, row_id="r", source="TLA", stage=stage,
                    line_exact=line_exact, seg_exact=1, boundary_tp=1, boundary_fp=fp,
                    boundary_fn=0, boundary_fp_outside_cartouche=fp,
                    boundary_fn_outside_cartouche=0, cartouches=0, cartouches_split=0,
                    boundaries_inside_cartouches=0)

    lines = pd.DataFrame(
        [line("all_off", "Earlier Egyptian", 0, 1), line("all_on", "Late Egyptian", 0, 0)]
    )
    return positions, lines


def _row(summary, arm, scope="all"):
    return next(r for r in summary if r["arm"] == arm and r["scope"] == scope)


def test_summarise_pairs_each_position_against_the_baseline_arm():
    positions, lines = _summary_frames()
    summary, _calibration = summarise(positions, lines)
    treatment = _row(summary, "all_on")
    assert treatment["better_than_baseline"] == 1
    assert treatment["worse_than_baseline"] == 1
    assert treatment["positions_changed_vs_baseline"] == 2


def test_summarise_pairs_within_each_cohort():
    positions, lines = _summary_frames()
    summary, _calibration = summarise(positions, lines)
    treatment = _row(summary, "all_on")
    baseline = _row(summary, "all_off")
    assert treatment["firing_positions"] == baseline["firing_positions"] == 1
    assert treatment["acc_firing"] == 1.0 and baseline["acc_firing"] == 0.0
    assert (treatment["firing_better"], treatment["firing_worse"]) == (1, 0)
    assert treatment["neighbour_positions"] == 1
    assert treatment["acc_neighbour"] == 0.0
    assert (treatment["neighbour_better"], treatment["neighbour_worse"]) == (0, 1)


def test_an_empty_cohort_has_no_rate_rather_than_a_zero_one():
    positions, lines = _summary_frames()
    summary, _calibration = summarise(positions, lines)
    treatment = _row(summary, "all_on")
    assert treatment["other_positions"] == 0
    assert treatment["acc_other"] is None
    assert ratio(0, 0) is None


def test_summarise_counts_a_stage_that_moved():
    positions, lines = _summary_frames()
    summary, _calibration = summarise(positions, lines)
    assert _row(summary, "all_off")["stage_changed_vs_baseline"] == 0
    assert _row(summary, "all_on")["stage_changed_vs_baseline"] == 1


def test_an_unrouted_line_in_both_arms_is_not_a_stage_move():
    positions, lines = _summary_frames()
    lines["stage"] = ""
    summary, _calibration = summarise(positions, lines)
    assert _row(summary, "all_on")["stage_changed_vs_baseline"] == 0


def test_summarise_reports_whole_line_gains_and_losses():
    positions, lines = _summary_frames()
    lines.loc[lines["arm"] == "all_off", "line_exact"] = 1
    summary, _calibration = summarise(positions, lines)
    treatment = _row(summary, "all_on")
    assert (treatment["lines_exact_gained"], treatment["lines_exact_lost"]) == (0, 1)


def test_summarise_writes_source_stratified_rows():
    positions, lines = _summary_frames()
    summary, _calibration = summarise(positions, lines)
    assert {r["scope"] for r in summary} == {"all", "source:TLA"}
    assert _row(summary, "all_on", "source:TLA")["firing_better"] == 1


def test_summarise_boundary_f1_is_the_usual_harmonic_mean():
    positions, lines = _summary_frames()
    summary, _calibration = summarise(positions, lines)
    baseline = _row(summary, "all_off")
    # tp 1, fp 1, fn 0 -> precision 0.5, recall 1.0, F1 2/3.
    assert baseline["boundary_precision"] == 0.5
    assert baseline["boundary_recall"] == 1.0
    assert baseline["boundary_f1"] == pytest.approx(2 / 3)


def test_calibration_reports_every_confidence_kind_with_and_without_no_reading():
    positions, lines = _summary_frames()
    positions.loc[0, "predicted"] = ""
    _summary, calibration = summarise(positions, lines)
    kinds = {(r["arm"], r["confidence_kind"], r["subset"]) for r in calibration}
    for arm in ("all_off", "all_on"):
        for kind in ("legacy", "undiscounted", "discounted"):
            assert (arm, kind, "all") in kinds
            assert (arm, kind, "with_reading") in kinds
    off_all = next(r for r in calibration if r["arm"] == "all_off"
                   and r["confidence_kind"] == "legacy" and r["subset"] == "all")
    off_read = next(r for r in calibration if r["arm"] == "all_off"
                    and r["confidence_kind"] == "legacy" and r["subset"] == "with_reading")
    assert off_all["n_total"] == 2 and off_read["n_total"] == 1


def test_sign_test_is_two_sided_and_blank_without_discordant_pairs():
    assert sign_test_p(0, 0) is None
    assert sign_test_p(3, 3) == 1.0
    assert sign_test_p(6, 0) == pytest.approx(2 / 64)


def test_legacy_confidence_is_the_leading_candidate_over_the_top_five():
    """The pre-branch number, which neither confidence_of arm reproduces."""
    from app.services.reading_model import train_reading_model

    # One minority-reading position: the decoder's choice is not candidates[0] when
    # context forces it, so construct the prediction directly.
    model = train_reading_model(rows([(SIGN_A, "x", ""), (SIGN_A, "x", ""), (SIGN_A, "y", "")]))
    prediction = model.predict_sequence([SIGN_A])[0]
    total = sum(score for _, score in prediction.candidates)
    assert legacy_confidence(prediction) == pytest.approx(
        prediction.candidates[0][1] / total
    )

    class Minority:
        candidates = [("x", 3.0), ("y", 1.0)]
        reading_probability = 0.25

    assert legacy_confidence(Minority()) == pytest.approx(0.75)
    assert confidence_of(Minority(), discount=False) == pytest.approx(0.25)


# ---------- calibration ----------


def test_calibration_bins_group_by_confidence_and_report_accuracy():
    records = [(0.05, False), (0.05, False), (0.95, True), (0.95, True)]
    out = calibration_rows(records, bins=10)
    first = out[0]
    last = out[-1]
    assert first["n"] == 2 and first["accuracy"] == 0.0
    assert last["n"] == 2 and last["accuracy"] == 1.0
    # A perfectly calibrated, confident set: Brier = mean (c - outcome)^2.
    assert first["brier"] == pytest.approx(0.0025, abs=1e-6)


def test_calibration_includes_a_confidence_of_exactly_one_in_the_top_bin():
    out = calibration_rows([(1.0, True)], bins=10)
    assert out[-1]["n"] == 1


def test_calibration_of_an_empty_set_is_empty():
    assert calibration_rows([], bins=10) == []
