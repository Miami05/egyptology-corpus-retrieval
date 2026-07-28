from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class Example(Base):
    __tablename__ = "examples"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_text_id",
            "source_sentence_id",
            name="uq_examples_source_text_sentence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100))
    source_text_id: Mapped[str] = mapped_column(String(100))
    source_sentence_id: Mapped[str] = mapped_column(String(100))
    language_stage: Mapped[str] = mapped_column(String(100), default="")
    script_type: Mapped[str] = mapped_column(String(100), default="")
    genre: Mapped[str] = mapped_column(String(100))
    period: Mapped[str] = mapped_column(String(100))
    hieroglyphs: Mapped[str] = mapped_column(Text, default="")
    mdc: Mapped[str] = mapped_column(Text)
    sign_sequence: Mapped[str] = mapped_column(Text)
    transliteration_gold: Mapped[str] = mapped_column(Text)
    translation: Mapped[str] = mapped_column(Text, default="")
    lemma_sequence: Mapped[str] = mapped_column(Text, default="")
    upos: Mapped[str] = mapped_column(Text, default="")
    glossing: Mapped[str] = mapped_column(Text, default="")
    grammar_notes: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(50), default="seed")
    formula_type: Mapped[str] = mapped_column(String(100), default="")
    deity: Mapped[str] = mapped_column(String(100), default="")
    recipient: Mapped[str] = mapped_column(String(100), default="")
    offering_items: Mapped[str] = mapped_column(Text, default="")
    formula_slot: Mapped[str] = mapped_column(String(100), default="")
    display_sequence: Mapped[str] = mapped_column(Text, default="")
    normalized_reading_order: Mapped[str] = mapped_column(Text, default="")
    alt_transliterations: Mapped[str] = mapped_column(Text, default="")
    variant_writing_note: Mapped[str] = mapped_column(Text, default="")
    morphology_note: Mapped[str] = mapped_column(Text, default="")
    syntax_note: Mapped[str] = mapped_column(Text, default="")
    aesthetic_arrangement_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    mdc_norm: Mapped[str] = mapped_column(Text)
    sign_sequence_norm: Mapped[str] = mapped_column(Text)
    transliteration_norm: Mapped[str] = mapped_column(Text)
    formula_type_norm: Mapped[str] = mapped_column(String(100), default="")
    deity_norm: Mapped[str] = mapped_column(String(100), default="")
    recipient_norm: Mapped[str] = mapped_column(String(100), default="")
    offering_items_norm: Mapped[str] = mapped_column(Text, default="")
    formula_slot_norm: Mapped[str] = mapped_column(String(100), default="")
    display_sequence_norm: Mapped[str] = mapped_column(Text, default="")
    normalized_reading_order_norm: Mapped[str] = mapped_column(Text, default="")
    alt_transliterations_norm: Mapped[str] = mapped_column(Text, default="")
    annotations: Mapped[list["Annotation"]] = relationship(
        back_populates="example",
        cascade="all, delete-orphan",
    )


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    example_id: Mapped[int] = mapped_column(ForeignKey("examples.id"))
    transliteration: Mapped[str] = mapped_column(Text)
    uncertainty_note: Mapped[str] = mapped_column(Text, default="")
    grammar_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="edited")
    display_sequence: Mapped[str] = mapped_column(Text, default="")
    normalized_reading_order: Mapped[str] = mapped_column(Text, default="")
    alt_transliterations: Mapped[str] = mapped_column(Text, default="")
    variant_writing_note: Mapped[str] = mapped_column(Text, default="")
    morphology_note: Mapped[str] = mapped_column(Text, default="")
    syntax_note: Mapped[str] = mapped_column(Text, default="")
    aesthetic_arrangement_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    example: Mapped["Example"] = relationship(back_populates="annotations")


class RetrievalRun(Base):
    __tablename__ = "retrieval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_mdc: Mapped[str] = mapped_column(Text)
    query_mdc_norm: Mapped[str] = mapped_column(Text)
    query_reading_order: Mapped[str] = mapped_column(Text, default="")
    query_reading_order_norm: Mapped[str] = mapped_column(Text, default="")
    top_example_ids: Mapped[str] = mapped_column(Text)
    top_scores: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    example_id: Mapped[int] = mapped_column(Integer)
    rank_of_gold: Mapped[int] = mapped_column(Integer, default=999)
    top1_score: Mapped[float] = mapped_column(Float, default=0.0)
    top3_ids: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
