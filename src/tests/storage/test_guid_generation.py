"""Tests for GUID allocation in storage.utils.guid.

These tests deliberately avoid asserting which prefix belongs to which subtype -
that mapping is data in guid_prefixes.py and changes routinely. What is tested
here is the allocation *logic*: parsing the three historical GUID formats,
picking the correct maximum across them, and isolating one prefix from another.
Prefixes used below are looked up from the registry rather than hardcoded.
"""

from __future__ import annotations

import tempfile
from typing import Iterator, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.crud.phrase import next_phrase_guid
from storage.crud.sentence import next_sentence_guid
from storage.models.guid_prefixes import (
    PHRASE_SUBTYPE_GUID_PREFIXES,
    SENTENCE_GUID_PREFIX,
    SUBTYPE_GUID_PREFIXES,
)
from storage.models.guid_tombstone import GuidTombstone
from storage.models.schema import Base, Lemma
from storage.utils.guid import generate_guid


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _any_subtype(pos_type: str = "noun") -> Tuple[str, str, str]:
    """Return an arbitrary (pos_type, subtype, prefix) triple from the registry.

    Picking from the registry rather than naming a subtype keeps these tests
    working when subtypes are added, renamed, or re-prefixed.
    """
    subtype, prefix = sorted(SUBTYPE_GUID_PREFIXES[pos_type].items())[0]
    return pos_type, subtype, prefix


def _add_lemma(session: Session, guid: str, pos_type: str = "noun") -> None:
    session.add(
        Lemma(
            lemma_text=f"lemma-{guid}",
            definition_text=f"definition for {guid}",
            pos_type=pos_type,
            guid=guid,
        )
    )
    session.flush()


def test_first_guid_for_empty_subtype_starts_at_one() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        pos_type, subtype, prefix = _any_subtype()
        assert generate_guid(session, pos_type, subtype) == f"{prefix}_001"


def test_next_guid_is_max_across_all_historical_formats(session: Session) -> None:
    """Old (A01001), dot (A01.005) and underscore (A01_003) formats all count.

    The highest number wins regardless of which format encodes it, so a subtype
    holding legacy rows never re-issues a number already in use.
    """
    pos_type, subtype, prefix = _any_subtype()
    _add_lemma(session, f"{prefix}001")
    _add_lemma(session, f"{prefix}.005")
    _add_lemma(session, f"{prefix}_003")

    assert generate_guid(session, pos_type, subtype) == f"{prefix}_006"


def test_generated_guid_always_uses_underscore_format(session: Session) -> None:
    """New GUIDs are emitted in the underscore format even from legacy input."""
    pos_type, subtype, prefix = _any_subtype()
    _add_lemma(session, f"{prefix}007")

    generated = generate_guid(session, pos_type, subtype)

    assert generated == f"{prefix}_008"
    assert "." not in generated


def test_unparseable_guids_are_skipped_not_fatal(session: Session) -> None:
    """A malformed GUID in the table must not break allocation for its prefix."""
    pos_type, subtype, prefix = _any_subtype()
    _add_lemma(session, f"{prefix}_abc")
    _add_lemma(session, f"{prefix}_004")

    assert generate_guid(session, pos_type, subtype) == f"{prefix}_005"


def test_allocation_is_isolated_per_subtype(session: Session) -> None:
    """Numbering is per-prefix: a crowded subtype does not advance a fresh one."""
    pos_type, busy_subtype, busy_prefix = _any_subtype()
    other_subtype, other_prefix = sorted(SUBTYPE_GUID_PREFIXES[pos_type].items())[1]
    assert busy_prefix != other_prefix

    _add_lemma(session, f"{busy_prefix}_042")

    assert generate_guid(session, pos_type, other_subtype) == f"{other_prefix}_001"
    assert generate_guid(session, pos_type, busy_subtype) == f"{busy_prefix}_043"


def test_unknown_pos_type_and_subtype_raise(session: Session) -> None:
    pos_type, subtype, _ = _any_subtype()

    with pytest.raises(ValueError):
        generate_guid(session, "not_a_pos_type", subtype)

    with pytest.raises(ValueError):
        generate_guid(session, pos_type, "not_a_subtype")


def test_interjection_subtype_aliases_are_normalized(session: Session) -> None:
    """LLM output says "interjection" or "other"; both mean interjection_other."""
    canonical = generate_guid(session, "interjection", "interjection_other")

    assert generate_guid(session, "interjection", "interjection") == canonical
    assert generate_guid(session, "interjection", "other") == canonical


def _add_without_flush(session: Session, guid: str, pos_type: str) -> None:
    session.add(
        Lemma(
            lemma_text=f"unflushed-{guid}",
            definition_text="added but not flushed",
            pos_type=pos_type,
            guid=guid,
        )
    )


def test_unflushed_lemmas_do_not_get_duplicate_guids(session: Session) -> None:
    """A lemma added but not flushed still reserves its GUID."""
    pos_type, subtype, _ = _any_subtype()

    first = generate_guid(session, pos_type, subtype)
    _add_without_flush(session, first, pos_type)
    second = generate_guid(session, pos_type, subtype)

    assert first != second


def test_allocating_without_assigning_repeats_the_same_guid(session: Session) -> None:
    """Known limitation: a GUID is only reserved once it is attached to a Lemma.

    generate_guid infers what is taken from the table plus the session's pending
    lemmas, so calling it twice without assigning the first result returns the
    same GUID both times. Callers that pre-allocate into a dict or form field -
    words.add_word and the barsukas lemma routes - must build the Lemma before
    allocating the next GUID. Fixing this properly needs the session to track
    handed-out GUIDs, which is deliberately out of scope here.
    """
    pos_type, subtype, _ = _any_subtype()

    first = generate_guid(session, pos_type, subtype)
    second = generate_guid(session, pos_type, subtype)

    assert first == second


def test_allocation_is_safe_without_autoflush() -> None:
    """Correctness does not depend on autoflush being enabled."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    pos_type, subtype, _ = _any_subtype()

    with Session(engine, autoflush=False) as session:
        first = generate_guid(session, pos_type, subtype)
        _add_without_flush(session, first, pos_type)
        second = generate_guid(session, pos_type, subtype)

        assert first != second


def test_reassigned_guids_in_the_same_transaction_do_not_collide(session: Session) -> None:
    """Moving lemmas to a new subtype mid-transaction allocates distinct GUIDs.

    This is the handle_lemma_type_subtype_change path: existing rows get a new
    GUID from a different prefix without an intervening flush.
    """
    pos_type, subtype, prefix = _any_subtype()
    other_subtype, _ = sorted(SUBTYPE_GUID_PREFIXES[pos_type].items())[1]

    _add_lemma(session, f"{prefix}_001", pos_type)
    _add_lemma(session, f"{prefix}_002", pos_type)
    moved = session.query(Lemma).all()

    for lemma in moved:
        lemma.pos_subtype = other_subtype
        lemma.guid = generate_guid(session, pos_type, other_subtype)

    assert len({lemma.guid for lemma in moved}) == len(moved)


def test_concurrent_sessions_are_guarded_by_the_unique_constraint() -> None:
    """Separate transactions can allocate the same GUID; the DB rejects the second.

    Documented in generate_guid: cross-session allocation is not coordinated,
    because a session cannot see another's uncommitted rows. The guid column is
    UNIQUE so the loser fails loudly at commit instead of persisting a duplicate.
    Pinned here so that safety net cannot be dropped from the schema unnoticed.
    """
    engine = create_engine(f"sqlite:///{tempfile.mkdtemp()}/guid-concurrency.sqlite")
    Base.metadata.create_all(engine)
    pos_type, subtype, _ = _any_subtype()

    with Session(engine) as first_session, Session(engine) as second_session:
        first_guid = generate_guid(first_session, pos_type, subtype)
        second_guid = generate_guid(second_session, pos_type, subtype)
        assert first_guid == second_guid, "separate sessions do not coordinate allocation"

        _add_without_flush(first_session, first_guid, pos_type)
        first_session.commit()

        _add_without_flush(second_session, second_guid, pos_type)
        with pytest.raises(IntegrityError):
            second_session.commit()


def _tombstone(session: Session, guid: str, pos_type: str = "noun") -> None:
    session.add(
        GuidTombstone(
            guid=guid,
            original_lemma_text=f"retired-{guid}",
            original_pos_type=pos_type,
            original_pos_subtype=None,
            reason="release_history_gap",
        )
    )
    session.flush()


def test_tombstoned_guids_are_never_reissued(session: Session) -> None:
    """A retired GUID is taken even though no lemma row holds it any more.

    This is the case the tombstone table exists for: a prefix whose lemmas were
    all moved or deleted still has published numbers behind it, and counting
    only live rows walks straight back onto them.
    """
    pos_type, subtype, prefix = _any_subtype()
    _tombstone(session, f"{prefix}_003", pos_type)

    assert generate_guid(session, pos_type, subtype) == f"{prefix}_004"


def test_tombstones_above_the_live_maximum_advance_allocation(session: Session) -> None:
    """The real data shape: live lemmas below, retired GUIDs above.

    data/release has prefixes where the highest tombstoned number exceeds the
    highest live one, so allocating from live rows alone hands out a GUID that
    already belongs to a removed word.
    """
    pos_type, subtype, prefix = _any_subtype()
    _add_lemma(session, f"{prefix}_045", pos_type)
    _tombstone(session, f"{prefix}_053", pos_type)

    assert generate_guid(session, pos_type, subtype) == f"{prefix}_054"


def test_tombstones_below_the_live_maximum_change_nothing(session: Session) -> None:
    """An interior gap was never reissuable; tombstoning it must not skip ahead."""
    pos_type, subtype, prefix = _any_subtype()
    _add_lemma(session, f"{prefix}_010", pos_type)
    _tombstone(session, f"{prefix}_004", pos_type)

    assert generate_guid(session, pos_type, subtype) == f"{prefix}_011"


def test_tombstones_are_isolated_per_prefix(session: Session) -> None:
    """A retired GUID in one subtype does not advance another subtype."""
    pos_type, busy_subtype, busy_prefix = _any_subtype()
    other_subtype, other_prefix = sorted(SUBTYPE_GUID_PREFIXES[pos_type].items())[1]
    assert busy_prefix != other_prefix

    _tombstone(session, f"{busy_prefix}_042", pos_type)

    assert generate_guid(session, pos_type, other_subtype) == f"{other_prefix}_001"
    assert generate_guid(session, pos_type, busy_subtype) == f"{busy_prefix}_043"


def test_tombstoned_guids_in_legacy_formats_still_count(session: Session) -> None:
    """The dot and unseparated forms are parsed for tombstones too."""
    pos_type, subtype, prefix = _any_subtype()
    _tombstone(session, f"{prefix}.007", pos_type)
    _tombstone(session, f"{prefix}009", pos_type)

    assert generate_guid(session, pos_type, subtype) == f"{prefix}_010"


def test_next_phrase_guid_skips_tombstoned_numbers(session: Session) -> None:
    """Phrases allocate from the same evidence as lemmas."""
    phrase_subtype, prefix = sorted(PHRASE_SUBTYPE_GUID_PREFIXES.items())[0]
    _tombstone(session, f"{prefix}_012", "phrase")

    assert next_phrase_guid(session, phrase_subtype) == f"{prefix}_013"


def test_next_sentence_guid_skips_tombstoned_numbers(session: Session) -> None:
    """Sentence GUIDs are five digits wide but retire on the same rule."""
    _tombstone(session, f"{SENTENCE_GUID_PREFIX}_00077", "sentence")

    assert next_sentence_guid(session) == f"{SENTENCE_GUID_PREFIX}_00078"
