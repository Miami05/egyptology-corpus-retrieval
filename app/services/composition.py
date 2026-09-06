"""Read an unattested sign group sign by sign, from what each sign *does*.

Item C2. Camilla's core objection to a corpus-based tool is the case with no parallel:
a group this corpus has never attested, and the external lexicon has not either. Until
now the only answer was `nearest_known_group` — borrow the readings of the most
similar attested group — which is right about **28%** of the time (measured 2026-09-06
on 1,485 such positions). Borrowing is a guess about *this group*; composition is a
statement about *these signs*, which is the kind of knowledge an Egyptologist actually
applies to an unfamiliar spelling.

**The rule was frozen** (ROADMAP.md, item C, C2.2, pre-registered before any run) and
**amended once by the lead on 2026-09-06**, before any measurement under the amended
form, on four points: only rows describing the sign *standing alone* are used; rows
Nederhof hedges or that are qualified plural/dual/numeral are dropped; a group holding
any sign the tables do not describe standalone yields **no** candidate rather than
silently losing that sign; and identical readings are deduplicated before the cap.

Walk the group's glyphs left to right; each glyph's standalone rows in
`app.services.sign_functions` (Nederhof's table plus this project's supplement) say
what it may contribute:

    phonogram v                            append v
    logogram v                             append v
    logogram or determinative v            append v, OR nothing
    phonogram or phonetic determinative v  nothing if v's consonants are already a
                                           suffix of the reading so far, else append v
    phonetic determinative                 nothing
    determinative                          nothing
    typographic                            nothing

A glyph's choice set is the union of what its rows allow. The candidates are the
product of the choices, **deduplicated and then capped at 24 per group**; a candidate
that composes to the empty string is not a candidate, so a group all of whose signs
are silent yields nothing. The order the cap bites in is the corpus's own
`P(value | sign)` — how often the corpus reads that single glyph, standing alone as a
group, that way — and table order for a value the corpus never shows alone.

Scoring, also frozen: a candidate's score is `Σ log P(value | sign)` over the glyphs
that actually contributed, from the corpus where the corpus has an opinion and
`log(1 / entries of the sign)` where it has none. The emission handed to the decoder is
that score normalised over the candidates, so a composed group is a proper
distribution like any other; the transition and context terms are the ones a lexicon
group gets, i.e. the smoothing defaults, because the corpus has no context statistics
for a group it never saw.

**Revisions, made on dev and logged** (the amended evaluation allows revising the
rules on the dev cut only, each change named after the failure pattern it answers):

* **Revision 1, phonetic complement** (`COMPLEMENT_SKIP`). Egyptian writes a
  multiliteral together with uniliterals repeating its consonants: 𓄤𓆑𓂋 is *nfr*,
  not *nfrfr*, and 𓈖𓏌 is *nw*, not *nnw*. The pre-registered rule suppressed a
  repetition only for the `phonogram or phonetic determinative` class, but the
  complements are ordinarily plain `phonogram` rows, so every such spelling composed
  with doubled consonants. A phonogram may now also contribute nothing when its
  consonants are already written to its left or open a value the next sign could
  contribute. The skip is an *extra* choice, never a replacement, so genuinely
  geminated writings (ꜥmꜥm) stay reachable.
* **Revision 2, optional logogram** (`OPTIONAL_LOGOGRAM`). Y1 𓏛 carries a logogram
  row (*dmḏ*) as well as its determinative rows, so every group ending in the book-
  roll classifier composed with "dmḏ" glued on. A `logogram` row may now contribute
  nothing too, exactly as `logogram or determinative` already could.

**Both revisions raised the ceiling and neither made composition usable.** The dev
numbers are in `reading_model.USE_COMPOSED_BY_DEFAULT`: oracle recall went 0.058 →
0.101 → 0.122 and the composition's own top choice 0.006 → 0.017 → 0.035, against
0.2835 for the glyph-similarity fallback it would have replaced. C2 is a null result;
this module ships switched off.

Composition is **not** an attestation. A composed reading is marked `is_composed` on
`ReadingPrediction`, is counted as borrowed everywhere a fallback is counted, and is
labelled in the UI as read sign by sign rather than observed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import exp, log

from app.services.sign_functions import (
    DET,
    LOG,
    PHON,
    PHONDET,
    TYP,
    FunctionEntry,
    SignFunctions,
)

#: Never return more than this many candidates for one group (pre-registered).
MAX_CANDIDATES = 24

#: **Revision 1, "phonetic complement" (dev, 2026-09-06).** A plain `phonogram` row
#: may also contribute *nothing* when it looks like a phonetic complement — its
#: consonants are already written to its left, or they open a value the next sign
#: could contribute. The skip is an extra choice, never a replacement, because real
#: geminated writings (ꜥmꜥm) must stay reachable. See the module docstring.
COMPLEMENT_SKIP = True

#: **Revision 2, "optional logogram" (dev, 2026-09-06).** A plain `logogram` row may
#: also contribute nothing, exactly as `logogram or determinative` already does.
OPTIONAL_LOGOGRAM = True

#: Work guard, not part of the frozen rule. The product of the choices is enumerated
#: depth-first in the pre-registered order and normally stops at `MAX_CANDIDATES`
#: *distinct non-empty* readings — but a group whose paths collapse to duplicates or
#: to the empty string reaches that cap slowly or never, and a ten-glyph group with
#: three choices each has 59,049 paths. This bounds the walk. It is loose enough that
#: the candidate cap is what stops the enumeration for ordinary groups; it is not a
#: measured maximum, and a group that hits it simply returns fewer candidates.
MAX_LEAVES = 2000

#: Characters that are not consonants of the transliteration and are ignored when
#: asking whether a phonetic determinative merely repeats what is already written.
#: The corpus's TLA convention marks reconstructions with brackets and dots and a
#: suffix pronoun with `=`; none of those is a sound.
_NOT_CONSONANT = set(".()[]{}⸢⸣=-⸗ ‑")


def consonants(value: str) -> str:
    """The consonant skeleton of a transliteration, for the phondet suffix test."""
    return "".join(c for c in value if c not in _NOT_CONSONANT)


@dataclass(frozen=True)
class ComposedReading:
    """One way the signs of a group could be read, and how well it scores."""

    reading: str
    score: float
    #: (sign, value) for each glyph that contributed something.
    contributions: tuple[tuple[str, str], ...]


def _sign_log_probability(
    sign: str, value: str, corpus: dict[str, Counter], entry_count: int
) -> float:
    """`log P(value | sign)` from the corpus, else `log(1 / entries of the sign)`.

    "From the corpus" means: this single glyph, standing alone as a whole sign group,
    is attested with this reading. That is the only place the corpus has an opinion
    about what one sign reads on its own.
    """
    counts = corpus.get(sign)
    if counts:
        total = sum(counts.values())
        seen = counts.get(value, 0)
        if total and seen:
            return log(seen / total)
    return log(1.0 / max(entry_count, 1))


# How a choice behaves during enumeration.
MODE_ALWAYS = "always"          # append the value, no alternative
MODE_SILENT = "silent"          # contribute nothing
MODE_PHONDET = "phondet_cond"   # append UNLESS the consonants are already written
MODE_COMPLEMENT = "complement"  # append, OR skip when it is plainly a phonetic complement
MODE_OPTIONAL = "optional"      # append, OR skip — unconditionally


def _ordered_options(
    sign: str,
    entries: tuple[FunctionEntry, ...],
    corpus: dict[str, Counter],
    complement_skip: bool = True,
    optional_logogram: bool = True,
) -> list[tuple[str, str, float]]:
    """The glyph's choices as `(value, mode, log P)`, best first.

    `value` is what would be appended; `""` with mode `SILENT` means "contribute
    nothing". Modes other than `ALWAYS`/`SILENT` depend on the reading being built,
    so they are resolved during enumeration, not here.

    `complement_skip` and `optional_logogram` are the two dev revisions; see the
    module docstring's "Revisions" section.
    """
    options: dict[tuple[str, str], float] = {}
    entry_count = max(len(entries), 1)

    def offer(value: str, mode: str, score: float | None = None) -> None:
        if not value:
            options.setdefault(("", MODE_SILENT), 0.0)
            return
        options.setdefault(
            (value, mode),
            _sign_log_probability(sign, value, corpus, entry_count)
            if score is None
            else score,
        )

    for entry in entries:
        classes = entry.classes
        value = entry.value
        if classes == frozenset({PHON}):
            offer(value, MODE_COMPLEMENT if complement_skip else MODE_ALWAYS)
        elif classes == frozenset({LOG}):
            offer(value, MODE_OPTIONAL if optional_logogram else MODE_ALWAYS)
        elif classes == frozenset({LOG, DET}):
            offer(value, MODE_OPTIONAL)
            options.setdefault(("", MODE_SILENT), 0.0)
        elif classes == frozenset({PHON, PHONDET}):
            if value:
                offer(value, MODE_PHONDET)
            else:
                options.setdefault(("", MODE_SILENT), 0.0)
        else:
            # determinative, phonetic determinative, typographic, unk — silent.
            options.setdefault(("", MODE_SILENT), 0.0)
    # Highest corpus probability first; "contribute nothing" (score 0.0) would
    # otherwise sort above every real value, so it is pushed last. The sort is stable
    # and `options` preserves the order the rows were read in, so values the corpus
    # has no opinion about keep **table order** — the pre-registered tie-break.
    ordered = sorted(options.items(), key=lambda item: (item[0][1] == MODE_SILENT, -item[1]))
    return [(value, mode, score) for (value, mode), score in ordered]


def compose_group(
    group: str,
    functions: SignFunctions,
    corpus: dict[str, Counter],
    max_candidates: int = MAX_CANDIDATES,
    complement_skip: bool = COMPLEMENT_SKIP,
    optional_logogram: bool = OPTIONAL_LOGOGRAM,
) -> list[ComposedReading]:
    """Every reading the group's signs compose to, best first, capped.

    Returns `[]` when nothing composes — no sign contributes, or every candidate is
    empty. The caller then falls through to the glyph-similarity fallback exactly as
    before, so a group composition cannot read is not made worse by this code.
    """
    if not group:
        return []

    per_sign: list[tuple[str, list[tuple[str, str, float]]]] = []
    for sign in group:
        entries = functions.standalone_entries_for(sign)
        if not entries:
            # ABSTAIN (amended rule 3). A sign with no standalone row is a sign the
            # tables say nothing about on its own. Treating it as silent would drop
            # it from the reading without telling anyone, and a reading missing a
            # whole sign is worse than no reading: the caller falls through to the
            # lexicon and the glyph-similarity fallback exactly as before item C2.
            return []
        per_sign.append(
            (
                sign,
                _ordered_options(
                    sign,
                    entries,
                    corpus,
                    complement_skip=complement_skip,
                    optional_logogram=optional_logogram,
                ),
            )
        )

    # For the "complement written *before* its multiliteral" case: the consonant
    # skeletons every following sign could contribute, so `n` before `nw` can be
    # recognised as a complement without looking at the reading built so far.
    next_skeletons: list[set[str]] = [set() for _ in per_sign]
    for index in range(len(per_sign) - 2, -1, -1):
        values = {
            consonants(value)
            for value, _mode, _score in per_sign[index + 1][1]
            if value
        }
        next_skeletons[index] = {v for v in values if v}

    # Depth-first over the product, each glyph's choices in the pre-registered order
    # (corpus P(value | sign) first, table order for a value the corpus never shows
    # alone, "contribute nothing" last), so the cap keeps the first 24 candidates of
    # that enumeration — which is what "cap 24 per group" was frozen to mean.
    results: list[ComposedReading] = []
    seen: set[str] = set()
    leaves = 0

    def walk(
        index: int,
        reading: str,
        score: float,
        contributions: tuple[tuple[str, str], ...],
        last_value: str = "",
    ) -> None:
        """`last_value` is what the most recent contributing sign appended — the
        multiliteral a following phonetic complement would be complementing."""
        nonlocal leaves
        if len(results) >= max_candidates or leaves >= MAX_LEAVES:
            return
        if index == len(per_sign):
            leaves += 1
            if reading and reading not in seen:
                seen.add(reading)
                results.append(ComposedReading(reading, score, contributions))
            return
        sign, options = per_sign[index]
        for value, mode, option_score in options:
            if len(results) >= max_candidates or leaves >= MAX_LEAVES:
                return
            if mode == MODE_SILENT or not value:
                walk(index + 1, reading, score, contributions, last_value)
                continue

            skeleton = consonants(value)
            if mode == MODE_PHONDET:
                # "phonogram or phonetic determinative": nothing if the consonants are
                # already a suffix of the reading so far, else append. One choice,
                # exactly as pre-registered.
                if skeleton and consonants(reading).endswith(skeleton):
                    walk(index + 1, reading, score, contributions, last_value)
                    continue
            elif mode == MODE_COMPLEMENT:
                # Revision 1: this sign *may* be a phonetic complement — a shorter
                # phonogram repeating consonants of the multiliteral beside it, which
                # Egyptian writes but transliteration does not repeat. 𓄤𓆑𓂋 is *nfr*,
                # 𓈖𓏌 is *nw*. Offer the skip as an alternative (never instead) when
                # it looks like one, either because the multiliteral to its left
                # already contains those consonants, or because they open a longer
                # value the next sign could contribute. A complement is by definition
                # shorter than what it complements, which is what keeps a genuine
                # gemination (ꜥm + ꜥm) out of this branch.
                left = consonants(last_value)
                repeats_left = (
                    bool(skeleton) and len(skeleton) < len(left) and skeleton in left
                )
                opens_right = bool(skeleton) and any(
                    len(skeleton) < len(other) and other.startswith(skeleton)
                    for other in next_skeletons[index]
                )
                if repeats_left or opens_right:
                    walk(index + 1, reading, score, contributions, last_value)
            elif mode == MODE_OPTIONAL:
                # Revision 2 (and the pre-registered "logogram or determinative"):
                # the sign may equally be a classifier and contribute nothing.
                walk(index + 1, reading, score, contributions, last_value)

            if len(results) >= max_candidates or leaves >= MAX_LEAVES:
                return
            walk(
                index + 1,
                reading + value,
                score + option_score,
                contributions + ((sign, value),),
                value,
            )

    walk(0, "", 0.0, ())
    return results


def composed_distribution(
    readings: list[ComposedReading],
) -> Counter:
    """The candidates' scores, normalised over the candidates, as a distribution.

    A `Counter` of floats summing to 1.0, so every caller that already handles a
    Counter of corpus counts handles this too (`most_common` orders it, `sum` is 1).
    """
    distribution: Counter = Counter()
    if not readings:
        return distribution
    top = max(candidate.score for candidate in readings)
    # Shifted by the maximum before exponentiating: the scores are sums of log
    # probabilities and a long group's can be very negative.
    weights = [(candidate.reading, exp(candidate.score - top)) for candidate in readings]
    total = sum(weight for _reading, weight in weights)
    if total <= 0:
        share = 1.0 / len(weights)
        for reading, _weight in weights:
            distribution[reading] = share
        return distribution
    for reading, weight in weights:
        distribution[reading] = weight / total
    return distribution
