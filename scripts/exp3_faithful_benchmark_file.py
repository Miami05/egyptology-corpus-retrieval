"""Experiment 3: the faithful benchmark file of a set built with a faithful column.

Held-out 2 (and, once, held-out 3) carry the builder's folded query in `query_input`
and the faithful one in `faithful_query_input` (scripts/exp3_build_heldouts.py, which
uses scripts/exp3_step0_faithful_queries.py's derivation). The competitive harness
reads `query_input`, so the faithful run needs a file where that column holds the
faithful query. This writes it in the same shape step 0 writes the four older sets'
faithful files (`--faithful-benchmarks-dir`): `query_input` replaced, the stored query
kept as `stored_query_input` right after it, every other column unchanged.

The addendum's precondition is checked on every row before the file is written: the
fold-back `search_fold(faithful) == stored query`. Any failure writes nothing and exits 1.

    python scripts/exp3_faithful_benchmark_file.py IN.csv OUT.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import search_fold  # noqa: E402

FAITHFUL = "faithful_query_input"


def faithful_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """The faithful benchmark frame, and the ids whose fold-back fails."""
    if FAITHFUL not in frame.columns:
        raise ValueError(f"no {FAITHFUL} column")
    if "stored_query_input" in frame.columns:
        raise ValueError("already a faithful benchmark file (has stored_query_input)")
    bad = [
        str(row.benchmark_id)
        for row in frame.itertuples(index=False)
        if not str(getattr(row, FAITHFUL)).strip()
        or search_fold(getattr(row, FAITHFUL)) != row.query_input
    ]
    out = frame.copy()
    out.insert(out.columns.get_loc("query_input") + 1, "stored_query_input", out["query_input"])
    out["query_input"] = out[FAITHFUL]
    return out, bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source")
    parser.add_argument("out")
    args = parser.parse_args(argv)
    frame = pd.read_csv(args.source, dtype=str, keep_default_na=False)
    out, bad = faithful_frame(frame)
    if bad:
        print(f"fold-back fails on {len(bad)}/{len(frame)}: {' '.join(bad)}", file=sys.stderr)
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"fold-back holds on {len(frame)}/{len(frame)}; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
