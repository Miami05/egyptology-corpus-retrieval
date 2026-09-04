"""The Ramses Transliteration Corpus importer: character mapping, word splitting,
lacuna handling and id stability.

The real sample lines below are copied verbatim from `tgt-train.txt` / `src-sep-train.txt`
(line numbers noted) so the tests pin the importer against actual corpus content, not
invented examples.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import alignment_report  # noqa: E402
from app.data.normalizer import normalize_hieroglyphs  # noqa: E402
from scripts.import_ramses import (  # noqa: E402
    content_id,
    convert,
    convert_word,
    group_src_sep,
    has_bracket_lacuna,
    is_glyph_lacuna_code,
    is_translit_lacuna_word,
    rejoin_words,
    to_schema,
)

# tgt-train.txt line 2: "i w _ i w _ = i _ r _ s w r _ m _ = f _"
LINE_2_TOKENS = list("i w _ i w _ = i _ r _ s w r _ m _ = f _".split())
# src-sep-train.txt line 2
LINE_2_SRCSEP = "M17 Z7 _ M17 Z7 _ A1 _ D21 _ S29 G36 D21 N35A A2 _ M17 G17 _ I9 _".split()


# --- character mapping ---------------------------------------------------------


def test_ascii_letters_map_to_the_tla_convention() -> None:
    # A a i H x X S T D -> ꜣ ꜥ ꞽ ḥ ḫ ẖ š ṯ ḏ, per the task's character table.
    assert convert_word("AaiHxXSTD") == "ꜣꜥꞽḥḫẖšṯḏ"


def test_unchanged_letters_pass_through() -> None:
    assert convert_word("qkgtdbpfmnrhzswy") == "qkgtdbpfmnrhzswy"


def test_yod_is_i_not_j_and_j_is_folded_to_the_same_sign() -> None:
    """Ramses already writes the yod as `i` (unlike BBAW/AES, which write `j`). The
    rare `j` (19 occurrences corpus-wide, always inside the editorial `n(j)` genitive
    marker) is the same letter under a different spelling and folds to the same
    sign, so `n(j)` and `n(i)` are not two different readings."""
    assert convert_word("i") == "ꞽ"
    assert convert_word("n(j)") == "n(ꞽ)"
    assert convert_word("n(i)") == "n(ꞽ)"


def test_capitalised_yod_mirrors_the_bbaw_convention() -> None:
    """`I`, capitalised (5 occurrences, always a proper name like `IsD`), maps to the
    capital yod `Ꞽ`, mirroring BBAW's own `J` -> `Ꞽ` for capitalised names."""
    assert convert_word("I") == "Ꞽ"
    assert convert_word("IsD") == "Ꞽ" + convert_word("sD")


def test_dots_hyphens_and_suffix_marker_survive() -> None:
    assert convert_word("=f") == "=f"
    assert convert_word("qn-Hr-xpS.f") == "qn-ḥr-ḫpš.f"


def test_plus_markup_around_a_foreign_name_is_stripped_but_l_is_kept() -> None:
    """`+name+l` is Ramses's own markup wrapper around a handful of foreign or
    hypocoristic personal names (e.g. `+tpA-di-mnTw+l`, real corpus text) — the `+`
    characters are not transliteration and are deleted; `l`, unlike `+`, is a
    legitimate Late Egyptian transliteration letter for such names and is kept. The
    ordinary letter mapping (`A` -> `ꜣ`, `i` -> `ꞽ`, `T` -> `ṯ`, ...) still applies
    inside the name — there is no way to tell "foreign word" from context, so `i` is
    the yod there exactly as it is everywhere else in the corpus."""
    assert convert_word("+tpA-di-mnTw+l") == "tpꜣ-dꞽ-mnṯwl"
    assert "+" not in convert_word("+tqny-imn+l")
    assert convert_word("+tqny-imn+l").endswith("l")


def test_rare_foreign_name_letters_pass_through_verbatim() -> None:
    """`e`, `u`, `F`, `o` have no defined TLA equivalent and appear only inside a
    handful of foreign proper names (e.g. the Hittite name `tili-tesub` in the
    Ramses-Hittite treaty text); they are kept exactly as written, never guessed at
    or dropped. Ordinary letters elsewhere in the same word still convert as usual
    (`i` -> `ꞽ`), since nothing marks a word as "foreign" for the mapping to skip."""
    assert convert_word("tili-tesub") == "tꞽlꞽ-tesub"
    assert convert_word("SrSr.two") == "šršr.two"


# --- word splitting on `_` ------------------------------------------------------


def test_rejoin_words_splits_on_the_word_boundary_token() -> None:
    assert rejoin_words(LINE_2_TOKENS) == ["iw", "iw", "=i", "r", "swr", "m", "=f"]


def test_bracket_lacuna_is_detected_on_raw_tokens_before_splitting() -> None:
    """`[_]` is the MdC indeterminate-lacuna convention. At the character level its
    `_` is indistinguishable from a word-boundary `_` once the stream has been
    rejoined, so detection has to happen on the raw token list first."""
    tokens = list("a A - [ _ ] _ n x t _".split())
    assert has_bracket_lacuna(tokens)
    assert not has_bracket_lacuna(list("p A _ h r w _".split()))


def test_group_src_sep_groups_codes_between_underscore_tokens() -> None:
    assert group_src_sep(LINE_2_SRCSEP) == [
        ["M17", "Z7"],
        ["M17", "Z7"],
        ["A1"],
        ["D21"],
        ["S29", "G36", "D21", "N35A", "A2"],
        ["M17", "G17"],
        ["I9"],
    ]


# --- lacuna markers --------------------------------------------------------------


def test_whole_word_lacuna_markers() -> None:
    assert is_translit_lacuna_word("LACUNA")
    assert is_translit_lacuna_word("MISSING")
    assert is_translit_lacuna_word("//")
    assert is_translit_lacuna_word("///")
    assert not is_translit_lacuna_word("1/2")  # a fraction, not a lacuna
    assert not is_translit_lacuna_word("pA")


def test_glyph_side_lacuna_codes() -> None:
    assert is_glyph_lacuna_code("LACUNA")
    assert is_glyph_lacuna_code("MISSING")
    assert is_glyph_lacuna_code("SHADED2")
    assert is_glyph_lacuna_code("SHADED1")
    assert not is_glyph_lacuna_code("Ff100")  # a real (if unmapped) Ramses code
    assert not is_glyph_lacuna_code("N35")


# --- stable id -------------------------------------------------------------------


def test_content_id_is_stable_and_prefixed() -> None:
    first = content_id("train", 2, "ꞽw ꞽw =ꞽ r swr m =f", "abc")
    second = content_id("train", 2, "ꞽw ꞽw =ꞽ r swr m =f", "abc")
    assert first == second
    assert first.startswith("RAMSES_")


def test_content_id_depends_on_every_input() -> None:
    base = content_id("train", 2, "ꞽw", "abc")
    assert content_id("val", 2, "ꞽw", "abc") != base
    assert content_id("train", 3, "ꞽw", "abc") != base
    assert content_id("train", 2, "ꞽr", "abc") != base
    assert content_id("train", 2, "ꞽw", "xyz") != base


# --- text-only rows carry no glyph display ---------------------------------------


def test_to_schema_keeps_hieroglyphs_and_display_sequence_independent() -> None:
    """`hieroglyphs` is a display column the result card renders verbatim, so a
    text-only row must leave it genuinely empty rather than stuffing it with
    something that merely *normalises* to empty; `display_sequence` falls back to
    the transliteration instead, matching the BBAW text-only convention."""
    aligned_like = to_schema("train", 1, "ꞽw", "𓅱", "𓅱")
    assert aligned_like["hieroglyphs"] == "𓅱"
    assert aligned_like["display_sequence"] == "𓅱"

    text_only_like = to_schema("train", 2, "ꞽw ꞽw =ꞽ", "", "ꞽw ꞽw =ꞽ")
    assert text_only_like["hieroglyphs"] == ""
    assert text_only_like["display_sequence"] == "ꞽw ꞽw =ꞽ"
    assert normalize_hieroglyphs(text_only_like["hieroglyphs"]) == ""


# --- end to end on the real corpus (small slice) ---------------------------------


RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ramses" / "ramses-trl" / "data"
import pytest  # noqa: E402

requires_raw = pytest.mark.skipif(
    not RAW_DIR.exists(), reason="Ramses raw corpus not present in this checkout (gitignored)."
)


@requires_raw
def test_convert_on_a_slice_never_misaligns() -> None:
    # `limit` caps *kept* rows, not lines scanned (many lines are dropped for a
    # transliteration-side lacuna), so this reads well over 2,000 raw lines.
    frame, report = convert(RAW_DIR, ["train"], limit=2000)
    assert report.total > 2000
    assert len(frame) == 2000
    frame = frame.assign(
        hieroglyphs_norm=frame["hieroglyphs"].map(lambda v: normalize_hieroglyphs(v) if v else "")
    )
    align = alignment_report(frame)
    assert align.misaligned_rows == 0


@requires_raw
def test_line_2_of_train_is_a_correctly_aligned_row() -> None:
    """`iw iw =i r swr m =f` against `M17Z7 M17Z7 A1 D21 S29G36D21N35AA2 M17G17 I9`:
    seven words, seven sign groups, verified by hand against the raw corpus files."""
    frame, _ = convert(RAW_DIR, ["train"], limit=10)
    matches = frame[frame["source_ref"] == "ramses-trl 2019-09-01 train line 2"]
    assert len(matches) == 1
    row = matches.iloc[0]
    assert row["transliteration_gold"] == "ꞽw ꞽw =ꞽ r swr m =f"
    assert row["hieroglyphs"] != ""
    norm = normalize_hieroglyphs(row["hieroglyphs"])
    assert len(norm.split()) == 7
    assert row["display_sequence"] == row["hieroglyphs"]


@requires_raw
def test_text_only_rows_from_the_real_corpus_have_no_glyph_display() -> None:
    """Every text-only row (count mismatch or glyph-side lacuna) must have an empty
    `hieroglyphs` — never a raw Gardiner-code dump the UI would render as ASCII
    garbage — and `display_sequence` must fall back to the transliteration."""
    frame, report = convert(RAW_DIR, ["train"], limit=500)
    assert report.text_only > 0
    text_only_rows = frame[frame["hieroglyphs"] == ""]
    assert len(text_only_rows) == report.text_only
    assert (text_only_rows["display_sequence"] == text_only_rows["transliteration_gold"]).all()
    align = alignment_report(
        frame.assign(hieroglyphs_norm=frame["hieroglyphs"].map(lambda v: normalize_hieroglyphs(v) if v else ""))
    )
    assert align.text_only_rows == report.text_only
    assert align.misaligned_rows == 0


def test_to_schema_carries_the_required_grammar_note() -> None:
    row = to_schema("train", 1, "ꞽw", "𓅱", "𓅱")
    assert row["grammar_notes"] == (
        "Ramses transliteration is normalised to the expected grammatical form, not "
        "the attested spelling."
    )
    assert row["source"] == "Ramses"
    assert row["language_stage"] == "Late Egyptian"
    assert row["period"] == "New Kingdom"
    assert row["source_text_id"].startswith("RAMSES_")
