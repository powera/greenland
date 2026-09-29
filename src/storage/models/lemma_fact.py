"""
LemmaFact model for storing language-independent facts about a lemma.

GrammarFact is keyed by language; this table holds facts about the concept
itself, such as whether "five X" makes sense (quantifiable).
"""

import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .schema import Base


class LemmaFact(Base):
    """
    Language-independent key-value fact about a lemma.

    Examples:
        - quantifiable: "true" (bear, atmosphere) or "false" (rice, sugar)

    Absence of a row means the fact has not been classified.
    """

    __tablename__ = "lemma_facts"
    __table_args__ = (UniqueConstraint("lemma_id", "fact_type", name="uq_lemma_fact"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lemma_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lemmas.id", ondelete="CASCADE"), nullable=False, index=True
    )

    fact_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    fact_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    lemma = relationship("Lemma", back_populates="lemma_facts")

    def __repr__(self) -> str:
        return f"<LemmaFact(lemma_id={self.lemma_id}, {self.fact_type}={self.fact_value})>"
