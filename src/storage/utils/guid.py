"""GUID generation utilities for lemmas."""

from typing import Iterator, Optional

from sqlalchemy.orm import Session

from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.schema import Lemma


def _guid_sequence_number(guid: str, prefix: str) -> Optional[int]:
    """Parse the numeric part of a GUID, or None if it is not parseable.

    Three historical formats are accepted: the current underscore form
    (``A01_001``), an intermediate dot form (``A01.001``), and the original
    unseparated form (``A01001``).
    """
    if not guid.startswith(prefix):
        return None

    remainder = guid[len(prefix) :]
    if remainder[:1] in ("_", "."):
        remainder = remainder[1:]

    try:
        return int(remainder)
    except ValueError:
        return None


def _pending_guids(session: Session, prefix: str) -> Iterator[str]:
    """Yield GUIDs on lemmas that are in the session but not yet in the table.

    ``session.new`` covers lemmas added but not yet flushed; ``session.dirty``
    covers lemmas whose GUID was reassigned in this transaction. Autoflush makes
    these visible to the query in the common case, but not when the session has
    nothing pending to flush, so they are checked explicitly.
    """
    for instance in list(session.new) + list(session.dirty):
        if isinstance(instance, Lemma) and instance.guid and instance.guid.startswith(prefix):
            yield instance.guid


def generate_guid(session: Session, pos_type: str, subtype: str) -> str:
    """
    Generate a unique GUID for a lemma in a specific POS type and subtype.

    Committed rows, flushed rows, and lemmas still pending in this session are
    all considered, so adding lemmas back-to-back without flushing between them
    does not reuse a GUID.

    A GUID counts as taken only once it is attached to a Lemma. Calling this
    twice without assigning the first result returns the same GUID both times,
    so callers that pre-allocate into a dict or a form field must build the
    Lemma before allocating the next one.

    Concurrency caveat: two *separate* sessions allocating at the same time do
    not see each other's uncommitted rows, so both can compute the same GUID.
    That is not preventable from here - it would need a dedicated allocation
    table or a locking read. The ``guid`` column is UNIQUE, so the second
    committer fails with an IntegrityError rather than persisting a duplicate.
    Scripts should therefore not write lemmas from concurrent transactions.

    Args:
        session: Database session
        pos_type: POS type (e.g., 'noun', 'verb', 'adjective')
        subtype: POS subtype name (e.g., 'body_part', 'color')

    Returns:
        Unique GUID string (e.g., 'N14_001')
    """
    if pos_type not in SUBTYPE_GUID_PREFIXES:
        raise ValueError(f"Unknown pos_type: {pos_type}")

    # Normalize common LLM output variations
    # For interjection, "interjection" or "other" subtype should map to "interjection_other"
    if pos_type == "interjection" and subtype in ("interjection", "other"):
        subtype = "interjection_other"

    if subtype not in SUBTYPE_GUID_PREFIXES[pos_type]:
        raise ValueError(f"Unknown subtype '{subtype}' for pos_type '{pos_type}'")

    prefix = SUBTYPE_GUID_PREFIXES[pos_type][subtype]

    # Find the highest existing GUID number for this subtype. Unparseable GUIDs
    # are skipped rather than raising, so one malformed row cannot block
    # allocation for its whole prefix.
    existing_guids = (
        session.query(Lemma.guid)
        .filter(Lemma.guid.like(f"{prefix}%"))
        .filter(Lemma.guid != None)
        .all()
    )

    max_num = 0
    for (guid,) in existing_guids:
        if guid:
            sequence_number = _guid_sequence_number(guid, prefix)
            if sequence_number is not None:
                max_num = max(max_num, sequence_number)

    # Fold in GUIDs held by lemmas that are pending in this session but not yet
    # visible to the query above.
    for pending_guid in _pending_guids(session, prefix):
        sequence_number = _guid_sequence_number(pending_guid, prefix)
        if sequence_number is not None:
            max_num = max(max_num, sequence_number)

    # Generate next GUID in new format (using underscore for valid Python variable names)
    next_num = max_num + 1
    return f"{prefix}_{next_num:03d}"
