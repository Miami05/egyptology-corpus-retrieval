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

Before comparing, each pair is validated (`validate_pair`): both runs must cover exactly
the same benchmark ids with the same query and target, under the same stage mode,
the first with twin exclusion off and the second with one threshold above 0. (The
query path and useful rule are not in the per-query CSV; check them in the two runs'
printed summaries.) A pair that fails is refused, because the headline
numbers are computed per run while the change table only sees ids present in both, so
a dropped or swapped query could look like an improvement.
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


# Columns that identify a query and its target: they must agree id for id.
IDENTITY_COLUMNS = (
    "query_input",
    "query_type",
    "expected_transliteration",
    "expected_source_text_id",
    "expected_source_sentence_id",
)
# Run configuration that must be the same in both runs, when the results record it.
SHARED_CONFIG_COLUMNS = ("stage_mode",)


def _single_value(results: pd.DataFrame, column: str, label: str) -> str:
    values = {str(value) for value in results[column]}
    if len(values) != 1:
        raise ValueError(f"{label}: {column} is not constant across rows: {sorted(values)}")
    return values.pop()


def validate_pair(twins_in: pd.DataFrame, twins_out: pd.DataFrame, name: str = "") -> None:
    """Refuse to compare two runs that are not the same benchmark under two twin settings.

    Raises ValueError, naming the problem, when: a benchmark id repeats in either run;
    the id sets differ; any identity column (query, query type, expected reading and
    target ids) differs for an id; the stage mode differs; the first run did not have
    twin exclusion off or the second did not have one threshold above 0.
    """
    label = name or "pair"
    for side, frame in (("twins-in", twins_in), ("twins-out", twins_out)):
        if "benchmark_id" not in frame.columns:
            raise ValueError(f"{label}: {side} run has no benchmark_id column")
        repeated = sorted(frame.loc[frame["benchmark_id"].duplicated(), "benchmark_id"].astype(str))
        if repeated:
            raise ValueError(f"{label}: {side} run repeats benchmark ids {repeated}")
    ids_in = set(twins_in["benchmark_id"].astype(str))
    ids_out = set(twins_out["benchmark_id"].astype(str))
    if ids_in != ids_out:
        raise ValueError(
            f"{label}: the runs cover different queries; only in twins-in "
            f"{sorted(ids_in - ids_out)}, only in twins-out {sorted(ids_out - ids_in)}"
        )
    left = twins_in.assign(benchmark_id=twins_in["benchmark_id"].astype(str)).set_index("benchmark_id")
    right = twins_out.assign(benchmark_id=twins_out["benchmark_id"].astype(str)).set_index("benchmark_id")
    for column in IDENTITY_COLUMNS:
        if column not in left.columns or column not in right.columns:
            raise ValueError(f"{label}: both runs need the {column} column")
        mismatched = sorted(
            bid for bid in ids_in if str(left.at[bid, column]) != str(right.at[bid, column])
        )
        if mismatched:
            raise ValueError(f"{label}: {column} differs for {mismatched}")
    for column in SHARED_CONFIG_COLUMNS:
        if column in twins_in.columns and column in twins_out.columns:
            value_in = _single_value(twins_in, column, f"{label} twins-in")
            value_out = _single_value(twins_out, column, f"{label} twins-out")
            if value_in != value_out:
                raise ValueError(f"{label}: {column} differs ({value_in} vs {value_out})")
    for side, frame in (("twins-in", twins_in), ("twins-out", twins_out)):
        if "twin_exclusion" not in frame.columns:
            raise ValueError(f"{label}: {side} run has no twin_exclusion column")
    threshold_in = float(_single_value(twins_in, "twin_exclusion", f"{label} twins-in"))
    threshold_out = float(_single_value(twins_out, "twin_exclusion", f"{label} twins-out"))
    if threshold_in != 0.0:
        raise ValueError(f"{label}: the twins-in run had twin exclusion {threshold_in}, not off")
    if not 0.0 < threshold_out <= 1.0:
        raise ValueError(
            f"{label}: the twins-out run had twin exclusion {threshold_out}, not in (0, 1]"
        )


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
        validate_pair(twins_in, twins_out, name)
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
