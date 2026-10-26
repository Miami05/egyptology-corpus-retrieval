"""Which app segment answers which gold group — endpoint G's missing piece.

`docs/kri-bfreq-baseline-2026-10-26.md`, "Not built yet":

    The scorer is shared, but **no evaluator maps app segments onto gold spans**.
    §4e's app score needs exactly that: which app segment answers which gold group,
    and how merges, splits and repeated groups are handled (all three are misses for
    the app, but something has to detect them). `score_endpoint_g` takes that
    mapping's output as an argument; the mapping itself must be built, tested and
    frozen **before any scoring run**.

This module is that mapping. Its output is the `app_candidates` argument of
`scripts.bfreq_baseline.score_endpoint_g`: one ranked list per gold group, or `None`
where the app did not produce that group — §4e: "A group the app's segmentation does
not produce, or that it merges or splits, counts as a miss for the app."

How it works
------------

The app and the gold division describe the *same* glyph input, so they agree
character by character even where they disagree about word boundaries. The mapping
is therefore by **character offset over the normalised sign string**:

    alignment_key(x) = normalize_hieroglyphs(x) with every space removed

`normalize_hieroglyphs` deletes the layout controls and folds variant codepoints, and
it *keeps* the Private Use placeholders TLA's `<g>…</g>` markup becomes. That is
deliberate and is the one place this differs from §4a's `signs`: `signs` deletes
placeholders, which is right for B-freq's lookup key (B-freq cannot answer a group
with no sign string) and wrong for an alignment, where a deleted character would give
a placeholder-only gold group a zero-length span and silently shift every later
group. Lookup keeps `signs`; alignment keeps placeholders.

Concatenating the gold groups' alignment keys gives the line's sign string, and each
gold group owns the half-open span `[start, end)` it occupies in it. The app's
segments own spans in the same string. Then, per gold group:

    exact            some app segment has exactly this span      -> its top 3
    merged           an app segment covers this span and more    -> None (miss)
    split            every app segment meeting this span lies    -> None (miss)
                     inside it, and there is more than one
    partial_overlap  app boundaries cross this group's           -> None (miss)
    absent           no app segment meets this span (empty app   -> None (miss)
                     output)
    no_signs         the gold group has no signs at all          -> None (miss)

Repeated identical groups
-------------------------

A line may hold the same sign group twice. Offsets tell the two occurrences apart, so
each is answered by the app segment at *its own* position and no app segment is ever
consumed twice (`test_one_app_segment_never_answers_two_gold_groups` pins that). That
is a deliberate reading of a conflict in the brief, and it is stated here rather than
buried: the baseline document lists "repeated groups" beside merges and splits as a
miss for the app, while the same brief requires character-offset alignment — and
offsets make repetition unambiguous, so the hazard the phrase names (a string-keyed
mapping pairing a gold group with the wrong segment, or reusing one segment) is
removed by construction rather than paid for. §4e itself lists only "does not
produce, merges or splits" as misses. Penalising a correctly aligned repeat would
make the app lose a group for the gold line containing one word twice, which is not a
fact about reading Egyptian.

Every repeat is nonetheless counted and reported per line (`repeated_groups`,
`GroupOutcome.repeated_sign_string`), so the lead can see every case; `REPEATED_GROUP_RULE`
is the frozen statement of the rule. Changing it is a code change and a re-freeze, as
§4e requires of any change after results are seen.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import normalize_hieroglyphs  # noqa: E402
from scripts.bfreq_baseline import DEFAULT_TOP_K  # noqa: E402

OUTCOME_EXACT = "exact"
OUTCOME_MERGED = "merged"
OUTCOME_SPLIT = "split"
OUTCOME_PARTIAL = "partial_overlap"
OUTCOME_ABSENT = "absent"
OUTCOME_NO_SIGNS = "no_signs"

#: Every outcome except `exact` is a miss for the app (§4e).
OUTCOMES = (
    OUTCOME_EXACT,
    OUTCOME_MERGED,
    OUTCOME_SPLIT,
    OUTCOME_PARTIAL,
    OUTCOME_ABSENT,
    OUTCOME_NO_SIGNS,
)

REPEATED_GROUP_RULE = (
    "Repeated identical gold groups are told apart by their character offsets: each "
    "occurrence is answered by the app segment at its own position, and no app "
    "segment answers two gold groups. Repeats are counted and reported per line, "
    "never scored as misses for being repeats."
)

ALIGNMENT_RULE = (
    "alignment_key(x) = normalize_hieroglyphs(x) with spaces removed — placeholders "
    "kept (unlike §4a `signs`), so a placeholder-only gold group has a real span and "
    "no later group is shifted."
)


class MappingError(ValueError):
    """The app output cannot describe the same glyph input as the gold division."""


def alignment_key(value: object) -> str:
    """The string both sides are aligned in — see `ALIGNMENT_RULE`."""
    return "".join(normalize_hieroglyphs(value).split())


def spans_of(groups: Sequence[object]) -> list[tuple[int, int]]:
    """Each group's half-open `[start, end)` span in the concatenated sign string."""
    spans: list[tuple[int, int]] = []
    position = 0
    for group in groups:
        length = len(alignment_key(group))
        spans.append((position, position + length))
        position += length
    return spans


@dataclass(frozen=True)
class GroupOutcome:
    """What the app did with one gold group."""

    gold_index: int
    span: tuple[int, int]
    outcome: str
    #: The app segments that meet this gold group's span, in app order.
    app_indices: tuple[int, ...]
    #: The app's ranked readings for this gold group, or `None` for a miss.
    candidates: tuple[str, ...] | None
    #: Whether this gold group's sign string occurs more than once in the line.
    repeated_sign_string: bool

    @property
    def hit_possible(self) -> bool:
        """Whether the app was even given a chance at this group."""
        return self.outcome == OUTCOME_EXACT


@dataclass(frozen=True)
class MappingResult:
    """One line's mapping: the scorer's input, plus why each group looks as it does."""

    outcomes: tuple[GroupOutcome, ...]
    alignment_length: int
    app_segments: int

    @property
    def app_candidates(self) -> list[list[str] | None]:
        """Exactly what `score_endpoint_g(…, app_candidates=…)` expects."""
        return [
            None if outcome.candidates is None else list(outcome.candidates)
            for outcome in self.outcomes
        ]

    @property
    def counts(self) -> dict[str, int]:
        return {
            outcome: sum(1 for item in self.outcomes if item.outcome == outcome)
            for outcome in OUTCOMES
        }

    @property
    def repeated_groups(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.repeated_sign_string)

    def summary(self) -> str:
        counts = ", ".join(
            f"{name} {value}" for name, value in self.counts.items() if value
        )
        return (
            f"{len(self.outcomes)} gold groups vs {self.app_segments} app segments "
            f"over {self.alignment_length} signs: {counts or 'nothing'}"
            + (f"; {self.repeated_groups} repeated sign string(s)" if self.repeated_groups else "")
        )


def map_app_segments_to_gold(
    gold_groups: Sequence[object],
    app_segments: Sequence[object],
    app_candidates: Sequence[Sequence[str]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> MappingResult:
    """Map the app's segmentation onto the gold word division. Deterministic.

    `gold_groups` is Camilla's word division of the line (the glyphs of each gold
    word); `app_segments` is `Segmentation.groups` from the app's paste path, and
    `app_candidates[j]` the app's ranked readings for segment *j*.

    Raises `MappingError` when the two describe different glyph input — an empty app
    output is not that case (it is every group `absent`, a clean sweep of misses),
    but a different sign string is: no span of one can be read in the other. The
    driver refuses a gold division that is not its glyph input before the app runs,
    so at scoring time this error means the app's own output lost or changed signs;
    the driver then scores every group of that line as a miss for the app (§4e: a
    group the app does not produce) and flags the line. The message carries lengths
    and offsets only, never glyphs: this runs on KRI material.
    """
    if len(app_segments) != len(app_candidates):
        raise MappingError(
            f"one candidate list per app segment: {len(app_segments)} segments, "
            f"{len(app_candidates)} candidate lists"
        )
    if top_k < 1:
        raise MappingError("top_k must be at least 1")

    gold_spans = spans_of(gold_groups)
    gold_string_length = gold_spans[-1][1] if gold_spans else 0
    app_spans = spans_of(app_segments)
    app_string_length = app_spans[-1][1] if app_spans else 0

    gold_keys = [alignment_key(group) for group in gold_groups]
    repeated = {key for key in gold_keys if key and gold_keys.count(key) > 1}

    empty_app = app_string_length == 0
    if not empty_app:
        gold_string = "".join(gold_keys)
        app_string = "".join(alignment_key(segment) for segment in app_segments)
        if gold_string != app_string:
            first_difference = next(
                (
                    index
                    for index in range(min(len(gold_string), len(app_string)))
                    if gold_string[index] != app_string[index]
                ),
                min(len(gold_string), len(app_string)),
            )
            raise MappingError(
                "the app output and the gold division are not the same sign string: "
                f"{len(gold_string)} gold signs vs {len(app_string)} app signs, first "
                f"difference at offset {first_difference}. The run is mis-assembled; "
                "scoring it would compare two different lines."
            )

    # An app segment with no signs (a stray space) owns an empty span and can answer
    # nothing; it is skipped so it cannot look like a split.
    real_app = [(index, span) for index, span in enumerate(app_spans) if span[1] > span[0]]

    outcomes: list[GroupOutcome] = []
    for gold_index, (start, end) in enumerate(gold_spans):
        repeated_here = gold_keys[gold_index] in repeated
        if end == start:
            outcomes.append(
                GroupOutcome(
                    gold_index=gold_index,
                    span=(start, end),
                    outcome=OUTCOME_NO_SIGNS,
                    app_indices=(),
                    candidates=None,
                    repeated_sign_string=repeated_here,
                )
            )
            continue

        meeting = [
            (index, span) for index, span in real_app if span[0] < end and span[1] > start
        ]
        indices = tuple(index for index, _ in meeting)

        if not meeting:
            outcome, candidates = OUTCOME_ABSENT, None
        elif any(span == (start, end) for _, span in meeting):
            outcome = OUTCOME_EXACT
            match = next(index for index, span in meeting if span == (start, end))
            candidates = tuple(str(item) for item in app_candidates[match][:top_k])
        elif any(span[0] <= start and span[1] >= end for _, span in meeting):
            outcome, candidates = OUTCOME_MERGED, None
        elif all(span[0] >= start and span[1] <= end for _, span in meeting):
            outcome, candidates = OUTCOME_SPLIT, None
        else:
            outcome, candidates = OUTCOME_PARTIAL, None

        outcomes.append(
            GroupOutcome(
                gold_index=gold_index,
                span=(start, end),
                outcome=outcome,
                app_indices=indices,
                candidates=candidates,
                repeated_sign_string=repeated_here,
            )
        )

    return MappingResult(
        outcomes=tuple(outcomes),
        alignment_length=gold_string_length,
        app_segments=len(app_segments),
    )
