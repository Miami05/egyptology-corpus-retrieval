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
      python scripts/migrate_example_ids.py --new-csv data/processed/examples.csv \\
        --source TLA --yes

The mapping runs in two passes (Astra #9, 2026-10-25):

1. **Unchanged rows first.** A database row whose composite key `(source,
   source_text_id, source_sentence_id)` is still in the CSV *with the same hieroglyphs
   and transliteration* keeps its id. This is checked before any ambiguity, so the
   52,216 BBAW rows that all share one `source_ref` no longer block a migration of
   another source.
2. **Changed rows, per source, only for the sources named with `--source`.** Inside
   one source a remaining row is matched to a remaining CSV row by `source_ref` plus
   content, or by content alone when it has no `source_ref`. A key that is not unique
   on either side is ambiguous. A row whose text changed is not matched (content is
   checked, not trusted).

The plan must be a bijection before anything is written: every database row is
unchanged or renamed, no two rows get the same new key, and no new key is held by a
row that stays. Otherwise the rows are reported and nothing is touched. Changed rows of
a source that was not named are reported as "not selected" and block the run too, so a
partial migration cannot orphan annotations silently. Renames are applied in two steps
(a temporary id first) so swapped ids do not trip the unique constraint.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402

from app.storage.db import DATABASE_URL, SessionLocal  # noqa: E402
from app.storage.models import Annotation, Example  # noqa: E402

# Prefix of the temporary sentence id used during the two-step rename.
TEMP_PREFIX = "__migrating__"


def _content(hieroglyphs: str, transliteration: str) -> str:
    return f"{(hieroglyphs or '').strip()}\x1f{(transliteration or '').strip()}"


def _key(source_ref: str, hieroglyphs: str, transliteration: str) -> tuple[str, str]:
    """Within-source match key: the raw-source pointer plus the text, else the text.

    The text is part of the key even when there is a `source_ref`, because one
    reference can cover many rows (all BBAW rows share one) and because a pointer
    whose text changed is not the same row any more.
    """
    content = _content(hieroglyphs, transliteration)
    ref = (source_ref or "").strip()
    if ref:
        return ("ref", f"{ref}\x1f{content}")
    return ("text", content)


def _composite(source: str, text_id: str, sentence_id: str) -> tuple[str, str, str]:
    return (str(source or ""), str(text_id or ""), str(sentence_id or ""))


def build_mapping(
    csv_df: pd.DataFrame,
    rows: list[Example],
    sources: "set[str] | None" = None,
) -> dict:
    """Plan the rename. `sources` names the sources whose changed rows may be
    migrated; None allows every source (the dry run's view). Nothing is written."""
    records = csv_df.to_dict("records")
    csv_by_composite: dict[tuple[str, str, str], int] = {}
    csv_duplicates: list[tuple[str, str, str]] = []
    for position, record in enumerate(records):
        composite = _composite(
            record.get("source", ""),
            record.get("source_text_id", ""),
            record.get("source_sentence_id", ""),
        )
        if composite in csv_by_composite:
            csv_duplicates.append(composite)
        csv_by_composite[composite] = position

    # Pass 1: unchanged composite key and unchanged text.
    claimed: set[int] = set()
    unchanged = 0
    pending: dict[str, list[Example]] = defaultdict(list)
    for example in rows:
        composite = _composite(
            example.source, example.source_text_id, example.source_sentence_id
        )
        position = csv_by_composite.get(composite)
        if position is not None and position not in claimed:
            record = records[position]
            if _content(example.hieroglyphs, example.transliteration_gold) == _content(
                str(record.get("hieroglyphs", "")),
                str(record.get("transliteration_gold", "")),
            ):
                claimed.add(position)
                unchanged += 1
                continue
        pending[str(example.source or "")].append(example)

    # Pass 2: changed rows, per selected source, unique keys on both sides.
    csv_unclaimed: dict[str, dict[tuple[str, str], list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for position, record in enumerate(records):
        if position in claimed:
            continue
        csv_unclaimed[str(record.get("source", ""))][
            _key(
                str(record.get("source_ref", "")),
                str(record.get("hieroglyphs", "")),
                str(record.get("transliteration_gold", "")),
            )
        ].append(position)

    renames: list[tuple[Example, str, str]] = []
    unmatched: list[Example] = []
    ambiguous: list[Example] = []
    not_selected: list[Example] = []
    for source, examples in pending.items():
        if sources is not None and source not in sources:
            not_selected.extend(examples)
            continue
        keys = {
            id(example): _key(
                example.source_ref or "",
                example.hieroglyphs or "",
                example.transliteration_gold or "",
            )
            for example in examples
        }
        db_counts = Counter(keys.values())
        for example in examples:
            key = keys[id(example)]
            matches = csv_unclaimed[source].get(key, [])
            if not matches:
                unmatched.append(example)
            elif len(matches) > 1 or db_counts[key] > 1:
                ambiguous.append(example)
            else:
                record = records[matches[0]]
                renames.append(
                    (example, str(record["source_text_id"]), str(record["source_sentence_id"]))
                )

    # Bijection: no two renames share a target, and no target is held by a row that
    # keeps its key (every row not renamed away keeps it).
    renamed_away = {id(example) for example, _, _ in renames}
    held = {
        _composite(example.source, example.source_text_id, example.source_sentence_id)
        for example in rows
        if id(example) not in renamed_away
    }
    targets = Counter(
        _composite(example.source, new_text, new_sentence)
        for example, new_text, new_sentence in renames
    )
    collisions = [
        example
        for example, new_text, new_sentence in renames
        if targets[_composite(example.source, new_text, new_sentence)] > 1
        or _composite(example.source, new_text, new_sentence) in held
    ]

    return {
        "renames": renames,
        "unchanged": unchanged,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "not_selected": not_selected,
        "collisions": collisions,
        "csv_duplicates": csv_duplicates,
    }


def is_applicable(plan: dict) -> bool:
    """True only when every database row is unchanged or renamed one-to-one."""
    return not any(
        plan[key]
        for key in ("unmatched", "ambiguous", "not_selected", "collisions", "csv_duplicates")
    )


def apply_renames(session, renames: list[tuple[Example, str, str]]) -> None:
    """Two-step rename: every row to a temporary key first, then to its new key, so a
    swap of two ids never holds the same key twice at a flush."""
    for example, _, _ in renames:
        example.source_sentence_id = f"{TEMP_PREFIX}{example.id}"
    session.flush()
    for example, new_text, new_sentence in renames:
        example.source_text_id = new_text
        example.source_sentence_id = new_sentence
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-csv",
        default="data/processed/examples.csv",
        help="The regenerated corpus CSV carrying the new ids.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        help=(
            "A source whose changed ids may be migrated (repeatable). Without it the "
            "dry run shows every source's changes, and --yes refuses."
        ),
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

        sources = set(args.source) if args.source else None
        plan = build_mapping(csv_df, rows, sources)
        print(f"  sources   : {', '.join(sorted(sources)) if sources else '(all, dry run)'}")
        print(f"  unchanged : {plan['unchanged']}")
        print(f"  to rename : {len(plan['renames'])}")
        by_source = Counter(str(example.source) for example, _, _ in plan["renames"])
        for source, count in sorted(by_source.items()):
            print(f"    {source}: {count}")
        for key in ("unmatched", "ambiguous", "not_selected", "collisions", "csv_duplicates"):
            print(f"  {key:<14}: {len(plan[key])}")

        for example, new_text, new_sentence in plan["renames"][:5]:
            print(
                f"    {example.source_text_id}/{example.source_sentence_id}"
                f"  ->  {new_text}/{new_sentence}"
            )
        if len(plan["renames"]) > 5:
            print(f"    … and {len(plan['renames']) - 5} more")

        if not is_applicable(plan):
            print(
                "\nRefusing to apply: some database rows do not map one-to-one onto "
                "the new CSV (or belong to a source not named with --source). Renaming "
                "only part of the corpus would orphan the annotations on the rest."
            )
            raise SystemExit(1)

        if not plan["renames"]:
            print("\nNothing to do — the database already carries these ids.")
            return

        if not args.yes:
            print("\nDry run. Re-run with --yes and --source <name> to apply.")
            return
        if sources is None:
            print("\nRefusing to apply without --source: name the sources to migrate.")
            raise SystemExit(1)

        apply_renames(session, plan["renames"])
        print(f"\nRenamed {len(plan['renames'])} rows; annotations kept their example ids.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
