"""Tests for the GUID tombstone table and the lookups built on it.

A tombstone is the only record that a GUID was ever spent once its lemma row is
gone, so these tests are about that record staying trustworthy: one row per
GUID, a vocabulary of reasons that cannot drift, and a replacement chain that
terminates.

Allocation itself - that generate_guid refuses to reissue a tombstoned number -
is tested in test_guid_generation.py, beside the rest of the allocator.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.crud.guid_tombstone import (
    create_tombstone,
    get_replacement_chain,
    get_tombstone_by_guid,
    get_tombstones_by_lemma_id,
    is_guid_tombstoned,
)
from storage.crud.lemma import handle_lemma_type_subtype_change
from storage.guid_router import resolve_guid_with_history
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_RELEASE_REMOVAL,
    TOMBSTONE_REASON_SUBTYPE_CHANGE,
    TOMBSTONE_REASON_SYNONYM_MERGE,
    TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
    TOMBSTONE_REASON_TYPE_CHANGE,
    TOMBSTONE_REASONS,
    GuidTombstone,
)
from storage.models.schema import Base, Lemma
from storage.utils.guid import generate_guid


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _tombstone(
    session: Session,
    guid: str,
    *,
    replacement_guid: str | None = None,
    reason: str = TOMBSTONE_REASON_TYPE_CHANGE,
    lemma_id: int | None = None,
    notes: str | None = None,
    changed_by: str | None = None,
) -> GuidTombstone:
    return create_tombstone(
        session=session,
        guid=guid,
        original_lemma_text=f"word-{guid}",
        original_pos_type="noun",
        original_pos_subtype="animal",
        replacement_guid=replacement_guid,
        lemma_id=lemma_id,
        reason=reason,
        notes=notes,
        changed_by=changed_by,
    )


def _add_lemma(session: Session, guid: str) -> Lemma:
    lemma = Lemma(
        lemma_text=f"lemma-{guid}",
        definition_text=f"definition for {guid}",
        pos_type="noun",
        pos_subtype="animal",
        guid=guid,
    )
    session.add(lemma)
    session.flush()
    return lemma


class TestCreateAndLookup:
    def test_a_tombstoned_guid_is_reported_as_tombstoned(self, session: Session) -> None:
        _tombstone(session, "N02_001")

        assert is_guid_tombstoned(session, "N02_001") is True
        assert is_guid_tombstoned(session, "N02_002") is False

    def test_lookup_returns_the_recorded_row(self, session: Session) -> None:
        _tombstone(session, "N02_001", replacement_guid="N08_001")

        found = get_tombstone_by_guid(session, "N02_001")

        assert found is not None
        assert found.replacement_guid == "N08_001"
        assert found.original_lemma_text == "word-N02_001"

    def test_tombstones_for_a_lemma_are_listed(self, session: Session) -> None:
        lemma = _add_lemma(session, "N02_009")
        _tombstone(session, "N02_001", lemma_id=lemma.id)
        _tombstone(session, "N02_005", lemma_id=lemma.id)
        _tombstone(session, "N02_007", lemma_id=lemma.id + 1000)

        found = get_tombstones_by_lemma_id(session, lemma.id)

        assert {row.guid for row in found} == {"N02_001", "N02_005"}


class TestReasonVocabulary:
    def test_an_unknown_reason_is_rejected(self, session: Session) -> None:
        with pytest.raises(ValueError, match="Unknown tombstone reason"):
            _tombstone(session, "N02_001", reason="because_i_said_so")

    def test_every_named_reason_is_accepted(self, session: Session) -> None:
        for index, reason in enumerate(sorted(TOMBSTONE_REASONS)):
            _tombstone(session, f"N02_{index:03d}", reason=reason)

        assert session.query(GuidTombstone).count() == len(TOMBSTONE_REASONS)

    def test_reasons_used_in_the_codebase_are_in_the_vocabulary(self) -> None:
        """The constants the production paths pass must be members of the set."""
        assert TOMBSTONE_REASON_TYPE_CHANGE in TOMBSTONE_REASONS
        assert TOMBSTONE_REASON_SYNONYM_MERGE in TOMBSTONE_REASONS
        assert TOMBSTONE_REASON_RELEASE_REMOVAL in TOMBSTONE_REASONS


class TestUniqueness:
    def test_re_tombstoning_updates_rather_than_duplicating(self, session: Session) -> None:
        """Re-running a backfill or re-applying a sync must not double the row.

        Duplicates would not merely be untidy: get_tombstone_by_guid takes
        .first(), so a second row makes both it and get_replacement_chain pick a
        branch nondeterministically.
        """
        _tombstone(session, "N02_001", replacement_guid=None, notes="first pass")
        _tombstone(session, "N02_001", replacement_guid="N08_001", notes="second pass")

        rows = session.query(GuidTombstone).filter(GuidTombstone.guid == "N02_001").all()

        assert len(rows) == 1
        assert rows[0].replacement_guid == "N08_001"
        assert rows[0].notes == "second pass"

    def test_the_schema_refuses_a_duplicate_guid(self, session: Session) -> None:
        """The unique constraint backs up create_tombstone's own upsert."""
        _tombstone(session, "N02_001")

        session.add(
            GuidTombstone(
                guid="N02_001",
                original_lemma_text="a second row for the same guid",
                original_pos_type="noun",
                reason=TOMBSTONE_REASON_TYPE_CHANGE,
            )
        )

        with pytest.raises(IntegrityError):
            session.flush()


class TestReplacementChain:
    def test_a_single_hop_chain(self, session: Session) -> None:
        _tombstone(session, "N02_001", replacement_guid="N08_001")

        chain = get_replacement_chain(session, "N02_001")

        assert [row.guid for row in chain] == ["N02_001"]

    def test_the_chain_follows_successive_replacements(self, session: Session) -> None:
        _tombstone(session, "A03_001", replacement_guid="N08_001")
        _tombstone(session, "N08_001", replacement_guid="N12_004")

        chain = get_replacement_chain(session, "A03_001")

        assert [row.guid for row in chain] == ["A03_001", "N08_001"]

    def test_an_untombstoned_guid_has_an_empty_chain(self, session: Session) -> None:
        assert get_replacement_chain(session, "N02_001") == []

    def test_a_cycle_terminates_instead_of_hanging(self, session: Session) -> None:
        """max_depth is the guard; without it this call would never return."""
        _tombstone(session, "N02_001", replacement_guid="N02_002")
        _tombstone(session, "N02_002", replacement_guid="N02_001")

        chain = get_replacement_chain(session, "N02_001")

        assert len(chain) == 100


class TestResolveGuidWithHistory:
    def test_a_live_guid_resolves_with_no_history(self, session: Session) -> None:
        _add_lemma(session, "N02_001")

        resolved = resolve_guid_with_history(session, "N02_001")

        assert resolved.exists is True
        assert resolved.is_tombstoned is False
        assert resolved.replacement is None

    def test_a_retired_guid_reports_what_replaced_it(self, session: Session) -> None:
        """The question this exists to answer: what happened to A03_001?"""
        replacement = _add_lemma(session, "N08_001")
        _tombstone(session, "A03_001", replacement_guid="N08_001")

        resolved = resolve_guid_with_history(session, "A03_001")

        assert resolved.exists is False
        assert resolved.is_tombstoned is True
        assert resolved.replacement_guid == "N08_001"
        assert resolved.replacement is replacement

    def test_the_chain_is_followed_to_the_final_replacement(self, session: Session) -> None:
        final = _add_lemma(session, "N12_004")
        _tombstone(session, "A03_001", replacement_guid="N08_001")
        _tombstone(session, "N08_001", replacement_guid="N12_004")

        resolved = resolve_guid_with_history(session, "A03_001")

        assert resolved.replacement_guid == "N12_004"
        assert resolved.replacement is final

    def test_a_plain_deletion_has_no_replacement(self, session: Session) -> None:
        _tombstone(session, "N02_001", reason=TOMBSTONE_REASON_RELEASE_REMOVAL)

        resolved = resolve_guid_with_history(session, "N02_001")

        assert resolved.is_tombstoned is True
        assert resolved.replacement_guid is None
        assert resolved.replacement is None

    def test_an_unknown_guid_is_neither_live_nor_tombstoned(self, session: Session) -> None:
        resolved = resolve_guid_with_history(session, "N02_404")

        assert resolved.exists is False
        assert resolved.is_tombstoned is False
        assert resolved.kind == "lemma"


class TestTypeSubtypeChange:
    """The main production path that mints tombstones.

    Exercised end to end here because until now nothing tested it directly: the
    only coverage was a docstring mention in test_guid_generation.py.
    """

    def _noun_and_verb_subtypes(self) -> tuple[str, str]:
        noun_subtype, _ = sorted(SUBTYPE_GUID_PREFIXES["noun"].items())[0]
        verb_subtype, _ = sorted(SUBTYPE_GUID_PREFIXES["verb"].items())[0]
        return noun_subtype, verb_subtype

    def test_changing_pos_tombstones_the_old_guid_and_mints_a_new_one(
        self, session: Session
    ) -> None:
        noun_subtype, verb_subtype = self._noun_and_verb_subtypes()
        lemma = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="noun",
            pos_subtype=noun_subtype,
            guid=generate_guid(session, "noun", noun_subtype),
        )
        session.add(lemma)
        session.flush()
        old_guid = lemma.guid

        result = handle_lemma_type_subtype_change(
            session=session,
            lemma=lemma,
            new_pos_type="verb",
            new_pos_subtype=verb_subtype,
            source="test",
            notes="miscategorised",
        )

        assert result["tombstone_created"] is True
        assert result["old_guid"] == old_guid
        assert lemma.guid == result["new_guid"] != old_guid

        tombstone = get_tombstone_by_guid(session, old_guid)
        assert tombstone is not None
        assert tombstone.replacement_guid == lemma.guid
        # Moving noun -> verb necessarily moves the subtype too, so both axes
        # changed and the reason says so.
        assert tombstone.reason == TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE
        assert tombstone.changed_by == "test"

    def test_the_reason_records_which_axis_changed(self, session: Session) -> None:
        noun_subtype, _ = self._noun_and_verb_subtypes()
        other_subtype, _ = sorted(SUBTYPE_GUID_PREFIXES["noun"].items())[1]
        lemma = Lemma(
            lemma_text="triangle",
            definition_text="a three-sided shape",
            pos_type="noun",
            pos_subtype=noun_subtype,
            guid=generate_guid(session, "noun", noun_subtype),
        )
        session.add(lemma)
        session.flush()
        old_guid = lemma.guid
        assert old_guid is not None

        handle_lemma_type_subtype_change(
            session=session,
            lemma=lemma,
            new_pos_type="noun",
            new_pos_subtype=other_subtype,
        )

        tombstone = get_tombstone_by_guid(session, old_guid)
        assert tombstone is not None
        assert tombstone.reason == TOMBSTONE_REASON_SUBTYPE_CHANGE

    def test_an_unchanged_lemma_is_not_tombstoned(self, session: Session) -> None:
        noun_subtype, _ = self._noun_and_verb_subtypes()
        lemma = Lemma(
            lemma_text="dog",
            definition_text="a domesticated canine",
            pos_type="noun",
            pos_subtype=noun_subtype,
            guid=generate_guid(session, "noun", noun_subtype),
        )
        session.add(lemma)
        session.flush()

        result = handle_lemma_type_subtype_change(
            session=session,
            lemma=lemma,
            new_pos_type="noun",
            new_pos_subtype=noun_subtype,
        )

        assert result["tombstone_created"] is False
        assert session.query(GuidTombstone).count() == 0

    def test_the_retired_guid_is_not_handed_back_out(self, session: Session) -> None:
        """The whole point of the tombstone, checked through the real path.

        A lemma that vacates the last GUID of its subtype leaves the prefix with
        no live rows at all; without the tombstone the next word in that subtype
        would be given the number the released files already use.
        """
        noun_subtype, verb_subtype = self._noun_and_verb_subtypes()
        lemma = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="noun",
            pos_subtype=noun_subtype,
            guid=generate_guid(session, "noun", noun_subtype),
        )
        session.add(lemma)
        session.flush()
        vacated_guid = lemma.guid

        handle_lemma_type_subtype_change(
            session=session,
            lemma=lemma,
            new_pos_type="verb",
            new_pos_subtype=verb_subtype,
        )

        assert generate_guid(session, "noun", noun_subtype) != vacated_guid
