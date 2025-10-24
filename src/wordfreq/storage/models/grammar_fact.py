"""
GrammarFact model for storing language-specific grammatical properties.

This table stores grammatical metadata about lemmas that varies by language,
such as gender, declension class, and number restrictions (plurale tantum, etc.).
"""

import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, Boolean, ForeignKey, TIMESTAMP, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .schema import Base


class GrammarFact(Base):
    """
    Language-specific grammatical properties for lemmas.

    Examples:
        - number_type: plurale_tantum (scissors, pants)
        - number_type: singulare_tantum (information, furniture)
        - gender: masculine/feminine/neuter (for gendered languages)
        - declension: declension class (1, 2, 3, etc. for Lithuanian/Latin)
        - defective_verb: missing certain conjugations
        - indeclinable: doesn't decline/conjugate

    Design principle: Only store POSITIVE assertions. Absence of a fact means
    normal/default behavior for that language.
    """
    __tablename__ = "grammar_facts"
    __table_args__ = (
        # One fact of each type per lemma+language combination
        UniqueConstraint("lemma_id", "language_code", "fact_type", name="uq_grammar_fact"),
        # Composite index for querying by fact type and language
        Index("idx_fact_type_language", "fact_type", "language_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Links to the lemma this fact describes
    lemma_id: Mapped[int] = mapped_column(Integer, ForeignKey("lemmas.id", ondelete="CASCADE"), nullable=False, index=True)

    # Language code (ISO 639-1): "en", "lt", "fr", etc.
    # Same lemma can have different grammatical properties in different languages
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Type of grammatical fact
    # Common values: "number_type", "gender", "declension", "defective_verb", "indeclinable"
    fact_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Specific value for this fact type
    # Examples:
    #   fact_type="number_type" -> fact_value="plurale_tantum" or "singulare_tantum"
    #   fact_type="gender" -> fact_value="masculine", "feminine", "neuter"
    #   fact_type="declension" -> fact_value="1", "2", "3", "4", "5"
    #   fact_type="defective_verb" -> fact_value="no_imperative" or similar
    fact_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Optional notes for edge cases or clarifications
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human verification status
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamp
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationship to parent lemma
    lemma = relationship("Lemma", back_populates="grammar_facts")

    def __repr__(self):
        return f"<GrammarFact(lemma_id={self.lemma_id}, lang={self.language_code}, {self.fact_type}={self.fact_value})>"
