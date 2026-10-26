"""Unit tests for the app-segment → gold-span mapping (endpoint G).

Synthetic fixtures only: the "lines" below are made of real hieroglyph codepoints in
invented combinations, and nothing here reads the corpus or any KRI path.

Exhaustive over the cases the brief names: exact match, split, merge, partial
overlap, repeated identical groups, placeholder-only gold groups, empty app output —
plus the mismatch that must stop a run rather than be scored.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bfreq_baseline import build_table, score_endpoint_g
from scripts.kri_segment_mapping import (
    OUTCOME_ABSENT,
    OUTCOME_EXACT,
    OUTCOME_MERGED,
    OUTCOME_NO_SIGNS,
    OUTCOME_PARTIAL,
    OUTCOME_SPLIT,
    MappingError,
    alignment_key,
    map_app_segments_to_gold,
    spans_of,
)

import pandas as pd

A = "\U00013000"
B = "\U00013001"
C = "\U00013002"
D = "\U00013003"
E = "\U00013004"
Z2 = "\U000133E5"
Z15B = "\U000133FC"
PLACEHOLDER = "<g>M12B</g>"
JOINER = "\U00013430"  # a layout control: deleted by the app's normalisation


def outcomes(result) -> list[str]:
    return [outcome.outcome for outcome in result.outcomes]


# --------------------------------------------------------------------- alignment


def test_the_alignment_string_keeps_placeholders_and_drops_controls_and_spaces():
    assert alignment_key(f"{A} {B}") == A + B
    assert alignment_key(A + JOINER + B) == A + B
    assert len(alignment_key(PLACEHOLDER)) == 1  # a placeholder is one aligned char


def test_spans_are_contiguous_and_half_open():
    assert spans_of([A + B, C, D + E]) == [(0, 2), (2, 3), (3, 5)]


def test_a_variant_codepoint_aligns_with_its_canonical_form():
    """Z15B and Z2 are one sign to the app, so they must not break the offsets."""
    result = map_app_segments_to_gold([A + Z15B], [A + Z2], [["nfr"]])
    assert outcomes(result) == [OUTCOME_EXACT]


# --------------------------------------------------------------------- the six outcomes


def test_exact_segmentation_hands_each_gold_group_its_own_top_three():
    result = map_app_segments_to_gold(
        [A + B, C, D],
        [A + B, C, D],
        [["nfr", "nfr.w", "nfrt"], ["ḥtp"], ["nswt", "nsw"]],
    )
    assert outcomes(result) == [OUTCOME_EXACT] * 3
    assert result.app_candidates == [["nfr", "nfr.w", "nfrt"], ["ḥtp"], ["nswt", "nsw"]]
    assert result.counts[OUTCOME_EXACT] == 3


def test_only_the_top_three_are_passed_on():
    result = map_app_segments_to_gold([A], [A], [["a", "b", "c", "d", "e"]])
    assert result.app_candidates == [["a", "b", "c"]]


def test_a_merge_is_a_miss_for_both_gold_groups_it_swallowed():
    """The app read AB as one word; the gold has A and B. §4e: a merge is a miss."""
    result = map_app_segments_to_gold([A, B, C], [A + B, C], [["nfrḥtp"], ["nswt"]])
    assert outcomes(result) == [OUTCOME_MERGED, OUTCOME_MERGED, OUTCOME_EXACT]
    assert result.app_candidates == [None, None, ["nswt"]]


def test_a_split_is_a_miss_for_the_gold_group_it_cut_up():
    result = map_app_segments_to_gold([A + B, C], [A, B, C], [["nfr"], ["ḥtp"], ["nswt"]])
    assert outcomes(result) == [OUTCOME_SPLIT, OUTCOME_EXACT]
    assert result.outcomes[0].app_indices == (0, 1)


def test_a_boundary_that_crosses_is_a_partial_overlap_not_a_split_or_a_merge():
    """Gold AB|CD, app ABC|D: the first app segment covers A B and part of the next."""
    result = map_app_segments_to_gold(
        [A + B, C + D], [A + B + C, D], [["nfrḥtp"], ["nswt"]]
    )
    assert outcomes(result) == [OUTCOME_MERGED, OUTCOME_PARTIAL]


def test_a_crossing_boundary_in_the_middle_is_partial_on_both_sides():
    """Gold AB|CD|E, app A|BC|DE.

    The first two gold groups are cut across — one app segment lies inside them and
    another crosses out of them, which is neither a clean split nor a clean merge.
    The last gold group, E, is wholly inside the app's final segment, so that one is
    a merge. All three are misses either way; the distinction is for the report.
    """
    result = map_app_segments_to_gold(
        [A + B, C + D, E], [A, B + C, D + E], [["a"], ["bc"], ["de"]]
    )
    assert outcomes(result) == [OUTCOME_PARTIAL, OUTCOME_PARTIAL, OUTCOME_MERGED]
    assert result.app_candidates == [None, None, None]


def test_empty_app_output_makes_every_gold_group_absent_rather_than_raising():
    """The app answering nothing is a clean sweep of misses, not a broken run."""
    result = map_app_segments_to_gold([A + B, C], [], [])
    assert outcomes(result) == [OUTCOME_ABSENT, OUTCOME_ABSENT]
    assert result.app_candidates == [None, None]


def test_a_gold_group_with_no_signs_is_a_miss_and_shifts_nothing():
    result = map_app_segments_to_gold([A, "", B], [A, B], [["nfr"], ["ḥtp"]])
    assert outcomes(result) == [OUTCOME_EXACT, OUTCOME_NO_SIGNS, OUTCOME_EXACT]
    assert result.app_candidates == [["nfr"], None, ["ḥtp"]]


def test_a_placeholder_only_gold_group_is_aligned_and_the_app_may_answer_it():
    """B-freq cannot key it (§4a `signs` deletes placeholders); the app can."""
    result = map_app_segments_to_gold(
        [A, PLACEHOLDER, B], [A, PLACEHOLDER, B], [["nfr"], ["ḥtp"], ["nswt"]]
    )
    assert outcomes(result) == [OUTCOME_EXACT] * 3
    assert result.app_candidates[1] == ["ḥtp"]


def test_a_placeholder_only_gold_group_the_app_merged_is_still_a_miss():
    result = map_app_segments_to_gold(
        [A, PLACEHOLDER, B], [A + PLACEHOLDER, B], [["nfrḥtp"], ["nswt"]]
    )
    assert outcomes(result) == [OUTCOME_MERGED, OUTCOME_MERGED, OUTCOME_EXACT]


# --------------------------------------------------------------------- repeats


def test_repeated_identical_groups_are_told_apart_by_position():
    result = map_app_segments_to_gold([A, B, A], [A, B, A], [["nfr"], ["ḥtp"], ["nfr"]])
    assert outcomes(result) == [OUTCOME_EXACT] * 3
    assert [o.repeated_sign_string for o in result.outcomes] == [True, False, True]
    assert result.repeated_groups == 2
    assert "repeated sign string" in result.summary()


def test_a_repeat_is_scored_on_its_own_app_segment_not_the_first_one():
    """The two occurrences may get different answers; each keeps its own."""
    result = map_app_segments_to_gold([A, B, A], [A, B, A], [["nfr"], ["ḥtp"], ["bꜣk"]])
    assert result.app_candidates == [["nfr"], ["ḥtp"], ["bꜣk"]]


def test_one_app_segment_never_answers_two_gold_groups():
    """A merge consumes nothing: both gold groups miss, neither borrows the answer."""
    result = map_app_segments_to_gold([A, A], [A + A], [["nfr nfr"]])
    assert result.app_candidates == [None, None]
    used = [index for o in result.outcomes if o.candidates is not None for index in o.app_indices]
    assert len(used) == len(set(used))


def test_a_repeat_that_the_app_merged_at_one_occurrence_only_loses_that_one():
    result = map_app_segments_to_gold(
        [A, B, A, C], [A, B, A + C], [["nfr"], ["ḥtp"], ["bꜣkC"]]
    )
    assert outcomes(result) == [OUTCOME_EXACT, OUTCOME_EXACT, OUTCOME_MERGED, OUTCOME_MERGED]


# --------------------------------------------------------------------- refusals


def test_a_different_sign_string_stops_the_run():
    with pytest.raises(MappingError) as error:
        map_app_segments_to_gold([A, B], [A, C], [["nfr"], ["ḥtp"]])
    message = str(error.value)
    assert "not the same sign string" in message
    assert A not in message and C not in message  # offsets only, never glyphs


def test_a_missing_candidate_list_is_refused():
    with pytest.raises(MappingError):
        map_app_segments_to_gold([A, B], [A, B], [["nfr"]])


def test_determinism_the_same_input_maps_the_same_way_every_time():
    args = ([A + B, C, A + B], [A, B, C, A + B], [["a"], ["b"], ["c"], ["ab"]])
    first = map_app_segments_to_gold(*args)
    second = map_app_segments_to_gold(*args)
    assert first == second
    assert outcomes(first) == [OUTCOME_SPLIT, OUTCOME_EXACT, OUTCOME_EXACT]


# --------------------------------------------------------------------- with the scorer


def corpus(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"hieroglyphs": h, "transliteration_gold": t, "language_stage": "Late Egyptian"}
            for h, t in rows
        ]
    )


def test_the_mapping_output_is_what_score_endpoint_g_takes():
    """End to end on a synthetic line: mapping → the frozen scorer, unmodified."""
    table = build_table(corpus([(f"{A} {B} {C}", "nfr ḥtp nswt")] * 2))
    gold_groups = [A, B, C]
    gold_readings = ["nfr", "ḥtp", "nswt"]
    # The app merged A and B, and read C correctly.
    mapping = map_app_segments_to_gold(gold_groups, [A + B, C], [["nfrḥtp"], ["nswt"]])
    report, app_score, baseline_score = score_endpoint_g(
        table, gold_groups, gold_readings, mapping.app_candidates
    )
    assert report.groups == 3 and report.scorable == 3
    assert app_score.hits == 1 and app_score.score == pytest.approx(1 / 3)
    assert app_score.success is False
    # B-freq is given the gold segmentation, so it answers all three.
    assert baseline_score.hits == 3 and baseline_score.success is True


def test_an_empty_app_output_scores_zero_without_crashing_the_scorer():
    table = build_table(corpus([(f"{A} {B}", "nfr ḥtp")]))
    mapping = map_app_segments_to_gold([A, B], [], [])
    _report, app_score, baseline_score = score_endpoint_g(
        table, [A, B], ["nfr", "ḥtp"], mapping.app_candidates
    )
    assert app_score.hits == 0 and app_score.success is False
    assert baseline_score.hits == 2
