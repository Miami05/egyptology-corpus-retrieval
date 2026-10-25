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


def test_deployment_md_describes_the_current_reviewer_key_guard():
    """The operator guide must match KeyAttemptGuard and the fail-closed settings
    (Astra re-review of fix round 2: it still described a process-wide lockout)."""
    import inspect
    from pathlib import Path

    from app.ui import review_common

    doc = (Path(__file__).resolve().parents[1] / "DEPLOYMENT.md").read_text(encoding="utf-8")
    # Obsolete descriptions are gone.
    assert "refuses *every* unlock" not in doc
    assert "anyone may save" not in doc
    assert "(N recent failures)" not in doc
    assert "comma-separated `source` values to drop" not in doc
    # The current guard, with numbers taken from the code's defaults.
    defaults = {
        k: v.default
        for k, v in inspect.signature(review_common.KeyAttemptGuard.__init__).parameters.items()
    }
    assert "Per session, exponential backoff" in doc
    assert f"After {defaults['free_attempts']} wrong keys" in doc
    assert f"above {defaults['global_free']} failures" in doc
    assert f"capped at {defaults['global_max_delay']:g} s" in doc
    assert "the key's length is the real protection" in doc
    # The log line documented is the one the app emits.
    app_src = (Path(w.__file__)).read_text(encoding="utf-8")
    assert "recent failures in this session" in app_src
    assert "recent failures in this session" in doc
    # Fail-closed saving and the source-or-stage exclusion are in the settings table.
    assert "unset = annotation saving off for everyone" in doc
    assert "`source` **or** its `language_stage`" in doc
