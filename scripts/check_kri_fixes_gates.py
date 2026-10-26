"""Evaluate the gates of docs/kri-fixes-preregistration-2026-10-26.md on a run directory.

Review fix (Opus + Astra, 2026-10-26): the pre-registration's command list used to run
the evaluations and leave the rules to be read off by hand. Several evaluators exit 0
whatever their numbers are (the competitive one always does), so "stop on any failure"
was a comment, not a mechanism. This script turns each rule into a check with an exit
code, so `scripts/run_kri_fixes_prereg.sh` (bash, `set -e`, a `run` wrapper that stops
on the first non-zero exit) can stop the run where the rule says it stops.

Subcommands, one per step of §5:

  harness      rules (a), (b), (c), (d) and (g) on the paired harness outputs
  paste        rule (e): 8/8 in auto and in declared
  routing      rule (e3): the routing sample is the attempt-2 sample, changes listed
  competitive  rule (f): zero top-3 answers lost by query identity, v4 T floors
  verify       rule (f): verify_release.py reproduces the step-7 aggregates exactly

Exit 0 = every gated rule in that subcommand passed; 1 = a gated rule failed (the
reason is printed as a line starting `FAIL`); 2 = the inputs are not what the rule
needs (a missing file, a count that does not reconcile) — also a stop.

Every CSV is read with `keep_default_na=False`, so a blank stage stays "" and never
becomes NaN (NaN != NaN would list every unrouted line as "moved").

The numbers below are the pre-registered budgets. They are fixed here and in §4 of
the pre-registration together; changing either needs a dated addendum.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

BASELINE_ARM = "all_off"
# Arms the "nothing else broke" gates (a) and (c) are applied to: the shipping
# configuration if rule (b) keeps the pooled fallback (all_on), and the one that ships
# if (b) disables it (cartouche_only; the discount moves no prediction, so its
# predictions are the shipped ones either way).
GATED_ARMS = ("all_on", "cartouche_only")
DECISION_ARM = "all_on"

# Rule (a): engineering loss budgets, net positions/lines lost against all_off.
OTHER_NET_LOSS_BUDGET = 5
NEIGHBOUR_NET_LOSS_BUDGET = 2
LINE_NET_LOSS_BUDGET = 3
# Rule (b): when an improvement may be *claimed* (it never decides shipping).
CLAIM_MIN_FIRING_POSITIONS = 30
CLAIM_MIN_FIRING_LINES = 20
CLAIM_MAX_SIGN_TEST_P = 0.05

COMPETITIVE_SETS = ("v4", "holdout", "le_v1")
COMPETITIVE_MODES = ("T", "L")
PASTE_MODES = ("auto", "declared")
EXPECTED_PASTES = 8
RELEASE_BASELINE = PROJECT_ROOT / "data" / "benchmarks" / "release_baseline.json"


class InputError(Exception):
    """The inputs cannot be judged (exit 2)."""


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise InputError(f"missing input: {path}")
    return pd.read_csv(path, keep_default_na=False, dtype=str)


def as_int(value) -> int:
    return int(float(value))


def as_float(value) -> "float | None":
    return None if value in ("", None) else float(value)


def truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# harness: rules (a), (b), (c), (d), (g)
# ---------------------------------------------------------------------------


def _summary_by_arm(summary: pd.DataFrame) -> dict[str, dict]:
    rows = summary[summary["scope"] == "all"]
    return {row["arm"]: row for row in rows.to_dict("records")}


def _recount_cohort(positions: pd.DataFrame, arm: str, cohort: str) -> tuple[int, int, int]:
    """(n, better, worse) for one arm and cohort, recomputed from the position rows."""
    base = positions[positions["arm"] == BASELINE_ARM].set_index(["row_id", "position"])
    part = positions[(positions["arm"] == arm) & (positions["class"] == cohort)]
    better = worse = 0
    for row in part.to_dict("records"):
        key = (row["row_id"], row["position"])
        if key not in base.index:
            raise InputError(f"{arm} position {key} has no {BASELINE_ARM} partner")
        base_correct = as_int(base.loc[key, "correct"])
        correct = as_int(row["correct"])
        better += int(correct == 1 and base_correct == 0)
        worse += int(correct == 0 and base_correct == 1)
    return len(part), better, worse


def check_harness(run_dir: Path) -> tuple[list[str], list[str]]:
    """Returns (report lines, failure reasons)."""
    summary = read_csv(run_dir / "kri_summary.csv")
    positions = read_csv(run_dir / "kri_positions.csv")
    lines = read_csv(run_dir / "kri_lines.csv")
    calibration = read_csv(run_dir / "kri_summary_calibration.csv")
    by_arm = _summary_by_arm(summary)
    out: list[str] = []
    failures: list[str] = []
    for arm in (BASELINE_ARM, DECISION_ARM, *GATED_ARMS):
        if arm not in by_arm:
            raise InputError(f"summary has no '{arm}' row")

    # Cohorts must be the same positions in every arm, or nothing below is paired.
    cohort_sets = {
        arm: frozenset(
            zip(part["row_id"], part["position"], part["class"])
        )
        for arm, part in positions.groupby("arm")
    }
    if len(set(cohort_sets.values())) != 1:
        raise InputError("position cohorts differ between arms; nothing can be paired")

    # Reconcile the summary with the position rows (the listing must agree with it).
    for arm in (DECISION_ARM, *GATED_ARMS):
        for cohort in ("firing", "neighbour", "other"):
            n, better, worse = _recount_cohort(positions, arm, cohort)
            row = by_arm[arm]
            recorded = (
                as_int(row[f"{cohort}_positions"]),
                as_int(row[f"{cohort}_better"]),
                as_int(row[f"{cohort}_worse"]),
            )
            if (n, better, worse) != recorded:
                raise InputError(
                    f"{arm}/{cohort}: positions file gives n/better/worse "
                    f"{(n, better, worse)}, summary says {recorded}"
                )

    # (a) collateral loss budgets.
    out.append("(a) collateral losses against all_off (net = worse - better)")
    for arm in GATED_ARMS:
        row = by_arm[arm]
        for cohort, budget in (
            ("other", OTHER_NET_LOSS_BUDGET),
            ("neighbour", NEIGHBOUR_NET_LOSS_BUDGET),
        ):
            better = as_int(row[f"{cohort}_better"])
            worse = as_int(row[f"{cohort}_worse"])
            net = worse - better
            verdict = "PASS" if net <= budget else "FAIL"
            out.append(
                f"  {arm:>14} {cohort:>9}: n={as_int(row[f'{cohort}_positions'])} "
                f"better={better} worse={worse} net={net} budget={budget} "
                f"sign-test p={row[f'{cohort}_sign_test_p'] or 'n/a'}  {verdict}"
            )
            if verdict == "FAIL":
                failures.append(f"(a) {arm} {cohort}: net loss {net} > {budget}")
        gained = as_int(row["lines_exact_gained"])
        lost = as_int(row["lines_exact_lost"])
        net = lost - gained
        verdict = "PASS" if net <= LINE_NET_LOSS_BUDGET else "FAIL"
        out.append(
            f"  {arm:>14}     lines: exact gained={gained} lost={lost} net={net} "
            f"budget={LINE_NET_LOSS_BUDGET}  {verdict}"
        )
        if verdict == "FAIL":
            failures.append(f"(a) {arm} whole lines: net loss {net} > {LINE_NET_LOSS_BUDGET}")

    # (b) firing positions: a decision, never a stop.
    row = by_arm[DECISION_ARM]
    n = as_int(row["firing_positions"])
    n_lines = as_int(row["firing_lines"])
    better = as_int(row["firing_better"])
    worse = as_int(row["firing_worse"])
    p = as_float(row["firing_sign_test_p"])
    out.append(
        f"(b) firing positions ({DECISION_ARM} vs all_off): n={n} in {n_lines} lines, "
        f"on-better={better} off-better={worse} unchanged={n - better - worse} "
        f"sign-test p={'n/a' if p is None else f'{p:.4g}'}"
    )
    out.append(f"    DECISION: {decide_pooled_fallback(n, n_lines, better, worse, p)}")
    base = positions[positions["arm"] == BASELINE_ARM].set_index(["row_id", "position"])
    firing = positions[(positions["arm"] == DECISION_ARM) & (positions["class"] == "firing")]
    for rec in firing.to_dict("records"):
        off = base.loc[(rec["row_id"], rec["position"])]
        out.append(
            f"    {rec['row_id']}#{rec['position']} stage={rec['stage']!r} "
            f"gold={rec['gold_reading']!r} off={off['predicted']!r}({off['correct']}) "
            f"on={rec['predicted']!r}({rec['correct']}) fired_here={rec['used_pooled_evidence']} "
            f"stage_count={rec['stage_attested_count']} pooled_count={rec['attested_count']}"
        )
    sources = summary[(summary["arm"] == DECISION_ARM) & (summary["scope"] != "all")]
    for rec in sources.to_dict("records"):
        out.append(
            f"    {rec['scope']}: firing n={rec['firing_positions']} "
            f"+{rec['firing_better']}/-{rec['firing_worse']}; other "
            f"+{rec['other_better']}/-{rec['other_worse']} (reported only)"
        )

    # (c) no new boundary errors outside cartouches.
    base_errors = as_int(by_arm[BASELINE_ARM]["boundary_errors_outside_cartouche"])
    for arm in GATED_ARMS:
        errors = as_int(by_arm[arm]["boundary_errors_outside_cartouche"])
        verdict = "PASS" if errors <= base_errors else "FAIL"
        row = by_arm[arm]
        out.append(
            f"(c) {arm}: boundary errors outside cartouches {errors} vs all_off "
            f"{base_errors}  {verdict}  (reported: F1 {row['boundary_f1']}, seg_exact "
            f"{row['seg_exact']}, cartouches split {row['cartouches_split']} of "
            f"{row['cartouches']}, boundaries inside cartouches "
            f"{row['boundaries_inside_cartouches']})"
        )
        if verdict == "FAIL":
            failures.append(f"(c) {arm}: {errors} > {base_errors}")

    # (d) every stage move listed, and the listing agrees with the summary.
    off_lines = lines[lines["arm"] == BASELINE_ARM].set_index("row_id")
    for arm in by_arm:
        if arm == BASELINE_ARM:
            continue
        arm_lines = lines[lines["arm"] == arm].set_index("row_id")
        moved = [
            row_id
            for row_id in arm_lines.index
            if off_lines.loc[row_id, "stage"] != arm_lines.loc[row_id, "stage"]
        ]
        recorded = as_int(by_arm[arm]["stage_changed_vs_baseline"])
        if len(moved) != recorded:
            raise InputError(
                f"(d) {arm}: {len(moved)} moved lines listed, summary says {recorded}"
            )
        out.append(f"(d) {arm}: lines whose stage moved: {len(moved)}")
        for row_id in moved:
            out.append(
                f"    {row_id}: {off_lines.loc[row_id, 'stage']!r} -> "
                f"{arm_lines.loc[row_id, 'stage']!r} | coverage off "
                f"{off_lines.loc[row_id, 'coverage']} | on {arm_lines.loc[row_id, 'coverage']}"
            )

    # (g) calibration, reported only.
    out.extend(calibration_report(calibration))
    return out, failures


def decide_pooled_fallback(
    n: int, n_lines: int, better: int, worse: int, p: "float | None"
) -> str:
    """Rule (b), as pre-registered. Shipping is decided on harm; claims on evidence."""
    if n == 0:
        return (
            "NOT EXERCISED - no firing position; ships as an unvalidated heuristic, "
            "its effect is unmeasured and no claim may be made"
        )
    if worse > better:
        return (
            "DISABLE - off-better exceeds on-better; use_pooled_fallback must default "
            "to off before merge"
        )
    if (
        n >= CLAIM_MIN_FIRING_POSITIONS
        and n_lines >= CLAIM_MIN_FIRING_LINES
        and better > worse
        and p is not None
        and p < CLAIM_MAX_SIGN_TEST_P
    ):
        return "SHIP, IMPROVEMENT MAY BE STATED - with the paired counts and p"
    return (
        "SHIP AS UNVALIDATED HEURISTIC - no harm measured, but no improvement may be "
        "claimed (low n, too few lines, or p >= 0.05)"
    )


def _brier(calibration: pd.DataFrame, arm: str, kind: str, subset: str) -> "float | None":
    part = calibration[
        (calibration["arm"] == arm)
        & (calibration["confidence_kind"] == kind)
        & (calibration["subset"] == subset)
    ]
    return None if part.empty else float(part["brier"].iloc[0])


def calibration_report(calibration: pd.DataFrame) -> list[str]:
    out = ["(g) calibration, reported only (Brier; lower is better)"]
    pairs = (
        ("pre-branch confidence", BASELINE_ARM, "legacy"),
        ("corrected, undiscounted", BASELINE_ARM, "undiscounted"),
        ("corrected + /k (discount_only)", "discount_only", "discounted"),
        ("all_on, shipped confidence", "all_on", "discounted"),
    )
    for subset in ("all", "with_reading"):
        values = {label: _brier(calibration, arm, kind, subset) for label, arm, kind in pairs}
        out.append(f"  subset={subset}: " + "; ".join(
            f"{label} {'n/a' if v is None else f'{v:.5f}'}" for label, v in values.items()
        ))

        def delta(a: str, b: str) -> str:
            if values[a] is None or values[b] is None:
                return "n/a"
            return f"{values[b] - values[a]:+.5f}"

        out.append(
            f"    discount effect (discount_only discounted - all_off undiscounted): "
            f"{delta('corrected, undiscounted', 'corrected + /k (discount_only)')}"
        )
        out.append(
            f"    correction effect (all_off undiscounted - all_off legacy): "
            f"{delta('pre-branch confidence', 'corrected, undiscounted')}"
        )
        out.append(
            f"    combined (all_on shipped - all_off legacy): "
            f"{delta('pre-branch confidence', 'all_on, shipped confidence')}"
        )
    return out


# ---------------------------------------------------------------------------
# paste: rule (e)
# ---------------------------------------------------------------------------


def check_paste(run_dir: Path) -> tuple[list[str], list[str]]:
    out: list[str] = []
    failures: list[str] = []
    for mode in PASTE_MODES:
        frame = read_csv(run_dir / f"paste_{mode}.csv")
        passed = sum(truthy(v) for v in frame["passed"])
        verdict = "PASS" if passed == EXPECTED_PASTES == len(frame) else "FAIL"
        out.append(f"(e) paste {mode}: {passed}/{len(frame)}  {verdict}")
        if verdict == "FAIL":
            failures.append(f"(e) paste {mode}: {passed}/{len(frame)}")
    return out, failures


# ---------------------------------------------------------------------------
# routing: rule (e3)
# ---------------------------------------------------------------------------

ROUTING_KEY = ("source", "source_text_id", "source_sentence_id")


def check_routing(run_dir: Path, baseline_dir: Path) -> tuple[list[str], list[str]]:
    now = read_csv(run_dir / "routing.csv")
    then = read_csv(baseline_dir / "routing.csv")
    key_now = [tuple(r) for r in now[list(ROUTING_KEY)].itertuples(index=False)]
    key_then = [tuple(r) for r in then[list(ROUTING_KEY)].itertuples(index=False)]
    out: list[str] = []
    failures: list[str] = []
    if sorted(key_now) != sorted(key_then):
        failures.append("(e3) the routing sample differs from attempt 2's; not comparable")
        return out, failures
    then_by_key = dict(zip(key_then, then["chosen_stage"]))
    changed = [
        (key, then_by_key[key], stage)
        for key, stage in zip(key_now, now["chosen_stage"])
        if then_by_key[key] != stage
    ]
    out.append(f"(e3) routing sample identical to attempt 2 ({len(key_now)} pastes)")
    out.append(f"(e3) chosen stage changed against attempt 2: {len(changed)} (listed, not gated)")
    for key, before, after in changed:
        out.append(f"    {':'.join(key)}: {before!r} -> {after!r}")
    return out, failures


# ---------------------------------------------------------------------------
# competitive: rule (f)
# ---------------------------------------------------------------------------


def parse_summary_block(text: str) -> dict[str, str]:
    """`key: value` lines of one 'Competitive ambiguity evaluation summary' block."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^([a-z0-9_]+): (.*)$", line.strip())
        if match and match.group(1) not in values:
            values[match.group(1)] = match.group(2).strip()
    return values


def check_competitive(
    run_dir: Path, baseline_dir: Path, release_baseline: Path = RELEASE_BASELINE
) -> tuple[list[str], list[str]]:
    out: list[str] = []
    failures: list[str] = []
    for set_name in COMPETITIVE_SETS:
        for mode in COMPETITIVE_MODES:
            name = f"{set_name}_{mode}_auto"
            now = read_csv(run_dir / f"{name}.csv")
            then = read_csv(baseline_dir / f"{name}.csv")
            if sorted(now["benchmark_id"]) != sorted(then["benchmark_id"]):
                failures.append(f"(f) {name}: query ids differ from attempt 2")
                continue
            hit_then = dict(zip(then["benchmark_id"], map(truthy, then["top3_useful_family_hit"])))
            rank_then = dict(zip(then["benchmark_id"], then["useful_family_rank"]))
            lost = [q for q, h in zip(now["benchmark_id"], now["top3_useful_family_hit"])
                    if hit_then[q] and not truthy(h)]
            gained = [q for q, h in zip(now["benchmark_id"], now["top3_useful_family_hit"])
                      if not hit_then[q] and truthy(h)]
            moved = [(q, rank_then[q], r) for q, r in zip(now["benchmark_id"], now["useful_family_rank"])
                     if rank_then[q] != r]
            s_now = parse_summary_block((run_dir / f"{name}.txt").read_text())
            s_then = parse_summary_block((baseline_dir / f"{name}.txt").read_text())
            verdict = "PASS" if not lost else "FAIL"
            out.append(
                f"(f) {name}: top-3 {s_then.get('top3_useful_family_accuracy')} -> "
                f"{s_now.get('top3_useful_family_accuracy')}, MRR {s_then.get('mrr')} -> "
                f"{s_now.get('mrr')}; lost {lost or 'none'}, gained {gained or 'none'}  {verdict}"
            )
            for q, before, after in moved:
                out.append(f"    {q}: useful rank {before or 'miss'} -> {after or 'miss'}")
            if lost:
                failures.append(f"(f) {name}: top-3 answers lost {lost}")
    twin = json.loads(release_baseline.read_text())["twin_controlled"]
    s_v4 = parse_summary_block((run_dir / "v4_T_auto.txt").read_text())
    top3 = float(s_v4["top3_useful_family_accuracy"])
    mrr = float(s_v4["mrr"])
    verdict = (
        "PASS"
        if top3 >= float(twin["top3_useful_floor"]) and mrr >= float(twin["mrr_floor"])
        else "FAIL"
    )
    out.append(
        f"(f) v4 T-auto release floors: top-3 {top3} >= {twin['top3_useful_floor']}, "
        f"MRR {mrr} >= {twin['mrr_floor']}  {verdict}"
    )
    if verdict == "FAIL":
        failures.append("(f) v4 T-auto below the release floors")
    return out, failures


# ---------------------------------------------------------------------------
# verify: verify_release.py must reproduce step 7
# ---------------------------------------------------------------------------

VERIFY_KEYS = ("top3_useful_family_accuracy", "mrr", "failures")


def _section(text: str, header: str) -> str:
    start = text.find(header)
    if start < 0:
        raise InputError(f"verify_release output has no section '{header}'")
    end = text.find("\n=== ", start + len(header))
    return text[start: end if end >= 0 else len(text)]


def _passed_line(text: str) -> str:
    match = re.search(r"^passed (\d+/\d+)", text, re.MULTILINE)
    if not match:
        raise InputError("no 'passed N/M' line")
    return match.group(1)


def check_verify(run_dir: Path) -> tuple[list[str], list[str]]:
    text = (run_dir / "verify_release.txt").read_text()
    out: list[str] = []
    failures: list[str] = []
    for header, step_file in (
        ("=== competitive ambiguity eval, LEGACY pool", "v4_L_auto.txt"),
        ("=== competitive ambiguity eval, TWIN-CONTROLLED pool", "v4_T_auto.txt"),
    ):
        mine = parse_summary_block(_section(text, header))
        step = parse_summary_block((run_dir / step_file).read_text())
        pairs = {k: (mine.get(k), step.get(k)) for k in VERIFY_KEYS}
        same = all(a is not None and a == b for a, b in pairs.values())
        out.append(f"(f) verify_release {header.split(',')[1].strip()} vs {step_file}: "
                   f"{pairs}  {'SAME' if same else 'DIFFERENT'}")
        if not same:
            failures.append(f"(f) determinism: verify_release differs from {step_file}")
    mine = _passed_line(_section(text, "=== expert paste eval ==="))
    step = _passed_line((run_dir / "paste_auto.txt").read_text())
    same = mine == step
    out.append(f"(f) verify_release paste {mine} vs paste_auto {step}  {'SAME' if same else 'DIFFERENT'}")
    if not same:
        failures.append("(f) determinism: verify_release paste differs from paste_auto")
    return out, failures


# ---------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("check", choices=("harness", "paste", "routing", "competitive", "verify"))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--baseline-dir", default="", help="attempt-2 run directory")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir).expanduser()
    baseline_dir = Path(args.baseline_dir).expanduser() if args.baseline_dir else None
    try:
        if args.check in ("routing", "competitive") and baseline_dir is None:
            raise InputError(f"{args.check} needs --baseline-dir")
        if args.check == "harness":
            out, failures = check_harness(run_dir)
        elif args.check == "paste":
            out, failures = check_paste(run_dir)
        elif args.check == "routing":
            out, failures = check_routing(run_dir, baseline_dir)
        elif args.check == "competitive":
            out, failures = check_competitive(run_dir, baseline_dir)
        else:
            out, failures = check_verify(run_dir)
    except InputError as error:
        print(f"STOP (inputs): {error}")
        return 2
    print("\n".join(out))
    for reason in failures:
        print(f"FAIL {reason}")
    print(f"{args.check}: {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
