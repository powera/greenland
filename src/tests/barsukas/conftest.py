"""Shared fixtures for Barsukas tests.

Provides a Flask test app backed by a temporary SQLite database,
with a small seed dataset for route smoke tests.

Speed note: building the 43-table schema with `Base.metadata.create_all` costs
~55ms, which dominated setup when every test paid it.  Instead a session-scoped
fixture builds the schema *and* the seed data once into a prototype file, and
each test copies that file (~0.3ms).  Copying rather than sharing one database
is deliberate: these are route tests that write, so they need real isolation,
and a shared database would couple them through the storage layer's global
engine cache.

Two things make the copy safe, and both are easy to get wrong:

* The copy must include the seed data, not just the schema.  Seeding after the
  copy would put the per-test cost straight back.
* `storage.backend.factory` caches engines by db_path and remembers which ones
  have had their tables ensured.  `create_app` calls `configure_backend`, which
  points that process-global state at the test database.  Each test therefore
  needs its own path (tmp_path gives one) and must drop the cached engine
  afterwards, or the cache grows for the whole run and holds file handles open
  on deleted databases.
"""

import shutil
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
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.variant_form import VariantForm


def _build_prototype(target: Path, seed: bool) -> str:
    """Create the schema once at `target`, optionally with the seed data."""
    import storage.models  # noqa: F401 — register all models

    engine = create_engine(f"sqlite:///{target}")
    Base.metadata.create_all(engine)
    if seed:
        factory = sessionmaker(bind=engine)
        session = factory()
        try:
            _seed_database(session)
        finally:
            session.close()
    engine.dispose()
    return str(target)


@pytest.fixture(scope="session")
def _empty_prototype(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Schema-only prototype, built once per session."""
    return _build_prototype(
        tmp_path_factory.mktemp("barsukas-empty") / "prototype.sqlite", seed=False
    )


@pytest.fixture(scope="session")
def _seeded_prototype(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Schema-plus-seed prototype, built once per session.

    Kept separate from the empty one on purpose: `db_session` promises an empty
    database (tests assert counts of zero) and `seeded_session` promises the
    seed.  One shared prototype would quietly break the former.
    """
    return _build_prototype(
        tmp_path_factory.mktemp("barsukas-seeded") / "prototype.sqlite", seed=True
    )


def _drop_cached_engine(db_path: str) -> None:
    """Dispose and forget `storage.backend.factory`'s engine for one database.

    `create_app` and the session fixtures both route through that module-global
    cache, which is keyed by path and never evicts.  Left alone across a few
    hundred tests it keeps an engine -- and its open file handle -- per deleted
    temp database.
    """
    from storage.backend import factory

    for cache_key in (db_path, f"{db_path}\x00readonly"):
        engine = factory._engine_cache.pop(cache_key, None)
        if engine is not None:
            engine.dispose()
        factory._engine_initialized.discard(cache_key)


@pytest.fixture()
def db_path(tmp_path: Path, _empty_prototype: str) -> Generator[str, None, None]:
    """The one database file for this test: schema, no rows.

    Every other database fixture resolves to this same path, so a test that
    writes through `client` and reads through `db_session` sees one database.
    `seeded_db_path` replaces this file's *contents* before anything opens it;
    it does not introduce a second file.
    """
    path = tmp_path / "test.sqlite"
    shutil.copyfile(_empty_prototype, path)
    yield str(path)
    _drop_cached_engine(str(path))


@pytest.fixture()
def seeded_db_path(db_path: str, _seeded_prototype: str) -> str:
    """The same database as `db_path`, refilled with the seed dataset.

    Depending on `db_path` rather than copying independently is what keeps the
    two in sync: two fixtures copying different prototypes onto one path race,
    and the loser's rows vanish.  Ordering is safe because the copy happens at
    fixture setup, before `app` or any session opens the file.
    """
    shutil.copyfile(_seeded_prototype, db_path)
    return db_path


@pytest.fixture()
def backend_config(db_path: str) -> DataSourceConfig:
    """A SQLite `DataSourceConfig` for the per-test database.

    Sessions are built from this rather than from a private `create_engine`,
    so they resolve through the same cached engine `create_app` uses.
    """
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


@pytest.fixture()
def seeded_backend_config(seeded_db_path: str) -> DataSourceConfig:
    """A SQLite `DataSourceConfig` for the seeded per-test database."""
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=seeded_db_path)


@pytest.fixture()
def db_engine(backend_config: DataSourceConfig) -> Generator:
    """The storage layer's engine for the per-test database."""
    from storage.backend.factory import _get_cached_engine

    assert backend_config.sqlite_path is not None
    yield _get_cached_engine(backend_config.sqlite_path)


@pytest.fixture()
def db_session(backend_config: DataSourceConfig) -> Generator[Session, None, None]:
    """A session on the per-test database, via the storage layer."""
    from storage.backend.factory import create_session

    session = create_session(backend_config)
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
    # "gray" carries the alternate spelling "grey" in variant_forms rather than
    # as its own lemma -- the case where search and the import guard used to
    # disagree about what the database contains.
    lemma3 = Lemma(
        id=3,
        lemma_text="gray",
        definition_text="of a color between black and white",
        pos_type="adjective",
        pos_subtype="color",
        guid="J01_001",
        difficulty_level=2,
        confidence=0.9,
        verified=False,
    )
    session.add_all([lemma1, lemma2, lemma3])
    session.flush()

    session.add(
        VariantForm(
            lemma_id=3,
            language_code="en",
            variant_kind="spelling",
            variant_key="grey",
            grammatical_form="adjective/en_positive",
            variant_form_text="grey",
            is_base_form=True,
        )
    )

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
def seeded_session(seeded_backend_config: DataSourceConfig) -> Generator[Session, None, None]:
    """A session on the per-test database, pre-loaded with the seed data."""
    from storage.backend.factory import create_session

    session = create_session(seeded_backend_config)
    yield session
    session.close()


@pytest.fixture()
def app(seeded_db_path: str) -> Flask:
    """Create a Flask test app backed by the temporary database.

    The database arrives already seeded with a small dataset, so route smoke
    tests have data to render.
    """
    from barsukas.app import create_app
    from barsukas.config import Config

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        DB_PATH = seeded_db_path
        DEBUG = False

    application = create_app(config_class=TestConfig)
    return application


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Return a Flask test client."""
    return app.test_client()
