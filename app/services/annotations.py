from __future__ import annotations

from app.storage.repo import AnnotationRepo


def _coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


def save_annotation(
    repo: AnnotationRepo,
    example_id: int,
    transliteration: str,
    uncertainty_note: str = "",
    grammar_note: str = "",
    status: str = "edited",
    display_sequence: str = "",
    normalized_reading_order: str = "",
    alt_transliterations: str = "",
    variant_writing_note: str = "",
    morphology_note: str = "",
    syntax_note: str = "",
    aesthetic_arrangement_flag: bool = False,
):
    return repo.add_annotation(
        example_id=example_id,
        transliteration=transliteration,
        uncertainty_note=uncertainty_note,
        grammar_note=grammar_note,
        status=status,
        display_sequence=display_sequence,
        normalized_reading_order=normalized_reading_order,
        alt_transliterations=alt_transliterations,
        variant_writing_note=variant_writing_note,
        morphology_note=morphology_note,
        syntax_note=syntax_note,
        aesthetic_arrangement_flag=_coerce_bool(aesthetic_arrangement_flag),
    )
