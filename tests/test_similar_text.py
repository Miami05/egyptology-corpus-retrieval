"""Item E: the cross-edition pair rule, tier detection, the per-field n-gram indexes.

The page's own smoke test lives in tests/test_frontend_smoke.py with the other pages.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.normalizer import normalize_hieroglyphs
from app.retrieval.tfidf import NgramIndex
from app.services.similar_text import (
    TIER_SIGNS,
    TIER_TRANSLATION,
    TIER_TRANSLITERATION,
    build_sign_ngram_index,
    build_translation_ngram_index,
    cosine_ranking,
    detect_tier,
    edit_reranked,
    sign_code_points,
    sign_ngram_list,
)
from scripts.build_cross_edition_pairs import (
    MAX_JACCARD,
    MIN_JACCARD,
    MIN_TOKENS,
    assert_yod_folds_together,
    find_candidate_pairs,
    loose_token_sets,
    select_pairs,
)


# --------------------------------------------------------------- the pair-building rule


#: Nonsense but well-behaved transliteration tokens: no Egyptological letter folds them
#: together, so the Jaccard of any two rows below is exactly what it looks like.
def _row(source: str, sentence_id: str, reading: str, **extra) -> dict[str, object]:
    row = {
        "source": source,
        "source_text_id": f"{source}_TEXT",
        "source_sentence_id": sentence_id,
        "language_stage": "Test stage",
        "transliteration_gold": reading,
        "hieroglyphs_norm": "",
        "translation": "",
    }
    row.update(extra)
    return row


@pytest.fixture
def synthetic_corpus() -> pd.DataFrame:
    """Rows chosen so every rule of the pair definition has a case that exercises it."""
    return pd.DataFrame(
        [
            # 0 / 1: different sources, 5 shared of 7 united = 0.714 -> in band.
            _row("Alpha", "A1", "wa wb wc wd we wf"),
            _row("Beta", "B1", "wa wb wc wd we wz"),
            # 2: same source as row 0 and the same reading -> must never pair with it, and
            # (since row 1 is already spoken for) must end up in no pair at all.
            _row("Alpha", "A2", "wa wb wc wd we wf"),
            # 3 / 4: different sources, 9 shared of 10 united = 0.900 -> excluded as a
            # near-copy twin.
            _row("Alpha", "A3", "xa xb xc xd xe xf xg xh xi xk"),
            _row("Beta", "B3", "xa xb xc xd xe xf xg xh xi"),
            # 5 / 6: different sources, 2 shared of 10 united = 0.200 -> below the band.
            _row("Alpha", "A4", "ya yb yc yd ye yf"),
            _row("Beta", "B4", "ya yb ym yn yo yp"),
            # 7 / 8: an obvious parallel, but only 3 tokens each -> not eligible at all.
            _row("Alpha", "A5", "za zb zc"),
            _row("Beta", "B5", "za zb zd"),
        ]
    )


def _pairs(df: pd.DataFrame, cap: int = 300) -> pd.DataFrame:
    token_sets = loose_token_sets(df)
    sources = df["source"].astype(str).tolist()
    eligible = [i for i, tokens in enumerate(token_sets) if len(tokens) >= MIN_TOKENS]
    candidates, _near_copies = find_candidate_pairs(token_sets, sources, eligible)
    return select_pairs(candidates, df, cap=cap)


def test_only_the_in_band_cross_source_pair_survives(synthetic_corpus: pd.DataFrame) -> None:
    pairs = _pairs(synthetic_corpus)
    assert len(pairs) == 1
    only = pairs.iloc[0]
    assert {only["a_source"], only["b_source"]} == {"Alpha", "Beta"}
    assert {only["a_sentence_id"], only["b_sentence_id"]} == {"A1", "B1"}
    assert MIN_JACCARD <= only["jaccard"] < MAX_JACCARD
    assert only["jaccard"] == pytest.approx(5 / 7)


def test_near_copies_at_or_above_the_upper_edge_are_counted_and_dropped(
    synthetic_corpus: pd.DataFrame,
) -> None:
    """The 0.9 twins are the whole reason for the upper band edge, so the builder has to
    see them and refuse them rather than never find them."""
    token_sets = loose_token_sets(synthetic_corpus)
    sources = synthetic_corpus["source"].astype(str).tolist()
    eligible = [i for i, tokens in enumerate(token_sets) if len(tokens) >= MIN_TOKENS]
    candidates, near_copies = find_candidate_pairs(token_sets, sources, eligible)
    assert near_copies == 1
    assert all(score < MAX_JACCARD for _a, _b, score in candidates)


def test_a_row_is_used_in_at_most_one_pair() -> None:
    df = pd.DataFrame(
        [
            _row("Alpha", "A1", "wa wb wc wd we wf"),
            _row("Beta", "B1", "wa wb wc wd we wz"),
            _row("Gamma", "C1", "wa wb wc wd we wy"),
        ]
    )
    pairs = _pairs(df)
    used = list(pairs["a_position"]) + list(pairs["b_position"])
    assert len(used) == len(set(used))


def test_selection_is_deterministic_and_the_cap_is_respected(
    synthetic_corpus: pd.DataFrame,
) -> None:
    first, second = _pairs(synthetic_corpus), _pairs(synthetic_corpus)
    pd.testing.assert_frame_equal(first, second)
    assert len(_pairs(synthetic_corpus, cap=0)) == 0


def test_the_three_editions_of_the_yod_already_fold_together() -> None:
    """The builder asserts this before it runs; if it ever stops holding, every
    Ramses<->TLA pair silently disappears."""
    assert_yod_folds_together()


# ----------------------------------------------------------------- tier auto-detection


EGYPTIAN_VOCABULARY = {"htp", "di", "nswt", "iri", "n", "f", "hrw"}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("𓊵𓏙 𓇓𓏏", TIER_SIGNS),
        ("𓊵𓏙 written out", TIER_SIGNS),
        ("htp di nswt", TIER_TRANSLITERATION),
        ("ꜥḥꜥ.n stẖ qnd", TIER_TRANSLITERATION),
        ("aHa.n stX qnd", TIER_TRANSLITERATION),
        ("Worte sprechen durch den Siegler", TIER_TRANSLATION),
        ("An offering which the king gives", TIER_TRANSLATION),
        ("", TIER_TRANSLITERATION),
    ],
)
def test_detect_tier(text: str, expected: str) -> None:
    tier, reason = detect_tier(text, vocabulary=EGYPTIAN_VOCABULARY)
    assert tier == expected
    assert reason and reason[-1] == "."


def test_ascii_transliteration_needs_the_vocabulary_step() -> None:
    """Without the corpus vocabulary the original rule stands, and `htp di nswt` — plain
    ASCII, spaced, no Egyptological letter — reads as a translation. That is exactly why
    the vocabulary step exists; the deviation is recorded in the evaluation document."""
    assert detect_tier("htp di nswt", vocabulary=None)[0] == TIER_TRANSLATION
    assert detect_tier("htp di nswt", vocabulary=EGYPTIAN_VOCABULARY)[0] == TIER_TRANSLITERATION


# ------------------------------------------------------- one index class, three fields


def test_sign_analyzer_drops_group_boundaries_and_emits_1_to_3_grams() -> None:
    assert sign_code_points("𓀀 𓀁 𓀂") == "𓀀𓀁𓀂"
    assert sign_ngram_list("𓀀 𓀁") == ["𓀀", "𓀁", "𓀀𓀁"]


def test_transliteration_index_ranks_the_near_duplicate_first() -> None:
    frame = pd.DataFrame(
        {"mdc_norm": ["htp di nswt wsir", "ini n f hrw asha", "sdjm n f nb ta"]}
    )
    index = NgramIndex.build(frame["mdc_norm"])
    order = cosine_ranking(index.scores("htp di nswt wsr"))
    assert int(order[0]) == 0


def test_sign_index_ranks_the_near_duplicate_first() -> None:
    frame = pd.DataFrame(
        {
            "hieroglyphs_norm": [
                normalize_hieroglyphs("𓊵𓏙 𓇓𓏏 𓀭"),
                normalize_hieroglyphs("𓅓 𓂋 𓈖"),
                normalize_hieroglyphs("𓃀 𓎡 𓏏"),
            ]
        }
    )
    index = build_sign_ngram_index(frame)
    order = cosine_ranking(index.scores(normalize_hieroglyphs("𓊵𓏙𓇓𓏏")))
    assert int(order[0]) == 0


def test_translation_index_ranks_the_near_duplicate_first() -> None:
    frame = pd.DataFrame(
        {
            "translation": [
                "Worte sprechen durch den Siegler des Königs",
                "Er möge Brot und Bier geben",
                "Der Himmel öffnet sich für den Ka",
            ]
        }
    )
    index = build_translation_ngram_index(frame)
    order = cosine_ranking(index.scores("Worte sprechen durch den Siegler"))
    assert int(order[0]) == 0


def test_the_analyzer_travels_with_the_index() -> None:
    """`scores()` must vectorise the query with the analyzer the rows were built with —
    a sign index handed the default character analyzer would score everything 0."""
    frame = pd.DataFrame({"hieroglyphs_norm": ["𓀀 𓀁 𓀂"]})
    assert build_sign_ngram_index(frame).scores("𓀀𓀁𓀂") == pytest.approx([1.0])


def test_the_edit_rerank_only_touches_the_head_and_keeps_ties_in_cosine_order() -> None:
    import numpy as np

    texts = ["aaaa", "aaab", "zzzz", "aaaa"]
    order = np.array([2, 1, 0, 3])
    reordered, similarities = edit_reranked(order, "aaaa", texts, depth=3)
    # Row 3 was below the re-rank depth, so it stays exactly where the cosine put it.
    assert reordered.tolist()[-1] == 3
    # Within the head, the exact match rises above the near match, which rises above zzzz.
    assert reordered.tolist()[:3] == [0, 1, 2]
    assert similarities[0] == pytest.approx(1.0)
    assert set(similarities) == {0, 1, 2}
