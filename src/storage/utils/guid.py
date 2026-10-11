"""GUID generation utilities for lemmas."""

import threading
from typing import Callable, Dict, Iterable, Iterator, Optional, Tuple, TypeVar

from sqlalchemy.orm import Session

from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.guid_tombstone import GuidTombstone
from storage.models.schema import Lemma

T = TypeVar("T")

# Lemma GUID allocation reads the highest GUID in use and the caller inserts
# the next one, so two sessions allocating at once would both read the same
# maximum: neither sees the other's uncommitted lemma.  Every write that
# assigns a lemma GUID therefore runs through run_lemma_write, which holds this
# mutex from before the GUID is read until the lemma is committed.  It covers
# every thread of one process -- Barsukas's request threads, task worker and
# batch poller.  Separate processes (a CLI agent beside Barsukas) are not
# covered; the UNIQUE guid column still turns that race into an IntegrityError
# rather than a duplicate.
_lemma_write_lock = threading.Lock()
_LEMMA_WRITE_KEY = "lemma_write_scope"

# Shorter than SQLite's 30s busy_timeout.  A session that flushed other writes
# before entering run_lemma_write holds the database write lock while it waits
# here; if the mutex holder is itself waiting for that write lock, this
# timeout breaks the cycle first, and the waiting write fails rather than both.
LEMMA_WRITE_LOCK_TIMEOUT_SECONDS = 10.0

# Tests build lemmas directly with storage.crud.lemma.add_lemma and commit as
# they please; the suite's conftest clears this, and the tests of the scope
# itself set it again.
require_lemma_write_scope = True


class LemmaWriteBusyError(RuntimeError):
    """Another lemma write held the GUID mutex (at once, with ``fail_fast``)."""


class LemmaWriteScopeError(RuntimeError):
    """A lemma GUID was allocated outside :func:`run_lemma_write`."""


def run_lemma_write(
    session: Session,
    write: Callable[[], T],
    *,
    fail_fast: bool = False,
    commit: bool = True,
) -> T:
    """Run ``write`` and commit it, serialized with every other lemma GUID write.

    The single path for anything that assigns a lemma GUID -- a new lemma or a
    renumbered one.  The mutex is held from before ``write`` runs until the
    commit, so the next writer's :func:`generate_guid` sees this one's lemma.
    Any exception rolls the session back and is re-raised.

    A call nested inside another on the same session runs ``write`` in the
    outer scope: the outer call holds the mutex and commits.

    Args:
        session: The session ``write`` uses.
        write: Does the writes, calling :func:`generate_guid` as it needs.
        fail_fast: Raise :class:`LemmaWriteBusyError` at once if another write
            holds the mutex, instead of waiting up to
            ``LEMMA_WRITE_LOCK_TIMEOUT_SECONDS``.
        commit: False rolls the writes back instead (a preview or dry run).

    Returns:
        What ``write`` returns.
    """
    if session.info.get(_LEMMA_WRITE_KEY):
        return write()
    acquired = (
        _lemma_write_lock.acquire(blocking=False)
        if fail_fast
        else _lemma_write_lock.acquire(timeout=LEMMA_WRITE_LOCK_TIMEOUT_SECONDS)
    )
    if not acquired:
        raise LemmaWriteBusyError(
            "Another lemma is being added; try again"
            if fail_fast
            else f"Another lemma write held the GUID lock for {LEMMA_WRITE_LOCK_TIMEOUT_SECONDS:.0f}s"
        )
    session.info[_LEMMA_WRITE_KEY] = True
    try:
        result = write()
        if commit:
            session.commit()
        else:
            session.rollback()
        return result
    except BaseException:
        session.rollback()
        raise
    finally:
        session.info.pop(_LEMMA_WRITE_KEY, None)
        _lemma_write_lock.release()


# Sentence and phrase GUIDs are not written through run_lemma_write; each number
# they hand out is reserved in this process instead, under a mutex held only
# for the reservation, so the next allocation starts above it whether or not
# that row is committed yet.  A rolled-back allocation leaves a gap, as a
# tombstone does.
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

    A GUID counts as taken only once it is attached to a Lemma, so callers
    that allocate several must build each Lemma before allocating the next.

    Must run inside :func:`run_lemma_write`, which keeps concurrent writers in
    one process off the same GUID.  Across processes nothing does; the
    ``guid`` column is UNIQUE, so the second committer fails with an
    IntegrityError rather than persisting a duplicate.

    Args:
        session: Database session
        pos_type: POS type (e.g., 'noun', 'verb', 'adjective')
        subtype: POS subtype name (e.g., 'body_part', 'color')

    Returns:
        Unique GUID string (e.g., 'N14_001')

    Raises:
        LemmaWriteScopeError: Called outside :func:`run_lemma_write`.
    """
    if require_lemma_write_scope and not session.info.get(_LEMMA_WRITE_KEY):
        raise LemmaWriteScopeError(
            "generate_guid must run inside storage.utils.guid.run_lemma_write"
        )
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
    next_num = max_num + 1
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
