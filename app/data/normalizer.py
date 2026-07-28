from __future__ import annotations

import re

WHITESPACE_RE = re.compile(r"\s+")
NON_ALNUM_KEEP_COLON_RE = re.compile(r"[^a-z0-9:_\-\s]")
MULTI_COLON_RE = re.compile(r":+")

# Egyptian Hieroglyphs: U+13000-U+1342F, plus the format controls and the extended
# block used for quadrat layout. Anything here is a sign, not transliteration.
HIEROGLYPH_RE = re.compile(
    r"[\U00013000-\U0001342F\U00013430-\U0001345F\U00013460-\U000143FF]"
)
NON_HIEROGLYPH_RE = re.compile(
    r"[^\U00013000-\U0001342F\U00013430-\U0001345F\U00013460-\U000143FF\s]"
)


def contains_hieroglyphs(value: object) -> bool:
    """True when the text carries Unicode Egyptian hieroglyphs.

    Used to decide whether a query should be matched against sign columns instead
    of transliteration columns. `normalize_mdc` deletes these codepoints, so without
    this check a glyph query normalises to an empty string and matches nothing.
    """
    return bool(HIEROGLYPH_RE.search(str(value)))


def normalize_hieroglyphs(value: object) -> str:
    """Keep only hieroglyphs, preserving whitespace as the sign-group separator.

    The TLA data separates quadrats/sign groups with spaces and those groups line up
    one-to-one with transliteration tokens, so whitespace is meaningful and must
    survive normalisation.
    """
    text = str(value)
    if not text.strip():
        return ""
    text = NON_HIEROGLYPH_RE.sub(" ", text)
    return normalize_whitespace(text)


def normalize_whitespace(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.strip())


def normalize_text(value: str) -> str:
    value = str(value).lower().strip()
    return normalize_whitespace(value)


def normalize_mdc(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("*", ":")
    value = NON_ALNUM_KEEP_COLON_RE.sub("", value)
    value = MULTI_COLON_RE.sub(":", value)
    return normalize_whitespace(value)


def normalize_sign_sequence(value: str) -> str:
    return normalize_whitespace(normalize_text(value))


def normalize_transliteration(value: str) -> str:
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
