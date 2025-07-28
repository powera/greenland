#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Text, Float, ForeignKey, TIMESTAMP, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

class WordToken(Base):
    """Model for storing word tokens - the specific letters/spelling of a word."""
    __tablename__ = 'word_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Combined harmonic mean rank
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    derivative_forms = relationship("DerivativeForm", back_populates="word_token", cascade="all, delete-orphan")
    frequencies = relationship("WordFrequency", back_populates="word_token", cascade="all, delete-orphan")

class Lemma(Base):
    """Model for storing lemmas - specific concepts and their base meanings."""
    __tablename__ = 'lemmas'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_text: Mapped[str] = mapped_column(String, nullable=False, index=True)
    definition_text: Mapped[str] = mapped_column(Text, nullable=False)
    pos_type: Mapped[str] = mapped_column(String, nullable=False)  # Part of speech
    pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Dictionary generation fields
    guid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)  # e.g., N14001
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)  # e.g., body_parts, colors
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # For which Trakaido "level"
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Combined frequency rank
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tags
    
    # Metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    derivative_forms = relationship("DerivativeForm", back_populates="lemma", cascade="all, delete-orphan")

class DerivativeForm(Base):
    """Model for storing derivative forms - specific combinations of WordToken and Lemma with grammatical information."""
    __tablename__ = 'derivative_forms'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_token_id: Mapped[int] = mapped_column(ForeignKey("word_tokens.id"), nullable=False)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)
    
    # Grammatical form information
    grammatical_form: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "gerund", "present_participle", "infinitive"
    is_base_form: Mapped[bool] = mapped_column(Boolean, default=False)  # True for infinitive verbs, singular nouns, etc.
    
    # Pronunciations for this specific form
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Translations for this specific form
    chinese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    french_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    korean_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    swahili_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lithuanian_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vietnamese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Special flags
    multiple_meanings: Mapped[bool] = mapped_column(Boolean, default=False)
    special_case: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    word_token = relationship("WordToken", back_populates="derivative_forms")
    lemma = relationship("Lemma", back_populates="derivative_forms")
    example_sentences = relationship("ExampleSentence", back_populates="derivative_form", cascade="all, delete-orphan")

class ExampleSentence(Base):
    """Model for storing example sentences for a derivative form."""
    __tablename__ = 'example_sentences'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    derivative_form_id: Mapped[int] = mapped_column(ForeignKey("derivative_forms.id"), nullable=False)
    example_text: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    derivative_form = relationship("DerivativeForm", back_populates="example_sentences")

class Corpus(Base):
    """Model for storing corpus information."""
    __tablename__ = 'corpus'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    corpus_weight: Mapped[float] = mapped_column(Float, default=1.0)  # Overall weight of this corpus in calculations (0.0-1.0)
    max_unknown_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Max rank for words not in this corpus (penalty/placeholder)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # Whether to include in calculations
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=True)
    
    # Relationships
    word_frequencies = relationship("WordFrequency", back_populates="corpus", cascade="all, delete-orphan")

class WordFrequency(Base):
    """Model for storing word frequency in different corpora - tied to WordToken."""
    __tablename__ = 'word_frequencies'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_token_id: Mapped[int] = mapped_column(ForeignKey("word_tokens.id"), nullable=False)
    corpus_id: Mapped[int] = mapped_column(ForeignKey("corpus.id"), nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Optional raw frequency
    
    # Relationships
    word_token = relationship("WordToken", back_populates="frequencies")
    corpus = relationship("Corpus", back_populates="word_frequencies")
