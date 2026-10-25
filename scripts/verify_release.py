"""One command that says whether a build is fit to deploy.

    python scripts/verify_release.py
    python scripts/verify_release.py --benchmark data/benchmarks/competitive_ambiguity_eval_queries_v4.csv
    python scripts/verify_release.py --baseline data/benchmarks/release_baseline.json

Runs, in order: the full pytest suite; the competitive ambiguity evaluation (the only
reportable accuracy metric — target row excluded from the searchable corpus); and the
expert-paste evaluation. Every evaluation writes to a temporary directory, never to the
committed files under data/benchmarks, so a release check leaves the working tree as
it found it. Prints a one-screen summary and exits non-zero if anything failed.

The benchmark and the accuracy floors are read from a committed baseline
(data/benchmarks/release_baseline.json by default). That file names the benchmark, the
stage mode and the query path explicitly, and this script passes all three to the
evaluation on the command line — so the run is self-describing and a number can never
be silently measured against a different benchmark than the floors were set on. The
default harness benchmark has been wrong before (see the memory notes); relying on the
"newest *_v<N>.csv" glob for a release check was that same trap. `--benchmark` still
overrides the file's benchmark, and `--baseline` selects another baseline file.

The verdict is NOT READY when top-3 useful accuracy or MRR falls below its floor, when
fewer than the required expert pastes pass, or when any step exited non-zero. Each floor
is printed beside the number it gates.

Twin-controlled gate (audit A4/A23). The number that gates is the *twin-controlled* one:
the baseline's `twin_controlled` block names the `exclude_twins` overlap, the
`expected_tokens` mode and that run's own floors (`top3_useful_floor`, `mrr_floor`, and
optional `margin_floors` such as `margin_over_bm25_baseline_top3`, the app's margin over
the fixed baselines). The legacy pool (only the target removed, edition twins left in,
frozen expected tokens) is still run and printed beside it, labelled and non-gating.
A baseline without a `twin_controlled` block is NOT READY, because its number includes
free edition-copy hits; `--allow-legacy-gate` gates on the legacy pool instead, loudly
labelled, until the pre-registered re-measure has set the twin-controlled floors.

Why the summary quotes top-3 *useful-family* accuracy and not exact match: the tool's
job is to surface the right reading family with its evidence, not to reproduce an
unseen sentence verbatim. See data/benchmarks/CORPUS_SCALING_REPORT.md.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = PROJECT_ROOT / "data/benchmarks/release_baseline.json"
BENCHMARK_DIR = PROJECT_ROOT / "data/benchmarks"

# Equality with a floor must pass: a number measured at exactly the floor (0.90 == 0.90)
# is fine, and only a genuine drop below it fails. This tolerance also absorbs the last
# ulp of float noise so a re-measured 0.9 never trips the gate against a 0.90 floor.
FLOOR_EPSILON = 1e-9

EXPECTED_TOKEN_MODES = ("current", "frozen")
# The legacy pool, exactly as every published floor before audit A4 was measured.
LEGACY_RUN = {"exclude_twins": 0.0, "expected_tokens": "frozen"}
# The margins the competitive eval prints; a `margin_floors` key must be one of these.
MARGIN_KEYS = (
    "margin_over_overlap_baseline_top3",
    "margin_over_overlap_baseline_mrr_value",
    "margin_over_bm25_baseline_top3",
    "margin_over_bm25_baseline_mrr_value",
)


def _finite_number(value, name: str) -> float:
    """`value` as a finite float, or ValueError. Strings ("0.9", "NaN") and bools are
    refused: a floor that is not a real number would make every comparison against it
    silently pass (NaN) or mean something else than written."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def validate_floors(block: dict, where: str) -> dict:
    """Validated copies of a floor block's accuracy, MRR and margin floors.

    `top3_useful_floor` and `mrr_floor` must be finite and in (0, 1] (a zero floor gates
    nothing); every `margin_floors` key must be a margin the eval prints, with a finite
    floor in [0, 1] (a negative floor would accept the app losing to a fixed baseline).
    Raises ValueError naming `where` and the bad key.
    """
    floors: dict = {}
    for key in ("top3_useful_floor", "mrr_floor"):
        if key not in block:
            raise ValueError(f"{where} has no {key}")
        number = _finite_number(block[key], f"{where} {key}")
        if not 0.0 < number <= 1.0:
            raise ValueError(f"{where} {key} {number} is not in (0, 1]")
        floors[key] = number
    margin_floors = block.get("margin_floors")
    if margin_floors is None:
        if "margin_floors" in block:
            raise ValueError(f"{where} margin_floors is null")
        floors["margin_floors"] = {}
        return floors
    if not isinstance(margin_floors, dict):
        raise ValueError(f"{where} margin_floors must be an object")
    checked: dict = {}
    for key, value in margin_floors.items():
        if key not in MARGIN_KEYS:
            raise ValueError(f"{where} margin_floors key {key!r} is not a known margin")
        number = _finite_number(value, f"{where} margin_floors {key}")
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{where} margin_floors {key} {number} is not in [0, 1]")
        checked[key] = number
    floors["margin_floors"] = checked
    return floors


def load_baseline(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_pastes(text: str) -> tuple[int, int] | None:
    """`"8/8"` -> (8, 8); anything unparseable -> None."""
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(text))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def check_release_floors(
    top3: float | None,
    mrr: float | None,
    pastes: tuple[int, int] | None,
    baseline: dict,
    margins: "dict[str, float | None] | None" = None,
) -> list[str]:
    """Pure floor check: return one message per failed gate, empty when all pass.

    No I/O and no eval run, so it is unit-tested without the corpus. `top3`/`mrr` are
    the measured numbers (None if the run produced no parseable value); `pastes` is
    (passed, total). `baseline` may carry `margin_floors` ({summary key: floor}); each
    is checked against `margins` (the measured margins over the fixed baselines).
    """
    try:
        validate_floors(baseline, "baseline")
    except ValueError as error:
        # A malformed floor must fail, never compare (NaN < x is always False).
        return [str(error)]
    failures: list[str] = []
    measured_margins = margins or {}
    for key, floor in (baseline.get("margin_floors") or {}).items():
        value = measured_margins.get(key)
        if value is None:
            failures.append(f"{key} could not be measured")
        elif value < float(floor) - FLOOR_EPSILON:
            failures.append(f"{key} {value} below floor {float(floor)}")

    top3_floor = float(baseline["top3_useful_floor"])
    if top3 is None:
        failures.append("top-3 useful accuracy could not be measured")
    elif top3 < top3_floor - FLOOR_EPSILON:
        failures.append(f"top-3 useful {top3} below floor {top3_floor}")

    mrr_floor = float(baseline["mrr_floor"])
    if mrr is None:
        failures.append("MRR could not be measured")
    elif mrr < mrr_floor - FLOOR_EPSILON:
        failures.append(f"MRR {mrr} below floor {mrr_floor}")

    expected_pastes = parse_pastes(baseline["expert_pastes_floor"])
    if expected_pastes is None:
        failures.append("baseline expert_pastes_floor is not 'N/N'")
    elif pastes is None:
        failures.append("expert pastes could not be measured")
    else:
        passed, total = pastes
        want_passed, want_total = expected_pastes
        if total != want_total or passed < want_passed:
            failures.append(
                f"expert pastes {passed}/{total} below floor "
                f"{want_passed}/{want_total}"
            )

    return failures


def run(cmd: list[str], label: str) -> tuple[int, str, float]:
    started = time.monotonic()
    print(f"\n=== {label} ===\n$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    print(output[-4000:], flush=True)
    return proc.returncode, output, time.monotonic() - started


def grab(pattern: str, text: str, default: str = "?") -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1) if match else default


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def twin_controlled_config(baseline: dict) -> "dict | None":
    """The baseline's `twin_controlled` block, validated; None when there is none.

    Raises ValueError for a block that is present but unusable (an overlap outside
    (0, 1], an unknown expected-token mode, a missing floor): a typo here must stop
    the gate, not silently fall back to the legacy pool.
    """
    if "twin_controlled" not in baseline:
        return None
    block = baseline["twin_controlled"]
    if block is None:
        # Present-but-null is a broken configuration, not an absent one: treating it as
        # absent would let the legacy pool decide READY without --allow-legacy-gate.
        raise ValueError("baseline twin_controlled is null")
    if not isinstance(block, dict):
        raise ValueError("baseline twin_controlled must be an object")
    try:
        overlap = float(block["exclude_twins"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("baseline twin_controlled needs a numeric exclude_twins") from error
    if not 0.0 < overlap <= 1.0:
        raise ValueError(f"baseline twin_controlled exclude_twins {overlap} is not in (0, 1]")
    mode = str(block.get("expected_tokens", "current"))
    if mode not in EXPECTED_TOKEN_MODES:
        raise ValueError(f"baseline twin_controlled expected_tokens {mode!r} is unknown")
    floors = validate_floors(block, "baseline twin_controlled")
    return {
        **block,
        **floors,
        "exclude_twins": overlap,
        "expected_tokens": mode,
        "expert_pastes_floor": baseline["expert_pastes_floor"],
    }


def competitive_eval_command(
    python: str,
    benchmark: Path,
    baseline: dict,
    run: dict,
    results: Path,
    failures: Path,
) -> list[str]:
    """The competitive-eval command line for one pool (`run`: exclude_twins, expected_tokens).

    Every setting that decides the number is passed explicitly, straight from the
    baseline, so the log says exactly what produced it.
    """
    return [
        python,
        "scripts/run_competitive_ambiguity_eval.py",
        "--benchmark",
        str(benchmark),
        "--stage",
        str(baseline.get("stage", "auto")),
        "--query-path",
        str(baseline.get("query_path", "app")),
        "--useful-rule",
        str(baseline.get("useful_rule", "v4")),
        "--exclude-twins",
        str(run["exclude_twins"]),
        "--expected-tokens",
        str(run["expected_tokens"]),
        "--results",
        str(results),
        "--failures",
        str(failures),
    ]


def parse_competitive(out: str) -> dict:
    """The numbers verify_release reads from one competitive-eval run's output."""
    margins = {
        key: _to_float(grab(rf"^{key}:\s*(-?[\d.]+)$", out, ""))
        for key in (
            "margin_over_overlap_baseline_top3",
            "margin_over_overlap_baseline_mrr_value",
            "margin_over_bm25_baseline_top3",
            "margin_over_bm25_baseline_mrr_value",
        )
    }
    return {
        "corpus_rows": grab(r"corpus_rows:\s*(\d+)", out),
        "queries": grab(r"total_queries:\s*(\d+)", out),
        "top1": grab(r"top1_useful_family_accuracy:\s*([\d.]+)", out),
        "top3": grab(r"top3_useful_family_accuracy:\s*([\d.]+)", out),
        "mrr": grab(r"mrr:\s*([\d.]+)", out),
        "failures": grab(r"failures:\s*(\d+)", out),
        "pool": grab(r"^pool:\s*(\S+)", out),
        "margins": margins,
    }


def resolve_benchmark(baseline: dict, override: str | None) -> Path:
    if override:
        return Path(override)
    return BENCHMARK_DIR / baseline["benchmark"]


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Committed baseline JSON with the benchmark, flags and accuracy floors.",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Override the baseline's benchmark CSV (path or name under data/benchmarks).",
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip pytest (evaluations only)."
    )
    parser.add_argument(
        "--allow-legacy-gate",
        action="store_true",
        help=(
            "Gate on the legacy pool (edition twins left in) when the baseline has no "
            "twin_controlled block. Without it such a baseline is NOT READY (audit A4)."
        ),
    )
    args = parser.parse_args(argv)

    baseline = load_baseline(Path(args.baseline))
    benchmark = resolve_benchmark(baseline, args.benchmark)
    stage = str(baseline.get("stage", "auto"))
    query_path = str(baseline.get("query_path", "app"))
    useful_rule = str(baseline.get("useful_rule", "v4"))
    python = sys.executable
    failures: list[str] = []

    try:
        twin_config = twin_controlled_config(baseline)
    except ValueError as error:
        twin_config = None
        failures.append(str(error))
    # The top-level (legacy) floors are validated up front too, so a malformed floor
    # stops the gate before any evaluation runs.
    try:
        validate_floors(baseline, "baseline")
    except ValueError as error:
        failures.append(str(error))
    if failures:
        print("NOT READY — " + "; ".join(failures))
        return 1
    if twin_config is None and not args.allow_legacy_gate:
        failures.append(
            "baseline has no twin_controlled block, so the only number is the legacy "
            "pool's, which includes free edition-twin hits (audit A4); set it after the "
            "pre-registered re-measure, or pass --allow-legacy-gate"
        )
    legacy_gates = twin_config is None

    with tempfile.TemporaryDirectory(prefix="verify-release-") as tmp:
        tmp_dir = Path(tmp)

        # 1. tests
        if args.skip_tests:
            tests_line = "skipped"
        else:
            code, out, secs = run([python, "-m", "pytest", "-q"], "pytest")
            tests_line = grab(r"(\d+ passed[^\n]*)", out, "no summary line")
            tests_line = f"{tests_line} ({secs:.0f}s)"
            if code != 0:
                failures.append("pytest")

        # 2. competitive ambiguity benchmark — benchmark AND every flag it must run
        #    under are passed explicitly, straight from the baseline, so the log says
        #    exactly what produced the number and it cannot drift onto another file.
        #    The legacy pool always runs (printed, and gating only when no
        #    twin_controlled block exists); the twin-controlled pool runs when the
        #    baseline names one, and then it is the number that gates.
        flags = f"--stage {stage} --query-path {query_path} --useful-rule {useful_rule}"
        code, out, _ = run(
            competitive_eval_command(
                python, benchmark, baseline, LEGACY_RUN,
                tmp_dir / "legacy_results.csv", tmp_dir / "legacy_failures.csv",
            ),
            f"competitive ambiguity eval, LEGACY pool — {benchmark.name} ({flags})",
        )
        if code != 0:
            failures.append("competitive eval (legacy pool)")
        legacy = parse_competitive(out)
        gated = legacy
        if twin_config is not None:
            code, out, _ = run(
                competitive_eval_command(
                    python, benchmark, baseline, twin_config,
                    tmp_dir / "twin_results.csv", tmp_dir / "twin_failures.csv",
                ),
                f"competitive ambiguity eval, TWIN-CONTROLLED pool — {benchmark.name} "
                f"({flags} --exclude-twins {twin_config['exclude_twins']} "
                f"--expected-tokens {twin_config['expected_tokens']})",
            )
            if code != 0:
                failures.append("competitive eval (twin-controlled pool)")
            gated = parse_competitive(out)

        # 3. expert pastes
        code, out, secs = run(
            [
                python,
                "scripts/run_expert_paste_eval.py",
                "--results",
                str(tmp_dir / "expert_paste_results.csv"),
            ],
            "expert paste eval",
        )
        if code != 0:
            failures.append("expert paste eval")
        pastes = grab(r"passed (\d+/\d+)", out)

    # Floor check on the gated numbers (a step that itself exited non-zero is already
    # in `failures`; this adds a failure when a step ran but under-performed).
    floors = twin_config if twin_config is not None else baseline
    failures.extend(
        check_release_floors(
            _to_float(gated["top3"]),
            _to_float(gated["mrr"]),
            parse_pastes(pastes),
            floors,
            gated["margins"],
        )
    )

    expected_rows = baseline.get("expected_corpus_rows", "?")
    if legacy_gates:
        pool_line = "LEGACY pool gates (twins in; --allow-legacy-gate or no twin_controlled)"
    else:
        pool_line = (
            f"TWIN-CONTROLLED pool gates (--exclude-twins {twin_config['exclude_twins']} "
            f"--expected-tokens {twin_config['expected_tokens']})"
        )
    legacy_line = (
        f"top-3 {legacy['top3']}  MRR {legacy['mrr']}  "
        f"(floors {baseline['top3_useful_floor']} / {baseline['mrr_floor']})"
        + ("" if legacy_gates else "  NON-GATING, twins in")
    )
    margin_lines = "".join(
        f"│ {key:<36} {value}"
        + (
            f"   floor {floors['margin_floors'][key]}"
            if key in (floors.get("margin_floors") or {})
            else ""
        )
        + "\n"
        for key, value in gated["margins"].items()
    )

    verdict = "READY" if not failures else "NOT READY — " + "; ".join(failures)
    print(
        "\n"
        "┌─ release summary ─────────────────────────────────────────\n"
        f"│ tests            {tests_line}\n"
        f"│ baseline         {Path(args.baseline).name} "
        f"(recorded {baseline.get('recorded_at', '?')} @ "
        f"{baseline.get('recorded_commit', '?')})\n"
        f"│ corpus rows      {gated['corpus_rows']}   (baseline {expected_rows})\n"
        f"│ benchmark        {benchmark.name} ({gated['queries']} queries, target row excluded)\n"
        f"│ run flags        {flags}\n"
        f"│ gate pool        {pool_line}\n"
        f"│ top-1 useful     {gated['top1']}\n"
        f"│ top-3 useful     {gated['top3']}   floor {floors['top3_useful_floor']}"
        "   <- the reportable number\n"
        f"│ MRR              {gated['mrr']}   floor {floors['mrr_floor']}\n"
        f"│ benchmark fails  {gated['failures']}\n"
        f"{margin_lines}"
        f"│ legacy pool      {legacy_line}\n"
        f"│ expert pastes    {pastes} passed   floor {baseline['expert_pastes_floor']}\n"
        f"│ verdict          {verdict}\n"
        "└───────────────────────────────────────────────────────────"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
