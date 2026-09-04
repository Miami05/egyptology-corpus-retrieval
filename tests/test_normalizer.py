"""Normalisation tests, focused on the bug that made sign queries impossible."""

from __future__ import annotations

from app.data.normalizer import (
    contains_hieroglyphs,
    fold_plural_marker,
    normalize_hieroglyphs,
    normalize_mdc,
    normalize_transliteration,
)

GLYPHS = "𓊵𓏙 𓇓𓏏 𓊵𓏙 𓃢 𓏃𓊹𓉱"


def test_normalize_mdc_still_strips_hieroglyphs():
    # Documents the original defect: the MdC path is ASCII-only, so a glyph query
    # sent down it becomes empty and matches nothing. Sign queries must not use it.
    assert normalize_mdc(GLYPHS) == ""


def test_normalize_hieroglyphs_keeps_signs():
    assert normalize_hieroglyphs(GLYPHS) == GLYPHS


def test_normalize_hieroglyphs_preserves_sign_group_boundaries():
    # Whitespace separates sign groups and those groups align 1:1 with
    # transliteration tokens, so collapsing them would destroy the alignment.
    assert len(normalize_hieroglyphs(GLYPHS).split()) == 5


def test_normalize_hieroglyphs_drops_surrounding_noise():
    assert normalize_hieroglyphs("(1) 𓊵𓏙 — 𓇓𓏏 [sic]") == "𓊵𓏙 𓇓𓏏"


def test_normalize_hieroglyphs_handles_empty_and_ascii():
    assert normalize_hieroglyphs("") == ""
    assert normalize_hieroglyphs("   ") == ""
    assert normalize_hieroglyphs("htp-dji nswt") == ""


def test_contains_hieroglyphs_discriminates_scripts():
    assert contains_hieroglyphs(GLYPHS) is True
    assert contains_hieroglyphs("htp-dji nswt") is False
    assert contains_hieroglyphs("ḥtp-ḏi̯ nswt") is False
    assert contains_hieroglyphs("") is False


def test_contains_hieroglyphs_detects_mixed_input():
    # A user may paste glyphs with a note attached; it should still route to signs.
    assert contains_hieroglyphs("line 2: 𓊵𓏙") is True


def test_transliteration_normalisation_folds_egyptological_characters():
    assert normalize_transliteration("ḥtp-ḏi̯ nswt") == "htp-dji̯ nswt"
    assert normalize_transliteration("ḫnt.ꞽ") == "khnt.i"  # the yod is kept as i


def test_plural_marker_folds_pl_to_w():
    # TLA writes `.PL`, AES/BBAW write `.pl`; both fold to the phonemic `.w`.
    assert fold_plural_marker("nṯr.pl") == "nṯr.w"
    assert fold_plural_marker("nṯr.PL".lower()) == "nṯr.w"


def test_plural_marker_collapses_w_pl_instead_of_doubling_w():
    # 1,127 tokens are written `.w.PL`/`.w.pl` (e.g. `sr.w.PL`). A naive `.pl` -> `.w`
    # replace would produce `sr.w.w` (read as `srww`); the fold must collapse the
    # whole `.w.pl` to a single `.w`.
    assert fold_plural_marker("sr.w.pl") == "sr.w"
    assert fold_plural_marker("sr.w.PL".lower()) == "sr.w"


def test_plural_marker_leaves_existing_w_ending_unchanged():
    assert fold_plural_marker("sr.w") == "sr.w"


def test_plural_marker_not_folded_when_followed_by_a_letter():
    # `.pl` inside a longer letter sequence must not be treated as the marker.
    assert fold_plural_marker("nṯr.plt") == "nṯr.plt"


def test_normalize_transliteration_folds_plural_marker():
    assert normalize_transliteration("nṯr.PL") == "ntjr.w"
    assert normalize_transliteration("sr.w.PL") == "sr.w"
