"""Models for source-language idioms and their cross-language equivalents."""

import datetime
from typing import Optional

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.elements.interfaces import LanguageValue
from storage.models.schema import Base

IDIOM_EQUIVALENCE_KINDS: tuple[str, ...] = (
    "idiomatic",
    "near_equivalent",
    "paraphrase",
)


class Idiom(Base):
    """An idiomatic expression anchored in a source language and meaning."""

    __tablename__ = "idioms"
    __table_args__ = (
        UniqueConstraint(
            "source_language_code",
            "expression",
            "meaning",
            name="uq_idiom_source_expression_meaning",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)
    source_language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    expression: Mapped[str] = mapped_column(String, nullable=False, index=True)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    usage_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    register: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    equivalents: Mapped[list["IdiomEquivalent"]] = relationship(
        "IdiomEquivalent", back_populates="idiom", cascade="all, delete-orphan"
    )

    @property
    def element_type(self) -> str:
        return "idiom"

    @property
    def display_text(self) -> str:
        return self.expression

    @property
    def expression_text(self) -> str:
        return self.expression

    @property
    def level(self) -> Optional[int]:
        return self.difficulty_level

    @property
    def language_values(self) -> tuple[LanguageValue, ...]:
        """Project equivalents through the shared read-only element interface.

        The literal gloss is a gloss, not a status note: it explains what the
        equivalent's words say, which is descriptive rather than a workflow
        state. Register stays in ``status`` because it does qualify how the
        equivalent may be used.

        The usage note is a ``note`` rather than a ``status_note`` so it keeps
        a persistent line of its own. These notes carry the reason an
        equivalent reads the way it does - that no idiomatic equivalent is
        conventional in a language, say - which is content a hover tooltip
        would hide.
        """
        return tuple(
            LanguageValue(
                id=equivalent.id,
                language_code=equivalent.language_code,
                text=equivalent.expression,
                value_kind=equivalent.equivalence_kind,
                verified=equivalent.verified,
                status=equivalent.register,
                note=equivalent.usage_note,
                gloss=equivalent.literal_gloss,
            )
            for equivalent in sorted(
                self.equivalents,
                key=lambda row: (row.language_code, row.equivalence_kind, row.id or 0),
            )
        )


class IdiomEquivalent(Base):
    """A natural equivalent, near-equivalent, or paraphrase in one language."""

    __tablename__ = "idiom_equivalents"
    __table_args__ = (
        CheckConstraint(
            "equivalence_kind IN ('idiomatic', 'near_equivalent', 'paraphrase')",
            name="ck_idiom_equivalent_kind",
        ),
        UniqueConstraint(
            "idiom_id",
            "language_code",
            "expression",
            name="uq_idiom_equivalent_language_expression",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idiom_id: Mapped[int] = mapped_column(
        ForeignKey("idioms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    expression: Mapped[str] = mapped_column(String, nullable=False)
    equivalence_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    literal_gloss: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usage_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    register: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    idiom: Mapped[Idiom] = relationship("Idiom", back_populates="equivalents")
