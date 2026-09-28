"""CRUD, validation and release round-trip for curriculum level metadata."""

from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.crud.curriculum_level import (
    delete_curriculum_level,
    get_curriculum_level,
    list_curriculum_levels,
    set_curriculum_level,
    set_level_translation,
    to_manifest_entry,
)
from storage.crud.operation_log import (
    CURRICULUM_LEVEL_CREATE,
    CURRICULUM_LEVEL_DELETE,
    CURRICULUM_LEVEL_TRANSLATION_UPDATE,
    CURRICULUM_LEVEL_UPDATE,
)
from storage.models.curriculum_level import CurriculumLevelTranslation
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
        name=" Food & Cooking I ",
        cefr="b1",
        prerequisites=["20", 5, 20],
        extra={"icon": "🍳"},
        translations={"es": " Comida y cocina I ", "fr": "  "},
        source="tests/create",
    )

    assert row.name == "Food & Cooking I"
    assert row.get_names() == {"en": "Food & Cooking I", "es": "Comida y cocina I"}
    assert row.cefr == "B1"
    assert row.get_prerequisites() == [5, 20]
    assert row.get_extra() == {"icon": "🍳"}
    assert len(_logs(session, CURRICULUM_LEVEL_CREATE)) == 1
    assert len(_logs(session, CURRICULUM_LEVEL_TRANSLATION_UPDATE)) == 1


def test_set_updates_in_place_and_logs_only_changes(session: Session) -> None:
    set_curriculum_level(session, 1, name="First Words", cefr="A1.1")
    set_curriculum_level(session, 1, name="First Words", cefr="A1.2", source="tests/edit")
    set_curriculum_level(session, 1, name="First Words", cefr="A1.2", source="tests/edit")

    assert len(list_curriculum_levels(session)) == 1
    row = get_curriculum_level(session, 1)
    assert row is not None and row.cefr == "A1.2"
    # The second edit changed nothing, so only one update is logged.
    assert len(_logs(session, CURRICULUM_LEVEL_UPDATE)) == 1


def test_translations_set_only_the_languages_named(session: Session) -> None:
    set_curriculum_level(
        session, 20, name="Everyday Life", translations={"es": "Vida", "lt": "Buitis"}
    )

    # None leaves translations alone; a mapping touches only its languages.
    set_curriculum_level(session, 20, name="Everyday Life")
    row = set_curriculum_level(
        session, 20, name="Everyday Life", translations={"es": "Vida diaria"}
    )
    assert row.get_translations() == {"es": "Vida diaria", "lt": "Buitis"}

    # A blank value removes that language.
    set_level_translation(session, 20, "lt", "")
    assert row.get_translations() == {"es": "Vida diaria"}
    assert session.query(CurriculumLevelTranslation).count() == 1


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"level": -1, "name": "x"}, "not a curriculum level"),
        ({"level": 5, "name": "  "}, "English name"),
        ({"level": 5, "name": "x", "cefr": "D1"}, "Unknown CEFR"),
        ({"level": 5, "name": "x", "extra": {"name": "y"}}, "reserved"),
        ({"level": 5, "name": "x", "translations": {"xx": "y"}}, "Unknown language"),
        ({"level": 5, "name": "x", "translations": {"en": "y"}}, "not a translation"),
    ],
)
def test_set_rejects_invalid_fields(session: Session, kwargs: Dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        set_curriculum_level(session, **kwargs)


def test_prerequisites_are_not_sanity_checked(session: Session) -> None:
    """Self-references, cycles and unknown levels are curation questions, not errors."""
    set_curriculum_level(session, 100, name="A", prerequisites=[120, 100, 99999])
    row = set_curriculum_level(session, 120, name="B", prerequisites=[100])
    assert row.get_prerequisites() == [100]


def test_translating_a_level_without_a_row_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="no metadata row"):
        set_level_translation(session, 42, "es", "Hola")


def test_delete_removes_translations_and_ignores_dependents(session: Session) -> None:
    set_curriculum_level(session, 100, name="Food I", translations={"es": "Comida I"})
    set_curriculum_level(session, 120, name="Food II", prerequisites=[100])

    assert delete_curriculum_level(session, 100, source="tests/delete")
    assert not delete_curriculum_level(session, 100)
    assert session.query(CurriculumLevelTranslation).count() == 0
    assert len(_logs(session, CURRICULUM_LEVEL_DELETE)) == 1


def test_manifest_entry_omits_empty_fields_and_merges_extra(session: Session) -> None:
    bare = set_curriculum_level(session, 20, name="Everyday Life")
    full = set_curriculum_level(
        session,
        120,
        name="Food & Cooking II",
        cefr="B1",
        prerequisites=[100],
        extra={"icon": "🍳"},
        notes="internal only",
        translations={"es": "Comida y cocina II"},
    )

    assert to_manifest_entry(bare) == {"level": 20, "name": {"en": "Everyday Life"}}
    assert to_manifest_entry(full) == {
        "level": 120,
        "name": {"en": "Food & Cooking II", "es": "Comida y cocina II"},
        "cefr": "B1",
        "prerequisites": [100],
        "icon": "🍳",
    }


def test_release_round_trip(session: Session, tmp_path: Path) -> None:
    set_curriculum_level(session, 120, name="Food II", prerequisites=[100], notes="n")
    set_curriculum_level(session, 1, name="First Words", cefr="A1", translations={"es": "Primeras"})
    session.commit()

    assert level_release.export_to_release(session, tmp_path) == 2
    records = level_release.read_release_records(tmp_path)
    assert records == [
        {"level": 1, "name": "First Words", "translations": {"es": "Primeras"}, "cefr": "A1"},
        {"level": 120, "name": "Food II", "prerequisites": [100], "notes": "n"},
    ]

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as fresh:
        assert level_release.import_from_release(fresh, tmp_path) == 2
        # Re-importing upserts rather than duplicating.
        assert level_release.import_from_release(fresh, tmp_path) == 2
        rebuilt = [level_release.to_release_record(row) for row in list_curriculum_levels(fresh)]
    assert rebuilt == records
