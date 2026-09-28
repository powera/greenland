"""CRUD, validation and release round-trip for curriculum level metadata."""

from pathlib import Path
from typing import Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.crud.curriculum_level import (
    delete_curriculum_level,
    get_curriculum_level,
    list_curriculum_levels,
    set_curriculum_level,
    to_manifest_entry,
)
from storage.crud.operation_log import (
    CURRICULUM_LEVEL_CREATE,
    CURRICULUM_LEVEL_DELETE,
    CURRICULUM_LEVEL_UPDATE,
)
from storage.models.operation_log import OperationLog
from storage.models.schema import Base
from storage.release import curriculum_level as level_release


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _logs(session: Session, operation_type: str) -> List[OperationLog]:
    return session.query(OperationLog).filter_by(operation_type=operation_type).all()


def test_set_creates_and_normalizes(session: Session) -> None:
    row = set_curriculum_level(
        session,
        100,
        names={"en": " Food & Cooking I ", "es": "Comida y cocina I", "fr": "  "},
        cefr="b1",
        prerequisites=[20, 5, 20],
        extra={"icon": "🍳"},
        source="tests/create",
    )

    assert row.get_names() == {"en": "Food & Cooking I", "es": "Comida y cocina I"}
    assert row.cefr == "B1"
    assert row.get_prerequisites() == [5, 20]
    assert row.get_extra() == {"icon": "🍳"}
    assert row.display_name == "Food & Cooking I"
    (entry,) = _logs(session, CURRICULUM_LEVEL_CREATE)
    assert entry.entity_guid is None


def test_set_updates_in_place_and_logs_only_changes(session: Session) -> None:
    set_curriculum_level(session, 1, names={"en": "First Words"}, cefr="A1.1")
    set_curriculum_level(session, 1, names={"en": "First Words"}, cefr="A1.2", source="tests/edit")
    set_curriculum_level(session, 1, names={"en": "First Words"}, cefr="A1.2", source="tests/edit")

    assert len(list_curriculum_levels(session)) == 1
    assert get_curriculum_level(session, 1) is not None
    assert get_curriculum_level(session, 1).cefr == "A1.2"  # type: ignore[union-attr]
    # The second edit changed nothing, so only one update is logged.
    assert len(_logs(session, CURRICULUM_LEVEL_UPDATE)) == 1


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"level": -1, "names": {"en": "x"}}, "not a curriculum level"),
        ({"level": 5, "names": {"es": "solo"}}, "English"),
        ({"level": 5, "names": {"en": "x", "xx": "y"}}, "Unknown language"),
        ({"level": 5, "names": {"en": "x"}, "cefr": "D1"}, "Unknown CEFR"),
        ({"level": 5, "names": {"en": "x"}, "prerequisites": [5]}, "own prerequisite"),
        ({"level": 5, "names": {"en": "x"}, "prerequisites": [99999]}, "not a curriculum"),
        ({"level": 5, "names": {"en": "x"}, "extra": {"name": "y"}}, "reserved"),
    ],
)
def test_set_rejects_invalid_fields(session: Session, kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        set_curriculum_level(session, **kwargs)


def test_set_rejects_prerequisite_cycle(session: Session) -> None:
    set_curriculum_level(session, 100, names={"en": "A"}, prerequisites=[120])
    set_curriculum_level(session, 120, names={"en": "B"}, prerequisites=[140])

    with pytest.raises(ValueError, match="cycle"):
        set_curriculum_level(session, 140, names={"en": "C"}, prerequisites=[100])


def test_delete_refuses_while_a_dependent_remains(session: Session) -> None:
    set_curriculum_level(session, 100, names={"en": "Food I"})
    set_curriculum_level(session, 120, names={"en": "Food II"}, prerequisites=[100])

    with pytest.raises(ValueError, match="prerequisite of"):
        delete_curriculum_level(session, 100)

    assert delete_curriculum_level(session, 120, source="tests/delete")
    assert delete_curriculum_level(session, 100)
    assert not delete_curriculum_level(session, 100)
    assert len(_logs(session, CURRICULUM_LEVEL_DELETE)) == 1


def test_manifest_entry_omits_empty_fields_and_merges_extra(session: Session) -> None:
    bare = set_curriculum_level(session, 20, names={"en": "Everyday Life"})
    full = set_curriculum_level(
        session,
        120,
        names={"en": "Food & Cooking II"},
        cefr="B1",
        prerequisites=[100],
        extra={"icon": "🍳"},
        notes="internal only",
    )

    assert to_manifest_entry(bare) == {"level": 20, "name": {"en": "Everyday Life"}}
    assert to_manifest_entry(full) == {
        "level": 120,
        "name": {"en": "Food & Cooking II"},
        "cefr": "B1",
        "prerequisites": [100],
        "icon": "🍳",
    }


def test_release_round_trip(session: Session, tmp_path: Path) -> None:
    set_curriculum_level(session, 120, names={"en": "Food II"}, prerequisites=[100], notes="n")
    set_curriculum_level(session, 1, names={"en": "First Words", "es": "Primeras"}, cefr="A1")
    session.commit()

    assert level_release.export_to_release(session, tmp_path) == 2
    records = level_release.read_release_records(tmp_path)
    assert [record["level"] for record in records] == [1, 120]
    assert records[1] == {
        "level": 120,
        "names": {"en": "Food II"},
        "prerequisites": [100],
        "notes": "n",
    }

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as fresh:
        assert level_release.import_from_release(fresh, tmp_path) == 2
        # Re-importing upserts rather than duplicating.
        assert level_release.import_from_release(fresh, tmp_path) == 2
        rebuilt = {
            row.level: level_release.to_release_record(row) for row in list_curriculum_levels(fresh)
        }
    assert list(rebuilt.values()) == records
