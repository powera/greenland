"""Tests for the scene dialog workqueue handler (generation -> stored rows).

The LLM is stubbed; what these pin is the storage contract the older
keyword-driven path did not have: word links, a *derived* minimum level that
ignores names, and cast registration that reuses an existing name row.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.types import Response
from sentences.dialog_scene import SceneRequest
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.name_entity import find_name
from storage.models.name_entity import Name
from storage.models.schema import (
    Base,
    Conversation,
    ConversationSentence,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from workqueue.handlers.conversations.scene import (
    generate_scene_conversation,
    handle_conversations_scene_generate,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=":memory:", model="test-model"
    )


_REPLY: Dict[str, Any] = {
    "title": "Buying tomatoes",
    "theme": "shopping",
    "turns": [
        {"speaker": "George", "text": "Are these tomatoes fresh?"},
        {"speaker": "Clerk", "text": "George, they arrived this morning."},
    ],
    "cast": [{"name_text": "George", "kind": "given_name", "gender": "masculine"}],
}


class _StubClient:
    def __init__(self, reply: Dict[str, Any]) -> None:
        self.reply = reply

    def generate_chat(self, **kwargs: Any) -> Response:
        return Response(response_text="", structured_data=self.reply, usage=None)


def _add_lemma(session: Session, text: str, level: Optional[int], pos_type: str = "noun") -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"a {text}",
        pos_type=pos_type,
        difficulty_level=level,
        guid=f"X_{text}",
    )
    session.add(lemma)
    session.flush()
    return lemma


def _generate(
    session: Session,
    config: DataSourceConfig,
    *,
    reply: Optional[Dict[str, Any]] = None,
    target_level: int = 3,
) -> Dict[str, Any]:
    request = SceneRequest(
        scene="buying tomatoes at the grocery store",
        target_level=target_level,
        num_turns=2,
    )
    with patch("sentences.dialog_scene.UnifiedLLMClient") as mock_client_class:
        mock_client_class.from_config.return_value = _StubClient(reply or _REPLY)
        return generate_scene_conversation(session, request, config)


def test_stores_the_conversation_and_its_scene(session: Session, config: DataSourceConfig) -> None:
    result = _generate(session, config)

    conversation = session.get(Conversation, result["conversation_id"])
    assert conversation is not None
    assert conversation.title == "Buying tomatoes"
    assert conversation.theme == "shopping"
    assert conversation.scene_prompt == "buying tomatoes at the grocery store"
    assert conversation.target_level == 3
    assert conversation.source_model == "test-model"
    assert conversation.verified is False


def test_stores_one_sentence_per_turn_in_order(session: Session, config: DataSourceConfig) -> None:
    result = _generate(session, config)

    links = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.conversation_id == result["conversation_id"])
        .order_by(ConversationSentence.position)
        .all()
    )
    assert [link.speaker for link in links] == ["George", "Clerk"]
    assert [link.position for link in links] == [0, 1]

    first_text = (
        session.query(SentenceTranslation)
        .filter(SentenceTranslation.sentence_id == links[0].sentence_id)
        .one()
    )
    assert first_text.language_code == "en"
    assert first_text.translation_text == "Are these tomatoes fresh?"


def test_links_words_to_lemmas_and_names(session: Session, config: DataSourceConfig) -> None:
    _add_lemma(session, "tomato", 3)
    _add_lemma(session, "fresh", 4, pos_type="adjective")

    _generate(session, config)

    words = session.query(SentenceWord).all()
    linked_lemmas = {word.english_text for word in words if word.lemma_id is not None}
    linked_names = {word.english_text for word in words if word.name_id is not None}

    assert "tomatoes" in linked_lemmas
    assert "fresh" in linked_lemmas
    # Speaker labels are not tokens; only the name spoken in a line is linked.
    assert linked_names == {"George"}


def test_links_every_occurrence_of_a_name(session: Session, config: DataSourceConfig) -> None:
    reply = {
        "title": "Two Georges",
        "turns": [
            {"speaker": "Clerk", "text": "Hello George."},
            {"speaker": "Clerk", "text": "Goodbye George."},
        ],
        "cast": [{"name_text": "George", "kind": "given_name"}],
    }

    _generate(session, config, reply=reply)

    words = session.query(SentenceWord).all()
    assert sum(1 for word in words if word.name_id is not None) == 2


def test_registers_the_cast_once(session: Session, config: DataSourceConfig) -> None:
    _generate(session, config)

    george = find_name(session, "George")
    assert george is not None
    assert george.kind == "given_name"
    assert george.gender == "masculine"
    assert george.source_model == "test-model"
    assert session.query(Name).count() == 1


def test_reuses_an_existing_name_across_dialogs(session: Session, config: DataSourceConfig) -> None:
    """A recurring character must not fork into two rows with two renderings."""
    _generate(session, config)
    _generate(session, config)

    assert session.query(Name).count() == 1


def test_minimum_level_is_derived_from_the_words_used(
    session: Session, config: DataSourceConfig
) -> None:
    _add_lemma(session, "tomato", 3)
    _add_lemma(session, "fresh", 9, pos_type="adjective")

    result = _generate(session, config, target_level=3)

    # Asked for level 3, but "fresh" is level 9, so the dialog really is level 9.
    assert result["target_level"] == 3
    assert result["computed_minimum_level"] == 9

    conversation = session.get(Conversation, result["conversation_id"])
    assert conversation is not None
    assert conversation.minimum_level == 9


def test_names_do_not_contribute_to_the_level(session: Session, config: DataSourceConfig) -> None:
    _add_lemma(session, "tomato", 3)

    result = _generate(session, config)

    # The second line is all name + function words + missing words, so it has
    # no level of its own and cannot raise the conversation's.
    assert result["computed_minimum_level"] == 3
    second_sentence = session.get(Sentence, result["turns"][1]["sentence_id"])
    assert second_sentence is not None
    assert second_sentence.minimum_level is None


def test_reports_the_words_the_dictionary_lacks(session: Session, config: DataSourceConfig) -> None:
    _add_lemma(session, "tomato", 3)

    result = _generate(session, config)

    assert "fresh" in result["missing_words"]
    assert "arrived" in result["missing_words"]
    # Names and known words are not reported as missing.
    assert "George" not in result["missing_words"]
    assert "tomatoes" not in result["missing_words"]


def test_handler_requires_a_scene(session: Session) -> None:
    with pytest.raises(ValueError, match="No scene provided"):
        handle_conversations_scene_generate(session, {"target_level": 3})


def test_handler_returns_a_summary_message(session: Session) -> None:
    _add_lemma(session, "tomato", 3)

    with patch("sentences.dialog_scene.UnifiedLLMClient") as mock_client_class:
        mock_client_class.from_config.return_value = _StubClient(_REPLY)
        message = handle_conversations_scene_generate(
            session,
            {
                "scene": "buying tomatoes at the grocery store",
                "target_level": 3,
                "num_turns": 2,
                "model": "test-model",
            },
        )

    assert "Buying tomatoes" in message
    assert "target level 3" in message
    assert "not in the dictionary yet" in message
