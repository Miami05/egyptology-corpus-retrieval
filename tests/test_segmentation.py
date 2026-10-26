"""Phase 1 — the resegmentation lattice.

The user's spaces are hints, not the segmentation. Each test builds a tiny corpus in
which the right grouping is unambiguous by construction and checks that the lattice
finds it from wrong or missing spacing — including the two behaviours the audit
flagged as decisive: a well-attested split must beat a once-attested long group, and
a once-attested long group must beat a three-way split of common short groups.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.normalizer import normalize_hieroglyphs
from app.services.reading_model import glyph_similarity, train_reading_model
from app.services.segmentation import (
    DEFAULT_SEGMENTATION_WEIGHTS,
    MAX_GROUP_GLYPHS,
    Segmenter,
    glyph_stream,
)


def corpus(pairs: list[tuple[str, str]], repeat: int = 1) -> pd.DataFrame:
    rows = []
    for i, (signs, readings) in enumerate(pairs):
        for _ in range(repeat):
            rows.append(
                {
                    "hieroglyphs_norm": signs,
                    "transliteration_gold": readings,
                    "source_text_id": f"T{i}",
                    "source_sentence_id": f"S{i}",
                }
            )
    return pd.DataFrame(rows)


def filler(tokens: int = 10_000, distinct: int = 50) -> pd.DataFrame:
    """Background mass of unrelated groups.

    The singleton-vs-split decision depends on the size of the corpus: a group seen
    300 times is 300/70k of the real corpus, not 300/320 of a toy one. Tests that pin
    that decision add this filler so the proportions resemble the real corpus.
    """
    per_group = tokens // distinct
    return corpus([(f"F{i}", f"f{i}") for i in range(distinct)], repeat=per_group)


def segmenter(
    pairs: list[tuple[str, str]] | pd.DataFrame, boundary_model: float | None = None
) -> Segmenter:
    df = pairs if isinstance(pairs, pd.DataFrame) else corpus(pairs)
    weights = DEFAULT_SEGMENTATION_WEIGHTS
    if boundary_model is not None:
        weights = weights.replace(boundary_model=boundary_model)
    return Segmenter(train_reading_model(df), weights)


# Item C1 added the adjacent-glyph boundary bigram and shipped it on. Two tests below
# pin the *unigram* design decision (the Good-Turing singleton discount) on a corpus
# built by hand, and they switch that term off, for a reason worth stating: in these
# fixtures the two groups whose boundary is at issue are only ever attested as
# one-group sentences, so the pair straddling the disputed cut is never once observed
# across a boundary and the bigram, correctly, has no evidence for cutting there. The
# real corpus does not have that hole, and the behaviour these tests are about is
# checked on it by the expert paste gate — PASTE_005 is the same 𓈖𓏏𓈖𓏥 case and
# passes 8/8 at the shipped weight. Mixing the two terms here would let a change in
# either silently rewrite a test about the other.
NO_BOUNDARY_TERM = 0.0


# ---------- glyph stream and hints ----------


def test_glyph_stream_records_internal_boundaries_only():
    stream, hints = glyph_stream(["AB", "C", "DE"])
    assert stream == "ABCDE"
    assert hints == {2, 3}


def test_empty_input_yields_empty_segmentation():
    assert segmenter([("A", "x")]).segment([]).groups == []


# ---------- the core behaviours ----------


def test_unspaced_paste_is_split_into_attested_groups():
    seg = segmenter([("AB C", "ab c"), ("AB C", "ab c")])
    result = seg.segment(["ABC"])
    assert result.groups == ["AB", "C"]
    assert result.inserted_boundaries == [2]
    assert result.crossed_hints == []


def test_wrong_space_is_moved_to_the_attested_boundary():
    # Pasted as "A BC" but the corpus only knows "AB" and "C".
    seg = segmenter([("AB C", "ab c")] * 3)
    result = seg.segment(["A", "BC"])
    assert result.groups == ["AB", "C"]
    assert result.crossed_hints == [1]
    assert result.inserted_boundaries == [2]


def test_well_attested_split_beats_once_attested_long_group():
    """The (ꞽ)ntn case: N-T-N-strokes attested once as one group, but N and
    T-N-strokes are attested many times as two. The split must win."""
    df = pd.concat(
        [
            filler(),
            corpus([("N", "n")], repeat=300),
            corpus([("TNS", "=tn")], repeat=20),
            corpus([("NTNS", "(ꞽ)ntn")], repeat=1),
        ]
    )
    result = segmenter(df, boundary_model=NO_BOUNDARY_TERM).segment(["NTNS"])
    assert result.groups == ["N", "TNS"]


def test_once_attested_long_group_beats_three_way_split_of_common_groups():
    """The rmṯ(.t) case: the noun with its classifier and plural strokes is attested
    once as one group; its pieces are all common on their own. Merging must win."""
    df = pd.concat(
        [
            filler(),
            # Real proportions: 𓂋𓍿 2×, 𓀀 628×, 𓏥 alone 4×, 𓂋𓍿𓀀𓏥 1×.
            corpus([("R", "r")], repeat=2),
            corpus([("A", "=ꞽ")], repeat=600),
            corpus([("S", "3")], repeat=4),
            corpus([("RAS", "rmṯ(.t)")], repeat=1),
        ]
    )
    result = segmenter(df).segment(["R", "A", "S"])
    assert result.groups == ["RAS"]
    assert result.crossed_hints == [1, 2]


def test_singleton_discount_is_what_decides_the_split_case():
    """Pin the design decision: with no discount, the once-attested long group would
    win the (ꞽ)ntn case on raw counts."""
    df = pd.concat(
        [
            filler(),
            corpus([("N", "n")], repeat=300),
            corpus([("TNS", "=tn")], repeat=20),
            corpus([("NTNS", "(ꞽ)ntn")], repeat=1),
        ]
    )
    model = train_reading_model(df)
    base = DEFAULT_SEGMENTATION_WEIGHTS.replace(boundary_model=NO_BOUNDARY_TERM)
    with_discount = Segmenter(model, base).segment(["NTNS"]).groups
    no_discount = Segmenter(
        model, base.replace(singleton_discount=1.0)
    ).segment(["NTNS"]).groups
    assert with_discount == ["N", "TNS"]
    # Under raw counts P(N)·P(TNS) = 300·20/N² is below P(NTNS) = 1/N once N is
    # above 6,000 tokens, so the singleton wins there — the discount is not decorative.
    assert no_discount == ["NTNS"]


def test_hints_break_exact_ties():
    # "AB C" and "A BC" are equally attested, so the objective ties on the group
    # model and only the user's spacing separates them. (Hints are weak on purpose:
    # they cannot overturn a well-attested grouping, which is the whole point.)
    seg = segmenter([("AB C", "x y"), ("A BC", "p q")] * 3)
    assert seg.segment(["AB", "C"]).groups == ["AB", "C"]
    assert seg.segment(["A", "BC"]).groups == ["A", "BC"]


def test_fewer_groups_win_when_counts_are_equal():
    # A unigram model prefers one attested group over two equally attested ones;
    # a single hint does not change that.
    seg = segmenter([("A B", "a b"), ("AB", "ab")])
    assert seg.segment(["A", "B"]).groups == ["AB"]


def test_unattested_span_is_kept_whole_rather_than_shredded_into_singles():
    # "XYZ" is unknown; so are X, Y, Z. No attested split exists, so the pasted
    # group survives intact for the fallback reader instead of becoming 3 unknowns.
    seg = segmenter([("AB", "ab")])
    result = seg.segment(["XYZ"])
    assert result.groups == ["XYZ"]
    assert result.unattested_groups == ["XYZ"]


def test_unattested_multi_glyph_span_is_not_invented_across_a_user_boundary():
    seg = segmenter([("AB", "ab")])
    result = seg.segment(["XY", "Z"])
    assert result.groups == ["XY", "Z"]


def test_segmentation_is_deterministic():
    seg = segmenter([("AB C", "ab c"), ("A BC", "a bc")])
    runs = {tuple(seg.segment(["ABC"]).groups) for _ in range(5)}
    assert len(runs) == 1


def test_score_segmentation_matches_decoder_objective():
    seg = segmenter([("AB C", "ab c")] * 3)
    result = seg.segment(["ABC"])
    _, hints = glyph_stream(["ABC"])
    assert seg.score_segmentation(result.groups, hints) == pytest.approx(result.score)


# ---------- order-aware fallback similarity ----------


def test_reordered_group_is_less_similar_than_a_group_with_an_extra_determinative():
    # f-ḏd-d vs ḏd-f: same glyphs, different order. The old set-Jaccard gave 0.75 with
    # no order penalty at all.
    reversed_score = glyph_similarity("FDD", "DDFX")
    extra_determinative = glyph_similarity("DDF", "DDFX")
    assert extra_determinative > reversed_score
    assert glyph_similarity("ABC", "ABC") == 1.0
    assert glyph_similarity("A", "AB") > 0.0  # a lone sign can still borrow


def test_order_weight_zero_recovers_plain_set_jaccard():
    # {F, J, D} against {J, D, F, X}: three shared of four — the 0.75 of the trial.
    assert glyph_similarity("FJD", "JDFX", order_weight=0.0) == pytest.approx(3 / 4)


# ---------- the trial sentence, end to end on the real corpus ----------


@pytest.fixture(scope="module")
def real_corpus_model():
    from app.data.loader import load_examples_csv

    from app.services.stage import compatible_frame

    df = load_examples_csv("data/processed/examples.csv")
    # Item A (2026-09-04): segment pooled, read by stage. Word boundaries are stable
    # across language stages, so the segmenter is built from the whole corpus; the
    # reading model is stage-restricted, because since Ramses joined, pooled readings
    # for a Middle Egyptian paste are outvoted by 40k normalised Late Egyptian rows
    # (rmṯ nb instead of r(m)ṯ(.t) nb.t). Auto mode resolves Urk. IV 1 to Earlier
    # Egyptian by reading-model likelihood; this fixture uses that stage directly.
    pooled = train_reading_model(df)
    model = train_reading_model(compatible_frame(df, "Earlier Egyptian"))
    return model, Segmenter(pooled)


@pytest.mark.parametrize(
    "paste",
    [
        "𓆓𓂧 𓆑𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏼 𓂋𓍿 𓀀 𓏼𓎟𓏏",  # the expert's paste, her spacing
        "𓆓𓂧𓆑 𓆓𓂧𓀀 𓈖𓏏𓈖𓏼 𓂋𓍿𓀀𓏼 𓎟𓏏",  # grouped by word
        "𓆓𓂧𓆑𓆓𓂧𓀀𓈖𓏏𓈖𓏼𓂋𓍿𓀀𓏼𓎟𓏏",  # no spaces at all
    ],
    ids=["as_pasted", "by_word", "unspaced"],
)
def test_trial_sentence_reads_correctly_from_any_spacing(real_corpus_model, paste):
    """Phase 1 'done when': Urk. IV 1, every group attested, zero fallbacks."""
    model, seg = real_corpus_model
    groups = seg.segment(normalize_hieroglyphs(paste).split()).groups
    predictions = model.predict_sequence(groups)
    assert " ".join(p.predicted for p in predictions) == "ḏd =f ḏd =ꞽ n =tn r(m)ṯ(.t) nb.t"
    assert not any(p.is_fallback for p in predictions)
    assert all(p.was_seen for p in predictions)


# ---------- unattested groups report what the corpus does hold ----------


def test_unattested_group_reports_related_attested_groups():
    """"Unreadable" alone is a dead end. Below the borrowing threshold the model
    still knows which attested groups share these signs, and saying so is evidence,
    not invention."""
    model = train_reading_model(
        corpus([("ABCD", "known-word"), ("ABCX", "other-word")] * 2)
    )
    related = model.related_attested_groups("ABCZ")
    assert related, "expected the shared-glyph neighbours to be reported"
    groups = [g for g, _, _, _ in related]
    assert "ABCD" in groups and "ABCX" in groups
    # Sorted by similarity, and each carries its reading and attestation count.
    for group, similarity, reading, count in related:
        assert 0.0 < similarity <= 1.0
        assert reading and count >= 1


def test_attested_group_reports_no_neighbours():
    """The list is only meaningful for a group the model refuses to read."""
    model = train_reading_model(corpus([("AB", "x")] * 3))
    assert model.related_attested_groups("AB") == []


def test_group_sharing_nothing_reports_nothing():
    model = train_reading_model(corpus([("AB", "x")] * 3))
    assert model.related_attested_groups("ZZ") == []


# ---------- a cartouche is one sign group (KRI self-test, 2026-10-26) ----------

# V011A / V011B, the cartouche written as signs. In data/processed/examples.csv
# 1,841 sign groups contain a matched pair and only 13 hold one half on its own, so
# "the cartouche is the group" is the rule the corpus supports; see
# `app.data.normalizer.cartouche_spans`.
CARTOUCHE_OPEN = "\U00013379"
CARTOUCHE_CLOSE = "\U0001337A"


def cartouche_corpus() -> pd.DataFrame:
    """A corpus that attests the pieces of a royal name but never the name itself.

    Exactly the trap the self-test fell into: every fragment is a common attested
    group, the corpus has seen boundaries between all four of them, and the name as
    a whole it has never seen — so a lattice free to cut inside the cartouche
    prefers four cheap known groups to one expensive unknown one. The two fragments
    carrying a cartouche sign are then unreadable as a name, and it leaves the
    reading entirely.
    """
    return pd.concat(
        [
            corpus(
                [(f"{CARTOUCHE_OPEN} A B {CARTOUCHE_CLOSE}", "open a b close")],
                repeat=200,
            ),
            corpus([("A B", "a b")], repeat=200),
            filler(),
        ],
        ignore_index=True,
    )


def test_cartouche_is_kept_whole_even_when_its_pieces_are_attested():
    seg = segmenter(cartouche_corpus())
    name = CARTOUCHE_OPEN + "AB" + CARTOUCHE_CLOSE
    assert seg.segment([name]).groups == [name]


def test_cartouche_is_kept_whole_across_the_pastes_own_spaces():
    """The self-test's shape: the paste spaces the name by quadrat, not by word."""
    seg = segmenter(cartouche_corpus())
    name = CARTOUCHE_OPEN + "AB" + CARTOUCHE_CLOSE
    result = seg.segment([CARTOUCHE_OPEN + "A", "B" + CARTOUCHE_CLOSE])
    assert result.groups == [name]


def test_signs_outside_a_cartouche_are_still_segmented_normally():
    seg = segmenter(cartouche_corpus())
    name = CARTOUCHE_OPEN + "AB" + CARTOUCHE_CLOSE
    assert seg.segment(["AB" + name + "AB"]).groups == ["A", "B", name, "A", "B"]


def test_an_unmatched_cartouche_sign_constrains_nothing():
    # One half of a pair is not structure: the lattice segments as it always did,
    # which here means splitting into the attested groups.
    seg = segmenter(cartouche_corpus())
    assert seg.segment([CARTOUCHE_OPEN + "AB"]).groups == [CARTOUCHE_OPEN, "A", "B"]


def test_the_constraint_is_what_keeps_the_cartouche_whole(monkeypatch):
    """The same lattice, with the constraint removed, cuts the name into four.

    Pins what the fix is doing rather than only that the result is now right: with
    `cartouche_spans` reporting nothing, nothing else in the objective keeps this
    name together.
    """
    import app.services.segmentation as segmentation_module

    monkeypatch.setattr(segmentation_module, "cartouche_spans", lambda stream: [])
    seg = segmenter(cartouche_corpus())
    name = CARTOUCHE_OPEN + "AB" + CARTOUCHE_CLOSE
    assert seg.segment([name]).groups == [
        CARTOUCHE_OPEN,
        "A",
        "B",
        CARTOUCHE_CLOSE,
    ]


def test_score_segmentation_refuses_a_grouping_that_cuts_a_cartouche():
    """The scorer and the optimiser must agree on what is a legal segmentation.

    `score_segmentation` ranks a grouping `segment` never proposed — the user's own
    spacing, for the runner-up line. Without the same constraint, a split through a
    cartouche scored *higher* than the constrained optimum and would be offered as a
    better reading the app had declined to give.
    """
    seg = segmenter(cartouche_corpus())
    name = CARTOUCHE_OPEN + "AB" + CARTOUCHE_CLOSE
    chosen = seg.segment([name])
    _stream, hints = glyph_stream([name])
    split = [CARTOUCHE_OPEN, "A", "B", CARTOUCHE_CLOSE]
    assert seg.score_segmentation(split, hints) == float("-inf")
    # And the grouping it did choose is still scored by the ordinary objective.
    assert seg.score_segmentation(chosen.groups, hints) == pytest.approx(chosen.score)


def test_score_segmentation_still_scores_a_cut_outside_the_cartouche():
    seg = segmenter(cartouche_corpus())
    name = CARTOUCHE_OPEN + "AB" + CARTOUCHE_CLOSE
    groups = ["A", name, "B"]
    _stream, hints = glyph_stream(["A" + name + "B"])
    assert seg.score_segmentation(groups, hints) > float("-inf")


def test_a_cartouche_longer_than_the_window_is_still_kept_whole():
    """`MAX_GROUP_GLYPHS` is 10; this name is 14 signs including its brackets.

    The sliding window never offers a span that long, so `segment` has to offer the
    cartouche explicitly — otherwise the constraint would leave no path at all.
    """
    long_name = CARTOUCHE_OPEN + "AB" * 6 + CARTOUCHE_CLOSE
    assert len(long_name) > MAX_GROUP_GLYPHS
    seg = segmenter(cartouche_corpus())
    assert seg.segment([long_name]).groups == [long_name]
    assert seg.segment([CARTOUCHE_OPEN + "AB", "AB" * 5 + CARTOUCHE_CLOSE]).groups == [
        long_name
    ]


# ---------- a long cartouche counts as one unit of the window (KRI fixes, 2026-10-27) ----
#
# Attempt 1 of the KRI-fixes measurement failed rule (c) by one boundary error, and both
# independent diagnoses traced it to the candidate window, not to the rule. The window
# measured `max_group_glyphs` in raw glyphs, the constraint forbids every start inside a
# cartouche, and the only escape offered the span that is *exactly* the cartouche. So a
# group holding a long cartouche plus one sign on either side was never a candidate,
# and every path had to cut at the cartouche's edge even where the objective prefers no
# cut: `segment` returned a grouping that `score_segmentation`, the same objective,
# ranks below another legal grouping. These tests are synthetic on purpose — the rule is
# general, not tuned to the line that exposed it.


@pytest.mark.parametrize("payload_length", [9, 10, 13])
@pytest.mark.parametrize("side", ["left", "right"])
def test_long_cartouche_does_not_force_an_edge_cut(payload_length, side):
    """Every span is unattested, so the per-glyph cost of any grouping is the same and
    an extra cut only pays log P(cut) = log 0.25 against log P(no cut) = log 0.75. The
    whole line as one group is therefore the optimum, and `segment` must find it."""
    from app.services.boundary_model import BoundaryModel
    from app.services.reading_model import ReadingModel

    seg = Segmenter(
        ReadingModel(),
        use_lexicon=False,
        boundary_model=BoundaryModel(prior=0.25, use_class_backoff=False),
    )
    name = CARTOUCHE_OPEN + "A" * payload_length + CARTOUCHE_CLOSE
    stream = "Z" + name if side == "left" else name + "Z"
    result = seg.segment([stream])
    assert result.groups == [stream]
    assert result.score == pytest.approx(seg.score_segmentation([stream], set()))


def test_a_long_cartouche_does_not_force_a_cut_at_its_closing_edge():
    """On an attested corpus: the optimiser must never return less than the objective's
    own score of a legal grouping it could have proposed."""
    df = pd.concat([cartouche_corpus(), corpus([("Q", "q")])], ignore_index=True)
    seg = segmenter(df, boundary_model=NO_BOUNDARY_TERM)
    line = CARTOUCHE_OPEN + "AB" * 6 + CARTOUCHE_CLOSE + "Q"  # 15 glyphs > window
    result = seg.segment([line])
    assert result.score >= seg.score_segmentation([line], set()) - 1e-9
    assert result.groups == [line]


def test_the_cartouche_window_changes_nothing_without_a_cartouche():
    """With no matched pair in the stream the window is the raw-glyph window it always
    was, so every line without a cartouche segments exactly as before."""
    seg = segmenter(cartouche_corpus())
    stream = "AB" * 12
    assert seg.segment([stream]).groups == ["A", "B"] * 12
