"""Evaluate the sign-level reading decoder against baselines on held-out sentences.

The question is narrow on purpose: given a sign, does the model pick the reading the
editors chose? Accuracy over *all* signs is easy to inflate, because most signs have
only one attested reading and any method gets those right. So the headline number is
accuracy on **ambiguous** signs -- the ones where a choice is actually being made, and
the only ones Camilla's objection is about.

Three systems are compared on the same held-out sentences:

  most-frequent  always the commonest reading of the sign, ignoring context
  context model  Viterbi over readings using reading bigrams and sign context
  (coverage)     signs never seen in training, which no count-based method can read

A gain over most-frequent is the evidence that *context* resolves multivalence, which
is the claim the project rests on.
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
from app.services.lexicon import load_lexicon
from app.services.reading_model import train_reading_model

EXAMPLES_PATH = "data/processed/examples.csv"
RESULTS_PATH = "data/benchmarks/reading_model_eval.csv"
ERRORS_PATH = "data/benchmarks/reading_model_errors.csv"


def aligned_rows(df: pd.DataFrame) -> pd.DataFrame:
    signs = df["hieroglyphs_norm"].astype(str).str.split()
    readings = df["transliteration_gold"].astype(str).str.split()
    mask = signs.map(len).gt(0) & (signs.map(len) == readings.map(len))
    return df[mask].copy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--results", default=RESULTS_PATH)
    parser.add_argument("--errors", default=ERRORS_PATH)
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help="Read with the corpus alone, without the Helsinki sign-reading lexicon.",
    )
    parser.add_argument(
        "--sizes",
        default="300,500,1000,2000,5000,0",
        help="Corpus sizes to evaluate; 0 means the whole corpus.",
    )
    parser.add_argument(
        "--test-fraction",
        type=float,
        default=0.2,
        help="Share of aligned sentences held out for testing.",
    )
    parser.add_argument(
        "--exclude-duplicates",
        action="store_true",
        help=(
            "Drop held-out sentences whose exact sign string also occurs in training. "
            "Without this, a formulaic corpus lets the model score by memorisation."
        ),
    )
    args = parser.parse_args()

    full = aligned_rows(load_examples_csv(args.examples))
    print(f"aligned sentences available: {len(full)}")

    summary_rows: list[dict] = []
    error_rows: list[dict] = []

    for raw_size in [int(s) for s in args.sizes.split(",")]:
        size = len(full) if raw_size == 0 else min(raw_size, len(full))
        subset = full.head(size)
        # Deterministic split: every 5th sentence is held out. No shuffling, so the
        # split is reproducible and the same sentences are held out at every size.
        test = subset.iloc[:: int(1 / args.test_fraction)]
        train = subset.drop(test.index)
        if train.empty or test.empty:
            continue

        # This corpus is heavily formulaic (Pyramid Text spells recur), so a large
        # share of held-out sentences have an identical twin in training. Accuracy on
        # those is memorisation, not prediction, so they are optionally dropped and
        # the clean figure is reported alongside.
        train_sign_strings = set(train["hieroglyphs_norm"].astype(str))
        leaked_mask = test["hieroglyphs_norm"].astype(str).isin(train_sign_strings)
        leaked_count = int(leaked_mask.sum())
        if args.exclude_duplicates:
            test = test[~leaked_mask]
            if test.empty:
                continue

        # The lexicon is the variable under test here: held-out groups the training
        # split never saw are exactly where it is consulted.
        model = train_reading_model(train, None if args.no_lexicon else load_lexicon())
        ambiguous = model.ambiguous_signs

        totals = {
            "all": 0,
            "ambiguous": 0,
            "unseen": 0,
            "single": 0,
            "fallback": 0,
            "lexicon": 0,
        }
        correct = {
            "freq_all": 0,
            "ctx_all": 0,
            "freq_ambiguous": 0,
            "ctx_ambiguous": 0,
            "left_only_ambiguous": 0,
            "fallback": 0,
            "lexicon": 0,
        }

        for _, row in test.iterrows():
            signs = str(row["hieroglyphs_norm"]).split()
            gold = str(row["transliteration_gold"]).split()
            if not signs or len(signs) != len(gold):
                # zip() would silently truncate and score misaligned positions as if
                # they lined up; such a row cannot be evaluated at all.
                continue
            predictions = model.predict_sequence(signs)
            # Ablation: same model, right-hand sign context switched off, so any
            # difference is attributable to that term alone.
            left_only = model.predict_sequence(signs, next_sign_weight=0.0)
            baseline = model.predict_most_frequent(signs)

            for sign, truth, prediction, base, left in zip(
                signs, gold, predictions, baseline, left_only
            ):
                totals["all"] += 1
                if not prediction.was_seen:
                    totals["unseen"] += 1
                    # A fallback reading is the new capability: the group itself was
                    # never attested, so previously nothing could be proposed at all.
                    if prediction.is_fallback:
                        totals["fallback"] += 1
                        if prediction.predicted == truth:
                            correct["fallback"] += 1
                    # A lexicon reading: the group is unattested here but attested in
                    # the Helsinki AES+Ramses word lists. Scored separately so the two
                    # ways of reading an unseen group can be compared directly.
                    elif prediction.is_lexicon:
                        totals["lexicon"] += 1
                        if prediction.predicted == truth:
                            correct["lexicon"] += 1
                    continue
                if sign in ambiguous:
                    totals["ambiguous"] += 1
                    if prediction.predicted == truth:
                        correct["ctx_ambiguous"] += 1
                    if base == truth:
                        correct["freq_ambiguous"] += 1
                    if left.predicted == truth:
                        correct["left_only_ambiguous"] += 1
                    if prediction.predicted != truth and size == len(full):
                        error_rows.append(
                            {
                                "sign": sign,
                                "gold_reading": truth,
                                "context_prediction": prediction.predicted,
                                "most_frequent_prediction": base,
                                "attested_count": prediction.attested_count,
                                "candidates": " | ".join(
                                    f"{r}:{p:.2f}" for r, p in prediction.candidates
                                ),
                                "sentence": str(row["transliteration_gold"])[:90],
                            }
                        )
                else:
                    totals["single"] += 1
                if prediction.predicted == truth:
                    correct["ctx_all"] += 1
                if base == truth:
                    correct["freq_all"] += 1

        seen = totals["all"] - totals["unseen"]
        amb = totals["ambiguous"] or 1
        row_out = {
            "corpus_sentences": size,
            "train_sentences": len(train),
            "test_sentences": len(test),
            "duplicate_test_sentences": leaked_count,
            "duplicates_excluded": bool(args.exclude_duplicates),
            "ambiguous_sign_types": len(ambiguous),
            "test_sign_instances": totals["all"],
            "unseen_signs": totals["unseen"],
            "unseen_share": round(totals["unseen"] / (totals["all"] or 1), 4),
            "ambiguous_instances": totals["ambiguous"],
            "ambiguous_share_of_seen": round(totals["ambiguous"] / (seen or 1), 4),
            "acc_all_most_frequent": round(correct["freq_all"] / (seen or 1), 4),
            "acc_all_context": round(correct["ctx_all"] / (seen or 1), 4),
            "acc_ambiguous_most_frequent": round(correct["freq_ambiguous"] / amb, 4),
            "acc_ambiguous_left_only": round(correct["left_only_ambiguous"] / amb, 4),
            "acc_ambiguous_context": round(correct["ctx_ambiguous"] / amb, 4),
            "lexicon_predictions": totals["lexicon"],
            "lexicon_share_of_unseen": round(totals["lexicon"] / (totals["unseen"] or 1), 4),
            "acc_lexicon": round(correct["lexicon"] / (totals["lexicon"] or 1), 4),
            "coverage_with_lexicon_and_fallback": round(
                (seen + totals["lexicon"] + totals["fallback"]) / (totals["all"] or 1), 4
            ),
            # Fallback readings for sign groups that were never attested: previously
            # no reading could be offered for these at all.
            "fallback_predictions": totals["fallback"],
            "fallback_share_of_unseen": round(
                totals["fallback"] / (totals["unseen"] or 1), 4
            ),
            "acc_fallback": round(correct["fallback"] / (totals["fallback"] or 1), 4),
            "coverage_before_fallback": round(
                (totals["all"] - totals["unseen"]) / (totals["all"] or 1), 4
            ),
            "coverage_with_fallback": round(
                (totals["all"] - totals["unseen"] + totals["fallback"])
                / (totals["all"] or 1),
                4,
            ),
        }
        row_out["ambiguous_gain"] = round(
            row_out["acc_ambiguous_context"] - row_out["acc_ambiguous_most_frequent"], 4
        )
        row_out["right_context_gain"] = round(
            row_out["acc_ambiguous_context"] - row_out["acc_ambiguous_left_only"], 4
        )
        summary_rows.append(row_out)
        print(
            f"  {size:>6} sentences | amb types {len(ambiguous):>4} | "
            f"freq {row_out['acc_ambiguous_most_frequent']:.3f} -> "
            f"left {row_out['acc_ambiguous_left_only']:.3f} -> "
            f"+right {row_out['acc_ambiguous_context']:.3f} "
            f"(right {row_out['right_context_gain']:+.3f}) | "
            f"coverage {row_out['coverage_before_fallback']:.1%} -> "
            f"{row_out['coverage_with_lexicon_and_fallback']:.1%} "
            f"(lexicon {row_out['lexicon_predictions']} @ acc {row_out['acc_lexicon']:.3f}; "
            f"fallback {row_out['fallback_predictions']} @ acc {row_out['acc_fallback']:.3f})"
        )

    summary = pd.DataFrame(summary_rows)
    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.results, index=False)
    print("\nFull table:")
    print(summary.to_string(index=False))
    print(f"\nSaved to {args.results}")

    if error_rows:
        errors = pd.DataFrame(error_rows)
        errors.to_csv(args.errors, index=False)
        print(f"Saved {len(errors)} ambiguous-sign errors (full corpus) to {args.errors}")


if __name__ == "__main__":
    main()
