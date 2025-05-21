#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Text, Float, ForeignKey, TIMESTAMP, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from wordfreq.models.translations import TranslationSet

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

class Word(Base):
    """Model for storing word information."""
    __tablename__ = 'words'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships - now to definitions instead of directly to POS and lemmas
    definitions = relationship("Definition", back_populates="word", cascade="all, delete-orphan")
    frequencies = relationship("WordFrequency", back_populates="word", cascade="all, delete-orphan")

class Definition(Base):
    """Model for storing definitions of a word."""
    __tablename__ = 'definitions'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False)
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # IPA pronunciation
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Phonetic pronunciation
    definition_text: Mapped[str] = mapped_column(Text, nullable=False)
    pos_type: Mapped[str] = mapped_column(String, nullable=False)  # Part of speech for this definition
    pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Store the subtype as string for flexibility
    lemma: Mapped[str] = mapped_column(String, nullable=False)     # Lemma for this definition
    chinese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    french_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    korean_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    swahili_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lithuanian_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vietnamese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Special flags for handling complex cases (moved from POS to definition level)
    multiple_meanings: Mapped[bool] = mapped_column(Boolean, default=False)
    special_case: Mapped[bool] = mapped_column(Boolean, default=False)
    
    confidence: Mapped[float] = mapped_column(Integer, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    word = relationship("Word", back_populates="definitions")
    examples = relationship("Example", back_populates="definition", cascade="all, delete-orphan")

class Example(Base):
    """Model for storing example sentences for a definition."""
    __tablename__ = 'examples'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("definitions.id"), nullable=False)
    example_text: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    definition = relationship("Definition", back_populates="examples")

class QueryLog(Base):
    """Model for tracking LLM queries for auditing and debugging."""
    __tablename__ = 'query_logs'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String, nullable=False)
    query_type: Mapped[str] = mapped_column(String, nullable=False)  # 'definition', 'examples', etc.
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Corpus(Base):
    """Model for storing corpus information."""
    __tablename__ = 'corpus'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)
    
    # Relationships
    word_frequencies = relationship("WordFrequency", back_populates="corpus", cascade="all, delete-orphan")

class WordFrequency(Base):
    """Model for storing word frequency in different corpora."""
    __tablename__ = 'word_frequencies'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False)
    corpus_id: Mapped[int] = mapped_column(ForeignKey("corpus.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=True)
    frequency: Mapped[float] = mapped_column(Float, nullable=True)  # Optional raw frequency
    
    # Relationships
    word = relationship("Word", back_populates="frequencies")
    corpus = relationship("Corpus", back_populates="word_frequencies")


# Add relationship to Word model - is this needed?
Word.frequencies = relationship("WordFrequency", back_populates="word", cascade="all, delete-orphan")
