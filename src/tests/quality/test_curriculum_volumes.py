"""Balanced equivalent volumes preserve subjects, frozen menus and existing placements."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from quality import curriculum_volumes as volumes
from storage.backend import BackendType, DataSourceConfig
from storage.crud.curriculum_level import set_curriculum_level
from storage.models.schema import Base, Lemma

BOUNDARY = "One shared subject boundary"

# series -> (volume-1 name, levels in volume order, senses parked on volume 1)
FAMILIES = {
    "advanced-character": ("Advanced Character, Thought and Feelings", (1300, 1310, 1311), 6),
    "advanced-actions": ("Advanced Actions, Change and Movement", (1301, 1320, 1321), 5),
    "figurative": ("Figurative Language and Imagery", (1182, 1330), 4),
}


def setup_families(tmp_path: Path) -> tuple[Session, DataSourceConfig]:
    path = tmp_path / "main.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for series, (name, levels, count) in FAMILIES.items():
        for volume, level in enumerate(levels, start=1):
            set_curriculum_level(
                session,
                level,
                name if volume == 1 else f"{name} {volume}",
                cefr="C1",
                notes=BOUNDARY,
                series=series,
                volume=volume,
            )
        for index in range(count):
            session.add(
                Lemma(
                    guid=f"N72_{levels[0]}_{index}",
                    lemma_text=f"sense-{index}",
                    definition_text="A reviewed sense.",
                    pos_type="noun",
                    difficulty_level=levels[0],
                )
            )
    session.add(
        Lemma(
            guid="N72_other",
            lemma_text="untouched",
            definition_text="Another subject.",
            pos_type="noun",
            difficulty_level=1302,
        )
    )
    session.commit()
    return session, DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(path))


def test_families_come_from_series_columns(tmp_path: Path) -> None:
    session, _ = setup_families(tmp_path)
    # A series whose volumes have no shared boundary notes is not interchangeable.
    set_curriculum_level(session, 165, "Plants and Growth", cefr="B1", series="plants", volume=1)
    set_curriculum_level(session, 170, "Plants and Growth 2", cefr="B1", series="plants", volume=2)
    # Nor is one whose volumes differ in CEFR.
    set_curriculum_level(session, 196, "Events", cefr="B1", notes="x", series="events", volume=1)
    set_curriculum_level(session, 285, "Events 2", cefr="B2", notes="x", series="events", volume=2)
    session.commit()

    families = volumes.volume_families(session)
    assert [(family.series, family.levels) for family in families] == [
        ("advanced-actions", (1301, 1320, 1321)),
        ("advanced-character", (1300, 1310, 1311)),
        ("figurative", (1182, 1330)),
    ]
    context = volumes.volume_context(session)
    assert "1300, 1310, 1311 | Advanced Character, Thought and Feelings" in context
    assert "Plants" not in context
    session.close()


def test_balance_and_repeat_preserve_other_topics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, config = setup_families(tmp_path)
    backups: list[str] = []

    def backup(config: DataSourceConfig, label: str, tier: str) -> Path:
        backups.append(tier)
        return tmp_path / "backup"

    monkeypatch.setattr(volumes, "create_backup", backup)
    preview = volumes.balance_volumes(session, config, dry_run=True)
    assert len(preview["moves"]) == 4 + 3 + 2
    assert session.query(Lemma).filter(Lemma.difficulty_level == 1310).count() == 0
    result = volumes.balance_volumes(session, config)
    assert {item["family"]: list(item["levels"].values()) for item in result["families"]} == {
        "Advanced Actions, Change and Movement": [2, 2, 1],
        "Advanced Character, Thought and Feelings": [2, 2, 2],
        "Figurative Language and Imagery": [2, 2],
    }
    assert session.query(Lemma).filter(Lemma.guid == "N72_other").one().difficulty_level == 1302
    assert volumes.balance_volumes(session, config)["moved"] == 0
    assert backups == ["minor"]
    session.close()


def test_balance_can_be_limited_to_named_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, config = setup_families(tmp_path)
    monkeypatch.setattr(volumes, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    result = volumes.balance_volumes(session, config, series=["figurative"])
    assert result["moved"] == 2
    assert session.query(Lemma).filter(Lemma.difficulty_level == 1310).count() == 0
    session.close()


def test_unknown_series_blocks_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    session, config = setup_families(tmp_path)
    backup = Mock()
    monkeypatch.setattr(volumes, "create_backup", backup)
    with pytest.raises(ValueError, match="Not an interchangeable volume family"):
        volumes.balance_volumes(session, config, series=["plants"])
    backup.assert_not_called()
    session.close()


def test_live_allocator_reserves_balanced_slots_and_respects_menu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, config = setup_families(tmp_path)
    monkeypatch.setattr(volumes, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    volumes.balance_volumes(session, config)
    allocator = volumes.VolumeAllocator(session)
    assert [allocator.choose(1300, [1300, 1310, 1311], 1399) for _ in range(6)] == [
        1300,
        1310,
        1311,
        1300,
        1310,
        1311,
    ]
    assert allocator.choose(1300, [1300], 1399) == 1300
    assert allocator.choose(1300, [1300, 1310, 1311], 1311) == 1311
    assert allocator.choose(1399, [1399], None) == 1399
    assert allocator.choose(1302, [1302, 1300], 1399) == 1302
    session.close()


def test_new_adverbs_flow_to_empty_landing_volume_without_rebalancing_existing(
    tmp_path: Path,
) -> None:
    session, _ = setup_families(tmp_path)
    for volume, (level, name) in enumerate(((105, "Adverbs"), (324, "Adverbs 2")), start=1):
        set_curriculum_level(
            session,
            level,
            name,
            cefr="B1",
            notes="Ordinary everyday adverbs only",
            series="adverbs",
            volume=volume,
        )
    for index in range(3):
        session.add(
            Lemma(
                guid=f"D01_existing{index}",
                lemma_text=f"adverb-{index}",
                definition_text="An ordinary adverb.",
                pos_type="adverb",
                difficulty_level=105,
            )
        )
    session.commit()
    allocator = volumes.VolumeAllocator(session)
    assert [allocator.choose(105, [105, 324], 1399) for _ in range(3)] == [324, 324, 324]
    assert session.query(Lemma).filter(Lemma.difficulty_level == 105).count() == 3
    assert session.query(Lemma).filter(Lemma.difficulty_level == 324).count() == 0
    assert allocator.choose(105, [105, 324], 105) == 105
    session.close()
