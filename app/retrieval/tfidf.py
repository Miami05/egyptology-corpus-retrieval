from __future__ import annotations

from collections import Counter
from typing import Callable

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize

from math import sqrt


def _char_ngram_list(text: str, min_n: int = 2, max_n: int = 4) -> list[str]:
    """2-4 character n-grams of `text`, padded with a leading/trailing space and
    with whitespace runs left uncollapsed.

    This is the one place that decides what an n-gram is. It doubles as the
    `analyzer` callable handed to `CountVectorizer`: sklearn's own
    `analyzer="char"` neither pads the string nor keeps whitespace runs
    uncollapsed, so reusing this exact routine (rather than sklearn's built-in
    char analyzer) is what keeps `NgramIndex` numerically identical to the
    `_char_ngrams`/`cosine_score` reference path below. `_char_ngrams` is
    defined in terms of this function so the two representations (flat list
    for the vectorizer, `Counter` for the reference implementation) cannot
    silently drift apart.
    """
    padded = f" {str(text).lower().strip()} "
    return [
        padded[index : index + n]
        for n in range(min_n, max_n + 1)
        for index in range(0, max(len(padded) - n + 1, 0))
    ]


def _char_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> Counter[str]:
    return Counter(_char_ngram_list(text, min_n, max_n))


def _norm(counter: Counter[str]) -> float:
    return sqrt(sum(value * value for value in counter.values()))


def char_ngram_vector(text: str) -> tuple[Counter[str], float]:
    """The n-gram counter and its norm, for one string.

    Kept as the reference implementation: small, pure, and used both by tests
    that check `NgramIndex` against it and by any one-off caller that wants a
    single vector without building an index.
    """
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

    Reference implementation only — this is the one-Counter-per-row approach
    `NgramIndex` replaces for production use (216 MB at 31k rows, 584 MB at
    78k). Kept for tests that check the sparse index against it; nothing in
    `app/` builds a corpus-wide list of these any more.
    """
    return [char_ngram_vector(str(value)) for value in values]


class NgramIndex:
    """Sparse, L2-normalised 2-4 character n-gram index over one text column.

    Replaces one Python `Counter` per row with a single CSR matrix: same
    cosine scores (see the equivalence tests in tests/test_phase3_performance.py),
    a fraction of the memory, and one sparse matrix-vector product per query
    instead of a Python loop. Measured on the real corpus (`pd.concat`-doubled
    to ~78k rows for the dry run): the index object itself drops from 453 MB
    (list of Counters) to 67 MB (this class) at 78k rows, and the per-query
    cosine-scoring step drops from 178 ms to 10 ms.

    Field-generic by construction: `build` takes any `pd.Series` of strings, so
    the same class indexes `mdc_norm` today and can index a hieroglyph or
    translation column tomorrow without change.

    Analyzer-generic too (ROADMAP item E): `build(values, analyzer=...)` swaps what
    an n-gram *is*. The default is `_char_ngram_list`, the 2-4 character n-grams
    every existing caller expects, so `mdc_norm` and `translation` are indexed
    identically; the sign tier passes `app.services.similar_text.sign_ngram_list`
    instead, which emits 1-3-grams of Unicode hieroglyph code points. The analyzer
    is kept on the instance so `scores()` vectorises the query the same way the
    rows were vectorised — the two must never be allowed to disagree.
    """

    __slots__ = ("_vectorizer", "_matrix", "_analyzer")

    def __init__(
        self,
        vectorizer: CountVectorizer,
        matrix: sparse.csr_matrix,
        analyzer: Callable[[str], list[str]] = _char_ngram_list,
    ) -> None:
        self._vectorizer = vectorizer
        self._matrix = matrix  # L2-normalised rows, dtype float64
        self._analyzer = analyzer

    @classmethod
    def build(
        cls,
        values: pd.Series,
        analyzer: Callable[[str], list[str]] = _char_ngram_list,
    ) -> "NgramIndex":
        texts = [str(value) for value in values]
        vectorizer = CountVectorizer(analyzer=analyzer, dtype=np.float64)
        if texts:
            counts = vectorizer.fit_transform(texts)
        else:
            counts = sparse.csr_matrix((0, 0), dtype=np.float64)
        # normalize(..., copy=False) rescales `counts`'s own .data array in place
        # (row by row, without ever materialising a second same-size matrix) —
        # `counts.multiply(counts)` to get row norms would silently double peak
        # memory during the build for no benefit, since `counts` is discarded
        # right after this call anyway.
        matrix = normalize(counts, norm="l2", copy=False).tocsr()
        matrix.indices = matrix.indices.astype(np.int32, copy=False)
        matrix.indptr = matrix.indptr.astype(np.int32, copy=False)
        return cls(vectorizer, matrix, analyzer)

    def __len__(self) -> int:
        return self._matrix.shape[0]

    def scores(self, query_text: str) -> np.ndarray:
        """Cosine similarity of `query_text` against every indexed row, in row order.

        The query is vectorised two ways on purpose:
        - its norm comes from the FULL n-gram `Counter`, including n-grams never
          seen in the corpus (they contribute 0 to every dot product but still
          count towards the query's own length) — matching the original
          `cosine_score` exactly;
        - the dot product uses `vectorizer.transform`, which silently drops
          n-grams outside the fitted vocabulary. That is safe for the numerator
          only: an n-gram absent from every corpus row contributes 0 to every
          row's score regardless, so dropping it before the dot product changes
          nothing but saves the work.
        """
        n_rows = self._matrix.shape[0]
        if n_rows == 0:
            return np.zeros(0, dtype=np.float64)
        query_counter = Counter(self._analyzer(str(query_text)))
        query_norm = _norm(query_counter)
        if not query_counter or query_norm == 0.0:
            return np.zeros(n_rows, dtype=np.float64)
        query_vector = self._vectorizer.transform([str(query_text)]).astype(np.float64)
        dot = self._matrix.dot(query_vector.T).toarray().ravel()
        return dot / query_norm


def tfidf_candidates(
    df: pd.DataFrame,
    query_mdc_norm: str,
    index: NgramIndex | None = None,
) -> pd.DataFrame:
    """Character n-gram cosine similarity against `mdc_norm`.

    Despite the module name there is no IDF term here; it is a plain cosine over
    2-4 character n-grams, kept because it catches near-spellings that token
    overlap misses.
    """
    out = df.copy()
    if index is not None and len(index) == len(out):
        out["tfidf_score"] = index.scores(query_mdc_norm)
    else:
        row_index = NgramIndex.build(out["mdc_norm"])
        out["tfidf_score"] = row_index.scores(query_mdc_norm)
    return out.sort_values("tfidf_score", ascending=False, kind="mergesort")
