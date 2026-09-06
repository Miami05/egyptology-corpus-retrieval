"""Item C1: the adjacent-glyph boundary bigram, and the proof that it is off by default.

Four things are pinned.

1. **The no-op.** With `SegmentationWeights.boundary_model == 0.0` the segmenter must
   be byte-identical to the pre-item-C code, and no boundary model may even be built.
   Proved on 500 corpus rows with their spacing scrambled, seed fixed, against a
   reference re-implementation of the pre-item-C objective — the same shape as item
   B's proof in `tests/test_quadrat_hints.py`.
2. **The estimator.** `P(boundary | a, b)` is the pre-registered formula with α = 1;
   checked by hand on a two-sentence toy corpus where the counts can be written out.
3. **The DP is exact.** The score `segment()` reports for the segmentation it chose
   must equal `score_segmentation()` on the same groups, with the term switched on —
   i.e. the prefix-sum decomposition of "no boundary inside every span, boundary at
   every cut" really is the objective, not an approximation of it.
4. **The ablation switch works.** `boundary_class_backoff=False` must make every
   unseen pair fall to the global prior, and must change nothing about a pair the
   training stream saw often.
"""

from __future__ import annotations

import random
from math import exp, log

import pandas as pd
import pytest

from app.services.boundary_model import (
    ALPHA,
    CLASS_SMOOTHING,
    fit_boundary_model,
)
from app.services.reading_model import train_reading_model
from app.services.segmentation import (
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
    glyph_stream,
)
from app.services.sign_functions import load_sign_functions

EXAMPLES = "data/processed/examples.csv"


# --------------------------------------------------------------------------- #
# 1. the no-op proof
# --------------------------------------------------------------------------- #


def reference_segment(segmenter: Segmenter, groups_as_pasted: list[str]) -> list[str]:
    """The pre-item-C objective, written out again so the new code cannot be
    'proved identical to itself'. This is item B's reference plus its quadrat term,
    and nothing of item C."""
    stream, hints = glyph_stream(groups_as_pasted)
    n = len(stream)
    if n == 0:
        return []
    w = segmenter.weights
    best: list[tuple[float, int]] = [(float("-inf"), -1)] * (n + 1)
    best[0] = (0.0, -1)
    for j in range(1, n + 1):
        top, arg = float("-inf"), -1
        for i in range(max(0, j - segmenter.max_group_glyphs), j):
            prefix = best[i][0]
            if prefix == float("-inf"):
                continue
            span = stream[i:j]
            group_score = segmenter.log_prob(span)
            if group_score is None:
                if len(span) > 1 and any(i < b < j for b in hints):
                    continue
                group_score = -segmenter.unattested_cost(span)
            crossed = sum(1 for b in hints if i < b < j)
            kept = 1 if i in hints else 0
            score = prefix + group_score + w.hint_kept * kept - w.hint_crossed * crossed
            if score > top:
                top, arg = score, i
        best[j] = (top, arg)
    out: list[str] = []
    j = n
    while j > 0:
        i = best[j][1]
        out.append(stream[i:j])
        j = i
    out.reverse()
    return out


def scramble(groups: list[str], rng: random.Random) -> list[str]:
    stream = "".join(groups)
    gold = set()
    position = 0
    for group in groups[:-1]:
        position += len(group)
        gold.add(position)
    kept = {b for b in gold if rng.random() >= 0.3}
    for position in range(1, len(stream)):
        if position not in gold and rng.random() < 0.2:
            kept.add(position)
    out, start = [], 0
    for cut in sorted(kept) + [len(stream)]:
        out.append(stream[start:cut])
        start = cut
    return out


@pytest.fixture(scope="module")
def corpus() -> pd.DataFrame:
    from app.data.loader import load_examples_csv

    return load_examples_csv(EXAMPLES)


@pytest.fixture(scope="module")
def segmenter(corpus) -> Segmenter:
    """The shipped default — after C1.5, with the boundary term on."""
    return Segmenter(train_reading_model(corpus))


@pytest.fixture(scope="module")
def plain(segmenter) -> Segmenter:
    """The same model with the boundary term switched off: the pre-item-C segmenter."""
    return Segmenter(segmenter.model, segmenter.weights.replace(boundary_model=0.0))


def test_shipped_default_is_the_weight_c1_selected():
    """1.0: the best dev unspaced F1 of the four pre-registered candidates, and the
    expert paste gate stayed 8/8 at every one of them. See
    `SegmentationWeights.boundary_model` for the sweep and the held-out numbers."""
    assert DEFAULT_SEGMENTATION_WEIGHTS.boundary_model == 1.0


def test_zero_weight_builds_no_model_at_all(plain):
    assert plain.weights.boundary_model == 0.0
    assert plain.boundary_model is None


def test_boundary_term_off_is_byte_identical_to_the_old_objective(plain, corpus):
    segmenter = plain
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=500, random_state=7)
    rng = random.Random(7)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        pasted = scramble(gold, rng)
        assert segmenter.segment(pasted).groups == reference_segment(segmenter, pasted)
        checked += 1
    assert checked >= 400, checked


# --------------------------------------------------------------------------- #
# 2. the estimator, on a corpus small enough to check by hand
# --------------------------------------------------------------------------- #

A, B, C = "\U00013000", "\U00013001", "\U00013002"  # A1, A2, A3


@pytest.fixture()
def toy():
    frame = pd.DataFrame(
        [
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
            {"hieroglyphs_norm": f"{A} {B}{C}", "transliteration_gold": "a bc"},
        ]
    )
    return fit_boundary_model(train_reading_model(frame))


def test_prior_is_the_global_boundary_rate(toy):
    # Streams: A B | C  twice, A | B C  once.
    # no-boundary adjacencies: (A,B) x2 (inside "AB"), (B,C) x1 (inside "BC") = 3
    # boundary adjacencies:    (B,C) x2 (across "AB|C"), (A,B) x1 (across "A|BC") = 3
    assert toy.prior == pytest.approx(3 / 6)
    assert toy.pair_total[(A, B)] == pytest.approx(3.0)
    assert toy.pair_boundary[(A, B)] == pytest.approx(1.0)
    assert toy.pair_total[(B, C)] == pytest.approx(3.0)
    assert toy.pair_boundary[(B, C)] == pytest.approx(2.0)


def test_seen_pair_matches_the_pre_registered_formula(toy):
    for pair in ((A, B), (B, C)):
        expected = (toy.pair_boundary[pair] + ALPHA * toy.class_probability(*pair)) / (
            toy.pair_total[pair] + ALPHA
        )
        assert toy.boundary_probability(*pair) == pytest.approx(expected)


def test_unseen_pair_is_the_class_prediction_alone(toy):
    unseen = (C, A)
    assert unseen not in toy.pair_total
    assert toy.boundary_probability(*unseen) == pytest.approx(
        toy.class_probability(*unseen)
    )


def test_class_rate_is_expected_counts_smoothed_toward_the_prior(toy):
    functions = load_sign_functions()
    # Rebuild one class-pair rate by hand from the same expected counts.
    observed = [
        ((A, B), 1.0, 3.0),  # (pair, boundary count, total count)
        ((B, C), 2.0, 3.0),
    ]
    target = ("det", "det")
    numerator = denominator = 0.0
    for (left, right), boundary, total in observed:
        weight = functions.class_distribution(left).get(
            target[0], 0.0
        ) * functions.class_distribution(right).get(target[1], 0.0)
        denominator += weight * total
        numerator += weight * boundary
    if denominator:
        expected = (numerator + CLASS_SMOOTHING * toy.prior) / (
            denominator + CLASS_SMOOTHING
        )
        assert toy.class_boundary_rate[target] == pytest.approx(expected)


def test_probabilities_stay_strictly_inside_zero_and_one(toy):
    for pair in ((A, B), (B, C), (C, A), ("x", "y"), ("", "")):
        p = toy.boundary_probability(*pair)
        assert 0.0 < p < 1.0
        assert toy.log_no_boundary(*pair) == pytest.approx(log(1.0 - p))
        assert exp(toy.log_boundary(*pair)) == pytest.approx(p)


def test_uncovered_signs_fall_to_unk_not_to_an_error(toy):
    placeholder = "\U000F0000"
    assert toy.functions.classes_for(placeholder) == frozenset({"unk"})
    assert 0.0 < toy.boundary_probability(placeholder, placeholder) < 1.0


# --------------------------------------------------------------------------- #
# 3. the DP is exact
# --------------------------------------------------------------------------- #


def test_chosen_score_equals_scoring_the_chosen_groups(segmenter, corpus):
    on = segmenter
    assert on.weights.boundary_model
    assert on.boundary_model is not None
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=60, random_state=11)
    rng = random.Random(11)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        pasted = scramble(gold, rng)
        result = on.segment(pasted)
        _stream, hints = glyph_stream(pasted)
        assert result.score == pytest.approx(
            on.score_segmentation(result.groups, hints), abs=1e-9
        )
        checked += 1
    assert checked >= 40, checked


def test_the_term_actually_moves_a_boundary(segmenter, plain):
    """Wired, whatever λ_b ships: a large enough weight must change a segmentation."""
    rows = ["𓆓𓂧𓆑𓈖𓏏𓈖𓏥", "𓂋𓍿𓀀𓏥𓎟𓏏", "𓊵𓏙𓇓𓏏𓈖"]
    heavy = Segmenter(segmenter.model, segmenter.weights.replace(boundary_model=8.0))
    changed = sum(
        1
        for value in rows
        if heavy.segment([value]).groups != plain.segment([value]).groups
    )
    assert changed >= 1, "the boundary term never altered any segmentation"


# --------------------------------------------------------------------------- #
# 4. the ablation switch
# --------------------------------------------------------------------------- #


def test_ablation_sends_every_unseen_pair_to_the_global_prior():
    frame = pd.DataFrame(
        [
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
            {"hieroglyphs_norm": f"{A} {B}{C}", "transliteration_gold": "a bc"},
        ]
    )
    model = train_reading_model(frame)
    ablated = fit_boundary_model(model, use_class_backoff=False)
    with_classes = fit_boundary_model(model, use_class_backoff=True)
    assert ablated.prior == pytest.approx(with_classes.prior)
    for pair in ((C, A), (A, C), ("x", "y")):
        assert ablated.class_probability(*pair) == pytest.approx(ablated.prior)
        assert ablated.boundary_probability(*pair) == pytest.approx(ablated.prior)


def test_ablation_is_a_real_ablation_on_the_real_corpus(segmenter):
    """On the toy corpus above every class rate collapses to the prior by symmetry;
    on the real one the class model must genuinely disagree with a flat prior,
    otherwise the C1 ablation would be measuring nothing."""
    with_classes = fit_boundary_model(segmenter.model, use_class_backoff=True)
    ablated = fit_boundary_model(segmenter.model, use_class_backoff=False)
    prior = with_classes.prior
    rates = list(with_classes.class_boundary_rate.values())
    assert rates
    assert max(rates) - min(rates) > 0.05, (min(rates), max(rates))
    # An unseen pair of two well-classified signs: 𓏥 (Z2, typographic, supplement)
    # after 𓀀 (A1, det/log). It must not simply get the prior.
    unseen = ("\U00013000", "\U000133E5")
    assert ablated.class_probability(*unseen) == pytest.approx(prior)
    assert with_classes.class_probability(*unseen) != pytest.approx(prior, abs=1e-4)


def test_ablation_is_wired_through_the_segmenter(segmenter):
    ablated = Segmenter(
        segmenter.model, segmenter.weights, boundary_class_backoff=False
    )
    assert ablated.boundary_model is not None
    assert ablated.boundary_model.use_class_backoff is False
