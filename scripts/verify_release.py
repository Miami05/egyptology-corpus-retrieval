"""One command that says whether a build is fit to deploy.

    python scripts/verify_release.py
    python scripts/verify_release.py --benchmark data/benchmarks/competitive_ambiguity_eval_queries_v4.csv

Runs, in order: the full pytest suite; the competitive ambiguity evaluation (the only
reportable accuracy metric — target row excluded from the searchable corpus); and the
expert-paste evaluation. Every evaluation writes to a temporary directory, never to the
committed files under data/benchmarks, so a release check leaves the working tree as
it found it. Prints a one-screen summary and exits non-zero if anything failed.

Why the summary quotes top-3 *useful-family* accuracy and not exact match: the tool's
job is to surface the right reading family with its evidence, not to reproduce an
unseen sentence verbatim. See data/benchmarks/CORPUS_SCALING_REPORT.md.
"""

from __future__ import annotations

import argparse
import glob
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_GLOB = "data/benchmarks/competitive_ambiguity_eval_queries_v*.csv"


def newest_benchmark() -> Path:
    """The highest-numbered competitive benchmark: v10 must sort after v9."""
    candidates = glob.glob(str(PROJECT_ROOT / BENCHMARK_GLOB))
    if not candidates:
        raise SystemExit(f"no benchmark matches {BENCHMARK_GLOB}")

    def version(path: str) -> int:
        match = re.search(r"_v(\d+)\.csv$", path)
        return int(match.group(1)) if match else -1

    return Path(max(candidates, key=version))


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Competitive benchmark CSV (default: newest *_v<N>.csv under data/benchmarks).",
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip pytest (evaluations only)."
    )
    args = parser.parse_args()

    benchmark = Path(args.benchmark) if args.benchmark else newest_benchmark()
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

        # 2. competitive ambiguity benchmark
        code, out, secs = run(
            [
                python,
                "scripts/run_competitive_ambiguity_eval.py",
                "--benchmark",
                str(benchmark),
                "--results",
                str(tmp_dir / "competitive_results.csv"),
                "--failures",
                str(tmp_dir / "competitive_failures.csv"),
            ],
            f"competitive ambiguity eval — {benchmark.name}",
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

    verdict = "READY" if not failures else "NOT READY — failed: " + ", ".join(failures)
    print(
        "\n"
        "┌─ release summary ─────────────────────────────────────────\n"
        f"│ tests            {tests_line}\n"
        f"│ corpus rows      {corpus_rows}\n"
        f"│ benchmark        {benchmark.name} ({queries} queries, target row excluded)\n"
        f"│ top-1 useful     {top1}\n"
        f"│ top-3 useful     {top3}   <- the reportable number\n"
        f"│ MRR              {mrr}\n"
        f"│ benchmark fails  {bench_failures}\n"
        f"│ expert pastes    {pastes} passed\n"
        f"│ verdict          {verdict}\n"
        "└───────────────────────────────────────────────────────────"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
