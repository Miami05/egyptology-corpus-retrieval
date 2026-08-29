"""Leave-one-out evaluation of sign sequence -> reading.

This is the measurement that speaks to Camilla's objection. Every other benchmark
queries with a transliteration, which assumes the reading is already largely known.
Here the query is the *hieroglyphs* of a sentence whose own row has been removed from
the corpus, so the tool must propose a reading from sign evidence and parallels alone
-- the position an Egyptologist is actually in.

Two accuracies are reported:
  exact  - the gold reading is reproduced verbatim (very hard on unseen sentences)
  useful - a suggestion shares enough of the gold reading's tokens or lemmas to be a
           genuine lead, using the same rule as the competitive ambiguity benchmark
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import canonical_reading, loose_reading_form, suggest_top_readings

EXAMPLES_PATH = "data/processed/examples.csv"
RESULTS_PATH = "data/benchmarks/sign_reading_eval_results.csv"
FAILURES_PATH = "data/benchmarks/sign_reading_eval_failures.csv"

USEFUL_TOKEN_THRESHOLD = 0.30


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


def main() -> None:
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
        "--exclude-duplicates",
        action="store_true",
        help=(
            "Skip queries whose exact sign string also occurs elsewhere in the corpus. "
            "This corpus is formulaic, so without this the score partly measures "
            "memorisation of a twin rather than prediction."
        ),
    )
    args = parser.parse_args()

    df = load_examples_csv(args.examples)
    have_signs = df[df["hieroglyphs_norm"].astype(str).str.strip() != ""].copy()
    print(f"corpus {len(df)} rows; {len(have_signs)} carry hieroglyphs")

    targets = have_signs
    if args.exclude_duplicates:
        counts = have_signs["hieroglyphs_norm"].astype(str).value_counts()
        unique_signs = set(counts[counts == 1].index)
        before = len(targets)
        targets = targets[targets["hieroglyphs_norm"].astype(str).isin(unique_signs)]
        print(
            f"excluded {before - len(targets)} rows whose sign string recurs in the "
            "corpus; a twin would make retrieval trivial"
        )
    if args.min_signs > 1:
        targets = targets[
            targets["hieroglyphs_norm"].astype(str).str.split().map(len)
            >= args.min_signs
        ]
    if args.limit:
        targets = targets.head(args.limit)
    print(f"evaluating {len(targets)} sign queries (leave-one-out)\n")

    rows: list[dict] = []
    exact1 = exact3 = useful1 = useful3 = 0
    reciprocal = 0.0

    for position, (_, target) in enumerate(targets.iterrows(), start=1):
        pool = df[
            ~(
                (df["source_text_id"] == target["source_text_id"])
                & (df["source_sentence_id"] == target["source_sentence_id"])
            )
        ]
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
                    matches = pool[
                        pool["transliteration_gold"].map(canonical_reading)
                        == canonical_reading(candidate)
                    ]
                    cand_lemmas: set[str] = set()
                    for value in matches["lemma_sequence"]:
                        cand_lemmas |= _lemma_ids(value)
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

    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.results, index=False)
    results[~results["top3_useful"]].to_csv(args.failures, index=False)
    print(f"\nSaved results to {args.results}")
    print(f"Saved failures to {args.failures}")


if __name__ == "__main__":
    main()
