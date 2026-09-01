"""Seeding and id-attachment against a real, temporary database.

Three properties that only show up in production and are therefore worth pinning:
the bulk seed inserts every row exactly once across chunk boundaries; a second boot
leaves a populated table and its annotations untouched (the guard that protects an
expert's corrections); and attaching database ids never downloads whole corpus rows —
the query that exhausted the hosted database's data-transfer quota twice.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests.test_storage_bootstrap import _one_row_frame


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """A fresh SQLite file wired into bootstrap and review_common in place of the
    module-level engine, so these tests never touch the developer's egyptology.db."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.storage.bootstrap as bootstrap
    import app.ui.review_common as review_common
    from app.storage.db import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(bootstrap, "engine", engine)
    monkeypatch.setattr(bootstrap, "SessionLocal", session_factory)
    monkeypatch.setattr(review_common, "SessionLocal", session_factory)
    return session_factory


def _frame(n: int) -> pd.DataFrame:
    """n distinct corpus rows with every column example_payload reads."""
    base = _one_row_frame().iloc[0].to_dict()
    rows = []
    for i in range(n):
        row = dict(base)
        row["source"] = "TEST"
        row["source_text_id"] = f"T{i // 10}"
        row["source_sentence_id"] = f"S{i}"
        row["transliteration_gold"] = f"reading {i}"
        rows.append(row)
    return pd.DataFrame(rows)


def test_bulk_seed_inserts_every_row_across_chunk_boundaries(isolated_db) -> None:
    """Row count must be exact when the frame is larger than one chunk and not a
    multiple of it — the two places an off-by-one in chunking would hide."""
    import app.storage.bootstrap as bootstrap

    n = bootstrap.BULK_CHUNK * 2 + 7
    assert bootstrap.ensure_corpus_ready(_frame(n)) == n
    assert bootstrap.example_count() == n


def test_seeding_twice_neither_duplicates_nor_overwrites(isolated_db) -> None:
    """The empty-table guard is load-bearing: a second boot must leave the table —
    and any annotation attached to it — exactly as it was."""
    import app.storage.bootstrap as bootstrap
    from app.storage.repo import AnnotationRepo, ExampleRepo

    df = _frame(25)
    assert bootstrap.ensure_corpus_ready(df) == 25

    session = isolated_db()
    try:
        first_id = ExampleRepo(session).list_example_keys()[0][0]
        AnnotationRepo(session).add_annotation(first_id, "corrected reading")
    finally:
        session.close()

    # Second boot with a *changed* frame: nothing may be inserted or refreshed.
    changed = df.copy()
    changed["transliteration_gold"] = "SHOULD NOT LAND"
    assert bootstrap.ensure_corpus_ready(changed) == 25
    assert bootstrap.example_count() == 25

    session = isolated_db()
    try:
        example = ExampleRepo(session).get_example(first_id)
        assert example is not None
        assert example.transliteration_gold == "reading 0"
        assert len(AnnotationRepo(session).list_for_example(first_id)) == 1
    finally:
        session.close()


def test_attach_db_ids_never_pulls_full_corpus_rows(isolated_db, monkeypatch) -> None:
    """Regression for the Neon outage: the id map must come from the four-column
    select. Downloading every column of every row on each boot is what exhausted the
    free tier's data-transfer quota, twice."""
    import app.storage.bootstrap as bootstrap
    from app.storage.repo import ExampleRepo
    from app.ui.review_common import attach_db_ids

    df = _frame(12)
    bootstrap.ensure_corpus_ready(df)

    def forbidden(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("this call pulls whole corpus rows over the wire")

    monkeypatch.setattr(ExampleRepo, "list_examples", forbidden)
    monkeypatch.setattr(ExampleRepo, "list_examples_by_ids", forbidden)

    out = attach_db_ids(df)
    assert "id" in out.columns
    assert out["id"].notna().all()
    assert out["id"].nunique() == 12
