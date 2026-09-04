"""Evaluate real hieroglyph pastes end to end: normalise → resegment → read.

Why this exists. Every other benchmark in this repo is generated from the corpus's
own transliteration tokens, so none of them contains a hieroglyph paste, non-TLA
spacing, a variant codepoint or a layout-control character. The entire failure class
that the first expert trial reported was therefore untestable by construction: the
pipeline was only ever asked questions it had written itself.

These queries come from outside the pipeline. The first four are the trial sentence
(Sethe, Urkunden IV, 1) as an expert actually pasted it and in three other spacings;
the rest are shapes other tools produce — quadrat joiners, an attached line number,
a decomposed transliteration, and signs the corpus does not contain.

Each row is checked on what it can be checked on:

  expected_groups   the segmentation the corpus itself uses
  expected_reading  the reading those groups carry
  must_be_attested  whether every group must be attested (no borrowed readings)

Rows with no expectation (an unattested sequence) assert only that the pipeline
answers honestly rather than inventing a parallel.

    python scripts/run_expert_paste_eval.py
    python scripts/run_expert_paste_eval.py --results out.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.data.normalizer import (  # noqa: E402
    contains_hieroglyphs,
    normalize_hieroglyphs,
)
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.retrieval import retrieve_top_k  # noqa: E402
from app.services.segmentation import DEFAULT_SEGMENTATION_WEIGHTS  # noqa: E402
from app.services.stage import (  # noqa: E402
    StageResources,
    build_stage_resources,
    infer_stage,
    normalize_stage,
)
from app.services.suggestions import suggest_top_readings  # noqa: E402

EXAMPLES_PATH = "data/processed/examples.csv"
QUERIES_PATH = "data/benchmarks/expert_paste_queries.csv"
RESULTS_PATH = "data/benchmarks/expert_paste_eval_results.csv"


def _text(value: object) -> str:
    text = "" if value is None else str(value)
    return "" if text.strip().lower() in {"", "nan"} else text.strip()


def resolve_stage(
    stage_mode: str,
    row: pd.Series,
    get_resources,
) -> tuple[str | None, bool]:
    """Which stage's resources this row should be read/segmented/retrieved with.

    Returns (stage, inferred). 'none' always returns (None, False) — today's pooled
    behaviour, unchanged. 'declared' reads the row's own `language_stage` column.
    'auto' runs a first retrieval pass on the pooled resources (glyph queries are
    segmented with the pooled model first, since the reading/glyph signal needs
    *some* segmentation to search on) and infers the stage from that pass's results,
    exactly as `retrieve_with_stage` does for a plain retrieval query.
    """
    if stage_mode == "none":
        return None, False
    if stage_mode == "declared":
        return normalize_stage(row.get("language_stage", "")), False

    # auto
    pooled = get_resources(None)
    query = str(row["query_input"])
    regrouped = ""
    if contains_hieroglyphs(query):
        as_pasted = normalize_hieroglyphs(query).split()
        regrouped = " ".join(pooled.segmenter.segment(as_pasted).groups)
    first_pass = retrieve_top_k(
        pooled.frame,
        query_mdc=query,
        k=10,
        query_hieroglyphs_norm=regrouped or None,
        index=pooled.index,
    )
    stage = infer_stage(first_pass)
    return stage, stage is not None


def evaluate_row(row: pd.Series, resources: StageResources, stage_mode: str, inferred: bool) -> dict:
    query = str(row["query_input"])
    expected_reading = _text(row.get("expected_reading"))
    expected_groups = _text(row.get("expected_groups"))
    must_be_attested = _text(row.get("must_be_attested")).lower() == "yes"

    model, segmenter, index, df = (
        resources.reading_model,
        resources.segmenter,
        resources.index,
        resources.frame,
    )

    is_glyph_query = contains_hieroglyphs(query)
    groups: list[str] = []
    reading = ""
    fallbacks = 0
    unreadable = 0
    regrouped = ""

    if is_glyph_query:
        as_pasted = normalize_hieroglyphs(query).split()
        segmentation = segmenter.segment(as_pasted)
        groups = segmentation.groups
        regrouped = " ".join(groups)
        predictions = model.predict_sequence(groups)
        reading = " ".join(p.predicted for p in predictions if p.predicted)
        fallbacks = sum(1 for p in predictions if p.is_fallback)
        unreadable = sum(1 for p in predictions if not p.was_seen and not p.is_fallback)

    pool = retrieve_top_k(
        df,
        query_mdc=query,
        k=50,
        query_hieroglyphs_norm=regrouped or None,
        index=index,
    )
    suggestions = suggest_top_readings(
        pool, query_mdc=query, top_n=3, query_hieroglyphs=regrouped
    )

    groups_ok = (not expected_groups) or (regrouped == expected_groups)
    reading_ok = (not expected_reading) or (reading == expected_reading)
    attested_ok = (not must_be_attested) or (fallbacks == 0 and unreadable == 0)
    # A row with no expected reading is testing honesty: it must NOT claim a
    # parallel it does not have. `min_parallels` inverts that for rows whose point
    # is that a differently-encoded query still finds its matches.
    min_parallels = int(float(_text(row.get("min_parallels")) or 0))
    if min_parallels:
        honesty_ok = len(pool) >= min_parallels
    elif not expected_reading and is_glyph_query:
        honesty_ok = pool.empty or not suggestions
    else:
        honesty_ok = True

    return {
        "benchmark_id": row["benchmark_id"],
        "source": row.get("source", ""),
        "query_input": query,
        "stage_mode": stage_mode,
        "stage_used": resources.stage or "",
        "stage_inferred": inferred,
        "expected_groups": expected_groups,
        "actual_groups": regrouped,
        "groups_ok": groups_ok,
        "expected_reading": expected_reading,
        "actual_reading": reading,
        "reading_ok": reading_ok,
        "fallback_groups": fallbacks,
        "unreadable_groups": unreadable,
        "attested_ok": attested_ok,
        "honesty_ok": honesty_ok,
        "passed": groups_ok and reading_ok and attested_ok and honesty_ok,
        "parallels_found": int(len(pool)),
        "top_suggestion": suggestions[0].candidate_transliteration if suggestions else "",
        "top_confidence": round(suggestions[0].confidence_score, 3) if suggestions else 0.0,
        "min_parallels": min_parallels,
        "notes": row.get("notes", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--queries", default=QUERIES_PATH)
    parser.add_argument("--results", default=RESULTS_PATH)
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help="Read with the corpus alone, without the Helsinki sign-reading lexicon.",
    )
    parser.add_argument(
        "--lexicon-weight",
        type=float,
        default=None,
        help="Override SegmentationWeights.lexicon_weight (for sweeps).",
    )
    parser.add_argument(
        "--stage",
        choices=["none", "auto", "declared"],
        default="none",
        help=(
            "Language-stage handling (item A). 'none' (default) reproduces today's "
            "pooled reading/segmentation/retrieval exactly. 'declared' reads each "
            "row's own language_stage column. 'auto' infers the stage per row from "
            "a first retrieval pass over the pooled resources."
        ),
    )
    args = parser.parse_args()

    df = load_examples_csv(args.examples)
    lexicon = None if args.no_lexicon else load_lexicon()
    weights = DEFAULT_SEGMENTATION_WEIGHTS
    if args.lexicon_weight is not None:
        weights = weights.replace(lexicon_weight=args.lexicon_weight)

    # One StageResources per stage actually needed, built lazily and reused across
    # rows — training the reading model and building the search index are the
    # expensive steps, and at most 4 distinct stages (None + STAGES) are ever asked
    # for regardless of how many benchmark rows there are.
    resources_cache: dict[str | None, StageResources] = {}

    def get_resources(target: str | None) -> StageResources:
        if target not in resources_cache:
            resources_cache[target] = build_stage_resources(
                df,
                target,
                lexicon=lexicon,
                segmentation_weights=weights,
                use_lexicon=not args.no_lexicon,
            )
        return resources_cache[target]

    queries = pd.read_csv(args.queries, keep_default_na=False)

    rows = []
    for _, row in queries.iterrows():
        stage, inferred = resolve_stage(args.stage, row, get_resources)
        resources = get_resources(stage)
        rows.append(evaluate_row(row, resources, args.stage, inferred))
    results = pd.DataFrame(rows)

    pooled = get_resources(None)
    print(f"corpus {len(pooled.frame)} rows; {len(results)} expert pastes; stage={args.stage}\n")
    for row in rows:
        mark = "PASS" if row["passed"] else "FAIL"
        stage_note = ""
        if args.stage != "none":
            stage_label = row["stage_used"] or "(none)"
            inferred_note = " inferred" if row["stage_inferred"] else ""
            stage_note = f"  [stage={stage_label}{inferred_note}]"
        print(f"[{mark}] {row['benchmark_id']}  {row['source']}{stage_note}")
        if row["expected_reading"]:
            print(f"        reading : {row['actual_reading']}")
            if not row["reading_ok"]:
                print(f"        expected: {row['expected_reading']}")
        if row["expected_groups"] and not row["groups_ok"]:
            print(f"        groups  : {row['actual_groups']}")
            print(f"        expected: {row['expected_groups']}")
        if row["fallback_groups"] or row["unreadable_groups"]:
            print(
                f"        {row['fallback_groups']} borrowed, "
                f"{row['unreadable_groups']} unreadable"
            )

    passed = sum(1 for row in rows if row["passed"])
    print(f"\npassed {passed}/{len(rows)}")

    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.results, index=False)
    print(f"Saved results to {args.results}")

    if passed != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
