"""Per-row token structures, built once per corpus and reused by every query.

Why this exists (ROADMAP item 3, 2026-09-05). `app.retrieval.scorer.combine_scores`
used to walk the whole corpus in Python for every search: re-tokenising each
candidate string, building two `set`s per row, and re-deriving the IDF weight of
every token from a dict — three times over (plain overlap, IDF overlap, and again
for the sign columns). On the 130k-row corpus that was ~5 s of the ~5.7 s a warm
query took, and it grew linearly with the corpus. None of it depends on the query.

So it is done once, here, at resource-build time:

* `TokenTable` — the corpus column's token *sets* as a binary CSR matrix
  (rows x vocabulary), plus each row's token count and its string forms. Set
  intersection with a query becomes one sparse mat-vec instead of 130,000 Python
  set operations.
* `TokenWeights` — the IDF weight of every vocabulary token, and each row's total
  token weight. These depend on the document frequencies, which are *per stage*
  (see `app.services.stage`), so a `TokenTable` is shared by all four stage
  resource sets — every `StageResources.frame` is the same pooled frame — while
  each set gets its own `TokenWeights`.
* `ScoringTables` — the pair of the above for the transliteration column and the
  sign column, tagged with the frame's row labels so a caller can check that the
  frame it is scoring really is the frame these were built from.

Equivalence. Every score here is the same formula as the scalar reference in
`scorer.py`, and `tests/test_scoring_equivalence.py` locks that down against the
reference implementation. Two caveats, both deliberate and documented there:

* the overlap scores are pure integer arithmetic (shared / (|q| + |c| - shared)),
  so they are bit-identical to the scalar path;
* the IDF overlap sums the same weights in a different order (ascending column
  index, rather than Python `set` iteration order), which is a different rounding
  of the same sum. The difference is at the 1e-16 level — see the test, which
  asserts both a tight tolerance and identical ranking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from math import log

import numpy as np
import pandas as pd
from scipy import sparse

TOKEN_SPLIT_RE = re.compile(r"[\s:\-]+")

# Sign groups are encoded as single characters so rapidfuzz can run the
# longest-common-subsequence match over sign *groups* at C speed. The private-use
# planes start here; `_GROUP_CODE_LIMIT` is how many distinct groups fit below the
# top of the Unicode range, beyond which `encode_groups` gives up and the caller
# falls back to the scalar path.
_GROUP_CODE_BASE = 0x20000
_GROUP_CODE_LIMIT = 0x110000 - _GROUP_CODE_BASE


@lru_cache(maxsize=100_000)
def _tokenize_cached(raw: str) -> tuple[str, ...]:
    return tuple(tok for tok in TOKEN_SPLIT_RE.split(raw) if tok)


def tokenize_query(text: str) -> list[str]:
    """Split a query or candidate into content tokens.

    Cached: one search used to call this ~64,000 times — roughly five times per
    corpus row, because the overlap, IDF-overlap and document-frequency passes each
    re-split the same strings. Since `TokenTable` those corpus-side calls happen
    once at build time, and the cache now only serves query-side calls.
    """
    return list(_tokenize_cached(str(text).strip().lower()))


@dataclass(frozen=True)
class TokenTable:
    """One corpus text column, tokenised once.

    `matrix` is a row-per-corpus-row, column-per-vocabulary-token indicator matrix
    with 1.0 in every cell whose token occurs in that row — i.e. exactly the
    `set(tokenize_query(value))` the scalar path builds per query, in CSR form. A
    query's shared-token count against every row at once is then `matrix @ v`,
    where `v` marks the query's own columns.

    `texts` and `stripped` are `str(value)` and `str(value).strip()` per row, kept
    because the fuzzy score, the exact bonus and the sign exact bonus each used to
    rebuild one of them per query.
    """

    vocabulary: dict[str, int]
    matrix: sparse.csr_matrix
    row_sizes: np.ndarray  # int64, the number of distinct tokens per row
    texts: np.ndarray  # object array of str(value)
    stripped: np.ndarray  # object array of str(value).strip()
    # Sign-group encoding, for the order-aware glyph signal. `None` for a column
    # that is not a sign column.
    encoded: np.ndarray | None
    group_codes: dict[str, str] | None

    @property
    def n_rows(self) -> int:
        return int(self.matrix.shape[0])

    @classmethod
    def build(cls, values: pd.Series, encode_groups: bool = False) -> "TokenTable":
        n_rows = len(values)
        vocabulary: dict[str, int] = {}
        indices: list[int] = []
        indptr = np.zeros(n_rows + 1, dtype=np.int64)
        row_sizes = np.zeros(n_rows, dtype=np.int64)
        texts = np.empty(n_rows, dtype=object)
        stripped = np.empty(n_rows, dtype=object)
        group_codes: dict[str, str] | None = {} if encode_groups else None
        encoded = np.empty(n_rows, dtype=object) if encode_groups else None

        for position, value in enumerate(values):
            text = str(value)
            texts[position] = text
            stripped[position] = text.strip()
            # Same tokens the scalar path sees: tokenize_query lowercases and
            # strips before splitting, and the scorer takes the set of them.
            columns = {
                vocabulary.setdefault(token, len(vocabulary))
                for token in tokenize_query(text)
            }
            # Sorted so the mat-vec sums a row's weights in a stable order and the
            # matrix satisfies scipy's canonical-CSR expectations.
            indices.extend(sorted(columns))
            row_sizes[position] = len(columns)
            indptr[position + 1] = len(indices)
            if group_codes is not None and encoded is not None:
                encoded[position] = "".join(
                    _group_code(group_codes, group) for group in text.split()
                )

        matrix = sparse.csr_matrix(
            (
                np.ones(len(indices), dtype=np.float64),
                np.asarray(indices, dtype=np.int32),
                indptr.astype(np.int32),
            ),
            shape=(n_rows, max(len(vocabulary), 1)),
        )
        if group_codes is not None and len(group_codes) >= _GROUP_CODE_LIMIT:
            # More distinct sign groups than there are codepoints to encode them
            # with. Not reachable on any corpus this project could hold, but the
            # scalar fallback must stay correct rather than silently collide.
            group_codes, encoded = None, None
        return cls(
            vocabulary=vocabulary,
            matrix=matrix,
            row_sizes=row_sizes,
            texts=texts,
            stripped=stripped,
            encoded=encoded,
            group_codes=group_codes,
        )

    def query_vector(self, query_tokens: set[str]) -> tuple[np.ndarray, list[int]]:
        """A dense indicator vector over this column's vocabulary, and its columns."""
        columns = sorted(
            self.vocabulary[token]
            for token in query_tokens
            if token in self.vocabulary
        )
        vector = np.zeros(self.matrix.shape[1], dtype=np.float64)
        if columns:
            vector[columns] = 1.0
        return vector, columns

    def overlap_scores(
        self, query_tokens: set[str], candidate_surplus_penalty: float = 1.0
    ) -> np.ndarray:
        """`scorer.token_overlap_score` of the query against every row.

        Bit-identical to the scalar path: every quantity below is an exact integer
        held in a float64, and the single division is the same correctly-rounded
        one Python's `/` performs.
        """
        n_rows = self.n_rows
        query_size = len(query_tokens)
        if query_size == 0 or n_rows == 0:
            return np.zeros(n_rows, dtype=np.float64)
        vector, columns = self.query_vector(query_tokens)
        shared = (
            self.matrix @ vector if columns else np.zeros(n_rows, dtype=np.float64)
        )
        candidate_size = self.row_sizes.astype(np.float64)
        # Written in the scalar path's own grouping: shared + |q - c| + penalty*|c - q|.
        denominator = (
            shared
            + (query_size - shared)
            + candidate_surplus_penalty * (candidate_size - shared)
        )
        scores = np.zeros(n_rows, dtype=np.float64)
        usable = (self.row_sizes > 0) & (denominator > 0.0)
        scores[usable] = shared[usable] / denominator[usable]
        return scores

    def exact_matches(self, query: str, strip: bool) -> np.ndarray:
        """1.0 where the row's text equals `query`, as the exact bonuses do it."""
        source = self.stripped if strip else self.texts
        if self.n_rows == 0:
            return np.zeros(0, dtype=np.float64)
        return (source == query).astype(np.float64)


def _group_code(group_codes: dict[str, str], group: str) -> str:
    code = group_codes.get(group)
    if code is None:
        index = len(group_codes)
        code = chr(_GROUP_CODE_BASE + index) if index < _GROUP_CODE_LIMIT else "\uffff"
        group_codes[group] = code
    return code


def encode_groups(table: TokenTable, text: str) -> str | None:
    """Encode a query's sign groups with the corpus's own group->character map.

    The scalar path builds this map per query, starting from the query's groups;
    here the corpus's map is reused and query-only groups are appended after it.
    Either way the map is a bijection, and the longest-common-subsequence
    similarity depends only on which symbols compare equal — never on which
    characters were chosen — so the two encodings score identically.

    Returns `None` when the corpus map is unusable (see `TokenTable.build`) or the
    query needs more codes than remain, so the caller falls back to the scalar path.
    """
    if table.group_codes is None or table.encoded is None:
        return None
    codes = table.group_codes
    extra: dict[str, str] = {}
    pieces: list[str] = []
    for group in str(text).split():
        code = codes.get(group) or extra.get(group)
        if code is None:
            index = len(codes) + len(extra)
            if index >= _GROUP_CODE_LIMIT:
                return None
            code = chr(_GROUP_CODE_BASE + index)
            extra[group] = code
        pieces.append(code)
    return "".join(pieces)


@dataclass(frozen=True)
class TokenWeights:
    """The IDF weight of every token of one `TokenTable`, for one stage.

    `weight` is `scorer.idf_overlap_score`'s own `weight()`:
    `log((corpus_size + 1) / (document_frequency + 1)) + 1`. `unseen` is that
    weight for a token the frequency table has never seen — the value a query token
    outside the corpus (or outside this stage's rows) carries.

    `row_totals[i]` is the summed weight of row `i`'s tokens, which is what turns a
    candidate's surplus weight into a subtraction rather than a per-row loop.

    Stage-dependent (the frequencies are), while the `TokenTable` it weights is
    not — see the module docstring.
    """

    weights: np.ndarray
    row_totals: np.ndarray
    unseen: float
    corpus_size: int

    @classmethod
    def build(
        cls, table: TokenTable, frequencies: dict[str, int], corpus_size: int
    ) -> "TokenWeights":
        weights = np.empty(table.matrix.shape[1], dtype=np.float64)
        weights.fill(log(corpus_size + 1) + 1.0)
        for token, column in table.vocabulary.items():
            weights[column] = log((corpus_size + 1) / (frequencies.get(token, 0) + 1)) + 1.0
        return cls(
            weights=weights,
            row_totals=table.matrix @ weights,
            unseen=log(corpus_size + 1) + 1.0,
            corpus_size=corpus_size,
        )

    def idf_overlap_scores(
        self,
        table: TokenTable,
        query_tokens: set[str],
        candidate_surplus_penalty: float = 1.0,
    ) -> np.ndarray:
        """`scorer.idf_overlap_score` of the query against every row.

        Same formula, same weights; the shared weight is accumulated by the sparse
        mat-vec in ascending column order rather than in Python `set` order, which
        rounds the identical sum differently at the last bit or two. See the module
        docstring and `tests/test_scoring_equivalence.py`.
        """
        n_rows = table.n_rows
        if not query_tokens or n_rows == 0:
            return np.zeros(n_rows, dtype=np.float64)
        vector = np.zeros(table.matrix.shape[1], dtype=np.float64)
        query_weight = 0.0
        any_column = False
        for token in sorted(query_tokens):
            column = table.vocabulary.get(token)
            if column is None:
                query_weight += self.unseen
            else:
                weight = float(self.weights[column])
                vector[column] = weight
                query_weight += weight
                any_column = True
        shared = (
            table.matrix @ vector if any_column else np.zeros(n_rows, dtype=np.float64)
        )
        # The scalar path's grouping: shared + query-only + penalty * candidate-only.
        denominator = (
            shared
            + (query_weight - shared)
            + candidate_surplus_penalty * (self.row_totals - shared)
        )
        scores = np.zeros(n_rows, dtype=np.float64)
        usable = (table.row_sizes > 0) & (denominator > 0.0)
        scores[usable] = shared[usable] / denominator[usable]
        return scores


@dataclass(frozen=True)
class ScoringTables:
    """The precomputed structures for one `SearchIndex`.

    `row_ids` are the frame's row labels as they were at build time. Every
    consumer checks them against the frame it is about to score (`matches`), and
    falls back to the scalar path if they differ — the precomputed rows are
    positional, so scoring a filtered or reordered frame with them would silently
    mis-attribute scores.
    """

    row_ids: np.ndarray
    text: TokenTable
    text_weights: TokenWeights
    glyph: TokenTable | None
    glyph_weights: TokenWeights | None

    def matches(self, frame: pd.DataFrame) -> bool:
        if len(frame) != len(self.row_ids):
            return False
        return bool(np.array_equal(frame.index.to_numpy(), self.row_ids))

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        mdc_frequencies: dict[str, int],
        glyph_frequencies: dict[str, int],
        reuse: "ScoringTables | None" = None,
    ) -> "ScoringTables":
        """Build the tables for `df`, weighted by the given document frequencies.

        `reuse` supplies already-built `TokenTable`s for the same frame — every
        stage's `StageResources.frame` is the same pooled frame, so the four stage
        resource sets tokenise the corpus once between them and differ only in
        their `TokenWeights` (one mat-vec each). Ignored if it was built from a
        different frame.
        """
        row_ids = df.index.to_numpy()
        share = reuse if reuse is not None and reuse.matches(df) else None
        text = share.text if share is not None else TokenTable.build(df["mdc_norm"])
        glyph: TokenTable | None
        if "hieroglyphs_norm" in df.columns:
            glyph = (
                share.glyph
                if share is not None and share.glyph is not None
                else TokenTable.build(df["hieroglyphs_norm"], encode_groups=True)
            )
        else:
            glyph = None
        corpus_size = len(df)
        return cls(
            row_ids=row_ids,
            text=text,
            text_weights=TokenWeights.build(text, mdc_frequencies, corpus_size),
            glyph=glyph,
            glyph_weights=(
                TokenWeights.build(glyph, glyph_frequencies, corpus_size)
                if glyph is not None
                else None
            ),
        )
