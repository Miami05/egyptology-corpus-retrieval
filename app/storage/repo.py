from __future__ import annotations

from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Annotation, EvaluationResult, Example, RetrievalRun


def _coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


class ExampleRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_source_keys(
        self,
        source: str,
        source_text_id: str,
        source_sentence_id: str,
    ) -> Example | None:
        stmt = (
            select(Example)
            .where(Example.source == source)
            .where(Example.source_text_id == source_text_id)
            .where(Example.source_sentence_id == source_sentence_id)
        )
        return self.session.scalars(stmt).first()

    def add_or_get_example(self, **kwargs) -> tuple[Example, bool]:
        existing = self.get_by_source_keys(
            source=kwargs["source"],
            source_text_id=kwargs["source_text_id"],
            source_sentence_id=kwargs["source_sentence_id"],
        )
        if existing is not None:
            return existing, False
        example = Example(**kwargs)
        self.session.add(example)
        self.session.commit()
        self.session.refresh(example)
        return example, True

    def upsert_example(self, **kwargs) -> tuple[Example, bool, list[str]]:
        """Insert a corpus row, or refresh the corpus fields of an existing one.

        `add_or_get_example` leaves existing rows untouched, so a re-import after the
        importer improves (e.g. deriving a real period from the TLA dates) never
        reached the database. This updates the corpus columns in place and keeps the
        row's id, so saved annotations stay attached.

        Returns (example, created, changed_fields).
        """
        existing = self.get_by_source_keys(
            source=kwargs["source"],
            source_text_id=kwargs["source_text_id"],
            source_sentence_id=kwargs["source_sentence_id"],
        )
        if existing is None:
            example = Example(**kwargs)
            self.session.add(example)
            self.session.commit()
            self.session.refresh(example)
            return example, True, []

        # The source keys identify the row; never rewrite them.
        immutable = {"source", "source_text_id", "source_sentence_id"}
        changed: list[str] = []
        for field, new_value in kwargs.items():
            if field in immutable or not hasattr(existing, field):
                continue
            if getattr(existing, field) != new_value:
                setattr(existing, field, new_value)
                changed.append(field)
        if changed:
            self.session.commit()
            self.session.refresh(existing)
        return existing, False, changed

    def list_examples(self) -> list[Example]:
        stmt = select(Example).order_by(Example.id.asc())
        return list(self.session.scalars(stmt).all())

    def get_example(self, example_id: int) -> Example | None:
        return self.session.get(Example, example_id)


class AnnotationRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_annotation(
        self,
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
    ) -> Annotation:
        annotation = Annotation(
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
        self.session.add(annotation)
        self.session.commit()
        self.session.refresh(annotation)
        return annotation

    def list_for_example(self, example_id: int) -> list[Annotation]:
        stmt = (
            select(Annotation)
            .where(Annotation.example_id == example_id)
            .order_by(Annotation.created_at.desc(), Annotation.id.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_latest_for_example(self, example_id: int) -> Annotation | None:
        rows = self.list_for_example(example_id)
        return rows[0] if rows else None

    def list_all_annotations(self) -> list[Annotation]:
        stmt = select(Annotation).order_by(
            Annotation.created_at.desc(), Annotation.id.desc()
        )
        return list(self.session.scalars(stmt).all())

    def list_latest_annotations_only(self) -> list[Annotation]:
        rows = self.list_all_annotations()
        latest_by_example: OrderedDict[int, Annotation] = OrderedDict()
        for row in rows:
            if row.example_id not in latest_by_example:
                latest_by_example[row.example_id] = row

        return list(latest_by_example.values())


class RetrievalRunRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log_run(
        self,
        query_mdc: str,
        query_mdc_norm: str,
        query_reading_order: str,
        query_reading_order_norm: str,
        top_example_ids: str,
        top_scores: str,
    ) -> RetrievalRun:
        row = RetrievalRun(
            query_mdc=query_mdc,
            query_mdc_norm=query_mdc_norm,
            query_reading_order=query_reading_order,
            query_reading_order_norm=query_reading_order_norm,
            top_example_ids=top_example_ids,
            top_scores=top_scores,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row


class EvaluationRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_result(
        self,
        example_id: int,
        rank_of_gold: int,
        top1_score: float,
        top3_ids: str,
    ) -> EvaluationResult:
        row = EvaluationResult(
            example_id=example_id,
            rank_of_gold=rank_of_gold,
            top1_score=top1_score,
            top3_ids=top3_ids,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row
