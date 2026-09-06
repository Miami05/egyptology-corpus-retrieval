"""Item D's proper-noun definitions, pinned (2026-09-06).

D1 — regrouping suggestions by a name-normalised key — was **not built**: the
pre-registration's own STOP fired, because the symptom it targets does not occur in
our data (0 name-duplicate slots on the NAME-v1 baseline; see
docs/proper-nouns-2026-09-06.md). What *was* built is the measurement: the
name-normalised key and the NAME-v1 builder flags. These tests pin those definitions
so a later reader can see exactly what was measured, and so that a re-run of the
metric cannot silently change meaning — a metric that reads 0 because it is broken
looks the same as one that reads 0 because the symptom is absent.

Precedent: tests/test_adjacency.py does the same for Experiment 2's null.
"""

from __future__ import annotations

import pandas as pd

from app.services.suggestions import (
    aligned_annotation,
    name_normalised_reading_key,
    strict_reading_key,
    suggest_top_readings,
)
from scripts.build_competitive_ambiguity_benchmark import (
    propn_spelling_table,
    variant_name_token,
)
from scripts.run_competitive_ambiguity_eval import (
    build_annotation_lookup,
    name_duplicate_slots,
)

# Osiris (TLA lemma 49460) is written both `wsꞽr` and `(w)sr(.w)` in the corpus;
# Anubis (27360) both `ꞽnp.w` and `ꞽnp(.w)`.
OSIRIS = "49460"


def test_alignment_needs_all_three_counts_to_agree():
    assert aligned_annotation("ḥtp wsꞽr", "1|htp 49460|wsir", "NOUN PROPN") == [
        ("ḥtp", "1", "NOUN"),
        ("wsꞽr", "49460", "PROPN"),
    ]
    # One tag short: no alignment at all, rather than a zip over the shorter list.
    assert aligned_annotation("ḥtp wsꞽr", "1|htp 49460|wsir", "NOUN") == []
    assert aligned_annotation("ḥtp wsꞽr", "", "") == []


def test_two_spellings_of_one_name_share_a_name_normalised_key():
    lemma = f"1|htp 2|rdi {OSIRIS}|wsir"
    upos = "NOUN VERB PROPN"
    first = name_normalised_reading_key("ḥtp ḏi̯ wsꞽr", lemma, upos)
    second = name_normalised_reading_key("ḥtp ḏi̯ (w)sr(.w)", lemma, upos)
    # `ḏꞽ`, not `ḏi̯`: item D′ folds the weak-consonant marker inside the strict key
    # this is built on (tests/test_notation_fold.py). The name still collapses.
    assert first == second == f"ḥtp ḏꞽ {OSIRIS}"
    # And the key this replaces did *not* consider them one reading — which is the
    # whole reason item D was pre-registered.
    assert strict_reading_key("ḥtp ḏi̯ wsꞽr") != strict_reading_key("ḥtp ḏi̯ (w)sr(.w)")


def test_a_verb_in_two_inflections_stays_two_readings():
    # Same lemma, different inflection, tagged VERB: nothing collapses. Only names do.
    assert name_normalised_reading_key("sḏm =f", "10|sdm 20|f", "VERB PRON") != (
        name_normalised_reading_key("sḏm.n =f", "10|sdm 20|f", "VERB PRON")
    )


def test_an_unannotated_row_keeps_the_plain_strict_key():
    # 71% of the corpus (BBAW, Ramses, 553 misaligned AES rows) has no alignment.
    for reading in ("ḥtp ḏi̯ wsꞽr", "ꞽ:nḏ ḥr =ṯ", "pꜣ mw nty-ꞽw"):
        assert name_normalised_reading_key(reading, "", "") == strict_reading_key(reading)


def test_name_duplicate_slots_counts_repeats_after_the_first():
    class Slot:
        def __init__(self, reading: str, label: str) -> None:
            self.candidate_transliteration = reading
            self.supporting_sources = [label]

    lemma = f"1|htp 2|rdi {OSIRIS}|wsir"
    annotations = {
        ("t/T1/S1", strict_reading_key("ḥtp ḏi̯ wsꞽr")): (lemma, "NOUN VERB PROPN"),
        ("t/T1/S2", strict_reading_key("ḥtp ḏi̯ (w)sr(.w)")): (lemma, "NOUN VERB PROPN"),
        ("t/T1/S3", strict_reading_key("ꞽnp.w")): ("27360|inpw", "PROPN"),
    }
    same_name = [Slot("ḥtp ḏi̯ wsꞽr", "t/T1/S1"), Slot("ḥtp ḏi̯ (w)sr(.w)", "t/T1/S2")]
    assert name_duplicate_slots(same_name, annotations) == 1
    assert name_duplicate_slots(same_name + [Slot("ꞽnp.w", "t/T1/S3")], annotations) == 1
    assert name_duplicate_slots([Slot("ꞽnp.w", "t/T1/S3")], annotations) == 0


def test_annotation_lookup_finds_a_row_by_its_printed_source_label():
    frame = pd.DataFrame(
        [
            {
                "source": "TLA",
                "source_text_id": "T1",
                "source_sentence_id": "S1",
                "transliteration_gold": "ḥtp ḏi̯ wsꞽr",
                "lemma_sequence": f"1|htp 2|rdi {OSIRIS}|wsir",
                "upos": "NOUN VERB PROPN",
            }
        ]
    )
    lookup = build_annotation_lookup(frame)
    assert lookup[("TLA/T1/S1", strict_reading_key("ḥtp ḏi̯ wsꞽr"))] == (
        f"1|htp 2|rdi {OSIRIS}|wsir",
        "NOUN VERB PROPN",
    )


def test_spelling_table_and_substitute_pick_the_most_frequent_other_form():
    frame = pd.DataFrame(
        [
            {
                "transliteration_gold": "ḥtp wsꞽr",
                "lemma_sequence": f"1|htp {OSIRIS}|wsir",
                "upos": "NOUN PROPN",
            },
            {
                "transliteration_gold": "ḥtp wsꞽr",
                "lemma_sequence": f"1|htp {OSIRIS}|wsir",
                "upos": "NOUN PROPN",
            },
            {
                "transliteration_gold": "ḥtp (w)sr(.w)",
                "lemma_sequence": f"1|htp {OSIRIS}|wsir",
                "upos": "NOUN PROPN",
            },
            {  # not a PROPN: never enters the table
                "transliteration_gold": "ḥtp ḥtp",
                "lemma_sequence": "1|htp 1|htp",
                "upos": "NOUN NOUN",
            },
        ]
    )
    table = propn_spelling_table(frame)
    assert dict(table[OSIRIS]) == {"wsꞽr": 2, "(w)sr(.w)": 1}
    assert "1" not in table
    # A row spelling it `wsꞽr` is asked about under the other attested spelling …
    assert variant_name_token(
        "ḥtp wsꞽr", f"1|htp {OSIRIS}|wsir", "NOUN PROPN", table
    ) == (1, "wsꞽr", OSIRIS, "(w)sr(.w)")
    # … and a row spelling it the rare way is asked about under the common one.
    assert variant_name_token(
        "ḥtp (w)sr(.w)", f"1|htp {OSIRIS}|wsir", "NOUN PROPN", table
    ) == (1, "(w)sr(.w)", OSIRIS, "wsꞽr")


def test_a_name_with_one_spelling_is_not_a_candidate():
    frame = pd.DataFrame(
        [
            {
                "transliteration_gold": "ḥtp wsꞽr",
                "lemma_sequence": f"1|htp {OSIRIS}|wsir",
                "upos": "NOUN PROPN",
            }
        ]
    )
    table = propn_spelling_table(frame)
    assert variant_name_token("ḥtp wsꞽr", f"1|htp {OSIRIS}|wsir", "NOUN PROPN", table) is None


def test_suggestion_grouping_is_unchanged_by_item_D():
    """D1 was not built, so two spellings of one name are still two suggestions.

    This is the behaviour the null leaves in place; it is pinned here so that if
    anyone later ships the name-normalised grouping key, this test fails loudly and
    the change is a deliberate one rather than a drift.
    """
    frame = pd.DataFrame(
        [
            {
                "transliteration_gold": "ḥtp ḏi̯ wsꞽr",
                "final_score": 0.9,
                "lemma_sequence": f"1|htp 2|rdi {OSIRIS}|wsir",
                "upos": "NOUN VERB PROPN",
                "source": "TLA",
                "source_text_id": "T1",
                "source_sentence_id": "S1",
                "translation": "an offering",
            },
            {
                "transliteration_gold": "ḥtp ḏi̯ (w)sr(.w)",
                "final_score": 0.8,
                "lemma_sequence": f"1|htp 2|rdi {OSIRIS}|wsir",
                "upos": "NOUN VERB PROPN",
                "source": "TLA",
                "source_text_id": "T2",
                "source_sentence_id": "S1",
                "translation": "an offering",
            },
        ]
    )
    suggestions = suggest_top_readings(frame, query_mdc="ḥtp ḏi̯ wsꞽr", top_n=3)
    assert [s.candidate_transliteration for s in suggestions] == [
        "ḥtp ḏi̯ wsꞽr",
        "ḥtp ḏi̯ (w)sr(.w)",
    ]
    assert not hasattr(suggestions[0], "variant_readings")
