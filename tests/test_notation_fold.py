"""Item D′ (2026-09-06): the weak-consonant notation fold in the suggestion identity key.

TLA's weak-consonant marker U+032F writes a weak radical that another edition writes
plain: `rdi̯` and `rdꞽ`, `hru̯` and `hrw`. It is a notation, not a different sound, so
`strict_reading_key` folds `i̯` → `ꞽ` and `u̯` → `w` and two rows that differ only in it
are one reading — one suggestion group instead of two.

The tests are the ones named in the pre-registration, in its order, plus the fixture
that proves the fold left every marker-free reading's key byte-identical.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from app.data.normalizer import fold_weak_consonant_marker
from app.services.suggestions import (
    canonical_reading,
    notation_folded_reading_key,
    strict_reading_key,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "marker_free_readings.json"

MARK = "̯"


def test_the_same_verb_in_two_notations_is_one_reading():
    assert strict_reading_key(f"rdi{MARK} =f") == strict_reading_key("rdꞽ =f")
    # …and the fold is what does it: the two spellings really differ byte-wise.
    assert f"rdi{MARK} =f" != "rdꞽ =f"


def test_the_fold_survives_the_dots_and_brackets():
    assert strict_reading_key(f"ḏi{MARK}.t") == strict_reading_key("ḏꞽ.t")
    assert strict_reading_key(f"ḥtp-ḏi{MARK} nswt") == strict_reading_key("ḥtp-ḏꞽ nswt")
    # The bracketed letter is still kept, as it always was — only the marks vanish.
    assert strict_reading_key(f"(w)di{MARK}") == "wdꞽ"


def test_u_with_the_marker_folds_to_w():
    assert strict_reading_key(f"hru{MARK}") == strict_reading_key("hrw")
    assert strict_reading_key(f"nn zꜣu{MARK} =ṯn") == strict_reading_key("nn zꜣw =ṯn")


def test_decomposed_input_folds_like_composed_input():
    composed = f"rdi{MARK} =f"
    decomposed = unicodedata.normalize("NFD", composed)
    assert strict_reading_key(decomposed) == strict_reading_key("rdꞽ =f")
    # An NFD sentence whose *other* letters decompose too still keys the same.
    sentence = f"ḥtp-ḏi{MARK} nswt ẖnm"
    assert strict_reading_key(unicodedata.normalize("NFD", sentence)) == strict_reading_key(
        sentence
    )


def test_distinct_consonants_stay_distinct():
    # The fold merges a notation, never a letter.
    assert strict_reading_key("ḥtp") != strict_reading_key("htp")
    for left, right in [("ꜣ", "ꜥ"), ("ḥ", "h"), ("ḫ", "ẖ"), ("ṯ", "t"), ("ḏ", "d")]:
        assert strict_reading_key(f"n{left}") != strict_reading_key(f"n{right}")
    # Item D's other duplicate pair: a genuine spelling variant, which must NOT merge.
    assert strict_reading_key("ꞽt") != strict_reading_key("ꞽtꞽ")


def test_the_fold_is_idempotent():
    for reading in [f"rdi{MARK} =f", f"hru{MARK}", "ḏꞽ.t", "ḥtp nswt"]:
        once = strict_reading_key(reading)
        assert strict_reading_key(once) == once
        assert fold_weak_consonant_marker(fold_weak_consonant_marker(reading)) == (
            fold_weak_consonant_marker(reading)
        )


def test_marker_free_readings_key_exactly_as_they_did_before_the_fold():
    """200 corpus readings without the marker, stamped with their pre-D′ keys.

    The keys in the fixture were computed by re-running the pristine pipeline (NFC,
    lower, ⸗→=, plural fold, drop editorial marks) — so this is a before/after
    comparison, not the current code agreeing with itself.
    """
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(fixture) == 200
    for entry in fixture:
        assert MARK not in unicodedata.normalize("NFC", entry["reading"])
        assert strict_reading_key(entry["reading"]) == entry["pristine_strict_key"]


def test_the_measurement_key_and_the_shipped_key_now_agree():
    """`notation_folded_reading_key` is the metric's key; once the fold shipped it is
    the identity key itself. If a later change undid the fold this fails loudly."""
    for reading in [f"rdi{MARK} =f", f"ḥtp-ḏi{MARK} nswt ḥtp-ḏi{MARK} ꞽnp.w", f"hru{MARK}"]:
        assert notation_folded_reading_key(reading) == strict_reading_key(reading)
        assert canonical_reading(reading) == strict_reading_key(reading)
