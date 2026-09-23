"""Tests for the high-frequency missing-word report."""

from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from reports.missing_words import check_high_frequency_missing_words
from storage.models import Base, Lemma, PendingImport, WordToken


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'missing_words.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


def _pending(word: str, *, queried_word: str | None = None) -> PendingImport:
    return PendingImport(
        english_word=word,
        queried_word=queried_word,
        definition="Pending definition",
        disambiguation_translation="laukiama",
        disambiguation_language="lt",
    )


def test_pending_imports_are_reported_separately_from_missing_words(session: Session) -> None:
    session.add_all(
        [
            WordToken(token="present", language_code="en", frequency_rank=1),
            WordToken(token="social", language_code="en", frequency_rank=2),
            WordToken(token="foreign", language_code="en", frequency_rank=3),
            WordToken(token="novelword", language_code="en", frequency_rank=4),
            Lemma(
                lemma_text="present",
                definition_text="Existing word",
                pos_type="adjective",
                guid="A01_001",
            ),
            _pending("social"),
            _pending("alien", queried_word="foreign"),
        ]
    )
    session.commit()

    results = check_high_frequency_missing_words(session, top_n=4)

    assert [row["word"] for row in results["pending_words"]] == ["social", "foreign"]
    assert results["pending_count"] == 2
    assert [row["word"] for row in results["missing_words"]] == ["novelword"]
    assert results["missing_count"] == 1


def test_existing_word_wins_over_stale_pending_import(session: Session) -> None:
    session.add_all(
        [
            WordToken(token="social", language_code="en", frequency_rank=1),
            Lemma(
                lemma_text="social",
                definition_text="Existing word",
                pos_type="adjective",
                guid="A01_001",
            ),
            _pending("social"),
        ]
    )
    session.commit()

    results = check_high_frequency_missing_words(session, top_n=1)

    assert results["pending_count"] == 0
    assert results["missing_count"] == 0
