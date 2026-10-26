"""§4a overlap predicates: is a KRI line already in the corpus the tool searches?

Why this exists. `docs/plan-data-cleanup-2026-10-26.md` §4a fixes seven predicates and
their thresholds *in advance*, so that "the tool read this line" can never turn out to
mean "the tool had already been shown this line". A line is labelled

    contained   if any of C1-C4 holds against some corpus row,
    partial     else if any of P1-P3 holds,
    new         otherwise,

and only a `new` line may be run (§4d). The precedence is fixed, and the report prints
*every* predicate that fired with its witness row and Jaccard value, so a `partial`
reached through P2/P3 is never presented as containment.

The predicates, verbatim from §4a (q = the line, r = a corpus row of the gate corpus G):

    C1  skey(q) = skey(r) or fold(q) = fold(r), both non-empty   identical reading
    C2  signs(q) = signs(r), both with >= 2 signs                identical signs
    C3  J(q, r) >= 0.70                                          near-identical tokens
    C4  q has >= 3 folded words and is word-bounded inside r     q contained in r
    P1  0.50 <= J(q, r) < 0.70                                   shared tokens
    P2  q and r share a contiguous run of >= 3 folded words      shared word run
    P3  |T(q) & T(r)| / |T(q)| >= 0.50, T = sign trigrams,       shared sign trigrams
        both sides >= 3 signs

Every function named in §4a is **imported, never re-written**:

    fold   = app.data.normalizer.search_fold
    skey   = app.services.suggestions.strict_reading_key
    J      = scripts.eval_guards.jaccard over
             scripts.build_competitive_ambiguity_benchmark._token_set(
                 app.services.suggestions.loose_reading_form(.))
    signs  = scripts.bfreq_baseline.sign_key, which is
             scripts.import_ud_egyptian_pc.glyph_key after the app's sign
             normalisation — see `SIGNS_RULE` for why the normalisation is there and
             what is reported when it is what makes C2/P3 fire.

Thresholds are compared as exact rationals (`fractions.Fraction`), never as floats:
0.50 and 0.70 are inclusive bounds in §4a, and a float comparison at an inclusive
bound is how this project lost a twin guard once already (`int((1-0.9)*10) == 0`,
2026-09-05).

This module holds the rules; `scripts/check_overlap.py` is the command-line front end
and the dev/gate fixture runner.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Iterator, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import search_fold  # noqa: E402
from app.services.suggestions import (  # noqa: E402
    loose_reading_form,
    strict_reading_key,
)
from scripts.bfreq_baseline import sign_key  # noqa: E402
from scripts.build_competitive_ambiguity_benchmark import _token_set  # noqa: E402
from scripts.eval_guards import jaccard  # noqa: E402
from scripts.import_ud_egyptian_pc import glyph_key  # noqa: E402

# --------------------------------------------------------------------------- rules

#: §4a thresholds, as exact rationals.
C3_MIN_JACCARD = Fraction(7, 10)
P1_MIN_JACCARD = Fraction(1, 2)
P3_MIN_TRIGRAM_SHARE = Fraction(1, 2)
MIN_C2_SIGNS = 2
MIN_C4_WORDS = 3
MIN_RUN_WORDS = 3
MIN_TRIGRAM_SIGNS = 3

CONTAINED = "contained"
PARTIAL = "partial"
NEW = "new"

CONTAINMENT_PREDICATES = ("C1", "C2", "C3", "C4")
PARTIAL_PREDICATES = ("P1", "P2", "P3")
PREDICATES = CONTAINMENT_PREDICATES + PARTIAL_PREDICATES

EVIDENCE_TYPE = {
    "C1": "identical reading",
    "C2": "identical signs",
    "C3": "near-identical tokens",
    "C4": "q contained in r",
    "P1": "shared tokens",
    "P2": "shared word run",
    "P3": "shared sign trigrams",
    "EXTRA_FOLD": "extra-fold reading match (reported only, never a C/P result)",
}

#: §4a's `signs`, and the one place this checker is stricter than the letter of the
#: plan. §4a says "the same definition as `glyph_key` in `import_ud_egyptian_pc.py`,
#: imported, not re-written". We import exactly that function, but through
#: `scripts.bfreq_baseline.sign_key`, which runs the app's own
#: `normalize_hieroglyphs` first — the definition the frozen B-freq baseline already
#: uses. Without it a line pasted with a variant codepoint (TLA's Z15B U+133FC
#: against the corpus's Z2 U+133E5, the mismatch in Camilla's first trial) would not
#: match a row the corpus holds, and the checker would call a line `new` that the
#: tool has seen. The error that matters here is the missed overlap, so the fold is
#: applied — and whenever it is what made C2 or P3 fire, the evidence says so
#: ("normalised-only"), so the deviation is visible in the report rather than
#: assumed.
SIGNS_RULE = (
    "signs(x) = glyph_key(normalize_hieroglyphs(x)) (scripts.bfreq_baseline.sign_key): "
    "every space, layout control and placeholder removed, after the app's sign "
    "normalisation. Evidence marked 'normalised-only' fired only because of that "
    "normalisation."
)

#: §4a: "plus the yod ꞽ/j/i and spacing-before-`=` folds the tool uses. A fold beyond
#: `search_fold` is reported as its own evidence type and never changes a C/P
#: result." Both named folds are already *inside* `search_fold`
#: (`normalize_transliteration` folds ꞽ/j/ı/i to i, `normalize_mdc` normalises the
#: suffix marker and the space before it) — `tests/test_kri_overlap.py` pins that,
#: so if either ever leaves `search_fold` the suite fails rather than the checker
#: silently losing a fold. `extra_fold` therefore adds only the belt-and-braces
#: whitespace collapse, and anything it finds that the predicates did not is
#: reported as the separate evidence type `EXTRA_FOLD`, which never changes a label.
EXTRA_FOLD_RULE = (
    "extra_fold(x) = search_fold(x) with every run of whitespace collapsed and the "
    "space before '=' removed; reported as EXTRA_FOLD evidence only."
)


def fold(value: object) -> str:
    """§4a `fold`: `app.data.normalizer.search_fold`."""
    return search_fold(value)


def extra_fold(value: object) -> str:
    """`fold` plus the §4a folds the tool uses — see `EXTRA_FOLD_RULE`.

    Never used by C1-C4 or P1-P3. It exists so a match that only an extra fold can
    see is *reported* rather than lost, and labelled as what it is.
    """
    return " ".join(fold(value).replace(" =", "=").split())


def token_set(value: object) -> set[str]:
    """§4a `J`'s token set: `_token_set(loose_reading_form(·))`, both pinned."""
    return _token_set(loose_reading_form(value))


def signs(value: object) -> str:
    """§4a `signs` — see `SIGNS_RULE`."""
    return sign_key(value)


def raw_signs(value: object) -> str:
    """`glyph_key` with no normalisation: the literal reading of §4a's wording.

    Only used to tell whether a C2/P3 hit needed the app's sign normalisation.
    """
    return glyph_key("" if value is None else str(value))


def pinned_jaccard(left: set[str], right: set[str]) -> float:
    """§4a's `J`, exactly as pinned: `scripts.eval_guards.jaccard`, as a float.

    The predicates compare `exact_jaccard` instead, which is the same quantity as a
    rational; `tests/test_kri_overlap.py` pins that the two agree, so the exactness
    is a safer *comparison*, never a different measure.
    """
    return jaccard(left, right)


def exact_jaccard(left: set[str], right: set[str]) -> Fraction:
    """J as an exact rational. `jaccard` (pinned) is asserted to agree, as a float."""
    if not left or not right:
        return Fraction(0)
    return Fraction(len(left & right), len(left | right))


def word_trigrams(words: Sequence[str]) -> set[tuple[str, ...]]:
    """Every contiguous run of exactly three folded words."""
    return {tuple(words[i : i + MIN_RUN_WORDS]) for i in range(len(words) - MIN_RUN_WORDS + 1)}


def sign_trigrams(value: str) -> set[str]:
    """§4a `T(x)`: the contiguous sign trigrams of `signs(x)`."""
    return {value[i : i + 3] for i in range(len(value) - 2)}


def word_bounded(inner: str, outer: str) -> bool:
    """§4a "word-bounded x in y": ` fold(x) ` is a substring of ` fold(y) `."""
    if not inner or not outer:
        return False
    return f" {inner} " in f" {outer} "


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Prepared:
    """Everything the predicates need about one text, computed once."""

    key: str
    source: str
    folded: str
    strict: str
    tokens: frozenset[str]
    words: tuple[str, ...]
    word_runs: frozenset[tuple[str, ...]]
    sign_string: str
    raw_sign_string: str
    sign_runs: frozenset[str]
    extra: str


def prepare(key: str, transliteration: object, hieroglyphs: object, source: str = "") -> Prepared:
    folded = fold(transliteration)
    words = tuple(folded.split())
    sign_string = signs(hieroglyphs)
    return Prepared(
        key=key,
        source=source,
        folded=folded,
        strict=strict_reading_key(transliteration),
        tokens=frozenset(token_set(transliteration)),
        words=words,
        word_runs=frozenset(word_trigrams(words)),
        sign_string=sign_string,
        raw_sign_string=raw_signs(hieroglyphs),
        sign_runs=frozenset(sign_trigrams(sign_string)),
        extra=extra_fold(transliteration),
    )


@dataclass(frozen=True)
class Evidence:
    """One predicate firing against one corpus row."""

    predicate: str
    witness: str
    witness_source: str
    jaccard: Fraction
    detail: str = ""

    @property
    def evidence_type(self) -> str:
        return EVIDENCE_TYPE[self.predicate]

    def describe(self) -> str:
        bits = f"{self.predicate} ({self.evidence_type}) vs {self.witness} J={float(self.jaccard):.3f}"
        return f"{bits} [{self.detail}]" if self.detail else bits


@dataclass
class LineResult:
    """The §4a verdict on one line, with every predicate that fired."""

    line_id: str
    label: str = NEW
    evidence: dict[str, Evidence] = field(default_factory=dict)
    max_jaccard: Fraction = Fraction(0)
    max_jaccard_witness: str = ""
    #: §4d: "the overlap report … shows the Ramses nearest neighbour and its score
    #: for every line, whatever the label" — Ramses is Ramesside Late Egyptian,
    #: shuffled and id-less, so its overlap can only be seen by content.
    nearest_ramses: Fraction = Fraction(0)
    nearest_ramses_witness: str = ""
    rows_checked: int = 0
    #: Exclusion-manifest entries that already cover this line (§4d/§4e).
    excluded_by: tuple[str, ...] = ()

    @property
    def fired(self) -> tuple[str, ...]:
        return tuple(p for p in PREDICATES if p in self.evidence)

    @property
    def runnable(self) -> bool:
        """§4d: "The tool runs only on `new` lines" — and never on an excluded one."""
        return self.label == NEW and not self.excluded_by

    def summary(self) -> str:
        fired = ", ".join(self.evidence[p].describe() for p in self.fired) or "nothing fired"
        return f"{self.line_id}: {self.label} — {fired}"


RAMSES_SOURCE = "Ramses"


# --------------------------------------------------------------------------- the rules


def predicates_for(query: Prepared, row: Prepared) -> dict[str, str]:
    """Which of C1-C4/P1-P3 fire for this (line, row) pair, with their details.

    Returns `{predicate: detail}`; the detail is "" unless something about the hit
    has to be reported (today: a sign match that needed the app's normalisation).
    """
    hits: dict[str, str] = {}
    j = exact_jaccard(set(query.tokens), set(row.tokens))

    # C1 — identical reading, under either identity.
    if (query.strict and query.strict == row.strict) or (query.folded and query.folded == row.folded):
        which = []
        if query.strict and query.strict == row.strict:
            which.append("strict key")
        if query.folded and query.folded == row.folded:
            which.append("search fold")
        hits["C1"] = " + ".join(which)

    # C2 — identical signs, both sides with at least two.
    if (
        len(query.sign_string) >= MIN_C2_SIGNS
        and query.sign_string == row.sign_string
    ):
        hits["C2"] = (
            "" if query.raw_sign_string == row.raw_sign_string else "normalised-only"
        )

    # C3 / P1 — the pinned Jaccard, on either side of 0.70.
    if j >= C3_MIN_JACCARD:
        hits["C3"] = ""
    elif j >= P1_MIN_JACCARD:
        hits["P1"] = ""

    # C4 — the line, three folded words or more, word-bounded inside the row.
    if len(query.words) >= MIN_C4_WORDS and word_bounded(query.folded, row.folded):
        hits["C4"] = ""

    # P2 — a shared contiguous run of three folded words. A row of >= 3 words lying
    # inside the line (UD's second `overlap_partial` branch) shares its own first
    # trigram with the line, so one test covers both directions.
    shared_runs = query.word_runs & row.word_runs
    if shared_runs:
        hits["P2"] = " ".join(min(shared_runs))

    # P3 — shared sign trigrams, as a share of the line's own.
    if (
        len(query.sign_string) >= MIN_TRIGRAM_SIGNS
        and len(row.sign_string) >= MIN_TRIGRAM_SIGNS
        and query.sign_runs
    ):
        shared_runs_count = len(query.sign_runs & row.sign_runs)
        share = Fraction(shared_runs_count, len(query.sign_runs))
        if share >= P3_MIN_TRIGRAM_SHARE:
            # "normalised-only" means the app's sign normalisation is what carried
            # the share over the threshold — not merely that the two sign strings
            # differ, which for P3 they are expected to.
            raw_query = sign_trigrams(query.raw_sign_string)
            raw_share = (
                Fraction(len(raw_query & sign_trigrams(row.raw_sign_string)), len(raw_query))
                if raw_query
                else Fraction(0)
            )
            # Reported as the raw counts, not the reduced fraction: a reader
            # checking the threshold wants |T(q) & T(r)| and |T(q)| themselves.
            hits["P3"] = f"share {shared_runs_count}/{len(query.sign_runs)}" + (
                "" if raw_share >= P3_MIN_TRIGRAM_SHARE else "; normalised-only"
            )

    return hits


def label_for(fired: Iterable[str]) -> str:
    """§4a's fixed precedence: any C beats any P, any P beats nothing."""
    fired = set(fired)
    if fired & set(CONTAINMENT_PREDICATES):
        return CONTAINED
    if fired & set(PARTIAL_PREDICATES):
        return PARTIAL
    return NEW


def check_lines(
    lines: Sequence[Prepared],
    rows: Iterable[Prepared],
) -> list[LineResult]:
    """Run every predicate of every line against every corpus row, in one pass.

    One pass over `rows` so the corpus can be streamed: the KRI set is a handful of
    lines and the corpus is six figures of rows, so the loop belongs this way round.
    For each predicate the witness kept is the one with the highest Jaccard; ties
    keep the first row in corpus order, which makes the report deterministic given
    the corpus.
    """
    results = {line.key: LineResult(line_id=line.key) for line in lines}
    for row in rows:
        for line in lines:
            result = results[line.key]
            result.rows_checked += 1
            j = exact_jaccard(set(line.tokens), set(row.tokens))
            if j > result.max_jaccard:
                result.max_jaccard, result.max_jaccard_witness = j, row.key
            if row.source == RAMSES_SOURCE and (
                not result.nearest_ramses_witness or j > result.nearest_ramses
            ):
                result.nearest_ramses, result.nearest_ramses_witness = j, row.key
            for predicate, detail in predicates_for(line, row).items():
                previous = result.evidence.get(predicate)
                if previous is None or j > previous.jaccard:
                    result.evidence[predicate] = Evidence(
                        predicate=predicate,
                        witness=row.key,
                        witness_source=row.source,
                        jaccard=j,
                        detail=detail,
                    )
            if (
                "C1" not in result.evidence
                and "EXTRA_FOLD" not in result.evidence
                and line.extra
                and line.extra == row.extra
                and line.folded != row.folded
                and line.strict != row.strict
            ):
                result.evidence["EXTRA_FOLD"] = Evidence(
                    predicate="EXTRA_FOLD",
                    witness=row.key,
                    witness_source=row.source,
                    jaccard=j,
                    detail="matches only beyond search_fold; reported, not a C/P result",
                )
    for result in results.values():
        result.label = label_for(result.fired)
    return [results[line.key] for line in lines]


# --------------------------------------------------------------------------- corpora


#: The columns the checker reads from a corpus CSV. `source`/`source_ref` are only
#: used to name witnesses in the report.
CORPUS_COLUMNS = ("transliteration_gold", "hieroglyphs", "source", "source_ref")


def prepare_corpus(frame, *, label: str = "") -> Iterator[Prepared]:
    """Prepare every row of a corpus frame, streamed (never materialised as a list)."""
    columns = {name: (name in frame.columns) for name in CORPUS_COLUMNS}
    for position, row in enumerate(frame.itertuples(index=False)):
        values = {name: (getattr(row, name) if present else "") for name, present in columns.items()}
        source = str(values["source"] or "")
        ref = str(values["source_ref"] or "")
        key = f"{source}:{ref}" if (source or ref) else f"row{position}"
        if label:
            key = f"{label}/{key}"
        yield prepare(
            key=key,
            transliteration=values["transliteration_gold"],
            hieroglyphs=values["hieroglyphs"],
            source=source,
        )


#: The columns a `--lines` file must carry. `hieroglyphs` may be empty for a line
#: supplied as transliteration only; C2/P3 then simply cannot fire.
LINE_COLUMNS = ("line_id", "transliteration", "hieroglyphs")


def prepare_lines(records: Iterable[dict]) -> list[Prepared]:
    """Prepare the lines under test. `records` are plain dicts — never a KRI path."""
    prepared: list[Prepared] = []
    seen: set[str] = set()
    for position, record in enumerate(records):
        line_id = str(record.get("line_id") or f"line{position + 1}").strip()
        if line_id in seen:
            raise ValueError(f"duplicate line_id {line_id!r}: a line is one unit of analysis")
        seen.add(line_id)
        prepared.append(
            prepare(
                key=line_id,
                transliteration=record.get("transliteration", ""),
                hieroglyphs=record.get("hieroglyphs", ""),
                source="(line under test)",
            )
        )
    return prepared
