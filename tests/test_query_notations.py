"""Every notation a reading can be typed in must reach the same corpus rows.

Each test here pins one half of the defect an Egyptologist reported on 2026-09-01:
she queried `ꜥḥꜥ.n stẖ qnd r ḏw ꜣꜥ wr` on the web and `aHa.n stX qnd r Dw Aa wr` on
her phone, and both found nothing. The causes were independent — a query fold that
deleted the Egyptological letters instead of folding them, an index built from a
column that 37% of the corpus ships empty, and "MdC" naming a scheme the tool never
implemented — so they are pinned independently.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.loader import load_examples_csv
from app.data.normalizer import normalize_mdc, search_fold
from app.data.query import mdc_to_transliteration, parse_query
from app.services.retrieval import build_search_index, retrieve_top_k

EXAMPLES_PATH = "data/processed/examples.csv"

# The four ways to write the opening of the sentence she tried.
UNICODE_QUERY = "ꜥḥꜥ.n stẖ qnd r ḏw ꜣꜥ wr"
MDC_QUERY = "aHa.n stX qnd r Dw Aa wr"


@pytest.fixture(scope="module")
def corpus() -> pd.DataFrame:
    return load_examples_csv(EXAMPLES_PATH)


@pytest.fixture(scope="module")
def index(corpus: pd.DataFrame):
    return build_search_index(corpus)


# --- the fold ---------------------------------------------------------------


def test_egyptological_letters_are_folded_not_deleted() -> None:
    """`normalize_mdc` alone deletes them; the search key must fold them.

    This is the original defect: the query reached the corpus as `n st qnd r w wr`.
    """
    assert normalize_mdc(UNICODE_QUERY) == "n st qnd r w wr"
    assert search_fold(UNICODE_QUERY) == "ahan stkh qnd r djw aa wr"


def test_suffix_marker_separates_whether_or_not_it_is_spaced() -> None:
    """The corpus tokenises `ḏd =f` as two tokens, so `ḏd=f` must not become one."""
    assert search_fold("ḏd=f ḏd=ꞽ n=ṯn") == search_fold("ḏd =f ḏd =ꞽ n =ṯn")
    assert search_fold("ḏd=f") == "djd f"


def test_manuel_de_codage_letters_become_transliteration() -> None:
    assert mdc_to_transliteration(MDC_QUERY) == "ꜥḥꜥ.n stẖ qnd r ḏw ꜣꜥ wr"


# --- the parser -------------------------------------------------------------


def test_mdc_and_unicode_reduce_to_the_same_search_key(index) -> None:
    vocabulary = index.vocabulary
    assert (
        parse_query(MDC_QUERY, vocabulary=vocabulary).search_key
        == parse_query(UNICODE_QUERY, vocabulary=vocabulary).search_key
    )


def test_mdc_is_chosen_on_evidence_not_on_capital_letters(index) -> None:
    """`stX` is ẖ, and the corpus is what says so: the MdC reading of the string has
    more tokens the corpus actually contains than the plain-ASCII reading does."""
    parse = parse_query(MDC_QUERY, vocabulary=index.vocabulary)
    assert parse.notation == "mdc"
    assert parse.reading == UNICODE_QUERY


def test_plain_ascii_is_not_mistaken_for_mdc(index) -> None:
    """A lower-case ASCII query has no MdC-only letter and must stay ASCII, or every
    `htp di nsw` would be re-read as ḥtp dꞽ nsw and lose its i."""
    parse = parse_query("htp di nsw", vocabulary=index.vocabulary)
    assert parse.notation == "ascii"
    assert parse.search_key == "htp di nsw"


def test_a_supplied_sign_grouping_survives_an_empty_raw_query() -> None:
    """The workspace resegments a paste and then searches on the groups alone; the
    parser must not treat that as an empty query (it did, and returned nothing)."""
    parse = parse_query("", hieroglyphs_norm="\U00013000 \U00013001")
    assert parse.is_hieroglyphic
    assert not parse.is_empty


def test_hieroglyph_query_ignores_latin_apparatus() -> None:
    parse = parse_query("line 2: \U00013000\U00013001 (sic)")
    assert parse.notation == "hieroglyphs"
    assert parse.search_key == ""


# --- end to end -------------------------------------------------------------


def test_every_corpus_row_is_reachable_by_transliteration(corpus: pd.DataFrame) -> None:
    """No row may sit in the corpus with an empty reading key.

    All 9,823 AES rows did: their `mdc` column ships empty and the index was built
    from that column, so 37% of the corpus could not be found by any transliteration
    query at all.
    """
    empty = corpus["mdc_norm"].astype(str).str.strip() == ""
    has_reading = corpus["transliteration_gold"].astype(str).str.strip() != ""
    assert not (empty & has_reading).any()


@pytest.mark.parametrize("source", ["TLA", "AES"])
def test_a_corpus_sentence_finds_itself(corpus, index, source: str) -> None:
    """The weakest possible search test, and it failed for AES: query a row's own
    transliteration and it must come back first."""
    row = corpus[
        (corpus["source"] == source)
        & (corpus["transliteration_gold"].astype(str).str.split().str.len() >= 5)
    ].iloc[0]
    top = retrieve_top_k(corpus, query_mdc=row["transliteration_gold"], k=3, index=index)
    assert not top.empty
    assert top.iloc[0]["transliteration_gold"] == row["transliteration_gold"]


@pytest.mark.parametrize("query", [UNICODE_QUERY, MDC_QUERY])
def test_the_reported_query_returns_its_parallels(corpus, index, query: str) -> None:
    """Her sentence itself is not in the corpus — `qnd` occurs four times and never
    with `stẖ` — but `ꜥḥꜥ.n stẖ …` is, and that is what a parallel search owes her.
    Before the fix both notations returned rows sharing nothing with the query."""
    top = retrieve_top_k(corpus, query_mdc=query, k=3, index=index)
    assert not top.empty
    assert all(
        str(row["transliteration_gold"]).startswith("ꜥḥꜥ.n stẖ")
        for _, row in top.iterrows()
    )


def test_a_mixed_paste_still_reads_its_mdc_letters(index) -> None:
    """Typing MdC and then tapping a palette character must not silently downgrade
    the MdC: `stX` is ẖ whether or not the rest of the string is already Unicode."""
    parse = parse_query("ꜥḥꜥ.n stX qnd", vocabulary=index.vocabulary)
    assert parse.notation == "mdc"
    assert parse.search_key == parse_query(
        "ꜥḥꜥ.n stẖ qnd", vocabulary=index.vocabulary
    ).search_key


def test_a_unicode_query_is_reported_as_unicode(index) -> None:
    parse = parse_query(UNICODE_QUERY, vocabulary=index.vocabulary)
    assert parse.notation == "unicode"
    assert parse.reading == UNICODE_QUERY
