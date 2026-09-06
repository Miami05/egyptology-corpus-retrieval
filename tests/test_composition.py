"""Item C2: reading an unattested group sign by sign from the sign-function table.

The composition rule was frozen in the pre-registration before any run (ROADMAP.md,
item C, C2.2). This file pins it clause by clause on synthetic entries, so a later
edit to `app/services/composition.py` cannot quietly re-interpret it, and then checks
the three integration properties: the source order (corpus → lexicon → composed →
fallback), the honesty marking, and the no-op when the switch is off.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from app.services.composition import (
    MAX_CANDIDATES,
    compose_group,
    composed_distribution,
    consonants,
)
from app.services.reading_model import ReadingPrediction, train_reading_model
from app.services.sign_functions import FunctionEntry, SignFunctions

# Placeholder characters; nothing here depends on them being real hieroglyphs.
S1, S2, S3 = "\U00013000", "\U00013001", "\U00013002"


def inventory(**rows: list[tuple[str, str]]) -> SignFunctions:
    """Build a `SignFunctions` from `sign -> [(function, value), ...]`."""
    functions = SignFunctions()
    for sign, entries in rows.items():
        built = tuple(
            FunctionEntry(
                sign=sign,
                gardiner="",
                function=function,
                value=value,
                meaning="",
                source_note="test",
            )
            for function, value in entries
        )
        functions.entries[sign] = built
        folded: set[str] = set()
        for entry in built:
            folded |= entry.classes
        functions.classes[sign] = frozenset(folded)
    return functions


def readings(
    group: str,
    functions: SignFunctions,
    corpus=None,
    complement_skip: bool = False,
    optional_logogram: bool = False,
) -> list[str]:
    """Compose, with the two dev revisions OFF unless a test asks for them.

    The clause-by-clause tests below pin the *pre-registered* rule; the revisions get
    their own tests, so a change to either cannot hide inside the other.
    """
    return [
        c.reading
        for c in compose_group(
            group,
            functions,
            corpus or {},
            complement_skip=complement_skip,
            optional_logogram=optional_logogram,
        )
    ]


# --------------------------------------------------------------------------- #
# the frozen rule, clause by clause
# --------------------------------------------------------------------------- #


def test_phonogram_and_logogram_append_their_value():
    functions = inventory(**{S1: [("phonogram", "n")], S2: [("logogram", "rꜥ")]})
    assert readings(S1 + S2, functions) == ["nrꜥ"]


def test_determinative_typographic_and_phonetic_determinative_are_silent():
    functions = inventory(
        **{
            S1: [("phonogram", "n")],
            S2: [("determinative", "man")],
            S3: [("typographic", "")],
        }
    )
    assert readings(S1 + S2 + S3, functions) == ["n"]
    silent = inventory(**{S1: [("phonogram", "n")], S2: [("phonetic determinative", "n")]})
    assert readings(S1 + S2, silent) == ["n"]


def test_logogram_or_determinative_offers_both_the_value_and_nothing():
    functions = inventory(
        **{S1: [("phonogram", "n")], S2: [("logogram or determinative", "pr")]}
    )
    assert set(readings(S1 + S2, functions)) == {"npr", "n"}


def test_phonogram_or_phonetic_determinative_is_silent_only_when_it_repeats():
    functions = inventory(
        **{
            S1: [("phonogram", "mr")],
            S2: [("phonogram or phonetic determinative", "mr")],
        }
    )
    # "mr" is already a suffix of the reading so far -> contribute nothing.
    assert readings(S1 + S2, functions) == ["mr"]

    other = inventory(
        **{
            S1: [("phonogram", "n")],
            S2: [("phonogram or phonetic determinative", "mr")],
        }
    )
    # "mr" is not a suffix of "n" -> append it.
    assert readings(S1 + S2, other) == ["nmr"]


def test_the_suffix_test_ignores_brackets_dots_and_the_suffix_marker():
    assert consonants("r(m)ṯ(.t)") == "rmṯt"
    assert consonants("=ṯn") == "ṯn"
    functions = inventory(
        **{
            S1: [("phonogram", "n.b")],
            S2: [("phonogram or phonetic determinative", "(n)b")],
        }
    )
    assert readings(S1 + S2, functions) == ["n.b"]


def test_a_group_that_composes_to_nothing_yields_no_candidate():
    functions = inventory(**{S1: [("determinative", "x")], S2: [("typographic", "")]})
    assert compose_group(S1 + S2, functions, {}) == []


def test_a_sign_with_no_standalone_row_makes_the_whole_group_abstain():
    """Amended rule 3: never silently drop a sign the tables do not describe."""
    functions = inventory(**{S1: [("phonogram", "n")]})
    assert compose_group(S1 + S2, functions, {}) == []
    # A row scoped to a sign combination does not count as describing the sign alone.
    scoped = SignFunctions()
    scoped.entries[S2] = (
        FunctionEntry(S2, "", "logogram", "rḥw", "men", "test", group="A1:Z2"),
    )
    scoped.classes[S2] = frozenset({"log"})
    scoped.entries[S1] = inventory(**{S1: [("phonogram", "n")]}).entries[S1]
    scoped.classes[S1] = frozenset({"phon"})
    assert scoped.standalone_entries_for(S2) == ()
    assert compose_group(S1 + S2, scoped, {}) == []


def test_hedged_and_plural_dual_numeral_rows_are_not_standalone():
    for qualifier in ("certain=false", "plural=true", "dual=true", "numeral=10"):
        entry = FunctionEntry(S1, "", "phonogram", "n", "", "test", qualifier=qualifier)
        assert not entry.is_standalone, qualifier
    for qualifier in ("period=MK", "texttype=hieratic", "root=nb", "certain=true", ""):
        entry = FunctionEntry(S1, "", "phonogram", "n", "", "test", qualifier=qualifier)
        assert entry.is_standalone, qualifier


# --------------------------------------------------------------------------- #
# the two dev revisions
# --------------------------------------------------------------------------- #


def test_revision_1_offers_a_skip_for_a_trailing_phonetic_complement():
    """nfr + f + r must be able to compose to "nfr", not only to "nfrfr"."""
    functions = inventory(
        **{
            S1: [("phonogram", "nfr")],
            S2: [("phonogram", "f")],
            S3: [("phonogram", "r")],
        }
    )
    without = readings(S1 + S2 + S3, functions)
    assert without == ["nfrfr"]
    with_revision = readings(S1 + S2 + S3, functions, complement_skip=True)
    assert "nfr" in with_revision
    # The skip is an extra choice, not a replacement.
    assert "nfrfr" in with_revision


def test_revision_1_offers_a_skip_for_a_leading_phonetic_complement():
    """n before nw must be able to compose to "nw", not only to "nnw"."""
    functions = inventory(**{S1: [("phonogram", "n")], S2: [("phonogram", "nw")]})
    assert readings(S1 + S2, functions) == ["nnw"]
    assert set(readings(S1 + S2, functions, complement_skip=True)) == {"nnw", "nw"}


def test_revision_1_keeps_a_genuine_gemination_reachable():
    functions = inventory(**{S1: [("phonogram", "ꜥm")], S2: [("phonogram", "ꜥm")]})
    assert "ꜥmꜥm" in readings(S1 + S2, functions, complement_skip=True)


def test_revision_2_lets_a_logogram_be_a_classifier_instead():
    functions = inventory(**{S1: [("phonogram", "n")], S2: [("logogram", "dmḏ")]})
    assert readings(S1 + S2, functions) == ["ndmḏ"]
    assert set(readings(S1 + S2, functions, optional_logogram=True)) == {"ndmḏ", "n"}


def test_the_cap_is_twenty_four():
    # Six signs, each offering "a value or nothing" -> 2^6 = 64 paths.
    rows = {}
    for index in range(6):
        rows[chr(0x13000 + index)] = [("logogram or determinative", f"v{index}")]
    functions = inventory(**rows)
    group = "".join(chr(0x13000 + index) for index in range(6))
    out = compose_group(group, functions, {})
    assert len(out) == MAX_CANDIDATES == 24


def test_candidate_order_follows_the_corpus_probability_of_the_single_sign():
    functions = inventory(
        **{S1: [("phonogram", "rare"), ("phonogram", "common")]}
    )
    corpus = {S1: Counter({"common": 90, "rare": 10})}
    assert readings(S1, functions, corpus) == ["common", "rare"]
    # With no corpus opinion the table order stands.
    assert readings(S1, functions) == ["rare", "common"]


def test_score_is_the_sum_of_log_probabilities_of_the_contributing_signs():
    from math import log

    functions = inventory(**{S1: [("phonogram", "a")], S2: [("phonogram", "b")]})
    corpus = {S1: Counter({"a": 1, "x": 3}), S2: Counter()}
    out = compose_group(S1 + S2, functions, corpus)
    assert len(out) == 1
    # S1: corpus says P(a | S1) = 1/4. S2: no corpus opinion, 1 entry -> log(1/1) = 0.
    assert out[0].score == pytest.approx(log(0.25) + log(1.0))


def test_distribution_is_normalised_over_the_candidates():
    functions = inventory(
        **{S1: [("phonogram", "a")], S2: [("logogram or determinative", "b")]}
    )
    out = compose_group(S1 + S2, functions, {})
    distribution = composed_distribution(out)
    assert set(distribution) == {"ab", "a"}
    assert sum(distribution.values()) == pytest.approx(1.0)
    assert composed_distribution([]) == Counter()


# --------------------------------------------------------------------------- #
# integration with the decoder
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def model():
    frame = pd.DataFrame(
        [
            {"hieroglyphs_norm": "𓆓𓂧 𓆑", "transliteration_gold": "ḏd =f"},
            {"hieroglyphs_norm": "𓆓𓂧 𓀀", "transliteration_gold": "ḏd =ꞽ"},
        ]
    )
    return train_reading_model(frame)


UNATTESTED = "\U0001333B"  # U7, "mr" in the project supplement


def test_composed_is_used_before_the_fallback_and_is_marked(model):
    prediction = model.predict_sequence([UNATTESTED], use_composed=True)[0]
    assert prediction.is_composed
    assert prediction.is_borrowed
    assert not prediction.is_fallback
    assert not prediction.was_seen
    assert prediction.attested_count == 0
    assert prediction.lexicon_count == 0
    assert prediction.predicted == "mr"


def test_switch_off_reproduces_the_pre_item_c2_decode(model):
    off = model.predict_sequence([UNATTESTED], use_composed=False)[0]
    assert not off.is_composed
    assert off.predicted != "mr" or off.is_fallback or off.predicted == ""


def test_an_attested_group_never_becomes_composed(model):
    prediction = model.predict_sequence(["𓆓𓂧"], use_composed=True)[0]
    assert prediction.was_seen and not prediction.is_composed
    assert prediction.predicted == "ḏd"


def test_is_borrowed_covers_both_kinds():
    assert ReadingPrediction("s", "r", [], 0, False, False, fallback_from="g").is_borrowed
    assert ReadingPrediction("s", "r", [], 0, False, False, is_composed=True).is_borrowed
    assert not ReadingPrediction("s", "r", [], 1, False, True).is_borrowed


def test_candidates_are_probabilities_summing_to_one(model):
    prediction = model.predict_sequence([UNATTESTED], use_composed=True)[0]
    assert prediction.candidates
    assert sum(p for _r, p in prediction.candidates) == pytest.approx(1.0)
