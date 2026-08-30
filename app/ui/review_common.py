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

from app.storage.db import DatabaseUnavailable, SessionLocal
from app.storage.repo import AnnotationRepo, ExampleRepo

ANNOTATION_STATUSES = ["accepted", "edited", "rejected", "uncertain"]

# CC BY-SA 4.0 §3(a) applies to every distribution of adapted material, not just to
# the repository. The reviewed export carries `transliteration_gold` and `translation`
# — TLA text, not this project's own work — so a copy that leaves the app must carry
# the attribution, the licence, the statement that it is adapted, and a link to the
# original. Shipped as a column rather than a comment header because a `#` line
# breaks `pd.read_csv` for anyone downstream.
LICENCE_NOTICE = (
    "Corpus text (transliteration_gold, translation) derived from the Thesaurus "
    "Linguae Aegyptiae, Earlier Egyptian corpus v18, ed. Richter & Werning (BBAW) "
    "and Fischer-Elfert & Dils (SAW Leipzig); https://thesaurus-linguae-aegyptiae.de "
    "— licensed CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). "
    "Adapted: normalised, re-segmented and extended with derived fields; see "
    "DATA-LICENSE.md. Annotation columns are this project's own editorial additions. "
    "Redistribution of this file must keep this notice and stay under CC BY-SA 4.0. "
    "No warranties are given; the licence may not give you all the permissions "
    "necessary for your intended use."
)


def with_licence_notice(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the CC BY-SA notice to every row of an export."""
    out = frame.copy()
    out["licence"] = LICENCE_NOTICE
    return out

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
    """Add the database `id` for each CSV row, so annotations can be attached.

    Raises DatabaseUnavailable rather than propagating a driver error, so the caller
    can decide to carry on read-only. A frame without an `id` column is still fully
    usable for reading, searching and browsing — only saving needs the ids.
    """
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        repo = ExampleRepo(session)
        id_map = {
            (source, source_text_id, source_sentence_id): example_id
            for example_id, source, source_text_id, source_sentence_id in (
                repo.list_example_keys()
            )
        }
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()

    out = df.copy()
    # Vectorised: the per-row .apply() over 12,772 rows was pure overhead.
    keys = pd.MultiIndex.from_arrays(
        [out["source"], out["source_text_id"], out["source_sentence_id"]]
    )
    out["id"] = [id_map.get(key) for key in keys]
    return out


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
    """Return (latest annotation, full history) for one example.

    One query, not two: the history is fetched and the newest row taken from it in
    Python. Asking the database for "latest" separately meant running the same
    ordered SELECT twice for every result row on every rerun.
    """
    if example_id is None:
        return None, annotation_history_to_df([])
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        repo = AnnotationRepo(session)
        rows = repo.list_for_example(example_id)
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()
    return (rows[0] if rows else None), annotation_history_to_df(rows)


def annotated_example_count() -> int:
    """How many examples carry at least one annotation.

    Home and Projects only need this number. They used to call
    `reviewed_annotation_rows()`, which pulls every annotation ever written *and*
    the full corpus row for each annotated example — on every sidebar click.
    """
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        return AnnotationRepo(session).count_annotated_examples()
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()


def annotated_example_ids() -> set[int]:
    """Ids of examples with at least one annotation (for badges in listings)."""
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        return set(AnnotationRepo(session).annotated_example_ids())
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()


def load_annotation_states(
    example_ids: list[int],
) -> dict[int, tuple[object | None, pd.DataFrame]]:
    """Latest annotation and history for many examples, in one query.

    The Workspace shows several parallels at once and each needs its own annotation
    state; fetching them one at a time meant a round trip per visible row on every
    rerun — including every keystroke in a note field.
    """
    wanted = [int(i) for i in example_ids if i is not None]
    if not wanted:
        return {}
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
    try:
        rows = AnnotationRepo(session).list_for_examples(wanted)
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()

    grouped: dict[int, list] = {example_id: [] for example_id in wanted}
    for row in rows:
        grouped.setdefault(row.example_id, []).append(row)
    return {
        example_id: (
            (history[0] if history else None),
            annotation_history_to_df(history),
        )
        for example_id, history in grouped.items()
    }


def reviewed_annotation_rows() -> list[dict]:
    """Every example that has at least one saved annotation, base + latest."""
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover - driver-level failure
        raise DatabaseUnavailable(str(exc)) from exc
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
    except DatabaseUnavailable:
        raise
    except Exception as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        session.close()


def build_reviewed_export_csv() -> str:
    buffer = StringIO()
    with_licence_notice(pd.DataFrame(reviewed_annotation_rows())).to_csv(
        buffer, index=False
    )
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
