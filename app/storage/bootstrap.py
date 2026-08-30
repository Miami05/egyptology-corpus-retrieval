"""Create and seed the database from the processed CSV.

The database is gitignored (SQLite) or entirely external (Postgres), so a fresh
deployment starts with no schema and no rows. `ensure_corpus_ready` builds the schema
and imports `data/processed/examples.csv` when the corpus table is empty, which is what
gives every row the stable `id` that annotations are attached to.

The column mapping lives once, in `example_payload`, and is shared by the fast bulk
seed and the incremental upsert used by scripts/import_examples.py.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select

from app.storage.db import Base, SessionLocal, engine
from app.storage.models import EvaluationResult  # noqa: F401
from app.storage.models import Annotation, Example  # noqa: F401
from app.storage.repo import ExampleRepo

# Importing the models above is what registers the tables on Base.metadata;
# without them create_all() would silently create nothing.

# Chunk size for the bulk seed. Large enough that a remote round trip is amortised,
# small enough that one statement does not exceed a provider's query size limits.
BULK_CHUNK = 1000


def create_tables() -> None:
    """Create any missing tables. Existing tables and rows are left alone."""
    Base.metadata.create_all(bind=engine)


def example_count() -> int:
    session = SessionLocal()
    try:
        return session.execute(select(func.count()).select_from(Example)).scalar_one()
    finally:
        session.close()


def example_payload(row: pd.Series) -> dict[str, object]:
    """Map one CSV row to Example column values.

    Single source of truth for the mapping — it is long, and having it twice is how
    a new column silently gets left out of one code path.
    """
    return {
        "source": row["source"],
        "source_text_id": row["source_text_id"],
        "source_sentence_id": row["source_sentence_id"],
        "language_stage": row["language_stage"],
        "script_type": row["script_type"],
        "genre": row["genre"],
        "period": row["period"],
        "hieroglyphs": row["hieroglyphs"],
        "mdc": row["mdc"],
        "sign_sequence": row["sign_sequence"],
        "transliteration_gold": row["transliteration_gold"],
        "translation": row["translation"],
        "lemma_sequence": row["lemma_sequence"],
        "upos": row["upos"],
        "glossing": row["glossing"],
        "grammar_notes": row["grammar_notes"],
        "source_ref": row["source_ref"],
        "review_status": row["review_status"],
        "formula_type": row["formula_type"],
        "deity": row["deity"],
        "recipient": row["recipient"],
        "offering_items": row["offering_items"],
        "formula_slot": row["formula_slot"],
        "display_sequence": row["display_sequence"],
        "normalized_reading_order": row["normalized_reading_order"],
        "alt_transliterations": row["alt_transliterations"],
        "variant_writing_note": row["variant_writing_note"],
        "morphology_note": row["morphology_note"],
        "syntax_note": row["syntax_note"],
        "aesthetic_arrangement_flag": bool(row["aesthetic_arrangement_flag_bool"]),
        "mdc_norm": row["mdc_norm"],
        "sign_sequence_norm": row["sign_sequence_norm"],
        "transliteration_norm": row["transliteration_norm"],
        "formula_type_norm": row["formula_type_norm"],
        "deity_norm": row["deity_norm"],
        "recipient_norm": row["recipient_norm"],
        "offering_items_norm": row["offering_items_norm"],
        "formula_slot_norm": row["formula_slot_norm"],
        "display_sequence_norm": row["display_sequence_norm"],
        "normalized_reading_order_norm": row["normalized_reading_order_norm"],
        "alt_transliterations_norm": row["alt_transliterations_norm"],
    }


def bulk_insert_examples(df: pd.DataFrame) -> int:
    """Insert every row with no per-row SELECT. Only safe on an empty corpus table.

    The upsert path issues a lookup plus a write per row. That is ~25,000 round trips
    for this corpus: unnoticeable on local SQLite, minutes against hosted Postgres,
    during which the app looks hung on its very first page load. Chunked bulk inserts
    turn it into a few dozen statements.
    """
    payloads = [example_payload(row) for _, row in df.iterrows()]

    session = SessionLocal()
    try:
        for start in range(0, len(payloads), BULK_CHUNK):
            session.bulk_insert_mappings(
                Example, payloads[start : start + BULK_CHUNK]
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return len(payloads)


def upsert_examples(df: pd.DataFrame) -> dict[str, object]:
    """Insert or refresh one corpus row per CSV row, preserving annotations.

    Returns counts of created/updated/unchanged rows plus a per-field tally of
    what was refreshed on rows that already existed.
    """
    session = SessionLocal()
    created = 0
    updated = 0
    unchanged = 0
    field_changes: dict[str, int] = {}

    try:
        repo = ExampleRepo(session)

        for _, row in df.iterrows():
            _, was_created, changed = repo.upsert_example(**example_payload(row))

            if was_created:
                created += 1
            elif changed:
                updated += 1
                for field in changed:
                    field_changes[field] = field_changes.get(field, 0) + 1
            else:
                unchanged += 1
    finally:
        session.close()

    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "field_changes": field_changes,
    }


def sync_new_examples(df: pd.DataFrame) -> dict[str, int]:
    """Insert corpus rows the database does not have yet, and touch nothing else.

    The upsert path issues a SELECT and a write per row — fine for a first import
    into an empty SQLite file, punishing against hosted Postgres: growing the corpus
    from 12,772 to 16,373 rows would be 16,373 round trips on a free tier that has
    already hit its transfer quota once. This reads the existing keys in one query
    (four columns, the same call `attach_db_ids` uses) and bulk-inserts only what is
    missing, so adding a corpus costs a handful of statements.

    Existing rows keep their `id`, so every saved annotation stays attached. Use
    `upsert_examples` instead when the *content* of existing rows has changed.
    """
    create_tables()
    session = SessionLocal()
    try:
        existing = {
            (source, text_id, sentence_id)
            for _, source, text_id, sentence_id in ExampleRepo(
                session
            ).list_example_keys()
        }
    finally:
        session.close()

    missing = [
        example_payload(row)
        for _, row in df.iterrows()
        if (row["source"], row["source_text_id"], row["source_sentence_id"])
        not in existing
    ]
    if missing:
        session = SessionLocal()
        try:
            for start in range(0, len(missing), BULK_CHUNK):
                session.bulk_insert_mappings(
                    Example, missing[start : start + BULK_CHUNK]
                )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    return {
        "already_present": len(df) - len(missing),
        "inserted": len(missing),
        "total": len(df),
    }


def ensure_corpus_ready(df: pd.DataFrame) -> int:
    """Make the database usable, then report how many corpus rows it holds.

    Safe to call on every app start: the schema step is idempotent, and seeding only
    runs when the corpus table is empty, so a populated database is never re-imported
    and existing annotations are never disturbed. That empty-table guard is
    load-bearing — do not remove it.
    """
    create_tables()

    count = example_count()
    if count == 0:
        bulk_insert_examples(df)
        count = example_count()

    return count
