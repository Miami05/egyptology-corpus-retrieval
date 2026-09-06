"""Item C1b: `SegmentationWeights.unattested_may_cross_hints`, the switchable veto.

Until item C the lattice refused outright to propose an *unattested* multi-glyph span
that crossed one of the paste's own spaces ("only propose an unattested span as a whole
pasted group or a single glyph"). C1b makes that veto a flag. What has to be proved:

1. **The flag is off by default and off is a no-op.** With the flag False the chosen
   segmentation is what the pre-C1b code chose, on 500 corpus rows with their spacing
   scrambled — checked against a reference DP that carries the veto in its own code, so
   the new code cannot be "proved identical to itself". Same shape as the proof in
   `tests/test_boundary_model.py`.
2. **Unspaced input cannot be affected.** No spaces means no hints, and the veto only
   ever fired on a hint, so both settings must give the identical result.
3. **The flag really lifts the veto** (a positive control): on a toy corpus where an
   unattested span crossing a hint is the highest-scoring analysis, the flag off cannot
   reach it and the flag on chooses it.
4. **Nothing but the candidate set changes.** With the flag on, a span crossing k hints
   still pays `hint_crossed` k times and κ per glyph — the score the decoder reports is
   the score `score_segmentation` computes for the same groups.
"""

from __future__ import annotations

import random
from math import log

import pandas as pd
import pytest

from app.services.reading_model import train_reading_model
from app.services.segmentation import (
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
    glyph_stream,
)

EXAMPLES = "data/processed/examples.csv"

P_DROP = 0.3
P_ADD = 0.2


def boundaries(groups: list[str]) -> set[int]:
    out: set[int] = set()
    position = 0
    for group in groups[:-1]:
        position += len(group)
        out.add(position)
    return out


def scramble(groups: list[str], rng: random.Random) -> list[str]:
    """The eval script's scramble, so the proof runs on paste-shaped input."""
    stream = "".join(groups)
    gold = boundaries(groups)
    kept = {b for b in gold if rng.random() >= P_DROP}
    for position in range(1, len(stream)):
        if position not in gold and rng.random() < P_ADD:
            kept.add(position)
    out, start = [], 0
    for cut in sorted(kept) + [len(stream)]:
        out.append(stream[start:cut])
        start = cut
    return out


def reference_segment(segmenter: Segmenter, groups_as_pasted: list[str]) -> list[str]:
    """The objective as it stood before C1b, written out independently: the veto on an
    unattested multi-glyph span across a hint is unconditional here."""
    stream, hints = glyph_stream(groups_as_pasted)
    n = len(stream)
    if n == 0:
        return []
    w = segmenter.weights
    log_boundary, no_boundary_prefix = segmenter._boundary_terms(stream)
    best: list[tuple[float, int]] = [(float("-inf"), -1)] * (n + 1)
    best[0] = (0.0, -1)
    for j in range(1, n + 1):
        top, arg = float("-inf"), -1
        for i in range(max(0, j - segmenter.max_group_glyphs), j):
            prefix = best[i][0]
            if prefix == float("-inf"):
                continue
            span = stream[i:j]
            crossed = sum(1 for b in hints if i < b < j)
            group_score = segmenter.log_prob(span)
            if group_score is None:
                if len(span) > 1 and crossed:
                    continue
                group_score = -w.unattested_per_glyph * len(span)
            score = (
                prefix
                + group_score
                + w.hint_kept * (1 if i in hints else 0)
                - w.hint_crossed * crossed
            )
            if log_boundary:
                score += w.boundary_model * (
                    (log_boundary[i] if i > 0 else 0.0)
                    + no_boundary_prefix[j - 1]
                    - no_boundary_prefix[i]
                )
            if score > top:
                top, arg = score, i
        best[j] = (top, arg)
    groups: list[str] = []
    j = n
    while j > 0:
        i = best[j][1]
        groups.append(stream[i:j])
        j = i
    groups.reverse()
    return groups


@pytest.fixture(scope="module")
def corpus() -> pd.DataFrame:
    from app.data.loader import load_examples_csv

    return load_examples_csv(EXAMPLES)


@pytest.fixture(scope="module")
def restricted(corpus) -> Segmenter:
    """The shipped default: the veto in place."""
    return Segmenter(train_reading_model(corpus))


@pytest.fixture(scope="module")
def relaxed(restricted) -> Segmenter:
    """The same counts with the veto lifted."""
    return Segmenter(
        restricted.model,
        restricted.weights.replace(unattested_may_cross_hints=True),
        boundary_model=restricted.boundary_model,
    )


def test_the_restriction_is_the_shipped_default():
    assert DEFAULT_SEGMENTATION_WEIGHTS.unattested_may_cross_hints is False


def test_flag_off_is_byte_identical_to_the_pre_c1b_objective(restricted, corpus):
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=500, random_state=7)
    rng = random.Random(7)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        pasted = scramble(gold, rng)
        assert restricted.segment(pasted).groups == reference_segment(restricted, pasted)
        checked += 1
    assert checked >= 400, checked


def test_unspaced_input_cannot_see_the_flag(restricted, relaxed, corpus):
    """No spaces, no hints: the veto never fired there, so both settings agree."""
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=200, random_state=7)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        stream = ["".join(gold)]
        a, b = restricted.segment(stream), relaxed.segment(stream)
        assert a.groups == b.groups
        assert a.score == b.score
        checked += 1
    assert checked >= 150, checked


def test_on_real_pastes_the_flag_only_ever_buys_a_crossing_unattested_span(
    restricted, relaxed, corpus
):
    """Where the two settings disagree, the relaxed one has taken a span the veto
    forbade — an unattested group that swallows one of the paste's spaces — and the
    restricted one has no such group anywhere. That is the whole difference."""
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=500, random_state=7)
    rng = random.Random(7)
    differing = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        pasted = scramble(gold, rng)
        a, b = restricted.segment(pasted), relaxed.segment(pasted)
        _stream, hints = glyph_stream(pasted)

        def crossing_unattested(segmentation) -> list[str]:
            found, position = [], 0
            for group in segmentation.groups:
                start, end = position, position + len(group)
                if (
                    len(group) > 1
                    and not restricted.is_known(group)
                    and any(start < h < end for h in hints)
                ):
                    found.append(group)
                position = end
            return found

        assert crossing_unattested(a) == []
        if a.groups != b.groups:
            differing += 1
            assert crossing_unattested(b), (pasted, b.groups)
    assert differing > 0, "the flag changed nothing at all on 500 scrambled rows"


# --------------------------------------------------------------------------- #
# positive control on a toy corpus
# --------------------------------------------------------------------------- #

A, B, C = "\U00013000", "\U00013001", "\U00013002"  # A1, A2, A3


@pytest.fixture(scope="module")
def toy() -> Segmenter:
    """Three signs; `AB` is attested, `BC` and `ABC` are not."""
    frame = pd.DataFrame(
        [
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
        ]
    )
    model = train_reading_model(frame)
    # κ tiny, so the unattested three-glyph span `ABC` is the cheapest analysis by
    # score and only the veto can keep it out. Under κ alone `ABC` and `A B C` tie
    # exactly (κ is per glyph), so the tie is broken by a quadrat penalty on the two
    # interior positions — a cut there is what the paste's layout says not to do.
    # The boundary term is off, so every number below can be checked by hand.
    weights = DEFAULT_SEGMENTATION_WEIGHTS.replace(
        unattested_per_glyph=0.01,
        hint_crossed=0.0,
        hint_kept=0.0,
        quadrat_crossed=5.0,
        boundary_model=0.0,
        lexicon_weight=0.0,
    )
    return Segmenter(model, weights, use_lexicon=False)


# One hint (position 2) and a layout that says do not cut at 1 or 2. Scores:
#   [ABC]      -3κ                          = -0.03   (unattested, crosses the hint)
#   [AB][C]    log P(AB) + log P(C) - 5     = -7.197
#   [A][B][C]  -3κ - 5 - 5                  = -10.03
PASTED = [f"{A}{B}", C]
NO_CUT = frozenset({1, 2})


def test_veto_blocks_the_unattested_span_when_the_flag_is_off(toy):
    assert not toy.is_known(f"{A}{B}{C}")
    chosen = toy.segment(PASTED, no_cut=NO_CUT)
    assert chosen.groups == [f"{A}{B}", C]
    assert chosen.score == pytest.approx(2 * log(2 / 6) - 5.0)


def test_flag_on_makes_the_crossing_span_reachable(toy):
    relaxed = Segmenter(
        toy.model,
        toy.weights.replace(unattested_may_cross_hints=True),
        use_lexicon=False,
    )
    chosen = relaxed.segment(PASTED, no_cut=NO_CUT)
    assert chosen.groups == [f"{A}{B}{C}"]
    assert chosen.score == pytest.approx(-0.03)
    assert chosen.unattested_groups == [f"{A}{B}{C}"]
    assert chosen.crossed_hints == [2]


def test_the_crossing_span_still_pays_the_crossing_penalty_and_kappa(toy):
    """The flag adds a candidate; it does not make the candidate cheaper."""
    weights = toy.weights.replace(unattested_may_cross_hints=True, hint_crossed=1.0)
    relaxed = Segmenter(toy.model, weights, use_lexicon=False)
    stream = f"{A}{B}{C}"
    hints = {2}
    scored = relaxed.score_segmentation([stream], hints)
    # κ per glyph, one crossed hint — and nothing else.
    assert scored == pytest.approx(-weights.unattested_per_glyph * 3 - weights.hint_crossed)
    # The decoder's own score for whatever it picks is that same objective.
    chosen = relaxed.segment([f"{A}{B}", C])
    assert chosen.score == pytest.approx(
        relaxed.score_segmentation(chosen.groups, hints)
    )


def test_relaxed_lattice_never_scores_a_span_above_its_attested_probability(toy):
    """Guard against the flag accidentally granting an unattested span a probability:
    `log_prob` still returns None for it, both ways."""
    relaxed = Segmenter(
        toy.model,
        toy.weights.replace(unattested_may_cross_hints=True),
        use_lexicon=False,
    )
    assert relaxed.log_prob(f"{A}{B}{C}") is None
    # 2 tokens of AB out of 4 group tokens, vocabulary 2 in the denominator.
    assert relaxed.log_prob(f"{A}{B}") == pytest.approx(log(2 / (4 + 2)))
