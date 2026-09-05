"""The roadmap gate for the St Andrews importer (item 4, 2026-09-05).

Two questions, answered from one build of the stage resources because building them
over a 138k-row corpus is the expensive part:

1. **Camilla's Urk. IV 1 line (`PASTE_001`) against his rows.** Where does the St
   Andrews row for that line rank — among all rows, and among St Andrews rows alone?
2. **Do the 8 expert paste checks still pass with the private rows present?**
   `scripts/run_expert_paste_eval.py` has no `--private-dir` or environment override
   (its argparse takes `--examples`, `--queries`, `--results`, `--no-lexicon`,
   `--lexicon-weight`, `--stage`), so its own `evaluate_row` is imported here and run
   against the combined frame instead of re-running it on a temporary CSV.

The corpus is assembled exactly as `app/ui/whyptology_app.py` assembles it: the public
CC BY-SA frame first (`load_examples_csv`), the private CC BY-NC-SA rows appended
afterwards (`load_private_examples`), never merged into the public file.

    python scripts/check_standrews_urkiv_gate.py
    python scripts/check_standrews_urkiv_gate.py --stage none
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv, load_private_examples  # noqa: E402
from app.data.normalizer import (  # noqa: E402
    contains_hieroglyphs,
    normalize_hieroglyphs,
    search_fold,
)
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.retrieval import retrieve_top_k  # noqa: E402
from app.services.segmentation import DEFAULT_SEGMENTATION_WEIGHTS  # noqa: E402
from app.services.stage import StageResources, build_stage_resources  # noqa: E402
from app.services.suggestions import suggest_top_readings  # noqa: E402
from scripts.run_expert_paste_eval import evaluate_row, resolve_stage  # noqa: E402

EXAMPLES_PATH = PROJECT_ROOT / "data" / "processed" / "examples.csv"
PRIVATE_DIR = PROJECT_ROOT / "data" / "private"
QUERIES_PATH = PROJECT_ROOT / "data" / "benchmarks" / "expert_paste_queries.csv"

GATE_BENCHMARK = "PASTE_001"
# His division of Urk. IV 1: `<2> Dd=f` and `<@6>Dd=j n=Tn rmT nbt` are two body
# blocks, so no single St Andrews row carries the whole of the expert's line. The
# second block is the row the gate is measured on.
GATE_MARKER = "urkIV-001"


def load_corpus() -> pd.DataFrame:
    public = load_examples_csv(str(EXAMPLES_PATH))
    private = load_private_examples(PRIVATE_DIR)
    if private.empty:
        return public
    return pd.concat([public, private], ignore_index=True, sort=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["none", "auto", "declared"], default="auto")
    parser.add_argument("--rank-k", type=int, default=0, help="0 = the whole corpus")
    args = parser.parse_args()

    started = time.time()
    df = load_corpus()
    counts = df["source"].value_counts().to_dict()
    print(f"corpus {len(df):,} rows: {counts}")

    lexicon = load_lexicon()
    cache: dict[str | None, StageResources] = {}

    def get_resources(target: str | None) -> StageResources:
        if target not in cache:
            pooled_reading_model = (
                get_resources(None).reading_model if target is not None else None
            )
            cache[target] = build_stage_resources(
                df,
                target,
                lexicon=lexicon,
                segmentation_weights=DEFAULT_SEGMENTATION_WEIGHTS,
                use_lexicon=True,
                pooled_reading_model=pooled_reading_model,
            )
        return cache[target]

    queries = pd.read_csv(QUERIES_PATH, keep_default_na=False)

    # --- the 8 expert paste checks, with the private rows present ----------------
    results = []
    for _, row in queries.iterrows():
        stage, inferred, scores = resolve_stage(args.stage, row, get_resources)
        results.append(
            evaluate_row(
                row, get_resources(stage), args.stage, inferred, stage_scores=scores
            )
        )
    passed = sum(1 for row in results if row["passed"])
    print(f"\nexpert paste checks (stage={args.stage}): {passed}/{len(results)}")
    for row in results:
        mark = "PASS" if row["passed"] else "FAIL"
        print(f"  [{mark}] {row['benchmark_id']}  {row['actual_reading']}")
        if not row["passed"] and row["expected_reading"]:
            print(f"         expected: {row['expected_reading']}")

    # --- the rank of the St Andrews row for Camilla's line ----------------------
    gate = queries[queries["benchmark_id"] == GATE_BENCHMARK].iloc[0]
    stage, _inferred, _scores = resolve_stage(args.stage, gate, get_resources)
    resources = get_resources(stage)
    query = str(gate["query_input"])
    regrouped = ""
    if contains_hieroglyphs(query):
        as_pasted = normalize_hieroglyphs(query).split()
        regrouped = " ".join(resources.segmenter.segment(as_pasted).groups)
    rank_k = args.rank_k or len(df)
    pool = retrieve_top_k(
        resources.frame,
        query_mdc=query,
        k=rank_k,
        query_hieroglyphs_norm=regrouped or None,
        index=resources.index,
    )
    print(
        f"\n{GATE_BENCHMARK} '{query}' — stage {stage or '(pooled)'}, "
        f"retrieval pool {len(pool):,} of {len(df):,} (k={rank_k:,})"
    )
    pool = pool.reset_index(drop=True)
    standrews = pool[pool["source"] == "StAndrews"]
    urk = standrews[standrews["source_ref"].astype(str).str.contains(GATE_MARKER)]
    print(f"  St Andrews rows in the pool: {len(standrews):,}")
    for label, frame in (("all rows", pool), ("St Andrews rows only", standrews)):
        if urk.empty:
            print(f"  rank among {label}: not retrieved in the top {rank_k:,}")
            continue
        best = urk.index[0]
        rank = int(frame.index.get_indexer([best])[0]) + 1
        print(f"  rank among {label}: {rank}")
    if not urk.empty:
        top = urk.iloc[0]
        print(f"  row: {top['transliteration_gold']}")
        print(f"       {top['source_ref']}")
        print(f"       fold: {search_fold(top['transliteration_gold'])}")
    print(f"  query fold: {search_fold(gate['expected_reading'])}")
    print("\n  top 5 overall:")
    for position, (_, row) in enumerate(pool.head(5).iterrows(), start=1):
        print(
            f"    {position}. [{row['source']}] {str(row['transliteration_gold'])[:70]}"
        )

    suggestions = suggest_top_readings(
        pool, query_mdc=query, top_n=3, query_hieroglyphs=regrouped
    )
    print("\n  top 3 suggestions:")
    for position, suggestion in enumerate(suggestions, start=1):
        print(
            f"    {position}. {suggestion.candidate_transliteration}  "
            f"({suggestion.confidence_score:.4f})"
        )

    print(f"\ndone in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
