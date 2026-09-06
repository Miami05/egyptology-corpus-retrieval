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
from app.data.normalizer import contains_hieroglyphs  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.retrieval import resolve_auto_stage, retrieve_top_k  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    DEFAULT_SEGMENTATION_WEIGHTS,
    segment_paste,
)
from app.services.stage import (  # noqa: E402
    StageResources,
    build_stage_resources,
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
) -> tuple[str | None, bool, dict[str, float] | None]:
    """Which stage's resources this row should be read/segmented/retrieved with.

    Returns (stage, inferred, likelihood_scores). 'none' always returns
    (None, False, None) — today's pooled behaviour, unchanged. 'declared' reads
    the row's own `language_stage` column. 'auto' delegates to
    `app.services.retrieval.resolve_auto_stage` — the one shared implementation
    `app/ui/whyptology_app.py`'s `resolve_ui_stage` also calls — which resolves a
    hieroglyph paste by per-stage reading likelihood
    (`app.services.stage.choose_stage_by_likelihood`) and a text query by the
    original label-based first-pass + `infer_stage` rule. `likelihood_scores` is
    that function's per-stage per-sign audit dict for a glyph query (for the
    per-paste table `main` prints below), `None` for 'none'/'declared' and empty
    for a text query in 'auto' mode (no likelihoods computed there).
    """
    if stage_mode == "none":
        return None, False, None
    if stage_mode == "declared":
        return normalize_stage(row.get("language_stage", "")), False, None

    stage, inferred, scores = resolve_auto_stage(str(row["query_input"]), get_resources)
    return stage, inferred, scores


def evaluate_row(
    row: pd.Series,
    resources: StageResources,
    stage_mode: str,
    inferred: bool,
    stage_scores: dict[str, float] | None = None,
    use_format_hints: bool = True,
) -> dict:
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
        segmentation, _as_pasted = segment_paste(
            query, segmenter, use_format_hints=use_format_hints
        )
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
        "stage_likelihoods": (
            "; ".join(f"{stage}={value:.3f}" for stage, value in stage_scores.items())
            if stage_scores
            else ""
        ),
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
        "--quadrat-crossed",
        type=float,
        default=None,
        help="Override SegmentationWeights.quadrat_crossed (item B constant sweep).",
    )
    parser.add_argument(
        "--no-format-hints",
        action="store_true",
        help=(
            "Delete the paste's layout controls (U+13430-1345F) instead of reading "
            "them as 'do not cut inside this quadrat' hints — the behaviour before "
            "item B."
        ),
    )
    parser.add_argument(
        "--stage",
        choices=["none", "auto", "declared"],
        default="auto",
        help=(
            "Language-stage handling (item A). 'none' (default) reproduces today's "
            "pooled reading/segmentation/retrieval exactly. 'declared' reads each "
            "row's own language_stage column. 'auto' resolves a hieroglyph paste by "
            "per-stage reading likelihood and a text query by a first retrieval pass "
            "over the pooled resources (app.services.retrieval.resolve_auto_stage)."
        ),
    )
    args = parser.parse_args()

    df = load_examples_csv(args.examples)
    lexicon = None if args.no_lexicon else load_lexicon()
    weights = DEFAULT_SEGMENTATION_WEIGHTS
    if args.lexicon_weight is not None:
        weights = weights.replace(lexicon_weight=args.lexicon_weight)
    if args.quadrat_crossed is not None:
        weights = weights.replace(quadrat_crossed=args.quadrat_crossed)

    # One StageResources per stage actually needed, built lazily and reused across
    # rows — training the reading model and building the search index are the
    # expensive steps, and at most 4 distinct stages (None + STAGES) are ever asked
    # for regardless of how many benchmark rows there are.
    resources_cache: dict[str | None, StageResources] = {}

    def get_resources(target: str | None) -> StageResources:
        if target not in resources_cache:
            # Every stage's segmenter is built from the pooled frame (see
            # build_stage_resources), so a concrete-stage build always needs the
            # pooled reading model too; build/cache target=None first (recursion
            # bottoms out there) so it is fit once, not once per stage.
            pooled_reading_model = (
                get_resources(None).reading_model if target is not None else None
            )
            resources_cache[target] = build_stage_resources(
                df,
                target,
                lexicon=lexicon,
                segmentation_weights=weights,
                use_lexicon=not args.no_lexicon,
                pooled_reading_model=pooled_reading_model,
            )
        return resources_cache[target]

    queries = pd.read_csv(args.queries, keep_default_na=False)

    rows = []
    for _, row in queries.iterrows():
        stage, inferred, scores = resolve_stage(args.stage, row, get_resources)
        resources = get_resources(stage)
        rows.append(
            evaluate_row(
                row,
                resources,
                args.stage,
                inferred,
                stage_scores=scores,
                use_format_hints=not args.no_format_hints,
            )
        )
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
        if row["stage_likelihoods"]:
            print(f"        per-sign log-likelihood: {row['stage_likelihoods']}")

    passed = sum(1 for row in rows if row["passed"])
    print(f"\npassed {passed}/{len(rows)}")

    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.results, index=False)
    print(f"Saved results to {args.results}")

    if passed != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
