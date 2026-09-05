from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.storage.models import Annotation, EvaluationResult, Example


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

    def upsert_example(
        self, dry_run: bool = False, **kwargs
    ) -> tuple[Example | None, bool, list[str]]:
        """Insert a corpus row, or refresh the corpus fields of an existing one.

        `add_or_get_example` leaves existing rows untouched, so a re-import after the
        importer improves (e.g. deriving a real period from the TLA dates) never
        reached the database. This updates the corpus columns in place and keeps the
        row's id, so saved annotations stay attached.

        With `dry_run=True` nothing is written: the same comparison runs, but neither
        the new row nor any field change is committed, so the caller can report what a
        real run *would* do. The returned example is None for a would-be insert then.

        Returns (example, created, changed_fields).
        """
        existing = self.get_by_source_keys(
            source=kwargs["source"],
            source_text_id=kwargs["source_text_id"],
            source_sentence_id=kwargs["source_sentence_id"],
        )
        if existing is None:
            if dry_run:
                return None, True, []
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
                if not dry_run:
                    setattr(existing, field, new_value)
                changed.append(field)
        if changed and not dry_run:
            self.session.commit()
            self.session.refresh(existing)
        return existing, False, changed

    def list_examples(self) -> list[Example]:
        stmt = select(Example).order_by(Example.id.asc())
        return list(self.session.scalars(stmt).all())

    def list_example_keys(self) -> list[tuple[int, str, str, str]]:
        """(id, source, source_text_id, source_sentence_id) for every example.

        Deliberately not `list_examples()`: that pulls every corpus column over the
        wire, and on hosted Postgres downloading the full corpus on each boot is what
        exhausted the free tier's data-transfer quota. The id map only needs these
        four columns.
        """
        stmt = select(
            Example.id,
            Example.source,
            Example.source_text_id,
            Example.source_sentence_id,
        ).order_by(Example.id.asc())
        return [tuple(row) for row in self.session.execute(stmt).all()]

    def list_examples_by_ids(self, ids: list[int]) -> list[Example]:
        """Full rows, but only for the given ids.

        Exports only need the annotated examples — a handful of rows — so fetching
        the whole corpus first and discarding most of it wastes the same hosted
        egress that `list_example_keys` exists to avoid.
        """
        if not ids:
            return []
        stmt = select(Example).where(Example.id.in_(ids)).order_by(Example.id.asc())
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
        """Most recent annotation for one example, in one query.

        This used to call `list_for_example`, so asking for "the latest" re-ran the
        full history query — the Workspace issued the same SELECT twice per result
        row, on every rerun, including every keystroke in a note field.
        """
        stmt = (
            select(Annotation)
            .where(Annotation.example_id == example_id)
            .order_by(Annotation.created_at.desc(), Annotation.id.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def latest_ids(self) -> list[int]:
        """Ids of the newest annotation per example, computed in the database.

        The Python version pulled *every* annotation ever written to pick one per
        example — the query that grows without bound as the tool is used.
        """
        newest = (
            select(func.max(Annotation.id).label("id"))
            .group_by(Annotation.example_id)
            .subquery()
        )
        return [row[0] for row in self.session.execute(select(newest.c.id)).all()]

    def annotated_example_ids(self) -> list[int]:
        """Distinct example ids that have at least one annotation.

        Home and Projects only need the count of reviewed examples; fetching whole
        annotation rows to count them is what made a sidebar click scan the table.
        """
        stmt = select(Annotation.example_id).distinct()
        return [row[0] for row in self.session.execute(stmt).all()]

    def count_annotated_examples(self) -> int:
        stmt = select(func.count(func.distinct(Annotation.example_id)))
        return int(self.session.execute(stmt).scalar_one())

    def latest_for_examples(self, example_ids: list[int]) -> dict[int, Annotation]:
        """Latest annotation for each of many examples, in one round trip."""
        if not example_ids:
            return {}
        newest = (
            select(func.max(Annotation.id).label("id"))
            .where(Annotation.example_id.in_(example_ids))
            .group_by(Annotation.example_id)
            .subquery()
        )
        stmt = select(Annotation).join(newest, Annotation.id == newest.c.id)
        return {row.example_id: row for row in self.session.scalars(stmt).all()}

    def list_for_examples(self, example_ids: list[int]) -> list[Annotation]:
        """Full annotation history for several examples, newest first, in one query."""
        if not example_ids:
            return []
        stmt = (
            select(Annotation)
            .where(Annotation.example_id.in_(example_ids))
            .order_by(Annotation.created_at.desc(), Annotation.id.desc())
        )
        return list(self.session.scalars(stmt).all())

    def list_all_annotations(self) -> list[Annotation]:
        stmt = select(Annotation).order_by(
            Annotation.created_at.desc(), Annotation.id.desc()
        )
        return list(self.session.scalars(stmt).all())

    def list_latest_annotations_only(self) -> list[Annotation]:
        """Newest annotation per example, selected in the database."""
        ids = self.latest_ids()
        if not ids:
            return []
        stmt = (
            select(Annotation)
            .where(Annotation.id.in_(ids))
            .order_by(Annotation.created_at.desc(), Annotation.id.desc())
        )
        return list(self.session.scalars(stmt).all())


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
