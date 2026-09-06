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
    # The bracketed w survives; the weak-consonant marker does not — item D′ folds
    # `i̯` to `ꞽ` inside the key (see tests/test_notation_fold.py).
    assert strict_reading_key("(w)di̯") == "wdꞽ"
    assert strict_reading_key("ḏd⸗f") == "ḏd=f"


def test_canonical_reading_is_the_strict_key():
    assert canonical_reading("Ḥtp-ḏi̯ nswt") == strict_reading_key("ḥtp-ḏi̯ nswt")


def test_strict_key_folds_plural_marker_before_dropping_dots():
    # TLA writes `.PL`, AES/BBAW write `.pl` — both must key the same as `.w`.
    assert strict_reading_key("nṯr.PL") == strict_reading_key("nṯr.w")
    assert strict_reading_key("nṯr.pl") == strict_reading_key("nṯr.w")
    # `sr.w.PL` must collapse to `sr.w`, not double up to `sr.w.w`.
    assert strict_reading_key("sr.w.PL") == strict_reading_key("sr.w")


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


def test_alignment_report_separates_text_only_rows_from_misaligned():
    """A row with no hieroglyphs (BBAW text-only, Demotic) is not a defect: it is
    counted in `text_only_rows`, kept out of `misaligned_rows`, and `usable_rows`
    excludes both."""
    df = frame(
        [
            ("𓊵𓏙 𓇓𓏏", "ḥtp nswt"),  # aligned: 2 signs, 2 readings
            ("𓊵𓏙 𓇓𓏏", "ḥtp nswt sḏm"),  # misaligned: 2 signs, 3 readings
            ("", "ḥtp"),  # text-only: no signs, but a transliteration
        ]
    )
    report = alignment_report(df)
    assert report.total_rows == 3
    assert report.misaligned_rows == 1
    assert report.misaligned_indices == [1]
    assert report.text_only_rows == 1
    assert report.usable_rows == 1


def test_reading_model_separates_text_only_rows_from_misaligned():
    df = frame(
        [
            ("𓊵𓏙 𓇓𓏏", "ḥtp nswt"),
            ("𓊵𓏙 𓇓𓏏", "ḥtp nswt sḏm"),
            ("", "ḥtp"),
        ]
    )
    model = train_reading_model(df)
    assert model.sentences_seen == 1
    assert model.sentences_skipped == 1
    assert model.sentences_text_only == 1


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


# ---------- merging a second TLA corpus (2026-08-30) ----------


def test_nested_g_markup_becomes_one_placeholder():
    """The Late Egyptian corpus nests the markup: <g><g>ID</g></g>."""
    groups = normalize_hieroglyphs("𓅓<g><g>US9No2VARA</g></g>𓏌").split()
    assert len(groups) == 1
    assert placeholder_to_markup(groups[0][1]) == "US9No2VARA"


def test_non_glyph_run_between_two_signs_does_not_split_the_group():
    """A stray Latin letter or a doubled parenthesis inside a group used to become a
    space and misalign the whole sentence — the same defect as the <g> shredding."""
    assert normalize_hieroglyphs("𓄂𓏏Y𓄣𓏤").split() == ["𓄂𓏏𓄣𓏤"]
    assert len(normalize_hieroglyphs("𓅷𓏤((𓏲))𓅯").split()) == 1


def test_whitespace_still_separates_groups_around_noise():
    """The rule is only about characters *between* two signs with no space; a
    separator surrounded by spaces must still split."""
    assert normalize_hieroglyphs("(1) 𓊵𓏙 — 𓇓𓏏 [sic]") == "𓊵𓏙 𓇓𓏏"


def test_shipped_corpus_is_fully_aligned():
    """The merged corpus must lose no row to normalisation."""
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    report = df.attrs["alignment"]
    assert report.misaligned_rows == 0, report.misaligned_indices[:5]
    # Text-only rows (transliteration + translation, no hieroglyphs) are a legitimate
    # state since the BBAW text-only import of 2026-09-04, not a normalisation loss.
    # Every row with signs must still align; the text-only count is checked against
    # the source column so a silent glyph-stripping bug would show up here.
    text_only_by_source = (df["hieroglyphs_norm"].astype(str).str.strip() == "").sum()
    assert report.text_only_rows == text_only_by_source
    assert report.text_only_rows > 40_000
    assert report.usable_rows > 31_000
    assert report.total_rows > 78_000


def test_both_language_stages_are_present_and_labelled():
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    stages = set(df["language_stage"])
    assert {"Earlier Egyptian", "Late Egyptian"} <= stages
    # New Kingdom coverage is the point of the merge: it was 9 rows before.
    assert (df["period"] == "New Kingdom").sum() > 2_000


def test_suffix_marker_is_uniform_across_the_corpus():
    """Two conventions for one morpheme made the same sentence read `n =tn` or
    `n ⸗tn` depending only on which corpus attested the spelling more often."""
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    assert not df["transliteration_gold"].astype(str).str.contains("⸗").any()


def test_corpus_ids_are_unique_and_prefixed_per_source():
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    keys = df[["source", "source_text_id", "source_sentence_id"]]
    assert not keys.duplicated().any()
    prefixes = {str(v).rsplit("_", 1)[0] for v in df["source_text_id"]}
    assert {"TLA_EARLIER", "TLA_LATE"} <= prefixes


def test_corpus_csv_loads_without_mixed_type_warning():
    """The six sparse text columns (mdc, lemma_sequence, upos, glossing, grammar_notes,
    normalized_reading_order) are empty for most rows, so pandas used to infer float for
    some chunks and str for others — a DtypeWarning at every boot and a per-cell type that
    depended on chunk boundaries. `load_examples_csv` pins them to str; present values are
    unchanged and missing cells stay NaN."""
    import warnings

    from app.data.loader import SPARSE_TEXT_COLUMNS, load_examples_csv

    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.DtypeWarning)
        df = load_examples_csv("data/processed/examples.csv")
    for column in SPARSE_TEXT_COLUMNS:
        assert column in df.columns
        present = df[column].dropna()
        assert present.map(lambda value: isinstance(value, str)).all(), column
