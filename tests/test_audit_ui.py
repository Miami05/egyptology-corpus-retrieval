"""Regression tests for the UI batch of the 2026-10-11 audit (docs/audit-2026-10-11.md).

One section per finding id (A1 ... A63). The AppTest-based ones drive the real app
script, exactly like tests/test_private_corpus.py does.
"""

from __future__ import annotations

import gc
import logging
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(PROJECT_ROOT / "app" / "ui" / "whyptology_app.py")
EXAMPLES_CSV = PROJECT_ROOT / "data" / "processed" / "examples.csv"

import app.ui.review_common as review_common  # noqa: E402
from app.ui.review_common import (  # noqa: E402
    LICENCE_NOTICE,
    PUBLIC_CREDITS,
    KeyAttemptGuard,
    check_reviewer_key,
    licence_notice_for,
    md_code,
    md_escape,
    neutralise_spreadsheet_formulas,
    with_licence_notice,
)


@pytest.fixture(autouse=True)
def _fresh_key_guard(monkeypatch):
    """A lockout must never leak between tests: every test gets its own counter."""
    monkeypatch.setattr(review_common, "REVIEWER_KEY_GUARD", KeyAttemptGuard())


@pytest.fixture(scope="module")
def examples_meta() -> pd.DataFrame:
    return pd.read_csv(
        EXAMPLES_CSV,
        usecols=["source", "language_stage", "source_text_id"],
        dtype=str,
        keep_default_na=False,
    )


def _app(page: str | None = None, **env) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    if page is not None:
        app.query_params["view"] = page
    app.query_params["stage"] = "all"
    return app


def _texts(app: AppTest, *kinds: str) -> list[str]:
    out: list[str] = []
    for kind in kinds or ("markdown", "caption", "warning", "error", "info", "success"):
        for element in getattr(app, kind):
            out.append(str(getattr(element, "value", "")))
    return out


# ---------- A1: personal exports are gitignored ----------


@pytest.mark.parametrize(
    "probe",
    [
        "extracted-data-2026-09-22/conversations.json",
        "extracted-data-2026-09-22.zip",
        "outputs/a.csv",
    ],
)
def test_export_dirs_are_gitignored(probe):
    result = subprocess.run(
        ["git", "check-ignore", probe], cwd=PROJECT_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, f"{probe} is not covered by .gitignore"


def test_the_corpus_is_not_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "data/processed/examples.csv"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


# ---------- A5: 'Prepare CSV export' ----------

_REVIEW_ROW = {
    "example_id": 1,
    "source": "TLA",
    "source_text_id": "TLA_EARLIER_x",
    "source_sentence_id": "s1",
    "language_stage": "Earlier Egyptian",
    "script_type": "Hieroglyphic",
    "genre": "g",
    "period": "p",
    "hieroglyphs": "𓊵",
    "mdc": "R4",
    "sign_sequence": "R4",
    "transliteration_gold": "=f ḥtp",
    "translation": "Frieden",
    "latest_transliteration": "ḥtp",
    "latest_status": "edited",
    "latest_uncertainty_note": "",
    "latest_grammar_note": "",
    "latest_annotation_created_at": "2026-10-11 10:00:00",
}


def test_prepare_csv_export_gives_a_download_button(monkeypatch):
    monkeypatch.setattr(review_common, "reviewed_annotation_rows", lambda: [dict(_REVIEW_ROW)])
    app = _app("reviews")
    app.run()
    assert not app.exception, app.exception
    prepare = [b for b in app.button if b.label == "Prepare CSV export"]
    assert prepare, "the Reviews page should offer the export"
    prepare[0].click().run()
    assert not app.exception, app.exception
    assert "whyptology_export_csv" in app.session_state
    assert app.get("download_button"), "a download button should appear"
    csv_text = app.session_state["whyptology_export_csv"]
    assert "licence" in csv_text.splitlines()[0]


# ---------- A19 / A27: a non-ASCII reviewer key must not crash ----------


def test_check_reviewer_key_handles_non_ascii():
    assert check_reviewer_key("Pässwort", "Pässwort") is True
    assert check_reviewer_key("ägypten", "secret") is False
    assert check_reviewer_key("ꜣbḏw", "ꜣbḏw") is True
    assert check_reviewer_key("secret", "Pässwort") is False
    assert check_reviewer_key("", "x") is False
    assert check_reviewer_key("x", "") is False
    assert check_reviewer_key("", "") is False


def _gate_app(monkeypatch, key: str | None, **session) -> AppTest:
    if key is None:
        monkeypatch.delenv("REVIEWER_KEY", raising=False)
    else:
        monkeypatch.setenv("REVIEWER_KEY", key)
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    app = _app("home")
    for name, val in session.items():
        app.session_state[name] = val
    return app


def test_non_ascii_key_typed_into_the_gate_is_rejected_not_a_traceback(monkeypatch):
    app = _gate_app(monkeypatch, "ASCIIkey")
    app.run()
    app.text_input(key="whyptology_reviewer_key_input").set_value("Pässwort")
    app.button(key="whyptology_reviewer_unlock").click().run()
    assert not app.exception, app.exception
    assert any("That key was not recognised" in e.value for e in app.error)
    assert "whyptology_reviewer_ok" not in app.session_state


def test_an_operator_key_with_an_umlaut_still_unlocks(monkeypatch):
    app = _gate_app(monkeypatch, "Pässwort")
    app.run()
    app.text_input(key="whyptology_reviewer_key_input").set_value("Pässwort")
    app.button(key="whyptology_reviewer_unlock").click().run()
    assert not app.exception, app.exception
    assert app.session_state["whyptology_reviewer_ok"] is True


# ---------- A18 / A58: attempts are counted, locked out and logged ----------


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_guard_locks_after_the_free_attempts_and_unlocks_after_the_cooldown():
    clock = _Clock()
    guard = KeyAttemptGuard(clock=clock)
    for _ in range(4):
        guard.record_failure()
        assert guard.seconds_locked() == 0
    assert guard.record_failure() == 5
    assert guard.seconds_locked() == 30
    clock.now += 29
    assert guard.seconds_locked() == 1
    clock.now += 2
    assert guard.seconds_locked() == 0


def test_guard_cooldown_grows_and_is_capped():
    clock = _Clock()
    guard = KeyAttemptGuard(window=10**9, clock=clock)
    waits = []
    for _ in range(40):
        guard.record_failure()
        waits.append(guard.seconds_locked())
        clock.now += waits[-1] + 1
    nonzero = [w for w in waits if w]
    assert nonzero[:3] == [30, 60, 120]
    assert max(nonzero) == 15 * 60


def test_guard_forgets_failures_outside_the_window_and_reset_clears():
    clock = _Clock()
    guard = KeyAttemptGuard(clock=clock)
    for _ in range(4):
        guard.record_failure()
    clock.now += 16 * 60
    assert guard.record_failure() == 1, "old failures are forgotten"
    assert guard.seconds_locked() == 0
    for _ in range(4):
        guard.record_failure()
    assert guard.seconds_locked() > 0
    guard.reset()
    assert guard.seconds_locked() == 0
    assert guard.record_failure() == 1


def test_failed_unlock_is_logged_with_a_count_and_never_the_typed_key(monkeypatch, caplog):
    app = _gate_app(monkeypatch, "ASCIIkey")
    app.run()
    with caplog.at_level(logging.INFO):
        app.text_input(key="whyptology_reviewer_key_input").set_value("hunter2")
        app.button(key="whyptology_reviewer_unlock").click().run()
    assert not app.exception, app.exception
    warnings = [r for r in caplog.records if "failed unlock attempt" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "(1 recent failures)" in warnings[0].getMessage()
    assert "hunter2" not in caplog.text
    assert "ASCIIkey" not in caplog.text


def test_an_empty_submission_is_not_counted_as_a_guess(monkeypatch):
    app = _gate_app(monkeypatch, "ASCIIkey")
    app.run()
    app.button(key="whyptology_reviewer_unlock").click().run()
    assert not app.exception, app.exception
    assert review_common.REVIEWER_KEY_GUARD.record_failure() == 1


def test_a_locked_gate_refuses_even_the_correct_key(monkeypatch):
    monkeypatch.setattr(review_common, "REVIEWER_KEY_GUARD", KeyAttemptGuard(free_attempts=1))
    app = _gate_app(monkeypatch, "ASCIIkey")
    app.run()
    for typed in ("wrong-1", "wrong-2", "ASCIIkey"):
        app.text_input(key="whyptology_reviewer_key_input").set_value(typed)
        app.button(key="whyptology_reviewer_unlock").click().run()
        assert not app.exception, app.exception
    assert any("Too many failed attempts" in e.value for e in app.error)
    assert "whyptology_reviewer_ok" not in app.session_state, (
        "a correct key must not unlock while the counter is in cooldown"
    )


def test_a_correct_key_resets_the_counter(monkeypatch):
    guard = KeyAttemptGuard()
    monkeypatch.setattr(review_common, "REVIEWER_KEY_GUARD", guard)
    app = _gate_app(monkeypatch, "ASCIIkey")
    app.run()
    app.text_input(key="whyptology_reviewer_key_input").set_value("nope")
    app.button(key="whyptology_reviewer_unlock").click().run()
    app.text_input(key="whyptology_reviewer_key_input").set_value("ASCIIkey")
    app.button(key="whyptology_reviewer_unlock").click().run()
    assert app.session_state["whyptology_reviewer_ok"] is True
    assert guard.record_failure() == 1


# ---------- A20: annotation writes fail closed ----------


class _FakeStreamlit:
    def __init__(self, state: dict):
        self.session_state = state


def test_annotations_closed_without_a_key_unless_explicitly_allowed(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setattr(app_module, "configured_reviewer_key", lambda: "")
    monkeypatch.delenv("ALLOW_OPEN_ANNOTATIONS", raising=False)
    assert app_module.annotations_unlocked() is False
    for truthy in ("1", "true", "YES"):
        monkeypatch.setenv("ALLOW_OPEN_ANNOTATIONS", truthy)
        assert app_module.annotations_unlocked() is True
    monkeypatch.setenv("ALLOW_OPEN_ANNOTATIONS", "0")
    assert app_module.annotations_unlocked() is False


def test_annotations_with_a_key_need_the_session_flag_whatever_the_open_switch(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setattr(app_module, "configured_reviewer_key", lambda: "secret")
    monkeypatch.setenv("ALLOW_OPEN_ANNOTATIONS", "1")
    monkeypatch.setattr(app_module, "st", _FakeStreamlit({}))
    assert app_module.annotations_unlocked() is False
    monkeypatch.setattr(app_module, "st", _FakeStreamlit({"whyptology_reviewer_ok": True}))
    assert app_module.annotations_unlocked() is True


_SEARCH_QUERY = "ꜥḥꜥ.n stẖ ḥr ḏd n =f"


def _workspace_app(monkeypatch) -> AppTest:
    monkeypatch.delenv("REVIEWER_KEY", raising=False)
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    return _app("workspace")


def _search(app: AppTest, query: str = _SEARCH_QUERY) -> AppTest:
    app.run()
    app.text_area[0].set_value(query).run()
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run()
    assert not app.exception, app.exception
    return app


def test_workspace_has_no_save_button_when_no_key_is_configured(monkeypatch):
    monkeypatch.setenv("ANNOTATIONS_DURABLE", "1")
    monkeypatch.delenv("ALLOW_OPEN_ANNOTATIONS", raising=False)
    app = _search(_workspace_app(monkeypatch))
    assert not [b for b in app.button if b.label == "Save annotation"]
    assert any("switched off" in c.value for c in app.caption)


def test_workspace_offers_save_when_open_annotations_are_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("ANNOTATIONS_DURABLE", "1")
    monkeypatch.setenv("ALLOW_OPEN_ANNOTATIONS", "1")
    app = _search(_workspace_app(monkeypatch))
    assert [b for b in app.button if b.label == "Save annotation"]


# ---------- A59: the keyed-search hint ----------


def test_reviewer_expander_warns_about_the_first_keyed_search(monkeypatch):
    app = _gate_app(monkeypatch, "ASCIIkey", whyptology_reviewer_ok=True)
    app.run()
    assert not app.exception, app.exception
    assert any("first search after the server restarts" in c.value for c in app.caption)
    app = _gate_app(monkeypatch, None)
    app.run()
    assert not any("first search after the server restarts" in c.value for c in app.caption)


# ---------- A30: the export credits each row's own corpus ----------

_ONE_PER_SOURCE = [
    ("TLA", "Earlier Egyptian", "tla-Earlier_Egyptian_original-v18-premium"),
    ("TLA", "Late Egyptian", "tla-late_egyptian-v19-premium"),
    ("TLA", "Demotic", "tla-demotic-v18-premium"),
    ("AES", "Unspecified (AES)", "simondschweitzer/aes"),
    ("BBAW", "Unspecified (BBAW)", "phiwi/bbaw_egyptian"),
    ("Ramses", "Late Egyptian", "zenodo.4954597"),
]
_ALL_SLUGS = [slug for *_, slug in _ONE_PER_SOURCE]


def test_each_export_row_names_its_own_corpus_only():
    frame = pd.DataFrame(
        [
            {"source": src, "language_stage": stage, "transliteration_gold": "ḥtp"}
            for src, stage, _ in _ONE_PER_SOURCE
        ]
    )
    out = with_licence_notice(frame)
    assert out["licence"].nunique() == len(_ONE_PER_SOURCE)
    for (_, _, slug), notice in zip(_ONE_PER_SOURCE, out["licence"]):
        assert slug in notice
        for other in _ALL_SLUGS:
            if other != slug:
                assert other not in notice, f"{slug} row also names {other}"
        assert "CC BY-SA 4.0" in notice and "Adapted" in notice and "warrant" in notice


def test_unknown_or_missing_source_falls_back_to_the_generic_notice():
    assert licence_notice_for("Nowhere", "") == LICENCE_NOTICE
    assert licence_notice_for("", "") == LICENCE_NOTICE
    assert licence_notice_for("TLA", "Klingon") == LICENCE_NOTICE
    assert licence_notice_for(None, None) == LICENCE_NOTICE
    for slug in _ALL_SLUGS:
        assert slug in LICENCE_NOTICE, "the generic notice must name every public corpus"


def test_a_frame_without_a_source_column_gets_the_generic_notice():
    out = with_licence_notice(pd.DataFrame([{"a": "x"}, {"a": "y"}]))
    assert list(out["licence"]) == [LICENCE_NOTICE, LICENCE_NOTICE]


def test_plain_credits_stay_in_step_with_the_html_credits():
    """Every URL the footer links to is also in the plain-text notice."""
    import app.ui.whyptology_app as app_module

    for source, html_credit in app_module.CORPUS_CREDITS.items():
        plain = " ".join(text for (src, _), text in PUBLIC_CREDITS.items() if src == source)
        assert plain, f"no plain-text credit for {source}"
        for url in re.findall(r'href="([^"]+)"', html_credit):
            assert url in plain, f"{source}: {url} is linked in the footer but not exported"
    assert {src for src, _ in PUBLIC_CREDITS} == set(app_module.CORPUS_CREDITS)


def test_every_source_and_stage_in_the_corpus_has_a_specific_notice(examples_meta):
    pairs = examples_meta.groupby(["source", "language_stage"]).size().index
    for source, stage in pairs:
        assert licence_notice_for(source, stage) != LICENCE_NOTICE, (source, stage)


# ---------- A62: spreadsheet formulas ----------


def test_formula_like_cells_are_neutralised_with_a_leading_quote():
    cells = ["=f ꞽw sḫꜣ.tw", "-ꜥnḫ", "+x", "@x", '=HYPERLINK("https://evil","s")', "\t=1", "\r=1"]
    out = with_licence_notice(pd.DataFrame({"transliteration_gold": cells}))
    assert all(c.startswith("'") for c in out["transliteration_gold"])
    assert out["transliteration_gold"][0] == "'=f ꞽw sḫꜣ.tw"


def test_ordinary_cells_and_numbers_are_left_alone_and_the_input_is_not_mutated():
    frame = pd.DataFrame(
        {
            "text": ["-5", "3.2", "+7", "ꜥnḫ", "", None, "a=b"],
            "n": [1, 2, 3, 4, 5, 6, 7],
        }
    )
    before = frame.copy(deep=True)
    out = neutralise_spreadsheet_formulas(frame)
    assert list(out["text"][:4]) == ["-5", "3.2", "+7", "ꜥnḫ"]
    assert out["text"][4] == ""
    assert pd.isna(out["text"][5])
    assert out["text"][6] == "a=b"
    assert list(out["n"]) == list(frame["n"])
    pd.testing.assert_frame_equal(frame, before)


def test_exported_csv_round_trips_with_no_formula_cell():
    from io import StringIO

    frame = pd.DataFrame(
        {
            "source": ["TLA"] * 3,
            "language_stage": ["Earlier Egyptian"] * 3,
            "transliteration_gold": ["=f ḥr bw-nfr", "-nb", "ꜥnḫ"],
            "note": ['=HYPERLINK("https://evil","source")', "", "x"],
        }
    )
    csv_text = with_licence_notice(frame).to_csv(index=False)
    back = pd.read_csv(StringIO(csv_text), keep_default_na=False)
    assert len(back) == 3
    for column in back.columns:
        for cell in back[column].astype(str):
            assert not cell.startswith(("=", "+", "-", "@")), (column, cell)


# ---------- A2 / A39: credits and DATA-LICENSE.md match the corpus ----------


def test_every_tla_stage_is_credited(examples_meta):
    import app.ui.whyptology_app as app_module

    slugs = {
        "Earlier Egyptian": "tla-Earlier_Egyptian_original-v18-premium",
        "Late Egyptian": "tla-late_egyptian-v19-premium",
        "Demotic": "tla-demotic-v18-premium",
    }
    tla = examples_meta[examples_meta["source"] == "TLA"]
    assert set(tla["language_stage"]) <= set(slugs), "a TLA stage with no credit"
    for stage in set(tla["language_stage"]):
        frame = pd.DataFrame({"source": ["TLA"], "language_stage": [stage]})
        assert slugs[stage] in app_module.corpus_credit_html(frame)
    prefixes = {
        "TLA_EARLIER_": "Earlier Egyptian",
        "TLA_LATE_": "Late Egyptian",
        "TLA_DEMOTIC_": "Demotic",
    }
    for prefix, stage in prefixes.items():
        ids = tla[tla["source_text_id"].str.startswith(prefix)]
        assert len(ids), prefix
        assert set(ids["language_stage"]) == {stage}


def test_data_licence_matches_the_corpus(examples_meta):
    text = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    assert "tla-demotic-v18-premium" in text
    assert "tlaDemoticV18premium" in text
    for count in ("11,996", "40,064", "52,216", "27,937", "12,127", "46,847"):
        assert count in text, count
    assert "does not yet contain Ramses" not in text
    assert "is **not** part\nof `examples.csv`" not in text
    sizes = examples_meta.groupby(["source", "language_stage"]).size()
    assert sizes[("TLA", "Demotic")] == 11996
    assert sizes[("Ramses", "Late Egyptian")] == 40064
    assert sizes[("BBAW", "Unspecified (BBAW)")] == 52216


# ---------- A9: CORPUS_SOURCES_EXCLUDE matches the stage too ----------

_EXCLUDE_FRAME = pd.DataFrame(
    {
        "source": ["TLA", "TLA", "Ramses", "BBAW", "TLA"],
        "language_stage": [
            "Earlier Egyptian",
            "Demotic",
            "Late Egyptian",
            "Unspecified (BBAW)",
            "Late Egyptian",
        ],
    }
)


def test_excluding_demotic_drops_the_tla_demotic_rows(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "Ramses,Demotic")
    out = app_module.exclude_corpus_sources(_EXCLUDE_FRAME)
    assert list(out["source"]) == ["TLA", "BBAW", "TLA"]
    assert "Demotic" not in set(out["language_stage"])


def test_exclusion_tokens_can_be_a_source_or_a_stage(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "TLA")
    assert list(app_module.exclude_corpus_sources(_EXCLUDE_FRAME)["source"]) == ["Ramses", "BBAW"]
    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "Late Egyptian")
    assert list(app_module.exclude_corpus_sources(_EXCLUDE_FRAME)["source"]) == ["TLA", "TLA", "BBAW"]
    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "")
    assert len(app_module.exclude_corpus_sources(_EXCLUDE_FRAME)) == 5


def test_exclusion_works_on_a_frame_with_no_stage_column(monkeypatch):
    import app.ui.whyptology_app as app_module

    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "Ramses,Demotic")
    frame = _EXCLUDE_FRAME[["source"]]
    assert list(app_module.exclude_corpus_sources(frame)["source"]) == ["TLA", "TLA", "BBAW", "TLA"]


def test_the_live_exclusion_setting_leaves_the_78k_corpus(monkeypatch):
    import app.ui.whyptology_app as app_module
    from app.data.loader import load_examples_csv

    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "Ramses,Demotic")
    full = load_examples_csv(str(EXAMPLES_CSV))
    assert len(full) == 130472
    assert len(app_module.exclude_corpus_sources(full)) == 130472 - 40064 - 11996


# ---------- A28 / A29: Markdown escaping ----------

_HOSTILE = [
    "![x](https://attacker.example/p.png) xxxx",
    "[Session expired, re-enter your reviewer key](https://phish.example)",
    "$ṯms.t$-Pflanze",
    "dm.tw rn =k rʾ n [r](m)t.pl",
    "*b*",
    "_x_",
    ":smile:",
    "# h",
    "- item",
    "1. item",
    "<img src=x>",
    "a\nb",
    "a | b ~~c~~ `d` {e}",
    "back\\slash",
    "==setext\n===",
]
_MD_CHARS = set("\\`*_{}[]()#+-.!$|~<>:&=")


def _unescaped_specials(out: str) -> list[str]:
    """Special characters in `out` that are not themselves escaped by a backslash."""
    found, i = [], 0
    while i < len(out):
        if out[i] == "\\":
            assert i + 1 < len(out), "dangling backslash"
            i += 2
            continue
        if out[i] in _MD_CHARS:
            found.append(out[i])
        i += 1
    return found


@pytest.mark.parametrize("text", _HOSTILE)
def test_md_escape_leaves_no_active_markdown_and_no_newline(text):
    out = md_escape(text)
    assert _unescaped_specials(out) == []
    assert "\n" not in out and "\r" not in out


def test_md_escape_keeps_egyptological_letters_and_handles_none():
    out = md_escape("ꜥḥꜥ.n stẖ")
    assert out == "ꜥḥꜥ\\.n stẖ"
    assert md_escape(None) == ""
    assert md_escape(12) == "12"


def test_md_code_cannot_be_closed_early():
    out = md_code("a`b``c")
    assert out.startswith("`") and out.endswith("`")
    assert "`" not in out[1:-1]
    assert md_code("x\ny") == "`x y`"


def test_the_empty_result_clause_cannot_inject_an_image_or_a_link():
    import app.ui.whyptology_app as app_module
    from app.data.query import parse_query

    assert app_module.looked_for_clause(None) == ""
    for hostile in _HOSTILE[:2]:
        clause = app_module.looked_for_clause(parse_query(hostile))
        assert "![" not in clause and "](" not in clause
        assert "\\!\\[" in clause or "\\[" in clause or "\\(" in clause


def test_no_unescaped_corpus_or_query_text_reaches_a_markdown_call():
    """Source guard: every f-string placeholder that carries corpus, model or query
    text inside a Markdown-rendering call (st.markdown without unsafe_allow_html,
    caption, warning, info, expander ...) goes through md_escape / md_code."""
    import ast

    source = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    tree = ast.parse(source)
    sinks = {"markdown", "caption", "warning", "info", "error", "success", "expander", "write"}
    risky = re.compile(
        r"\bvalue\(|\bsearched\b|\bparse\.(reading|raw|search_key|hieroglyphs_norm)\b"
        r"|\bpasted_reading\b|\bp\.predicted\b|\bothers\b"
    )
    safe = re.compile(r"md_escape\(|md_code\(|looked_for_clause\(")
    offenders = []
    for call in ast.walk(tree):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in sinks
        ):
            continue
        if any(k.arg == "unsafe_allow_html" for k in call.keywords):
            continue
        for node in ast.walk(call):
            if isinstance(node, ast.FormattedValue):
                expr = ast.unparse(node.value)
                if risky.search(expr) and not safe.search(expr):
                    offenders.append((call.lineno, expr))
    assert not offenders, f"unescaped Markdown interpolation: {offenders}"


def test_hostile_query_in_the_empty_state_is_escaped_on_the_page():
    """Seeds the state the empty result reads, so it is deterministic."""
    from app.data.query import parse_query

    hostile = "![x](https://a.example/p.png) zzzz"
    app = _app("workspace")
    app.session_state["whyptology_results"] = pd.DataFrame()
    app.session_state["whyptology_suggestions"] = []
    app.session_state["whyptology_last_query"] = hostile
    app.session_state["whyptology_last_parse"] = parse_query(hostile)
    app.run()
    assert not app.exception, app.exception
    warnings = [w.value for w in app.warning if w.value.startswith("No parallel")]
    assert warnings, "the empty-result warning should show"
    assert "![x](" not in warnings[0]
    assert "\\!\\[x\\]\\(" in warnings[0]


# ---------- A31 / A44: the corpus signature ----------


def _signature_frame(ids=None) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "hieroglyphs_norm": ["𓊵𓏏", "𓇓𓏏", ""],
            "transliteration_gold": ["ḥtp", "nb.t", "x"],
        }
    )
    if ids is not None:
        frame["id"] = ids
    return frame


def test_signature_is_hashed_once_per_frame_object(monkeypatch):
    import app.ui.whyptology_app as app_module

    calls = []
    real = pd.util.hash_pandas_object

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(pd.util, "hash_pandas_object", spy)
    frame = _signature_frame()
    first = app_module.corpus_signature(frame)
    assert app_module.corpus_signature(frame) == first
    assert app_module.corpus_signature(frame) == first
    assert len(calls) == 2, "two columns hashed once, not once per call"
    other = _signature_frame()
    assert app_module.corpus_signature(other) == first
    assert len(calls) == 4, "a different frame object is hashed again"

    key = id(frame)
    assert key in review_common._SIGNATURE_MEMO
    del frame
    gc.collect()
    assert key not in review_common._SIGNATURE_MEMO, "the memo must not keep frames alive"


def test_signature_says_whether_the_frame_has_database_ids():
    import app.ui.whyptology_app as app_module

    no_ids = app_module.corpus_signature(_signature_frame())
    with_ids = app_module.corpus_signature(_signature_frame([1, 2, 3]))
    all_none = app_module.corpus_signature(_signature_frame([None, None, None]))
    partial = app_module.corpus_signature(_signature_frame([None, 2, None]))
    assert no_ids.endswith("+noids")
    assert with_ids.endswith("+ids")
    assert all_none.endswith("+noids"), "an id column of all None is still id-less"
    assert partial.endswith("+ids")
    assert no_ids.split("+")[0] == with_ids.split("+")[0] == all_none.split("+")[0]


def test_stage_resources_are_rebuilt_once_the_frame_gains_ids():
    """A boot-time database failure must not pin the id-less frame in every cache."""
    import app.ui.whyptology_app as app_module
    from app.data.loader import load_examples_csv

    corpus = load_examples_csv(str(EXAMPLES_CSV)).head(400).reset_index(drop=True)
    plain = corpus.copy()
    keyed = corpus.copy()
    keyed["id"] = range(1, len(keyed) + 1)
    plain_sig = app_module.corpus_signature(plain)
    keyed_sig = app_module.corpus_signature(keyed)
    assert plain_sig != keyed_sig
    first = app_module.load_stage_resources(None, plain_sig, plain)
    second = app_module.load_stage_resources(None, keyed_sig, keyed)
    assert "id" not in first.frame.columns
    assert second is not first
    assert "id" in second.frame.columns


def test_no_stage_warm_up_when_the_database_was_down_at_boot(monkeypatch):
    import streamlit as st

    import app.services.stage as stage_module
    from app.storage.db import DatabaseUnavailable

    built = []

    def refuse(*args, **kwargs):
        built.append(args)
        raise RuntimeError("test: no resources may be built")

    def down(_df):
        raise DatabaseUnavailable("test: database offline")

    st.cache_resource.clear()
    try:
        monkeypatch.setenv("WARM_STAGE_RESOURCES", "1")
        monkeypatch.setattr(stage_module, "build_stage_resources", refuse)
        monkeypatch.setattr(review_common, "attach_db_ids", down)
        app = _app("home")
        app.run()
        assert not app.exception, app.exception
        assert any("Read-only mode" in w.value for w in app.warning)
        assert built == [], "warm-up must not spend memory on an id-less frame"
    finally:
        st.cache_resource.clear()


# ---------- A61: Home navigation keeps the session ----------


def test_home_has_no_new_tab_links_and_buttons_keep_the_session(monkeypatch):
    monkeypatch.setenv("REVIEWER_KEY", "ASCIIkey")
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    for label, page in (
        ("Explore the workspace →", "Workspace"),
        ("Browse the corpus", "Corpus"),
    ):
        app = _app()
        app.session_state["whyptology_reviewer_ok"] = True
        app.run()
        assert not app.exception, app.exception
        assert not any('href="?view=' in m.value for m in app.markdown)
        next(b for b in app.button if b.label == label).click().run()
        assert not app.exception, app.exception
        assert app.session_state["page"] == page
        assert app.session_state["whyptology_reviewer_ok"] is True


# ---------- A63: the card-view caption ----------


def test_card_view_does_not_claim_the_first_30(monkeypatch):
    app = _app("corpus")
    app.run()
    app.number_input[0].set_value(2).run()
    assert not app.exception, app.exception
    captions = [c.value for c in app.caption]
    assert not any("first 30" in c for c in captions)
    assert any(c.startswith("Showing 51–100 of") for c in captions)


# ---------- A60: the evidence table uses the transliteration font ----------


def test_html_table_escapes_and_marks_only_the_reading_columns():
    import app.ui.whyptology_app as app_module

    frame = pd.DataFrame(
        {"Reading": ["ꞽw <script>x</script>"], "Note<b>": ["a & b"], "Text": ["t"]}
    )
    out = app_module.html_table(frame, {"Reading"})
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<th>Note&lt;b&gt;</th>" in out
    assert "a &amp; b" in out
    assert out.count('class="corpus-cell-reading"') == 1
    assert '<td class="corpus-cell-reading">ꞽw' in out
    assert out.startswith('<div class="corpus-table-wrap">')


def test_workspace_evidence_table_is_html_with_the_reading_font():
    import html

    app = _search(_workspace_app_plain())
    tables = [m.value for m in app.markdown if 'class="corpus-table"' in m.value]
    assert tables, "the evidence table should be rendered as an HTML table"
    assert "corpus-cell-reading" in tables[0]
    assert "<th>Match</th>" in tables[0]
    top = app.session_state["whyptology_results"].iloc[0]["transliteration_gold"]
    assert html.escape(str(top)) in tables[0]


def _workspace_app_plain() -> AppTest:
    return _app("workspace")


# ---------- A52: the API carries licence and attribution ----------


def test_api_response_carries_licence_and_attribution():
    from app.api.main import search_examples

    payload = search_examples(query_mdc="htp", k=3)
    assert payload["query"] == "htp" and payload["results"]
    assert payload["licence"]["name"] == "CC BY-SA 4.0"
    assert payload["licence"]["url"].startswith("https://creativecommons.org/")
    assert payload["attribution"] and all(isinstance(a, str) for a in payload["attribution"])
    sources = {row["source"] for row in payload["results"]}
    joined = " ".join(payload["attribution"])
    marker = {
        "TLA": "thesaurus-linguae-aegyptiae",
        "AES": "simondschweitzer/aes",
        "BBAW": "phiwi/bbaw_egyptian",
        "Ramses": "zenodo.4954597",
    }
    for source in sources:
        assert marker[source] in joined, f"no attribution for {source}"


def test_api_limits_the_query_length():
    from app.api.main import app as api_app

    params = api_app.openapi()["paths"]["/examples/search"]["get"]["parameters"]
    query = next(p for p in params if p["name"] == "query_mdc")
    assert query["schema"]["maxLength"] == 500
