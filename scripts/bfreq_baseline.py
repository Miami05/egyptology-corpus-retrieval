"""B-freq: the frozen glyph → reading baseline for KRI endpoint G.

Why this exists. `docs/plan-data-cleanup-2026-10-26.md` §4e splits the KRI
confirmation into two endpoint-specific comparisons that are never pooled. Endpoint R
(transliteration → retrieval) already had a baseline — word overlap, BM25 secondary.
Endpoint G (glyph input → reading) had none, so the app had nothing to beat. §4e
defines one, **B-freq**, and makes it a precondition:

    "G can be part of a confirmation only if B-freq is implemented, unit-tested on
    synthetic fixtures and committed with its sha256 **before** any 4e material
    arrives. Otherwise G is reported as exploratory, and no G number goes to experts."

This module is that implementation. It is deliberately dull: for a sign group, the
readings the pinned public corpus attests for exactly that sign string, ranked by how
often. No context, no stage filter (the stage-restricted variant is a *secondary*,
descriptive table), no smoothing, no similarity fallback, no lexicon — and in
particular **no call into the app**. An unattested sign string returns an empty list,
which the scorer counts as a miss. That is the point: the baseline must be able to
lose, and it must lose on its own terms rather than quietly borrowing the app's
fallback machinery.

What is shared with the app, and why. Two things, both so the comparison is fair
rather than rigged by a notation mismatch:

* the **sign-group key** — `app.data.normalizer.normalize_hieroglyphs` (the app's own
  sign normalisation, which folds variant codepoints and strips format controls),
  then `scripts.import_ud_egyptian_pc.glyph_key`, which is the §4a `signs` definition
  (every space, layout control and placeholder removed). §4a says that function is
  imported, never re-written, so it is imported here;
* the **reading identity** — `app.services.suggestions.strict_reading_key`, the
  suggestion identity key, primary per §4d ("strict key primary; folded key
  reported"). `app.data.normalizer.search_fold` is available as the secondary,
  reported key. Neither is re-implemented.

What is *not* shared is the prediction. The word-level (sign group, reading) pairs are
re-derived here by `iter_word_pairs`, which mirrors `ReadingModel.fit` exactly —
`hieroglyphs_norm` split on whitespace, zipped with `transliteration_gold` split on
whitespace, the row skipped unless the two line up one-to-one — so the baseline sees
the same alignment the app's reading model is built from, and nothing more.
`tests/test_bfreq_baseline.py` pins that equality against `ReadingModel` itself, so a
change to the app's alignment cannot silently make the two corpora differ.

Scoring (§4e, endpoint G) lives here too, in **one** function used by both sides:

    per gold group:  a hit if the gold reading's key is among the side's top 3
    line score  s =  hits / groups
    binary success:  s ≥ 0.5

A group the app's segmentation does not produce, or that it merges or splits, is
passed as `None` and counts as a miss for the app. B-freq is given the gold
segmentation, which favours the baseline; §4e says so and the report must repeat it.

Custody. Nothing here may ever read KRI material: the baseline is frozen *before* any
KRI line is opened, and that is the whole evidentiary value of the file. Every path
that reaches this module goes through `assert_public_path`, a lexical tripwire against
the pre-registered custody directory (§4b) and against the private corpus directory.
It is a tripwire, not a secret scanner — it cannot know what a file holds, only where
it sits.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePath

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import normalize_hieroglyphs, search_fold
from app.services.suggestions import strict_reading_key
from scripts.import_ud_egyptian_pc import glyph_key

# ---------------------------------------------------------------------------
# frozen constants — changing any of these retires the baseline (§4e)
# ---------------------------------------------------------------------------

#: How many readings a side may offer per group. §4e scores "in the top 3".
DEFAULT_TOP_K = 3

#: §4e: "Binary success per line: `s ≥ 0.5`, for both app and baseline."
SUCCESS_THRESHOLD = 0.5

#: The secondary, descriptive restriction of §4e. The exact `language_stage` value
#: used by the corpus (the others are "Earlier Egyptian", "Demotic",
#: "Unspecified (BBAW)", "Unspecified (AES)").
LATE_EGYPTIAN = "Late Egyptian"

#: §4e leaves the ordering of equally frequent readings open, which would make the
#: table depend on row order. Fixed here and stated in every header and report:
TIE_BREAK_RULE = (
    "descending attestation count, then strict_reading_key ascending by Unicode "
    "code point (Python string order on the NFC key)"
)

#: What B-freq actually *offers* for a selected reading identity.
#:
#: The identity key is how candidates are grouped and ranked; it is not a spelling.
#: Offering the key itself broke the secondary folded scorer, because the strict key
#: has already lost the editorial apparatus the ASCII fold treats differently: a
#: corpus, app and gold reading that are all `n(.ꞽ).t` give strict key `nꞽt`, and
#: `search_fold("nꞽt") = "nit"` while `search_fold("n(.ꞽ).t") = "nt"`. The app offers
#: surface spellings, so under the folded key the app scored a hit and B-freq a miss
#: on identical material — an artefact of representation, not of reading Egyptian.
#: B-freq therefore offers an attested surface spelling, like the app does, and both
#: sides are folded from the same kind of string.
#:
#: Under the primary strict key this changes nothing: the surface form is chosen from
#: the words that carry that key, so `strict_reading_key(surface)` is the key again.
SURFACE_RULE = (
    "the most frequent attested surface spelling carrying that reading identity in "
    "the same corpus, ties broken by the spelling ascending in Unicode code-point "
    "order"
)

#: Declared in advance, before any KRI line is scored (§4e, and the review of
#: 2026-10-26): how a gold group that B-freq cannot key is handled.
PLACEHOLDER_GOLD_TREATMENT = (
    "A gold group whose signs are all internal <g> markup placeholders, or which "
    "carries no signs at all, has no sign key: B-freq cannot answer it and the app "
    "can. Such groups STAY in the denominator and are scored as misses for the "
    "baseline. They are counted and reported by inspect_gold_groups() BEFORE any "
    "prediction is scored, and no group is ever dropped from a line after its "
    "predictions have been seen."
)

#: Columns `build_table` needs from the corpus CSV. Reading only these keeps the
#: pass light: the file is ~69 MB, these three columns are a fraction of it.
CORPUS_COLUMNS = ("hieroglyphs", "transliteration_gold", "language_stage")

#: Path components that must never appear in a path this module reads or writes.
#: `egyptology-private-kri` is the custody directory of §4b and `kri` catches a
#: shorter-named copy. Matching is on whole, case-folded path components, so this
#: branch (`kri-baseline-2026-10-26`) and this file's documentation are unaffected.
FORBIDDEN_PATH_COMPONENTS = frozenset({"egyptology-private-kri", "kri"})

#: The non-redistributable corpus directory, refused as well: endpoint G's baseline
#: is built on the public corpus only, never with `--private-dir`. Matched as the
#: *pair* `data/private` rather than a bare `private` component, because macOS puts
#: every temporary directory under `/private/var/folders/…` and a bare match would
#: refuse ordinary paths — the test suite caught exactly that.
FORBIDDEN_PATH_PAIRS = (("data", "private"),)


class ForbiddenPathError(RuntimeError):
    """A path pointed at KRI custody or at the private corpus."""


def assert_public_path(path: str | os.PathLike[str], *, what: str = "path") -> Path:
    """Refuse a KRI-custody or private-corpus path, and return the path otherwise.

    Purely lexical: `os.path.abspath` normalises without touching the filesystem, so
    checking a custody path never stats, lists or opens it. That matters — the whole
    claim this module makes is that it never touched KRI material, and a guard that
    had to look at the directory to say so would weaken it.
    """
    absolute = os.path.abspath(os.path.expanduser(str(path)))
    parts = [part.casefold() for part in PurePath(absolute).parts]
    hit = sorted(set(parts) & FORBIDDEN_PATH_COMPONENTS)
    if not hit:
        pairs = set(zip(parts, parts[1:]))
        hit = ["/".join(pair) for pair in FORBIDDEN_PATH_PAIRS if pair in pairs]
    if hit:
        raise ForbiddenPathError(
            f"{what} {absolute!r} lies under a forbidden directory {hit[0]!r}: "
            f"B-freq is built and scored on the public corpus only, and never reads "
            f"KRI material (plan 2026-10-26 §4b, §4e)"
        )
    return Path(absolute)


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


def sign_key(value: object) -> str:
    """The lookup key of one sign group.

    The app's hieroglyph normalisation first, then the §4a `signs` definition. §4e
    says only "`signs(group)`"; running the app's normalisation first is what makes
    the lookup *fair* rather than merely literal. Without it a gold group written
    with a variant codepoint (TLA's Z15B three strokes, U+133FC, against the corpus's
    Z2, U+133E5) or with a variation selector would miss a group the corpus attests
    thousands of times, and B-freq would lose for a reason that has nothing to do
    with reading Egyptian. On text that is already plain Unicode signs the extra step
    is a no-op.

    Returns "" for a group with no signs at all (text-only rows, or a group that was
    nothing but a `<g>` placeholder). An empty key is never stored and never matches.
    """
    return glyph_key(normalize_hieroglyphs(value))


def reading_key(value: object) -> str:
    """The primary reading identity: the app's suggestion identity key (§4d)."""
    return strict_reading_key(value)


def folded_reading_key(value: object) -> str:
    """The secondary, *reported* key of §4d: the ASCII search fold.

    Never the primary. It merges consonants the strict key keeps apart (ꜣ/ꜥ → a,
    ḫ/ẖ → kh), which Nederhof rejected as an identity (expert round 2), so a number
    scored with it is reported beside the strict one, never instead of it.
    """
    return search_fold(value)


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BFreqEntry:
    """One ranked reading of one sign group."""

    rank: int
    #: The reading identity: how candidates are grouped and ranked.
    reading_key: str
    count: int
    #: What B-freq offers for that identity — see `SURFACE_RULE`. This is
    #: load-bearing, not decoration: the app offers surface spellings, so the
    #: baseline must too, or the secondary folded scorer compares a stripped key
    #: against an unstripped spelling and the two sides are not scored alike.
    surface_reading: str


@dataclass
class BFreqTable:
    """Sign group → readings, ranked, from one pinned corpus."""

    entries: dict[str, tuple[BFreqEntry, ...]] = field(default_factory=dict)
    stage_filter: str | None = None
    rows_read: int = 0
    rows_used: int = 0
    #: Rows whose sign groups and readings did not line up one-to-one. The same
    #: condition `ReadingModel.fit` counts as `sentences_skipped`.
    rows_misaligned: int = 0
    #: Rows with no hieroglyphs at all (BBAW text-only, Demotic). Expected, not a
    #: defect — `ReadingModel.fit`'s `sentences_text_only`.
    rows_text_only: int = 0
    pairs: int = 0
    #: Pairs dropped because the group had no signs or the reading no key.
    pairs_dropped: int = 0

    @property
    def groups(self) -> int:
        return len(self.entries)

    def _entries_for(self, group: object, top_k: int) -> tuple[BFreqEntry, ...]:
        if top_k < 0:
            raise ValueError("top_k must not be negative")
        key = sign_key(group)
        if not key:
            return ()
        return self.entries.get(key, ())[:top_k]

    def top(self, group: object, *, top_k: int = DEFAULT_TOP_K) -> list[str]:
        """What B-freq offers for `group`: ranked surface spellings (`SURFACE_RULE`).

        Surface spellings, not identity keys, because the app offers spellings and
        both sides have to be the same kind of string for the secondary folded
        scorer to mean anything. Under the primary strict key the two are
        interchangeable — `strict_reading_key(surface)` is the identity it was
        chosen for — so this changes no strict-key result; use `top_keys` when the
        identity itself is wanted.

        `[]` is the explicit "no reading" of §4e. There is deliberately no fallback
        to the app's glyph-similarity borrowing, its lexicon or its composition: an
        unattested sign string is a miss for the baseline.
        """
        return [entry.surface_reading for entry in self._entries_for(group, top_k)]

    def top_keys(self, group: object, *, top_k: int = DEFAULT_TOP_K) -> list[str]:
        """The ranked reading *identities* for `group` — inspection and reports."""
        return [entry.reading_key for entry in self._entries_for(group, top_k)]

    def predict_line(
        self, groups: list[object], *, top_k: int = DEFAULT_TOP_K
    ) -> list[list[str]]:
        """B-freq's answer for a whole line, one ranked list per gold group.

        §4e hands the baseline the *gold* word division ("B-freq is given the gold
        segmentation, which favours the baseline; that is stated in the report"), so
        unlike the app it never fails to produce a group — it only fails to read one.
        """
        return [self.top(group, top_k=top_k) for group in groups]


#: What `iter_aligned_rows` says about a row.
ROW_ALIGNED = "aligned"
ROW_TEXT_ONLY = "text_only"
ROW_MISALIGNED = "misaligned"


def iter_aligned_rows(df: pd.DataFrame):
    """Yield `(status, signs, words, language_stage)` for every corpus row.

    This mirrors `app.services.reading_model.ReadingModel.fit` exactly: groups come
    from `hieroglyphs_norm` split on whitespace, readings from
    `transliteration_gold` split on whitespace, a row with no signs is `text_only`
    (an expected state — BBAW text-only rows, Demotic), and a row whose two sides do
    not line up one-to-one is `misaligned` and contributes nothing. `ReadingModel`
    counts those two classes as `sentences_text_only` and `sentences_skipped`.
    """
    if "hieroglyphs_norm" in df.columns:
        norm = df["hieroglyphs_norm"].astype(str)
    else:
        norm = df["hieroglyphs"].astype(str).map(normalize_hieroglyphs)
    readings = df["transliteration_gold"].astype(str)
    stages = (
        df["language_stage"].astype(str)
        if "language_stage" in df.columns
        else pd.Series([""] * len(df), index=df.index)
    )
    for signs_value, reading_value, stage in zip(norm, readings, stages):
        signs = signs_value.split()
        words = reading_value.split()
        if not signs:
            yield ROW_TEXT_ONLY, [], words, stage
        elif len(signs) != len(words):
            yield ROW_MISALIGNED, signs, words, stage
        else:
            yield ROW_ALIGNED, signs, words, stage


def iter_word_pairs(df: pd.DataFrame):
    """Yield `(sign group, reading, language_stage)` for every aligned corpus word.

    `tests/test_bfreq_baseline.py` asserts this multiset equals the (sign, reading)
    pairs `ReadingModel.fit` counts on the same frame, so "the same word alignment
    the app's reading model is built from" (§4e) is a tested property, not a comment.
    """
    for status, signs, words, stage in iter_aligned_rows(df):
        if status != ROW_ALIGNED:
            continue
        for group, word in zip(signs, words):
            yield group, word, stage


def build_table(df: pd.DataFrame, *, stage: str | None = None) -> BFreqTable:
    """Count every attested (sign group, reading) pair and rank the readings.

    `stage` restricts the rows to one `language_stage` value — §4e's secondary,
    descriptive "B-freq restricted to Late Egyptian rows". The primary table is built
    with `stage=None`: no stage filter, no context, the whole pinned public corpus.
    """
    counts: dict[str, Counter] = {}
    surfaces: dict[tuple[str, str], Counter] = {}
    table = BFreqTable(stage_filter=stage, rows_read=len(df))
    for status, signs, words, row_stage in iter_aligned_rows(df):
        if stage is not None and row_stage != stage:
            continue
        if status == ROW_TEXT_ONLY:
            table.rows_text_only += 1
            continue
        if status == ROW_MISALIGNED:
            table.rows_misaligned += 1
            continue
        table.rows_used += 1
        for group, word in zip(signs, words):
            key = sign_key(group)
            rkey = reading_key(word)
            if not key or not rkey:
                table.pairs_dropped += 1
                continue
            table.pairs += 1
            counts.setdefault(key, Counter())[rkey] += 1
            surfaces.setdefault((key, rkey), Counter())[word] += 1

    for key, counter in counts.items():
        ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        entries = []
        for rank, (rkey, count) in enumerate(ranked, start=1):
            # SURFACE_RULE: most frequent attested spelling for this identity, ties
            # by code point. Deterministic, so the offered string is reproducible.
            surface = sorted(
                surfaces[(key, rkey)].items(), key=lambda item: (-item[1], item[0])
            )[0][0]
            entries.append(
                BFreqEntry(rank=rank, reading_key=rkey, count=count, surface_reading=surface)
            )
        table.entries[key] = tuple(entries)
    return table


def load_corpus(path: str | os.PathLike[str]) -> pd.DataFrame:
    """Read the three columns B-freq needs from a public corpus CSV.

    `keep_default_na=False` so an empty cell stays `""` and never becomes the float
    `nan`, which would otherwise reach `normalize_hieroglyphs` as the string "nan".
    """
    checked = assert_public_path(path, what="corpus")
    return pd.read_csv(
        checked, usecols=list(CORPUS_COLUMNS), dtype=str, keep_default_na=False
    )


def table_rows(table: BFreqTable, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """The frozen table as CSV rows, in a deterministic order.

    Sign keys in Unicode code-point order, readings by rank. Two runs on the same
    corpus therefore produce byte-identical files, which is what the committed
    sha256 pins.
    """
    rows: list[dict] = []
    for key in sorted(table.entries):
        for entry in table.entries[key][:top_k]:
            rows.append(
                {
                    "sign_key": key,
                    "rank": entry.rank,
                    "reading_key": entry.reading_key,
                    "count": entry.count,
                    "surface_reading": entry.surface_reading,
                }
            )
    return rows


TABLE_COLUMNS = ("sign_key", "rank", "reading_key", "count", "surface_reading")


# ---------------------------------------------------------------------------
# scoring — ONE function, used by both sides (§4e)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineScore:
    """The §4e unit of analysis: one declared line, scored for one side."""

    groups: int
    hits: int
    score: float
    success: bool
    #: Per gold group, whether that side hit it. Kept so the "group-level hit counts"
    #: secondary of §4e needs no second pass.
    group_hits: tuple[bool, ...]


def score_line(
    gold_readings: list[object],
    candidates: list[list[str] | None],
    *,
    top_k: int = DEFAULT_TOP_K,
    key: object = reading_key,
    success_threshold: float = SUCCESS_THRESHOLD,
) -> LineScore:
    """Score one line for one side. The only scorer; the app and B-freq both use it.

    `gold_readings` is Camilla's gold word division of the line. `candidates[i]` is
    that side's ranked suggestions for gold group *i*, or `None` where the side did
    not produce the group at all — §4e: "A group the app's segmentation does not
    produce, or that it merges or splits, counts as a miss for the app." B-freq is
    handed the gold segmentation, so its entries are never `None`, only possibly
    empty (an unattested sign string).

    A gold reading with an empty key cannot be matched by anything and is a miss for
    both sides, so neither is rewarded for an unreadable gold.
    """
    if len(gold_readings) != len(candidates):
        raise ValueError(
            f"one candidate list per gold group: {len(gold_readings)} gold groups, "
            f"{len(candidates)} candidate lists"
        )
    if not gold_readings:
        raise ValueError("a line with no gold groups is not a unit of analysis (§4e)")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    hits: list[bool] = []
    for gold, offered in zip(gold_readings, candidates):
        gold_key = key(gold)
        if not gold_key or not offered:
            hits.append(False)
            continue
        hits.append(any(key(item) == gold_key for item in offered[:top_k]))
    score = sum(hits) / len(hits)
    return LineScore(
        groups=len(hits),
        hits=sum(hits),
        score=score,
        success=score >= success_threshold,
        group_hits=tuple(hits),
    )


def score_pair(
    gold_readings: list[object],
    app_candidates: list[list[str] | None],
    baseline_candidates: list[list[str] | None],
    **kwargs,
) -> tuple[LineScore, LineScore]:
    """Score the app and B-freq on one line, in one call, with the same scorer.

    Exists so no second scoring path can appear: an analysis that wants both numbers
    calls this, and the two sides are symmetric by construction — swapping the
    arguments swaps the results and changes nothing else.
    """
    return (
        score_line(gold_readings, app_candidates, **kwargs),
        score_line(gold_readings, baseline_candidates, **kwargs),
    )


# ---------------------------------------------------------------------------
# gold groups: counted and declared before anything is scored
# ---------------------------------------------------------------------------

GROUP_SCORABLE = "scorable"
#: Signs present, but every one of them is an internal `<g>` markup placeholder, so
#: the §4a `signs` definition leaves no key. B-freq cannot answer it; the app can.
GROUP_PLACEHOLDER_ONLY = "placeholder_only"
#: No signs at all (empty, or only layout controls).
GROUP_NO_SIGNS = "no_signs"


@dataclass(frozen=True)
class GoldGroupReport:
    """What a line's gold groups look like *before* any prediction is scored.

    The review of 2026-10-26 asked for this: the claim "placeholder-only groups
    cannot bias the comparison" holds only while the input policy holds (gold groups
    supplied as Unicode hieroglyphs). Rather than rely on the policy, every line's
    groups are classified and counted first, under the treatment declared in
    `PLACEHOLDER_GOLD_TREATMENT`, so a group B-freq cannot key is on the record
    before anyone has seen who won it — and can never be dropped afterwards.
    """

    groups: int
    scorable: int
    placeholder_only: int
    no_signs: int
    kinds: tuple[str, ...]
    placeholder_indices: tuple[int, ...]
    no_signs_indices: tuple[int, ...]

    @property
    def unkeyable(self) -> int:
        """Groups B-freq structurally cannot answer. All stay in the denominator."""
        return self.placeholder_only + self.no_signs

    def summary(self) -> str:
        return (
            f"{self.groups} gold groups: {self.scorable} scorable, "
            f"{self.placeholder_only} placeholder-only, {self.no_signs} without "
            f"signs; {self.unkeyable} unkeyable by B-freq and kept in the "
            f"denominator as misses"
        )


def classify_gold_group(group: object) -> str:
    """One gold group's kind — see the `GROUP_*` constants."""
    if sign_key(group):
        return GROUP_SCORABLE
    # No key. Distinguish "there were signs, but only ours" from "there were none":
    # `normalize_hieroglyphs` turns `<g>ID</g>` into a Private Use placeholder, which
    # `glyph_key` then deletes.
    return GROUP_PLACEHOLDER_ONLY if normalize_hieroglyphs(group) else GROUP_NO_SIGNS


def inspect_gold_groups(gold_groups: list[object]) -> GoldGroupReport:
    """Classify and count a line's gold groups. Call this before scoring."""
    kinds = tuple(classify_gold_group(group) for group in gold_groups)
    return GoldGroupReport(
        groups=len(kinds),
        scorable=sum(1 for kind in kinds if kind == GROUP_SCORABLE),
        placeholder_only=sum(1 for kind in kinds if kind == GROUP_PLACEHOLDER_ONLY),
        no_signs=sum(1 for kind in kinds if kind == GROUP_NO_SIGNS),
        kinds=kinds,
        placeholder_indices=tuple(
            i for i, kind in enumerate(kinds) if kind == GROUP_PLACEHOLDER_ONLY
        ),
        no_signs_indices=tuple(i for i, kind in enumerate(kinds) if kind == GROUP_NO_SIGNS),
    )


def score_endpoint_g(
    table: BFreqTable,
    gold_groups: list[object],
    gold_readings: list[object],
    app_candidates: list[list[str] | None],
    **kwargs,
) -> tuple[GoldGroupReport, LineScore, LineScore]:
    """The endpoint-G entry point for one line: report first, then score both sides.

    Returns `(gold-group report, app score, baseline score)`. The report is computed
    *before* either side is scored and covers every gold group, so the record of
    which groups B-freq structurally cannot answer exists independently of who won
    them. Both sides go through `score_pair`, hence through the single scorer.

    Not yet wired to anything: the app's own predictions still have to be mapped onto
    the gold spans (merges, splits and repeated groups), which is not built — see
    `docs/kri-bfreq-baseline-2026-10-26.md`. `app_candidates` is that mapping's
    output and is supplied by the caller.
    """
    if len(gold_groups) != len(gold_readings):
        raise ValueError(
            f"one gold reading per gold group: {len(gold_groups)} groups, "
            f"{len(gold_readings)} readings"
        )
    report = inspect_gold_groups(gold_groups)
    baseline_candidates = table.predict_line(
        gold_groups, top_k=kwargs.get("top_k", DEFAULT_TOP_K)
    )
    app_score, baseline_score = score_pair(
        gold_readings, app_candidates, baseline_candidates, **kwargs
    )
    return report, app_score, baseline_score
