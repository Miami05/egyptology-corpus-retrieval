"""Write every reviewed example (base corpus fields + latest annotation) to a CSV.

The rows and the per-row licence column come from the same serializer the in-app
"Download reviewed annotations CSV" button uses (`app.ui.review_common`), so the two
exports cannot drift apart. That serializer carries `language_stage`, which is what
lets a TLA row get the credit of its own TLA corpus (Earlier Egyptian, Late Egyptian
or Demotic) rather than the generic all-corpora notice; the hand-built row dict this
script used to keep had no stage column (review of the 2026-10-11 audit fixes).
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import review_common  # noqa: E402

OUTPUT_PATH = "data/processed/reviewed_annotations_export.csv"


def main() -> None:
    # CC BY-SA 4.0: this file redistributes adapted corpus text, so the attribution
    # (one licence cell per row, via with_licence_notice) has to travel with it.
    csv_text = review_common.build_reviewed_export_csv()
    out = Path(OUTPUT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(csv_text, encoding="utf-8")
    try:
        rows = len(pd.read_csv(StringIO(csv_text)))
    except pd.errors.EmptyDataError:
        rows = 0
    print(f"Exported {rows} reviewed rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
