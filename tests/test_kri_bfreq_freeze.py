"""The B-freq baseline is frozen: the committed sha256s must still be the truth.

`docs/kri-bfreq-baseline-2026-10-26.md` records the sha256 of every file that decides
what B-freq answers, because §4e of the 2026-10-26 plan only lets endpoint G count
toward a confirmation if the baseline was "implemented, unit-tested on synthetic
fixtures and committed with its sha256 **before** any 4e material arrives".

A baseline nobody can re-identify is not frozen, so this test fails loudly the moment
one of those files changes without the document being re-frozen with it. That failure
is the correct outcome, not an inconvenience: per §4e a change after material has been
seen retires the set, and before that it simply means the document must be amended in
the same commit.

Deliberately *not* pinned here: the corpus sha256 and the table sha256s. The corpus
legitimately changes in part 1 (cleanup) and part 3 (PT admission), each of which
amends the document with a rebuilt table. Pinning them would turn an expected,
documented event into a red suite in an unrelated workstream. The document says how
that amendment works; this test guards the code.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

DOC = PROJECT_ROOT / "docs" / "kri-bfreq-baseline-2026-10-26.md"

FROZEN_FILES = (
    "scripts/bfreq_baseline.py",
    "scripts/build_bfreq_table.py",
    "tests/test_bfreq_baseline.py",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_hashes() -> dict[str, str]:
    """The `| `path` | sha256 `…` |` rows of the freeze table."""
    text = DOC.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name in FROZEN_FILES:
        match = re.search(
            rf"`{re.escape(name)}`\s*\|\s*sha256 `([0-9a-f]{{64}})`", text
        )
        if match:
            found[name] = match.group(1)
    return found


def test_the_freeze_document_exists_and_records_every_frozen_file():
    assert DOC.exists(), f"{DOC} is the freeze record for endpoint G and must exist"
    assert set(recorded_hashes()) == set(FROZEN_FILES)


@pytest.mark.parametrize("name", FROZEN_FILES)
def test_the_frozen_file_still_has_its_recorded_sha256(name):
    recorded = recorded_hashes()[name]
    actual = sha256_file(PROJECT_ROOT / name)
    assert actual == recorded, (
        f"{name} changed after the B-freq freeze.\n"
        f"  recorded in {DOC.name}: {recorded}\n"
        f"  on disk now:            {actual}\n"
        "If this change is intended, re-freeze: update the sha256 in the document "
        "in the SAME commit, and note in it whether any KRI material had already "
        "been seen — if it had, plan 2026-10-26 §4e retires endpoint G to "
        "exploratory."
    )


def test_the_document_records_the_corpus_and_the_tables():
    """The other three things that identify the table, present but not pinned here."""
    text = DOC.read_text(encoding="utf-8")
    assert re.search(r"`44543932a3c83d76b823d5498ce0054b746fae6abb884e97e2650398f39df1e2`", text)
    assert "bfreq_table_all.csv" in text and "bfreq_table_late_egyptian.csv" in text
    assert "130,472" in text


def test_the_document_states_the_tie_break_and_the_freeze_claim():
    from scripts.bfreq_baseline import TIE_BREAK_RULE

    text = " ".join(DOC.read_text(encoding="utf-8").split())
    # The two halves of the tie-break must both be stated in the document, because
    # a reader rebuilding the table has only the document to go on.
    assert "strict_reading_key" in TIE_BREAK_RULE and "code point" in TIE_BREAK_RULE
    assert "code-point order" in text
    assert "count, descending" in text
    assert "before any KRI content was opened" in text
