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
