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
) -> dict[str, dict[str, float]]:
    model = train_reading_model(train, load_lexicon() if use_lexicon else None)
    segmenter = Segmenter(model, weights, use_lexicon=use_lexicon)
    rng = random.Random(seed)
    tallies = {
        name: {"tp": 0, "fp": 0, "fn": 0, "exact": 0, "n": 0}
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
    args = parser.parse_args()

    df = load_examples_csv(str(args.examples))
    train, test = split(df)
    if args.limit:
        test = test.head(args.limit)
    print(f"train {len(train)} rows; test {len(test)} rows (twins of training strings excluded)\n")

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

    for name, weights in configs:
        results = evaluate(train, test, weights, use_lexicon=not args.no_lexicon)
        print(f"[{name}] {weights}")
        for case, metrics in results.items():
            print(
                f"  {case:10s} n={metrics['sentences']:5d}  P={metrics['precision']:.3f}  "
                f"R={metrics['recall']:.3f}  F1={metrics['f1']:.3f}  exact={metrics['exact']:.3f}"
            )
        print()


if __name__ == "__main__":
    main()
