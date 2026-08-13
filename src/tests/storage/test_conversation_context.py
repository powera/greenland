"""Tests for the dialog context a translation prompt gets for one sentence.

Translation runs one LLM call per sentence, which leaves a dialog line with no
way to know what it is answering. These tests pin what
``get_sentence_conversation_context`` hands the prompt: the surrounding turns
with speaker labels, the scene, the cast, and the size rule that decides between
the whole dialog and just its run-up.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.conversation import (
    CONTEXT_FALLBACK_TURNS,
    add_conversation,
    add_conversation_sentence,
    get_sentence_conversation_context,
)
from storage.crud.name_entity import create_name
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.models.schema import Base, Conversation, Sentence, SentenceWordHint


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _build_dialog(
    session: Session,
    lines: List[Tuple[str, str]],
    *,
    scene_prompt: Optional[str] = "two children meeting at a playground",
    turn_indexes: Optional[List[int]] = None,
) -> Tuple[Conversation, List[int]]:
    """Store a dialog as one Sentence per line; return it and its sentence ids."""
    conversation = add_conversation(session, title="At the playground")
    conversation.scene_prompt = scene_prompt

    sentence_ids: List[int] = []
    for position, (speaker, text) in enumerate(lines):
        sentence = add_sentence(session, pattern_type="conversation")
        add_sentence_translation(
            session, sentence=sentence, language_code="en", translation_text=text
        )
        add_conversation_sentence(
            session,
            conversation=conversation,
            sentence=sentence,
            position=position,
            speaker=speaker,
            turn_index=turn_indexes[position] if turn_indexes else None,
        )
        sentence_ids.append(sentence.id)
    session.flush()
    return conversation, sentence_ids


def test_standalone_sentence_has_no_context(session: Session) -> None:
    """A sentence in no conversation must not get a dialog prompt variant."""
    sentence = add_sentence(session, pattern_type="declarative")
    add_sentence_translation(
        session, sentence=sentence, language_code="en", translation_text="The sky is blue."
    )
    session.flush()

    assert get_sentence_conversation_context(session, sentence.id) is None


def test_short_dialog_returns_every_turn(session: Session) -> None:
    """Under the token budget the whole dialog goes in, on both sides."""
    _conversation, sentence_ids = _build_dialog(
        session,
        [
            ("Maria", "Look at the children."),
            ("Ben", "They look happy."),
            ("Maria", "They are."),
            ("Ben", "Ben is usually shy."),
        ],
    )

    context = get_sentence_conversation_context(session, sentence_ids[2])
    assert context is not None
    assert context.truncated is False
    assert context.speaker == "Maria"
    assert [line.text for line in context.previous_lines] == [
        "Look at the children.",
        "They look happy.",
    ]
    assert [line.text for line in context.next_lines] == ["Ben is usually shy."]
    assert context.scene_prompt == "two children meeting at a playground"


def test_first_and_last_lines_have_empty_sides(session: Session) -> None:
    """The ends of a dialog are a normal case, not an error."""
    _conversation, sentence_ids = _build_dialog(
        session, [("Maria", "Hello."), ("Ben", "Hi."), ("Maria", "Goodbye.")]
    )

    first = get_sentence_conversation_context(session, sentence_ids[0])
    last = get_sentence_conversation_context(session, sentence_ids[-1])
    assert first is not None and last is not None
    assert first.previous_lines == []
    assert len(first.next_lines) == 2
    assert last.next_lines == []
    assert len(last.previous_lines) == 2


def test_long_dialog_keeps_only_the_run_up(session: Session) -> None:
    """Over budget, context becomes the preceding turns and nothing after."""
    long_line = " ".join(["word"] * 60)
    lines = [(f"Speaker{index % 2}", f"{long_line} {index}.") for index in range(10)]
    _conversation, sentence_ids = _build_dialog(session, lines)

    context = get_sentence_conversation_context(session, sentence_ids[8])
    assert context is not None
    assert context.truncated is True
    assert context.next_lines == []
    assert len(context.previous_lines) == CONTEXT_FALLBACK_TURNS
    # The turns kept are the ones immediately before this line, not the opening.
    assert [line.position for line in context.previous_lines] == [5, 6, 7]


def test_truncation_keeps_the_whole_of_this_sentences_turn(session: Session) -> None:
    """A split turn must not lose the rest of itself to the token budget."""
    long_line = " ".join(["word"] * 60)
    lines = [(f"Speaker{index % 2}", f"{long_line} {index}.") for index in range(10)]
    # Positions 6, 7 and 8 are one three-sentence turn.
    turn_indexes = [0, 1, 2, 3, 4, 5, 6, 6, 6, 7]
    _conversation, sentence_ids = _build_dialog(session, lines, turn_indexes=turn_indexes)

    context = get_sentence_conversation_context(session, sentence_ids[7])
    assert context is not None
    assert context.truncated is True
    # Position 6 is the same turn, so it survives on the previous side; position
    # 8 is the same turn, so it survives on the next side despite truncation.
    assert 6 in [line.position for line in context.previous_lines]
    assert [line.position for line in context.next_lines] == [8]


def test_turn_index_groups_a_split_turn(session: Session) -> None:
    """With turn_index set, a whole previous turn is context, not one row."""
    _conversation, sentence_ids = _build_dialog(
        session,
        [
            ("Ben", "Thanks."),
            ("Ben", "I have two apples in my bag."),
            ("Ben", "Would you like one?"),
            ("Maria", "Yes please."),
        ],
        turn_indexes=[0, 0, 0, 1],
    )

    context = get_sentence_conversation_context(session, sentence_ids[3])
    assert context is not None
    assert context.turn_index == 1
    assert [line.text for line in context.previous_lines] == [
        "Thanks.",
        "I have two apples in my bag.",
        "Would you like one?",
    ]


def test_cast_is_collected_and_deduplicated(session: Session) -> None:
    """The cast comes from word links; a name used twice is listed once."""
    _conversation, sentence_ids = _build_dialog(
        session, [("Maria", "Hello Ben."), ("Ben", "Hello Maria.")]
    )
    ben = create_name(session, name_text="Ben", kind="given_name", gender="masculine")
    ben.notes = "a small boy on the playground"
    session.flush()

    for position, sentence_id in enumerate(sentence_ids):
        session.add(
            SentenceWordHint(
                sentence_id=sentence_id,
                name_id=ben.id,
                position=position,
                slot_name="name",
                english_text="Ben",
            )
        )
    session.flush()

    context = get_sentence_conversation_context(session, sentence_ids[0])
    assert context is not None
    assert [name.name_text for name in context.cast] == ["Ben"]
    assert context.cast[0].notes == "a small boy on the playground"


def test_language_falls_back_to_english(session: Session) -> None:
    """A language with no translation still gets readable context."""
    _conversation, sentence_ids = _build_dialog(
        session, [("Maria", "They look happy."), ("Ben", "They are.")]
    )

    context = get_sentence_conversation_context(session, sentence_ids[1], language_code="vi")
    assert context is not None
    assert [line.text for line in context.previous_lines] == ["They look happy."]


def test_sentence_in_two_conversations_resolves_deterministically(session: Session) -> None:
    """merge_duplicate_sentences allows this; the prompt must not vary by luck."""
    first, sentence_ids = _build_dialog(session, [("Maria", "Hello."), ("Ben", "Hi.")])
    second = add_conversation(session, title="Another dialog")
    second.scene_prompt = "a different scene"
    shared_sentence_id = sentence_ids[1]
    shared_sentence = session.get(Sentence, shared_sentence_id)
    assert shared_sentence is not None
    add_conversation_sentence(
        session,
        conversation=second,
        sentence=shared_sentence,
        position=0,
        speaker="Ben",
    )
    session.flush()

    first_call = get_sentence_conversation_context(session, shared_sentence_id)
    second_call = get_sentence_conversation_context(session, shared_sentence_id)
    assert first_call is not None and second_call is not None
    assert first_call.conversation_id == second_call.conversation_id
    # Lowest conversation id wins.
    assert first_call.conversation_id == min(first.id, second.id)
