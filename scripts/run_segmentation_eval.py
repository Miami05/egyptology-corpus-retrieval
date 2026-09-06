"""Measure the resegmentation lattice on held-out corpus sentences.

The question the segmenter answers is "where do the sign groups end?", so the
evaluation is boundary precision/recall/F1 against the TLA segmentation, plus the
share of sentences segmented exactly right. Three inputs are tried per sentence:

  unspaced   every space removed — the hardest case, no hints at all
  scrambled  each gold boundary dropped with probability P_DROP and a spurious
             boundary inserted inside a group with probability P_ADD — what a paste
             from a PDF or a sign editor looks like
  as_pasted  the scrambled spacing taken at face value, i.e. what the app did before
             this work — the baseline the lattice has to beat

Held-out means: the model and the segmenter's lexicon are fitted on the training
split only, and test sentences whose exact sign string also occurs in training are
excluded, because on this formulaic corpus that would measure memorisation.

    python scripts/run_segmentation_eval.py                 # default weights
    python scripts/run_segmentation_eval.py --grid          # small weight sweep
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.loader import load_examples_csv  # noqa: E402
from app.services.boundary_model import fit_boundary_model  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.reading_model import train_reading_model  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
    SegmentationWeights,
)

EXAMPLES_PATH = Path("data/processed/examples.csv")
P_DROP = 0.3
P_ADD = 0.2


def boundaries(groups: list[str]) -> set[int]:
    out: set[int] = set()
    position = 0
    for group in groups[:-1]:
        position += len(group)
        out.add(position)
    return out


def scramble(groups: list[str], rng: random.Random) -> list[str]:
    stream = "".join(groups)
    gold = boundaries(groups)
    kept = {b for b in gold if rng.random() >= P_DROP}
    for position in range(1, len(stream)):
        if position not in gold and rng.random() < P_ADD:
            kept.add(position)
    cuts = sorted(kept)
    out: list[str] = []
    start = 0
    for cut in cuts + [len(stream)]:
        out.append(stream[start:cut])
        start = cut
    return out


def evaluate(
    train: pd.DataFrame,
    test: pd.DataFrame,
    weights: SegmentationWeights,
    seed: int = 7,
    use_lexicon: bool = True,
    boundary_class_backoff: bool = True,
    model=None,
    boundary_model=None,
) -> dict[str, dict[str, float]]:
    """Boundary scores for one weight setting.

    `model` and `boundary_model` let a sweep fit the counts once and vary only the
    weights. Neither set of counts depends on a weight, so this is the same
    computation as refitting per setting — minutes rather than hours.
    """
    if model is None:
        model = train_reading_model(train, load_lexicon() if use_lexicon else None)
    segmenter = Segmenter(
        model,
        weights,
        use_lexicon=use_lexicon,
        boundary_model=boundary_model,
        boundary_class_backoff=boundary_class_backoff,
    )
    rng = random.Random(seed)
    # Groups the training split attested as whole groups. The unseen-word breakdown
    # below is the diagnosis that motivated item C1: 90% of the spurious boundaries
    # fell inside a gold group the training split never saw, and an aggregate F1
    # cannot show whether that moved.
    attested_groups = set(model.sign_reading)
    tallies = {
        name: {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "exact": 0,
            "n": 0,
            # missed boundaries (gold, not predicted)
            "fn_between_attested": 0,
            "fn_touching_unattested": 0,
            # spurious boundaries (predicted, not gold), by the gold group they cut
            "fp_inside_attested": 0,
            "fp_inside_unattested": 0,
            # denominators for the shares
            "gold_groups": 0,
            "gold_groups_unattested": 0,
        }
        for name in ("unspaced", "scrambled", "as_pasted")
    }

    def record(name: str, predicted: list[str], gold: list[str]) -> None:
        p, g = boundaries(predicted), boundaries(gold)
        t = tallies[name]
        t["tp"] += len(p & g)
        t["fp"] += len(p - g)
        t["fn"] += len(g - p)
        t["exact"] += int(predicted == gold)
        t["n"] += 1

        # Map every glyph position to the gold group that spans it, and every gold
        # boundary to the two groups it separates.
        spans: list[tuple[int, int, str]] = []
        position = 0
        for group in gold:
            spans.append((position, position + len(group), group))
            position += len(group)
        t["gold_groups"] += len(gold)
        t["gold_groups_unattested"] += sum(
            1 for group in gold if group not in attested_groups
        )
        seen_by_start = {start: group for start, _end, group in spans}
        seen_by_end = {end: group for _start, end, group in spans}
        for boundary in g - p:
            left = seen_by_end.get(boundary, "")
            right = seen_by_start.get(boundary, "")
            if left in attested_groups and right in attested_groups:
                t["fn_between_attested"] += 1
            else:
                t["fn_touching_unattested"] += 1
        for boundary in p - g:
            inside = next(
                (group for start, end, group in spans if start < boundary < end), ""
            )
            if inside in attested_groups:
                t["fp_inside_attested"] += 1
            else:
                t["fp_inside_unattested"] += 1

    for _, row in test.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        record("unspaced", segmenter.segment(["".join(gold)]).groups, gold)
        scrambled = scramble(gold, rng)
        record("scrambled", segmenter.segment(scrambled).groups, gold)
        record("as_pasted", scrambled, gold)

    results: dict[str, dict[str, float]] = {}
    for name, t in tallies.items():
        precision = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else 0.0
        recall = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results[name] = {
            "sentences": t["n"],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "exact": round(t["exact"] / t["n"], 4) if t["n"] else 0.0,
            "missed": t["fn"],
            "missed_between_attested": t["fn_between_attested"],
            "missed_touching_unattested": t["fn_touching_unattested"],
            "spurious": t["fp"],
            "spurious_inside_attested": t["fp_inside_attested"],
            "spurious_inside_unattested": t["fp_inside_unattested"],
            "gold_groups": t["gold_groups"],
            "gold_groups_unattested": t["gold_groups_unattested"],
            "unattested_group_share": round(
                t["gold_groups_unattested"] / (t["gold_groups"] or 1), 4
            ),
        }
    return results


def split(df: pd.DataFrame, test_share: float = 0.1, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    usable = df[df["hieroglyphs_norm"].astype(str).str.strip() != ""]
    shuffled = usable.sample(frac=1.0, random_state=seed)
    cut = int(len(shuffled) * (1 - test_share))
    train, test = shuffled.iloc[:cut], shuffled.iloc[cut:]
    train_strings = set(train["hieroglyphs_norm"].astype(str))
    test = test[~test["hieroglyphs_norm"].astype(str).isin(train_strings)]
    return train, test


def dev_split(
    train: pd.DataFrame, dev_share: float = 0.1
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carve a dev split out of the training split, for weight selection (item C1).

    Pre-registered as "the last 10% of that shuffled training split". `split` has
    already shuffled with the fixed seed, so this is a slice, not a second sample —
    the test split is never touched by a selection run. Twins are excluded by the
    same rule `split` applies to the test split: a dev sentence whose exact sign
    string also occurs in the fitting portion would measure memorisation.
    """
    cut = int(len(train) * (1 - dev_share))
    fit, dev = train.iloc[:cut], train.iloc[cut:]
    fit_strings = set(fit["hieroglyphs_norm"].astype(str))
    dev = dev[~dev["hieroglyphs_norm"].astype(str).isin(fit_strings)]
    return fit, dev


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--grid", action="store_true", help="Sweep a few weight settings.")
    parser.add_argument("--limit", type=int, default=0, help="Evaluate at most N test sentences.")
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help="Segment over corpus-attested groups only, without the Helsinki lexicon's groups.",
    )
    parser.add_argument(
        "--lexicon-weights",
        default="",
        help="Comma-separated lexicon_weight values to sweep (e.g. 0.39,0.2,0.1,0.05).",
    )
    parser.add_argument(
        "--boundary-weights",
        default="",
        help=(
            "Comma-separated SegmentationWeights.boundary_model values to sweep "
            "(item C1 lambda_b, pre-registered as 0.25,0.5,1.0,2.0). The counts are "
            "fitted once and reused across the values."
        ),
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help=(
            "Select on the dev split — the last 10%% of the shuffled training split "
            "— fitting on the first 90%%. The test split is not touched. This is the "
            "only mode a weight may be chosen in (item C1)."
        ),
    )
    parser.add_argument(
        "--no-class-backoff",
        action="store_true",
        help=(
            "Item C1 ablation: the boundary model uses the sign bigram alone, an "
            "unseen pair falling to the global prior instead of to the sign-function "
            "classes. Isolates what Nederhof's table itself contributed."
        ),
    )
    args = parser.parse_args()

    df = load_examples_csv(str(args.examples))
    train, test = split(df)
    if args.dev:
        train, test = dev_split(train)
        print("SELECTION RUN — dev split; the test split is untouched.")
    if args.limit:
        test = test.head(args.limit)
    label = "dev" if args.dev else "test"
    print(
        f"train {len(train)} rows; {label} {len(test)} rows "
        "(twins of training strings excluded)\n"
    )

    configs: list[tuple[str, SegmentationWeights]] = [("default", DEFAULT_SEGMENTATION_WEIGHTS)]
    if args.grid:
        base = DEFAULT_SEGMENTATION_WEIGHTS
        configs += [
            ("unattested_3", base.replace(unattested_per_glyph=3.0)),
            ("unattested_4", base.replace(unattested_per_glyph=4.0)),
            ("unattested_5", base.replace(unattested_per_glyph=5.0)),
            ("unattested_6", base.replace(unattested_per_glyph=6.0)),
            ("unattested_8", base.replace(unattested_per_glyph=8.0)),
            ("unattested_6_nodisc", base.replace(unattested_per_glyph=6.0, singleton_discount=1.0)),
        ]
    if args.lexicon_weights:
        configs = [
            (f"lexicon_weight_{value}", DEFAULT_SEGMENTATION_WEIGHTS.replace(lexicon_weight=float(value)))
            for value in args.lexicon_weights.split(",")
        ]
    if args.boundary_weights:
        configs = [
            (
                f"boundary_model_{value}",
                DEFAULT_SEGMENTATION_WEIGHTS.replace(boundary_model=float(value)),
            )
            for value in args.boundary_weights.split(",")
        ]

    # Fit once, reuse across every config: neither the group counts nor the boundary
    # statistics depend on a weight.
    model = train_reading_model(train, None if args.no_lexicon else load_lexicon())
    boundary_model = None
    if any(weights.boundary_model for _name, weights in configs):
        boundary_model = fit_boundary_model(
            model, use_class_backoff=not args.no_class_backoff
        )
        print(
            f"boundary model: {len(boundary_model.pair_total):,} adjacent sign pairs, "
            f"prior P(boundary) {boundary_model.prior:.4f}, class back-off "
            f"{'ON' if boundary_model.use_class_backoff else 'OFF (ablation)'}\n"
        )

    for name, weights in configs:
        results = evaluate(
            train,
            test,
            weights,
            use_lexicon=not args.no_lexicon,
            model=model,
            boundary_model=boundary_model,
        )
        print(f"[{name}] {weights}")
        for case, metrics in results.items():
            print(
                f"  {case:10s} n={metrics['sentences']:5d}  P={metrics['precision']:.3f}  "
                f"R={metrics['recall']:.3f}  F1={metrics['f1']:.3f}  exact={metrics['exact']:.3f}"
            )
        # The unseen-word breakdown: does the term move the errors that motivated it?
        print("  boundary errors by whether the gold group was attested in training:")
        for case in ("unspaced", "scrambled"):
            m = results[case]
            print(
                f"    {case:10s} gold groups {m['gold_groups']:,} "
                f"({m['gold_groups_unattested']:,} unattested, "
                f"{m['unattested_group_share']:.1%})"
            )
            print(
                f"      missed   {m['missed']:>6,}  = "
                f"{m['missed_between_attested']:>6,} between two attested groups + "
                f"{m['missed_touching_unattested']:>6,} touching an unattested one"
            )
            print(
                f"      spurious {m['spurious']:>6,}  = "
                f"{m['spurious_inside_attested']:>6,} inside an attested gold group + "
                f"{m['spurious_inside_unattested']:>6,} inside an unattested one"
            )
        print()


if __name__ == "__main__":
    main()
