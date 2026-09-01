from __future__ import annotations

import base64
import hashlib
import os
import secrets
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
from app.data.query import parse_query
from app.data.normalizer import (
    contains_hieroglyphs,
    display_sign_group,
    normalize_hieroglyphs,
    normalize_mdc,
)
from app.services.annotations import save_annotation
from app.services.retrieval import build_search_index, retrieve_top_k
from app.services.reading_model import train_reading_model
from app.services.segmentation import Segmenter, glyph_stream
from app.services.signs import (
    build_sign_index,
    multivalence_summary,
    ranked_multivalent,
)
from app.services.suggestions import suggest_top_readings
from app.storage.bootstrap import ensure_corpus_ready
from app.storage.db import IS_SQLITE, DatabaseUnavailable, SessionLocal
from app.storage.repo import AnnotationRepo
from app.ui.review_common import (
    ANNOTATION_STATUSES,
    attach_db_ids,
    build_reviewed_export_csv,
    build_row_key,
    coerce_bool,
    annotated_example_count,
    LICENCE_NOTICE,
    annotated_example_ids,
    annotation_history_to_df,
    load_annotation_state,
    load_annotation_states,
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


@st.cache_data(show_spinner=False)
def theme_css() -> str:
    """Stylesheet text, read from disk once per session rather than per rerun."""
    return THEME_PATH.read_text()


def inject_theme() -> None:
    # The font face is appended AFTER the stylesheet, never before: the theme starts
    # with an @import, and @import is only valid before any other rule. Prepending
    # here would silently invalidate it. @font-face has no such ordering constraint.
    st.markdown(
        f"<style>{theme_css()}\n{translit_font_face()}</style>",
        unsafe_allow_html=True,
    )


# One citation per corpus that can appear in `source`. CC BY-SA 4.0 §3(a) requires the
# attribution to reach whoever views the data, so every corpus actually loaded has to be
# named — not just the one the project started with. `test_every_corpus_source_is_credited`
# fails if a new source is imported without adding its citation here.
CORPUS_CREDITS: dict[str, str] = {
    "TLA": (
        '<a href="https://thesaurus-linguae-aegyptiae.de" target="_blank" '
        'rel="noopener">Thesaurus Linguae Aegyptiae</a>, Earlier Egyptian corpus v18 '
        "and Late Egyptian corpus v19, ed. Richter &amp; Werning (BBAW) and "
        "Fischer-Elfert &amp; Dils (SAW Leipzig)"
    ),
    "AES": (
        '<a href="https://github.com/simondschweitzer/aed-tei" target="_blank" '
        "rel=\"noopener\">AES — Ancient Egyptian Sentences</a>, derived from AED-TEI "
        "(S. Schweitzer and contributors, BBAW/SAW)"
    ),
}

LICENCE_LINK = (
    '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" '
    'rel="noopener">CC&nbsp;BY-SA&nbsp;4.0</a>'
)


def corpus_credit_html(df: pd.DataFrame) -> str:
    """Citations for exactly the corpora present, in a stable order."""
    sources = sorted({str(s).strip() for s in df.get("source", []) if str(s).strip()})
    cited = [CORPUS_CREDITS[s] for s in sources if s in CORPUS_CREDITS]
    if not cited:
        cited = list(CORPUS_CREDITS.values())
    return (
        "Corpus data: "
        + "; ".join(cited)
        + f". Licensed {LICENCE_LINK}. Adapted: normalised, re-segmented, "
        "transliteration conventions unified, and extended with derived fields — "
        "see DATA-LICENSE.md."
    )


def render_attribution_footer(df: pd.DataFrame | None = None) -> None:
    """Corpus credit at the foot of every page.

    The sidebar credit is the primary attribution, but the sidebar is collapsed by
    default on a phone, so a mobile visitor could read the whole corpus without ever
    seeing whose work it is. CC BY-SA 4.0 §3(a) requires the attribution to reach the
    person viewing the data. Streamlit has no footer slot, so this is called at the
    end of each page render.
    """
    body = corpus_credit_html(df if df is not None else pd.DataFrame())
    st.markdown(f'<div class="page-footer">{body}</div>', unsafe_allow_html=True)


def corpus_signature(df: pd.DataFrame) -> str:
    """Content hash of the columns the reading model trains on.

    The row count used to serve as the cache key, but a re-import with the same
    number of rows then silently kept the stale model. Hashing the sign and reading
    columns (a few ms) invalidates exactly when the training data changes.
    """
    hasher = hashlib.blake2b(digest_size=16)
    for column in ("hieroglyphs_norm", "transliteration_gold"):
        hasher.update(pd.util.hash_pandas_object(df[column], index=False).values.tobytes())
    return hasher.hexdigest()


@st.cache_resource(show_spinner=False)
def load_reading_model(signature: str, _df: pd.DataFrame):
    """Train the sign-level reading model once per corpus content.

    `_df` is the already-loaded corpus (the underscore keeps Streamlit from hashing
    it; `signature` carries the identity instead), so the CSV is not parsed a second
    time. Training is fast (well under a second on the full corpus) but it should
    not run on every rerun.
    """
    return train_reading_model(_df)


@st.cache_resource(show_spinner=False)
def load_segmenter(signature: str, _model) -> Segmenter:
    """The resegmentation lattice over the trained model's attested groups."""
    return Segmenter(_model)


def resegment_query(df: pd.DataFrame, query: str):
    """Sign groups for a pasted glyph query: the paste's spaces are hints, not truth.

    Returns (segmentation, groups_as_pasted, model, segmenter).
    """
    signature = corpus_signature(df)
    model = load_reading_model(signature, df)
    segmenter = load_segmenter(signature, model)
    as_pasted = normalize_hieroglyphs(query).split()
    return segmenter.segment(as_pasted), as_pasted, model, segmenter


@st.cache_resource(show_spinner="Preparing the corpus…")
def load_corpus_csv() -> pd.DataFrame:
    """The corpus frame, independent of any database.

    `cache_resource`, not `cache_data`: cache_data pickles a fresh 11 MB copy for
    every session that touches it (~28 MB resident each), which is the largest
    single memory cost on a 1 GB container. Nothing in the retrieval stack mutates
    this frame in place — every stage does its own `.copy()` — so one shared
    instance is safe. Anything added here must keep that true.
    """
    return load_examples_csv(str(DATA_PATH))


@st.cache_resource(show_spinner=False)
def load_corpus_with_ids(_df: pd.DataFrame, signature: str) -> pd.DataFrame:
    """The corpus with database ids attached, or the plain frame if the DB is down.

    Deliberately separate from `load_corpus_csv`. These used to be one cached
    function, so an unreachable database raised inside it at module scope and took
    down every page — including Corpus and Sign readings, which need no database.
    Splitting them means a database outage costs exactly the features that need a
    database: saving annotations and the review pages.
    """
    ensure_corpus_ready(_df)
    return attach_db_ids(_df)


def load_corpus() -> tuple[pd.DataFrame, str]:
    """(corpus frame, database status). Status is "ok" or a failure message."""
    df = load_corpus_csv()
    try:
        return load_corpus_with_ids(df, corpus_signature(df)), "ok"
    except DatabaseUnavailable as exc:
        return df, str(exc)
    except Exception as exc:  # bootstrap/driver failures land here too
        return df, str(exc)


@st.cache_resource(show_spinner=False)
def load_search_index(_df: pd.DataFrame, signature: str):
    """Query-independent search statistics, built once per corpus."""
    return build_search_index(_df)


@st.cache_resource(show_spinner=False)
def load_sign_index(_df: pd.DataFrame, signature: str):
    """Sign-to-reading index, built once per corpus.

    A full-frame `iterrows` — 0.4 s — that used to re-run on every interaction with
    the Sign readings page, including moving its own selectbox.
    """
    return build_sign_index(_df)


# Longest accepted annotation field. Every note column is unbounded TEXT, so a
# single visitor could otherwise write megabytes per save to a free-tier database.
MAX_ANNOTATION_FIELD = 2000


def configured_reviewer_key() -> str:
    """Shared reviewer passphrase, from Streamlit secrets or the environment."""
    try:
        value = st.secrets.get("reviewer_key", "")
    except Exception:
        value = ""
    return str(value or os.getenv("REVIEWER_KEY", ""))


def clip(text: object) -> str:
    """Trim a user-supplied field to the accepted maximum."""
    return str(text or "")[:MAX_ANNOTATION_FIELD]


def value(row: pd.Series, key: str, fallback: str = "—") -> str:
    raw = row.get(key, fallback)
    if raw is None or (not isinstance(raw, (list, dict)) and pd.isna(raw)):
        return fallback
    text = str(raw).strip()
    return fallback if not text or text.lower() == "nan" else text


def go_to(page: str) -> None:
    st.session_state["page"] = page


def sidebar(sidebar_df: pd.DataFrame | None = None) -> str:
    if "page" not in st.session_state:
        st.session_state["page"] = "Home"
    sidebar_df = sidebar_df if sidebar_df is not None else pd.DataFrame()

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
        # Planned pages, not built yet. The "soon" tag has to be in the label text:
        # a disabled st.button gets no distinct styling from Streamlit beyond a
        # cursor change, so without it these read as broken links to a first-time
        # visitor who clicks one and sees nothing happen.
        st.button("◫  Dictionary — soon", width="stretch", disabled=True)
        st.button("⌘  Sign list — soon", width="stretch", disabled=True)
        st.button("▱  Collections — soon", width="stretch", disabled=True)
        render_reviewer_gate()
        # CC BY-SA 4.0 requires that attribution reach the viewer of the data, not
        # just a file in the repo. Do not remove this: the corpus is not our work.
        # See DATA-LICENSE.md for the full citation and the record of modifications.
        st.markdown(
            """
            <div class="open-access-note">
              <span class="open-access-dot"></span>
              Open research access<br>
              <small>No account required to read</small>
            </div>
            <div class="corpus-credit">__CORPUS_CREDIT__</div>
            """.replace("__CORPUS_CREDIT__", corpus_credit_html(sidebar_df)),
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
    try:
        annotated = annotated_example_count()
    except DatabaseUnavailable:
        annotated = 0
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


def storage_is_ephemeral() -> bool:
    """True when saved annotations will not outlive the process.

    A SQLite file is perfectly fine locally. On a hosted platform it lives inside the
    container filesystem, which Streamlit Community Cloud recreates on every reboot
    and redeploy — so an expert's correction is accepted, shown as saved, and then
    silently lost. Nothing in the UI said so; a reviewer had no way to know their work
    was not being kept.
    """
    return IS_SQLITE


def render_storage_warning(once_key: str = "") -> None:
    """Say plainly whether corrections are being kept.

    `once_key` keeps the notice to one per page: the Workspace renders an annotation
    form per parallel, and repeating the same warning five times reads as breakage
    rather than as information.
    """
    if not storage_is_ephemeral():
        return
    if once_key:
        seen = st.session_state.setdefault("_storage_warning_shown", set())
        if once_key in seen:
            return
        seen.add(once_key)
    st.warning(
        "**Annotations are not stored durably.** This deployment is using a local "
        "SQLite file, which is recreated whenever the app restarts — corrections "
        "saved here will be lost. Point `DATABASE_URL` at a managed Postgres "
        "database to keep them.",
        icon="⚠️",
    )


def annotations_unlocked() -> bool:
    """Whether this visitor may write annotations.

    The app is public and unauthenticated, yet every visitor could insert unbounded
    rows into a free-tier database that has already had one quota outage. Streamlit
    exposes no per-visitor identity and session counters reset on refresh, so
    rate-limiting has nothing to key on; a shared reviewer passphrase is the
    mechanism that actually fits. Set `reviewer_key` in Streamlit secrets (or the
    REVIEWER_KEY environment variable) to require it. With no key configured the
    app stays open, exactly as before, so local development is unaffected.
    """
    expected = str(configured_reviewer_key() or "")
    if not expected:
        return True
    return st.session_state.get("whyptology_reviewer_ok", False)


def render_reviewer_gate() -> None:
    """Passphrase box shown once per session when a reviewer key is configured."""
    expected = str(configured_reviewer_key() or "")
    if not expected or st.session_state.get("whyptology_reviewer_ok", False):
        return
    with st.expander("Reviewer access — unlock annotation saving"):
        st.caption(
            "Reading, searching and browsing need no key. Saving annotations writes "
            "to the shared project database, so it is limited to reviewers."
        )
        entered = st.text_input(
            "Reviewer key", type="password", key="whyptology_reviewer_key_input"
        )
        if st.button("Unlock", key="whyptology_reviewer_unlock"):
            if entered and secrets.compare_digest(entered, expected):
                st.session_state["whyptology_reviewer_ok"] = True
                st.rerun()
            else:
                st.error("That key was not recognised.")


def render_annotation_form(
    row: pd.Series,
    position: int,
    states: dict | None = None,
) -> None:
    """Accept / edit / reject / uncertain workflow for one corpus parallel.

    `states` is the batch prefetched for all visible rows; without it this falls
    back to a single-row query, which is what the older UI does.
    """
    row_id = row.get("id")
    example_id = int(row_id) if pd.notna(row_id) else None
    row_key = build_row_key(row, position)
    if states is not None:
        latest, history = states.get(example_id, (None, annotation_history_to_df([])))
    else:
        try:
            latest, history = load_annotation_state(example_id)
        except DatabaseUnavailable:
            latest, history = None, annotation_history_to_df([])

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

    if not annotations_unlocked():
        st.caption("Saving is limited to reviewers — unlock it in the sidebar.")
        return

    render_storage_warning(once_key="workspace")

    if st.button("Save annotation", key=f"save_{row_key}", type="primary"):
        if example_id is None:
            st.error(
                "This row is not linked to the project database, so the annotation "
                "cannot be saved. If the database is offline, try again later."
            )
        elif not str(transliteration).strip():
            st.error("Enter a reading before saving.")
        else:
            try:
                session = SessionLocal()
                try:
                    save_annotation(
                        repo=AnnotationRepo(session),
                        example_id=example_id,
                        transliteration=clip(transliteration),
                        uncertainty_note=clip(uncertainty_note),
                        grammar_note=clip(grammar_note),
                        status=status,
                        display_sequence=clip(display_sequence),
                        normalized_reading_order=clip(normalized_reading_order),
                        alt_transliterations=clip(alt_transliterations),
                        variant_writing_note=clip(variant_writing_note),
                        morphology_note=clip(morphology_note),
                        syntax_note=clip(syntax_note),
                        aesthetic_arrangement_flag=coerce_bool(
                            st.session_state.get(aesthetic_key, aesthetic_flag)
                        ),
                    )
                finally:
                    session.close()
            except Exception as exc:
                st.error(
                    "Could not save: the project database is not reachable right "
                    "now. Your text is still in the form — try again in a moment."
                )
                st.caption(f"({type(exc).__name__})")
                return
            # The rerun below reloads the form with the saved values as defaults, so
            # the confirmation has to survive it via session state.
            st.session_state["whyptology_saved_notice"] = (
                f"Saved “{status}” for example {example_id}."
            )
            st.rerun()

    if not history.empty:
        with st.expander(f"Annotation history ({len(history)})"):
            st.dataframe(history, hide_index=True, width="stretch")


# The letters an Egyptological transliteration needs and a Latin keyboard does not
# have. `=` is here too: it separates a suffix pronoun, and on a phone it is buried
# under a symbol layer.
TRANSLITERATION_PALETTE = [
    "ꜣ", "ꜥ", "ꞽ", "ḥ", "ḫ", "ẖ", "š", "ṯ", "ḏ", "ṱ", "=",
]


# The query text the app controls, and a counter that forces the text area to take
# it. A Streamlit widget keeps its own state under its key and ignores `value=` on
# every rerun after the first, so the only reliable way to put a character *into*
# the box is to render a widget under a new key. The counter is that key.
QUERY_TEXT_KEY = "whyptology_query_text"
QUERY_NONCE_KEY = "whyptology_query_nonce"
PENDING_INSERTS_KEY = "whyptology_pending_inserts"


def query_widget_key() -> str:
    return f"whyptology_query_{st.session_state.get(QUERY_NONCE_KEY, 0)}"


def queue_palette_character(character: str) -> None:
    """Remember a tapped character; `apply_palette_inserts` puts it in the box.

    The tap is a form submit, so it arrives with whatever the user has typed. The
    character is only *queued* here because a callback cannot reliably read a form
    widget's freshly submitted value — the first attempt did, and silently dropped
    every insert. Applying it in the script body, where the submitted text is an
    ordinary variable, has no such ordering question.

    Buttons rather than `st.pills`: a single-select pill with nothing selected
    cannot be serialised by Streamlit's own AppTest harness, which took the whole
    front-end smoke suite down.
    """
    if character:
        st.session_state.setdefault(PENDING_INSERTS_KEY, []).append(character)


def apply_palette_inserts(submitted_text: str) -> bool:
    """Append any queued characters to the submitted text. True if it changed."""
    pending = st.session_state.pop(PENDING_INSERTS_KEY, [])
    if not pending:
        return False
    st.session_state[QUERY_TEXT_KEY] = submitted_text + "".join(pending)
    st.session_state[QUERY_NONCE_KEY] = st.session_state.get(QUERY_NONCE_KEY, 0) + 1
    return True


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

    # One column, not two: on a phone the old side-by-side layout pushed the search
    # button below the fold, under an optional field, so a reviewer typed a query,
    # pressed return — which does nothing in a text area — and reported that the app
    # gave no response at all.
    st.markdown(
        '<div class="panel-title">Query · Transliteration, MdC or hieroglyphs</div>',
        unsafe_allow_html=True,
    )
    # A form, and this is the fix for "it didn't give me any response". A bare
    # `st.text_area` only sends its value when it loses focus, so tapping the search
    # button did two things at once: the blur committed the text and triggered a
    # rerun, and the click that caused it was swallowed by that rerun. Verified
    # against the old build in a browser: text typed, button tapped *twice*, and the
    # suggestions panel still read "Run a query…" — the search never ran. A form
    # sends the text and the submit together, in one round trip, always.
    with st.form("whyptology_search", border=False):
        query = st.text_area(
            "Reading query",
            height=110,
            value=st.session_state.get(QUERY_TEXT_KEY, ""),
            key=query_widget_key(),
            placeholder="ꜥḥꜥ.n stẖ …  ·  aHa.n stX …  ·  htp di nsw  ·  𓊵𓏙 𓇓𓏏 …",
            label_visibility="collapsed",
        )
        # A click-to-insert row, because the alternative is switching keyboards: an
        # Egyptologist working from a phone has no ꜣ or ẖ key, which is the single
        # most common reason a transliteration gets typed in ASCII and then fails to
        # match. These are *submit* buttons, not ordinary ones: a form takes no
        # ordinary buttons, and a widget inside a form ignores session-state writes
        # from outside it — so an outside palette silently stopped appending. As
        # submitters they commit whatever is typed first, then append to it.
        with st.container(horizontal=True, key="translit_palette"):
            for character in TRANSLITERATION_PALETTE:
                st.form_submit_button(
                    character,
                    on_click=queue_palette_character,
                    args=(character,),
                    help=f"Insert {character}",
                )
        search = st.form_submit_button(
            f"Suggest top {settings.top_k} readings", type="primary", width="stretch"
        )
    # Tell the user which index the query will hit and, for transliteration, which
    # notation it was read as — the two are matched against different columns and
    # the notations fold differently, so guessing silently looks like a broken
    # search. Showing the interpretation back is what makes a misread visible.
    parse = parse_query(query, vocabulary=load_search_index(df, corpus_signature(df)).vocabulary)
    if not parse.is_empty:
        if parse.is_hieroglyphic:
            groups = parse.hieroglyphs_norm.split()
            st.caption(
                f"Detected **hieroglyphs** · {len(groups)} sign group"
                f"{'s' if len(groups) != 1 else ''} as pasted · your spaces are "
                "treated as hints: signs are regrouped against the corpus before "
                "reading, and you can correct the grouping afterwards"
            )
            if normalize_mdc(query):
                st.caption(
                    "The Latin text in this paste is ignored for matching — a "
                    "hieroglyph query is matched on signs only."
                )
        elif parse.reading and parse.notation == "mdc":
            st.caption(
                f"Read as **Manuel de Codage** → {parse.reading} · "
                f"searched as `{parse.search_key}`"
            )
        else:
            st.caption(
                f"Detected **{parse.notation_label}** · searched as `{parse.search_key}`"
            )

    with st.expander("Normalized reading order (optional)"):
        reading_order = st.text_input(
            "Normalized reading order",
            placeholder="Use when the visual arrangement differs from the reading order",
            label_visibility="collapsed",
        )
    st.caption(
        "Suggestions are grouped from real corpus parallels. Nothing is generated."
    )

    with st.expander("Which transliteration does this expect?"):
        st.markdown(
            "The corpus follows **TLA / Berlin conventions**: "
            "`ꜣ ꜥ ꞽ ḥ ḫ ẖ š q ṯ ḏ`, yod written `ꞽ`, `q` rather than `ḳ`, and suffix "
            "pronouns written as separate tokens (`ḏd =f`, not `ḏd=f`).\n\n"
            "You do not have to type it that way. All four of these are read as the "
            "same query:\n\n"
            "| You type | Notation |\n|---|---|\n"
            "| `ꜥḥꜥ.n stẖ qnd` | Unicode, TLA conventions |\n"
            "| `aHa.n stX qnd` | Manuel de Codage, as JSesh writes it |\n"
            "| `aha.n stkh qnd` | plain ASCII, no special keys |\n"
            "| `𓊢𓂝𓈖 𓋴𓏏𓅆` | Unicode hieroglyphs |\n\n"
            "Whichever you use, the caption above the results says how it was read. "
            "`=` and `.` are optional — `ḏd=f`, `ḏd =f` and `ḏdf` all match `ḏd =f`."
        )

    # A palette tap submits the form like any other button, so it lands here with
    # the typed text. Apply the insert and rerun so the box shows it; nothing is
    # searched, because the user asked for a character, not a query.
    if apply_palette_inserts(query):
        st.rerun()

    if search:
        st.session_state[QUERY_TEXT_KEY] = query
        if not query.strip():
            st.warning("Enter a transliteration, MdC string or sign sequence first.")
        else:
            with st.spinner("Searching corpus parallels…"):
                # For a glyph query, regroup the signs first so the parallels are
                # matched on corpus-style groups rather than on the paste's spacing.
                regrouped: str | None = None
                if contains_hieroglyphs(query):
                    segmentation, _, _, _ = resegment_query(df, query)
                    regrouped = " ".join(segmentation.groups)
                    st.session_state["whyptology_segments"] = segmentation.groups
                else:
                    st.session_state.pop("whyptology_segments", None)
                # Pool of 50: the evaluation scripts rank within 50, so what ships
                # must rank within the same pool or the tuned behaviour differs.
                pool = retrieve_top_k(
                    df,
                    query_mdc=query,
                    query_reading_order=reading_order,
                    k=max(settings.top_k, 50),
                    query_hieroglyphs_norm=regrouped,
                    index=load_search_index(df, corpus_signature(df)),
                )
                st.session_state["whyptology_results"] = pool.head(
                    max(settings.top_k, 5)
                ).copy()
                st.session_state["whyptology_last_query"] = query
                # The parse of the query that was actually *searched*, kept so the
                # empty state can say what was looked for even after the box has
                # been edited. `parse` above tracks the box, not the search.
                searched = parse_query(
                    query,
                    vocabulary=load_search_index(df, corpus_signature(df)).vocabulary,
                    hieroglyphs_norm=regrouped,
                )
                st.session_state["whyptology_last_parse"] = searched
                st.session_state["whyptology_suggestions"] = suggest_top_readings(
                    pool,
                    # Manuel de Codage and plain ASCII are not readings, so the
                    # suggestion layer — which compares readings as strings of
                    # sounds — is given the transliteration the query was
                    # understood as, falling back to the text as typed.
                    query_mdc=searched.reading or query,
                    query_reading_order=reading_order,
                    top_n=settings.top_k,
                    query_hieroglyphs=regrouped or "",
                )
            # No st.rerun(): rerunning doubled the cost of every search. But the
            # tabs below read `results`/`suggestions`, which were captured from
            # session state at the top of this function *before* the search wrote
            # them — so they must be refreshed here, or the tabs render the previous
            # search's state and the user has to click twice. (Found by the
            # pre-release test pass; the removed rerun had been masking this.)
            results = st.session_state.get("whyptology_results")
            suggestions = st.session_state.get("whyptology_suggestions", [])
            top_row = (
                results.iloc[0] if results is not None and not results.empty else None
            )

    # Tab order follows the query. "Sign-by-sign reading" is deliberately empty for
    # a transliteration query — there is nothing to decode when the reading is
    # already given — so leading with it showed a reviewer who had typed a
    # transliteration an empty panel, and she reported that no analysis was
    # produced. The suggestions are the answer to her query, so they come first.
    last_query = st.session_state.get("whyptology_last_query", "")
    decode_first = contains_hieroglyphs(last_query) if last_query else False
    # Kept short on purpose: at a 500px viewport the previous labels ran to 596px,
    # so "Analysis" and "Source" sat off-screen behind a horizontal scroll — the
    # same failure mode as leading with an empty tab, one scroll further along.
    tab_titles = [
        "Sign by sign",
        "Suggested readings",
        "Parallels & review",
        "Analysis",
        "Source",
    ]
    if not decode_first:
        tab_titles[0], tab_titles[1] = tab_titles[1], tab_titles[0]
    tabs = st.tabs(tab_titles)
    if decode_first:
        decode_tab, suggestions_tab = tabs[0], tabs[1]
    else:
        suggestions_tab, decode_tab = tabs[0], tabs[1]
    parallels_tab, analysis_tab, source_tab = tabs[2], tabs[3], tabs[4]

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
        # `last_query` is read once above, where it also decides the tab order.
        if not last_query or not contains_hieroglyphs(last_query):
            st.info(
                "Paste hieroglyphs above and search to get a sign-by-sign reading. "
                "A transliteration query skips this step, because the reading is "
                "already given."
            )
        else:
            segmentation, as_pasted, model, segmenter = resegment_query(df, last_query)
            suggested = " ".join(segmentation.groups)

            # --- segmentation editor -------------------------------------------
            # The lattice's grouping is a proposal. An Egyptologist must be able to
            # override it, so the groups are shown as chips and the spacing can be
            # edited directly: a space is a boundary. The widget key includes the
            # query so a new search starts from the new proposal.
            edit_key = f"whyptology_segment_edit_{hashlib.blake2b(last_query.encode(), digest_size=8).hexdigest()}"
            edited = st.text_input(
                "Sign groups — edit the spaces to split or merge groups",
                value=suggested,
                key=edit_key,
                help="One space = one group boundary. The reading below follows this grouping.",
            )
            signs = normalize_hieroglyphs(edited).split() or segmentation.groups
            chips = "".join(
                f'<span class="seg-chip{" seg-chip-unattested" if g not in segmenter.group_counts else ""}">'
                f"{escape(display_sign_group(g))}</span>"
                for g in signs
            )
            st.markdown(f'<div class="seg-chips">{chips}</div>', unsafe_allow_html=True)

            if signs == segmentation.groups and segmentation.changed_from_hints:
                parts = []
                if segmentation.crossed_hints:
                    parts.append(
                        f"merged across {len(segmentation.crossed_hints)} of your space"
                        f"{'s' if len(segmentation.crossed_hints) != 1 else ''}"
                    )
                if segmentation.inserted_boundaries:
                    parts.append(
                        f"added {len(segmentation.inserted_boundaries)} boundar"
                        f"{'ies' if len(segmentation.inserted_boundaries) != 1 else 'y'}"
                    )
                st.caption(
                    "Regrouped from your spacing (" + ", ".join(parts) + ") to match "
                    "how the corpus writes these signs. Every group shown as a chip is "
                    "attested unless marked; edit the spaces above to overrule."
                )
                # Runner-up: the reading under the user's own spacing, when its score
                # is close enough that a specialist might reasonably prefer it.
                _, hints = glyph_stream(as_pasted)
                pasted_score = segmenter.score_segmentation(as_pasted, hints)
                gap = segmentation.score - pasted_score
                if gap < 8.0:
                    pasted_reading = " ".join(
                        p.predicted or "∅" for p in model.predict_sequence(as_pasted)
                    )
                    st.caption(
                        f"Runner-up — your spacing as pasted ({gap:.1f} nats behind): "
                        f"*{escape(pasted_reading)}*"
                    )
            elif signs != segmentation.groups:
                st.caption("Using your edited grouping.")

            predictions = model.predict_sequence(signs)
            reading = " ".join(p.predicted for p in predictions if p.predicted)
            unseen = [p for p in predictions if not p.was_seen]
            fallbacks = [p for p in predictions if p.is_fallback]
            unreadable = [p for p in unseen if not p.is_fallback]
            ambiguous = [p for p in predictions if p.is_ambiguous]

            # The badge must reflect what the reading is worth: a tick claims every
            # group was attested, which is false the moment anything was borrowed or
            # could not be read at all.
            if unreadable:
                badge, badge_title = "!", "some sign groups could not be read"
            elif fallbacks:
                badge, badge_title = "~", "some readings were inferred from similar groups"
            else:
                badge, badge_title = "✓", "every sign group is attested in the corpus"
            st.markdown(
                '<div class="suggestion-card">'
                '<div class="suggestion-head">'
                f'<span class="suggestion-rank" title="{badge_title}">{badge}</span>'
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
                        "Sign": display_sign_group(p.sign),
                        "Chosen reading": p.predicted or "— unreadable —",
                        "Evidence": (
                            f"inferred from {display_sign_group(p.fallback_from)} "
                            f"({p.fallback_similarity:.0%} glyph match)"
                            if p.is_fallback
                            else f"attested {p.attested_count}×"
                            if p.was_seen
                            # Not attested and too different to borrow from: say what
                            # the corpus does hold rather than leaving a dead end.
                            else (
                                "unattested — closest attested groups: "
                                + ", ".join(
                                    f"{display_sign_group(g)} = {r} ({n}×)"
                                    for g, _, r, n in model.related_attested_groups(p.sign, limit=2)
                                )
                                if model.related_attested_groups(p.sign, limit=2)
                                else "unattested — no group in the corpus shares these signs"
                            )
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
                # Show the evidence that does exist. A reader can often recognise the
                # word from a near neighbour even when the model will not commit to
                # one, and seeing the corpus is not silent is more useful than a blank.
                for p in unreadable:
                    related = model.related_attested_groups(p.sign)
                    if not related:
                        continue
                    shown = " · ".join(
                        f"{display_sign_group(g)} = *{r}* ({n}×, {s:.0%} shared signs)"
                        for g, s, r, n in related
                    )
                    st.markdown(
                        f"- **{display_sign_group(p.sign)}** is not attested. "
                        f"Groups in the corpus sharing its signs: {shown}"
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
                        f"- **{display_sign_group(p.sign)}** → chose `{p.predicted}` over {others or '—'}"
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
            # "Nothing found" has two very different meanings and the user cannot
            # tell them apart from a blank panel: the reading may be unattested, or
            # the text may simply be outside the subset we are licensed to hold.
            # Say which, name what was searched for, and say how big the haystack is.
            searched = st.session_state.get("whyptology_last_parse")
            looked_for = ""
            if searched is not None and not searched.is_hieroglyphic:
                looked_for = (
                    f" for **{searched.reading or searched.raw}** "
                    f"(searched as `{searched.search_key}`)"
                )
            elif searched is not None:
                looked_for = f" for **{searched.hieroglyphs_norm}**"
            st.warning(
                f"No parallel in this corpus{looked_for}. Nothing here shares a sign "
                "group or a reading token with it — an honest empty result, not a "
                "weak match."
            )
            st.caption(
                f"That means it is absent from the {len(df):,} sentences this tool "
                f"holds ({', '.join(sorted(set(df['source'].astype(str))))}), which is "
                "the openly licensed part of the TLA and AES corpora — not that it is "
                "unattested in Egyptian. A text outside that subset cannot be found "
                "here however it is typed."
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
            # One query for every visible parallel's annotation state, instead of
            # one per row per rerun.
            try:
                annotation_states = load_annotation_states(
                    [
                        int(v)
                        for v in results.get("id", pd.Series(dtype=float)).tolist()
                        if pd.notna(v)
                    ]
                )
            except DatabaseUnavailable:
                annotation_states = {}
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
                    # Not "MdC key": the stored column is an ASCII fold of the
                    # reading, not Manuel de Codage, and it is empty for every AES
                    # row. What matters to a user is the key the row is *searched*
                    # under, which is what `mdc_norm` holds.
                    st.markdown(f"**Search key:** `{value(row, 'mdc_norm')}`")
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
                    render_annotation_form(row, position, annotation_states)

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
        placeholder="Search a reading (any notation), translation or text ID…",
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
        # A literal substring match over the raw columns only finds a reading typed
        # exactly as the corpus writes it — so `aha.n stkh` and `aHa.n stX` found
        # nothing here even though both name a row that exists. Matching the folded
        # key as well makes the explorer accept the same four notations the
        # workspace does.
        parse = parse_query(query, vocabulary=load_search_index(df, corpus_signature(df)).vocabulary)
        if parse.search_key and "mdc_norm" in filtered.columns:
            mask |= filtered["mdc_norm"].fillna("").astype(str).str.contains(
                parse.search_key, case=False, regex=False
            )
        if parse.hieroglyphs_norm and "hieroglyphs_norm" in filtered.columns:
            mask |= filtered["hieroglyphs_norm"].fillna("").astype(str).str.contains(
                parse.hieroglyphs_norm, regex=False
            )
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
        st.session_state["whyptology_corpus_page_rows"] = window

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

    # The card list below repeated the same rows the table above already shows. It
    # is kept only for the narrow screens where the table scrolls awkwardly, and
    # shows the current page rather than a second, unrelated slice of the corpus.
    page_rows = st.session_state.get("whyptology_corpus_page_rows")
    if page_rows is None or page_rows.empty:
        return
    with st.expander(f"Card view of this page ({len(page_rows)} records)"):
        for _, row in page_rows.iterrows():
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

    try:
        reviewed_ids = annotated_example_ids()
    except DatabaseUnavailable:
        reviewed_ids = set()
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

    index = load_sign_index(df, corpus_signature(df))
    summary = multivalence_summary(index)
    alignment = df.attrs.get("alignment")
    if alignment is not None:
        if alignment.misaligned_rows:
            st.warning(
                f"{alignment.misaligned_rows:,} of {alignment.total_rows:,} corpus rows "
                "have sign groups that do not line up with their transliteration and "
                "are excluded from these counts."
            )
        else:
            st.caption(
                f"All {alignment.total_rows:,} corpus rows are sign/reading aligned and "
                "counted here."
            )
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
        f"{display_sign_group(entry.sign)}  —  {entry.distinct_count} readings, {entry.total_instances} instances"
        for entry in multivalent
    ]
    chosen = st.selectbox("Sign group", labels, label_visibility="collapsed")
    entry = multivalent[labels.index(chosen)]

    st.markdown(
        '<div class="hieroglyph-panel"><div class="glyph-line">'
        f'<span class="glyphs">{escape(display_sign_group(entry.sign))}</span></div></div>',
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

    render_storage_warning(once_key="reviews")
    try:
        rows = reviewed_annotation_rows()
    except DatabaseUnavailable:
        st.warning(
            "The project database is not reachable, so saved reviews cannot be "
            "shown. Reading, searching and browsing the corpus still work."
        )
        return
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
        # Built from the rows already fetched above, and only when asked for:
        # `data=build_reviewed_export_csv()` re-queried the database and
        # re-materialised the whole CSV on every rerun of this page, whether or not
        # anyone ever clicked the button.
        st.caption(
            "The export carries corpus text under CC BY-SA 4.0; a licence column "
            "travels with every row so the attribution reaches whoever receives it."
        )
        if st.button("Prepare CSV export", width="stretch"):
            st.session_state["whyptology_export_csv"] = with_licence_notice(
                reviewed
            ).to_csv(index=False)
        export_csv = st.session_state.get("whyptology_export_csv")
        if export_csv:
            st.download_button(
                label="Download reviewed annotations CSV",
                data=export_csv,
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
# One notice per page per run, not one per annotation form.
st.session_state["_storage_warning_shown"] = set()
corpus, database_status = load_corpus()
if database_status != "ok":
    st.warning(
        "**Read-only mode.** The project database is not reachable, so annotations "
        "cannot be loaded or saved right now. Everything that reads the corpus — "
        "search, sign-by-sign readings, the corpus explorer and sign readings — "
        "works normally.",
        icon="⚠️",
    )

query_page = st.query_params.get("view")
if query_page in {"home", "workspace", "corpus", "projects", "reviews", "signs"}:
    st.session_state["page"] = query_page.title()
    # Consume the deep link, don't let it pin the page. This block runs on every
    # rerun, so leaving ?view= in the URL would overwrite whatever the sidebar
    # buttons set and navigation would be dead for the rest of the session.
    del st.query_params["view"]

page = sidebar(corpus)
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

# Attribution has to reach the viewer on every page, including on a phone where
# the sidebar starts collapsed.
render_attribution_footer(corpus)
