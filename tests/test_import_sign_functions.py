"""The sign-function table: Nederhof's XML in, `data/processed/sign_functions.csv` out.

The committed CSV is checked here too, because it is a redistributed data file under a
different licence from everything else in `data/processed/` (CC BY 4.0, credited to
Mark-Jan Nederhof by his grant of 2026-09-04) and its attribution must not go missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_sign_functions import COLUMNS, FUNCTIONS, convert  # noqa: E402

TABLE_PATH = PROJECT_ROOT / "data" / "processed" / "sign_functions.csv"

# signuse.xml, sign A3, verbatim; signunicode.xml gives A3 its codepoint.
SIGNUSE = """<?xml version="1.0" encoding="UTF-8"?>
<signlist>
<p>Prose that is not a sign entry.</p>
<sign id="A3">
<det>
<al root="Hms">Hmsj</al>
<tr>sit</tr>
    <example>
        <hi>N41:z-A3</hi>
    </example>
</det>
<p>Cf. <signref name="A30" /></p>
</sign>
<sign id="A1">
<logdet plural="true">
<group>A1:Z2</group>
<al>rHw</al>
<tr>men</tr>
</logdet>
</sign>
</signlist>
"""

SIGNUNICODE = """<?xml version="1.0" encoding="UTF-8"?>
<signlist>
<sign id="A1" code="0x13000" />
<sign id="A3" code="0x13002" />
</signlist>
"""


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    (tmp_path / "signuse.xml").write_text(SIGNUSE, encoding="utf-8")
    (tmp_path / "signunicode.xml").write_text(SIGNUNICODE, encoding="utf-8")
    return tmp_path


def test_one_row_per_function_element_with_the_sign_as_a_character(
    raw_dir: Path,
) -> None:
    frame, stats = convert(raw_dir)
    assert list(frame.columns) == COLUMNS
    assert len(frame) == 2  # the two `<p>` elements are prose, not functions
    assert stats["signs"] == 2
    assert set(frame["sign"]) == {"𓀂", "𓀀"}
    assert set(frame["codepoint"]) == {"U+13002", "U+13000"}


def test_the_transliteration_is_converted_and_the_root_kept(raw_dir: Path) -> None:
    frame, _ = convert(raw_dir)
    row = frame[frame["gardiner"] == "A3"].iloc[0]
    assert row["function"] == "determinative"
    assert row["value"] == "ḥmsꞽ"  # Hmsj, his yod is `j`
    assert row["meaning"] == "sit"
    assert row["qualifier"] == "root=ḥms"


def test_a_reading_that_belongs_to_a_combination_records_the_group(
    raw_dir: Path,
) -> None:
    frame, _ = convert(raw_dir)
    row = frame[frame["gardiner"] == "A1"].iloc[0]
    assert row["function"] == "logogram or determinative"
    assert row["group"] == "A1:Z2"
    assert row["qualifier"] == "plural=true"


def test_every_row_carries_the_attribution(raw_dir: Path) -> None:
    frame, _ = convert(raw_dir)
    assert (frame["source_note"] != "").all()
    assert frame["source_note"].str.contains("Nederhof").all()
    assert frame["source_note"].str.contains("CC BY 4.0").all()


def test_the_committed_table_matches_the_schema_and_the_documented_classes() -> None:
    if not TABLE_PATH.exists():
        pytest.skip("sign_functions.csv has not been built")
    frame = pd.read_csv(TABLE_PATH, keep_default_na=False)
    assert list(frame.columns) == COLUMNS
    assert set(frame["function"]) <= set(FUNCTIONS.values())
    assert (frame["gardiner"] != "").all()
    assert (frame["sign"] != "").all()
    assert frame["source_note"].str.contains("Nederhof").all()
