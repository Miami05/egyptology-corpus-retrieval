"""The paired test, the interval, Holm and the power floor — §4e's statistics.

Pre-registration (`docs/remeasure-preregistration-2026-10-25.md`, protocol B) and
`docs/plan-data-cleanup-2026-10-26.md` §4e:

    Per query, both are scored useful-in-top-3 or not. Discordant pairs: W (app only)
    and L (baseline only); ties (both or neither) are dropped from the test and
    reported. Test: one-sided exact sign test, `P(X >= W | X ~ Bin(W+L, 0.5)) < 0.05`.
    Effect: paired margin (W - L)/N with a 95% Newcombe (score, paired) interval.
    "Beats word overlap" only if p < 0.05 **and** the interval's lower bound > 0.
    … **Holm** correction across the two endpoints (family of 2, alpha = 0.05). An
    endpoint below its power floor is reported as "uninformative" and still counts in
    the family.

Nothing here is endpoint-specific: endpoints R and G hand it the same shape (per
line, a binary success for each side) and are analysed separately, never pooled.

The sign test is computed in exact integer arithmetic (`math.comb` over `2 ** n`),
so a p-value at the boundary is decided by the rational, not by a float. The
interval is Newcombe's method 10 for the difference of paired proportions (the
MOVER/"square-and-add" combination of two Wilson score intervals with the sample
correlation), which is what "Newcombe (score, paired)" names.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

#: Two-sided 95% normal quantile, for the Wilson intervals inside Newcombe's method.
Z_95 = 1.959963984540054

ALPHA = 0.05

#: §4e: "about 150 lines of this endpoint", judged separately per endpoint.
POWER_FLOOR = 150


@dataclass(frozen=True)
class PairedCounts:
    """The 2x2 table of one endpoint: `a` both, `b` app only, `c` baseline only, `d` neither."""

    both: int
    app_only: int
    baseline_only: int
    neither: int

    @classmethod
    def from_pairs(cls, pairs: list[tuple[bool, bool]]) -> "PairedCounts":
        """`pairs` is one `(app success, baseline success)` per line."""
        return cls(
            both=sum(1 for app, base in pairs if app and base),
            app_only=sum(1 for app, base in pairs if app and not base),
            baseline_only=sum(1 for app, base in pairs if base and not app),
            neither=sum(1 for app, base in pairs if not app and not base),
        )

    @property
    def n(self) -> int:
        return self.both + self.app_only + self.baseline_only + self.neither

    @property
    def discordant(self) -> int:
        return self.app_only + self.baseline_only

    @property
    def ties(self) -> int:
        """Dropped from the test, reported (pre-registration)."""
        return self.both + self.neither

    @property
    def app_rate(self) -> float:
        return (self.both + self.app_only) / self.n if self.n else 0.0

    @property
    def baseline_rate(self) -> float:
        return (self.both + self.baseline_only) / self.n if self.n else 0.0

    @property
    def margin(self) -> float:
        """The paired margin (W - L) / N."""
        return (self.app_only - self.baseline_only) / self.n if self.n else 0.0


def exact_sign_test(wins: int, losses: int) -> Fraction:
    """One-sided exact sign test: `P(X >= wins | X ~ Bin(wins + losses, 0.5))`.

    Exact rational arithmetic. With no discordant pairs the p-value is 1 — there is
    no evidence either way, which is not the same as a tie being evidence of no
    difference.
    """
    if wins < 0 or losses < 0:
        raise ValueError("wins and losses are counts")
    n = wins + losses
    if n == 0:
        return Fraction(1)
    tail = sum(math.comb(n, k) for k in range(wins, n + 1))
    return Fraction(tail, 2**n)


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval, the building block of Newcombe's paired method."""
    if n == 0:
        return (0.0, 1.0)
    centre = (successes + z * z / 2) / (n + z * z)
    half = (z / (n + z * z)) * math.sqrt(successes * (n - successes) / n + z * z / 4)
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe_paired_interval(counts: PairedCounts, z: float = Z_95) -> tuple[float, float]:
    """A 95% Newcombe (score, paired) interval for the difference of proportions.

    Newcombe's method 10: take Wilson intervals for the two marginal proportions and
    combine them with the sample correlation phi of the 2x2 table.

        lower = D - sqrt((p1-l1)^2 - 2 phi (p1-l1)(u2-p2) + (u2-p2)^2)
        upper = D + sqrt((u1-p1)^2 - 2 phi (u1-p1)(p2-l2) + (p2-l2)^2)

    with D = p1 - p2. When a margin is degenerate the correlation is undefined and
    phi is taken as 0, which widens the interval rather than narrowing it. The
    radicands are clamped at 0: with phi near 1 floating point can take them a hair
    below, and a negative radicand here is arithmetic noise, not a result.
    """
    n = counts.n
    if n == 0:
        return (-1.0, 1.0)
    a, b, c, d = counts.both, counts.app_only, counts.baseline_only, counts.neither
    p1, p2 = (a + b) / n, (a + c) / n
    diff = p1 - p2
    l1, u1 = wilson_interval(a + b, n, z)
    l2, u2 = wilson_interval(a + c, n, z)
    denominator = (a + b) * (c + d) * (a + c) * (b + d)
    phi = ((a * d - b * c) / math.sqrt(denominator)) if denominator > 0 else 0.0
    lower_radicand = (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2
    upper_radicand = (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2
    lower = diff - math.sqrt(max(0.0, lower_radicand))
    upper = diff + math.sqrt(max(0.0, upper_radicand))
    return (max(-1.0, lower), min(1.0, upper))


@dataclass(frozen=True)
class EndpointResult:
    """One endpoint's verdict. Endpoints are never pooled (§4e)."""

    endpoint: str
    counts: PairedCounts
    p_value: float
    p_value_exact: Fraction
    interval: tuple[float, float]
    underpowered: bool
    holm_threshold: float = ALPHA
    holm_reject: bool = False

    @property
    def interval_excludes_zero(self) -> bool:
        return self.interval[0] > 0

    @property
    def beats_baseline(self) -> bool:
        """Both conditions, both required: the Holm-corrected test and the interval."""
        return self.holm_reject and self.interval_excludes_zero

    @property
    def verdict(self) -> str:
        if self.underpowered:
            return "uninformative (below the power floor; counts in the Holm family)"
        if self.beats_baseline:
            return "beats its baseline"
        return "no difference shown"

    def describe(self) -> str:
        low, high = self.interval
        return (
            f"endpoint {self.endpoint}: n={self.counts.n}, app {self.counts.app_rate:.0%} "
            f"vs baseline {self.counts.baseline_rate:.0%}, W={self.counts.app_only} "
            f"L={self.counts.baseline_only} ties={self.counts.ties}; "
            f"margin {self.counts.margin:+.3f} [{low:+.3f}, {high:+.3f}]; "
            f"p={self.p_value:.4f} (Holm threshold {self.holm_threshold:.4f}); "
            f"{self.verdict}"
        )


def holm_thresholds(p_values: dict[str, float], alpha: float = ALPHA) -> dict[str, float]:
    """Holm's step-down thresholds for a family, keyed as `p_values` is.

    The family is every endpoint analysed, including one that is uninformative: §4e
    says an underpowered endpoint "still counts in the family", so the smallest
    threshold stays alpha / 2 for a family of two whether or not both are informative.
    """
    family = len(p_values)
    order = sorted(p_values, key=lambda key: (p_values[key], key))
    thresholds: dict[str, float] = {}
    still_rejecting = True
    for rank, key in enumerate(order):
        threshold = alpha / (family - rank)
        thresholds[key] = threshold
        if still_rejecting and p_values[key] > threshold:
            # Holm is step-down: once one hypothesis is not rejected, nothing after
            # it is either, however small its own threshold.
            still_rejecting = False
    return thresholds


def holm_rejections(p_values: dict[str, float], alpha: float = ALPHA) -> dict[str, bool]:
    family = len(p_values)
    order = sorted(p_values, key=lambda key: (p_values[key], key))
    rejected: dict[str, bool] = {}
    still_rejecting = True
    for rank, key in enumerate(order):
        threshold = alpha / (family - rank)
        if still_rejecting and p_values[key] <= threshold:
            rejected[key] = True
        else:
            still_rejecting = False
            rejected[key] = False
    return rejected


def analyse_endpoint(endpoint: str, pairs: list[tuple[bool, bool]]) -> EndpointResult:
    """One endpoint's counts, p-value and interval, before the Holm correction."""
    counts = PairedCounts.from_pairs(pairs)
    exact = exact_sign_test(counts.app_only, counts.baseline_only)
    return EndpointResult(
        endpoint=endpoint,
        counts=counts,
        p_value=float(exact),
        p_value_exact=exact,
        interval=newcombe_paired_interval(counts),
        underpowered=counts.n < POWER_FLOOR,
    )


def analyse_family(
    pairs_by_endpoint: dict[str, list[tuple[bool, bool]]], alpha: float = ALPHA
) -> dict[str, EndpointResult]:
    """Analyse each endpoint and apply Holm across the family. Never pools them."""
    results = {
        endpoint: analyse_endpoint(endpoint, pairs)
        for endpoint, pairs in pairs_by_endpoint.items()
    }
    p_values = {endpoint: result.p_value for endpoint, result in results.items()}
    thresholds = holm_thresholds(p_values, alpha)
    rejections = holm_rejections(p_values, alpha)
    return {
        endpoint: EndpointResult(
            endpoint=result.endpoint,
            counts=result.counts,
            p_value=result.p_value,
            p_value_exact=result.p_value_exact,
            interval=result.interval,
            underpowered=result.underpowered,
            holm_threshold=thresholds[endpoint],
            holm_reject=rejections[endpoint],
        )
        for endpoint, result in results.items()
    }
