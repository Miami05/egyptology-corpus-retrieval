"""Import the St Andrews Corpus of Ancient Egyptian texts (Mark-Jan Nederhof).

Licence: **CC BY-NC-SA 4.0** on Nederhof's mail of 2026-09-02 (there is no public
licence statement on his site; see `docs/permission-requests.md`, Email 3, and
`DATA-LICENSE.md`). Non-commercial means the rows can never enter the CC BY-SA
`data/processed/examples.csv`, so the output goes to `data/private/standrews.csv`,
which is gitignored and must never be committed or copied into the public corpus.

    python scripts/import_standrews.py                 # write data/private/standrews.csv
    python scripts/import_standrews.py --limit 200     # a quick sample
    python scripts/import_standrews.py --output /tmp/x.csv

What the archive looks like
---------------------------
`corpus.xml` lists `<text location="texts/<Name>.xml"/>`; every path in the archive is
relative to the file that references it. A text file declares `<primary>` (a title and
the language of the *translation*), `<collection>` (the printed editions it follows),
one `<resource>` per annotation tier, and `<autoalign>`/`<precedence>` elements saying
which tiers were aligned with which. Nothing in it declares a language stage, a genre
or a period, so those three columns are left empty rather than guessed at.

Two tiers matter here:

* `resources/<Name>Hi*.xml` — the hieroglyphic tier, `<segment><texthi>` holding
  **RES** (Nederhof's Revised Encoding Scheme, *not* Manuel de Codage), with
  `<coord id="N"/>` marking where line N of the printed edition begins and
  `<pos id="N"/>` marking anchors used to align *transliteration witnesses to each
  other* (never to the hieroglyphic tier — no `Hi` file that pairs with a `Tr` file
  carrying `<@N>` anchors has a single `<pos>` of its own). 57 files, covering 55 of
  the 94 texts.
* `resources/<Name>Tr*.txt` — the transliteration tier in Nederhof's "lite" text
  format, 101 files (a text can have several witnesses: `SinuheTrB`, `SinuheTrR`, …,
  one per manuscript). Documented under "The lite format" below.

The lite format, as found in these 101 files
--------------------------------------------
A header of `key = value` lines (`creator`, `name`, `labelname`, `created`,
`modified`, `version`, `scheme`, `language`, `upload`, `email`, `password`, and one
`shown`/`ignored` line per tier), then free prose and bibliography, then the body.
Blocks are separated by blank lines. A **body block** is exactly a block containing a
line that is nothing but `;` — that is the only reliable marker, because the prose
and bibliography sections are separated the same way and the `###` rules that divide
them are not present in every file. All 8,203 body blocks in the archive have exactly
one `;`: the lines before it are the transliteration, the lines after it the
translation. Blocks are the author's own sentence division and become one row each.

Markup inside a block (counts over all 101 files):

* `<N>`, `<25,6>`, `<A1>`, `<"B">` — a **coordinate label**: line, column,
  page-and-line or plate of the printed edition. It marks the *position* where that
  line begins and can fall inside a word (`xft-Hr<3>-n`), which is exactly where the
  hieroglyphic tier's `<coord id="3"/>` falls too.
* `<@N>` — a **positional anchor**, the transliteration-witness alignment ids above.
  Dropped: it is not a line label and not part of the reading.
* `<note>…</note>` (183) — an editorial footnote, which may itself contain `<al>…</al>`
  (a transliteration) and `<hi>…</hi>` (a RES sign group). Removed from the reading and
  kept in `variant_writing_note`.
* `<al>…</al>` (100), `<hi>…</hi>` (48), `<i>…</i>` (406) — inline markup, almost all of
  it inside notes or prose. Tags stripped, contents kept.
* `<no>…</no>` (20) — "not part of the text": ditto marks (`""`) in a list of dates.
  Element and contents both dropped.
* XML entities `&quot;` `&amp;` `&lt;` `&gt;` `&apos;`, unescaped *after* the markers
  are removed so an escaped `&lt;` can never be read as a marker.

Transliteration conventions (Hannig, as `DATA-LICENSE.md` records)
------------------------------------------------------------------
Measured over the 8,203 body blocks: the yod is `j` (9,432) and `i` is a typo-level 7
occurrences — the opposite of the Ramses corpus, where it is `i`. There is **one** `z`
in the whole archive, confirming the Hannig no-`z`/`s` rule, and no `.t` dot. Those two
absences are left exactly as written: bridging them is a `search_fold` matter (`z`→`s`,
dots dropped) and must never be done to his text. `^` prefixes a proper name (2,050);
it is markup, not a letter, and is dropped like the Ramses `+name+l` wrapper.
`{…}` (superfluous signs), `[…]` (restored), `(…)` (supplied) are editorial apparatus
`normalize_mdc` already drops on both sides of the search, and are kept verbatim.

`=` is written closed up (`Dd=f`). The corpus writes the suffix pronoun as a token of
its own (`ḏd =f`, and `search_fold` splits on `=` for exactly that reason), and the
RES tier writes it as a quadrat of its own, so `=` becomes a token boundary here. No
character of his text is changed, added or removed by that: only whitespace is
inserted at a boundary he already marks.

RES → Unicode, and why most rows end up without glyphs
------------------------------------------------------
`hieropy` 0.1.9 (Nederhof's own GPL package; `pip install hieropy`) parses RES and
converts it to Unicode hieroglyphs with the Unicode format controls (U+13430…U+13438)
that encode the quadrat layout. Importing it headless needs a stub for
`hieropy.unieditor`, whose GUI chain pulls in `tkinter`/`tkinterweb` — see
`_install_hieropy_stub`. `normalize_hieroglyphs` deletes the format controls, so they
could never reach the search index anyway; they are preserved verbatim in the
per-line side file below, because they are the layout evidence item B (format
controls as segmenter hints) needs.

**No word-level sign/reading alignment is derivable from this archive, so the
`hieroglyphs` column is empty on every row.** The only anchor the two tiers share is
the coordinate (`<coord>`-to-`<coord>`, one printed line); inside a line, RES's top
level is the **quadrat**, not the word. A word whose determinative sits in its own
quadrat (`rmT` = `D21:V13` + `A1*(Z1:Z1:Z1)`) is two groups for one reading, so the
group and reading counts disagree on 1,486 of the 1,710 lines that have both tiers
(a further 174 carry RES damage notation and have no glyph to index at all).
The 50 lines where they *do* agree were checked by hand and the agreement is a
coincidence: `urkIV-030` line 2 pairs 20 groups with 20 readings and gets `ḥm` on the
quadrat for `ḥm=ꞽ`, `=ꞽ` on `ꜥnḫ`, and `ꜥ.w.s.` on `wḏꜣ-snb`. A count check is
sufficient evidence in `import_ramses.py` because `src-sep` marks word boundaries
explicitly; here there is nothing to check *against*, and a coincidence would train
the reading model on wrong pairs. So the count is measured and reported and then not
used. Recovering the word grouping means knowing which quadrats are classifiers —
which is exactly item C (`data/processed/sign_functions.csv`, from Nederhof's own
sign-function XML), not something to guess at here.

Two things are still produced from the RES:

* `display_sequence` carries the line's glyphs for the 135 blocks that *are* a whole
  line (one line, no damage notation, no word broken by a coordinate label, and the
  block accounts for every reading of the line). Those signs are exactly the signs of
  that sentence; only their grouping is unknown, and `display_sequence` is a display
  column no service reads.
* `data/raw/standrews/standrews_lines.csv` (gitignored, alongside the raw archive and
  *not* under `data/private/`, which the app loads wholesale) holds one record per
  line: the Unicode glyphs with their format controls beside that line's reading. That
  is the input for item B (format controls as segmentation hints) and for measuring
  item C's classifier rule against a real line.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import html
import re
import sys
import time
import types
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS, alignment_report  # noqa: E402
from app.data.normalizer import normalize_hieroglyphs, search_fold  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "standrews" / "corpus"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "private" / "standrews.csv"
# The per-line RES→Unicode rendering, kept for items B (format controls as
# segmentation hints) and C (sign functions). It must NOT live under data/private/:
# `load_private_examples` loads every `*.csv` in that directory as corpus rows and
# rejects any file without a `source` column. data/raw/standrews/ is gitignored too.
DEFAULT_LINES_OUTPUT = PROJECT_ROOT / "data" / "raw" / "standrews" / "standrews_lines.csv"
LINE_COLUMNS = [
    "text",
    "witness_file",
    "witness",
    "line",
    "res_groups",
    "readings",
    "hieroglyphs",
    "transliteration",
]

SOURCE = "StAndrews"
CITATION_URL = "https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/"
CONVENTION_NOTE = (
    "St Andrews corpus, Hannig transliteration conventions (no z/s distinction, no "
    "dot before the feminine .t), left as written; suffix pronouns tokenised on the "
    "author's own '='."
)

# ---------------------------------------------------------------------------
# Nederhof's MdC-style ASCII transliteration -> the corpus's TLA convention
# ---------------------------------------------------------------------------

# Deliberately *not* the same table as `import_ramses.py`: this corpus writes the yod
# `j` (9,432 occurrences) where Ramses writes it `i` (and `j` only inside `n(j)`).
# The 7 bare `i` here are the same letter written the other way in a handful of files,
# so both map to `ꞽ`. `y` (638) is the doubled yod and has no TLA replacement — it is
# already how the corpus writes it. Everything else (`b d f g h k l m n p q r s t w`,
# the digits and the editorial apparatus `. - = ( ) [ ] { } / ,`) is left exactly as
# written; the single `z` in the archive is kept as a `z`, because folding it to `s`
# would be inventing a distinction Hannig does not make.
STANDREWS_CHAR_MAP: dict[str, str] = {
    "A": "ꜣ",
    "a": "ꜥ",
    "j": "ꞽ",
    "i": "ꞽ",
    "H": "ḥ",
    "x": "ḫ",
    "X": "ẖ",
    "S": "š",
    "T": "ṯ",
    "D": "ḏ",
}
_STANDREWS_TABLE = str.maketrans(STANDREWS_CHAR_MAP)


def convert_word(word: str) -> str:
    """One St Andrews ASCII transliteration word -> the corpus's TLA convention."""
    return word.translate(_STANDREWS_TABLE)


# ---------------------------------------------------------------------------
# The lite transliteration format
# ---------------------------------------------------------------------------

NOTE_RE = re.compile(r"<note>(.*?)</note>", re.DOTALL)
DROP_ELEMENT_RE = re.compile(r"<no>.*?</no>", re.DOTALL)
INLINE_TAG_RE = re.compile(r"</?(?:al|hi|i|b|sup|sub)>")
MARKER_RE = re.compile(r"<([^<>\s][^<>]*)>")
HEADER_LINE_RE = re.compile(r"^[a-z]+\s*=\s*(.*)$")


@dataclass
class Piece:
    """One indivisible run of transliteration, tagged with where it came from.

    A piece is what sits between two of: whitespace, a `=` boundary, and a coordinate
    label. `glued` says the piece continues the previous one without a space — the
    `xft-Hr<3>-n` case, a word the printed edition broke across two lines.
    """

    text: str
    line_label: str
    glued: bool


@dataclass
class Block:
    """One body block: the author's own sentence unit."""

    index: int
    pieces: list[Piece]
    translation: str
    notes: list[str]

    @property
    def line_labels(self) -> list[str]:
        seen: list[str] = []
        for piece in self.pieces:
            if piece.line_label not in seen:
                seen.append(piece.line_label)
        return seen


def split_lite_blocks(raw: str) -> list[str]:
    """Blank-line-separated blocks of a lite file that are body blocks.

    A body block is one containing a line that is nothing but `;`. Header, prose and
    bibliography blocks are separated the same way and are excluded by that test
    alone — the `###` rules are not present in every file.
    """
    return [
        block
        for block in re.split(r"\n[ \t]*\n", raw)
        if any(line.strip() == ";" for line in block.split("\n"))
    ]


def read_lite_header(raw: str) -> dict[str, str]:
    """The `key = value` lines at the top of a lite file, up to the first blank line."""
    header: dict[str, str] = {}
    for line in raw.split("\n"):
        if not line.strip():
            break
        key, _, value = line.partition("=")
        if HEADER_LINE_RE.match(line):
            header[key.strip()] = value.strip()
    return header


def strip_markup(text: str) -> tuple[str, list[str]]:
    """Remove the lite format's non-reading markup; return (text, notes).

    `<no>…</no>` (ditto marks in date lists) goes entirely. `<note>…</note>` is
    lifted out and returned. Remaining inline tags lose the tag but keep the
    contents. Coordinate labels and `<@N>` anchors survive this step — they carry
    position and are handled by `parse_pieces`.
    """
    notes = [
        INLINE_TAG_RE.sub("", note).strip() for note in NOTE_RE.findall(text)
    ]
    text = NOTE_RE.sub("", text)
    text = DROP_ELEMENT_RE.sub("", text)
    text = INLINE_TAG_RE.sub("", text)
    return text, [note for note in notes if note]


def parse_pieces(text: str, current_label: str) -> tuple[list[Piece], str]:
    """Split a block's transliteration into `Piece`s; return (pieces, label after).

    Boundaries are whitespace, `=` (the corpus writes the suffix pronoun as its own
    token) and coordinate labels. `<@N>` anchors are dropped without splitting.
    Entities are unescaped and `^` (proper-name marker) removed at the very end, so
    neither can be mistaken for markup or for a boundary.
    """
    pieces: list[Piece] = []
    label = current_label
    glue_next = False
    position = 0
    matches: list[re.Match[str] | None] = list(MARKER_RE.finditer(text))
    matches.append(None)
    for match in matches:
        chunk = text[position : match.start()] if match else text[position:]
        first_in_chunk = True
        for raw_word in chunk.split():
            for part in _split_on_suffix_marker(raw_word):
                if not part:
                    continue
                pieces.append(
                    Piece(
                        text=part,
                        line_label=label,
                        # Only the first piece after a mid-word label continues the
                        # word that label interrupted.
                        glued=glue_next and first_in_chunk,
                    )
                )
                first_in_chunk = False
                glue_next = False
        if match is None:
            break
        marker = match.group(1)
        if not marker.startswith("@"):
            label = marker
            # A label with no whitespace on either side means the printed edition
            # broke a word across two lines (`xft-Hr<3>-n`).
            before = text[: match.start()]
            after = text[match.end() :]
            glue_next = (
                bool(before)
                and not before[-1].isspace()
                and bool(after)
                and not after[0].isspace()
            )
        position = match.end()
    for piece in pieces:
        piece.text = html.unescape(piece.text).replace("^", "")
    return [piece for piece in pieces if piece.text], label


def _split_on_suffix_marker(word: str) -> list[str]:
    """`Dd=f` -> `['Dd', '=f']`; `n=Tn` -> `['n', '=Tn']`; `sDm` -> `['sDm']`."""
    if "=" not in word:
        return [word]
    parts = word.split("=")
    out = [parts[0]]
    out.extend("=" + part for part in parts[1:])
    return [part for part in out if part not in ("", "=")]


def parse_lite_file(path: Path) -> tuple[dict[str, str], list[Block]]:
    raw = path.read_text(encoding="utf-8")
    header = read_lite_header(raw)
    blocks: list[Block] = []
    label = ""
    for index, chunk in enumerate(split_lite_blocks(raw), start=1):
        lines = chunk.strip("\n").split("\n")
        cut = next(i for i, line in enumerate(lines) if line.strip() == ";")
        translit_text, notes = strip_markup(" ".join(lines[:cut]))
        translation_text, _ = strip_markup(" ".join(lines[cut + 1 :]))
        translation_text = MARKER_RE.sub("", translation_text)
        pieces, label = parse_pieces(translit_text, label)
        blocks.append(
            Block(
                index=index,
                pieces=pieces,
                translation=html.unescape(translation_text).strip(),
                notes=notes,
            )
        )
    return header, blocks


# ---------------------------------------------------------------------------
# The hieroglyphic tier: RES -> Unicode
# ---------------------------------------------------------------------------


def _install_hieropy_stub() -> None:
    """Make `import hieropy` work without a display.

    `hieropy/__init__.py` imports `UniEditor`, which pulls in `tkinter` and
    `tkinterweb`; the venv has no `_tkinter`, and stubbing `tkinter` itself is not
    enough because `tkinterweb` subclasses `ttk.Scrollbar` at import time. Replacing
    the one GUI submodule the package's `__init__` needs is both smaller and safer:
    nothing this script calls (the RES parser and the RES→Unicode converter) touches
    it.
    """
    if "hieropy.unieditor" in sys.modules:
        return
    module = types.ModuleType("hieropy.unieditor")
    module.UniEditor = type("UniEditor", (), {})
    sys.modules["hieropy.unieditor"] = module


def load_res_converter():
    """(parser, converter) from hieropy, or (None, None) if it is not installed."""
    _install_hieropy_stub()
    try:
        from hieropy.hieroparsing import ResParser
        from hieropy.resconversion import ResUniConverter
    except ImportError:  # pragma: no cover - exercised only without hieropy
        return None, None
    return ResParser(), ResUniConverter()


def res_line_chunks(path: Path) -> list[tuple[str, str]]:
    """[(line label, RES text)] for one `Hi` file, split at `<coord id="N"/>`.

    `<segment>` boundaries are not line boundaries (a segment can be a whole line or
    a fragment of one), so every segment's RES is concatenated with `-`, the RES
    top-level separator, and the stream is cut only at coordinates — the one anchor
    the transliteration tier shares. `<pos>`, `<note>` and `<etc>` carry no glyphs
    and contribute only their tail text.
    """
    root = ET.parse(path).getroot()
    chunks: list[tuple[str, str]] = []
    label = ""
    current: list[str] = []
    for segment in root.findall("segment"):
        texthi = segment.find("texthi")
        if texthi is None:
            continue
        if texthi.text:
            current.append(texthi.text)
        for child in texthi:
            if child.tag == "coord":
                chunks.append((label, "".join(current)))
                current = []
                label = child.get("id", "")
            if child.tail:
                current.append(child.tail)
        current.append("-")
    chunks.append((label, "".join(current)))
    return chunks


def res_groups_by_line(path: Path, parser, converter) -> dict[str, list[str]]:
    """{line label: [Unicode string per RES top-level group]} for one `Hi` file."""
    by_line: dict[str, list[str]] = {}
    for label, res in res_line_chunks(path):
        res = res.strip().strip("-").strip()
        if not label or not res:
            continue
        fragment = parser.parse(res)
        if fragment is None or fragment.hiero is None:
            continue
        groups: list[str] = []
        for group in fragment.hiero.groups:
            converted = converter.convert_group(group)
            text = "" if converted is None else str(converted)
            # A group that normalises away is RES damage notation — a lost sign
            # (`[[`/`]]`), a hatched or shaded quadrat — carrying no glyph. It is a
            # real position in the line (`[...]` on the reading side), but it cannot
            # be indexed, and `normalize_hieroglyphs` deletes it, so leaving it in
            # would silently shorten the group list against the reading list. It is
            # kept as an empty slot, which disqualifies its line from alignment.
            groups.append(text if normalize_hieroglyphs(text) else "")
        by_line.setdefault(label, []).extend(groups)
    return by_line


# ---------------------------------------------------------------------------
# The archive
# ---------------------------------------------------------------------------


@dataclass
class TextEntry:
    name: str
    title: str
    path: Path
    collections: list[str]
    translit_paths: list[Path]
    hiero_paths: list[Path]
    # Tr file -> the Hi file `<autoalign>` pairs it with.
    autoalign: dict[Path, Path]


def _resolve(base: Path, location: str) -> Path:
    return (base.parent / location).resolve()


def read_corpus(raw_dir: Path) -> list[TextEntry]:
    corpus_path = raw_dir / "corpus.xml"
    root = ET.parse(corpus_path).getroot()
    entries: list[TextEntry] = []
    for text_element in root.findall("text"):
        path = _resolve(corpus_path, text_element.get("location", ""))
        if not path.exists():
            continue
        entries.append(read_text(path))
    return entries


def read_text(path: Path) -> TextEntry:
    root = ET.parse(path).getroot()
    primary = root.find("primary")
    title = primary.get("name", "") if primary is not None else ""
    collections_: list[str] = []
    for element in root.findall("collection"):
        parts = [element.get("collect", ""), element.get("section", "")]
        parts = [part for part in parts if part]
        if parts:
            collections_.append(" ".join(parts))
    translit_paths: list[Path] = []
    hiero_paths: list[Path] = []
    for element in root.findall("resource"):
        resource = _resolve(path, element.get("location", ""))
        if not resource.exists():
            continue
        if resource.suffix == ".txt":
            translit_paths.append(resource)
        elif is_hieroglyphic_resource(resource):
            hiero_paths.append(resource)
    autoalign: dict[Path, Path] = {}
    for element in root.findall("autoalign"):
        if element.get("tier1") != "hieroglyphic" or element.get("tier2") != (
            "transliteration"
        ):
            continue
        hiero = _resolve(path, element.get("location1", ""))
        translit = _resolve(path, element.get("location2", ""))
        if hiero.exists() and translit.exists():
            autoalign[translit] = hiero
    return TextEntry(
        name=path.stem,
        title=title,
        path=path,
        collections=collections_,
        translit_paths=translit_paths,
        hiero_paths=hiero_paths,
        autoalign=autoalign,
    )


def pair_by_name(entry: TextEntry, translit_path: Path) -> Path | None:
    """The `Hi` file for a `Tr` file that `<autoalign>` does not cover.

    50 of the 102 witnesses have no `<autoalign>`; for 6 of them the text does have a
    hieroglyphic tier. The archive names witnesses by manuscript: `PeasantTrB1` is the
    same manuscript as `PeasantHiB1`, `PtahhotepTrP` as `PtahhotepHiP`. Pairing is
    allowed only on an exact `Tr`→`Hi` substitution in the file name — never on "this
    text has exactly one Hi file", which would pair `ShipwreckedTrNld` (the Dutch
    translation witness) with a hieroglyphic manuscript it does not transcribe.
    """
    candidate = translit_path.stem.replace("Tr", "Hi", 1)
    for hiero_path in entry.hiero_paths:
        if hiero_path.stem == candidate:
            return hiero_path
    return None


def is_hieroglyphic_resource(path: Path) -> bool:
    """True for a `<egyptian>` file that actually carries a `<texthi>` RES tier.

    Named-based detection would be wrong: `PtahhotepDevaudP.txt` is a transliteration
    with no `Tr` in its name, and `ShipwreckedOrtho.xml`, `WestcarOrtho.xml`,
    `PeasantEq*.xml` and the `Im` image files are `.xml` but carry no glyphs.
    """
    if path.suffix != ".xml":
        return False
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return False
    return root.tag == "egyptian" and root.find("segment/texthi") is not None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def content_id(text_name: str, witness: str, index: int, transliteration: str) -> str:
    parts = [
        f"text={text_name}",
        f"witness={witness}",
        f"block={index}",
        f"transliteration_gold={transliteration}",
    ]
    digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=6)
    return f"STANDREWS_{digest.hexdigest().upper()}"


def to_schema(
    entry: TextEntry,
    witness_file: str,
    witness_name: str,
    block: Block,
    transliteration: str,
    display_glyphs: str,
    translation: str,
    has_hiero_tier: bool,
) -> dict:
    labels = [label for label in block.line_labels if label]
    line_ref = f"line {', '.join(labels)}" if labels else f"block {block.index}"
    notes = [CONVENTION_NOTE]
    if witness_name:
        notes.append(f"Witness: {witness_name}.")
    if entry.collections:
        notes.append("Follows " + "; ".join(entry.collections) + ".")
    out = {column: "" for column in REQUIRED_COLUMNS}
    out.update(
        {
            "source": SOURCE,
            "source_text_id": content_id(
                entry.name, witness_file, block.index, transliteration
            ),
            "source_sentence_id": f"S_{entry.name}_{witness_file}_{block.index:04d}",
            # Nothing in the archive declares a language stage, genre or period, so
            # all three stay empty rather than being inferred from the title.
            "language_stage": "",
            "script_type": "hieroglyphic" if has_hiero_tier else "",
            "genre": "",
            "period": "",
            # Always empty: see `_line_display`. RES's top level is the quadrat, so
            # no word-level sign/reading pairing can be derived from this archive,
            # and `hieroglyphs` is the column the reading model and the sign index
            # pair token-for-token.
            "hieroglyphs": "",
            "mdc": "",
            "sign_sequence": transliteration,
            "transliteration_gold": transliteration,
            "translation": translation,
            "grammar_notes": " ".join(notes),
            "source_ref": f"{CITATION_URL} {entry.name} ({witness_file}) {line_ref}",
            "review_status": "seed",
            "display_sequence": display_glyphs or transliteration,
            "variant_writing_note": " ".join(block.notes),
            "aesthetic_arrangement_flag": False,
        }
    )
    return out


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


@dataclass
class ImportReport:
    texts: int = 0
    texts_with_glyphs: int = 0
    witnesses: int = 0
    blocks: int = 0
    rows: int = 0
    rows_with_line_display: int = 0
    lines_seen: int = 0
    lines_count_coincidence: int = 0
    lines_with_lost_signs: int = 0
    dropped_empty: int = 0
    dropped_unsearchable: int = 0
    hieropy_missing: bool = False
    mismatch_examples: list[str] = field(default_factory=list)


def convert(
    raw_dir: Path, limit: int = 0, max_examples: int = 8
) -> tuple[pd.DataFrame, pd.DataFrame, ImportReport]:
    report = ImportReport()
    parser, converter = load_res_converter()
    report.hieropy_missing = parser is None
    rows: list[dict] = []
    lines: list[dict] = []

    for entry in read_corpus(raw_dir):
        report.texts += 1
        if entry.hiero_paths:
            report.texts_with_glyphs += 1
        for translit_path in entry.translit_paths:
            report.witnesses += 1
            header, blocks = parse_lite_file(translit_path)
            witness_name = header.get("name", "") or header.get("labelname", "")
            hiero_path = entry.autoalign.get(translit_path) or pair_by_name(
                entry, translit_path
            )
            groups_by_line: dict[str, list[str]] = {}
            if hiero_path is not None and parser is not None:
                groups_by_line = res_groups_by_line(hiero_path, parser, converter)

            pieces_by_line: dict[str, list[Piece]] = collections.defaultdict(list)
            for block in blocks:
                for piece in block.pieces:
                    pieces_by_line[piece.line_label].append(piece)
            for label, pieces in pieces_by_line.items():
                if not label or label not in groups_by_line:
                    continue
                report.lines_seen += 1
                if not all(groups_by_line[label]):
                    report.lines_with_lost_signs += 1
                elif len(groups_by_line[label]) == len(pieces):
                    report.lines_count_coincidence += 1
                elif len(report.mismatch_examples) < max_examples:
                    report.mismatch_examples.append(
                        f"{entry.name} line {label}: "
                        f"{len(groups_by_line[label])} RES groups vs "
                        f"{len(pieces)} readings "
                        f"({' '.join(p.text for p in pieces)[:70]})"
                    )
                lines.append(
                    {
                        "text": entry.name,
                        "witness_file": translit_path.stem,
                        "witness": witness_name,
                        "line": label,
                        "res_groups": len(groups_by_line[label]),
                        "readings": len(pieces),
                        "hieroglyphs": " ".join(groups_by_line[label]),
                        "transliteration": " ".join(
                            convert_word(piece.text) for piece in pieces
                        ),
                    }
                )

            for block in blocks:
                report.blocks += 1
                tokens, glued_seen = _assemble(block)
                transliteration = " ".join(convert_word(token) for token in tokens)
                if not transliteration:
                    report.dropped_empty += 1
                    continue
                if not search_fold(transliteration):
                    report.dropped_unsearchable += 1
                    continue
                display_glyphs = _line_display(
                    block, groups_by_line, pieces_by_line, glued_seen
                )
                if display_glyphs:
                    report.rows_with_line_display += 1
                rows.append(
                    to_schema(
                        entry,
                        translit_path.stem,
                        witness_name,
                        block,
                        transliteration,
                        display_glyphs,
                        block.translation,
                        bool(entry.hiero_paths),
                    )
                )
                report.rows += 1
                if limit and len(rows) >= limit:
                    return (
                        pd.DataFrame(rows, columns=REQUIRED_COLUMNS),
                        pd.DataFrame(lines, columns=LINE_COLUMNS),
                        report,
                    )

    return (
        pd.DataFrame(rows, columns=REQUIRED_COLUMNS),
        pd.DataFrame(lines, columns=LINE_COLUMNS),
        report,
    )


def _assemble(block: Block) -> tuple[list[str], bool]:
    """(transliteration tokens, a word was broken across two lines).

    Pieces a coordinate label split inside a word are glued back together, so the
    reading that leaves this function is his word, unbroken.
    """
    tokens: list[str] = []
    glued_seen = False
    for piece in block.pieces:
        if piece.glued and tokens:
            tokens[-1] = tokens[-1] + piece.text
            glued_seen = True
        else:
            tokens.append(piece.text)
    return tokens, glued_seen


def _line_display(
    block: Block,
    groups_by_line: dict[str, list[str]],
    pieces_by_line: dict[str, list[Piece]],
    glued_seen: bool,
) -> str:
    """The line's glyphs, but only when this block *is* the whole line.

    A display-only rendering for `display_sequence` — never for `hieroglyphs`, which
    the reading model and the sign index read and which must be token-aligned. The
    conditions are all objective: the block sits in one line, that line has no damage
    notation, no word of it was broken by a coordinate label, and the block accounts
    for every reading in the line. When they hold, the glyphs shown are exactly the
    signs of this sentence and nothing else; only the quadrat/word grouping inside
    them is unknown, which display does not need.
    """
    labels = {piece.line_label for piece in block.pieces}
    if glued_seen or len(labels) != 1:
        return ""
    label = labels.pop()
    groups = groups_by_line.get(label)
    if not groups or not all(groups):
        return ""
    if len(pieces_by_line.get(label, [])) != len(block.pieces):
        return ""
    return " ".join(groups)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--lines-output", default=str(DEFAULT_LINES_OUTPUT))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    started = time.time()
    frame, line_frame, report = convert(Path(args.raw_dir), limit=args.limit)

    if report.hieropy_missing:
        print("hieropy is NOT installed — no glyph rendering at all.\n")
    print(f"texts in corpus.xml            {report.texts:>8,}")
    print(f"  with a hieroglyphic tier     {report.texts_with_glyphs:>8,}")
    print(f"transliteration witnesses      {report.witnesses:>8,}")
    print(f"body blocks read               {report.blocks:>8,}")
    print(f"  dropped: empty reading       {report.dropped_empty:>8,}")
    print(f"  dropped: unsearchable        {report.dropped_unsearchable:>8,}")
    print(f"rows written                   {report.rows:>8,}")
    print("  hieroglyphs column filled            0  (see the module docstring)")
    print(f"  display-only line rendering  {report.rows_with_line_display:>8,}")
    print(f"lines with both tiers          {report.lines_seen:>8,}")
    print(f"  RES damage notation          {report.lines_with_lost_signs:>8,}")
    print(f"  group/reading counts equal   {report.lines_count_coincidence:>8,}"
          "  (a coincidence, not evidence — not used)")
    if report.mismatch_examples:
        print("\nline count mismatches, first few:")
        for example in report.mismatch_examples:
            print(f"  {example}")

    align = alignment_report(
        frame.assign(
            hieroglyphs_norm=frame["hieroglyphs"].map(
                lambda value: normalize_hieroglyphs(value) if value else ""
            )
        )
    )
    print(
        f"\nalignment check on the produced frame: total={align.total_rows} "
        f"misaligned={align.misaligned_rows} text_only={align.text_only_rows} "
        f"usable={align.usable_rows}"
    )
    if align.misaligned_rows:
        print("MISALIGNED ROWS FOUND (should be 0):", align.misaligned_indices[:20])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    lines_output = Path(args.lines_output)
    lines_output.parent.mkdir(parents=True, exist_ok=True)
    line_frame.to_csv(lines_output, index=False)
    print(f"\nwrote {len(frame)} rows to {output} in {time.time() - started:.1f}s")
    print(
        f"wrote {len(line_frame)} line records to {lines_output} — the RES→Unicode "
        "rendering per line, for items B and C; NOT loaded by the app "
        "(load_private_examples reads *.csv, so this file lives outside data/private/)."
    )
    print("PRIVATE, CC BY-NC-SA 4.0 — never commit this file or merge it into "
          "data/processed/examples.csv.")


if __name__ == "__main__":
    main()
