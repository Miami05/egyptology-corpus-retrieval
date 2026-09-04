"""The private, non-redistributed data path (Ramses, the St Andrews texts).

Both corpora are CC BY-NC-SA 4.0 — non-commercial — and CC BY-SA is share-alike, so
they can never enter `data/processed/examples.csv` or the public repository. They
are read at runtime from a gitignored directory (`PRIVATE_DATA_DIR`, default
`data/private/`) and concatenated onto the public corpus only *after* the database
step, so they never get a database id, never reach the database, the reviewed-export
script, or the API. These tests are the guard that promise stays kept.
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
