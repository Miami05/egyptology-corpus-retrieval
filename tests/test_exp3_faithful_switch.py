"""Experiment 3, configuration F-a, behind its switch (app.services.faithful).

Frozen definition: ROADMAP.md, Experiment 3 addendum 2026-10-26, "F-a, frozen
definition (revision)". Pinned here, on a small hand-made corpus (no full index):

- switch off (the default): no faithful code runs at all, so behaviour is today's;
- switch on, Unicode query: retrieval and re-rank match by the faithful key only
  (ḥ ≠ h ≠ ḫ, ꜣ ≠ ꜥ), ASCII-only words of the query included (`hrw` means h);
- switch on, ASCII / MdC / hieroglyph query: every column identical to switch off.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd
import pytest

import app.services.faithful as faithful
from app.data.loader import _normalize_corpus_frame
from app.data.query import parse_query
from app.services.faithful import (
    EXP3_FA_DEFAULT,
    FAITHFUL_COLUMN,
    faithful_search_column,
    faithful_search_enabled,
)
from app.services.retrieval import build_search_index, retrieve_top_k
from app.services.stage import build_stage_resources
from app.services.suggestions import QueryForms, suggest_top_readings

ROOT = Path(__file__).resolve().parents[1]

READINGS = [
    # (transliteration, stage, hieroglyphs)
    ("ḥtp dꞽ nswt", "Earlier Egyptian", "𓊵 𓏏 𓊪"),
    ("htp dꞽ nswt", "Earlier Egyptian", ""),
    ("ḫtp dꞽ nswt", "Earlier Egyptian", ""),
    ("ḥtp ḥrw nfr", "Earlier Egyptian", ""),
    ("ḥtp hrw nfr", "Earlier Egyptian", ""),
    ("ꜥḥꜥ.n stẖ qnd", "Earlier Egyptian", "𓊢 𓂝 𓈖"),
    ("ꜣḥꜥ.n stẖ qnd", "Late Egyptian", ""),
    ("ꜥḥꜥ.n sth qnd", "Late Egyptian", ""),
    ("ḏd mdw ꞽn", "Late Egyptian", ""),
    ("nfr ḥr ꜥnḫ", "Late Egyptian", ""),
    ("", "Late Egyptian", "𓋹 𓄤"),
]

SAMPLE_QUERIES = (
    "ḥtp dꞽ nswt",  # unicode
    "ḥtp hrw",  # unicode with an ASCII-only word
    "ꜥḥꜥ.n stẖ",  # unicode
    "htp di nswt",  # ascii
    "aHa.n stX qnd",  # mdc
    "Htp",  # mdc or ascii, decided by the vocabulary
)


def _corpus() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "source": "test",
                "source_text_id": f"T{i // 3}",
                "source_sentence_id": f"S{i}",
                "language_stage": stage,
                "transliteration_gold": reading,
                "hieroglyphs": glyphs,
                "mdc": "ankh nfr" if not reading else "",
                "translation": f"t{i}",
            }
            for i, (reading, stage, glyphs) in enumerate(READINGS)
        ]
    )
    return _normalize_corpus_frame(frame)


@pytest.fixture
def switch(monkeypatch):
    # "1" switches F-a on, "0" off: the module constant, the only switch.
    def set_to(value: str) -> None:
        monkeypatch.setattr(faithful, "EXP3_FA_DEFAULT", value == "1")

    return set_to


def _run(corpus: pd.DataFrame, query: str, hieroglyphs: str | None = None):
    index = build_search_index(corpus)
    top = retrieve_top_k(corpus, query, k=20, index=index, query_hieroglyphs_norm=hieroglyphs)
    parse = parse_query(query, vocabulary=index.vocabulary, hieroglyphs_norm=hieroglyphs)
    suggestions = suggest_top_readings(
        top,
        query_mdc=parse.reading or query,
        query_raw=query,
        top_n=5,
        query_hieroglyphs=parse.hieroglyphs_norm,
        query_notation=parse.notation,
    )
    # Every field of every suggestion (dataclass equality), in order.
    return index, top, list(suggestions)


# --- the switch ---------------------------------------------------------------


def test_switch_defaults_off() -> None:
    assert EXP3_FA_DEFAULT is False
    assert faithful_search_enabled() is False


def test_environment_does_not_switch_it_on(monkeypatch) -> None:
    # The experiment-time override is gone: production reads the code default only.
    monkeypatch.setenv("WHYPTOLOGY_EXP3_FA", "1")
    assert faithful_search_enabled() is False


def test_switch_follows_the_module_constant(switch) -> None:
    switch("1")
    assert faithful_search_enabled() is True
    switch("0")
    assert faithful_search_enabled() is False


# --- switch off: today's path, nothing faithful computed -----------------------


@pytest.mark.parametrize("query", SAMPLE_QUERIES)
def test_switch_off_runs_no_faithful_code(switch, monkeypatch, query: str) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("faithful code ran with the switch off")

    monkeypatch.setattr(faithful, "faithful_key", boom)
    monkeypatch.setattr(faithful, "faithful_view", boom)
    monkeypatch.setattr(faithful, "build_faithful_index", boom)
    corpus = _corpus()
    index, _, _ = _run(corpus, query)
    assert index.faithful is None
    assert FAITHFUL_COLUMN not in corpus.columns


@pytest.mark.parametrize("query", SAMPLE_QUERIES)
def test_switch_off_explicit_equals_default(switch, query: str) -> None:
    corpus = _corpus()
    _, top_default, sugg_default = _run(corpus, query)
    switch("0")
    _, top_off, sugg_off = _run(corpus, query)
    pd.testing.assert_frame_equal(top_default, top_off)
    assert sugg_default == sugg_off


def test_switch_off_keeps_a54_per_word_mode(switch) -> None:
    """Today's behaviour: the ASCII-only word of a Unicode query stays loose."""
    corpus = _corpus()
    _, _, suggestions = _run(corpus, "ḥtp hrw")
    readings = [s.candidate_transliteration for s in suggestions]
    assert QueryForms.build("ḥtp hrw", "ḥtp hrw").mode == "mixed"
    # Retrieval is lossy: ḥtp ḥrw nfr is reachable through `hrw`.
    assert "ḥtp ḥrw nfr" in readings


# --- switch on: F-a for Unicode queries -----------------------------------------


def test_faithful_column_is_the_unfolded_form() -> None:
    keys = faithful_search_column(_corpus())
    assert keys.iloc[0] == "ḥtp dꞽ nswt"
    assert keys.iloc[5] == "ꜥḥꜥ n stẖ qnd"  # marker split, letters as written
    assert keys.iloc[10] == ""  # no transliteration: no faithful key


def test_switch_on_retrieval_is_faithful(switch) -> None:
    switch("1")
    corpus = _corpus()
    index, top, suggestions = _run(corpus, "ḥtp dꞽ nswt")
    assert index.faithful is not None
    found = set(top["transliteration_gold"])
    assert "ḥtp dꞽ nswt" in found
    # htp / ḫtp are lossy-only matches of `ḥtp`: they may still share `dꞽ nswt`,
    # but the query word ḥtp itself must not count for them.
    assert top.iloc[0]["transliteration_gold"] == "ḥtp dꞽ nswt"
    # The rows keep their own (folded) search key for display.
    assert set(top["mdc_norm"]) <= set(corpus["mdc_norm"])


def test_switch_on_ascii_word_of_unicode_query_is_strict(switch) -> None:
    """`hrw` in a Unicode query means h: ḥrw is no longer a match, in retrieval or re-rank."""
    switch("1")
    corpus = _corpus()
    _, top, suggestions = _run(corpus, "hrw ꜥḥꜥ")
    found = set(top["transliteration_gold"])
    assert "ḥtp hrw nfr" in found
    assert "ḥtp ḥrw nfr" not in found
    assert "ꜣḥꜥ.n stẖ qnd" not in found  # ꜣḥꜥ is not ꜥḥꜥ
    switch("0")
    _, top_off, _ = _run(corpus, "hrw ꜥḥꜥ")
    assert "ḥtp ḥrw nfr" in set(top_off["transliteration_gold"])


def test_switch_on_rerank_is_strict_for_the_whole_query(switch) -> None:
    switch("1")
    corpus = _corpus()
    index = build_search_index(corpus)
    # Hand the re-rank a pool containing the lossy neighbour, to see the forms only.
    pool = retrieve_top_k(corpus, "ḥtp", k=20, index=index)
    signals: list[dict] = []
    suggest_top_readings(
        pool,
        query_mdc="ḥtp hrw",
        query_raw="ḥtp hrw",
        top_n=5,
        debug_signals=signals,
        query_notation="unicode",
    )
    switch("0")
    signals_off: list[dict] = []
    suggest_top_readings(
        pool,
        query_mdc="ḥtp hrw",
        query_raw="ḥtp hrw",
        top_n=5,
        debug_signals=signals_off,
        query_notation="unicode",
    )
    assert signals != signals_off  # mixed (A54) vs strict (F-a) re-rank


@pytest.mark.parametrize("query", ["htp di nswt", "aHa.n stX qnd", "Htp", "nfr"])
def test_switch_on_leaves_non_unicode_queries_identical(switch, query: str) -> None:
    corpus = _corpus()
    _, top_off, sugg_off = _run(corpus, query)
    switch("1")
    corpus_on = _corpus()
    index_on, top_on, sugg_on = _run(corpus_on, query)
    assert parse_query(query, vocabulary=index_on.vocabulary).notation != "unicode"
    pd.testing.assert_frame_equal(top_off, top_on)
    assert sugg_off == sugg_on


def test_switch_on_leaves_hieroglyph_queries_identical(switch) -> None:
    corpus = _corpus()
    _, top_off, sugg_off = _run(corpus, "𓊵 𓏏 𓊪")
    switch("1")
    _, top_on, sugg_on = _run(_corpus(), "𓊵 𓏏 𓊪")
    pd.testing.assert_frame_equal(top_off, top_on)
    assert sugg_off == sugg_on


def test_switch_on_without_a_faithful_index_refuses(switch) -> None:
    corpus = _corpus()
    index = build_search_index(corpus)  # built with the switch off
    switch("1")
    with pytest.raises(ValueError, match="faithful twin"):
        retrieve_top_k(corpus, "ḥtp", k=5, index=index)
    # ...but an ASCII query does not need it.
    retrieve_top_k(corpus, "htp", k=5, index=index)


def test_stage_resources_build_a_faithful_twin_with_stage_frequencies(switch) -> None:
    switch("1")
    corpus = _corpus()
    pooled = build_stage_resources(corpus, None)
    late = build_stage_resources(
        corpus,
        "Late Egyptian",
        pooled_reading_model=pooled.reading_model,
        pooled_index=pooled.index,
    )
    assert pooled.index.faithful is not None and late.index.faithful is not None
    # n-gram index and token table shared from the pooled twin, weights per stage.
    assert late.index.faithful.text_index is pooled.index.faithful.text_index
    assert late.index.faithful.tables.text is pooled.index.faithful.tables.text
    pooled_df = pooled.index.faithful.stats.mdc_frequencies
    late_df = late.index.faithful.stats.mdc_frequencies
    assert pooled_df["ḥtp"] == 3 and "ḥtp" not in late_df
    assert late_df["ꜣḥꜥ"] == 1
    top = retrieve_top_k(late.frame, "ꜥḥꜥ.n stẖ", k=10, index=late.index)
    assert "ꜣḥꜥ.n stẖ qnd" not in set(top["transliteration_gold"][top["idf_overlap_score"] >= 1.0])


def test_stage_resources_off_have_no_faithful_twin(switch) -> None:
    corpus = _corpus()
    pooled = build_stage_resources(corpus, None)
    assert pooled.index.faithful is None


# --- the held-out faithful benchmark file -----------------------------------------


def test_faithful_benchmark_file_checks_fold_back(tmp_path) -> None:
    from scripts.exp3_faithful_benchmark_file import faithful_frame

    frame = pd.DataFrame(
        {
            "benchmark_id": ["H1", "H2"],
            "query_input": ["ahan stkh", "htp"],
            "faithful_query_input": ["ꜥḥꜥ.n stẖ", "ḫtp"],
            "expected_transliteration": ["x", "y"],
        }
    )
    out, bad = faithful_frame(frame)
    assert bad == ["H2"]  # ḫtp folds to khtp, not htp
    assert list(out.columns[:3]) == ["benchmark_id", "query_input", "stored_query_input"]
    assert out["query_input"].tolist() == ["ꜥḥꜥ.n stẖ", "ḫtp"]
    assert out["stored_query_input"].tolist() == ["ahan stkh", "htp"]


# --- the run script ---------------------------------------------------------------


def test_run_script_parses_and_never_touches_held_out_3() -> None:
    script = ROOT / "scripts" / "run_exp3_prereg.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")
    assert "holdout3" not in text.lower() and "sealed" not in text.lower()
    bad = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert bad.returncode == 2 and "usage" in bad.stderr
