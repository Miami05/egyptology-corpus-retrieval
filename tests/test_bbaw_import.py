"""The `phiwi/bbaw_egyptian` importer: Gardiner codes, MdC grouping, conventions.

Each test pins a rule the importer relies on. The grouping test uses the row that was
verified by hand before the importer existed: 11 transcription tokens, 11 sign groups.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_bbaw_egyptian import (  # noqa: E402
    GARDINER_TO_UNICODE,
    convert,
    dedup_key,
    parse_glyph_field,
    sign_for_code,
    to_corpus_convention,
)

VERIFIED_GLYPHS = (
    "D54 *Z7 -M17 *N35 D21 I9 M20 -X1 *Z4 -A1 Q3 -N35 D21 F42 -D21 -A2 N35 I9 "
    "4\\R90 *W24 O34 -Q3 -O50"
)
VERIFIED_TRANSCRIPTION = "jwi̯.jn r =f sḫ,tj pn r spr n =f 4.nw sp"


# --- Gardiner code -> Unicode ------------------------------------------------


def test_known_codes_map_to_the_unicode_block() -> None:
    assert sign_for_code("A1") == "\U00013000"
    assert sign_for_code("D21") == "\U0001308B"
    assert sign_for_code("N35") == "\U00013216"
    assert sign_for_code("Aa1") == "\U0001340D"


def test_code_spelling_variants_meet_on_one_sign() -> None:
    """`Aa1`, `AA1` and `aa001` are the same sign to a hieroglyph editor."""
    assert sign_for_code("AA1") == sign_for_code("Aa1") == sign_for_code("aa001")


def test_a_code_without_a_codepoint_becomes_placeholder_markup() -> None:
    """The normaliser already turns `<g>ID</g>` into a stable placeholder sign, so a
    code Unicode never encoded still occupies exactly one slot in its group."""
    assert sign_for_code("Ff100") == "<g>Ff100</g>"
    assert sign_for_code("US9No2VARA") == "<g>US9No2VARA</g>"
    assert len(GARDINER_TO_UNICODE) > 1000


# --- grouping ------------------------------------------------------------------


def test_the_verified_row_yields_one_group_per_word() -> None:
    parsed = parse_glyph_field(VERIFIED_GLYPHS)
    assert not parsed.lacuna and not parsed.unreadable
    assert len(parsed.groups) == len(VERIFIED_TRANSCRIPTION.split()) == 11
    # The rotation modifier on `4\R90` is dropped and the bare digit becomes a
    # numeral placeholder that stays joined to `*W24` in the same word.
    assert parsed.groups[9] == "<g>NUM4</g>" + sign_for_code("W24")


def test_group_zero_is_the_four_signs_of_the_first_word() -> None:
    parsed = parse_glyph_field("D54 *Z7 -M17 *N35 D21")
    assert parsed.groups == [
        sign_for_code("D54") + sign_for_code("Z7") + sign_for_code("M17") + sign_for_code("N35"),
        sign_for_code("D21"),
    ]


def test_uncertainty_brackets_and_erasures_do_not_split_or_merge_words() -> None:
    # `[? *A26 *?]` is one uncertain word; `[[ *X8 *]]` an erased/restored one.
    parsed = parse_glyph_field("M17 -[? *A26 *?] S34 [[ *X8 *]] N35")
    assert parsed.groups == [
        sign_for_code("M17") + sign_for_code("A26"),
        sign_for_code("S34"),
        sign_for_code("X8"),
        sign_for_code("N35"),
    ]


def test_ligature_and_annotations() -> None:
    """`F39&Aa1` is two signs; `"lb"` (line break) and `"var"` are not signs at all."""
    parsed = parse_glyph_field('M17 -F39&Aa1 -"lb" -A2 A282 *"var"')
    assert parsed.groups == [
        sign_for_code("M17") + sign_for_code("F39") + sign_for_code("Aa1") + sign_for_code("A2"),
        sign_for_code("A282"),
    ]


def test_lacuna_and_unreadable_sign_mark_the_row_for_dropping() -> None:
    assert parse_glyph_field("D21 -// N35").lacuna
    assert parse_glyph_field('D21 *"?" N35').unreadable
    assert parse_glyph_field('D21 -"⸮" N35').unreadable
    assert not parse_glyph_field("D21 -/ N35").lacuna  # `/` is shading, not a gap


# --- transcription convention ------------------------------------------------


def test_comma_becomes_dot_and_plural_braces_are_dropped() -> None:
    assert to_corpus_convention("sḫ,tj pn ḥm{,pl}-nṯr ≡f") == "sḫ.tj pn ḥm.pl-nṯr =f"
    assert to_corpus_convention("jwi̯.jn r =f") == "jwi̯.jn r =f"


def test_dedup_key_is_yod_insensitive() -> None:
    """The same sentence written `jwi̯` (BBAW) and `ꞽwi̯` (TLA) must count once."""
    assert dedup_key("jwi̯.jn r =f") == dedup_key("ꞽwi̯.jn r =f") == dedup_key("iwi.jn r =f")


# --- end to end on a tiny frame -----------------------------------------------


def test_convert_keeps_aligned_rows_and_counts_the_rest() -> None:
    frame = pd.DataFrame(
        {
            "transcription": [VERIFIED_TRANSCRIPTION, "ḏd =f", "ḏd =f", "text only", ""],
            "translation": ["a", "b", "c", "d", "e"],
            "hieroglyphs": [VERIFIED_GLYPHS, "I10 -D46 // I9", "I10 -D46 I9 N35", "", "A1"],
        }
    )
    rows, report = convert(frame, include_text_only=False)
    assert report.aligned == 1
    assert report.dropped_lacuna == 1
    assert report.dropped_mismatch == 1  # 3 groups for 2 tokens
    assert report.text_only == 1
    assert report.dropped_empty_transcription == 1
    assert list(rows["source"]) == ["BBAW"]
    assert rows.iloc[0]["source_sentence_id"] == "B000000"
    assert rows.iloc[0]["transliteration_gold"] == "jwi̯.jn r =f sḫ.tj pn r spr n =f 4.nw sp"

    rows, report = convert(frame, include_text_only=True)
    assert report.text_only == 1 and len(rows) == 2
    assert rows.iloc[1]["hieroglyphs"] == ""
