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

Why the summary quotes top-3 *useful-family* accuracy and not exact match: the tool's
job is to surface the right reading family with its evidence, not to reproduce an
unseen sentence verbatim. See data/benchmarks/CORPUS_SCALING_REPORT.md.
"""

from __future__ import annotations

import argparse
import json
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
) -> list[str]:
    """Pure floor check: return one message per failed gate, empty when all pass.

    No I/O and no eval run, so it is unit-tested without the corpus. `top3`/`mrr` are
    the measured numbers (None if the run produced no parseable value); `pastes` is
    (passed, total).
    """
    failures: list[str] = []

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
    match = re.search(pattern, text)
    return match.group(1) if match else default


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_benchmark(baseline: dict, override: str | None) -> Path:
    if override:
        return Path(override)
    return BENCHMARK_DIR / baseline["benchmark"]


def main() -> int:
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
    args = parser.parse_args()

    baseline = load_baseline(Path(args.baseline))
    benchmark = resolve_benchmark(baseline, args.benchmark)
    stage = str(baseline.get("stage", "auto"))
    query_path = str(baseline.get("query_path", "app"))
    python = sys.executable
    failures: list[str] = []

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

        # 2. competitive ambiguity benchmark — benchmark AND the flags it must run
        #    under are passed explicitly, straight from the baseline, so the log says
        #    exactly what produced the number and it cannot drift onto another file.
        code, out, secs = run(
            [
                python,
                "scripts/run_competitive_ambiguity_eval.py",
                "--benchmark",
                str(benchmark),
                "--stage",
                stage,
                "--query-path",
                query_path,
                "--results",
                str(tmp_dir / "competitive_results.csv"),
                "--failures",
                str(tmp_dir / "competitive_failures.csv"),
            ],
            f"competitive ambiguity eval — {benchmark.name} "
            f"(--stage {stage} --query-path {query_path})",
        )
        if code != 0:
            failures.append("competitive eval")
        corpus_rows = grab(r"corpus_rows:\s*(\d+)", out)
        queries = grab(r"total_queries:\s*(\d+)", out)
        top1 = grab(r"top1_useful_family_accuracy:\s*([\d.]+)", out)
        top3 = grab(r"top3_useful_family_accuracy:\s*([\d.]+)", out)
        mrr = grab(r"mrr:\s*([\d.]+)", out)
        bench_failures = grab(r"failures:\s*(\d+)", out)

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

    # Floor check on the measured numbers (a step that itself exited non-zero is
    # already in `failures`; this adds a failure when a step ran but under-performed).
    floor_failures = check_release_floors(
        _to_float(top3), _to_float(mrr), parse_pastes(pastes), baseline
    )
    failures.extend(floor_failures)

    top3_floor = baseline["top3_useful_floor"]
    mrr_floor = baseline["mrr_floor"]
    pastes_floor = baseline["expert_pastes_floor"]
    expected_rows = baseline.get("expected_corpus_rows", "?")

    verdict = "READY" if not failures else "NOT READY — " + "; ".join(failures)
    print(
        "\n"
        "┌─ release summary ─────────────────────────────────────────\n"
        f"│ tests            {tests_line}\n"
        f"│ baseline         {Path(args.baseline).name} "
        f"(recorded {baseline.get('recorded_at', '?')} @ "
        f"{baseline.get('recorded_commit', '?')})\n"
        f"│ corpus rows      {corpus_rows}   (baseline {expected_rows})\n"
        f"│ benchmark        {benchmark.name} ({queries} queries, target row excluded)\n"
        f"│ run flags        --stage {stage} --query-path {query_path}\n"
        f"│ top-1 useful     {top1}\n"
        f"│ top-3 useful     {top3}   floor {top3_floor}   <- the reportable number\n"
        f"│ MRR              {mrr}   floor {mrr_floor}\n"
        f"│ benchmark fails  {bench_failures}\n"
        f"│ expert pastes    {pastes} passed   floor {pastes_floor}\n"
        f"│ verdict          {verdict}\n"
        "└───────────────────────────────────────────────────────────"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
