"""GUID generation utilities for lemmas."""

import threading
from typing import Dict, Iterable, Iterator, Optional, Tuple

from sqlalchemy.orm import Session

from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.guid_tombstone import GuidTombstone
from storage.models.schema import Lemma

# Allocation reads the highest GUID and the caller inserts the next one, so two
# sessions allocating at once would both read the same maximum: neither sees
# the other's uncommitted row.  Every number handed out is therefore reserved
# in this process, under a mutex held only for the reservation, and the next
# allocation starts above it whether or not that row is committed yet.  This
# covers every thread of one process -- Barsukas's request threads, task worker
# and batch poller.  A rolled-back allocation leaves a gap, as a tombstone
# does.  Separate processes (a CLI agent beside Barsukas) are not covered; the
# UNIQUE guid column still turns that race into an IntegrityError rather than
# a duplicate.
_reservation_lock = threading.Lock()
# (database URL, prefix) -> highest sequence number handed out in this process
_reserved: Dict[Tuple[str, str], int] = {}


def _reserve_after(session: Session, prefix: str, highest_in_use: int) -> int:
    """Hand out the next sequence number above both ``highest_in_use`` and every earlier reservation."""
    key = (str(session.get_bind().engine.url), prefix)
    with _reservation_lock:
        next_number = max(highest_in_use, _reserved.get(key, 0)) + 1
        _reserved[key] = next_number
    return next_number


def clear_reservations() -> None:
    """Forget every reservation, as a new process would.

    For tests, which build a fresh database at the same URL (``sqlite:///:memory:``)
    over and over.
    """
    with _reservation_lock:
        _reserved.clear()


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


def _highest_sequence_number(guids: Iterable[Optional[str]], prefix: str) -> int:
    """The largest parseable sequence number among ``guids``, or 0 if none parse.

    Unparseable GUIDs are skipped rather than raising, so one malformed row
    cannot block allocation for its whole prefix.
    """
    highest = 0
    for guid in guids:
        if not guid:
            continue
        sequence_number = _guid_sequence_number(guid, prefix)
        if sequence_number is not None:
            highest = max(highest, sequence_number)
    return highest


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

    Committed rows, flushed rows, lemmas still pending in this session, and
    GUIDs recorded in ``guid_tombstones`` are all considered, so adding lemmas
    back-to-back without flushing between them does not reuse a GUID, and a
    retired GUID is never reissued.

    Tombstoned GUIDs are permanently retired. ``data/release`` treats a GUID as
    immutable and leaves a gap where a word was removed (see AGENTS.md), so a
    number that was ever published must not come back attached to a different
    word - even once its lemma row is gone from this database.

    Each call reserves the GUID it returns for the life of the process, so
    calling twice returns two GUIDs even when the first is never used; an
    unused one is a gap, never a duplicate.  This is what keeps two threads
    allocating at once apart (see ``_reserved``).  Across processes nothing
    does; the ``guid`` column is UNIQUE, so the second committer fails with an
    IntegrityError rather than persisting a duplicate.

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

    # Find the highest existing GUID number for this subtype.
    existing_guids = (
        session.query(Lemma.guid)
        .filter(Lemma.guid.like(f"{prefix}%"))
        .filter(Lemma.guid != None)
        .all()
    )
    max_num = _highest_sequence_number((guid for (guid,) in existing_guids), prefix)

    # Fold in GUIDs held by lemmas that are pending in this session but not yet
    # visible to the query above.
    max_num = max(max_num, _highest_sequence_number(_pending_guids(session, prefix), prefix))

    # Fold in retired GUIDs. Their lemma rows may be long gone, so the query
    # above cannot see them, and without this the next allocation walks straight
    # back onto a number that ships in released data.
    max_num = max(max_num, _highest_sequence_number(tombstoned_guids(session, prefix), prefix))

    # Generate next GUID in new format (using underscore for valid Python variable names)
    next_num = _reserve_after(session, prefix, max_num)
    return f"{prefix}_{next_num:03d}"


def tombstoned_guids(session: Session, prefix: str) -> Iterator[str]:
    """Yield every tombstoned GUID that starts with ``prefix``.

    Shared by the lemma and phrase allocators so both retire numbers on the same
    evidence.
    """
    rows = session.query(GuidTombstone.guid).filter(GuidTombstone.guid.like(f"{prefix}%")).all()
    for (guid,) in rows:
        if guid:
            yield guid


def next_sequence_number(session: Session, prefix: str, live_guids: Iterable[str]) -> int:
    """The next free sequence number for ``prefix``, honouring tombstones.

    ``live_guids`` are the GUIDs currently attached to rows of whichever table
    owns this prefix. Callers outside :func:`generate_guid` (phrases, sentences)
    use this so that "never reuse a retired GUID" is stated in one place.  The
    number is reserved as :func:`generate_guid`'s are.
    """
    highest = _highest_sequence_number(live_guids, prefix)
    highest = max(highest, _highest_sequence_number(tombstoned_guids(session, prefix), prefix))
    return _reserve_after(session, prefix, highest)
