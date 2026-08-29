"""Phase 0 — data integrity.

Every test here pins a defect found in the 2026-08-29 audit, in the order the
roadmap lists them: `<g>…</g>` markup shredding, variation selectors splitting groups,
missing NFC, unfolded variant codepoints, format controls, the lossy reading key, and
the sign index falling back to raw markup.
"""

from __future__ import annotations

import unicodedata

import pandas as pd

from app.data.loader import alignment_report
from app.data.normalizer import (
    PLACEHOLDER_RE,
    contains_hieroglyphs,
    display_sign_group,
    markup_to_placeholder,
    normalize_hieroglyphs,
    normalize_transliteration,
    placeholder_to_markup,
)
from app.services.reading_model import train_reading_model
from app.services.signs import build_sign_index
from app.services.suggestions import canonical_reading, loose_reading_form, strict_reading_key

Z2 = "\U000133E5"  # 𓏥 plural strokes
Z15B = "\U000133FC"  # 𓏼 three vertical strokes — visually the same marker
VS1 = "︀"
JOINER = "\U00013431"  # quadrat joiner, a format control


# ---------- <g>…</g> markup ----------


def test_markup_becomes_one_placeholder_glyph_not_spaces():
    # Before: every character of "<g>M12B</g>" became a space, so the group vanished
    # and every reading after it was paired with the wrong sign.
    groups = normalize_hieroglyphs("𓊵𓏙 <g>M12B</g> 𓇓𓏏").split()
    assert len(groups) == 3
    assert PLACEHOLDER_RE.fullmatch(groups[1])


def test_markup_inside_a_group_keeps_the_group_whole():
    # 981 corpus rows have markup glued to a real sign. Splitting them trained the
    # model on a truncated group without ever skipping the row.
    groups = normalize_hieroglyphs("𓅓<g>D77</g> 𓀀").split()
    assert len(groups) == 2
    assert groups[0].startswith("𓅓") and len(groups[0]) == 2


def test_same_sign_id_always_gets_the_same_placeholder():
    assert markup_to_placeholder("D77") == markup_to_placeholder("D77")
    assert markup_to_placeholder("D77") != markup_to_placeholder("D207")


def test_placeholder_round_trips_to_its_id_for_display():
    placeholder = markup_to_placeholder("M12B")
    assert placeholder_to_markup(placeholder) == "M12B"
    assert display_sign_group(f"𓅓{placeholder}") == "𓅓⟨M12B⟩"


def test_bare_gardiner_token_is_treated_like_markup():
    # One corpus row writes an unencoded sign as a bare "V31Aa" token.
    groups = normalize_hieroglyphs("𓎼𓂋𓀁 V31Aa 𓅜𓐍𓏛").split()
    assert len(groups) == 3
    assert placeholder_to_markup(groups[1]) == "V31Aa"


def test_placeholders_alone_do_not_count_as_hieroglyphs():
    assert contains_hieroglyphs(markup_to_placeholder("D77")) is False


# ---------- variation selectors, format controls, editorial brackets ----------


def test_variation_selector_does_not_split_a_group():
    # 26 corpus rows were skipped only because a selector between two signs turned
    # into a space.
    assert normalize_hieroglyphs(f"𓇓{VS1}𓏏 𓊵𓏙") == "𓇓𓏏 𓊵𓏙"


def test_format_controls_are_deleted_not_spaced():
    # The corpus has none, so a paste from a layout-aware editor could never match.
    assert normalize_hieroglyphs(f"𓊵{JOINER}𓏙") == "𓊵𓏙"


def test_query_of_only_format_controls_is_not_a_glyph_query():
    assert contains_hieroglyphs(JOINER) is False
    assert normalize_hieroglyphs(JOINER) == ""


def test_editorial_brackets_do_not_split_a_group():
    assert normalize_hieroglyphs("𓋴𓂝𓂋⟦𓌪⟧ 𓅓").split() == ["𓋴𓂝𓂋𓌪", "𓅓"]


def test_ordinary_punctuation_still_separates_groups():
    # Unchanged behaviour, kept as a guard: noise around groups is a separator.
    assert normalize_hieroglyphs("(1) 𓊵𓏙 — 𓇓𓏏 [sic]") == "𓊵𓏙 𓇓𓏏"


# ---------- variant codepoints ----------


def test_plural_strokes_variants_fold_together():
    # The first expert trial pasted U+133FC; the corpus writes U+133E5.
    assert normalize_hieroglyphs(f"𓂋𓍿𓀀{Z15B}") == normalize_hieroglyphs(f"𓂋𓍿𓀀{Z2}")
    assert Z15B not in normalize_hieroglyphs(Z15B)


# ---------- NFC ----------


def test_decomposed_letters_fold_like_precomposed_ones():
    precomposed = "ẖnm"
    decomposed = unicodedata.normalize("NFD", precomposed)
    assert precomposed != decomposed  # the two spellings really differ byte-wise
    # Before NFC the decomposed form leaked through the fold as a bare "h".
    assert normalize_transliteration(decomposed) == normalize_transliteration(precomposed) == "khnm"
    assert strict_reading_key(decomposed) == strict_reading_key(precomposed)


# ---------- the reading key: strict identity, loose display ----------


def test_strict_key_keeps_distinct_consonants_distinct():
    for left, right in [("ꜣ", "ꜥ"), ("ḥ", "h"), ("ḫ", "ẖ"), ("ṯ", "t"), ("ḏ", "d")]:
        assert strict_reading_key(f"n{left}") != strict_reading_key(f"n{right}")
    # …while the search fold still merges them, which is its job.
    assert normalize_transliteration("nꜣ") == normalize_transliteration("nꜥ")


def test_strict_key_keeps_yod_and_suffix_marker():
    # The old key deleted both: "=ꞽ" became "" and "nḫt"/"nḫtꞽ" merged.
    assert strict_reading_key("=ꞽ") == "=ꞽ"
    assert strict_reading_key("=n") != strict_reading_key("n")
    assert strict_reading_key("nḫt") != strict_reading_key("nḫtꞽ")


def test_strict_key_drops_editorial_marks_but_never_letters():
    assert strict_reading_key("zꜣ-(ꜣ)st") == strict_reading_key("zꜣ-ꜣs.t") == "zꜣ-ꜣst"
    assert strict_reading_key("(w)di̯") == "wdi̯"
    assert strict_reading_key("ḏd⸗f") == "ḏd=f"


def test_canonical_reading_is_the_strict_key():
    assert canonical_reading("Ḥtp-ḏi̯ nswt") == strict_reading_key("ḥtp-ḏi̯ nswt")


def test_loose_form_still_bridges_ascii_and_editorial_variants():
    assert loose_reading_form("htp") == loose_reading_form("ḥtp")
    assert loose_reading_form("n.t") == loose_reading_form("n(.ꞽ).t")


# ---------- alignment: the loader reports, the models skip nothing silently ----------


def frame(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "hieroglyphs": glyphs,
                "hieroglyphs_norm": normalize_hieroglyphs(glyphs),
                "transliteration_gold": reading,
                "source_text_id": f"T{i}",
                "source_sentence_id": f"S{i}",
                "translation": "",
                "period": "",
                "lemma_sequence": "",
            }
            for i, (glyphs, reading) in enumerate(rows)
        ]
    )


def test_alignment_report_counts_and_lists_bad_rows():
    df = frame([("𓊵𓏙 𓇓𓏏", "ḥtp nswt"), ("𓊵𓏙", "ḥtp nswt")])
    report = alignment_report(df)
    assert report.total_rows == 2
    assert report.misaligned_rows == 1
    assert report.misaligned_indices == [1]
    assert report.usable_rows == 1


def test_markup_rows_are_now_aligned_and_trained_on():
    df = frame([("𓅓<g>D77</g> 𓀀 <g>M12B</g>", "m =ꞽ mꜣꜥ")])
    assert alignment_report(df).misaligned_rows == 0
    model = train_reading_model(df)
    assert model.sentences_seen == 1
    assert model.sentences_skipped == 0
    groups = df.loc[0, "hieroglyphs_norm"].split()
    assert model.sign_reading[groups[0]]["m"] == 1
    assert model.sign_reading[groups[2]]["mꜣꜥ"] == 1


def test_reading_model_reports_skipped_rows():
    model = train_reading_model(frame([("𓊵𓏙 𓇓𓏏", "ḥtp"), ("𓊵𓏙", "ḥtp")]))
    assert model.sentences_seen == 1
    assert model.sentences_skipped == 1


def test_sign_index_never_contains_raw_markup():
    df = frame([("<g>E198</g>", "x"), ("𓊵𓏙", "ḥtp")])
    index = build_sign_index(df)
    assert all("<g>" not in key for key in index)
    assert len(index) == 2


def test_fallback_source_is_deterministic():
    # Two equally similar, equally attested groups: the choice must not depend on the
    # process hash seed.
    df = frame([("𓆓𓂧𓆑𓏛", "ḏdf"), ("𓆓𓂧𓆑𓅪", "ḏdf")])
    picks = {train_reading_model(df).predict_sequence(["𓆑𓆓𓂧"])[0].fallback_from for _ in range(5)}
    assert picks == {"𓆓𓂧𓆑𓅪"}  # sorted() order: 𓅪 U+1316A < 𓏛 U+133DB
