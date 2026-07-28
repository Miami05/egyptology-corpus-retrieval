from __future__ import annotations

from collections import Counter
from math import sqrt

import pandas as pd


def _char_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> Counter[str]:
    padded = f" {str(text).lower().strip()} "
    grams: Counter[str] = Counter()
    for n in range(min_n, max_n + 1):
        for index in range(0, max(len(padded) - n + 1, 0)):
            grams[padded[index : index + n]] += 1
    return grams


def _cosine_score(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[token] * right.get(token, 0) for token in left)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def tfidf_candidates(df: pd.DataFrame, query_mdc_norm: str) -> pd.DataFrame:
    """
    Lightweight character n-gram similarity.

    The original prototype used sklearn TF-IDF here. For the MVP we keep the
    same output column while avoiding a heavy sklearn import during app start.
    """
    query_vector = _char_ngrams(query_mdc_norm)
    out = df.copy()
    out["tfidf_score"] = out["mdc_norm"].map(
        lambda value: _cosine_score(query_vector, _char_ngrams(str(value)))
    )
    return out.sort_values("tfidf_score", ascending=False)
