"""The B-freq baseline is frozen: the committed sha256s must still be the truth.

`docs/kri-bfreq-baseline-2026-10-26.md` records the sha256 of every file that decides
what B-freq answers, because §4e of the 2026-10-26 plan only lets endpoint G count
toward a confirmation if the baseline was "implemented, unit-tested on synthetic
fixtures and committed with its sha256 before any 4e material arrives".

A baseline nobody can re-identify is not frozen, so this test fails loudly the moment
one of those files changes without the document being re-frozen with it. That failure
is the correct outcome, not an inconvenience.

**Three layers, because file hashes alone are not enough** (review of 2026-10-26):

1. the three repo files of the baseline itself;
2. the *dependency* functions in the app that decide normalisation, identity and
   folding. B-freq imports them rather than re-implementing them, so a change there
   changes what B-freq answers while leaving its own files untouched. They are pinned
   by one combined digest over `inspect.getsource` of each, with the per-function
   digests printed on failure so the culprit is obvious;
3. golden key vectors. Source hashing cannot see the module-level regexes, tables and
   constants those functions read — `SIGN_VARIANTS`, the sign classes, the plural and
   weak-consonant folds. The vectors pin the behaviour those data produce, which is
   what actually decides a lookup.

Deliberately *not* pinned: the corpus sha256 and the table sha256s. The corpus
legitimately changes in part 1 (cleanup) and part 3 (PT admission), each of which
amends the document with a rebuilt table. Pinning them would turn an expected,
documented event into a red suite in an unrelated workstream. The document says how
that amendment works; this file guards the code and the behaviour.
"""

from __future__ import annotations

import hashlib
import inspect
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from app.data import normalizer
from app.services import suggestions
from app.services.reading_model import ReadingModel
from scripts import bfreq_baseline as bf
from scripts import import_ud_egyptian_pc as ud

DOC = PROJECT_ROOT / "docs" / "kri-bfreq-baseline-2026-10-26.md"

FROZEN_FILES = (
    "scripts/bfreq_baseline.py",
    "scripts/build_bfreq_table.py",
    "tests/test_bfreq_baseline.py",
)

#: Every function B-freq imports that can change what it answers.
PINNED_DEPENDENCIES = {
    "app.data.normalizer.normalize_hieroglyphs": normalizer.normalize_hieroglyphs,
    "app.data.normalizer.normalize_transliteration": normalizer.normalize_transliteration,
    "app.data.normalizer.normalize_mdc": normalizer.normalize_mdc,
    "app.data.normalizer.search_fold": normalizer.search_fold,
    "app.data.normalizer.fold_plural_marker": normalizer.fold_plural_marker,
    "app.data.normalizer.fold_weak_consonant_marker": normalizer.fold_weak_consonant_marker,
    "app.data.normalizer.fold_letter_variants": normalizer.fold_letter_variants,
    "app.services.suggestions.strict_reading_key": suggestions.strict_reading_key,
    "app.services.reading_model.ReadingModel.fit": ReadingModel.fit,
    "scripts.import_ud_egyptian_pc.glyph_key": ud.glyph_key,
    "scripts.import_ud_egyptian_pc.is_hieroglyph": ud.is_hieroglyph,
}

#: Behaviour the data behind those functions must keep producing. Each line is
#: (what it pins, the callable's name, input, expected output).
GOLDEN_VECTORS = (
    ("variant sign fold Z15B -> Z2", "sign_key", "\U000133FC", "\U000133E5"),
    ("plain sign survives", "sign_key", "\U00013000", "\U00013000"),
    ("variation selector dropped", "sign_key", "\U00013000︀", "\U00013000"),
    ("spacing dropped", "sign_key", " \U00013000 \U00013001 ", "\U00013000\U00013001"),
    ("<g> placeholder is not a sign", "sign_key", "<g>US9No2</g>", ""),
    ("weak-consonant notation folds", "reading_key", "ḏi̯=f", "ḏꞽ=f"),
    ("brackets and dots leave the identity", "reading_key", "n(.ꞽ).t", "nꞽt"),
    ("plural marker folds to .w", "reading_key", "šms.pl", "šmsw"),
    ("consonants stay distinct", "reading_key", "ꜣb", "ꜣb"),
    ("consonants stay distinct", "reading_key", "ꜥb", "ꜥb"),
    ("the ASCII fold is not the identity", "folded_reading_key", "ꜣb", "ab"),
    ("the ASCII fold merges ꜣ and ꜥ", "folded_reading_key", "ꜥb", "ab"),
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dependency_digests() -> dict[str, str]:
    return {
        name: sha256_text(inspect.getsource(func))
        for name, func in sorted(PINNED_DEPENDENCIES.items())
    }


def combined_dependency_digest() -> str:
    """One digest over every pinned dependency's source, in name order."""
    parts = [f"{name}\n{digest}" for name, digest in sorted(dependency_digests().items())]
    return sha256_text("\n".join(parts))


def recorded_hashes() -> dict[str, str]:
    """The ``| `path` | sha256 `…` |`` rows of the freeze table."""
    text = DOC.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name in FROZEN_FILES:
        match = re.search(rf"`{re.escape(name)}`\s*\|\s*sha256 `([0-9a-f]{{64}})`", text)
        if match:
            found[name] = match.group(1)
    return found


def recorded_dependency_digest() -> str:
    match = re.search(
        r"combined dependency digest[^`]*`([0-9a-f]{64})`",
        DOC.read_text(encoding="utf-8"),
        re.IGNORECASE,
    )
    assert match, "the document must record the combined dependency digest"
    return match.group(1)


# ---------------------------------------------------------------------------
# layer 1: the baseline's own files
# ---------------------------------------------------------------------------


def test_the_freeze_document_exists_and_records_every_frozen_file():
    assert DOC.exists(), f"{DOC} is the freeze record for endpoint G and must exist"
    assert set(recorded_hashes()) == set(FROZEN_FILES)


@pytest.mark.parametrize("name", FROZEN_FILES)
def test_the_frozen_file_still_has_its_recorded_sha256(name):
    recorded = recorded_hashes()[name]
    actual = hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
    assert actual == recorded, (
        f"{name} changed after the B-freq freeze.\n"
        f"  recorded in {DOC.name}: {recorded}\n"
        f"  on disk now:            {actual}\n"
        "If this change is intended, re-freeze: update the sha256 in the document "
        "in the SAME commit, and note in it whether any KRI material had already "
        "been seen."
    )


# ---------------------------------------------------------------------------
# layer 2: the app functions B-freq imports
# ---------------------------------------------------------------------------


def test_the_pinned_dependencies_have_not_drifted():
    """B-freq imports these rather than copying them, so a change there is a change here."""
    actual = combined_dependency_digest()
    recorded = recorded_dependency_digest()
    assert actual == recorded, (
        "a function B-freq depends on changed after the freeze.\n"
        f"  recorded: {recorded}\n  now:      {actual}\n"
        "Per-function digests, to find which:\n"
        + "\n".join(f"    {name}  {digest}" for name, digest in dependency_digests().items())
        + "\nIf the change is intended, re-freeze the digest in "
        f"{DOC.name} in the SAME commit and record what it did to the table."
    )


def test_every_pinned_dependency_is_one_b_freq_actually_uses():
    """A pin on something unused would be noise; a missing pin would be a hole.

    "Uses" includes transitively: `is_hieroglyph` is never named in
    `bfreq_baseline.py`, but `glyph_key` calls it on every character, so it decides
    the sign key just as directly.
    """
    reachable = (PROJECT_ROOT / "scripts" / "bfreq_baseline.py").read_text(encoding="utf-8")
    reachable += "\n".join(inspect.getsource(func) for func in PINNED_DEPENDENCIES.values())
    for name in PINNED_DEPENDENCIES:
        assert name.rsplit(".", 1)[1] in reachable, name


# ---------------------------------------------------------------------------
# layer 3: behaviour, which source hashing cannot see
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("what,func_name,value,expected", GOLDEN_VECTORS)
def test_the_golden_key_vectors_still_hold(what, func_name, value, expected):
    func = getattr(bf, func_name)
    assert func(value) == expected, (
        f"{what}: {func_name}({value!r}) is now {func(value)!r}, was {expected!r}. "
        "The tables were built under the old behaviour, so they must be rebuilt and "
        "the document re-frozen."
    )


# ---------------------------------------------------------------------------
# what the document has to say
# ---------------------------------------------------------------------------


def doc_prose() -> str:
    """The document as one line of prose, with Markdown furniture removed.

    Blockquote markers and emphasis sit *between* words once the text is collapsed,
    so a required sentence would never be found literally. Stripping them lets the
    checks below assert the wording rather than the formatting.
    """
    text = DOC.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^\s*>\s?", "", text)  # blockquote markers
    text = text.replace("**", "").replace("*", "")
    return " ".join(text.split())


def test_the_document_records_the_corpus_and_the_tables():
    """The other things that identify the table, present but not pinned here."""
    text = DOC.read_text(encoding="utf-8")
    assert "44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2" in text
    assert "bfreq_table_all.csv" in text and "bfreq_table_late_egyptian.csv" in text
    assert "130,472" in text


def test_the_document_states_the_rules_a_rebuilder_needs():
    text = doc_prose()
    assert "strict_reading_key" in bf.TIE_BREAK_RULE and "code point" in bf.TIE_BREAK_RULE
    assert "code-point order" in text
    assert "count, descending" in text
    # The surface rule is load-bearing since the folded-scorer fix, so it must be
    # written down, not only in the code.
    assert "most frequent attested surface spelling" in text


def test_the_document_states_the_deviation_from_the_pre_arrival_freeze():
    """§4e wants the freeze before the material ARRIVES. It was not. Say so plainly."""
    text = doc_prose()
    assert "not the pre-arrival freeze §4e requires" in text
    assert "exploratory" in text
    assert "This was not independently verified." in text
    assert "endpoint R is unaffected" in text


def test_the_document_declares_the_unkeyable_gold_group_treatment():
    text = doc_prose()
    assert "counted and reported before scoring" in text
    assert "no difficult group is excluded after predictions are seen" in text


def test_the_document_flags_the_missing_segment_to_gold_span_mapping():
    text = doc_prose()
    assert "no evaluator maps app segments onto gold spans" in text
