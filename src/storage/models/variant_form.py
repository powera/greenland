"""VariantForm model for alternate spellings and other orthographic variants.

A variant form is the *same lexeme* as its lemma, written differently:
"grey" for "gray", "donut" for "doughnut", "catalogue" for "catalog".  It is
neither a synonym (which is a different lexeme with a similar meaning, e.g.
"large"/"huge") nor an inflection (which is a different grammatical slot of
the same spelling, e.g. "gray"/"grayer").

Variants carry a *full paradigm*, which is why they cannot be a single extra
row on ``derivative_forms``: "grey" needs "greyer" and "greyest" alongside it.
Each variant is identified by a (``variant_kind``, ``variant_key``) pair:

    kind="spelling", key="grey"    -> grey / greyer / greyest
    kind="spelling", key="donut"   -> donut / donuts

``variant_kind`` is deliberately free-form.  The set of meaningful kinds is
language-specific -- English has spelling variants, Chinese additionally has
script (simplified/traditional) variants, and other languages have their own --
so no central enum enumerates them.  Any per-language validation belongs in
``langtools/<lang>/``.

``is_base_form`` is scoped to the variant: "grey" is the base form of the
"grey" variant, while "gray" remains the base form of the lemma itself in
``derivative_forms``.  Because variant identity is part of the unique key,
this does not produce two competing base forms for one language.

These rows live in a separate table from ``derivative_forms`` on purpose: an
unfiltered read of a lemma's forms should *not* return "grey".  Consumers that
want variants -- duplicate detection, wordlist coverage, "which lemma is
'grey'?" lookups -- opt in by querying this table explicitly.

Note that a regional *dialect* is a different axis from a spelling variant and
is not modeled here.  "grey" is an alternate spelling of "gray" within
en-US (this table), and would separately be the en-GB translation of the same
lemma (``lemma_translations``, mirroring how zh-tw works today).  Both
statements are true and neither is derivable from the other: "donut" has no
dialect, and Taiwanese vocabulary like 軟體 is not a variant of anything.
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

from storage.models.schema import Base

# Variant kind for alternate spellings of the same word ("grey"/"gray").
VARIANT_KIND_SPELLING: str = "spelling"

# Variant kind for script variants of the same word (e.g. Chinese
# simplified/traditional).  Distinct from regional vocabulary differences,
# which are dialect translations rather than variants.
VARIANT_KIND_SCRIPT: str = "script"


class VariantForm(Base):
    """A single grammatical form belonging to a variant paradigm of a lemma.

    One row per (variant, grammatical form).  A three-form English adjective
    variant such as "grey" is therefore three rows sharing a ``variant_key``.
    """

    __tablename__ = "variant_forms"
    __table_args__ = (
        UniqueConstraint(
            "lemma_id",
            "language_code",
            "variant_kind",
            "variant_key",
            "grammatical_form",
            name="uq_variant_form",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(ForeignKey("lemmas.id"), nullable=False, index=True)

    # Language this variant belongs to, e.g. "en".  A variant is always within
    # a single language; cross-language equivalents are translations instead.
    language_code: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # What sort of variant this is, e.g. "spelling" or "script".  Free-form:
    # the meaningful values are language-specific and are not centrally enumerated.
    variant_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Identifies which variant of the lemma this row belongs to.  Conventionally
    # the variant's own base form ("grey", "donut"), which keeps release files
    # readable and is naturally unique among a lemma's variants.
    variant_key: Mapped[str] = mapped_column(String, nullable=False)

    # Grammatical slot, using the same vocabulary as DerivativeForm
    # (e.g. "adjective/en_positive", "noun/en_plural").
    grammatical_form: Mapped[str] = mapped_column(String, nullable=False)

    # The actual text of this form of the variant, e.g. "greyer".
    variant_form_text: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Optional link to WordToken for frequency data (single-word forms only),
    # mirroring DerivativeForm.
    word_token_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("word_tokens.id"), nullable=True
    )

    # True for the variant's own base form ("grey" within the "grey" variant).
    is_base_form: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Pronunciations for this specific form
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Metadata
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lemma = relationship("Lemma", back_populates="variant_forms")
    word_token = relationship("WordToken")
