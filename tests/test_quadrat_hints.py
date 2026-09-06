"""Item B: the format controls read as weak segmenter hints.

Two things are pinned here.

1. **The invariant.** `quadrat_hints(value)[0]` must equal
   `normalize_hieroglyphs(value).split()` for every input. The hint extractor runs a
   second copy of the normalisation pipeline that keeps U+13430-1345F in place
   instead of deleting them; if that copy ever drifts from the real one, positions
   would be computed against a different sign stream and the hints would be silently
   wrong. Checked on the 8 expert pastes, on every St Andrews line when the
   (gitignored) raw file is present, and on a seeded fuzz of hostile shapes.

2. **The no-op.** `Segmenter.segment(groups)` with the default empty `no_cut` must
   return byte-identical segmentations to the pre-item-B code. Proved on 500 corpus
   rows with their spacing scrambled, seed fixed, against a reference re-implementation
   of the old objective.

`hypothesis` is not a dependency of this project (2026-09-06), so the fuzz case is a
seeded `random.Random`, not a hypothesis strategy.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import pytest

from app.data.normalizer import (
    QUADRAT_BRACKETS,
    QUADRAT_JOINERS,
    normalize_hieroglyphs,
    quadrat_hints,
)
from app.services.reading_model import train_reading_model
from app.services.segmentation import Segmenter, glyph_stream, segment_paste

PASTES_PATH = Path("data/benchmarks/expert_paste_queries.csv")
STANDREWS_LINES = Path("data/raw/standrews/standrews_lines.csv")

# Real signs used to build fuzz inputs; nothing here depends on their readings.
SIGNS = "𓀀𓂧𓆓𓆑𓈖𓏏𓏥𓂋𓍿𓎟𓊵𓏙𓇓"
CONTROLS = [chr(c) for c in range(0x13430, 0x13456)]


def check_invariant(value: str) -> tuple[list[str], frozenset[int]]:
    groups, no_cut = quadrat_hints(value)
    assert groups == normalize_hieroglyphs(value).split(), value
    total = sum(len(g) for g in groups)
    for position in no_cut:
        assert 0 < position < total, (value, position, total)
    return groups, no_cut


# --------------------------------------------------------------------------- #
# 1. the invariant
# --------------------------------------------------------------------------- #


def test_invariant_on_expert_pastes():
    queries = pd.read_csv(PASTES_PATH, keep_default_na=False)
    assert len(queries) == 8
    for value in queries["query_input"]:
        check_invariant(str(value))


def test_paste_005_marks_every_within_group_boundary():
    """PASTE_005 joins every sign of each chunk horizontally, so the hints say
    'do not cut anywhere inside a pasted group' and nothing about the group
    boundaries themselves. That is why a *hard* no-cut rule would fail the gate."""
    queries = pd.read_csv(PASTES_PATH, keep_default_na=False)
    row = queries[queries["benchmark_id"] == "PASTE_005"].iloc[0]
    groups, no_cut = check_invariant(str(row["query_input"]))
    _stream, hints = glyph_stream(groups)
    total = sum(len(g) for g in groups)
    inside = {b for b in range(1, total)} - hints
    assert set(no_cut) == inside
    assert not (set(no_cut) & hints)


@pytest.mark.skipif(
    not STANDREWS_LINES.exists(),
    reason="data/raw/standrews/standrews_lines.csv is gitignored and absent here",
)
def test_invariant_on_every_standrews_line():
    lines = pd.read_csv(STANDREWS_LINES, keep_default_na=False)
    for value in lines["hieroglyphs"].astype(str):
        check_invariant(value)


def test_invariant_under_seeded_fuzz():
    rng = random.Random(19)
    for _ in range(400):
        pieces: list[str] = []
        for _ in range(rng.randrange(1, 12)):
            roll = rng.random()
            if roll < 0.45:
                pieces.append(rng.choice(SIGNS))
            elif roll < 0.75:
                pieces.append(rng.choice(CONTROLS))
            elif roll < 0.85:
                pieces.append(" ")
            elif roll < 0.92:
                pieces.append(rng.choice(["(", ")", "[", "]", "x", "12", "—", "︀"]))
            else:
                pieces.append(rng.choice(["<g>D77</g>", "<g></g>", "A1", "⟦", "⟧"]))
        check_invariant("".join(pieces))


def test_hostile_shapes_do_not_raise():
    for value in ("", "   ", "\U00013431\U00013432", "<g>D77</g>", "…—()[]"):
        check_invariant(value)


# --------------------------------------------------------------------------- #
# 2. what the controls mean
# --------------------------------------------------------------------------- #


def test_joiner_between_two_signs_marks_that_boundary():
    for code in sorted(QUADRAT_JOINERS):
        groups, no_cut = check_invariant(f"𓆓{chr(code)}𓂧𓆑")
        assert groups == ["𓆓𓂧𓆑"]
        assert no_cut == frozenset({1}), hex(code)


def test_bracket_pair_marks_every_boundary_strictly_inside():
    for open_code, close_code in QUADRAT_BRACKETS.items():
        value = f"𓆓{chr(open_code)}𓂧𓆑𓈖{chr(close_code)}𓏏"
        groups, no_cut = check_invariant(value)
        assert groups == ["𓆓𓂧𓆑𓈖𓏏"]
        # signs inside the pair are indices 1,2,3 -> boundaries 2 and 3
        assert no_cut == frozenset({2, 3}), hex(open_code)


def test_mirror_blanks_and_damage_carry_no_hint():
    for code in [0x13440, *range(0x13441, 0x13456)]:
        _groups, no_cut = check_invariant(f"𓆓{chr(code)}𓂧")
        assert no_cut == frozenset(), hex(code)


def test_joiner_across_a_group_separating_space_is_ignored():
    _groups, no_cut = check_invariant("𓆓\U00013430 𓂧")
    assert no_cut == frozenset()


def test_unmatched_bracket_contributes_nothing():
    _groups, no_cut = check_invariant("𓆓\U00013437𓂧𓆑")
    assert no_cut == frozenset()
    _groups, no_cut = check_invariant("𓆓𓂧\U00013438𓆑")
    assert no_cut == frozenset()


def test_no_controls_means_no_hints():
    groups, no_cut = check_invariant("𓊵𓏙 𓇓𓏏")
    assert groups == ["𓊵𓏙", "𓇓𓏏"]
    assert no_cut == frozenset()


# --------------------------------------------------------------------------- #
# 3. the no-op proof
# --------------------------------------------------------------------------- #


def reference_segment(segmenter: Segmenter, groups_as_pasted: list[str]) -> list[str]:
    """The pre-item-B objective, written out again so the new code cannot be
    'proved identical to itself'. Kept deliberately close to the original."""
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
def segmenter() -> Segmenter:
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    return Segmenter(train_reading_model(df))


def test_empty_no_cut_is_byte_identical_to_the_old_objective(segmenter):
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    rows = df[df["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=500, random_state=7)
    rng = random.Random(7)
    checked = 0
    for _, row in sample.iterrows():
        gold = str(row["hieroglyphs_norm"]).split()
        if len(gold) < 2:
            continue
        pasted = scramble(gold, rng)
        result = segmenter.segment(pasted)
        assert result.groups == reference_segment(segmenter, pasted)
        assert result.crossed_quadrats == []
        checked += 1
    assert checked >= 400, checked


def test_shipped_default_is_the_constant_item_b_selected(segmenter):
    """1.0: the highest of the four candidates that keeps the expert paste gate at
    8/8 (2.0 has the better BBAW dev F1 and fails PASTE_005). See
    `SegmentationWeights.quadrat_crossed` for the sweep."""
    assert segmenter.weights.quadrat_crossed == 1.0


def test_a_query_without_controls_is_unaffected_by_the_hints(segmenter):
    """The whole corpus and every benchmark are control-free, so `quadrat_hints`
    returns an empty `no_cut` for them and the objective is the pre-item-B one."""
    for value in ("𓆓𓂧𓆑𓆓𓂧𓀀", "𓊵𓏙 𓇓𓏏", "𓂋𓍿𓀀𓏥 𓎟𓏏"):
        with_hints, groups = segment_paste(value, segmenter, use_format_hints=True)
        without, groups_off = segment_paste(value, segmenter, use_format_hints=False)
        assert groups == groups_off
        assert with_hints.groups == without.groups
        assert with_hints.score == without.score
        assert with_hints.crossed_quadrats == []


def test_quadrat_penalty_bites_when_the_weight_is_raised(segmenter):
    """A penalty large enough to beat the corpus evidence must move a boundary — the
    machinery is wired, whatever constant ships."""
    heavy = Segmenter(segmenter.model, segmenter.weights.replace(quadrat_crossed=50.0))
    value = "𓆓\U00013431𓂧\U00013431𓆑"
    hinted, _groups = segment_paste(value, heavy, use_format_hints=True)
    plain, _groups = segment_paste(value, heavy, use_format_hints=False)
    assert plain.groups == ["𓆓𓂧", "𓆑"]
    assert hinted.groups == ["𓆓𓂧𓆑"]
    assert hinted.crossed_quadrats == []


def test_score_segmentation_charges_the_penalty_too(segmenter):
    heavy = Segmenter(segmenter.model, segmenter.weights.replace(quadrat_crossed=2.0))
    groups = ["𓆓𓂧", "𓆑"]
    base = heavy.score_segmentation(groups, hints=set())
    penalised = heavy.score_segmentation(groups, hints=set(), no_cut=frozenset({2}))
    assert penalised == pytest.approx(base - 2.0)
