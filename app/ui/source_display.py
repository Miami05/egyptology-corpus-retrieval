"""HTML for a supporting row's hieroglyphs and source on a suggestion card.

Pure functions returning escaped HTML, so they can be tested without Streamlit.
Every data-derived string is escaped here with `html.escape(..., quote=True)`; the
only tags in the output are the ones written in this file. The output never holds a
newline (and so never a blank line): a blank line inside an `st.markdown` HTML block
ends the block, and Streamlit then shows the rest as text.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from html import escape
from pathlib import Path

from app.data.normalizer import G_MARKUP_RE, G_NESTED_RE
from app.data.source_metadata import NOT_RECORDED, Citation

SIGN_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "processed" / "sign_reference.csv"
)

NO_GLYPHS = "no hieroglyphs recorded in this source"

# A sign code that is a number (`2`, `NUM4`) is a numeral the source wrote as a code.
NUMERAL_CODE_RE = re.compile(r"^(?:NUM)?[0-9]+$")
WHITESPACE_RE = re.compile(r"\s+")

CC_BY_SA_LINK = (
    '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" '
    'rel="noopener">CC&nbsp;BY-SA&nbsp;4.0</a>'
)
CC0_LINK = (
    '<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" '
    'rel="noopener">CC0&nbsp;1.0</a>'
)
ORAEC_LINK = (
    '<a href="https://github.com/oraec/corpus_raw_data" target="_blank" '
    'rel="noopener">ORAEC</a>'
)

# Footer credits, appended only when AES or BBAW rows (the two corpora joined to the
# ORAEC metadata) are in the frame. Deliberately not CORPUS_CREDITS entries: those
# are keyed by `source`, and a test keeps them in step with review_common's
# PUBLIC_CREDITS. The author list is DATA-LICENSE.md's.
ORAEC_CREDIT = (
    f"Text metadata (titles, inventory numbers, dates, bibliographies): {ORAEC_LINK}, "
    "corpus_raw_data, from the AED/AES publications of the Berlin-Brandenburg "
    "Academy's “Strukturen und Transformationen des Wortschatzes der ägyptischen "
    "Sprache” (database excerpt of January 2018); authors: Burkhard Backes, Susanne "
    "Beck, Marc Brose, Adelheid Burkhardt, Roberto A. Díaz Hernández, Peter Dils, "
    "Roland Enmarch, Frank Feder, Heinz Felber, Silke Grallert, Stefan Grunert, "
    "Ingelore Hafemann, Anne Herzberg, John M. Iskander, Ines Köhler, Renata "
    "Landgrafova, Verena Lepper, Lutz Popko, Alexander Schütze, Stephan Seidlmayer, "
    "Gunnar Sperveslage, Susanne Töpfer, Doris Topmann, Altägyptisches Wörterbuch; "
    f"licensed {CC_BY_SA_LINK}. Adapted for display: entities decoded, first "
    "bibliography entry shown."
)
TRISMEGISTOS_CREDIT = f"Trismegistos text ids: ORAEC mapping, {CC0_LINK}."

STANDREWS_CARD_CREDIT = (
    "St Andrews Corpus of Ancient Egyptian texts, Mark-Jan Nederhof — "
    '<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" '
    'rel="noopener">CC&nbsp;BY-NC-SA&nbsp;4.0</a>, adapted (changes listed in the page '
    "credit), non-commercial, not redistributed."
)


@lru_cache(maxsize=1)
def sign_reference(path: str = str(SIGN_REFERENCE_PATH)) -> dict[str, tuple[str, str]]:
    """Gardiner/JSesh code → (Unikemet code point, description), from sign_reference.csv.

    Used for a tooltip only. That Unikemet lists a code does not prove the source
    meant that sign, so a code is never replaced by the character.
    """
    out: dict[str, tuple[str, str]] = {}
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("gardiner") or "").strip()
                if code and code not in out:
                    out[code] = (
                        (row.get("codepoint") or "").strip(),
                        WHITESPACE_RE.sub(" ", row.get("unikemet_description") or "").strip(),
                    )
    except OSError:
        return {}
    return out


def sign_code_tooltip(code: str, signs: dict[str, tuple[str, str]] | None = None) -> str:
    """The plain-text tooltip for one `<g>code</g>` sign code."""
    code = WHITESPACE_RE.sub(" ", code).strip() or "(empty)"
    if NUMERAL_CODE_RE.match(code):
        return f"Sign code {code}: a numeral written as a code in this source."
    tip = f"Sign code {code}, not encoded as a Unicode sign in this source."
    known = (signs or {}).get(code)
    if known and known[0]:
        codepoint, description = known
        tip += f" Unikemet 18 lists {code} as {codepoint}"
        tip += f": {description}" if description else "."
    return tip


def glyph_markup(raw: object, signs: dict[str, tuple[str, str]] | None = None) -> str:
    """The inline HTML for a raw `hieroglyphs` value, codes as marked boxes.

    The `<g>…</g>` codes (Ramses, BBAW and TLA all carry them) are split out *before*
    escaping, each becoming a neutral dashed box with the code in an escaped
    tooltip; everything else is escaped text, so malformed markup stays visible as
    text instead of becoming a tag.
    """
    text = "" if raw is None else str(raw)
    text = G_NESTED_RE.sub(lambda m: m.group(1), text)
    pieces = G_MARKUP_RE.split(text)
    out: list[str] = []
    for index, piece in enumerate(pieces):
        if index % 2 == 0:
            out.append(escape(WHITESPACE_RE.sub(" ", piece), quote=True))
        else:
            tip = escape(sign_code_tooltip(piece, signs), quote=True)
            out.append(
                f'<span class="glyph-missing" role="img" tabindex="0" '
                f'title="{tip}" aria-label="{tip}"></span>'
            )
    return "".join(out).strip()


def glyphs_html(
    raw: object,
    signs: dict[str, tuple[str, str]] | None = None,
    css_class: str = "suggestion-glyphs",
) -> str:
    """The row's glyphs as one block, or the explicit "none recorded" line."""
    if not WHITESPACE_RE.sub("", "" if raw is None else str(raw)):
        return f'<div class="no-glyphs">{NO_GLYPHS}</div>'
    return f'<div class="{css_class}">{glyph_markup(raw, signs)}</div>'


def _div(css_class: str, body: str) -> str:
    return f'<div class="{css_class}">{body}</div>'


def citation_html(citation: Citation, source: str = "") -> str:
    """The citation block for one supporting row. `source` is the row's corpus."""
    if citation.kind == "oraec" and citation.text is not None:
        t = citation.text
        parts = [_div("citation-title", escape(t.title or "untitled text", quote=True))]
        meta = [escape(t.location, quote=True)] if t.location else []
        # ORAEC's idno is sometimes a name (`pD'Orbiney`), not a number.
        meta.append(
            f"Inv./designation: {escape(t.idno, quote=True)}"
            if t.idno
            else "inventory number not recorded"
        )
        if t.date:
            meta.append(escape(t.date, quote=True))
        parts.append(_div("citation-meta", " · ".join(meta)))
        parts.append(
            _div("citation-bib", escape(t.bib_short, quote=True) or "bibliography not recorded")
        )
        if t.tm_id:
            url = escape(t.tm_url, quote=True)
            parts.append(
                _div(
                    "citation-tm",
                    f'<a href="{url}" target="_blank" rel="noopener">'
                    f"Trismegistos TM {escape(t.tm_id)} ↗</a>",
                )
            )
        else:
            parts.append(_div("citation-tm", "Trismegistos link not recorded"))
        if source == "BBAW":
            # The link is sentence → text; the archive line is not known.
            parts.append(_div("citation-note", "Linked to this text by sentence match; line not recorded."))
        authors = escape(t.authors, quote=True) if t.authors else "AED authors"
        credit = f"Text metadata: {ORAEC_LINK} ({authors}), {CC_BY_SA_LINK}"
        if t.tm_id:
            credit += f" · Trismegistos id: {CC0_LINK}"
        parts.append(_div("suggestion-credit", credit))
        return _div("suggestion-citation", "".join(parts))
    if citation.kind == "standrews" and citation.private is not None:
        p = citation.private
        witness = escape(p.witness, quote=True)
        if p.witness_name:
            witness += f" ({escape(p.witness_name, quote=True)})"
        where = f"text {escape(p.text, quote=True)}"
        if witness:
            where += f", witness {witness}"
        where += f", {escape(p.line, quote=True)}"
        parts = [_div("citation-title", f"St Andrews corpus: {where}")]
        if p.edition:
            parts.append(_div("citation-bib", f"Follows {escape(p.edition, quote=True)}"))
        parts.append(_div("suggestion-credit", STANDREWS_CARD_CREDIT))
        return _div("suggestion-citation", "".join(parts))
    return _div("suggestion-citation suggestion-citation-none", NOT_RECORDED)


def example_block_html(
    example,
    citation: Citation,
    signs: dict[str, tuple[str, str]] | None = None,
) -> str:
    """One supporting row: its own glyphs, then its own citation."""
    return _div(
        "suggestion-example",
        glyphs_html(example.hieroglyphs, signs) + citation_html(citation, example.source),
    )


def examples_html(
    examples,
    citations: list[Citation],
    signs: dict[str, tuple[str, str]] | None = None,
) -> str:
    """The card's evidence: the row the reading came from, then the others folded.

    `examples[0]` is the exact row the suggestion used (`best`); it is shown first
    whatever it looks like. The other distinct supporting rows go into a native
    `<details>`, each with its own glyphs and citation.
    """
    if not examples:
        return ""
    blocks = [example_block_html(e, c, signs) for e, c in zip(examples, citations)]
    html = _div("suggestion-example-label", "Supporting example") + blocks[0]
    others = blocks[1:]
    if others:
        noun = "attestation" if len(others) == 1 else "attestations"
        html += (
            f'<details class="suggestion-more"><summary>{len(others)} more {noun}</summary>'
            + "".join(others)
            + "</details>"
        )
    return html
