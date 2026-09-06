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

from app.data.normalizer import normalize_hieroglyphs, quadrat_hints
from app.services.boundary_model import BoundaryModel, fit_boundary_model
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
    # Pseudo-count for a group attested only in the external lexicon (never in this
    # corpus). It must sit BELOW the singleton discount: at 0.39 a lexicon group
    # outbid the corpus's own three-way split of Camilla's Urk. IV line
    # (𓆓𓂧 𓀀 𓈖 = ḏd =ꞽ n, attested thousands of times) with the Ramses-normalised
    # merge ḏd(.t).n, and the expert-paste gate fell to 7/8. Swept 2026-09-01 on 288
    # held-out sentences (31,565-row corpus) with the gate as a hard constraint:
    #
    #   weight   unspaced F1 / exact   scrambled F1 / exact   Urk. IV gate
    #   none        0.854 / 0.309         0.862 / 0.316         8/8
    #   0.39        0.931 / 0.590         0.943 / 0.628         7/8  <- fails
    #   0.2         0.931 / 0.590         0.944 / 0.635         8/8  <- chosen
    #   0.1         0.929 / 0.569         0.941 / 0.615         8/8
    #   0.05        0.928 / 0.552         0.940 / 0.597         8/8
    #   0.02        0.927 / 0.549         0.938 / 0.576         8/8
    lexicon_weight: float = 0.2
    # Penalty per boundary the segmentation places at a position the paste's own
    # layout controls (U+13430-1345F, read by `normalizer.quadrat_hints`) say is
    # inside one quadrat (nats). The corpus carries no controls at all, so this
    # weight only ever fires on a paste from a layout-aware editor; every benchmark
    # here is unaffected by construction.
    #
    # Swept 2026-09-06 (item B) on 11,386 raw BBAW rows whose Manuel de Codage glyph
    # field marks its own quadrats, controls synthesised from `:`/`*`, memorisation
    # guard applied, seed 7, dev/test 50/50
    # (scripts/run_format_hint_eval_bbaw.py). Boundary scores on the unspaced input:
    #
    #   weight   dev F1 / exact   test F1 / exact   expert paste gate
    #   0 (off)   0.781 / 0.547     0.784 / 0.541     8/8
    #   0.25      0.941 / 0.639     0.938 / 0.625     8/8
    #   0.5       0.941 / 0.642     0.938 / 0.628     8/8
    #   1.0       0.943 / 0.645     0.940 / 0.631     8/8  <- chosen
    #   2.0       0.949 / 0.654     0.945 / 0.643     7/8  <- fails PASTE_005
    #
    # 2.0 has the best dev F1 and is rejected by the hard constraint: PASTE_005 joins
    # every sign of each wrongly chunked piece, so at 2.0 the quadrat structure
    # outvotes the corpus evidence (𓆑 → =f, 3,878/3,907) and the paste is read as one
    # long group. 1.0 is the highest constant that keeps the gate at 8/8.
    #
    # On real RES-derived input — 1,701 St Andrews lines, reading measured end to end
    # (scripts/run_format_hint_eval_standrews.py) — 1.0 buys token F1 0.587 -> 0.591
    # unspaced (+0.0046, 195 lines better / 69 worse) and 0.577 -> 0.581 as rendered
    # (+0.0038, 178 / 56). Small, positive, and in the pre-registered direction.
    quadrat_crossed: float = 1.0
    # λ_b — weight of the adjacent-glyph boundary bigram (app.services.boundary_model),
    # the term that gives the lattice an opinion about a group it has never seen.
    # Scored exactly under the semi-Markov DP: at every placed boundary
    # log P(boundary | s_{i-1}, s_i), and at every position *inside* a chosen span
    # log P(no boundary | s_{k-1}, s_k). At 0.0 no boundary model is built at all and
    # the objective is bit-for-bit the pre-item-C one (tests/test_boundary_model.py
    # proves it on 500 scrambled corpus rows).
    #
    # Swept 2026-09-06 (item C1) on the pre-registered {0.25, 0.5, 1.0, 2.0}. Dev =
    # the last 10% of the shuffled training split (4,746 sentences after twins),
    # fitted on the first 90%; the test split was not looked at during selection.
    # Boundary scores on the unspaced input, expert paste gate as the hard constraint:
    #
    #   weight   dev F1 / exact   expert paste gate
    #   0 (off)   0.921 / 0.548    8/8
    #   0.25      0.928 / 0.560    8/8
    #   0.5       0.932 / 0.572    8/8
    #   1.0       0.937 / 0.582    8/8  <- chosen (best dev F1, gate intact)
    #   2.0       0.936 / 0.576    7/8  <- fails PASTE_005
    #
    # 1.0 is both the dev argmax and the largest candidate that keeps the gate, so the
    # constraint and the criterion agree here; 2.0 is already past the dev peak and
    # would have been rejected either way. Its failure is the same shape as item B's
    # at 2.0: the boundary bigram outvotes the corpus evidence on PASTE_005 and reads
    # 𓈖𓏏𓈖𓏥 as the once-attested "(ꞽ)ntn" instead of the 3,039x + 19x split "n =tn".
    #
    # Held-out test at 1.0 (5,298 sentences, the same split every earlier number in
    # this file used): unspaced F1 0.923 -> 0.939, exact 0.539 -> 0.579; scrambled
    # 0.937 -> 0.946, exact 0.599 -> 0.635. Ablation at the same weight with the
    # function-class back-off removed (sign bigram alone, unseen pair -> the global
    # prior): unspaced 0.938 / 0.578, scrambled 0.946 / 0.635 — so of the +0.016 F1
    # the adjacent-sign bigram contributes +0.015 and the sign-function table +0.001.
    # On real RES-derived input (1,701 St Andrews lines, reading measured end to end)
    # unspaced token F1 rises 0.591 -> 0.603.
    boundary_model: float = 1.0

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
    # Positions the paste's layout controls said were inside one quadrat and the
    # segmentation cut at anyway — the reverse of `crossed_hints`, and the places
    # where the corpus evidence outvoted the quadrat structure.
    crossed_quadrats: list[int] = field(default_factory=list)

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
        use_lexicon: bool = True,
        boundary_model: BoundaryModel | None = None,
        boundary_class_backoff: bool = True,
    ) -> None:
        self.model = model
        self.weights = weights
        self.max_group_glyphs = max_group_glyphs
        self.group_counts: Counter[str] = Counter(
            {group: sum(readings.values()) for group, readings in model.sign_reading.items()}
        )
        # A group the external lexicon attests is a legitimate span to cut at, even
        # though this corpus never saw it. It is kept apart from the corpus counts and
        # enters the unigram model at `weights.lexicon_weight`, below a corpus
        # singleton: the lexicon's own frequencies come from corpora of a different
        # size and period and would swamp a model estimated from our own tokens, and
        # even parity with a singleton proved too strong (see SegmentationWeights).
        self.lexicon_groups: set[str] = (
            {group for group in model.lexicon if group not in self.group_counts}
            if use_lexicon
            else set()
        )
        self.total = sum(self.group_counts.values())
        self.vocabulary = len(self.group_counts) + len(self.lexicon_groups)
        self._log_prob_cache: dict[str, float] = {}
        # Built only when the term is switched on, so a default segmenter costs
        # exactly what it cost before item C and behaves identically.
        self.boundary_model: BoundaryModel | None = boundary_model
        if self.weights.boundary_model and self.boundary_model is None:
            self.boundary_model = fit_boundary_model(
                model, use_class_backoff=boundary_class_backoff
            )

    def is_known(self, group: str) -> bool:
        """Attested in this corpus or in the lexicon — i.e. a span worth proposing."""
        return group in self.group_counts or group in self.lexicon_groups

    # ---------- unigram group model ----------

    def log_prob(self, group: str) -> float | None:
        """log P(group) under the discounted unigram model; None when unattested."""
        cached = self._log_prob_cache.get(group)
        if cached is not None:
            return cached
        count = self.group_counts.get(group)
        if not count:
            if group in self.lexicon_groups:
                value = log(self.weights.lexicon_weight / (self.total + self.vocabulary))
                self._log_prob_cache[group] = value
                return value
            return None
        effective = self.weights.singleton_discount if count == 1 else float(count)
        # Vocabulary smoothing in the denominator keeps the total mass below 1 so
        # that the discounted singletons and the unattested spans share the rest.
        value = log(effective / (self.total + self.vocabulary))
        self._log_prob_cache[group] = value
        return value

    def unattested_cost(self, span: str) -> float:
        return self.weights.unattested_per_glyph * len(span)

    # ---------- boundary bigram (item C1) ----------

    def _boundary_terms(self, stream: str) -> tuple[list[float], list[float]]:
        """`(log_boundary, no_boundary_prefix)` for one stream, or `([], [])` when off.

        The empty result is the switch: every caller guards on it, so with
        `weights.boundary_model == 0.0` not one extra term is computed or added and
        the objective is the pre-item-C one exactly.
        """
        if not self.weights.boundary_model or self.boundary_model is None:
            return [], []
        log_boundary, log_no_boundary = self.boundary_model.stream_terms(stream)
        prefix = [0.0] * (len(stream) + 1)
        for k in range(1, len(stream)):
            prefix[k] = prefix[k - 1] + log_no_boundary[k]
        # There is no adjacency at position len(stream); carrying the last value there
        # lets the span arithmetic run without a special case at the end of a stream.
        if stream:
            prefix[len(stream)] = prefix[len(stream) - 1]
        return log_boundary, prefix

    # ---------- decoding ----------

    def segment(
        self,
        groups_as_pasted: list[str],
        no_cut: frozenset[int] | set[int] = frozenset(),
    ) -> Segmentation:
        """Best segmentation of the pasted groups, spaces treated as hints.

        `no_cut` holds boundary positions (same indexing as `glyph_stream`) that the
        paste's layout controls say sit inside one quadrat; placing a boundary at one
        costs `weights.quadrat_crossed`. The default empty set leaves the objective
        exactly as it was, so every earlier number is reproduced bit for bit.
        """
        stream, hints = glyph_stream(groups_as_pasted)
        n = len(stream)
        if n == 0:
            return Segmentation(groups=[], score=0.0)

        # best[j] = (score, start_of_last_group) for the best segmentation of
        # stream[:j]. best[0] is the empty prefix.
        best: list[tuple[float, int]] = [(float("-inf"), -1)] * (n + 1)
        best[0] = (0.0, -1)
        w = self.weights
        # λ_b term (item C1), precomputed once per stream. `no_boundary_prefix[m]` is
        # Σ_{k=1..m} log P(no boundary | stream[k-1], stream[k]), so the internal
        # positions of the span [i, j) cost prefix[j-1] - prefix[i] — exact under the
        # semi-Markov DP, no approximation. Empty when the term is off.
        log_boundary, no_boundary_prefix = self._boundary_terms(stream)
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
                # A boundary at i cuts a quadrat when the layout controls joined the
                # signs either side of i. i == 0 is the start of the stream, not a cut.
                cut_quadrat = 1 if (i > 0 and i in no_cut) else 0
                score = (
                    prefix_score
                    + group_score
                    + w.hint_kept * kept
                    - w.hint_crossed * crossed
                    - w.quadrat_crossed * cut_quadrat
                )
                if log_boundary:
                    score += w.boundary_model * (
                        (log_boundary[i] if i > 0 else 0.0)
                        + no_boundary_prefix[j - 1]
                        - no_boundary_prefix[i]
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
        unattested = [g for g in groups if not self.is_known(g)]
        return Segmentation(
            groups=groups,
            score=best[n][0],
            crossed_hints=crossed,
            inserted_boundaries=inserted,
            unattested_groups=unattested,
            crossed_quadrats=sorted(boundaries & set(no_cut)),
        )

    def score_segmentation(
        self,
        groups: list[str],
        hints: set[int],
        no_cut: frozenset[int] | set[int] = frozenset(),
    ) -> float:
        """Score an arbitrary segmentation with the same objective, for comparison
        (e.g. the user's own spacing against the suggested one)."""
        w = self.weights
        total = 0.0
        position = 0
        log_boundary, no_boundary_prefix = self._boundary_terms("".join(groups))
        for index, group in enumerate(groups):
            start = position
            end = position + len(group)
            group_score = self.log_prob(group)
            if group_score is None:
                group_score = -self.unattested_cost(group)
            crossed = sum(1 for b in hints if start < b < end)
            kept = 1 if (index > 0 and start in hints) else 0
            cut_quadrat = 1 if (index > 0 and start in no_cut) else 0
            total += (
                group_score
                + w.hint_kept * kept
                - w.hint_crossed * crossed
                - w.quadrat_crossed * cut_quadrat
            )
            if log_boundary and group:
                total += w.boundary_model * (
                    (log_boundary[start] if start > 0 else 0.0)
                    + no_boundary_prefix[end - 1]
                    - no_boundary_prefix[start]
                )
            position = end
        return total


def segment_paste(
    query: str,
    segmenter: Segmenter,
    use_format_hints: bool = True,
) -> tuple[Segmentation, list[str]]:
    """Normalise a raw paste and segment it — the one path every caller uses.

    Returns `(segmentation, groups_as_pasted)`. With `use_format_hints` the paste's
    layout controls are read by `normalizer.quadrat_hints` first and handed to the
    segmenter as `no_cut` positions; without it the controls are simply deleted, which
    is what every caller did before item B. Either way `groups_as_pasted` is exactly
    `normalize_hieroglyphs(query).split()`.
    """
    if use_format_hints:
        groups, no_cut = quadrat_hints(query)
        return segmenter.segment(groups, no_cut=no_cut), groups
    groups = normalize_hieroglyphs(query).split()
    return segmenter.segment(groups), groups


def resegment(
    model: ReadingModel,
    groups_as_pasted: list[str],
    weights: SegmentationWeights = DEFAULT_SEGMENTATION_WEIGHTS,
) -> Segmentation:
    """Convenience wrapper: build a Segmenter and segment once."""
    return Segmenter(model, weights).segment(groups_as_pasted)
