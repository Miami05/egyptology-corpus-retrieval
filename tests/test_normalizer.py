"""Normalisation tests, focused on the bug that made sign queries impossible."""

from __future__ import annotations

from app.data.normalizer import (
    cartouche_spans,
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
    # The weak-consonant marker is folded too (audit A47): `ḏi̯` is `dji`, not `dji̯`.
    assert normalize_transliteration("ḥtp-ḏi̯ nswt") == "htp-dji nswt"
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


# ---------- cartouche spans (KRI self-test, 2026-10-26) ----------

# V011A and V011B, the cartouche written as signs rather than as the Unicode
# enclosure controls. Public-corpus spelling: 𓍹𓃹𓈖𓇋𓋴𓍺, the name Wnjs.
CARTOUCHE_OPEN = "\U00013379"
CARTOUCHE_CLOSE = "\U0001337A"
WNIS = CARTOUCHE_OPEN + "𓃹𓈖𓇋𓋴" + CARTOUCHE_CLOSE


def test_cartouche_spans_finds_a_matched_pair():
    assert cartouche_spans(WNIS) == [(0, 6)]


def test_cartouche_spans_reports_position_within_a_longer_stream():
    assert cartouche_spans("𓋹𓍑" + WNIS + "𓊹") == [(2, 8)]


def test_cartouche_spans_finds_each_of_two_cartouches():
    assert cartouche_spans(WNIS + WNIS) == [(0, 6), (6, 12)]


def test_cartouche_spans_ignores_an_unmatched_half():
    assert cartouche_spans(CARTOUCHE_OPEN + "𓃹𓈖") == []
    assert cartouche_spans("𓃹𓈖" + CARTOUCHE_CLOSE) == []


def test_cartouche_spans_reports_the_outermost_pair_when_both_close():
    nested = CARTOUCHE_OPEN + CARTOUCHE_OPEN + "𓃹" + CARTOUCHE_CLOSE + CARTOUCHE_CLOSE
    assert cartouche_spans(nested) == [(0, 5)]


def test_cartouche_spans_takes_the_pair_that_closes_when_an_opener_is_stray():
    # OPEN OPEN X CLOSE: only the inner pair is complete, and it is the structure.
    # Counting nesting depth lost it, because the depth never returned to zero.
    stray = CARTOUCHE_OPEN + CARTOUCHE_OPEN + "𓃹" + CARTOUCHE_CLOSE
    assert cartouche_spans(stray) == [(1, 4)]


def test_a_stray_opener_does_not_suppress_a_later_complete_cartouche():
    stream = CARTOUCHE_OPEN + "𓋹" + WNIS
    assert cartouche_spans(stream) == [(2, 8)]


def test_cartouche_spans_of_a_cartouche_longer_than_the_segmenter_window():
    # 12 signs inside: longer than segmentation.MAX_GROUP_GLYPHS, which is why
    # `Segmenter.segment` offers the span explicitly rather than relying on its
    # sliding window.
    long_name = CARTOUCHE_OPEN + "𓃹𓈖𓇋𓋴" * 3 + CARTOUCHE_CLOSE
    assert cartouche_spans(long_name) == [(0, 14)]


def test_cartouche_spans_empty_stream():
    assert cartouche_spans("") == []
