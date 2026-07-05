"""Text-work models: the story library beside the concepts encyclopedia.

A :class:`TextWork` is a story/conversation/song/poem whose *text itself* we
store, as opposed to the encyclopedia entry *about* it (which stays a
:class:`~storage.models.concept.Concept` / ``SubConcept``). The actual texts
live in :class:`TextVersion` rows -- one per (work, language, difficulty)
rendering -- so a fable can carry a reference telling and easier tellings as
versions of one work.

The central axis is textual authority, derived from ``text_type``:

- **Authored** types (fable, folk_tale, ..., conversation): the text is our
  own; versions are generated/edited freely and none may be canonical.
- **Canonical** types (poem, song, ..., quote): one authoritative text exists;
  exactly one version is marked canonical, it is transcribed rather than
  generated, and it must record a license.

Like concepts, text works live OUTSIDE the lemma/GUID/data-release machinery:
they carry no GUID, are not exported, and their bodies never contain
``[[wiki links]]`` (they are stories, not encyclopedia entries, and never feed
the rank graph). Linking to the encyclopedia is by Wikidata Q-id only --
``qid`` (the work's own identity, unique) and ``attribution_qid`` (whose words
these are; non-unique, the quote-readiness anchor) -- resolved through
``concept_wikidata_index`` at read time. See docs/fables_design.md.

Slugs reuse the concept slug conventions (:func:`normalize_concept_slug`) but
form a separate namespace: wiki links never target works.
"""

import datetime
from typing import List, Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.concept import concept_slug_to_title
from storage.models.schema import Base

# Types whose text is OUR OWN: generated/edited freely, no version may be
# marked canonical, no license needed. Traditional stories are retold from the
# tradition (no canonical text exists); conversations are original
# compositions. Extend by editing this tuple.
AUTHORED_TEXT_TYPES: tuple[str, ...] = (
    "fable",  # Aesop-style traditional tale
    "folk_tale",  # Three Billy Goats Gruff, Gingerbread Man
    "fairy_tale",  # literary-tradition tales retold from the tradition
    "myth",  # Icarus, Prometheus
    "legend",  # King Arthur-type traditional narratives
    "conversation",  # original constructed dialogue (cafe, doctor, airport)
)

# Types with a single authoritative text: exactly one version is canonical,
# it is transcribed rather than generated, and licensing must be recorded.
CANONICAL_TEXT_TYPES: tuple[str, ...] = (
    "poem",
    "song",  # lyrics
    "nursery_rhyme",
    "speech",
    "short_story",
    "book_excerpt",  # a self-contained passage, never a whole book
    "quote",  # reserved: no intake yet (see INTAKE_DEFERRED_TEXT_TYPES)
)

ALL_TEXT_TYPES: tuple[str, ...] = AUTHORED_TEXT_TYPES + CANONICAL_TEXT_TYPES

# Types that are in the vocabulary (so nothing downstream hardcodes their
# absence) but whose intake is deferred to a later phase: CRUD refuses to
# create works of these types until the phase lands.
INTAKE_DEFERRED_TEXT_TYPES: tuple[str, ...] = ("quote",)

# UI grouping for the type select (mirrors SUB_CONCEPT_CATEGORY_GROUPS).
TEXT_TYPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Authored (our own text)", AUTHORED_TEXT_TYPES),
    ("Canonical (transcribed, licensed)", CANONICAL_TEXT_TYPES),
)

# Languages a TextVersion may be stored in. English-only for now by policy;
# the column exists so going multilingual later is data, not a migration.
SUPPORTED_TEXT_VERSION_LANGS: tuple[str, ...] = ("en",)


def is_authored_text_type(text_type: str) -> bool:
    """Return True when a text type's versions are our own authored texts."""
    return text_type in AUTHORED_TEXT_TYPES


def is_canonical_text_type(text_type: str) -> bool:
    """Return True when a text type has a single authoritative (canonical) text."""
    return text_type in CANONICAL_TEXT_TYPES


def is_intake_deferred_text_type(text_type: str) -> bool:
    """Return True when a text type is reserved but not yet accepted at intake."""
    return text_type in INTAKE_DEFERRED_TEXT_TYPES


class TextWork(Base):
    """A story/conversation/song/poem whose text (in one or more versions) we store.

    The encyclopedia entry ABOUT the work stays a Concept/SubConcept; this row
    is the anchor for the work's actual text(s) in ``text_versions``.
    """

    __tablename__ = "text_works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Canonical underscore-joined slug, reusing normalize_concept_slug().
    # Separate namespace from concepts: wiki links never target works, so a
    # slug may freely coexist in concepts/sub_concepts/text_works.
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # Required type from ALL_TEXT_TYPES; authority (authored vs canonical) is
    # derived from it. Indexed for the library's type filter.
    text_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Wikidata Q-id of the work ITSELF, when it has one. Resolves through
    # concept_wikidata_index to whichever entry (main concept or sub-concept)
    # covers the topic. Nullable -- conversations and obscure tales have none.
    # Unique: one library anchor per work Q-id.
    qid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)

    # Wikidata Q-id of the ATTRIBUTED person/source (poet, singer, speaker;
    # for quotes, the person quoted). Non-unique by design: many works hang
    # off one person.
    attribution_qid: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Display attribution line ("Robert Frost", "trad. Norwegian"). The
    # structured link is attribution_qid; this is what pages render.
    attribution: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # One-sentence description ("A troll under a bridge meets three goats.").
    # For conversations this doubles as the scenario brief for generation.
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Review metadata (house conventions).
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[List["TextVersion"]] = relationship(
        "TextVersion",
        back_populates="work",
        cascade="all, delete-orphan",
        order_by="TextVersion.lang, TextVersion.is_canonical.desc(), TextVersion.difficulty_level",
    )

    @property
    def title(self) -> str:
        """Human-readable display title derived from the slug."""
        return concept_slug_to_title(self.slug)

    @property
    def is_authored(self) -> bool:
        """True when this work's versions are our own authored texts."""
        return is_authored_text_type(self.text_type)

    @property
    def canonical_version(self) -> Optional["TextVersion"]:
        """The single canonical version, if one exists."""
        for version in self.versions:
            if version.is_canonical:
                return version
        return None

    def __repr__(self) -> str:
        return (
            f"<TextWork(id={self.id}, slug={self.slug!r}, "
            f"text_type={self.text_type!r}, qid={self.qid!r})>"
        )


class TextVersion(Base):
    """One rendering of a work: a specific language x difficulty text.

    For authored works every version is ours (``is_canonical`` always False).
    For canonical works exactly one version is the authoritative text
    (``is_canonical=True``, transcribed, license recorded).

    Invariants (enforced in :mod:`storage.crud.text_work`, mirroring the
    CRUD-layer posture of the sub-concepts one-target guard):

    1. At most one canonical version per work, only for canonical-type works.
    2. At most one version per (work, lang, difficulty_level) slot, treating
       NULL difficulty as its own slot (CRUD-enforced because SQLite treats
       NULLs as distinct in unique indexes).
    3. Canonical versions require ``license`` and are never fed to a generator.
    """

    __tablename__ = "text_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("text_works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Language of THIS text, using the language codes from
    # storage.translation_helpers conventions. English-only for now
    # (SUPPORTED_TEXT_VERSION_LANGS).
    lang: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # True only for the single authoritative text of a canonical-type work.
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Target difficulty for learner-oriented versions, same integer scale as
    # lemma difficulty levels. NULL for the canonical text and for the plain
    # reference telling (neither is difficulty-targeted).
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # The text itself. Markdown, NO [[wiki links]]. Nullable so a canonical
    # work whose text we cannot store (license) can still exist as a
    # metadata-only version.
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provenance, exactly one flavor per version:
    # authored/generated versions (mirrors Concept conventions)...
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # ...or canonical/transcribed versions.
    text_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    license: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    work: Mapped[TextWork] = relationship("TextWork", back_populates="versions")

    @property
    def variant_label(self) -> str:
        """Short human-readable label for this version ("en", "en · level 3")."""
        parts = [self.lang]
        if self.is_canonical:
            parts.append("canonical")
        if self.difficulty_level is not None:
            parts.append(f"level {self.difficulty_level}")
        return " · ".join(parts)

    def __repr__(self) -> str:
        return (
            f"<TextVersion(id={self.id}, work_id={self.work_id}, lang={self.lang!r}, "
            f"is_canonical={self.is_canonical}, difficulty_level={self.difficulty_level})>"
        )
