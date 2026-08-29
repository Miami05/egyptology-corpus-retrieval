"""Resegment a pasted sign string into corpus-attested sign groups.

Why this exists. The corpus separates sign groups with spaces and those groups align
one-to-one with transliteration tokens, so the reading model works group by group.
Until now the *user's* spaces were taken as that segmentation. A copy-paste from a
PDF or a sign editor carries whatever spacing the layout happened to have, and the
first expert trial showed what follows: a suffix pronoun glued to the wrong word, a
classifier detached from its noun, and readings chosen for groups that never existed.

What it does. The query is treated as a stream of glyphs, and the spaces as *hints*.
A dynamic programme (semi-Markov Viterbi over spans) chooses the segmentation that
maximises

    Σ over groups  log P(group)        a unigram model of attested sign groups
  + β · (hinted boundaries kept)       the user's spaces, as weak evidence
  − γ · (hinted boundaries crossed)
  − κ · (glyphs in unattested spans)   an unattested span is allowed but costly

with one design decision that the audit of this project identified as decisive:

    P(group) is count-weighted with a Good-Turing discount for rare groups.

The corpus is formulaic and two thirds of its distinct sign groups are attested
exactly once. If every attested group were treated as equally trustworthy, a lattice
would systematically prefer one long once-attested group over a split into two
well-attested ones — on the trial sentence it would read 𓈖𓏏𓈖𓏥 as the singleton
"(ꞽ)ntn" instead of the 3,039× + 19× split "n =tn". Discounting a count of 1 to
≈0.39 (the Good-Turing estimate on this corpus) turns that decision around, while a
genuinely long attested group still beats a three-way split of common short groups by
orders of magnitude, which is exactly what keeps the classifier 𓀀 attached to
𓂋𓍿𓀀𓏥 "rmṯ(.t)". Every weight here is measured by scripts/run_segmentation_eval.py
on held-out corpus sentences whose spacing was removed or scrambled; the numbers in
`DEFAULT_SEGMENTATION_WEIGHTS` are the ones that measured best.

The segmenter does not read the groups. It hands the chosen groups to
ReadingModel.predict_sequence, which is unchanged, so the two stages stay inspectable
on their own.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import log

from app.services.reading_model import ReadingModel

# Groups longer than this are never proposed by the segmenter (they may still be
# pasted with explicit spaces). 10 glyphs covers 99.8% of corpus group tokens; the
# longest attested group is 27 glyphs and there are 20 groups above 14.
MAX_GROUP_GLYPHS = 10


@dataclass(frozen=True)
class SegmentationWeights:
    # Bonus per user-hinted boundary the segmentation keeps (nats).
    hint_kept: float = 0.5
    # Penalty per user-hinted boundary the segmentation merges across (nats).
    hint_crossed: float = 1.0
    # Penalty per glyph inside a span that is not an attested group (nats). Measured
    # on 845 held-out sentences (scripts/run_segmentation_eval.py, 2026-08-29):
    #
    #   penalty   unspaced F1 / exact   scrambled F1 / exact
    #      3         0.630 / 0.097         0.817 / 0.228   (keeps novel spans whole)
    #      4         0.805 / 0.244         0.853 / 0.297
    #      5         0.844 / 0.289         0.863 / 0.321
    #      6         0.856 / 0.311         0.866 / 0.331   <- chosen
    #      8         0.850 / 0.306         0.851 / 0.314
    #     12         0.831 / 0.301         0.832 / 0.305   (over-splits novel spellings)
    #
    # Baseline "trust the paste's spaces" on the same scrambled input: F1 0.669,
    # exact 0.061. The singleton discount moved these aggregates by < 0.003 either
    # way; it is kept for the reason in the module docstring.
    unattested_per_glyph: float = 6.0
    # Good-Turing style discount applied to a count of exactly 1. Counts of 2 or more
    # are used as they are; see module docstring.
    singleton_discount: float = 0.39

    def replace(self, **changes: float) -> SegmentationWeights:
        return SegmentationWeights(**{**self.__dict__, **changes})


DEFAULT_SEGMENTATION_WEIGHTS = SegmentationWeights()


@dataclass
class Segmentation:
    groups: list[str]
    score: float
    # Positions (glyph indices) where the user's spacing had a boundary but the
    # segmentation merged across it, and vice versa — shown so the reader sees
    # exactly where the tool disagreed with the paste.
    crossed_hints: list[int] = field(default_factory=list)
    inserted_boundaries: list[int] = field(default_factory=list)
    unattested_groups: list[str] = field(default_factory=list)

    @property
    def changed_from_hints(self) -> bool:
        return bool(self.crossed_hints or self.inserted_boundaries)


def glyph_stream(groups_as_pasted: list[str]) -> tuple[str, set[int]]:
    """Flatten user groups into one glyph string plus the set of hinted boundaries.

    A boundary index b means "a group ends before glyph b". Boundaries at 0 and at
    the end are implicit and never counted as hints.
    """
    stream = "".join(groups_as_pasted)
    hints: set[int] = set()
    position = 0
    for group in groups_as_pasted[:-1]:
        position += len(group)
        if 0 < position < len(stream):
            hints.add(position)
    return stream, hints


class Segmenter:
    """Count-weighted lattice over attested sign groups."""

    def __init__(
        self,
        model: ReadingModel,
        weights: SegmentationWeights = DEFAULT_SEGMENTATION_WEIGHTS,
        max_group_glyphs: int = MAX_GROUP_GLYPHS,
    ) -> None:
        self.model = model
        self.weights = weights
        self.max_group_glyphs = max_group_glyphs
        self.group_counts: Counter[str] = Counter(
            {group: sum(readings.values()) for group, readings in model.sign_reading.items()}
        )
        self.total = sum(self.group_counts.values())
        self.vocabulary = len(self.group_counts)
        self._log_prob_cache: dict[str, float] = {}

    # ---------- unigram group model ----------

    def log_prob(self, group: str) -> float | None:
        """log P(group) under the discounted unigram model; None when unattested."""
        cached = self._log_prob_cache.get(group)
        if cached is not None:
            return cached
        count = self.group_counts.get(group)
        if not count:
            return None
        effective = self.weights.singleton_discount if count == 1 else float(count)
        # Vocabulary smoothing in the denominator keeps the total mass below 1 so
        # that the discounted singletons and the unattested spans share the rest.
        value = log(effective / (self.total + self.vocabulary))
        self._log_prob_cache[group] = value
        return value

    def unattested_cost(self, span: str) -> float:
        return self.weights.unattested_per_glyph * len(span)

    # ---------- decoding ----------

    def segment(self, groups_as_pasted: list[str]) -> Segmentation:
        """Best segmentation of the pasted groups, spaces treated as hints."""
        stream, hints = glyph_stream(groups_as_pasted)
        n = len(stream)
        if n == 0:
            return Segmentation(groups=[], score=0.0)

        # best[j] = (score, start_of_last_group) for the best segmentation of
        # stream[:j]. best[0] is the empty prefix.
        best: list[tuple[float, int]] = [(float("-inf"), -1)] * (n + 1)
        best[0] = (0.0, -1)
        w = self.weights
        for j in range(1, n + 1):
            top = float("-inf")
            arg = -1
            for i in range(max(0, j - self.max_group_glyphs), j):
                prefix_score = best[i][0]
                if prefix_score == float("-inf"):
                    continue
                span = stream[i:j]
                group_score = self.log_prob(span)
                if group_score is None:
                    # Only propose an unattested span as a *whole pasted group* or a
                    # single glyph: a made-up multi-glyph span across a user boundary
                    # is not a hypothesis worth paying for.
                    if len(span) > 1 and any(i < b < j for b in hints):
                        continue
                    group_score = -self.unattested_cost(span)
                crossed = sum(1 for b in hints if i < b < j)
                # A boundary at i (start of this group) is "kept" when the user also
                # had one there; the sentence start is not a hint.
                kept = 1 if i in hints else 0
                score = (
                    prefix_score
                    + group_score
                    + w.hint_kept * kept
                    - w.hint_crossed * crossed
                )
                if score > top:
                    top = score
                    arg = i
            best[j] = (top, arg)

        # Walk back.
        groups: list[str] = []
        j = n
        boundaries: set[int] = set()
        while j > 0:
            i = best[j][1]
            groups.append(stream[i:j])
            if i > 0:
                boundaries.add(i)
            j = i
        groups.reverse()

        crossed = sorted(hints - boundaries)
        inserted = sorted(boundaries - hints)
        unattested = [g for g in groups if g not in self.group_counts]
        return Segmentation(
            groups=groups,
            score=best[n][0],
            crossed_hints=crossed,
            inserted_boundaries=inserted,
            unattested_groups=unattested,
        )

    def score_segmentation(self, groups: list[str], hints: set[int]) -> float:
        """Score an arbitrary segmentation with the same objective, for comparison
        (e.g. the user's own spacing against the suggested one)."""
        w = self.weights
        total = 0.0
        position = 0
        for index, group in enumerate(groups):
            start = position
            end = position + len(group)
            group_score = self.log_prob(group)
            if group_score is None:
                group_score = -self.unattested_cost(group)
            crossed = sum(1 for b in hints if start < b < end)
            kept = 1 if (index > 0 and start in hints) else 0
            total += group_score + w.hint_kept * kept - w.hint_crossed * crossed
            position = end
        return total


def resegment(
    model: ReadingModel,
    groups_as_pasted: list[str],
    weights: SegmentationWeights = DEFAULT_SEGMENTATION_WEIGHTS,
) -> Segmentation:
    """Convenience wrapper: build a Segmenter and segment once."""
    return Segmenter(model, weights).segment(groups_as_pasted)
