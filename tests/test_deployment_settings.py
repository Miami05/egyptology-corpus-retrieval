"""Deployment knobs read from secrets or the environment (see configured_setting)."""

from __future__ import annotations

import app.ui.whyptology_app as w


def test_durable_flag_switches_off_the_ephemeral_state(monkeypatch):
    monkeypatch.setenv("ANNOTATIONS_DURABLE", "1")
    assert w.storage_is_ephemeral() is False
    monkeypatch.setenv("ANNOTATIONS_DURABLE", "0")
    assert w.storage_is_ephemeral() is w.IS_SQLITE


def test_default_stage_setting(monkeypatch):
    monkeypatch.delenv("DEFAULT_STAGE", raising=False)
    assert w.configured_default_stage() == "auto"
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    assert w.configured_default_stage() is None
    assert w.stage_param_to_internal(None) is None
    monkeypatch.setenv("DEFAULT_STAGE", "Late Egyptian")
    assert w.configured_default_stage() == "Late Egyptian"
    monkeypatch.setenv("DEFAULT_STAGE", "nonsense")
    assert w.configured_default_stage() == "auto"


def test_moved_banner_escapes_and_links():
    out = w.moved_to_banner_html("https://example.org/app?x=1&y=2")
    assert 'href="https://example.org/app?x=1&amp;y=2"' in out
    assert "has moved to" in out


def test_corpus_sources_exclude_drops_only_named_sources(monkeypatch):
    import pandas as pd
    df = pd.DataFrame({"source": ["TLA", "Ramses", "BBAW", "Demotic", "TLA"], "x": range(5)})
    monkeypatch.delenv("CORPUS_SOURCES_EXCLUDE", raising=False)
    assert len(w.exclude_corpus_sources(df)) == 5
    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "Ramses, Demotic")
    out = w.exclude_corpus_sources(df)
    assert list(out["source"]) == ["TLA", "BBAW", "TLA"]
    assert list(out.index) == [0, 1, 2]
