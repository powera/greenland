#!/usr/bin/python3

"""Database model for tracking removed/replaced GUIDs."""

import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column
from wordfreq.storage.models.schema import Base


class GuidTombstone(Base):
    """Model for tracking GUIDs that have been removed or replaced.

    When a word's type/subtype changes, the old GUID is tombstoned here.
    This prevents GUID reuse conflicts and provides an audit trail.
    For example, if "triangle" was mischaracterized as an adjective (A03_001)
    and then corrected to a noun (N08_001), the A03_001 GUID would be tombstoned
    and could potentially be reused for "triangular" later.
    """

    __tablename__ = "guid_tombstones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The GUID that was removed/replaced
    guid: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # The lemma that previously had this GUID
    original_lemma_text: Mapped[str] = mapped_column(String, nullable=False)
    original_pos_type: Mapped[str] = mapped_column(String, nullable=False)
    original_pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # The new GUID that replaced this one (if applicable)
    replacement_guid: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Reference to the lemma that had this GUID (nullable since lemma might be deleted)
    # Note: No foreign key constraint to avoid cascading deletes
    lemma_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Reason for tombstoning
    reason: Mapped[str] = mapped_column(
        String, nullable=False, default="type_change"
    )  # e.g., "type_change", "subtype_change", "manual_correction"

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
