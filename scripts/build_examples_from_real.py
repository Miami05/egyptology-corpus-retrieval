"""Turn the TLA worklist into a corpus CSV with the final column set.

This only *seeds* a TLA-only corpus (the original 12,772 Earlier Egyptian rows). It is
not the producer of the full corpus in data/processed/examples.csv: that file is the
seed plus the rows the import_* scripts append (`--append`). Writing it from the
worklist alone would drop every other source, so `--output` is required and an
existing output that holds more than the new rows is refused unless `--force` is given.

    python scripts/build_examples_from_real.py --output scratch/examples_tla.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_bbaw_egyptian import refuse_unsafe_output  # noqa: E402

INPUT_PATH = "data/raw/real_examples_worklist.csv"

FINAL_COLUMNS = [
    "source",
    "source_text_id",
    "source_sentence_id",
    "language_stage",
    "script_type",
    "genre",
    "period",
    "hieroglyphs",
    "mdc",
    "sign_sequence",
    "transliteration_gold",
    "translation",
    "lemma_sequence",
    "upos",
    "glossing",
    "grammar_notes",
    "source_ref",
    "review_status",
    "formula_type",
    "deity",
    "recipient",
    "offering_items",
    "formula_slot",
    "display_sequence",
    "normalized_reading_order",
    "alt_transliterations",
    "variant_writing_note",
    "morphology_note",
    "syntax_note",
    "aesthetic_arrangement_flag",
]

MIN_REQUIRED_FIELDS = [
    "source",
    "source_text_id",
    "source_sentence_id",
    "genre",
    "period",
    "mdc",
    "sign_sequence",
    "transliteration_gold",
]


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _normalize_defaults(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for col in FINAL_COLUMNS:
        if col not in out.columns:
            out[col] = ""

    out = out.fillna("")
    # An empty label stays visibly unknown; it used to be filled with
    # "offering_formula" / "Middle Egyptian", which asserts a genre and a period.
    out["genre"] = out["genre"].map(_safe_str).replace("", "unknown")
    out["period"] = out["period"].map(_safe_str).replace("", "unknown")
    out["review_status"] = out["review_status"].map(_safe_str).replace("", "seed")

    for col in FINAL_COLUMNS:
        out[col] = out[col].map(_safe_str)

    return out


def _is_complete_row(row: pd.Series) -> bool:
    for field in MIN_REQUIRED_FIELDS:
        if not _safe_str(row.get(field, "")):
            return False
    return True


def _refuse_to_shrink(output: Path, ready: pd.DataFrame) -> None:
    """Exit when `output` already holds rows this build would lose."""
    if not output.exists():
        return
    held = pd.read_csv(output, dtype=str, usecols=["source"]).fillna("")["source"]
    lost_sources = sorted(set(held) - set(ready["source"]))
    if lost_sources or len(held) > len(ready):
        raise SystemExit(
            f"refusing to overwrite {output}: it holds {len(held):,} rows "
            f"(sources: {', '.join(sorted(set(held)))}) and this build has "
            f"{len(ready):,} rows (sources: {', '.join(sorted(set(ready['source'])))}). "
            "Pick another --output, or pass --force."
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", default=INPUT_PATH, help="The TLA worklist CSV.")
    parser.add_argument(
        "--output",
        required=True,
        help="CSV to write. Required: the old default was the 130k-row corpus itself.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite --output even if it holds rows (or sources) this build lacks.",
    )
    args = parser.parse_args(argv)
    refuse_unsafe_output(args.output, allow_corpus=True)

    df = pd.read_csv(args.input)
    df = _normalize_defaults(df)

    complete_mask = cast(pd.Series, df.apply(_is_complete_row, axis=1))
    ready = cast(pd.DataFrame, df.loc[complete_mask, :].copy())
    skipped = cast(pd.DataFrame, df.loc[~complete_mask, :].copy())

    if ready.empty:
        print("No complete real rows found yet.")
        print(
            "Fill at least the minimum required fields in data/raw/real_examples_worklist.csv"
        )
        return

    ready = cast(pd.DataFrame, ready.loc[:, FINAL_COLUMNS].copy())
    ready = cast(
        pd.DataFrame,
        ready.drop_duplicates(
            subset=["source", "source_text_id", "source_sentence_id"],
            keep="first",
        ),
    )

    output = Path(args.output)
    if not args.force:
        _refuse_to_shrink(output, ready)
    output.parent.mkdir(parents=True, exist_ok=True)
    ready.to_csv(output, index=False)

    print(f"Wrote {len(ready)} complete rows to {output}")

    if not skipped.empty:
        print(f"Skipped {len(skipped)} incomplete worklist rows.")
        print("Incomplete rows:")
        for _, row in skipped.iterrows():
            print(
                f"- source={row.get('source', '')} "
                f"text_id={row.get('source_text_id', '')} "
                f"sentence_id={row.get('source_sentence_id', '')}"
            )


if __name__ == "__main__":
    main()
