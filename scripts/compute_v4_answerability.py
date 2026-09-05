"""Rule A: is each v4 benchmark query answerable at all, with its target removed?

Pre-registered on 2026-09-05 (docs/v4-answerability-and-v5-rule.md) before any run:

    For each v4 query, exclude the expected row exactly as `_exclude_expected` does,
    then apply the harness's own `_useful_reason` to EVERY remaining corpus row (same
    functions, same per-query `acceptable_token_overlap_threshold` from the benchmark
    column — 0.26 or 0.34 — not a flat 0.26). A query is *answerable* iff at least one
    corpus row is useful under the rule. Unanswerable queries are flagged and excluded
    from the answerable-only denominator.

This asks a different question from the eval harness. The harness asks "did ranking put
a useful row in the top 3"; this asks "does a useful row exist anywhere in the corpus".
A query that is unanswerable cannot be a ranking failure — there is nothing to rank up.

Why this is not just a loop over `_useful_reason`: that function calls
`_candidate_lemmas`, which scans the whole corpus for every candidate. 20 queries ×
130,472 rows would be 2.6 million full-corpus scans. Instead the two expensive pieces
are precomputed once over the corpus —

  * `loose_reading_form` token set per distinct `transliteration_gold`, and
  * canonical reading -> union of lemma ids over the rows sharing that reading

— and the decision itself is then made by `useful_decision`, the harness's own code,
imported not copied. `--verify N` re-checks N random rows against the unrefactored
`_useful_reason` path and aborts on any disagreement.

The one subtlety the precomputation has to respect: `_candidate_lemmas` runs over the
*candidate pool*, i.e. the corpus minus this query's target row. So a lemma id that only
the target row contributes to its reading group must disappear for that query. The
per-reading lemma union is therefore rebuilt for the single affected group per query,
and a distinct transliteration attested only by the target row is skipped entirely.

Usage:
    python scripts/compute_v4_answerability.py --useful-rule v4
    python scripts/compute_v4_answerability.py --useful-rule v5
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.suggestions import canonical_reading, loose_reading_form
from scripts.run_competitive_ambiguity_eval import (  # noqa: E402
    USEFUL_RULES,
    _lemma_ids,
    _tokens,
    _useful_reason,
    useful_decision,
)

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_V4_PATH = "data/benchmarks/competitive_ambiguity_eval_queries_v4.csv"
OUT_TEMPLATE = "data/benchmarks/competitive_ambiguity_eval_answerability_{rule}.csv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--examples", default=EXAMPLES_PATH, help="Corpus CSV to search.")
    parser.add_argument(
        "--benchmark",
        default=BENCHMARK_V4_PATH,
        help="Benchmark queries CSV (defaults to v4 — the plain-named file is v1).",
    )
    parser.add_argument("--useful-rule", choices=list(USEFUL_RULES), default="v4")
    parser.add_argument("--out", default="", help="Where to write the per-query CSV.")
    parser.add_argument(
        "--verify",
        type=int,
        default=200,
        help="Cross-check the fast path against _useful_reason on N random rows (0 = skip).",
    )
    return parser.parse_args()


def _build_corpus_index(examples_df: pd.DataFrame) -> dict[str, object]:
    """Precompute everything the per-row decision needs, once."""
    text_ids = examples_df["source_text_id"].astype(str).tolist()
    sentence_ids = examples_df["source_sentence_id"].astype(str).tolist()
    readings = examples_df["transliteration_gold"].astype(str).tolist()
    lemma_cells = examples_df["lemma_sequence"].astype(str).tolist()

    # Distinct raw readings: the loose token set depends on the raw string, so this is
    # the finest grouping that is still safe to share a token set across.
    positions_by_reading: dict[str, list[int]] = defaultdict(list)
    for position, reading in enumerate(readings):
        positions_by_reading[reading].append(position)

    canon_by_reading = {reading: canonical_reading(reading) for reading in positions_by_reading}
    tokens_by_reading = {
        reading: _tokens(loose_reading_form(reading)) for reading in positions_by_reading
    }

    # canonical reading -> the rows that carry it, and the union of their lemma ids
    # (exactly what _candidate_lemmas returns for a candidate with that reading).
    positions_by_canon: dict[str, list[int]] = defaultdict(list)
    for position, reading in enumerate(readings):
        positions_by_canon[canon_by_reading[reading]].append(position)
    lemmas_by_position = [_lemma_ids(cell) for cell in lemma_cells]
    lemmas_by_canon: dict[str, set[str]] = {}
    for canon, positions in positions_by_canon.items():
        union: set[str] = set()
        for position in positions:
            union |= lemmas_by_position[position]
        lemmas_by_canon[canon] = union

    key_to_position = {
        (text_ids[position], sentence_ids[position]): position for position in range(len(readings))
    }
    return {
        "readings": readings,
        "text_ids": text_ids,
        "sentence_ids": sentence_ids,
        "positions_by_reading": positions_by_reading,
        "positions_by_canon": positions_by_canon,
        "canon_by_reading": canon_by_reading,
        "tokens_by_reading": tokens_by_reading,
        "lemmas_by_position": lemmas_by_position,
        "lemmas_by_canon": lemmas_by_canon,
        "key_to_position": key_to_position,
    }


def _scan_query(
    index: dict[str, object],
    expected: str,
    expected_key_tokens: set[str],
    expected_lemma_ids: set[str],
    token_threshold: float,
    rule: str,
    excluded_position: int | None,
) -> dict[str, object]:
    readings: list[str] = index["readings"]  # type: ignore[assignment]
    text_ids: list[str] = index["text_ids"]  # type: ignore[assignment]
    sentence_ids: list[str] = index["sentence_ids"]  # type: ignore[assignment]
    positions_by_reading: dict[str, list[int]] = index["positions_by_reading"]  # type: ignore[assignment]
    positions_by_canon: dict[str, list[int]] = index["positions_by_canon"]  # type: ignore[assignment]
    canon_by_reading: dict[str, str] = index["canon_by_reading"]  # type: ignore[assignment]
    tokens_by_reading: dict[str, set[str]] = index["tokens_by_reading"]  # type: ignore[assignment]
    lemmas_by_position: list[set[str]] = index["lemmas_by_position"]  # type: ignore[assignment]
    lemmas_by_canon: dict[str, set[str]] = index["lemmas_by_canon"]  # type: ignore[assignment]

    expected_canon = canonical_reading(expected)

    # The excluded row shrinks exactly one reading group and one canon group.
    excluded_reading = readings[excluded_position] if excluded_position is not None else None
    excluded_canon = canon_by_reading[excluded_reading] if excluded_reading is not None else None
    patched_canon_lemmas: set[str] | None = None
    if excluded_canon is not None:
        union: set[str] = set()
        for position in positions_by_canon[excluded_canon]:
            if position != excluded_position:
                union |= lemmas_by_position[position]
        patched_canon_lemmas = union

    useful_count = 0
    first_useful: tuple[str, str, str, str] | None = None
    best_token = (-1.0, "", "")
    best_lemma = (-1.0, 0, "", "")

    for reading, positions in positions_by_reading.items():
        surviving = len(positions) - (1 if excluded_reading == reading else 0)
        if surviving <= 0:
            continue
        canon = canon_by_reading[reading]
        is_exact = canon == expected_canon
        candidate_lemmas = (
            patched_canon_lemmas
            if excluded_canon is not None and canon == excluded_canon
            else lemmas_by_canon[canon]
        )
        useful, reason, token_score, lemma_score = useful_decision(
            is_exact=is_exact,
            candidate_tokens=tokens_by_reading[reading],
            candidate_lemmas=candidate_lemmas,
            expected_key_tokens=expected_key_tokens,
            expected_lemma_ids=expected_lemma_ids,
            token_threshold=token_threshold,
            rule=rule,
        )
        # A representative surviving row for reporting.
        row_position = next(
            (position for position in positions if position != excluded_position), positions[0]
        )
        row_id = f"{text_ids[row_position]}/{sentence_ids[row_position]}"
        if token_score > best_token[0]:
            best_token = (token_score, row_id, reading)
        shared = len(expected_lemma_ids & candidate_lemmas)
        if (lemma_score, shared) > (best_lemma[0], best_lemma[1]):
            best_lemma = (lemma_score, shared, row_id, reading)
        if useful:
            useful_count += surviving
            if first_useful is None:
                first_useful = (row_id, reading, reason, f"{token_score:.3f}/{lemma_score:.3f}")

    return {
        "answerable": first_useful is not None,
        "useful_row_count": useful_count,
        "first_useful_row_id": first_useful[0] if first_useful else "",
        "first_useful_transliteration": first_useful[1] if first_useful else "",
        "first_useful_reason": first_useful[2] if first_useful else "",
        "first_useful_scores": first_useful[3] if first_useful else "",
        "best_token_score": round(best_token[0], 4),
        "best_token_row_id": best_token[1],
        "best_token_transliteration": best_token[2],
        "best_lemma_score": round(best_lemma[0], 4),
        "best_lemma_intersection": best_lemma[1],
        "best_lemma_row_id": best_lemma[2],
        "best_lemma_transliteration": best_lemma[3],
    }


def _verify_fast_path(
    examples_df: pd.DataFrame,
    index: dict[str, object],
    bench_row: pd.Series,
    rule: str,
    sample_size: int,
    seed: int,
) -> list[str]:
    """Re-run the original `_useful_reason` on a random sample and compare."""
    expected = str(bench_row["expected_transliteration"])
    expected_key_tokens = _tokens(bench_row["expected_key_tokens"])
    expected_lemma_ids = _tokens(bench_row["expected_lemma_ids"])
    token_threshold = float(bench_row["acceptable_token_overlap_threshold"])
    expected_key = (
        str(bench_row["expected_source_text_id"]),
        str(bench_row["expected_source_sentence_id"]),
    )
    key_to_position: dict[tuple[str, str], int] = index["key_to_position"]  # type: ignore[assignment]
    excluded_position = key_to_position.get(expected_key)

    mask = ~(
        (examples_df["source_text_id"].astype(str) == expected_key[0])
        & (examples_df["source_sentence_id"].astype(str) == expected_key[1])
    )
    pool = examples_df.loc[mask, :].copy()

    readings: list[str] = index["readings"]  # type: ignore[assignment]
    canon_by_reading: dict[str, str] = index["canon_by_reading"]  # type: ignore[assignment]
    tokens_by_reading: dict[str, set[str]] = index["tokens_by_reading"]  # type: ignore[assignment]
    positions_by_canon: dict[str, list[int]] = index["positions_by_canon"]  # type: ignore[assignment]
    lemmas_by_position: list[set[str]] = index["lemmas_by_position"]  # type: ignore[assignment]
    lemmas_by_canon: dict[str, set[str]] = index["lemmas_by_canon"]  # type: ignore[assignment]
    excluded_canon = (
        canon_by_reading[readings[excluded_position]] if excluded_position is not None else None
    )

    rng = random.Random(seed)
    sample = rng.sample(range(len(readings)), min(sample_size, len(readings)))
    problems: list[str] = []
    for position in sample:
        if position == excluded_position:
            continue
        candidate = readings[position]
        slow = _useful_reason(
            candidate,
            candidate_pool=pool,
            expected=expected,
            expected_key_tokens=expected_key_tokens,
            expected_lemma_ids=expected_lemma_ids,
            token_threshold=token_threshold,
            rule=rule,
        )
        canon = canon_by_reading[candidate]
        if excluded_canon is not None and canon == excluded_canon:
            candidate_lemmas: set[str] = set()
            for other in positions_by_canon[canon]:
                if other != excluded_position:
                    candidate_lemmas |= lemmas_by_position[other]
        else:
            candidate_lemmas = lemmas_by_canon[canon]
        fast = useful_decision(
            is_exact=canon == canonical_reading(expected),
            candidate_tokens=tokens_by_reading[candidate],
            candidate_lemmas=candidate_lemmas,
            expected_key_tokens=expected_key_tokens,
            expected_lemma_ids=expected_lemma_ids,
            token_threshold=token_threshold,
            rule=rule,
        )
        if slow != fast:
            problems.append(f"row {position} ({candidate!r}): slow={slow} fast={fast}")
    return problems


def main() -> None:
    args = _parse_args()
    rule = args.useful_rule
    out_path = Path(args.out or OUT_TEMPLATE.format(rule=rule))

    examples_df = load_examples_csv(args.examples)
    benchmark_df = pd.read_csv(args.benchmark).fillna("")
    print(f"corpus rows: {len(examples_df)}  queries: {len(benchmark_df)}  rule: {rule}")

    index = _build_corpus_index(examples_df)
    print(
        f"distinct readings: {len(index['positions_by_reading'])}  "  # type: ignore[arg-type]
        f"distinct canonical readings: {len(index['positions_by_canon'])}"  # type: ignore[arg-type]
    )

    if args.verify:
        first_row = benchmark_df.iloc[0]
        problems = _verify_fast_path(examples_df, index, first_row, rule, args.verify, seed=20260905)
        if problems:
            for problem in problems[:10]:
                print(f"VERIFY MISMATCH: {problem}")
            raise SystemExit(f"fast path disagrees with _useful_reason on {len(problems)} rows")
        print(f"verify: fast path agrees with _useful_reason on {args.verify} random rows")

    key_to_position: dict[tuple[str, str], int] = index["key_to_position"]  # type: ignore[assignment]
    rows: list[dict[str, object]] = []
    for _, bench_row in benchmark_df.iterrows():
        expected_key = (
            str(bench_row["expected_source_text_id"]),
            str(bench_row["expected_source_sentence_id"]),
        )
        excluded_position = key_to_position.get(expected_key)
        result = _scan_query(
            index,
            expected=str(bench_row["expected_transliteration"]),
            expected_key_tokens=_tokens(bench_row["expected_key_tokens"]),
            expected_lemma_ids=_tokens(bench_row["expected_lemma_ids"]),
            token_threshold=float(bench_row["acceptable_token_overlap_threshold"]),
            rule=rule,
            excluded_position=excluded_position,
        )
        rows.append(
            {
                "benchmark_id": bench_row["benchmark_id"],
                "useful_rule": rule,
                "query_input": bench_row["query_input"],
                "query_type": bench_row["query_type"],
                "expected_transliteration": bench_row["expected_transliteration"],
                "expected_row_id": "/".join(expected_key),
                "expected_row_found_in_corpus": excluded_position is not None,
                "acceptable_token_overlap_threshold": bench_row[
                    "acceptable_token_overlap_threshold"
                ],
                "expected_lemma_id_count": len(_tokens(bench_row["expected_lemma_ids"])),
                **result,
            }
        )
        print(
            f"{bench_row['benchmark_id']}: answerable={result['answerable']} "
            f"useful_rows={result['useful_row_count']} "
            f"best_token={result['best_token_score']} "
            f"best_lemma={result['best_lemma_score']} (|∩|={result['best_lemma_intersection']})"
        )

    out_df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    answerable = int(out_df["answerable"].sum())
    print(f"\nanswerable under {rule}: {answerable}/{len(out_df)}")
    unanswerable = out_df.loc[~out_df["answerable"], "benchmark_id"].tolist()
    if unanswerable:
        print(f"unanswerable: {', '.join(str(value) for value in unanswerable)}")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
