#!/usr/bin/python3

"""CRUD operations for GUID tombstones."""

from typing import Optional, List
from sqlalchemy.orm import Session
from wordfreq.storage.models.guid_tombstone import GuidTombstone


def create_tombstone(
    session: Session,
    guid: str,
    original_lemma_text: str,
    original_pos_type: str,
    original_pos_subtype: Optional[str],
    replacement_guid: Optional[str],
    lemma_id: Optional[int],
    reason: str = "type_change",
    notes: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> GuidTombstone:
    """
    Create a tombstone entry for a removed/replaced GUID.

    Args:
        session: Database session
        guid: The GUID being tombstoned
        original_lemma_text: The lemma that had this GUID
        original_pos_type: The original POS type
        original_pos_subtype: The original POS subtype
        replacement_guid: The new GUID that replaced this one (if applicable)
        lemma_id: The lemma ID (if still exists)
        reason: Reason for tombstoning (default: "type_change")
        notes: Optional notes
        changed_by: Who made this change

    Returns:
        The created GuidTombstone object
    """
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
    return session.query(GuidTombstone).filter(GuidTombstone.guid == guid).first()


def get_tombstones_by_lemma_id(session: Session, lemma_id: int) -> List[GuidTombstone]:
    """
    Get all tombstone entries for a specific lemma.

    Args:
        session: Database session
        lemma_id: The lemma ID

    Returns:
        List of GuidTombstone objects
    """
    return (
        session.query(GuidTombstone)
        .filter(GuidTombstone.lemma_id == lemma_id)
        .order_by(GuidTombstone.tombstoned_at.desc())
        .all()
    )


def is_guid_tombstoned(session: Session, guid: str) -> bool:
    """
    Check if a GUID has been tombstoned.

    Args:
        session: Database session
        guid: The GUID to check

    Returns:
        True if the GUID is tombstoned, False otherwise
    """
    return session.query(GuidTombstone).filter(GuidTombstone.guid == guid).count() > 0


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
    current_guid = guid

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
