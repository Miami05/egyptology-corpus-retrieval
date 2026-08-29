"""Fuzz the whole pipeline with corpus-derived and hostile queries.

Not a correctness oracle — a crash-and-invariants net over Phases 0–2 as one system:
segmentation → reading model → retrieval → suggestions must never raise, must keep
scores in [0, 1], and must be deterministic, for any input a user can paste. Inputs
are derived from real corpus rows (with spacing removed or scrambled, variant
codepoints substituted, Latin noise appended) plus known-hostile shapes (empty,
format controls only, markup, mixed scripts).

A heavier run of the same harness (300 queries) is executed before each release;
this committed version keeps the suite fast.
"""

from __future__ import annotations

import random

import pytest

from app.data.normalizer import contains_hieroglyphs, normalize_hieroglyphs
from app.services.reading_model import train_reading_model
from app.services.retrieval import retrieve_top_k
from app.services.segmentation import Segmenter
from app.services.suggestions import suggest_top_readings

HOSTILE = [
    "",
    "   ",
    "\U00013431\U00013432",  # format controls only
    "<g>D77</g>",
    "<g></g>",
    "𓀀" * 60,  # one absurd group
    "line 2: 𓊵𓏙 [sic] wad",
    "ḥtp-ḏi̯ nswt",
    "H*t:p",
    "𓏼𓏼𓏼",  # variant plural strokes only
    "…—()[]",
]


@pytest.fixture(scope="module")
def stack():
    from app.data.loader import load_examples_csv

    df = load_examples_csv("data/processed/examples.csv")
    model = train_reading_model(df)
    return df, model, Segmenter(model)


def corpus_derived_queries(df, count: int, seed: int = 11) -> list[str]:
    rng = random.Random(seed)
    rows = df[df["hieroglyphs_norm"].astype(str).str.strip() != ""]
    sample = rows.sample(n=count, random_state=seed)
    queries: list[str] = []
    for _, row in sample.iterrows():
        groups = str(row["hieroglyphs_norm"]).split()
        start = rng.randrange(len(groups))
        fragment = groups[start : start + rng.randint(1, 6)]
        stream = "".join(fragment)
        style = rng.randrange(4)
        if style == 0:  # no spaces
            queries.append(stream)
        elif style == 1:  # random spaces
            cut = sorted(rng.sample(range(1, len(stream)), min(2, len(stream) - 1))) if len(stream) > 1 else []
            parts, prev = [], 0
            for c in cut + [len(stream)]:
                parts.append(stream[prev:c])
                prev = c
            queries.append(" ".join(parts))
        elif style == 2:  # variant strokes + Latin noise
            queries.append(stream.replace("\U000133E5", "\U000133FC") + " p. 12")
        else:  # as attested
            queries.append(" ".join(fragment))
    return queries


def run_once(df, model, segmenter, query: str):
    regrouped = None
    if contains_hieroglyphs(query):
        groups = segmenter.segment(normalize_hieroglyphs(query).split()).groups
        predictions = model.predict_sequence(groups)
        assert len(predictions) == len(groups)
        regrouped = " ".join(groups)
    pool = retrieve_top_k(
        df, query_mdc=query, k=50, query_hieroglyphs_norm=regrouped
    )
    if not pool.empty:
        scores = pool["final_score"]
        assert scores.between(0.0, 1.0 + 1e-9).all(), f"score out of range for {query!r}"
        assert pool["evidence"].map(lambda e: isinstance(e, str) and e != "").all()
    suggestions = suggest_top_readings(
        pool, query_mdc=query, query_hieroglyphs=regrouped or ""
    )
    for s in suggestions:
        assert 0.0 <= s.confidence_score <= 0.99
        assert s.supporting_example_count >= 1
    return pool.head(5)["source_text_id"].tolist(), [
        s.candidate_transliteration for s in suggestions
    ]


@pytest.mark.parametrize("query", HOSTILE)
def test_hostile_inputs_never_raise(stack, query):
    df, model, segmenter = stack
    run_once(df, model, segmenter, query)


def test_corpus_derived_queries_never_raise_and_are_deterministic(stack):
    df, model, segmenter = stack
    for query in corpus_derived_queries(df, count=12):
        first = run_once(df, model, segmenter, query)
        second = run_once(df, model, segmenter, query)
        assert first == second, f"nondeterministic for {query!r}"
