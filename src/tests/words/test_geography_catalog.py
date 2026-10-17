"""The geography catalog is internally consistent, and 1031 splits by sense."""

import importlib.util
from collections import Counter
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.crud.lemma import add_lemma
from storage.models.schema import Base, Lemma
from words.difficulty.geography_catalog import (
    CATALOG_COUNTRY_NAMES,
    GEOGRAPHY_SENSES,
    MAIN,
    MAIN_COUNTRY_NAMES,
    find_sense,
)


def split_migration() -> ModuleType:
    source = (
        Path(__file__).resolve().parents[3]
        / "migrations/20261017_split_extended_geography_levels.py"
    )
    spec = importlib.util.spec_from_file_location("geography_level_split", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_association_names_a_catalog_country() -> None:
    for sense in GEOGRAPHY_SENSES:
        assert set(sense.countries) <= CATALOG_COUNTRY_NAMES, sense.lemma_text


def test_main_tier_senses_follow_a_main_country() -> None:
    """Otherwise promotion would send a 232/233 sense to the extended tier."""
    for sense in GEOGRAPHY_SENSES:
        if sense.tier == MAIN:
            assert set(sense.countries) & MAIN_COUNTRY_NAMES, sense.lemma_text


def test_each_headword_is_listed_once_per_subtype() -> None:
    counts = Counter((sense.lemma_text, sense.pos_subtype) for sense in GEOGRAPHY_SENSES)
    assert [key for key, count in counts.items() if count > 1] == []


def test_split_levels_by_sense() -> None:
    levels = {(sense.tier, sense.pos_subtype): sense.base_level for sense in GEOGRAPHY_SENSES}
    assert levels[("main", "region")] == 231
    assert levels[("main", "language_name")] == 233
    assert levels[("extended", "region")] == 1031
    assert levels[("extended", "nationality")] == levels[("extended", "origin")] == 1032
    assert levels[("extended", "language_name")] == 1033
    by_text = {(sense.lemma_text, sense.pos_subtype): sense for sense in GEOGRAPHY_SENSES}
    assert by_text[("Chinese", "language_name")].base_level == 233
    assert by_text[("Cantonese", "language_name")].base_level == 1033
    assert by_text[("Greek", "nationality")].base_level == 232
    assert by_text[("Puerto Rico", "region")].base_level == 1031
    # Singapore the place is a city lemma; only its people are listed.
    assert ("Singapore", "region") not in by_text
    assert ("Singaporean", "nationality") in by_text


def test_georgia_the_state_is_not_the_country() -> None:
    state = Lemma(lemma_text="Georgia", pos_type="noun", pos_subtype="region")
    country = Lemma(
        lemma_text="Georgia", pos_type="noun", pos_subtype="region", disambiguation="country"
    )
    assert find_sense(state) is None
    sense = find_sense(country)
    assert sense is not None and sense.base_level == 1031


def test_split_moves_old_extended_senses_and_names_levels() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        mongolia = add_lemma(
            session, "Mongolia", "the country", "noun", "region", difficulty_level=1031
        )
        igbo = add_lemma(
            session, "Igbo", "the language", "noun", "language_name", difficulty_level=1031
        )
        person = add_lemma(
            session, "Igbo person", "an Igbo", "noun", "nationality", difficulty_level=1031
        )
        set_curriculum_level(session, 1031, "Extended Countries, Languages and Ethnicities")
        set_curriculum_level(session, 1033, "Human title")
        session.commit()

        module = split_migration()
        moves = module.move_senses(session)
        assert {(lemma.lemma_text, level) for lemma, level in moves} == {
            ("Igbo", 1033),
            ("Igbo person", 1032),
        }
        assert mongolia.difficulty_level == 1031
        assert igbo.difficulty_level == 1033 and person.difficulty_level == 1032
        assert module.move_senses(session) == []

        assert module.name_levels(session) == 2
        renamed = get_curriculum_level(session, 1031)
        kept = get_curriculum_level(session, 1033)
        assert renamed is not None and renamed.name == "Extended Countries"
        assert kept is not None and kept.name == "Human title"
        assert module.name_levels(session) == 0
