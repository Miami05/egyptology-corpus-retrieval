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


def segmenter(pairs: list[tuple[str, str]] | pd.DataFrame) -> Segmenter:
    df = pairs if isinstance(pairs, pd.DataFrame) else corpus(pairs)
    return Segmenter(train_reading_model(df))


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
    result = segmenter(df).segment(["NTNS"])
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
    with_discount = Segmenter(model).segment(["NTNS"]).groups
    no_discount = Segmenter(
        model, DEFAULT_SEGMENTATION_WEIGHTS.replace(singleton_discount=1.0)
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

    df = load_examples_csv("data/processed/examples.csv")
    model = train_reading_model(df)
    return model, Segmenter(model)


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
