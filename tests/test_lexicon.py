"""The external sign-reading lexicon: how it is built, and how the model uses it.

The lexicon (Helsinki AES+Ramses word lists, CC BY 4.0) sits between "attested in
this corpus" and "guessed from a similar group". Every test here pins one boundary
of that position: it must never make an unattested group look attested, it must
never outrank the corpus, and its two halves must be read in their own conventions.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from app.services.lexicon import Lexicon, load_lexicon, LEXICON_PATH
from app.services.reading_model import train_reading_model
from app.services.segmentation import Segmenter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_helsinki_lexicon import (  # noqa: E402
    encoding_to_group,
    reading_to_corpus_convention,
)


# --- import conventions ------------------------------------------------------


def test_gardiner_encoding_becomes_one_normalised_group() -> None:
    import unicodedata

    group = encoding_to_group("D21 Z1")
    assert len(group) == 2, "two codes must become one two-sign group, no separator"
    assert [unicodedata.name(ch) for ch in group] == [
        "EGYPTIAN HIEROGLYPH D021",
        "EGYPTIAN HIEROGLYPH Z001",
    ]
    assert encoding_to_group("A1") == "\U00013000"  # 𓀀 is the first codepoint of the block
    assert encoding_to_group("") == ""


def test_the_two_halves_write_the_yod_differently() -> None:
    """AES writes the yod as `y` and the weak radical as `i`; Ramses writes the yod
    as `i`/`j` and keeps `y` for the double reed. Read with the wrong table, 𓀀
    "=y" (AES) and "=i" (Ramses) would have been two different readings."""
    assert reading_to_corpus_convention("=y", "AES") == "=ꞽ"
    assert reading_to_corpus_convention("=i", "Ramses") == "=ꞽ"
    assert reading_to_corpus_convention("ywi", "AES") == "ꞽwi"  # i̯ stays i
    assert reading_to_corpus_convention("y", "Ramses") == "y"  # double reed stays y
    assert reading_to_corpus_convention("jrj.t", "Ramses") == "ꞽrꞽ.t"


def test_mdc_capitals_convert_before_lower_casing() -> None:
    """`H` is ḥ and `h` is h: lower-casing first would destroy the distinction. Proper
    names (Nfr) are capitalised in the source and lower-cased to match the corpus."""
    assert reading_to_corpus_convention("Hr", "Ramses") == "ḥr"
    assert reading_to_corpus_convention("nTr.w", "Ramses") == "nṯr.w"
    assert reading_to_corpus_convention("Nfr", "AES") == "nfr"
    assert reading_to_corpus_convention("psDn.tyw", "AES") == "psḏn.tꞽw"


# --- loader -------------------------------------------------------------------


def test_missing_file_yields_an_empty_lexicon(tmp_path) -> None:
    lexicon = load_lexicon(tmp_path / "nope.csv")
    assert len(lexicon) == 0
    assert "\U00013000" not in lexicon


def test_loader_merges_rows_and_records_sources(tmp_path) -> None:
    path = tmp_path / "lex.csv"
    path.write_text(
        "group,reading,freq,source\n"
        "\U00013000,=ꞽ,10,AES+Ramses\n"
        "\U00013000,wꞽ,2,Ramses\n"
        "\U000130A1,r,5,AES\n",
        encoding="utf-8",
    )
    lexicon = load_lexicon(path)
    assert lexicon.candidates_for("\U00013000") == [("=ꞽ", 10), ("wꞽ", 2)]
    assert lexicon.total("\U00013000") == 12
    assert lexicon.source_of("\U00013000") == "AES+Ramses"
    assert lexicon.source_of("\U000130A1") == "AES"


@pytest.mark.skipif(not LEXICON_PATH.exists(), reason="lexicon not built")
def test_shipped_lexicon_is_in_corpus_convention() -> None:
    frame = pd.read_csv(LEXICON_PATH, dtype=str).fillna("")
    assert len(frame) > 90_000
    assert not frame["reading"].str.contains("j").any(), "ASCII yod leaked through"
    assert not frame["reading"].str.contains("[A-Z]", regex=True).any(), "MdC capital leaked through"
    a1 = frame[frame["group"] == "\U00013000"]
    assert a1.iloc[0]["reading"] == "=ꞽ" and a1.iloc[0]["source"] == "AES+Ramses"


# --- the model ----------------------------------------------------------------

SIGN_A, SIGN_B, SIGN_C = "\U00013000", "\U000130A1", "\U00013001"


def _corpus() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"hieroglyphs_norm": f"{SIGN_A} {SIGN_B}", "transliteration_gold": "=ꞽ r"},
            {"hieroglyphs_norm": f"{SIGN_A} {SIGN_B}", "transliteration_gold": "=ꞽ r"},
        ]
    )


def _lexicon() -> Lexicon:
    lexicon = Lexicon()
    lexicon.readings[SIGN_C] = Counter({"nfr": 30, "ꜥꜣ": 5})  # unattested in the corpus
    lexicon.readings[SIGN_A] = Counter({"wꞽ": 999})  # attested in the corpus: must lose
    lexicon.sources = {SIGN_C: "Ramses", SIGN_A: "AES+Ramses"}
    return lexicon


def test_lexicon_reads_a_group_the_corpus_never_saw() -> None:
    model = train_reading_model(_corpus(), _lexicon())
    prediction = model.predict_sequence([SIGN_C])[0]
    assert prediction.predicted == "nfr"
    assert prediction.is_lexicon and not prediction.was_seen and not prediction.is_fallback
    assert prediction.lexicon_count == 35 and prediction.lexicon_source == "Ramses"
    assert prediction.attested_count == 0, "a lexicon reading must not count as attested here"
    assert prediction.candidates[0] == ("nfr", 30 / 35)


def test_corpus_attestation_outranks_the_lexicon() -> None:
    """𓀀 is attested here as =ꞽ twice; the lexicon's 999× wꞽ must not override it."""
    model = train_reading_model(_corpus(), _lexicon())
    prediction = model.predict_sequence([SIGN_A])[0]
    assert prediction.predicted == "=ꞽ" and prediction.was_seen and not prediction.is_lexicon
    assert prediction.attested_count == 2 and prediction.lexicon_count == 0


def test_without_a_lexicon_the_model_behaves_as_before() -> None:
    model = train_reading_model(_corpus())
    prediction = model.predict_sequence([SIGN_C])[0]
    assert not prediction.is_lexicon
    assert prediction.lexicon_count == 0


def test_lexicon_groups_are_cut_points_below_singleton_weight() -> None:
    """A lexicon-only group is a legitimate span, priced below a corpus singleton
    (0.39 broke the Urk. IV paste gate; 0.2 is the default), and kept out of the
    corpus counts so it can never masquerade as attested."""
    from math import log

    model = train_reading_model(_corpus(), _lexicon())
    with_lexicon = Segmenter(model)
    without = Segmenter(model, use_lexicon=False)
    assert with_lexicon.is_known(SIGN_C) and SIGN_C in with_lexicon.lexicon_groups
    assert SIGN_C not in with_lexicon.group_counts
    assert not without.is_known(SIGN_C)
    expected = log(with_lexicon.weights.lexicon_weight / (with_lexicon.total + with_lexicon.vocabulary))
    assert with_lexicon.log_prob(SIGN_C) == pytest.approx(expected)
    assert with_lexicon.weights.lexicon_weight < with_lexicon.weights.singleton_discount
    # A corpus-attested group keeps its corpus count; the lexicon does not inflate it.
    assert with_lexicon.group_counts[SIGN_A] == 2 and SIGN_A not in with_lexicon.lexicon_groups
    assert without.log_prob(SIGN_C) is None


# --- the UI ---------------------------------------------------------------------


@pytest.mark.skipif(not LEXICON_PATH.exists(), reason="lexicon not built")
def test_workspace_labels_a_lexicon_reading_as_such() -> None:
    """Paste a group the corpus never saw but the lexicon has: the decode table must
    say "lexicon N× … no sentence in this corpus", the badge must not be the tick,
    and the footer must credit Helsinki (a CC BY 4.0 condition)."""
    from streamlit.testing.v1 import AppTest
    from app.data.loader import load_examples_csv

    corpus = load_examples_csv("data/processed/examples.csv")
    attested = set()
    for value in corpus["hieroglyphs_norm"].astype(str):
        attested.update(value.split())
    lexicon = load_lexicon()
    # A well-attested lexicon group with no placeholder signs, absent from the corpus.
    group = next(
        g for g, counts in sorted(lexicon.readings.items(), key=lambda kv: -sum(kv[1].values()))
        if g not in attested and all("\U00013000" <= ch <= "\U0001342F" for ch in g)
    )
    app = AppTest.from_file("app/ui/whyptology_app.py", default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    app.text_area[0].set_value(group).run()
    next(b for b in app.button if b.label.startswith("Suggest top")).click().run()
    assert not app.exception
    markdown = "\n".join(m.value for m in app.markdown)
    assert "◇" in markdown or "from the lexicon" in markdown
    table_text = " ".join(str(d.value.to_dict()) for d in app.dataframe)
    assert "no sentence in this corpus" in table_text
    assert "Helsinki" in markdown
