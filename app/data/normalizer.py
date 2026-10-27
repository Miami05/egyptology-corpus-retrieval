from __future__ import annotations

import re
import unicodedata
import zlib

WHITESPACE_RE = re.compile(r"\s+")
# `=` (and the Egyptological `⸗`) mark a suffix pronoun. They separate tokens.
SUFFIX_MARKER_RE = re.compile(r"[=\u2e17]")
# An editorially supplied yod: `(ꞽ)`, `(.ꞽ)`, `(j)`, `(.j)`, and the ASCII `(i)`, `(.i)` a
# typist without special keys writes — see normalize_transliteration.
PARENTHESISED_YOD_RE = re.compile(r"\(\.?[ꞽjıi]\)")
NON_ALNUM_KEEP_COLON_RE = re.compile(r"[^a-z0-9:_\-\s]")
MULTI_COLON_RE = re.compile(r":+")
# The plural marker: TLA rows write `.PL` (2,842 tokens), AES/BBAW rows write `.pl`
# (4,873), 277 stems attested both ways. Fold both to `.w`, the phonemic plural
# ending, so the two spellings match. 1,127 tokens are written `.w.PL`/`.w.pl`
# (`sr.w.PL`) — the optional `(?:\.w)?` prefix collapses that to `.w`, not `.w.w`
# (a naive `.pl` → `.w` replace would make `srww`). The negative lookahead
# `(?![^\W\d_])` (no following letter) stops the fold firing inside a longer
# sequence. Case-insensitive so `.PL` matches directly (callers may run this before
# lowercasing); `.PL.t` never occurs in the corpus, so no interaction to handle.
PLURAL_MARKER_RE = re.compile(r"(?:\.w)?\.pl(?![^\W\d_])", re.IGNORECASE)
# Brackets around either half of the plural notation: `šms(.w).pl` (74 corpus rows),
# `šms.w(.pl)` (8), `šms(.w)(.pl)`, and `nb(.pl)` (271). PLURAL_MARKER_RE cannot see a
# `.w` across a `)`, so the fold used to add a second one (`šms.w.w`, indexed `shmsww`).
# `fold_plural_marker` first unbrackets `(.pl)` and then drops a bracketed `.w` that
# stands right before `.pl`, so all four spellings fold to `šms.w`. Only `.w`: `(.t).pl`
# and `(ꞽ).pl` are another morpheme plus the plural, and a stem-final `w` outside the
# brackets (`nw(.w).pl` → `nw.w`) is kept.
BRACKETED_PLURAL_PL_RE = re.compile(r"\(\.pl\)(?![^\W\d_])", re.IGNORECASE)
BRACKETED_PLURAL_W_RE = re.compile(r"\(\.?w\)(?=\.pl(?![^\W\d_]))", re.IGNORECASE)
# `{…}` marks text the editor considers superfluous (BBAW; also the St Andrews
# convention, see scripts/import_standrews.py): written on the monument, not part of the
# reading, so it is deleted from the search key. See `drop_superfluous_text`.
SUPERFLUOUS_RE = re.compile(r"\{[^{}]*\}")
# The one exception, `{{…}}`: in this corpus only BBAW rows use it (148 rows, e.g.
# `{{pꜣ}} {{pri̯}} {{[ꞽri̯.n]}}`), always around whole words of captions and additions
# that are read as text. That is an observation of the committed data, not a documented
# BBAW convention (checked 2026-10-25; no source documentation found), so the rule is
# deliberately narrow: exactly two braces on each side with no brace inside.
DOUBLE_BRACED_RE = re.compile(r"\{\{([^{}]*)\}\}")
# A `/` between two digits is a fraction (`1/2`, `1/64`). Deleting it made `1/2` the
# whole number `12`. `_` survives NON_ALNUM_KEEP_COLON_RE and is not a token split, so
# `1_2` stays one token that no whole number can equal.
FRACTION_SLASH_RE = re.compile(r"(?<=\d)/(?=\d)")


def fold_plural_marker(value: str) -> str:
    """Fold the `.PL`/`.pl` plural marker to `.w`, the phonemic plural ending.

    Brackets around either half are resolved first (`šms(.w).pl`, `šms.w(.pl)`,
    `šms(.w)(.pl)` → `šms.w`; see BRACKETED_PLURAL_PL_RE), so the search key and the
    strict reading key both see one plural ending, never `.w.w`.
    """
    value = BRACKETED_PLURAL_PL_RE.sub(".pl", value)
    value = BRACKETED_PLURAL_W_RE.sub("", value)
    return PLURAL_MARKER_RE.sub(".w", value)


def drop_superfluous_text(value: str) -> str:
    """Delete editorially superfluous `{…}` text, nested braces included.

    `nb{.t}` → `nb`, `ḏd.n={f}` → `ḏd.n=`, `{a{b}c}` → ``. `{{…}}` is the one exception
    (see DOUBLE_BRACED_RE): its braces are removed and its words kept. A text that is
    superfluous from end to end (3 BBAW rows, `{m} ={tn} {ꞽs} {ḫ}`) comes back empty on
    purpose: it has no reading to search, only a raw text to display (A17). An unbalanced
    brace is left for `normalize_mdc` to delete.
    """
    while True:
        # Unwrap `{{…}}` before every pass, so `{{šꜥ{f}.t}}` loses the inner `{f}`
        # first and then keeps `šꜥ.t` instead of being read as two nested `{…}`.
        dropped = SUPERFLUOUS_RE.sub("", DOUBLE_BRACED_RE.sub(r"\1", value))
        if dropped == value:
            return value
        value = dropped


# Stand in for a deleted character / a deleted space in `superfluous_kept_words`;
# never in a reading.
_DELETED = "\x00"
_DELETED_SPACE = "\x01"
_DELETED_SPACES_RE = re.compile(_DELETED_SPACE + "+")


def _blank(text: str) -> str:
    return "".join(_DELETED_SPACE if char.isspace() else _DELETED for char in text)


def superfluous_kept_words(value: str) -> list[str]:
    """`drop_superfluous_text` per whitespace word: one entry per word of `value`,
    holding what survives of it (`''` when the whole word was superfluous).

    A caller that treats words one at a time (the suggestion layer decides loose or
    strict matching per typed word, A54) cannot run `drop_superfluous_text` on each
    word: `{n nswt}` split at the space is `{n` and `nswt}`, two unbalanced braces
    that delete nothing. This runs the same rules over the whole text with the
    deleted characters blanked in place, so the word boundaries, and with them the
    alignment to another word list, survive. `''.join` of the kept words, spaced,
    equals `drop_superfluous_text(value)` up to whitespace.

    A deleted span that spans a space joins what survives on either side into one
    word, as `drop_superfluous_text` does (`h{a b}tp` → `htp`, not `h tp`): the joined
    word is the entry of the first raw word it came from, and the others are `''`.
    """
    while True:
        masked = DOUBLE_BRACED_RE.sub(
            lambda m: _blank("{{") + m.group(1) + _blank("}}"), value
        )
        masked = SUPERFLUOUS_RE.sub(lambda m: _blank(m.group(0)), masked)
        if masked == value:
            break
        value = masked
    kept: list[str] = []
    for chunk in value.split():
        parts = _DELETED_SPACES_RE.split(chunk)
        kept.append("".join(parts).replace(_DELETED, ""))
        kept.extend("" for _ in parts[1:])
    return kept


# TLA's weak-consonant marker, the combining inverted breve below (U+032F): `i̯` and
# `u̯` write the *same* weak radical as the plain yod `ꞽ` and the plain `w`, in an
# edition that marks it. It sits on 36,547 corpus tokens (3.4%: TLA 5,960, AES 4,079,
# BBAW 26,508, Ramses 0) and only ever after `i` or `u` (36,322 / 582), and 554
# lowercased token types are attested both with and without it (`rdi̯`/`rdꞽ`,
# `ḏi̯.t`/`ḏꞽ.t`, `hru̯`/`hrw`). There is no precomposed codepoint for either, so the
# NFC and NFD shapes of the marker are the same two codepoints and one pattern covers
# both. Uppercase is folded to the lowercase letter: the only caller lowercases first,
# and the marker is a notation, not a letter whose case carries information.
WEAK_CONSONANT_MARKER_RE = re.compile("([iuIU])\u032f")
_WEAK_CONSONANT_FOLD = {"i": "ꞽ", "u": "w"}


def fold_weak_consonant_marker(value: str) -> str:
    """Fold TLA's weak-consonant notation: `i̯` → `ꞽ`, `u̯` → `w` (item D′).

    A notation for a weak radical, not a different sound, so two readings that differ
    only in it are the same reading. Composes to NFC first, because the marker is a
    combining character and a caller may hand over either shape.
    """
    text = unicodedata.normalize("NFC", value)
    return WEAK_CONSONANT_MARKER_RE.sub(
        lambda match: _WEAK_CONSONANT_FOLD[match.group(1).lower()], text
    )


# Variant spellings of an Egyptological letter, mapped to the *canonical letter* (not
# to ASCII) so they follow whatever the later ꜣ/ꜥ/ꞽ folds do. `ʿ` (U+02BF) is a common
# substitute for the ayin ꜥ, `ȝ`/`Ȝ` (U+021D/U+021C) for the aleph ꜣ, `ỉ`/`Ỉ` for the yod
# ꞽ. The corpus holds none of them (0 rows), so this only touches queries; before it
# they fell through to normalize_mdc and were deleted (`ʿnḫ` → `nkh`, `ỉr` → `r`).
_LETTER_VARIANTS = str.maketrans({"ʿ": "ꜥ", "ȝ": "ꜣ", "Ȝ": "Ꜣ", "ỉ": "ꞽ", "Ỉ": "Ꞽ"})


def fold_letter_variants(value: str) -> str:
    """`ʿ ȝ ỉ` → `ꜥ ꜣ ꞽ`: one letter, two encodings. Lossless — no two different
    consonants are merged — so the strict reading key uses it as well as the search
    key (A16/A54)."""
    return value.translate(_LETTER_VARIANTS)


# The yod's other encodings and two letter variants that the *search* key folds
# (`normalize_transliteration`: `ꞽ j ı ı͗ i` → `i`, `ḳ` → `q`, `ṱ` → `t`), mapped to one
# letter instead of to ASCII. They are one letter in different editions' conventions
# (Hannig/Leipzig and the St Andrews data write `j`, ASCII typists and Ramses `i`,
# BBAW `ı͗`; Nederhof accepts merging i/j), so mapping them together merges no two
# consonants: ꜣ/ꜥ, ḥ/h, ḫ/ẖ, ṯ/t and ḏ/d all stay distinct. Not part of
# `normalize_notation`: the search key keeps its own order of folds (its bracketed-yod
# rule matches `(ı)` but not `(ı͗)`), and the grouping key is left as it is.
_YOD_ALIASES = str.maketrans({"ı": "ꞽ", "j": "ꞽ", "i": "ꞽ", "ḳ": "q", "ṱ": "t"})


def fold_strict_aliases(value: str) -> str:
    """`j ı ı͗ i` → `ꞽ`, `ḳ` → `q`, `ṱ` → `t` on already-normalised (NFC, lower-case)
    text whose weak-consonant marker `i̯` was folded first. Used by the strict
    comparison form in app.services.suggestions, so a query letter the search key
    accepts is never a different letter there (final audit, search-ranking-1)."""
    return value.replace("ı\u0357", "ꞽ").translate(_YOD_ALIASES)

# ---------------------------------------------------------------------------
# Hieroglyph character classes
#
# Three kinds of codepoint appear in sign strings and each needs different handling:
#
#   signs            U+13000-1342F (Egyptian Hieroglyphs) and U+13460-143FF
#                    (Extended-A). These are the content.
#   format controls  U+13430-1345F: quadrat joiners, insertion and enclosure marks
#                    used by layout-aware editors. They say how signs are arranged,
#                    not which signs there are. The corpus contains none, so a pasted
#                    query carrying them could never match — they are deleted. Their
#                    *structure* is read off first by `quadrat_hints` (item B), which
#                    turns "these signs share a quadrat" into segmenter hints.
#   placeholders     Private Use Area codepoints this module allocates for TLA's
#                    `<g>M12B</g>` markup (signs that have no Unicode codepoint yet).
#                    See `markup_to_placeholder`.
#
# Variation selectors (U+FE00-FE0F, U+E0100-E01EF) attach to the preceding sign and
# are deleted rather than treated as separators: replacing one with a space used to
# split a sign group in two, misaligning every group after it.
# ---------------------------------------------------------------------------
SIGN_CLASS = r"\U00013000-\U0001342F\U00013460-\U000143FF"
FORMAT_CONTROL_CLASS = r"\U00013430-\U0001345F"
PLACEHOLDER_CLASS = r"\U000F0000-\U000FFFFD\U00100000-\U0010FFFD"
VARIATION_SELECTOR_CLASS = r"\uFE00-\uFE0F\U000E0100-\U000E01EF"

# Real signs only: the detector that routes a query to the sign index. Format
# controls and placeholders alone must not make a query count as hieroglyphic.
HIEROGLYPH_RE = re.compile(f"[{SIGN_CLASS}]")
# Everything that may stay inside a normalised sign group.
NON_GROUP_CHAR_RE = re.compile(f"[^{SIGN_CLASS}{PLACEHOLDER_CLASS}\\s]")
DELETE_IN_GROUP_RE = re.compile(f"[{FORMAT_CONTROL_CLASS}{VARIATION_SELECTOR_CLASS}]")
PLACEHOLDER_RE = re.compile(f"[{PLACEHOLDER_CLASS}]")

# TLA writes a sign that has no Unicode codepoint as <g>GARDINER_ID</g>. The Late
# Egyptian corpus also nests them — <g><g>US9No2VARA</g></g> — so the inner tag is
# unwrapped first and the outer one then matches normally.
G_NESTED_RE = re.compile(r"<g>\s*(<g>[^<>]*</g>)\s*</g>")
G_MARKUP_RE = re.compile(r"<g>([^<>]*)</g>")

# A run of non-glyph characters sitting *directly between two signs*, with no space
# on either side, is noise inside one sign group — an editorial bracket, a stray
# Latin letter left in the source, a doubled parenthesis. Turning it into a space
# (the default for anything non-glyph) would split the group and misalign the whole
# sentence, which is the same defect the <g> handling exists to prevent. Whitespace
# around such a character still separates groups, so "(1) 𓊵𓏙 — 𓇓𓏏" is unaffected.
INTRA_GROUP_NOISE_RE = re.compile(
    f"(?<=[{SIGN_CLASS}{PLACEHOLDER_CLASS}])[^{SIGN_CLASS}{PLACEHOLDER_CLASS}\\s]+"
    f"(?=[{SIGN_CLASS}{PLACEHOLDER_CLASS}])"
)

# Visually identical or interchangeable codepoints, folded to one canonical form on
# both the corpus and the query side. Each entry needs a reason; do not fold signs
# that merely look alike to a non-specialist.
#
#   U+133FC Z15B (three vertical strokes) -> U+133E5 Z2 (plural strokes). Text
#   editors and PDFs emit either for the plural marker; the corpus uses Z2 1,763
#   times and Z15B 7 times. This was the mismatch in the first expert trial.
SIGN_VARIANTS: dict[str, str] = {
    "\U000133FC": "\U000133E5",
}
_SIGN_VARIANT_TABLE = str.maketrans(SIGN_VARIANTS)

# Placeholder registry. A placeholder is a Private Use codepoint derived from the
# markup content by a hash, so the same sign ID maps to the same codepoint in every
# process and the reading model can treat it as one more glyph. When two IDs hash to
# the same slot the later one probes forward; that is deterministic as long as IDs
# are first seen in the same order, which holds because the corpus CSV is loaded in
# file order before any query is normalised. The registry also lets the UI turn a
# placeholder back into its ID for display.
_PLACEHOLDER_BASE = 0xF0000
_PLACEHOLDER_SLOTS = 0x10FFFD - 0xF0000 + 1  # both supplementary PUA planes
_PLACEHOLDER_SKIP = {0xFFFFE, 0xFFFFF}  # noncharacters between the two planes
_placeholder_to_id: dict[str, str] = {}
_id_to_placeholder: dict[str, str] = {}
# (existing id, new id) pairs that shared a hash slot and were resolved by probing.
# Informational; the loader reports the count.
PLACEHOLDER_COLLISIONS: list[tuple[str, str]] = []

# A bare Gardiner sign number standing alone as a token (e.g. "V31Aa" between two sign
# groups) is the same thing as <g>V31Aa</g> without its markup; one corpus row writes
# it that way. Only whole whitespace-delimited tokens qualify.
BARE_GARDINER_TOKEN_RE = re.compile(r"(?<!\S)(?:[A-Z]|Aa|NL|NU)\d{1,3}[A-Za-z]{0,2}(?!\S)")

# TLA restoration brackets ⟦ ⟧ wrap a sign inside a group; they are deleted, not
# spaced, so the group they sit in is not split.
EDITORIAL_BRACKETS_RE = re.compile(r"[\u27e6\u27e7\u2e22-\u2e25\u2329\u232a\u27e8\u27e9]")


def markup_to_placeholder(sign_id: str) -> str:
    """One Private Use codepoint standing in for a `<g>…</g>` sign ID."""
    key = normalize_whitespace(sign_id) or "(empty)"
    known = _id_to_placeholder.get(key)
    if known is not None:
        return known
    slot = zlib.crc32(key.encode("utf-8")) % _PLACEHOLDER_SLOTS
    probed = False
    while True:
        codepoint = _PLACEHOLDER_BASE + (slot % _PLACEHOLDER_SLOTS)
        if codepoint in _PLACEHOLDER_SKIP:
            slot += 1
            continue
        placeholder = chr(codepoint)
        existing = _placeholder_to_id.get(placeholder)
        if existing is None:
            break
        if not probed:
            PLACEHOLDER_COLLISIONS.append((existing, key))
            probed = True
        slot += 1
    _placeholder_to_id[placeholder] = key
    _id_to_placeholder[key] = placeholder
    return placeholder


def placeholder_to_markup(placeholder: str) -> str:
    """The sign ID behind a placeholder, e.g. 'D77'; '?' when unknown."""
    return _placeholder_to_id.get(placeholder, "?")


def is_placeholder(char: str) -> bool:
    return bool(PLACEHOLDER_RE.fullmatch(char))


def display_sign_group(group: str) -> str:
    """Render a normalised sign group for humans: placeholders become ⟨ID⟩."""
    return PLACEHOLDER_RE.sub(lambda m: f"⟨{placeholder_to_markup(m.group(0))}⟩", group)


def nfc(value: object) -> str:
    """Canonical composition. Egyptological transliteration mixes precomposed and
    combining forms of the same letter (ẖ appears both ways in the corpus), and they
    only compare equal after composition. Every normaliser starts here."""
    return unicodedata.normalize("NFC", str(value))


def contains_hieroglyphs(value: object) -> bool:
    """True when the text carries Unicode Egyptian hieroglyphs.

    Used to decide whether a query should be matched against sign columns instead
    of transliteration columns. `normalize_mdc` deletes these codepoints, so without
    this check a glyph query normalises to an empty string and matches nothing.
    """
    return bool(HIEROGLYPH_RE.search(str(value)))


def normalize_hieroglyphs(value: object) -> str:
    """Keep only sign groups, preserving whitespace as the group separator.

    The TLA data separates sign groups with spaces and those groups line up
    one-to-one with transliteration tokens, so whitespace is meaningful and must
    survive normalisation — and nothing else may introduce or remove a space.

    Steps, in order:
      1. NFC.
      2. `<g>ID</g>` markup becomes a single placeholder codepoint, so a sign
         without a Unicode codepoint stays one sign instead of vanishing or
         splitting its group.
      3. Format controls, variation selectors and editorial brackets ⟦⟧ are
         deleted (not spaced), so they never split a group — as is any other
         non-glyph run sitting directly between two signs.
      4. Variant codepoints are folded to their canonical sign.
      5. Anything else that is not a sign becomes a space.
    """
    text = nfc(value)
    if not text.strip():
        return ""
    text = G_NESTED_RE.sub(lambda m: m.group(1), text)
    text = G_MARKUP_RE.sub(lambda m: markup_to_placeholder(m.group(1)), text)
    text = BARE_GARDINER_TOKEN_RE.sub(lambda m: markup_to_placeholder(m.group(0)), text)
    text = DELETE_IN_GROUP_RE.sub("", text)
    text = EDITORIAL_BRACKETS_RE.sub("", text)
    text = INTRA_GROUP_NOISE_RE.sub("", text)
    text = text.translate(_SIGN_VARIANT_TABLE)
    text = NON_GROUP_CHAR_RE.sub(" ", text)
    return normalize_whitespace(text)


def normalize_whitespace(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.strip())


# ---------------------------------------------------------------------------
# Quadrat hints (item B, 2026-09-06)
#
# `normalize_hieroglyphs` deletes U+13430-1345F because the corpus contains none of
# them, so a query carrying them could never match. But they are not noise: they say
# how the pasted signs were laid out, and "these two signs sit in one quadrat" is
# evidence — weak evidence — that a word boundary does not fall between them.
# `quadrat_hints` reads that structure off the raw paste *before* it is thrown away
# and returns it as boundary indices the segmenter may penalise cutting at
# (`SegmentationWeights.quadrat_crossed`).
#
# Which controls carry adjacency information:
#
#   13430-13436  joiners: vertical, horizontal, insert at top/bottom start/end,
#                overlay middle. The signs either side share a quadrat.
#   13439-1343B  insert at middle/top/bottom. Same reading.
#   13437/13438  begin/end segment       -> everything strictly inside is one unit
#   1343C/1343D  begin/end enclosure     -> ditto (cartouche and friends)
#   1343E/1343F  begin/end walled enclosure
#   13440        mirror horizontally     -> about one sign's orientation, no adjacency
#   13441-13446  blanks and lost-sign shapes  -> no adjacency
#   13447-13455  damage modifiers             -> no adjacency
#
# Positions are indices into the *normalised* sign stream, so they line up with
# `glyph_stream(normalize_hieroglyphs(value).split())`: a position b means "a group
# would end before sign b". This is why the hints cannot simply be counted off the
# raw string - placeholder folding, bracket deletion and the intra-group noise rule
# all move signs around first.
# ---------------------------------------------------------------------------
QUADRAT_JOINERS = frozenset(
    [*range(0x13430, 0x13437), *range(0x13439, 0x1343C)]
)
# (opening codepoint, closing codepoint) for the bracketing controls.
QUADRAT_BRACKETS: dict[int, int] = {
    0x13437: 0x13438,  # begin/end segment
    0x1343C: 0x1343D,  # begin/end enclosure
    0x1343E: 0x1343F,  # begin/end walled enclosure
}
_QUADRAT_CLOSERS = {close: open_ for open_, close in QUADRAT_BRACKETS.items()}

# The cartouche written with *signs* instead of the enclosure controls above:
# V011A (U+13379) opens it, V011B (U+1337A) closes it. These survive
# `normalize_hieroglyphs` — they are ordinary signs to every character class here —
# so they reach the segmenter, which until now was free to cut between them.
#
# What the corpus does (data/processed/examples.csv, 130,472 rows, checked
# 2026-10-26): 1,305 rows carry one of the two signs; 1,841 sign groups contain a
# matched V011A…V011B pair, against 13 groups holding only one half of a pair, and
# only 5 rows split a cartouche across two groups. 0 groups have them out of order.
# So "a cartouche is one sign group" is what the data says, at 99.3% of the groups
# that contain either sign, and `app.services.segmentation` enforces it.
CARTOUCHE_OPEN_SIGN = 0x13379
CARTOUCHE_CLOSE_SIGN = 0x1337A


def cartouche_spans(stream: str) -> list[tuple[int, int]]:
    """Outermost matched cartouche spans in a glyph stream, as half-open `(start, end)`.

    `start` indexes the opening V011A and `end` is one past the closing V011B, so
    the boundary positions *inside* the cartouche are `range(start + 1, end)` in the
    indexing `app.services.segmentation.glyph_stream` uses. A closing sign with no
    opener is ignored: an unmatched half is not structure anybody can trust (the same
    rule `quadrat_hints` applies to the enclosure controls).

    Matching is by stack, and an unclosed opener is simply left on it. Counting
    nesting *depth* instead looked equivalent and was not: it reported a span only
    where the depth returned to zero, so a stray opener earlier in the line
    suppressed every complete cartouche after it — `OPEN A OPEN B CLOSE` found
    nothing at all, and in `OPEN OPEN X CLOSE` the one pair that genuinely closes was
    lost. Both shapes occur: the corpus holds 13 groups carrying one half of a pair.

    Of the pairs that do close, one enclosed by another is dropped, so the result is
    the outermost completed pairs and the spans never overlap. The returned spans are
    in order of their opening sign.
    """
    completed: list[tuple[int, int]] = []
    stack: list[int] = []
    for position, char in enumerate(stream):
        code = ord(char)
        if code == CARTOUCHE_OPEN_SIGN:
            stack.append(position)
        elif code == CARTOUCHE_CLOSE_SIGN and stack:
            completed.append((stack.pop(), position + 1))
    spans = [
        (start, end)
        for start, end in completed
        if not any(
            other_start <= start and end <= other_end and (other_start, other_end) != (start, end)
            for other_start, other_end in completed
        )
    ]
    spans.sort()
    return spans
FORMAT_CONTROL_RE = re.compile(f"[{FORMAT_CONTROL_CLASS}]")
# The same three rules as `normalize_hieroglyphs`, but with the format controls
# treated as part of a sign group instead of deleted, so their position survives.
_GROUP_CHAR_CLASS = f"{SIGN_CLASS}{PLACEHOLDER_CLASS}{FORMAT_CONTROL_CLASS}"
_DELETE_KEEPING_CONTROLS_RE = re.compile(f"[{VARIATION_SELECTOR_CLASS}]")
_NON_GROUP_CHAR_KEEPING_CONTROLS_RE = re.compile(f"[^{_GROUP_CHAR_CLASS}\\s]")
_INTRA_GROUP_NOISE_KEEPING_CONTROLS_RE = re.compile(
    f"(?<=[{_GROUP_CHAR_CLASS}])[^{_GROUP_CHAR_CLASS}\\s]+(?=[{_GROUP_CHAR_CLASS}])"
)


def _normalize_keeping_controls(value: object) -> str:
    """`normalize_hieroglyphs`, except that format controls are kept in place.

    Every step is the same and in the same order; only the character classes differ,
    so that a control neither splits a group (it is treated as group content) nor
    vanishes. Deleting the controls from the result must give `normalize_hieroglyphs`
    back exactly - that is the invariant `quadrat_hints` asserts on its own output.
    """
    text = nfc(value)
    if not text.strip():
        return ""
    text = G_NESTED_RE.sub(lambda m: m.group(1), text)
    text = G_MARKUP_RE.sub(lambda m: markup_to_placeholder(m.group(1)), text)
    text = BARE_GARDINER_TOKEN_RE.sub(lambda m: markup_to_placeholder(m.group(0)), text)
    text = _DELETE_KEEPING_CONTROLS_RE.sub("", text)
    text = EDITORIAL_BRACKETS_RE.sub("", text)
    text = _INTRA_GROUP_NOISE_KEEPING_CONTROLS_RE.sub("", text)
    text = text.translate(_SIGN_VARIANT_TABLE)
    text = _NON_GROUP_CHAR_KEEPING_CONTROLS_RE.sub(" ", text)
    return normalize_whitespace(text)


def quadrat_hints(value: object) -> tuple[list[str], frozenset[int]]:
    """Read the layout controls of a paste as "do not cut here" positions.

    Returns `(groups_as_pasted, no_cut)`:

      groups_as_pasted  exactly `normalize_hieroglyphs(value).split()` - the caller
                        can use this instead of normalising a second time.
      no_cut            glyph-stream boundary indices (the indexing of
                        `app.services.segmentation.glyph_stream`) that fall between
                        two signs a format control says share a quadrat.

    A joiner contributes the one boundary between the sign before it and the sign
    after it; the two must be immediate neighbours in the normalised stream (only
    other controls may sit between them, never a group-separating space). A
    bracketing pair contributes every boundary strictly inside it, so a three-sign
    cartouche yields two positions. Unmatched or empty brackets contribute nothing.
    Positions 0 and len(stream) are never returned: they are not boundaries.
    """
    text = _normalize_keeping_controls(value)
    if not text:
        return [], frozenset()

    groups: list[str] = []
    # Sign index at the *start* of each character of `text`, plus a flag saying what
    # the character is. Signs are the characters that survive into the stream.
    signs_before: list[int] = []
    seen = 0
    for char in text:
        signs_before.append(seen)
        if char != " " and not FORMAT_CONTROL_RE.match(char):
            seen += 1
    signs_before.append(seen)
    total = seen

    for chunk in text.split(" "):
        stripped = FORMAT_CONTROL_RE.sub("", chunk)
        if stripped:
            groups.append(stripped)

    no_cut: set[int] = set()
    stack: list[int] = []
    for position, char in enumerate(text):
        code = ord(char)
        if code in QUADRAT_JOINERS:
            left = position - 1
            while left >= 0 and FORMAT_CONTROL_RE.match(text[left]):
                left -= 1
            right = position + 1
            while right < len(text) and FORMAT_CONTROL_RE.match(text[right]):
                right += 1
            if left < 0 or right >= len(text):
                continue
            if text[left] == " " or text[right] == " ":
                continue
            boundary = signs_before[position]
            if 0 < boundary < total:
                no_cut.add(boundary)
        elif code in QUADRAT_BRACKETS:
            stack.append(position)
        elif code in _QUADRAT_CLOSERS:
            if not stack or ord(text[stack[-1]]) != _QUADRAT_CLOSERS[code]:
                continue  # unmatched closer: no structure to trust
            opener = stack.pop()
            first = signs_before[opener]
            last = signs_before[position]  # one past the last sign inside
            for boundary in range(first + 1, last):
                if 0 < boundary < total:
                    no_cut.add(boundary)

    return groups, frozenset(no_cut)


def normalize_text(value: str) -> str:
    # Compose again after lowercasing: capital H̱ has no precomposed codepoint, so it is
    # `H` + U+0331 until `.lower()` makes it `h` + U+0331, which only NFC turns into ẖ.
    value = nfc(nfc(value).lower()).strip()
    return normalize_whitespace(value)


def normalize_mdc(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("*", ":")
    # A suffix pronoun is a token of its own in the corpus (`ḏd =f` is indexed as
    # `djd f`), so a `=` typed without a space in front of it has to separate rather
    # than vanish: deleting it turned `ḏd=f` into the single token `djdf`, which
    # matches nothing. The corpus side is unaffected — no stored value contains `=`.
    value = SUFFIX_MARKER_RE.sub(" ", value)
    value = FRACTION_SLASH_RE.sub("_", value)
    value = NON_ALNUM_KEEP_COLON_RE.sub("", value)
    value = MULTI_COLON_RE.sub(":", value)
    return normalize_whitespace(value)


def normalize_sign_sequence(value: str) -> str:
    return normalize_whitespace(normalize_text(value))


def normalize_notation(value: str) -> str:
    """The *lossless* notation normalisation every transliteration comparison shares.

    NFC + lower case, superfluous `{…}` text deleted (`drop_superfluous_text`), TLA's
    weak-consonant marker folded (`i̯` → `ꞽ`, `u̯` → `w`), variant letter encodings
    mapped to the canonical letter (`ʿ ȝ ỉ` → `ꜥ ꜣ ꞽ`) and the plural notation folded
    to `.w`. Every consonant stays as written (ꜣ ≠ ꜥ, ḥ ≠ h), so the strict comparison
    in app.services.suggestions builds on this (adding `fold_strict_aliases` for the
    yod encodings and `ḳ`/`ṱ`), and `normalize_transliteration` adds the lossy ASCII
    fold on top. Together they make sure a query letter the search key accepts can
    never be one the suggestion layer silently treats as a different letter.
    """
    value = normalize_text(value)
    value = drop_superfluous_text(value)
    value = fold_weak_consonant_marker(value)
    value = fold_letter_variants(value)
    return fold_plural_marker(value)


def normalize_transliteration(value: str) -> str:
    """ASCII search fold for transliteration (ḥtp → htp, ḏ → dj …).

    This is deliberately lossy: it exists so a user typing plain ASCII can hit the
    corpus. It merges ꜣ/ꜥ and ḥ/h, so it must never be used as an identity key for
    readings — see `strict_reading_key` in app.services.suggestions for that.
    NFC runs first (inside normalize_text) so a decomposed ẖ folds to kh like its
    precomposed twin instead of leaking through as a bare h.

    The yod is folded to `i`, never deleted. Until 2026-09-01 `ꞽ` fell through to
    `normalize_mdc`, which stripped it, so `ꞽri̯.n` was indexed as `rin`: 71% of corpus
    rows contain ꞽ, ASCII typists write `i`, MdC and Gardiner-school typists write
    `j`, and the bbaw_egyptian and Ramses datasets write `j` — none of them could
    match. `ꞽ`, `j`, dotless `ı` (+ its combining half ring U+0357) all become `i`;
    `ṱ` becomes `t` and `ḳ` becomes `q` for the same reason.

    Before any of that the text goes through `normalize_notation`, the lossless part
    that the suggestion layer shares: superfluous `{…}` text is deleted, the
    weak-consonant marker, the variant letters ʿ ȝ ỉ and the plural notation are folded.
    """
    value = normalize_notation(value)
    # `n(.ꞽ).t`, `(ꞽ)r(.ꞽ)-pꜥ.t`: a yod in round brackets is one the editor supplied,
    # not one written on the wall. It is dropped so `n.t` and `n(.ꞽ).t` stay one
    # search key — which they always were, because the old fold deleted every yod;
    # keeping written yods must not split 4,438 rows away from what a reader types.
    value = PARENTHESISED_YOD_RE.sub("", value)
    value = value.replace("\u0357", "")  # combining right half ring on ı
    value = value.replace("ꞽ", "i")
    value = value.replace("ı", "i")
    value = value.replace("j", "i")
    value = value.replace("ṱ", "t")
    value = value.replace("ḳ", "q")
    value = value.replace("ꜣ", "a")
    value = value.replace("ꜥ", "a")
    value = value.replace("ḥ", "h")
    value = value.replace("ḫ", "kh")
    value = value.replace("ẖ", "kh")
    value = value.replace("š", "sh")
    value = value.replace("ṯ", "tj")
    value = value.replace("ḏ", "dj")
    return normalize_whitespace(value)


def search_fold(value: object) -> str:
    """The one key both the corpus index and a query are reduced to.

    `normalize_transliteration` folds the Egyptological letters to ASCII and
    `normalize_mdc` drops the editorial apparatus (dots, brackets, breves) and
    splits on the suffix marker. Running them in this order is what makes a typed
    reading comparable to a corpus row — and both sides must call *this* function,
    not one of the halves. They did not: the corpus was indexed with the pair and
    the query was cleaned with `normalize_mdc` alone, which does not fold, it
    deletes, so `ꜥḥꜥ.n stẖ qnd` reached the search as `n st qnd`.
    """
    return normalize_mdc(normalize_transliteration(str(value)))


def normalize_label(value: str) -> str:
    return normalize_whitespace(normalize_text(value))


def normalize_pipe_list(value: str) -> str:
    raw = normalize_text(value)
    if not raw:
        return ""
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    return "|".join(parts)


def pipe_list_to_set(value: str) -> set[str]:
    norm = normalize_pipe_list(value)
    if not norm:
        return set()
    return {part.strip() for part in norm.split("|") if part.strip()}


def parse_bool(value: object) -> bool:
    text = normalize_text(str(value))
    return text in {"1", "true", "yes", "y", "t"}
