"""Tests for scene-driven dialog generation (prompt building and parsing).

The LLM call itself is stubbed; what is pinned here is everything around it:
request validation, the vocabulary sample that steers the level, the prompt
placeholders, and how a reply becomes a draft (including the malformed replies
that must not become empty sentence rows).
"""

from __future__ import annotations

import random
from typing import Any, Dict, Iterator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.types import Response
from sentences.dialog_scene import (
    CastMember,
    SceneRequest,
    build_scene_context,
    build_scene_prompt,
    build_scene_schema,
    generate_scene,
    parse_scene_response,
    sample_encouraged_vocabulary,
)
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


_AUTO_GUID = "<auto>"


def _add_lemma(
    session: Session, text: str, level: Optional[int], guid: Optional[str] = _AUTO_GUID
) -> None:
    session.add(
        Lemma(
            lemma_text=text,
            definition_text=f"a {text}",
            pos_type="noun",
            difficulty_level=level,
            guid=f"N_{text}" if guid == _AUTO_GUID else guid,
        )
    )


def _request(**overrides: Any) -> SceneRequest:
    defaults: Dict[str, Any] = {
        "scene": "buying tomatoes at the grocery store",
        "target_level": 3,
        "num_turns": 8,
    }
    defaults.update(overrides)
    return SceneRequest(**defaults)


class _StubClient:
    """Stands in for UnifiedLLMClient, recording the call it received."""

    def __init__(self, structured_data: Dict[str, Any]) -> None:
        self.structured_data = structured_data
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        return Response(response_text="", structured_data=self.structured_data, usage=None)


_VALID_REPLY: Dict[str, Any] = {
    "title": "Buying tomatoes",
    "theme": "shopping",
    "turns": [
        {"speaker": "George", "text": "Are these tomatoes fresh?"},
        {"speaker": "Clerk", "text": "Yes, they came in this morning."},
    ],
    "cast": [
        {
            "name_text": "George",
            "kind": "given_name",
            "gender": "masculine",
            "role": "the shopper",
        }
    ],
}


def test_validate_rejects_an_empty_scene() -> None:
    with pytest.raises(ValueError, match="needs a scene"):
        _request(scene="   ").validate()


def test_validate_rejects_a_nonpositive_level() -> None:
    with pytest.raises(ValueError, match="1 or greater"):
        _request(target_level=0).validate()


def test_validate_rejects_an_absurd_turn_count() -> None:
    with pytest.raises(ValueError, match="between 2 and 40"):
        _request(num_turns=200).validate()


def test_sample_encouraged_vocabulary_prefers_the_target_level(session: Session) -> None:
    for index in range(20):
        _add_lemma(session, f"target{index}", 3)
    for index in range(20):
        _add_lemma(session, f"easy{index}", 1)
    session.flush()

    sample = sample_encouraged_vocabulary(session, 3, sample_size=10, rng=random.Random(0))

    assert len(sample) == 10
    at_level = [word for word in sample if word.startswith("target")]
    assert len(at_level) == 5  # TARGET_LEVEL_SHARE of the sample


def test_sample_encouraged_vocabulary_excludes_harder_levels(session: Session) -> None:
    _add_lemma(session, "simple", 2)
    _add_lemma(session, "arcane", 30)
    session.flush()

    sample = sample_encouraged_vocabulary(session, 3, sample_size=10, rng=random.Random(0))

    assert "simple" in sample
    assert "arcane" not in sample


def test_sample_encouraged_vocabulary_skips_uncurated_lemmas(session: Session) -> None:
    """Lemmas without a GUID are not release vocabulary and must not be offered."""
    _add_lemma(session, "draft", 3, guid=None)
    session.flush()

    assert sample_encouraged_vocabulary(session, 3, rng=random.Random(0)) == []


def test_sample_encouraged_vocabulary_is_empty_on_an_empty_database(session: Session) -> None:
    assert sample_encouraged_vocabulary(session, 5, rng=random.Random(0)) == []


def test_build_scene_prompt_fills_every_placeholder() -> None:
    prompt = build_scene_prompt(
        _request(notes="the tomatoes are sold out"),
        encouraged_words=["tomato", "store"],
        known_names=["George"],
    )

    assert "buying tomatoes at the grocery store" in prompt
    assert "level 3" in prompt
    assert "about 8 turns" in prompt
    assert "tomato, store" in prompt
    assert "George" in prompt
    assert "the tomatoes are sold out" in prompt
    assert "{" not in prompt  # no unsubstituted placeholders


def test_build_scene_prompt_handles_an_empty_database() -> None:
    prompt = build_scene_prompt(_request(), encouraged_words=[], known_names=[])

    assert "no curated vocabulary available yet" in prompt
    assert "none yet" in prompt


def test_scene_context_and_schema_are_well_formed() -> None:
    assert "language-learning app" in build_scene_context()

    schema = build_scene_schema()
    assert set(schema.all_properties()) == {"title", "theme", "turns", "cast"}
    assert "turns" in schema.required_properties()
    assert "cast" not in schema.required_properties()


def test_parse_scene_response_builds_a_draft() -> None:
    draft = parse_scene_response(
        _VALID_REPLY, request=_request(), encouraged_words=["tomato"], source_model="test-model"
    )

    assert draft.title == "Buying tomatoes"
    assert draft.theme == "shopping"
    assert [turn.speaker for turn in draft.turns] == ["George", "Clerk"]
    assert draft.lines[0] == "Are these tomatoes fresh?"
    assert draft.cast_names() == ["George"]
    assert draft.target_level == 3
    assert draft.source_model == "test-model"
    assert draft.encouraged_words == ["tomato"]


def test_parse_scene_response_drops_empty_turns() -> None:
    """An empty line would become a Sentence row with no text; drop it instead."""
    reply = {
        "title": "Half a dialog",
        "turns": [
            {"speaker": "A", "text": "Hello."},
            {"speaker": "B", "text": "   "},
            "not an object",
            {"speaker": "B", "text": "Goodbye."},
        ],
    }

    draft = parse_scene_response(reply, request=_request())

    assert draft.lines == ["Hello.", "Goodbye."]


def test_parse_scene_response_supplies_missing_speakers() -> None:
    reply = {"title": "T", "turns": [{"text": "One."}, {"text": "Two."}]}

    draft = parse_scene_response(reply, request=_request())

    assert [turn.speaker for turn in draft.turns] == ["A", "B"]


def test_parse_scene_response_falls_back_to_the_scene_for_a_title() -> None:
    reply = {"turns": [{"speaker": "A", "text": "Hi."}]}

    draft = parse_scene_response(reply, request=_request())

    assert draft.title == "buying tomatoes at the grocery store"
    assert draft.theme is None


def test_parse_scene_response_raises_when_nothing_is_usable() -> None:
    with pytest.raises(ValueError, match="no usable dialog turns"):
        parse_scene_response({"title": "T", "turns": []}, request=_request())


def test_cast_member_coerces_unknown_labels() -> None:
    """A mislabeled name is still a usable name; coerce rather than fail."""
    member = CastMember(name_text="  George ", kind="protagonist", gender="male").normalized()

    assert member.name_text == "George"
    assert member.kind == "other"
    assert member.gender is None


def test_cast_names_dedupes_in_order() -> None:
    draft = parse_scene_response(
        {
            "title": "T",
            "turns": [{"speaker": "A", "text": "Hi."}],
            "cast": [
                {"name_text": "George", "kind": "given_name"},
                {"name_text": "Maria", "kind": "given_name"},
                {"name_text": "George", "kind": "given_name"},
            ],
        },
        request=_request(),
    )

    assert draft.cast_names() == ["George", "Maria"]


def test_generate_scene_passes_prompt_context_and_schema(session: Session) -> None:
    _add_lemma(session, "tomato", 3)
    session.flush()
    client = _StubClient(_VALID_REPLY)
    config = DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=":memory:", model="test-model"
    )

    draft = generate_scene(session, _request(), config, known_names=["Maria"], client=client)

    assert draft.title == "Buying tomatoes"
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert "buying tomatoes at the grocery store" in call["prompt"]
    assert call["json_schema"].name == "DialogScene"
    assert call["context"]


def test_generate_scene_requires_a_model(session: Session) -> None:
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=":memory:")

    with pytest.raises(ValueError, match="requires a model"):
        generate_scene(session, _request(), config, client=_StubClient(_VALID_REPLY))


def test_generate_scene_raises_on_an_empty_reply(session: Session) -> None:
    config = DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=":memory:", model="test-model"
    )

    with pytest.raises(RuntimeError, match="no structured data"):
        generate_scene(session, _request(), config, client=_StubClient({}))
