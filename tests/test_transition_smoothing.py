"""Tests for the candidate transition-smoothing schemes in `app/services/reading_model.py`.

The schemes are defined in `docs/transition-smoothing-preregistration-2026-10-28.md`
(section 3). What is pinned here:

* the default reproduces today's add-k **exactly** (a golden hash of 60 decodes made
  with the code as it was before the schemes existed, and the verbatim old formula);
* every scheme's probabilities sum to 1 over the vocabulary (R plus the OOV bucket);
* the pathology of section 1 — a context with one distinct successor scores that
  successor at exactly 1.0, 0.0 nats — is gone under every scheme;
* the special cases the document fixes (unseen context, `''`, the pooled level of C3,
  Ney's d and its fallback) behave as written;
* stage routing does not move when the decoder's default scheme does (R2).
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from math import log

import pandas as pd
import pytest

import app.services.reading_model as reading_model
from app.services.reading_model import (
    BOUNDARY,
    FALLBACK_DISCOUNT,
    SMOOTHING,
    SMOOTHING_SCHEMES,
    ReadingModel,
    smoothing_modes,
    train_reading_model,
)
from app.services.stage import choose_stage_by_likelihood, build_stage_resources

# ---------- fixtures ----------


def corpus(pairs):
    return pd.DataFrame(
        [{"hieroglyphs_norm": signs, "transliteration_gold": readings} for signs, readings in pairs]
    )


def golden_corpus() -> pd.DataFrame:
    """300 seeded sentences over 12 signs; the golden hash below was made on this."""
    rng = random.Random(20261028)
    signs = [f"S{i}" for i in range(12)]
    readings = {s: [f"{s.lower()}{j}" for j in range(1 + (i % 4))] for i, s in enumerate(signs)}
    rows = []
    for _ in range(300):
        length = rng.randint(2, 7)
        ss = [rng.choice(signs) for _ in range(length)]
        rs = [rng.choice(readings[s]) for s in ss]
        rows.append({"hieroglyphs_norm": " ".join(ss), "transliteration_gold": " ".join(rs)})
    return pd.DataFrame(rows)


def golden_queries() -> list[list[str]]:
    rng = random.Random(77)
    signs = [f"S{i}" for i in range(12)] + ["UNSEEN"]
    return [[rng.choice(signs) for _ in range(rng.randint(1, 8))] for _ in range(60)]


# sha256 of json.dumps([[predicted readings, repr(path score)], ...]) for golden_queries()
# decoded by the model fitted on golden_corpus(), computed with the reading model as it
# stood on main at 51f3757, i.e. BEFORE the smoothing schemes were added.
GOLDEN_DECODE_SHA256 = "c9566b0da9f83d0cee1f3f7cec44f80e8e96036e4b7ec8460294633644393b3c"


def decode_blob(model: ReadingModel, **kwargs) -> str:
    out = []
    for query in golden_queries():
        predictions, score = model.predict_sequence_scored(query, **kwargs)
        out.append([[p.predicted for p in predictions], repr(score)])
    return json.dumps(out)


@pytest.fixture(scope="module")
def toy() -> ReadingModel:
    """Contexts of every kind: a singleton, a V_obs = 1 context with N = 5, rich ones."""
    pairs = (
        [("A B", "a1 b1")]  # reading a1 is followed by b1 once: N = 1, V = 1
        + [("C D", "c1 d1")] * 5  # c1 followed by d1 five times: N = 5, V = 1
        + [("E F", "e1 f1")] * 3
        + [("E F", "e1 f2")] * 2
        + [("E G", "e2 g1")] * 4
        + [("E F", "e2 f1")]
        + [("E F", "e1 f3")]
        + [("H H", "h1 h1"), ("H H", "h1 h2"), ("H H", "h2 h1")]
    )
    return train_reading_model(corpus(pairs))


def reference_add_k(counts: Counter, reading: str) -> float:
    """The pre-change formula, written out again (verbatim from main at 51f3757)."""
    total = sum(counts.values())
    if total == 0:
        return log(SMOOTHING)
    vocabulary = max(len(counts), 1)
    return log((counts.get(reading, 0) + SMOOTHING) / (total + SMOOTHING * vocabulary))


def vocabulary_of(model: ReadingModel) -> list[str]:
    counts, _total, size = model._unigram()
    support = set(counts)
    for readings in model.reading_bigram.values():
        support.update(readings)
    support.discard("")
    support.discard(BOUNDARY)
    assert len(support) == size
    return sorted(support)


# ---------- the default is today's add-k, exactly ----------


def test_default_decodes_are_byte_identical_to_the_pre_change_code():
    model = train_reading_model(golden_corpus())
    blob = decode_blob(model)
    assert hashlib.sha256(blob.encode()).hexdigest() == GOLDEN_DECODE_SHA256
    assert decode_blob(model, smoothing="off") == blob


def test_the_default_scheme_is_off_and_the_environment_switch_is_validated(monkeypatch):
    assert reading_model.TRANSITION_SMOOTHING_BY_DEFAULT == "off"
    monkeypatch.delenv(reading_model.TRANSITION_SMOOTHING_ENV, raising=False)
    assert reading_model._default_smoothing_scheme() == "off"
    monkeypatch.setenv(reading_model.TRANSITION_SMOOTHING_ENV, "c3")
    assert reading_model._default_smoothing_scheme() == "c3"
    monkeypatch.setenv(reading_model.TRANSITION_SMOOTHING_ENV, "witten-bell")
    with pytest.raises(ValueError):
        reading_model._default_smoothing_scheme()


def test_every_scoring_term_equals_the_old_formula_under_off(toy):
    for previous in [BOUNDARY, "a1", "c1", "e1", "e2", "h1", "never-seen", ""]:
        for reading in vocabulary_of(toy) + ["", "oov"]:
            assert toy._transition(previous, reading) == reference_add_k(
                toy.reading_bigram.get(previous, Counter()), reading
            )
    for key in list(toy.sign_context) + [("Q", "R")]:
        for reading in vocabulary_of(toy)[:6] + [""]:
            assert toy._sign_context(*key, reading) == reference_add_k(
                toy.sign_context.get(key, Counter()), reading
            )
            assert toy._next_sign_context(*key, reading) == reference_add_k(
                toy.next_sign_context.get(key, Counter()), reading
            )


def test_unknown_schemes_are_refused():
    model = train_reading_model(corpus([("A", "a")]))
    with pytest.raises(ValueError):
        model.predict_sequence(["A"], smoothing="c1")
    with pytest.raises(ValueError):
        smoothing_modes("c1")
    assert SMOOTHING_SCHEMES == ("off", "c2", "c3", "c2_transition_only")


def test_the_schemes_do_change_a_decode_but_only_through_the_three_terms():
    # Seed 6 of an exploratory search over 3,000 random toy corpora: a shape on which the
    # four schemes disagree with add-k. This asserts that they act, nothing about which is
    # better.
    rng = random.Random(6)
    signs = ["X", "Y", "Z"]
    readings = {"X": ["a", "b"], "Y": ["c", "d"], "Z": ["e", "f"]}
    pairs = []
    for _ in range(rng.randint(8, 16)):
        length = rng.randint(2, 3)
        ss = [rng.choice(signs) for _ in range(length)]
        pairs.append((" ".join(ss), " ".join(rng.choice(readings[s]) for s in ss)))
    model = train_reading_model(corpus(pairs))
    off = [p.predicted for p in model.predict_sequence(["X", "Y"], smoothing="off")]
    for scheme in ("c2", "c3", "c2_transition_only"):
        other = model.predict_sequence(["X", "Y"], smoothing=scheme)
        assert [p.predicted for p in other] != off
        # the evidence fields do not depend on the scheme
        assert [p.attested_count for p in other] == [
            p.attested_count for p in model.predict_sequence(["X", "Y"])
        ]


# ---------- probabilities sum to one ----------


def _contexts(model: ReadingModel):
    for key in model.reading_bigram:
        yield "transition", key
    for key in model.sign_context:
        yield "sign_context", key
    for key in model.next_sign_context:
        yield "next_sign_context", key


def _score(model: ReadingModel, table: str, key, reading: str, mode: str) -> float:
    if table == "transition":
        return model._transition(key, reading, mode)
    if table == "sign_context":
        return model._sign_context(key[0], key[1], reading, mode)
    return model._next_sign_context(key[0], key[1], reading, mode)


@pytest.mark.parametrize("mode", ["wb", "ad"])
def test_probabilities_sum_to_one_over_the_vocabulary_and_the_oov_bucket(toy, mode):
    vocabulary = vocabulary_of(toy)
    checked = 0
    for table, key in _contexts(toy):
        total = sum(_score_exp(toy, table, key, r, mode) for r in vocabulary)
        total += _score_exp(toy, table, key, "<an out-of-vocabulary reading>", mode)
        assert total == pytest.approx(1.0, abs=1e-12), (table, key)
        checked += 1
    assert checked > 20


def _score_exp(model, table, key, reading, mode):
    from math import exp

    return exp(_score(model, table, key, reading, mode))


def test_c3_with_a_pooled_level_sums_to_one_over_the_pooled_vocabulary():
    pairs = [("A B", "a1 b1")] * 3 + [("A B", "a1 b2")] + [("A C", "a2 c1")] * 2
    pooled = train_reading_model(corpus(pairs + [("A B", "a2 b1")] * 2 + [("A D", "a1 d1")] * 4))
    stage = train_reading_model(corpus(pairs)).attach_pooled(pooled)
    vocabulary = vocabulary_of(pooled)  # the stage's R is a subset of the pooled R
    for table, key in _contexts(stage):
        total = sum(_score_exp(stage, table, key, r, "ad") for r in vocabulary)
        total += _score_exp(stage, table, key, "<oov>", "ad")
        assert total == pytest.approx(1.0, abs=1e-12), (table, key)


def test_c3_uses_the_pooled_estimate_only_when_the_pooled_context_is_seen():
    stage = train_reading_model(corpus([("A B", "a1 b1")] * 2 + [("A B", "a1 b2")]))
    empty_pooled = ReadingModel()  # attests nothing at all
    stage.attach_pooled(empty_pooled)
    alone = train_reading_model(corpus([("A B", "a1 b1")] * 2 + [("A B", "a1 b2")]))
    for reading in ("b1", "b2", "zz"):
        assert stage._transition("a1", reading, "ad") == alone._transition("a1", reading, "ad")


def test_the_pooled_level_is_one_level_deep_and_changes_the_value():
    stage_pairs = [("A B", "a1 b1")]
    pooled = train_reading_model(corpus(stage_pairs + [("A B", "a1 b2")] * 3))
    stage = train_reading_model(corpus(stage_pairs)).attach_pooled(pooled)
    with_pooled = stage._transition("a1", "b2", "ad")
    without = train_reading_model(corpus(stage_pairs))._transition("a1", "b2", "ad")
    assert with_pooled > without  # the pooled model has seen b2 after a1
    # decoding with the pooled model itself skips the first level: it has no pooled model,
    # so its value is its own add-one-level estimate and attaching nothing changes nothing
    assert pooled.pooled is None
    alone = train_reading_model(corpus(stage_pairs + [("A B", "a1 b2")] * 3))
    assert pooled._transition("a1", "b2", "ad") == alone._transition("a1", "b2", "ad")


# ---------- the pathology of section 1 ----------


def test_off_gives_a_free_transition_to_a_context_with_one_successor(toy):
    # N = 1, V = 1 (the section 1 case) and N = 5, V = 1 (R1: the defect is V_obs = 1).
    assert toy._transition("a1", "b1") == 0.0
    assert toy._transition("c1", "d1") == 0.0
    assert toy._transition("a1", "zz") == pytest.approx(log(0.1 / 1.1))


@pytest.mark.parametrize("mode", ["wb", "ad"])
def test_every_scheme_charges_the_single_successor_something(toy, mode):
    for previous, successor in (("a1", "b1"), ("c1", "d1")):
        assert toy._transition(previous, successor, mode) < -0.01
        for other in vocabulary_of(toy):
            if other != successor:
                # an unseen successor is still much less likely than the seen one
                assert toy._transition(previous, other, mode) < toy._transition(
                    previous, successor, mode
                )


def test_witten_bell_values_are_the_formula(toy):
    uni = toy._p_unigram("b1")
    # singleton: lambda = 1/2, so the one successor scores 0.5 + 0.5 * P_uni, not 1.0
    assert toy._transition("a1", "b1", "wb") == pytest.approx(log(0.5 + 0.5 * uni))
    # N = 5, V = 1: lambda = 5/6
    assert toy._transition("c1", "d1", "wb") == pytest.approx(
        log(5 / 6 + 1 / 6 * toy._p_unigram("d1"))
    )
    # a rich context keeps most of its own evidence
    counts = toy.reading_bigram["e1"]
    total, observed = sum(counts.values()), len(counts)
    lam = total / (total + observed)
    assert toy._transition("e1", "f1", "wb") == pytest.approx(
        log(lam * counts["f1"] / total + (1 - lam) * toy._p_unigram("f1"))
    )


def test_sign_context_scores_use_the_sign_distribution_as_lower_order(toy):
    # (previous sign, sign) -> reading; lower order is P(reading | the current sign)
    key = ("C", "D")
    assert toy._sign_context(*key, "d1", "wb") == pytest.approx(
        log(5 / 6 + 1 / 6 * toy._p_sign("D", "d1"))
    )
    # (sign, next sign) -> reading; lower order is P(reading | the first sign)
    assert toy._next_sign_context("C", "D", "c1", "wb") == pytest.approx(
        log(5 / 6 + 1 / 6 * toy._p_sign("C", "c1"))
    )
    # a sign nobody has seen backs off to the unigram
    assert toy._p_sign("never", "d1") == toy._p_unigram("d1")


def test_the_sign_distribution_is_itself_a_distribution(toy):
    vocabulary = vocabulary_of(toy)
    for sign in ("E", "F", "H", "never"):
        total = sum(toy._p_sign(sign, r) for r in vocabulary) + toy._p_sign(sign, "<oov>")
        assert total == pytest.approx(1.0, abs=1e-12), sign


def test_absolute_discounting_values_are_the_formula(toy):
    report = toy.discount("transition")
    n1 = sum(1 for readings in toy.reading_bigram.values() for c in readings.values() if c == 1)
    n2 = sum(1 for readings in toy.reading_bigram.values() for c in readings.values() if c == 2)
    assert (report["n1"], report["n2"]) == (n1, n2)
    d = n1 / (n1 + 2 * n2)
    assert 0 < d < 1 and report["d"] == d and report["fallback"] is False
    counts = toy.reading_bigram["a1"]  # N = 1, V = 1
    assert toy._transition("a1", "b1", "ad") == pytest.approx(
        log((1 - d) / 1 + d * 1 / 1 * toy._p_unigram("b1"))
    )
    # an unseen successor only receives the redistributed mass
    assert toy._transition("a1", "zz", "ad") == pytest.approx(log(d * toy._p_unigram("zz")))
    assert counts == Counter({"b1": 1})


def test_ney_discount_falls_back_when_undefined():
    # n1 = 2, n2 = 0 gives d = 1, outside the open interval: the fallback applies
    only_singletons = train_reading_model(corpus([("A B", "a b"), ("C D", "c d")]))
    report = only_singletons.discount("transition")
    assert (report["n1"], report["n2"]) == (4, 0)
    assert (report["fallback"], report["d"]) == (True, FALLBACK_DISCOUNT)
    # no counts at all: n1 + 2 * n2 = 0
    assert ReadingModel().discount("sign_context") == {
        "n1": 0,
        "n2": 0,
        "d": FALLBACK_DISCOUNT,
        "fallback": True,
    }
    # one reading seen once and two seen twice give d = 1 / (1 + 4) = 0.2, no fallback
    rich = train_reading_model(corpus([("A", "a")] * 2 + [("A", "b")] * 2 + [("A", "c")]))
    report = rich.discount("transition")
    assert (report["n1"], report["n2"], report["d"], report["fallback"]) == (1, 2, 0.2, False)
    assert set(rich.smoothing_report()) == {
        "vocabulary",
        "unigram_total",
        "transition",
        "sign_context",
        "next_sign_context",
    }
    assert rich.smoothing_report()["vocabulary"] == 3


# ---------- what is left alone ----------


@pytest.mark.parametrize("mode", ["wb", "ad"])
def test_unseen_contexts_and_the_unreadable_sentinel_keep_the_add_k_value(toy, mode):
    # N(h) = 0: log(SMOOTHING), exactly as before (BOUNDARY included when it is empty)
    empty = ReadingModel()
    assert empty._transition(BOUNDARY, "x", mode) == log(SMOOTHING)
    assert toy._transition("never-seen", "b1", mode) == log(SMOOTHING)
    assert toy._sign_context("Q", "R", "b1", mode) == log(SMOOTHING)
    assert toy._next_sign_context("Q", "R", "b1", mode) == log(SMOOTHING)
    # into `''` and out of `''`: the add-k value
    assert toy._transition("e1", "", mode) == toy._transition("e1", "")
    assert toy._transition("", "b1", mode) == toy._transition("", "b1")
    assert toy._sign_context("E", "F", "", mode) == toy._sign_context("E", "F", "")


def test_boundary_is_a_context_like_any_other(toy):
    assert toy._transition(BOUNDARY, "a1", "wb") != toy._transition(BOUNDARY, "a1")
    assert BOUNDARY not in vocabulary_of(toy)


def test_oov_readings_are_scored_never_dropped(toy):
    for mode in ("wb", "ad"):
        value = toy._transition("e1", "a-lexicon-only-reading", mode)
        assert value < 0 and value > -50
    counts, total, vocabulary = toy._unigram()
    assert toy._p_unigram("a-lexicon-only-reading") == pytest.approx(
        SMOOTHING / (total + SMOOTHING * (vocabulary + 1))
    )


def test_smoothing_modes_per_scheme():
    assert smoothing_modes("off") == ("off", "off")
    assert smoothing_modes("c2") == ("wb", "wb")
    assert smoothing_modes("c3") == ("ad", "ad")
    assert smoothing_modes("c2_transition_only") == ("wb", "off")


def test_c2_transition_only_leaves_the_sign_context_terms_on_add_k():
    model = train_reading_model(golden_corpus())
    query = ["S1", "S2", "S3", "S1"]
    transition_only = model.predict_sequence_scored(query, smoothing="c2_transition_only")[1]
    off = model.predict_sequence_scored(query, smoothing="off")[1]
    both = model.predict_sequence_scored(query, smoothing="c2")[1]
    assert transition_only != off and transition_only != both


def test_fitting_again_clears_the_derived_tables():
    model = train_reading_model(corpus([("A B", "a b")]))
    first = model._transition("a", "b", "wb")
    model.fit(corpus([("A B", "a b"), ("A C", "a c")]))
    assert model._transition("a", "b", "wb") != first


# ---------- routing stays on add-k (R2) ----------


def test_the_router_ignores_the_decoders_default_scheme(monkeypatch):
    rows = []
    for i in range(4):
        rows.append(
            {
                "hieroglyphs_norm": "𓆓𓂧 𓀀",
                "transliteration_gold": "ḏd =f",
                "language_stage": "Earlier Egyptian",
                "source_text_id": f"EE_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "dd =f",
            }
        )
    for i in range(4):
        rows.append(
            {
                "hieroglyphs_norm": "𓈖𓏏𓈖 𓅓",
                "transliteration_gold": "n m",
                "language_stage": "Late Egyptian",
                "source_text_id": f"LE_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "n m",
            }
        )
    df = pd.DataFrame(rows)
    cache: dict = {}

    def get(stage):
        if stage not in cache:
            cache[stage] = build_stage_resources(df, stage, use_lexicon=False)
        return cache[stage]

    before = choose_stage_by_likelihood("𓆓𓂧 𓀀", get)
    monkeypatch.setattr(reading_model, "TRANSITION_SMOOTHING_BY_DEFAULT", "c2")
    after = choose_stage_by_likelihood("𓆓𓂧 𓀀", get)
    assert after == before
    # ...while asking the router for a scheme explicitly is the diagnostic the experiment uses
    asked = choose_stage_by_likelihood("𓆓𓂧 𓀀", get, smoothing="c2")
    assert asked[1] != before[1]
    # and the decoder's default has moved, so the monkeypatch really was in force
    model = get("Earlier Egyptian").reading_model
    default_score = model.predict_sequence_scored(["𓆓𓂧", "𓀀"])[1]
    assert default_score == model.predict_sequence_scored(["𓆓𓂧", "𓀀"], smoothing="c2")[1]
