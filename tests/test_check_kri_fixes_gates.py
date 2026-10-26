"""Tests for scripts/check_kri_fixes_gates.py and scripts/run_kri_fixes_prereg.sh.

The gate checker turns the pre-registration's rules into exit codes; the runner stops
on the first non-zero one. Both were added in review round 1 (Opus + Astra,
2026-10-26), because the earlier command list ran the evaluations and left every rule
to a reader — and the competitive evaluator exits 0 whatever its numbers are.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from scripts.check_kri_fixes_gates import (
    check_competitive,
    check_routing,
    check_verify,
    decide_pooled_fallback,
    main,
    sign_test_p as checker_sign_test_p,
)
from scripts.run_kri_fixes_eval import sign_test_p, summarise

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("all_off", "pooled_only", "discount_only", "cartouche_only", "all_on")


# ---------- harness ----------


def _harness_dir(tmp_path: Path, on_correct=(1, 1, 1), stage_on="", base_correct=(0, 1, 1)):
    """Three positions: 0 firing, 1 neighbour, 2 other. One line, unrouted in all_off."""
    classes = ("firing", "neighbour", "other")
    positions = []
    for arm in ARMS:
        correct = base_correct if arm in ("all_off", "discount_only") else on_correct
        for i in range(3):
            positions.append(dict(
                arm=arm, row_id="TLA:0", source="TLA", position=i, group="g",
                gold_reading="x", predicted="x" if correct[i] else "y",
                correct=correct[i], stage="" if arm == "all_off" else stage_on,
                used_pooled_evidence=int(i == 0 and "pooled" in arm or arm == "all_on" and i == 0),
                stage_attested_count=3, attested_count=37, confidence=0.5,
                confidence_legacy=0.6, confidence_undiscounted=0.5,
                confidence_discounted=0.4, **{"class": classes[i]},
            ))
    lines = []
    for arm in ARMS:
        correct = base_correct if arm in ("all_off", "discount_only") else on_correct
        lines.append(dict(
            arm=arm, row_id="TLA:0", source="TLA",
            stage="" if arm == "all_off" else stage_on, coverage="",
            line_exact=int(all(correct)), seg_exact=1, boundary_tp=2, boundary_fp=0,
            boundary_fn=0, boundary_fp_outside_cartouche=0,
            boundary_fn_outside_cartouche=0, cartouches=0, cartouches_split=0,
            boundaries_inside_cartouches=0,
        ))
    positions, lines = pd.DataFrame(positions), pd.DataFrame(lines)
    summary, calibration = summarise(positions, lines)
    positions.to_csv(tmp_path / "kri_positions.csv", index=False)
    lines.to_csv(tmp_path / "kri_lines.csv", index=False)
    pd.DataFrame(summary).to_csv(tmp_path / "kri_summary.csv", index=False)
    pd.DataFrame(calibration).to_csv(tmp_path / "kri_summary_calibration.csv", index=False)
    return tmp_path


def test_harness_gates_pass_and_report_the_decision(tmp_path, capsys):
    run_dir = _harness_dir(tmp_path)
    assert main(["harness", "--run-dir", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "DECISION: SHIP AS UNVALIDATED HEURISTIC" in out
    assert "TLA:0#0" in out  # the firing position is listed individually
    assert "discount effect" in out


def test_an_unrouted_line_survives_the_csv_round_trip_as_unmoved(tmp_path, capsys):
    """A blank stage read back with default NaN handling is NaN != NaN, a fake move.
    The checker reads with keep_default_na=False and reconciles against the summary."""
    run_dir = _harness_dir(tmp_path, stage_on="")
    assert main(["harness", "--run-dir", str(run_dir)]) == 0
    assert "(d) all_on: lines whose stage moved: 0" in capsys.readouterr().out


def test_a_listing_that_disagrees_with_the_summary_stops_the_run(tmp_path, capsys):
    run_dir = _harness_dir(tmp_path, stage_on="Late Egyptian")
    summary = pd.read_csv(run_dir / "kri_summary.csv", keep_default_na=False)
    summary.loc[summary["arm"] == "all_on", "stage_changed_vs_baseline"] = 0
    summary.to_csv(run_dir / "kri_summary.csv", index=False)
    assert main(["harness", "--run-dir", str(run_dir)]) == 2


def test_collateral_loss_beyond_the_neighbour_budget_fails_rule_a(tmp_path, capsys):
    # Fixture has one neighbour; widen it so a net loss of 3 > budget 2 is possible.
    rows = []
    for arm in ARMS:
        base = arm in ("all_off", "discount_only")
        for i in range(4):
            cohort = "firing" if i == 0 else "neighbour"
            correct = 1 if (base or i == 0) else 0
            rows.append(dict(arm=arm, row_id="TLA:0", source="TLA", position=i,
                             group="g", gold_reading="x", predicted="x" if correct else "y",
                             correct=correct, stage="", used_pooled_evidence=0,
                             stage_attested_count=0, attested_count=0, confidence=0.5,
                             confidence_legacy=0.5, confidence_undiscounted=0.5,
                             confidence_discounted=0.5, **{"class": cohort}))
    positions = pd.DataFrame(rows)
    lines = pd.DataFrame([dict(arm=a, row_id="TLA:0", source="TLA", stage="", coverage="",
                               line_exact=0, seg_exact=1, boundary_tp=0, boundary_fp=0,
                               boundary_fn=0, boundary_fp_outside_cartouche=0,
                               boundary_fn_outside_cartouche=0, cartouches=0,
                               cartouches_split=0, boundaries_inside_cartouches=0)
                          for a in ARMS])
    summary, calibration = summarise(positions, lines)
    positions.to_csv(tmp_path / "kri_positions.csv", index=False)
    lines.to_csv(tmp_path / "kri_lines.csv", index=False)
    pd.DataFrame(summary).to_csv(tmp_path / "kri_summary.csv", index=False)
    pd.DataFrame(calibration).to_csv(tmp_path / "kri_summary_calibration.csv", index=False)
    assert main(["harness", "--run-dir", str(tmp_path)]) == 1
    assert "FAIL (a) all_on neighbour: net loss 3 > 2" in capsys.readouterr().out


def test_cohorts_that_differ_between_arms_cannot_be_judged(tmp_path):
    run_dir = _harness_dir(tmp_path)
    positions = pd.read_csv(run_dir / "kri_positions.csv", keep_default_na=False)
    positions.loc[(positions["arm"] == "all_off") & (positions["position"] == 0), "class"] = "other"
    positions.to_csv(run_dir / "kri_positions.csv", index=False)
    assert main(["harness", "--run-dir", str(run_dir)]) == 2


@pytest.mark.parametrize(
    "n, lines, better, worse, line_better, line_worse, expected",
    [
        (0, 0, 0, 0, 0, 0, "NOT EXERCISED"),
        (20, 20, 3, 5, 3, 5, "DISABLE"),
        (500, 100, 10, 11, 10, 11, "DISABLE"),
        (20, 20, 10, 0, 10, 0, "SHIP AS UNVALIDATED"),  # low n: no claim
        (40, 10, 30, 0, 10, 0, "SHIP AS UNVALIDATED"),  # too few distinct lines
        (40, 30, 12, 8, 12, 8, "SHIP AS UNVALIDATED"),  # not significant
        (39, 20, 20, 0, 1, 0, "SHIP AS UNVALIDATED"),  # all gains in one line
        (40, 30, 20, 2, 18, 2, "SHIP, IMPROVEMENT MAY BE STATED"),
    ],
)
def test_rule_b_decides_shipping_on_harm_and_claims_on_evidence(
    n, lines, better, worse, line_better, line_worse, expected
):
    assert decide_pooled_fallback(
        n, lines, better, worse, line_better, line_worse
    ).startswith(expected)


def test_the_checker_sign_test_is_the_harness_sign_test():
    for better in range(0, 12):
        for worse in range(0, 12):
            assert checker_sign_test_p(better, worse) == sign_test_p(better, worse)


def _write_harness(tmp_path: Path, positions: pd.DataFrame, lines: pd.DataFrame) -> Path:
    summary, calibration = summarise(positions, lines)
    positions.to_csv(tmp_path / "kri_positions.csv", index=False)
    lines.to_csv(tmp_path / "kri_lines.csv", index=False)
    pd.DataFrame(summary).to_csv(tmp_path / "kri_summary.csv", index=False)
    pd.DataFrame(calibration).to_csv(tmp_path / "kri_summary_calibration.csv", index=False)
    return tmp_path


def test_gains_clustered_in_one_line_do_not_license_an_improvement_claim(tmp_path, capsys):
    """Astra, round 2: 20 gains in one line plus 19 unchanged firing lines gave a
    position-level p of 2e-6 and 'IMPROVEMENT MAY BE STATED'. The claim is now tested
    over lines: 1 better line, 0 worse, p = 1.0."""
    layout = [("TLA:0", i, True) for i in range(20)] + [
        (f"TLA:{k}", 0, False) for k in range(1, 20)
    ]
    rows, line_rows = [], []
    for arm in ARMS:
        base = arm in ("all_off", "discount_only")
        for row_id, position, gains in layout:
            correct = 0 if (base and gains) else 1
            rows.append(dict(arm=arm, row_id=row_id, source="TLA", position=position,
                             group="g", gold_reading="x", predicted="x" if correct else "y",
                             correct=correct, stage="", used_pooled_evidence=0,
                             stage_attested_count=3, attested_count=37, confidence=0.5,
                             confidence_legacy=0.5, confidence_undiscounted=0.5,
                             confidence_discounted=0.5, **{"class": "firing"}))
        for k in range(20):
            line_rows.append(dict(arm=arm, row_id=f"TLA:{k}", source="TLA", stage="",
                                  coverage="", line_exact=int(not (base and k == 0)),
                                  seg_exact=1, boundary_tp=0, boundary_fp=0, boundary_fn=0,
                                  boundary_fp_outside_cartouche=0,
                                  boundary_fn_outside_cartouche=0, cartouches=0,
                                  cartouches_split=0, boundaries_inside_cartouches=0))
    run_dir = _write_harness(tmp_path, pd.DataFrame(rows), pd.DataFrame(line_rows))
    assert main(["harness", "--run-dir", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "n=39 in 20 lines, on-better=20 off-better=0" in out
    assert "firing lines: on-better=1 off-better=0 tied=19 line sign-test p=1" in out
    assert "IMPROVEMENT MAY BE STATED" not in out
    assert "DECISION: SHIP AS UNVALIDATED HEURISTIC" in out


# ---------- paste ----------


def test_paste_needs_eight_of_eight_in_both_modes(tmp_path, capsys):
    for mode in ("auto", "declared"):
        pd.DataFrame({"passed": [True] * 8}).to_csv(tmp_path / f"paste_{mode}.csv", index=False)
    assert main(["paste", "--run-dir", str(tmp_path)]) == 0
    pd.DataFrame({"passed": [True] * 7 + [False]}).to_csv(tmp_path / "paste_declared.csv", index=False)
    assert main(["paste", "--run-dir", str(tmp_path)]) == 1


# ---------- competitive ----------


SUMMARY_TXT = """Competitive ambiguity evaluation summary:
corpus_rows: 130472
top3_useful_family_accuracy: {top3}
mrr: {mrr}
failures: {fails}
"""


def _competitive_dir(path: Path, hits: dict[str, bool], top3=0.85, mrr=0.75, fails=3):
    path.mkdir(parents=True, exist_ok=True)
    for s in ("v4", "holdout", "le_v1"):
        for m in ("T", "L"):
            pd.DataFrame({
                "benchmark_id": list(hits),
                "top3_useful_family_hit": list(hits.values()),
                "useful_family_rank": ["1" if h else "" for h in hits.values()],
            }).to_csv(path / f"{s}_{m}_auto.csv", index=False)
            (path / f"{s}_{m}_auto.txt").write_text(
                SUMMARY_TXT.format(top3=top3, mrr=mrr, fails=fails)
            )
    return path


def _release(tmp_path: Path) -> Path:
    path = tmp_path / "release.json"
    path.write_text(json.dumps({"twin_controlled": {"top3_useful_floor": 0.8, "mrr_floor": 0.7}}))
    return path


def test_competitive_passes_when_no_answer_is_lost(tmp_path):
    base = _competitive_dir(tmp_path / "base", {"Q1": True, "Q2": False})
    run = _competitive_dir(tmp_path / "run", {"Q1": True, "Q2": True})
    _out, failures = check_competitive(run, base, _release(tmp_path))
    assert failures == []


def test_competitive_fails_on_a_lost_query_even_if_the_aggregate_is_unchanged(tmp_path):
    # Q1 lost and Q2 gained: same accuracy, but a lost answer by identity.
    base = _competitive_dir(tmp_path / "base", {"Q1": True, "Q2": False})
    run = _competitive_dir(tmp_path / "run", {"Q1": False, "Q2": True})
    _out, failures = check_competitive(run, base, _release(tmp_path))
    assert any("lost ['Q1']" in f for f in failures)


def test_competitive_applies_the_release_floors_to_v4_t_only(tmp_path):
    base = _competitive_dir(tmp_path / "base", {"Q1": True})
    run = _competitive_dir(tmp_path / "run", {"Q1": True}, top3=0.75, mrr=0.6667)
    _out, failures = check_competitive(run, base, _release(tmp_path))
    assert failures == ["(f) v4 T-auto below the release floors"]


# ---------- routing ----------


def _routing(path: Path, stages: list[str], ids: list[str]):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"source": "TLA", "source_text_id": ids, "source_sentence_id": "S",
                  "chosen_stage": stages}).to_csv(path / "routing.csv", index=False)


def test_routing_lists_changed_choices_and_rejects_a_different_sample(tmp_path):
    _routing(tmp_path / "base", ["Earlier Egyptian", ""], ["a", "b"])
    _routing(tmp_path / "run", ["Late Egyptian", ""], ["a", "b"])
    out, failures = check_routing(tmp_path / "run", tmp_path / "base")
    assert failures == []
    assert any("changed against attempt 2: 1" in line for line in out)
    _routing(tmp_path / "run", ["Late Egyptian", ""], ["a", "c"])
    _out, failures = check_routing(tmp_path / "run", tmp_path / "base")
    assert failures


# ---------- verify ----------


def test_verify_requires_verify_release_to_reproduce_steps_seven_and_four(tmp_path):
    (tmp_path / "v4_L_auto.txt").write_text(SUMMARY_TXT.format(top3=0.9, mrr=0.8, fails=2))
    (tmp_path / "v4_T_auto.txt").write_text(SUMMARY_TXT.format(top3=0.85, mrr=0.75, fails=3))
    (tmp_path / "paste_auto.txt").write_text("...\npassed 8/8\n")
    verify = (
        "=== competitive ambiguity eval, LEGACY pool - x ===\n"
        + SUMMARY_TXT.format(top3=0.9, mrr=0.8, fails=2)
        + "=== competitive ambiguity eval, TWIN-CONTROLLED pool - x ===\n"
        + SUMMARY_TXT.format(top3=0.85, mrr=0.75, fails=3)
        + "=== expert paste eval ===\npassed 8/8\n"
    )
    (tmp_path / "verify_release.txt").write_text(verify)
    _out, failures = check_verify(tmp_path)
    assert failures == []
    (tmp_path / "verify_release.txt").write_text(verify.replace("mrr: 0.75", "mrr: 0.7"))
    _out, failures = check_verify(tmp_path)
    assert failures and "v4_T_auto.txt" in failures[0]


# ---------- the runner and the pre-registration ----------


def test_the_runner_is_valid_bash():
    script = ROOT / "scripts" / "run_kri_fixes_prereg.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_the_preregistration_reproduces_the_runner_verbatim():
    """§5 of the pre-registration is the runner. If they drift, the registered
    commands are not the ones that run."""
    doc = (ROOT / "docs" / "kri-fixes-preregistration-2026-10-26.md").read_text()
    section = doc[doc.index("## 5. Exact commands"): doc.index("## 6.")]
    blocks = re.findall(r"```bash\n(.*?)```", section, re.DOTALL)
    assert len(blocks) == 1
    script = (ROOT / "scripts" / "run_kri_fixes_prereg.sh").read_text()
    assert blocks[0] == script


RUNNER = ROOT / "scripts" / "run_kri_fixes_prereg.sh"
REGISTERED_WT = Path(
    "/Users/lediodurmishaj/projects/Egyptology-APP/.claude/worktrees/kri-fixes-2026-10-26"
)


def _run_runner(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path),
           "KRI_RUNS_BASE": str(tmp_path / "runs"), "KRI_STOP_AFTER": "0"}
    return subprocess.run(["bash", str(RUNNER), *args], env=env, capture_output=True,
                          text=True, timeout=120)


@pytest.mark.parametrize("args", [(), ("deadbeef",), ("0" * 40, "extra")])
def test_the_runner_refuses_to_start_without_one_full_approved_sha(tmp_path, args):
    """Round 2 (Astra): the runner must be told which commit was approved."""
    result = _run_runner(tmp_path, *args)
    assert result.returncode == 2
    assert "usage" in result.stderr
    assert not (tmp_path / "runs").exists()  # no attempt directory allocated


@pytest.mark.skipif(
    ROOT != REGISTERED_WT,
    reason="the runner is pinned to the registered worktree; only checkable there",
)
def test_the_runner_stops_when_head_is_not_the_approved_commit(tmp_path):
    """Round 2 (Astra): a different clean commit on the branch must not pass step 0."""
    result = _run_runner(tmp_path, "0" * 40)
    assert result.returncode != 0
    (attempt,) = (tmp_path / "runs").iterdir()
    log = (attempt / "run_log.txt").read_text()
    assert "STOP at step0-approved-commit" in log
    assert (attempt / "approved_commit.txt").read_text().strip() == "0" * 40
