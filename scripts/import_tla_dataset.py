from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import normalize_mdc, normalize_transliteration

DEFAULT_DATASET_PATH = (
    "thesaurus-linguae-aegyptiae/tla-Earlier_Egyptian_original-v18-premium"
)
DEFAULT_OUTPUT_PATH = "data/raw/real_examples_worklist.csv"
FALLBACK_WORKLIST_PATH = "data/raw/real_examples_worklist.csv"

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
    "tla_sentence_url",
    "lemma_ref",
    "notes_internal",
]

FIELD_ALIASES = {
    "source_text_id": [
        "source_text_id",
        "text_id",
        "textId",
        "text.id",
        "document.id",
        "source.id",
    ],
    "source_sentence_id": [
        "source_sentence_id",
        "sentence_id",
        "sentenceId",
        "sentence.id",
        "id",
        "_id",
    ],
    "language_stage": ["language_stage", "languageStage", "language", "stage"],
    "script_type": ["script_type", "scriptType", "script", "writingSystem"],
    "period": ["period", "dating", "date", "epoch"],
    "genre": ["genre", "textGenre", "category"],
    "hieroglyphs": ["hieroglyphs", "hieroglyphic", "glyphs", "mdcHieroglyphs"],
    "transliteration_gold": [
        "transliteration_gold",
        "transliteration",
        "transcription",
        "transcriptionAscii",
        "sentence.transliteration",
        "tokens.transliteration",
    ],
    "translation": [
        "translation",
        "translation_de",
        "translations.de",
        "german",
        "sentence.translation",
    ],
    "lemma_sequence": ["lemma_sequence", "lemmas", "lemmaIds", "tokens.lemma"],
    "upos": ["upos", "pos", "partOfSpeech", "tokens.upos"],
    "glossing": ["glossing", "gloss", "glosses", "tokens.gloss"],
    "source_ref": ["source_ref", "url", "tla_sentence_url", "reference"],
}

PARQUET_ALIASES = {
    "source_text_id": ["text_id", "source_text_id", "textId"],
    "source_sentence_id": ["sentence_id", "source_sentence_id", "sentenceId", "id"],
    "genre": ["genre", "textGenre", "category"],
    "hieroglyphs": ["hieroglyphs"],
    "transliteration_gold": ["transliteration", "transliteration_gold"],
    "translation": ["translation"],
    "lemma_sequence": ["lemmatization", "lemma_sequence", "lemmas"],
    "upos": ["UPOS", "upos"],
    "glossing": ["glossing"],
    "source_ref": ["source_ref", "url", "tla_sentence_url", "reference"],
}


# Conventional Egyptian chronology (Shaw, *The Oxford History of Ancient Egypt*),
# used to turn the TLA dateNotBefore/dateNotAfter range into a period label. Bounds
# are negative years, i.e. BC. Ordered from earliest to latest.
PERIOD_RANGES = [
    ("Predynastic Period", -4000, -3000),
    ("Early Dynastic Period", -3000, -2686),
    ("Old Kingdom", -2686, -2181),
    ("First Intermediate Period", -2181, -2055),
    ("Middle Kingdom", -2055, -1650),
    ("Second Intermediate Period", -1650, -1550),
    ("New Kingdom", -1550, -1069),
    ("Third Intermediate Period", -1069, -664),
    ("Late Period", -664, -332),
    ("Ptolemaic Period", -332, -30),
]


def _parse_year(value: object) -> int | None:
    text = _safe_str(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _derive_period(date_not_before: object, date_not_after: object) -> str:
    """Map a TLA date range onto a conventional period label.

    The midpoint of the attested range decides the period, so a text dated
    -1878..-1843 lands in the Middle Kingdom rather than being reported as the
    generic language stage. Returns "" when the dataset carries no usable dates,
    so the caller can fall back rather than invent a period.
    """
    start = _parse_year(date_not_before)
    end = _parse_year(date_not_after)
    if start is None and end is None:
        return ""
    if start is None:
        start = end
    if end is None:
        end = start
    midpoint = (start + end) / 2
    for label, lower, upper in PERIOD_RANGES:
        if lower <= midpoint < upper:
            return label
    # Dated, but outside the table above — report the range instead of guessing.
    return f"Undated range ({start} to {end})"


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "|".join(_safe_str(item) for item in value if _safe_str(item))
    if isinstance(value, dict):
        return "|".join(
            _safe_str(item)
            for item in value.values()
            if isinstance(item, (str, int, float))
        )
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(child, next_prefix))
        return out
    if isinstance(value, list):
        out = {prefix: value}
        if value and all(isinstance(item, dict) for item in value):
            child_keys = set().union(*(item.keys() for item in value))
            for child_key in child_keys:
                out[f"{prefix}.{child_key}"] = [
                    item.get(child_key, "") for item in value if isinstance(item, dict)
                ]
        return out
    return {prefix: value}


def _first(flat: dict[str, Any], aliases: list[str]) -> str:
    lower_lookup = {key.lower(): key for key in flat}
    for alias in aliases:
        if alias in flat:
            value = _safe_str(flat[alias])
            if value:
                return value
        key = lower_lookup.get(alias.lower())
        if key:
            value = _safe_str(flat[key])
            if value:
                return value
    for alias in aliases:
        alias_tail = alias.lower().split(".")[-1]
        for key, value in flat.items():
            if key.lower().split(".")[-1] == alias_tail:
                text = _safe_str(value)
                if text:
                    return text
    return ""


def _iter_json_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["rows", "data", "sentences", "items", "records"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _iter_csv_records(path: Path) -> list[dict[str, Any]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [dict(row) for row in reader]


def _iter_dataset_records(dataset_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    suffixes = {".json", ".jsonl", ".csv", ".tsv"}
    for path in sorted(dataset_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        try:
            if path.suffix.lower() in {".json", ".jsonl"}:
                records.extend(_iter_json_records(path))
            else:
                records.extend(_iter_csv_records(path))
        except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
            print(f"Skipped unreadable dataset file {path}: {exc}")
    return records


def _row_from_record(record: dict[str, Any], index: int) -> tuple[dict[str, str], bool, bool] | None:
    flat = _flatten(record)
    transliteration = _first(flat, FIELD_ALIASES["transliteration_gold"])
    if not transliteration:
        return None

    source_text_id = _first(flat, FIELD_ALIASES["source_text_id"])
    source_sentence_id = _first(flat, FIELD_ALIASES["source_sentence_id"])
    generated_text_id = not bool(source_text_id)
    generated_sentence_id = not bool(source_sentence_id)
    if generated_text_id:
        source_text_id = f"TLA_AUTO_{index:03d}"
    if generated_sentence_id:
        source_sentence_id = f"S{index:03d}"

    translit_ascii = normalize_transliteration(transliteration)
    mdc = normalize_mdc(translit_ascii)
    hieroglyphs = _first(flat, FIELD_ALIASES["hieroglyphs"])
    source_ref = _first(flat, FIELD_ALIASES["source_ref"])
    if not source_ref and source_sentence_id and not generated_sentence_id:
        source_ref = f"https://thesaurus-linguae-aegyptiae.de/sentence/{source_sentence_id}"

    row = {column: "" for column in FINAL_COLUMNS}
    row.update(
        {
            "source": "TLA",
            "source_text_id": source_text_id,
            "source_sentence_id": source_sentence_id,
            "language_stage": _first(flat, FIELD_ALIASES["language_stage"]),
            "script_type": _first(flat, FIELD_ALIASES["script_type"]),
            "genre": _first(flat, FIELD_ALIASES["genre"]),
            "period": _first(flat, FIELD_ALIASES["period"]),
            "hieroglyphs": hieroglyphs,
            "mdc": mdc,
            "sign_sequence": hieroglyphs or mdc,
            "display_sequence": hieroglyphs or transliteration,
            "normalized_reading_order": mdc,
            "transliteration_gold": transliteration,
            "translation": _first(flat, FIELD_ALIASES["translation"]),
            "lemma_sequence": _first(flat, FIELD_ALIASES["lemma_sequence"]),
            "upos": _first(flat, FIELD_ALIASES["upos"]),
            "glossing": _first(flat, FIELD_ALIASES["glossing"]),
            "grammar_notes": "",
            "source_ref": source_ref,
            "review_status": "seed",
            "aesthetic_arrangement_flag": "False",
            "tla_sentence_url": source_ref,
            "notes_internal": (
                "Imported from TLA premium dataset; mdc is a local ASCII query key "
                "derived from transliteration."
            ),
        }
    )
    return row, generated_text_id, generated_sentence_id


def _load_fallback_worklist(limit: int) -> pd.DataFrame:
    fallback_path = Path(FALLBACK_WORKLIST_PATH)
    if not fallback_path.exists():
        return pd.DataFrame(columns=FINAL_COLUMNS)
    df = pd.read_csv(fallback_path).fillna("")
    for column in FINAL_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df.loc[:, FINAL_COLUMNS].head(limit).copy()


def _row_value(row: pd.Series, aliases: list[str]) -> str:
    for alias in aliases:
        if alias in row.index:
            value = _safe_str(row.get(alias))
            if value:
                return value
    lower_lookup = {str(key).lower(): key for key in row.index}
    for alias in aliases:
        key = lower_lookup.get(alias.lower())
        if key is not None:
            value = _safe_str(row.get(key))
            if value:
                return value
    return ""


def _row_from_parquet(
    row: pd.Series,
    output_index: int,
    input_path: Path,
) -> tuple[dict[str, str], bool, bool] | None:
    transliteration = _row_value(row, PARQUET_ALIASES["transliteration_gold"])
    if not transliteration:
        return None

    source_text_id = _row_value(row, PARQUET_ALIASES["source_text_id"])
    source_sentence_id = _row_value(row, PARQUET_ALIASES["source_sentence_id"])
    generated_text_id = not bool(source_text_id)
    generated_sentence_id = not bool(source_sentence_id)
    if generated_text_id:
        source_text_id = f"TLA_EARLIER_{output_index:03d}"
    if generated_sentence_id:
        source_sentence_id = f"S{output_index:03d}"

    translit_ascii = normalize_transliteration(transliteration)
    mdc = normalize_mdc(translit_ascii)
    hieroglyphs = _row_value(row, PARQUET_ALIASES["hieroglyphs"])
    source_ref = _row_value(row, PARQUET_ALIASES["source_ref"])
    if not source_ref:
        source_ref = f"{input_path.as_posix()}#row={int(row.name) + 1}"

    date_not_before = _safe_str(row.get("dateNotBefore"))
    date_not_after = _safe_str(row.get("dateNotAfter"))
    date_note = ""
    if date_not_before or date_not_after:
        date_note = f"dateNotBefore={date_not_before}; dateNotAfter={date_not_after}"
    # The dataset dates every sentence, so derive a real period instead of stamping
    # every row with the language stage (which made the period filter useless).
    period = _derive_period(date_not_before, date_not_after) or "Earlier Egyptian"

    out = {column: "" for column in FINAL_COLUMNS}
    out.update(
        {
            "source": "TLA",
            "source_text_id": source_text_id,
            "source_sentence_id": source_sentence_id,
            "language_stage": "Earlier Egyptian",
            "script_type": "hieroglyphic/hieratic",
            "genre": _row_value(row, PARQUET_ALIASES["genre"]) or "unknown",
            "period": period,
            "hieroglyphs": hieroglyphs,
            "mdc": mdc,
            "sign_sequence": transliteration,
            "display_sequence": hieroglyphs or transliteration,
            "normalized_reading_order": mdc,
            "transliteration_gold": transliteration,
            "translation": _row_value(row, PARQUET_ALIASES["translation"]),
            "lemma_sequence": _row_value(row, PARQUET_ALIASES["lemma_sequence"]),
            "upos": _row_value(row, PARQUET_ALIASES["upos"]),
            "glossing": _row_value(row, PARQUET_ALIASES["glossing"]),
            "source_ref": source_ref,
            "review_status": "seed",
            "aesthetic_arrangement_flag": "False",
            "tla_sentence_url": source_ref,
            "notes_internal": (
                "Imported from local TLA Earlier Egyptian Parquet; mdc is a local "
                f"ASCII query key derived from transliteration. {date_note}".strip()
            ),
        }
    )
    return out, generated_text_id, generated_sentence_id


def _load_parquet_input(input_path: Path, limit: int) -> tuple[pd.DataFrame, int, int]:
    df = pd.read_parquet(input_path)
    rows: list[dict[str, str]] = []
    generated_text_ids = 0
    generated_sentence_ids = 0
    seen_keys: set[tuple[str, str, str]] = set()

    for _, row in df.iterrows():
        mapped = _row_from_parquet(row, len(rows) + 1, input_path)
        if mapped is None:
            continue
        out_row, generated_text_id, generated_sentence_id = mapped
        key = (
            out_row["source"],
            out_row["source_text_id"],
            out_row["source_sentence_id"],
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(out_row)
        generated_text_ids += int(generated_text_id)
        generated_sentence_ids += int(generated_sentence_id)
        if len(rows) >= limit:
            break

    return pd.DataFrame(rows, columns=FINAL_COLUMNS), generated_text_ids, generated_sentence_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        help="Local dataset file. Parquet inputs are read with pandas.read_parquet().",
    )
    parser.add_argument("--dataset-path", default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    generated_text_ids = 0
    generated_sentence_ids = 0
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        if input_path.suffix.lower() != ".parquet":
            raise ValueError("--input currently expects a local .parquet file")
        out, generated_text_ids, generated_sentence_ids = _load_parquet_input(
            input_path=input_path,
            limit=args.limit,
        )
    else:
        dataset_path = Path(args.dataset_path)
        rows: list[dict[str, str]] = []
        if dataset_path.exists():
            records = _iter_dataset_records(dataset_path)
            seen_keys: set[tuple[str, str, str]] = set()
            for record in records:
                mapped = _row_from_record(record, len(rows) + 1)
                if mapped is None:
                    continue
                row, generated_text_id, generated_sentence_id = mapped
                key = (row["source"], row["source_text_id"], row["source_sentence_id"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(row)
                generated_text_ids += int(generated_text_id)
                generated_sentence_ids += int(generated_sentence_id)
                if len(rows) >= args.limit:
                    break
            out = pd.DataFrame(rows, columns=FINAL_COLUMNS)
        else:
            print(f"Dataset path not found: {dataset_path}")
            print("Keeping the existing real TLA worklist path alive as fallback.")
            out = _load_fallback_worklist(args.limit)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print(f"Wrote {len(out)} TLA rows to {output_path}")
    print(f"Generated source_text_id values: {generated_text_ids}")
    print(f"Generated source_sentence_id values: {generated_sentence_ids}")
    if generated_text_ids or generated_sentence_ids:
        print(
            "Generated IDs are stable local IDs such as TLA_EARLIER_001 "
            "or TLA_AUTO_001 and S001."
        )


if __name__ == "__main__":
    main()
