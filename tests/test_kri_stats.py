"""Unit tests for §4e's statistics: sign test, Newcombe interval, Holm, power floor.

Synthetic counts only — nothing here reads data of any kind.

Note on verification: the sign test is checked against exact binomial arithmetic
computed independently in the test, and the Wilson interval against the textbook
value for 10/10 (0.7225, 1.0). The Newcombe paired interval is checked on its
*properties* (containment of the point estimate, antisymmetry under swapping the two
sides, degeneracy at zero discordance, and the phi = 0 fallback), not against a
published worked example — none was available offline, and a regression value
produced by this code would only pin this code to itself.
"""

from __future__ import annotations

import math
import sys
from fractions import Fraction
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.kri_stats import (
    ALPHA,
    POWER_FLOOR,
    PairedCounts,
    analyse_endpoint,
    analyse_family,
    exact_sign_test,
    holm_rejections,
    holm_thresholds,
    newcombe_paired_interval,
    wilson_interval,
)


def pairs(both: int, app_only: int, baseline_only: int, neither: int):
    return (
        [(True, True)] * both
        + [(True, False)] * app_only
        + [(False, True)] * baseline_only
        + [(False, False)] * neither
    )


# --------------------------------------------------------------------- the sign test


def test_the_sign_test_is_the_exact_binomial_tail():
    for wins in range(0, 8):
        for losses in range(0, 8):
            n = wins + losses
            expected = (
                Fraction(sum(math.comb(n, k) for k in range(wins, n + 1)), 2**n)
                if n
                else Fraction(1)
            )
            assert exact_sign_test(wins, losses) == expected


def test_five_wins_and_no_losses_is_one_in_thirty_two():
    assert exact_sign_test(5, 0) == Fraction(1, 32)
    assert float(exact_sign_test(5, 0)) < ALPHA


def test_four_wins_and_no_losses_does_not_reach_significance():
    """The smallest cohort that can ever produce p < 0.05 one-sided is five."""
    assert exact_sign_test(4, 0) == Fraction(1, 16)
    assert float(exact_sign_test(4, 0)) > ALPHA


def test_no_discordant_pairs_gives_p_equal_to_one():
    """No evidence either way is not evidence of no difference."""
    assert exact_sign_test(0, 0) == 1


def test_the_test_is_exact_at_the_boundary_not_floating():
    assert exact_sign_test(5, 0) == Fraction(1, 32)
    assert exact_sign_test(5, 0) * 32 == 1


# --------------------------------------------------------------------- Wilson


def test_the_wilson_interval_matches_the_textbook_value_for_ten_out_of_ten():
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=5e-4)
    assert high == pytest.approx(1.0)


def test_the_wilson_interval_is_symmetric_under_swapping_successes_and_failures():
    low, high = wilson_interval(3, 10)
    other_low, other_high = wilson_interval(7, 10)
    assert low == pytest.approx(1 - other_high)
    assert high == pytest.approx(1 - other_low)


# --------------------------------------------------------------------- Newcombe


def test_the_interval_contains_the_point_estimate():
    for counts in [
        PairedCounts(10, 5, 2, 3),
        PairedCounts(0, 7, 0, 3),
        PairedCounts(4, 4, 4, 4),
        PairedCounts(0, 0, 0, 20),
    ]:
        low, high = newcombe_paired_interval(counts)
        assert low <= counts.margin <= high


def test_swapping_the_two_sides_reflects_the_interval():
    counts = PairedCounts(both=12, app_only=9, baseline_only=3, neither=6)
    swapped = PairedCounts(both=12, app_only=3, baseline_only=9, neither=6)
    low, high = newcombe_paired_interval(counts)
    other_low, other_high = newcombe_paired_interval(swapped)
    assert low == pytest.approx(-other_high)
    assert high == pytest.approx(-other_low)


def test_a_complete_sweep_for_the_app_excludes_zero():
    low, _high = newcombe_paired_interval(PairedCounts(both=0, app_only=20, baseline_only=0, neither=0))
    assert low > 0


def test_perfect_agreement_gives_an_interval_around_zero():
    low, high = newcombe_paired_interval(PairedCounts(both=10, app_only=0, baseline_only=0, neither=10))
    assert low <= 0 <= high


def test_an_empty_endpoint_gives_the_widest_possible_interval():
    assert newcombe_paired_interval(PairedCounts(0, 0, 0, 0)) == (-1.0, 1.0)


def test_a_degenerate_margin_falls_back_to_phi_zero_rather_than_dividing_by_zero():
    """Every line a success for both sides: one marginal is degenerate."""
    low, high = newcombe_paired_interval(PairedCounts(both=10, app_only=0, baseline_only=0, neither=0))
    assert low <= 0 <= high
    assert math.isfinite(low) and math.isfinite(high)


# --------------------------------------------------------------------- Holm


def test_holm_thresholds_for_a_family_of_two():
    thresholds = holm_thresholds({"G": 0.01, "R": 0.90})
    assert thresholds["G"] == pytest.approx(ALPHA / 2)
    assert thresholds["R"] == pytest.approx(ALPHA)


def test_holm_rejects_the_smaller_p_only_when_it_clears_alpha_over_two():
    assert holm_rejections({"G": 0.01, "R": 0.90}) == {"G": True, "R": False}
    assert holm_rejections({"G": 0.03, "R": 0.04}) == {"G": False, "R": False}
    assert holm_rejections({"G": 0.001, "R": 0.02}) == {"G": True, "R": True}


def test_holm_is_step_down_a_later_hypothesis_cannot_overtake_an_earlier_one():
    """0.049 < alpha, but the smaller p failed alpha/2, so nothing is rejected."""
    assert holm_rejections({"G": 0.03, "R": 0.049}) == {"G": False, "R": False}


def test_an_underpowered_endpoint_still_occupies_a_slot_in_the_family():
    """§4e: it is reported "uninformative" and still counts in the family of two."""
    analysis = analyse_family({"G": pairs(0, 5, 0, 0), "R": []})
    assert analysis["R"].underpowered and analysis["R"].counts.n == 0
    assert analysis["G"].holm_threshold == pytest.approx(ALPHA / 2)


# --------------------------------------------------------------------- the verdict


def test_both_conditions_are_required_to_beat_a_baseline():
    """p < alpha (Holm-corrected) AND the interval's lower bound > 0 (§4e)."""
    analysis = analyse_family({"G": pairs(0, 6, 0, 0), "R": pairs(2, 3, 2, 3)})
    g = analysis["G"]
    assert g.p_value < g.holm_threshold and g.interval[0] > 0 and g.beats_baseline
    r = analysis["R"]
    assert not r.beats_baseline


def test_an_endpoint_below_the_power_floor_is_uninformative_in_words():
    result = analyse_endpoint("G", pairs(0, 6, 0, 0))
    assert result.counts.n < POWER_FLOOR
    assert result.underpowered and "uninformative" in result.verdict


def test_an_endpoint_above_the_floor_is_not_marked_uninformative():
    result = analyse_endpoint("R", pairs(POWER_FLOOR, 0, 0, 0))
    assert not result.underpowered


def test_the_counts_split_ties_from_discordant_pairs():
    counts = PairedCounts.from_pairs(pairs(3, 4, 2, 1))
    assert (counts.n, counts.discordant, counts.ties) == (10, 6, 4)
    assert counts.app_rate == pytest.approx(0.7) and counts.baseline_rate == pytest.approx(0.5)
    assert counts.margin == pytest.approx(0.2)


def test_the_description_names_the_endpoint_and_both_conditions():
    text = analyse_endpoint("G", pairs(1, 5, 1, 1)).describe()
    assert text.startswith("endpoint G:") and "margin" in text and "Holm threshold" in text
