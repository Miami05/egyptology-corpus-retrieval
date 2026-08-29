"""One human-readable line saying which signals actually ranked this row.

The line must show the signals that produced the ranking. The old version printed
only the transliteration signals, so every hit for a hieroglyph query read
`fuzzy=0.00 | tfidf=0.00` — the glyph signals that did all the work were invisible,
which made correct rankings look arbitrary.
"""

from __future__ import annotations

import pandas as pd


def _value(row: pd.Series, key: str) -> float:
    return float(row.get(key, 0.0) or 0.0)


def build_evidence(row: pd.Series) -> str:
    bits: list[str] = []

    if _value(row, "exact_bonus") == 1.0:
        bits.append("matched by exact normalized MdC")
    if _value(row, "glyph_exact_bonus") == 1.0:
        bits.append("exact sign-group match")

    glyph_bits: list[str] = []
    for key, label in [
        ("glyph_idf_overlap_score", "sign IDF overlap"),
        ("glyph_order_score", "sign order"),
        ("glyph_overlap_score", "sign overlap"),
    ]:
        value = _value(row, key)
        if value > 0.0:
            glyph_bits.append(f"{label}={value:.2f}")
    if glyph_bits:
        bits.append("sign match: " + " · ".join(glyph_bits))

    text_bits: list[str] = []
    for key, label in [
        ("idf_overlap_score", "IDF overlap"),
        ("overlap_score", "token overlap"),
        ("fuzzy_score", "fuzzy"),
        ("tfidf_score", "char ngram"),
    ]:
        value = _value(row, key)
        if value > 0.0:
            text_bits.append(f"{label}={value:.2f}")
    if text_bits:
        bits.append("text match: " + " · ".join(text_bits))

    reading_order = _value(row, "reading_order_overlap")
    if reading_order > 0.0:
        bits.append(f"reading order contributed ({reading_order:.2f})")

    if not bits:
        bits.append("no matching signal — ranked by tie order only")
    return " | ".join(bits)
