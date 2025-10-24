#!/usr/bin/python3

"""Database models for managing word imports and exclusions."""

import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from .schema import Base


class PendingImport(Base):
    """Model for storing words pending import with disambiguation context."""
    __tablename__ = 'pending_imports'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    english_word: Mapped[str] = mapped_column(String, nullable=False, index=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    disambiguation_translation: Mapped[str] = mapped_column(String, nullable=False)  # Foreign language word
    disambiguation_language: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "lt", "fr"

    # POS and categorization (optional, especially for verbs where subtypes are incomplete)
    pos_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)  # noun, verb, adjective, adverb
    pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)  # e.g., animals, physical_action

    # Optional metadata
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Where this came from
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # From word frequency data
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())


class WordExclusion(Base):
    """Model for storing words to exclude from import/processing."""
    __tablename__ = 'word_exclusions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    excluded_word: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)  # Which language
    exclusion_reason: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "truncation", "artifact", "profanity"
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
