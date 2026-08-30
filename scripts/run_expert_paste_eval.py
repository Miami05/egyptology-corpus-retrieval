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
from app.services.reading_model import train_reading_model  # noqa: E402
from app.services.retrieval import build_search_index, retrieve_top_k  # noqa: E402
from app.services.segmentation import Segmenter  # noqa: E402
from app.services.suggestions import suggest_top_readings  # noqa: E402

EXAMPLES_PATH = "data/processed/examples.csv"
QUERIES_PATH = "data/benchmarks/expert_paste_queries.csv"
RESULTS_PATH = "data/benchmarks/expert_paste_eval_results.csv"


def _text(value: object) -> str:
    text = "" if value is None else str(value)
    return "" if text.strip().lower() in {"", "nan"} else text.strip()


def evaluate_row(row: pd.Series, df: pd.DataFrame, model, segmenter, index) -> dict:
    query = str(row["query_input"])
    expected_reading = _text(row.get("expected_reading"))
    expected_groups = _text(row.get("expected_groups"))
    must_be_attested = _text(row.get("must_be_attested")).lower() == "yes"

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
    args = parser.parse_args()

    df = load_examples_csv(args.examples)
    model = train_reading_model(df)
    segmenter = Segmenter(model)
    index = build_search_index(df)
    queries = pd.read_csv(args.queries)

    rows = [
        evaluate_row(row, df, model, segmenter, index)
        for _, row in queries.iterrows()
    ]
    results = pd.DataFrame(rows)

    print(f"corpus {len(df)} rows; {len(results)} expert pastes\n")
    for row in rows:
        mark = "PASS" if row["passed"] else "FAIL"
        print(f"[{mark}] {row['benchmark_id']}  {row['source']}")
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
