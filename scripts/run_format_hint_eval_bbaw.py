"""Item B, step 4: the *upper bound* on what quadrat hints can do for segmentation.

Why BBAW and why an upper bound. The public corpus carries no format controls at all
(`data/processed/examples.csv`: zero U+13430-1345F), so there is no way to measure a
control-aware segmenter on it directly. The raw BBAW export does carry layout: its
Manuel de Codage glyph field marks every within-word adjacency with `-`, `:` or `*`,
and the importer already reads exactly that to decide where a word ends. So we can
synthesise Unicode controls from it — U+13430 (vertical joiner) for a `:` token,
U+13431 (horizontal joiner) for a `*`, nothing for `-` — and ask what a segmenter
gains from them.

The answer is an **upper bound and nothing else**, because the hints and the gold
segmentation come from the same annotation: a control-marked adjacency is inside a
gold word by construction, so hint precision is 1.0 by construction too. Real pastes
(St Andrews, `run_format_hint_eval_standrews.py`) are where the honest number is.

What is measured. Two input shapes per eligible row, both a single unspaced blob so
the paste's own spacing gives the segmenter nothing:

  unspaced + controls   the synthesised controls kept, read by `quadrat_hints`
  controls deleted      the same signs with no controls — today's behaviour

plus, for reference, `as_pasted`: the importer's own word groups taken at face value,
which is the trivial ceiling (F1 1.0) and is printed only so the table is readable.

Metric: boundary precision / recall / F1 and exact-sentence rate, the same definitions
`scripts/run_segmentation_eval.py` uses (its `boundaries` function is imported).

Memorisation guard: an eligible row's normalised glyph string is removed from the
frame the reading model and the segmenter's group counts are fitted on, exactly as
`run_segmentation_eval.split` does. Without it the lattice would be scored on strings
it was fitted on and every configuration would look perfect.

Split: seed 7, dev 50% / test 50%. The constant is chosen on **dev** only.

    python scripts/run_format_hint_eval_bbaw.py
    python scripts/run_format_hint_eval_bbaw.py --limit 500      # a quick sample
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.data.normalizer import (  # noqa: E402
    normalize_hieroglyphs,
    quadrat_hints,
    search_fold,
)
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.reading_model import train_reading_model  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
)
from scripts.import_bbaw_egyptian import (  # noqa: E402
    ANNOTATION_RE,
    CLOSER_RE,
    CODE_TOKEN_RE,
    DECORATION_RE,
    LACUNA_RE,
    MODIFIER_RE,
    NUMERAL_RE,
    OPENER_RE,
    OPERATOR_PREFIX_RE,
    SHADING_RE,
    UNREADABLE_RE,
    sign_for_code,
    to_corpus_convention,
)
from scripts.run_segmentation_eval import boundaries  # noqa: E402

EXAMPLES_PATH = PROJECT_ROOT / "data" / "processed" / "examples.csv"
RAW_PARQUET = PROJECT_ROOT / "data" / "raw" / "bbaw_egyptian" / "train.parquet"
OUT_DIR = PROJECT_ROOT / "data" / "benchmarks" / "format_hints"

VERTICAL_JOINER = "\U00013430"  # MdC `:`  — one sign above another
HORIZONTAL_JOINER = "\U00013431"  # MdC `*` — one sign beside another
CANDIDATE_CONSTANTS = (0.25, 0.5, 1.0, 2.0)
SEED = 7


def parse_glyph_field_with_controls(text: str) -> tuple[list[str], bool] | None:
    """`import_bbaw_egyptian.parse_glyph_field`, but recording the layout operators.

    Returns `(groups, has_control)` where each group is the word's signs with a
    Unicode joiner inserted at every adjacency the MdC field marked with `:` or `*`,
    or `None` when the importer would have dropped the row (lacuna / unreadable /
    no group). `-` marks a plain within-word adjacency with no quadrat claim and
    emits nothing, per the pre-registration.

    The loop below is deliberately a line-for-line copy of the importer's, so the
    groups it produces are the importer's groups and the gold segmentation is the
    one that actually shipped.
    """
    groups: list[list[str]] = []
    has_control = False

    def current() -> list[str]:
        if not groups:
            groups.append([])
        return groups[-1]

    for raw in str(text).split():
        prefix = OPERATOR_PREFIX_RE.match(raw)
        continues = bool(prefix)
        operators = prefix.group(0) if prefix else ""
        core = raw[prefix.end():] if prefix else raw
        core = MODIFIER_RE.sub("", core)
        if not core:
            continue
        if LACUNA_RE.match(core):
            return None
        if SHADING_RE.match(core):
            continue
        if CLOSER_RE.match(core):
            continue
        if OPENER_RE.match(core):
            if not continues and current():
                groups.append([])
            continue
        if UNREADABLE_RE.match(core):
            return None
        if ANNOTATION_RE.match(core):
            continue
        core = DECORATION_RE.sub("", core)
        if not core:
            continue
        if not continues and current():
            groups.append([])
        target = current()
        # A joiner only means something *between two signs of the same group*. It is
        # held back until a sign is actually appended: after a bare opener the
        # continuing token is the group's first sign (nothing to its left), and a
        # token whose only piece is a stray the importer discards appends no sign at
        # all — emitting the joiner there would leave it dangling at the front of the
        # next word and claim an adjacency the annotation never made.
        pending = ""
        if target:
            if ":" in operators:
                pending = VERTICAL_JOINER
            elif "*" in operators:
                pending = HORIZONTAL_JOINER

        def append(sign: str) -> None:
            nonlocal pending, has_control
            if pending:
                target.append(pending)
                has_control = True
                pending = ""
            target.append(sign)

        for piece in core.split("&"):  # `F39&Aa1` is a ligature of two signs
            if not piece:
                continue
            if NUMERAL_RE.match(piece):
                append(f"<g>NUM{piece}</g>")
            elif CODE_TOKEN_RE.match(piece):
                append(sign_for_code(piece))
            # else: a stray token. The importer records it and appends nothing, so
            # this branch does nothing either.
    out = ["".join(group) for group in groups if group]
    if not out:
        return None
    return out, has_control


def eligible_rows(parquet: Path, limit: int = 0) -> list[dict]:
    """Rows the importer would have accepted, that carry at least one `:`/`*`."""
    frame = pd.read_parquet(parquet)
    rows: list[dict] = []
    for record in frame.itertuples(index=False):
        transcription = to_corpus_convention(record.transcription or "")
        if not transcription or not search_fold(transcription):
            continue
        glyph_field = str(record.hieroglyphs or "").strip()
        if not glyph_field:
            continue
        parsed = parse_glyph_field_with_controls(glyph_field)
        if parsed is None:
            continue
        raw_groups, has_control = parsed
        if not has_control:
            continue
        # The importer's alignment filter: one sign group per transcription token.
        plain = [g.replace(VERTICAL_JOINER, "").replace(HORIZONTAL_JOINER, "") for g in raw_groups]
        tokens = transcription.split()
        if len(plain) != len(tokens):
            continue
        gold = normalize_hieroglyphs(" ".join(plain)).split()
        if len(gold) != len(plain) or len(gold) < 2:
            continue
        rows.append(
            {
                "transcription": transcription,
                "gold": gold,
                "with_controls": "".join(raw_groups),
                "without_controls": "".join(plain),
                "gold_key": " ".join(gold),
            }
        )
        if limit and len(rows) >= limit:
            break
    return rows


def hint_precision(rows: list[dict]) -> tuple[float, int, int]:
    """Share of control-marked boundaries that fall strictly inside a gold group."""
    inside = 0
    total = 0
    for row in rows:
        _groups, no_cut = quadrat_hints(row["with_controls"])
        gold_boundaries = boundaries(row["gold"])
        for position in no_cut:
            total += 1
            if position not in gold_boundaries:
                inside += 1
    return (inside / total if total else 0.0), inside, total


def score(tallies: dict[str, int]) -> dict[str, float]:
    tp, fp, fn = tallies["tp"], tallies["fp"], tallies["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": tallies["n"],
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "exact": round(tallies["exact"] / tallies["n"], 4) if tallies["n"] else 0.0,
    }


def run_shape(segmenter: Segmenter, rows: list[dict], shape: str) -> dict[str, float]:
    tallies = {"tp": 0, "fp": 0, "fn": 0, "exact": 0, "n": 0}
    for row in rows:
        gold = row["gold"]
        if shape == "with_controls":
            groups, no_cut = quadrat_hints(row["with_controls"])
            predicted = segmenter.segment(groups, no_cut=no_cut).groups
        elif shape == "controls_deleted":
            predicted = segmenter.segment([row["without_controls"]]).groups
        elif shape == "as_pasted":
            predicted = gold  # the importer's own grouping, the trivial ceiling
        else:  # pragma: no cover - guarded by the caller
            raise ValueError(shape)
        p, g = boundaries(predicted), boundaries(gold)
        tallies["tp"] += len(p & g)
        tallies["fp"] += len(p - g)
        tallies["fn"] += len(g - p)
        tallies["exact"] += int(predicted == gold)
        tallies["n"] += 1
    return score(tallies)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=str(EXAMPLES_PATH))
    parser.add_argument("--parquet", default=str(RAW_PARQUET))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--limit", type=int, default=0, help="At most N eligible rows.")
    parser.add_argument("--no-lexicon", action="store_true")
    args = parser.parse_args()

    rows = eligible_rows(Path(args.parquet), limit=args.limit)
    print(f"eligible BBAW rows (importer-accepted, with ':' or '*'): {len(rows):,}")
    if len(rows) < 500:
        raise SystemExit(
            f"STOP: fewer than 500 eligible rows ({len(rows)}) — the pre-registered "
            "stop condition for this step."
        )

    precision, inside, total = hint_precision(rows)
    print(
        f"hint precision: {precision:.4f} ({inside:,}/{total:,} control-marked "
        "boundaries fall strictly inside a gold word) — 1.0 by construction, which "
        "is why this is an upper bound"
    )

    rng = random.Random(SEED)
    order = list(range(len(rows)))
    rng.shuffle(order)
    cut = len(order) // 2
    dev = [rows[i] for i in order[:cut]]
    test = [rows[i] for i in order[cut:]]
    print(f"split seed {SEED}: dev {len(dev):,} rows / test {len(test):,} rows")

    frame = load_examples_csv(args.examples)
    held_out = {row["gold_key"] for row in rows}
    keep = ~frame["hieroglyphs_norm"].astype(str).isin(held_out)
    train = frame[keep]
    print(
        f"training frame {len(train):,} of {len(frame):,} rows "
        f"({int((~keep).sum()):,} removed by the memorisation guard)"
    )

    lexicon = None if args.no_lexicon else load_lexicon()
    model = train_reading_model(train, lexicon)

    records: list[dict] = []

    def add(config: str, constant: float, shape: str, half: str, metrics: dict) -> None:
        records.append(
            {"config": config, "quadrat_crossed": constant, "shape": shape, "half": half, **metrics}
        )

    base = Segmenter(
        model,
        DEFAULT_SEGMENTATION_WEIGHTS.replace(quadrat_crossed=0.0),
        use_lexicon=not args.no_lexicon,
    )
    for half, subset in (("dev", dev), ("test", test)):
        add("controls_deleted", 0.0, "unspaced", half, run_shape(base, subset, "controls_deleted"))
        add("as_pasted", 0.0, "as_pasted", half, run_shape(base, subset, "as_pasted"))

    for constant in CANDIDATE_CONSTANTS:
        segmenter = Segmenter(
            model,
            DEFAULT_SEGMENTATION_WEIGHTS.replace(quadrat_crossed=constant),
            use_lexicon=not args.no_lexicon,
        )
        for half, subset in (("dev", dev), ("test", test)):
            add(
                f"hints_{constant}",
                constant,
                "unspaced+controls",
                half,
                run_shape(segmenter, subset, "with_controls"),
            )

    results = pd.DataFrame(records)
    header = f"{'config':22s} {'shape':18s} {'half':5s} {'n':>6s}  {'P':>6s} {'R':>6s} {'F1':>6s} {'exact':>6s}"
    lines = [header, "-" * len(header)]
    for record in records:
        lines.append(
            f"{record['config']:22s} {record['shape']:18s} {record['half']:5s} "
            f"{record['n']:6.0f}  {record['precision']:6.3f} {record['recall']:6.3f} "
            f"{record['f1']:6.3f} {record['exact']:6.3f}"
        )
    table = "\n".join(lines)
    print()
    print(table)

    dev_hint_rows = [r for r in records if r["half"] == "dev" and r["config"].startswith("hints_")]
    best = max(dev_hint_rows, key=lambda r: (r["f1"], -r["quadrat_crossed"]))
    print(
        f"\nbest unspaced F1 on dev: quadrat_crossed={best['quadrat_crossed']} "
        f"(F1 {best['f1']:.4f}); paste 8/8 at that constant is a separate hard "
        "constraint, checked by scripts/run_expert_paste_eval.py --stage auto"
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "bbaw_upper_bound.csv"
    md_path = out_dir / "bbaw_upper_bound.md"
    results.to_csv(csv_path, index=False)
    md_path.write_text(
        "# BBAW upper bound on quadrat hints (item B, 2026-09-06)\n\n"
        f"Eligible rows: {len(rows):,}. Split seed {SEED}: dev {len(dev):,} / test "
        f"{len(test):,}. Hint precision {precision:.4f} ({inside:,}/{total:,}).\n"
        f"Training frame {len(train):,} of {len(frame):,} rows after the memorisation "
        "guard.\n\n"
        "`as_pasted` is the importer's own grouping handed back unchanged — the\n"
        "trivial ceiling, printed for orientation only.\n\n"
        "```\n" + table + "\n```\n\n"
        f"Best unspaced F1 on dev: quadrat_crossed={best['quadrat_crossed']} "
        f"(F1 {best['f1']:.4f}).\n",
        encoding="utf-8",
    )
    print(f"\nSaved {csv_path}\nSaved {md_path}")


if __name__ == "__main__":
    main()
