"""Tests for scripts/check_transition_smoothing_gates.py and scripts/run_transition_smoothing_prereg.sh.

The gate checker turns the pre-registration's rules into exit codes; the runner stops on the
first non-zero one. Like the KRI-fixes pair it replaces for this experiment, the runner is
reproduced verbatim in the pre-registration and a test fails if the two differ.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import check_transition_smoothing_gates as gates
from scripts.check_transition_smoothing_gates import (
    ALL_ARMS,
    bootstrap_indices,
    check_dev,
    check_dev_manifest,
    check_harness,
    check_paste,
    check_preflight,
    group_counts,
    main,
    mechanism_report,
    paired_difference,
    select_primary,
)

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "transition-smoothing-preregistration-2026-10-28.md"
RUNNER = ROOT / "scripts" / "run_transition_smoothing_prereg.sh"
REGISTERED_WT = Path(
    "/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/transition-smoothing-2026-10-28"
)


# ---------- the paired bootstrap ----------


def test_bootstrap_indices_are_a_fixed_function_of_the_seed():
    first = bootstrap_indices(50, resamples=200)
    again = bootstrap_indices(50, resamples=200)
    assert first.dtype == np.int32 and first.shape == (200, 50)
    assert np.array_equal(first, again)
    assert first.min() >= 0 and first.max() < 50
    assert (gates.SEED, gates.BOOTSTRAP_RESAMPLES, gates.CI_PERCENTILES) == (20261026, 10_000, (2.5, 97.5))
    rng = np.random.default_rng(20261026)
    assert np.array_equal(first, rng.integers(0, 50, size=(200, 50), dtype=np.int32))


def test_identical_arms_have_a_zero_interval_and_a_clear_gain_has_a_positive_one():
    positions = np.full(60, 5)
    base = np.full(60, 3)
    indices = bootstrap_indices(60, resamples=1000)
    same = paired_difference(base, base, positions, indices)
    assert (same["point"], same["ci_low"], same["ci_high"], same["correct_diff"]) == (0.0, 0.0, 0.0, 0)
    better = paired_difference(base + 1, base, positions, indices)
    assert better["ci_low"] == pytest.approx(0.2) and better["ci_high"] == pytest.approx(0.2)
    # a gain concentrated in a few groups has an interval that reaches zero
    patchy = base.copy()
    patchy[:3] += 5
    ci = paired_difference(patchy, base, positions, indices)
    assert ci["correct_diff"] == 15 and ci["ci_low"] <= 0.0 < ci["ci_high"]


def test_the_ratio_of_sums_is_used_not_a_mean_of_group_accuracies():
    # group 0: 1 position, group 1: 99 positions; a mean of per-group accuracies would weigh
    # them equally, the ratio of sums does not
    per_group_positions = np.array([1, 99])
    a = np.array([1, 50])
    b = np.array([0, 50])
    indices = np.array([[0, 0]], dtype=np.int32)  # one resample: group 0 twice
    out = paired_difference(a, b, per_group_positions, indices)
    assert out["ci_low"] == 1.0  # (1 + 1) / (1 + 1)
    assert out["point"] == pytest.approx(1 / 100)


# ---------- R7 selection ----------


def per_group(corrects: dict, positions_per_group=10, groups=40, seed=1):
    """A group_counts-shaped dict with `corrects[arm]` total correct spread over the groups."""
    rng = np.random.default_rng(seed)
    out = {"keys": [f"g{i:03d}" for i in range(groups)], "positions": np.full(groups, positions_per_group)}
    for arm, total in corrects.items():
        base = np.full(groups, total // groups)
        for i in rng.permutation(groups)[: total % groups]:
            base[i] += 1
        out[arm] = base
    return out


def test_no_eligible_arm_means_no_primary():
    table = per_group({"off": 200, "c2_transition_only": 199, "c2": 200, "c3": 150})
    record = select_primary(table, bootstrap_indices(40, resamples=500))
    assert record["eligible"] == [] and record["primary"] is None and record["best"] is None
    assert record["arms"]["c2"]["eligible"] is False  # equal is not better


def test_the_simplest_arm_wins_when_it_is_not_distinguishably_worse_than_the_best():
    # c3 is best by one position; c2_transition_only is eligible and within the noise of c3
    table = per_group({"off": 200, "c2_transition_only": 205, "c2": 203, "c3": 206})
    record = select_primary(table, bootstrap_indices(40, resamples=500))
    assert record["best"] == "c3"
    assert record["eligible"] == ["c2_transition_only", "c2", "c3"]
    assert record["primary"] == "c2_transition_only"
    assert record["walk"][0]["qualifies"] is True and len(record["walk"]) == 1


def test_a_clearly_better_complex_arm_wins_over_an_eligible_simple_one():
    # every group gains for c3, almost none for c2_transition_only: the interval of
    # acc(c3) - acc(c2_transition_only) is strictly positive, so the walk moves on
    table = per_group({"off": 200, "c2_transition_only": 201, "c2": 201, "c3": 320})
    record = select_primary(table, bootstrap_indices(40, resamples=1000))
    assert record["best"] == "c3" and record["primary"] == "c3"
    assert [step["arm"] for step in record["walk"]] == ["c2_transition_only", "c2", "c3"]
    assert [step["qualifies"] for step in record["walk"]] == [False, False, True]
    assert record["walk"][0]["best_minus_arm"]["ci_low"] > 0


def test_an_exact_tie_in_delta_is_broken_by_simplicity():
    table = per_group({"off": 200, "c2_transition_only": 200, "c2": 210, "c3": 210})
    record = select_primary(table, bootstrap_indices(40, resamples=500))
    assert record["eligible"] == ["c2", "c3"] and record["best"] == "c2" and record["primary"] == "c2"


def test_an_ineligible_simple_arm_is_never_primary():
    table = per_group({"off": 200, "c2_transition_only": 190, "c2": 205, "c3": 205})
    record = select_primary(table, bootstrap_indices(40, resamples=500))
    assert record["primary"] == "c2" and "c2_transition_only" not in record["eligible"]


# ---------- fixtures for the CSV-level checks ----------


def make_positions(correct_by_arm: dict, groups=30, per_group_n=4, members=(1, 2)):
    rows = []
    rng = np.random.default_rng(5)
    for arm in ALL_ARMS:
        flags = correct_by_arm[arm]
        for g in range(groups):
            for pos in range(per_group_n):
                rows.append(
                    {
                        "arm": arm, "row_id": f"TLA:{g}", "source": "TLA" if g % 2 else "BBAW",
                        "group_key": f"TLA:sentence:{g}", "position": pos, "group": "g",
                        "gold_reading": "x", "predicted": "x" if flags(g, pos) else "y",
                        "correct": int(flags(g, pos)), "stage": "Earlier Egyptian",
                        "was_seen": 1, "is_borrowed": 0, "attested_count": 5, "reading_count": 5,
                        "reading_probability": 0.5, "confidence": 0.5, "prev_gold": "p" if pos else "",
                        "prev_n": 1 if pos in members else 0, "prev_vobs": 1 if pos in members else 2,
                        "band": "1" if pos in members else "", "member1": int(pos in members),
                        "member2": 0, "own_prev_vobs1": int(pos in members and arm != "c3"),
                        "runner_up": "", "t_chosen_off": 0.0, "t_chosen_arm": -0.5,
                        "t_runner_off": "", "t_runner_arm": "",
                    }
                )
    return pd.DataFrame(rows)


def make_lines(positions: pd.DataFrame, hyp_stage="Earlier Egyptian", fp_extra=0):
    rows = []
    for arm in ALL_ARMS:
        for g in sorted(set(positions["group_key"])):
            rows.append(
                {
                    "arm": arm, "row_id": f"TLA:{g.split(':')[-1]}", "source": "TLA", "group_key": g,
                    "stage": "Earlier Egyptian", "coverage": "Earlier Egyptian=4",
                    "off_scores": "Earlier Egyptian=-1.0", "hyp_stage": hyp_stage if arm != "off" else "Earlier Egyptian",
                    "hyp_coverage": "Earlier Egyptian=4", "hyp_scores": "Earlier Egyptian=-1.5",
                    "n_positions": 4, "n_correct": 4, "line_exact": 1, "seg_exact": 1,
                    "boundary_tp": 3, "boundary_fp": fp_extra if arm == "c2" else 0, "boundary_fn": 0,
                }
            )
    return pd.DataFrame(rows)


def write_test_dir(tmp_path, positions, lines, monkeypatch, record_primary="c2"):
    run = tmp_path / "run"
    run.mkdir(parents=True)
    positions.to_csv(run / "test_positions.csv", index=False)
    lines.to_csv(run / "test_lines.csv", index=False)
    (run / "test_manifest_used.csv").write_text("source\nTLA\n")
    monkeypatch.setattr(gates, "TEST_MANIFEST_SHA", hashlib.sha256(b"source\nTLA\n").hexdigest())
    pd.DataFrame(
        [{"arm": a, "subset": "all", "brier": 0.2, "bin_low": 0} for a in ALL_ARMS]
    ).to_csv(run / "test_calibration.csv", index=False)
    pd.DataFrame([{"component": "decode_off", "seconds": 1.0}]).to_csv(run / "test_timing.csv", index=False)
    record = tmp_path / "record.json"
    record.write_text(
        json.dumps(
            {"primary": record_primary, "dev_manifest_sha256": "x", "approved_commit": "a" * 40,
             "arms": {}, "eligible": [], "walk": [], "dev_rate": 0.1}
        )
    )
    return run, record


def flags(base_rate_by_arm):
    """correct(group, position): a deterministic pattern with a per-arm number of misses."""
    def make(misses):
        return lambda g, pos: not (pos == 0 and g < misses)
    return {arm: make(m) for arm, m in base_rate_by_arm.items()}


# ---------- harness rules ----------


def test_the_primary_passes_c_prime_when_the_interval_excludes_zero(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions), monkeypatch)
    out, failures = check_harness(run, record)
    assert failures == []
    text = "\n".join(out)
    assert "(c') c2 [PRIMARY]" in text and "PASS" in text
    assert "(d') mechanism positions" in text and "(f') c2: decoded under off's stage on every line: yes" in text
    assert "(h) off: Brier" in text and "(i) runtime" in text


def test_the_primary_fails_c_prime_when_it_is_not_better_than_off(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 5, "c2_transition_only": 5, "c2": 5, "c3": 5}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions), monkeypatch)
    out, failures = check_harness(run, record)
    assert any(f.startswith("(c')") for f in failures)


def test_a_primary_that_loses_accuracy_fails(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 5, "c2_transition_only": 5, "c2": 14, "c3": 5}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions), monkeypatch)
    _out, failures = check_harness(run, record)
    assert any(f.startswith("(c')") for f in failures)


def test_more_boundary_errors_than_off_fail_only_for_the_primary(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions, fp_extra=1), monkeypatch)
    _out, failures = check_harness(run, record)
    assert any(f.startswith("(e) c2") for f in failures)
    positions2 = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 12, "c3": 2}))
    run2, record2 = write_test_dir(tmp_path / "third", positions2, make_lines(positions2, fp_extra=1), monkeypatch, record_primary="c3")
    _out, failures = check_harness(run2, record2)
    assert not any(f.startswith("(e)") for f in failures)  # c2 exceeded off, but c2 is not primary


def test_a_line_decoded_under_a_different_stage_fails_f_prime(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}))
    lines = make_lines(positions)
    lines.loc[(lines["arm"] == "c2") & (lines["group_key"] == "TLA:sentence:3"), "stage"] = "Late Egyptian"
    run, record = write_test_dir(tmp_path, positions, lines, monkeypatch)
    _out, failures = check_harness(run, record)
    assert any(f.startswith("(f')") for f in failures)


def test_hypothetical_routing_differences_are_listed_not_gated(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions, hyp_stage="Late Egyptian"), monkeypatch)
    out, failures = check_harness(run, record)
    assert failures == []
    assert any("would-route-differently lines: 30" in line for line in out)
    assert any("would route 'Late Egyptian'" in line for line in out)


def test_a_wrong_test_manifest_fails(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions), monkeypatch)
    (run / "test_manifest_used.csv").write_text("something else\n")
    _out, failures = check_harness(run, record)
    assert any("manifest" in f for f in failures)


def test_a_record_without_a_primary_arm_stops_the_test_phase(tmp_path, monkeypatch):
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}))
    run, record = write_test_dir(tmp_path, positions, make_lines(positions), monkeypatch, record_primary=None)
    with pytest.raises(gates.InputError):
        check_harness(run, record)
    assert main(["primary", "--record", str(record)]) == 2


def test_the_mechanism_report_counts_members_predecessors_and_overlaps():
    positions = make_positions(flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 12}), members=(1, 2))
    report = mechanism_report(positions, "member1", "c2")
    # 30 rows x positions 1 and 2 are members; position 2's predecessor (position 1) is a member
    assert report["all"]["n"] == 60 and report["all"]["overlaps"] == 30 and report["overlaps_total"] == 30
    assert report["1"]["n"] == 60 and report["2-3"]["n"] == 0
    # position 0 misses for the first `misses` groups, so the predecessor of position 1 is
    # right for c2 (2 misses) and wrong for off (12 misses) in groups 2..11
    assert report["all"]["better_prev"] == 10 and report["all"]["worse_prev"] == 0
    assert report["all"]["better_i"] == 0
    assert report["all"]["own_path_vobs1"] == 60


# ---------- the dev stage ----------


def dev_dir(tmp_path, corrects, rate=0.1, sha=None):
    run = tmp_path / "dev"
    run.mkdir()
    positions = make_positions(corrects)
    positions.to_csv(run / "dev_positions.csv", index=False)
    (run / "dev_manifest_used.csv").write_text("m\n")
    counts = {
        "attempts": [{"rate": rate, "dev_positions": len(positions) // 4, "dev_members": 60, "ok": True}],
        "chosen_rate": rate, "min_dev_positions": 2000, "min_dev_members": 100,
    }
    (run / "dev_counts.json").write_text(json.dumps(counts))
    (run / "approved_commit.txt").write_text("b" * 40 + "\n")
    return run


def test_the_dev_selection_writes_the_record_and_names_the_primary(tmp_path):
    run = dev_dir(tmp_path, flags({"off": 12, "c2_transition_only": 12, "c2": 2, "c3": 8}))
    assert main(["dev", "--run-dir", str(run)]) == 0
    record = json.loads((run / "dev_record.json").read_text())
    assert record["best"] == "c2" and record["primary"] in ("c2_transition_only", "c2", "c3")
    assert record["approved_commit"] == "b" * 40 and record["dev_rate"] == 0.1
    assert record["bootstrap"] == {"seed": 20261026, "resamples": 10000, "percentiles": [2.5, 97.5]}
    assert set(record["arms"]) == set(ALL_ARMS)


def test_the_dev_selection_records_that_no_candidate_survived(tmp_path):
    run = dev_dir(tmp_path, flags({"off": 5, "c2_transition_only": 5, "c2": 6, "c3": 9}))
    assert main(["dev", "--run-dir", str(run)]) == 0
    record = json.loads((run / "dev_record.json").read_text())
    assert record["primary"] is None and record["eligible"] == []


def test_the_dev_manifest_must_be_the_pinned_one_for_its_rate(tmp_path, monkeypatch):
    run = dev_dir(tmp_path, flags({"off": 5, "c2_transition_only": 5, "c2": 6, "c3": 9}))
    _out, failures = check_dev_manifest(run)
    assert failures  # "m\n" is not the pinned manifest
    monkeypatch.setitem(gates.DEV_MANIFEST_SHA, 0.10, hashlib.sha256(b"m\n").hexdigest())
    _out, failures = check_dev_manifest(run)
    assert failures == []


def test_an_unrunnable_dev_stage_is_an_input_error(tmp_path):
    run = dev_dir(tmp_path, flags({"off": 5, "c2_transition_only": 5, "c2": 6, "c3": 9}))
    (run / "dev_counts.json").write_text(json.dumps({"attempts": [], "chosen_rate": None}))
    assert main(["dev-manifest", "--run-dir", str(run)]) == 2


# ---------- the committed record, and nothing else changed ----------


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path, primary="c2"):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "code.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "dev phase commit")
    approved = git(repo, "rev-parse", "HEAD")
    record = repo / gates.DEV_RECORD_PATH
    record.parent.mkdir(parents=True)
    record.write_text(
        json.dumps(
            {"primary": primary, "dev_manifest_sha256": gates.DEV_MANIFEST_SHA[0.10], "dev_rate": 0.1,
             "approved_commit": approved, "arms": {}, "eligible": [], "walk": []}
        )
    )
    return repo, record, approved


def test_preflight_accepts_exactly_the_record_as_the_only_change(tmp_path):
    repo, record, _approved = make_repo(tmp_path)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "dev record")
    out, failures = check_preflight(record, repo)
    assert failures == [] and any("primary arm from the dev record: c2" in line for line in out)


def test_preflight_refuses_any_other_change_after_the_dev_phase(tmp_path):
    repo, record, _approved = make_repo(tmp_path)
    (repo / "code.py").write_text("x = 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "record and a code change")
    _out, failures = check_preflight(record, repo)
    assert failures and "only change allowed" in failures[0]


def test_preflight_refuses_a_record_with_no_primary_or_a_wrong_manifest(tmp_path):
    repo, record, _approved = make_repo(tmp_path, primary=None)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "dev record")
    _out, failures = check_preflight(record, repo)
    assert failures and "no primary arm" in failures[0]
    repo2, record2, _ = make_repo(tmp_path / "two")
    data = json.loads(record2.read_text())
    data["dev_manifest_sha256"] = "0" * 64
    record2.write_text(json.dumps(data))
    git(repo2, "add", "-A")
    git(repo2, "commit", "-q", "-m", "dev record")
    _out, failures = check_preflight(record2, repo2)
    assert any("manifest" in f for f in failures)


# ---------- the expert pastes ----------


def paste_csv(path: Path, passed: list[bool], stage="Earlier Egyptian", lik="E=-1"):
    pd.DataFrame(
        [
            {"benchmark_id": f"PASTE_{i:03d}", "passed": str(p), "stage_used": stage,
             "stage_inferred": "True", "stage_likelihoods": lik}
            for i, p in enumerate(passed)
        ]
    ).to_csv(path, index=False)


def test_the_paste_rules(tmp_path):
    base, run = tmp_path / "base", tmp_path / "run"
    base.mkdir()
    run.mkdir()
    none = [False] * 5 + [True] * 3
    paste_csv(base / "paste_none.csv", none)
    for name, passed in (("auto", [True] * 8), ("declared", [True] * 8), ("none", none), ("auto_off", [True] * 8)):
        paste_csv(run / f"paste_{name}.csv", passed)
    out, failures = check_paste(run, base)
    assert failures == []
    paste_csv(run / "paste_auto.csv", [True] * 7 + [False])
    _out, failures = check_paste(run, base)
    assert any("paste auto: 7/8" in f for f in failures)
    paste_csv(run / "paste_auto.csv", [True] * 8, stage="Late Egyptian")
    _out, failures = check_paste(run, base)
    assert any("routed differently" in f for f in failures)
    paste_csv(run / "paste_auto.csv", [True] * 8)
    paste_csv(run / "paste_none.csv", [True] * 4 + [False] * 4)
    _out, failures = check_paste(run, base)
    assert any("3/8" in f for f in failures)


# ---------- the runner and the pre-registration ----------


def test_the_runner_is_valid_bash():
    subprocess.run(["bash", "-n", str(RUNNER)], check=True)


def test_the_preregistration_reproduces_the_runner_verbatim():
    """Section 8 of the pre-registration is the runner. If they drift, the registered
    commands are not the ones that run."""
    doc = DOC.read_text()
    section = doc[doc.index("## 8. Exact commands") : doc.index("## 9.")]
    blocks = re.findall(r"```bash\n(.*?)```", section, re.DOTALL)
    assert len(blocks) == 1
    assert blocks[0] == RUNNER.read_text()


def test_the_pinned_identities_agree_between_runner_checker_and_document():
    runner, doc = RUNNER.read_text(), DOC.read_text()
    for sha in (gates.TEST_MANIFEST_SHA, gates.DEV_MANIFEST_SHA[0.10], gates.DEV_MANIFEST_SHA[0.20]):
        assert sha in runner and sha in doc
    assert gates.DEV_RECORD_PATH in runner and gates.DEV_RECORD_PATH in doc
    for constant in ("20261026", "10,000", "2,000", "0.80", "0.7917"):
        assert constant in doc
    import scripts.run_transition_smoothing_eval as harness

    assert (harness.SEED, gates.SEED) == (20261026, 20261026)
    assert harness.SIMPLICITY_ORDER == gates.SIMPLICITY_ORDER
    assert tuple(a.name for a in harness.ARMS) == gates.ALL_ARMS
    assert (harness.MIN_DEV_POSITIONS, harness.MIN_DEV_MEMBERS) == (2000, 100)
    assert gates.MIN_BAND_N == 30


@pytest.mark.parametrize(
    "args",
    [(), ("dev",), ("test", "deadbeef"), ("both", "0" * 40), ("dev", "0" * 40, "extra")],
)
def test_the_runner_refuses_to_start_without_a_phase_and_one_full_approved_sha(tmp_path, args):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path), "TS_RUNS_BASE": str(tmp_path / "runs")}
    result = subprocess.run(["bash", str(RUNNER), *args], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 2
    assert "usage" in result.stderr
    assert not (tmp_path / "runs").exists()  # no attempt directory allocated


@pytest.mark.skipif(
    ROOT != REGISTERED_WT,
    reason="the runner is pinned to the registered worktree; only checkable there",
)
@pytest.mark.parametrize("phase", ["dev", "test"])
def test_the_runner_stops_when_head_is_not_the_approved_commit(tmp_path, phase):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path),
           "TS_RUNS_BASE": str(tmp_path / "runs"), "TS_STOP_AFTER": "0"}
    result = subprocess.run(["bash", str(RUNNER), phase, "0" * 40], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode != 0
    (attempt,) = (tmp_path / "runs").iterdir()
    assert attempt.name == f"transition-smoothing-2026-10-28-{phase}-attempt1"
    assert "STOP at step0-approved-commit" in (attempt / "run_log.txt").read_text()
    assert (attempt / "approved_commit.txt").read_text().strip() == "0" * 40


# ---------- the competitive sets ----------


def competitive_dir(path: Path, hits: dict, top3="0.85", mrr="0.75"):
    path.mkdir(parents=True, exist_ok=True)
    for (set_name, mode), flags_ in hits.items():
        name = f"{set_name}_{mode}_auto"
        pd.DataFrame(
            [
                {"benchmark_id": f"Q{i}", "top3_useful_family_hit": str(hit), "useful_family_rank": "1" if hit else ""}
                for i, hit in enumerate(flags_)
            ]
        ).to_csv(path / f"{name}.csv", index=False)
        (path / f"{name}.txt").write_text(
            f"Competitive ambiguity evaluation summary:\ntop3_useful_family_accuracy: {top3}\nmrr: {mrr}\n"
        )


def test_the_competitive_rule_loses_no_top3_answer_and_applies_the_floors_where_they_apply(tmp_path):
    runs = gates.COMPETITIVE_RUNS
    assert runs == (("v4", "T"), ("v4", "L"), ("holdout", "T"), ("holdout", "C"), ("le_v1", "T"), ("le_v1", "C"))
    hits = {key: [True, True, False, True] for key in runs}
    baseline, now = tmp_path / "base", tmp_path / "now"
    competitive_dir(baseline, hits, top3="0.90", mrr="0.80")
    competitive_dir(now, hits, top3="0.90", mrr="0.80")
    out, failures = gates.check_competitive(now, baseline)
    assert failures == [] and "do not exercise the decoder" in out[0]
    # one lost answer in held-out C fails; a gained one does not
    lost = dict(hits)
    lost[("holdout", "C")] = [True, False, False, True]
    competitive_dir(now, lost, top3="0.90", mrr="0.80")
    _out, failures = gates.check_competitive(now, baseline)
    assert failures == ["(g') holdout_C_auto: top-3 answers lost ['Q1']"]
    gained = dict(hits)
    gained[("le_v1", "T")] = [True, True, True, True]
    competitive_dir(now, gained, top3="0.90", mrr="0.80")
    assert gates.check_competitive(now, baseline)[1] == []
    # the floors of release_baseline.json apply to v4 only
    competitive_dir(now, hits, top3="0.70", mrr="0.60")
    _out, failures = gates.check_competitive(now, baseline)
    assert any("v4 T-auto below" in f for f in failures) and any("v4 L-auto below" in f for f in failures)
