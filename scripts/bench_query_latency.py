"""Measure the end-to-end latency of one search, the way the app runs it.

Why this exists. ROADMAP item 3 (2026-09-05) asks for a transliteration query on the
130k-row corpus to drop below 0.5 s *with scores and ranks unchanged*. Both halves
need a harness: a timing that goes through the same call path the Streamlit app uses
for a search in Auto mode (stage resolution -> resegmentation for a glyph paste ->
`retrieve_with_stage` at k=50 -> `suggest_top_readings`), and a dump of the FULL
scored candidate frame per query so that any optimisation can be proved
score-and-rank-identical rather than merely "about the same".

    python scripts/bench_query_latency.py --out /tmp/item3/before
    python scripts/bench_query_latency.py --out /tmp/item3/after
    python scripts/bench_query_latency.py --compare /tmp/item3/before /tmp/item3/after

Resource building (corpus load, reading models, indexes) happens once, before any
timing, and is excluded from it — the server warms these at start-up, so a query's
honest cost is the warm one.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.data.normalizer import contains_hieroglyphs  # noqa: E402
from app.services import retrieval as retrieval_module  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.retrieval import resolve_auto_stage, retrieve_with_stage  # noqa: E402
from app.services.segmentation import segment_paste  # noqa: E402
from app.services.stage import STAGES, StageResources, build_stage_resources  # noqa: E402
from app.services.suggestions import suggest_top_readings  # noqa: E402

EXAMPLES_PATH = "data/processed/examples.csv"
V4_PATH = "data/benchmarks/competitive_ambiguity_eval_queries_v4.csv"
PASTE_PATH = "data/benchmarks/expert_paste_queries.csv"

# Every column `combine_scores` produces, plus the ranking it produced them in.
SCORE_COLUMNS = [
    "fuzzy_score",
    "tfidf_score",
    "exact_bonus",
    "overlap_score",
    "idf_overlap_score",
    "glyph_overlap_score",
    "glyph_idf_overlap_score",
    "glyph_order_score",
    "glyph_exact_bonus",
    "reading_order_overlap",
    "final_score",
]


def build_resources(df: pd.DataFrame):
    """The lazy per-stage resource cache the eval scripts and the UI both use."""
    cache: dict[str | None, StageResources] = {}
    lexicon = load_lexicon()

    def get_resources(target: str | None) -> StageResources:
        if target not in cache:
            pooled = get_resources(None) if target is not None else None
            cache[target] = build_stage_resources(
                df,
                target,
                lexicon=lexicon,
                pooled_reading_model=pooled.reading_model if pooled else None,
                pooled_index=pooled.index if pooled else None,
            )
        return cache[target]

    return get_resources, cache


def run_query(query: str, get_resources) -> None:
    """One search, exactly as `app/ui/whyptology_app.py` runs it in Auto mode.

    Mirrors the block under `if run_search:` there: `resolve_ui_stage` ("auto" ->
    `resolve_auto_stage`), then this stage's resources, then `resegment_query` for a
    glyph paste, then `retrieve_with_stage` on the *resolved* (never "auto") stage at
    k=50, then the suggestion layer over that pool.
    """
    resolved_stage, _inferred, _scores = resolve_auto_stage(query, get_resources)
    resources = get_resources(resolved_stage)
    regrouped: str | None = None
    if contains_hieroglyphs(query):
        segmentation, _as_pasted = segment_paste(query, resources.segmenter)
        regrouped = " ".join(segmentation.groups)
    stage_result = retrieve_with_stage(
        resources.frame,
        resources_by_stage=get_resources,
        query_mdc=query,
        query_reading_order="",
        stage=resolved_stage,
        k=50,
        query_hieroglyphs_norm=regrouped,
    )
    suggest_top_readings(
        stage_result.results,
        query_mdc=query,
        query_reading_order="",
        top_n=3,
        query_hieroglyphs=regrouped or "",
    )


class _Capture:
    """Records every full scored frame `combine_scores` produces during one query.

    A query in Auto mode can score the corpus twice (the pooled first pass that
    resolves the stage, then the real pass on the resolved stage's statistics), and
    both passes must be identical after an optimisation, so both are recorded.
    """

    def __init__(self) -> None:
        self.frames: list[pd.DataFrame] = []
        self._original = retrieval_module.combine_scores

    def __enter__(self) -> "_Capture":
        def wrapper(*args, **kwargs):
            scored = self._original(*args, **kwargs)
            keep = [c for c in SCORE_COLUMNS if c in scored.columns]
            frame = scored[keep].copy()
            frame.insert(0, "row_index", scored.index.to_numpy())
            frame.reset_index(drop=True, inplace=True)
            # The corpus frame carries a non-JSON-serialisable `attrs` payload
            # (the loader's AlignmentReport), which pandas tries to pickle into
            # the parquet key-value metadata and chokes on.
            frame.attrs = {}
            self.frames.append(frame)
            return scored

        retrieval_module.combine_scores = wrapper
        return self

    def __exit__(self, *exc) -> None:
        retrieval_module.combine_scores = self._original


def load_queries(limit_text: int = 8, limit_paste: int = 2) -> list[tuple[str, str]]:
    v4 = pd.read_csv(PROJECT_ROOT / V4_PATH)
    paste = pd.read_csv(PROJECT_ROOT / PASTE_PATH)
    queries = [
        (str(row["benchmark_id"]), str(row["query_input"]))
        for _, row in v4.head(limit_text).iterrows()
    ]
    queries += [
        (str(row["benchmark_id"]), str(row["query_input"]))
        for _, row in paste.head(limit_paste).iterrows()
    ]
    return queries


def rss_mb() -> float:
    """Resident set size *now*, in MB.

    Not `ru_maxrss`: that is the high-water mark, so it never goes down and a
    before/after comparison of it measures whichever run happened to peak higher
    during a transient (index building allocates and frees a lot). `ps` reports
    what the process is holding at this moment, which is the number the server's
    memory budget cares about.
    """
    import subprocess

    try:
        output = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(__import__("os").getpid())],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(output.stdout.strip()) / 1024  # ps reports kilobytes
    except Exception:  # pragma: no cover - diagnostics only
        return float("nan")


def peak_rss_mb() -> float:
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes, Linux kilobytes.
        return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024
    except Exception:  # pragma: no cover - diagnostics only
        return float("nan")


def compare(before_dir: Path, after_dir: Path) -> int:
    """Exact-equality check of every dumped score column, per query and per pass."""
    before_files = sorted(before_dir.glob("*.parquet"))
    if not before_files:
        print(f"no dumps in {before_dir}")
        return 1
    worst = 0.0
    failures = 0
    for path in before_files:
        other = after_dir / path.name
        if not other.exists():
            print(f"MISSING {other}")
            failures += 1
            continue
        left = pd.read_parquet(path)
        right = pd.read_parquet(other)
        if list(left.columns) != list(right.columns) or len(left) != len(right):
            print(f"SHAPE   {path.name}: {left.shape} vs {right.shape}")
            failures += 1
            continue
        row_order_same = np.array_equal(
            left["row_index"].to_numpy(), right["row_index"].to_numpy()
        )
        diffs = {}
        for column in left.columns:
            if column == "row_index":
                continue
            a = left[column].to_numpy(dtype=np.float64)
            b = right[column].to_numpy(dtype=np.float64)
            if not np.array_equal(a, b):
                diffs[column] = float(np.max(np.abs(a - b)))
        if diffs:
            worst = max(worst, max(diffs.values()))
        # Rank agreement on the visible pool, independent of the row order above.
        top50_same = set(left["row_index"].head(50)) == set(right["row_index"].head(50))
        status = "OK" if (not diffs and row_order_same) else "DIFF"
        if status == "DIFF":
            failures += 1
        print(
            f"{status:4} {path.name:38} rows={len(left)} order_identical={row_order_same} "
            f"top50_same={top50_same} "
            + (
                "max_abs_diff="
                + ", ".join(f"{c}={v:.3e}" for c, v in sorted(diffs.items()))
                if diffs
                else "all columns bit-identical"
            )
        )
    print(f"\n{len(before_files) - failures}/{len(before_files)} dumps identical; "
          f"worst max abs diff {worst:.3e}")
    return 0 if failures == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--out", default=None, help="directory for the score dumps")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--profile", action="store_true", help="cProfile one query")
    parser.add_argument(
        "--memory-only",
        action="store_true",
        help="build the resources, report RSS, and stop (no timing)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="compare two dump directories and exit",
    )
    args = parser.parse_args()

    if args.compare:
        raise SystemExit(compare(Path(args.compare[0]), Path(args.compare[1])))

    t0 = time.perf_counter()
    df = load_examples_csv(args.examples)
    print(f"corpus: {len(df):,} rows loaded in {time.perf_counter() - t0:.1f} s")
    rss_before = rss_mb()

    get_resources, cache = build_resources(df)
    t0 = time.perf_counter()
    for target in (None, *STAGES):
        get_resources(target)
    print(
        f"resources: {len(cache)} stage sets built in {time.perf_counter() - t0:.1f} s; "
        f"RSS {rss_before:.0f} MB -> {rss_mb():.0f} MB "
        f"(peak {peak_rss_mb():.0f} MB)"
    )
    if args.memory_only:
        return

    queries = load_queries()
    # One untimed warm-up per query: lru_caches and lazily-built structures must not
    # be charged to the first repetition.
    for _, query in queries:
        run_query(query, get_resources)

    rows = []
    all_wall: list[float] = []
    all_cpu: list[float] = []
    for qid, query in queries:
        wall: list[float] = []
        cpu: list[float] = []
        for _ in range(args.repeats):
            start_cpu = time.process_time()
            start = time.perf_counter()
            run_query(query, get_resources)
            wall.append(time.perf_counter() - start)
            cpu.append(time.process_time() - start_cpu)
        all_wall.extend(wall)
        all_cpu.extend(cpu)
        rows.append(
            {
                "query_id": qid,
                "cpu_median_s": statistics.median(cpu),
                "cpu_p95_s": float(np.percentile(cpu, 95)),
                "wall_median_s": statistics.median(wall),
                "wall_p95_s": float(np.percentile(wall, 95)),
            }
        )
    table = pd.DataFrame(rows)
    pd.set_option("display.width", 140)
    print("\nper query (s):")
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    # CPU time is the headline: this box runs several agents at once, and a wall
    # clock on a contended machine measures the neighbours, not the query.
    print(
        f"\noverall CPU:  median {statistics.median(all_cpu):.3f} s  "
        f"p95 {np.percentile(all_cpu, 95):.3f} s"
    )
    print(
        f"overall wall: median {statistics.median(all_wall):.3f} s  "
        f"p95 {np.percentile(all_wall, 95):.3f} s  n={len(all_wall)}"
    )

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for qid, query in queries:
            with _Capture() as capture:
                run_query(query, get_resources)
            for pass_no, frame in enumerate(capture.frames):
                frame.to_parquet(out_dir / f"{qid}_pass{pass_no}.parquet", index=False)
        print(f"\nscore dumps written to {out_dir}")

    if args.profile:
        query = queries[0][1]
        profiler = cProfile.Profile()
        profiler.enable()
        run_query(query, get_resources)
        profiler.disable()
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(25)
        print("\ncProfile (cumulative, top 25) for", queries[0][0])
        print(stream.getvalue())

    print(f"RSS at exit: {rss_mb():.0f} MB (peak {peak_rss_mb():.0f} MB)")


if __name__ == "__main__":
    main()
