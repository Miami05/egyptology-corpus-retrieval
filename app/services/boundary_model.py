"""Where does one sign group end and the next begin? — a bigram over adjacent glyphs.

Item C1. Nederhof's third criticism of this project was that the resegmentation lattice
is a *unigram over attested groups* and knows nothing about what a sign does. The
diagnosis that followed (ROADMAP.md, item C, measured 2026-09-06) put a number on the
cost: of 7,029 spurious boundaries on held-out unspaced input, **6,351 fall inside a
gold group the training split never saw whole**. 10.7% of gold groups are unattested,
and they cause 90% of the false cuts — the unigram has no hypothesis for an unseen
word, so it cuts it into seen fragments.

A model over *adjacent glyph pairs* has the property the unigram lacks: 98.2% of the
adjacent sign pairs in held-out text were seen in training even when the group as a
whole was not. So this model asks a different question at every position of the stream:

    P(boundary | previous glyph, this glyph)

estimated from the same training sentences, with two levels of back-off.

**Level 1 — the pair itself.** For a pair seen n(a, b) times with n_b(a, b) of those at
a group boundary::

    P(boundary | a, b) = (n_b(a, b) + α · P_class(a, b)) / (n(a, b) + α)

with **α = 1, fixed and not tuned** (pre-registered). One pseudo-observation drawn from
the class model: a pair seen once moves halfway from the class prediction to its own
evidence, a pair seen a thousand times is its own evidence.

**Level 2 — the sign's function class.** An unseen pair has no counts, so it falls back
to what the two signs *are*, from `app.services.sign_functions`::

    P_class(a, b) = Σ_c1 Σ_c2  P(c1 | a) · P(c2 | b) · P(boundary | c1, c2)

`P(c | sign)` is uniform over the sign's folded class set (the tables carry no
frequencies), so the class assignment is soft: only 14.9% of corpus sign tokens have a
single function class, and forcing a choice would invent precision the table does not
have. `P(boundary | c1, c2)` is estimated from *expected* counts under that same soft
assignment, smoothed by 0.5 toward the global boundary rate.

**Level 3** is the global rate itself, which is what a pair of two `unk` signs
effectively gets.

Nothing here is fitted to a decision. The only free parameter is the weight the lattice
gives the whole term (`SegmentationWeights.boundary_model`), swept once on a dev split
carved out of the training data; see that field's comment for the table.

The statistics come from a fitted `ReadingModel`, not from a DataFrame, so any caller
that can build a `Segmenter` can build this too. They are the same counts: a group's
token count gives its internal (no-boundary) adjacencies, and `ReadingModel.
sign_context`, whose keys are (previous group, group) pairs, gives the boundary ones.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import log
from typing import TYPE_CHECKING

from app.services.sign_functions import SignFunctions, load_sign_functions

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.services.reading_model import ReadingModel

#: Pseudo-count mixing the class prediction into a seen pair. Pre-registered as
#: fixed; it is not swept anywhere in this project.
ALPHA = 1.0

#: Additive smoothing of each class-pair rate toward the global boundary rate.
CLASS_SMOOTHING = 0.5

#: Clamp so a probability of exactly 0 or 1 never produces -inf in the lattice. Both
#: ends are reachable: a class pair that never once carried a boundary in 50k
#: sentences is not evidence that it *cannot*.
_EPSILON = 1e-9


@dataclass
class BoundaryModel:
    """P(boundary | previous glyph, this glyph), with function-class back-off."""

    #: (a, b) -> boundary count in the training stream.
    pair_boundary: dict[tuple[str, str], float] = field(default_factory=dict)
    #: (a, b) -> total adjacency count in the training stream.
    pair_total: dict[tuple[str, str], float] = field(default_factory=dict)
    #: (c1, c2) -> P(boundary | c1, c2), from expected counts.
    class_boundary_rate: dict[tuple[str, str], float] = field(default_factory=dict)
    #: Global P(boundary) over all adjacent positions.
    prior: float = 0.5
    #: When False the class level is skipped entirely and an unseen pair gets the
    #: global prior — the pre-registered C1 ablation, isolating what the function
    #: table itself contributed over a bare sign bigram.
    use_class_backoff: bool = True
    functions: SignFunctions = field(default_factory=SignFunctions)

    _cache: dict[tuple[str, str], float] = field(default_factory=dict, repr=False)

    # ---------- estimation ----------

    def class_probability(self, a: str, b: str) -> float:
        """`P_class(a, b)` — the class-model prediction, before any pair counts."""
        if not self.use_class_backoff:
            return self.prior
        left = self.functions.class_distribution(a)
        right = self.functions.class_distribution(b)
        total = 0.0
        for c1, p1 in left.items():
            for c2, p2 in right.items():
                total += p1 * p2 * self.class_boundary_rate.get((c1, c2), self.prior)
        return total

    def boundary_probability(self, a: str, b: str) -> float:
        """`P(boundary | a, b)`, in (0, 1)."""
        cached = self._cache.get((a, b))
        if cached is not None:
            return cached
        backoff = self.class_probability(a, b)
        total = self.pair_total.get((a, b), 0.0)
        if total:
            value = (self.pair_boundary.get((a, b), 0.0) + ALPHA * backoff) / (
                total + ALPHA
            )
        else:
            value = backoff
        value = min(max(value, _EPSILON), 1.0 - _EPSILON)
        self._cache[(a, b)] = value
        return value

    def log_boundary(self, a: str, b: str) -> float:
        return log(self.boundary_probability(a, b))

    def log_no_boundary(self, a: str, b: str) -> float:
        return log(1.0 - self.boundary_probability(a, b))

    # ---------- one stream, scored ----------

    def stream_terms(self, stream: str) -> tuple[list[float], list[float]]:
        """Per-position `log P(boundary)` and `log P(no boundary)` for one glyph stream.

        Index k (1 <= k < len(stream)) is the position *before* `stream[k]`, the same
        indexing `segmentation.glyph_stream` uses for hints. Index 0 is unused and
        holds 0.0 so the lists line up with the stream.
        """
        boundary = [0.0] * len(stream)
        no_boundary = [0.0] * len(stream)
        for k in range(1, len(stream)):
            probability = self.boundary_probability(stream[k - 1], stream[k])
            boundary[k] = log(probability)
            no_boundary[k] = log(1.0 - probability)
        return boundary, no_boundary


def fit_boundary_model(
    model: ReadingModel,
    functions: SignFunctions | None = None,
    use_class_backoff: bool = True,
) -> BoundaryModel:
    """Estimate the boundary statistics from a fitted `ReadingModel`.

    Two sources, both the same training sentences the reading model saw:

    * **no-boundary** adjacencies, from the group token counts — a group `g` attested
      `n` times contributes `n` to every internal pair `(g[k-1], g[k])`;
    * **boundary** adjacencies, from `sign_context`, whose keys are (previous group,
      group) pairs — the pair `(previous[-1], group[0])` sat across a real boundary.
      Keys whose previous group is the sentence-start marker are skipped: there is no
      preceding glyph there, and a sentence start is not a boundary the segmenter can
      place.
    """
    from app.services.reading_model import BOUNDARY as SENTENCE_START

    functions = functions if functions is not None else load_sign_functions()
    boundary_model = BoundaryModel(
        use_class_backoff=use_class_backoff, functions=functions
    )

    pair_boundary: dict[tuple[str, str], float] = defaultdict(float)
    pair_no_boundary: dict[tuple[str, str], float] = defaultdict(float)

    for group, readings in model.sign_reading.items():
        count = float(sum(readings.values()))
        if not count:
            continue
        for k in range(1, len(group)):
            pair_no_boundary[(group[k - 1], group[k])] += count

    for (previous_group, group), readings in model.sign_context.items():
        if previous_group == SENTENCE_START or not previous_group or not group:
            continue
        count = float(sum(readings.values()))
        if not count:
            continue
        pair_boundary[(previous_group[-1], group[0])] += count

    total_boundary = sum(pair_boundary.values())
    total_no_boundary = sum(pair_no_boundary.values())
    total = total_boundary + total_no_boundary
    boundary_model.prior = (total_boundary / total) if total else 0.5

    # Expected class-pair counts under the soft assignment P(c | sign).
    class_boundary: dict[tuple[str, str], float] = defaultdict(float)
    class_total: dict[tuple[str, str], float] = defaultdict(float)
    distributions: dict[str, dict[str, float]] = {}

    def distribution(sign: str) -> dict[str, float]:
        cached = distributions.get(sign)
        if cached is None:
            cached = functions.class_distribution(sign)
            distributions[sign] = cached
        return cached

    for counts, is_boundary in ((pair_boundary, True), (pair_no_boundary, False)):
        for (a, b), count in counts.items():
            for c1, p1 in distribution(a).items():
                for c2, p2 in distribution(b).items():
                    weight = p1 * p2 * count
                    class_total[(c1, c2)] += weight
                    if is_boundary:
                        class_boundary[(c1, c2)] += weight

    prior = boundary_model.prior
    boundary_model.class_boundary_rate = {
        pair: (class_boundary.get(pair, 0.0) + CLASS_SMOOTHING * prior)
        / (denominator + CLASS_SMOOTHING)
        for pair, denominator in class_total.items()
    }

    for pair, count in pair_boundary.items():
        boundary_model.pair_boundary[pair] = count
    for counts in (pair_boundary, pair_no_boundary):
        for pair, count in counts.items():
            boundary_model.pair_total[pair] = boundary_model.pair_total.get(pair, 0.0) + count

    return boundary_model
