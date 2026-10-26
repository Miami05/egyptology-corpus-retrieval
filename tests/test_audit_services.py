"""Audit 2026-10-11, batch "services": A3, A21, A22, A53, A54.

Each test names the finding it pins. Most build a tiny frame or model by hand; the
A22 tests read the real corpus (the attested 11+ sign groups only exist there).
"""

from __future__ import annotations

import random
from dataclasses import replace

import pandas as pd
import pytest

from app.services import reading_model as reading_model_module
from app.services import suggestions as suggestions_module
from app.services.reading_model import ReadingModel, train_reading_model
from app.services.segmentation import DEFAULT_SEGMENTATION_WEIGHTS, Segmenter
from app.services.stage import (
    build_stage_resources,
    choose_stage_by_likelihood,
    count_own_aligned_rows,
)
from app.services.suggestions import (
    char_ngram_similarity,
    has_egyptological_letters,
    suggest_top_readings,
)

EXAMPLES = "data/processed/examples.csv"


# --------------------------------------------------------------------------- #
# A53: an unreadable group is not free
# --------------------------------------------------------------------------- #


def _model_attesting(signs: list[str], readings_each: int = 30) -> ReadingModel:
    model = ReadingModel()
    for sign in signs:
        for k in range(readings_each):
            model.sign_reading[sign][f"r{k}"] += 1
    model.sentences_seen = 30
    return model


def _per_sign(model: ReadingModel, signs: list[str]) -> float:
    _predictions, score = model.predict_sequence_scored(
        signs, use_lexicon=False, use_composed=False
    )
    return score / len(signs)


# Fix round 1: "a model that attests the signs wins" is now a property of the stage
# choice (readable coverage first), not of the per-sign number alone — see
# tests/test_fix_round1_services.py::test_a53_a_small_model_that_reads_nothing_loses_to_a_large_ambiguous_one.


def test_a53_old_free_emission_let_the_ignorant_model_win(monkeypatch):
    # The same pair with the old behaviour (unreadable costs nothing) reproduces
    # the audit's inversion, so the test above really is about the new charge.
    monkeypatch.setattr(
        reading_model_module.ReadingModel, "unreadable_emission", property(lambda self: 0.0)
    )
    paste = ["𓀀", "𓁐"]
    assert _per_sign(_model_attesting(["𓀁", "𓀂"]), paste) > _per_sign(
        _model_attesting(["𓀀", "𓁐"]), paste
    )


def _small_real_model() -> ReadingModel:
    rows = []
    for i in range(5):
        rows.append(("𓆓𓂧 𓀀 𓊵𓏏", "ḏd =f ḥtp"))
        rows.append(("𓈖𓏏𓈖 𓅓", "n m"))
    df = pd.DataFrame(
        {
            "hieroglyphs_norm": [r[0] for r in rows],
            "transliteration_gold": [r[1] for r in rows],
        }
    )
    return train_reading_model(df)


def test_a53_predictions_are_unchanged_only_the_score_moves(monkeypatch):
    model = _small_real_model()
    # Unseen groups (𓁐, 𓌳𓌳𓌳) mixed in between attested ones.
    paste = ["𓆓𓂧", "𓁐", "𓀀", "𓌳𓌳𓌳", "𓊵𓏏", "𓈖𓏏𓈖"]
    new_predictions, new_score = model.predict_sequence_scored(paste, use_lexicon=False)
    monkeypatch.setattr(
        reading_model_module.ReadingModel, "unreadable_emission", property(lambda self: 0.0)
    )
    old_predictions, old_score = model.predict_sequence_scored(paste, use_lexicon=False)
    assert [p.predicted for p in new_predictions] == [p.predicted for p in old_predictions]
    assert [p.is_ambiguous for p in new_predictions] == [p.is_ambiguous for p in old_predictions]
    unreadable = sum(1 for p in new_predictions if p.predicted == "")
    assert unreadable >= 1
    assert new_score < old_score  # each unreadable group now costs something


def test_a53_a_model_with_no_attested_groups_scores_finite():
    model = ReadingModel()
    _predictions, score = model.predict_sequence_scored(["𓀀", "𓁐"], use_lexicon=False)
    assert score == score and abs(score) != float("inf")
    assert model.unreadable_emission < 0.0


def test_a53_penalty_is_shared_by_every_model_size():
    # Fix round 1: a per-model scale let a smaller model charge less for not knowing.
    model = _model_attesting(["𓀀"], readings_each=30)
    assert model.unreadable_emission == _model_attesting(["𓀀"], readings_each=3).unreadable_emission
    assert model.unreadable_emission == reading_model_module.UNREADABLE_EMISSION


# --------------------------------------------------------------------------- #
# A3: a stage with no hieroglyph rows of its own is not a candidate
# --------------------------------------------------------------------------- #


def _stage_corpus() -> pd.DataFrame:
    rows = []

    def add(hier, translit, stage, tag, i):
        rows.append(
            {
                "hieroglyphs_norm": hier,
                "transliteration_gold": translit,
                "language_stage": stage,
                "source_text_id": f"{tag}_{i}",
                "source_sentence_id": "S0",
                "mdc_norm": "x",
            }
        )

    for i in range(4):
        add("𓆓𓂧 𓀀", "ḏd =f", "Earlier Egyptian", "EE", i)
    for i in range(4):
        add("𓈖𓏏𓈖 𓅓", "n m", "Late Egyptian", "LE", i)
    for i in range(3):  # text-only Demotic: no hieroglyphs at all
        add("", "ḏd", "Demotic", "D", i)
    for i in range(8):  # unlabelled but aligned: in every stage's reading frame
        add("𓁐𓂋 𓀁", "z r", "", "UNSPEC", i)
    add("𓁐 𓀁", "a", "Earlier Egyptian", "MISALIGNED", 0)  # 2 groups, 1 reading
    return pd.DataFrame(rows)


def _resources(df: pd.DataFrame):
    cache: dict = {}

    def get(stage):
        if stage not in cache:
            cache[stage] = build_stage_resources(df, stage, use_lexicon=False)
        return cache[stage]

    return get


def test_a3_own_aligned_rows_counts_only_the_stages_aligned_hieroglyph_rows():
    df = _stage_corpus()
    assert count_own_aligned_rows(df, "Earlier Egyptian") == 4  # misaligned row not counted
    assert count_own_aligned_rows(df, "Late Egyptian") == 4
    assert count_own_aligned_rows(df, "Demotic") == 0
    get = _resources(df)
    assert get("Demotic").own_aligned_rows == 0
    assert get("Earlier Egyptian").own_aligned_rows == 4
    assert get(None).own_aligned_rows is None


def test_a3_demotic_is_not_scored_just_because_unlabelled_rows_fill_its_model():
    df = _stage_corpus()
    get = _resources(df)
    # Demotic's model is fitted on the 8 unlabelled aligned rows, so the old guard
    # (sentences_seen == 0) never fired for it.
    assert get("Demotic").reading_model.sentences_seen == 8
    paste = "𓁐𓂋 𓀁"  # exactly the unlabelled rows' group

    stage, scores = choose_stage_by_likelihood(paste, get)
    assert "Demotic" not in scores
    assert stage != "Demotic"

    # Same resources with the new information removed: the old behaviour, where the
    # pooled "unspecified rows" model wins on this paste.
    def without_count(stage_name):
        return replace(get(stage_name), own_aligned_rows=None)

    old_stage, old_scores = choose_stage_by_likelihood(paste, without_count)
    assert "Demotic" in old_scores
    assert old_stage == "Demotic"


def test_a3_unknown_count_never_skips_a_stage():
    df = _stage_corpus()
    get = _resources(df)

    def unknown(stage_name):
        return replace(get(stage_name), own_aligned_rows=None)

    _stage, scores = choose_stage_by_likelihood("𓆓𓂧 𓀀", unknown)
    assert set(scores) == {"Earlier Egyptian", "Late Egyptian", "Demotic"}


def test_a3_a_paste_of_a_stages_own_groups_still_routes_to_it():
    df = _stage_corpus()
    stage, scores = choose_stage_by_likelihood("𓆓𓂧 𓀀", _resources(df))
    assert stage == "Earlier Egyptian"
    assert set(scores) == {"Earlier Egyptian", "Late Egyptian"}


# --------------------------------------------------------------------------- #
# A22: an attested group longer than the window is offered at any length
# --------------------------------------------------------------------------- #

def has_long_known_span(segmenter: Segmenter, groups_as_pasted: list[str]) -> bool:
    """Whether the pasted stream contains a known group longer than the window, i.e.
    whether `Segmenter.segment` now offers a candidate the old window-only code never
    did. The reference-DP tests in test_boundary_model.py, test_pasted_space_restriction.py
    and test_quadrat_hints.py compare against the old objective, so they skip these
    rows (A22 changes them on purpose)."""
    stream = "".join(groups_as_pasted)
    return any(
        segmenter.is_known(stream[i : i + length])
        for length in segmenter._long_lengths
        for i in range(len(stream) - length + 1)
    )


LONG_GROUP = "𓃒𓂡𓉻𓇓𓇋𓇋𓏏𓏪𓎟𓇾𓇾𓇳𓄊𓁧𓈘𓇋𓏠𓈖"  # 18 signs, 'wsr-mꜣꜥ.t-rꜥ-mry-ꞽmn' x54


@pytest.fixture(scope="module")
def corpus_segmenter() -> Segmenter:
    from app.data.loader import load_examples_csv

    return Segmenter(train_reading_model(load_examples_csv(EXAMPLES)))


def test_a22_the_audits_18_sign_group_pasted_alone_comes_back_whole(corpus_segmenter):
    assert len(LONG_GROUP) == 18
    assert LONG_GROUP in corpus_segmenter.group_counts
    assert corpus_segmenter.segment([LONG_GROUP]).groups == [LONG_GROUP]


def test_a22_many_attested_long_groups_come_back_whole(corpus_segmenter):
    seg = corpus_segmenter
    longest_first = sorted(
        (g for g in seg.group_counts if len(g) > 10),
        key=lambda g: (-seg.group_counts[g], g),
    )
    sample = longest_first[:200]
    assert len(sample) == 200
    whole = sum(seg.segment([g]).groups == [g] for g in sample)
    # A handful may legitimately split (a frequent shorter split can outscore a
    # rare long group); the audit's failure was that *none* could stay whole.
    assert whole >= 195


def test_a22_an_unspaced_stream_keeps_the_long_group_whole(corpus_segmenter):
    stream = "𓇋𓏏" + LONG_GROUP + "𓇳"
    groups = corpus_segmenter.segment([stream]).groups
    assert LONG_GROUP in groups


def _tiny_model(groups: dict[str, int]) -> ReadingModel:
    model = ReadingModel()
    for group, count in groups.items():
        model.sign_reading[group]["r"] += count
    model.sentences_seen = 1
    return model


def test_a22_unattested_long_spans_are_still_never_offered():
    long_attested = "𓀀𓀁𓀂𓀃𓀄𓀅𓀆𓀇𓀈𓀉𓀊𓀋"  # 12 glyphs, attested
    long_unattested = "𓁀𓁁𓁂𓁃𓁄𓁅𓁆𓁇𓁈𓁉𓁊𓁋"  # 12 glyphs, not attested
    seg = Segmenter(_tiny_model({long_attested: 5, "𓁀": 5}))
    assert seg._long_lengths == [12]
    assert seg.segment([long_attested]).groups == [long_attested]
    # The unattested neighbour is not proposed as one span: it is cut up instead.
    groups = seg.segment([long_unattested]).groups
    assert groups != [long_unattested]
    assert "".join(groups) == long_unattested


def _window_only_reference(segmenter: Segmenter, stream: str) -> list[str]:
    """The pre-A22 objective on one unspaced stream: window candidates only."""
    w = segmenter.weights
    n = len(stream)
    best: list[tuple[float, int]] = [(float("-inf"), -1)] * (n + 1)
    best[0] = (0.0, -1)
    for j in range(1, n + 1):
        top, arg = float("-inf"), -1
        for i in range(max(0, j - segmenter.max_group_glyphs), j):
            if best[i][0] == float("-inf"):
                continue
            span = stream[i:j]
            group_score = segmenter.log_prob(span)
            if group_score is None:
                group_score = -segmenter.unattested_cost(span)
            score = best[i][0] + group_score
            if score > top:
                top, arg = score, i
        best[j] = (top, arg)
    out: list[str] = []
    j = n
    while j > 0:
        out.append(stream[best[j][1] : j])
        j = best[j][1]
    return out[::-1]


def test_a22_streams_without_long_groups_are_unchanged():
    model = _tiny_model({"𓆓𓂧": 4, "𓀀": 6, "𓊵𓏏": 3, "𓈖": 9, "𓏏": 2})
    seg = Segmenter(
        model, DEFAULT_SEGMENTATION_WEIGHTS.replace(boundary_model=0.0)
    )
    assert seg._long_lengths == []
    rng = random.Random(7)
    alphabet = ["𓆓", "𓂧", "𓀀", "𓊵", "𓏏", "𓈖"]
    for _ in range(50):
        stream = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 14)))
        assert seg.segment([stream]).groups == _window_only_reference(seg, stream)


# --------------------------------------------------------------------------- #
# A54: a Unicode query is not matched through the lossy ASCII fold
# --------------------------------------------------------------------------- #


def _row(translit: str, score: float, hieroglyphs: str = "𓊵 𓏏 𓊪") -> dict:
    return {
        "transliteration_gold": translit,
        "final_score": score,
        "hieroglyphs_norm": hieroglyphs,
        "translation": "x",
        "source": "AES",
        "source_text_id": f"t{translit}",
        "source_sentence_id": "s",
    }


def test_a54_the_exact_unicode_reading_outranks_a_different_consonant():
    frame = pd.DataFrame([_row("ꜣḥꜥ", 0.80), _row("ꜥḥꜥ", 0.74)])
    result = suggest_top_readings(frame, "ꜥḥꜥ")
    assert result[0].candidate_transliteration == "ꜥḥꜥ"
    wrong = next(s for s in result if s.candidate_transliteration == "ꜣḥꜥ")
    assert "shared transliteration tokens: ꜣḥꜥ" not in wrong.evidence_summary
    assert "simplified" not in wrong.evidence_summary
    assert wrong.confidence_score < result[0].confidence_score


def test_a54_ascii_queries_keep_the_loose_match_and_its_label():
    # 'aha' is plain ASCII, so it may mean either ꜥ or ꜣ: loose matching stays.
    frame = pd.DataFrame([_row("ꜥḥꜥ", 0.74)])
    (suggestion,) = suggest_top_readings(frame, "aha")
    assert "same simplified query reading" in suggestion.evidence_summary
    debug: list[dict] = []
    suggest_top_readings(frame, "aha", debug_signals=debug)
    assert debug[0]["signals"]["exact_or_near"]["value"] == 0.85
    # An ASCII digraph query becomes Unicode only *after* the decision is taken.
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.8)])
    (suggestion,) = suggest_top_readings(frame, "htp dji nswt")
    assert "same simplified query reading" in suggestion.evidence_summary
    assert "shared transliteration tokens: ḏi, ḥtp, nswt" in suggestion.evidence_summary


def test_a54_unicode_query_still_matches_words_across_morpheme_dots():
    frame = pd.DataFrame([_row("ꜥḥꜥ.n =f", 0.8)])
    (suggestion,) = suggest_top_readings(frame, "ꜥḥꜥ")
    assert "shared transliteration tokens: ꜥḥꜥ" in suggestion.evidence_summary


def test_a54_char_ngram_similarity_fold_switch():
    assert char_ngram_similarity("ꜥḥꜥ", "ꜣḥꜥ") == pytest.approx(1.0)  # default: folded
    assert char_ngram_similarity("ꜥḥꜥ", "ꜣḥꜥ", fold=False) < 1.0
    assert char_ngram_similarity("ꜥḥꜥ", "ꜥḥꜥ", fold=False) == pytest.approx(1.0)


@pytest.mark.parametrize("text", ["ꜣ", "ꜥnḫ", "ꞽw", "ḥtp", "ḏd", "xu̯", "rdi̯ =f"])
def test_a54_helper_recognises_egyptological_letters(text):
    assert has_egyptological_letters(text)


@pytest.mark.parametrize("text", ["", "htp dji nswt", "A1-N35", "a.n =f", "x(.t)"])
def test_a54_helper_ignores_plain_ascii(text):
    assert not has_egyptological_letters(text)


# --------------------------------------------------------------------------- #
# A21: confidence reflects absolute evidence, ranking is untouched
# --------------------------------------------------------------------------- #


def test_a21_one_shared_group_of_ten_is_a_low_confidence():
    query = "𓊵 𓀀 𓀁 𓀂 𓀃 𓀄 𓀅 𓀆 𓀇 𓀈"
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.05)])
    (suggestion,) = suggest_top_readings(frame, query, query_hieroglyphs=query)
    assert "cover 10% of the query" in suggestion.evidence_summary
    assert suggestion.confidence_score <= 0.15


def test_a21_a_text_query_with_no_shared_token_is_near_zero():
    frame = pd.DataFrame([_row("sḏm =f", 0.05)])
    (suggestion,) = suggest_top_readings(frame, "ꞽw rḫ.n =ꞽ ḏd mdw nb ꜥnḫ wꜣs")
    assert suggestion.confidence_score < 0.05


def test_a21_exact_matches_keep_a_high_confidence():
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.9, "𓊵𓏏 𓇋𓏏 𓇓")])
    (text_hit,) = suggest_top_readings(frame, "ḥtp ḏi nswt")
    assert text_hit.confidence_score >= 0.8
    (glyph_hit,) = suggest_top_readings(
        frame, "𓊵𓏏 𓇋𓏏 𓇓", query_hieroglyphs="𓊵𓏏 𓇋𓏏 𓇓"
    )
    assert glyph_hit.confidence_score >= 0.8


def _random_pool(rng: random.Random) -> tuple[pd.DataFrame, dict]:
    words = ["ꜥḥꜥ", "ḥtp", "ḏi", "nswt", "sḏm", "ꞽw", "rꜥ", "ꜥnḫ", "wꜣs", "n", "m"]
    glyphs = ["𓊵", "𓏏", "𓂧", "𓀀", "𓈖", "𓅓", "𓇋"]
    rows = []
    for index in range(rng.randint(1, 9)):
        translit = " ".join(rng.choice(words) for _ in range(rng.randint(1, 4)))
        rows.append(
            {
                **_row(translit, round(rng.random(), 3)),
                "hieroglyphs_norm": " ".join(
                    "".join(rng.choice(glyphs) for _ in range(rng.randint(1, 2)))
                    for _ in range(rng.randint(1, 4))
                ),
                "normalized_reading_order": " ".join(rng.choice(glyphs) for _ in range(3)),
                "source_text_id": f"t{index}",
            }
        )
    glyph_query = rng.random() < 0.5
    if glyph_query:
        query = " ".join(rng.choice(glyphs) * rng.randint(1, 2) for _ in range(rng.randint(2, 4)))
        kwargs = {"query_mdc": query, "query_hieroglyphs": query}
    else:
        kwargs = {"query_mdc": " ".join(rng.choice(words) for _ in range(rng.randint(1, 4)))}
    if rng.random() < 0.4:
        kwargs["query_reading_order"] = " ".join(rng.choice(glyphs) for _ in range(3))
    return pd.DataFrame(rows), kwargs


def test_a21_ranking_is_exactly_the_relative_ranking():
    # The absolute-evidence factor is applied after sorting, so the order must be
    # the one the relative confidence alone gives, ties included.
    rng = random.Random(21)
    for _ in range(150):
        frame, kwargs = _random_pool(rng)
        debug: list[dict] = []
        shown = suggest_top_readings(frame, top_n=50, debug_signals=debug, **kwargs)
        by_candidate = {entry["candidate_transliteration"]: entry for entry in debug}
        expected = sorted(
            shown,
            key=lambda s: (
                -by_candidate[s.candidate_transliteration]["relative_confidence"],
                -s.supporting_example_count,
                s.candidate_transliteration,
            ),
        )
        assert [s.candidate_transliteration for s in shown] == [
            s.candidate_transliteration for s in expected
        ]
        for suggestion in shown:
            entry = by_candidate[suggestion.candidate_transliteration]
            assert suggestion.confidence_score == entry["confidence_score"]
            assert 0.0 <= suggestion.confidence_score <= 0.99
            assert suggestion.confidence_score <= entry["relative_confidence"] + 1e-9


def test_a21_top_one_is_the_same_with_and_without_the_factor(monkeypatch):
    rng = random.Random(210)
    pools = [_random_pool(rng) for _ in range(120)]
    with_factor = [
        [s.candidate_transliteration for s in suggest_top_readings(f, top_n=5, **kw)]
        for f, kw in pools
    ]
    # Old behaviour: the factor forced to 1.0.
    monkeypatch.setattr(suggestions_module, "absolute_evidence", lambda evidence: 1.0)
    without_factor = [
        [s.candidate_transliteration for s in suggest_top_readings(f, top_n=5, **kw)]
        for f, kw in pools
    ]
    assert with_factor == without_factor


def test_a21_debug_entries_carry_both_the_relative_and_final_confidence():
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.9), _row("sḏm =f", 0.3)])
    debug: list[dict] = []
    shown = suggest_top_readings(frame, "ḥtp ḏi nswt", debug_signals=debug)
    for entry in debug:
        assert entry["confidence_score"] == round(
            min(0.99, entry["relative_confidence"] * entry["evidence"]), 3
        )
    assert {s.confidence_score for s in shown} == {e["confidence_score"] for e in debug}
