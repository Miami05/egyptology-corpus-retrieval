"""The KRI test tooling is frozen: the committed sha256s must still be the truth.

The B-freq freeze record (`docs/kri-bfreq-baseline-2026-10-26.md`, "Still to be done",
step 1) requires the app-segment → gold-span mapping to be "built, tested and frozen
before any scoring run". The 2026-10-26 review round (Opus finding 9) extended that to
every script that decides what a KRI run counts: the overlap predicates and checker,
the manifest, the declaration, the mapping, the statistics and the driver. Their
sha256s are recorded in `docs/kri-official-test-tooling-2026-10-26.md`, and this test
fails the moment one changes without that record being re-frozen in the same commit.

A failure here is the correct outcome, not an inconvenience: after KRI material is in
sight, a change to any of these files is a change to the experiment.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DOC = PROJECT_ROOT / "docs" / "kri-official-test-tooling-2026-10-26.md"
BFREQ_DOC = PROJECT_ROOT / "docs" / "kri-bfreq-baseline-2026-10-26.md"

FROZEN_TOOLING = (
    "scripts/check_overlap.py",
    "scripts/kri_declaration.py",
    "scripts/kri_exclusion_manifest.py",
    "scripts/kri_overlap.py",
    "scripts/kri_segment_mapping.py",
    "scripts/kri_stats.py",
    "scripts/run_kri_endpoints.py",
)


def recorded_hashes() -> dict[str, str]:
    """The ``| `path` | sha256 `…` |`` rows of the tooling freeze table (last wins)."""
    text = DOC.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name in FROZEN_TOOLING:
        matches = re.findall(rf"`{re.escape(name)}`\s*\|\s*sha256 `([0-9a-f]{{64}})`", text)
        if matches:
            found[name] = matches[-1]
    return found


def test_the_tooling_doc_records_every_frozen_file():
    assert set(recorded_hashes()) == set(FROZEN_TOOLING)


@pytest.mark.parametrize("name", FROZEN_TOOLING)
def test_the_frozen_tooling_file_still_has_its_recorded_sha256(name):
    recorded = recorded_hashes()[name]
    actual = hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
    assert actual == recorded, (
        f"{name} changed after the KRI tooling freeze.\n"
        f"  recorded in {DOC.name}: {recorded}\n"
        f"  on disk now:            {actual}\n"
        "If the change is intended, re-freeze: append the new sha256 to the record in the "
        "SAME commit, and state whether any KRI result had already been seen."
    )


def test_the_repeated_group_rule_is_amended_into_the_bfreq_record():
    """The B-freq record's "(all three are misses)" parenthetical is superseded, in
    writing, by an appended amendment — the record itself is append-only."""
    from scripts.kri_segment_mapping import REPEATED_GROUP_RULE

    text = " ".join(BFREQ_DOC.read_text(encoding="utf-8").split())
    assert "Amendment 2026-10-26 (rev. 3): repeated gold groups" in text
    assert REPEATED_GROUP_RULE in text
