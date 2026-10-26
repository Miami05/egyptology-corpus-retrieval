"""Tests for the sign-level contextual reading decoder.

The decoder's whole purpose is choosing between competing readings of one sign, so the
tests build tiny corpora where the correct choice is unambiguous by construction and
check that context — not just frequency — decides.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.reading_model import (
    BOUNDARY,
    NO_READING_MARK,
    ReadingModel,
    train_reading_model,
)


def corpus(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    """Build a minimal corpus frame from (signs, readings) string pairs."""
    return pd.DataFrame(
        [
            {
                "hieroglyphs_norm": signs,
                "transliteration_gold": readings,
                "source_text_id": f"T{i:03d}",
                "source_sentence_id": f"S{i:03d}",
            }
            for i, (signs, readings) in enumerate(pairs)
        ]
    )


def test_learns_readings_per_sign():
    model = train_reading_model(corpus([("A B", "x y"), ("A B", "x y")]))
    assert dict(model.sign_reading["A"]) == {"x": 2}
    assert model.sentences_seen == 2


def test_skips_misaligned_rows():
    # Three signs against two readings cannot be paired without guessing.
    model = train_reading_model(corpus([("A B C", "x y")]))
    assert model.sentences_seen == 0
    assert model.sign_reading == {}


def test_identifies_ambiguous_signs():
    model = train_reading_model(corpus([("A", "x"), ("A", "y"), ("B", "z")]))
    assert model.is_ambiguous("A") is True
    assert model.is_ambiguous("B") is False
    assert model.ambiguous_signs == {"A"}


def test_most_frequent_baseline_ignores_context():
    model = train_reading_model(
        corpus([("A", "x"), ("A", "x"), ("A", "x"), ("A", "y")])
    )
    assert model.predict_most_frequent(["A"]) == ["x"]


def test_context_overrides_frequency():
    """The decisive behaviour: a rarer reading wins when context demands it.

    Sign A is read 'x' three times and 'y' once, so frequency alone always says 'x'.
    But 'y' only ever follows sign P (reading 'p'), so after P the decoder must
    choose 'y'.
    """
    model = train_reading_model(
        corpus(
            [
                ("Q A", "q x"),
                ("Q A", "q x"),
                ("Q A", "q x"),
                ("P A", "p y"),
                ("P A", "p y"),
            ]
        )
    )
    assert model.predict_most_frequent(["P", "A"]) == ["p", "x"]  # baseline is wrong
    predictions = model.predict_sequence(["P", "A"])
    assert [p.predicted for p in predictions] == ["p", "y"]  # context fixes it


def test_unseen_sign_is_reported_not_guessed():
    model = train_reading_model(corpus([("A", "x")]))
    prediction = model.predict_sequence(["ZZZ"])[0]
    assert prediction.was_seen is False
    assert prediction.predicted == ""
    assert prediction.candidates == []


def test_prediction_exposes_candidate_distribution():
    model = train_reading_model(
        corpus([("A", "x"), ("A", "x"), ("A", "x"), ("A", "y")])
    )
    prediction = model.predict_sequence(["A"])[0]
    assert prediction.is_ambiguous is True
    assert prediction.attested_count == 4
    readings = dict(prediction.candidates)
    assert readings["x"] == 0.75
    assert readings["y"] == 0.25


def test_empty_input_returns_no_predictions():
    model = train_reading_model(corpus([("A", "x")]))
    assert model.predict_sequence([]) == []


def test_boundary_context_is_recorded():
    model = train_reading_model(corpus([("A B", "x y")]))
    assert model.reading_bigram[BOUNDARY]["x"] == 1
    assert model.reading_bigram["x"]["y"] == 1


def test_sequence_length_always_matches_input():
    model = train_reading_model(corpus([("A B", "x y"), ("B C", "y z")]))
    for signs in (["A"], ["A", "B"], ["A", "B", "C"], ["A", "ZZ", "C"]):
        assert len(model.predict_sequence(signs)) == len(signs)


# ---------- right-hand context (determinatives follow the phonetic signs) ----------


def test_next_sign_context_is_recorded():
    model = train_reading_model(corpus([("A B", "x y")]))
    assert model.next_sign_context[("A", "B")]["x"] == 1
    assert model.next_sign_context[("B", BOUNDARY)]["y"] == 1


def test_viterbi_already_propagates_information_from_the_right():
    """Worth pinning: the reading chain alone can carry right-hand information.

    Here 'x' is only ever followed by reading 'd' and 'y' only by 'e', so even without
    any next-sign term the best whole path for "A E" must read A as 'y'. This is why a
    naive "left context only" description of the model is inaccurate.
    """
    model = train_reading_model(
        corpus(
            [("A D", "x d"), ("A D", "x d"), ("A D", "x d"), ("A E", "y e"), ("A E", "y e")]
        )
    )
    assert model.predict_most_frequent(["A", "E"]) == ["x", "e"]  # frequency is wrong
    no_right_term = model.predict_sequence(["A", "E"], next_sign_weight=0.0)
    assert no_right_term[0].predicted == "y"


def test_following_sign_disambiguates_when_the_reading_chain_cannot():
    """The case that genuinely needs the next *sign*.

    Both following signs D and E are read the same way ('c'), so the reading-bigram
    chain cannot tell the paths apart, and frequency favours 'x' (3 vs 2). The only
    remaining signal is the identity of the following sign — the determinative
    pattern, where the same sound is written before different determinatives.
    """
    model = train_reading_model(
        corpus(
            [("A D", "x c"), ("A D", "x c"), ("A D", "x c"), ("A E", "y c"), ("A E", "y c")]
        )
    )
    assert model.predict_most_frequent(["A", "E"]) == ["x", "c"]  # frequency is wrong

    with_right = model.predict_sequence(["A", "E"])
    assert with_right[0].predicted == "y"  # next-sign context fixes it

    without_right = model.predict_sequence(["A", "E"], next_sign_weight=0.0)
    assert without_right[0].predicted == "x"  # and without it, the error returns


# ---------- fallback for unattested sign groups ----------


def test_unattested_group_falls_back_to_closest_attested_group():
    """𓏃𓊹𓉱-style case: the group is new, but its glyphs are known."""
    model = train_reading_model(corpus([("AB C", "known c"), ("AB C", "known c")]))
    prediction = model.predict_sequence(["ABX"])[0]
    assert prediction.was_seen is False       # this exact group was never attested
    assert prediction.is_fallback is True     # but a similar one was
    assert prediction.fallback_from == "AB"
    assert prediction.predicted == "known"


def test_fallback_can_be_disabled():
    model = train_reading_model(corpus([("AB", "known")]))
    prediction = model.predict_sequence(["ABX"], use_fallback=False)[0]
    assert prediction.is_fallback is False
    assert prediction.predicted == ""


def test_fallback_requires_real_glyph_overlap():
    """A group sharing almost nothing must not borrow a reading."""
    model = train_reading_model(corpus([("ABCDEFG", "known")]))
    prediction = model.predict_sequence(["ZZZ"])[0]
    assert prediction.is_fallback is False
    assert prediction.predicted == ""


def test_nearest_known_group_prefers_better_attested_on_ties():
    model = train_reading_model(
        corpus([("AB", "rare"), ("AB2", "common"), ("AB2", "common"), ("AB2", "common")])
    )
    group, score = model.nearest_known_group("AB2")
    assert group == "AB2"
    assert score == 1.0


def test_attested_group_is_never_treated_as_fallback():
    model = train_reading_model(corpus([("AB", "known")]))
    prediction = model.predict_sequence(["AB"])[0]
    assert prediction.was_seen is True
    assert prediction.is_fallback is False


# ---------- a group with no reading keeps its place (KRI self-test, 2026-10-26) ----------


def test_group_with_no_reading_is_an_explicit_placeholder_not_an_empty_string():
    """An unreadable group must be visible in the result, not joined away.

    The self-test's royal name came back as two groups nothing could read, and a
    caller joining `p.predicted` dropped them — so the name left the line reading
    with nothing marking the loss. The placeholder belongs to the prediction, so
    every renderer marks the same gap the same way.
    """
    model = train_reading_model(corpus([("A B", "x y")]))
    predictions = model.predict_sequence(["A", "Q", "B"])
    middle = predictions[1]
    assert middle.predicted == ""
    assert middle.has_reading is False
    assert middle.display_reading == NO_READING_MARK
    assert [p.display_reading for p in predictions] == ["x", NO_READING_MARK, "y"]


def test_a_read_group_displays_its_reading_unchanged():
    model = train_reading_model(corpus([("A", "x")]))
    prediction = model.predict_sequence(["A"])[0]
    assert prediction.has_reading is True
    assert prediction.display_reading == "x"


# ---------- a tie on singleton evidence is not a confident reading ----------


def test_readings_attested_once_each_are_reported_as_a_tie():
    """Three readings, one attestation each: the corpus ranks none of them.

    The decode still prints one of them, but `is_singleton_tie` says the choice is
    the tie-break's rather than the evidence's, and the confidence is discounted so
    it cannot be read as a measured preference.
    """
    model = train_reading_model(corpus([("A", "x"), ("A", "y"), ("A", "z")]))
    prediction = model.predict_sequence(["A"])[0]
    assert prediction.was_seen is True
    assert prediction.is_singleton_tie is True
    assert prediction.tied_singleton_readings == ["x", "y", "z"]
    # share 1/3, divided by the three tied readings.
    assert prediction.confidence == pytest.approx(1 / 9)


def test_a_reading_with_real_evidence_is_not_a_tie():
    model = train_reading_model(corpus([("A", "x"), ("A", "x"), ("A", "y")]))
    prediction = model.predict_sequence(["A"])[0]
    assert prediction.is_singleton_tie is False
    assert prediction.tied_singleton_readings == []
    assert prediction.confidence == pytest.approx(2 / 3)


def test_one_reading_attested_once_is_not_a_tie():
    model = train_reading_model(corpus([("A", "x")]))
    prediction = model.predict_sequence(["A"])[0]
    assert prediction.is_singleton_tie is False
    assert prediction.confidence == pytest.approx(1.0)


# ---------- pooled evidence for a group the stage filter emptied ----------


def _stage_emptied_models() -> tuple[ReadingModel, ReadingModel]:
    """(pooled, stage) models for a group the stage restriction all but empties.

    The shape traced in the KRI self-test: one sign read one way 34 times, every one
    of those rows belonging to a stage the router did not choose, plus three readings
    attested once each that survive the restriction.
    """
    singletons = [("H", "hy"), ("H", "wsht"), ("H", "thr")]
    pooled = train_reading_model(corpus([("H", "haw")] * 34 + singletons))
    stage = train_reading_model(corpus(singletons))
    return pooled, stage


def test_stage_emptied_group_is_read_from_the_pooled_corpus_and_marked():
    pooled, stage = _stage_emptied_models()
    before = stage.predict_sequence(["H"])[0]
    assert before.is_singleton_tie is True
    assert before.used_pooled_evidence is False

    stage.attach_pooled(pooled)
    after = stage.predict_sequence(["H"])[0]
    assert after.used_pooled_evidence is True
    assert after.predicted == "haw"
    assert after.stage_attested_count == 3
    assert after.attested_count == 37
    assert after.reading_count == 34
    assert after.is_singleton_tie is False
    # It is still attested here — the pooled corpus IS this corpus, unrestricted.
    assert after.was_seen is True


def test_pooled_fallback_can_be_switched_off_per_call():
    """The stage router decodes with it off, so its decision rule cannot move."""
    pooled, stage = _stage_emptied_models()
    stage.attach_pooled(pooled)
    prediction = stage.predict_sequence(["H"], use_pooled_fallback=False)[0]
    assert prediction.used_pooled_evidence is False
    assert prediction.is_singleton_tie is True


def test_pooled_fallback_leaves_a_group_the_stage_attests_well_alone():
    # 8 attestations in the stage is above POOLED_FALLBACK_MAX_STAGE_COUNT, so the
    # filter has thinned this group's evidence, not emptied it.
    pooled = train_reading_model(corpus([("H", "haw")] * 100 + [("H", "hy")] * 8))
    stage = train_reading_model(corpus([("H", "hy")] * 8))
    stage.attach_pooled(pooled)
    prediction = stage.predict_sequence(["H"])[0]
    assert prediction.used_pooled_evidence is False
    assert prediction.predicted == "hy"


def test_pooled_fallback_needs_the_pooled_evidence_to_be_substantial():
    # Stage 1, pooled 12: clears the ratio but not POOLED_FALLBACK_MIN_POOLED_COUNT.
    pooled = train_reading_model(corpus([("H", "haw")] * 11 + [("H", "hy")]))
    stage = train_reading_model(corpus([("H", "hy")]))
    stage.attach_pooled(pooled)
    assert stage.uses_pooled_evidence("H") is False


def test_pooled_fallback_needs_an_order_of_magnitude_more_pooled_evidence():
    # Stage 3, pooled 24: clears the minimum count but 24 < 10 x 3.
    pooled = train_reading_model(
        corpus([("H", "haw")] * 21 + [("H", "hy"), ("H", "wsht"), ("H", "thr")])
    )
    stage = train_reading_model(corpus([("H", "hy"), ("H", "wsht"), ("H", "thr")]))
    stage.attach_pooled(pooled)
    assert stage.uses_pooled_evidence("H") is False


def test_pooled_fallback_does_not_touch_a_group_the_stage_never_saw():
    """Stage count 0 keeps its own documented chain (lexicon/compose/borrow)."""
    pooled = train_reading_model(corpus([("H", "haw")] * 40))
    stage = train_reading_model(corpus([("A", "x")]))
    stage.attach_pooled(pooled)
    assert stage.uses_pooled_evidence("H") is False
    prediction = stage.predict_sequence(["H"])[0]
    assert prediction.was_seen is False
    assert prediction.used_pooled_evidence is False


def test_attaching_a_model_to_itself_is_a_no_op():
    model = train_reading_model(corpus([("A", "x")]))
    model.attach_pooled(model)
    assert model.pooled is None


def test_confidence_is_about_the_reading_that_was_chosen():
    """A minority reading chosen by context must not inherit the majority's number.

    'A' is read 'x' three times and 'y' once, but after 'q' the corpus only ever
    reads it 'y' — so the decoder chooses 'y', whose own share of the group's
    evidence is 1/4, not 'x''s 3/4.
    """
    model = train_reading_model(
        corpus(
            [("P A", "p x"), ("P A", "p x"), ("P A", "p x"), ("Q A", "q y")]
        )
    )
    prediction = model.predict_sequence(["Q", "A"])[1]
    assert prediction.predicted == "y"
    assert prediction.confidence == pytest.approx(1 / 4)
