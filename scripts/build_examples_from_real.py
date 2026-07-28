from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INPUT_PATH = "data/raw/real_examples_worklist.csv"
OUTPUT_PATH = "data/processed/examples.csv"

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
    out["genre"] = out["genre"].map(_safe_str).replace("", "offering_formula")
    out["period"] = out["period"].map(_safe_str).replace("", "Middle Egyptian")
    out["review_status"] = out["review_status"].map(_safe_str).replace("", "seed")

    for col in FINAL_COLUMNS:
        out[col] = out[col].map(_safe_str)

    return out


def _is_complete_row(row: pd.Series) -> bool:
    for field in MIN_REQUIRED_FIELDS:
        if not _safe_str(row.get(field, "")):
            return False
    return True


def main() -> None:
    df = pd.read_csv(INPUT_PATH)
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

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    ready.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(ready)} complete rows to {OUTPUT_PATH}")

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
