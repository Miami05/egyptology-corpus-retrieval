"""Item C2, Stage 1: can composition even *generate* the right reading? (dev only)

The amended C2 evaluation (lead, 2026-09-06) splits the question in two, and this is
the first half. Before asking whether a composed reading beats a borrowed one, ask
whether the composition produces the gold reading **at all**. Three numbers, on the
positions where the pristine model has nothing of its own — the group is attested
neither in this corpus nor in the Helsinki lexicon:

  coverage      share of those positions where composition yields >= 1 candidate
  oracle recall share of *covered* positions whose gold reading appears ANYWHERE
                among the candidates (exact match, and the item B lenient fold
                reported beside it)
  candidates    how many per covered position (mean, median)

Oracle recall is the ceiling: no scoring or decoding can do better than "the right
answer was on the list". If it is low, the composition rules are wrong, and no amount
of re-weighting will fix them.

**This runs on DEV only.** The dev split is the last 10% of the reading eval's own
training rows, fitted on the first 90%, with twins excluded by the same rule
`run_segmentation_eval.split` applies between train and test — so the held-out test
rows the Stage 2 paired comparison uses are never seen here. Word boundaries are the
gold ones: this measures composition, not segmentation.

    python scripts/run_composition_dev_eval.py
    python scripts/run_composition_dev_eval.py --examples ... --dev-share 0.1
"""

from __future__ import annotations

import argparse
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.services.composition import MAX_CANDIDATES, compose_group  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.reading_model import train_reading_model  # noqa: E402
from app.services.sign_functions import load_sign_functions  # noqa: E402
from scripts.run_reading_model_eval import aligned_rows  # noqa: E402

EXAMPLES_PATH = "data/processed/examples.csv"
RESULTS_PATH = "data/benchmarks/composition_dev_eval.csv"
EXAMPLES_OUT = "data/benchmarks/composition_dev_examples.csv"

# The item B lenient fold, reused verbatim so the two reports are comparable.
_FOLD_TABLE = {ord(c): None for c in ".()[]{}⸢⸣"}


def fold(value: str) -> str:
    return unicodedata.normalize("NFC", str(value)).lower().translate(_FOLD_TABLE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--results", default=RESULTS_PATH)
    parser.add_argument("--examples-out", default=EXAMPLES_OUT)
    parser.add_argument("--dev-share", type=float, default=0.1)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--no-lexicon", action="store_true")
    parser.add_argument(
        "--no-complement-skip",
        action="store_true",
        help="Turn off dev revision 1 (a phonogram may be a phonetic complement).",
    )
    parser.add_argument(
        "--no-optional-logogram",
        action="store_true",
        help="Turn off dev revision 2 (a logogram may equally be a classifier).",
    )
    parser.add_argument(
        "--label", default="", help="Name for this configuration in the printout."
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=MAX_CANDIDATES,
        help=(
            "Override the cap. Only for the dev diagnostic that asks whether the cap "
            "or the composition rules are what limits oracle recall; the shipped cap "
            "is the pre-registered 24."
        ),
    )
    parser.add_argument(
        "--sizes",
        default="0",
        help="Corpus sizes to evaluate; 0 means the whole corpus.",
    )
    args = parser.parse_args()

    complement_skip = not args.no_complement_skip
    optional_logogram = not args.no_optional_logogram
    print(
        f"[{args.label or 'config'}] complement_skip={complement_skip} "
        f"optional_logogram={optional_logogram}"
    )

    full = aligned_rows(load_examples_csv(args.examples))
    print(f"aligned sentences available: {len(full)}")

    functions = load_sign_functions()
    total_rows = sum(len(v) for v in functions.entries.values())
    standalone_rows = sum(
        1
        for entries in functions.entries.values()
        for entry in entries
        if entry.is_standalone
    )
    signs_with_standalone = sum(
        1 for sign in functions.entries if functions.standalone_entries_for(sign)
    )
    print(
        f"sign-function table: {total_rows:,} rows over {len(functions.entries):,} signs; "
        f"{standalone_rows:,} rows usable standalone ({total_rows - standalone_rows} "
        f"excluded), {signs_with_standalone:,} signs keep at least one"
    )

    summary_rows: list[dict] = []
    example_rows: list[dict] = []

    for raw_size in [int(s) for s in args.sizes.split(",")]:
        size = len(full) if raw_size == 0 else min(raw_size, len(full))
        subset = full.head(size)
        # The reading eval's own split, then a dev cut of its training half.
        test = subset.iloc[:: int(1 / args.test_fraction)]
        train = subset.drop(test.index)
        cut = int(len(train) * (1 - args.dev_share))
        fit, dev = train.iloc[:cut], train.iloc[cut:]
        before = len(dev)
        fit_strings = set(fit["hieroglyphs_norm"].astype(str))
        dev = dev[~dev["hieroglyphs_norm"].astype(str).isin(fit_strings)]
        print(
            f"\n{size} sentences | fit {len(fit)} | dev {len(dev)} "
            f"({before - len(dev)} twins of the fitting rows removed) | "
            f"held-out test {len(test)} rows NOT touched here"
        )
        if fit.empty or dev.empty:
            continue

        model = train_reading_model(fit, None if args.no_lexicon else load_lexicon())

        unreadable = 0          # positions with no corpus and no lexicon entry
        covered = 0             # ... of which composition produced >= 1 candidate
        oracle_exact = 0
        oracle_lenient = 0
        top1_exact = 0
        candidate_counts: list[int] = []
        abstained_signs: Counter = Counter()

        for _, row in dev.iterrows():
            signs = str(row["hieroglyphs_norm"]).split()
            gold = str(row["transliteration_gold"]).split()
            if len(signs) != len(gold):
                continue
            for sign, truth in zip(signs, gold):
                if sign in model.sign_reading:
                    continue
                if not args.no_lexicon and sign in model.lexicon:
                    continue
                unreadable += 1
                candidates = compose_group(
                    sign,
                    functions,
                    model.sign_reading,
                    complement_skip=complement_skip,
                    optional_logogram=optional_logogram,
                    max_candidates=args.max_candidates,
                )
                if not candidates:
                    for glyph in sign:
                        if not functions.standalone_entries_for(glyph):
                            abstained_signs[glyph] += 1
                    continue
                covered += 1
                candidate_counts.append(len(candidates))
                values = [c.reading for c in candidates]
                hit_exact = truth in values
                hit_lenient = fold(truth) in {fold(v) for v in values}
                oracle_exact += int(hit_exact)
                oracle_lenient += int(hit_lenient)
                top1_exact += int(values[0] == truth)
                if len(example_rows) < 400:
                    example_rows.append(
                        {
                            "group": sign,
                            "gold": truth,
                            "top1": values[0],
                            "candidates": len(values),
                            "gold_in_candidates_exact": int(hit_exact),
                            "gold_in_candidates_lenient": int(hit_lenient),
                            "first_five": " | ".join(values[:5]),
                        }
                    )

        covered_or_one = covered or 1
        out = {
            "label": args.label or "config",
            "complement_skip": complement_skip,
            "optional_logogram": optional_logogram,
            "corpus_sentences": size,
            "fit_sentences": len(fit),
            "dev_sentences": len(dev),
            "dev_twins_removed": before - len(dev),
            "positions_unreadable": unreadable,
            "positions_covered": covered,
            "coverage": round(covered / (unreadable or 1), 4),
            "oracle_recall_exact": round(oracle_exact / covered_or_one, 4),
            "oracle_recall_lenient": round(oracle_lenient / covered_or_one, 4),
            "top1_exact": round(top1_exact / covered_or_one, 4),
            "candidates_mean": round(statistics.fmean(candidate_counts), 3)
            if candidate_counts
            else 0.0,
            "candidates_median": statistics.median(candidate_counts)
            if candidate_counts
            else 0,
            "candidates_max": max(candidate_counts) if candidate_counts else 0,
        }
        summary_rows.append(out)
        print(
            f"  positions the corpus and lexicon cannot read: {unreadable:,}\n"
            f"  coverage      {out['coverage']:.4f}  ({covered:,} of {unreadable:,})\n"
            f"  oracle recall {out['oracle_recall_exact']:.4f} exact / "
            f"{out['oracle_recall_lenient']:.4f} lenient (of the covered)\n"
            f"  top-1 exact   {out['top1_exact']:.4f}\n"
            f"  candidates    mean {out['candidates_mean']}, median "
            f"{out['candidates_median']}, max {out['candidates_max']}"
        )
        if abstained_signs:
            print(
                "  most frequent signs causing an abstention (no standalone row): "
                + ", ".join(f"{g} x{n}" for g, n in abstained_signs.most_common(12))
            )

    summary = pd.DataFrame(summary_rows)
    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.results, index=False)
    print(f"\nSaved {args.results}")
    if example_rows:
        pd.DataFrame(example_rows).to_csv(args.examples_out, index=False)
        print(f"Saved {len(example_rows)} dev examples to {args.examples_out}")


if __name__ == "__main__":
    main()
