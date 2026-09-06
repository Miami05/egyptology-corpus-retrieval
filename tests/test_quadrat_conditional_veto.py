"""Item C1c: the pasted-space veto is lifted only when the spaces are quadrats.

C1b made the veto on an unattested multi-glyph span crossing a pasted space a flag
(`SegmentationWeights.unattested_may_cross_hints`, default False) and measured a
contradiction: lifting it globally *costs* boundary F1 on scrambled corpus spacing and
*buys* reading token F1 on real St Andrews quadrat spacing. C1c resolves it by asking
what a space means. `segment_paste` turns the flag on for one call iff
`normalizer.quadrat_hints` found at least one quadrat hint — i.e. the paste carries
layout controls, so its spaces separate quadrats and a word may legitimately span them.

What has to be proved here:

1. **A paste without controls is untouched.** No controls, no `no_cut`, so
   `segment_paste` must return exactly what the pre-C1c two-liner returned, on real
   corpus rows with paste-shaped (scrambled) spacing.
2. **A paste with controls can now keep an unseen word whole**, and the identical
   paste without controls still cannot. That is the whole change, as a positive
   control on a toy corpus.
3. **`Segmenter.segment` itself is unchanged.** `scripts/run_segmentation_eval.py`
   calls it directly with no `no_cut`, so nothing in that script's path can see C1c.
4. **The caller's segmenter is not mutated** — the lifted view is a shallow copy, so a
   shared cached `Segmenter` (the app builds one per corpus) keeps its own weights.
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

from app.data.normalizer import normalize_hieroglyphs, quadrat_hints
from app.services.reading_model import train_reading_model
from app.services.segmentation import (
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmentation,
    Segmenter,
    glyph_stream,
    segment_paste,
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
    """The segmentation eval's own scramble, so the proof runs on paste-shaped input."""
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


def reference_segment_paste(
    query: str, segmenter: Segmenter, use_format_hints: bool = True
) -> tuple[Segmentation, list[str]]:
    """`segment_paste` exactly as it stood before C1c, written out here so the new
    code is compared with something other than itself."""
    if use_format_hints:
        groups, no_cut = quadrat_hints(query)
        return segmenter.segment(groups, no_cut=no_cut), groups
    groups = normalize_hieroglyphs(query).split()
    return segmenter.segment(groups), groups


@pytest.fixture(scope="module")
def corpus() -> pd.DataFrame:
    from app.data.loader import load_examples_csv

    return load_examples_csv(EXAMPLES)


@pytest.fixture(scope="module")
def segmenter(corpus) -> Segmenter:
    """The shipped default configuration."""
    return Segmenter(train_reading_model(corpus))


# --------------------------------------------------------------------------- #
# 1. a paste without controls is byte-identical to the pre-C1c behaviour
# --------------------------------------------------------------------------- #


def test_paste_without_controls_is_identical_to_the_pre_c1c_path(segmenter, corpus):
    """The corpus carries no layout controls at all, so `no_cut` is empty on every one
    of these pastes and the new branch must never be entered."""
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=400, random_state=7)
    rng = random.Random(7)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        query = " ".join(scramble(gold, rng))
        _groups, no_cut = quadrat_hints(query)
        assert no_cut == frozenset(), "corpus paste unexpectedly carries quadrat hints"
        new, new_groups = segment_paste(query, segmenter)
        old, old_groups = reference_segment_paste(query, segmenter)
        assert new_groups == old_groups
        assert new.groups == old.groups
        assert new.score == old.score
        assert new.crossed_hints == old.crossed_hints
        assert new.inserted_boundaries == old.inserted_boundaries
        assert new.unattested_groups == old.unattested_groups
        assert new.crossed_quadrats == old.crossed_quadrats
        checked += 1
    assert checked >= 300, checked


def test_hints_off_never_enters_the_new_branch(segmenter, corpus):
    """`use_format_hints=False` deletes the controls, so C1c cannot fire there either —
    this is the arm `run_format_hint_eval_standrews.py` calls `hints_off`."""
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=100, random_state=7)
    rng = random.Random(7)
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        query = " ".join(scramble(gold, rng))
        new, _ = segment_paste(query, segmenter, use_format_hints=False)
        old, _ = reference_segment_paste(query, segmenter, use_format_hints=False)
        assert new.groups == old.groups
        assert new.score == old.score


# --------------------------------------------------------------------------- #
# 2. positive control: controls present -> the unseen word survives the space
# --------------------------------------------------------------------------- #

A, B, C = "\U00013000", "\U00013001", "\U00013002"  # A1, A2, A3
JOINER = "\U00013430"  # vertical joiner: "these two signs share a quadrat"


@pytest.fixture(scope="module")
def toy() -> Segmenter:
    """Three signs; `AB` and `C` are attested, `ABC` — the word we want back — is not.

    κ is tiny so that the unattested three-glyph span is the cheapest analysis by
    score and *only the veto* can keep it out; the boundary term is off so every
    number below can be checked by hand.
    """
    frame = pd.DataFrame(
        [
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
            {"hieroglyphs_norm": f"{A}{B} {C}", "transliteration_gold": "ab c"},
        ]
    )
    model = train_reading_model(frame)
    weights = DEFAULT_SEGMENTATION_WEIGHTS.replace(
        unattested_per_glyph=0.01,
        hint_crossed=0.0,
        hint_kept=0.0,
        quadrat_crossed=5.0,
        boundary_model=0.0,
        lexicon_weight=0.0,
    )
    return Segmenter(model, weights, use_lexicon=False)


# The same two signs, pasted with a space between the quadrats. With the joiner the
# paste says "A and B share a quadrat", i.e. no_cut = {1}; without it the paste says
# nothing at all. Either way the pasted space is a hint at position 2.
WITH_CONTROLS = f"{A}{JOINER}{B} {C}"
WITHOUT_CONTROLS = f"{A}{B} {C}"


def test_the_toy_paste_carries_exactly_one_quadrat_hint(toy):
    groups, no_cut = quadrat_hints(WITH_CONTROLS)
    assert groups == [f"{A}{B}", C]
    assert no_cut == frozenset({1})
    plain_groups, plain_no_cut = quadrat_hints(WITHOUT_CONTROLS)
    assert plain_groups == groups
    assert plain_no_cut == frozenset()
    assert not toy.is_known(f"{A}{B}{C}")


def test_controls_present_recovers_the_unseen_word_across_the_space(toy):
    chosen, as_pasted = segment_paste(WITH_CONTROLS, toy)
    assert as_pasted == [f"{A}{B}", C]
    # κ per glyph and nothing else: the span cuts nowhere, so it pays no quadrat
    # penalty, and `hint_crossed` is 0 in this toy.
    assert chosen.groups == [f"{A}{B}{C}"]
    assert chosen.score == pytest.approx(-0.03)
    assert chosen.unattested_groups == [f"{A}{B}{C}"]
    assert chosen.crossed_hints == [2]


def test_the_same_paste_without_controls_still_cannot_reach_it(toy):
    """Identical signs, identical space — only the controls are gone. `ABC` is now
    unreachable at any price, and the lattice shatters the word into single glyphs
    (a single glyph is the one unattested span the veto always allowed)."""
    chosen, as_pasted = segment_paste(WITHOUT_CONTROLS, toy)
    assert as_pasted == [f"{A}{B}", C]
    assert chosen.groups == [A, B, C]
    assert f"{A}{B}{C}" not in chosen.groups
    # And that is the pre-C1c answer, not a coincidence of this fixture.
    old, _ = reference_segment_paste(WITHOUT_CONTROLS, toy)
    assert old.groups == chosen.groups
    assert old.score == chosen.score


def test_the_lifted_call_does_not_mutate_the_caller_s_segmenter(toy):
    before = toy.weights
    segment_paste(WITH_CONTROLS, toy)
    assert toy.weights is before
    assert toy.weights.unattested_may_cross_hints is False
    assert DEFAULT_SEGMENTATION_WEIGHTS.unattested_may_cross_hints is False
    # The heavy statistics are shared rather than refitted: proved by the fact that a
    # second lifted call gives the same answer with the same cache object in place.
    cache_id = id(toy._log_prob_cache)
    segment_paste(WITH_CONTROLS, toy)
    assert id(toy._log_prob_cache) == cache_id


# --------------------------------------------------------------------------- #
# 3. `Segmenter.segment` — the path `run_segmentation_eval.py` uses — is untouched
# --------------------------------------------------------------------------- #


def test_segment_called_directly_still_vetoes(toy):
    """`run_segmentation_eval.py` calls `segmenter.segment(...)`, never
    `segment_paste`, and passes no `no_cut`. C1c lives in `segment_paste`, so that
    script's objective is the shipped one, controls or no controls."""
    groups, no_cut = quadrat_hints(WITH_CONTROLS)
    assert no_cut  # the paste does carry hints ...
    chosen = toy.segment(groups)  # ... and calling segment directly ignores them
    assert chosen.groups == [A, B, C]
    assert f"{A}{B}{C}" not in chosen.groups
    # Even handed the hints explicitly, `segment` keeps the veto — it only pays the
    # quadrat penalty, which pushes it off the three-glyph shattering and onto the
    # attested split. Lifting the veto is `segment_paste`'s decision alone.
    with_no_cut = toy.segment(groups, no_cut=no_cut)
    assert with_no_cut.groups == [f"{A}{B}", C]
    assert f"{A}{B}{C}" not in with_no_cut.groups


def test_the_eval_s_two_calls_never_produce_a_crossing_unattested_span(
    segmenter, corpus
):
    """The corpus-scale version of the same claim, in the exact shape the eval uses:
    `segment(["".join(gold)])` for the unspaced arm and `segment(scrambled)` for the
    scrambled one. A span the veto forbids — an unattested multi-glyph group swallowing
    one of the paste's spaces — must appear in neither."""
    rows = corpus[corpus["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=300, random_state=7)
    rng = random.Random(7)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        pasted = scramble(gold, rng)
        for stream_groups in (["".join(gold)], pasted):
            chosen = segmenter.segment(stream_groups)
            _stream, hints = glyph_stream(stream_groups)
            position = 0
            for group in chosen.groups:
                start, end = position, position + len(group)
                assert not (
                    len(group) > 1
                    and not segmenter.is_known(group)
                    and any(start < h < end for h in hints)
                ), (stream_groups, chosen.groups)
                position = end
        checked += 1
    assert checked >= 200, checked
