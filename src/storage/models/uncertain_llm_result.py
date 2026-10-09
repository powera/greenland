"""
UncertainLLMResult model: "if you ask an LLM this, it will be uncertain."

One row per question about a lemma or a sentence (a grammar fact, a lemma
fact, a translation) where a model answered below the confidence its caller
needed.  Agents skip a question with a row here unless told to retry, so the
same uncertain answer is not paid for again.

This is working state, not linguistic data: nothing in the release export
reads it, and storing a fact for the same question deletes the row.
"""

import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .schema import Base

# The model answered, but below the caller's confidence threshold.
REASON_LOW_CONFIDENCE = "low_confidence"


class UncertainLLMResult(Base):
    """A question an LLM answered with too little confidence to store.

    Exactly one of ``lemma_id`` / ``sentence_id`` is set.  ``language_code``
    is NULL for a language-independent question (a lemma fact).  ``topic``
    names the question, e.g. a grammar fact type ("grammatical_gender").
    """

    __tablename__ = "uncertain_llm_results"
    __table_args__ = (
        CheckConstraint(
            "(lemma_id IS NULL) <> (sentence_id IS NULL)",
            name="ck_uncertain_llm_result_one_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lemma_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("lemmas.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sentence_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sentences.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # NULL for a language-independent question.
    language_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # What was asked, e.g. "grammatical_gender".
    topic: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Why the answer was not stored; see REASON_* above.
    reason: Mapped[str] = mapped_column(String, nullable=False)

    # Free text for a reviewer, e.g. "gpt-6-luna leaned masculine (0.55)".
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    lemma = relationship("Lemma", back_populates="uncertain_llm_results")
    sentence = relationship("Sentence", back_populates="uncertain_llm_results")

    def __repr__(self) -> str:
        target = f"lemma_id={self.lemma_id}" if self.lemma_id else f"sentence_id={self.sentence_id}"
        return (
            f"<UncertainLLMResult({target}, lang={self.language_code}, "
            f"{self.topic}: {self.reason})>"
        )


# One row per question.  A plain UNIQUE treats the NULL columns as distinct
# and would never fire, so the index coalesces them.
Index(
    "uq_uncertain_llm_result",
    func.coalesce(UncertainLLMResult.lemma_id, 0),
    func.coalesce(UncertainLLMResult.sentence_id, 0),
    func.coalesce(UncertainLLMResult.language_code, ""),
    UncertainLLMResult.topic,
    unique=True,
)
