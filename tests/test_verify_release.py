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
    "expected_corpus_rows": 130472,
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


# ---------------------------------------------------------------------------
# Audit A4/A23 (fix round 2): the gate measures the twin-controlled pool
# ---------------------------------------------------------------------------

TWIN_BLOCK = {
    "exclude_twins": 0.7,
    "expected_tokens": "current",
    "top3_useful_floor": 0.80,
    "mrr_floor": 0.70,
    "margin_floors": {"margin_over_bm25_baseline_top3": 0.0},
}


def _eval_output(top3: float, mrr: float, pool: str, margin: float = 0.1) -> str:
    return (
        "corpus_rows: 130472\ntotal_queries: 20\n"
        f"top1_useful_family_accuracy: 0.5\ntop3_useful_family_accuracy: {top3}\n"
        f"mrr: {mrr}\nfailures: 2\npool: {pool} (...)\n"
        f"margin_over_bm25_baseline_top3: {margin}\nmargin_over_overlap_baseline_top3: 0.2\n"
    )


CORPUS_BYTES = b"source,hieroglyphs\nBBAW,A1\n"


def _run_main(
    monkeypatch, tmp_path, baseline: dict, *argv: str, twin_top3=0.85, margin=0.1,
    benchmark_rows=20, corpus_rows=130472, queries=20,
):
    """verify_release.main with every subprocess replaced by canned output, the
    benchmark directory and the corpus file pointed at small files under tmp_path."""
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir(exist_ok=True)
    (benchmark_dir / "v4.csv").write_text(
        "query_id,query\n" + "".join(f"Q{i},\"a\nb\"\n" for i in range(benchmark_rows)),
        encoding="utf-8",
    )
    corpus = tmp_path / "examples.csv"
    corpus.write_bytes(CORPUS_BYTES)
    monkeypatch.setattr(vr, "BENCHMARK_DIR", benchmark_dir)
    monkeypatch.setattr(vr, "CORPUS_PATH", corpus)
    path = tmp_path / "baseline.json"
    path.write_text(__import__("json").dumps(baseline), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(cmd, label):
        commands.append(cmd)
        if "scripts/run_expert_paste_eval.py" in cmd:
            return 0, "passed 8/8", 0.0
        if "--exclude-twins" in cmd and cmd[cmd.index("--exclude-twins") + 1] != "0.0":
            out = _eval_output(twin_top3, 0.75, "twin-controlled", margin)
        else:
            out = _eval_output(0.90, 0.7917, "legacy")
        out = out.replace("corpus_rows: 130472", f"corpus_rows: {corpus_rows}")
        return 0, out.replace("total_queries: 20", f"total_queries: {queries}"), 0.0

    monkeypatch.setattr(vr, "run", fake_run)
    code = vr.main(["--baseline", str(path), "--skip-tests", *argv])
    return code, commands


def _flag(cmd: list[str], name: str) -> str:
    return cmd[cmd.index(name) + 1]


def test_a_baseline_without_a_twin_controlled_block_is_not_ready(monkeypatch, tmp_path, capsys):
    """Both reviews' blocker: the legacy pool (twins in) must not decide READY."""
    code, commands = _run_main(monkeypatch, tmp_path, dict(BASELINE, benchmark="v4.csv"))
    assert code == 1
    assert "no twin_controlled block" in capsys.readouterr().out
    evals = [c for c in commands if "scripts/run_competitive_ambiguity_eval.py" in c]
    assert len(evals) == 1 and _flag(evals[0], "--exclude-twins") == "0.0"


def test_allow_legacy_gate_gates_on_the_legacy_pool_and_says_so(monkeypatch, tmp_path, capsys):
    code, commands = _run_main(
        monkeypatch, tmp_path, dict(BASELINE, benchmark="v4.csv"), "--allow-legacy-gate"
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "LEGACY pool gates" in out and "verdict          READY" in out
    legacy = [c for c in commands if "scripts/run_competitive_ambiguity_eval.py" in c][0]
    # Exactly the published floors' configuration: twins in, frozen expected tokens.
    assert _flag(legacy, "--expected-tokens") == "frozen"
    assert _flag(legacy, "--useful-rule") == "v4"


def test_the_twin_controlled_run_gates_and_the_legacy_run_is_printed_beside_it(monkeypatch, tmp_path, capsys):
    baseline = dict(BASELINE, benchmark="v4.csv", useful_rule="v4", twin_controlled=TWIN_BLOCK)
    code, commands = _run_main(monkeypatch, tmp_path, baseline)
    assert code == 0
    evals = [c for c in commands if "scripts/run_competitive_ambiguity_eval.py" in c]
    assert [_flag(c, "--exclude-twins") for c in evals] == ["0.0", "0.7"]
    assert _flag(evals[1], "--expected-tokens") == "current"
    out = capsys.readouterr().out
    assert "TWIN-CONTROLLED pool gates" in out and "NON-GATING" in out
    # Legacy floors (0.90) are not applied to the twin-controlled number (0.85).
    code, _ = _run_main(monkeypatch, tmp_path, baseline, twin_top3=0.79)
    assert code == 1
    assert "top-3 useful 0.79 below floor 0.8" in capsys.readouterr().out


def test_a_margin_below_its_floor_fails_the_gate(monkeypatch, tmp_path, capsys):
    baseline = dict(BASELINE, benchmark="v4.csv", twin_controlled=TWIN_BLOCK)
    code, _ = _run_main(monkeypatch, tmp_path, baseline, margin=-0.05)
    assert code == 1
    assert "margin_over_bm25_baseline_top3 -0.05 below floor 0.0" in capsys.readouterr().out


def test_margin_floors_in_the_pure_check() -> None:
    floors = dict(BASELINE, margin_floors={"margin_over_bm25_baseline_top3": 0.05})
    assert vr.check_release_floors(0.9, 0.8, (8, 8), floors, {"margin_over_bm25_baseline_top3": 0.05}) == []
    assert len(vr.check_release_floors(0.9, 0.8, (8, 8), floors, {})) == 1
    # No margin floors: the old call shape is unchanged.
    assert vr.check_release_floors(0.9, 0.8, (8, 8), BASELINE) == []


@pytest.mark.parametrize(
    "block, message",
    [
        (dict(TWIN_BLOCK, exclude_twins=70), "not in (0, 1]"),
        (dict(TWIN_BLOCK, exclude_twins=0), "not in (0, 1]"),
        (dict(TWIN_BLOCK, expected_tokens="stale"), "unknown"),
        ({k: v for k, v in TWIN_BLOCK.items() if k != "mrr_floor"}, "no mrr_floor"),
        ({k: v for k, v in TWIN_BLOCK.items() if k != "exclude_twins"}, "numeric exclude_twins"),
    ],
)
def test_a_broken_twin_controlled_block_is_refused(block, message) -> None:
    with pytest.raises(ValueError, match=__import__("re").escape(message)):
        vr.twin_controlled_config(dict(BASELINE, twin_controlled=block))


def test_a_broken_block_stops_the_gate_instead_of_falling_back(monkeypatch, tmp_path, capsys):
    baseline = dict(BASELINE, benchmark="v4.csv", twin_controlled=dict(TWIN_BLOCK, exclude_twins=70))
    code, _ = _run_main(monkeypatch, tmp_path, baseline, "--allow-legacy-gate")
    assert code == 1
    assert "not in (0, 1]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Fix round 3 (Astra re-review): malformed configuration must fail closed
# ---------------------------------------------------------------------------


def test_an_explicitly_null_twin_controlled_block_is_not_ready(monkeypatch, tmp_path, capsys):
    """`"twin_controlled": null` is broken configuration, not absence: it must not let
    the legacy pool decide READY, with or without --allow-legacy-gate."""
    baseline = dict(BASELINE, benchmark="v4.csv", twin_controlled=None)
    for argv in ((), ("--allow-legacy-gate",)):
        code, commands = _run_main(monkeypatch, tmp_path, baseline, *argv)
        assert code == 1
        assert "twin_controlled is null" in capsys.readouterr().out
        assert not [c for c in commands if "scripts/run_competitive_ambiguity_eval.py" in c]


def test_an_absent_block_still_follows_the_legacy_override(monkeypatch, tmp_path, capsys):
    baseline = dict(BASELINE, benchmark="v4.csv")
    assert vr.twin_controlled_config(baseline) is None
    assert _run_main(monkeypatch, tmp_path, baseline)[0] == 1
    assert _run_main(monkeypatch, tmp_path, baseline, "--allow-legacy-gate")[0] == 0


@pytest.mark.parametrize(
    "block, message",
    [
        (dict(TWIN_BLOCK, top3_useful_floor="NaN"), "must be a number"),
        (dict(TWIN_BLOCK, top3_useful_floor=float("nan")), "must be finite"),
        (dict(TWIN_BLOCK, mrr_floor=float("inf")), "must be finite"),
        (dict(TWIN_BLOCK, top3_useful_floor=0), "not in (0, 1]"),
        (dict(TWIN_BLOCK, mrr_floor=0.0), "not in (0, 1]"),
        (dict(TWIN_BLOCK, mrr_floor=1.5), "not in (0, 1]"),
        (dict(TWIN_BLOCK, mrr_floor=True), "must be a number"),
        (dict(TWIN_BLOCK, margin_floors={"margin_over_bm25_baseline_top3": -0.5}), "not in [0, 1]"),
        (dict(TWIN_BLOCK, margin_floors={"margin_over_bm25_baseline_top3": float("nan")}), "must be finite"),
        (dict(TWIN_BLOCK, margin_floors={"margin_over_bm25_baseline_top3": "NaN"}), "must be a number"),
        (dict(TWIN_BLOCK, margin_floors={"margin_over_bm25": 0.0}), "not a known margin"),
        (dict(TWIN_BLOCK, margin_floors=[0.0]), "must be an object"),
        (dict(TWIN_BLOCK, margin_floors=None), "margin_floors is null"),
    ],
)
def test_malformed_floors_are_refused(block, message) -> None:
    with pytest.raises(ValueError, match=__import__("re").escape(message)):
        vr.twin_controlled_config(dict(BASELINE, twin_controlled=block))


def test_a_nan_floor_stops_the_gate_before_any_evaluation(monkeypatch, tmp_path, capsys):
    baseline = dict(
        BASELINE, benchmark="v4.csv",
        twin_controlled=dict(TWIN_BLOCK, top3_useful_floor=float("nan")),
    )
    code, commands = _run_main(monkeypatch, tmp_path, baseline)
    assert code == 1
    assert "must be finite" in capsys.readouterr().out
    assert not [c for c in commands if "scripts/run_competitive_ambiguity_eval.py" in c]


def test_a_malformed_top_level_floor_stops_the_legacy_gate(monkeypatch, tmp_path, capsys):
    baseline = dict(BASELINE, benchmark="v4.csv", top3_useful_floor=float("nan"))
    code, _ = _run_main(monkeypatch, tmp_path, baseline, "--allow-legacy-gate")
    assert code == 1
    assert "baseline top3_useful_floor must be finite" in capsys.readouterr().out


def test_the_pure_check_fails_on_a_nan_floor_instead_of_passing() -> None:
    assert vr.check_release_floors(0.5, 0.5, (8, 8), dict(BASELINE, mrr_floor=float("nan")))
    assert vr.check_release_floors(
        0.9, 0.8, (8, 8),
        dict(BASELINE, margin_floors={"margin_over_bm25_baseline_top3": -0.5}),
        {"margin_over_bm25_baseline_top3": -0.4},
    )


# ---------------------------------------------------------------------------
# Astra #15 / pre-registration A5: the gate checks it evaluated the intended inputs
# ---------------------------------------------------------------------------

READY_BASELINE = dict(BASELINE, benchmark="v4.csv", twin_controlled=TWIN_BLOCK)


def test_ready_inputs_pass_and_the_eval_is_pointed_at_the_hashed_corpus(monkeypatch, tmp_path, capsys):
    code, commands = _run_main(monkeypatch, tmp_path, READY_BASELINE)
    assert code == 0, capsys.readouterr().out
    evals = [c for c in commands if "scripts/run_competitive_ambiguity_eval.py" in c]
    assert {_flag(c, "--examples") for c in evals} == {str(tmp_path / "examples.csv")}
    assert "not pinned" in capsys.readouterr().out


def test_a_corpus_row_count_mismatch_fails(monkeypatch, tmp_path, capsys):
    code, _ = _run_main(monkeypatch, tmp_path, READY_BASELINE, corpus_rows=130471)
    assert code == 1
    assert "corpus rows (legacy pool) 130471 != expected 130472" in capsys.readouterr().out


def test_a_baseline_without_expected_corpus_rows_fails(monkeypatch, tmp_path, capsys):
    baseline = {k: v for k, v in READY_BASELINE.items() if k != "expected_corpus_rows"}
    code, _ = _run_main(monkeypatch, tmp_path, baseline)
    assert code == 1
    assert "expected_corpus_rows must be an integer" in capsys.readouterr().out


def test_a_query_count_that_differs_from_the_benchmark_fails(monkeypatch, tmp_path, capsys):
    """The eval answered fewer queries than the benchmark holds (or the file was
    swapped under it): the denominator changed, so the average is not comparable."""
    code, _ = _run_main(monkeypatch, tmp_path, READY_BASELINE, benchmark_rows=21)
    assert code == 1
    assert "query count (legacy pool) 20 != 21 rows in the benchmark" in capsys.readouterr().out


def test_expected_queries_is_enforced_when_present(monkeypatch, tmp_path, capsys):
    """Hard rows deleted from the benchmark itself: file and eval agree (18), the
    baseline's pinned count (20) does not."""
    baseline = dict(READY_BASELINE, expected_queries=20)
    code, _ = _run_main(monkeypatch, tmp_path, baseline, benchmark_rows=18, queries=18)
    assert code == 1
    assert "benchmark has 18 queries, baseline expects 20" in capsys.readouterr().out


def test_a_pinned_corpus_sha256_is_enforced(monkeypatch, tmp_path, capsys):
    import hashlib

    good = hashlib.sha256(CORPUS_BYTES).hexdigest()
    assert _run_main(monkeypatch, tmp_path, dict(READY_BASELINE, expected_corpus_sha256=good))[0] == 0
    capsys.readouterr()
    code, _ = _run_main(monkeypatch, tmp_path, dict(READY_BASELINE, expected_corpus_sha256="0" * 64))
    assert code == 1
    assert f"corpus sha256 {good} != expected {'0' * 64}" in capsys.readouterr().out


def test_an_absent_corpus_sha256_fails_only_when_required(monkeypatch, tmp_path, capsys):
    assert _run_main(monkeypatch, tmp_path, READY_BASELINE)[0] == 0
    code, _ = _run_main(monkeypatch, tmp_path, READY_BASELINE, "--require-corpus-sha256")
    assert code == 1
    assert "no expected_corpus_sha256" in capsys.readouterr().out
