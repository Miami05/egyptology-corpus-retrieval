from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import SessionLocal
from app.storage.repo import AnnotationRepo, ExampleRepo

OUTPUT_PATH = "data/processed/reviewed_annotations_export.csv"


def main() -> None:
    session = SessionLocal()
    try:
        example_repo = ExampleRepo(session)
        annotation_repo = AnnotationRepo(session)

        latest_annotations = {
            row.example_id: row
            for row in annotation_repo.list_latest_annotations_only()
        }
        examples = example_repo.list_examples_by_ids(list(latest_annotations))

        export_rows: list[dict] = []
        for example in examples:
            latest = latest_annotations.get(example.id)
            if latest is None:
                continue

            export_rows.append(
                {
                    "example_id": example.id,
                    "source": example.source,
                    "source_text_id": example.source_text_id,
                    "source_sentence_id": example.source_sentence_id,
                    "genre": example.genre,
                    "period": example.period,
                    "mdc": example.mdc,
                    "sign_sequence": example.sign_sequence,
                    "transliteration_gold": example.transliteration_gold,
                    "translation": example.translation,
                    "formula_type": example.formula_type,
                    "deity": example.deity,
                    "recipient": example.recipient,
                    "offering_items": example.offering_items,
                    "formula_slot": example.formula_slot,
                    "base_display_sequence": example.display_sequence,
                    "base_normalized_reading_order": example.normalized_reading_order,
                    "base_alt_transliterations": example.alt_transliterations,
                    "base_variant_writing_note": example.variant_writing_note,
                    "base_morphology_note": example.morphology_note,
                    "base_syntax_note": example.syntax_note,
                    "base_aesthetic_arrangement_flag": bool(
                        example.aesthetic_arrangement_flag
                    ),
                    "latest_transliteration": latest.transliteration,
                    "latest_status": latest.status,
                    "latest_uncertainty_note": latest.uncertainty_note or "",
                    "latest_grammar_note": latest.grammar_note or "",
                    "latest_display_sequence": latest.display_sequence or "",
                    "latest_normalized_reading_order": latest.normalized_reading_order
                    or "",
                    "latest_alt_transliterations": latest.alt_transliterations or "",
                    "latest_variant_writing_note": latest.variant_writing_note or "",
                    "latest_morphology_note": latest.morphology_note or "",
                    "latest_syntax_note": latest.syntax_note or "",
                    "latest_aesthetic_arrangement_flag": bool(
                        latest.aesthetic_arrangement_flag
                    ),
                    "source_ref": example.source_ref,
                    "latest_annotation_created_at": latest.created_at,
                }
            )

        df = pd.DataFrame(export_rows)
        Path("data/processed").mkdir(parents=True, exist_ok=True)
        df.to_csv(OUTPUT_PATH, index=False)
        print(f"Exported {len(df)} reviewed rows to {OUTPUT_PATH}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
