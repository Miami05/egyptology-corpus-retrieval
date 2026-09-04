from __future__ import annotations

import base64
import hashlib
import html
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
from app.data.loader import load_examples_csv, load_private_examples
from app.data.query import parse_query
from app.data.normalizer import (
    contains_hieroglyphs,
    display_sign_group,
    normalize_hieroglyphs,
    normalize_mdc,
)
from app.services.annotations import save_annotation
from app.services.retrieval import (
    build_search_index,
    resolve_auto_stage,
    retrieve_with_stage,
)
from app.services.lexicon import LEXICON_CREDIT, LEXICON_LABEL, load_lexicon
from app.services.reading_model import train_reading_model
from app.services.segmentation import Segmenter, glyph_stream
from app.services.signs import (
    build_sign_index,
    multivalence_summary,
    ranked_multivalent,
)
from app.services.stage import (
    STAGES,
    StageResources,
    build_stage_resources,
    normalize_stage,
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
# Non-commercial corpora (Ramses, the St Andrews texts) never enter examples.csv —
# CC BY-SA is share-alike and cannot carry NC material — so they live here instead:
# a gitignored directory (see .gitignore and test_private_data_dir_is_gitignored),
# loaded at runtime and concatenated onto the public corpus only after it has been
# through the database step (see load_corpus below), so they never get a database
# id, never enter the database itself, and are invisible to the exports and the API.
PRIVATE_DATA_DIR = Path(
    os.environ.get("PRIVATE_DATA_DIR") or str(PROJECT_ROOT / "data" / "private")
)
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
    # Every open source we hold translates into German. Saying so where the column
    # is labelled stops an English reader taking it for a defect.
    "translation": "Translation (German, from the corpus)",
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
    # Linked to the two licensed dataset publications (§3(a)(1)(A)(v) asks for a URI
    # to the *licensed material*), not to the TLA website — the website itself carries
    # no CC licence for its data, see DATA-LICENSE.md.
    "TLA": (
        'the <a href="https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/'
        'tla-Earlier_Egyptian_original-v18-premium" target="_blank" rel="noopener">'
        "Earlier Egyptian corpus v18</a> and "
        '<a href="https://huggingface.co/datasets/thesaurus-linguae-aegyptiae/'
        'tla-late_egyptian-v19-premium" target="_blank" rel="noopener">'
        "Late Egyptian corpus v19</a> of the Thesaurus Linguae Aegyptiae (TLA), "
        "ed. Richter &amp; Werning (BBAW) and Fischer-Elfert &amp; Dils (SAW Leipzig)"
    ),
    "AES": (
        '<a href="https://github.com/simondschweitzer/aes" target="_blank" '
        'rel="noopener">AES — Ancient Egyptian Sentences</a>, derived from '
        '<a href="https://github.com/simondschweitzer/aed-tei" target="_blank" '
        'rel="noopener">AED-TEI</a> (S. Schweitzer and contributors, BBAW/SAW)'
    ),
    "BBAW": (
        '<a href="https://huggingface.co/datasets/phiwi/bbaw_egyptian" target="_blank" '
        'rel="noopener">BBAW Egyptian corpus</a>, derived from the AED-TEI publication '
        "of the project “Strukturen und Transformationen des Wortschatzes der "
        "ägyptischen Sprache” (Berlin-Brandenburgische Akademie der Wissenschaften), "
        "January 2018 snapshot"
    ),
    # Not NC here: the rights holders (Projet Ramses / Université de Liège) granted
    # CC BY-SA 4.0 for this project's use by email 2026-09-04 — see
    # docs/permission-requests.md ("Reply from Projet Ramses, 2026-09-04") and
    # DATA-LICENSE.md. The Ramses README's own CC BY-NC-SA 4.0 terms still govern
    # everyone else. Rows are not in examples.csv yet (withheld for an unrelated
    # modelling reason), so this entry is dormant — see corpus_credit_html: a public
    # entry only renders when that source is actually present in the frame.
    "Ramses": (
        '<a href="https://doi.org/10.5281/zenodo.4954597" target="_blank" '
        'rel="noopener">the Ramses transliteration corpus V. 2019-09-01, '
        "University of Liège/Projet Ramses</a>"
    ),
}

LICENCE_LINK = (
    '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" '
    'rel="noopener">CC&nbsp;BY-SA&nbsp;4.0</a>'
)

# CC BY-SA 4.0 §3(a)(1)(A)(iv) requires a notice referring to the disclaimer of
# warranties; §5 is that disclaimer. Linked to the legal code, not the deed, because
# the deed is a summary and does not itself carry the §5 text.
WARRANTY_LINK = (
    '<a href="https://creativecommons.org/licenses/by-sa/4.0/legalcode" '
    'target="_blank" rel="noopener">CC&nbsp;BY-SA&nbsp;4.0&nbsp;§5</a>'
)

# The NC-licensed corpora (never in examples.csv — see PRIVATE_DATA_DIR above). Each
# gets its own credit line rather than being folded into the CC BY-SA sentence above,
# because that sentence is a licence claim and these rows are under a different
# licence entirely. `name` is the exact attribution string each source's licence (or,
# for St Andrews, Nederhof's permission mail) requires. `licence_url` points at the
# licence text itself (§3(a)(1)(C)); `source_url` is kept separate so the DOI / texts
# page a reader would actually want to open is not lost.
#
# Ramses used to be here too, but the rights holders (Projet Ramses / Université de
# Liège) granted CC BY-SA 4.0 for this project's use by email 2026-09-04, so it moved
# to the public CORPUS_CREDITS group above — see DATA-LICENSE.md. St Andrews has no
# such grant; it stays NC on Nederhof's permission mail alone.
PRIVATE_CORPUS_CREDITS: dict[str, dict[str, str]] = {
    "StAndrews": {
        "name": "St Andrews Corpus of Ancient Egyptian texts, Mark-Jan Nederhof",
        "source_url": "https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/",
        "licence_label": "CC&nbsp;BY-NC-SA&nbsp;4.0",
        "licence_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "changes": (
            "Hannig transliteration conventions preserved as written; provenance "
            "recorded in grammar_notes; normalised columns added"
        ),
        "note": (
            "Displayed here under its own licence for non-commercial use; the "
            "underlying files are not redistributed"
        ),
    },
}


def _private_source_credit_html(source: str) -> str:
    """One credit line for a private (non-commercial, non-redistributed) source.

    Falls back to a generic, still-non-CC-BY-SA line for a private source that has
    not been given a specific entry above yet, so a new NC corpus never silently
    inherits the public licence wording.
    """
    info = PRIVATE_CORPUS_CREDITS.get(source)
    if info is None:
        return (
            f"{escape(source)}: private, non-commercial corpus data — used "
            "locally under its own licence and not redistributed with this app."
        )
    licence = (
        f'<a href="{info["licence_url"]}" target="_blank" rel="noopener">'
        f'{info["licence_label"]}</a>'
    )
    source_link = (
        f'<a href="{info["source_url"]}" target="_blank" rel="noopener">source</a>'
    )
    return (
        f'{info["name"]} — licensed {licence} ({source_link}). Adapted: '
        f'{info["changes"]}. {info["note"]}.'
    )


def corpus_credit_html(df: pd.DataFrame) -> str:
    """Citations for exactly the corpora present, in a stable order.

    Public (CC BY-SA) sources are still folded into one sentence naming the shared
    licence. Private (NC) sources each get their own sentence, in their own licence
    — the CC BY-SA sentence must never read as if it covers them too.
    """
    sources = sorted({str(s).strip() for s in df.get("source", []) if str(s).strip()})
    public_sources = [s for s in sources if s in CORPUS_CREDITS]
    private_sources = [s for s in sources if s not in CORPUS_CREDITS]

    cited = [CORPUS_CREDITS[s] for s in public_sources]
    if not cited and not sources:
        # No frame loaded yet (e.g. an empty default): fall back to every public
        # corpus rather than showing no attribution at all.
        cited = list(CORPUS_CREDITS.values())

    parts = []
    if cited:
        credit = (
            "Corpus data: "
            + "; ".join(cited)
            + f". Licensed {LICENCE_LINK}. Adapted: Gardiner sign codes mapped to "
            "Unicode, transliteration conventions unified across sources, sign "
            "groups re-aligned to transliteration tokens, sentences deduplicated "
            "across corpora, and rows extended with derived fields — see "
            f"DATA-LICENSE.md. Provided as-is, without warranties ({WARRANTY_LINK})."
        )
        # CC BY 4.0 makes attribution a condition, and the lexicon is only in play
        # when its file shipped with this deployment.
        if len(load_sign_lexicon()):
            credit += " " + LEXICON_CREDIT
        parts.append(credit)
    parts.extend(_private_source_credit_html(source) for source in private_sources)
    return " ".join(parts)


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

    The external sign-reading lexicon is attached here so that a group this corpus
    never attests can still be read from an attested count elsewhere — labelled as
    such everywhere it appears (see app.services.lexicon).
    """
    return train_reading_model(_df, load_sign_lexicon())


@st.cache_resource(show_spinner=False)
def load_sign_lexicon():
    """The Helsinki AES+Ramses lexicon; empty (and harmless) if the file is absent."""
    return load_lexicon()


@st.cache_resource(show_spinner=False)
def load_segmenter(signature: str, _model) -> Segmenter:
    """The resegmentation lattice over the trained model's attested groups."""
    return Segmenter(_model)


def resegment_query(resources: StageResources, query: str):
    """Sign groups for a pasted glyph query: the paste's spaces are hints, not truth.

    Reads and segments with `resources.reading_model`/`resources.segmenter` rather
    than the pooled corpus, so a hieroglyph paste is read against the stage it was
    actually searched with (`resources.stage`, `None` for the pooled/"All" case).
    This is the change ROADMAP.md credits with rescuing most of the Urk. IV pastes
    that a Late-Egyptian-diluted pooled corpus otherwise mis-segments: restricting
    to one stage's own group counts fixes the sign grouping, not just which corpus
    rows get shown as parallels afterwards.

    Returns (segmentation, groups_as_pasted, model, segmenter).
    """
    model = resources.reading_model
    segmenter = resources.segmenter
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


@st.cache_resource(show_spinner=False)
def load_private_corpus() -> pd.DataFrame:
    """The private, non-redistributed corpus (Ramses, St Andrews…), if present.

    Reads only `PRIVATE_DATA_DIR`; never touches `examples.csv`, the database, the
    exports or the API. Cached like the public corpus so the CSVs are parsed once
    per process rather than on every rerun.
    """
    return load_private_examples(PRIVATE_DATA_DIR)


def _append_private_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Append the private corpus to `df`, an *already database-processed* frame.

    This must only ever be called after `ensure_corpus_ready`/`attach_db_ids` (or
    after the attempt, if the database was unreachable) has run on the public
    frame alone: `ensure_corpus_ready` is what seeds the database, so a private row
    that has not reached this function yet cannot have been written there. Private
    rows are given an explicit missing `id` — they are never linked to the
    database — which is the same state the UI already handles for any CSV row the
    database has no matching key for (see `attach_db_ids` / the "not linked to the
    project database" message in the annotation form).
    """
    private_df = load_private_corpus()
    if private_df.empty:
        return df
    private_df = private_df.copy()
    private_df["id"] = None
    return pd.concat([df, private_df], ignore_index=True, sort=False)


def load_corpus() -> tuple[pd.DataFrame, str]:
    """(corpus frame, database status). Status is "ok" or a failure message."""
    df = load_corpus_csv()
    try:
        with_ids = load_corpus_with_ids(df, corpus_signature(df))
        return _append_private_rows(with_ids), "ok"
    except DatabaseUnavailable as exc:
        return _append_private_rows(df), str(exc)
    except Exception as exc:  # bootstrap/driver failures land here too
        return _append_private_rows(df), str(exc)


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


@st.cache_resource(show_spinner=False)
def load_stage_resources(stage: str | None, signature: str, _df: pd.DataFrame) -> StageResources:
    """`StageResources` for one language stage, built lazily and cached per stage.

    Only the stage actually requested is ever built, and each is cached once — the
    UI must never build all of `STAGES` up front (ROADMAP.md, "Item A core landed
    2026-09-04": all four cached at once measured ~1.9 GB at 131k rows).

    `stage=None` (the pooled corpus, i.e. "All (no stage)") is special-cased to wrap
    the app's OWN pooled loaders — `load_search_index`, `load_reading_model`,
    `load_segmenter`, `load_sign_index`, every one of them already `st.cache_resource`
    — instead of calling `build_stage_resources`. `build_stage_resources(df, None,
    ...)` would reproduce the pooled behaviour exactly (its own docstring says so:
    `compatible_frame(df, None)` is `df` itself) but as brand-new objects, doubling
    memory for the pooled path even though nothing about it differs. Routing
    `stage=None` through the existing pooled loaders instead means a visitor who
    never touches the stage selectbox costs no more memory than before this feature
    existed — see `test_load_stage_resources_pooled_reuses_the_pooled_loaders` for
    the object-identity guarantee this relies on.

    A concrete stage has no pooled equivalent to reuse, so it goes through
    `build_stage_resources`, with the same lexicon the pooled reading model already
    uses (`load_sign_lexicon`) and `build_stage_resources`'s own default
    segmentation weights — which are exactly `load_segmenter`'s defaults too
    (`DEFAULT_SEGMENTATION_WEIGHTS`, `use_lexicon=True`), so a stage's resources
    differ from the pooled ones only in which rows they were built from.
    """
    if stage is None:
        reading_model = load_reading_model(signature, _df)
        return StageResources(
            stage=None,
            frame=_df,
            index=load_search_index(_df, signature),
            reading_model=reading_model,
            segmenter=load_segmenter(signature, reading_model),
            sign_index=load_sign_index(_df, signature),
        )
    return build_stage_resources(_df, stage, lexicon=load_sign_lexicon())


# Longest accepted annotation field. Every note column is unbounded TEXT, so a
# single visitor could otherwise write megabytes per save to a free-tier database.
MAX_ANNOTATION_FIELD = 2000


def configured_setting(secret_name: str, env_name: str, default: str = "") -> str:
    """One deployment setting, from Streamlit secrets first, then the environment.

    Streamlit Cloud carries settings in `st.secrets`; the systemd service on the
    server carries them in an EnvironmentFile. Reading both here keeps every
    deployment knob (reviewer key, durable-storage flag, default stage, moved-to
    banner) on one code path.
    """
    try:
        value = st.secrets.get(secret_name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(env_name, "") or default)


def configured_reviewer_key() -> str:
    """Shared reviewer passphrase, from Streamlit secrets or the environment."""
    return configured_setting("reviewer_key", "REVIEWER_KEY")


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

    On a machine with a real disk (the home/friend server runs the app from a
    checkout under systemd), the SQLite file persists across restarts, so the
    deployment declares that with `annotations_durable = "1"` / `ANNOTATIONS_DURABLE=1`
    and the warning and the read-only gating switch off. The flag is a statement
    about the host, so it is set per deployment, never in code.
    """
    if configured_setting("annotations_durable", "ANNOTATIONS_DURABLE").strip().lower() in {"1", "true", "yes"}:
        return False
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
    # When storage is a container-local file, a saved correction is accepted, shown
    # as saved and lost at the next restart. Rather than pretend, the form goes
    # read-only: every control is disabled and the reason is stated once per page.
    ephemeral = storage_is_ephemeral()
    if ephemeral:
        seen = st.session_state.setdefault("_storage_warning_shown", set())
        if "annotation-readonly" not in seen:
            seen.add("annotation-readonly")
            st.warning(
                "**Corrections cannot be stored on this deployment.** The database "
                "is a local file that is recreated on every restart, so anything "
                "saved here would be lost; the form is read-only until a managed "
                "database is configured. Searching and browsing are unaffected.",
                icon="⚠️",
            )
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
        disabled=ephemeral,
    )
    transliteration = st.text_input(
        "Transliteration",
        value=default("transliteration", "transliteration_gold"),
        key=f"translit_{row_key}",
        disabled=ephemeral,
    )
    col_a, col_b = st.columns(2)
    with col_a:
        display_sequence = st.text_input(
            "Display / visual sequence",
            value=default("display_sequence"),
            key=f"display_sequence_{row_key}",
            disabled=ephemeral,
        )
        normalized_reading_order = st.text_input(
            "Normalized reading order",
            value=default("normalized_reading_order"),
            key=f"reading_order_{row_key}",
            disabled=ephemeral,
        )
        alt_transliterations = st.text_input(
            "Alternate readings (pipe-separated)",
            value=default("alt_transliterations"),
            key=f"alt_{row_key}",
            disabled=ephemeral,
        )
        variant_writing_note = st.text_input(
            "Variant writing note",
            value=default("variant_writing_note"),
            key=f"variant_{row_key}",
            disabled=ephemeral,
        )
    with col_b:
        morphology_note = st.text_input(
            "Morphology note",
            value=default("morphology_note"),
            key=f"morphology_{row_key}",
            disabled=ephemeral,
        )
        syntax_note = st.text_input(
            "Syntax note",
            value=default("syntax_note"),
            key=f"syntax_{row_key}",
            disabled=ephemeral,
        )
        uncertainty_note = st.text_input(
            "Uncertainty note",
            value=safe_str(latest.uncertainty_note) if latest is not None else "",
            key=f"uncertainty_{row_key}",
            disabled=ephemeral,
        )
        grammar_note = st.text_input(
            "Grammar note",
            value=safe_str(latest.grammar_note) if latest is not None else "",
            key=f"grammar_{row_key}",
            disabled=ephemeral,
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
        disabled=ephemeral,
    )

    if not annotations_unlocked():
        st.caption("Saving is limited to reviewers — unlock it in the sidebar.")
        return

    render_storage_warning(once_key="workspace")

    if st.button(
        "Save annotation",
        key=f"save_{row_key}",
        type="primary",
        disabled=ephemeral,
        help=(
            "Disabled: this deployment cannot keep corrections."
            if ephemeral
            else None
        ),
    ):
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
    "ꜣ", "ꜥ", "ꞽ", "ḥ", "ḫ", "ẖ", "š", "ṯ", "ḏ",
]
# `ṱ` (516 rows) and `=` were dropped: `=` is folded away, so typing it changes no
# result, and nine keys fit one row on a phone where eleven wrapped.

# One example per notation the parser accepts. A first-time visitor faces an empty
# box and guesses — the expert who reported "found nothing" had guessed a notation we
# mishandled. One click shows what the tool takes and what it gives back.
EXAMPLE_QUERIES: list[tuple[str, str]] = [
    ("ꜥḥꜥ.n stẖ ḥr ḏd n =f", "Unicode transliteration"),
    ("aHa.n stX Hr Dd", "Manuel de Codage"),
    ("𓊵𓏙 𓇓𓏏", "Hieroglyphs"),
]


# The query text the app controls, and a counter that forces the text area to take
# it. A Streamlit widget keeps its own state under its key and ignores `value=` on
# every rerun after the first, so the only reliable way to put a character *into*
# the box is to render a widget under a new key. The counter is that key.
QUERY_TEXT_KEY = "whyptology_query_text"
QUERY_NONCE_KEY = "whyptology_query_nonce"
PENDING_INSERTS_KEY = "whyptology_pending_inserts"
# An example button or a ?q= link wants two things a form submit cannot do at once:
# put text in the box *and* search it. They queue the text here; the script body
# swaps it in under a new widget key and sets AUTO_SEARCH_KEY, and the next run
# searches exactly what the box now shows.
PENDING_EXAMPLE_KEY = "whyptology_pending_example"
AUTO_SEARCH_KEY = "whyptology_auto_search"
# ?q= is consumed once per session. Without this guard the parameter — which is
# deliberately left in the URL so the link stays shareable — would re-run the same
# search on every rerun and the user could never type anything else.
QUERY_PARAM_CONSUMED_KEY = "whyptology_q_param_consumed"


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


def queue_example_query(text: str) -> None:
    """Callback for an example button: remember the text, apply it in the body."""
    if text:
        st.session_state[PENDING_EXAMPLE_KEY] = text


def set_query_and_search(text: str) -> None:
    """Put `text` in the box under a fresh widget key and search it on the next run."""
    st.session_state[QUERY_TEXT_KEY] = text
    st.session_state[QUERY_NONCE_KEY] = st.session_state.get(QUERY_NONCE_KEY, 0) + 1
    st.session_state[AUTO_SEARCH_KEY] = True


def consume_query_param() -> bool:
    """Load a shared ?q= link once: fill the box and arm a search. True if it did."""
    if st.session_state.get(QUERY_PARAM_CONSUMED_KEY):
        return False
    shared = st.query_params.get("q")
    st.session_state[QUERY_PARAM_CONSUMED_KEY] = True
    if not shared or not str(shared).strip():
        return False
    set_query_and_search(str(shared))
    return True


# ---------------------------------------------------------------------------
# Language stage (item A, UI half)
#
# The internal stage value has three shapes: "auto" (infer per query), None (no
# restriction — search the pooled corpus, "All (no stage)" in the selectbox), or one
# of STAGES ("Earlier Egyptian" / "Late Egyptian" / "Demotic", a declared stage).
# The selectbox shows a fourth, human string ("Auto") for the first of these; the
# ?stage= link uses a fifth, url-safe one ("auto"/"all"/the stage name) so the
# param never collides with the empty string a missing param already means.
# ---------------------------------------------------------------------------

STAGE_STATE_KEY = "whyptology_stage"
STAGE_SELECT_WIDGET_KEY = "whyptology_stage_select"
STAGE_AUTO_LABEL = "Auto"
STAGE_ALL_LABEL = "All (no stage)"
STAGE_DISPLAY_OPTIONS: list[str] = [STAGE_AUTO_LABEL, *STAGES, STAGE_ALL_LABEL]


def stage_display_to_internal(display: str) -> str | None:
    """Selectbox label -> internal stage value ("auto" | None | a STAGES member)."""
    if display == STAGE_ALL_LABEL:
        return None
    if display == STAGE_AUTO_LABEL:
        return "auto"
    return display


def stage_internal_to_display(stage: str | None) -> str:
    """Internal stage value -> selectbox label. Inverse of stage_display_to_internal."""
    if stage is None:
        return STAGE_ALL_LABEL
    if stage == "auto":
        return STAGE_AUTO_LABEL
    return stage


def stage_internal_to_param(stage: str | None) -> str:
    """Internal stage value -> ?stage= text. "all" stands in for None: an empty
    string is indistinguishable from a missing parameter, so None cannot round-trip
    as itself."""
    return "all" if stage is None else stage


def stage_param_to_internal(param: str | None) -> str | None:
    """?stage= text -> internal stage value. Anything unrecognised (missing,
    empty, or not one of "auto"/"all"/a STAGES member — a hand-edited or stale
    link) defaults to "auto" rather than silently restricting the search."""
    if param == "all":
        return None
    if param in STAGES:
        return param
    return configured_default_stage()


def configured_default_stage() -> str | None:
    """The stage a fresh session starts in: "auto" unless the deployment says
    otherwise (`default_stage` secret / `DEFAULT_STAGE` env: "auto", "all" or a
    stage name).

    Auto builds a second set of resources for the inferred stage, ~400 MB at 78k
    rows — fine on the server, but over the limit on Streamlit Community Cloud's
    1 GB, so that deployment is set to "all" until it is retired.
    """
    value = configured_setting("default_stage", "DEFAULT_STAGE", "auto").strip()
    if value == "all":
        return None
    if value in STAGES:
        return value
    return "auto"


def init_stage_state() -> None:
    """Seed the stage from ?stage= the first time this session sees it.

    Mirrors `consume_query_param`'s "once per session" guard, but the stage is not
    *cleared* from the URL the way ?q= is: a shared link should keep restricting the
    search to the stage it names for as long as the tab is open, exactly like the
    selectbox itself would once the visitor touched it.
    """
    if STAGE_STATE_KEY not in st.session_state:
        st.session_state[STAGE_STATE_KEY] = stage_param_to_internal(
            st.query_params.get("stage")
        )


def resolve_ui_stage(
    selected: str | None,
    query: str,
    get_resources,
) -> tuple[str | None, bool]:
    """Which stage to search and read the query with, and whether it was inferred.

    Declared ("Earlier Egyptian" etc.) and "All" (None) need no first pass: the
    caller already knows which resources to use. "auto" delegates to
    `app.services.retrieval.resolve_auto_stage` — the one shared implementation
    `scripts/run_expert_paste_eval.py`'s `resolve_stage` also calls (previously
    each duplicated this). That function resolves a hieroglyph paste by per-stage
    *reading* likelihood (`app.services.stage.choose_stage_by_likelihood`: one
    pooled segmentation, then each stage's own reading model scores it — no
    first retrieval pass needed, since a paste has no reading of its own to
    match rows against) and a text query by the original label-based first pass
    + `infer_stage` rule, exactly what `retrieve_with_stage`'s own "auto" branch
    now also uses. This is called directly here rather than via
    `retrieve_with_stage(stage="auto", ...)` because this function's caller still
    needs the resolved stage on its own, to read/resegment the query with that
    stage's resources afterwards (see `resegment_query`) before the actual
    search runs.
    """
    if selected != "auto":
        return selected, False
    stage, inferred, _likelihood_scores = resolve_auto_stage(query, get_resources)
    return stage, inferred


def stage_caption(requested: str | None, stage_used: str | None, inferred: bool) -> str | None:
    """The one-line caption shown under the results, or None to show nothing.

    A pure function so the four states are unit-testable without a live session:
    `requested` is what the selectbox asked for ("auto" | None | a STAGES member —
    i.e. `st.session_state[STAGE_STATE_KEY]` at search time); `stage_used` and
    `inferred` come from resolving that request (`resolve_ui_stage`, or the matching
    fields on a `StageRetrievalResult`). `requested` has to be passed separately
    from a `StageRetrievalResult`: `stage_used=None, inferred=False` is what BOTH
    "All (no stage)" and "auto found nothing" look like from the result alone, and
    the two need different captions.
    """
    if requested is None:
        return None
    if requested == "auto":
        if inferred and stage_used:
            return f"Stage inferred: {stage_used} — change"
        return "No stage could be inferred; showing all stages."
    return f"Restricted to {requested} and rows without a stage label."


def evidence_stage_label(raw_stage: object) -> str:
    """A corpus row's `language_stage` -> the label shown next to its source.

    Normalises through `app.services.stage.normalize_stage`, so `Unspecified
    (AES)`, `Unspecified (BBAW)`, a blank cell and an unrecognised value all read
    the same, honest way: the corpus does not record a stage for this row, rather
    than repeating the raw import-specific placeholder text.
    """
    normalized = normalize_stage(raw_stage)
    return normalized if normalized is not None else "stage not recorded"


def render_workspace(df: pd.DataFrame) -> None:
    saved_notice = st.session_state.pop("whyptology_saved_notice", None)
    if saved_notice:
        st.success(saved_notice)

    results = st.session_state.get("whyptology_results")
    suggestions = st.session_state.get("whyptology_suggestions", [])
    top_row = (
        results.iloc[0] if results is not None and not results.empty else None
    )

    # The header is painted into a placeholder *after* the search block below. It
    # used to be rendered here, from session state as it stood before the search
    # ran, so the title kept naming the previous query's text until the next
    # interaction — a search returned results under a heading that still said
    # "Enter a reading to search the corpus".
    header_slot = st.empty()

    def paint_header(current_top_row) -> None:
        if current_top_row is None:
            heading, meta = "Reading workspace", "Enter a reading to search the corpus"
        else:
            heading = value(current_top_row, "source_text_id", "Reading workspace")
            meta = " · ".join(
                part
                for part in [
                    # Normalised, not the raw cell: `Unspecified (AES)` etc. would
                    # otherwise leak into this quiet meta line. An unrecorded stage
                    # is dropped from the line entirely (the "if part" filter
                    # below), same as any other empty field here.
                    normalize_stage(current_top_row.get("language_stage")) or "",
                    value(current_top_row, "period", ""),
                    value(current_top_row, "script_type", ""),
                    value(current_top_row, "source", ""),
                ]
                if part and part != "—"
            )
        header_slot.markdown(
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

    # A shared link (?q=…) fills the box and arms a search — once per session, so
    # the parameter can stay in the URL without pinning the query.
    consume_query_param()

    # Resolves a stage (or None, the pooled corpus) to its StageResources, built
    # lazily and cached per (stage, corpus signature) — see load_stage_resources.
    # Recreated every rerun, but it is a thin closure; the caching lives in
    # load_stage_resources itself, keyed on its own arguments.
    signature = corpus_signature(df)

    def get_resources(stage: str | None) -> StageResources:
        return load_stage_resources(stage, signature, df)

    init_stage_state()
    st.markdown('<div class="panel-title">Language stage</div>', unsafe_allow_html=True)
    chosen_display = st.selectbox(
        "Language stage",
        STAGE_DISPLAY_OPTIONS,
        index=STAGE_DISPLAY_OPTIONS.index(
            stage_internal_to_display(st.session_state[STAGE_STATE_KEY])
        ),
        key=STAGE_SELECT_WIDGET_KEY,
        label_visibility="collapsed",
        help=(
            "Auto infers the stage from the first pass of results. A declared "
            "stage restricts evidence to that stage plus rows with no stage "
            "recorded. All searches the whole corpus, unrestricted."
        ),
    )
    st.session_state[STAGE_STATE_KEY] = stage_display_to_internal(chosen_display)

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
        # Worked examples, one per notation. Also submit buttons (a form takes no
        # other kind); they queue the text and the body swaps it in and searches.
        st.caption("Try an example:")
        with st.container(horizontal=True, key="example_queries"):
            for example_text, example_label in EXAMPLE_QUERIES:
                st.form_submit_button(
                    example_text,
                    on_click=queue_example_query,
                    args=(example_text,),
                    help=example_label,
                )
        # A click-to-insert row, because the alternative is switching keyboards: an
        # Egyptologist working from a phone has no ꜣ or ẖ key, which is the single
        # most common reason a transliteration gets typed in ASCII and then fails to
        # match. These are *submit* buttons, not ordinary ones: a form takes no
        # ordinary buttons, and a widget inside a form ignores session-state writes
        # from outside it — so an outside palette silently stopped appending. As
        # submitters they commit whatever is typed first, then append to it.
        st.caption("No ꜣ on your keyboard? Tap to insert.")
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
    # An example button works the same way as a palette key, but replaces the text
    # and arms a search; the next run finds AUTO_SEARCH_KEY set and searches what
    # the box then shows.
    pending_example = st.session_state.pop(PENDING_EXAMPLE_KEY, None)
    if pending_example:
        set_query_and_search(pending_example)
        st.rerun()

    run_search = bool(search) or bool(st.session_state.pop(AUTO_SEARCH_KEY, False))
    if run_search:
        st.session_state[QUERY_TEXT_KEY] = query
        if not query.strip():
            st.warning("Enter a transliteration, MdC string or sign sequence first.")
        else:
            with st.spinner("Searching corpus parallels…"):
                # Which stage to search and read with (item A). "auto" runs its
                # own first pass here — see resolve_ui_stage — rather than being
                # forwarded to retrieve_with_stage(stage="auto", ...): the paste's
                # hieroglyphs, below, must be resegmented with the *resolved*
                # stage's own segmenter, and retrieve_with_stage has no hook to redo
                # that resegmentation between its internal first and second pass.
                requested_stage = st.session_state[STAGE_STATE_KEY]
                resolved_stage, stage_inferred = resolve_ui_stage(
                    requested_stage, query, get_resources
                )
                resources = get_resources(resolved_stage)
                st.session_state["whyptology_resolved_stage"] = resolved_stage
                st.session_state["whyptology_stage_outcome"] = (
                    requested_stage,
                    resolved_stage,
                    stage_inferred,
                )

                # For a glyph query, regroup the signs first so the parallels are
                # matched on corpus-style groups rather than on the paste's spacing.
                # Read with this stage's own reading model/segmenter — restricting
                # the group counts to one stage changes which grouping wins, which
                # is what rescues most of the Urk. IV pastes a Late-Egyptian-diluted
                # pooled corpus otherwise mis-segments (ROADMAP.md, "Item A core
                # landed 2026-09-04").
                regrouped: str | None = None
                if contains_hieroglyphs(query):
                    segmentation, _, _, _ = resegment_query(resources, query)
                    regrouped = " ".join(segmentation.groups)
                    st.session_state["whyptology_segments"] = segmentation.groups
                else:
                    st.session_state.pop("whyptology_segments", None)
                # Pool of 50: the evaluation scripts rank within 50, so what ships
                # must rank within the same pool or the tuned behaviour differs.
                # stage=resolved_stage, never "auto": resolve_ui_stage above already
                # did the auto inference, so this always retrieves on one concrete
                # (or pooled/None) stage's resources.
                stage_result = retrieve_with_stage(
                    df,
                    resources_by_stage=get_resources,
                    query_mdc=query,
                    query_reading_order=reading_order,
                    stage=resolved_stage,
                    k=max(settings.top_k, 50),
                    query_hieroglyphs_norm=regrouped,
                )
                pool = stage_result.results
                st.session_state["whyptology_results"] = pool.head(
                    max(settings.top_k, 5)
                ).copy()
                st.session_state["whyptology_last_query"] = query
                # Make the URL shareable: an expert can now send "this one is wrong"
                # as a link instead of describing the query. The stage travels with
                # it, so re-opening the link searches the same evidence again.
                st.query_params["q"] = query
                st.query_params["stage"] = stage_internal_to_param(requested_stage)
                # The parse of the query that was actually *searched*, kept so the
                # empty state can say what was looked for even after the box has
                # been edited. `parse` above tracks the box, not the search.
                searched = parse_query(
                    query,
                    vocabulary=resources.index.vocabulary,
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

    # Now that the search block has run, the header can name this run's top result.
    paint_header(top_row)

    # One line under the results saying how the stage was decided — nothing when
    # the search restricted to nothing ("All") or hasn't run yet.
    stage_outcome = st.session_state.get("whyptology_stage_outcome")
    if results is not None and stage_outcome is not None:
        requested_stage, resolved_stage, stage_inferred = stage_outcome
        caption_text = stage_caption(requested_stage, resolved_stage, stage_inferred)
        if caption_text:
            st.caption(caption_text)

    # Tab order follows the query. "Sign-by-sign reading" is deliberately empty for
    # a transliteration query — there is nothing to decode when the reading is
    # already given — so leading with it showed a reviewer who had typed a
    # transliteration an empty panel, and she reported that no analysis was
    # produced. The suggestions are the answer to her query, so they come first.
    last_query = st.session_state.get("whyptology_last_query", "")
    decode_first = contains_hieroglyphs(last_query) if last_query else False
    # Kept short on purpose: at a 500px viewport the original labels ran to 596px,
    # so "Analysis" and "Source" sat off-screen behind a horizontal scroll — the
    # same failure mode as leading with an empty tab, one scroll further along.
    # These five fit a 375px phone.
    tab_titles = [
        "Sign by sign",
        "Readings",
        "Parallels",
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
            # The same stage the search itself resolved to (item A), not a fresh
            # pooled resegmentation — otherwise this tab could show a different
            # grouping than the one the parallels/suggestions above were found with.
            decode_resources = get_resources(
                st.session_state.get("whyptology_resolved_stage")
            )
            segmentation, as_pasted, model, segmenter = resegment_query(
                decode_resources, last_query
            )
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
            from_lexicon = [p for p in predictions if p.is_lexicon]
            unreadable = [p for p in unseen if not p.is_fallback and not p.is_lexicon]
            ambiguous = [p for p in predictions if p.is_ambiguous]

            # The badge must reflect what the reading is worth: a tick claims every
            # group was attested in THIS corpus, which is false the moment anything
            # was borrowed, taken from the external lexicon, or could not be read.
            if unreadable:
                badge, badge_title = "!", "some sign groups could not be read"
            elif fallbacks:
                badge, badge_title = "~", "some readings were inferred from similar groups"
            elif from_lexicon:
                badge, badge_title = (
                    "◇",
                    f"some readings come from the {LEXICON_LABEL}, not from a "
                    "sentence in this corpus",
                )
            else:
                badge, badge_title = "✓", "every sign group is attested in the corpus"
            st.markdown(
                '<div class="suggestion-card">'
                '<div class="suggestion-head">'
                f'<span class="suggestion-rank" title="{badge_title}">{badge}</span>'
                f'<span class="suggestion-reading">{escape(reading) or "—"}</span>'
                "</div>"
                f'<div class="suggestion-support">{len(signs)} sign groups · '
                f"{len(ambiguous)} multivalent · {len(from_lexicon)} from the lexicon · "
                f"{len(fallbacks)} inferred from a similar sign · "
                f"{len(unreadable)} unreadable</div>"
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
                            # An attested count from another corpus: real evidence, but
                            # not a sentence we can show, and it says so.
                            else f"lexicon {p.lexicon_count}× ({p.lexicon_source}) — "
                            "no sentence in this corpus"
                            if p.is_lexicon
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

            if from_lexicon:
                st.info(
                    f"{len(from_lexicon)} sign group(s) are not attested in this corpus "
                    f"but are in the {LEXICON_LABEL} — word-level spelling→reading "
                    "counts from the AES and Ramses corpora (University of Helsinki, "
                    "CC BY 4.0). The reading shown is the one most often attested "
                    "there; there is no sentence here to show as a parallel. Ramses "
                    "readings are normalised to the grammatically expected form of "
                    "the word, not to the exact spelling."
                )
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
                    "language_stage",
                    "source_text_id",
                    "period",
                    "transliteration_gold",
                    "translation",
                    "final_score",
                ]
                if col in results.columns
            ]
            table = results.loc[:, show].copy()
            if "language_stage" in table.columns:
                # Next to Source, in the same quiet style — normalised so an
                # unspecified row reads "stage not recorded", not the raw
                # per-import placeholder text.
                table["language_stage"] = table["language_stage"].map(evidence_stage_label)
            table = table.rename(
                columns={
                    "source": "Source",
                    "language_stage": "Stage",
                    "source_text_id": "Text",
                    "period": "Period",
                    "transliteration_gold": "Reading",
                    "translation": "Translation (German, from the corpus)",
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
                            # Next to the source badge, same quiet style — see
                            # evidence_stage_label for the normalised wording.
                            ("Language stage", "language_stage"),
                            ("Sentence", "source_sentence_id"),
                            ("Script", "script_type"),
                        ],
                    ):
                        column.caption(caption)
                        text = (
                            evidence_stage_label(row.get("language_stage"))
                            if field == "language_stage"
                            else value(row, field)
                        )
                        column.markdown(f"**{text}**")

                    st.markdown(f"**Reading:** {value(row, 'transliteration_gold')}")
                    st.markdown(
                        "**Translation (German, from the corpus):** "
                        f"{value(row, 'translation')}"
                    )
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
                    # st.code renders Streamlit's copy button, which is the only
                    # clipboard access a Streamlit page has. Typing hieroglyphs is
                    # the thing testers say they will not do; copying is how they
                    # actually get a sign sequence into the box.
                    st.caption("Copy these hieroglyphs to reuse them as a query:")
                    st.code(glyphs, language=None)
                else:
                    st.caption("No hieroglyphs recorded for this row.")
                st.markdown(
                    '<div class="panel-title">Translation · German, from the corpus</div>',
                    unsafe_allow_html=True,
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
                # Normalised wording for the stage column, matching the workspace's
                # evidence rows — see evidence_stage_label.
                cell = escape(
                    evidence_stage_label(row.get("language_stage"))
                    if col == "language_stage"
                    else value(row, col, "—")
                )
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
    with st.expander(
        f"Card view of this page · copy hieroglyphs ({len(page_rows)} records)"
    ):
        st.caption(
            "Each card shows its hieroglyphs in a copyable block — paste them into "
            "the workspace to see what the tool makes of a sign sequence."
        )
        for _, row in page_rows.iterrows():
            source_label = escape(value(row, "source", "Unknown source"))
            text_label = escape(value(row, "source_text_id", "Uncatalogued text"))
            period_label = escape(value(row, "period", "Period unknown"))
            # Same normalised wording as the workspace's evidence rows — see
            # evidence_stage_label — rather than this card's own former "unknown"
            # phrasing, so a reader sees one consistent label everywhere.
            language_label = escape(evidence_stage_label(row.get("language_stage")))
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
            glyphs = value(row, "hieroglyphs", "")
            if glyphs and glyphs != "—":
                # The copy button on st.code is the clipboard; the HTML card above
                # cannot offer one.
                st.code(glyphs, language=None)
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
                f"All {alignment.usable_rows:,} of {alignment.total_rows:,} corpus rows "
                "with sign evidence are sign/reading aligned and counted here."
            )
        if alignment.text_only_rows:
            st.caption(
                f"{alignment.text_only_rows:,} of {alignment.total_rows:,} corpus rows "
                "have a transliteration but no hieroglyphs; they take part in the "
                "transliteration search but contribute no sign evidence."
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
# A shared query link (?q=…) lands on the workspace, whatever page the session was
# on. Only on first sight: the workspace consumes the parameter once and leaves it
# in the URL so the link stays copyable.
if (
    st.query_params.get("q")
    and not st.session_state.get(QUERY_PARAM_CONSUMED_KEY)
):
    st.session_state["page"] = "Workspace"

page = sidebar(corpus)
def moved_to_banner_html(url: str) -> str:
    """The notice shown on a deployment that has been superseded by another URL.

    Streamlit Community Cloud keeps serving the link Sophie and others already
    have; this points them at the server, where the full corpus and durable
    annotations live. Rendered only when `moved_to_url` / `MOVED_TO_URL` is set.
    """
    safe = html.escape(url, quote=True)
    return (
        '<div class="moved-banner">This app has moved to '
        f'<a href="{safe}">{safe}</a>. This copy stays online but carries the '
        "smaller corpus and does not keep annotations.</div>"
    )


_moved_to = configured_setting("moved_to_url", "MOVED_TO_URL").strip()
if _moved_to:
    st.markdown(moved_to_banner_html(_moved_to), unsafe_allow_html=True)

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
