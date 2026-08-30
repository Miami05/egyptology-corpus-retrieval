from __future__ import annotations

from collections import Counter

import pandas as pd

from math import sqrt


def _char_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> Counter[str]:
    padded = f" {str(text).lower().strip()} "
    grams: Counter[str] = Counter()
    for n in range(min_n, max_n + 1):
        for index in range(0, max(len(padded) - n + 1, 0)):
            grams[padded[index : index + n]] += 1
    return grams


def _norm(counter: Counter[str]) -> float:
    return sqrt(sum(value * value for value in counter.values()))


def char_ngram_vector(text: str) -> tuple[Counter[str], float]:
    """The n-gram counter and its norm, for one string."""
    counter = _char_ngrams(text)
    return counter, _norm(counter)


def cosine_score(left: Counter[str], left_norm: float, right: Counter[str], right_norm: float) -> float:
    if not left or not right or left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    # Iterate the smaller side; the query is almost always far shorter than a row.
    if len(left) > len(right):
        left, right = right, left
    numerator = sum(count * right.get(token, 0) for token, count in left.items())
    return numerator / (left_norm * right_norm)


def build_document_vectors(values: pd.Series) -> list[tuple[Counter[str], float]]:
    """Character n-gram vector and norm for every corpus row.

    Query-independent, so it belongs beside the corpus rather than inside a search:
    rebuilding all 12,772 counters per query was about half of every search.
    """
    return [char_ngram_vector(str(value)) for value in values]


def tfidf_candidates(
    df: pd.DataFrame,
    query_mdc_norm: str,
    document_vectors: list[tuple[Counter[str], float]] | None = None,
) -> pd.DataFrame:
    """Character n-gram cosine similarity against `mdc_norm`.

    Despite the module name there is no IDF term here; it is a plain cosine over
    2-4 character n-grams, kept because it catches near-spellings that token
    overlap misses.
    """
    query_vector, query_norm = char_ngram_vector(query_mdc_norm)
    out = df.copy()
    if document_vectors is not None and len(document_vectors) == len(out):
        out["tfidf_score"] = [
            cosine_score(query_vector, query_norm, vector, norm)
            for vector, norm in document_vectors
        ]
    else:
        out["tfidf_score"] = [
            cosine_score(query_vector, query_norm, *char_ngram_vector(str(value)))
            for value in out["mdc_norm"]
        ]
    return out.sort_values("tfidf_score", ascending=False, kind="mergesort")
