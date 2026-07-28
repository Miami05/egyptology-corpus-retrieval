from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExampleRow(BaseModel):
    source: str = Field(..., description="Corpus/source name")
    source_text_id: str
    source_sentence_id: str
    language_stage: Optional[str] = ""
    script_type: Optional[str] = ""
    genre: str
    period: str
    hieroglyphs: Optional[str] = ""
    mdc: str
    sign_sequence: str
    transliteration_gold: str
    translation: Optional[str] = ""
    lemma_sequence: Optional[str] = ""
    upos: Optional[str] = ""
    glossing: Optional[str] = ""
    grammar_notes: Optional[str] = ""
    source_ref: Optional[str] = ""
    review_status: str = "seed"


class AnnotationInput(BaseModel):
    example_id: int
    transliteration: str
    uncertainty_note: str = ""
    grammar_note: str = ""
    status: str = "edited"


class RetrievalResult(BaseModel):
    example_id: int
    source: str
    source_text_id: str
    source_sentence_id: str
    mdc: str
    sign_sequence: str
    transliteration_gold: str
    translation: str
    score: float
    evidence: str
