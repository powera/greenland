"""Tests for Dramblys pending-import synonym screening."""

from pathlib import Path
from typing import Any, Dict, Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from words.pending_imports.synonym_screening import (
    find_matching_translation_languages,
    run_synonym_screening,
)
from storage.models import Base, Lemma, LemmaTranslation, PendingImport


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'screening.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


class FakeResponse:
    def __init__(self, structured_data: Dict[str, Any]) -> None:
        self.structured_data = structured_data


class FakeLLMClient:
    def __init__(self, structured_data: Dict[str, Any]) -> None:
        self.structured_data = structured_data

    def generate_chat(self, **_: Any) -> FakeResponse:
        return FakeResponse(self.structured_data)


def _add_fast_lemma(session: Session) -> Lemma:
    lemma = Lemma(
        lemma_text="fast",
        definition_text="moving or able to move quickly",
        pos_type="adverb",
        pos_subtype="manner",
        guid="R99_001",
        confidence=0.95,
        verified=True,
    )
    session.add(lemma)
    session.flush()
    session.add_all(
        [
            LemmaTranslation(lemma_id=lemma.id, language_code="lt", translation="greitai"),
            LemmaTranslation(lemma_id=lemma.id, language_code="zh", translation="快速地"),
            LemmaTranslation(lemma_id=lemma.id, language_code="fr", translation="rapidement"),
            LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="rápidamente"),
        ]
    )
    session.flush()
    return lemma


def test_run_synonym_screening_resolves_existing_candidate(session: Session) -> None:
    """A speedily screen resolves fast and marks it strong with 3+ matches."""
    fast = _add_fast_lemma(session)
    pending = PendingImport(
        english_word="speedily",
        definition="quickly; with speed",
        disambiguation_translation="greitai",
        disambiguation_language="lt",
        pos_type="adverb",
        pos_subtype="manner",
        source="pytest",
    )
    session.add(pending)
    session.commit()

    llm_client = FakeLLMClient(
        {
            "candidate_synonyms": [
                {
                    "lemma": "fast",
                    "synonymy": "near",
                    "score": 0.88,
                    "explanation": "Both can mean moving quickly.",
                },
                {
                    "lemma": "quickly",
                    "synonymy": "strong",
                    "score": 0.91,
                    "explanation": "Usually interchangeable.",
                },
            ],
            "lithuanian_translation": "greitai",
            "chinese_translation": "快速地",
            "french_translation": "rapidement",
            "spanish_translation": "rápidamente",
        }
    )

    candidates = run_synonym_screening(session, pending, llm_client, model="test-model")

    assert len(candidates) == 2
    fast_candidate = next(
        candidate for candidate in candidates if candidate.candidate_text == "fast"
    )
    assert fast_candidate.lemma_id == fast.id
    assert fast_candidate.same_pos is True
    assert fast_candidate.matched_translation_count == 4
    assert fast_candidate.is_strong is True


def test_translation_overlap_threshold_is_three(session: Session) -> None:
    """Three exact non-English translation matches make the overlap strong enough."""
    fast = _add_fast_lemma(session)

    three_matches = find_matching_translation_languages(
        session,
        fast,
        {
            "lt": " greitai ",
            "zh": "快速地",
            "fr": "Rapidement",
            "es": "deprisa",
        },
    )
    two_matches = find_matching_translation_languages(
        session,
        fast,
        {
            "lt": "greitai",
            "zh": "快速地",
            "fr": "vite",
        },
    )

    assert three_matches == ["lt", "zh", "fr"]
    assert two_matches == ["lt", "zh"]
