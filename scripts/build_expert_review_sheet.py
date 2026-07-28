"""Build a review sheet an Egyptologist can actually work through.

The raw error file has 651 rows, but most are not worth a specialist's attention: about
40% are the same reading with editorial brackets in a different place (`z(my).t` vs
`z(my.)t`), and many of the rest differ only by a restored ending (`nb` vs `nb(.t)`).
Handing those over would waste the one resource that is hardest to get.

So disagreements are classified into three tiers and the sheet leads with the tier where
expert judgement genuinely decides something:

  different_lexeme  the two readings are different words (𓃾 as `kꜣ` "bull" or `ꞽḥ` "ox")
  ending_or_suffix  same word, different grammatical ending (`nb` vs `nb(.t)`)
  editorial_only    same reading, different bracketing — excluded by default

Each row carries the sentence context, the model's choice, every attested alternative
with its share, and empty columns for the reviewer's verdict. The TLA editorial reading
is shown in its own clearly labelled column: it is itself an editorial decision, not
ground truth, and the point of the exercise is to find where a specialist would differ.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.suggestions import loose_reading_form

ERRORS_PATH = "data/benchmarks/reading_model_errors_clean.csv"
OUTPUT_PATH = "data/benchmarks/expert_review_sheet.csv"


def _loose(value: object) -> str:
    return loose_reading_form(value).strip()


def classify(gold: str, prediction: str) -> str:
    """How substantive is the disagreement?"""
    gold_loose, prediction_loose = _loose(gold), _loose(prediction)
    if gold_loose == prediction_loose:
        return "editorial_only"
    gold_tokens, prediction_tokens = gold_loose.split(), prediction_loose.split()
    if not gold_tokens or not prediction_tokens:
        return "different_lexeme"
    # Same first token means the same base word with a different ending or suffix;
    # a different first token means a different word is being proposed.
    if gold_tokens[0] == prediction_tokens[0]:
        return "ending_or_suffix"
    # One reading being a prefix of the other is still an ending difference.
    if gold_loose.startswith(prediction_loose) or prediction_loose.startswith(gold_loose):
        return "ending_or_suffix"
    return "different_lexeme"


def candidate_support(candidates: str, reading: str, attested_count: int) -> int:
    """Approximate how often a reading is attested, from the stored share string.

    `candidates` looks like "n:0.77 | n(.ꞽ):0.21", i.e. shares of the sign's total, so
    multiplying by the total recovers the count closely enough to filter on.
    """
    for part in str(candidates).split("|"):
        name, _, share = part.strip().rpartition(":")
        if name.strip() == reading.strip():
            try:
                return round(float(share) * attested_count)
            except ValueError:
                return 0
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--errors", default=ERRORS_PATH)
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Cases to include. Keep it small enough that a specialist will finish it.",
    )
    parser.add_argument(
        "--include-editorial",
        action="store_true",
        help="Include bracket-only disagreements (off by default; they waste review time).",
    )
    parser.add_argument(
        "--max-per-sign",
        type=int,
        default=2,
        help=(
            "Cap cases per sign. One frequent sign otherwise fills the sheet and the "
            "reviewer sees no variety."
        ),
    )
    parser.add_argument(
        "--min-support",
        type=int,
        default=3,
        help=(
            "Require both competing readings to be attested at least this often. "
            "A reading used once against a sign used 2,000 times is usually a slip in "
            "the sign/reading alignment, not a real alternative, and asking a "
            "specialist to adjudicate it wastes the review."
        ),
    )
    args = parser.parse_args()

    errors = pd.read_csv(args.errors).fillna("")
    errors["disagreement_type"] = errors.apply(
        lambda row: classify(row["gold_reading"], row["context_prediction"]), axis=1
    )

    counts = errors["disagreement_type"].value_counts().to_dict()
    print("Disagreements by type:")
    for name in ("different_lexeme", "ending_or_suffix", "editorial_only"):
        print(f"  {name:<18} {counts.get(name, 0)}")

    pool = errors
    if not args.include_editorial:
        pool = pool[pool["disagreement_type"] != "editorial_only"]

    if args.min_support:
        before = len(pool)
        supported = pool.apply(
            lambda row: min(
                candidate_support(
                    row["candidates"], row["context_prediction"], row["attested_count"]
                ),
                candidate_support(
                    row["candidates"], row["gold_reading"], row["attested_count"]
                ),
            )
            >= args.min_support,
            axis=1,
        )
        pool = pool[supported]
        print(
            f"\nDropped {before - len(pool)} cases where one reading is attested fewer "
            f"than {args.min_support} times (likely alignment slips, not alternatives)."
        )

    # One row per distinct dispute: the same sign/reading pair recurring 65 times is one
    # question, not 65. Keep the best-attested instance of each.
    pool = pool.sort_values("attested_count", ascending=False)
    pool = pool.drop_duplicates(subset=["sign", "gold_reading", "context_prediction"])

    # Lead with genuine lexical choices, then endings; within a tier prefer the
    # best-attested signs, where a wrong reading matters most.
    tier_order = {"different_lexeme": 0, "ending_or_suffix": 1, "editorial_only": 2}
    pool = pool.assign(_tier=pool["disagreement_type"].map(tier_order)).sort_values(
        ["_tier", "attested_count"], ascending=[True, False]
    )
    if args.max_per_sign:
        pool = pool.groupby("sign", sort=False).head(args.max_per_sign)
        pool = pool.sort_values(["_tier", "attested_count"], ascending=[True, False])
    selected = pool.head(args.limit)

    rows: list[dict] = []
    for number, (_, row) in enumerate(selected.iterrows(), start=1):
        rows.append(
            {
                "case": f"C{number:02d}",
                "disagreement_type": row["disagreement_type"],
                "sign": row["sign"],
                "sentence_context": row["sentence"],
                "model_reading": row["context_prediction"],
                "tla_editorial_reading": row["gold_reading"],
                "attested_alternatives": row["candidates"],
                "times_sign_attested": row["attested_count"],
                # Reviewer columns, intentionally empty.
                "expert_reading": "",
                "expert_agrees_with": "",  # model / TLA / neither / both defensible
                "expert_reasoning": "",
                "expert_confidence": "",  # certain / probable / uncertain
                "expert_notes": "",
            }
        )

    sheet = pd.DataFrame(rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.to_csv(output, index=False)

    print(f"\nWrote {len(sheet)} review cases to {output}")
    print("Tier breakdown in the sheet:")
    print(sheet["disagreement_type"].value_counts().to_string())
    print("\nFirst cases:")
    for _, row in sheet.head(5).iterrows():
        print(
            f"  {row['case']} [{row['disagreement_type']}] {row['sign']}: "
            f"model {row['model_reading']!r} vs TLA {row['tla_editorial_reading']!r}"
        )


if __name__ == "__main__":
    main()
