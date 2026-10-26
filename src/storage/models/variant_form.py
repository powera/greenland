"""VariantForm model for the other ways of writing one lemma.

The database tells three things apart:

* An *inflection* is a different grammatical slot of one spelling: gray,
  grayer, grayest.  Those are ``derivative_forms`` rows, and that is now all
  ``derivative_forms`` holds.
* A *variant* is another way of writing the same lemma: "grey" for "gray",
  "donut" for "doughnut", "TV" for "television".  This table.
* A *synonym* is a different lemma with a similar meaning: quickly/swiftly.
  Neither word belongs to the other, so it is a reference between two lemmas --
  a ``LemmaRelationGroup`` of type ``synonym`` -- and not a row here or on
  ``derivative_forms``.

Variants carry a *full paradigm*, which is why they cannot be a single extra
row on ``derivative_forms``: "grey" needs "greyer" and "greyest" alongside it,
and "TV" needs "TVs".  Each variant is identified by a (``variant_kind``,
``variant_key``) pair:

    kind="spelling",     key="grey"        -> grey / greyer / greyest
    kind="spelling",     key="donut"       -> donut / donuts
    kind="abbreviation", key="TV"          -> TV / TVs
    kind="expanded",     key="television"  -> television / televisions
    kind="gender",       key="female"      -> actress / actresses

Gender variants are the male and female words for one person concept
(actor/actress, profesor/profesora, cousin's primo/prima). They exist only on
person nouns (storage.models.guid_prefixes.is_human_subtype), and the
expectation is that some language has them for most of those. Separate lemmas
for different people (aunt/uncle, boy/girl) are not gender variants.
The lemma's translation and derivative_forms remain the unspecified default;
gender variants use stable keys "male" and "female", even if their text repeats
the default, as for a common-gender noun (el/la estudiante). Their
grammatical_gender is recorded independently. Whether a language has been
checked is the gender_variant_status grammar fact: "pair" with these rows, or
"none" when one word with one grammatical gender serves both. They are
exported as gendered_forms, never unconditional accepted-answer alternatives.

``variant_kind`` is deliberately free-form, and the kinds named in this module
are what the table holds *today* rather than a closed definition.  The set of
meaningful kinds is language-specific -- English has spelling variants, Chinese
additionally has script (simplified/traditional) variants, and other languages
have their own -- so no central enum enumerates them.  Any per-language
validation belongs in ``langtools/<lang>/``.

Every kind here is currently orthographic: the variant and the lemma are the
same word, differing in spelling or in length.  That is not guaranteed to stay
true.  Pairs like couch/sofa, gift/present and use/utilize are two everyday
words for one concept, where a learner who answers either knows the word and
two lemmas would mean two cards testing the same thing; those may well become
variants of a further kind.  The line runs *inside* a synonym set rather than
around it -- for couch/sofa, "divan" and "chesterfield" are equally not lemmas,
but they are not everyday equivalents either.  Where exactly it falls is
undecided, so do not tighten ``variant_kind`` into an enum and do not restate
"a variant is the same word spelled differently" as though it were exhaustive.

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

**The existing English spelling variants describe en-US.** A row saying "grey" is an accepted
way to write "gray" carries no claim that it is *the British* form; that
regional axis is not stored yet.  When en-GB is taken up properly it becomes
either a region tag on these rows or a storage dialect of its own -- that
decision is deferred, not made here.  Until then, do not read a variant as
evidence of where a spelling is used.

Unrelated despite the name: ``exports/wireword/generate_variants.py`` emits a
registry of regional *varieties* of a language (``variants.json``, which tells
a client that lang_es and lang_es-419 both exist).  It has nothing to do with
this table.
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

from storage.elements.interfaces import ElementRef
from storage.models.schema import Base

# Variant kind for alternate spellings of the same word ("grey"/"gray").
VARIANT_KIND_SPELLING: str = "spelling"

# Variant kind for script variants of the same word (e.g. Chinese
# simplified/traditional).  Distinct from regional vocabulary differences,
# which are dialect translations rather than variants.
VARIANT_KIND_SCRIPT: str = "script"

# The same word at a different length: "TV" for "television", and the expansion
# back the other way.  Both directions are recorded, because which one is the
# lemma is a separate question from which spellings a reader may meet.
VARIANT_KIND_ABBREVIATION: str = "abbreviation"
VARIANT_KIND_EXPANDED: str = "expanded"

# A different everyday word for the same sense, held on the lemma so its
# tokens are accounted for: "couch" on "sofa", "allocate" on "distribute".
# This is the further kind the module docstring anticipates, and where its
# boundary falls is still unsettled.  Not an accepted answer: a learner asked
# for "distribute" has not answered it with "allocate".
VARIANT_KIND_EQUIVALENT: str = "equivalent"

# An obsolete form kept so old texts parse: "saith" and "hath", "goest" for the
# thou-form of "go".  Only the slots that differ from the modern paradigm are
# stored.  Not an accepted answer, and its claim on a shared token is
# down-weighted (see wordfreq.lexeme_frequency.get_token_share) so that "art"
# stays the noun rather than a form of "be".
VARIANT_KIND_ARCHAIC: str = "archaic"

# Male/female words for one person concept, on person nouns only. The lemma's
# ordinary translation is the unspecified default. Keys identify referents
# rather than spellings, so male may repeat the default.
VARIANT_KIND_GENDER: str = "gender"
GENDER_VARIANT_MALE: str = "male"
GENDER_VARIANT_FEMALE: str = "female"
GENDER_VARIANT_KEYS: frozenset[str] = frozenset({GENDER_VARIANT_MALE, GENDER_VARIANT_FEMALE})

# Grammar fact recording that a language was checked for gender variants.
# Absent means unchecked; it is never set on a lemma that is not a person noun.
GENDER_VARIANT_STATUS_FACT: str = "gender_variant_status"
# The language has male/female variant rows.
GENDER_VARIANT_STATUS_PAIR: str = "pair"
# No gendered term: one word with one grammatical gender serves both.
GENDER_VARIANT_STATUS_NONE: str = "none"
GENDER_VARIANT_STATUSES: frozenset[str] = frozenset(
    {GENDER_VARIANT_STATUS_PAIR, GENDER_VARIANT_STATUS_NONE}
)

# The kinds a learner may type as unconditional alternatives. Gender
# counterparts depend on the prompt's referent and are deliberately excluded.
ACCEPTED_ANSWER_VARIANT_KINDS: frozenset[str] = frozenset(
    {
        VARIANT_KIND_SPELLING,
        VARIANT_KIND_SCRIPT,
        VARIANT_KIND_ABBREVIATION,
        VARIANT_KIND_EXPANDED,
    }
)


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

    # The word's grammatical gender, independently of the variant's referent.
    # Repeated on its form rows; NULL for languages without grammatical gender
    # or an unclassified form. Never infer it from variant_key.
    grammatical_gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

    @property
    def surface_text(self) -> str:
        """The spelling; the :class:`~storage.elements.interfaces.SurfaceForm` view."""
        return self.variant_form_text

    @property
    def owner(self) -> ElementRef:
        return ElementRef(element_type="lemma", element_id=self.lemma_id)
