from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import replace as dataclasses_replace
from math import sqrt

import pandas as pd

from app.data.normalizer import (
    nfc,
    normalize_mdc,
    normalize_sign_sequence,
    normalize_transliteration,
    normalize_whitespace,
)
from app.retrieval.scorer import (
    effective_surplus_penalty,
    token_overlap_score,
    tokenize_query,
)

TOKEN_RE = re.compile(r"[\s|:;\-,=~{}\[\]().]+")
LOOSE_MARKER_RE = re.compile(r"[|:;\-,=~{}\[\]().]+")
# Characters the strict key drops: editorial brackets (round, square, curly, angle,
# half-brackets) and the morpheme dot. Their *contents* are kept — `(w)di̯` keeps its
# w — so only the marks vanish, never a letter.
STRICT_DROP_RE = re.compile(r"[()\[\]{}⟨⟩⸢⸣⸤⸥〈〉.|]+")


@dataclass(frozen=True)
class SuggestionWeights:
    """Weights for ranking grouped reading candidates.

    This layer re-ranks the readings that retrieval already ordered, so its weights
    decide what reaches the top 3. Keep `relative_score` dominant: it carries the
    tuned retrieval signal (including IDF-weighted overlap), and when this layer
    recomputes too much of its own similarity it can push a well-retrieved parallel
    out of the top 3.
    """

    relative_score: float = 0.24
    mean_score: float = 0.12
    translit_overlap: float = 0.20
    char_similarity: float = 0.16
    exact_or_near: float = 0.12
    reading_similarity: float = 0.08
    support: float = 0.05
    lemma_density: float = 0.03
    # Not a weight (never part of the weight mass): Tversky penalty on the
    # candidate reading's surplus tokens inside translit_overlap. At 1.0 the
    # overlap is symmetric Jaccard, which lets a one-token reading outscore the
    # full sentence that contains the whole query — see idf_overlap_score, whose
    # docstring also records how 0.3 was chosen and what the holdout showed.
    surplus_penalty: float = 0.3

    def replace(self, **changes: float) -> SuggestionWeights:
        return dataclasses_replace(self, **changes)


DEFAULT_SUGGESTION_WEIGHTS = SuggestionWeights()


@dataclass(frozen=True)
class ReadingSuggestion:
    candidate_transliteration: str
    confidence_score: float
    supporting_example_count: int
    supporting_sources: list[str]
    evidence_summary: str


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _token_set(value: object) -> set[str]:
    text = normalize_transliteration(_safe_str(value))
    return {token for token in TOKEN_RE.split(text) if token}


def strict_reading_key(value: object) -> str:
    """Identity key for a reading: two readings share it only if they are the same
    string of sounds.

    NFC, lower-case, `⸗` → `=`, editorial brackets and dots removed, everything else
    kept. In particular every Egyptological letter stays distinct (ꜣ ≠ ꜥ, ḥ ≠ h,
    ḫ ≠ ẖ, ṯ ≠ t, ḏ ≠ d), the yod ꞽ is a letter and is kept, and `=` survives so a
    suffix pronoun `=ꞽ` does not collapse to the empty string.

    This replaced the old canonical key, which ran the ASCII search fold first and
    merged 256 sentence-level readings that differ in a consonant (ꜣ/ꜥ 85 pairs, ḥ/h
    986 tokens) — corrupting suggestion grouping and support counts. The ASCII fold
    still exists for *search*; it is simply not an identity.
    """
    text = nfc(_safe_str(value)).lower().replace("⸗", "=")
    text = STRICT_DROP_RE.sub("", text)
    return normalize_whitespace(text)


def canonical_reading(value: object) -> str:
    """The key readings are grouped and compared by. Strict — see strict_reading_key."""
    return strict_reading_key(value)


def loose_reading_form(value: object) -> str:
    """Display / near-match form: ASCII-folded and stripped of editorial marks.

    Deliberately lossy (ḥ and h both become h), so it can tell that a user's plain
    ASCII `htp` means the corpus's `ḥtp` and that `n.t` and `n(.ꞽ).t` are one word.
    Never use it to decide that two corpus readings are identical.
    """
    text = normalize_transliteration(_safe_str(value))
    text = LOOSE_MARKER_RE.sub(" ", text)
    return normalize_mdc(text)


def char_ngram_similarity(left: object, right: object) -> float:
    left_text = f" {loose_reading_form(left)} "
    right_text = f" {loose_reading_form(right)} "
    if not left_text.strip() or not right_text.strip():
        return 0.0
    left_counts: Counter[str] = Counter()
    right_counts: Counter[str] = Counter()
    for ngram_size in (2, 3, 4):
        for index in range(0, max(len(left_text) - ngram_size + 1, 0)):
            left_counts[left_text[index : index + ngram_size]] += 1
        for index in range(0, max(len(right_text) - ngram_size + 1, 0)):
            right_counts[right_text[index : index + ngram_size]] += 1
    if not left_counts or not right_counts:
        return 0.0
    numerator = sum(left_counts[token] * right_counts.get(token, 0) for token in left_counts)
    left_norm = sqrt(sum(value * value for value in left_counts.values()))
    right_norm = sqrt(sum(value * value for value in right_counts.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def set_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _source_label(row: pd.Series) -> str:
    source = _safe_str(row.get("source")) or "unknown"
    text_id = _safe_str(row.get("source_text_id")) or "no_text_id"
    sentence_id = _safe_str(row.get("source_sentence_id")) or "no_sentence_id"
    return f"{source}/{text_id}/{sentence_id}"


def _evidence_summary(
    group: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str,
    candidate_transliteration: str,
) -> str:
    bits: list[str] = []
    candidate_key = canonical_reading(candidate_transliteration)
    query_key = canonical_reading(query_mdc)
    candidate_loose = loose_reading_form(candidate_transliteration)
    query_loose = loose_reading_form(query_mdc)

    if query_key and candidate_key == query_key:
        bits.append("same normalized query reading")
    elif query_loose and candidate_loose == query_loose:
        bits.append("same simplified query reading")
    elif query_key and char_ngram_similarity(query_key, candidate_key) >= 0.72:
        bits.append("near simplified query reading")

    query_reading_norm = normalize_sign_sequence(query_reading_order)
    if query_reading_norm:
        reading_scores = [
            token_overlap_score(
                query_reading_norm,
                _safe_str(row.get("normalized_reading_order_norm"))
                or normalize_sign_sequence(_safe_str(row.get("normalized_reading_order"))),
            )
            for _, row in group.iterrows()
        ]
        if max(reading_scores or [0.0]) >= 0.92:
            bits.append("same normalized reading order")
        elif max(reading_scores or [0.0]) > 0.0:
            bits.append("similar normalized reading order")

    query_tokens = set(tokenize_query(query_loose or query_key))
    candidate_tokens = set(tokenize_query(candidate_loose or candidate_key))
    if query_tokens and candidate_tokens:
        shared = sorted(query_tokens & candidate_tokens)
        if shared:
            shown = ", ".join(shared[:8])
            bits.append(f"shared transliteration tokens: {shown}")

    lemma_sets = [
        _token_set(row.get("lemma_sequence"))
        for _, row in group.iterrows()
        if _token_set(row.get("lemma_sequence"))
    ]
    shared_lemmas = set.intersection(*lemma_sets) if lemma_sets else set()
    if shared_lemmas:
        shown = ", ".join(sorted(shared_lemmas)[:8])
        bits.append(f"shared lemma IDs: {shown}")

    formula_bits = []
    for field, label in [
        ("formula_type", "formula type"),
        ("formula_slot", "formula slot"),
        ("genre", "genre"),
    ]:
        values = {_safe_str(value) for value in group.get(field, []) if _safe_str(value)}
        if len(values) == 1:
            formula_bits.append(label)
    if formula_bits:
        bits.append("shared context: " + ", ".join(formula_bits))

    support_count = len(group)
    bits.append(f"supported by {support_count} similar corpus row{'s' if support_count != 1 else ''}")

    return "; ".join(bits)


def suggest_top_readings(
    retrieval_results: pd.DataFrame,
    query_mdc: str,
    query_reading_order: str = "",
    top_n: int = 3,
    include_query_candidate: bool = False,
    weights: SuggestionWeights = DEFAULT_SUGGESTION_WEIGHTS,
) -> list[ReadingSuggestion]:
    if retrieval_results.empty:
        return []

    results = retrieval_results.copy()
    results["candidate_transliteration"] = results["transliteration_gold"].map(_safe_str)
    results = results[results["candidate_transliteration"] != ""].copy()
    if results.empty:
        return []

    results["candidate_key"] = results["candidate_transliteration"].map(canonical_reading)
    rows: list[dict] = []
    max_row_score = max(float(value) for value in results["final_score"].fillna(0.0))
    query_key = canonical_reading(query_mdc)
    query_loose = loose_reading_form(query_mdc)
    surplus_penalty = effective_surplus_penalty(
        query_loose or query_key, weights.surplus_penalty
    )

    for candidate_key, group in results.groupby("candidate_key", sort=False):
        group = group.sort_values("final_score", ascending=False).copy()
        best = group.iloc[0]
        best_score = float(best.get("final_score", 0.0) or 0.0)
        mean_score = float(group["final_score"].fillna(0.0).mean())
        support_count = int(len(group))
        support_bonus = min(support_count, 5) / 5.0
        best_candidate = best["candidate_transliteration"]
        candidate_loose = loose_reading_form(best_candidate)
        translit_overlap = max(
            token_overlap_score(query_key, candidate_key, surplus_penalty),
            token_overlap_score(query_loose, candidate_loose, surplus_penalty),
        )
        char_similarity = char_ngram_similarity(query_key, candidate_key)
        exact_or_near_bonus = 1.0 if candidate_key == query_key else 0.0
        if exact_or_near_bonus == 0.0 and query_loose == candidate_loose:
            exact_or_near_bonus = 0.85
        elif exact_or_near_bonus == 0.0 and char_similarity >= 0.82:
            exact_or_near_bonus = 0.65
        lemma_density = min(
            sum(1 for value in group.get("lemma_sequence", []) if _safe_str(value)),
            5,
        ) / 5.0
        reading_similarity = 0.0
        query_reading_norm = normalize_sign_sequence(query_reading_order)
        if query_reading_norm:
            reading_similarity = max(
                token_overlap_score(
                    query_reading_norm,
                    _safe_str(row.get("normalized_reading_order_norm"))
                    or normalize_sign_sequence(
                        _safe_str(row.get("normalized_reading_order"))
                    ),
                )
                for _, row in group.iterrows()
            )

        relative_score = best_score / max_row_score if max_row_score > 0 else 0.0
        weighted = (
            weights.relative_score * relative_score
            + weights.mean_score * mean_score
            + weights.translit_overlap * translit_overlap
            + weights.char_similarity * char_similarity
            + weights.exact_or_near * exact_or_near_bonus
            + weights.reading_similarity * reading_similarity
            + weights.support * support_bonus
            + weights.lemma_density * lemma_density
        )
        # Normalise by the weight mass so confidences stay comparable when the
        # weights are retuned, rather than shrinking as weights are redistributed.
        weight_mass = (
            weights.relative_score
            + weights.mean_score
            + weights.translit_overlap
            + weights.char_similarity
            + weights.exact_or_near
            + weights.reading_similarity
            + weights.support
            + weights.lemma_density
        )
        candidate_score = weighted / weight_mass if weight_mass > 0 else 0.0
        confidence = max(0.0, min(0.99, candidate_score))

        rows.append(
            {
                "candidate_transliteration": best["candidate_transliteration"],
                "confidence_score": round(confidence, 3),
                "supporting_example_count": support_count,
                "supporting_sources": [_source_label(row) for _, row in group.head(5).iterrows()],
                "evidence_summary": _evidence_summary(
                    group,
                    query_mdc=query_mdc,
                    query_reading_order=query_reading_order,
                    candidate_transliteration=best["candidate_transliteration"],
                ),
            }
        )

    if include_query_candidate and query_key:
        support_group = results.sort_values("final_score", ascending=False).head(5).copy()
        query_already_suggested = any(
            canonical_reading(row["candidate_transliteration"]) == query_key
            for row in rows
        )
        if not support_group.empty and not query_already_suggested:
            support_count = len(support_group)
            support_bonus = min(support_count, 5) / 5.0
            best_support = float(support_group["final_score"].fillna(0.0).max())
            relative_score = best_support / max_row_score if max_row_score > 0 else 0.0
            average_support = float(support_group["final_score"].fillna(0.0).mean())
            # The query's own reading matches itself, so the similarity terms are at
            # full strength; only the evidence terms vary.
            query_weighted = (
                weights.relative_score * relative_score
                + weights.mean_score * average_support
                + weights.translit_overlap
                + weights.char_similarity
                + weights.exact_or_near
                + weights.support * support_bonus
                + weights.lemma_density
            )
            query_mass = (
                weights.relative_score
                + weights.mean_score
                + weights.translit_overlap
                + weights.char_similarity
                + weights.exact_or_near
                + weights.reading_similarity
                + weights.support
                + weights.lemma_density
            )
            query_score = query_weighted / query_mass if query_mass > 0 else 0.0
            rows.append(
                {
                    "candidate_transliteration": query_key,
                    "confidence_score": round(max(0.0, min(0.99, query_score)), 3),
                    "supporting_example_count": support_count,
                    "supporting_sources": [
                        _source_label(row) for _, row in support_group.iterrows()
                    ],
                    "evidence_summary": _evidence_summary(
                        support_group,
                        query_mdc=query_mdc,
                        query_reading_order=query_reading_order,
                        candidate_transliteration=query_key,
                    ),
                }
            )

    rows = sorted(
        rows,
        key=lambda row: (
            row["confidence_score"],
            row["supporting_example_count"],
            row["candidate_transliteration"],
        ),
        reverse=True,
    )
    return [ReadingSuggestion(**row) for row in rows[:top_n]]
