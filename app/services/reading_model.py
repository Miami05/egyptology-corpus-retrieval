"""Predict the reading of each sign from context, rather than by sentence similarity.

Why a second approach. Sentence retrieval answers "which corpus sentences look like
this one", which only helps when a close parallel exists. Camilla's objection is
narrower and harder: a sign has several possible readings, so *which reading applies
here*. That is a sequence-labelling problem over signs, not a document-similarity
problem, and it is what this module models.

The model is deliberately simple and inspectable, because an Egyptologist has to be
able to see why a reading was chosen:

    score(reading | sign, context) =
        log P(reading | sign)                     how often this sign is read this way
      + log P(reading | previous reading)         how readings follow one another
      + log P(reading | previous sign)            left sign context
      + log P(reading | following sign)           right sign context

Decoding runs Viterbi over the candidate readings of each sign, so the chosen sequence
is jointly best rather than a chain of independent guesses. Every probability is a
smoothed count from real corpus sentences — nothing is generated.

Two measured notes, kept here so the code is not read more optimistically than the
evidence supports:

* The right sign context was added on the reasoning that Egyptian determinatives follow
  the phonetic signs, so they should be informative. Measured on held-out sentences its
  gain is within noise (+0.000 to +0.005 on ambiguous signs across six corpus sizes).
  The reason is that Viterbi already propagates information from the right through the
  reading-bigram chain, so the term is largely redundant. It is kept because it is
  cheap, tested, and may matter on a corpus with sparser reading sequences — but it
  should not be described as a source of the model's accuracy.
* An unattested sign group can borrow the readings of the closest attested group
  (`use_fallback`). That lifts coverage from 84% to 99.8% of sign instances, but those
  readings are correct only about a quarter of the time, against ~89% for attested
  groups. They are always flagged as fallbacks and carry their glyph similarity, and
  they must be presented as leads rather than attestations.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import log

import pandas as pd

from app.services.composition import compose_group, composed_distribution
from app.services.sign_functions import SignFunctions, load_sign_functions

BOUNDARY = "<s>"
# Additive smoothing. Small, because most sign/reading pairs are genuinely unattested
# and we do not want to invent readings the corpus never shows.
SMOOTHING = 0.1

# Minimum glyph overlap before an unattested sign group borrows another group's
# readings. Measured precision/coverage tradeoff on 1,689 held-out sentences
# (9,567 training sentences, duplicate sign strings excluded):
#
#   threshold   fallback precision   share of all signs newly readable
#     0.34            24.9%                       15.9%
#     0.50            25.3%                       15.5%
#     0.67            32.6%                        8.3%
#     0.80            33.7%                        4.8%
#
# 0.50 keeps almost all the coverage; raising it to 0.67 buys ~8 points of precision
# for half the coverage. Fallback readings are always flagged, so the reader can judge
# them, which is why coverage is preferred here.
#
# Re-measured 2026-08-29 after the similarity became order-aware (see
# `glyph_similarity`), same protocol, 2,555 held-out sentences, duplicates excluded:
#
#   similarity        threshold   fallback precision   coverage incl. fallback
#   set Jaccard (old)   0.50            27.8%                 99.45%
#   order-aware         0.50            32.6%                 95.54%
#   order-aware         0.40            29.5%                 97.67%   <- chosen
#   order-aware         0.30            28.1%                 98.76%
#
# Order awareness buys precision only by refusing more borrowings; 0.40 takes about
# half of the gain for a third of the coverage loss. Since the resegmentation lattice
# (app.services.segmentation) now removes most spurious unattested groups before
# reading, fewer queries reach this fallback at all.
FALLBACK_THRESHOLD = 0.4

# Weight of glyph-*order* agreement in the fallback similarity. The similarity used
# to be the Jaccard overlap of glyph sets alone, which is blind to order: on the first
# expert trial the unattested f-ḏd-d borrowed the snake-word ḏd-f at 0.75 with no
# penalty for the reversed sequence. Mixing in the Jaccard overlap of adjacent-glyph
# bigrams makes a reordered group less similar than a group that merely gained or
# lost a determinative. 0.5 = equal weight; the measured effect on fallback precision
# is recorded in ROADMAP.md, Phase 1.
FALLBACK_ORDER_WEIGHT = 0.5

# Whether a group neither the corpus nor the lexicon attests is read from what its
# signs *do* (app.services.composition, item C2) before the glyph-similarity fallback
# is tried. The pre-registered rule C2.4 ships it only if composed accuracy strictly
# beats fallback accuracy on the same positions, over at least 200 of them, without
# lowering acc_ambiguous_context.
#
# NULL RESULT, 2026-09-06. Stage 1 of the amended C2 evaluation asked the prior
# question — does the composition *generate* the gold reading at all? — on the dev cut
# of the reading eval's training split (4,761 sentences, 778 positions the corpus and
# the Helsinki lexicon both fail to read). Coverage 0.6632 (516 of 778). Oracle recall
# on the covered positions, i.e. the gold reading appearing ANYWHERE among the
# candidates:
#
#   rules                                   oracle exact / lenient   top-1 exact
#   as pre-registered (amended filters)        0.0581 / 0.0930         0.0058
#   + phonetic-complement skip (rev. 1)        0.1008 / 0.1570         0.0174
#   + optional logogram (rev. 2)               0.1221 / 0.1764         0.0349
#   the same, cap raised 24 -> 500             0.1880 / 0.2655         0.0349
#
# The glyph-similarity fallback these readings would replace scores **0.2835** on the
# comparable held-out positions. An oracle over the whole candidate list tops out at
# 0.188 and the composition's own top choice is right 3.5% of the time, so no scoring
# or decoding change can close that gap: the ceiling is below the incumbent's floor.
# Stage 2 (the paired accuracy test) was therefore not run — see
# `docs/sign-function-2026-09-06.md` for why, and for what would have to change first
# (the tables give a sign's readings out of context; Egyptian orthography writes
# phonetic complements and TLA transliteration writes morphology, neither of which a
# per-sign inventory can supply).
#
# The source kind stays in the code, off, as rule C2.4 prescribes.
USE_COMPOSED_BY_DEFAULT = False


def glyph_similarity(left: str, right: str, order_weight: float | None = None) -> float:
    """Order-aware glyph overlap in [0, 1]: (1-w)·Jaccard(glyphs) + w·Jaccard(bigrams).

    Single-glyph groups have no bigrams; for them the set overlap stands alone so a
    lone sign can still borrow from a group that contains it. `order_weight` defaults
    to the module constant at call time so evaluations can vary it.
    """
    if order_weight is None:
        order_weight = FALLBACK_ORDER_WEIGHT
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    set_score = len(left_set & right_set) / len(union)
    left_bigrams = {left[i : i + 2] for i in range(len(left) - 1)}
    right_bigrams = {right[i : i + 2] for i in range(len(right) - 1)}
    bigram_union = left_bigrams | right_bigrams
    if not bigram_union:
        return set_score
    order_score = len(left_bigrams & right_bigrams) / len(bigram_union)
    return (1.0 - order_weight) * set_score + order_weight * order_score


@dataclass
class ReadingPrediction:
    sign: str
    predicted: str
    candidates: list[tuple[str, float]]
    attested_count: int
    is_ambiguous: bool
    was_seen: bool
    # Set when the sign group itself is unattested and the candidates came from the
    # most similar known group instead. Such a reading is a lead, not an attestation,
    # and the UI must not present it as though the group were observed.
    fallback_from: str = ""
    # Glyph overlap between this group and the group it borrowed from, so a reader can
    # judge how far the guess reaches.
    fallback_similarity: float = 0.0
    # Set when the corpus has never attested this group but the external sign-reading
    # lexicon has (app.services.lexicon). The reading is then an attested count from
    # another corpus — real evidence, but not a sentence we can show — and the UI
    # labels it as such. `was_seen` stays False: it was not seen *here*.
    lexicon_count: int = 0
    lexicon_source: str = ""
    # Set when neither the corpus nor the lexicon attests this group and the reading
    # was *composed* from what each of its signs does (app.services.composition,
    # item C2). Like a fallback this is a lead, not an attestation — it is counted as
    # borrowed everywhere fallbacks are counted, and the UI says it was read sign by
    # sign from the sign-function list rather than observed.
    is_composed: bool = False

    @property
    def is_fallback(self) -> bool:
        return bool(self.fallback_from)

    @property
    def is_borrowed(self) -> bool:
        """Not attested here: a borrowed reading or a composed one.

        The one predicate every caller that used to test `is_fallback` for "this is a
        guess, label it" should test, so item C2 cannot silently make a composed
        reading look attested.
        """
        return self.is_fallback or self.is_composed

    @property
    def is_lexicon(self) -> bool:
        return self.lexicon_count > 0 and not self.was_seen

    @property
    def confidence(self) -> float:
        if not self.candidates:
            return 0.0
        total = sum(score for _, score in self.candidates)
        if total <= 0:
            return 0.0
        return self.candidates[0][1] / total


@dataclass
class ReadingModel:
    """Counts of how signs are read, and how readings follow one another."""

    sign_reading: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    reading_bigram: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    sign_context: dict[tuple[str, str], Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    # Reading given the sign that FOLLOWS. Egyptian writes determinatives after the
    # phonetic signs, and it is often the determinative that fixes which word is
    # meant, so left context alone misses the most informative neighbour.
    next_sign_context: dict[tuple[str, str], Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    # Individual glyph -> the sign groups it occurs in, used to read an unattested
    # group by falling back to the closest attested one.
    glyph_to_groups: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # External spelling → reading counts (see app.services.lexicon), consulted only for
    # groups the corpus has never attested. Kept apart from `sign_reading` on purpose:
    # the corpus counts are what "attested" means everywhere else in the app, and the
    # lexicon must never make an unattested group look attested.
    lexicon: dict[str, Counter] = field(default_factory=dict)
    lexicon_sources: dict[str, str] = field(default_factory=dict)
    # Sign functions (Nederhof's table plus this project's supplement), used by
    # `compose_group` to read a group neither the corpus nor the lexicon attests.
    # Loaded lazily on first use so a model that never meets an unattested group
    # never touches the file (item C2).
    sign_functions: SignFunctions | None = None
    _composed_cache: dict[str, Counter] = field(default_factory=dict, repr=False)
    sentences_seen: int = 0
    # Rows skipped because sign groups and readings did not align. Reported, not
    # hidden: on a clean load this must be 0 (see app.data.loader.alignment_report).
    sentences_skipped: int = 0
    # Rows skipped because they have no hieroglyphs at all (BBAW text-only rows,
    # Demotic). This is an expected state, not a defect, so it is counted apart
    # from `sentences_skipped` (see app.data.loader.AlignmentReport.text_only_rows).
    sentences_text_only: int = 0

    # ---------- training ----------

    def fit(self, df: pd.DataFrame) -> ReadingModel:
        for _, row in df.iterrows():
            signs = str(row.get("hieroglyphs_norm") or "").split()
            readings = str(row.get("transliteration_gold") or "").split()
            if not signs:
                # No hieroglyphs to fit on — a text-only row, not a misalignment.
                self.sentences_text_only += 1
                continue
            if len(signs) != len(readings):
                # Without one-to-one alignment a sign cannot be paired with a
                # reading; skipping keeps the counts honest.
                self.sentences_skipped += 1
                continue
            self.sentences_seen += 1
            previous_reading = BOUNDARY
            previous_sign = BOUNDARY
            for position, (sign, reading) in enumerate(zip(signs, readings)):
                self.sign_reading[sign][reading] += 1
                self.reading_bigram[previous_reading][reading] += 1
                self.sign_context[(previous_sign, sign)][reading] += 1
                next_sign = signs[position + 1] if position + 1 < len(signs) else BOUNDARY
                self.next_sign_context[(sign, next_sign)][reading] += 1
                for glyph in sign:
                    self.glyph_to_groups[glyph].add(sign)
                previous_reading = reading
                previous_sign = sign
        return self

    def attach_lexicon(self, readings: dict[str, Counter], sources: dict[str, str] | None = None) -> ReadingModel:
        """Make an external lexicon available for groups the corpus does not attest."""
        self.lexicon = dict(readings)
        self.lexicon_sources = dict(sources or {})
        return self

    # ---------- inspection ----------

    def candidates_for(self, sign: str) -> list[tuple[str, int]]:
        return self.sign_reading.get(sign, Counter()).most_common()

    def lexicon_candidates_for(self, sign: str) -> list[tuple[str, int]]:
        return self.lexicon.get(sign, Counter()).most_common()

    def in_lexicon(self, sign: str) -> bool:
        return sign in self.lexicon and sign not in self.sign_reading

    def is_ambiguous(self, sign: str) -> bool:
        return len(self.sign_reading.get(sign, Counter())) > 1

    @property
    def ambiguous_signs(self) -> set[str]:
        return {sign for sign, c in self.sign_reading.items() if len(c) > 1}

    # ---------- scoring ----------

    def _emission(self, sign: str, reading: str) -> float:
        counts = self.sign_reading.get(sign, Counter())
        total = sum(counts.values())
        vocabulary = max(len(counts), 1)
        numerator = counts.get(reading, 0) + SMOOTHING
        return log(numerator / (total + SMOOTHING * vocabulary))

    def _lexicon_emission(self, sign: str, reading: str) -> float:
        """Same estimate as `_emission`, over the external lexicon's counts."""
        counts = self.lexicon.get(sign, Counter())
        total = sum(counts.values())
        vocabulary = max(len(counts), 1)
        numerator = counts.get(reading, 0) + SMOOTHING
        return log(numerator / (total + SMOOTHING * vocabulary))

    def _transition(self, previous_reading: str, reading: str) -> float:
        counts = self.reading_bigram.get(previous_reading, Counter())
        total = sum(counts.values())
        if total == 0:
            return log(SMOOTHING)
        vocabulary = max(len(counts), 1)
        return log((counts.get(reading, 0) + SMOOTHING) / (total + SMOOTHING * vocabulary))

    def _sign_context(self, previous_sign: str, sign: str, reading: str) -> float:
        counts = self.sign_context.get((previous_sign, sign), Counter())
        total = sum(counts.values())
        if total == 0:
            return log(SMOOTHING)
        vocabulary = max(len(counts), 1)
        return log((counts.get(reading, 0) + SMOOTHING) / (total + SMOOTHING * vocabulary))

    def _next_sign_context(self, sign: str, next_sign: str, reading: str) -> float:
        counts = self.next_sign_context.get((sign, next_sign), Counter())
        total = sum(counts.values())
        if total == 0:
            return log(SMOOTHING)
        vocabulary = max(len(counts), 1)
        return log((counts.get(reading, 0) + SMOOTHING) / (total + SMOOTHING * vocabulary))

    def related_attested_groups(
        self, sign: str, limit: int = 4, min_similarity: float = 0.15
    ) -> list[tuple[str, float, str, int]]:
        """Attested groups that share glyphs with an unattested one.

        Used for the groups the model refuses to read: below the fallback threshold
        there is not enough evidence to borrow a reading, but "unreadable" on its own
        is a dead end for a reader who wants to know *why*. This reports what the
        corpus does contain — which attested groups share these signs, how they are
        read and how often — without proposing any of them as the reading of this
        group. Returns (group, similarity, commonest reading, attestations).
        """
        if sign in self.sign_reading:
            return []
        candidates: set[str] = set()
        for glyph in set(sign):
            candidates |= self.glyph_to_groups.get(glyph, set())
        scored: list[tuple[str, float, str, int]] = []
        for candidate in sorted(candidates):
            score = glyph_similarity(sign, candidate)
            if score < min_similarity:
                continue
            counts = self.sign_reading.get(candidate, Counter())
            total = sum(counts.values())
            reading = counts.most_common(1)[0][0] if counts else ""
            scored.append((candidate, score, reading, total))
        scored.sort(key=lambda row: (-row[1], -row[3], row[0]))
        return scored[:limit]

    def composed_readings(self, sign: str) -> Counter:
        """`Counter(reading -> probability)` composed from the group's sign functions.

        Empty when the signs compose to nothing, which is the signal to fall through
        to the glyph-similarity fallback exactly as before item C2. Cached per group:
        the same unattested spelling recurs across a document, and the composition is
        a pure function of the group and the corpus counts.
        """
        cached = self._composed_cache.get(sign)
        if cached is not None:
            return cached
        if self.sign_functions is None:
            self.sign_functions = load_sign_functions()
        readings = compose_group(sign, self.sign_functions, self.sign_reading)
        distribution = composed_distribution(readings)
        self._composed_cache[sign] = distribution
        return distribution

    def nearest_known_group(self, sign: str) -> tuple[str, float]:
        """Closest attested sign group to an unattested one, by order-aware glyph overlap.

        An unseen *group* is usually made of glyphs that are individually common, so
        rather than refusing to read it we find the attested group most similar to
        it (see `glyph_similarity`). Returns ("", 0.0) when nothing shares a glyph.
        """
        if sign in self.sign_reading:
            return sign, 1.0
        glyphs = set(sign)
        if not glyphs:
            return "", 0.0
        candidates: set[str] = set()
        for glyph in glyphs:
            candidates |= self.glyph_to_groups.get(glyph, set())
        best_group = ""
        best_score = 0.0
        # Sorted so the result is deterministic: set iteration order depends on the
        # hash seed, and two equally similar, equally attested groups used to swap
        # between runs.
        for candidate in sorted(candidates):
            score = glyph_similarity(sign, candidate)
            if score <= 0.0:
                continue
            # Prefer a closer match; break ties toward the better attested group so a
            # one-off spelling does not outrank a common word.
            if score > best_score or (
                score == best_score
                and sum(self.sign_reading.get(candidate, Counter()).values())
                > sum(self.sign_reading.get(best_group, Counter()).values())
            ):
                best_score = score
                best_group = candidate
        return best_group, best_score

    # ---------- decoding ----------

    def predict_sequence(
        self,
        signs: list[str],
        emission_weight: float = 1.0,
        transition_weight: float = 0.6,
        sign_context_weight: float = 0.8,
        next_sign_weight: float = 0.8,
        use_fallback: bool = True,
        fallback_threshold: float | None = None,
        use_lexicon: bool = True,
        use_composed: bool | None = None,
    ) -> list[ReadingPrediction]:
        """Viterbi over each sign's attested readings.

        `next_sign_weight` adds the right-hand neighbour, which matters because
        Egyptian determinatives follow the phonetic signs. It depends only on the
        neighbouring *sign*, not on its reading, so it stays a local term and Viterbi
        remains exact.

        `use_fallback` lets an unattested sign group borrow the readings of the closest
        attested group. Those predictions are marked so they are never mistaken for
        attested ones; with it off, an unknown group stays unknown.

        `use_lexicon=False` ignores `self.lexicon` entirely, as if none had been
        attached — every position falls straight through to fallback/none instead.
        For item A part 3's language identification (`app.services.stage.
        choose_stage_by_likelihood`): the external lexicon is stage-agnostic, but
        `build_stage_resources` scales its *effective* weight per stage, so a
        lexicon-only group would score differently across stages for a reason that
        has nothing to do with which stage is the right one. Default `True` keeps
        every other caller's behaviour unchanged.

        `use_composed` (item C2) reads a group neither the corpus nor the lexicon
        attests from what each of its signs does, before trying the glyph-similarity
        fallback. `None` means "the shipped default", `USE_COMPOSED_BY_DEFAULT` —
        which the C2.4 decision rule sets, and which is what every caller that does
        not pass the argument gets.
        """
        predictions, _path_score = self.predict_sequence_scored(
            signs,
            emission_weight=emission_weight,
            transition_weight=transition_weight,
            sign_context_weight=sign_context_weight,
            next_sign_weight=next_sign_weight,
            use_fallback=use_fallback,
            fallback_threshold=fallback_threshold,
            use_lexicon=use_lexicon,
            use_composed=use_composed,
        )
        return predictions

    def predict_sequence_scored(
        self,
        signs: list[str],
        emission_weight: float = 1.0,
        transition_weight: float = 0.6,
        sign_context_weight: float = 0.8,
        next_sign_weight: float = 0.8,
        use_fallback: bool = True,
        fallback_threshold: float | None = None,
        use_lexicon: bool = True,
        use_composed: bool | None = None,
    ) -> tuple[list[ReadingPrediction], float]:
        """`predict_sequence`, plus the chosen path's total Viterbi log-probability.

        Same decode, same predictions — this only additionally returns the score
        `predict_sequence` already computes internally and used to discard
        (`lattice[-1][best_final][0]` below). Added for item A part 3: language
        identification by likelihood needs this total (summed emission +
        transition + context terms over the whole sequence) to compare a paste's
        best reading across stages; `predict_sequence` itself is unchanged so
        every existing caller keeps its exact behaviour. See `predict_sequence`
        for `use_lexicon`.
        """
        if not signs:
            return [], 0.0
        if fallback_threshold is None:
            fallback_threshold = FALLBACK_THRESHOLD
        if use_composed is None:
            use_composed = USE_COMPOSED_BY_DEFAULT

        # Resolve which group's statistics each position will use, in order of how
        # much the evidence is worth: attested in this corpus → attested in the
        # external lexicon → composed from the signs' own functions → borrowed from
        # the most similar attested group → nothing.
        # (group whose statistics are used, fallback origin or "", glyph similarity, kind)
        sources: list[tuple[str, str, float, str]] = []
        # position -> Counter(reading -> probability) for the composed positions.
        composed: dict[int, Counter] = {}
        for position, sign in enumerate(signs):
            if sign in self.sign_reading:
                sources.append((sign, "", 1.0, "corpus"))
                continue
            if use_lexicon and sign in self.lexicon:
                sources.append((sign, "", 1.0, "lexicon"))
                continue
            if use_composed:
                distribution = self.composed_readings(sign)
                if distribution:
                    composed[position] = distribution
                    sources.append((sign, "", 0.0, "composed"))
                    continue
            if use_fallback:
                group, score = self.nearest_known_group(sign)
                # Require real glyph overlap; a token sharing almost nothing is not
                # evidence for anything.
                if group and score >= fallback_threshold:
                    sources.append((group, group, score, "fallback"))
                else:
                    sources.append(("", "", 0.0, "none"))
            else:
                sources.append(("", "", 0.0, "none"))

        def counts_for(position: int) -> Counter:
            group, _, _, kind = sources[position]
            if kind == "composed":
                return composed[position]
            if kind == "lexicon":
                return self.lexicon.get(group, Counter())
            return self.sign_reading.get(group, Counter())

        # (score, previous_state_index) per candidate at each position.
        lattice: list[list[tuple[float, int, str]]] = []
        for position, sign in enumerate(signs):
            source_group = sources[position][0]
            options = [reading for reading, _ in counts_for(position).most_common()]
            if not options:
                options = [""]
            next_sign = signs[position + 1] if position + 1 < len(signs) else BOUNDARY
            column: list[tuple[float, int, str]] = []
            for reading in options:
                # Terms depending only on this position, not on the previous state.
                # A lexicon group has no corpus context statistics, so only its
                # emission carries information there; the context terms fall back to
                # their smoothing defaults, which is the honest amount of knowledge.
                kind = sources[position][3]
                if kind == "composed":
                    # Already a normalised distribution over the composed candidates
                    # (app.services.composition), so it is its own emission.
                    emission = log(max(composed[position].get(reading, 0.0), 1e-12))
                elif kind == "lexicon":
                    emission = self._lexicon_emission(source_group, reading)
                else:
                    emission = self._emission(source_group, reading)
                local = (
                    emission_weight * emission
                    + next_sign_weight
                    * self._next_sign_context(source_group, next_sign, reading)
                )
                if position == 0:
                    score = (
                        local
                        + transition_weight * self._transition(BOUNDARY, reading)
                        + sign_context_weight
                        * self._sign_context(BOUNDARY, source_group, reading)
                    )
                    column.append((score, -1, reading))
                else:
                    previous_sign = sources[position - 1][0] or signs[position - 1]
                    best_score = float("-inf")
                    best_index = 0
                    for index, (previous_score, _, previous_reading) in enumerate(
                        lattice[position - 1]
                    ):
                        candidate_score = (
                            previous_score
                            + local
                            + transition_weight
                            * self._transition(previous_reading, reading)
                            + sign_context_weight
                            * self._sign_context(previous_sign, source_group, reading)
                        )
                        if candidate_score > best_score:
                            best_score = candidate_score
                            best_index = index
                    column.append((best_score, best_index, reading))
            lattice.append(column)

        # Walk back from the best final state.
        best_final = max(range(len(lattice[-1])), key=lambda i: lattice[-1][i][0])
        path: list[str] = []
        index = best_final
        for position in range(len(signs) - 1, -1, -1):
            score, previous_index, reading = lattice[position][index]
            path.append(reading)
            index = previous_index if previous_index >= 0 else 0
        path.reverse()

        predictions: list[ReadingPrediction] = []
        for position, (sign, reading) in enumerate(zip(signs, path)):
            source_group, fallback_from, similarity, kind = sources[position]
            counts = counts_for(position)
            total = sum(counts.values()) or 1
            candidates = [(r, n / total) for r, n in counts.most_common(5)]
            predictions.append(
                ReadingPrediction(
                    sign=sign,
                    predicted=reading,
                    candidates=candidates,
                    # Corpus attestations only. For a lexicon group this is 0: the
                    # count lives in `lexicon_count`, so the two are never confused.
                    # A composed group has no attestations at all — its "counts" are
                    # probabilities summing to 1 — so it reports 0, like a lexicon
                    # group whose count lives in its own field.
                    attested_count=(
                        sum(counts.values()) if kind not in ("lexicon", "composed") else 0
                    ),
                    is_ambiguous=len(counts) > 1,
                    # "Seen" means this exact group was attested in this corpus. A
                    # fallback reading is a lead from a similar group, and a lexicon
                    # reading is an attestation elsewhere — neither is one of ours.
                    was_seen=sign in self.sign_reading,
                    fallback_from=fallback_from,
                    fallback_similarity=round(similarity, 3) if fallback_from else 0.0,
                    lexicon_count=sum(counts.values()) if kind == "lexicon" else 0,
                    lexicon_source=self.lexicon_sources.get(sign, "") if kind == "lexicon" else "",
                    is_composed=kind == "composed",
                )
            )
        return predictions, lattice[-1][best_final][0]

    def predict_most_frequent(self, signs: list[str]) -> list[str]:
        """Context-free baseline: always the commonest reading of each sign."""
        out: list[str] = []
        for sign in signs:
            candidates = self.candidates_for(sign)
            out.append(candidates[0][0] if candidates else "")
        return out


def train_reading_model(df: pd.DataFrame, lexicon=None) -> ReadingModel:
    """Fit on the corpus; optionally attach an `app.services.lexicon.Lexicon`.

    The lexicon is an argument rather than loaded here so that every evaluation can
    run with and without it and report the difference, and so the model's own counts
    stay a pure function of the corpus.
    """
    model = ReadingModel().fit(df)
    if lexicon is not None and len(lexicon):
        model.attach_lexicon(lexicon.readings, lexicon.sources)
    return model
