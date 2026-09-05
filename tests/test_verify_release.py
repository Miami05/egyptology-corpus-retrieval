"""Floor-comparison logic for scripts/verify_release.py, tested without the corpus.

The release gate is only as trustworthy as the rule that turns measured numbers into a
READY / NOT READY verdict, and that rule must be checkable in milliseconds — no eval
run, no 130k-row load. `check_release_floors` is the pure function that decides, so it
is exercised directly here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_release", PROJECT_ROOT / "scripts" / "verify_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


vr = _load_module()

BASELINE = {
    "top3_useful_floor": 0.90,
    "mrr_floor": 0.7917,
    "expert_pastes_floor": "8/8",
}


def test_at_the_floor_is_ready() -> None:
    """A build measured at exactly the floor passes — equality is not a failure."""
    assert vr.check_release_floors(0.90, 0.7917, (8, 8), BASELINE) == []


def test_above_the_floor_is_ready() -> None:
    assert vr.check_release_floors(0.95, 0.82, (8, 8), BASELINE) == []


def test_top3_below_floor_fails() -> None:
    failures = vr.check_release_floors(0.85, 0.7917, (8, 8), BASELINE)
    assert len(failures) == 1
    assert "top-3" in failures[0]


def test_mrr_below_floor_fails() -> None:
    failures = vr.check_release_floors(0.90, 0.75, (8, 8), BASELINE)
    assert len(failures) == 1
    assert "MRR" in failures[0]


def test_fewer_than_eight_pastes_fails() -> None:
    failures = vr.check_release_floors(0.90, 0.7917, (7, 8), BASELINE)
    assert len(failures) == 1
    assert "expert pastes" in failures[0]


def test_all_three_can_fail_at_once() -> None:
    failures = vr.check_release_floors(0.10, 0.10, (3, 8), BASELINE)
    assert len(failures) == 3


def test_unmeasured_numbers_fail_rather_than_pass() -> None:
    """A run that produced no parseable number must never be read as 'at the floor'."""
    failures = vr.check_release_floors(None, None, None, BASELINE)
    assert len(failures) == 3


def test_a_different_paste_total_fails_even_if_all_passed() -> None:
    """`10/10` is not `8/8`: the paste set changed, which the gate must not wave
    through just because everything in it passed."""
    failures = vr.check_release_floors(0.90, 0.7917, (10, 10), BASELINE)
    assert len(failures) == 1
    assert "expert pastes" in failures[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8/8", (8, 8)),
        ("7/8", (7, 8)),
        (" 8 / 8 ", (8, 8)),
        ("?", None),
        ("", None),
        ("8", None),
    ],
)
def test_parse_pastes(text: str, expected) -> None:
    assert vr.parse_pastes(text) == expected


def test_committed_baseline_is_well_formed() -> None:
    """The shipped baseline must carry every field the gate reads, with the published
    v4 floors — a typo here silently weakens the release check."""
    baseline = vr.load_baseline(PROJECT_ROOT / "data" / "benchmarks" / "release_baseline.json")
    assert baseline["benchmark"] == "competitive_ambiguity_eval_queries_v4.csv"
    assert baseline["stage"] == "auto"
    assert baseline["query_path"] == "app"
    assert baseline["top3_useful_floor"] == 0.90
    assert baseline["mrr_floor"] == 0.7917
    assert baseline["expert_pastes_floor"] == "8/8"
    assert baseline["expected_corpus_rows"] == 130472
    # The floors as shipped must call the current published numbers READY.
    assert vr.check_release_floors(0.90, 0.7917, (8, 8), baseline) == []


def test_resolve_benchmark_prefers_override() -> None:
    baseline = {"benchmark": "competitive_ambiguity_eval_queries_v4.csv"}
    override = vr.resolve_benchmark(baseline, "/some/other.csv")
    assert str(override) == "/some/other.csv"
    default = vr.resolve_benchmark(baseline, None)
    assert default.name == "competitive_ambiguity_eval_queries_v4.csv"
