"""Apply the rules of docs/transition-smoothing-preregistration-2026-10-28.md to a run directory.

The harness (`scripts/run_transition_smoothing_eval.py`) only produces numbers. This script
turns the pre-registered rules into exit codes, so `scripts/run_transition_smoothing_prereg.sh`
(bash, `set -e`, a `run` wrapper that stops on the first non-zero exit) stops where the
rule says it stops. Subcommands, one per step of section 8:

  dev-manifest   dev phase: the dev manifest that was used is the pinned one for its rate
  dev            dev phase: R7 selection (eligibility, best arm, walk, primary arm) ->
                 `dev_record.json`. Exit 0 whether or not a primary arm exists; "no
                 candidate survived dev" is a result, not a fault.
  primary        test phase: print the primary arm of the committed dev record
  preflight      test phase: the committed dev record is valid, names a primary arm, and
                 is the ONLY change between the dev-phase approved commit and HEAD
  harness        test phase: rules (c'), (d'), (e), (f'), (h), (i)
  paste          rules (a) and (f') on the expert pastes
  competitive    rule (g'): per-query comparison against attempt 2, v4 floors
  verify         the release check reproduces the competitive and paste runs

Exit 0 = every gated rule of the subcommand passed; 1 = a gated rule failed (a line
starting `FAIL`); 2 = the inputs are not what the rule needs - also a stop.

Every CSV is read with `keep_default_na=False`. Gates are decided on integer counts and on
the lower bound of a paired bootstrap, never on a rounded rate. The constants below are the
pre-registered ones; changing one needs a dated addendum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_kri_fixes_gates import (  # noqa: E402
    InputError,
    check_verify,
    parse_summary_block,
    read_csv,
    truthy,
)

BASELINE_ARM = "off"
CANDIDATE_ARMS = ("c2_transition_only", "c2", "c3")
# R7: the order a tie and the walk are decided in, simplest first.
SIMPLICITY_ORDER = CANDIDATE_ARMS
ALL_ARMS = (BASELINE_ARM,) + CANDIDATE_ARMS

SEED = 20261026
BOOTSTRAP_RESAMPLES = 10_000
CI_PERCENTILES = (2.5, 97.5)
MIN_BAND_N = 30  # R5 (d'): a band with fewer positions is reported, never used for a claim
BANDS = ("1", "2-3", "4+")

# Identities pinned by content (sha256 of the manifest files, section 2 and R4).
TEST_MANIFEST_SHA = "ddc7fbe662b873e868d9db44421032e7117d89261f7642e7c4a3c05f1bee4fba"
DEV_MANIFEST_SHA = {
    0.10: "841e3c49c91c0791c3ae378c5c1991dc049ca2b04633450368983c176ceb6e99",
    0.20: "4aafa8059451e4644ab15e715d42152d7291b42d34069afd3e2cc5856e320c09",
}
DEV_RECORD_PATH = "docs/transition-smoothing-dev-record-2026-10-28.json"

PASTE_MODES = ("auto", "declared")
EXPECTED_PASTES = 8
NONE_MODE_EXPECTED_PASSES = 3  # `--stage none` is 3/8 by design
# (set, mode) pairs of rule (g'); a mode is the suffix of `<set>_<mode>_auto`.
COMPETITIVE_RUNS = (
    ("v4", "T"),
    ("v4", "L"),
    ("holdout", "T"),
    ("holdout", "C"),
    ("le_v1", "T"),
    ("le_v1", "C"),
)
RELEASE_BASELINE = PROJECT_ROOT / "data" / "benchmarks" / "release_baseline.json"


# ---------------------------------------------------------------------------
# Paired bootstrap (R7), shared by the dev selection and rule (c')
# ---------------------------------------------------------------------------


def bootstrap_indices(n_groups: int, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = SEED):
    """The resample indices, drawn once from a fresh `default_rng(seed)` and reused for every
    comparison: `resamples` rows of `n_groups` group numbers, int32, with replacement."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_groups, size=(resamples, n_groups), dtype=np.int32)


def paired_difference(
    correct_a: np.ndarray, correct_b: np.ndarray, positions: np.ndarray, indices: np.ndarray
) -> dict:
    """acc(a) - acc(b) with a percentile CI, as a ratio of sums over resampled groups.

    `correct_*` and `positions` are per-group integer counts in the same group order. In
    each resample the difference is sum(correct_a - correct_b) / sum(positions) over the
    resampled groups; the CI is the 2.5th and 97.5th percentile (`numpy.percentile`,
    linear interpolation) of the resamples.
    """
    per_group = (correct_a - correct_b).astype(np.int64)
    positions = positions.astype(np.int64)
    diffs = np.empty(len(indices), dtype=np.float64)
    step = 500
    for start in range(0, len(indices), step):
        block = indices[start : start + step]
        diffs[start : start + step] = per_group[block].sum(axis=1) / positions[block].sum(axis=1)
    low, high = np.percentile(diffs, CI_PERCENTILES)
    return {
        "point": float(per_group.sum() / positions.sum()),
        "ci_low": float(low),
        "ci_high": float(high),
        "correct_diff": int(per_group.sum()),
    }


def group_counts(positions: pd.DataFrame, arms=ALL_ARMS) -> dict:
    """Per-group (sorted by group key) correct counts per arm, and position counts."""
    frame = positions.copy()
    frame["correct"] = frame["correct"].astype(int)
    keys = sorted(set(frame["group_key"]))
    index = {key: i for i, key in enumerate(keys)}
    out: dict = {"keys": keys}
    for arm in arms:
        part = frame[frame["arm"] == arm]
        if part.empty:
            raise InputError(f"no positions for arm {arm!r}")
        correct = np.zeros(len(keys), dtype=np.int64)
        count = np.zeros(len(keys), dtype=np.int64)
        for key, value in zip(part["group_key"], part["correct"]):
            correct[index[key]] += value
            count[index[key]] += 1
        out[arm] = correct
        out[f"n_{arm}"] = count
    base = out[f"n_{arms[0]}"]
    for arm in arms[1:]:
        if not np.array_equal(base, out[f"n_{arm}"]):
            raise InputError(f"arm {arm!r} scored different positions than {arms[0]!r}")
    out["positions"] = base
    return out


def check_same_positions(positions: pd.DataFrame, arms=ALL_ARMS) -> None:
    """Every arm holds the same (row_id, position) records, in the same order, and the
    gold-defined columns do not depend on the arm."""
    reference = None
    for arm in arms:
        part = positions[positions["arm"] == arm]
        if part.empty:
            raise InputError(f"no positions for arm {arm!r}")
        identity = part[["row_id", "position", "gold_reading", "member1", "member2", "band", "stage"]]
        if reference is None:
            reference = identity.reset_index(drop=True)
        elif not identity.reset_index(drop=True).equals(reference):
            raise InputError(f"arm {arm!r}: positions or gold-defined columns differ from {arms[0]!r}")


def _manifest_sha(path: Path) -> str:
    if not path.exists():
        raise InputError(f"missing input: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise InputError(f"missing input: {path}")
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# dev-manifest and dev: R4 and R7
# ---------------------------------------------------------------------------


def check_dev_manifest(run_dir: Path) -> tuple[list[str], list[str]]:
    counts = _load_json(run_dir / "dev_counts.json")
    rate = counts.get("chosen_rate")
    if rate is None:
        raise InputError("dev_counts.json records no chosen draw rate (not runnable)")
    sha = _manifest_sha(run_dir / "dev_manifest_used.csv")
    expected = DEV_MANIFEST_SHA.get(round(float(rate), 2))
    out = [f"dev draw rate {rate}: manifest sha256 {sha}"]
    failures: list[str] = []
    if sha != expected:
        failures.append(f"dev manifest sha256 differs from the pinned one for rate {rate} ({expected})")
    chosen = next(a for a in counts["attempts"] if a["rate"] == rate)
    out.append(
        f"dev positions {chosen['dev_positions']} (>= {counts['min_dev_positions']}), "
        f"R5-population members {chosen['dev_members']} (>= {counts['min_dev_members']})"
    )
    if len(counts["attempts"]) > 1:
        out.append("the 10% draw was short; the one pre-registered step to 20% was taken: " + json.dumps(counts["attempts"][0]))
    return out, failures


def select_primary(per_group: dict, indices: np.ndarray) -> dict:
    """R7, exactly: eligibility, best arm, the simplicity walk, the primary arm."""
    corrects = {arm: int(per_group[arm].sum()) for arm in ALL_ARMS}
    total = int(per_group["positions"].sum())
    arms: dict = {}
    for arm in ALL_ARMS:
        delta = corrects[arm] - corrects[BASELINE_ARM]
        arms[arm] = {
            "correct": corrects[arm],
            "acc": corrects[arm] / total,
            "delta_correct_vs_off": delta,
            "delta_acc_vs_off": delta / total,
            "eligible": arm != BASELINE_ARM and delta > 0,
        }
    eligible = [arm for arm in SIMPLICITY_ORDER if arms[arm]["eligible"]]
    record: dict = {"positions": total, "arms": arms, "eligible": eligible, "best": None, "walk": [], "primary": None}
    if not eligible:
        return record
    # largest delta; an exact tie in correct counts goes to the simpler arm
    best = max(eligible, key=lambda arm: (arms[arm]["delta_correct_vs_off"], -SIMPLICITY_ORDER.index(arm)))
    record["best"] = best
    for arm in eligible:
        if arm == best:
            ci = {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "correct_diff": 0}
        else:
            ci = paired_difference(per_group[best], per_group[arm], per_group["positions"], indices)
        qualifies = ci["ci_low"] <= 0.0
        record["walk"].append({"arm": arm, "best_minus_arm": ci, "qualifies": qualifies})
        if qualifies:
            record["primary"] = arm
            break
    return record


def check_dev(run_dir: Path) -> tuple[list[str], list[str], dict]:
    positions = read_csv(run_dir / "dev_positions.csv")
    check_same_positions(positions)
    counts = _load_json(run_dir / "dev_counts.json")
    rate = counts.get("chosen_rate")
    if rate is None:
        raise InputError("dev_counts.json records no chosen draw rate (not runnable)")
    chosen = next(a for a in counts["attempts"] if a["rate"] == rate)
    per_group = group_counts(positions)
    if int(per_group["positions"].sum()) != chosen["dev_positions"]:
        raise InputError("dev positions in dev_positions.csv differ from dev_counts.json")
    indices = bootstrap_indices(len(per_group["keys"]))
    record = select_primary(per_group, indices)
    record.update(
        experiment="transition-smoothing-2026-10-28",
        dev_manifest_sha256=_manifest_sha(run_dir / "dev_manifest_used.csv"),
        dev_rate=rate,
        dev_counts=chosen,
        groups=len(per_group["keys"]),
        bootstrap={"seed": SEED, "resamples": BOOTSTRAP_RESAMPLES, "percentiles": list(CI_PERCENTILES)},
        approved_commit=(run_dir / "approved_commit.txt").read_text().strip()
        if (run_dir / "approved_commit.txt").exists()
        else "",
    )
    out = [f"dev positions {record['positions']} in {record['groups']} groups (draw rate {rate})"]
    for arm in ALL_ARMS:
        entry = record["arms"][arm]
        out.append(
            f"  {arm:>20}: correct {entry['correct']}  acc {entry['acc']:.5f}  "
            f"delta vs off {entry['delta_correct_vs_off']:+d} positions  eligible {entry['eligible']}"
        )
    out.append(f"eligible (simplicity order): {record['eligible'] or 'none'}")
    for step in record["walk"]:
        ci = step["best_minus_arm"]
        out.append(
            f"walk: {step['arm']}: acc({record['best']}) - acc({step['arm']}) = {ci['point']:+.5f}, "
            f"95% CI [{ci['ci_low']:+.5f}, {ci['ci_high']:+.5f}] -> "
            f"{'PRIMARY' if step['qualifies'] else 'distinguishably worse than the best; next'}"
        )
    if record["primary"]:
        out.append(f"PRIMARY ARM: {record['primary']} (best by delta: {record['best']})")
    else:
        out.append("NO CANDIDATE SURVIVED DEV: no arm beats off on dev; the test split is not opened")
    return out, [], record


# ---------------------------------------------------------------------------
# primary and preflight (test phase, step 0/1)
# ---------------------------------------------------------------------------


def load_record(path: Path) -> dict:
    record = _load_json(path)
    for key in ("primary", "dev_manifest_sha256", "approved_commit", "arms", "eligible", "walk"):
        if key not in record:
            raise InputError(f"dev record has no {key!r}")
    return record


def check_preflight(record_path: Path, repo: Path) -> tuple[list[str], list[str]]:
    record = load_record(record_path)
    out: list[str] = []
    failures: list[str] = []
    if record["primary"] not in CANDIDATE_ARMS:
        failures.append(f"the dev record names no primary arm ({record['primary']!r}); the test split is not opened")
        return out, failures
    out.append(f"primary arm from the dev record: {record['primary']}")
    if record["dev_manifest_sha256"] != DEV_MANIFEST_SHA.get(round(float(record["dev_rate"]), 2)):
        failures.append("the dev record's manifest sha256 is not the pinned one for its draw rate")
    approved = record["approved_commit"]
    if not approved:
        failures.append("the dev record does not name the commit the dev phase ran at")
        return out, failures

    def git(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        if done.returncode != 0:
            raise InputError(f"git {' '.join(args)}: {done.stderr.strip()}")
        return done.stdout.strip()

    head = git("rev-parse", "HEAD")
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", approved, head]).returncode != 0:
        failures.append(f"the dev-phase commit {approved} is not an ancestor of HEAD {head}")
        return out, failures
    changed = sorted(filter(None, git("diff", "--name-only", approved, head).splitlines()))
    out.append(f"files changed between the dev-phase commit and HEAD: {changed}")
    if changed != [DEV_RECORD_PATH]:
        failures.append(
            f"the only change allowed after the dev phase is {DEV_RECORD_PATH}; found {changed}"
        )
    return out, failures


# ---------------------------------------------------------------------------
# harness: rules (c'), (d'), (e), (f'), (h), (i)
# ---------------------------------------------------------------------------


def mechanism_report(positions: pd.DataFrame, member_col: str, arm_name: str) -> dict:
    """R5 (d') / R8 for one arm: members, accuracy at i and i-1, paired counts against off."""
    result: dict = {}
    frames = {}
    for arm in (BASELINE_ARM, arm_name):
        part = positions[positions["arm"] == arm].reset_index(drop=True)
        frames[arm] = part
    ref = frames[BASELINE_ARM]
    member = ref[member_col].astype(int).to_numpy() == 1
    index = np.flatnonzero(member)
    position = ref["position"].astype(int).to_numpy()
    if len(index) and (position[index] < 1).any():
        raise InputError("a member at position 0")
    previous = index - 1
    rows = ref["row_id"].to_numpy()
    if len(index) and not (rows[previous] == rows[index]).all():
        raise InputError("a member's predecessor is not in the same row")
    overlaps = int(np.isin(previous, index).sum())
    bands = ref["band"].to_numpy()
    for band in ("all",) + BANDS:
        sel = np.ones(len(index), dtype=bool) if band == "all" else (bands[index] == band)
        if member_col == "member2":
            sel = np.ones(len(index), dtype=bool) if band == "all" else np.zeros(len(index), dtype=bool)
        here, before = index[sel], previous[sel]
        entry = {"n": int(len(here)), "overlaps": int(np.isin(before, index).sum())}
        for label, arm in (("off", BASELINE_ARM), (arm_name, arm_name)):
            correct = frames[arm]["correct"].astype(int).to_numpy()
            entry[f"{label}_correct_i"] = int(correct[here].sum())
            entry[f"{label}_correct_prev"] = int(correct[before].sum())
        arm_correct = frames[arm_name]["correct"].astype(int).to_numpy()
        off_correct = frames[BASELINE_ARM]["correct"].astype(int).to_numpy()
        for label, left, right in (("i", here, here), ("prev", before, before)):
            entry[f"better_{label}"] = int(((arm_correct[left] == 1) & (off_correct[right] == 0)).sum())
            entry[f"worse_{label}"] = int(((arm_correct[left] == 0) & (off_correct[right] == 1)).sum())
        own = frames[arm_name]["own_prev_vobs1"].astype(int).to_numpy()
        entry["own_path_vobs1"] = int(own[here].sum())
        result[band] = entry
    result["overlaps_total"] = overlaps
    return result


def _mechanism_lines(positions: pd.DataFrame, member_col: str, title: str) -> list[str]:
    out = [title]
    for arm in ALL_ARMS:
        report = mechanism_report(positions, member_col, arm)
        for band in ("all",) + (BANDS if member_col == "member1" else ()):
            e = report[band]
            note = "" if e["n"] >= MIN_BAND_N else "  [n < 30: reported, no claim either way]"
            out.append(
                f"  {arm:>20} band {band:>3}: n={e['n']:>5}  correct@i {e[f'{arm}_correct_i']}"
                f" (off {e['off_correct_i']})  @i-1 {e[f'{arm}_correct_prev']}"
                f" (off {e['off_correct_prev']})  paired@i +{e['better_i']}/-{e['worse_i']}  "
                f"paired@i-1 +{e['better_prev']}/-{e['worse_prev']}  own-path V=1 {e['own_path_vobs1']}"
                f"  overlaps {e['overlaps']}{note}"
            )
    return out


def check_harness(run_dir: Path, record_path: Path) -> tuple[list[str], list[str]]:
    record = load_record(record_path)
    primary = record["primary"]
    if primary not in CANDIDATE_ARMS:
        raise InputError("the dev record names no primary arm")
    positions = read_csv(run_dir / "test_positions.csv")
    lines = read_csv(run_dir / "test_lines.csv")
    check_same_positions(positions)
    out: list[str] = []
    failures: list[str] = []
    if _manifest_sha(run_dir / "test_manifest_used.csv") != TEST_MANIFEST_SHA:
        failures.append("the test manifest used by the harness is not the pinned one")

    per_group = group_counts(positions)
    indices = bootstrap_indices(len(per_group["keys"]))
    total = int(per_group["positions"].sum())
    out.append(f"test positions {total} in {len(per_group['keys'])} groups; primary arm {primary}")

    # (c') overall accuracy: the lower bound of the paired CI of acc(primary) - acc(off) > 0
    for arm in CANDIDATE_ARMS:
        ci = paired_difference(per_group[arm], per_group[BASELINE_ARM], per_group["positions"], indices)
        is_primary = arm == primary
        verdict = ""
        if is_primary:
            verdict = "  PASS" if ci["ci_low"] > 0.0 else "  FAIL"
            if ci["ci_low"] <= 0.0:
                failures.append(
                    f"(c') {arm}: lower bound of the paired 95% CI of acc - acc(off) is {ci['ci_low']:+.5f}, not > 0"
                )
        base = positions[positions["arm"] == BASELINE_ARM]["correct"].astype(int).to_numpy()
        mine = positions[positions["arm"] == arm]["correct"].astype(int).to_numpy()
        better, worse = int(((mine == 1) & (base == 0)).sum()), int(((mine == 0) & (base == 1)).sum())
        out.append(
            f"(c') {arm}{' [PRIMARY]' if is_primary else ' [record only]'}: acc {mine.sum() / total:.5f} vs off "
            f"{base.sum() / total:.5f}, diff {ci['point']:+.5f} ({ci['correct_diff']:+d} positions), 95% CI "
            f"[{ci['ci_low']:+.5f}, {ci['ci_high']:+.5f}]; paired better {better} / off-better {worse} / "
            f"unchanged {total - better - worse}{verdict}"
        )
    for source in sorted(set(positions["source"])):
        sub = positions[positions["source"] == source]
        n = int((sub["arm"] == BASELINE_ARM).sum())
        accs = ", ".join(
            f"{arm} {sub[sub['arm'] == arm]['correct'].astype(int).sum()}/{n}" for arm in ALL_ARMS
        )
        out.append(f"(c') source {source}: {accs} (reported)")

    out += _mechanism_lines(positions, "member1", "(d') mechanism positions: gold previous reading with V_obs = 1 (reported)")
    out += _mechanism_lines(positions, "member2", "(d') secondary diagnostic: gold previous reading V_obs = 2, N <= 3 (reported)")

    # (e) boundary errors
    base_errors = None
    for arm in ALL_ARMS:
        part = lines[lines["arm"] == arm]
        tp, fp, fn = (int(part[c].astype(int).sum()) for c in ("boundary_tp", "boundary_fp", "boundary_fn"))
        errors = fp + fn
        if arm == BASELINE_ARM:
            base_errors = errors
        verdict = ""
        if arm != BASELINE_ARM:
            ok = errors <= base_errors
            verdict = "  PASS" if ok else "  FAIL"
            if not ok and arm == primary:
                failures.append(f"(e) {arm}: boundary errors {errors} > off {base_errors}")
        out.append(
            f"(e) {arm}: boundary errors {errors} (fp {fp}, fn {fn}), precision {tp / (tp + fp):.4f}, recall "
            f"{tp / (tp + fn):.4f}, F1 {2 * tp / (2 * tp + fp + fn):.4f}, exact segmentation "
            f"{int(part['seg_exact'].astype(int).sum())}/{len(part)}{verdict if arm == primary else ''}"
        )

    # (f') routing identity (hard) and the hypothetical routing (listed)
    base_lines = lines[lines["arm"] == BASELINE_ARM].reset_index(drop=True)
    for arm in CANDIDATE_ARMS:
        part = lines[lines["arm"] == arm].reset_index(drop=True)
        if not (part["row_id"].equals(base_lines["row_id"]) and part["stage"].equals(base_lines["stage"])):
            failures.append(f"(f') {arm}: the stage a row was decoded under differs from off's on some line")
        out.append(
            f"(f') {arm}: decoded under off's stage on every line: "
            f"{'yes' if part['stage'].equals(base_lines['stage']) else 'NO'}"
        )
    for arm in CANDIDATE_ARMS:
        part = lines[lines["arm"] == arm].reset_index(drop=True)
        moved = part[part["hyp_stage"] != base_lines["stage"]]
        out.append(f"(f') {arm}: would-route-differently lines: {len(moved)} (listed, no threshold)")
        for _, row in moved.iterrows():
            out.append(
                f"    {row['row_id']}: off stage {base_lines.loc[_, 'stage']!r} ({base_lines.loc[_, 'off_scores']}; "
                f"coverage {base_lines.loc[_, 'coverage']}) -> {arm} would route {row['hyp_stage']!r} "
                f"({row['hyp_scores']}; coverage {row['hyp_coverage']})"
            )

    # (h) calibration, reported
    calibration = read_csv(run_dir / "test_calibration.csv")
    for arm in ALL_ARMS:
        part = calibration[(calibration["arm"] == arm) & (calibration["subset"] == "all")]
        brier = part["brier"].iloc[0] if len(part) else "n/a"
        out.append(f"(h) {arm}: Brier of the shipped confidence {brier} (reported, never gated)")

    # (i) runtime, reported
    timing = read_csv(run_dir / "test_timing.csv")
    out.append("(i) runtime (reported): " + ", ".join(f"{c} {s}s" for c, s in zip(timing["component"], timing["seconds"])))
    return out, failures


# ---------------------------------------------------------------------------
# paste: rules (a) and (f')
# ---------------------------------------------------------------------------


def check_paste(run_dir: Path, baseline_dir: Path) -> tuple[list[str], list[str]]:
    out: list[str] = []
    failures: list[str] = []
    for mode in PASTE_MODES:
        frame = read_csv(run_dir / f"paste_{mode}.csv")
        passed = sum(truthy(v) for v in frame["passed"])
        verdict = "PASS" if passed == EXPECTED_PASTES == len(frame) else "FAIL"
        out.append(f"(a) paste {mode}: {passed}/{len(frame)}  {verdict}")
        if verdict == "FAIL":
            failures.append(f"(a) paste {mode}: {passed}/{len(frame)}")
    none = read_csv(run_dir / "paste_none.csv")
    then = read_csv(baseline_dir / "paste_none.csv")
    passed = sum(truthy(v) for v in none["passed"])
    same = list(none["benchmark_id"]) == list(then["benchmark_id"]) and [
        truthy(v) for v in none["passed"]
    ] == [truthy(v) for v in then["passed"]]
    ok = passed == NONE_MODE_EXPECTED_PASSES and same
    out.append(
        f"(a) paste none: {passed}/{len(none)} (by design {NONE_MODE_EXPECTED_PASSES}/8), "
        f"same per-paste outcome as attempt 2: {same}  {'PASS' if ok else 'FAIL'}"
    )
    if not ok:
        failures.append("(a) paste none is not unchanged at its by-design 3/8")
    # (f') the routing of the pastes does not move: the run under the candidate (paste_auto)
    # against the run with the default (paste_auto_off)
    mine = read_csv(run_dir / "paste_auto.csv")
    off = read_csv(run_dir / "paste_auto_off.csv")
    columns = ["benchmark_id", "stage_used", "stage_inferred", "stage_likelihoods"]
    equal = mine[columns].equals(off[columns])
    out.append(f"(f') paste routing under the candidate equals the default's (stage, likelihoods): {equal}  {'PASS' if equal else 'FAIL'}")
    if not equal:
        failures.append("(f') an expert paste was routed differently under the candidate")
    return out, failures


# ---------------------------------------------------------------------------
# competitive: rule (g')
# ---------------------------------------------------------------------------


def check_competitive(
    run_dir: Path, baseline_dir: Path, release_baseline: Path = RELEASE_BASELINE
) -> tuple[list[str], list[str]]:
    out: list[str] = []
    failures: list[str] = []
    out.append(
        "(g') NOTE: these sets do not exercise the decoder: passing is not evidence for the change, "
        "it only detects collateral damage."
    )
    for set_name, mode in COMPETITIVE_RUNS:
        name = f"{set_name}_{mode}_auto"
        now = read_csv(run_dir / f"{name}.csv")
        then = read_csv(baseline_dir / f"{name}.csv")
        if sorted(now["benchmark_id"]) != sorted(then["benchmark_id"]):
            failures.append(f"(g') {name}: query ids differ from attempt 2")
            continue
        hit_then = dict(zip(then["benchmark_id"], map(truthy, then["top3_useful_family_hit"])))
        lost = [q for q, h in zip(now["benchmark_id"], now["top3_useful_family_hit"]) if hit_then[q] and not truthy(h)]
        gained = [q for q, h in zip(now["benchmark_id"], now["top3_useful_family_hit"]) if not hit_then[q] and truthy(h)]
        s_now = parse_summary_block((run_dir / f"{name}.txt").read_text())
        s_then = parse_summary_block((baseline_dir / f"{name}.txt").read_text())
        verdict = "PASS" if not lost else "FAIL"
        out.append(
            f"(g') {name}: top-3 {s_then.get('top3_useful_family_accuracy')} -> {s_now.get('top3_useful_family_accuracy')}, "
            f"MRR {s_then.get('mrr')} -> {s_now.get('mrr')}; lost {lost or 'none'}, gained {gained or 'none'}  {verdict}"
        )
        if lost:
            failures.append(f"(g') {name}: top-3 answers lost {lost}")
    # release_baseline.json's floors apply only to the configuration that file names
    twin = json.loads(release_baseline.read_text())["twin_controlled"]
    s_v4 = parse_summary_block((run_dir / "v4_T_auto.txt").read_text())
    top3, mrr = float(s_v4["top3_useful_family_accuracy"]), float(s_v4["mrr"])
    ok = top3 >= float(twin["top3_useful_floor"]) and mrr >= float(twin["mrr_floor"])
    out.append(
        f"(g') v4 T-auto release floors: top-3 {top3} >= {twin['top3_useful_floor']}, MRR {mrr} >= {twin['mrr_floor']}  "
        f"{'PASS' if ok else 'FAIL'}"
    )
    if not ok:
        failures.append("(g') v4 T-auto below the release floors")
    legacy = json.loads(release_baseline.read_text())
    s_l = parse_summary_block((run_dir / "v4_L_auto.txt").read_text())
    top3, mrr = float(s_l["top3_useful_family_accuracy"]), float(s_l["mrr"])
    ok = top3 >= float(legacy["top3_useful_floor"]) and mrr >= float(legacy["mrr_floor"])
    out.append(
        f"(g') v4 L-auto release floors: top-3 {top3} >= {legacy['top3_useful_floor']}, MRR {mrr} >= {legacy['mrr_floor']}  "
        f"{'PASS' if ok else 'FAIL'}"
    )
    if not ok:
        failures.append("(g') v4 L-auto below the release floors")
    return out, failures


# ---------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "check",
        choices=("dev-manifest", "dev", "primary", "preflight", "harness", "paste", "competitive", "verify"),
    )
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--baseline-dir", default="", help="attempt-2 run directory of the 2026-10-25 re-measurement")
    parser.add_argument("--record", default=str(PROJECT_ROOT / DEV_RECORD_PATH))
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    baseline_dir = Path(args.baseline_dir).expanduser() if args.baseline_dir else None
    record_path = Path(args.record).expanduser()
    try:
        if args.check in ("paste", "competitive") and baseline_dir is None:
            raise InputError(f"{args.check} needs --baseline-dir")
        if args.check != "primary" and args.check != "preflight" and run_dir is None:
            raise InputError(f"{args.check} needs --run-dir")
        if args.check == "primary":
            record = load_record(record_path)
            if record["primary"] not in CANDIDATE_ARMS:
                raise InputError("the dev record names no primary arm")
            print(record["primary"])
            return 0
        if args.check == "dev":
            out, failures, record = check_dev(run_dir)
            (run_dir / "dev_record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        elif args.check == "dev-manifest":
            out, failures = check_dev_manifest(run_dir)
        elif args.check == "preflight":
            out, failures = check_preflight(record_path, PROJECT_ROOT)
        elif args.check == "harness":
            out, failures = check_harness(run_dir, record_path)
        elif args.check == "paste":
            out, failures = check_paste(run_dir, baseline_dir)
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
