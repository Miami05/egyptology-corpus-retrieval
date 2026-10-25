"""Where a corpus row comes from, in words a scholar can cite.

The corpus rows carry only internal provenance: `AES/bbawtempelbib#text=…`,
`phiwi/bbaw_egyptian (…)`, `ramses-trl 2019-09-01 train line 48`,
`…/tla_earlier.parquet#row=1`. None of that is a reference. The ORAEC text metadata
(`source_metadata_oraec.csv`, CC BY-SA 4.0, Trismegistos ids CC0 — see
DATA-LICENSE.md) gives a title, inventory number, date, bibliography and TM id per
AED text, and two corpora can be joined to it:

- **AES**: every row's `source_ref` names its AED text (`#text=<26 chars>`), and the
  metadata is keyed by that AED text id.
- **BBAW**: only through `source_metadata_oraec_bbaw_links.csv`, the importer's
  *accepted* sentence → text links (a key of three or more words and a matching
  translation). The candidates file holds the links that were not accepted and is
  never read here. A link names a text, not a line, so a citation never claims one.

Every other public row (Ramses, TLA including Demotic, an unlinked BBAW row) gets
`NOT_RECORDED` — never its internal `source_ref`. The private St Andrews rows (NC)
get their own text/witness/line citation, built in a separate index that only a
keyed session ever asks for (see `build_private_citations`).

The public index is keyed by the row identity `(source, source_text_id,
source_sentence_id)` — unique over all 130,472 public rows — and holds one shared
`TextCitation` per text, so it costs a few MiB rather than a 130k-row merge, and is
never added to the corpus frame (which would change `corpus_signature` and ride along
into the database step). No Streamlit here: the app caches it, tests call it directly.
"""

from __future__ import annotations

import html
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ExampleKey = tuple[str, str, str]

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
METADATA_FILE = "source_metadata_oraec.csv"
LINKS_FILE = "source_metadata_oraec_bbaw_links.csv"

NOT_RECORDED = "source text not recorded in this corpus"
LINE_NOT_RECORDED = "line not recorded"

# The importer's one accepted matching rule (scripts/import_oraec_metadata.py). A link
# made any other way is not one this display has been checked against.
ACCEPTED_MATCH_METHOD = "unique sentence dedup_key + translation"
MIN_KEY_WORDS = 3
BIB_SHORT_MAX = 160

AES_TEXT_RE = re.compile(r"#text=([^&\s]+)")
# ORAEC stores "not recorded" as the label of an empty thesaurus slot: `3 = Fundstellen`,
# `21 = Objekttyp`. That is a field name, not a value.
PLACEHOLDER_RE = re.compile(r"^\d+ = ")
WHITESPACE_RE = re.compile(r"\s+")
TM_ID_RE = re.compile(r"^[0-9]+$")
ORAEC_ID_RE = re.compile(r"^oraec[0-9]+$")


@dataclass(frozen=True)
class TextCitation:
    """One ORAEC text, cleaned for display. Shared by every row of that text."""

    oraec_id: str
    aed_text_id: str
    title: str = ""
    bib_short: str = ""
    idno: str = ""
    location: str = ""
    date: str = ""
    tm_id: str = ""
    authors: str = ""

    @property
    def tm_url(self) -> str:
        """Built from the validated id, never taken from the stored URL."""
        return f"https://www.trismegistos.org/text/{self.tm_id}" if self.tm_id else ""


@dataclass(frozen=True)
class PrivateCitation:
    """A St Andrews row's own text, witness and line — keyed sessions only."""

    text: str
    witness: str = ""
    witness_name: str = ""
    line: str = LINE_NOT_RECORDED
    edition: str = ""


@dataclass(frozen=True)
class Citation:
    """What a card says about a row's source.

    `kind` is "oraec" (an ORAEC text: `text` is set), "standrews" (a keyed session's
    private row: `private` is set) or "none" (`NOT_RECORDED`).
    """

    kind: str
    text: TextCitation | None = None
    private: PrivateCitation | None = None


NO_CITATION = Citation("none")


@dataclass(frozen=True)
class SourceCitations:
    """The public citation index: row identity → shared text citation."""

    by_key: dict[ExampleKey, TextCitation]
    text_count: int = 0

    def __len__(self) -> int:
        return len(self.by_key)


EMPTY_CITATIONS = SourceCitations({}, 0)


def clean_field(value: object) -> str:
    """Decode stored HTML entities once, drop placeholders, collapse whitespace.

    1,009 bibliographies, 78 titles, 119 author strings and 2 inventory numbers are
    stored entity-encoded (`&quot;Schmitt&quot;`); escaping them again at render time
    would show `&amp;quot;`. Whitespace is collapsed because a blank line inside an
    `st.markdown` HTML block ends the block and shows the rest as escaped text.
    """
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    text = WHITESPACE_RE.sub(" ", html.unescape(text)).strip()
    return "" if PLACEHOLDER_RE.match(text) else text


def bib_short(raw: object) -> str:
    """The first bibliography entry, at most BIB_SHORT_MAX characters.

    ORAEC bibliographies are `- `-prefixed lines, up to 7,000 characters; the card
    shows the first entry, cut at a word boundary with "…" when it is longer.
    """
    if raw is None:
        return ""
    for line in html.unescape(str(raw)).splitlines():
        line = WHITESPACE_RE.sub(" ", line).strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line or line.lower() == "nan" or PLACEHOLDER_RE.match(line):
            continue
        if len(line) <= BIB_SHORT_MAX:
            return line
        cut = line[: BIB_SHORT_MAX - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut.rstrip(" ,;:") + "…"
    return ""


def clean_authors(raw: object) -> str:
    """The text's AED author, or "" when the stored string is unusable.

    119 author strings were joined field-by-field upstream (`Renata & Peter
    Landgrafova & Dils`); printing that would misname two people, so those fall back
    to the generic "AED authors" wording at render time.
    """
    text = clean_field(raw)
    return "" if "&" in text else text


def aed_text_id_for(source_ref: object) -> str:
    """The AED text id an AES `source_ref` names (`…#text=<id>&sentence=…`)."""
    match = AES_TEXT_RE.search(str(source_ref or ""))
    return match.group(1) if match else ""


def _intern(value: object) -> str:
    return sys.intern(str(value))


def load_text_citations(metadata_path: Path) -> dict[str, TextCitation]:
    """oraec_id → TextCitation, from the ORAEC metadata file (only needed columns)."""
    columns = [
        "oraec_id",
        "aed_text_id",
        "title",
        "bibliography",
        "idno",
        "location",
        "date",
        "trismegistos_id",
        "text_authors",
    ]
    frame = pd.read_csv(metadata_path, dtype=str, keep_default_na=False, usecols=columns)
    texts: dict[str, TextCitation] = {}
    for row in frame.itertuples(index=False):
        oraec_id = str(row.oraec_id).strip()
        if not ORAEC_ID_RE.match(oraec_id):
            continue
        tm_id = str(row.trismegistos_id).strip()
        texts[oraec_id] = TextCitation(
            oraec_id=oraec_id,
            aed_text_id=str(row.aed_text_id).strip(),
            title=clean_field(row.title),
            bib_short=bib_short(row.bibliography),
            idno=clean_field(row.idno),
            location=clean_field(row.location),
            date=clean_field(row.date),
            tm_id=tm_id if TM_ID_RE.match(tm_id) else "",
            authors=clean_authors(row.text_authors),
        )
    return texts


def load_bbaw_links(links_path: Path, known_texts: set[str]) -> dict[str, str]:
    """BBAW source_sentence_id → oraec_id, accepted links only.

    Every condition the importer accepted a link on is re-checked rather than
    trusted: status, matching rule, a key of at least three words, a translation
    match parsed as exactly True, and a target text the metadata knows. A sentence
    linked to two different texts is ambiguous and gets neither.
    """
    frame = pd.read_csv(links_path, dtype=str, keep_default_na=False)
    links: dict[str, str] = {}
    conflicted: set[str] = set()
    for row in frame.itertuples(index=False):
        if str(row.source).strip() != "BBAW":
            continue
        if str(row.link_status).strip() != "accepted":
            continue
        if str(row.match_method).strip() != ACCEPTED_MATCH_METHOD:
            continue
        if str(row.translation_match).strip() != "True":
            continue
        try:
            if int(str(row.key_words).strip()) < MIN_KEY_WORDS:
                continue
        except ValueError:
            continue
        sentence = str(row.source_sentence_id).strip()
        oraec_id = str(row.oraec_id).strip()
        if not sentence or oraec_id not in known_texts:
            continue
        previous = links.get(sentence)
        if previous is not None and previous != oraec_id:
            conflicted.add(sentence)
        links[sentence] = oraec_id
    for sentence in conflicted:
        del links[sentence]
    if conflicted:
        logger.warning("ORAEC links: %d BBAW sentences link to two texts; dropped", len(conflicted))
    return links


def build_source_citations(
    public: pd.DataFrame,
    processed_dir: Path = PROCESSED_DIR,
) -> SourceCitations:
    """The public citation index over `public` (the public corpus frame).

    Missing metadata files give an empty index — every card then says
    `NOT_RECORDED` — rather than a broken page.
    """
    metadata_path = Path(processed_dir) / METADATA_FILE
    links_path = Path(processed_dir) / LINKS_FILE
    if not metadata_path.is_file() or public.empty:
        return EMPTY_CITATIONS
    texts = load_text_citations(metadata_path)
    by_aed = {text.aed_text_id: text for text in texts.values() if text.aed_text_id}
    bbaw_links = load_bbaw_links(links_path, set(texts)) if links_path.is_file() else {}

    by_key: dict[ExampleKey, TextCitation] = {}
    for column in ("source", "source_text_id", "source_sentence_id", "source_ref"):
        if column not in public.columns:
            return EMPTY_CITATIONS
    sources = public["source"].astype(str).str.strip()
    aes = public.loc[sources == "AES", ["source_text_id", "source_sentence_id", "source_ref"]]
    for text_id, sentence_id, ref in aes.itertuples(index=False):
        text = by_aed.get(aed_text_id_for(ref))
        if text is not None:
            by_key[("AES", _intern(str(text_id).strip()), str(sentence_id).strip())] = text
    bbaw = public.loc[sources == "BBAW", ["source_text_id", "source_sentence_id"]]
    for text_id, sentence_id in bbaw.itertuples(index=False):
        oraec_id = bbaw_links.get(str(sentence_id).strip())
        if oraec_id is not None:
            by_key[("BBAW", _intern(str(text_id).strip()), str(sentence_id).strip())] = texts[oraec_id]
    return SourceCitations(by_key, len({id(text) for text in by_key.values()}))


# ---------- St Andrews (private, NC) ----------

STANDREWS_REF_RE = re.compile(
    r"^\S+\s+(?P<text>\S+)\s+\((?P<witness>[^()]*)\)\s+(?P<where>(?:line|block)\b.*)$"
)
WITNESS_NOTE_RE = re.compile(r"Witness:\s*([^.]+)\.")
EDITION_NOTE_RE = re.compile(r"Follows\s+(.+?)\.?\s*$")


def parse_standrews_citation(source_ref: object, grammar_notes: object = "") -> PrivateCitation | None:
    """Text, witness and line from the importer's `source_ref` format.

    `<texts url> urkIV-001 (urkIV-001Tr) line 1`. A ref that ends in `block N` has
    no line label in the archive: the block number is the importer's own count, so
    it is reported as "line not recorded", never relabelled as a line. Anything
    else is not a format this parser knows, and gets no citation at all.
    """
    match = STANDREWS_REF_RE.match(clean_field(source_ref))
    if not match:
        return None
    where = match.group("where")
    line = where if where.startswith("line ") else LINE_NOT_RECORDED
    notes = clean_field(grammar_notes)
    witness_name = WITNESS_NOTE_RE.search(notes)
    edition = EDITION_NOTE_RE.search(notes)
    editions: list[str] = []
    if edition:
        for part in edition.group(1).split(";"):
            part = part.strip()
            if part and part not in editions:
                editions.append(part)
    return PrivateCitation(
        text=match.group("text"),
        witness=match.group("witness").strip(),
        witness_name=witness_name.group(1).strip() if witness_name else "",
        line=line,
        edition="; ".join(editions),
    )


def build_private_citations(private: pd.DataFrame) -> dict[ExampleKey, PrivateCitation]:
    """The private citation index, from the already loaded private corpus.

    Kept apart from the public index (its own cache in the app, keyed by the
    private directory and its revision) and consulted only after the session's
    reviewer key has been checked — see `citation_for`.
    """
    out: dict[ExampleKey, PrivateCitation] = {}
    if private.empty:
        return out
    for row in private.itertuples(index=False):
        source = str(getattr(row, "source", "")).strip()
        if source != "StAndrews":
            continue
        citation = parse_standrews_citation(
            getattr(row, "source_ref", ""), getattr(row, "grammar_notes", "")
        )
        if citation is not None:
            key = (source, str(row.source_text_id).strip(), str(row.source_sentence_id).strip())
            out[key] = citation
    return out


def citation_for(
    example,
    citations: SourceCitations,
    private_citations: dict[ExampleKey, PrivateCitation] | None = None,
    private_allowed: bool = False,
) -> Citation:
    """The citation a card shows for one supporting row (a `SupportingExample`).

    Looked up by the row's identity only — the row's own `source_ref` is never
    shown, so `parquet#row=`, `train line N` and dataset names cannot reach a card.
    A private row is cited only when `private_allowed` (the caller's per-access
    reviewer check) is true; otherwise it gets the same honest line as any row with
    no recorded source.
    """
    key = (
        str(example.source).strip(),
        str(example.source_text_id).strip(),
        str(example.source_sentence_id).strip(),
    )
    if key[0] == "StAndrews":
        if private_allowed and private_citations:
            private = private_citations.get(key)
            if private is not None:
                return Citation("standrews", private=private)
        return NO_CITATION
    text = citations.by_key.get(key)
    if text is not None:
        return Citation("oraec", text=text)
    return NO_CITATION


def metadata_revision(processed_dir: Path = PROCESSED_DIR) -> str:
    """A cache-identity string for the metadata files (size and mtime of each)."""
    parts = []
    for name in (METADATA_FILE, LINKS_FILE):
        path = Path(processed_dir) / name
        try:
            stat = path.stat()
            parts.append(f"{name}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{name}:missing")
    return "|".join(parts)
