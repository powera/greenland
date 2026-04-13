"""Shared fixtures for Barsukas tests.

Provides a Flask test app backed by a temporary SQLite database,
with a small seed dataset for route smoke tests.
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models.schema import (
    Base,
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    """Return a path for a temporary SQLite database file."""
    return str(tmp_path / "test.sqlite")


@pytest.fixture()
def db_engine(db_path: str) -> Generator:
    """Create a SQLAlchemy engine with all tables, yielding the engine."""
    import storage.models  # noqa: F401 — register all models

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:  # type: ignore[type-arg]
    """Provide a transactional DB session for helper-level tests."""
    factory = sessionmaker(bind=db_engine)
    session = factory()
    yield session
    session.close()


def _seed_database(session: Session) -> None:
    """Insert a minimal dataset used by route smoke tests."""
    lemma1 = Lemma(
        id=1,
        lemma_text="eat",
        definition_text="to consume food",
        pos_type="verb",
        pos_subtype="transitive",
        guid="V01_001",
        difficulty_level=3,
        confidence=0.95,
        verified=True,
    )
    lemma2 = Lemma(
        id=2,
        lemma_text="house",
        definition_text="a building for living in",
        pos_type="noun",
        pos_subtype="building",
        guid="N01_001",
        difficulty_level=2,
        confidence=0.9,
        verified=False,
    )
    session.add_all([lemma1, lemma2])
    session.flush()

    # Add a table-based translation for lemma1
    t1 = LemmaTranslation(lemma_id=1, language_code="fr", translation="manger")
    t2 = LemmaTranslation(lemma_id=1, language_code="es", translation="comer")
    session.add_all([t1, t2])

    # Add a difficulty override
    override = LemmaDifficultyOverride(lemma_id=1, language_code="zh", difficulty_level=5)
    session.add(override)

    # Add derivative forms covering all three categories
    forms = [
        DerivativeForm(
            lemma_id=1,
            language_code="en",
            derivative_form_text="eating",
            grammatical_form="present_participle",
            is_base_form=False,
        ),
        DerivativeForm(
            lemma_id=1,
            language_code="en",
            derivative_form_text="consume",
            grammatical_form="synonym",
            is_base_form=False,
        ),
        DerivativeForm(
            lemma_id=1,
            language_code="fr",
            derivative_form_text="bouffer",
            grammatical_form="synonym",
            is_base_form=False,
        ),
        DerivativeForm(
            lemma_id=1,
            language_code="en",
            derivative_form_text="eat up",
            grammatical_form="alternate_spelling",
            is_base_form=False,
        ),
    ]
    session.add_all(forms)

    sentence1 = Sentence(
        id=1,
        guid="S_00001",
        pattern_type="SVO",
        minimum_level=1,
        verified=False,
        rejected=False,
    )
    session.add(sentence1)
    session.flush()

    sentence_translation_en = SentenceTranslation(
        sentence_id=1,
        language_code="en",
        translation_text="I eat",
    )
    sentence_translation_lt = SentenceTranslation(
        sentence_id=1,
        language_code="lt",
        translation_text="Aš valgau",
    )
    session.add_all([sentence_translation_en, sentence_translation_lt])

    session.commit()


@pytest.fixture()
def seeded_session(db_engine) -> Generator[Session, None, None]:  # type: ignore[type-arg]
    """Provide a DB session pre-loaded with seed data."""
    factory = sessionmaker(bind=db_engine)
    session = factory()
    _seed_database(session)
    yield session
    session.close()


@pytest.fixture()
def app(db_path: str, db_engine) -> Flask:  # type: ignore[type-arg]
    """Create a Flask test app backed by the temporary database.

    The database is seeded with a small dataset so route smoke tests
    have data to render.
    """
    from barsukas.app import create_app
    from barsukas.config import Config
    from storage.backend.config import BackendType, DataSourceConfig

    # Seed the database before the app touches it
    factory = sessionmaker(bind=db_engine)
    session = factory()
    _seed_database(session)
    session.close()

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        DB_PATH = db_path
        DEBUG = False

    application = create_app(config_class=TestConfig)
    return application


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Return a Flask test client."""
    return app.test_client()
