"""Build the competitive ambiguity benchmark.

A benchmark row must have real rivals in the corpus but *no near-identical twin*:
the eval excludes the target row, so if a duplicate remains in the corpus the
expected reading is handed over for free and the score measures memorisation.

The twin check runs against the **whole corpus**, not a scan pool. It used to run
only inside the builder's 2,000-row candidate pool while the eval loaded all 12,772
rows, so a twin outside the pool was invisible to the guard and present at eval time
— 11 of the 20 selected rows turned out to have one, 7 of them identical. An
inverted index over rare tokens makes the full-corpus check affordable: instead of
163 million pairwise comparisons, each row is compared only with rows that share at
least one of its tokens.

Three flags narrow *candidacy* and nothing else — `--pool-size`, `--exclude-benchmark`
(repeatable) and `--stage` — and they all share one invariant, because breaking it
would be the same bug three times over: **twin detection always runs against the whole
corpus**. The eval loads the whole corpus, so a candidate whose edition twin sits
outside the narrowed candidate set would still be handed its expected reading for free
at eval time. `--stage` was added on 2026-09-05 to build LE-v1, the Late Egyptian
evaluation set (docs/late-egyptian-eval-set-2026-09-05.md); `--exclude-benchmark`
became repeatable in the same change so LE-v1 could be held out from v4 *and* from
held-out 1 at once.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.stage import normalize_stage
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
        "--exclude-benchmark",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Path to an existing benchmark CSV whose expected rows must not appear "
            "in this one. Those rows, and every corpus row within --max-twin-overlap "
            "of one of them (the same duplicate test used below), are removed from "
            "the *candidate* set. Twin detection still runs against the full corpus. "
            "This is how a held-out validation set disjoint from a frozen benchmark "
            "is built: the selection itself is deterministic — the builder ranks by "
            "number of genuine rivals and has no random seed — so disjointness comes "
            "from the exclusion, not from reseeding. Repeatable: pass the flag once "
            "per file to stay disjoint from several existing sets at once (LE-v1 is "
            "held out from v4 *and* from held-out 1). Repeating it is exactly "
            "equivalent to concatenating the files' expected rows — the union of the "
            "seed rows is taken before the near-twin sweep, so a row named by either "
            "file is excluded and no file's exclusions can mask another's."
        ),
    )
    parser.add_argument(
        "--exhaustive-twins",
        action="store_true",
        help=(
            "Use exhaustive_best_twin_overlap for the near-identical-twin guard "
            "instead of relying on rivals_for, whose 4,000-entry postings cap can "
            "miss a twin made entirely of frequent tokens (two v4 rows have one). "
            "Required for a held-out validation set; off by default so the frozen "
            "benchmarks stay reproducible."
        ),
    )
    parser.add_argument(
        "--id-prefix",
        default="COMP",
        help="Prefix for generated benchmark_id values (default COMP).",
    )
    parser.add_argument(
        "--stage",
        default="",
        help=(
            "Restrict benchmark *candidates* to corpus rows whose `language_stage` "
            "cell equals this exact string (e.g. 'Late Egyptian'). Empty (default) "
            "considers every row, so existing callers are unaffected. Like "
            "--pool-size and --exclude-benchmark, this narrows candidacy ONLY: twin "
            "detection still runs against the whole corpus, because the eval loads "
            "the whole corpus — a Late Egyptian row whose edition twin is a BBAW row "
            "would otherwise be handed its own answer for free. The corpus column is "
            "matched verbatim rather than through normalize_stage, so the flag names "
            "exactly the population it selects."
        ),
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=0,
        help=(
            "Rows considered as benchmark *candidates* (0 = all). Twin detection "
            "always runs against the full corpus regardless of this value."
        ),
    )
    return parser.parse_args()


def build_token_index(token_sets: list[set[str]]) -> dict[str, list[int]]:
    """token -> row indices containing it."""
    index: dict[str, list[int]] = defaultdict(list)
    for row_index, tokens in enumerate(token_sets):
        for token in tokens:
            index[token].append(row_index)
    return index


def rivals_for(
    row_index: int,
    token_sets: list[set[str]],
    token_index: dict[str, list[int]],
    min_overlap: float,
    max_candidates_per_token: int = 4000,
) -> tuple[int, float]:
    """(number of rivals above min_overlap, best overlap) against the whole corpus.

    Only rows sharing at least one token can reach a positive Jaccard overlap, so
    the index gives an exact answer while touching a small fraction of the corpus.
    Ubiquitous tokens (particles present in thousands of rows) are skipped for
    candidate *generation* only — a row sharing nothing but `n` cannot reach the
    overlap threshold anyway.
    """
    target = token_sets[row_index]
    if not target:
        return 0, 0.0
    candidates: set[int] = set()
    for token in target:
        postings = token_index.get(token, ())
        if len(postings) > max_candidates_per_token:
            continue
        candidates.update(postings)
    candidates.discard(row_index)

    rivals = 0
    best = 0.0
    for other in candidates:
        other_tokens = token_sets[other]
        shared = len(target & other_tokens)
        if not shared:
            continue
        score = shared / len(target | other_tokens)
        if score >= min_overlap:
            rivals += 1
            if score > best:
                best = score
    return rivals, best


def twin_probe_count(size: int, threshold: float) -> int:
    """How many of a row's rarest tokens the exhaustive twin scan must probe.

    If |A∩B| / |A∪B| >= t then |A∩B| >= t·|A|, so a twin B misses at most
    floor((1-t)·|A|) of A's tokens and must contain one of A's floor((1-t)·|A|) + 1
    rarest ones. The arithmetic has to be exact: in binary floating point
    `(1.0 - 0.9) * 10` is 0.9999999999999998, so `int()` gave 0 instead of 1 and the
    scan probed one token too few whenever (1-t)·|A| was a whole number. A ten-token
    row then missed a nine-token twin at exactly Jaccard 0.90 — reported and fixed
    2026-09-05. `Fraction(str(t))` reads the threshold as the decimal that was typed,
    and the floor is taken on the exact rational.
    """
    if size <= 0:
        return 0
    may_miss = int((1 - Fraction(str(threshold))) * size)
    return may_miss + 1


def exhaustive_best_twin_overlap(
    row_index: int,
    token_sets: list[set[str]],
    token_index: dict[str, list[int]],
    threshold: float,
) -> tuple[float, int | None]:
    """Highest Jaccard >= `threshold` against the whole corpus, with no postings cap.

    `rivals_for` skips any token whose postings list is longer than 4,000, which is
    right for *counting rivals* at overlap 0.16 (a row sharing nothing but `n` can
    never reach it) but wrong for *twin detection*: two editions of the same sentence
    built entirely from frequent tokens share every one of them, and every one of
    those postings lists is skipped, so the twin is never seen. Two v4 rows
    (COMP_004, COMP_017) have exactly such a twin.

    Exhaustive without scanning the corpus, by prefix filtering. If
    |A∩B| / |A∪B| >= t then |A∩B| >= t·|A|, so B may miss at most
    floor((1-t)·|A|) of A's tokens; by the pigeonhole principle B must therefore
    contain at least one of A's floor((1-t)·|A|) + 1 *rarest* tokens. Scanning only
    those postings lists is guaranteed to find every twin, and they are the shortest
    lists there are.

    Returns (best overlap at or above `threshold`, that row's index) or (0.0, None).
    """
    target = token_sets[row_index]
    if not target:
        return 0.0, None
    by_rarity = sorted(target, key=lambda token: len(token_index.get(token, ())))
    probes = by_rarity[: twin_probe_count(len(target), threshold)]
    candidates: set[int] = set()
    for token in probes:
        candidates.update(token_index.get(token, ()))
    candidates.discard(row_index)
    best = 0.0
    best_index: int | None = None
    for other in candidates:
        other_tokens = token_sets[other]
        shared = len(target & other_tokens)
        if not shared:
            continue
        score = shared / len(target | other_tokens)
        if score >= threshold and score > best:
            best = score
            best_index = other
    return best, best_index


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


# A generated query must carry enough signal to be answerable at all. A single
# ubiquitous token ("z" is in thousands of rows) asks the ranker to pick one of
# thousands of equally-matching sentences — the resulting failure measures nothing.
# One *rare* token is a fair question, so the rule is: at least two tokens, or one
# token appearing in under this share of the corpus.
MAX_SINGLE_TOKEN_DOC_SHARE = 0.005


def query_has_signal(
    query: str, frequencies: dict[str, int], corpus_size: int
) -> bool:
    tokens = _tokens(query)
    if len(tokens) >= 2:
        return True
    if not tokens:
        return False
    share = frequencies.get(tokens[0], 0) / max(corpus_size, 1)
    return share <= MAX_SINGLE_TOKEN_DOC_SHARE


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
    prepared = df.copy()
    prepared["competitive_tokens"] = prepared["transliteration_gold"].map(
        lambda value: _token_set(loose_reading_form(value))
    )
    prepared["competitive_lemma_ids"] = prepared["lemma_sequence"].map(_lemma_ids)
    prepared["competitive_canonical"] = prepared["transliteration_gold"].map(canonical_reading)

    # Twin detection always sees the whole corpus — the eval does, so the guard must.
    corpus_token_sets = list(prepared["competitive_tokens"])
    token_index = build_token_index(corpus_token_sets)
    print(
        f"Twin detection over the full corpus: {len(corpus_token_sets)} rows, "
        f"{len(token_index)} distinct tokens."
    )

    # Candidate rows may be capped for speed; the twin check above is not.
    candidate_positions = range(len(prepared))
    if args.pool_size and len(prepared) > args.pool_size:
        print(f"Considering the first {args.pool_size} rows as benchmark candidates.")
        candidate_positions = range(args.pool_size)

    # Rows an existing benchmark already spends, plus anything close enough to one of
    # them to be the same sentence (the builder's own duplicate test, same
    # threshold). Removing both is what makes a held-out set genuinely held out: a
    # near-twin of a v4 target would let the new set be answered by v4 evidence.
    excluded_positions: set[int] = set()
    exclude_paths = list(args.exclude_benchmark or [])
    if exclude_paths:
        # The union of every named file's expected rows is taken *before* the
        # near-twin sweep below, so passing the flag twice is the same as passing
        # one concatenated file and no file's exclusions can mask another's.
        keys: set[tuple[str, str]] = set()
        for exclude_path in exclude_paths:
            previous = pd.read_csv(exclude_path).fillna("")
            keys |= {
                (str(row["expected_source_text_id"]), str(row["expected_source_sentence_id"]))
                for _, row in previous.iterrows()
            }
        row_keys = [
            (str(text_id), str(sentence_id))
            for text_id, sentence_id in zip(
                prepared["source_text_id"], prepared["source_sentence_id"]
            )
        ]
        seed_positions = [
            position for position, key in enumerate(row_keys) if key in keys
        ]
        excluded_positions.update(seed_positions)
        for position in seed_positions:
            target = corpus_token_sets[position]
            if not target:
                continue
            # Exhaustive by construction (prefix filtering, no postings cap), so an
            # excluded row's edition twin cannot survive into the held-out set.
            by_rarity = sorted(target, key=lambda token: len(token_index.get(token, ())))
            neighbours: set[int] = set()
            for token in by_rarity[: twin_probe_count(len(target), args.max_twin_overlap)]:
                neighbours.update(token_index.get(token, ()))
            for other in neighbours:
                shared = len(target & corpus_token_sets[other])
                if not shared:
                    continue
                if shared / len(target | corpus_token_sets[other]) >= args.max_twin_overlap:
                    excluded_positions.add(other)
        print(
            f"Excluding {len(seed_positions)} rows named by "
            f"{', '.join(exclude_paths)} and "
            f"{len(excluded_positions) - len(seed_positions)} near-twins of them "
            f"(overlap >= {args.max_twin_overlap})."
        )

    # Candidate rows may also be restricted to one language stage (--stage). This is
    # a candidacy filter, nothing more: `corpus_token_sets` and `token_index` above
    # were built from the whole corpus and are what every twin test below consults.
    corpus_stages = (
        [str(value).strip() for value in prepared["language_stage"]]
        if "language_stage" in prepared.columns
        else [""] * len(prepared)
    )
    if args.stage:
        print(
            f"Restricting candidates to language_stage == {args.stage!r} "
            f"({sum(1 for value in corpus_stages if value == args.stage)} of "
            f"{len(corpus_stages)} corpus rows); twin detection stays whole-corpus."
        )

    positional_index = list(prepared.index)
    candidates: list[tuple[int, float, int]] = []
    skipped_excluded = 0
    skipped_wrong_stage = 0
    skipped_near_duplicate = 0
    skipped_no_distractor = 0
    skipped_too_short = 0
    for position in candidate_positions:
        if position in excluded_positions:
            skipped_excluded += 1
            continue
        if args.stage and corpus_stages[position] != args.stage:
            skipped_wrong_stage += 1
            continue
        index = positional_index[position]
        target_tokens = corpus_token_sets[position]
        if len(target_tokens) < 2:
            skipped_too_short += 1
            continue
        distractors, best_overlap = rivals_for(
            position, corpus_token_sets, token_index, min_overlap=0.16
        )
        if distractors == 0:
            skipped_no_distractor += 1
            continue
        if args.exhaustive_twins:
            # rivals_for's postings cap can hide a twin built from frequent tokens
            # (see exhaustive_best_twin_overlap). Take the larger of the two.
            exhaustive_overlap, _ = exhaustive_best_twin_overlap(
                position, corpus_token_sets, token_index, args.max_twin_overlap
            )
            best_overlap = max(best_overlap, exhaustive_overlap)
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
        # Take a surplus: the signal filter below drops some, and the benchmark
        # should still end up with `limit` usable rows.
        if len(selected_indices) >= args.limit * 3:
            break
    selected = prepared.loc[selected_indices, :].copy()

    stage_note = (
        f"{skipped_wrong_stage} outside language_stage {args.stage!r}, "
        if args.stage
        else ""
    )
    print(
        f"Candidates considered: {len(list(candidate_positions))} rows -> "
        f"{len(candidates)} eligible (skipped {skipped_excluded} excluded by "
        f"--exclude-benchmark, {stage_note}{skipped_too_short} too short, "
        f"{skipped_no_distractor} without distractors, {skipped_near_duplicate} "
        f"with a near-identical twin anywhere in the corpus at overlap >= "
        f"{args.max_twin_overlap})"
    )

    # Document frequencies over the loose forms, for the single-token signal rule.
    token_document_frequency: dict[str, int] = defaultdict(int)
    for tokens in corpus_token_sets:
        for token in tokens:
            token_document_frequency[token] += 1

    rows: list[dict[str, str]] = []
    skipped_no_signal = 0
    for row_num, (_, row) in enumerate(selected.iterrows(), start=1):
        key_tokens = sorted(row["competitive_tokens"])
        lemma_ids = row["competitive_lemma_ids"]
        query_input, query_type, notes = _competitive_query(row, row_num)
        if not query_has_signal(
            query_input, token_document_frequency, len(corpus_token_sets)
        ):
            skipped_no_signal += 1
            continue
        threshold = 0.34 if len(key_tokens) <= 4 else 0.26
        rows.append(
            {
                "benchmark_id": f"{args.id_prefix}_{row_num:03d}",
                "query_input": query_input,
                "query_type": query_type,
                "expected_transliteration": row["transliteration_gold"],
                "expected_source_text_id": row["source_text_id"],
                "expected_source_sentence_id": row["source_sentence_id"],
                "expected_key_tokens": " ".join(key_tokens),
                "expected_lemma_ids": " ".join(lemma_ids),
                "acceptable_token_overlap_threshold": f"{threshold:.2f}",
                "notes": notes,
                # The declared stage for `run_competitive_ambiguity_eval.py --stage
                # declared`, taken straight from the selected row's own corpus cell
                # (normalized_stage's vocabulary: one of STAGES, or blank for the
                # `Unspecified (...)` rows). v4's column of the same name was derived
                # post hoc by derive_v4_declared_stage; this one needs no derivation
                # because the corpus states it. Without the column, a `declared` run
                # declares nothing and silently degenerates to a pooled run.
                "language_stage": normalize_stage(row.get("language_stage", "")) or "",
            }
        )
        if len(rows) >= args.limit:
            break

    if skipped_no_signal:
        print(
            f"Dropped {skipped_no_signal} selected rows whose generated query was a "
            "single ubiquitous token (no retrievable signal)."
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
