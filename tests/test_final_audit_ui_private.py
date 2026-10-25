"""Final audit (2026-10-25), ui-private area: the confirmed findings, one test each.

Opus 1 / Astra 3  a malformed private CSV crashed the reviewer sidebar
Opus 2            README promised a fully open form with no key
Opus 3            the St Andrews "changes" line understated the importer's changes
Opus 4            private rows labelled with a public source name passed as public
Astra 1           keyed (possibly private) queries were written to ?q= and kept on lock
Astra 2           a line break in a data field ended the HTML block (Markdown injection)
Astra 4           a corpus file replaced with only non-reading fields changed kept the
                  old frame in every signature-keyed cache
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.loader import REQUIRED_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _row(**overrides) -> dict:
    row = {col: "" for col in REQUIRED_COLUMNS}
    row.update(
        source_text_id="t1",
        source_sentence_id="s1",
        transliteration_gold="ḥtp",
        hieroglyphs="𓊵𓏏𓊪",
        sign_sequence="R4 X1 Q3",
    )
    row.update(overrides)
    return row


@pytest.fixture()
def private_app(tmp_path, monkeypatch):
    import app.ui.whyptology_app as w

    monkeypatch.setattr(w, "PRIVATE_DATA_DIR", tmp_path)
    w.load_private_corpus.clear()
    yield w, tmp_path
    w.load_private_corpus.clear()


# ---------- Opus 1 / Astra 3: the sidebar survives a malformed private CSV ----------


def test_private_corpus_has_rows_is_false_not_a_crash_on_a_malformed_csv(private_app):
    w, directory = private_app
    pd.DataFrame([_row(source="StAndrews"), _row(source="")]).to_csv(
        directory / "standrews.csv", index=False
    )
    with pytest.raises(ValueError):
        w.current_private_corpus()  # precondition: the loader does raise
    assert w.private_corpus_has_rows() is False


def test_a_keyed_session_with_a_malformed_private_csv_still_renders_and_can_lock(
    tmp_path, monkeypatch
):
    from streamlit.testing.v1 import AppTest

    pd.DataFrame([_row(source="StAndrews"), _row(source="")]).to_csv(
        tmp_path / "standrews.csv", index=False
    )
    monkeypatch.setenv("PRIVATE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REVIEWER_KEY", "final-audit-key")
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    app = AppTest.from_file("app/ui/whyptology_app.py", default_timeout=240)
    app.query_params["view"] = "corpus"
    app.session_state["whyptology_reviewer_ok"] = True
    app.run()
    assert not app.exception, app.exception
    app.button(key="whyptology_reviewer_lock").click().run()
    assert not app.exception, app.exception
    assert app.session_state["whyptology_reviewer_ok"] is False


# ---------- Opus 2: README says saving fails closed ----------


def test_readme_says_annotation_saving_fails_closed_without_a_key():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "fully open" not in readme
    assert "ALLOW_OPEN_ANNOTATIONS=1" in readme


# ---------- Opus 3: the St Andrews credit states every change ----------


def test_st_andrews_credit_names_the_importers_changes():
    import app.ui.whyptology_app as w
    from app.ui.source_display import STANDREWS_CARD_CREDIT

    changes = w.PRIVATE_CORPUS_CREDITS["StAndrews"]["changes"]
    assert "suffix pronouns tokenised" in changes
    assert "'^' proper-name marker dropped" in changes
    assert "adapted" in STANDREWS_CARD_CREDIT


# ---------- Opus 4: a private row cannot pass as a public source ----------


def test_private_rows_with_a_public_source_name_are_refused(private_app):
    w, directory = private_app
    pd.DataFrame([_row(source="AES")]).to_csv(directory / "p.csv", index=False)
    public = pd.DataFrame({"source": ["TLA"], "id": [1]})
    with pytest.raises(ValueError, match="public source name"):
        w._append_private_rows(public)


def test_any_source_not_known_to_be_public_counts_as_private():
    import app.ui.whyptology_app as w

    assert w.is_private_example(SimpleNamespace(source="OtherNC"))
    assert w.is_private_example(SimpleNamespace(source="StAndrews"))
    assert not w.is_private_example(SimpleNamespace(source="TLA"))
    other = SimpleNamespace(supporting_examples=(SimpleNamespace(source="OtherNC"),))
    assert w.visible_suggestions([other], private_allowed=False) == []


# ---------- Astra 1: keyed queries never reach ?q=, and locking clears the box ----------


def test_a_keyed_search_is_not_published_to_the_url():
    import app.ui.whyptology_app as w

    params = {"q": "older public query"}
    w.publish_query_to_url("𓂀 private", "all", keyed=True, query_params=params)
    assert "q" not in params and params["stage"] == "all"
    w.publish_query_to_url("ḥtp", "all", keyed=False, query_params=params)
    assert params["q"] == "ḥtp"


def test_losing_private_access_clears_the_query_box_and_the_url(monkeypatch):
    import app.ui.whyptology_app as w

    state = {
        w.PRIVATE_ACCESS_SEEN_KEY: True,
        w.QUERY_TEXT_KEY: "𓂀 private",
        "whyptology_query_3": "𓂀 private",
        w.QUERY_NONCE_KEY: 3,
        w.PENDING_EXAMPLE_KEY: "x",
    }
    params = {"q": "𓂀 private", "stage": "all"}
    monkeypatch.setattr(w, "private_rows_unlocked", lambda: False)
    w.enforce_private_session_gate(state, params)
    assert w.QUERY_TEXT_KEY not in state
    assert "whyptology_query_3" not in state
    assert w.PENDING_EXAMPLE_KEY not in state
    assert state[w.QUERY_NONCE_KEY] == 4
    assert "q" not in params and params["stage"] == "all"


# ---------- Astra 2: no data line break reaches the Markdown parser ----------


def test_escape_folds_line_breaks_so_a_value_cannot_end_the_html_block():
    import app.ui.whyptology_app as w

    payload = "note\n\n![audit](https://example.invalid/pixel)\r\n end"
    out = w.escape(payload)
    assert not any(ch in out for ch in "\r\n ")
    assert "&lt;" in w.escape("<b>")
    table = w.html_table(pd.DataFrame({"translation": [payload]}))
    assert "\n\n" not in table


# ---------- Astra 4: the signature sees every column a cache hands out ----------


def test_signature_changes_when_only_a_translation_changes():
    import app.ui.whyptology_app as w

    base = {"hieroglyphs_norm": ["𓊵𓏏"], "transliteration_gold": ["ḥtp"]}
    old = pd.DataFrame({**base, "translation": ["old"], "source_text_id": ["a"]})
    new = pd.DataFrame({**base, "translation": ["new"], "source_text_id": ["a"]})
    assert w.corpus_signature(old) != w.corpus_signature(new)
