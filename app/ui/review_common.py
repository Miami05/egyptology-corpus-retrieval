"""Database-facing helpers shared by the Streamlit front ends.

The corpus is loaded from CSV but annotations live in SQLite, so every review
surface needs the same three things: a way to map CSV rows back to their database
IDs, a way to read an example's annotation history, and a way to export the
reviewed rows. Keeping them here means the reading-suggestion workspace and the
older annotation app cannot drift apart.
"""

from __future__ import annotations

from io import StringIO

import pandas as pd

from app.storage.db import SessionLocal
from app.storage.repo import AnnotationRepo, ExampleRepo

ANNOTATION_STATUSES = ["accepted", "edited", "rejected", "uncertain"]

HISTORY_COLUMNS = [
    "id",
    "status",
    "transliteration",
    "normalized_reading_order",
    "variant_writing_note",
    "morphology_note",
    "syntax_note",
    "aesthetic_arrangement_flag",
    "created_at",
]


def safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return "" if text.lower() == "nan" else text


def coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


def attach_db_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Add the SQLite `id` for each CSV row, so annotations can be attached."""
    session = SessionLocal()
    try:
        repo = ExampleRepo(session)
        id_map = {
            (source, source_text_id, source_sentence_id): example_id
            for example_id, source, source_text_id, source_sentence_id in (
                repo.list_example_keys()
            )
        }
        out = df.copy()
        out["id"] = out.apply(
            lambda row: id_map.get(
                (
                    row["source"],
                    row["source_text_id"],
                    row["source_sentence_id"],
                )
            ),
            axis=1,
        )
        return out
    finally:
        session.close()


def build_row_key(row: pd.Series, position: int) -> str:
    """Stable per-row key so Streamlit widget state does not collide."""
    db_id = safe_str(row.get("id")) or "noid"
    source = safe_str(row.get("source"))
    text_id = safe_str(row.get("source_text_id"))
    sentence_id = safe_str(row.get("source_sentence_id"))
    return f"{position}_{db_id}_{source}_{text_id}_{sentence_id}"


def annotation_history_to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=pd.Index(HISTORY_COLUMNS))
    return pd.DataFrame(
        [
            {
                "id": row.id,
                "status": row.status,
                "transliteration": row.transliteration,
                "normalized_reading_order": row.normalized_reading_order,
                "variant_writing_note": row.variant_writing_note,
                "morphology_note": row.morphology_note,
                "syntax_note": row.syntax_note,
                "aesthetic_arrangement_flag": bool(row.aesthetic_arrangement_flag),
                "created_at": row.created_at,
            }
            for row in rows
        ]
    )


def load_annotation_state(example_id: int | None) -> tuple[object | None, pd.DataFrame]:
    """Return (latest annotation, full history) for one example."""
    if example_id is None:
        return None, annotation_history_to_df([])
    session = SessionLocal()
    try:
        repo = AnnotationRepo(session)
        latest = repo.get_latest_for_example(example_id)
        history = annotation_history_to_df(repo.list_for_example(example_id))
        return latest, history
    finally:
        session.close()


def reviewed_annotation_rows() -> list[dict]:
    """Every example that has at least one saved annotation, base + latest."""
    session = SessionLocal()
    try:
        example_repo = ExampleRepo(session)
        annotation_repo = AnnotationRepo(session)

        latest_annotations = {
            row.example_id: row
            for row in annotation_repo.list_latest_annotations_only()
        }
        examples = example_repo.list_examples_by_ids(list(latest_annotations))

        export_rows: list[dict] = []
        for example in examples:
            latest = latest_annotations.get(example.id)
            if latest is None:
                continue
            export_rows.append(
                {
                    "example_id": example.id,
                    "source": example.source,
                    "source_text_id": example.source_text_id,
                    "source_sentence_id": example.source_sentence_id,
                    "language_stage": example.language_stage,
                    "script_type": example.script_type,
                    "genre": example.genre,
                    "period": example.period,
                    "hieroglyphs": example.hieroglyphs,
                    "mdc": example.mdc,
                    "sign_sequence": example.sign_sequence,
                    "transliteration_gold": example.transliteration_gold,
                    "translation": example.translation,
                    "lemma_sequence": example.lemma_sequence,
                    "upos": example.upos,
                    "glossing": example.glossing,
                    "formula_type": example.formula_type,
                    "deity": example.deity,
                    "recipient": example.recipient,
                    "offering_items": example.offering_items,
                    "formula_slot": example.formula_slot,
                    "base_display_sequence": example.display_sequence,
                    "base_normalized_reading_order": example.normalized_reading_order,
                    "base_alt_transliterations": example.alt_transliterations,
                    "base_variant_writing_note": example.variant_writing_note,
                    "base_morphology_note": example.morphology_note,
                    "base_syntax_note": example.syntax_note,
                    "base_aesthetic_arrangement_flag": bool(
                        example.aesthetic_arrangement_flag
                    ),
                    "latest_transliteration": latest.transliteration,
                    "latest_status": latest.status,
                    "latest_uncertainty_note": latest.uncertainty_note or "",
                    "latest_grammar_note": latest.grammar_note or "",
                    "latest_display_sequence": latest.display_sequence or "",
                    "latest_normalized_reading_order": (
                        latest.normalized_reading_order or ""
                    ),
                    "latest_alt_transliterations": latest.alt_transliterations or "",
                    "latest_variant_writing_note": latest.variant_writing_note or "",
                    "latest_morphology_note": latest.morphology_note or "",
                    "latest_syntax_note": latest.syntax_note or "",
                    "latest_aesthetic_arrangement_flag": bool(
                        latest.aesthetic_arrangement_flag
                    ),
                    "source_ref": example.source_ref,
                    "latest_annotation_created_at": latest.created_at,
                }
            )
        return export_rows
    finally:
        session.close()


def build_reviewed_export_csv() -> str:
    buffer = StringIO()
    pd.DataFrame(reviewed_annotation_rows()).to_csv(buffer, index=False)
    return buffer.getvalue()


def score_breakdown_lines(row: pd.Series) -> list[str]:
    keys = [
        "fuzzy_score",
        "tfidf_score",
        "overlap_score",
        "idf_overlap_score",
        "exact_bonus",
        "glyph_overlap_score",
        "glyph_idf_overlap_score",
        "glyph_order_score",
        "glyph_exact_bonus",
        "reading_order_overlap",
        "final_score",
    ]
    return [f"{key}: {float(row[key]):.4f}" for key in keys if key in row]
