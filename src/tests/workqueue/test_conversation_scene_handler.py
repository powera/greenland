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
    SentenceWordHint,
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

    words = session.query(SentenceWordHint).all()
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

    words = session.query(SentenceWordHint).all()
    assert sum(1 for word in words if word.name_id is not None) == 2


def test_leaves_english_sentence_words_for_decomposition(
    session: Session, config: DataSourceConfig
) -> None:
    """The mechanical pass must not look like a finished English decomposition.

    translate/decompose sets include_english from ``len(english_words) == 0``, so
    writing the generator's guesses to SentenceWord would make it skip English
    forever -- leaving the guessed part of speech as the final answer.
    """
    _add_lemma(session, "tomato", 3)

    result = _generate(session, config)

    assert session.query(SentenceWord).count() == 0
    assert session.query(SentenceWordHint).count() > 0

    sentence_ids = [entry["sentence_id"] for entry in result["sentences"]]
    english_words = (
        session.query(SentenceWord)
        .filter(SentenceWord.sentence_id.in_(sentence_ids), SentenceWord.language_code == "en")
        .all()
    )
    assert english_words == []


def test_grammatical_words_get_no_pattern_row(session: Session, config: DataSourceConfig) -> None:
    """A function word carries no pattern meaning, and the check constraint
    would reject a row with no lemma, pending import, or name."""
    _add_lemma(session, "tomato", 3)

    _generate(session, config)

    english_texts = {word.english_text for word in session.query(SentenceWordHint).all()}
    assert "are" not in english_texts
    assert "these" not in english_texts


def test_pattern_positions_are_dense_within_a_sentence(
    session: Session, config: DataSourceConfig
) -> None:
    """Skipping grammatical words must not leave gaps that collide with
    uq_sentence_word_hint_position."""
    _add_lemma(session, "tomato", 3)
    _add_lemma(session, "fresh", 4, pos_type="adjective")

    result = _generate(session, config)

    for entry in result["sentences"]:
        positions = sorted(
            word.position
            for word in session.query(SentenceWordHint)
            .filter_by(sentence_id=entry["sentence_id"])
            .all()
        )
        assert positions == list(range(len(positions)))


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

    # Asked for level 3, but the dialog uses only two leveled words, so there is
    # no 15% tail for the percentile to trim and "fresh" (level 9) stands.
    assert result["target_level"] == 3
    assert result["computed_minimum_level"] == 9

    conversation = session.get(Conversation, result["conversation_id"])
    assert conversation is not None
    assert conversation.minimum_level == 9


def test_a_single_hard_word_does_not_raise_a_dialogs_level(
    session: Session, config: DataSourceConfig
) -> None:
    """With enough easy vocabulary, one level-9 word falls in the trimmed tail."""
    reply = {
        "title": "Buying tomatoes",
        "turns": [
            {"speaker": "George", "text": "Are these tomatoes fresh?"},
            {"speaker": "Clerk", "text": "Bread, milk, cheese, apples, onions, rice, beans too."},
        ],
        "cast": [{"name_text": "George", "kind": "given_name"}],
    }
    _add_lemma(session, "tomato", 3)
    _add_lemma(session, "fresh", 9, pos_type="adjective")
    for word in ("bread", "milk", "cheese", "apple", "onion", "rice", "bean"):
        _add_lemma(session, word, 3)

    result = _generate(session, config, reply=reply, target_level=3)

    assert result["computed_minimum_level"] == 3


def test_computed_level_is_floored_at_the_requested_level(
    session: Session, config: DataSourceConfig
) -> None:
    """A dialog written for level 8 stays level 8 even when its words are easy."""
    _add_lemma(session, "tomato", 3)
    _add_lemma(session, "fresh", 8, pos_type="adjective")

    result = _generate(session, config, target_level=8)

    assert result["computed_minimum_level"] == 8


def test_computed_level_falls_below_target_when_all_words_are_easier(
    session: Session, config: DataSourceConfig
) -> None:
    """Nothing in the dialog reaches the requested level, so the floor lifts."""
    _add_lemma(session, "tomato", 2)
    _add_lemma(session, "fresh", 3, pos_type="adjective")

    result = _generate(session, config, target_level=9)

    assert result["computed_minimum_level"] == 3


def test_names_do_not_contribute_to_the_level(session: Session, config: DataSourceConfig) -> None:
    _add_lemma(session, "tomato", 3)

    result = _generate(session, config)

    # The second line is all name + function words + missing words, so it has
    # no level of its own and cannot raise the conversation's.
    assert result["computed_minimum_level"] == 3
    second_sentence = session.get(Sentence, result["sentences"][1]["sentence_id"])
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


# --------------------------------------------------------------------------- #
# One Sentence per sentence, grouped by turn_index                             #
# --------------------------------------------------------------------------- #


_SPLIT_REPLY: Dict[str, Any] = {
    "title": "Sharing apples",
    "theme": "food",
    "turns": [
        {
            "speaker": "Ben",
            "sentences": [
                "Thanks.",
                "I have two apples in my bag.",
                "Would you like one?",
            ],
        },
        {"speaker": "Maria", "sentences": ["Yes please."]},
    ],
    "cast": [{"name_text": "Ben", "kind": "given_name", "gender": "masculine"}],
}


def test_a_multi_sentence_turn_becomes_several_rows(
    session: Session, config: DataSourceConfig
) -> None:
    """The core of the change: one Sentence row per sentence, not per turn."""
    result = _generate(session, config, reply=_SPLIT_REPLY)

    links = (
        session.query(ConversationSentence)
        .filter_by(conversation_id=result["conversation_id"])
        .order_by(ConversationSentence.position)
        .all()
    )

    assert [link.position for link in links] == [0, 1, 2, 3]
    assert [link.turn_index for link in links] == [0, 0, 0, 1]
    assert [link.speaker for link in links] == ["Ben", "Ben", "Ben", "Maria"]
    assert result["num_turns"] == 2
    assert len(result["sentences"]) == 4


def test_each_sentence_stores_only_its_own_text(session: Session, config: DataSourceConfig) -> None:
    """A row's translation is its sentence, not the whole turn."""
    result = _generate(session, config, reply=_SPLIT_REPLY)

    texts = [
        session.query(SentenceTranslation)
        .filter_by(sentence_id=entry["sentence_id"], language_code="en")
        .one()
        .translation_text
        for entry in result["sentences"]
    ]
    assert texts == [
        "Thanks.",
        "I have two apples in my bag.",
        "Would you like one?",
        "Yes please.",
    ]


def test_minimum_level_is_per_sentence_within_a_turn(
    session: Session, config: DataSourceConfig
) -> None:
    """The reason for the split: a hard word must not gate its whole turn.

    "apple" is level 1 and "bag" level 6. Stored as one turn, every sentence of
    it would be gated at 6; stored per sentence, only the sentence that uses
    "bag" is.
    """
    _add_lemma(session, "apple", 1)
    _add_lemma(session, "bag", 6)

    result = _generate(session, config, reply=_SPLIT_REPLY)

    levels_by_text: Dict[str, Optional[int]] = {}
    for entry in result["sentences"]:
        stored = session.get(Sentence, entry["sentence_id"])
        assert stored is not None
        levels_by_text[entry["text"]] = stored.minimum_level
    assert levels_by_text["I have two apples in my bag."] == 6
    # The other sentences of the same turn use none of that vocabulary.
    assert levels_by_text["Thanks."] is None
    assert levels_by_text["Would you like one?"] is None


def test_consecutive_turns_by_one_speaker_stay_distinct(
    session: Session, config: DataSourceConfig
) -> None:
    """Turns cannot be recovered by grouping on speaker, which is why they have an index."""
    reply: Dict[str, Any] = {
        "title": "A pause",
        "turns": [
            {"speaker": "Ben", "sentences": ["Hello?"]},
            {"speaker": "Ben", "sentences": ["Is anyone there?"]},
        ],
        "cast": [],
    }
    result = _generate(session, config, reply=reply)

    links = (
        session.query(ConversationSentence)
        .filter_by(conversation_id=result["conversation_id"])
        .order_by(ConversationSentence.position)
        .all()
    )
    assert [link.speaker for link in links] == ["Ben", "Ben"]
    assert [link.turn_index for link in links] == [0, 1]
