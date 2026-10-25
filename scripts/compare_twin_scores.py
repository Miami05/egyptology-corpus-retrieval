"""Compare competitive-eval runs with and without twin exclusion (audit A4, A23).

    python scripts/compare_twin_scores.py \
        --pair v4 runs/ceval_v4_twins0_results.csv runs/ceval_v4_twins0.7_results.csv \
        --pair holdout runs/ceval_holdout_twins0_results.csv runs/ceval_holdout_twins0.7_results.csv

Each `--pair NAME TWINS_IN TWINS_OUT` joins two per-query result CSVs written by
`scripts/run_competitive_ambiguity_eval.py` (the first run left the target's twins in
the pool, the second took them out). It prints, per benchmark, the headline numbers
for both runs, the fixed baselines' numbers and the app's margin over them, and the
queries whose useful rank or shown suggestions changed. It only reads CSVs and writes
two NEW files; it never touches a committed result.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

METRICS_PATH = "data/benchmarks/twin_controlled_comparison_2026-10-12.csv"
CHANGES_PATH = "data/benchmarks/twin_controlled_query_changes_2026-10-12.csv"


def _rank(value: object) -> "int | None":
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value) == "":
        return None
    return int(float(value))


def _shares(ranks: "list[int | None]") -> tuple[float, float, float]:
    """(top-1 share, top-3 share, MRR) of per-query ranks, None = no hit in the top 3."""
    total = len(ranks) or 1
    top1 = sum(1 for r in ranks if r == 1) / total
    top3 = sum(1 for r in ranks if r is not None and r <= 3) / total
    mrr = sum(1.0 / r for r in ranks if r is not None) / total
    return top1, top3, mrr


def metrics_from_results(results: pd.DataFrame) -> dict[str, float]:
    """Headline and baseline numbers recomputed from a per-query results frame."""
    useful = [_rank(v) for v in results["useful_family_rank"]]
    exact = [_rank(v) for v in results["exact_rank"]]
    top1, top3, mrr = _shares(useful)
    _, exact3, _ = _shares(exact)
    out: dict[str, float] = {
        "queries": float(len(results)),
        "top1_useful": top1,
        "top3_useful": top3,
        "mrr": mrr,
        "top3_exact": exact3,
        "failures": float(sum(1 for r in useful if r is None)),
    }
    for column, label in [
        ("overlap_baseline_useful_rank", "overlap_baseline"),
        ("bm25_baseline_useful_rank", "bm25_baseline"),
        ("strict_useful_rank", "strict_useful"),
    ]:
        if column in results.columns:
            _, base3, base_mrr = _shares([_rank(v) for v in results[column]])
            out[f"{label}_top3"] = base3
            out[f"{label}_mrr"] = base_mrr
            if label != "strict_useful":
                out[f"margin_over_{label}_top3"] = top3 - base3
                out[f"margin_over_{label}_mrr"] = mrr - base_mrr
    if "top3_near_exact" in results.columns:
        out["top3_near_exact"] = float(
            results["top3_near_exact"].astype(str).str.lower().eq("true").mean()
        )
    return out


def query_changes(twins_in: pd.DataFrame, twins_out: pd.DataFrame) -> pd.DataFrame:
    """Per-query rows where the useful rank or the shown suggestions differ."""
    joined = twins_in.merge(
        twins_out, on="benchmark_id", suffixes=("_in", "_out"), validate="one_to_one"
    )
    rows = []
    for _, row in joined.iterrows():
        rank_in = _rank(row["useful_family_rank_in"])
        rank_out = _rank(row["useful_family_rank_out"])
        shown_changed = str(row["suggestions_in"]) != str(row["suggestions_out"])
        if rank_in != rank_out or shown_changed:
            rows.append(
                {
                    "benchmark_id": row["benchmark_id"],
                    "useful_rank_twins_in": rank_in if rank_in is not None else "",
                    "useful_rank_twins_out": rank_out if rank_out is not None else "",
                    "exact_rank_twins_in": _rank(row["exact_rank_in"]) or "",
                    "exact_rank_twins_out": _rank(row["exact_rank_out"]) or "",
                    "twins_removed": row.get("twins_removed_out", ""),
                    "suggestions_changed": shown_changed,
                    "top_suggestion_twins_in": str(row["suggestions_in"]).split(" || ")[0],
                    "top_suggestion_twins_out": str(row["suggestions_out"]).split(" || ")[0],
                }
            )
    return pd.DataFrame(rows)


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair",
        nargs=3,
        action="append",
        required=True,
        metavar=("NAME", "TWINS_IN_CSV", "TWINS_OUT_CSV"),
    )
    parser.add_argument("--metrics-output", default=METRICS_PATH)
    parser.add_argument("--changes-output", default=CHANGES_PATH)
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> None:
    args = _parse_args(argv)
    metric_rows: list[dict[str, object]] = []
    change_frames: list[pd.DataFrame] = []
    for name, in_path, out_path in args.pair:
        twins_in = pd.read_csv(in_path).fillna("")
        twins_out = pd.read_csv(out_path).fillna("")
        before = metrics_from_results(twins_in)
        after = metrics_from_results(twins_out)
        print(f"\n{name}: twins left in the pool vs twins removed")
        for metric in before:
            delta = after[metric] - before[metric]
            print(f"  {metric:<32} {before[metric]:8.4f} -> {after[metric]:8.4f} ({delta:+.4f})")
            metric_rows.append(
                {
                    "benchmark": name,
                    "metric": metric,
                    "twins_in": round(before[metric], 4),
                    "twins_out": round(after[metric], 4),
                    "delta": round(delta, 4),
                }
            )
        changes = query_changes(twins_in, twins_out)
        if len(changes):
            print(f"  queries that changed ({len(changes)}):")
            print(changes.to_string(index=False))
            change_frames.append(changes.assign(benchmark=name))
        else:
            print("  no query changed its rank or its shown suggestions")
    for path in (args.metrics_output, args.changes_output):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(metric_rows).to_csv(args.metrics_output, index=False)
    (pd.concat(change_frames) if change_frames else pd.DataFrame()).to_csv(
        args.changes_output, index=False
    )
    print(f"\nWrote {args.metrics_output} and {args.changes_output}")


if __name__ == "__main__":
    main()
