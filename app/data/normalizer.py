from __future__ import annotations

import re
import unicodedata
import zlib

WHITESPACE_RE = re.compile(r"\s+")
# `=` (and the Egyptological `⸗`) mark a suffix pronoun. They separate tokens.
SUFFIX_MARKER_RE = re.compile(r"[=\u2e17]")
NON_ALNUM_KEEP_COLON_RE = re.compile(r"[^a-z0-9:_\-\s]")
MULTI_COLON_RE = re.compile(r":+")

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
#                    query carrying them could never match — they are deleted.
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


def normalize_text(value: str) -> str:
    value = nfc(value).lower().strip()
    return normalize_whitespace(value)


def normalize_mdc(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("*", ":")
    # A suffix pronoun is a token of its own in the corpus (`ḏd =f` is indexed as
    # `djd f`), so a `=` typed without a space in front of it has to separate rather
    # than vanish: deleting it turned `ḏd=f` into the single token `djdf`, which
    # matches nothing. The corpus side is unaffected — no stored value contains `=`.
    value = SUFFIX_MARKER_RE.sub(" ", value)
    value = NON_ALNUM_KEEP_COLON_RE.sub("", value)
    value = MULTI_COLON_RE.sub(":", value)
    return normalize_whitespace(value)


def normalize_sign_sequence(value: str) -> str:
    return normalize_whitespace(normalize_text(value))


def normalize_transliteration(value: str) -> str:
    """ASCII search fold for transliteration (ḥtp → htp, ḏ → dj …).

    This is deliberately lossy: it exists so a user typing plain ASCII can hit the
    corpus. It merges ꜣ/ꜥ and ḥ/h, so it must never be used as an identity key for
    readings — see `strict_reading_key` in app.services.suggestions for that.
    NFC runs first (inside normalize_text) so a decomposed ẖ folds to kh like its
    precomposed twin instead of leaking through as a bare h.
    """
    value = normalize_text(value)
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
