"""Re-point corpus rows in the database when the importer's id scheme changes.

Annotations attach to an `examples.id`, and `attach_db_ids` matches a CSV row to
that database row by `(source, source_text_id, source_sentence_id)`. So renaming
source ids — which is exactly what switching from positional to content-derived ids
does — silently orphans every saved annotation: the corpus row is still there, the
CSV row is still there, and nothing links them any more.

`ensure_corpus_ready` cannot help, because it only seeds an *empty* corpus table.
This script does the rename in place, keeping every `examples.id` and therefore every
annotation, and refuses to run unless the mapping is unambiguous.

Usage — always dry run first:

    # what would change
    python scripts/migrate_example_ids.py --new-csv data/processed/examples.csv

    # apply it (against production, pass the production URL explicitly)
    DATABASE_URL='postgresql://...' \\
      python scripts/migrate_example_ids.py --new-csv data/processed/examples.csv --yes

The mapping is by content, not by position: a database row is matched to a CSV row
by its `source_ref` when both have one (the raw-source pointer, which survives an id
change), otherwise by the exact hieroglyphs + transliteration pair. Rows that cannot
be matched one-to-one are reported and left untouched.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402

from app.storage.db import DATABASE_URL, SessionLocal  # noqa: E402
from app.storage.models import Annotation, Example  # noqa: E402


def _key(source_ref: str, hieroglyphs: str, transliteration: str) -> tuple[str, str]:
    """Content key: the raw-source pointer if present, else the text itself."""
    ref = (source_ref or "").strip()
    if ref:
        return ("ref", ref)
    return ("text", f"{(hieroglyphs or '').strip()}\x1f{(transliteration or '').strip()}")


def build_mapping(csv_df: pd.DataFrame, rows: list[Example]) -> dict:
    """Match database rows to CSV rows by content, reporting anything ambiguous."""
    csv_by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, row in csv_df.iterrows():
        csv_by_key[
            _key(
                str(row.get("source_ref", "")),
                str(row.get("hieroglyphs", "")),
                str(row.get("transliteration_gold", "")),
            )
        ].append(position)

    renames: list[tuple[Example, str, str]] = []
    unchanged = 0
    unmatched: list[Example] = []
    ambiguous: list[Example] = []

    for example in rows:
        key = _key(
            example.source_ref or "",
            example.hieroglyphs or "",
            example.transliteration_gold or "",
        )
        matches = csv_by_key.get(key, [])
        if not matches:
            unmatched.append(example)
            continue
        if len(matches) > 1:
            ambiguous.append(example)
            continue
        csv_row = csv_df.loc[matches[0]]
        new_text_id = str(csv_row["source_text_id"])
        new_sentence_id = str(csv_row["source_sentence_id"])
        if (example.source_text_id, example.source_sentence_id) == (
            new_text_id,
            new_sentence_id,
        ):
            unchanged += 1
        else:
            renames.append((example, new_text_id, new_sentence_id))

    return {
        "renames": renames,
        "unchanged": unchanged,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-csv",
        default="data/processed/examples.csv",
        help="The regenerated corpus CSV carrying the new ids.",
    )
    parser.add_argument("--yes", action="store_true", help="Apply the rename.")
    args = parser.parse_args()

    print(f"database: {DATABASE_URL.split('@')[-1]}")
    csv_df = pd.read_csv(args.new_csv).fillna("")
    print(f"new CSV : {args.new_csv} ({len(csv_df)} rows)")

    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Example)).all())
        annotation_count = session.query(Annotation).count()
        print(f"database holds {len(rows)} corpus rows and {annotation_count} annotations\n")

        plan = build_mapping(csv_df, rows)
        print(f"  unchanged : {plan['unchanged']}")
        print(f"  to rename : {len(plan['renames'])}")
        print(f"  unmatched : {len(plan['unmatched'])}")
        print(f"  ambiguous : {len(plan['ambiguous'])}")

        for example, new_text, new_sentence in plan["renames"][:5]:
            print(
                f"    {example.source_text_id}/{example.source_sentence_id}"
                f"  ->  {new_text}/{new_sentence}"
            )
        if len(plan["renames"]) > 5:
            print(f"    … and {len(plan['renames']) - 5} more")

        if plan["unmatched"] or plan["ambiguous"]:
            print(
                "\nRefusing to apply: some database rows do not map one-to-one onto "
                "the new CSV. Renaming only part of the corpus would orphan the "
                "annotations on the rest."
            )
            raise SystemExit(1)

        if not plan["renames"]:
            print("\nNothing to do — the database already carries these ids.")
            return

        if not args.yes:
            print("\nDry run. Re-run with --yes to apply.")
            return

        for example, new_text, new_sentence in plan["renames"]:
            example.source_text_id = new_text
            example.source_sentence_id = new_sentence
        session.commit()
        print(f"\nRenamed {len(plan['renames'])} rows; annotations kept their example ids.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
