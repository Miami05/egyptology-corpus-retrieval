"""Fix round 1 (2026-10-25), services: reviewer findings on the audit branch.

Each test names the finding it pins: A54 (raw-notation strictness, mixed queries,
cfg_a/cfg_c carry-forward), A16/A54 (one lossless alias helper), A21 (per-candidate
evidence), A53 (unreadable groups across model sizes), A17 (superfluous text), A48
(bracketed plural notation) and A22 (an independent exhaustive reference for long
spans). Everything here is synthetic and runs without the corpus.
"""

from __future__ import annotations

import ast
import random
from collections import Counter
from math import log
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.normalizer import (
    drop_superfluous_text,
    normalize_notation,
    normalize_transliteration,
    search_fold,
)
from app.data.query import parse_query
from app.services.reading_model import ReadingModel, train_reading_model
from app.services.segmentation import (
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
    glyph_stream,
)
from app.services.stage import STAGES, choose_stage_by_likelihood
from app.services.suggestions import (
    SUGGESTION_PRESETS,
    strict_reading_key,
    suggest_top_readings,
    unfolded_reading_form,
)

APP_SOURCE = Path(__file__).resolve().parents[1] / "app" / "ui" / "whyptology_app.py"


def _row(translit: str, score: float, hieroglyphs: str = "𓊵 𓏏 𓊪", **extra) -> dict:
    return {
        "transliteration_gold": translit,
        "final_score": score,
        "hieroglyphs_norm": hieroglyphs,
        "translation": "x",
        "source": "AES",
        "source_text_id": f"t{translit}",
        "source_sentence_id": "s",
        **extra,
    }


# --------------------------------------------------------------------------- #
# A54: strictness is decided on what was typed, per word
# --------------------------------------------------------------------------- #


def _ui_call(frame: pd.DataFrame, query: str, vocabulary: set[str], **kwargs):
    """What app/ui/whyptology_app.py does: the suggestion layer gets the resolved
    reading *and* the raw query."""
    searched = parse_query(query, vocabulary=vocabulary)
    return suggest_top_readings(
        frame, query_mdc=searched.reading or query, query_raw=query, **kwargs
    )


def test_a54_the_apps_caller_contract_keeps_ascii_queries_loose():
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.80), _row("ḫtp ḏi nswt", 0.79)])
    vocabulary = {"htp", "dji", "nswt", "khtp"}
    searched = parse_query("htp dji nswt", vocabulary=vocabulary)
    # The app converts the ASCII digraphs before the suggestion layer sees them.
    assert searched.reading == "htp ḏi nswt"
    top, second = _ui_call(frame, "htp dji nswt", vocabulary)
    assert top.candidate_transliteration == "ḥtp ḏi nswt"
    assert "same simplified query reading" in top.evidence_summary
    assert "shared transliteration tokens: ḏi, ḥtp, nswt" in top.evidence_summary
    assert top.confidence_score > second.confidence_score


def test_a54_the_app_passes_the_raw_query_to_the_suggestion_layer():
    tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", "")) == "suggest_top_readings"
    ]
    assert calls, "the app no longer calls suggest_top_readings"
    for call in calls:
        keywords = {kw.arg: kw.value for kw in call.keywords}
        assert "query_raw" in keywords, "the app must pass the query as typed (A54)"
        assert isinstance(keywords["query_raw"], ast.Name)
        assert keywords["query_raw"].id == "query"


def test_a54_mixed_query_ascii_words_stay_loose_unicode_words_strict():
    # Opus review repro: `htp` typed in ASCII, `ḏi` with a palette letter.
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.80), _row("ḫtp ḏi nswt", 0.79)])
    top, second = suggest_top_readings(frame, "htp ḏi nswt")
    assert top.candidate_transliteration == "ḥtp ḏi nswt"
    assert "same simplified query reading" in top.evidence_summary
    assert "shared transliteration tokens: ḏi, ḥtp, nswt" in top.evidence_summary
    assert top.confidence_score >= 0.85
    assert second.candidate_transliteration == "ḫtp ḏi nswt"
    assert "same simplified" not in second.evidence_summary
    assert "ḫtp" not in second.evidence_summary.split("shared transliteration tokens:")[-1]


def test_a54_mixed_query_still_refuses_a_different_consonant_in_a_unicode_word():
    frame = pd.DataFrame([_row("ḥtp ꜣḥꜥ", 0.80), _row("ḥtp ꜥḥꜥ", 0.74)])
    result = suggest_top_readings(frame, "htp ꜥḥꜥ")
    assert result[0].candidate_transliteration == "ḥtp ꜥḥꜥ"
    wrong = next(s for s in result if s.candidate_transliteration == "ḥtp ꜣḥꜥ")
    assert "simplified query reading" not in wrong.evidence_summary or (
        "near simplified" in wrong.evidence_summary
    )
    assert "ꜣḥꜥ" not in wrong.evidence_summary.split("shared transliteration tokens:")[-1]


@pytest.mark.parametrize("preset", ["cfg_a", "cfg_c"])
def test_a54_carry_forward_does_not_overwrite_strict_overlap(preset):
    # Retrieval's overlap is computed on the lossy ASCII key, so it scores ꜣḥꜥ 1.0
    # against the query ꜥḥꜥ. A Unicode query must not inherit that.
    frame = pd.DataFrame(
        [
            _row("ꜣḥꜥ", 0.80, idf_overlap_score=1.0),
            _row("ꜥḥꜥ", 0.74, idf_overlap_score=1.0),
        ]
    )
    debug: list[dict] = []
    result = suggest_top_readings(
        frame, "ꜥḥꜥ", weights=SUGGESTION_PRESETS[preset], debug_signals=debug
    )
    by = {e["candidate_transliteration"]: e for e in debug}
    assert by["ꜣḥꜥ"]["signals"]["translit_overlap"]["value"] < 1.0
    assert result[0].candidate_transliteration == "ꜥḥꜥ"


@pytest.mark.parametrize("preset", ["cfg_a", "cfg_c"])
def test_a54_carry_forward_still_applies_to_an_ascii_query(preset):
    frame = pd.DataFrame([_row("ꜥḥꜥ", 0.74, idf_overlap_score=0.37)])
    debug: list[dict] = []
    suggest_top_readings(frame, "aha", weights=SUGGESTION_PRESETS[preset], debug_signals=debug)
    assert debug[0]["signals"]["translit_overlap"]["value"] == pytest.approx(0.37)


# --------------------------------------------------------------------------- #
# A16/A54: one lossless alias helper for search and suggestions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "variant, canonical", [("ʿnḫ", "ꜥnḫ"), ("ȝḫ", "ꜣḫ"), ("ỉr", "ꞽr"), ("ȜḪ", "ꜣḫ")]
)
def test_a16_letter_variants_are_the_same_letter_in_suggestions(variant, canonical):
    assert strict_reading_key(variant) == strict_reading_key(canonical)
    assert unfolded_reading_form(variant) == unfolded_reading_form(canonical)
    assert search_fold(variant) == search_fold(canonical)


def test_a16_a_variant_letter_query_gets_exact_credit_for_the_canonical_row():
    frame = pd.DataFrame([_row("ꜥnḫ", 0.8), _row("ꜣnḫ", 0.79)])
    debug: list[dict] = []
    result = suggest_top_readings(frame, "ʿnḫ", debug_signals=debug)
    assert result[0].candidate_transliteration == "ꜥnḫ"
    assert "same normalized query reading" in result[0].evidence_summary
    by = {e["candidate_transliteration"]: e for e in debug}
    assert by["ꜥnḫ"]["signals"]["exact_or_near"]["value"] == 1.0
    # Lossless: the aleph stays a different consonant.
    assert by["ꜣnḫ"]["signals"]["exact_or_near"]["value"] < 1.0


def test_a16_the_alias_helper_keeps_consonants_distinct():
    assert normalize_notation("ʿḥʿ") == "ꜥḥꜥ"
    assert normalize_notation("ꜣḥꜥ") != normalize_notation("ꜥḥꜥ")
    assert normalize_notation("ḫ") != normalize_notation("ẖ")


# --------------------------------------------------------------------------- #
# A21: each candidate's confidence rests on its own evidence
# --------------------------------------------------------------------------- #


def test_a21_a_strong_candidate_does_not_lift_a_weak_one():
    query = "𓊵 𓀀 𓀁 𓀂 𓀃 𓀄 𓀅 𓀆 𓀇 𓀈"
    frame = pd.DataFrame(
        [
            _row("ḥtp ḏi nswt", 0.5, hieroglyphs="𓊵 𓇋 𓇋 𓇋 𓇋 𓇋 𓇋 𓇋 𓇋 𓇋"),  # 10%
            _row("sḏm =f", 0.5, hieroglyphs=query),  # exact
        ]
    )
    debug: list[dict] = []
    result = suggest_top_readings(frame, query, query_hieroglyphs=query, debug_signals=debug)
    by = {s.candidate_transliteration: s for s in result}
    assert "cover 10% of the query" in by["ḥtp ḏi nswt"].evidence_summary
    assert by["ḥtp ḏi nswt"].confidence_score <= 0.15
    assert by["sḏm =f"].confidence_score >= 0.8
    # Order is still the relative order.
    entries = {e["candidate_transliteration"]: e for e in debug}
    expected = sorted(
        result,
        key=lambda s: (
            -entries[s.candidate_transliteration]["relative_confidence"],
            -s.supporting_example_count,
            s.candidate_transliteration,
        ),
    )
    assert [s.candidate_transliteration for s in result] == [
        s.candidate_transliteration for s in expected
    ]


def test_a21_mixed_text_pool_weak_candidate_stays_low():
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.5), _row("sḏm =f", 0.5)])
    result = suggest_top_readings(frame, "ḥtp ḏi nswt")
    by = {s.candidate_transliteration: s for s in result}
    assert by["ḥtp ḏi nswt"].confidence_score >= 0.8
    assert by["sḏm =f"].confidence_score < 0.2


def test_a21_debug_entries_carry_the_candidates_own_evidence():
    frame = pd.DataFrame([_row("ḥtp ḏi nswt", 0.9), _row("sḏm =f", 0.3)])
    debug: list[dict] = []
    shown = suggest_top_readings(frame, "ḥtp ḏi nswt", debug_signals=debug)
    by = {s.candidate_transliteration: s for s in shown}
    for entry in debug:
        assert 0.0 <= entry["evidence"] <= 1.0
        assert entry["confidence_score"] == round(
            min(0.99, entry["relative_confidence"] * entry["evidence"]), 3
        )
        assert by[entry["candidate_transliteration"]].confidence_score == entry[
            "confidence_score"
        ]


# --------------------------------------------------------------------------- #
# A53: a stage that cannot read the paste never wins, whatever its size
# --------------------------------------------------------------------------- #


def _trained(rows: list[tuple[str, str]]) -> ReadingModel:
    return train_reading_model(
        pd.DataFrame(
            {
                "hieroglyphs_norm": [r[0] for r in rows],
                "transliteration_gold": [r[1] for r in rows],
            }
        )
    )


def _fake_resources(models: dict[str | None, ReadingModel]):
    class _Identity:
        def segment(self, groups, **_hints):
            return SimpleNamespace(groups=list(groups))

    def get(stage):
        model = models.get(stage)
        if model is None:
            return SimpleNamespace(
                segmenter=_Identity(), reading_model=ReadingModel(), own_aligned_rows=0
            )
        return SimpleNamespace(segmenter=_Identity(), reading_model=model, own_aligned_rows=1)

    return get


def test_a53_a_small_model_that_reads_nothing_loses_to_a_large_ambiguous_one():
    # Astra's counterexample: A attests both pasted signs with 30 distinct readings
    # each; B was trained on one sentence of two *other* signs.
    knows = _trained([("𓀀 𓁐", f"a{k} b{k}") for k in range(30)])
    ignorant = _trained([("𓃀 𓃁", "x y")])
    earlier, late = STAGES[0], STAGES[1]
    stage, scores = choose_stage_by_likelihood(
        "𓀀 𓁐", _fake_resources({None: knows, earlier: knows, late: ignorant})
    )
    # The per-sign number alone still favours the ignorant model (that is why
    # coverage has to come first) ...
    assert scores[late] > scores[earlier]
    # ... but the model that reads the paste wins.
    assert stage == earlier


def test_a53_unreadable_charge_is_the_same_for_every_model_size():
    small = _trained([("𓃀", "x")])
    large = _trained([("𓀀 𓁐", f"a{k} b{k}") for k in range(30)])
    assert small.unreadable_emission == large.unreadable_emission == ReadingModel().unreadable_emission
    assert small.unreadable_emission < 0.0


def test_a53_equal_coverage_is_still_decided_by_likelihood():
    confident = _trained([("𓀀 𓁐", "a b")] * 30)
    ambiguous = _trained([("𓀀 𓁐", f"a{k} b{k}") for k in range(30)])
    earlier, late = STAGES[0], STAGES[1]
    stage, scores = choose_stage_by_likelihood(
        "𓀀 𓁐", _fake_resources({None: confident, earlier: ambiguous, late: confident})
    )
    assert scores[late] > scores[earlier]
    assert stage == late


# --------------------------------------------------------------------------- #
# A17: superfluous `{…}` text
# --------------------------------------------------------------------------- #


def test_a17_a_wholly_superfluous_text_has_an_empty_search_key():
    assert search_fold("{m} ={tn} {ꞽs} {ḫ}") == ""
    assert search_fold("{Ḫwi̯.n-H̱nm.w}") == ""
    assert search_fold("{ꞽri̯} {sw} {ḏd.ḫr} ={k}") == ""
    assert normalize_transliteration("{ꞽri̯} {sw} {ḏd.ḫr} {k}") == ""


@pytest.mark.parametrize(
    "text, expected",
    [
        ("{a{b}c} d", "d"),
        ("{{a} b} c", "c"),
        ("x {a {b} c} y", "x y"),
        ("nb{.t}", "nb"),
        ("ḏd.n={f}", "djdn"),
    ],
)
def test_a17_nested_braces_are_deleted_whole(text, expected):
    assert search_fold(text) == expected


def test_a17_double_braces_are_the_documented_exception():
    assert search_fold("{{pꜣ}} {{pri̯}} {{[ꞽri̯.n]}}") == "pa pri irin"
    assert drop_superfluous_text("{{pꜣ}} {x}") == "pꜣ "


# --------------------------------------------------------------------------- #
# A48: brackets around either half of the plural notation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "variant", ["šms.w.pl", "šms(.w).pl", "šms.w(.pl)", "šms(.w)(.pl)", "šms(w)(.pl)", "šms.w(.PL)"]
)
def test_a48_every_bracketing_of_the_plural_folds_like_sms_w(variant):
    assert search_fold(variant) == search_fold("šms.w") == "shmsw"
    assert strict_reading_key(variant) == strict_reading_key("šms.w")


def test_a48_stem_final_w_and_other_morphemes_are_kept():
    assert search_fold("nw(.w).pl") == "nww"
    assert search_fold("nfr(.t).pl") == "nfrtw"
    assert search_fold("nb(.pl)") == "nbw"


# --------------------------------------------------------------------------- #
# A22: an independent exhaustive reference, long spans included
# --------------------------------------------------------------------------- #


def _exhaustive_reference(
    corpus: dict[str, int],
    lexicon: set[str],
    weights,
    max_glyphs: int,
    pasted: list[str],
    no_cut: set[int],
) -> tuple[float, list[list[str]]]:
    """Every segmentation of the stream, scored from the definitions alone (no
    Segmenter code): returns the best score and every segmentation reaching it."""
    stream, hints = glyph_stream(pasted)
    n = len(stream)
    total = sum(corpus.values())
    vocabulary = len(corpus) + len(lexicon)

    def group_score(span: str, start: int, end: int) -> float | None:
        if span in corpus:
            count = corpus[span]
            effective = weights.singleton_discount if count == 1 else float(count)
            return log(effective / (total + vocabulary))
        if span in lexicon:
            return log(weights.lexicon_weight / (total + vocabulary))
        if len(span) > max_glyphs:
            return None  # an unattested span longer than the window is never offered
        if (
            not weights.unattested_may_cross_hints
            and len(span) > 1
            and any(start < h < end for h in hints)
        ):
            return None
        return -weights.unattested_per_glyph * len(span)

    best = float("-inf")
    winners: list[list[str]] = []
    for mask in range(1 << (n - 1)):
        cuts = [0] + [k for k in range(1, n) if mask >> (k - 1) & 1] + [n]
        score = 0.0
        for start, end in zip(cuts, cuts[1:]):
            g = group_score(stream[start:end], start, end)
            if g is None:
                score = float("-inf")
                break
            score += (
                g
                + weights.hint_kept * (1 if start in hints else 0)
                - weights.hint_crossed * sum(1 for h in hints if start < h < end)
                - weights.quadrat_crossed * (1 if start > 0 and start in no_cut else 0)
            )
        groups = [stream[a:b] for a, b in zip(cuts, cuts[1:])]
        if score > best + 1e-9:
            best, winners = score, [groups]
        elif abs(score - best) <= 1e-9:
            winners.append(groups)
    return best, winners


@pytest.mark.parametrize("lifted", [False, True])
def test_a22_segment_matches_an_exhaustive_reference_with_long_spans(lifted):
    alphabet = ["𓀀", "𓀁", "𓀂", "𓀃"]
    rng = random.Random(22 + int(lifted))
    max_glyphs = 3
    weights = DEFAULT_SEGMENTATION_WEIGHTS.replace(
        boundary_model=0.0, unattested_may_cross_hints=lifted
    )
    checked_long = 0
    for _ in range(250):
        corpus: dict[str, int] = {}
        for _g in range(rng.randint(3, 8)):
            group = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 6)))
            corpus[group] = rng.choice([1, 1, 2, 3, 7, 20])
        lexicon = {
            "".join(rng.choice(alphabet) for _ in range(rng.randint(2, 6)))
            for _ in range(rng.randint(0, 3))
        } - set(corpus)
        model = ReadingModel()
        for group, count in corpus.items():
            model.sign_reading[group]["r"] += count
        model.lexicon = {group: Counter({"r": 1}) for group in lexicon}
        model.sentences_seen = 1
        segmenter = Segmenter(model, weights, max_group_glyphs=max_glyphs)

        # Build a stream that often contains a known long group.
        pieces = [
            rng.choice(sorted(corpus | dict.fromkeys(lexicon, 0)))
            if rng.random() < 0.6
            else rng.choice(alphabet)
            for _ in range(rng.randint(1, 4))
        ]
        stream = "".join(pieces)[:11]
        if not stream:
            continue
        # Random pasted spacing and random quadrat (no-cut) positions.
        pasted: list[str] = []
        current = ""
        for glyph in stream:
            current += glyph
            if rng.random() < 0.35:
                pasted.append(current)
                current = ""
        if current:
            pasted.append(current)
        no_cut = {k for k in range(1, len(stream)) if rng.random() < 0.2}

        best, winners = _exhaustive_reference(
            corpus, lexicon, weights, max_glyphs, pasted, no_cut
        )
        result = segmenter.segment(pasted, no_cut=frozenset(no_cut))
        assert result.score == pytest.approx(best, abs=1e-9)
        assert result.groups in winners
        if any(len(g) > max_glyphs for g in result.groups):
            checked_long += 1
    # The property is only interesting if long known spans actually won sometimes.
    assert checked_long >= 20
