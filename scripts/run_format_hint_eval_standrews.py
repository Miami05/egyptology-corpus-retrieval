"""Item B, step 5: quadrat hints on real RES-derived input (St Andrews).

This is the honest measurement. `run_format_hint_eval_bbaw.py` synthesises controls
from the same annotation that defines the gold words, so its hints are perfect by
construction; here the controls are Nederhof's own RES layout, converted to Unicode
by `scripts/import_standrews.py`, and the gold is the *reading*, annotated
independently of the layout.

Why the metric is end-to-end reading and not boundary F1. In `standrews_lines.csv` the
spaces separate **quadrats**, not words: line 1 of urkIV-001 has 12 quadrats and 5
readings. There is no word-level grouping in the archive to score boundaries against,
so the only gold available is the `transliteration` column, and the only fair question
is "does the pipeline read the line better with the layout than without it".

The fold, fixed in the pre-registration before any run: NFC, lowercase, delete
`. ( ) [ ] { } ⸢ ⸣`, nothing else. It is deliberately weak — ṯ/t and yod spellings
differ between Hannig (St Andrews) and TLA (this corpus) and count as misses, but they
count as misses identically on both arms, so the *paired delta* is unaffected.

Two input shapes per line:

  as_rendered   the `hieroglyphs` column unchanged: quadrat spaces and controls
  unspaced      the same string with the spaces removed, controls kept

each read twice: hints off (controls deleted, `quadrat_crossed` 0.0 — today) and hints
on at the constant selected on the BBAW dev half.

The data file is gitignored (CC BY-NC-SA); this script is committed, its output is a
CSV of aggregates and paired deltas, not of Nederhof's text.

    python scripts/run_format_hint_eval_standrews.py --constant 0.5
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.data.normalizer import normalize_hieroglyphs  # noqa: E402
from app.services.boundary_model import fit_boundary_model  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.reading_model import train_reading_model  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
    segment_paste,
)

EXAMPLES_PATH = PROJECT_ROOT / "data" / "processed" / "examples.csv"
LINES_PATH = PROJECT_ROOT / "data" / "raw" / "standrews" / "standrews_lines.csv"
OUT_DIR = PROJECT_ROOT / "data" / "benchmarks" / "format_hints"

# The one lenient fold, fixed in the pre-registration. Nothing else is removed.
FOLD_DELETE = ".()[]{}⸢⸣"
_FOLD_TABLE = {ord(c): None for c in FOLD_DELETE}

CAMILLA_TEXT = "urkIV-001"
CAMILLA_LINE = "2"


def fold(value: str) -> list[str]:
    return unicodedata.normalize("NFC", str(value)).lower().translate(_FOLD_TABLE).split()


def multiset_scores(predicted: list[str], gold: list[str]) -> tuple[int, int, int]:
    """Overlap of two token multisets: (matched, predicted, gold)."""
    from collections import Counter

    overlap = Counter(predicted) & Counter(gold)
    return sum(overlap.values()), len(predicted), len(gold)


def read_line(
    raw: str, segmenter: Segmenter, model, use_format_hints: bool
) -> tuple[list[str], str]:
    segmentation, _as_pasted = segment_paste(
        raw, segmenter, use_format_hints=use_format_hints
    )
    groups = segmentation.groups
    predictions = model.predict_sequence(groups)
    reading = " ".join(p.predicted for p in predictions if p.predicted)
    return groups, reading


def evaluate(
    lines: pd.DataFrame,
    segmenter: Segmenter,
    model,
    shape: str,
    use_format_hints: bool,
) -> tuple[dict[str, float], list[dict]]:
    matched = predicted_n = gold_n = 0
    exact = 0
    group_gap = 0
    per_line: list[dict] = []
    for _, row in lines.iterrows():
        raw = str(row["hieroglyphs"])
        text = raw if shape == "as_rendered" else raw.replace(" ", "")
        groups, reading = read_line(text, segmenter, model, use_format_hints)
        gold = fold(row["transliteration"])
        got = fold(reading)
        m, p, g = multiset_scores(got, gold)
        matched += m
        predicted_n += p
        gold_n += g
        exact += int(got == gold)
        group_gap += abs(len(groups) - len(gold))
        line_f1 = 2 * m / (p + g) if p + g else 0.0
        per_line.append(
            {
                "text": row["text"],
                "line": row["line"],
                "f1": line_f1,
                "exact": int(got == gold),
                "groups": len(groups),
                "gold_tokens": len(gold),
            }
        )
    precision = matched / predicted_n if predicted_n else 0.0
    recall = matched / gold_n if gold_n else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    summary = {
        "lines": len(lines),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "exact_line_rate": round(exact / len(lines), 4) if len(lines) else 0.0,
        "mean_group_token_gap": round(group_gap / len(lines), 4) if len(lines) else 0.0,
    }
    return summary, per_line


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=str(EXAMPLES_PATH))
    parser.add_argument("--lines", default=str(LINES_PATH))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument(
        "--constant",
        type=float,
        required=True,
        help="quadrat_crossed to test, as selected on the BBAW dev half.",
    )
    parser.add_argument("--no-lexicon", action="store_true")
    parser.add_argument(
        "--boundary-model",
        type=float,
        default=None,
        help=(
            "Override SegmentationWeights.boundary_model on both arms (item C1). "
            "Item C's decision rule reads this script's unspaced token F1, so the "
            "candidate lambda_b has to be measurable here before it is the default."
        ),
    )
    parser.add_argument(
        "--unattested-may-cross-hints",
        action="store_true",
        help=(
            "Item C1b: let an unattested multi-glyph span cross a pasted space on "
            "both arms. In the as-rendered shape the pasted spaces are the quadrat "
            "spaces, so that is the shape this flag can move."
        ),
    )
    args = parser.parse_args()

    lines_path = Path(args.lines)
    if not lines_path.exists():
        raise SystemExit(f"{lines_path} is absent (gitignored CC BY-NC-SA data).")
    lines = pd.read_csv(lines_path, keep_default_na=False)
    lines = lines[lines["hieroglyphs"].astype(str).str.strip() != ""]
    lines = lines[lines["transliteration"].astype(str).str.strip() != ""]
    print(f"St Andrews lines with glyphs and a reading: {len(lines):,}")

    frame = load_examples_csv(args.examples)
    print(f"public corpus {len(frame):,} rows, sources {sorted(set(frame['source']))}")

    # Memorisation guard: a line whose normalised glyph string is already in the
    # public corpus would be scored on a string the reading model was fitted on, so
    # it is dropped (the rule `run_segmentation_eval.split` uses). One such line
    # exists on 2026-09-06: urkIV-024 line 2-8 is the single sign 𓅱, which the TLA
    # rows also carry on its own.
    corpus_strings = set(frame["hieroglyphs_norm"].astype(str))
    in_corpus = lines["hieroglyphs"].astype(str).map(
        lambda v: normalize_hieroglyphs(v) in corpus_strings
    )
    if in_corpus.any():
        for _, row in lines[in_corpus].iterrows():
            print(
                f"memorisation guard: dropping {row['text']} line {row['line']} "
                f"({normalize_hieroglyphs(row['hieroglyphs'])!r}) — already in the "
                "public corpus"
            )
    lines = lines[~in_corpus]
    remaining = [
        v for v in lines["hieroglyphs"].astype(str)
        if normalize_hieroglyphs(v) in corpus_strings
    ]
    assert not remaining, f"{len(remaining)} St Andrews lines still occur in the corpus"
    print(
        f"memorisation guard: {int(in_corpus.sum())} line(s) dropped, "
        f"{len(lines):,} evaluated, 0 of them in the public corpus"
    )

    lexicon = None if args.no_lexicon else load_lexicon()
    model = train_reading_model(frame, lexicon)
    base = DEFAULT_SEGMENTATION_WEIGHTS
    if args.boundary_model is not None:
        base = base.replace(boundary_model=args.boundary_model)
    if args.unattested_may_cross_hints:
        base = base.replace(unattested_may_cross_hints=True)
    print(f"segmentation weights: {base}")
    # Fitted once and shared, so the two arms differ only in `quadrat_crossed`.
    shared_boundary = fit_boundary_model(model) if base.boundary_model else None
    off = Segmenter(
        model,
        base.replace(quadrat_crossed=0.0),
        use_lexicon=not args.no_lexicon,
        boundary_model=shared_boundary,
    )
    on = Segmenter(
        model,
        base.replace(quadrat_crossed=args.constant),
        use_lexicon=not args.no_lexicon,
        boundary_model=shared_boundary,
    )

    records: list[dict] = []
    per_line_by_arm: dict[tuple[str, str], list[dict]] = {}
    for shape in ("as_rendered", "unspaced"):
        for arm, segmenter, hints in (
            ("hints_off", off, False),
            ("hints_on", on, True),
        ):
            summary, per_line = evaluate(lines, segmenter, model, shape, hints)
            constant = args.constant if arm == "hints_on" else 0.0
            records.append({"shape": shape, "arm": arm, "quadrat_crossed": constant, **summary})
            per_line_by_arm[(shape, arm)] = per_line

    header = (
        f"{'shape':12s} {'arm':10s} {'q':>5s} {'lines':>6s}  {'P':>6s} {'R':>6s} "
        f"{'F1':>6s} {'exact':>6s} {'|grp-tok|':>10s}"
    )
    table_lines = [header, "-" * len(header)]
    for record in records:
        table_lines.append(
            f"{record['shape']:12s} {record['arm']:10s} {record['quadrat_crossed']:5.2f} "
            f"{record['lines']:6d}  {record['precision']:6.3f} {record['recall']:6.3f} "
            f"{record['f1']:6.3f} {record['exact_line_rate']:6.3f} "
            f"{record['mean_group_token_gap']:10.3f}"
        )
    table = "\n".join(table_lines)
    print()
    print(table)

    delta_lines = ["", "paired deltas (hints_on - hints_off), per shape:"]
    deltas: list[dict] = []
    for shape in ("as_rendered", "unspaced"):
        a = per_line_by_arm[(shape, "hints_off")]
        b = per_line_by_arm[(shape, "hints_on")]
        improved = sum(1 for x, y in zip(a, b) if y["f1"] > x["f1"])
        worsened = sum(1 for x, y in zip(a, b) if y["f1"] < x["f1"])
        unchanged = len(a) - improved - worsened
        off_rec = next(r for r in records if r["shape"] == shape and r["arm"] == "hints_off")
        on_rec = next(r for r in records if r["shape"] == shape and r["arm"] == "hints_on")
        row = {
            "shape": shape,
            "delta_f1": round(on_rec["f1"] - off_rec["f1"], 4),
            "delta_exact": round(on_rec["exact_line_rate"] - off_rec["exact_line_rate"], 4),
            "delta_group_gap": round(
                on_rec["mean_group_token_gap"] - off_rec["mean_group_token_gap"], 4
            ),
            "improved": improved,
            "worsened": worsened,
            "unchanged": unchanged,
        }
        deltas.append(row)
        delta_lines.append(
            f"  {shape:12s} dF1 {row['delta_f1']:+.4f}  dexact {row['delta_exact']:+.4f}  "
            f"d|grp-tok| {row['delta_group_gap']:+.4f}  improved {improved}  "
            f"worsened {worsened}  unchanged {unchanged}"
        )
    print("\n".join(delta_lines))

    # --- Camilla's line, both ways ------------------------------------------
    camilla = lines[
        (lines["text"].astype(str) == CAMILLA_TEXT)
        & (lines["line"].astype(str) == CAMILLA_LINE)
    ]
    camilla_lines = ["", f"Camilla's line ({CAMILLA_TEXT}, line {CAMILLA_LINE}):"]
    if camilla.empty:
        camilla_lines.append("  not present in this file")
    else:
        row = camilla.iloc[0]
        camilla_lines.append(f"  gold      : {row['transliteration']}")
        for shape in ("as_rendered", "unspaced"):
            raw = str(row["hieroglyphs"])
            text = raw if shape == "as_rendered" else raw.replace(" ", "")
            for arm, segmenter, hints in (
                ("hints_off", off, False),
                ("hints_on", on, True),
            ):
                groups, reading = read_line(text, segmenter, model, hints)
                gold = fold(row["transliteration"])
                got = fold(reading)
                m, p, g = multiset_scores(got, gold)
                line_f1 = 2 * m / (p + g) if p + g else 0.0
                camilla_lines.append(f"  {shape} / {arm}  (F1 {line_f1:.4f}, {len(groups)} groups)")
                camilla_lines.append(f"    groups : {' '.join(groups)}")
                camilla_lines.append(f"    reading: {reading}")
    print("\n".join(camilla_lines))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "standrews.csv"
    md_path = out_dir / "standrews.md"
    pd.DataFrame(records).merge(
        pd.DataFrame(deltas), on="shape", how="left"
    ).to_csv(csv_path, index=False)
    md_path.write_text(
        "# Quadrat hints on real St Andrews input (item B, 2026-09-06)\n\n"
        f"{len(lines):,} lines with glyphs and a reading; public corpus "
        f"{len(frame):,} rows; memorisation guard passed (0 lines in the corpus).\n"
        f"Constant tested: quadrat_crossed = {args.constant}.\n\n"
        "Fold: NFC, lowercase, delete `. ( ) [ ] {{ }} ⸢ ⸣`, nothing else.\n\n"
        "```\n" + table + "\n" + "\n".join(delta_lines) + "\n"
        + "\n".join(camilla_lines) + "\n```\n",
        encoding="utf-8",
    )
    print(f"\nSaved {csv_path}\nSaved {md_path}")


if __name__ == "__main__":
    main()
