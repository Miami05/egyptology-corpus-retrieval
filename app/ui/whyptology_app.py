from __future__ import annotations

import base64
from html import escape
from pathlib import Path
import sys
from textwrap import dedent

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.data.loader import load_examples_csv
from app.data.normalizer import contains_hieroglyphs, normalize_hieroglyphs
from app.services.annotations import save_annotation
from app.services.retrieval import log_retrieval, retrieve_top_k
from app.services.reading_model import train_reading_model
from app.services.signs import (
    build_sign_index,
    multivalence_summary,
    ranked_multivalent,
)
from app.services.suggestions import suggest_top_readings
from app.storage.bootstrap import ensure_corpus_ready
from app.storage.db import SessionLocal
from app.storage.repo import AnnotationRepo, RetrievalRunRepo
from app.ui.review_common import (
    ANNOTATION_STATUSES,
    attach_db_ids,
    build_reviewed_export_csv,
    build_row_key,
    coerce_bool,
    load_annotation_state,
    reviewed_annotation_rows,
    safe_str,
    score_breakdown_lines,
)

DATA_PATH = PROJECT_ROOT / "data/processed/examples.csv"
THEME_PATH = Path(__file__).with_name("whyptology_theme.css")
# Gentium Plus (SIL OFL), subset to the characters the corpus transliterations use.
# Rebuild with pyftsubset if the corpus gains new characters — see DEPLOYMENT.md.
FONT_PATH = Path(__file__).with_name("static") / "GentiumPlus-Translit.woff2"
# The Egyptological characters the subset above really carries out of Latin Extended-D
# and the modifier letters — aleph, ayin, yod and the modifier aleph. Kept exact on
# purpose; see translit_font_face for why a range must never over-claim.
RANGE_LIMITED_CODEPOINTS = "U+A723, U+A725, U+A7BD, U+02BE"

# The corpus explorer table is hand-rendered HTML rather than st.dataframe, so it
# needs its own paging — see render_corpus for why.
CORPUS_PAGE_SIZE = 50
CORPUS_COLUMN_LABELS = {
    "source": "Source",
    "source_text_id": "Text",
    "period": "Period",
    "language_stage": "Language stage",
    "transliteration_gold": "Reading",
    "translation": "Translation",
}


st.set_page_config(
    page_title=f"{settings.app_name} · Scholarly Egyptology",
    page_icon="𓋹",
    layout="wide",
    # "auto", not "expanded": "expanded" forces the sidebar open on every device,
    # and a 16rem sidebar on a 390px phone left ~130px for the page — the hero text
    # was clipped mid-sentence. "auto" keeps it open on desktop and collapsed on
    # narrow screens, where the ☰ button opens it as an overlay.
    initial_sidebar_state="auto",
)


@st.cache_data(show_spinner=False)
def translit_font_face() -> str:
    """Embed the transliteration font as a base64 data URI.

    Serving it from app/ui/static did not survive deployment: Streamlit Cloud gates
    /app/static/ behind the app's auth redirect, so on the private deployment the
    font request returned an HTML login page instead of a woff2 and the face failed
    to load — the Egyptological yod reverted to a tofu box in production while
    working perfectly on localhost. Embedding removes both the URL that could be
    intercepted and the reliance on a server setting Cloud does not honour.

    The subset is only ~8KB because it is cut to the 88 characters the corpus
    actually uses, so inlining it costs little per rerun. Cached so the file is read
    and encoded once per session rather than on every rerun.

    Two faces are emitted from the same bytes, because the two jobs need different
    unicode-range behaviour:

    EgyptologicalText claims everything and is set on transliteration only. A base
    letter and its combining mark must resolve to ONE font or the cluster splits, which
    is the bug that started all of this.

    EgyptologicalLatin claims four codepoints and is safe to put in front of the UI
    font, so ꜣ ꜥ ꞽ ʾ survive in text Streamlit renders itself — expander labels,
    captions, st.markdown — where the sans stack is otherwise untouched.

    It used to load a version-pinned Gentium subset from fonts.gstatic.com, and that
    URL has stopped carrying the yod: U+A7BD came back as .notdef. A unicode-range is a
    claim, not a request, so the browser did not fall back to Source Sans — it drew the
    empty box from the font that had promised the character. Sourcing both faces from
    the file in this repo removes the external dependency that broke.

    RANGE_LIMITED_CODEPOINTS must list only codepoints this subset really contains, for
    that same reason — claiming one it lacks reintroduces the box. Verified against the
    file: it has exactly ꜣ (A723), ꜥ (A725), ꞽ (A7BD) and ʾ (02BE) from those blocks,
    and no U+02BF. None of the four ever carries a combining mark in the corpus, so
    supplying them from a different font than the surrounding text cannot split a
    cluster — re-check that with the scan in DEPLOYMENT.md if the corpus grows.
    """
    encoded = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
    source = f"src:url(data:font/woff2;base64,{encoded}) format('woff2');"
    return (
        "@font-face{font-family:'EgyptologicalText';"
        f"{source}"
        "font-display:swap;}"
        "@font-face{font-family:'EgyptologicalLatin';"
        f"{source}"
        f"unicode-range:{RANGE_LIMITED_CODEPOINTS};"
        "font-display:swap;}"
    )


def inject_theme() -> None:
    # The font face is appended AFTER the stylesheet, never before: the theme starts
    # with an @import, and @import is only valid before any other rule. Prepending
    # here would silently invalidate it. @font-face has no such ordering constraint.
    st.markdown(
        f"<style>{THEME_PATH.read_text()}\n{translit_font_face()}</style>",
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def load_reading_model(corpus_signature: int):
    """Train the sign-level reading model once per corpus.

    The signature argument is the row count, so the cache invalidates when the corpus
    is reimported. Training is fast (well under a second on the full corpus) but it
    should not run on every rerun.
    """
    return train_reading_model(load_examples_csv(str(DATA_PATH)))


@st.cache_data(show_spinner="Preparing the corpus…")
def load_corpus() -> pd.DataFrame:
    # attach_db_ids adds the SQLite id per row; without it annotations cannot be
    # saved against a retrieved parallel. The database file is gitignored, so on a
    # fresh deployment ensure_corpus_ready has to build and seed it first.
    df = load_examples_csv(str(DATA_PATH))
    ensure_corpus_ready(df)
    return attach_db_ids(df)


def value(row: pd.Series, key: str, fallback: str = "—") -> str:
    raw = row.get(key, fallback)
    if raw is None or (not isinstance(raw, (list, dict)) and pd.isna(raw)):
        return fallback
    text = str(raw).strip()
    return fallback if not text or text.lower() == "nan" else text


def go_to(page: str) -> None:
    st.session_state["page"] = page


def sidebar() -> str:
    if "page" not in st.session_state:
        st.session_state["page"] = "Home"

    with st.sidebar:
        st.markdown(
            """
            <div class="brand">
              <div class="brand-row">
                <div class="brand-mark">𓋹</div>
                <div class="brand-name">WHYPTOLOGY</div>
              </div>
              <div class="brand-tag">The open platform for ancient languages</div>
            </div>
            <div class="side-label">Research</div>
            """,
            unsafe_allow_html=True,
        )
        st.button("⌂  Home", width="stretch", on_click=go_to, args=("Home",))
        st.button(
            "▤  Text workspace",
            width="stretch",
            on_click=go_to,
            args=("Workspace",),
        )
        st.button(
            "⌕  Corpus explorer",
            width="stretch",
            on_click=go_to,
            args=("Corpus",),
        )
        st.button(
            "◇  Projects",
            width="stretch",
            on_click=go_to,
            args=("Projects",),
        )
        st.button(
            "✓  Reviews",
            width="stretch",
            on_click=go_to,
            args=("Reviews",),
        )
        st.markdown('<div class="side-label">Library</div>', unsafe_allow_html=True)
        st.button(
            "𓂀  Sign readings",
            width="stretch",
            on_click=go_to,
            args=("Signs",),
        )
        st.button("◫  Dictionary", width="stretch", disabled=True)
        st.button("⌘  Sign list", width="stretch", disabled=True)
        st.button("▱  Collections", width="stretch", disabled=True)
        # CC BY-SA 4.0 requires that attribution reach the viewer of the data, not
        # just a file in the repo. Do not remove this: the corpus is not our work.
        # See DATA-LICENSE.md for the full citation and the record of modifications.
        st.markdown(
            """
            <div class="open-access-note">
              <span class="open-access-dot"></span>
              Open research access<br>
              <small>No account required</small>
            </div>
            <div class="corpus-credit">
              Corpus data: <a href="https://thesaurus-linguae-aegyptiae.de"
                 target="_blank" rel="noopener">Thesaurus Linguae Aegyptiae</a>,
              Earlier Egyptian, corpus v18, ed. Richter &amp; Werning
              (BBAW) and Fischer-Elfert &amp; Dils (SAW Leipzig).
              Licensed <a href="https://creativecommons.org/licenses/by-sa/4.0/"
                 target="_blank" rel="noopener">CC&nbsp;BY-SA&nbsp;4.0</a>.
              Adapted: normalised, re-segmented and extended with derived fields.
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state["page"]


def render_home(df: pd.DataFrame) -> None:
    # The trust row lists the corpora actually loaded. It must never name
    # institutions that have not endorsed this project.
    sources = sorted({s for s in df["source"].dropna().astype(str) if s.strip()})
    periods = df["period"].nunique() if "period" in df.columns else 0
    trust_items = "".join(
        f"<span>{escape(source)}</span>" for source in sources
    ) or "<span>No corpus loaded</span>"

    st.markdown(
        f"""
        <section class="hero">
          <div class="hero-copy">
            <div class="hero-kicker">Open research infrastructure for Egyptology</div>
            <h1>Read the past.<br>Question it together.</h1>
            <p>
              Whyptology suggests likely readings from real corpus parallels, shows the
              evidence behind each one, and records expert corrections. It is not OCR
              and not automatic translation.
            </p>
            <div class="hero-actions">
              <a class="hero-button" href="?view=workspace">Explore the workspace&nbsp; →</a>
              <a class="hero-button secondary" href="?view=corpus">Browse the corpus</a>
            </div>
          </div>
          <div class="trust-row">
            <span>Corpus loaded:</span>{trust_items}
            <span>{len(df):,} sentences</span>
            <span>{periods} periods</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-heading">
          <div><div class="eyebrow">One scholarly system</div>
          <h2>From inscription to evidence</h2></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    features = [
        (
            "01",
            "𓂀",
            "Transliteration workspace",
            "Compare sign order, readings and grammatical notes without losing the original context.",
        ),
        (
            "02",
            "⌕",
            "Corpus evidence",
            "Surface parallels from the corpus and see why each match supports a proposed reading.",
        ),
        (
            "03",
            "◇",
            "Research projects",
            "Organise texts, collections and collaborators around a shared scholarly question.",
        ),
        (
            "04",
            "✓",
            "Peer review",
            "Track proposals, discussion and validation in a transparent, citable workflow.",
        ),
    ]
    for column, (number, icon, title, copy) in zip(cols, features):
        with column:
            st.markdown(
                f"""
                <article class="feature-card">
                  <div class="feature-number">{number}</div>
                  <div class="feature-icon">{icon}</div>
                  <h3>{title}</h3><p>{copy}</p>
                </article>
                """,
                unsafe_allow_html=True,
            )

    # Every figure below is counted from the loaded corpus and the annotation
    # database, so the page cannot claim coverage the data does not have.
    annotated = len({row["example_id"] for row in reviewed_annotation_rows()})
    with_translation = int(
        df["translation"].astype(str).str.strip().ne("").sum()
        if "translation" in df.columns
        else 0
    )
    with_glossing = int(
        df["glossing"].astype(str).str.strip().ne("").sum()
        if "glossing" in df.columns
        else 0
    )
    st.markdown(
        """
        <div class="section-heading">
          <div><div class="eyebrow">Living corpus</div>
          <h2>Grounded in real sources</h2></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metrics = st.columns(4)
    for column, label, number in zip(
        metrics,
        ["Corpus sentences", "With translation", "With glossing", "Expert-reviewed"],
        [
            f"{len(df):,}",
            f"{with_translation:,}",
            f"{with_glossing:,}",
            f"{annotated:,}",
        ],
    ):
        with column:
            st.markdown(
                f'<div class="stat-card"><div class="stat-label">{label}</div>'
                f'<div class="stat-value">{number}</div></div>',
                unsafe_allow_html=True,
            )


def token_analysis(row: pd.Series) -> pd.DataFrame:
    """Word-by-word table from the TLA token-aligned fields of one corpus row."""
    readings = safe_str(row.get("transliteration_gold")).split()
    glyphs = safe_str(row.get("hieroglyphs")).split()
    lemmas = safe_str(row.get("lemma_sequence")).split()
    upos = safe_str(row.get("upos")).split()
    glossing = safe_str(row.get("glossing")).split()

    rows = []
    for index, reading in enumerate(readings):
        lemma = lemmas[index] if index < len(lemmas) else ""
        # lemma_sequence stores "id|lemma"; show the lemma and keep the id visible.
        lemma_id, _, lemma_text = lemma.partition("|")
        rows.append(
            {
                "Sign": glyphs[index] if index < len(glyphs) else "",
                "Reading": reading,
                "Lemma": lemma_text or lemma_id,
                "Lemma ID": lemma_id if lemma_text else "",
                "Part of speech": upos[index] if index < len(upos) else "",
                "Glossing": glossing[index] if index < len(glossing) else "",
            }
        )
    return pd.DataFrame(rows)


def render_suggestion_card(rank: int, suggestion) -> None:
    """One ranked reading candidate with its confidence and corpus evidence."""
    score = float(suggestion.confidence_score)
    sources = "".join(
        f"<li>{escape(str(label))}</li>" for label in suggestion.supporting_sources
    )
    st.markdown(
        dedent(
            f"""
            <article class="suggestion-card">
              <div class="suggestion-head">
                <span class="suggestion-rank">{rank}</span>
                <span class="suggestion-reading">{escape(suggestion.candidate_transliteration)}</span>
              </div>
              <div class="confidence">
                <div class="confidence-track"><div class="confidence-fill" style="width:{min(score * 100, 100):.0f}%"></div></div>
                <div class="confidence-score">{score:.3f}</div>
              </div>
              <div class="suggestion-evidence">{escape(suggestion.evidence_summary)}</div>
              <div class="suggestion-support">Supported by {suggestion.supporting_example_count}
                corpus example{"s" if suggestion.supporting_example_count != 1 else ""}</div>
              <ul class="suggestion-sources">{sources}</ul>
            </article>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def render_annotation_form(row: pd.Series, position: int) -> None:
    """Accept / edit / reject / uncertain workflow for one corpus parallel."""
    row_id = row.get("id")
    example_id = int(row_id) if pd.notna(row_id) else None
    row_key = build_row_key(row, position)
    latest, history = load_annotation_state(example_id)

    def default(field: str, row_field: str | None = None, fallback: str = "") -> str:
        if latest is not None:
            return safe_str(getattr(latest, field, "")) or fallback
        return safe_str(row.get(row_field or field, fallback))

    if latest is None:
        st.caption("No expert annotation saved yet for this example.")
    else:
        st.markdown(
            f'<div class="status-pill">●&nbsp; {escape(str(latest.status))} '
            f"· saved {escape(str(latest.created_at))}</div>",
            unsafe_allow_html=True,
        )

    status_default = safe_str(latest.status) if latest is not None else "accepted"
    status_index = (
        ANNOTATION_STATUSES.index(status_default)
        if status_default in ANNOTATION_STATUSES
        else 0
    )

    status = st.selectbox(
        "Decision",
        ANNOTATION_STATUSES,
        index=status_index,
        key=f"status_{row_key}",
        help="accepted keeps the corpus reading, edited stores your correction.",
    )
    transliteration = st.text_input(
        "Transliteration",
        value=default("transliteration", "transliteration_gold"),
        key=f"translit_{row_key}",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        display_sequence = st.text_input(
            "Display / visual sequence",
            value=default("display_sequence"),
            key=f"display_sequence_{row_key}",
        )
        normalized_reading_order = st.text_input(
            "Normalized reading order",
            value=default("normalized_reading_order"),
            key=f"reading_order_{row_key}",
        )
        alt_transliterations = st.text_input(
            "Alternate readings (pipe-separated)",
            value=default("alt_transliterations"),
            key=f"alt_{row_key}",
        )
        variant_writing_note = st.text_input(
            "Variant writing note",
            value=default("variant_writing_note"),
            key=f"variant_{row_key}",
        )
    with col_b:
        morphology_note = st.text_input(
            "Morphology note",
            value=default("morphology_note"),
            key=f"morphology_{row_key}",
        )
        syntax_note = st.text_input(
            "Syntax note",
            value=default("syntax_note"),
            key=f"syntax_{row_key}",
        )
        uncertainty_note = st.text_input(
            "Uncertainty note",
            value=safe_str(latest.uncertainty_note) if latest is not None else "",
            key=f"uncertainty_{row_key}",
        )
        grammar_note = st.text_input(
            "Grammar note",
            value=safe_str(latest.grammar_note) if latest is not None else "",
            key=f"grammar_{row_key}",
        )

    aesthetic_key = f"aesthetic_{row_key}"
    aesthetic_default = (
        bool(latest.aesthetic_arrangement_flag)
        if latest is not None
        else coerce_bool(row.get("aesthetic_arrangement_flag_bool", False))
    )
    aesthetic_flag = st.checkbox(
        "Aesthetic arrangement affects reading order",
        value=aesthetic_default,
        key=aesthetic_key,
    )

    if st.button("Save annotation", key=f"save_{row_key}", type="primary"):
        if example_id is None:
            st.error(
                "This row has no SQLite ID yet. Run "
                "`python -m scripts.import_examples` to sync the database."
            )
        else:
            session = SessionLocal()
            try:
                save_annotation(
                    repo=AnnotationRepo(session),
                    example_id=example_id,
                    transliteration=transliteration,
                    uncertainty_note=uncertainty_note or "",
                    grammar_note=grammar_note or "",
                    status=status,
                    display_sequence=display_sequence or "",
                    normalized_reading_order=normalized_reading_order or "",
                    alt_transliterations=alt_transliterations or "",
                    variant_writing_note=variant_writing_note or "",
                    morphology_note=morphology_note or "",
                    syntax_note=syntax_note or "",
                    aesthetic_arrangement_flag=coerce_bool(
                        st.session_state.get(aesthetic_key, aesthetic_flag)
                    ),
                )
            finally:
                session.close()
            # The rerun below reloads the form with the saved values as defaults, so
            # the confirmation has to survive it via session state.
            st.session_state["whyptology_saved_notice"] = (
                f"Saved “{status}” for example {example_id}."
            )
            st.rerun()

    if not history.empty:
        with st.expander(f"Annotation history ({len(history)})"):
            st.dataframe(history, hide_index=True, width="stretch")


def render_workspace(df: pd.DataFrame) -> None:
    saved_notice = st.session_state.pop("whyptology_saved_notice", None)
    if saved_notice:
        st.success(saved_notice)

    results = st.session_state.get("whyptology_results")
    suggestions = st.session_state.get("whyptology_suggestions", [])
    top_row = (
        results.iloc[0] if results is not None and not results.empty else None
    )

    if top_row is None:
        heading, meta = "Reading workspace", "Enter a reading to search the corpus"
    else:
        heading = value(top_row, "source_text_id", "Reading workspace")
        meta = " · ".join(
            part
            for part in [
                value(top_row, "language_stage", ""),
                value(top_row, "period", ""),
                value(top_row, "script_type", ""),
                value(top_row, "source", ""),
            ]
            if part and part != "—"
        )

    st.markdown(
        dedent(
            f"""
            <header class="workspace-head">
              <div>
                <div class="breadcrumbs">Workspace &nbsp;›&nbsp; Reading suggestions</div>
                <h1 class="workspace-title">{escape(heading)}</h1>
                <div class="workspace-meta">{escape(meta)}</div>
              </div>
              <div class="status-pill">●&nbsp; {len(df):,} corpus rows</div>
            </header>
            """
        ).strip(),
        unsafe_allow_html=True,
    )

    query_col, action_col = st.columns([2.2, 1])
    with query_col:
        st.markdown(
            '<div class="panel-title">Query · Transliteration, MdC or sign sequence</div>',
            unsafe_allow_html=True,
        )
        query = st.text_area(
            "Reading query",
            height=110,
            placeholder="Paste hieroglyphs (𓊵𓏙 𓇓𓏏 …) or a transliteration (htp-dji nswt)",
            label_visibility="collapsed",
        )
        reading_order = st.text_input(
            "Normalized reading order (optional)",
            placeholder="Use when the visual arrangement differs from the reading order",
        )
        # Tell the user which index the query will hit; the two are matched against
        # different columns, so silently guessing wrong looks like a broken search.
        if query.strip():
            if contains_hieroglyphs(query):
                signs = normalize_hieroglyphs(query).split()
                st.caption(
                    f"Detected **hieroglyphs** · {len(signs)} sign group"
                    f"{'s' if len(signs) != 1 else ''} · matched against the corpus "
                    "sign index"
                )
            else:
                st.caption(
                    "Detected **transliteration / MdC** · matched against the corpus "
                    "reading index"
                )
    with action_col:
        st.markdown('<div class="panel-title">&nbsp;</div>', unsafe_allow_html=True)
        search = st.button(
            f"Suggest top {settings.top_k} readings", type="primary", width="stretch"
        )
        st.caption(
            "Suggestions are grouped from real corpus parallels. Nothing is generated."
        )

    if search:
        if not query.strip():
            st.warning("Enter a transliteration, MdC string or sign sequence first.")
        else:
            with st.spinner("Searching corpus parallels…"):
                pool = retrieve_top_k(
                    df,
                    query_mdc=query,
                    query_reading_order=reading_order,
                    k=max(settings.top_k, 25),
                )
                st.session_state["whyptology_results"] = pool.head(
                    max(settings.top_k, 5)
                ).copy()
                st.session_state["whyptology_last_query"] = query
                st.session_state["whyptology_suggestions"] = suggest_top_readings(
                    pool,
                    query_mdc=query,
                    query_reading_order=reading_order,
                    top_n=3,
                )
                session = SessionLocal()
                try:
                    log_retrieval(
                        RetrievalRunRepo(session),
                        query_mdc=query,
                        query_reading_order=reading_order,
                        top_df=st.session_state["whyptology_results"],
                    )
                finally:
                    session.close()
            st.rerun()

    decode_tab, suggestions_tab, parallels_tab, analysis_tab, source_tab = st.tabs(
        [
            "Sign-by-sign reading",
            "Suggested readings",
            "Corpus parallels & review",
            "Analysis",
            "Source text",
        ]
    )

    with decode_tab:
        st.markdown(
            '<div class="panel-title">Predicted reading, sign by sign</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Each sign's reading is chosen from the readings it is actually attested "
            "with, scored by the surrounding context rather than by frequency alone. "
            "This is the multivalence step: one sign, several possible readings."
        )
        last_query = st.session_state.get("whyptology_last_query", "")
        if not last_query or not contains_hieroglyphs(last_query):
            st.info(
                "Paste hieroglyphs above and search to get a sign-by-sign reading. "
                "A transliteration query skips this step, because the reading is "
                "already given."
            )
        else:
            model = load_reading_model(len(df))
            signs = normalize_hieroglyphs(last_query).split()
            predictions = model.predict_sequence(signs)
            reading = " ".join(p.predicted for p in predictions if p.predicted)
            unseen = [p for p in predictions if not p.was_seen]
            fallbacks = [p for p in predictions if p.is_fallback]
            unreadable = [p for p in unseen if not p.is_fallback]
            ambiguous = [p for p in predictions if p.is_ambiguous]

            st.markdown(
                '<div class="suggestion-card">'
                '<div class="suggestion-head">'
                '<span class="suggestion-rank">✓</span>'
                f'<span class="suggestion-reading">{escape(reading) or "—"}</span>'
                "</div>"
                f'<div class="suggestion-support">{len(signs)} sign groups · '
                f"{len(ambiguous)} multivalent · {len(fallbacks)} inferred from a "
                f"similar sign · {len(unreadable)} unreadable</div>"
                "</div>",
                unsafe_allow_html=True,
            )

            table = pd.DataFrame(
                [
                    {
                        "Sign": p.sign,
                        "Chosen reading": p.predicted or "— unreadable —",
                        "Evidence": (
                            f"inferred from {p.fallback_from} "
                            f"({p.fallback_similarity:.0%} glyph match)"
                            if p.is_fallback
                            else f"attested {p.attested_count}×"
                            if p.was_seen
                            else "no evidence"
                        ),
                        "Multivalent": "yes" if p.is_ambiguous else "",
                        "Alternatives": ", ".join(
                            f"{r} {share:.0%}" for r, share in p.candidates[:4]
                        ),
                    }
                    for p in predictions
                ]
            )
            st.dataframe(table, hide_index=True, width="stretch")

            if fallbacks:
                st.info(
                    f"{len(fallbacks)} sign group(s) are not attested in the corpus, so "
                    "their reading was inferred from the closest attested group. Such "
                    "readings are right roughly a quarter of the time, against about "
                    "89% for attested groups — treat them as leads, not evidence."
                )
            if unreadable:
                st.warning(
                    f"{len(unreadable)} sign group(s) share too little with anything in "
                    "the corpus to support even a guess. They are reported as "
                    "unreadable rather than invented."
                )
            if ambiguous:
                st.markdown(
                    '<div class="panel-title">Where the choice actually mattered</div>',
                    unsafe_allow_html=True,
                )
                for p in ambiguous:
                    others = ", ".join(
                        f"{r} ({share:.0%})"
                        for r, share in p.candidates
                        if r != p.predicted
                    )
                    st.markdown(
                        f"- **{p.sign}** → chose `{p.predicted}` over {others or '—'}"
                    )

    with suggestions_tab:
        st.markdown(
            '<div class="panel-title">Top 3 suggested readings</div>',
            unsafe_allow_html=True,
        )
        if suggestions:
            for rank, suggestion in enumerate(suggestions, start=1):
                render_suggestion_card(rank, suggestion)
        elif results is not None:
            st.info(
                "No reading could be grouped from the current corpus. "
                "The query may be too short, or this text family is not imported yet."
            )
        else:
            st.info("Run a query to see ranked reading suggestions with evidence.")

        if results is not None and not results.empty:
            st.markdown(
                '<div class="panel-title">Evidence · Ranked corpus matches</div>',
                unsafe_allow_html=True,
            )
            show = [
                col
                for col in [
                    "source",
                    "source_text_id",
                    "period",
                    "transliteration_gold",
                    "translation",
                    "final_score",
                ]
                if col in results.columns
            ]
            table = results.loc[:, show].rename(
                columns={
                    "source": "Source",
                    "source_text_id": "Text",
                    "period": "Period",
                    "transliteration_gold": "Reading",
                    "translation": "Translation",
                    "final_score": "Match",
                }
            )
            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
                column_config={
                    "Match": st.column_config.ProgressColumn(
                        "Match", min_value=0.0, max_value=1.0, format="%.2f"
                    )
                },
            )

    with parallels_tab:
        if results is None or results.empty:
            st.info("Run a query to review the corpus parallels behind a suggestion.")
        else:
            # Deliberately does not name the engine: the deployment runs on Postgres
            # via DATABASE_URL, local development on SQLite. Saying "SQLite" here was
            # wrong in production and is exactly the kind of detail a reviewer would
            # reasonably trust.
            st.caption(
                "Each parallel can be accepted, edited, rejected or marked uncertain. "
                "Decisions are saved to the project database and appear in the "
                "reviewed export."
            )
            for position, (_, row) in enumerate(results.reset_index(drop=True).iterrows()):
                label = value(row, "transliteration_gold", "Untitled reading")
                score = row.get("final_score")
                score_text = f" · match {float(score):.2f}" if pd.notna(score) else ""
                with st.expander(
                    f"{value(row, 'source_text_id', '—')}{score_text} — {label}",
                    expanded=position == 0,
                ):
                    meta_cols = st.columns(4)
                    for column, (caption, field) in zip(
                        meta_cols,
                        [
                            ("Source", "source"),
                            ("Sentence", "source_sentence_id"),
                            ("Language stage", "language_stage"),
                            ("Script", "script_type"),
                        ],
                    ):
                        column.caption(caption)
                        column.markdown(f"**{value(row, field)}**")

                    st.markdown(f"**Reading:** {value(row, 'transliteration_gold')}")
                    st.markdown(f"**Translation:** {value(row, 'translation')}")
                    if value(row, "hieroglyphs") != "—":
                        st.markdown(
                            '<div class="hieroglyph-panel"><div class="glyph-line">'
                            f'<span class="glyphs">{escape(value(row, "hieroglyphs"))}</span>'
                            "</div></div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(f"**MdC key:** `{value(row, 'mdc')}`")
                    st.markdown(
                        f"**Normalized reading order:** {value(row, 'normalized_reading_order')}"
                    )
                    if value(row, "evidence") != "—":
                        st.markdown(f"**Evidence:** {value(row, 'evidence')}")

                    breakdown = score_breakdown_lines(row)
                    if breakdown:
                        with st.expander("Scoring breakdown"):
                            for line in breakdown:
                                st.write(line)

                    st.markdown("---")
                    render_annotation_form(row, position)

    with analysis_tab:
        if top_row is None:
            st.info("Run a query to see the word-by-word analysis of the best match.")
        else:
            st.markdown(
                '<div class="panel-title">Word-by-word · '
                f'{escape(value(top_row, "source_text_id", "best match"))}</div>',
                unsafe_allow_html=True,
            )
            analysis = token_analysis(top_row)
            if analysis.empty:
                st.info("This corpus row has no token-level annotation.")
            else:
                st.dataframe(analysis, hide_index=True, width="stretch")
                st.caption(
                    "Lemma IDs, part of speech and glossing come from the TLA import, "
                    "not from any automatic analysis."
                )

    with source_tab:
        if top_row is None:
            st.info("Run a query to inspect the underlying source record.")
        else:
            left, right = st.columns([1, 1])
            with left:
                st.markdown(
                    '<div class="panel-title">Original · Hieroglyphs</div>',
                    unsafe_allow_html=True,
                )
                glyphs = value(top_row, "hieroglyphs", "")
                if glyphs and glyphs != "—":
                    st.markdown(
                        '<div class="hieroglyph-panel"><div class="glyph-line">'
                        f'<span class="line-no">1</span><span class="glyphs">{escape(glyphs)}</span>'
                        "</div></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No hieroglyphs recorded for this row.")
                st.markdown(
                    '<div class="panel-title">Translation</div>', unsafe_allow_html=True
                )
                st.markdown(
                    f'<div class="translation-line"><span>1</span>'
                    f'<span>{escape(value(top_row, "translation", "No translation"))}</span></div>',
                    unsafe_allow_html=True,
                )
            with right:
                st.markdown(
                    '<div class="panel-title">Source record</div>',
                    unsafe_allow_html=True,
                )
                for caption, field in [
                    ("Source", "source"),
                    ("Text ID", "source_text_id"),
                    ("Sentence ID", "source_sentence_id"),
                    ("Genre", "genre"),
                    ("Period", "period"),
                    ("Reference", "source_ref"),
                ]:
                    st.caption(caption)
                    st.markdown(f"**{value(top_row, field)}**")


def render_corpus(df: pd.DataFrame) -> None:
    st.markdown(
        """
        <header class="workspace-head"><div>
          <div class="breadcrumbs">Research &nbsp;›&nbsp; Corpus</div>
          <h1 class="workspace-title">Corpus explorer</h1>
          <div class="workspace-meta">Search across texts, periods, scripts and collections</div>
        </div></header>
        """,
        unsafe_allow_html=True,
    )
    query = st.text_input(
        "Search the corpus",
        placeholder="Search a reading, translation, text ID or MdC key…",
    )

    # Only offer a filter when the corpus actually varies along that column. A
    # dropdown with a single value looks functional but filters nothing.
    filter_specs = [
        ("source", "Source", "All sources"),
        ("period", "Period", "All periods"),
        ("language_stage", "Language stage", "All language stages"),
        ("script_type", "Script type", "All script types"),
        ("genre", "Genre", "All genres"),
    ]
    usable = [
        (column, label, any_label)
        for column, label, any_label in filter_specs
        if column in df.columns
        and df[column].astype(str).str.strip().replace("", pd.NA).dropna().nunique() > 1
    ]

    selections: dict[str, tuple[str, str]] = {}
    if usable:
        for holder, (column, label, any_label) in zip(st.columns(len(usable)), usable):
            with holder:
                options = [any_label] + sorted(
                    v
                    for v in df[column].dropna().astype(str).unique().tolist()
                    if v.strip()
                )
                selections[column] = (st.selectbox(label, options), any_label)
    else:
        st.caption(
            "No filter is offered yet: every loaded row shares the same source, period, "
            "language stage, script type and genre. Import more of the corpus to unlock "
            "filtering."
        )

    filtered = df.copy()
    for column, (chosen, any_label) in selections.items():
        if chosen != any_label:
            filtered = filtered[filtered[column].astype(str) == chosen]
    if query:
        searchable = [
            col
            for col in [
                "source",
                "source_text_id",
                "mdc",
                "transliteration_gold",
                "translation",
                "deity",
                "formula_type",
            ]
            if col in filtered.columns
        ]
        mask = filtered[searchable].fillna("").astype(str).apply(
            lambda col: col.str.contains(query, case=False, regex=False)
        ).any(axis=1)
        filtered = filtered[mask]

    st.caption(f"{len(filtered):,} matching corpus records")
    columns = [
        col
        for col in [
            "source",
            "source_text_id",
            "period",
            "language_stage",
            "transliteration_gold",
            "translation",
        ]
        if col in filtered.columns
    ]
    with st.container(key="corpus_table"):
        # Deliberately NOT st.dataframe. That widget draws on a canvas via
        # glide-data-grid, which ignores CSS font-family, so the Egyptological
        # characters (ꞽ U+A7BD and the combining marks) rendered as empty boxes in
        # the one column where being able to read them is the entire point. An HTML
        # table can use the transliteration font. It also has to be paginated: the
        # canvas grid virtualised 12,772 rows for free, HTML would not.
        total = len(filtered)
        pages = max(1, (total + CORPUS_PAGE_SIZE - 1) // CORPUS_PAGE_SIZE)

        page = 1
        if pages > 1:
            # Narrow column so the stepper does not span the full table width, and a
            # visible label so it is not just a floating "1".
            picker, _ = st.columns([1, 4])
            with picker:
                page = int(
                    st.number_input(
                        f"Page (1–{pages:,})",
                        min_value=1,
                        max_value=pages,
                        value=1,
                        step=1,
                        key="corpus_page",
                    )
                )

        start = (page - 1) * CORPUS_PAGE_SIZE
        window = filtered.iloc[start : start + CORPUS_PAGE_SIZE]

        header = "".join(
            f"<th>{escape(CORPUS_COLUMN_LABELS.get(col, col))}</th>" for col in columns
        )
        body_rows = []
        for _, row in window.iterrows():
            cells = []
            for col in columns:
                cell = escape(value(row, col, "—"))
                # Only the reading column gets the transliteration font; everything
                # else stays in the interface font.
                css_class = (
                    ' class="corpus-cell-reading"'
                    if col == "transliteration_gold"
                    else ""
                )
                cells.append(f"<td{css_class}>{cell}</td>")
            body_rows.append(f"<tr>{''.join(cells)}</tr>")

        st.markdown(
            f'<div class="corpus-table-wrap"><table class="corpus-table">'
            f"<thead><tr>{header}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table></div>",
            unsafe_allow_html=True,
        )

        if total:
            first = start + 1
            last = min(start + CORPUS_PAGE_SIZE, total)
            st.caption(f"Showing {first:,}–{last:,} of {total:,} matching records.")

    with st.container(key="corpus_cards"):
        for _, row in filtered.head(30).iterrows():
            source_label = escape(value(row, "source", "Unknown source"))
            text_label = escape(value(row, "source_text_id", "Uncatalogued text"))
            period_label = escape(value(row, "period", "Period unknown"))
            language_label = escape(
                value(row, "language_stage", "Language stage unknown")
            )
            reading = escape(value(row, "transliteration_gold", "No reading"))
            translation = escape(value(row, "translation", "No translation available"))
            st.markdown(
                f"""
                <article class="corpus-card">
                  <div class="corpus-card-top">
                    <span class="corpus-source">{source_label}</span>
                    <span class="corpus-period">{period_label}</span>
                  </div>
                  <h3>{text_label}</h3>
                  <div class="corpus-language">{language_label}</div>
                  <div class="corpus-reading">{reading}</div>
                  <p>{translation}</p>
                </article>
                """,
                unsafe_allow_html=True,
            )
        if len(filtered) > 30:
            st.caption(f"Showing the first 30 of {len(filtered):,} matching records.")


def render_projects(df: pd.DataFrame) -> None:
    """Corpus composition by period, with real review progress per period.

    This replaced a set of invented sample projects. Every number here is counted
    from the loaded corpus and the annotation table, so the page reports what has
    actually been imported and reviewed.
    """
    st.markdown(
        '<div class="breadcrumbs">Workspace &nbsp;›&nbsp; Collections</div>'
        '<h1 class="workspace-title">Corpus collections</h1>'
        '<div class="workspace-meta">Grouped by attested period, with expert review'
        " progress counted from saved annotations</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    reviewed_ids = {row["example_id"] for row in reviewed_annotation_rows()}
    if "id" in df.columns:
        reviewed_mask = df["id"].isin(reviewed_ids)
    else:
        reviewed_mask = pd.Series(False, index=df.index)

    groups = (
        df.assign(_reviewed=reviewed_mask)
        .groupby("period", dropna=False)
        .agg(
            sentences=("period", "size"),
            reviewed=("_reviewed", "sum"),
            translated=(
                "translation",
                lambda col: int(col.astype(str).str.strip().ne("").sum()),
            ),
        )
        .sort_values("sentences", ascending=False)
    )

    cards = []
    for period, stats in groups.iterrows():
        sentences = int(stats["sentences"])
        reviewed = int(stats["reviewed"])
        translated = int(stats["translated"])
        pct = round(reviewed / sentences * 100) if sentences else 0
        status = "Reviewed" if reviewed else "Awaiting review"
        cards.append(
            dedent(
                f"""
            <article class="project-card">
              <div class="project-card-head">
                <span class="project-status">{escape(status)}</span>
                <span class="project-arrow">→</span>
              </div>
              <h3>{escape(str(period) or "Undated")}</h3>
              <p>{translated:,} of {sentences:,} sentences carry a translation</p>
              <div class="project-metrics">
                <div><strong>{sentences:,}</strong><span>Sentences</span></div>
                <div><strong>{reviewed:,}</strong><span>Reviewed</span></div>
              </div>
              <div class="project-progress">
                <span style="width:{pct}%"></span>
              </div>
            </article>
            """
            ).strip()
        )

    if not cards:
        st.info("No corpus rows loaded yet. Run the import scripts first.")
        return

    st.markdown(
        f'<div class="project-grid">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"{len(groups)} periods · {int(groups['sentences'].sum()):,} sentences · "
        f"{int(groups['reviewed'].sum()):,} expert-reviewed"
    )


def render_signs(df: pd.DataFrame) -> None:
    """Multivalence explorer: which readings is each sign group attested with?

    This is the view that makes the project's premise visible — a sign does not map
    to one reading, and the corpus shows which readings compete and in what contexts.
    """
    st.markdown(
        '<div class="breadcrumbs">Library &nbsp;›&nbsp; Sign readings</div>'
        '<h1 class="workspace-title">Sign readings &amp; multivalence</h1>'
        '<div class="workspace-meta">Every reading each sign group is actually attested'
        " with, counted from the corpus</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    index = build_sign_index(df)
    summary = multivalence_summary(index)
    if not index:
        st.info(
            "No sign/reading alignment available. Rows need hieroglyphs whose sign "
            "groups line up with the transliteration tokens."
        )
        return

    metric_items = list(
        zip(
        [
            "Sign groups",
            "More than one reading",
            "Not just bracketing",
            f"Both readings attested {summary['min_support']}+ times",
        ],
        [
            f"{summary['sign_groups']:,}",
            f"{summary['literal_multi']:,}",
            f"{summary['genuinely_multivalent']:,}",
            f"{summary['well_attested_multivalent']:,}",
        ],
        )
    )
    metric_cards = "".join(
        f'<div class="stat-card"><div class="stat-label">{escape(label)}</div>'
        f'<div class="stat-value">{escape(metric_value)}</div></div>'
        for label, metric_value in metric_items
    )
    st.markdown(
        f'<div class="summary-grid summary-grid-four">{metric_cards}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "The counts narrow deliberately. “More than one reading” is the raw figure. "
        "“Not just bracketing” drops editorial variants, so `n.t` and `n(.ꞽ).t` count "
        "once while `sw` (“he”) and `nswt` (“king”) count twice. The last column is the "
        "defensible one: it also requires each reading to recur, because a reading used "
        "once against a sign used hundreds of times is usually a one-off spelling or a "
        "slip in the sign/reading alignment, not an alternative a model could learn."
    )

    multivalent = ranked_multivalent(index)
    if not multivalent:
        st.warning(
            "No genuinely multivalent signs in the loaded corpus, so it cannot yet "
            "demonstrate reading disambiguation. Import more of the corpus."
        )
        return

    st.markdown("")
    st.markdown(
        '<div class="panel-title">Ambiguous signs, most attested first</div>',
        unsafe_allow_html=True,
    )
    labels = [
        f"{entry.sign}  —  {entry.distinct_count} readings, {entry.total_instances} instances"
        for entry in multivalent
    ]
    chosen = st.selectbox("Sign group", labels, label_visibility="collapsed")
    entry = multivalent[labels.index(chosen)]

    st.markdown(
        '<div class="hieroglyph-panel"><div class="glyph-line">'
        f'<span class="glyphs">{escape(entry.sign)}</span></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"**{entry.total_instances}** instances · **{entry.literal_count}** literal "
        f"readings · **{entry.distinct_count}** distinct after collapsing editorial marks"
    )

    for reading, count in entry.literal_readings.most_common():
        share = count / entry.total_instances if entry.total_instances else 0.0
        st.markdown(
            dedent(
                f"""
                <article class="suggestion-card">
                  <div class="suggestion-head">
                    <span class="suggestion-rank">{count}</span>
                    <span class="suggestion-reading">{escape(reading)}</span>
                  </div>
                  <div class="confidence">
                    <div class="confidence-track"><div class="confidence-fill" style="width:{share * 100:.0f}%"></div></div>
                    <div class="confidence-score">{share:.0%}</div>
                  </div>
                  <div class="suggestion-support">attested {count} of
                    {entry.total_instances} times</div>
                </article>
                """
            ).strip(),
            unsafe_allow_html=True,
        )
        examples = entry.examples.get(reading, [])
        if examples:
            with st.expander(f"Sentences reading it as “{reading}” ({len(examples)})"):
                st.dataframe(
                    pd.DataFrame(examples).rename(
                        columns={
                            "source_text_id": "Text",
                            "source_sentence_id": "Sentence",
                            "transliteration": "Reading",
                            "translation": "Translation",
                            "period": "Period",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                )


def render_reviews() -> None:
    st.markdown(
        '<div class="breadcrumbs">Workflow &nbsp;\u203a&nbsp; Reviews</div>'
        '<h1 class="workspace-title">Review &amp; validation</h1>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    rows = reviewed_annotation_rows()
    if not rows:
        st.info(
            "No expert annotations saved yet. Search a reading in the workspace, open a "
            "corpus parallel and accept, edit, reject or flag it as uncertain."
        )
        return

    reviewed = pd.DataFrame(rows)
    status_counts = reviewed["latest_status"].value_counts().to_dict()
    review_metric_items = [("Reviewed examples", f"{len(reviewed):,}")] + [
        (status.title(), f"{status_counts.get(status, 0):,}")
        for status in ANNOTATION_STATUSES
    ]
    review_metric_cards = "".join(
        f'<div class="stat-card"><div class="stat-label">{escape(label)}</div>'
        f'<div class="stat-value">{escape(metric_value)}</div></div>'
        for label, metric_value in review_metric_items
    )
    st.markdown(
        f'<div class="summary-grid summary-grid-five">{review_metric_cards}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("")
    left, right = st.columns([1.65, 1])

    with left:
        st.markdown(
            '<div class="panel-title">Corpus reading vs expert decision</div>',
            unsafe_allow_html=True,
        )
        status_filter = st.multiselect(
            "Filter by decision",
            ANNOTATION_STATUSES,
            default=ANNOTATION_STATUSES,
        )
        view = reviewed[reviewed["latest_status"].isin(status_filter)]
        st.caption(f"{len(view):,} of {len(reviewed):,} reviewed examples")

        for _, row in view.head(25).iterrows():
            changed = (
                str(row["latest_transliteration"]).strip()
                != str(row["transliteration_gold"]).strip()
            )
            note = " · ".join(
                part
                for part in [
                    str(row.get("latest_uncertainty_note", "")).strip(),
                    str(row.get("latest_grammar_note", "")).strip(),
                ]
                if part
            )
            st.markdown(
                dedent(
                    f"""
                    <div class="review-card">
                      <div class="review-meta">{escape(str(row["source"]))} \u00b7
                        {escape(str(row["source_text_id"]))} \u00b7
                        {escape(str(row["latest_status"]))} \u00b7
                        {escape(str(row["latest_annotation_created_at"]))}</div>
                      <div class="review-title">{escape(str(row["latest_transliteration"]))}</div>
                      <div class="review-copy">
                        {"Corpus reading: " + escape(str(row["transliteration_gold"])) if changed
                         else "Unchanged from the corpus reading."}
                      </div>
                      {f'<div class="review-copy">{escape(note)}</div>' if note else ""}
                    </div>
                    """
                ).strip(),
                unsafe_allow_html=True,
            )
        if len(view) > 25:
            st.caption(f"Showing the first 25 of {len(view):,} reviewed examples.")

    with right:
        st.markdown(
            '<div class="panel-title">Export</div>', unsafe_allow_html=True
        )
        st.caption(
            "One row per annotated example, with the base corpus fields alongside the "
            "latest expert decision."
        )
        st.download_button(
            label="Download reviewed annotations CSV",
            data=build_reviewed_export_csv(),
            file_name="reviewed_annotations_export.csv",
            mime="text/csv",
            type="primary",
            width="stretch",
        )
        st.markdown(
            '<div class="panel-title">Edited readings</div>', unsafe_allow_html=True
        )
        edited = reviewed[
            reviewed["latest_transliteration"].astype(str).str.strip()
            != reviewed["transliteration_gold"].astype(str).str.strip()
        ]
        if edited.empty:
            st.caption("No expert corrections differ from the corpus reading yet.")
        else:
            st.dataframe(
                edited.loc[
                    :,
                    [
                        "source_text_id",
                        "transliteration_gold",
                        "latest_transliteration",
                        "latest_status",
                    ],
                ].rename(
                    columns={
                        "source_text_id": "Text",
                        "transliteration_gold": "Corpus",
                        "latest_transliteration": "Expert",
                        "latest_status": "Decision",
                    }
                ),
                hide_index=True,
                width="stretch",
            )


inject_theme()
corpus = load_corpus()

query_page = st.query_params.get("view")
if query_page in {"home", "workspace", "corpus", "projects", "reviews", "signs"}:
    st.session_state["page"] = query_page.title()
    # Consume the deep link, don't let it pin the page. This block runs on every
    # rerun, so leaving ?view= in the URL would overwrite whatever the sidebar
    # buttons set and navigation would be dead for the rest of the session.
    del st.query_params["view"]

page = sidebar()
if page == "Home":
    render_home(corpus)
elif page == "Workspace":
    render_workspace(corpus)
elif page == "Corpus":
    render_corpus(corpus)
elif page == "Projects":
    render_projects(corpus)
elif page == "Signs":
    render_signs(corpus)
else:
    render_reviews()
