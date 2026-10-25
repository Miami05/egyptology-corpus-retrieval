"""Eval-time twin guards shared by the evaluation scripts (audit findings A4, A55, A56).

The benchmark builder only refuses targets whose closest twin is at Jaccard 0.9 or
more, and only the target row itself is removed from the pool at eval time. Another
edition of the same sentence (overlap 0.7 to 0.9, or the same reading in another
notation) therefore stays in the pool and hands the expected reading over for free.
These helpers find *every* such row so an eval can remove them as well.

Everything here is a pure function over token sets and DataFrames; nothing runs at
import time. The token definition is the builder's own (`loose_reading_form`, then
whitespace split) and the candidate search is its exact prefix filter with no postings
cap, so the counts agree with `build_competitive_ambiguity_benchmark`.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.suggestions import loose_reading_form, notation_folded_reading_key
from scripts.build_competitive_ambiguity_benchmark import (
    _token_set,
    build_token_index,
    twin_probe_count,
)

# The audit's twin line: another edition of the same sentence starts around here.
DEFAULT_TWIN_THRESHOLD = 0.7


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def corpus_token_sets(df: pd.DataFrame) -> list[set[str]]:
    """One token set per corpus row, positionally aligned with `df`."""
    return [_token_set(loose_reading_form(value)) for value in df["transliteration_gold"]]


def corpus_token_lists(df: pd.DataFrame) -> list[list[str]]:
    """One token LIST per corpus row (repeats kept), positionally aligned with `df`.

    The same tokens as `corpus_token_sets`; the list form is what a term-frequency
    ranker (the BM25 baseline, audit A23) needs.
    """
    return [
        [token for token in loose_reading_form(value).split() if token.strip()]
        for value in df["transliteration_gold"]
    ]


def twin_rows(
    target_tokens: set[str],
    token_sets: list[set[str]],
    token_index: dict[str, list[int]],
    threshold: float,
) -> list[tuple[int, float]]:
    """Every row position whose Jaccard with `target_tokens` is >= `threshold`.

    Exhaustive without scanning the corpus: a row at Jaccard >= t must contain one of
    the target's floor((1-t)*|A|)+1 rarest tokens (see `exhaustive_best_twin_overlap`,
    which only keeps the best score; this returns all of them). Positions are
    returned sorted, and the target's own position is NOT removed here (the caller
    knows which positions are the target).
    """
    if not target_tokens:
        return []
    by_rarity = sorted(target_tokens, key=lambda token: len(token_index.get(token, ())))
    candidates: set[int] = set()
    for token in by_rarity[: twin_probe_count(len(target_tokens), threshold)]:
        candidates.update(token_index.get(token, ()))
    found: list[tuple[int, float]] = []
    for other in candidates:
        other_tokens = token_sets[other]
        shared = len(target_tokens & other_tokens)
        if not shared:
            continue
        score = shared / len(target_tokens | other_tokens)
        if score >= threshold:
            found.append((other, score))
    found.sort()
    return found


def folded_keys(df: pd.DataFrame) -> list[str]:
    """`notation_folded_reading_key` of every corpus row's reading, positionally."""
    return [notation_folded_reading_key(value) for value in df["transliteration_gold"]]


def folded_key_groups(keys: list[str]) -> dict[str, list[int]]:
    """Folded reading key -> row positions. Rows with an empty key are left out."""
    groups: dict[str, list[int]] = defaultdict(list)
    for position, key in enumerate(keys):
        if key:
            groups[key].append(position)
    return groups


def key_positions(df: pd.DataFrame) -> dict[tuple[str, str], list[int]]:
    """(source_text_id, source_sentence_id) -> row positions, as the eval matches them."""
    out: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, key in enumerate(
        zip(df["source_text_id"].astype(str), df["source_sentence_id"].astype(str))
    ):
        out[key].append(position)
    return out


class TwinGuard:
    """Corpus-wide structures for twin lookup, built once per eval run (about 4 s)."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.token_lists = corpus_token_lists(df)
        self.token_sets = [set(tokens) for tokens in self.token_lists]
        self.token_index = build_token_index(self.token_sets)
        self.keys = folded_keys(df)
        self.folded_groups = folded_key_groups(self.keys)
        self.positions = key_positions(df)

    def target_positions(self, bench_row: pd.Series) -> list[int]:
        return list(
            self.positions.get(
                (
                    str(bench_row["expected_source_text_id"]),
                    str(bench_row["expected_source_sentence_id"]),
                ),
                (),
            )
        )

    def twins(
        self, bench_row: pd.Series, threshold: float = DEFAULT_TWIN_THRESHOLD
    ) -> list[tuple[int, float, bool]]:
        """(position, Jaccard, folded-identical) for every twin of the target row.

        A twin is a row that is not the target but has Jaccard >= `threshold` with
        it, or the same notation-folded reading. Target tokens come from the corpus
        row; `expected_key_tokens` is only the fallback when the row is absent.
        """
        return twins_of_target(self, bench_row, threshold)


def twins_of_target(
    guard: TwinGuard, bench_row: pd.Series, threshold: float = DEFAULT_TWIN_THRESHOLD
) -> list[tuple[int, float, bool]]:
    target_positions = guard.target_positions(bench_row)
    target_set = set(target_positions)
    if target_positions:
        target_tokens = guard.token_sets[target_positions[0]]
        target_keys = {guard.keys[p] for p in target_positions if guard.keys[p]}
    else:
        target_tokens = {
            token for token in str(bench_row.get("expected_key_tokens", "")).split() if token
        }
        target_keys = set()
        expected = str(bench_row.get("expected_transliteration", ""))
        if expected.strip():
            target_keys.add(notation_folded_reading_key(expected))
        target_keys.discard("")

    scores: dict[int, float] = {}
    for position, score in twin_rows(
        target_tokens, guard.token_sets, guard.token_index, threshold
    ):
        if position not in target_set:
            scores[position] = score
    folded: set[int] = set()
    for key in target_keys:
        for position in guard.folded_groups.get(key, ()):
            if position not in target_set:
                folded.add(position)
                scores.setdefault(
                    position, jaccard(target_tokens, guard.token_sets[position])
                )
    return [
        (position, scores[position], position in folded) for position in sorted(scores)
    ]


# ---------------------------------------------------------------------------
# Text identity for text-level splits (audit A56).
#
# A held-out sentence whose sibling sentences from the same text sit in training is
# not held out in the sense that matters: names, formulae and spellings recur inside a
# text. Only some sources carry a trustworthy text identity:
#
#   AES     source_ref holds the real text id (`...#text=<id>&sentence=<id>`; 696
#           texts over 9,823 aligned sentences on 2026-10-25).
#   Ramses  every row has its own hashed source_text_id, but source_ref names
#           Rosmorduc's official split (`ramses-trl <date> train|val|test line N`),
#           which is the split the audit asks for.
#   TLA     source_text_id is per sentence (TLA_EARLIER_001, ...): no text identity.
#   BBAW    one source_text_id (`bbaw_egyptian_2018`) for every row: no text identity.
#
# Rows without a text identity fall back to the sentence as its own group, which is
# exactly the old sentence-level split. That is a stated limitation, not a fix;
# `SENTENCE_LEVEL_SOURCES` lets the evals print it.
# ---------------------------------------------------------------------------

AES_TEXT_RE = re.compile(r"[#&]text=([^&#\s]+)")
RAMSES_SPLIT_RE = re.compile(r"^ramses-trl\s+\S+\s+(train|val|test)\s+line\s+\d+")
SENTENCE_LEVEL_SOURCES = ("TLA", "BBAW")


def _column(df: pd.DataFrame, name: str) -> list[str]:
    if name not in df.columns:
        return [""] * len(df)
    return ["" if pd.isna(value) else str(value) for value in df[name]]


def text_group_keys(df: pd.DataFrame) -> list[str]:
    """A text-identity key per row, positionally: rows sharing a key are one text.

    AES rows use the text id from source_ref. Every other row, and an AES row whose
    source_ref has no text id, is its own group, keyed by source, text id and sentence
    id. Ramses' official split is not a grouping; `ramses_official_split` reads it.
    """
    keys: list[str] = []
    for label, source, text_id, sentence_id, ref in zip(
        df.index,
        _column(df, "source"),
        _column(df, "source_text_id"),
        _column(df, "source_sentence_id"),
        _column(df, "source_ref"),
    ):
        match = AES_TEXT_RE.search(ref) if source == "AES" else None
        if match:
            keys.append(f"AES:text:{match.group(1)}")
        elif text_id or sentence_id:
            keys.append(f"{source}:sentence:{text_id}:{sentence_id}")
        else:
            # No ids at all (synthetic frames): the row, by its index label so the key
            # survives slicing into train and test, is its own group.
            keys.append(f"{source}:row:{label}")
    return keys


def ramses_official_split(source: object, source_ref: object) -> "str | None":
    """'train', 'val' or 'test' for a Ramses row whose source_ref names it, else None."""
    if str(source) != "Ramses":
        return None
    match = RAMSES_SPLIT_RE.match(str(source_ref or ""))
    return match.group(1) if match else None


def text_level_test_mask(df: pd.DataFrame, test_fraction: float) -> list[bool]:
    """Which rows of `df` are held out under the text-level split (True = test).

    * A Ramses row that names an official split is test iff that split is `test`
      (`train` and `val` train), so Rosmorduc's split is used as published.
    * Every other row: its text group (`text_group_keys`) is held out when the group's
      ordinal, in order of first appearance, is a multiple of int(1 / test_fraction).
      A whole group always lands on one side.

    When every group is a single sentence and no row names a Ramses split, this is
    exactly the old `iloc[::k]` split, so TLA and BBAW are held out as before.
    """
    step = int(1 / test_fraction)
    ordinals: dict[str, int] = {}
    mask: list[bool] = []
    for key, source, ref in zip(
        text_group_keys(df), _column(df, "source"), _column(df, "source_ref")
    ):
        official = ramses_official_split(source, ref)
        if official is not None:
            mask.append(official == "test")
            continue
        if key not in ordinals:
            ordinals[key] = len(ordinals)
        mask.append(ordinals[key] % step == 0)
    return mask


def assert_text_groups_disjoint(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Raise ValueError when any text group has sentences on both sides of a split."""
    shared = set(text_group_keys(train)) & set(text_group_keys(test))
    if shared:
        raise ValueError(
            f"{len(shared)} text group(s) are in both train and test, "
            f"e.g. {sorted(shared)[0]}"
        )
