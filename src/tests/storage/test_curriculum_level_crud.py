"""CRUD, validation and release round-trip for curriculum level metadata."""

from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
import constants
from storage.crud.curriculum_level import (
    delete_curriculum_level,
    get_curriculum_level,
    list_curriculum_levels,
    manifest_entries,
    patch_curriculum_level,
    set_curriculum_level,
    set_level_translation,
    to_manifest_entry,
    validate_curriculum_levels,
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
        prerequisites=["20", 16, 20],
        extra={"icon": "🍳"},
        translations={"es": " Comida y cocina I ", "fr": "  "},
        source="tests/create",
    )

    assert row.name == "Food & Cooking I"
    assert row.get_names() == {"en": "Food & Cooking I", "es": "Comida y cocina I"}
    assert row.cefr == "B1"
    assert row.get_prerequisites() == [16, 20]
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
        ({"level": 100, "name": "x", "prerequisites": [100]}, "its own prerequisite"),
        ({"level": 100, "name": "x", "prerequisites": [15]}, "below 16"),
        ({"level": 100, "name": "x", "prerequisites": [1399]}, "not a curriculum level"),
        ({"level": 100, "name": "x", "prerequisites": [99999]}, "not a curriculum level"),
        ({"level": 100, "name": "x", "series": "Plants"}, "lower-case slug"),
        ({"level": 100, "name": "x", "series": "plants"}, "needs a volume"),
        ({"level": 100, "name": "x", "volume": 2, "series": None}, "needs a series"),
        ({"level": 100, "name": "x", "series": "plants", "volume": 0}, "start at 1"),
        ({"level": 100, "name": "x", "themes": ["beach"]}, "Unknown theme"),
        ({"level": 100, "name": "x", "content_flags": ["violence"]}, "Unknown content flag"),
    ],
)
def test_set_rejects_invalid_fields(session: Session, kwargs: Dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        set_curriculum_level(session, **kwargs)


def test_prerequisite_on_a_level_without_a_row_is_accepted_but_reported(
    session: Session,
) -> None:
    """A release file may name a level before its row is imported."""
    row = set_curriculum_level(session, 100, name="A", prerequisites=[120])
    assert row.get_prerequisites() == [120]
    assert validate_curriculum_levels(session) == [
        "Level 100 requires 120, which has no metadata row"
    ]
    set_curriculum_level(session, 120, name="B")
    assert validate_curriculum_levels(session) == []


def test_prerequisite_floor_follows_the_constant(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(constants, "MIN_PREREQUISITE_LEVEL", 20)
    with pytest.raises(ValueError, match="below 20"):
        set_curriculum_level(session, 100, name="A", prerequisites=[18])


def test_cycles_are_rejected(session: Session) -> None:
    set_curriculum_level(session, 100, name="A", prerequisites=[120])
    set_curriculum_level(session, 120, name="B", prerequisites=[130])
    with pytest.raises(ValueError, match="cycle: 130 -> 100 -> 120 -> 130"):
        set_curriculum_level(session, 130, name="C", prerequisites=[100])
    assert get_curriculum_level(session, 130) is None


def test_series_volumes_imply_prerequisites_for_cycles(session: Session) -> None:
    set_curriculum_level(session, 165, name="Plants", series="plants", volume=1)
    set_curriculum_level(session, 170, name="Plants 2", series="plants", volume=2)
    # 170 implicitly requires 165, so 165 requiring 170 is a cycle.
    with pytest.raises(ValueError, match="cycle"):
        set_curriculum_level(session, 165, name="Plants", prerequisites=[170])


def test_a_series_volume_is_used_once(session: Session) -> None:
    set_curriculum_level(session, 165, name="Plants", series="plants", volume=1)
    with pytest.raises(ValueError, match="already volume 1"):
        set_curriculum_level(session, 170, name="Plants 2", series="plants", volume=1)


def test_series_gaps_are_reported(session: Session) -> None:
    set_curriculum_level(session, 165, name="Plants", series="plants", volume=1)
    set_curriculum_level(session, 170, name="Plants 3", series="plants", volume=3)
    assert validate_curriculum_levels(session) == [
        "Series 'plants' has volumes [1, 3]; expected 1..2"
    ]


def test_new_fields_are_kept_unless_passed(session: Session) -> None:
    set_curriculum_level(
        session,
        204,
        name="Weapons",
        series="combat",
        volume=1,
        themes=["travel", "daily-life", "travel"],
        content_flags=["weapons", "drugs"],
    )
    # A caller that only renames (level naming, curriculum review) keeps them.
    row = set_curriculum_level(session, 204, name="Weapons and Combat", cefr="A2")
    assert (row.series, row.volume) == ("combat", 1)
    assert row.get_themes() == ["travel", "daily-life"]
    assert row.get_content_flags() == ["drugs", "weapons"]

    row = set_curriculum_level(
        session, 204, name="Weapons and Combat", series=None, volume=None, themes=[]
    )
    assert (row.series, row.volume, row.get_themes()) == (None, None, [])
    assert row.get_content_flags() == ["drugs", "weapons"]


def test_patch_changes_only_the_named_fields(session: Session) -> None:
    set_curriculum_level(
        session, 120, name="Food II", cefr="B1", prerequisites=[100], extra={"icon": "x"}
    )
    row = patch_curriculum_level(session, 120, themes=["daily-life"])
    assert (row.name, row.cefr, row.get_prerequisites(), row.get_extra()) == (
        "Food II",
        "B1",
        [100],
        {"icon": "x"},
    )
    assert row.get_themes() == ["daily-life"]
    with pytest.raises(ValueError, match="no metadata row"):
        patch_curriculum_level(session, 999, themes=[])


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


def test_manifest_entries_chain_volumes_and_whitelist_extra(session: Session) -> None:
    set_curriculum_level(session, 10, name="Food", series="food", volume=1)
    set_curriculum_level(session, 120, name="Food 2", series="food", volume=2)
    set_curriculum_level(
        session,
        130,
        name="Food 3",
        series="food",
        volume=3,
        prerequisites=[150],
        themes=["daily-life", "travel"],
        content_flags=["drugs"],
        extra={"icon": "🍳", "cefr_estimate_method": "manual"},
    )
    set_curriculum_level(session, 150, name="Cooking verbs")

    entries = {entry["level"]: entry for entry in manifest_entries(list_curriculum_levels(session))}
    # Volume 1 is a core level below the prerequisite floor, so 120 needs nothing.
    assert "prerequisites" not in entries[120]
    assert entries[120]["series"] == "food" and entries[120]["volume"] == 2
    assert entries[130] == {
        "level": 130,
        "name": {"en": "Food 3"},
        "prerequisites": [120, 150],
        "series": "food",
        "volume": 3,
        "themes": ["daily-life", "travel"],
        "content_flags": ["drugs"],
        "icon": "🍳",
    }


def test_shipped_release_file_is_consistent() -> None:
    """The checked-in release has no prerequisite cycles, dangling links or series gaps."""
    release_dir = Path(constants.RELEASE_DIR) / level_release.RELEASE_DIRNAME
    if not (release_dir / level_release.RELEASE_FILENAME).exists():
        pytest.skip("no levels release file")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as fresh:
        level_release.import_from_release(fresh, release_dir)
        assert validate_curriculum_levels(fresh) == []


def test_release_round_trip(session: Session, tmp_path: Path) -> None:
    set_curriculum_level(
        session,
        120,
        name="Food II",
        prerequisites=[100],
        notes="n",
        series="food",
        volume=2,
        themes=["school"],
        content_flags=["explicit-anatomy"],
    )
    set_curriculum_level(session, 1, name="First Words", cefr="A1", translations={"es": "Primeras"})
    session.commit()

    assert level_release.export_to_release(session, tmp_path) == 2
    records = level_release.read_release_records(tmp_path)
    assert records == [
        {"level": 1, "name": "First Words", "translations": {"es": "Primeras"}, "cefr": "A1"},
        {
            "level": 120,
            "name": "Food II",
            "prerequisites": [100],
            "series": "food",
            "volume": 2,
            "themes": ["school"],
            "content_flags": ["explicit-anatomy"],
            "notes": "n",
        },
    ]

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as fresh:
        assert level_release.import_from_release(fresh, tmp_path) == 2
        # Re-importing upserts rather than duplicating.
        assert level_release.import_from_release(fresh, tmp_path) == 2
        rebuilt = [level_release.to_release_record(row) for row in list_curriculum_levels(fresh)]
    assert rebuilt == records
