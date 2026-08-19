#!/usr/bin/python3

"""Database model for tracking removed/replaced GUIDs."""

import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.schema import Base

# Why a GUID was retired.  Free-form strings drifted into eight ad-hoc values,
# four of which existed only in data/release and appeared nowhere in the code,
# so the vocabulary is named here and validated in
# ``storage.crud.guid_tombstone.create_tombstone``.  Mirrors the
# ``VARIANT_KIND_*`` constants in ``storage.models.variant_form``.

#: The lemma's part of speech changed, so it needed a GUID from another prefix.
TOMBSTONE_REASON_TYPE_CHANGE: str = "type_change"

#: The lemma's subtype changed within the same part of speech.
TOMBSTONE_REASON_SUBTYPE_CHANGE: str = "subtype_change"

#: Both the part of speech and the subtype changed.
TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE: str = "type_and_subtype_change"

#: The lemma was absorbed into another as a synonym; see the merge-synonym API.
TOMBSTONE_REASON_SYNONYM_MERGE: str = "synonym_merge"

#: The lemma became an inflected form of another lemma rather than its own word.
TOMBSTONE_REASON_MERGED_INTO_INFLECTION: str = "merged_into_inflection"

#: The word was filed under the wrong category and was refiled by hand.
TOMBSTONE_REASON_WRONG_CATEGORY: str = "wrong_category"

#: Reconstructed from git history for a GUID that left a gap in data/release.
TOMBSTONE_REASON_RELEASE_HISTORY_GAP: str = "release_history_gap"

#: The lemma was deleted through the /sync removals page (gone from release).
TOMBSTONE_REASON_RELEASE_REMOVAL: str = "release_removal"

#: A GUID reassigned by hand, e.g. through the Barsukas edit form.
TOMBSTONE_REASON_MANUAL_CORRECTION: str = "manual_correction"

TOMBSTONE_REASONS: frozenset[str] = frozenset(
    {
        TOMBSTONE_REASON_TYPE_CHANGE,
        TOMBSTONE_REASON_SUBTYPE_CHANGE,
        TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
        TOMBSTONE_REASON_SYNONYM_MERGE,
        TOMBSTONE_REASON_MERGED_INTO_INFLECTION,
        TOMBSTONE_REASON_WRONG_CATEGORY,
        TOMBSTONE_REASON_RELEASE_HISTORY_GAP,
        TOMBSTONE_REASON_RELEASE_REMOVAL,
        TOMBSTONE_REASON_MANUAL_CORRECTION,
    }
)


class GuidTombstone(Base):
    """Model for tracking GUIDs that have been removed or replaced.

    When a word's type/subtype changes, the old GUID is tombstoned here.
    This provides an audit trail and, because ``storage.utils.guid`` reads this
    table, retires the number permanently.  For example, if "triangle" was
    mischaracterized as an adjective (A03_001) and then corrected to a noun
    (N08_001), A03_001 is tombstoned with N08_001 as its replacement.

    A tombstoned GUID is **never** reissued, not even to a closely related word
    like "triangular".  ``data/release`` treats a GUID as immutable and leaves a
    gap where a word was removed (see AGENTS.md), so a number that was ever
    published must not come back attached to something else -- the released
    files, the Trakaido export and any client that cached them would disagree
    about what it names.  This is why the table records retirements whose lemma
    row is long gone: it is the only remaining evidence that the number is spent.
    """

    __tablename__ = "guid_tombstones"
    # One row per retired GUID.  Uniqueness matters for correctness, not just
    # tidiness: get_tombstone_by_guid takes .first(), so duplicates would make
    # both it and get_replacement_chain pick a branch nondeterministically.
    __table_args__ = (UniqueConstraint("guid", name="uq_guid_tombstone_guid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The GUID that was removed/replaced
    guid: Mapped[str] = mapped_column(String, nullable=False, index=True, unique=True)

    # The lemma that previously had this GUID
    original_lemma_text: Mapped[str] = mapped_column(String, nullable=False)
    original_pos_type: Mapped[str] = mapped_column(String, nullable=False)
    original_pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # The new GUID that replaced this one (if applicable)
    replacement_guid: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Reference to the lemma that had this GUID (nullable since lemma might be deleted)
    # Note: No foreign key constraint to avoid cascading deletes
    lemma_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Reason for tombstoning; one of TOMBSTONE_REASONS above.
    reason: Mapped[str] = mapped_column(
        String, nullable=False, default=TOMBSTONE_REASON_TYPE_CHANGE
    )

    # Optional notes explaining the change
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Who made this change
    changed_by: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # e.g., "barsukas_user", "agent_name"

    # Metadata
    tombstoned_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), index=True
    )
