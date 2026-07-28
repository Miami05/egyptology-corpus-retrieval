from __future__ import annotations

import pandas as pd
import pytest

from app.storage.db import normalise_database_url


class TestNormaliseDatabaseUrl:
    """Hosted providers hand out `postgres://`, which SQLAlchemy refuses to parse.

    Getting this wrong is a crash on boot in production and nowhere else, so it is
    worth pinning even though it is three lines of code.
    """

    @pytest.mark.parametrize(
        "given",
        [
            "postgres://user:pw@host.neon.tech/db",
            "postgresql://user:pw@host.neon.tech/db",
        ],
    )
    def test_postgres_schemes_get_an_explicit_driver(self, given: str) -> None:
        result = normalise_database_url(given)
        assert result.startswith("postgresql+psycopg://")
        # Credentials and target must survive untouched.
        assert result.endswith("user:pw@host.neon.tech/db")

    def test_sqlite_urls_are_left_alone(self) -> None:
        assert normalise_database_url("sqlite:///egyptology.db") == (
            "sqlite:///egyptology.db"
        )

    def test_an_already_qualified_driver_is_not_doubled(self) -> None:
        given = "postgresql+psycopg://user@host/db"
        assert normalise_database_url(given) == given


def _one_row_frame() -> pd.DataFrame:
    """Minimal frame with every column example_payload reads."""
    columns = [
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
        "mdc_norm",
        "sign_sequence_norm",
        "transliteration_norm",
        "formula_type_norm",
        "deity_norm",
        "recipient_norm",
        "offering_items_norm",
        "formula_slot_norm",
        "display_sequence_norm",
        "normalized_reading_order_norm",
        "alt_transliterations_norm",
    ]
    row = {name: "x" for name in columns}
    row["aesthetic_arrangement_flag_bool"] = False
    return pd.DataFrame([row])


def test_example_payload_covers_every_model_column() -> None:
    """Guards the mapping against a column being added to the model and forgotten.

    The mapping used to be duplicated between the importer script and the app; a new
    column could land in one and not the other. Now there is one payload builder, and
    this asserts it stays in step with the table.
    """
    from app.storage.bootstrap import example_payload
    from app.storage.models import Example

    payload = example_payload(_one_row_frame().iloc[0])

    model_columns = {c.name for c in Example.__table__.columns}
    # id is autoincrement; created_at style columns default server-side.
    settable = {
        name
        for name in model_columns
        if name != "id" and not Example.__table__.columns[name].default
    }
    missing = settable - set(payload) - {"created_at", "updated_at"}

    assert not missing, f"example_payload is missing model columns: {sorted(missing)}"
