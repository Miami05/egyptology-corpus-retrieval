from __future__ import annotations

import pandas as pd

from app.data.normalizer import (
    normalize_hieroglyphs,
    normalize_label,
    normalize_mdc,
    normalize_pipe_list,
    normalize_sign_sequence,
    normalize_transliteration,
    parse_bool,
)

REQUIRED_COLUMNS = [
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


def load_examples_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    df["mdc_norm"] = df["mdc"].astype(str).map(normalize_mdc)
    df["sign_sequence_norm"] = (
        df["sign_sequence"].astype(str).map(normalize_sign_sequence)
    )
    # Searchable sign key. Without this the hieroglyphs are only ever displayed,
    # so a user holding signs rather than a transliteration cannot query at all.
    df["hieroglyphs_norm"] = df["hieroglyphs"].astype(str).map(normalize_hieroglyphs)
    df["transliteration_norm"] = (
        df["transliteration_gold"].astype(str).map(normalize_transliteration)
    )
    df["formula_type_norm"] = df["formula_type"].astype(str).map(normalize_label)
    df["deity_norm"] = df["deity"].astype(str).map(normalize_label)
    df["recipient_norm"] = df["recipient"].astype(str).map(normalize_label)
    df["offering_items_norm"] = (
        df["offering_items"].astype(str).map(normalize_pipe_list)
    )
    df["formula_slot_norm"] = df["formula_slot"].astype(str).map(normalize_label)

    df["display_sequence_norm"] = (
        df["display_sequence"].astype(str).map(normalize_sign_sequence)
    )
    df["normalized_reading_order_norm"] = (
        df["normalized_reading_order"].astype(str).map(normalize_sign_sequence)
    )
    df["alt_transliterations_norm"] = (
        df["alt_transliterations"].astype(str).map(normalize_pipe_list)
    )
    df["aesthetic_arrangement_flag_bool"] = df["aesthetic_arrangement_flag"].map(
        parse_bool
    )
    return df
