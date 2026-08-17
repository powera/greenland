"""Name models: proper names that appear in our texts but are not vocabulary.

A :class:`Name` is the third kind of entry beside lemmas and concepts, and it
exists because the other two both refuse it:

- A **lemma** is a dictionary headword with a difficulty level, a definition,
  and a place in ``data/release``. "George" is none of those -- a learner does
  not *learn* George, and gating a sentence on knowing him would be nonsense.
- A **concept** is an encyclopedia entry about a real topic, keyed to Wikidata.
  The George in "George likes skiing" is nobody in particular; there is no
  Q-id for him and never will be.

What a name still needs, and why this is storage rather than a prompt rule, is
a per-language rendering: a dialog line translated into Lithuanian needs
``Džordžas`` (and its declensions), Chinese needs ``乔治``, Japanese needs
katakana. Those renderings must be stable across every sentence that uses the
name, which means they have to live somewhere. They live in
:class:`NameTranslation`, which deliberately mirrors ``LemmaTranslation``.

Names do carry a GUID and are exported to ``data/release/names``: the
renderings above are content, not derived data, and a client that shows the
same character in Lithuanian and Japanese has to read them from somewhere.
Concepts stay out of the release tree; names do not. The GUID prefix encodes
:data:`~storage.models.name_entity.NAME_KINDS` via
:data:`storage.models.guid_prefixes.NAME_KIND_GUID_PREFIXES`.

Difficulty is the load-bearing distinction downstream: a sentence's
``minimum_level`` is the max difficulty of the *lemmas* it uses, and names are
skipped in that rollup. A dialog full of names is not a harder dialog.
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

from storage.elements.interfaces import LanguageValue
from storage.models.schema import Base

# Closed vocabulary for Name.kind. Extend this tuple rather than inventing
# values at call sites; the UI groups and the generator's name policy both read
# from it. "given_name" is the common case (dialog speakers); "full_name" is for
# names stored as a unit ("Mr. Chen") rather than assembled from parts.
NAME_KINDS: tuple[str, ...] = (
    "given_name",  # George, Maria, Jonas
    "family_name",  # Chen, Kazlauskas
    "full_name",  # Mr. Chen, Aunt Maria
    "place",  # Maple Street, Riverside Market (invented settings)
    "organization",  # Fresh Mart, Central Clinic (invented businesses)
    "brand",  # invented product names
    "animal",  # pets: Rex, Mittens
    "other",
)

# Display labels for the kinds, for selects and coverage tables.
NAME_KIND_LABELS: dict[str, str] = {
    "given_name": "Given name",
    "family_name": "Family name",
    "full_name": "Full name",
    "place": "Place",
    "organization": "Organization",
    "brand": "Brand",
    "animal": "Animal",
    "other": "Other",
}

# Optional gender hint. Languages that decline names (Lithuanian) or select
# honorifics by gender need it; it is a hint for generation and translation,
# never a claim about a real person.
NAME_GENDERS: tuple[str, ...] = ("masculine", "feminine", "neutral")


def is_valid_name_kind(kind: str) -> bool:
    """Return True when ``kind`` is part of the closed NAME_KINDS vocabulary."""
    return kind in NAME_KINDS


def normalize_name_text(name_text: str) -> str:
    """Return the canonical stored form of a name (trimmed, inner space collapsed).

    Capitalization is preserved and significant: names are looked up
    case-sensitively after normalization, so "Mark" (the name) never collides
    with "mark" (the lemma).

    Args:
        name_text: Raw name as typed or as returned by an LLM.

    Returns:
        The normalized name text.
    """
    return " ".join(name_text.split())


class Name(Base):
    """A proper name used in our texts: a person, place, or business we invented.

    See the module docstring for why these are neither lemmas nor concepts.
    """

    __tablename__ = "names"
    __table_args__ = (UniqueConstraint("name_text", "kind", name="uq_name_text_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Release GUID, e.g. "E01_004". Nullable because a name proposed by a
    # generator is a draft until it earns a place in the release namespace;
    # assign via storage.crud.name_entity.next_name_guid.
    guid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)

    # Canonical name text; assign via normalize_name_text(). Case-significant.
    name_text: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # One of NAME_KINDS.
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Optional role note that distinguishes same-text names, e.g. "the
    # pharmacist" vs "the neighbor". Display only -- uniqueness is (text, kind).
    disambiguation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # One of NAME_GENDERS, or NULL when it does not apply (places, brands).
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Provenance / review metadata (mirrors Lemma and Concept conventions).
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    translations = relationship(
        "NameTranslation", back_populates="name", cascade="all, delete-orphan"
    )

    @property
    def kind_label(self) -> str:
        """Human-readable label for this name's kind."""
        return NAME_KIND_LABELS.get(self.kind, self.kind)

    @property
    def display_text(self) -> str:
        """Name text with its disambiguation appended, when there is one."""
        if self.disambiguation:
            return f"{self.name_text} ({self.disambiguation})"
        return self.name_text

    @property
    def element_type(self) -> str:
        return "name"

    @property
    def language_values(self) -> list[LanguageValue]:
        """Project stable name renderings into the shared language view."""
        return [
            LanguageValue(
                id=translation.id,
                language_code=translation.language_code,
                text=translation.translation,
                value_kind="rendering",
                verified=translation.verified,
                status_note=translation.notes,
            )
            for translation in sorted(
                self.translations,
                key=lambda row: (row.language_code, row.id or 0),
            )
        ]

    def __repr__(self) -> str:
        return f"<Name(id={self.id}, name_text={self.name_text!r}, kind={self.kind!r})>"


class NameTranslation(Base):
    """How a name is rendered in one language (Džordžas, 乔治, ジョージ).

    Mirrors :class:`~storage.models.schema.LemmaTranslation` field-for-field
    where the fields mean the same thing, so the translation and audio
    pipelines can treat the two alike.
    """

    __tablename__ = "name_translations"
    __table_args__ = (UniqueConstraint("name_id", "language_code", name="uq_name_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("names.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # The name as written in this language (base/nominative form).
    translation: Mapped[str] = mapped_column(String, nullable=False, index=True)

    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Romanized/phonetic form for sorting (pinyin for zh, kana for ja).
    sort_key: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    name = relationship("Name", back_populates="translations")

    def __repr__(self) -> str:
        return (
            f"<NameTranslation(name_id={self.name_id}, "
            f"language_code={self.language_code!r}, translation={self.translation!r})>"
        )
