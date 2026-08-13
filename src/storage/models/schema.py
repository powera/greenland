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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, synonym

from storage.elements.interfaces import ElementRef, LanguageValue
from storage.models.pgvector import PGVector
from storage.rhyme_keys import sync_derivative_form_rhyme_key


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# Alternate spellings are deliberately absent here: "grey" is the same lexeme
# as "gray", not a different one, and it carries its own paradigm.  Those live
# in the variant_forms table; see storage.models.variant_form.
SYNONYM_GRAMMATICAL_FORMS: frozenset[str] = frozenset(
    {
        "synonym",
        "synonym_near",
        "synonym_regional",
        "synonym_register",
        "synonym_synecdoche",
        "synonym_related",
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

    # Translations of the lemma concept live in the LemmaTranslation table
    # (see below); read and write them via storage.translation_helpers. The
    # per-language columns that used to sit here (chinese_translation,
    # lithuanian_translation, ...) are gone. The SQLite columns still exist as
    # dead weight in older database files and are simply not mapped.

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
    # Alternate spellings and other orthographic variants of this same lexeme
    # ("grey" for "gray").  Deliberately separate from derivative_forms so an
    # unfiltered read of a lemma's forms does not return variant spellings;
    # see storage.models.variant_form.
    variant_forms = relationship(
        "VariantForm", back_populates="lemma", cascade="all, delete-orphan"
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

    @property
    def element_type(self) -> str:
        """Return the stable element discriminator used by shared consumers."""
        return "lemma"

    @property
    def display_text(self) -> str:
        """Return the lemma text with its optional sense disambiguation."""
        if self.disambiguation:
            return f"{self.lemma_text} ({self.disambiguation})"
        return self.lemma_text

    @property
    def word_text(self) -> str:
        """Return the lexical headword without sense disambiguation."""
        return self.lemma_text

    @property
    def level(self) -> Optional[int]:
        """Expose the stored learner difficulty through LeveledElement."""
        return self.difficulty_level

    @property
    def language_values(self) -> list[LanguageValue]:
        """Project lemma translations into the shared read-only representation.

        The per-language definition and sense disambiguation are projected as
        gloss and qualifier so the shared language-value table can render them
        as ordinary optional columns, rather than the lemma page needing its
        own copy of that table to show two extra fields.
        """
        return [
            LanguageValue(
                id=translation.id,
                language_code=translation.language_code,
                text=translation.translation,
                value_kind="headword",
                verified=translation.verified,
                status=translation.translation_status,
                status_note=translation.translation_status_note,
                gloss=translation.definition_text,
                qualifier=translation.disambiguation,
            )
            for translation in sorted(
                self.translations,
                key=lambda row: (row.language_code, row.id or 0),
            )
        ]


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
    word_hints = relationship(
        "SentenceWordHint", back_populates="sentence", cascade="all, delete-orphan"
    )
    audio_reviews = relationship("AudioQualityReview", back_populates="sentence")
    conversation_sentences = relationship("ConversationSentence", back_populates="sentence")

    @property
    def element_type(self) -> str:
        return "sentence"

    @property
    def display_text(self) -> str:
        """Prefer the English version, then any version, then the GUID."""
        translations_by_language = sorted(
            self.translations,
            key=lambda row: (row.language_code, row.id or 0),
        )
        english = next(
            (
                translation.translation_text
                for translation in translations_by_language
                if translation.language_code == "en"
            ),
            None,
        )
        if english is not None:
            return str(english)
        if translations_by_language:
            return str(translations_by_language[0].translation_text)
        return self.guid or f"Sentence {self.id}"

    @property
    def level(self) -> Optional[int]:
        return self.minimum_level

    @property
    def language_values(self) -> list[LanguageValue]:
        return [
            LanguageValue(
                id=translation.id,
                language_code=translation.language_code,
                text=translation.translation_text,
                value_kind="version",
                verified=translation.verified,
            )
            for translation in sorted(
                self.translations,
                key=lambda row: (row.language_code, row.id or 0),
            )
        ]


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

    A word may instead resolve to a proper name (``name_id``, see
    storage.models.name_entity): "George" is not vocabulary and carries no
    difficulty, so it is excluded from the minimum_level rollup rather than
    left unresolved. At most one of lemma_id / name_id is set.
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
    # Proper name this word resolves to, when it is a name rather than
    # vocabulary. Mutually exclusive with lemma_id; see storage.models.name_entity.
    name_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("names.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Language code for this word (e.g., 'lt', 'fr', 'zh')
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Position in the sentence (0-indexed, matches order in target language sentence)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Keep the existing database column name while exposing an accurate Python
    # attribute. The synonym preserves compatibility for storage/release code.
    part_of_speech: Mapped[str] = mapped_column("word_role", String, nullable=False)
    word_role = synonym("part_of_speech")

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

    # Universal Dependencies annotation (Phase 4; NULL on words never annotated)
    ud_relation: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Core UD relation, e.g. "nsubj", "obj", "det"
    ud_head_position: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Position of the head word; -1 marks the sentence root

    # Metadata
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    sentence = relationship("Sentence", back_populates="words")
    lemma = relationship("Lemma")
    name = relationship("Name")


class SentenceWordHint(Base):
    """Model for storing the words a sentence is *expected* to contain.

    These rows are hints, not a record of the final sentence. They are written
    before or independently of the authoritative word breakdown: the pattern and
    guided generators in buivolas pick lemmas first and build a sentence around
    them, and the dialog/scene path records its guesses the same way. A later
    LLM pass is free to reorder, drop, inflect, or substitute words, so a hint's
    position and slot_name describe the intent at generation time and may not
    match the sentence as it finally stands.

    SentenceWord is the authoritative per-language breakdown, with POS info and
    UD relations, and should be preferred wherever the actual sentence content
    matters. Use these hints for the questions they can still answer reliably:
    which lemmas a sentence was built to exercise, and whether a breakdown has
    been generated yet.

    Exactly one of lemma_id, pending_import_id, or name_id should be set. When a
    word used in a sentence doesn't exist in the lemmas table, pending_import_id
    links to the staged import for later review; when it is a proper name rather
    than vocabulary, name_id links to the Name row. A name is not a lemma and a
    learner does not study it, so it carries no difficulty and is excluded from
    level rollups -- but the hint still needs to record that the slot was
    filled by a name and not left as an unresolved gap.
    """

    __tablename__ = "sentence_word_hints"
    __table_args__ = (
        UniqueConstraint("sentence_id", "position", name="uq_sentence_word_hint_position"),
        CheckConstraint(
            "(lemma_id IS NOT NULL) OR (pending_import_id IS NOT NULL) " "OR (name_id IS NOT NULL)",
            name="ck_word_hint_has_reference",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)
    lemma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lemmas.id"), nullable=True)
    pending_import_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pending_imports.id"), nullable=True
    )
    name_id: Mapped[Optional[int]] = mapped_column(ForeignKey("names.id"), nullable=True)

    # Position in the pattern (0-indexed)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Slot name in the pattern (e.g., "subject", "verb", "object", "adjective", "fixed")
    slot_name: Mapped[str] = mapped_column(String, nullable=False)

    # English text of the lemma (for reference)
    english_text: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    sentence = relationship("Sentence", back_populates="word_hints")
    lemma = relationship("Lemma")
    pending_import = relationship("PendingImport")


class Phrase(Base):
    """Model for storing fixed traveler/greeting phrases (e.g. "See you later").

    Phrases are curated, fixed multi-word expressions that are *not* single
    lexemes. They used to live in the ``lemmas`` table with ``pos_type="phrase"``,
    which meant every lemma query had to filter them out. They now have their own
    table, mirroring the ``Sentence`` model: language-agnostic metadata here, the
    actual text per language in :class:`PhraseTranslation`.
    """

    __tablename__ = "phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guid: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True, index=True
    )  # e.g., "F01_003"

    # Phrase subtype (e.g. "greetings", "traveler"); drives the GUID prefix.
    phrase_subtype: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # English concept label and definition (formerly Lemma.lemma_text /
    # Lemma.definition_text).
    label: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g., "See you later"
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # For which Trakaido "level"
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    translations = relationship(
        "PhraseTranslation", back_populates="phrase", cascade="all, delete-orphan"
    )

    @property
    def element_type(self) -> str:
        return "phrase"

    @property
    def display_text(self) -> str:
        return self.label

    @property
    def expression_text(self) -> str:
        return self.label

    @property
    def level(self) -> Optional[int]:
        return self.difficulty_level

    @property
    def language_values(self) -> list[LanguageValue]:
        return [
            LanguageValue(
                id=translation.id,
                language_code=translation.language_code,
                text=translation.translation,
                value_kind="translation",
                verified=translation.verified,
                status=translation.translation_status,
                status_note=translation.translation_status_note,
            )
            for translation in sorted(
                self.translations,
                key=lambda row: (row.language_code, row.id or 0),
            )
        ]


class PhraseTranslation(Base):
    """Model for storing translations of phrases in various languages.

    Mirrors :class:`SentenceTranslation`; stores all language versions including
    the original/source (English) language.
    """

    __tablename__ = "phrase_translations"
    __table_args__ = (UniqueConstraint("phrase_id", "language_code", name="uq_phrase_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id"), nullable=False)
    language_code: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., "en", "lt", "zh"
    translation: Mapped[str] = mapped_column(Text, nullable=False)

    # Marks translations that are learner cues rather than natural phrasings
    # (e.g. lemma-form renderings). Mirrors LemmaTranslation.translation_status.
    translation_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    translation_status_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    phrase = relationship("Phrase", back_populates="translations")


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

    # The scene this dialog acts out, as the author typed it, e.g. "buying
    # tomatoes at the grocery store". NULL for conversations from the older
    # keyword-driven path, which had no scene input at all.
    scene_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # The level the dialog was *asked* for. Distinct from minimum_level, which
    # is what the words it actually used add up to; the gap between the two is
    # what the review page reports.
    target_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Model that generated the dialog (mirrors Lemma/Concept provenance).
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

    @property
    def element_type(self) -> str:
        return "conversation"

    @property
    def display_text(self) -> str:
        return self.title or self.scene_prompt or f"Conversation {self.id}"

    @property
    def level(self) -> Optional[int]:
        return self.minimum_level

    @property
    def children(self) -> list[ElementRef]:
        """Return sentence references in conversation order."""
        ordered_links = sorted(self.conversation_sentences, key=lambda link: link.position)
        return [
            ElementRef(element_type="sentence", element_id=link.sentence_id)
            for link in ordered_links
        ]


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

    # Position in the conversation (0-indexed), dense across the whole dialog.
    # One row is one sentence, so a turn that says three sentences occupies
    # three consecutive positions.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Which spoken turn this sentence belongs to (0-indexed). Several rows
    # share a turn_index when one turn ran to several sentences, so this is
    # deliberately not unique per conversation.
    #
    # Nullable because every row written before the turn split predates the
    # column; for those, one row *is* one turn and the migration backfills
    # turn_index = position. Readers must tolerate NULL and fall back to
    # position rather than grouping by speaker -- a speaker can genuinely hold
    # two consecutive turns, and grouping would silently merge them.
    turn_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

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
