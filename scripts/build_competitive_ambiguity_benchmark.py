from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.suggestions import canonical_reading, loose_reading_form

EXAMPLES_PATH = "data/processed/examples.csv"
OUTPUT_PATH = "data/benchmarks/competitive_ambiguity_eval_queries.csv"

STOP_TOKENS = {"m", "n", "r", "s", "f", "k", "t", "w", "pw", "hr"}

# Rows whose closest rival is at or above this token overlap are treated as
# duplicates rather than ambiguity cases and left out of the benchmark.
MAX_TWIN_OVERLAP = 0.9


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the competitive ambiguity benchmark: rows that have real rivals "
            "in the corpus but no near-identical twin to fall back on."
        )
    )
    parser.add_argument("--examples", default=EXAMPLES_PATH, help="Corpus CSV to draw rows from.")
    parser.add_argument("--output", default=OUTPUT_PATH, help="Where to write benchmark queries.")
    parser.add_argument("--limit", type=int, default=20, help="How many benchmark rows to select.")
    parser.add_argument(
        "--max-twin-overlap",
        type=float,
        default=MAX_TWIN_OVERLAP,
        help="Exclude rows whose closest rival meets this token overlap.",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=2000,
        help=(
            "Rows scanned when looking for rivals. Selection compares every row with "
            "every other, so the full corpus would take hours; 0 scans everything."
        ),
    )
    return parser.parse_args()


def _tokens(value: object) -> list[str]:
    return [token for token in str(value).split() if token.strip()]


def _token_set(value: object) -> set[str]:
    return set(_tokens(value))


def _lemma_ids(value: object) -> list[str]:
    ids: list[str] = []
    for part in str(value).split():
        lemma_id = part.split("|", 1)[0].strip()
        if lemma_id and lemma_id not in ids:
            ids.append(lemma_id)
    return ids


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _content_tokens(tokens: list[str]) -> list[str]:
    content = [token for token in tokens if token not in STOP_TOKENS]
    return content or tokens


def _strip_some_endings(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for token in tokens:
        if len(token) > 4 and token.endswith(("t", "w", "j", "y")):
            out.append(token[:-1])
        else:
            out.append(token)
    return out


def _competitive_query(row: pd.Series, row_num: int) -> tuple[str, str, str]:
    loose = loose_reading_form(row["transliteration_gold"])
    tokens = _strip_some_endings(_tokens(loose))
    content = _content_tokens(tokens)
    query_type = [
        "simplified_transliteration",
        "partial_transliteration",
        "normalized_reading_order",
    ][(row_num - 1) % 3]

    if query_type == "partial_transliteration":
        keep = max(2, min(len(content), round(len(content) * 0.6)))
        query_tokens = content[:keep]
        notes = "Target row excluded; query keeps only high-signal partial tokens."
    elif query_type == "normalized_reading_order":
        query_tokens = _tokens(row["normalized_reading_order"])
        if len(query_tokens) > 5:
            query_tokens = query_tokens[: max(4, round(len(query_tokens) * 0.75))]
        notes = "Target row excluded; normalized reading-order key is truncated."
    else:
        query_tokens = content
        if len(query_tokens) > 8:
            query_tokens = query_tokens[:8]
        notes = "Target row excluded; editorial markers and light endings removed."

    return " ".join(query_tokens), query_type, notes


def main() -> None:
    args = _parse_args()
    df = load_examples_csv(args.examples)
    # Rival detection compares every row against every other, so cap the scan. The
    # benchmark only needs enough rows to find competitive cases, not the whole corpus.
    if args.pool_size and len(df) > args.pool_size:
        print(
            f"Corpus has {len(df)} rows; scanning the first {args.pool_size} for rival "
            "detection (selection compares every row with every other)."
        )
        df = df.head(args.pool_size)
    prepared = df.copy()
    prepared["competitive_tokens"] = prepared["transliteration_gold"].map(
        lambda value: _token_set(loose_reading_form(value))
    )
    prepared["competitive_lemma_ids"] = prepared["lemma_sequence"].map(_lemma_ids)
    prepared["competitive_canonical"] = prepared["transliteration_gold"].map(canonical_reading)

    candidates: list[tuple[int, float, int]] = []
    skipped_near_duplicate = 0
    skipped_no_distractor = 0
    skipped_too_short = 0
    for index, row in prepared.iterrows():
        target_tokens = row["competitive_tokens"]
        if len(target_tokens) < 2:
            skipped_too_short += 1
            continue
        distractors = 0
        best_overlap = 0.0
        for other_index, other in prepared.iterrows():
            if other_index == index:
                continue
            score = _overlap(target_tokens, other["competitive_tokens"])
            if score >= 0.16:
                distractors += 1
                best_overlap = max(best_overlap, score)
        if distractors == 0:
            skipped_no_distractor += 1
            continue
        # A row that has a near-identical twin elsewhere in the corpus is not an
        # ambiguity case: excluding the target still leaves its duplicate in the
        # pool, so retrieval returns the expected reading for free. Such rows
        # inflate accuracy and become more common as the corpus grows.
        if best_overlap >= args.max_twin_overlap:
            skipped_near_duplicate += 1
            continue
        candidates.append((distractors, best_overlap, int(index)))

    # Rank by genuine competition (many moderate-overlap rivals) rather than by
    # closest single match, then keep one row per distinct reading so the
    # benchmark does not repeat the same sentence in several slots.
    selected_indices: list[int] = []
    seen_readings: set[str] = set()
    for _, _, index in sorted(candidates, reverse=True):
        reading = prepared.at[index, "competitive_canonical"]
        if reading in seen_readings:
            continue
        seen_readings.add(reading)
        selected_indices.append(index)
        if len(selected_indices) >= args.limit:
            break
    selected = prepared.loc[selected_indices, :].copy()

    print(
        f"Candidate pool: {len(prepared)} rows -> {len(candidates)} eligible "
        f"(skipped {skipped_too_short} too short, {skipped_no_distractor} without "
        f"distractors, {skipped_near_duplicate} with a near-identical twin at "
        f"overlap >= {args.max_twin_overlap})"
    )

    rows: list[dict[str, str]] = []
    for row_num, (_, row) in enumerate(selected.iterrows(), start=1):
        key_tokens = sorted(row["competitive_tokens"])
        lemma_ids = row["competitive_lemma_ids"]
        query_input, query_type, notes = _competitive_query(row, row_num)
        threshold = 0.34 if len(key_tokens) <= 4 else 0.26
        rows.append(
            {
                "benchmark_id": f"COMP_{row_num:03d}",
                "query_input": query_input,
                "query_type": query_type,
                "expected_transliteration": row["transliteration_gold"],
                "expected_source_text_id": row["source_text_id"],
                "expected_source_sentence_id": row["source_sentence_id"],
                "expected_key_tokens": " ".join(key_tokens),
                "expected_lemma_ids": " ".join(lemma_ids),
                "acceptable_token_overlap_threshold": f"{threshold:.2f}",
                "notes": notes,
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"Wrote {len(rows)} competitive ambiguity benchmark rows to {output_path}")
    if len(rows) < args.limit:
        print(
            f"Note: only {len(rows)} of the requested {args.limit} rows qualified. "
            "Import more corpus rows to widen the eligible pool."
        )


if __name__ == "__main__":
    main()
