"""Balanced equivalent volumes preserve subjects, frozen menus and existing placements."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from quality import curriculum_volumes as volumes
from storage.backend import BackendType, DataSourceConfig
from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.models.schema import Base, Lemma


def setup_families(tmp_path: Path) -> tuple[Session, DataSourceConfig]:
    path = tmp_path / "main.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for family, count in zip(volumes.VOLUME_FAMILIES, (6, 5, 4)):
        set_curriculum_level(
            session, family.levels[0], family.name, cefr="C1", notes="One shared subject boundary"
        )
        for index in range(count):
            session.add(
                Lemma(
                    guid=f"N72_{family.levels[0]}_{index}",
                    lemma_text=f"sense-{index}",
                    definition_text="A reviewed sense.",
                    pos_type="noun",
                    difficulty_level=family.levels[0],
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


def test_install_balance_and_repeat_preserve_other_topics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, config = setup_families(tmp_path)
    backups: list[str] = []

    def backup(config: DataSourceConfig, label: str, tier: str) -> Path:
        backups.append(tier)
        return tmp_path / "backup"

    monkeypatch.setattr(volumes, "create_backup", backup)
    preview = volumes.balance_volumes(
        session, config, dry_run=True, families=volumes.VOLUME_FAMILIES[:3]
    )
    assert len(preview["new_volumes"]) == 5
    assert session.query(Lemma).filter(Lemma.difficulty_level == 1310).count() == 0
    result = volumes.balance_volumes(session, config, families=volumes.VOLUME_FAMILIES[:3])
    assert result["new_volumes"] == 5
    assert [list(item["levels"].values()) for item in result["families"]] == [
        [2, 2, 2],
        [2, 2, 1],
        [2, 2],
    ]
    for family in volumes.VOLUME_FAMILIES[:3]:
        base = get_curriculum_level(session, family.levels[0])
        assert base is not None
        for position, level in enumerate(family.levels):
            row = get_curriculum_level(session, level)
            assert row is not None
            assert row.name == volumes.volume_name(family, position)
            assert row.cefr == "C1" and row.notes == base.notes
    assert session.query(Lemma).filter(Lemma.guid == "N72_other").one().difficulty_level == 1302
    assert (
        volumes.balance_volumes(session, config, families=volumes.VOLUME_FAMILIES[:3])["moved"] == 0
    )
    assert backups == ["minor"]
    session.close()


def test_live_allocator_reserves_balanced_slots_and_respects_menu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, config = setup_families(tmp_path)
    monkeypatch.setattr(volumes, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    volumes.balance_volumes(session, config, families=volumes.VOLUME_FAMILIES[:3])
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


def test_occupied_volume_number_blocks_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    session, config = setup_families(tmp_path)
    set_curriculum_level(session, 1310, "Some other topic", cefr="C1")
    session.commit()
    backup = Mock()
    monkeypatch.setattr(volumes, "create_backup", backup)
    with pytest.raises(ValueError, match="metadata conflict"):
        volumes.balance_volumes(session, config, families=volumes.VOLUME_FAMILIES[:3])
    backup.assert_not_called()
    session.close()


def test_new_adverbs_flow_to_empty_landing_volume_without_rebalancing_existing(
    tmp_path: Path,
) -> None:
    session, _ = setup_families(tmp_path)
    for level, name in ((105, "Adverbs"), (324, "Adverbs 2")):
        set_curriculum_level(
            session, level, name, cefr="B1", notes="Ordinary everyday adverbs only"
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
