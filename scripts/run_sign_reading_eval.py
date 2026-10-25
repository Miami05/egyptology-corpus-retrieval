"""Leave-one-out evaluation of sign sequence -> reading.

This is the measurement that speaks to Camilla's objection. Every other benchmark
queries with a transliteration, which assumes the reading is already largely known.
Here the query is the *hieroglyphs* of a sentence whose own row has been removed from
the corpus, so the tool must propose a reading from sign evidence and parallels alone
-- the position an Egyptologist is actually in.

Duplicate handling (audit A56): duplicate exclusion is ON by default. It skips targets
whose exact sign string recurs (as it always did) and now also removes from each
target's retrieval pool every row whose sign-group Jaccard with the target is at least
`--near-duplicate-overlap` (0.8) and every row with the same reading, so a near-copy
cannot be "predicted" by copying it. `--no-exclude-duplicates` restores the old default
and `--exclude-duplicates --near-duplicate-overlap 0` the old exact-only rule. Results
go to NEW `*_v2.csv` files so the committed sign_reading_eval*.csv, produced under the
old semantics, are never overwritten.

Two accuracies are reported:
  exact  - the gold reading is reproduced verbatim (very hard on unseen sentences)
  useful - a suggestion shares enough of the gold reading's tokens or lemmas to be a
           genuine lead, using the same rule as the competitive ambiguity benchmark
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import canonical_reading, loose_reading_form, suggest_top_readings
from scripts.build_competitive_ambiguity_benchmark import build_token_index
from scripts.eval_guards import folded_keys, twin_rows

EXAMPLES_PATH = "data/processed/examples.csv"
# NEW names on purpose (audit A56): the committed sign_reading_eval_results.csv and
# _failures.csv were measured with duplicate exclusion off and must stay as the
# legacy record, not be mixed with numbers from the new defaults.
RESULTS_PATH = "data/benchmarks/sign_reading_eval_results_v2.csv"
FAILURES_PATH = "data/benchmarks/sign_reading_eval_failures_v2.csv"

USEFUL_TOKEN_THRESHOLD = 0.30
NEAR_DUPLICATE_OVERLAP = 0.8


def _tokens(value: object) -> set[str]:
    return {token for token in str(value).split() if token.strip()}


def _lemma_ids(value: object) -> set[str]:
    ids: set[str] = set()
    for part in str(value).split():
        lemma_id = part.split("|", 1)[0].strip()
        if lemma_id:
            ids.add(lemma_id)
    return ids


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class SignDuplicateGuard:
    """Which pool rows are copies of a target: same reading, or near-same sign groups.

    Built once over the whole corpus. `removals(position)` returns the positions that
    must leave that target's pool besides the target's own sentence: rows with the
    same canonical reading (written with other signs or in another edition) and rows
    whose sign-group set has Jaccard >= `overlap` with the target's. `overlap` 0
    removes nothing, which is the legacy behaviour.
    """

    def __init__(self, df: pd.DataFrame, overlap: float) -> None:
        self.overlap = overlap
        self.sign_sets: list[set[str]] = []
        self.index: dict[str, list[int]] = {}
        self.keys: list[str] = folded_keys(df)
        self.by_key: dict[str, list[int]] = defaultdict(list)
        for position, key in enumerate(self.keys):
            self.by_key[key].append(position)
        if overlap > 0:
            self.sign_sets = [set(str(value).split()) for value in df["hieroglyphs_norm"]]
            self.index = build_token_index(self.sign_sets)

    def removals(self, position: int) -> set[int]:
        if self.overlap <= 0:
            return set()
        out = {
            other
            for other, _ in twin_rows(
                self.sign_sets[position], self.sign_sets, self.index, self.overlap
            )
        }
        key = self.keys[position]
        if key:
            out.update(self.by_key[key])
        out.discard(position)
        return out


def pool_keep_mask(
    df: pd.DataFrame, target: pd.Series, extra_removed: "set[int] | None" = None
) -> np.ndarray:
    """Boolean mask over `df` rows that stay in the target's pool (positional)."""
    keep = ~(
        (df["source_text_id"] == target["source_text_id"])
        & (df["source_sentence_id"] == target["source_sentence_id"])
    ).to_numpy()
    if extra_removed:
        keep[list(extra_removed)] = False
    return keep


def source_table(results: pd.DataFrame) -> pd.DataFrame:
    """Per-source accuracy: the pooled number hides that TLA, AES, BBAW and Ramses differ."""
    grouped = results.groupby("source")
    return pd.DataFrame(
        {
            "queries": grouped.size(),
            "top1_exact": grouped["top1_exact"].mean().round(4),
            "top3_exact": grouped["top3_exact"].mean().round(4),
            "top3_useful": grouped["top3_useful"].mean().round(4),
            "mean_pool_rows_removed": grouped["pool_rows_removed"].mean().round(2),
        }
    )


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--results", default=RESULTS_PATH)
    parser.add_argument("--failures", default=FAILURES_PATH)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Evaluate only the first N rows that have hieroglyphs (0 = all).",
    )
    parser.add_argument(
        "--min-signs",
        type=int,
        default=1,
        help="Skip queries with fewer than this many sign groups.",
    )
    parser.add_argument(
        "--stride-sample",
        type=int,
        default=0,
        help=(
            "Evaluate N targets taken every k-th over ALL targets (deterministic), so "
            "every source is represented. Drawn before the duplicate skip, so runs with "
            "different duplicate settings share the same sample. --limit takes the first "
            "N rows, which is TLA only; use this for a quick, comparable sample. 0 = off."
        ),
    )
    parser.add_argument(
        "--exclude-duplicates",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "On by default (audit A56). Skip queries whose exact sign string also "
            "occurs elsewhere in the corpus and, with --near-duplicate-overlap, drop "
            "near-copies from the pool. This corpus is formulaic, so without this the "
            "score partly measures memorisation of a twin rather than prediction. "
            "--no-exclude-duplicates restores the old default (nothing excluded)."
        ),
    )
    parser.add_argument(
        "--near-duplicate-overlap",
        type=float,
        default=NEAR_DUPLICATE_OVERLAP,
        help=(
            "With duplicate exclusion on: remove from each target's pool every row whose "
            "sign-group Jaccard with the target is at least this, and every row with the "
            "same reading. 0 = off (the old exact-only rule)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> None:
    args = _parse_args(argv)

    df = load_examples_csv(args.examples).reset_index(drop=True)
    have_signs = df[df["hieroglyphs_norm"].astype(str).str.strip() != ""].copy()
    print(f"corpus {len(df)} rows; {len(have_signs)} carry hieroglyphs")

    targets = have_signs
    if args.min_signs > 1:
        targets = targets[
            targets["hieroglyphs_norm"].astype(str).str.split().map(len)
            >= args.min_signs
        ]
    if args.stride_sample and len(targets) > args.stride_sample:
        # Taken BEFORE the duplicate skip below, so the same N targets are drawn
        # whatever the duplicate settings are and runs under different settings can be
        # compared query for query (the skip then removes a few of them).
        targets = targets.iloc[:: max(1, len(targets) // args.stride_sample)].head(
            args.stride_sample
        )
    if args.exclude_duplicates:
        counts = have_signs["hieroglyphs_norm"].astype(str).value_counts()
        unique_signs = set(counts[counts == 1].index)
        before = len(targets)
        targets = targets[targets["hieroglyphs_norm"].astype(str).isin(unique_signs)]
        print(
            f"excluded {before - len(targets)} rows whose sign string recurs in the "
            "corpus; a twin would make retrieval trivial"
        )
    if args.limit:
        targets = targets.head(args.limit)
    print(f"evaluating {len(targets)} sign queries (leave-one-out)\n")

    guard = SignDuplicateGuard(df, args.near_duplicate_overlap if args.exclude_duplicates else 0.0)
    # Canonical reading -> row positions, for the lemma lookup below (the old code
    # re-mapped canonical_reading over the whole pool for every candidate).
    rows_by_key = guard.by_key
    lemma_ids_by_row = [_lemma_ids(value) for value in df["lemma_sequence"]]

    rows: list[dict] = []
    exact1 = exact3 = useful1 = useful3 = 0
    reciprocal = 0.0

    for position, (target_position, target) in enumerate(targets.iterrows(), start=1):
        removed = guard.removals(target_position)
        keep = pool_keep_mask(df, target, removed)
        pool = df.loc[keep, :]
        excluded = set(np.flatnonzero(~keep).tolist())
        query = str(target["hieroglyphs"])
        gold = str(target["transliteration_gold"])
        gold_key = canonical_reading(gold)
        gold_tokens = _tokens(loose_reading_form(gold))
        gold_lemmas = _lemma_ids(target["lemma_sequence"])

        retrieved = retrieve_top_k(pool, query_mdc=query, k=min(50, len(pool)))
        suggestions = suggest_top_readings(
            retrieved, query_mdc=query, top_n=3
        )

        exact_rank = None
        useful_rank = None
        for rank, suggestion in enumerate(suggestions, start=1):
            candidate = suggestion.candidate_transliteration
            if exact_rank is None and canonical_reading(candidate) == gold_key:
                exact_rank = rank
            if useful_rank is None:
                cand_tokens = _tokens(loose_reading_form(candidate))
                if _overlap(gold_tokens, cand_tokens) >= USEFUL_TOKEN_THRESHOLD:
                    useful_rank = rank
                else:
                    cand_lemmas: set[str] = set()
                    for row_position in rows_by_key.get(canonical_reading(candidate), ()):
                        if row_position not in excluded:
                            cand_lemmas |= lemma_ids_by_row[row_position]
                    shared = gold_lemmas & cand_lemmas
                    if len(shared) >= 2:
                        useful_rank = rank

        if exact_rank == 1:
            exact1 += 1
        if exact_rank is not None and exact_rank <= 3:
            exact3 += 1
        if useful_rank == 1:
            useful1 += 1
        if useful_rank is not None and useful_rank <= 3:
            useful3 += 1
        if useful_rank is not None:
            reciprocal += 1.0 / useful_rank

        rows.append(
            {
                "source_text_id": target["source_text_id"],
                "source_sentence_id": target["source_sentence_id"],
                "sign_query": query,
                "sign_group_count": len(str(target["hieroglyphs_norm"]).split()),
                "gold_transliteration": gold,
                "exact_rank": exact_rank or "",
                "useful_rank": useful_rank or "",
                "top1_exact": exact_rank == 1,
                "top3_exact": exact_rank is not None and exact_rank <= 3,
                "top1_useful": useful_rank == 1,
                "top3_useful": useful_rank is not None and useful_rank <= 3,
                "suggestions": " || ".join(
                    s.candidate_transliteration for s in suggestions
                ),
                "confidences": " || ".join(
                    f"{s.confidence_score:.3f}" for s in suggestions
                ),
                # Appended last (audit A56): which corpus source the target is from and
                # how many near-copies were taken out of its pool.
                "source": target["source"],
                "pool_rows_removed": len(removed),
            }
        )
        if position % 50 == 0:
            print(f"  ...{position}/{len(targets)}")

    results = pd.DataFrame(rows)
    total = len(results) or 1
    print("\nSign -> reading evaluation (leave-one-out, query = hieroglyphs only):")
    for label, value in [
        ("queries", len(results)),
        ("top1_exact_accuracy", round(exact1 / total, 4)),
        ("top3_exact_accuracy", round(exact3 / total, 4)),
        ("top1_useful_accuracy", round(useful1 / total, 4)),
        ("top3_useful_accuracy", round(useful3 / total, 4)),
        ("mrr_useful", round(reciprocal / total, 4)),
        ("failures", int((~results["top3_useful"]).sum()) if len(results) else 0),
    ]:
        print(f"{label}: {value}")
    if len(results):
        print(f"pool_rows_removed_mean: {results['pool_rows_removed'].mean():.2f}")
        print(f"pool_rows_removed_max: {int(results['pool_rows_removed'].max())}")
        print("\nPer source:")
        print(source_table(results).to_string())

    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.results, index=False)
    results[~results["top3_useful"]].to_csv(args.failures, index=False)
    print(f"\nSaved results to {args.results}")
    print(f"Saved failures to {args.failures}")


if __name__ == "__main__":
    main()
