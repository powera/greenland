"""Tests for the fully specified term add path (words.add_term).

add_term is the path for terms the sense-discovery pipeline cannot handle: the
caller supplies the term, POS, subtype and definition, and the LLM is asked for
translations only. The motivating case is a borrowed legal term like "ex post
facto", where asking the model to find a native English headword produces
nonsense.

The LLM call is stubbed here, so no real request is made. What is covered is
the logic around it: POS validation against the GUID prefixes, the existence
guard, exactly-one-lemma, translation storage, and the partial-response case.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401
from storage.backend.config import BackendType, DataSourceConfig
from storage.models import Base, Lemma
from storage.models.operation_log import OperationLog
from storage.translation_helpers import get_translation
from words.add_term import TRANSLATION_LANGUAGES, add_term


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'add_term.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


@pytest.fixture()
def config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=":memory:", model="test-model"
    )


class _FakeResponse:
    def __init__(self, structured_data: Any) -> None:
        self.structured_data = structured_data


class _FakeClient:
    """Stand-in for UnifiedLLMClient returning a canned translation object."""

    def __init__(self, structured_data: Any, error: Optional[Exception] = None) -> None:
        self._structured_data = structured_data
        self._error = error
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._structured_data)


def _all_languages(text: str = "ex post facto") -> Dict[str, str]:
    """A complete response: every target language borrows the term unchanged."""
    return {lang_code: text for lang_code in TRANSLATION_LANGUAGES}


def _add(session: Session, config: DataSourceConfig, client: _FakeClient, **kwargs: Any) -> Any:
    defaults: Dict[str, Any] = {
        "term": "ex post facto",
        "pos_type": "adjective",
        "pos_subtype": "adjective_other",
        "definition": "applying to acts committed before the law was passed",
        "config": config,
        "client": client,
    }
    defaults.update(kwargs)
    return add_term(session, **defaults)


def test_target_languages_match_the_definitions_prompt() -> None:
    """add_term's language tuple is a copy; it must not drift from the original.

    It is spelled out in add_term rather than imported because importing the
    wordfreq.translation package from a module that words/__init__ re-exports
    closes an import cycle. This test is what keeps the copy honest.
    """
    from wordfreq.translation.definitions import DEFINITIONS_PROMPT_LANGUAGES

    assert TRANSLATION_LANGUAGES == DEFINITIONS_PROMPT_LANGUAGES


class TestCreation:
    def test_one_lemma_is_created_with_its_translations(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())

        result = _add(session, config, client)

        assert result.status == "created"
        assert result.guid
        assert result.missing_languages == []

        lemmas = session.query(Lemma).filter(Lemma.lemma_text == "ex post facto").all()
        assert len(lemmas) == 1
        assert lemmas[0].pos_type == "adjective"
        assert lemmas[0].definition_text.startswith("applying to acts")

        for lang_code in TRANSLATION_LANGUAGES:
            assert get_translation(session, lemmas[0], lang_code) == "ex post facto"

    def test_exactly_one_llm_call_is_made(self, session: Session, config: DataSourceConfig) -> None:
        client = _FakeClient(_all_languages())
        _add(session, config, client)
        assert len(client.calls) == 1

    def test_the_definition_is_sent_to_the_model(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # The definition is what tells the model which sense to translate; a
        # borrowed term's sense cannot be inferred from its surface form.
        client = _FakeClient(_all_languages())
        _add(session, config, client)

        prompt = client.calls[0]["prompt"]
        assert "applying to acts committed before the law was passed" in prompt
        assert "ex post facto" in prompt

    def test_multi_word_terms_are_not_reduced(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())
        _add(session, config, client)

        prompt = client.calls[0]["prompt"]
        assert "more than one word" in prompt

    def test_the_level_is_stamped_at_creation(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())
        _add(session, config, client, difficulty_level=1210)

        lemma = session.query(Lemma).filter(Lemma.lemma_text == "ex post facto").one()
        assert lemma.difficulty_level == 1210

    def test_whitespace_in_the_term_is_normalized(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())
        result = _add(session, config, client, term="  ex   post  facto ")

        assert result.term == "ex post facto"
        assert session.query(Lemma).filter(Lemma.lemma_text == "ex post facto").count() == 1


class TestTranslationsThatDiffer:
    def test_a_term_with_native_equivalents_stores_each_one(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # Not every legal borrowing is kept as-is: "tort" has real native
        # equivalents, and the path must store whatever the model returns
        # rather than assuming the term travels unchanged.
        client = _FakeClient(
            {
                "lt": "deliktas",
                "es": "ilícito civil",
                "es-419": "ilícito civil",
                "fr": "délit civil",
                "zh": "侵权行为",
            }
        )

        result = _add(
            session,
            config,
            client,
            term="tort",
            pos_type="noun",
            pos_subtype="noun_other",
            definition="a civil wrong giving rise to liability",
        )

        assert result.status == "created"
        lemma = session.query(Lemma).filter(Lemma.lemma_text == "tort").one()
        assert get_translation(session, lemma, "lt") == "deliktas"
        assert get_translation(session, lemma, "zh") == "侵权行为"


class TestPartialAndBadResponses:
    def test_a_missing_language_is_reported_but_the_lemma_is_kept(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        partial = _all_languages()
        del partial["zh"]
        client = _FakeClient(partial)

        result = _add(session, config, client)

        assert result.status == "created"
        assert result.missing_languages == ["zh"]
        lemma = session.query(Lemma).filter(Lemma.lemma_text == "ex post facto").one()
        assert get_translation(session, lemma, "zh") is None

    def test_a_blank_translation_counts_as_missing(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        partial = _all_languages()
        partial["fr"] = "   "
        client = _FakeClient(partial)

        result = _add(session, config, client)
        assert "fr" in result.missing_languages

    def test_a_json_string_response_is_parsed(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(json.dumps(_all_languages()))

        result = _add(session, config, client)
        assert result.status == "created"
        assert result.translations["lt"] == "ex post facto"

    def test_a_non_object_response_is_an_error_and_writes_nothing(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(["not", "an", "object"])

        result = _add(session, config, client)

        assert result.status == "error"
        assert session.query(Lemma).count() == 0

    def test_a_failed_call_is_an_error_and_writes_nothing(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(None, error=RuntimeError("upstream timed out"))

        result = _add(session, config, client)

        assert result.status == "error"
        assert result.error is not None
        assert "upstream timed out" in result.error
        assert session.query(Lemma).count() == 0


class TestValidation:
    def test_an_unknown_pos_type_is_rejected_before_the_llm_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())

        result = _add(session, config, client, pos_type="interjection")

        assert result.status == "error"
        assert client.calls == []
        assert session.query(Lemma).count() == 0

    def test_an_invalid_subtype_is_rejected_before_the_llm_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())

        result = _add(session, config, client, pos_subtype="not_a_subtype")

        assert result.status == "error"
        assert client.calls == []

    def test_a_missing_definition_is_rejected(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())

        result = _add(session, config, client, definition="   ")

        assert result.status == "error"
        assert client.calls == []

    def test_an_empty_term_is_rejected(self, session: Session, config: DataSourceConfig) -> None:
        client = _FakeClient(_all_languages())

        result = _add(session, config, client, term="   ")

        assert result.status == "error"
        assert client.calls == []


class TestExistenceGuard:
    def test_an_existing_term_is_not_added_twice(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())
        _add(session, config, client)

        second_client = _FakeClient(_all_languages())
        result = _add(session, config, second_client)

        assert result.status == "already_exists"
        # No second call: the guard runs before the LLM, so a re-run is free.
        assert second_client.calls == []
        assert session.query(Lemma).filter(Lemma.lemma_text == "ex post facto").count() == 1


class TestOperationLog:
    def test_creation_and_each_translation_are_logged(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_all_languages())
        result = _add(session, config, client)

        created = (
            session.query(OperationLog).filter(OperationLog.operation_type == "lemma_create").all()
        )
        assert len(created) == 1
        assert created[0].entity_guid == result.guid

        translations = (
            session.query(OperationLog).filter(OperationLog.operation_type == "translation").all()
        )
        assert len(translations) == len(TRANSLATION_LANGUAGES)
