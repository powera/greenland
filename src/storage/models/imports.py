#!/usr/bin/python3

"""Database models for managing word imports and exclusions.

A :class:`PendingImport` is a term someone (an agent, a document parse, a
sentence that could not link a word) wants in the database but that nobody has
decided about yet. Approval turns it into one of three things -- see
``PENDING_IMPORT_TARGET_KINDS`` -- and the code that does the turning lives in
``words.pending_imports``.
"""

import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .schema import Base

# What a pending import becomes when it is approved. A term is one of three
# things and the three are stored in different tables:
#
# * "lemma"   -- vocabulary: a dictionary headword with a GUID, a difficulty
#                level, and a place in data/release. The default, and the only
#                kind that costs an LLM call to approve.
# * "name"    -- a proper name used in our texts ("George", "Fresh Mart"). Goes
#                to the names table, carries no difficulty, and is skipped in
#                sentence level rollups.
# * "concept" -- an encyclopedia topic ("World War II"). Goes to the concepts
#                table, outside the lemma/GUID machinery entirely.
#
# Nothing else belongs in this vocabulary: a term that is none of the three is
# rejected rather than given a fourth kind.
TARGET_KIND_LEMMA: str = "lemma"
TARGET_KIND_NAME: str = "name"
TARGET_KIND_CONCEPT: str = "concept"

PENDING_IMPORT_TARGET_KINDS: tuple[str, ...] = (
    TARGET_KIND_LEMMA,
    TARGET_KIND_NAME,
    TARGET_KIND_CONCEPT,
)

PENDING_IMPORT_TARGET_KIND_LABELS: dict[str, str] = {
    TARGET_KIND_LEMMA: "Lemma (vocabulary)",
    TARGET_KIND_NAME: "Name (proper noun)",
    TARGET_KIND_CONCEPT: "Concept (encyclopedia entry)",
}


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

    # What this term becomes on approval: one of PENDING_IMPORT_TARGET_KINDS.
    # Defaults to "lemma" so rows staged before this column existed, and every
    # caller that stages ordinary vocabulary, keep their old behavior.
    target_kind: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        default=TARGET_KIND_LEMMA,
        server_default=TARGET_KIND_LEMMA,
    )

    # Only meaningful when target_kind == "name": one of NAME_KINDS. NULL means
    # the kind was never determined; approval falls back to "other".
    name_kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Only meaningful when target_kind == "concept": the coarse classification
    # stored on Concept.concept_type (e.g. "event", "person"). Free-form.
    concept_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # POS and categorization (optional, especially for verbs where subtypes are incomplete)
    pos_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # noun, verb, adjective, adverb
    pos_subtype: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )  # e.g., animals, physical_action

    # Example sentence showing this word in context (helps LLM pick the right sense)
    example_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON array of free-form tags to apply to the lemma this import becomes,
    # e.g. ["legal"] for words staged from a statutory corpus. Mirrors
    # Lemma.tags; read/write it with storage.crud.lemma_tags.
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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

    # Sentences waiting on this term. The ORM-level cascade is the load-bearing
    # part: SQLite does not enforce foreign keys here, so ON DELETE CASCADE
    # alone would leave orphan rows behind whenever a pending import is
    # deleted. With this, ``session.delete(pending)`` takes its links with it.
    sentence_links = relationship(
        "SentencePendingImport",
        back_populates="pending_import",
        cascade="all, delete-orphan",
    )


class SentencePendingImport(Base):
    """A sentence waiting on a staged term, before that term becomes anything.

    This is the back-link that closes the sentence import loop: a sentence
    whose word resolved to no lemma stages the word, and this row is what lets
    the approval of that staged word find the sentence again.

    It used to be recorded on :class:`~storage.models.schema.SentenceWordHint`
    via a ``pending_import_id`` column, which was wrong in three ways that all
    showed up as flakiness:

    * hints are unique on ``(sentence_id, position)`` and are written by four
      other components, so two writers appending a slot in one transaction
      could collide on a position;
    * a hint already resolved to a lemma could not also record that the
      sentence was waiting on a staged word, so stage STAGE would never
      complete for that sentence;
    * the foreign key had no ON DELETE behavior, so *every* code path that
      deleted a pending import had to remember to detach the hints first, and
      the one that forgot left a row pointing at nothing.

    A link row carries no position and no uniqueness beyond ``(sentence_id,
    pending_import_id)``, so writing one is always safe, and it disappears with
    the pending row it references. Hints go back to meaning what their
    docstring says they mean: which lemmas a sentence was built to exercise.
    """

    __tablename__ = "sentence_pending_imports"
    __table_args__ = (
        UniqueConstraint("sentence_id", "pending_import_id", name="uq_sentence_pending_import"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sentence_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sentences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pending_import_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pending_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The English gloss the sentence could not resolve. Stage predicates match
    # on this rather than on a position, because hint positions are slot-shaped
    # while sentence-word positions are token-shaped.
    english_text: Mapped[str] = mapped_column(String, nullable=False)

    # Part of speech the generator expected for the slot, when it named one.
    slot_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    pending_import = relationship("PendingImport", back_populates="sentence_links")


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
