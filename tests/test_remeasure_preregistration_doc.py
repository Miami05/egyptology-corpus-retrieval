"""docs/remeasure-preregistration-2026-10-25.md agrees with the scripts it runs.

Final eval, 2026-10-25: the pre-registration must run as written, so its shell blocks
may not use a variable they never set, its release-check comparison must name the runs
`verify_release.py` really makes, its floor clamp must give floors `verify_release.py`
accepts, and the paste eval's `--help` must state its real `--stage` default. Nothing
here runs an evaluation or reads the corpus.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import verify_release  # noqa: E402

DOC = PROJECT_ROOT / "docs" / "remeasure-preregistration-2026-10-25.md"


def _part_a() -> str:
    text = DOC.read_text(encoding="utf-8")
    return text.split("# (B) Confirmation", 1)[0]


def test_part_a_shell_blocks_set_every_variable_they_use():
    blocks = "\n".join(re.findall(r"```bash\n(.*?)```", _part_a(), flags=re.S))
    assigned = set(re.findall(r"(?:^|[\s;)])([A-Z][A-Z0-9_]*)=", blocks, flags=re.M))
    assigned |= set(re.findall(r"\bfor ([A-Z][A-Z0-9_]*) in\b", blocks))
    used = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]*)", blocks))
    assert used - assigned == set()


def test_release_check_is_compared_with_the_runs_verify_release_makes():
    assert verify_release.LEGACY_RUN["expected_tokens"] == "frozen"  # i.e. L, not C
    prose = " ".join(_part_a().split())
    assert "C-auto or L-auto" not in prose
    assert "v4 **L-auto**" in prose and "v4 **T-auto**" in prose


def test_rule_8_clamp_gives_floors_verify_release_accepts():
    match = re.search(r"clamped to \[([0-9.]+), 1\]", _part_a())
    assert match, "rule 8 no longer states its clamp"
    lowest = float(match.group(1))
    floors = verify_release.validate_floors(
        {"top3_useful_floor": lowest, "mrr_floor": lowest}, "rule 8"
    )
    assert floors["top3_useful_floor"] == lowest


def test_paste_eval_help_states_the_real_stage_default():
    script = PROJECT_ROOT / "scripts" / "run_expert_paste_eval.py"
    out = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, check=True, cwd=PROJECT_ROOT,
    ).stdout
    flat = " ".join(out.split())
    assert "'auto' (default)" in flat
    assert "'none' (default)" not in flat


# --- A7, 2026-10-26: the amendment is a dated addendum, never an edit of the old rule ---

ORIGINAL_A22 = (
    "2. **Urk. IV gate:** PASTE_001–004 pass in auto and declared; with the private rows loaded\n"
    "   (the script prints the resolved directory and a private row count > 0) the St Andrews\n"
    "   row for Camilla's line is rank 1 among St Andrews rows and the 8 pastes still pass. If\n"
    "   the private rows are not loaded, the St Andrews half is \"not run\", never \"passed\"."
)


def test_the_original_a2_2_rule_text_is_unchanged():
    """Attempt 1 was judged against this text; A7 supersedes it without rewriting it."""
    assert ORIGINAL_A22 in DOC.read_text(encoding="utf-8")


def test_a7_amends_a2_2_and_keeps_attempt_1_failed():
    text = DOC.read_text(encoding="utf-8")
    assert "## A7 — Specification correction (2026-10-26, after attempt 1)" in text
    a7 = text.split("## A7 — Specification correction", 1)[1]
    flat = " ".join(a7.split())
    # the amendment is dated, supersedes rather than edits, and leaves attempt 1 failed
    assert "amends" in flat and "is not edited" in flat
    assert "attempt 1 stays **FAILED**" in flat
    # the rank is reported, not gated; presence of the pinned row still gates
    assert "rank among St Andrews rows is reported, not gated" in flat
    assert "S_urkIV-001_urkIV-001Tr_0003" in flat
    # no substituting a gold transliteration to make the paste gate pass
    assert "gold-transliteration query must not be substituted" in flat
    # attempt 2 re-runs all of (A) and the floors come from it alone
    assert "re-runs **all** of (A)" in flat
    assert "remeasure-2026-10-25-attempt1" in flat


def test_a7_gate_block_runs_the_script_in_both_stage_modes():
    a7 = DOC.read_text(encoding="utf-8").split("## A7 — Specification correction", 1)[1]
    block = re.search(r"```bash\n(.*?)```", a7, flags=re.S)
    assert block, "A7 no longer carries its gate command block"
    body = block.group(1)
    assert "for M in auto declared" in body
    assert "urkiv_standrews_$M.txt" in body


def test_the_gate_script_no_longer_judges_the_rank():
    from scripts import check_standrews_urkiv_gate as gate

    assert gate.gate_verdict(8, 8) == []
    assert gate.gate_verdict(1, 8) == ["paste checks 1/8"]
