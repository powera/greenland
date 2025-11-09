#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Text, Float, ForeignKey, TIMESTAMP, Boolean, func, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

class WordToken(Base):
    """Model for storing word tokens - the specific letters/spelling of a word in a specific language."""
    __tablename__ = 'word_tokens'
    __table_args__ = (
        UniqueConstraint('token', 'language_code', name='uq_word_token_language'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, nullable=False, index=True)
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "en", "lt", "zh", "fr"
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
    guid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)  # e.g., N14_001
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # For which Trakaido "level"
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Combined frequency rank
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tags
    
    # Language-specific translations of the lemma concept
    chinese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., 吃
    french_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., manger
    korean_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., 먹다
    swahili_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., kula
    lithuanian_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., valgyti
    vietnamese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., ăn
    
    # Metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    derivative_forms = relationship("DerivativeForm", back_populates="lemma", cascade="all, delete-orphan")
    grammar_facts = relationship("GrammarFact", back_populates="lemma", cascade="all, delete-orphan")
    translations = relationship("LemmaTranslation", back_populates="lemma", cascade="all, delete-orphan")
    difficulty_overrides = relationship("LemmaDifficultyOverride", back_populates="lemma", cascade="all, delete-orphan")

class LemmaTranslation(Base):
    """Model for storing translations of lemmas in various languages.

    This table replaces the individual language columns (french_translation, etc.)
    on the Lemma table to support scalable multi-language translations.
    """
    __tablename__ = 'lemma_translations'
    __table_args__ = (
        UniqueConstraint('lemma_id', 'language_code', name='uq_lemma_translation'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "fr", "es", "de"
    translation: Mapped[str] = mapped_column(String, nullable=False)  # Base form of the translation

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    lemma = relationship("Lemma", back_populates="translations")

class LemmaDifficultyOverride(Base):
    """Model for storing per-language difficulty level overrides for lemmas.

    This allows different Trakaido levels for the same word across languages.
    For example, 筷子 (chopsticks) might be level 2 in Chinese but level 8 in German.
    A difficulty_level of -1 means the word should be excluded from that language's wordlist.
    """
    __tablename__ = 'lemma_difficulty_overrides'
    __table_args__ = (
        UniqueConstraint('lemma_id', 'language_code', name='uq_lemma_difficulty_override'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "zh", "fr", "de"
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False)  # Trakaido level (1-20) or -1 to exclude

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Reason for override
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    lemma = relationship("Lemma", back_populates="difficulty_overrides")

class DerivativeForm(Base):
    """Model for storing derivative forms - language-specific combinations of WordToken and Lemma with grammatical information.
    
    For single-word forms (e.g., "eating"), word_token_id links to the WordToken for frequency data.
    For multi-word forms (e.g., "to eat", "have eaten"), word_token_id is NULL and only derivative_form_text is used.
    Application logic determines which single word (if any) to link for frequency purposes.
    
    Note: When word_token_id is present, the language_code must match the WordToken's language_code.
    """
    __tablename__ = 'derivative_forms'
    __table_args__ = (
        UniqueConstraint('lemma_id', 'language_code', 'grammatical_form', 'derivative_form_text', name='uq_derivative_form'),
    )
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)
    
    # The actual text of this derivative form (single or multi-word)
    derivative_form_text: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "eating", "to eat", "have eaten"
    
    # Optional link to WordToken for frequency data (single-word forms only)
    word_token_id: Mapped[Optional[int]] = mapped_column(ForeignKey("word_tokens.id"), nullable=True)
    
    # Language specification - must match the WordToken's language_code when word_token_id is present
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "en", "lt", "zh", "fr"
    
    # Grammatical form information (language-specific)
    grammatical_form: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "gerund", "1st_person_singular_present", "infinitive"
    is_base_form: Mapped[bool] = mapped_column(Boolean, default=False)  # True for infinitive verbs, singular nouns, etc.
    
    # Pronunciations for this specific form
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Metadata
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
