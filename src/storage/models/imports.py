#!/usr/bin/python3

"""Database models for managing word imports and exclusions."""

import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Boolean, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .schema import Base


class PendingImport(Base):
    """Model for storing words pending import with disambiguation context."""

    __tablename__ = "pending_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    english_word: Mapped[str] = mapped_column(String, nullable=False, index=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    disambiguation_translation: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Foreign language word
    disambiguation_language: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "lt", "fr"

    # POS and categorization (optional, especially for verbs where subtypes are incomplete)
    pos_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # noun, verb, adjective, adverb
    pos_subtype: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # e.g., animals, physical_action

    # Example sentence showing this word in context (helps LLM pick the right sense)
    example_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional metadata
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Where this came from
    frequency_rank: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # From word frequency data
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    synonym_candidates = relationship(
        "PendingImportSynonymCandidate",
        back_populates="pending_import",
        cascade="all, delete-orphan",
    )


class PendingImportSynonymCandidate(Base):
    """Potential existing lemma match for a pending import."""

    __tablename__ = "pending_import_synonym_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pending_import_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pending_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lemma_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lemmas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_text: Mapped[str] = mapped_column(String, nullable=False)
    same_pos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_synonym_category: Mapped[str] = mapped_column(String, nullable=False)
    llm_synonym_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    matched_translation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_translation_languages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    candidate_translations: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_strong: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    pending_import = relationship("PendingImport", back_populates="synonym_candidates")
    lemma = relationship("Lemma")


class WordExclusion(Base):
    """Model for storing words to exclude from import/processing."""

    __tablename__ = "word_exclusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    excluded_word: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)  # Which language
    exclusion_reason: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., "truncation", "artifact", "profanity"
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
