"""The private, non-redistributed data path (Ramses, the St Andrews texts).

Both corpora are CC BY-NC-SA 4.0 — non-commercial — and CC BY-SA is share-alike, so
they can never enter `data/processed/examples.csv` or the public repository. They
are read at runtime from a gitignored directory (`PRIVATE_DATA_DIR`, default
`data/private/`) and concatenated onto the public corpus only *after* the database
step, so they never get a database id, never reach the database, the reviewed-export
script, or the API. These tests are the guard that promise stays kept.

Since 2026-09-05 there is a second guard on top: the *reviewer-key gate*. The app is
deployed on one public URL, so "the directory is empty on the server" is no longer
the only thing keeping the NC rows off it — a session sees them only after presenting
`REVIEWER_KEY`. The gate is the frame itself, not a filter: an unkeyed session holds
the public frame and every index built from it, a keyed session holds public+private
under its own `corpus_signature` and a second, separately cached set of indexes. The
"reviewer-key gate" section below walks every surface that shows a corpus row and
checks both sides of it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from app.data.loader import REQUIRED_COLUMNS, load_examples_csv, load_private_examples  # noqa: E402


# ---------- the directory itself is never committed ----------


def test_private_data_dir_is_not_tracked_by_git():
    result = subprocess.run(
        ["git", "ls-files", "data/private"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", (
        "data/private must never be committed: "
        f"git tracks {result.stdout.strip()!r}"
    )


def test_private_data_dir_is_gitignored():
    probe = PROJECT_ROOT / "data" / "private" / "probe_file_for_gitignore_test.csv"
    result = subprocess.run(
        ["git", "check-ignore", str(probe)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "data/private/ is not covered by .gitignore (git check-ignore exited "
        f"{result.returncode}); a private CSV dropped there could be committed by "
        "accident"
    )


# ---------- the loader ----------


def test_load_private_examples_is_empty_with_the_right_columns_when_missing(tmp_path):
    missing = tmp_path / "does_not_exist"
    df = load_private_examples(missing)
    assert df.empty
    for col in REQUIRED_COLUMNS:
        assert col in df.columns


def test_load_private_examples_is_empty_with_the_right_columns_when_the_folder_is_empty(
    tmp_path,
):
    df = load_private_examples(tmp_path)
    assert df.empty
    for col in REQUIRED_COLUMNS:
        assert col in df.columns


def _private_row(**overrides) -> dict:
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


def test_load_private_examples_reads_every_csv_and_logs_counts(tmp_path, caplog):
    rows_a = [_private_row(source="Ramses", source_sentence_id=f"a{i}") for i in range(2)]
    rows_b = [_private_row(source="StAndrews", source_sentence_id=f"b{i}") for i in range(3)]
    pd.DataFrame(rows_a).to_csv(tmp_path / "ramses.csv", index=False)
    pd.DataFrame(rows_b).to_csv(tmp_path / "standrews.csv", index=False)

    with caplog.at_level("INFO"):
        df = load_private_examples(tmp_path)

    assert len(df) == 5
    assert set(df["source"]) == {"Ramses", "StAndrews"}
    assert "2 private rows from ramses.csv" in caplog.text
    assert "3 private rows from standrews.csv" in caplog.text


def test_load_private_examples_rejects_a_blank_source(tmp_path):
    rows = [_private_row(source="Ramses"), _private_row(source="")]
    pd.DataFrame(rows).to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(ValueError, match="empty 'source'"):
        load_private_examples(tmp_path)


def test_load_private_examples_matches_the_public_schema(tmp_path):
    pd.DataFrame([_private_row(source="Ramses")]).to_csv(tmp_path / "r.csv", index=False)
    private_df = load_private_examples(tmp_path)
    public_df = load_examples_csv(str(PROJECT_ROOT / "data" / "processed" / "examples.csv"))
    assert set(private_df.columns) == set(public_df.columns)


# ---------- concatenation happens after the database step ----------


@pytest.fixture()
def private_app(tmp_path, monkeypatch):
    """The whyptology_app module, pointed at a temporary private-data directory.

    Imported once per test process (other tests import it too), so the directory
    is swapped on the already-imported module object and its `st.cache_resource`
    caches are cleared rather than re-importing the module.
    """
    import app.ui.whyptology_app as w

    monkeypatch.setattr(w, "PRIVATE_DATA_DIR", tmp_path)
    w.load_private_corpus.clear()
    yield w, tmp_path
    w.load_private_corpus.clear()


def test_private_rows_are_appended_after_attach_db_ids_with_no_id(private_app):
    w, tmp_path = private_app
    rows = [_private_row(source="TestPrivate", source_sentence_id=f"p{i}") for i in range(3)]
    pd.DataFrame(rows).to_csv(tmp_path / "test_private.csv", index=False)

    public_before = w.load_corpus_csv()
    with_ids = w.load_corpus_with_ids(public_before, w.corpus_signature(public_before))
    combined = w._append_private_rows(with_ids)

    # The public frame itself is untouched.
    assert len(with_ids) == len(public_before)
    assert "TestPrivate" not in set(with_ids["source"])

    # The private rows are present in the combined frame...
    private_rows = combined[combined["source"] == "TestPrivate"]
    assert len(private_rows) == 3
    # ...carry no database id...
    assert private_rows["id"].isna().all()
    # ...and every other row is exactly what attach_db_ids produced.
    assert len(combined) == len(with_ids) + 3
    non_private = combined[combined["source"] != "TestPrivate"]
    # Compare values, not dtypes: with a fresh local database every id is present and the
    # column is int64; with a stale one some ids are missing and it is float64 — both are
    # legitimate states, and appending private rows must change neither the values nor
    # the order. A plain list comparison would also trip on nan != nan.
    pd.testing.assert_series_equal(
        non_private["id"].reset_index(drop=True),
        with_ids["id"].reset_index(drop=True),
        check_dtype=False,
        check_names=False,
    )


def test_private_data_dir_env_var_default(monkeypatch):
    monkeypatch.delenv("PRIVATE_DATA_DIR", raising=False)
    # Reproduce the module's own default-resolution logic to pin its behaviour: a
    # fresh interpreter with no PRIVATE_DATA_DIR set resolves to data/private/ under
    # the project root.
    import os

    default = os.environ.get("PRIVATE_DATA_DIR") or str(PROJECT_ROOT / "data" / "private")
    assert default == str(PROJECT_ROOT / "data" / "private")


# ---------- per-source credit lines ----------


def test_credit_html_has_a_non_cc_by_sa_line_for_a_private_source(private_app):
    w, tmp_path = private_app
    frame = pd.DataFrame(
        {
            "source": ["TLA", "TLA", "TestPrivate", "TestPrivate", "TestPrivate"],
        }
    )
    rendered = w.corpus_credit_html(frame)
    private_line = (
        "TestPrivate: private, non-commercial corpus data — used locally under "
        "its own licence and not redistributed with this app."
    )
    assert private_line in rendered
    assert "BY-SA" not in private_line
    # The public sentence is still there, and still says CC BY-SA, for the public
    # sources actually present.
    assert "BY-SA" in rendered
    # The TLA hyperlink points at the licensed dataset publications, not the
    # TLA website (which carries no CC licence for its data — see the audit).
    assert "huggingface.co/datasets/thesaurus-linguae-aegyptiae" in rendered


def test_credit_html_gives_ramses_its_required_wording_in_the_public_sentence():
    """Ramses moved from the NC private group to the public CC BY-SA group on
    2026-09-04: the rights holders (Projet Ramses / Université de Liège) granted
    CC BY-SA 4.0 for this project's use by email — see docs/permission-requests.md
    ("Reply from Projet Ramses, 2026-09-04") and DATA-LICENSE.md. The required
    attribution string is unchanged from when it was the NC entry."""
    from app.ui.whyptology_app import corpus_credit_html

    rendered = corpus_credit_html(pd.DataFrame({"source": ["Ramses"]}))
    assert "Ramses transliteration corpus V. 2019-09-01" in rendered
    assert "University of Liège" in rendered or "Liège" in rendered
    assert "zenodo.4954597" in rendered
    # It is folded into the CC BY-SA sentence now, not a separate NC one.
    assert "BY-SA" in rendered
    assert "BY-NC-SA" not in rendered


def test_credit_html_gives_st_andrews_its_required_nc_wording():
    from app.ui.whyptology_app import corpus_credit_html

    rendered = corpus_credit_html(pd.DataFrame({"source": ["StAndrews"]}))
    assert "St Andrews Corpus of Ancient Egyptian texts" in rendered
    assert "Mark-Jan Nederhof" in rendered
    assert "mjn.host.cs.st-andrews.ac.uk/egyptian/texts" in rendered
    # Reworded per the licence audit: the app does "Share" the rows (CC §1), so
    # "not redistributed with this app" (true only of the files) became this.
    assert "underlying files are not redistributed" in rendered
    # The licence label itself hyperlinks to the licence text, not the source.
    assert "creativecommons.org/licenses/by-nc-sa/4.0" in rendered
    assert "BY-SA" not in rendered
    assert "BY-NC-SA" in rendered


def test_credit_html_only_shows_the_nc_licence_link_when_st_andrews_is_present():
    """A frame carrying only Ramses rows must read as plain CC BY-SA — the
    by-nc-sa link is St Andrews' alone now that Ramses has its own BY-SA grant."""
    from app.ui.whyptology_app import corpus_credit_html

    ramses_only = corpus_credit_html(pd.DataFrame({"source": ["Ramses"]}))
    assert "by-nc-sa" not in ramses_only

    both = corpus_credit_html(pd.DataFrame({"source": ["Ramses", "StAndrews"]}))
    assert "creativecommons.org/licenses/by-nc-sa/4.0" in both
    # Ramses still appears, inside the public sentence, not the NC one.
    assert "Ramses transliteration corpus V. 2019-09-01" in both


def test_pure_public_corpus_credit_still_reads_as_cc_by_sa_for_all_rows():
    """No private rows present: the CC BY-SA sentence must not have grown a
    disclaimer or otherwise read as partial coverage."""
    from app.ui.whyptology_app import corpus_credit_html

    corpus = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "examples.csv")
    rendered = corpus_credit_html(corpus)
    assert "CC" in rendered and "BY-SA" in rendered
    assert "BY-NC-SA" not in rendered


def test_credit_html_attribution_gaps_from_the_licence_audit_are_closed():
    """2026-09-04 licence audit (docs/licence-audit-2026-09-04.md), Q6: the TLA link
    pointed at the (non-CC-licensed) website instead of the licensed datasets, no
    warranty-disclaimer notice reached the viewer, and the NC licence label linked
    the source instead of the licence text. All three are attribution conditions
    (§3(a)(1)(A)(iv)/(v), §3(a)(1)(C)) that must hold wherever the credit is shown.

    (Ramses is used for the TLA/warranty checks only incidentally; it moved to the
    public CC BY-SA group on 2026-09-04 after a rights-holder grant, so the NC-link
    check below uses St Andrews, the source that is still NC.)"""
    from app.ui.whyptology_app import corpus_credit_html

    public_rendered = corpus_credit_html(pd.DataFrame({"source": ["TLA"]}))
    # (v): a URI to the licensed material — the Hugging Face dataset publication,
    # not the TLA website, which the audit found carries no CC licence.
    assert "huggingface.co/datasets/thesaurus-linguae-aegyptiae" in public_rendered
    # (iv): a notice referring to the disclaimer of warranties, linked to the legal
    # code (the deed alone does not carry the §5 text).
    assert "creativecommons.org/licenses/by-sa/4.0/legalcode" in public_rendered
    assert "warrant" in public_rendered.lower()

    st_andrews_rendered = corpus_credit_html(pd.DataFrame({"source": ["StAndrews"]}))
    # (C): the NC rows' licence label must link the licence text itself.
    assert "creativecommons.org/licenses/by-nc-sa/4.0" in st_andrews_rendered


# ---------- exports and the API cannot see private rows ----------


def test_export_reviewed_script_never_reads_the_private_directory():
    """It reads only the database (see app/storage), which never receives private
    rows because ensure_corpus_ready only ever runs on the public frame."""
    source = (PROJECT_ROOT / "scripts" / "export_reviewed.py").read_text()
    assert "PRIVATE_DATA_DIR" not in source
    assert "load_private_examples" not in source


def test_api_never_reads_the_private_directory():
    """The API loads examples.csv directly and has no notion of private rows."""
    source = (PROJECT_ROOT / "app" / "api" / "main.py").read_text()
    assert "PRIVATE_DATA_DIR" not in source
    assert "load_private_examples" not in source
    assert 'DATA_PATH = "data/processed/examples.csv"' in source


# ===========================================================================
# The reviewer-key gate
# ===========================================================================
#
# Every test below runs the real app through Streamlit's AppTest with a private
# directory that has files in it and a reviewer key configured — the exact state the
# server is in. The question each one asks is the only one that matters: does this
# surface show a private row to a session that has not presented the key?
#
# One private directory is shared by the whole section (module scope) on purpose. The
# keyed frame's `corpus_signature` keys every `st.cache_resource` below it, so one
# directory means the second, keyed search index is built once for the section rather
# than once per test — ~10 s and ~525 MB on the developer's Mac, measured 2026-09-05.

from contextlib import contextmanager  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = "app/ui/whyptology_app.py"
GATE_KEY = "gate-test-reviewer-key"

# The tracers: a reading, two single hieroglyphs, a text id and a translation that no
# public row contains — every one of them checked against all 130,472 rows and every
# column of the public frame. Wherever one of these shows up, a private row reached
# that surface.
#
# The two signs are *characters* absent from the corpus, not merely absent sign
# *groups*: the first pair tried (U+133FF, U+1340F) were absent as groups but occur
# inside longer public groups, and the unkeyed pages matched them by substring.
PRIVATE_READING = "zzqqwx"
PRIVATE_READING_ALT = "zzqqwy"  # the same sign read differently — see the fixture
PRIVATE_SIGNS = ("\U0001302e", "\U00013042")  # absent from examples.csv AND helsinki_lexicon.csv
PRIVATE_TEXT_ID = "pGateTest"
PRIVATE_TRANSLATION = "Ein privater Gutachter-Testsatz."
PRIVATE_ROW_COUNT = 3


@pytest.fixture(scope="module")
def gate_private_dir(tmp_path_factory) -> Path:
    """A populated PRIVATE_DATA_DIR: three St Andrews rows carrying the tracer."""
    directory = tmp_path_factory.mktemp("gate-private")
    rows = []
    for n in range(PRIVATE_ROW_COUNT):
        row = {col: "" for col in REQUIRED_COLUMNS}
        row.update(
            source="StAndrews",
            source_text_id=PRIVATE_TEXT_ID,
            source_sentence_id=f"gate{n}",
            language_stage="Earlier Egyptian",
            script_type="hieroglyphic",
            period="Test period",
            # Two space-separated sign groups against two transliteration tokens, so
            # the row is sign/reading aligned and does reach the sign index.
            hieroglyphs=f"{PRIVATE_SIGNS[0]} {PRIVATE_SIGNS[1]}",
            sign_sequence="Zz1 Zz2",
            # Two readings across the three rows for the first sign, so it is
            # *genuinely multivalent* and therefore reaches the Sign readings page —
            # which lists ambiguous signs only, and would otherwise show nothing for
            # a private row however well the gate was (or was not) working.
            transliteration_gold=(
                f"{PRIVATE_READING} nfr" if n < 2 else f"{PRIVATE_READING_ALT} nfr"
            ),
            translation=PRIVATE_TRANSLATION,
        )
        rows.append(row)
    pd.DataFrame(rows).to_csv(directory / "standrews.csv", index=False)
    return directory


@contextmanager
def _host(monkeypatch, private_dir: Path | None, reviewer_key: str | None):
    """Configure the host the way a deployment does, for one AppTest run.

    The app script resolves `PRIVATE_DATA_DIR` and the reviewer key at module scope on
    every run, and AppTest executes the file fresh each time, so the environment is
    what a test has to set — monkeypatching the imported module object would not reach
    the script AppTest runs.
    """
    if private_dir is None:
        monkeypatch.delenv("PRIVATE_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("PRIVATE_DATA_DIR", str(private_dir))
    if reviewer_key is None:
        monkeypatch.delenv("REVIEWER_KEY", raising=False)
    else:
        monkeypatch.setenv("REVIEWER_KEY", reviewer_key)
    # "auto" would infer a stage and build a second resource set per stage; the gate is
    # not about stages, and the pooled path keeps this section to one keyed index.
    monkeypatch.setenv("DEFAULT_STAGE", "all")
    yield


def _run(page: str | None = None, query: str | None = None, keyed: bool = False) -> AppTest:
    """One app run, optionally on `page`, optionally with `?q=`, optionally keyed.

    A keyed run seeds the session flag rather than typing the passphrase — the
    passphrase path itself is exercised by
    `test_the_passphrase_is_what_opens_and_closes_the_gate`.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    if page is not None:
        app.query_params["view"] = page
    if query is not None:
        app.query_params["q"] = query
    app.query_params["stage"] = "all"
    if keyed:
        app.session_state["whyptology_reviewer_ok"] = True
    app.run()
    assert not app.exception, app.exception
    return app


def _rendered(app: AppTest) -> str:
    """Everything this run put on the page, as one string."""
    parts: list[str] = []
    for name in (
        "markdown",
        "caption",
        "text",
        "title",
        "header",
        "subheader",
        "info",
        "warning",
        "error",
        "success",
        "code",
        "metric",
    ):
        for element in getattr(app, name):
            parts.append(str(getattr(element, "value", "")))
            parts.append(str(getattr(element, "label", "")))
    for box in app.selectbox:
        parts.extend(str(option) for option in (box.options or []))
    return "\n".join(parts)


def _assert_no_private_row(app: AppTest, where: str) -> None:
    """No part of a private row is on this page.

    `PRIVATE_READING` is deliberately NOT one of the tracers: it is also the query
    these tests type, and the workspace echoes the query back ("searched as `…`"), so
    its presence proves nothing. Everything a private *row* carries and a query does
    not — its source, its text id, its translation, its signs — is checked instead.
    """
    rendered = _rendered(app)
    assert "StAndrews" not in rendered, f"{where}: a private row's source reached the page"
    assert PRIVATE_TEXT_ID not in rendered, f"{where}: a private text id reached the page"
    assert PRIVATE_TRANSLATION not in rendered, f"{where}: a private translation was shown"
    for sign in PRIVATE_SIGNS:
        assert sign not in rendered, f"{where}: a private sign reached the page"
    # The NC attribution is rendered exactly when NC rows are present, so its absence
    # is a second, independent reading of the same fact.
    assert "by-nc-sa" not in rendered, f"{where}: the NC credit line reached the page"


def _corpus_total(app: AppTest) -> int:
    """The row count the corpus explorer reports for this session's frame."""
    for caption in app.caption:
        text = str(caption.value)
        if "matching records" in text:
            return int(text.rsplit(" of ", 1)[1].split(" ")[0].replace(",", ""))
    raise AssertionError("the corpus explorer did not report a record count")


# ---------- the surfaces, unkeyed ----------


def test_unkeyed_workspace_search_cannot_reach_a_private_row(monkeypatch, gate_private_dir):
    """The one that matters most: the search a visitor actually runs."""
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(page="workspace", query=PRIVATE_READING)
    _assert_no_private_row(app, "workspace search")


def test_unkeyed_corpus_explorer_shows_the_public_row_count(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(page="corpus")
    _assert_no_private_row(app, "corpus explorer")
    # The Source filter is drawn from the frame, so it names every source loaded.
    sources = [str(o) for box in app.selectbox for o in (box.options or [])]
    assert "StAndrews" not in sources
    import app.ui.whyptology_app as w

    public, _status = w.load_public_corpus()
    assert _corpus_total(app) == len(public)


def test_unkeyed_similar_text_page_returns_no_private_parallel(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = AppTest.from_file(APP_PATH, default_timeout=240)
        app.query_params["view"] = "similar"
        app.query_params["stage"] = "all"
        app.session_state["whyptology_similar_query"] = f"{PRIVATE_READING} nfr"
        app.session_state["whyptology_similar_tier"] = "Transliteration"
        app.run()
    assert not app.exception, app.exception
    _assert_no_private_row(app, "similar text")


def test_unkeyed_sign_readings_has_no_private_derived_reading(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(page="signs")
    _assert_no_private_row(app, "sign readings")


def test_unkeyed_footer_carries_no_nc_licence_line(monkeypatch, gate_private_dir):
    """Attribution is the mirror of the gate: the NC sentence appears exactly when NC
    rows are in this session's frame, and the pure CC BY-SA wording otherwise."""
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run()
    rendered = _rendered(app)
    assert "BY-NC-SA" not in rendered
    assert "St Andrews Corpus of Ancient Egyptian texts" not in rendered
    assert "BY-SA" in rendered, "the public CC BY-SA credit must still be shown"


# ---------- the surfaces, keyed ----------


def test_keyed_workspace_search_finds_the_private_row(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(page="workspace", query=PRIVATE_READING, keyed=True)
    rendered = _rendered(app)
    # The row, not the echoed query: its source and its text id.
    assert "StAndrews" in rendered, "a keyed session must actually get the private row"
    assert PRIVATE_TEXT_ID in rendered


def test_locking_drops_the_keyed_search_results_from_the_workspace(monkeypatch, gate_private_dir):
    """Regression (adversarial verifier, 2026-09-05): the workspace paints its last
    results from session state, so a search made while keyed kept showing the private
    row after Lock — with the NC credit line gone, because that follows the frame.
    Locking must drop every result computed on the keyed frame."""
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(page="workspace", query=PRIVATE_READING, keyed=True)
        assert "StAndrews" in _rendered(app), "precondition: the keyed search found the row"
        assert "whyptology_results" in app.session_state
        app.button(key="whyptology_reviewer_lock").click().run()
        assert not app.exception, app.exception
        assert app.session_state["whyptology_reviewer_ok"] is False
        assert "whyptology_results" not in app.session_state
        assert "whyptology_suggestions" not in app.session_state
        rendered = _rendered(app)
        assert "StAndrews" not in rendered and PRIVATE_TEXT_ID not in rendered, (
            "after Lock the workspace must not keep showing rows from the keyed frame"
        )


def test_keyed_corpus_explorer_counts_public_plus_private(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        keyed = _run(page="corpus", keyed=True)
    import app.ui.whyptology_app as w

    public, _status = w.load_public_corpus()
    assert _corpus_total(keyed) == len(public) + PRIVATE_ROW_COUNT
    sources = [str(o) for box in keyed.selectbox for o in (box.options or [])]
    assert "StAndrews" in sources


def test_keyed_similar_text_page_returns_the_private_parallel(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = AppTest.from_file(APP_PATH, default_timeout=240)
        app.query_params["view"] = "similar"
        app.query_params["stage"] = "all"
        app.session_state["whyptology_reviewer_ok"] = True
        app.session_state["whyptology_similar_query"] = f"{PRIVATE_READING} nfr"
        app.session_state["whyptology_similar_tier"] = "Transliteration"
        app.run()
    assert not app.exception, app.exception
    rendered = _rendered(app)
    assert "StAndrews" in rendered, "the keyed session's parallels must include the private row"
    assert PRIVATE_TEXT_ID in rendered


def test_keyed_sign_readings_shows_the_private_derived_reading(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(page="signs", keyed=True)
    rendered = _rendered(app)
    assert any(sign in rendered for sign in PRIVATE_SIGNS), (
        "the keyed sign index must be built from the keyed frame, so the private "
        "sign groups are among the signs it offers"
    )


def test_keyed_footer_carries_the_nc_licence_line(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = _run(keyed=True)
    rendered = _rendered(app)
    assert "BY-NC-SA" in rendered
    assert "St Andrews Corpus of Ancient Egyptian texts" in rendered
    assert "creativecommons.org/licenses/by-nc-sa/4.0" in rendered


# ---------- the key itself ----------


def test_the_passphrase_is_what_opens_and_closes_the_gate(monkeypatch, gate_private_dir):
    """Drives the real widget rather than seeding the flag: a wrong key must leave the
    session exactly as public as it was, and Lock must put it back."""
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = AppTest.from_file(APP_PATH, default_timeout=240)
        app.query_params["view"] = "corpus"
        app.query_params["stage"] = "all"
        app.run()
        assert not app.exception, app.exception
        public_total = _corpus_total(app)
        _assert_no_private_row(app, "before unlocking")

        # Wrong key: rejected, and the session stays the unkeyed one.
        app.text_input(key="whyptology_reviewer_key_input").set_value("not-the-key")
        app.button(key="whyptology_reviewer_unlock").click().run()
        assert [str(e.value) for e in app.error] == ["That key was not recognised."]
        assert "whyptology_reviewer_ok" not in app.session_state
        assert _corpus_total(app) == public_total
        _assert_no_private_row(app, "after a wrong key")

        # Right key: the session re-runs on the keyed frame.
        app.text_input(key="whyptology_reviewer_key_input").set_value(GATE_KEY)
        app.button(key="whyptology_reviewer_unlock").click().run()
        assert not app.exception, app.exception
        assert app.session_state["whyptology_reviewer_ok"] is True
        assert _corpus_total(app) == public_total + PRIVATE_ROW_COUNT

        # Lock: back to public-only, in the same session.
        app.button(key="whyptology_reviewer_lock").click().run()
        assert not app.exception, app.exception
        assert app.session_state["whyptology_reviewer_ok"] is False
        assert _corpus_total(app) == public_total
        _assert_no_private_row(app, "after locking")


def test_no_key_configured_means_the_private_rows_are_never_loaded(monkeypatch, gate_private_dir):
    """A full directory and no `REVIEWER_KEY` is the dangerous combination: the CSV is
    on the host and nothing can be presented to reach it. It must fail closed — and
    say so, or a copied-but-invisible file reads as a broken import."""
    with _host(monkeypatch, gate_private_dir, reviewer_key=None):
        app = _run(page="corpus")
        _assert_no_private_row(app, "no key configured")
        assert "`REVIEWER_KEY` is not set" in _rendered(app)

        # Not even a session that somehow carries the flag gets them: with nothing
        # configured there is no key that could have been presented.
        forced = _run(page="corpus", keyed=True)
    _assert_no_private_row(forced, "no key configured, flag forced")


def test_the_reviewer_key_never_reaches_the_url(monkeypatch, gate_private_dir):
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        app = AppTest.from_file(APP_PATH, default_timeout=240)
        app.query_params["view"] = "corpus"
        app.query_params["stage"] = "all"
        app.run()
        app.text_input(key="whyptology_reviewer_key_input").set_value(GATE_KEY)
        app.button(key="whyptology_reviewer_unlock").click().run()
        assert app.session_state["whyptology_reviewer_ok"] is True
        for name, param in app.query_params.items():
            assert GATE_KEY not in str(param), f"?{name}= carries the reviewer key"
            assert "reviewer" not in str(name).lower()


def test_a_shared_q_link_opened_in_a_fresh_session_is_public_only(monkeypatch, gate_private_dir):
    """A keyed reviewer copies the ?q= link out of their address bar. The link is the
    query and nothing else, so whoever opens it starts unkeyed and gets public rows."""
    with _host(monkeypatch, gate_private_dir, GATE_KEY):
        keyed = _run(page="workspace", query=PRIVATE_READING, keyed=True)
        assert "StAndrews" in _rendered(keyed), "precondition: the reviewer sees it"
        shared_link = dict(keyed.query_params)

        visitor = AppTest.from_file(APP_PATH, default_timeout=240)
        for name, param in shared_link.items():
            visitor.query_params[name] = param
        visitor.run()
    assert not visitor.exception, visitor.exception
    _assert_no_private_row(visitor, "a shared ?q= link in a fresh session")


# ---------- the gate's own logic, and the paths around it ----------


def test_private_rows_unlocked_is_off_by_default_and_fails_closed(monkeypatch):
    import app.ui.whyptology_app as app_module

    class _FakeStreamlit:
        def __init__(self, state):
            self.session_state = state

    # No key configured: off, whatever the session says.
    monkeypatch.setattr(app_module, "configured_reviewer_key", lambda: "")
    monkeypatch.setattr(app_module, "st", _FakeStreamlit({"whyptology_reviewer_ok": True}))
    assert app_module.private_rows_unlocked() is False

    # Key configured, nothing presented: off.
    monkeypatch.setattr(app_module, "configured_reviewer_key", lambda: "secret")
    monkeypatch.setattr(app_module, "st", _FakeStreamlit({}))
    assert app_module.private_rows_unlocked() is False

    # Key configured and presented: on.
    monkeypatch.setattr(app_module, "st", _FakeStreamlit({"whyptology_reviewer_ok": True}))
    assert app_module.private_rows_unlocked() is True

    # The key check itself blowing up must read as "public", not as "reviewer".
    def _explode():
        raise RuntimeError("secrets backend down")

    monkeypatch.setattr(app_module, "configured_reviewer_key", _explode)
    assert app_module.private_rows_unlocked() is False


def test_session_corpus_serves_public_rows_when_the_private_corpus_fails(monkeypatch):
    """A malformed private CSV costs the reviewer the private rows. It must never
    cost the app, and it must never fall through to serving them."""
    import app.ui.whyptology_app as app_module

    public = pd.DataFrame({"source": ["TLA"], "id": [1]})
    monkeypatch.setattr(app_module, "private_rows_unlocked", lambda: True)
    monkeypatch.setattr(
        app_module, "corpus_signature", lambda df: (_ for _ in ()).throw(ValueError("boom"))
    )
    pd.testing.assert_frame_equal(app_module.session_corpus(public), public)


def test_load_corpus_is_the_public_frame_for_an_unkeyed_session(private_app):
    """The public path must be exactly what it was before the gate existed: with no
    session key, `load_corpus()` is `load_public_corpus()`, row for row."""
    w, tmp_path = private_app
    pd.DataFrame([_private_row(source="StAndrews")]).to_csv(tmp_path / "s.csv", index=False)

    public, public_status = w.load_public_corpus()
    session_frame, status = w.load_corpus()

    assert status == public_status
    assert "StAndrews" not in set(public["source"])
    assert "StAndrews" not in set(session_frame["source"])
    pd.testing.assert_frame_equal(session_frame, public)
    # And the identity every downstream cache is keyed on is the public one.
    assert w.corpus_signature(session_frame) == w.corpus_signature(public)


def test_the_warm_up_is_driven_by_the_public_frame():
    """`scripts/warm_streamlit.py` opens an ordinary, unkeyed session, so the warm-up
    would build the public set anyway — but a keyed reviewer's rerun also reaches this
    line, and process-global `st.cache_resource` means one such rerun would leave the
    private resource set resident for the life of the service. The module scope must
    hand it `public_corpus`, not the session frame."""
    source = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    assert "warm_stage_resources(public_corpus)" in source
    assert "warm_stage_resources(corpus)" not in source


def test_warm_stage_resources_builds_only_the_frame_it_was_handed(monkeypatch):
    import app.ui.whyptology_app as app_module

    public = pd.DataFrame({"source": ["TLA"]})
    monkeypatch.setattr(app_module, "configured_setting", lambda *a, **k: "1")
    monkeypatch.setattr(app_module, "corpus_signature", lambda df: "public-signature")
    seen: list[tuple] = []
    monkeypatch.setattr(
        app_module,
        "load_stage_resources",
        lambda stage, signature, frame: seen.append((stage, signature, id(frame))),
    )
    app_module.warm_stage_resources(public)

    assert seen, "the warm-up did not run"
    assert {signature for _stage, signature, _frame in seen} == {"public-signature"}
    assert {frame for _stage, _signature, frame in seen} == {id(public)}


def test_load_private_corpus_is_cached_per_directory(tmp_path):
    """The cache used to have one slot for whatever directory the module pointed at,
    so changing PRIVATE_DATA_DIR silently served the previous directory's rows."""
    import app.ui.whyptology_app as app_module

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    pd.DataFrame([_private_row(source="FirstPrivate")]).to_csv(first / "a.csv", index=False)
    pd.DataFrame(
        [_private_row(source="SecondPrivate"), _private_row(source="SecondPrivate")]
    ).to_csv(second / "b.csv", index=False)

    app_module.load_private_corpus.clear()
    try:
        assert set(app_module.load_private_corpus(str(first))["source"]) == {"FirstPrivate"}
        assert set(app_module.load_private_corpus(str(second))["source"]) == {"SecondPrivate"}
        assert len(app_module.load_private_corpus(str(second))) == 2
    finally:
        app_module.load_private_corpus.clear()


def test_private_data_dir_has_files_is_only_a_report_never_a_decision():
    """It answers the operator's question ("is the CSV there?"), and must not be able
    to turn the gate on by itself."""
    import inspect

    import app.ui.whyptology_app as app_module

    assert app_module.private_data_dir_has_files() is False  # conftest pins an empty dir
    gate = inspect.getsource(app_module.private_rows_unlocked)
    assert "private_data_dir_has_files" not in gate
    assert "private_data_dir_has_files" not in inspect.getsource(app_module.session_corpus)
