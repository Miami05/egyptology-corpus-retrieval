"""`_derive_period` in scripts/import_tla_dataset.py: the date-range -> period map.

Before the Demotic import, every TLA date range was negative (BCE), so the map had
never been exercised with a positive (CE) year. The Demotic corpus is dated up to
+475, past the Roman Period's conventional 395 CE upper bound.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_tla_dataset import _derive_period  # noqa: E402


def test_a_roman_period_date_range_is_labelled_roman_period() -> None:
    """201..250 CE (a real Demotic row) has midpoint 225.5, inside -30..395."""
    assert _derive_period("201", "250") == "Roman Period"


def test_a_date_range_spanning_the_bce_ce_boundary_is_roman_period() -> None:
    """-10..40 straddles year 0; the midpoint (15) still falls in the Roman range."""
    assert _derive_period("-10", "40") == "Roman Period"


def test_a_late_period_date_range_is_still_labelled_correctly() -> None:
    """A pre-existing (BCE-only) range must still resolve after adding Roman Period."""
    assert _derive_period("-664", "-626") == "Late Period"


def test_a_date_range_past_the_roman_period_falls_back_to_undated_range() -> None:
    """451..475 CE (an actual Demotic row) is dated but past 395, the Roman upper
    bound, so it should be reported rather than silently mislabelled."""
    assert _derive_period("451", "475") == "Undated range (451 to 475)"
