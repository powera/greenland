#!/usr/bin/python3

"""CRUD operations for GUID tombstones."""

from typing import List, Optional

from sqlalchemy.orm import Session

from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_TYPE_CHANGE,
    TOMBSTONE_REASONS,
    GuidTombstone,
)


def create_tombstone(
    session: Session,
    guid: str,
    original_lemma_text: str,
    original_pos_type: str,
    original_pos_subtype: Optional[str],
    replacement_guid: Optional[str],
    lemma_id: Optional[int],
    reason: str = TOMBSTONE_REASON_TYPE_CHANGE,
    notes: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> GuidTombstone:
    """
    Create (or refresh) a tombstone entry for a removed/replaced GUID.

    Idempotent on ``guid``, which is unique: re-tombstoning a GUID updates the
    existing row rather than raising, so re-running a backfill or applying the
    same sync twice is safe.  This mirrors ``add_variant_form``'s upsert on its
    own unique key.

    Args:
        session: Database session
        guid: The GUID being tombstoned
        original_lemma_text: The lemma that had this GUID
        original_pos_type: The original POS type
        original_pos_subtype: The original POS subtype
        replacement_guid: The new GUID that replaced this one (if applicable)
        lemma_id: The lemma ID (if still exists)
        reason: Reason for tombstoning; must be one of TOMBSTONE_REASONS
        notes: Optional notes
        changed_by: Who made this change

    Returns:
        The created or updated GuidTombstone object

    Raises:
        ValueError: If ``reason`` is not a known tombstone reason.
    """
    if reason not in TOMBSTONE_REASONS:
        raise ValueError(
            f"Unknown tombstone reason {reason!r}; expected one of {sorted(TOMBSTONE_REASONS)}"
        )

    existing = get_tombstone_by_guid(session, guid)
    if existing is not None:
        existing.original_lemma_text = original_lemma_text
        existing.original_pos_type = original_pos_type
        existing.original_pos_subtype = original_pos_subtype
        existing.replacement_guid = replacement_guid
        existing.lemma_id = lemma_id
        existing.reason = reason
        if notes is not None:
            existing.notes = notes
        if changed_by is not None:
            existing.changed_by = changed_by
        session.flush()
        return existing

    tombstone = GuidTombstone(
        guid=guid,
        original_lemma_text=original_lemma_text,
        original_pos_type=original_pos_type,
        original_pos_subtype=original_pos_subtype,
        replacement_guid=replacement_guid,
        lemma_id=lemma_id,
        reason=reason,
        notes=notes,
        changed_by=changed_by,
    )
    session.add(tombstone)
    session.flush()
    return tombstone


def get_tombstone_by_guid(session: Session, guid: str) -> Optional[GuidTombstone]:
    """
    Get a tombstone entry by GUID.

    Args:
        session: Database session
        guid: The tombstoned GUID to look up

    Returns:
        GuidTombstone object if found, None otherwise
    """
    result: Optional[GuidTombstone] = (
        session.query(GuidTombstone).filter(GuidTombstone.guid == guid).first()
    )
    return result


def get_tombstones_by_lemma_id(session: Session, lemma_id: int) -> List[GuidTombstone]:
    """
    Get all tombstone entries for a specific lemma.

    Args:
        session: Database session
        lemma_id: The lemma ID

    Returns:
        List of GuidTombstone objects
    """
    result: list[GuidTombstone] = (
        session.query(GuidTombstone)
        .filter(GuidTombstone.lemma_id == lemma_id)
        .order_by(GuidTombstone.tombstoned_at.desc())
        .all()
    )
    return result


def is_guid_tombstoned(session: Session, guid: str) -> bool:
    """
    Check if a GUID has been tombstoned.

    Args:
        session: Database session
        guid: The GUID to check

    Returns:
        True if the GUID is tombstoned, False otherwise
    """
    count: int = session.query(GuidTombstone).filter(GuidTombstone.guid == guid).count()
    return count > 0


def get_replacement_chain(session: Session, guid: str) -> List[GuidTombstone]:
    """
    Get the chain of replacements for a GUID.

    Args:
        session: Database session
        guid: The starting GUID

    Returns:
        List of GuidTombstone objects showing the replacement chain
    """
    chain = []
    current_guid: Optional[str] = guid

    # Prevent infinite loops with a maximum depth
    max_depth = 100
    depth = 0

    while current_guid and depth < max_depth:
        tombstone = get_tombstone_by_guid(session, current_guid)
        if tombstone:
            chain.append(tombstone)
            current_guid = tombstone.replacement_guid
        else:
            break
        depth += 1

    return chain
