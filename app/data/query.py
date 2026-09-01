"""One front door for every notation a reading can be typed in.

An Egyptologist writes the same sentence in at least four ways, and before this
module each of them took a different path into the search — three of them broken:

    ꜥḥꜥ.n stẖ qnd    Unicode, TLA/Berlin conventions   (was: characters deleted)
    aHa.n stX qnd    Manuel de Codage, as JSesh emits  (was: read as plain ASCII)
    aha.n stkh qnd   plain ASCII, no special keys      (worked)
    𓊢𓂝𓈖 𓋴𓏏𓅆       Unicode hieroglyphs               (worked, separate index)

`parse_query` decides which of those it is holding, reduces it to the single key
the corpus is indexed under (`search_fold`), and hands back the Unicode reading it
believes you meant so the app can show its interpretation instead of silently
searching for something else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Container, Iterable

from app.data.normalizer import (
    contains_hieroglyphs,
    nfc,
    normalize_hieroglyphs,
    search_fold,
)

# Manuel de Codage transliteration alphabet, as produced by JSesh and by every
# hieroglyph editor that predates convenient Unicode input. Case is meaningful and
# is the whole point: `H` is ḥ but `h` is h, `x` is ḫ but `X` is ẖ. Letters absent
# from this table (b p f m n r w y z s k g t d and the digits) stand for themselves.
#
# `i` and `j` both map to yod: MdC writes it `i`, several teaching grammars write
# `j`, and the corpus writes `ꞽ`.
MDC_TO_TRANSLITERATION: dict[str, str] = {
    "A": "ꜣ",
    "a": "ꜥ",
    "i": "ꞽ",
    "j": "ꞽ",
    "H": "ḥ",
    "x": "ḫ",
    "X": "ẖ",
    "S": "š",
    "T": "ṯ",
    "D": "ḏ",
    "Q": "q",
}

# The letters above that a plain-ASCII typist would have no reason to produce: they
# are upper-case in the middle of a lower-case word (`aHa`, `stX`, `Dw`). Their
# presence is the cheap signal that a string is MdC; `_pick_notation` only falls
# back to it when there is no corpus vocabulary to decide the question properly.
MDC_MARKED_LETTERS = frozenset("AHXSTD")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_TOKEN_RE = re.compile(r"[^\s:\-]+")


@dataclass(frozen=True)
class QueryParse:
    """What the user typed, what we think it says, and what we will search for."""

    raw: str
    #: "hieroglyphs" | "unicode" | "mdc" | "ascii" | "empty"
    notation: str
    #: Index-space key. Empty for a hieroglyph query, which matches on signs.
    search_key: str
    #: Normalised sign groups. Empty for a text query.
    hieroglyphs_norm: str
    #: The Unicode transliteration this was understood as — for showing back to the
    #: user. Empty when the input cannot be reconstructed (plain ASCII loses which
    #: letter was meant, so `htp` could be ḥtp or htp and we do not guess).
    reading: str

    @property
    def is_hieroglyphic(self) -> bool:
        return bool(self.hieroglyphs_norm)

    @property
    def is_empty(self) -> bool:
        return not self.search_key and not self.hieroglyphs_norm

    @property
    def notation_label(self) -> str:
        return {
            "hieroglyphs": "hieroglyphs",
            "unicode": "transliteration (Unicode)",
            "mdc": "transliteration (Manuel de Codage)",
            "ascii": "transliteration (plain ASCII)",
            "empty": "nothing",
        }[self.notation]


# The plain-ASCII digraphs the app documents (`aha.n stkh qnd`, `htp dji nswt`).
# Now that the yod folds to `i`, an ASCII `j` is ambiguous: `dji` is either ḏi̯
# written with our digraph or d + yod + i. `_pick_notation` folds both readings and
# lets the corpus decide, exactly as it does for Manuel de Codage.
ASCII_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("kh", "ḫ"),
    ("sh", "š"),
    ("tj", "ṯ"),
    ("dj", "ḏ"),
)


def ascii_digraphs_to_transliteration(text: str) -> str:
    """Read `kh sh tj dj` as ḫ š ṯ ḏ — the app's own documented ASCII convention."""
    out = nfc(text)
    for digraph, letter in ASCII_DIGRAPHS:
        out = out.replace(digraph, letter)
    return out


def mdc_to_transliteration(text: str) -> str:
    """Rewrite Manuel de Codage letters as the Unicode transliteration they encode."""
    return "".join(MDC_TO_TRANSLITERATION.get(char, char) for char in nfc(text))


def looks_like_mdc(text: str) -> bool:
    """True when an ASCII string carries an MdC-only letter (`aHa`, `stX`, `Dw`)."""
    if any(ord(char) > 127 for char in text):
        return False
    return any(char in MDC_MARKED_LETTERS for char in text)


def _known_token_count(key: str, vocabulary: Container[str]) -> int:
    return sum(1 for token in _TOKEN_RE.findall(key) if token in vocabulary)


def _pick_notation(text: str, vocabulary: Container[str] | None) -> tuple[str, str, str]:
    """Choose between reading the Latin letters as MdC and taking them at face value.

    Decided by evidence where there is any: both readings are folded and the one
    with more tokens the corpus actually contains wins. `aHa.n stX qnd r Dw` folds
    to `ahan stx qnd r dw` at face value (three known tokens) and to `ahan stkh qnd
    r djw` as MdC (six), so MdC wins on its own merits rather than on a guess about
    capital letters. Ties go to the face value, which is the lossier but safer read.

    This runs for a string that already contains Egyptological characters too. A
    query is often mixed — someone types `stX` and then taps `ꜣ` from the palette —
    and treating "has a Unicode letter" as proof that the Latin letters are not MdC
    silently turned that `X` back into a plain x.

    Returns (notation, search_key, reading).
    """
    has_egyptological = any(ord(char) > 127 for char in text)
    plain_notation = "unicode" if has_egyptological else "ascii"
    plain_key = search_fold(text)
    plain_reading = text if has_egyptological else ""
    if not _ASCII_LETTER_RE.search(text):
        return plain_notation, plain_key, plain_reading
    mdc_reading = mdc_to_transliteration(text)
    mdc_key = search_fold(mdc_reading)
    # Third reading, ASCII only: our documented digraphs. Since the yod folds to
    # `i`, `htp dji nswt` at face value is `htp dii nswt`; read with digraphs it is
    # ḥtp ḏi̯ nswt → `htp dji nswt`, which is what the corpus holds.
    digraph_key = "" if has_egyptological else search_fold(ascii_digraphs_to_transliteration(text))
    if digraph_key == plain_key:
        digraph_key = ""
    if mdc_key == plain_key and not digraph_key:
        return plain_notation, plain_key, plain_reading
    if vocabulary is None:
        if looks_like_mdc(text):
            return "mdc", mdc_key, mdc_reading
        if digraph_key:
            return "ascii", digraph_key, ascii_digraphs_to_transliteration(text)
        return plain_notation, plain_key, plain_reading
    plain_hits = _known_token_count(plain_key, vocabulary)
    best_notation, best_key, best_reading, best_hits = (
        plain_notation, plain_key, plain_reading, plain_hits,
    )
    if digraph_key and _known_token_count(digraph_key, vocabulary) >= best_hits:  # a tie goes to our documented convention
        best_notation, best_key, best_reading, best_hits = (
            "ascii",
            digraph_key,
            ascii_digraphs_to_transliteration(text),
            _known_token_count(digraph_key, vocabulary),
        )
    if mdc_key != plain_key and _known_token_count(mdc_key, vocabulary) > best_hits:
        best_notation, best_key, best_reading = "mdc", mdc_key, mdc_reading
    return best_notation, best_key, best_reading


def parse_query(
    raw: object,
    vocabulary: Container[str] | None = None,
    hieroglyphs_norm: str | None = None,
) -> QueryParse:
    """Read a query in whatever notation it arrived in.

    `vocabulary` is the set of tokens the corpus is indexed under — pass
    `SearchIndex.stats.mdc_frequencies` — and is used only to tell Manuel de Codage
    from plain ASCII. `hieroglyphs_norm` overrides the sign grouping, which is how
    the workspace feeds in the resegmented groups instead of the paste's spacing.
    """
    text = nfc(str(raw or "")).strip()
    if hieroglyphs_norm is None and contains_hieroglyphs(text):
        hieroglyphs_norm = normalize_hieroglyphs(text)
    # Groups passed in by the caller decide the mode even when the raw query is
    # empty: the workspace resegments the paste and then searches on the groups
    # alone, and the evaluation scripts pass groups with no text at all.
    if hieroglyphs_norm:
        # A sign query is matched on signs alone. Latin text in the same paste (a
        # line number, a note) is deliberately ignored rather than mixed in — see
        # the comment in app.services.retrieval for what it used to cost.
        return QueryParse(
            raw=text,
            notation="hieroglyphs",
            search_key="",
            hieroglyphs_norm=hieroglyphs_norm,
            reading="",
        )

    if not text:
        return QueryParse(
            raw="", notation="empty", search_key="", hieroglyphs_norm="", reading=""
        )

    notation, search_key, reading = _pick_notation(text, vocabulary)
    return QueryParse(
        raw=text,
        notation=notation,
        search_key=search_key,
        hieroglyphs_norm="",
        reading=reading,
    )


def vocabulary_from(values: Iterable[str]) -> set[str]:
    """Every token the given index column contains — the set `parse_query` wants."""
    tokens: set[str] = set()
    for value in values:
        tokens.update(_TOKEN_RE.findall(str(value)))
    return tokens
