"""Phase 5 — licence compliance and the remaining UI paper cuts.

The licence tests are the ones that matter: CC BY-SA 4.0 §3(a) obliges attribution to
travel with every distribution of adapted material, and this repository is public.
A missing credit is not a cosmetic bug, so each obligation gets a test rather than a
comment.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from app.ui.review_common import LICENCE_NOTICE, with_licence_notice  # noqa: E402


# ---------- the licence travels with the data ----------


def test_notice_names_everything_section_3a_requires():
    """Attribution, licence, link to the original, and a statement of adaptation."""
    assert "Thesaurus Linguae Aegyptiae" in LICENCE_NOTICE
    assert "CC BY-SA 4.0" in LICENCE_NOTICE
    assert "creativecommons.org/licenses/by-sa/4.0" in LICENCE_NOTICE
    assert "thesaurus-linguae-aegyptiae.de" in LICENCE_NOTICE
    assert "Adapted" in LICENCE_NOTICE
    assert "warrant" in LICENCE_NOTICE.lower()  # §5 disclaimer pointer


def test_export_carries_the_notice_on_every_row():
    frame = pd.DataFrame(
        [
            {"transliteration_gold": "ḥtp", "translation": "Frieden"},
            {"transliteration_gold": "nswt", "translation": "König"},
        ]
    )
    out = with_licence_notice(frame)
    assert list(out["licence"]) == [LICENCE_NOTICE, LICENCE_NOTICE]
    # The original frame is untouched.
    assert "licence" not in frame.columns


def test_notice_is_a_column_so_downstream_read_csv_still_works(tmp_path):
    """A `#` comment header would silently break pandas for whoever receives the
    file; a column cannot."""
    path = tmp_path / "export.csv"
    with_licence_notice(pd.DataFrame([{"a": 1}, {"a": 2}])).to_csv(path, index=False)
    back = pd.read_csv(path)
    assert len(back) == 2
    assert back["licence"].nunique() == 1


def test_committed_export_carries_the_notice():
    """The export checked into the repository is itself a distribution."""
    path = PROJECT_ROOT / "data" / "processed" / "reviewed_annotations_export.csv"
    frame = pd.read_csv(path)
    assert "licence" in frame.columns
    assert frame["licence"].astype(str).str.contains("CC BY-SA 4.0").all()


def test_both_export_paths_use_the_same_notice():
    """The app download and the standalone script must not drift apart."""
    script = (PROJECT_ROOT / "scripts" / "export_reviewed.py").read_text()
    common = (PROJECT_ROOT / "app" / "ui" / "review_common.py").read_text()
    assert "with_licence_notice" in script
    assert "def build_reviewed_export_csv" in common
    assert "with_licence_notice" in common.split("def build_reviewed_export_csv")[1]


# ---------- attribution reaches the viewer ----------


def test_every_corpus_source_is_credited_in_the_app():
    """CC BY-SA 4.0 §3(a) attribution must reach the viewer for *every* corpus loaded,
    not only the one the project started with. Importing a new source without adding
    its citation is a licence breach, so this fails loudly when that happens."""
    import pandas as pd

    from app.ui.whyptology_app import CORPUS_CREDITS, corpus_credit_html

    corpus = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "examples.csv")
    sources = {str(s).strip() for s in corpus["source"] if str(s).strip()}
    missing = sources - set(CORPUS_CREDITS)
    assert not missing, f"corpora present but not credited in the app: {missing}"

    rendered = corpus_credit_html(corpus)
    for source in sources:
        assert source in rendered or CORPUS_CREDITS[source][:40] in rendered
    assert "CC" in rendered and "BY-SA" in rendered


def test_credit_names_both_tla_corpora_and_aes():
    from app.ui.whyptology_app import CORPUS_CREDITS

    tla = CORPUS_CREDITS["TLA"]
    assert "v18" in tla and "v19" in tla, "both TLA corpora are in use"
    aes = CORPUS_CREDITS["AES"]
    assert "AED-TEI" in aes and "Schweitzer" in aes


def test_every_page_renders_the_attribution_footer():
    """The sidebar credit is collapsed by default on a phone, so a footer carries the
    attribution on every page."""
    app_source = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    assert "def render_attribution_footer" in app_source
    # Called unconditionally at module level, after whichever page rendered.
    assert app_source.rstrip().endswith("render_attribution_footer(corpus)")
    assert "page-footer" in (PROJECT_ROOT / "app" / "ui" / "whyptology_theme.css").read_text()


def test_sidebar_attribution_is_still_present():
    """The footer supplements the sidebar credit; it does not replace it."""
    app_source = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    assert "corpus-credit" in app_source
    # Both surfaces render the same generated citation block, so assert on what a
    # viewer actually sees rather than on how many times a URL appears in the source.
    import pandas as pd

    from app.ui.whyptology_app import corpus_credit_html

    rendered = corpus_credit_html(
        pd.DataFrame({"source": ["TLA", "AES"]})
    )
    # The TLA hyperlink points at the licensed dataset publications, not the TLA
    # website (2026-09-04 licence audit: the website itself carries no CC licence
    # for its data).
    assert "huggingface.co/datasets/thesaurus-linguae-aegyptiae" in rendered
    assert "AED-TEI" in rendered


def test_data_licence_lists_every_copy_of_the_corpus():
    doc = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    for path in [
        "data/processed/examples.csv",
        "data/raw/real_examples_worklist.csv",
        "data/processed/reviewed_annotations_export.csv",
    ]:
        assert path in doc, f"{path} redistributes corpus data but is not listed"


def test_data_licence_font_filename_matches_the_file_on_disk():
    doc = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    fonts = list((PROJECT_ROOT / "app" / "ui" / "static").glob("*.woff2"))
    assert fonts, "no font file found"
    for font in fonts:
        assert font.name in doc


def test_data_licence_carries_the_warranty_disclaimer():
    doc = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    assert "as-is" in doc or "as is" in doc
    assert "legalcode" in doc


# ---------- the legacy entry point is gone ----------


@pytest.mark.parametrize(
    "path", ["app/ui/streamlit_app.py", "app/services/evaluation.py"]
)
def test_legacy_files_are_deleted(path):
    """streamlit_app.py rendered no TLA attribution at all — a second, licence-
    noncompliant entry point in a public repo. evaluation.py was its only remaining
    consumer."""
    assert not (PROJECT_ROOT / path).exists()


def test_nothing_still_imports_the_legacy_modules():
    offenders = []
    for source in list((PROJECT_ROOT / "app").rglob("*.py")) + list(
        (PROJECT_ROOT / "scripts").rglob("*.py")
    ) + list((PROJECT_ROOT / "tests").rglob("*.py")):
        text = source.read_text()
        if "streamlit_app" in text or "services.evaluation" in text:
            if source.name != "test_phase5_licence_and_polish.py":
                offenders.append(source.name)
    assert not offenders, offenders


def test_one_deployed_entry_point():
    config = (PROJECT_ROOT / ".streamlit" / "config.toml")
    readme = (PROJECT_ROOT / "README.md").read_text()
    assert "whyptology_app.py" in readme
    assert "streamlit_app.py" not in readme
    if config.exists():
        assert "streamlit_app" not in config.read_text()


# ---------- UI paper cuts ----------


def test_reading_badge_reflects_whether_groups_were_attested():
    """A tick claims every group is attested; that is false the moment a reading was
    borrowed or a group could not be read."""
    source = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    block = source.split("badge, badge_title")[0][-600:]
    assert "if unreadable:" in source
    assert "elif fallbacks:" in source
    # The unconditional tick is gone.
    assert '<span class="suggestion-rank">✓</span>' not in source


def test_corpus_explorer_does_not_render_two_different_slices():
    """The card list used to show `filtered.head(30)` — an unrelated slice from the
    table above it, so page 5 showed page 1's cards."""
    source = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    assert "filtered.head(30)" not in source
    assert "whyptology_corpus_page_rows" in source


def test_late_egyptian_corpus_is_cited():
    """The corpus now merges two TLA datasets; CC BY-SA 4.0 requires attribution for
    each, not just the one the project started with."""
    doc = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    assert "Late Egyptian" in doc
    assert "v19" in doc


def test_suffix_marker_unification_is_declared_as_a_modification():
    """Rewriting ⸗ to = changes the licensed text, so §3(a)(1)(B) requires saying so."""
    doc = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    assert "suffix-pronoun marker" in doc
    assert "⸗" in doc


# ---------- the honest messages have to be readable ----------


def test_streamlit_theme_is_pinned():
    """Without a pinned theme Streamlit colours its own components from the viewer's
    system dark/light setting, while the stylesheet paints a fixed light surface —
    which rendered every st.warning and st.info as near-white text on a pale tint."""
    config = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text()
    assert "[theme]" in config
    assert 'base = "light"' in config
    assert "textColor" in config


def test_alert_text_contrast_is_stated_explicitly():
    """Belt and braces: even if a future Streamlit default changes, the alerts that
    carry 'no attested parallel' and 'not stored durably' must stay readable."""
    css = (PROJECT_ROOT / "app" / "ui" / "whyptology_theme.css").read_text()
    assert '[data-testid="stAlert"]' in css
    alert_block = css.split('[data-testid="stAlert"]', 1)[1]
    assert "#14231f !important" in alert_block, "alert text colour not forced"
    for kind in ("warning", "info", "error", "success"):
        assert kind in alert_block, f"no explicit styling for {kind} alerts"


def test_aes_corpus_is_cited_and_its_changes_declared():
    """A third corpus with its own editors and its own transliteration convention."""
    doc = (PROJECT_ROOT / "DATA-LICENSE.md").read_text()
    assert "AES" in doc and "AED-TEI" in doc
    assert "Simon Schweitzer" in doc
    assert "fully aligned sentences were taken" in doc
    assert "disagrees on a letter in none" in doc
