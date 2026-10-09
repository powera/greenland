"""The geography migration preserves reviewed senses and separates homographs."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.lemma import add_lemma
from storage.models.schema import Base, Lemma
from words.difficulty.geography_catalog import GEOGRAPHY_SENSES, GeographySense, find_sense


def migration_module() -> ModuleType:
    source = Path(__file__).resolve().parents[3] / "migrations/20261009_add_geography_senses.py"
    spec = importlib.util.spec_from_file_location("geography_migration", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rerun_preserves_existing_senses_and_separates_language() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        existing = add_lemma(
            session,
            "English",
            "Existing reviewed English language",
            "noun",
            "communication_information",
            difficulty_level=400,
        )
        original_guid = existing.guid
        module = migration_module()
        added = module.add_missing_senses(session)
        assert added
        assert existing.guid == original_guid
        assert existing.difficulty_level == 400
        assert existing.definition_text == "Existing reviewed English language"
        assert module.add_missing_senses(session) == []
        assert len({lemma.guid for lemma in session.query(Lemma)}) == session.query(Lemma).count()
        assert session.query(Lemma).filter_by(lemma_text="English").count() == 2
        assert (
            len(
                [
                    sense
                    for sense in GEOGRAPHY_SENSES
                    if sense.pos_subtype == "communication_information" and sense.base_level == 233
                ]
            )
            == 22
        )


def test_ambiguous_senses_rejected() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sense = GeographySense(
        "French person", "noun", "nationality", "a person from France", ("France",)
    )
    with Session(engine) as session:
        for definition in ("a French citizen", "a French inhabitant"):
            add_lemma(session, "French person", definition, "noun", "nationality")
        with pytest.raises(ValueError, match="Ambiguous"):
            migration_module().add_missing_senses(session, (sense,))


def test_generic_origin_adjectives_are_not_geography() -> None:
    assert (
        find_sense(Lemma(lemma_text="regional", pos_type="adjective", pos_subtype="origin")) is None
    )
    igbo = next(sense for sense in GEOGRAPHY_SENSES if sense.lemma_text == "Igbo person")
    assert igbo.base_level == 1031
    assert "ethnic" in igbo.definition


def test_optional_base_normalization_is_logged_and_rollback_safe() -> None:
    from storage.models.operation_log import OperationLog
    from storage.models.schema import LemmaDifficultyOverride

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        language = add_lemma(
            session,
            "English",
            "English language",
            "noun",
            "communication_information",
            difficulty_level=400,
        )
        country = add_lemma(
            session, "England", "England country", "noun", "region", difficulty_level=245
        )
        generic = add_lemma(
            session, "regional", "relating to a region", "adjective", "origin", difficulty_level=360
        )
        session.add(
            LemmaDifficultyOverride(lemma_id=country.id, language_code="lt", difficulty_level=18)
        )
        session.commit()
        module = migration_module()
        updates = module.normalize_base_levels(session)
        assert len(updates) == 2
        assert language.difficulty_level == 233
        assert country.difficulty_level == 231
        assert generic.difficulty_level == 360
        assert session.query(LemmaDifficultyOverride).one().difficulty_level == 18
        assert session.query(OperationLog).filter_by(source=module.SOURCE).count() == 2
        assert module.normalize_base_levels(session) == []
        session.rollback()
        assert language.difficulty_level == 400
        assert country.difficulty_level == 245
        assert session.query(OperationLog).filter_by(source=module.SOURCE).count() == 0


def test_level_names_preserve_human_edits_and_rollback() -> None:
    from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        set_curriculum_level(
            session,
            231,
            "Human title",
            cefr="B1",
            prerequisites=[15],
            notes="Keep this",
            translations={"lt": "Žmogaus vardas"},
        )
        session.commit()
        module = migration_module()
        assert module.ensure_level_names(session) == 3
        existing = get_curriculum_level(session, 231)
        assert existing is not None
        assert existing.name == "Human title"
        assert existing.cefr == "B1"
        assert existing.notes == "Keep this"
        assert existing.translations[0].name == "Žmogaus vardas"
        assert get_curriculum_level(session, 1031) is not None
        assert module.ensure_level_names(session) == 0
        session.rollback()
        assert get_curriculum_level(session, 1031) is None
