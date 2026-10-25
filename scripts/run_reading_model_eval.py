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

Honest defaults (audit A24, A56). Duplicate exclusion is on: held-out sentences whose
exact sign string is in training are dropped (as before, when the flag was given) and
so are those with a sign-group Jaccard >= `--near-duplicate-overlap` (0.8) to some
training sentence. And the Helsinki lexicon is built from AES and Ramses word lists
covering all Ramses splits, so for test rows from those sources the lexicon reads back
the test sentence's own counts: with the lexicon on, rows from
`--lexicon-exclude-test-sources` (default Ramses,AES) are removed from the TEST split
only (they stay in training). Per-source lexicon-assisted accuracy is written to
`--by-source-results`. Even so, do not quote a lexicon-on number as a held-out result
until a lexicon variant is built without the held-out texts. Results go to NEW
`*_v2.csv` files; the committed reading_model_eval*.csv are the legacy record.

Text-level split (audit A56, `--split text`, the default): AES sentences are held out
by whole text (the text id in source_ref) and Ramses by Rosmorduc's official test
split; TLA and BBAW rows carry no text identity in this corpus, so they are still split
by sentence. That limitation is printed with every run.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.lexicon import load_lexicon
from app.services.reading_model import train_reading_model
from scripts.build_competitive_ambiguity_benchmark import build_token_index
from scripts.eval_guards import (
    SENTENCE_LEVEL_SOURCES,
    assert_text_groups_disjoint,
    text_level_test_mask,
    twin_rows,
)

EXAMPLES_PATH = "data/processed/examples.csv"
# NEW names on purpose (audit A24, A56): the committed reading_model_eval*.csv were
# measured with duplicates in and the lexicon leaking, and stay as the legacy record.
RESULTS_PATH = "data/benchmarks/reading_model_eval_v2.csv"
ERRORS_PATH = "data/benchmarks/reading_model_errors_v2.csv"
BY_SOURCE_PATH = "data/benchmarks/reading_model_eval_by_source_v2.csv"
NEAR_DUPLICATE_OVERLAP = 0.8
LEXICON_EXCLUDE_TEST_SOURCES = "Ramses,AES"
# Sources whose lexicon-assisted numbers are not held-out (see the module docstring).
LEXICON_TAINTED_SOURCES = {"Ramses", "AES", "BBAW"}
# How held-out sentences are chosen (audit A56): 'text' keeps every sentence of a text
# on one side (see scripts/eval_guards.text_level_test_mask), 'sentence' is the old
# every-k-th-sentence split.
SPLIT_MODES = ("text", "sentence")


def aligned_rows(df: pd.DataFrame) -> pd.DataFrame:
    signs = df["hieroglyphs_norm"].astype(str).str.split()
    readings = df["transliteration_gold"].astype(str).str.split()
    mask = signs.map(len).gt(0) & (signs.map(len) == readings.map(len))
    return df[mask].copy()


def parse_source_list(text: str) -> set[str]:
    """'Ramses, AES' -> {'Ramses', 'AES'}; empty string -> empty set."""
    return {part.strip() for part in str(text).split(",") if part.strip()}


def near_duplicate_mask(test: pd.DataFrame, train: pd.DataFrame, overlap: float) -> np.ndarray:
    """True for each test sentence with a training sentence at sign-group Jaccard >= `overlap`."""
    if overlap <= 0 or test.empty or train.empty:
        return np.zeros(len(test), dtype=bool)
    train_sets = [set(str(value).split()) for value in train["hieroglyphs_norm"]]
    index = build_token_index(train_sets)
    mask = np.zeros(len(test), dtype=bool)
    for position, value in enumerate(test["hieroglyphs_norm"]):
        mask[position] = bool(twin_rows(set(str(value).split()), train_sets, index, overlap))
    return mask


@dataclass
class SplitResult:
    train: pd.DataFrame
    test: pd.DataFrame
    exact_duplicates: int
    near_duplicates: int
    excluded_for_lexicon: int


def select_test_rows(
    subset: pd.DataFrame,
    test_fraction: float,
    exclude_duplicates: bool,
    near_duplicate_overlap: float,
    lexicon_on: bool,
    lexicon_exclude_sources: "set[str]",
    split_by: str = "sentence",
) -> SplitResult:
    """The deterministic split and what is dropped from test.

    `split_by="sentence"` holds out every k-th sentence (the old split, still this
    function's default so earlier callers are unchanged); `"text"` holds out whole
    texts where the source has a text identity and Ramses' official test split, and
    raises if any text group ends up on both sides (audit A56).

    Order: split; count test sentences whose exact sign string is in training
    (`exact_duplicates`, reported whether or not they are dropped); with duplicate
    exclusion on, drop them and then drop sentences whose sign groups are within
    `near_duplicate_overlap` of a training sentence (`near_duplicates`, the ones that
    are not exact copies); finally, with the lexicon on, drop test sentences from
    `lexicon_exclude_sources` (`excluded_for_lexicon`). Training is never touched.
    """
    if split_by == "text":
        held_out = np.array(text_level_test_mask(subset, test_fraction), dtype=bool)
        test = subset[held_out]
        train = subset[~held_out]
        assert_text_groups_disjoint(train, test)
    elif split_by == "sentence":
        test = subset.iloc[:: int(1 / test_fraction)]
        train = subset.drop(test.index)
    else:
        raise ValueError(f"split_by must be one of {SPLIT_MODES}, not {split_by!r}")
    train_sign_strings = set(train["hieroglyphs_norm"].astype(str))
    leaked_mask = test["hieroglyphs_norm"].astype(str).isin(train_sign_strings)
    exact = int(leaked_mask.sum())
    near = 0
    if exclude_duplicates:
        test = test[~leaked_mask]
        near_mask = near_duplicate_mask(test, train, near_duplicate_overlap)
        near = int(near_mask.sum())
        test = test[~near_mask]
    excluded = 0
    if lexicon_on and lexicon_exclude_sources:
        in_excluded = test["source"].astype(str).isin(lexicon_exclude_sources)
        excluded = int(in_excluded.sum())
        test = test[~in_excluded]
    return SplitResult(train, test, exact, near, excluded)


def by_source_records(size: int, per_source: "dict[str, Counter]") -> list[dict]:
    """One row per source: the pooled counters split by where the test sentence came from."""
    rows = []
    for source, tally in sorted(per_source.items()):
        lexicon = tally["lexicon_predictions"]
        fallback = tally["fallback_predictions"]
        ambiguous = tally["ambiguous_instances"]
        rows.append(
            {
                "corpus_sentences": size,
                "source": source,
                "test_sentences": tally["test_sentences"],
                "test_sign_instances": tally["sign_instances"],
                "unseen_signs": tally["unseen"],
                "lexicon_predictions": lexicon,
                "lexicon_correct": tally["lexicon_correct"],
                "acc_lexicon": round(tally["lexicon_correct"] / (lexicon or 1), 4),
                "fallback_predictions": fallback,
                "fallback_correct": tally["fallback_correct"],
                "acc_fallback": round(tally["fallback_correct"] / (fallback or 1), 4),
                "ambiguous_instances": ambiguous,
                "ambiguous_context_correct": tally["ambiguous_context_correct"],
                "acc_ambiguous_context": round(
                    tally["ambiguous_context_correct"] / (ambiguous or 1), 4
                ),
            }
        )
    return rows


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--results", default=RESULTS_PATH)
    parser.add_argument("--errors", default=ERRORS_PATH)
    parser.add_argument(
        "--by-source-results",
        default=BY_SOURCE_PATH,
        help="Per-source lexicon / fallback / ambiguous accuracy (audit A24).",
    )
    parser.add_argument(
        "--lexicon-exclude-test-sources",
        default=LEXICON_EXCLUDE_TEST_SOURCES,
        help=(
            "Comma-separated sources removed from the TEST split when the lexicon is on "
            "(they stay in training): the lexicon is built from AES and Ramses word lists "
            "over all Ramses splits, so for those rows it reads back the test sentence. "
            "Empty string = the old behaviour. Ignored with --no-lexicon."
        ),
    )
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
        "--split",
        choices=list(SPLIT_MODES),
        default="text",
        help=(
            "Audit A56. 'text' (default) holds out whole texts: AES by its text id, "
            "Ramses by Rosmorduc's official test split; TLA and BBAW rows carry no text "
            "identity, so each of their sentences is its own group (a stated "
            "limitation). 'sentence' is the old every-k-th-sentence split."
        ),
    )
    parser.add_argument(
        "--composed",
        action="store_true",
        help=(
            "Item C2: also decode every test sentence with composed readings on and "
            "with them off, and report the paired comparison on exactly the positions "
            "where the pristine (composed-off) model used its glyph-similarity "
            "fallback. That paired accuracy is the C2.4 decision rule."
        ),
    )
    parser.add_argument(
        "--exclude-duplicates",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "On by default (audit A56). Drop held-out sentences whose exact sign string "
            "also occurs in training, and (--near-duplicate-overlap) near-copies. "
            "Without this, a formulaic corpus lets the model score by memorisation. "
            "--no-exclude-duplicates restores the old default."
        ),
    )
    parser.add_argument(
        "--near-duplicate-overlap",
        type=float,
        default=NEAR_DUPLICATE_OVERLAP,
        help=(
            "With duplicate exclusion on: also drop held-out sentences whose sign-group "
            "Jaccard with some training sentence is at least this. 0 = off (the old "
            "exact-only rule)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> None:
    args = _parse_args(argv)

    full = aligned_rows(load_examples_csv(args.examples))
    print(f"aligned sentences available: {len(full)}")
    if args.split == "text":
        print(
            "split: whole texts (AES text id, Ramses official test split); "
            f"{', '.join(SENTENCE_LEVEL_SOURCES)} have no text identity and are split "
            "by sentence"
        )

    summary_rows: list[dict] = []
    error_rows: list[dict] = []
    by_source_rows: list[dict] = []
    lexicon_on = not args.no_lexicon
    lexicon_exclude = parse_source_list(args.lexicon_exclude_test_sources) if lexicon_on else set()

    for raw_size in [int(s) for s in args.sizes.split(",")]:
        size = len(full) if raw_size == 0 else min(raw_size, len(full))
        subset = full.head(size)
        # Deterministic split (--split): whole texts by default, every 5th sentence
        # with --split sentence. No shuffling, so the split is reproducible and the
        # same sentences are held out at every size.
        #
        # This corpus is heavily formulaic (Pyramid Text spells recur), so a large
        # share of held-out sentences have an identical twin in training. Accuracy on
        # those is memorisation, not prediction, so they are dropped by default (exact
        # copies, then near-copies) and the lexicon-leaking sources leave the test split
        # when the lexicon is on: see select_test_rows.
        split = select_test_rows(
            subset,
            args.test_fraction,
            args.exclude_duplicates,
            args.near_duplicate_overlap,
            lexicon_on,
            lexicon_exclude,
            split_by=args.split,
        )
        train, test = split.train, split.test
        if train.empty or test.empty:
            continue
        leaked_count = split.exact_duplicates
        if lexicon_on:
            tainted = sorted(
                set(test["source"].astype(str)) & LEXICON_TAINTED_SOURCES
            )
            if tainted:
                print(
                    f"  WARNING: lexicon is on and the test split still holds "
                    f"{', '.join(tainted)} rows: lexicon-assisted numbers for those rows "
                    "are not held-out."
                )

        # The lexicon is the variable under test here: held-out groups the training
        # split never saw are exactly where it is consulted.
        model = train_reading_model(train, load_lexicon() if lexicon_on else None)
        ambiguous = model.ambiguous_signs

        totals = {
            "all": 0,
            "ambiguous": 0,
            "unseen": 0,
            "single": 0,
            "fallback": 0,
            "lexicon": 0,
            "composed": 0,
            # Item C2's paired denominator: positions where the pristine
            # (composed-off) decode used its glyph-similarity fallback AND the
            # composed decode produced a composed reading. Only these can be compared.
            "paired": 0,
            # Fallback positions the composition could not reach at all.
            "fallback_not_composed": 0,
            "ambiguous_composed_arm": 0,
        }
        correct = {
            "freq_all": 0,
            "ctx_all": 0,
            "freq_ambiguous": 0,
            "ctx_ambiguous": 0,
            "left_only_ambiguous": 0,
            "fallback": 0,
            "lexicon": 0,
            "composed": 0,
            "paired_fallback": 0,
            "paired_composed": 0,
            "ctx_ambiguous_composed": 0,
        }

        # Audit A24: the pooled lexicon accuracy hides which source is reading itself
        # back, so the same counts are also kept per source.
        per_source: dict[str, Counter] = {}

        for _, row in test.iterrows():
            tally = per_source.setdefault(str(row["source"]), Counter())
            tally["test_sentences"] += 1
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

            if args.composed:
                # The two arms of the C2 paired comparison, on the same sentence:
                # the pristine decode (composition off, so an unattested group
                # borrows) and the composed decode. The pristine arm is what defines
                # which positions are comparable at all.
                pristine = model.predict_sequence(signs, use_composed=False)
                composed_arm = model.predict_sequence(signs, use_composed=True)
                # A composed position feeds the reading-bigram chain, so switching
                # composition on can move a *seen ambiguous* sign beside it. C2.4
                # forbids that from lowering acc_ambiguous_context, so it is measured
                # rather than assumed.
                for sign, truth, now in zip(signs, gold, composed_arm):
                    if now.was_seen and sign in ambiguous:
                        totals["ambiguous_composed_arm"] += 1
                        if now.predicted == truth:
                            correct["ctx_ambiguous_composed"] += 1
                for truth, was, now in zip(gold, pristine, composed_arm):
                    if now.is_composed:
                        totals["composed"] += 1
                        if now.predicted == truth:
                            correct["composed"] += 1
                    if not was.is_fallback:
                        continue
                    if not now.is_composed:
                        totals["fallback_not_composed"] += 1
                        continue
                    totals["paired"] += 1
                    if was.predicted == truth:
                        correct["paired_fallback"] += 1
                    if now.predicted == truth:
                        correct["paired_composed"] += 1

            for sign, truth, prediction, base, left in zip(
                signs, gold, predictions, baseline, left_only
            ):
                totals["all"] += 1
                tally["sign_instances"] += 1
                if not prediction.was_seen:
                    totals["unseen"] += 1
                    tally["unseen"] += 1
                    # A fallback reading is the new capability: the group itself was
                    # never attested, so previously nothing could be proposed at all.
                    if prediction.is_fallback:
                        totals["fallback"] += 1
                        tally["fallback_predictions"] += 1
                        if prediction.predicted == truth:
                            correct["fallback"] += 1
                            tally["fallback_correct"] += 1
                    # A lexicon reading: the group is unattested here but attested in
                    # the Helsinki AES+Ramses word lists. Scored separately so the two
                    # ways of reading an unseen group can be compared directly.
                    elif prediction.is_lexicon:
                        totals["lexicon"] += 1
                        tally["lexicon_predictions"] += 1
                        if prediction.predicted == truth:
                            correct["lexicon"] += 1
                            tally["lexicon_correct"] += 1
                    continue
                if sign in ambiguous:
                    totals["ambiguous"] += 1
                    tally["ambiguous_instances"] += 1
                    if prediction.predicted == truth:
                        correct["ctx_ambiguous"] += 1
                        tally["ambiguous_context_correct"] += 1
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
        if args.composed:
            paired = totals["paired"] or 1
            row_out.update(
                {
                    "composed_predictions": totals["composed"],
                    "acc_composed": round(correct["composed"] / (totals["composed"] or 1), 4),
                    # The C2.4 decision rule: same positions, both arms.
                    "paired_positions": totals["paired"],
                    "paired_acc_fallback": round(correct["paired_fallback"] / paired, 4),
                    "paired_acc_composed": round(correct["paired_composed"] / paired, 4),
                    "paired_gain": round(
                        (correct["paired_composed"] - correct["paired_fallback"]) / paired, 4
                    ),
                    "fallback_positions_not_composed": totals["fallback_not_composed"],
                }
            )
        row_out["ambiguous_gain"] = round(
            row_out["acc_ambiguous_context"] - row_out["acc_ambiguous_most_frequent"], 4
        )
        row_out["right_context_gain"] = round(
            row_out["acc_ambiguous_context"] - row_out["acc_ambiguous_left_only"], 4
        )
        # Appended last (audit A24, A56), so every column above keeps its name.
        row_out["near_duplicate_test_sentences"] = split.near_duplicates
        row_out["near_duplicate_overlap"] = (
            args.near_duplicate_overlap if args.exclude_duplicates else 0.0
        )
        row_out["lexicon_test_sources_excluded"] = ",".join(sorted(lexicon_exclude))
        row_out["test_sentences_excluded_for_lexicon"] = split.excluded_for_lexicon
        row_out["split"] = args.split
        by_source_rows.extend(by_source_records(size, per_source))
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
        if args.composed:
            print(
                f"         composed: {row_out['composed_predictions']} positions @ acc "
                f"{row_out['acc_composed']:.4f}\n"
                f"         PAIRED on the {row_out['paired_positions']} positions the "
                f"pristine model read by fallback: "
                f"fallback {row_out['paired_acc_fallback']:.4f} vs composed "
                f"{row_out['paired_acc_composed']:.4f} "
                f"({row_out['paired_gain']:+.4f}); "
                f"{row_out['fallback_positions_not_composed']} fallback positions the "
                "composition could not reach"
            )

    summary = pd.DataFrame(summary_rows)
    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.results, index=False)
    by_source = pd.DataFrame(by_source_rows)
    Path(args.by_source_results).parent.mkdir(parents=True, exist_ok=True)
    by_source.to_csv(args.by_source_results, index=False)
    print("\nFull table:")
    print(summary.to_string(index=False))
    print("\nPer source (lexicon-assisted numbers are not held-out for AES, Ramses, BBAW):")
    print(by_source.to_string(index=False))
    print(f"\nSaved to {args.results} and {args.by_source_results}")

    if error_rows:
        errors = pd.DataFrame(error_rows)
        errors.to_csv(args.errors, index=False)
        print(f"Saved {len(errors)} ambiguous-sign errors (full corpus) to {args.errors}")


if __name__ == "__main__":
    main()
