"""Phase 3 — round trips, degraded mode, write gating, precomputation.

The audit measured the cost of a page view in database queries and a search in
seconds. These tests pin the shapes that produced those costs, so a regression is a
test failure rather than a bill: one query instead of one-per-row, a database outage
that leaves the corpus pages working, unbounded writes, and per-query work that only
depends on the corpus.
"""

from __future__ import annotations

import collections

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.retrieval.scorer import build_corpus_stats, document_frequencies, tokenize_query
from app.retrieval.tfidf import build_document_vectors, char_ngram_vector, cosine_score
from app.services.retrieval import build_search_index, retrieve_top_k
from app.storage.db import Base, DatabaseUnavailable
from app.storage.models import Annotation, Example
from app.storage.repo import AnnotationRepo


@pytest.fixture()
def db(tmp_path):
    """A throwaway SQLite database with a few examples and annotations."""
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    for index in range(1, 6):
        session.add(
            Example(
                source="test",
                source_text_id=f"T{index}",
                source_sentence_id=f"S{index}",
                genre="",
                period="",
                mdc="",
                sign_sequence="",
                transliteration_gold=f"reading {index}",
                mdc_norm="",
                sign_sequence_norm="",
                transliteration_norm="",
            )
        )
    session.commit()
    repo = AnnotationRepo(session)
    for example_id in (1, 2, 3):
        for revision in range(3):  # history, so "latest" has to choose
            repo.add_annotation(
                example_id=example_id,
                transliteration=f"v{revision}",
                status="edited",
            )
    session.commit()

    counter = collections.Counter()

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        counter[statement.strip().split()[0].upper()] += 1

    yield session, repo, counter
    session.close()


def queries(counter) -> int:
    return sum(counter.values())


# ---------- round trips ----------


def test_latest_for_one_example_is_a_single_query(db):
    session, repo, counter = db
    counter.clear()
    latest = repo.get_latest_for_example(1)
    assert latest is not None
    # Was two: "latest" re-ran the whole history query.
    assert queries(counter) == 1


def test_history_for_many_examples_is_a_single_query(db):
    session, repo, counter = db
    counter.clear()
    rows = repo.list_for_examples([1, 2, 3])
    assert {row.example_id for row in rows} == {1, 2, 3}
    assert queries(counter) == 1


def test_latest_for_examples_batches(db):
    session, repo, counter = db
    counter.clear()
    latest = repo.latest_for_examples([1, 2, 3])
    assert set(latest) == {1, 2, 3}
    assert all(row.transliteration == "v2" for row in latest.values())
    assert queries(counter) == 1


def test_counting_annotated_examples_does_not_fetch_them(db):
    session, repo, counter = db
    counter.clear()
    assert repo.count_annotated_examples() == 3
    assert queries(counter) == 1


def test_latest_only_does_not_scan_every_annotation(db):
    session, repo, counter = db
    all_rows = repo.list_all_annotations()
    latest = repo.list_latest_annotations_only()
    # 9 annotations exist, but only the 3 newest are the "latest" set.
    assert len(all_rows) == 9
    assert len(latest) == 3
    assert {row.transliteration for row in latest} == {"v2"}


def test_empty_id_list_costs_no_query(db):
    session, repo, counter = db
    counter.clear()
    assert repo.list_for_examples([]) == []
    assert repo.latest_for_examples([]) == {}
    assert queries(counter) == 0


# ---------- degraded mode ----------


def test_attach_db_ids_raises_database_unavailable(monkeypatch):
    """A dead database must surface as DatabaseUnavailable, not a driver error, so
    the UI can fall back to read-only instead of crashing every page."""
    from app.ui import review_common

    class Boom:
        def __call__(self):
            raise OSError("connection refused")

    monkeypatch.setattr(review_common, "SessionLocal", Boom())
    frame = pd.DataFrame(
        [{"source": "s", "source_text_id": "t", "source_sentence_id": "u"}]
    )
    with pytest.raises(DatabaseUnavailable):
        review_common.attach_db_ids(frame)


def test_annotation_helpers_raise_database_unavailable(monkeypatch):
    from app.ui import review_common

    class Boom:
        def __call__(self):
            raise OSError("connection refused")

    monkeypatch.setattr(review_common, "SessionLocal", Boom())
    for call in (
        lambda: review_common.load_annotation_state(1),
        lambda: review_common.load_annotation_states([1]),
        lambda: review_common.annotated_example_count(),
        lambda: review_common.annotated_example_ids(),
        lambda: review_common.reviewed_annotation_rows(),
    ):
        with pytest.raises(DatabaseUnavailable):
            call()


def test_load_annotation_states_of_nothing_is_empty():
    from app.ui import review_common

    assert review_common.load_annotation_states([]) == {}


def test_connect_timeout_is_configured_for_hosted_postgres():
    """A black-holed endpoint must fail, not hang the script thread forever."""
    import app.storage.db as db_module

    source = open(db_module.__file__).read()
    assert "connect_timeout" in source


# ---------- write limits ----------


def test_annotation_fields_are_clipped():
    from app.ui.whyptology_app import MAX_ANNOTATION_FIELD, clip

    assert len(clip("x" * 10_000)) == MAX_ANNOTATION_FIELD
    assert clip(None) == ""
    assert clip("short") == "short"


def test_reviewer_gate_is_open_when_no_key_is_configured(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setattr(app_module, "configured_reviewer_key", lambda: "")
    assert app_module.annotations_unlocked() is True


def test_reviewer_gate_closes_when_a_key_is_configured(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setattr(app_module, "configured_reviewer_key", lambda: "secret")
    monkeypatch.setattr(app_module, "st", _FakeStreamlit({}))
    assert app_module.annotations_unlocked() is False
    monkeypatch.setattr(
        app_module, "st", _FakeStreamlit({"whyptology_reviewer_ok": True})
    )
    assert app_module.annotations_unlocked() is True


class _FakeStreamlit:
    def __init__(self, state: dict):
        self.session_state = state


# ---------- precomputation correctness ----------


def small_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "t",
                "source_text_id": f"T{i}",
                "source_sentence_id": f"S{i}",
                "mdc_norm": text,
                "hieroglyphs_norm": glyphs,
                "transliteration_gold": text,
                "translation": "",
                "lemma_sequence": "",
                "normalized_reading_order_norm": "",
                "normalized_reading_order": "",
            }
            for i, (text, glyphs) in enumerate(
                [
                    ("htp dji nswt", "A B C"),
                    ("htp m pr", "A D"),
                    ("nswt bity", "C E"),
                ]
            )
        ]
    )


def test_precomputed_index_gives_identical_results():
    """The index is an optimisation only: same ranking, same scores."""
    df = small_frame()
    index = build_search_index(df)
    for query in ["htp dji nswt", "htp", "nswt"]:
        without = retrieve_top_k(df, query_mdc=query, k=5)
        with_index = retrieve_top_k(df, query_mdc=query, k=5, index=index)
        assert without["source_text_id"].tolist() == with_index["source_text_id"].tolist()
        assert without["final_score"].round(9).tolist() == (
            with_index["final_score"].round(9).tolist()
        )


def test_corpus_stats_match_direct_computation():
    df = small_frame()
    stats = build_corpus_stats(df)
    assert stats.mdc_frequencies == document_frequencies(df["mdc_norm"])
    assert stats.glyph_frequencies == document_frequencies(df["hieroglyphs_norm"])


def test_document_vectors_match_direct_cosine():
    df = small_frame()
    vectors = build_document_vectors(df["mdc_norm"])
    query_vector, query_norm = char_ngram_vector("htp dji nswt")
    for value, (vector, norm) in zip(df["mdc_norm"], vectors):
        direct = char_ngram_vector(value)
        assert cosine_score(query_vector, query_norm, vector, norm) == pytest.approx(
            cosine_score(query_vector, query_norm, *direct)
        )


def test_tokenizer_cache_returns_equal_but_independent_lists():
    """The cache must not hand out a shared mutable list."""
    first = tokenize_query("htp dji nswt")
    second = tokenize_query("htp dji nswt")
    assert first == second
    first.append("mutated")
    assert tokenize_query("htp dji nswt") == second


def test_search_does_not_mutate_the_corpus_frame():
    """load_corpus_csv is cache_resource — one shared frame across sessions — so
    every stage must copy rather than write into it."""
    df = small_frame()
    before = df.copy(deep=True)
    index = build_search_index(df)
    retrieve_top_k(df, query_mdc="htp dji nswt", k=5, index=index)
    retrieve_top_k(df, query_mdc="", k=5, query_hieroglyphs_norm="A B C", index=index)
    pd.testing.assert_frame_equal(df, before)
