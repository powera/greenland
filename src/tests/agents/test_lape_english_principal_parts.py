"""Tests for Lape's paired English verb-principal-parts task."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Generator, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from agents.lape.cli import get_argument_parser
from storage.models import Base, Lemma
from storage.backend.config import DataSourceConfig
from storage.models.grammar_fact import GrammarFact
from words.grammar_fact_generation import generate_grammar_fact_for_lemma
from words.grammar_facts import GrammarFactService
from words.grammar_fact_tasks.english_principal_parts import (
    ENGLISH_PRINCIPAL_PARTS_TASK,
    generate_and_store_english_principal_parts,
    generate_english_principal_parts,
)
from wordfreq.tools.generate_mechanical_forms import build_for_lemma


class FakeResponse:
    def __init__(self, structured_data: Optional[dict[str, Any]]) -> None:
        self.structured_data = structured_data


class FakeLLMClient:
    def __init__(self, structured_data: Optional[dict[str, Any]]) -> None:
        self.structured_data = structured_data
        self.prompts: list[str] = []

    def generate_chat(self, prompt: str = "", **_: Any) -> FakeResponse:
        self.prompts.append(prompt)
        return FakeResponse(self.structured_data)


def _agent(structured_data: Optional[dict[str, Any]]) -> Any:
    client = FakeLLMClient(structured_data)
    return SimpleNamespace(
        get_llm_client=lambda: client,
        _client=client,
        config=SimpleNamespace(model="test-model"),
    )


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'principal_parts.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


def _verb() -> Lemma:
    return Lemma(
        lemma_text="hang",
        definition_text="To execute by suspension from the neck.",
        disambiguation="execute",
        pos_type="verb",
        guid="V01_999",
    )


def test_generation_returns_both_parts_and_uses_sense_context() -> None:
    agent = _agent(
        {
            "past": "hanged",
            "past_participle": "hanged",
            "explanation": "Execution sense.",
            "confidence": 0.99,
        }
    )

    result = generate_english_principal_parts(agent, _verb())

    assert result is not None
    assert result.past == "hanged"
    assert result.past_participle == "hanged"
    assert "execute" in agent._client.prompts[0]


def test_both_facts_are_stored_together(session: Session) -> None:
    lemma = _verb()
    session.add(lemma)
    session.commit()
    agent = _agent(
        {
            "past": "hanged",
            "past_participle": "hanged",
            "explanation": "Execution sense.",
            "confidence": 0.99,
        }
    )

    result = generate_and_store_english_principal_parts(agent, session, lemma)

    assert result["fact_value"] == "hanged / hanged"
    facts = {
        row.fact_type: row.fact_value
        for row in session.query(GrammarFact).filter(GrammarFact.lemma_id == lemma.id).all()
    }
    assert facts == {"past": "hanged", "past_participle": "hanged"}
    paradigm = build_for_lemma(session, lemma, "en")
    assert paradigm is not None
    assert paradigm["past"] == "hanged"
    assert paradigm["past_participle"] == "hanged"


def test_complete_existing_pair_is_skipped_without_an_llm_call(session: Session) -> None:
    lemma = _verb()
    session.add(lemma)
    session.flush()
    session.add_all(
        [
            GrammarFact(
                lemma_id=lemma.id,
                language_code="en",
                fact_type="past",
                fact_value="hanged",
            ),
            GrammarFact(
                lemma_id=lemma.id,
                language_code="en",
                fact_type="past_participle",
                fact_value="hanged",
            ),
        ]
    )
    session.commit()
    agent = _agent(None)

    result = generate_and_store_english_principal_parts(agent, session, lemma)

    assert result["reason"] == "existing"
    assert agent._client.prompts == []


def test_lape_cli_exposes_the_compound_task() -> None:
    args = get_argument_parser().parse_args(
        ["--task", "english-principal-parts", "--languages", "en"]
    )

    assert args.task == "english-principal-parts"
    assert ENGLISH_PRINCIPAL_PARTS_TASK == "english_principal_parts"


def test_scalar_past_workqueue_request_generates_the_pair(session: Session) -> None:
    lemma = _verb()
    session.add(lemma)
    session.commit()
    client = FakeLLMClient(
        {
            "past": "hanged",
            "past_participle": "hanged",
            "explanation": "Execution sense.",
            "confidence": 0.99,
        }
    )

    with patch.object(GrammarFactService, "get_llm_client", return_value=client):
        result = generate_grammar_fact_for_lemma(
            session,
            lemma,
            "past",
            "en",
            config=DataSourceConfig(sqlite_path="unused.sqlite"),
        )

    assert result["past"] == "hanged"
    assert result["past_participle"] == "hanged"
    assert session.query(GrammarFact).filter(GrammarFact.lemma_id == lemma.id).count() == 2


def test_non_english_participle_does_not_use_english_pair_generator(
    session: Session,
) -> None:
    lemma = _verb()
    session.add(lemma)
    session.commit()
    client = FakeLLMClient(None)

    with patch.object(GrammarFactService, "get_llm_client", return_value=client):
        result = generate_grammar_fact_for_lemma(
            session,
            lemma,
            "past_participle",
            "fr",
            config=DataSourceConfig(sqlite_path="unused.sqlite"),
        )

    assert result["error"] == "Unsupported fact type: past_participle"
    assert client.prompts == []
