"""Audit 2026-10-11, batch "normalizer": findings A14 A16 A17 A47 A48 A49 A50 A51.

(A15, folding ʾ, is deliberately not shipped: see the characterisation test at the end.)

Most assertions compare against another *spelling* (`search_fold('H̱nm.w') ==
search_fold('ẖnm.w')`) rather than against an ASCII literal, so that the pending
aleph/ayin and ḫ/ẖ split (all-ASCII read as MdC) only has to touch the few literal
checks marked "literal" below.
"""

from __future__ import annotations

import pandas as pd

from app.data.loader import _normalize_corpus_frame
from app.data.normalizer import (
    normalize_text,
    normalize_transliteration,
    search_fold,
)
from app.retrieval.tokens import ScoringTables, TokenWeights, tokenize_query
from app.services.suggestions import loose_reading_form, strict_reading_key


# ---------------------------------------------------------------------------
# A14: capital H̱ has no precomposed codepoint
# ---------------------------------------------------------------------------
def test_a14_capital_h_with_line_below_folds_like_lowercase():
    assert normalize_text("H̱") == "ẖ"
    assert search_fold("H̱nm.w") == search_fold("ẖnm.w")
    assert search_fold("H̱ty") == search_fold("ẖty")
    assert search_fold("Zꜣ.t-H̱.t.y") == search_fold("zꜣ.t-ẖ.t.y")


def test_a14_capital_h_with_line_below_literal():
    assert search_fold("H̱nm.w") == "khnmw"  # literal: changes with the ḫ/ẖ split
    assert search_fold("H̱nm.w") != search_fold("nm.w")


def test_a14_plain_capitals_unchanged():
    assert normalize_text("ḤTP Ḏd") == "ḥtp ḏd"


# ---------------------------------------------------------------------------
# A16: ʿ ȝ ỉ are variant letters, not noise
# ---------------------------------------------------------------------------
def test_a16_variant_letters_are_the_canonical_letters():
    assert search_fold("ʿnḫ") == search_fold("ꜥnḫ")
    assert search_fold("ȝḫ") == search_fold("ꜣḫ")
    assert search_fold("Ȝḫ") == search_fold("ꜣḫ")
    assert search_fold("ỉr") == search_fold("ꞽr")
    assert search_fold("Ỉr") == search_fold("ꞽr")
    assert search_fold("n(.ỉ).t") == search_fold("n.t")
    assert search_fold("(ỉ)r(.ỉ)-pꜣ.t") == search_fold("(ꞽ)r(.ꞽ)-pꜣ.t")


def test_a16_structural_no_literal_letter():
    assert normalize_transliteration("ʿ") == normalize_transliteration("ꜥ")
    assert normalize_transliteration("ȝ") == normalize_transliteration("ꜣ")
    assert normalize_transliteration("ỉ") == normalize_transliteration("ꞽ")


def test_a16_literal():
    assert search_fold("ʿnḫ") == "ankh"  # literal: changes with the aleph/ayin split
    assert search_fold("ỉr") == "ir"


# ---------------------------------------------------------------------------
# A47: the weak-consonant marker is folded in the search key
# ---------------------------------------------------------------------------
def test_a47_u_with_inverted_breve_is_w():
    assert search_fold("ḥru̯") == search_fold("hrw") == "hrw"
    assert search_fold("hru̯") == search_fold("hrw")  # decomposed marker
    assert search_fold("ḥrU̯") == search_fold("hrw")  # uppercase
    assert search_fold("ḫru̯") == search_fold("ḫrw")


def test_a47_i_with_inverted_breve_is_yod():
    assert search_fold("rdi̯") == search_fold("rdꞽ") == "rdi"
    assert search_fold("(i̯)r") == search_fold("r")


def test_a47_strict_reading_key_unchanged():
    # strict_reading_key already folds the marker itself; this change must not move it.
    assert strict_reading_key("hru̯") == "hrw"
    assert strict_reading_key("rdi̯") == "rdꞽ"


# ---------------------------------------------------------------------------
# A49: an ASCII bracketed yod is an editorial yod too
# ---------------------------------------------------------------------------
def test_a49_ascii_bracketed_yod_dropped():
    assert search_fold("n(.i).t") == search_fold("n.t") == search_fold("n(.ꞽ).t") == "nt"
    assert search_fold("(i)r(.i)-pꜣ.t") == search_fold("(ꞽ)r(.ꞽ)-pꜣ.t")
    assert search_fold("(ỉ)r") == search_fold("r")


def test_a49_unbracketed_yod_kept():
    assert search_fold("ir") == "ir"
    assert search_fold("n.i.t") != search_fold("n.t")


# ---------------------------------------------------------------------------
# A48: a bracketed .w before .pl is the plural, not a second w
# ---------------------------------------------------------------------------
def test_a48_bracketed_plural_w():
    assert search_fold("šms(.w).pl") == search_fold("šms.w") == "shmsw"
    assert search_fold("šms(w).pl") == search_fold("šms.w")
    assert search_fold("šms(.w).PL") == search_fold("šms.w")


def test_a48_other_plural_shapes_unchanged():
    assert search_fold("sr.w.PL") == "srw"
    assert search_fold("kꜣ.pl") == search_fold("kꜣ.w")
    assert search_fold("ꜣpd(.pl)") == search_fold("ꜣpd.w")
    # `(.t).pl` is a different morpheme plus the plural: untouched here.
    assert search_fold("šms(.t).pl") == search_fold("šms(.t).w")


def test_a48_strict_reading_key_unchanged():
    # strict_reading_key shares the plural regexes; the bracketed-w rule is search-fold only.
    assert strict_reading_key("šms(.w).pl") == "šmsww"


# ---------------------------------------------------------------------------
# A50: a slash between digits is a fraction, not nothing
# ---------------------------------------------------------------------------
def test_a50_fraction_is_not_a_whole_number():
    assert search_fold("1/2") == "1_2"
    assert search_fold("1/2") != search_fold("12")
    assert search_fold("1/64") == "1_64"
    assert search_fold("3/4") == "3_4"
    assert search_fold("1/2/3") == "1_2_3"


def test_a50_slash_between_letters_still_dropped():
    assert search_fold("a/b") == "ab"


def test_a50_fraction_stays_one_token_and_lacuna_untouched():
    assert tokenize_query(search_fold("rdi 1/2")) == ["rdi", "1_2"]
    assert search_fold("x _ y") == "x _ y"


# ---------------------------------------------------------------------------
# A17: {…} is the editor's "superfluous" mark, {{…}} is real text
# ---------------------------------------------------------------------------
def test_a17_single_braces_are_deleted_with_content():
    assert search_fold("nb{.t}") == search_fold("nb")
    assert search_fold("wḫꜣ{ḫ}") == search_fold("wḫꜣ")
    assert search_fold("n{t}n.t") == search_fold("nn.t")
    assert search_fold("ḏd.n={f}") == search_fold("ḏd.n")
    assert loose_reading_form("nb{.t}") == loose_reading_form("nb")


def test_a17_literal():
    assert search_fold("nb{.t}") == "nb"
    assert search_fold("ḏd.n={f}") == "djdn"


def test_a17_double_braces_keep_their_text():
    assert search_fold("{{ꞽt}} ={{f}}") == search_fold("ꞽt f")
    assert search_fold("{{šꜥ{f}.t}}") == search_fold("šꜥ.t")


def test_a17_fully_single_braced_text_keeps_a_key():
    # Deleting every span would leave an empty key: the row would be unreachable
    # (tests/test_query_notations.py::test_every_corpus_row_is_reachable...).
    assert search_fold("{m} ={tn}") == search_fold("m tn")
    assert search_fold("{Ḫwi̯.n-H̱nm.w}") != ""


def test_a17_loader_survives_a_fully_braced_row():
    frame = pd.DataFrame(
        {
            "source": ["BBAW", "BBAW", "BBAW"],
            "transliteration_gold": ["{m} ={tn}", "nb{.t}", "{{ꞽt}} ={{f}}"],
            "mdc": ["", "", ""],
        }
    )
    out = _normalize_corpus_frame(frame)
    assert out["mdc_norm"].tolist() == [search_fold("m tn"), search_fold("nb"), search_fold("ꞽt f")]


# ---------------------------------------------------------------------------
# A51: IDF uses the size of the subset the document frequencies came from
# ---------------------------------------------------------------------------
def _toy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "mdc_norm": ["n htp", "n rdi", "n nb", "htp nb"],
            "hieroglyphs_norm": ["a b", "a c", "a d", "b d"],
        }
    )


def test_a51_corpus_size_override():
    from math import log

    df = _toy_frame()
    text_f = {"n": 3, "htp": 2, "rdi": 1, "nb": 2}
    glyph_f = {"a": 3, "b": 2, "c": 1, "d": 2}
    tables = ScoringTables.build(df, text_f, glyph_f, corpus_size=50)
    assert tables.text_weights.corpus_size == 50
    assert tables.glyph_weights is not None and tables.glyph_weights.corpus_size == 50
    column = tables.text.vocabulary["n"]
    assert abs(tables.text_weights.weights[column] - (log(51 / 4) + 1.0)) < 1e-12


def test_a51_default_corpus_size_is_len_df():
    df = _toy_frame()
    tables = ScoringTables.build(df, {"n": 3}, {"a": 3})
    assert tables.text_weights.corpus_size == len(df)
    assert tables.glyph_weights is not None and tables.glyph_weights.corpus_size == len(df)
    assert isinstance(tables.text_weights, TokenWeights)


def test_a51_stage_resources_use_the_stage_subset_size():
    from app.retrieval.scorer import build_corpus_stats
    from app.services.stage import build_stage_resources

    df = pd.DataFrame(
        {
            "hieroglyphs_norm": ["A", "B", "C"],
            "transliteration_gold": ["x", "y", "z"],
            "language_stage": ["Earlier Egyptian", "Late Egyptian", "Late Egyptian"],
            "source_text_id": ["T0", "T1", "T2"],
            "source_sentence_id": ["S0", "S1", "S2"],
            "mdc_norm": ["x", "y", "z"],
        }
    )
    assert build_corpus_stats(df).n_rows == 3
    declared = build_stage_resources(df, "Earlier Egyptian")
    assert declared.index.stats.n_rows == 1
    assert declared.index.tables is not None
    assert declared.index.tables.text_weights.corpus_size == 1
    pooled = build_stage_resources(df, None)
    assert pooled.index.tables is not None
    assert pooled.index.tables.text_weights.corpus_size == 3


def test_a51_slow_path_uses_the_stats_row_count():
    from app.retrieval.scorer import CorpusStats, combine_scores

    df = pd.DataFrame(
        {
            "mdc_norm": ["n htp", "n rdi", "htp nb"],
            "hieroglyphs_norm": ["", "", ""],
            "normalized_reading_order_norm": ["", "", ""],
        }
    )
    frequencies = {"n": 2, "htp": 1}

    def scores(n_rows):
        stats = CorpusStats(mdc_frequencies=frequencies, glyph_frequencies={}, n_rows=n_rows)
        return combine_scores(df, query_mdc_norm="n htp", corpus_stats=stats)[
            "idf_overlap_score"
        ].tolist()

    # n_rows unset falls back to the frame length (3), as before.
    assert scores(None) == scores(3)
    # A stage subset of 2 rows must weight with N=2, not the pooled frame's 3.
    assert scores(2) != scores(3)


# ---------------------------------------------------------------------------
# A15 (not shipped): ʾ is still deleted. This records the decision; see the batch
# report. Lemma data favours deletion 76 to 2 and folding to ꜣ would split mʾw.t from
# mw.t. Revisit together with the aleph/ayin split.
# ---------------------------------------------------------------------------
def test_a15_aleph_sign_is_still_deleted_on_purpose():
    assert search_fold("mʾw.t") == search_fold("mw.t")
