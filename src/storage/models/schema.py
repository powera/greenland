#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    literal_column,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from storage.models.pgvector import PGVector
from storage.rhyme_keys import sync_derivative_form_rhyme_key


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


SYNONYM_GRAMMATICAL_FORMS: frozenset[str] = frozenset(
    {
        "synonym",
        "synonym_near",
        "synonym_regional",
        "synonym_register",
        "synonym_synecdoche",
        "synonym_related",
        "synonym_spelling",
    }
)

# Non-inflection grammatical forms that can legitimately repeat per
# (lemma, language) — same shape semantics as synonyms (list, not dict).
# True inflectional grammatical_form values (e.g. "singular",
# "verb/en_3s_present") are expected to be unique per (lemma, language).
NON_INFLECTION_GRAMMATICAL_FORMS: frozenset[str] = SYNONYM_GRAMMATICAL_FORMS | frozenset(
    {"abbreviation", "expanded_form"}
)


# Sense prominence values for Lemma.sense_prominence.
# Used to split shared-token frequency across competing lemmas (homographs).
SENSE_PROMINENCE_VERY_COMMON: str = "very_common"
SENSE_PROMINENCE_COMMON: str = "common"
SENSE_PROMINENCE_UNCOMMON: str = "uncommon"
SENSE_PROMINENCE_RARE: str = "rare"
SENSE_PROMINENCE_VALUES: frozenset[str] = frozenset(
    {
        SENSE_PROMINENCE_VERY_COMMON,
        SENSE_PROMINENCE_COMMON,
        SENSE_PROMINENCE_UNCOMMON,
        SENSE_PROMINENCE_RARE,
    }
)
SENSE_PROMINENCE_WEIGHTS: dict[str, float] = {
    SENSE_PROMINENCE_VERY_COMMON: 20.0,
    SENSE_PROMINENCE_COMMON: 5.0,
    SENSE_PROMINENCE_UNCOMMON: 1.0,
    SENSE_PROMINENCE_RARE: 0.15,
}


class WordToken(Base):
    """Model for storing word tokens - the specific letters/spelling of a word in a specific language."""

    __tablename__ = "word_tokens"
    __table_args__ = (UniqueConstraint("token", "language_code", name="uq_word_token_language"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, nullable=False, index=True)
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "en", "lt", "zh", "fr"
    frequency_rank: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Combined harmonic mean rank
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    derivative_forms = relationship(
        "DerivativeForm", back_populates="word_token", cascade="all, delete-orphan"
    )


class Lemma(Base):
    """Model for storing lemmas - specific concepts and their base meanings."""

    __tablename__ = "lemmas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_text: Mapped[str] = mapped_column(String, nullable=False, index=True)
    definition_text: Mapped[str] = mapped_column(Text, nullable=False)
    pos_type: Mapped[str] = mapped_column(String, nullable=False)  # Part of speech
    pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Dictionary generation fields
    guid: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True, index=True
    )  # e.g., N14_001
    difficulty_level: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # For which Trakaido "level"
    # Combined frequency rank: weighted harmonic mean across enabled wordfreq
    # corpora and YLE/CEFR tier signals. Batch-computed by
    # ``wordfreq.frequency.combined_rank``; refresh via ``pradzia --calc-ranks``
    # after bulk lemma/form/tier changes.
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tags
    # Emoji representation(s) of this concept, e.g. ["🐕", "🐶"] for "dog".
    # Treated as a semi-language attached directly to the lemma rather than a
    # row in lemma_translations; stored as a JSON-encoded array of strings.
    emoji: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Concept-level reason this lemma may not have a conventional native lexical
    # item in historical/classical languages. Example: "post-classical technology".
    lexical_gap_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Language-specific translations of the lemma concept
    chinese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., 吃
    french_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., manger
    korean_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., 먹다
    swahili_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., kula
    lithuanian_translation: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., valgyti
    vietnamese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., ăn

    # Disambiguation for polysemes (e.g., "mouse (animal)" vs "mouse (computer)")
    disambiguation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Sense prominence: how prominent this sense is when its surface form is shared
    # with other lemmas (homographs). Drives weighted split of token frequency in
    # wordfreq.lexeme_frequency. One of SENSE_PROMINENCE_VALUES; default "common".
    # For lemmas with no homograph competition, the value has no effect on the rollup.
    sense_prominence: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=SENSE_PROMINENCE_COMMON,
        default=SENSE_PROMINENCE_COMMON,
    )

    # Metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    derivative_forms = relationship(
        "DerivativeForm", back_populates="lemma", cascade="all, delete-orphan"
    )
    grammar_facts = relationship(
        "GrammarFact", back_populates="lemma", cascade="all, delete-orphan"
    )
    translations = relationship(
        "LemmaTranslation", back_populates="lemma", cascade="all, delete-orphan"
    )
    difficulty_overrides = relationship(
        "LemmaDifficultyOverride", back_populates="lemma", cascade="all, delete-orphan"
    )
    relation_memberships = relationship(
        "LemmaRelationMember", back_populates="lemma", cascade="all, delete-orphan"
    )
    embeddings = relationship(
        "LemmaEmbedding", back_populates="lemma", cascade="all, delete-orphan"
    )
    tiers = relationship("LemmaTier", back_populates="lemma", cascade="all, delete-orphan")


class LemmaTranslation(Base):
    """Model for storing translations of lemmas in various languages.

    This table replaces the individual language columns (french_translation, etc.)
    on the Lemma table to support scalable multi-language translations.

    Now includes definition_text to support definitions in multiple languages.
    """

    __tablename__ = "lemma_translations"
    __table_args__ = (UniqueConstraint("lemma_id", "language_code", name="uq_lemma_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "fr", "es", "de", "en"
    translation: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # Base form of the translation (indexed for search)
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # IPA pronunciation for the lemma/base translation
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Simplified/romanized pronunciation for the lemma/base translation
    definition_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # Definition in this language
    sort_key: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # Romanized/phonetic form for sorting (e.g. pinyin for zh, kana for ja, jamo for ko)

    # Disambiguation for translations that share the same word in the target language.
    # E.g., Lithuanian "oda" can mean both "skin" and "leather", so we store a
    # Lithuanian disambiguator like "žmogaus" or "medžiaga" to display alongside.
    disambiguation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Marks translations that are useful learner cues but not ordinary historical
    # vocabulary, e.g. Neo-Latin, modern loans, or descriptive Sanskrit coinages.
    # Suggested values: conventional, late_construction, modern_loan, descriptive,
    # uncertain.
    translation_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    translation_status_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lemma = relationship("Lemma", back_populates="translations")


class LemmaDifficultyOverride(Base):
    """Model for storing per-language difficulty level overrides for lemmas.

    This allows different Trakaido levels for the same word across languages.
    For example, 筷子 (chopsticks) might be level 2 in Chinese but level 8 in German.
    A difficulty_level of -1 means the word should be excluded from that language's wordlist.
    """

    __tablename__ = "lemma_difficulty_overrides"
    __table_args__ = (
        UniqueConstraint("lemma_id", "language_code", name="uq_lemma_difficulty_override"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "zh", "fr", "de"
    difficulty_level: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Trakaido level (1-20) or -1 to exclude

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Reason for override
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lemma = relationship("Lemma", back_populates="difficulty_overrides")


class LemmaEmbedding(Base):
    """Vector embeddings for semantic lemma similarity search."""

    __tablename__ = "lemma_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "lemma_id",
            "language_code",
            "text_source",
            "model_name",
            name="uq_lemma_embedding",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False, index=True)
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    text_source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[str] = mapped_column(PGVector(1536), nullable=False)  # type: ignore[arg-type]
    embedding_norm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    lemma = relationship("Lemma", back_populates="embeddings")


class DerivativeForm(Base):
    """Model for storing derivative forms - language-specific combinations of WordToken and Lemma with grammatical information.

    For single-word forms (e.g., "eating"), word_token_id links to the WordToken for frequency data.
    For multi-word forms (e.g., "to eat", "have eaten"), word_token_id is NULL and only derivative_form_text is used.
    Application logic determines which single word (if any) to link for frequency purposes.

    Note: When word_token_id is present, the language_code must match the WordToken's language_code.
    """

    __tablename__ = "derivative_forms"
    __table_args__ = (
        UniqueConstraint(
            "lemma_id",
            "language_code",
            "grammatical_form",
            "derivative_form_text",
            name="uq_derivative_form",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False)

    # The actual text of this derivative form (single or multi-word)
    derivative_form_text: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "eating", "to eat", "have eaten"

    # Optional link to WordToken for frequency data (single-word forms only)
    word_token_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("word_tokens.id"), nullable=True
    )

    # Language specification - must match the WordToken's language_code when word_token_id is present
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "en", "lt", "zh", "fr"

    # Grammatical form information (language-specific)
    grammatical_form: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., "gerund", "1st_person_singular_present", "infinitive"
    is_base_form: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # True for infinitive verbs, singular nouns, etc.

    # Pronunciations for this specific form
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Rhyme family key derived from IPA (e.g., "æt" for words rhyming with "cat").
    # Computed by the shared langtools/storage rhyme-key helpers for supported languages.
    rhyme_key: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    word_token = relationship("WordToken", back_populates="derivative_forms")
    lemma = relationship("Lemma", back_populates="derivative_forms")


class Sentence(Base):
    """Model for storing sentence metadata.

    This table stores language-agnostic metadata about sentences.
    The actual sentence text in various languages is stored in SentenceTranslation.
    Words used in the sentence are tracked in SentenceWord for difficulty calculation.
    """

    __tablename__ = "sentences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guid: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True, index=True
    )  # e.g., "S_00001"

    # Sentence pattern metadata
    pattern_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # e.g., "SVO", "SVAO"
    tense: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "past", "present", "future"

    # Difficulty level - calculated as the maximum difficulty of all words used
    # NULL means difficulty hasn't been calculated yet
    minimum_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Collection — which sentence set this belongs to (e.g., "beginner", "gutenberg")
    sentence_collection: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Source tracking
    source_filename: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "sentence_a1_1"

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )  # Rejected sentences won't be regenerated
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    translations = relationship(
        "SentenceTranslation", back_populates="sentence", cascade="all, delete-orphan"
    )
    words = relationship("SentenceWord", back_populates="sentence", cascade="all, delete-orphan")
    pattern_words = relationship(
        "SentencePatternWord", back_populates="sentence", cascade="all, delete-orphan"
    )
    audio_reviews = relationship("AudioQualityReview", back_populates="sentence")
    conversation_sentences = relationship("ConversationSentence", back_populates="sentence")


class SentenceTranslation(Base):
    """Model for storing translations of sentences in various languages.

    Unlike the Lemma table which has legacy translation columns, this table stores
    ALL language versions including the original/source language.
    """

    __tablename__ = "sentence_translations"
    __table_args__ = (
        UniqueConstraint("sentence_id", "language_code", name="uq_sentence_translation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "en", "lt", "zh"
    translation_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    sentence = relationship("Sentence", back_populates="translations")


class SentenceWord(Base):
    """Model for tracking which words/lemmas are used in a sentence.

    This junction table links sentences to the lemmas (words) they contain,
    enabling calculation of minimum difficulty level (don't show a sentence until
    all its words are known).

    The lemma_id may be NULL for function words (pronouns, particles) that aren't
    tracked as separate vocabulary items.
    """

    __tablename__ = "sentence_words"
    __table_args__ = (
        UniqueConstraint(
            "sentence_id", "language_code", "position", name="uq_sentence_word_lang_position"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)
    lemma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lemmas.id"), nullable=True)

    # Language code for this word (e.g., 'lt', 'fr', 'zh')
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Position in the sentence (0-indexed, matches order in target language sentence)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Word role in the sentence (semantic, not grammatical)
    word_role: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., "subject", "verb", "object", "pronoun", "adjective"

    # Reference text in both languages (from words_used JSON)
    english_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_language_text: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Base form in target language

    # Grammatical metadata (how the word is used in this specific sentence)
    grammatical_form: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "1s_past", "gerund"
    grammatical_case: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "accusative", "nominative"
    declined_form: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Actual form used in sentence (e.g., "banką")

    # Metadata
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    sentence = relationship("Sentence", back_populates="words")
    lemma = relationship("Lemma")


class SentencePatternWord(Base):
    """Model for storing the pattern definition of a sentence.

    This table records which lemmas/GUIDs are intended to be used in each slot
    of a sentence pattern (e.g., which noun goes in the 'object' slot). This is
    the "template" or "pattern" information that defines what the sentence is about.

    Unlike SentenceWord (which stores actual translation word breakdowns with POS info),
    this table stores the original pattern definition and never gets overwritten.

    This enables:
    1. Permanent record of which lemmas were selected for the pattern
    2. Clear distinction between pattern definition vs. translation POS data
    3. Ability to detect when English word breakdown hasn't been generated yet

    Either lemma_id or pending_import_id should be set (not both). When a word
    used in a sentence doesn't exist in the lemmas table, pending_import_id
    links to the staged import for later review.
    """

    __tablename__ = "sentence_pattern_words"
    __table_args__ = (
        UniqueConstraint("sentence_id", "position", name="uq_sentence_pattern_position"),
        CheckConstraint(
            "(lemma_id IS NOT NULL) OR (pending_import_id IS NOT NULL)",
            name="ck_pattern_word_has_reference",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)
    lemma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lemmas.id"), nullable=True)
    pending_import_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pending_imports.id"), nullable=True
    )

    # Position in the pattern (0-indexed)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Slot name in the pattern (e.g., "subject", "verb", "object", "adjective", "fixed")
    slot_name: Mapped[str] = mapped_column(String, nullable=False)

    # English text of the lemma (for reference)
    english_text: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    sentence = relationship("Sentence", back_populates="pattern_words")
    lemma = relationship("Lemma")
    pending_import = relationship("PendingImport")


class Corpus(Base):
    """Model for storing corpus information."""

    __tablename__ = "corpus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    corpus_weight: Mapped[float] = mapped_column(
        Float, default=1.0
    )  # Overall weight of this corpus in calculations (0.0-1.0)
    max_unknown_rank: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Max rank for words not in this corpus (penalty/placeholder)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # Whether to include in calculations
    added_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=True
    )


class TierDefinition(Base):
    """Definition of a single tier within a tier source (e.g. Cambridge YLE, CEFR).

    Tier sources (e.g. ``cambridge_yle``, ``cefr``) define their own set of named
    tiers; the ordinal column orders them within a source so consumers can sort
    or threshold without baking the order into code.
    """

    __tablename__ = "tier_definitions"
    __table_args__ = (
        UniqueConstraint("source", "tier_name", name="uq_tier_definition_source_name"),
        UniqueConstraint("source", "ordinal", name="uq_tier_definition_source_ordinal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "cambridge_yle", "cefr"
    tier_name: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., "starters", "movers", "flyers", "A1", "B2"
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = easiest within source
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )


class LemmaTier(Base):
    """Tier (e.g. Cambridge YLE level, CEFR level) assigned to a Lemma by a source.

    A lemma may have at most one tier per source. The tier_name must be a known
    tier_name in TierDefinition for the same source; this is enforced by the
    importer rather than by a DB-level FK so that bulk imports can fall back
    to bootstrap defaults if a source's TierDefinition rows are missing.
    """

    __tablename__ = "lemma_tiers"
    __table_args__ = (UniqueConstraint("lemma_id", "source", name="uq_lemma_tier_lemma_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tier_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    themes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lemma = relationship("Lemma", back_populates="tiers")


class ExternalLexemeAnnotation(Base):
    """An assertion by an external source (Cambridge YLE, CEFR, ...) that a
    surface form (WordToken) belongs to a tier, optionally with a POS or sense
    hint from the source.

    Decoupled from Lemma: the same row exists whether or not any lemma in the
    DB matches the surface form. The optional 0/1/N relation to Lemma lives in
    the join table ExternalLexemeAnnotationLemma. Reconcile after lemma adds
    to attach new candidates.

    The unique key includes pos_hint and sense_hint because a source may emit
    distinct rows for the same word at different POS (e.g. ``bank`` n vs v).
    SQLite treats NULLs as distinct in unique indexes, which is intentional
    here: a row with no pos_hint and a row with pos_hint="n" are distinct.
    """

    __tablename__ = "external_lexeme_annotations"
    __table_args__ = (
        UniqueConstraint(
            "word_token_id",
            "source",
            "pos_hint",
            "sense_hint",
            name="uq_external_lexeme_annotation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_token_id: Mapped[int] = mapped_column(
        ForeignKey("word_tokens.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tier_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pos_hint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sense_hint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ordinal_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    frequency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    themes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    word_token = relationship("WordToken")
    lemma_links = relationship(
        "ExternalLexemeAnnotationLemma",
        back_populates="annotation",
        cascade="all, delete-orphan",
    )


class ExternalLexemeAnnotationLemma(Base):
    """Join table linking an ExternalLexemeAnnotation to zero, one, or many Lemmas.

    ON DELETE CASCADE on both FKs: deleting an annotation removes its links;
    deleting a lemma removes its links. Neither action affects the other parent.
    """

    __tablename__ = "external_lexeme_annotation_lemmas"
    __table_args__ = (
        UniqueConstraint("annotation_id", "lemma_id", name="uq_external_lexeme_annotation_lemma"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    annotation_id: Mapped[int] = mapped_column(
        ForeignKey("external_lexeme_annotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lemma_id: Mapped[int] = mapped_column(
        ForeignKey("lemmas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    annotation = relationship("ExternalLexemeAnnotation", back_populates="lemma_links")
    lemma = relationship("Lemma")


class AudioQualityReview(Base):
    """Model for tracking audio file quality reviews.

    Audio files are generated for lemmas and sentences in various languages and voices.
    This table tracks the review status and quality issues for each audio file.

    For lemmas: guid is set, sentence_id is null. Supports derivative forms via grammatical_form.
    For sentences: sentence_id is set, guid is null, grammatical_form is null.

    NOTE: Derivative form audio (grammatical_form != null) is not currently generated,
    though the schema supports it for future use.
    """

    __tablename__ = "audio_quality_reviews"
    __table_args__ = (
        UniqueConstraint(
            "guid", "language_code", "voice_name", "grammatical_form", name="uq_audio_review_lemma"
        ),
        UniqueConstraint(
            "sentence_id", "language_code", "voice_name", name="uq_audio_review_sentence"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Audio file identification - either guid (for lemmas) or sentence_id (for sentences)
    guid: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # e.g., "N01_001" - set for lemma audio, null for sentence audio
    sentence_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sentences.id"), nullable=True, index=True
    )  # Set for sentence audio, null for lemma audio
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "zh", "ko", "fr"
    voice_name: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "ash", "alloy", "echo"
    grammatical_form: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # e.g., "1s_present", null for base forms (not currently generated)
    filename: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "N01_001.mp3" or "aš_gyvenu.mp3"

    # Audio content
    expected_text: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Word/phrase/sentence that should be spoken
    manifest_md5: Mapped[str] = mapped_column(String, nullable=False)  # MD5 hash from manifest

    # S3 Storage - staging and production URLs
    s3_staging_url: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # URL in staging/{agent}/ bucket - set when audio is first generated
    s3_staging_manifest_url: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # URL of manifest file in staging/{agent}/
    s3_prod_url: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # URL in prod/ bucket - set when audio is accepted for production
    staging_agent: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # Agent that generated the audio: "vieversys", "strazdas", etc.

    # Optional link to lemma (hybrid approach: try GUID match, fallback to text matching)
    lemma_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lemmas.id"), nullable=True, index=True
    )

    # Review status
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending_review", index=True
    )  # 'pending_review', 'approved', 'needs_replacement'

    # Quality issues (JSON array of issue types)
    # e.g., ["audible_breath", "extra_syllable", "missing_syllable", "bd_confusion", "echo_effect"]
    quality_issues: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Free-text notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Review metadata
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Username or identifier

    # Acceptance metadata (when audio is moved from staging to production)
    accepted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, nullable=True, index=True
    )
    accepted_by: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Username or identifier who accepted the audio

    # Timestamps
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lemma = relationship("Lemma")
    sentence = relationship("Sentence", back_populates="audio_reviews")

    @hybrid_property
    def display_voice(self) -> str:
        """Display voice as 'language/voice' format for UX."""
        return f"{self.language_code}/{self.voice_name}"

    @display_voice.expression  # type: ignore[no-redef]
    def display_voice(cls) -> str:
        """SQL expression for display_voice."""
        return cls.language_code + literal_column("'/'") + cls.voice_name


class BarsukasTask(Base):
    """Background task queued by the Barsukas web app.

    These tasks allow Barsukas to defer long-running LLM work to a worker process
    while keeping the web UI responsive.
    """

    __tablename__ = "barsukas_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, nullable=True)
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, nullable=True)


class Conversation(Base):
    """Model for storing conversation metadata.

    A conversation is a collection of related sentences that form a dialog
    or exchange between speakers. Each conversation contains multiple
    sentences in a specific order, with speaker attribution.

    Used by the Trakaido app for conversation-based language learning exercises.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Conversation metadata
    title: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "At the doctor's office"
    theme: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # e.g., "medical", "shopping", "restaurant"

    # Keywords that were used to generate this conversation
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of keywords

    # Difficulty level - calculated as the maximum difficulty of all sentences
    minimum_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Source tracking
    source_filename: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "conversation_level3_001"

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )  # Rejected conversations won't be regenerated
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    conversation_sentences = relationship(
        "ConversationSentence", back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationSentence(Base):
    """Model for linking sentences to conversations with ordering and speaker info.

    This junction table connects sentences to conversations, tracking:
    - Position in the conversation (0-indexed)
    - Speaker identifier (e.g., "A", "B", or character names)

    The same sentence could theoretically appear in multiple conversations,
    though this is uncommon. Each conversation has its own ordering.
    """

    __tablename__ = "conversation_sentences"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_conv_sentence_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)

    # Position in the conversation (0-indexed)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Speaker identifier (e.g., "A", "B", or character names like "Maria", "Doctor")
    speaker: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    conversation = relationship("Conversation", back_populates="conversation_sentences")
    sentence = relationship("Sentence")


@event.listens_for(DerivativeForm, "before_insert")
@event.listens_for(DerivativeForm, "before_update")
def _sync_derivative_form_rhyme_key_before_save(
    _mapper: Any,
    _connection: Any,
    target: DerivativeForm,
) -> None:
    """Keep rhyme keys synchronized with the derivative form's IPA."""
    sync_derivative_form_rhyme_key(target)
