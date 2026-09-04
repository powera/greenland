"""
LemmaRelationGroup and LemmaRelationMember models for relations between lemmas.

A group is an unordered set of 2+ lemmas.  No member is "primary" — they are
peers.  ``relation_type`` says what the members have in common.

**derivational** — same morphological root, differing by POS-changing
derivation:

    - {rectangle (N37_004), rectangular (A03_003)} — noun/adjective pair
    - {destroy (V03_005), destruction (N24_007), destructive (A99_042)}

**synonym** — different lemmas with a similar meaning: {quickly, swiftly}.
This is a relation rather than a form row because neither word belongs to the
other.  An alternate spelling is the opposite case — one lemma written another
way — and belongs in ``variant_forms`` instead.

Out of scope:  Antonyms (big/small), semantic relations (wood/tree).

Release files live in data/release/lemma_relations/{relation_type}/{subtype}.jsonl,
where {subtype} is chosen by priority: verb's subtype > noun's subtype > "other".
"""

import datetime
from typing import List, Optional

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.schema import Base

# Same root, different part of speech: rectangle/rectangular.
RELATION_TYPE_DERIVATIONAL: str = "derivational"

# Different lemmas with a similar meaning: quickly/swiftly.  A synonym is a
# relation *between* lemmas because neither word belongs to the other -- unlike
# an alternate spelling, which is one lemma written another way and lives in
# ``variant_forms``.  See ``storage.models.variant_form``, which also records
# why some near-synonym pairs (couch/sofa) may end up as variants instead.
RELATION_TYPE_SYNONYM: str = "synonym"

# ``relation_type`` doubles as the release subdirectory name
# (``data/release/lemma_relations/{relation_type}/{subtype}.jsonl``), so a new
# type needs no loader change -- the JSONL backend reads it from the directory.


class LemmaRelationGroup(Base):
    """A group of lemmas related to each other, per ``relation_type``.

    A ``derivational`` group is a word family whose members share a root and
    differ by POS-changing derivation (rectangle/rectangular).  A ``synonym``
    group is a set of lemmas with a similar meaning (quickly/swiftly).  Either
    way the group is unordered — no member is the "source" or "target".
    """

    __tablename__ = "lemma_relation_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # One of the RELATION_TYPE_* constants above.
    relation_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Human-readable label for this group (e.g., "rectangle", "destroy")
    concept_label: Mapped[str] = mapped_column(String, nullable=False)

    # Optional notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[List["LemmaRelationMember"]] = relationship(
        "LemmaRelationMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<LemmaRelationGroup(id={self.id}, type={self.relation_type!r}, "
            f"label={self.concept_label!r})>"
        )


class LemmaRelationMember(Base):
    """Membership of a lemma in a relation group.

    Each row links one lemma to one group.  A lemma may belong to at most
    one group of a given relation_type (enforced by application logic, not
    by a DB constraint, since a lemma could theoretically appear in both
    a derivational group and a future synonym group).
    """

    __tablename__ = "lemma_relation_members"
    __table_args__ = (UniqueConstraint("group_id", "lemma_id", name="uq_relation_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lemma_relation_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lemma_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lemmas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamp
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Relationships
    group: Mapped["LemmaRelationGroup"] = relationship(
        "LemmaRelationGroup", back_populates="members"
    )
    lemma = relationship("Lemma", back_populates="relation_memberships")

    def __repr__(self) -> str:
        return f"<LemmaRelationMember(group_id={self.group_id}, " f"lemma_id={self.lemma_id})>"
