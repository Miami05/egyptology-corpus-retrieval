"""Held-out stage routing: does "auto" send an Earlier or Late paste to Demotic?

Written to rule A2.3 of docs/remeasure-preregistration-2026-10-25.md, exactly; read
that rule before changing anything here, because a change after the first run is a
dated addendum there, not an edit here.

Sample (A2.3, exact):

* eligible = public rows (`--examples`, never the private directory) with non-empty
  normalised hieroglyphs whose `language_stage` is Earlier Egyptian (source TLA) or
  Late Egyptian (source Ramses or TLA);
* sorted by (`source`, `source_text_id`, `source_sentence_id`), one row kept per
  normalised sign string (the first in that order);
* `rng = numpy.random.default_rng(seed)`; Earlier drawn first, then Late, each with
  `rng.choice(len(eligible_of_that_stage), per_stage, replace=False)`. Fewer eligible
  rows than `--per-stage` stops the run (exit 2).

Removed from the pool once, before the stage resources are built: the sampled rows,
every row with the same normalised sign string, and every row sharing a
`source_text_id` with a sampled row. Each sampled row's raw `hieroglyphs` is then
routed by the app's own "auto" rule (`resolve_auto_stage`, the function the app and
the paste eval call).

Pass rule: Earlier -> Demotic and Late -> Demotic are 0 each; anything above 0 exits 1.
Reported only: the full confusion table (true Earlier/Late x chosen Earlier/Late/
Demotic/None), abstentions, token reading accuracy with the chosen stage's model vs
the true stage's model (on the row's own sign groups, rows whose groups align one to
one with the transliteration; an abstention reads with the pooled model, as the app
does), and the number of pastes where the app's choice differs from the A2.4 decision
function recomputed from the per-stage coverage and score (a difference is written
down in the results note, not fixed).

Two coverages are recorded per paste (final eval, 2026-10-25). `coverage_<stage>` is the
app's own count, from a reading model that is also fitted on every unlabelled row
(`compatible_frame`); `own_coverage_<stage>` is A2.4's as written, counting only the
groups attested in that stage's own labelled, aligned rows. The A2.4 decision is
recomputed with each (`reference_stage`, `own_reference_stage`), and the report prints
how often the two coverages, and the app and the A2.4-as-written decision, differ.

Only aggregates are printed. Per-paste rows (ids, true stage, choice, per-stage
coverage and per-sign score) go to `--results`.

    python scripts/run_stage_routing_eval.py --seed 20261025 --per-stage 200 \\
        --results ~/egyptology-runs/remeasure-2026-10-25/routing.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.data.normalizer import normalize_hieroglyphs, search_fold  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.retrieval import resolve_auto_stage  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    DEFAULT_SEGMENTATION_WEIGHTS,
    segment_paste,
)
from app.services.stage import (  # noqa: E402
    STAGES,
    StageResources,
    build_stage_resources,
    choose_stage_by_likelihood,
    normalize_stage,
)

EXAMPLES_PATH = PROJECT_ROOT / "data" / "processed" / "examples.csv"
EARLIER, LATE, DEMOTIC = "Earlier Egyptian", "Late Egyptian", "Demotic"
# Which sources' labels count, per true stage (A2.3).
ELIGIBLE_SOURCES = {EARLIER: {"TLA"}, LATE: {"Ramses", "TLA"}}
SORT_KEYS = ["source", "source_text_id", "source_sentence_id"]
# A2.4: equal coverage abstains when the per-sign gap is at most this (not tuned).
MARGIN = 1e-9
NONE_LABEL = "None"


def eligible_rows(df: pd.DataFrame) -> pd.DataFrame:
    """A2.3's eligible set: labelled Earlier (TLA) / Late (Ramses, TLA) rows with
    signs, sorted, one row per normalised sign string. Adds `true_stage`."""
    stage = df["language_stage"].map(normalize_stage)
    source = df["source"].astype(str)
    keep = pd.Series(False, index=df.index)
    for target, sources in ELIGIBLE_SOURCES.items():
        keep |= (stage == target) & source.isin(sources)
    keep &= df["hieroglyphs_norm"].astype(str).str.strip() != ""
    eligible = df.loc[keep].assign(true_stage=stage[keep])
    eligible = eligible.sort_values(SORT_KEYS, kind="mergesort")
    return eligible.drop_duplicates("hieroglyphs_norm", keep="first")


def draw_sample(eligible: pd.DataFrame, seed: int, per_stage: int) -> pd.DataFrame:
    """Earlier then Late, one generator, `rng.choice(n, per_stage, replace=False)`.

    Raises ValueError when a stage has fewer than `per_stage` eligible rows.
    """
    rng = np.random.default_rng(seed)
    parts = []
    for target in (EARLIER, LATE):
        pool = eligible.loc[eligible["true_stage"] == target]
        if len(pool) < per_stage:
            raise ValueError(
                f"{target}: {len(pool)} eligible rows, fewer than --per-stage {per_stage}"
            )
        picks = rng.choice(len(pool), per_stage, replace=False)
        parts.append(pool.iloc[picks])
    return pd.concat(parts)


def held_out_pool(df: pd.DataFrame, sample: pd.DataFrame) -> pd.DataFrame:
    """`df` without the sampled rows, their sign-string twins and their texts."""
    drop = df.index.isin(sample.index)
    drop |= df["hieroglyphs_norm"].isin(set(sample["hieroglyphs_norm"]))
    drop |= df["source_text_id"].isin(set(sample["source_text_id"]))
    return df.loc[~drop]


def reference_decision(coverage: dict[str, int], scores: dict[str, float]) -> str | None:
    """Rule A2.4 as written, recomputed from one paste's per-stage numbers.

    Candidates are the scored stages (both guards passed). 0 -> None; 1 -> that stage
    if its coverage is above 0, else None; 2 or more -> order by (coverage desc, score
    desc); a strict coverage lead wins outright, equal coverage abstains when the
    per-sign gap is at most MARGIN.
    """
    candidates = [stage for stage in STAGES if stage in scores]
    if not candidates:
        return None
    if len(candidates) == 1:
        only = candidates[0]
        return only if coverage.get(only, 0) > 0 else None
    ranked = sorted(candidates, key=lambda s: (-coverage.get(s, 0), -scores[s]))
    first, second = ranked[0], ranked[1]
    if coverage.get(first, 0) > coverage.get(second, 0):
        return first
    return None if scores[first] - scores[second] <= MARGIN else first


def own_attested_groups(df: pd.DataFrame) -> dict[str, set[str]]:
    """Per stage, the sign groups attested in its own labelled rows whose groups and
    readings align one to one (the rows `ReadingModel.fit` learns from) - A2.4's
    "that stage's own aligned rows", without the unlabelled rows the app adds."""
    stage = df["language_stage"].map(normalize_stage)
    signs = df["hieroglyphs_norm"].fillna("").astype(str).str.split()
    readings = df["transliteration_gold"].fillna("").astype(str).str.split()
    aligned = (signs.str.len() > 0) & (signs.str.len() == readings.str.len())
    groups: dict[str, set[str]] = {}
    for target in STAGES:
        mask = aligned & (stage == target)
        groups[target] = {group for row in signs[mask] for group in row}
    return groups


def own_coverage(
    groups: list[str], scored: dict[str, float], attested: dict[str, set[str]]
) -> dict[str, int]:
    """A2.4's `c` for every scored stage: segmented groups attested in its own rows."""
    return {
        stage: sum(1 for group in groups if group in attested.get(stage, set()))
        for stage in scored
    }


def reading_hits(model, groups: list[str], gold: list[str]) -> tuple[int, int]:
    """(tokens read right, tokens) on aligned groups; (0, 0) when not aligned."""
    if not groups or len(groups) != len(gold):
        return 0, 0
    predictions = model.predict_sequence(groups)
    right = sum(
        1
        for prediction, token in zip(predictions, gold)
        if prediction.predicted and search_fold(prediction.predicted) == search_fold(token)
    )
    return right, len(gold)


def route_sample(
    sample: pd.DataFrame, get_resources, attested: dict[str, set[str]]
) -> pd.DataFrame:
    """One row per paste: the app's choice, the A2.4 recomputation and the numbers.

    `attested` is `own_attested_groups` of the pool the resources were built from.
    """
    rows = []
    for _, row in sample.iterrows():
        query = str(row["hieroglyphs"])
        chosen, _inferred, scores = resolve_auto_stage(query, get_resources)
        coverage: dict[str, int] = {}
        _audit_choice, audit_scores = choose_stage_by_likelihood(
            normalize_hieroglyphs(query), get_resources, coverage=coverage
        )
        groups = str(row["hieroglyphs_norm"]).split()
        gold = str(row["transliteration_gold"]).split()
        chosen_right, tokens = reading_hits(get_resources(chosen).reading_model, groups, gold)
        true_right, _ = reading_hits(
            get_resources(row["true_stage"]).reading_model, groups, gold
        )
        reference = reference_decision(coverage, audit_scores)
        # The groups the router scored: the pooled segmenter on the same string.
        segmentation, _as_pasted = segment_paste(
            normalize_hieroglyphs(query), get_resources(None).segmenter
        )
        own = own_coverage(list(segmentation.groups), audit_scores, attested)
        own_reference = reference_decision(own, audit_scores)
        record = {
            "source": row["source"],
            "source_text_id": row["source_text_id"],
            "source_sentence_id": row["source_sentence_id"],
            "true_stage": row["true_stage"],
            "chosen_stage": chosen or NONE_LABEL,
            "reference_stage": reference or NONE_LABEL,
            "matches_reference": (chosen or None) == reference,
            "own_reference_stage": own_reference or NONE_LABEL,
            "matches_own_reference": (chosen or None) == own_reference,
            "coverage_differs": any(
                coverage.get(stage) != own.get(stage) for stage in audit_scores
            ),
            "aligned_tokens": tokens,
            "chosen_model_right": chosen_right,
            "true_model_right": true_right,
        }
        for stage in STAGES:
            record[f"coverage_{stage}"] = coverage.get(stage, "")
            record[f"own_coverage_{stage}"] = own.get(stage, "")
            record[f"score_{stage}"] = (scores or {}).get(stage, "")
        rows.append(record)
    return pd.DataFrame(rows)


def summarize(results: pd.DataFrame) -> tuple[str, bool]:
    """The printed aggregate report, and whether the A2.3 pass rule holds."""
    columns = [EARLIER, LATE, DEMOTIC, NONE_LABEL]
    table = (
        pd.crosstab(results["true_stage"], results["chosen_stage"])
        .reindex(index=[EARLIER, LATE], columns=columns, fill_value=0)
        .fillna(0)
        .astype(int)
    )
    to_demotic = {stage: int(table.loc[stage, DEMOTIC]) for stage in (EARLIER, LATE)}
    passed = all(count == 0 for count in to_demotic.values())
    lines = ["confusion (rows = true stage, columns = chosen):", table.to_string(), ""]
    for stage in (EARLIER, LATE):
        lines.append(f"{stage} -> Demotic: {to_demotic[stage]}/{int(table.loc[stage].sum())}")
    lines.append(f"abstentions (None): {int(table[NONE_LABEL].sum())}/{len(results)}")
    tokens = int(results["aligned_tokens"].sum())
    for label, column in (("chosen stage", "chosen_model_right"), ("true stage", "true_model_right")):
        right = int(results[column].sum())
        share = f"{right / tokens:.4f}" if tokens else "n/a"
        lines.append(f"reading accuracy, {label}'s model: {share} ({right}/{tokens} aligned tokens)")
    differ = int((~results["matches_reference"].astype(bool)).sum())
    lines.append(
        "app choice differs from the A2.4 decision function (app's coverage): "
        f"{differ}/{len(results)}"
    )
    if "matches_own_reference" in results.columns:
        own_differ = int((~results["matches_own_reference"].astype(bool)).sum())
        coverage_differ = int(results["coverage_differs"].astype(bool).sum())
        lines.append(
            "app choice differs from A2.4 as written (own aligned rows' coverage): "
            f"{own_differ}/{len(results)}"
        )
        lines.append(
            "pastes whose app coverage differs from own-aligned-row coverage: "
            f"{coverage_differ}/{len(results)}"
        )
    lines.append(
        "pass rule (A2.3, Earlier -> Demotic = Late -> Demotic = 0): "
        + ("PASS" if passed else "FAIL")
    )
    return "\n".join(lines), passed


def make_resource_cache(df: pd.DataFrame, lexicon):
    """`get_resources(stage)`, built once per stage from `df`, as the paste eval does."""
    cache: dict[str | None, StageResources] = {}

    def get_resources(target: str | None) -> StageResources:
        if target not in cache:
            pooled = get_resources(None) if target is not None else None
            cache[target] = build_stage_resources(
                df,
                target,
                lexicon=lexicon,
                segmentation_weights=DEFAULT_SEGMENTATION_WEIGHTS,
                use_lexicon=True,
                pooled_reading_model=pooled.reading_model if pooled else None,
                pooled_index=pooled.index if pooled else None,
            )
        return cache[target]

    return get_resources


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--examples", default=str(EXAMPLES_PATH), help="Public corpus CSV.")
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--per-stage", type=int, default=200)
    parser.add_argument("--results", required=True, help="Per-paste CSV to write.")
    parser.add_argument(
        "--lexicon",
        default=None,
        help="Lexicon CSV (default: the app's). Pass a missing path for none.",
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(argv)
    started = time.time()
    df = load_examples_csv(args.examples)
    eligible = eligible_rows(df)
    print(f"corpus {len(df):,} rows; eligible after dedup: "
          + ", ".join(f"{s} {int((eligible['true_stage'] == s).sum()):,}" for s in (EARLIER, LATE)))
    try:
        sample = draw_sample(eligible, args.seed, args.per_stage)
    except ValueError as error:
        print(f"STOP: {error}")
        return 2
    pool = held_out_pool(df, sample)
    print(f"seed {args.seed}, {args.per_stage} per stage; pool {len(pool):,} rows "
          f"({len(df) - len(pool):,} held out)")
    # Review nit (Opus): A2.3 writes `rng.choice(len(eligible), ...)`; the only reading
    # that yields per_stage rows of each stage is a draw from each stage's own pool.
    # Printed so the interpretation is on record in the run's output.
    print("sampling: rng.choice over each stage's own eligible pool "
          "(Earlier first, then Late, one generator) - A2.3 read per stage")

    get_resources = make_resource_cache(pool, load_lexicon(args.lexicon))
    results = route_sample(sample, get_resources, own_attested_groups(pool))
    results_path = Path(args.results).expanduser()
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(results_path, index=False)

    report, passed = summarize(results)
    print(report)
    print(f"per-paste rows: {results_path}\ndone in {time.time() - started:.1f}s")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
