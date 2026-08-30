"""Unit tests for the 3-phase translate-and-decompose pipeline.

Covers orchestration behavior with a mocked LLM client. The DB-touching
Phase 2 path is exercised separately in ``test_candidate_lookup.py``.
"""

import json
from typing import Any, Dict, List, Optional, cast
from unittest.mock import MagicMock

import pytest

from clients.unified_client import UnifiedLLMClient
from langtools.dialect_overrides import get_dialect_display_name
from sentences.translate_and_decompose import (
    DecomposedLanguage,
    TranslateAndDecomposeResult,
    build_phase1_prompt,
    format_conversation_context,
    translate_and_decompose,
)
from storage.crud.conversation import ConversationContext, ConversationLine
from storage.models.name_entity import Name
from util.prompt_loader import get_context, get_prompt


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.structured_data = payload
        self.response_text = json.dumps(payload)
        self.usage = None


class _ScriptedLLMClient:
    """LLM client stub that returns pre-scripted responses in order.

    Each ``generate_chat`` call pops the next scripted response off the queue.
    Recorded calls are exposed so tests can assert on the prompts the pipeline
    actually built.
    """

    def __init__(self, scripted_responses: List[Dict[str, Any]]) -> None:
        self._responses = list(scripted_responses)
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(
        self,
        *,
        prompt: str,
        model: str,
        json_schema: Optional[Dict[str, Any]] = None,
        context: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> _FakeResponse:
        if not self._responses:
            raise AssertionError("Unexpected extra LLM call; no scripted response left")
        payload = self._responses.pop(0)
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "json_schema": json_schema,
                "context": context,
                "max_tokens": max_tokens,
            }
        )
        return _FakeResponse(payload)


def _decomposed_word(position: int, surface_form: str, part_of_speech: str) -> Dict[str, Any]:
    """One entry of a Phase-3 word list, in the shape the schema requires."""
    return {
        "position": position,
        "part_of_speech": part_of_speech,
        "english_gloss": surface_form,
        "surface_form": surface_form,
        "grammatical_form": None,
        "lemma_guid": "SYN1",
        "lemma": surface_form,
    }


def _make_session_with_no_candidates() -> Any:
    """Return a session stub where Phase 2 finds zero candidate lemmas.

    ``find_candidate_lemmas_from_translations`` runs real SQLAlchemy queries
    against ``session``; routing every query through ``MagicMock`` makes them
    return chained empty result sets, so the lookup yields ``{}``.
    """
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.filter_by.return_value.all.return_value = []
    return session


@pytest.fixture()
def phase2_returns_a_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make Phase 2 yield one candidate lemma.

    Phase 3 refuses to run without at least one candidate, and this module
    deliberately stubs out the DB (Phase 2 is covered in test_candidate_lookup).
    Patching the lookup keeps these orchestration tests focused on Phase 1/3.
    """
    from sentences.candidate_lookup import CandidateLemma

    candidate = CandidateLemma(
        guid="V01_001",
        lemma_text="read",
        disambiguation="",
        pos="verb",
        definition="to look at and comprehend written words",
    )
    monkeypatch.setattr(
        "sentences.translate_and_decompose.find_candidate_lemmas_from_translations",
        lambda *args, **kwargs: [candidate],
    )


def test_pipeline_translates_and_decomposes_english_by_default(
    phase2_returns_a_candidate: None,
) -> None:
    """With ``decompose_languages=None`` the pipeline runs Phase 3 only for English."""
    phase1_payload = {
        "en": "I read a book",
        "fr": "Je lis un livre",
        "zh": "我读一本书",
        "bn": "আমি একটি বই পড়ি",
        "uk": "Я читаю книгу",
        "kn": "ನಾನು ಪುಸ್ತಕ ಓದುತ್ತೇನೆ",
    }
    # The word list has to cover the translation: a breakdown that stops short
    # of the last tokens is how a truncated response looks, and is now a failed
    # decomposition rather than a partial one.
    phase3_payload = {
        "en": "I read a book",
        "words_en": [
            {
                "position": 0,
                "part_of_speech": "pronoun",
                "english_gloss": "I",
                "surface_form": "I",
                "grammatical_form": "subject",
                "lemma_guid": "SYN1",
                "lemma": "I",
            },
            {
                "position": 1,
                "part_of_speech": "verb",
                "english_gloss": "read",
                "surface_form": "read",
                "grammatical_form": "present",
                "lemma_guid": "SYN2",
                "lemma": "read",
            },
            {
                "position": 2,
                "part_of_speech": "noun",
                "english_gloss": "a book",
                "surface_form": "a book",
                "grammatical_form": "singular",
                "lemma_guid": "SYN3",
                "lemma": "book",
            },
        ],
    }
    client = _ScriptedLLMClient([phase1_payload, phase3_payload])

    result = translate_and_decompose(
        sentence_text="Leo un libro",
        source_language="es",
        session=_make_session_with_no_candidates(),
        client=cast(UnifiedLLMClient, client),
        target_languages=["en", "fr", "zh"],
    )

    assert isinstance(result, TranslateAndDecomposeResult)
    assert result.phase1_ok
    assert result.translations["en"] == "I read a book"
    assert result.translations["fr"] == "Je lis un livre"
    assert "en" in result.decompositions
    assert result.decompositions["en"].success
    assert len(result.decompositions["en"].words) == 3
    assert result.decompositions["en"].words[1]["surface_form"] == "read"

    assert len(client.calls) == 2
    # Phase 1 prompt should reference the source sentence.
    assert "Leo un libro" in client.calls[0]["prompt"]


def test_pipeline_drops_source_language_from_targets() -> None:
    """The source language must not appear in Phase 1 targets even if requested."""
    phase1_payload = {
        "fr": "Je lis un livre",
        "bn": "আমি বই পড়ি",
        "uk": "Я читаю книгу",
        "kn": "ನಾನು ಓದುತ್ತೇನೆ",
    }
    phase3_en_payload = {
        "en": "I read",
        "words_en": [],
    }
    client = _ScriptedLLMClient([phase1_payload, phase3_en_payload])

    result = translate_and_decompose(
        sentence_text="I read a book",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=cast(UnifiedLLMClient, client),
        target_languages=["en", "fr"],
        decompose_languages=["en"],
    )
    assert result.phase1_ok
    # Phase 1 schema must NOT have requested English.
    phase1_schema = client.calls[0]["json_schema"]
    assert phase1_schema is not None
    assert "en" not in phase1_schema["properties"]
    assert "fr" in phase1_schema["properties"]


def test_pipeline_runs_phase3_in_one_combined_call(phase2_returns_a_candidate: None) -> None:
    """Multiple ``decompose_languages`` share a single combined Phase 3 call."""
    phase1_payload = {
        "fr": "Je lis",
        "lt": "Aš skaitau",
        "bn": "আমি পড়ি",
        "uk": "Я читаю",
        "kn": "ನಾನು ಓದುತ್ತೇನೆ",
    }
    # Cover every token: an empty word list is now a failed decomposition, and
    # this test is about the call count, not about coverage.
    phase3_payload = {
        "fr": "Je lis",
        "words_fr": [
            _decomposed_word(0, "Je", "pronoun"),
            _decomposed_word(1, "lis", "verb"),
        ],
        "lt": "Aš skaitau",
        "words_lt": [
            _decomposed_word(0, "Aš", "pronoun"),
            _decomposed_word(1, "skaitau", "verb"),
        ],
    }
    client = _ScriptedLLMClient([phase1_payload, phase3_payload])

    result = translate_and_decompose(
        sentence_text="I read",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=cast(UnifiedLLMClient, client),
        target_languages=["fr", "lt"],
        decompose_languages=["fr", "lt"],
    )

    assert result.phase1_ok
    assert set(result.decompositions.keys()) == {"fr", "lt"}
    assert all(d.success for d in result.decompositions.values())
    assert len(client.calls) == 2  # 1 translate + 1 combined decompose


def test_pipeline_reports_phase1_failure() -> None:
    """If the LLM fails Phase 1, no Phase 3 calls are made and ``phase1_ok`` is False."""
    client = MagicMock()
    client.generate_chat.side_effect = RuntimeError("model unavailable")

    result = translate_and_decompose(
        sentence_text="I read",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=client,
        target_languages=["fr"],
    )

    assert not result.phase1_ok
    assert result.phase1_error is not None
    assert result.decompositions == {}


def test_pipeline_records_phase3_failure_for_every_language(
    phase2_returns_a_candidate: None,
) -> None:
    """A combined Phase 3 LLM failure marks each requested language as failed."""
    phase1_payload = {
        "fr": "Je lis",
        "lt": "Aš skaitau",
        "bn": "আমি পড়ি",
        "uk": "Я читаю",
        "kn": "ನಾನು ಓದುತ್ತೇನೆ",
    }

    class _FailingPhase3Client:
        def __init__(self) -> None:
            self.call_count = 0

        def generate_chat(self, **kwargs: Any) -> _FakeResponse:
            self.call_count += 1
            if self.call_count == 1:
                return _FakeResponse(phase1_payload)
            raise RuntimeError("decomposition exploded")

    client = _FailingPhase3Client()
    result = translate_and_decompose(
        sentence_text="I read",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=cast(UnifiedLLMClient, client),
        target_languages=["fr", "lt"],
        decompose_languages=["fr", "lt"],
    )
    assert result.phase1_ok
    assert set(result.decompositions.keys()) == {"fr", "lt"}
    assert not result.decompositions["fr"].success
    assert not result.decompositions["lt"].success
    assert "decomposition exploded" in (result.decompositions["fr"].error or "")
    assert "decomposition exploded" in (result.decompositions["lt"].error or "")


def test_decomposed_language_dataclass_defaults() -> None:
    """Sanity check on the small result dataclass."""
    decomposed = DecomposedLanguage(language_code="es", translation="Hola")
    assert decomposed.success is True
    assert decomposed.error is None
    assert decomposed.words == []


# --------------------------------------------------------------------------- #
# Phase-1 prompt variants: standalone vs. dialog line                          #
# --------------------------------------------------------------------------- #


def _dialog_context() -> ConversationContext:
    """A minimal dialog context: scene, one character, one turn either side."""
    return ConversationContext(
        conversation_id=1,
        title="At the playground",
        scene_prompt="two children meeting at a playground",
        speaker="Maria",
        position=2,
        turn_index=None,
        previous_lines=[ConversationLine("Ben", "They look happy.", 1, None)],
        next_lines=[ConversationLine("Ben", "Ben is usually shy.", 3, None)],
        cast=[
            Name(
                id=1,
                name_text="Ben",
                kind="given_name",
                gender="masculine",
                notes="a small boy on the playground",
            )
        ],
    )


def test_phase1_prompt_without_context_is_unchanged() -> None:
    """A standalone sentence keeps the ordinary translate_only prompt."""
    built = build_phase1_prompt(
        sentence_text="The sky is blue.",
        source_language="en",
        target_languages=["lt", "vi"],
    )
    assert built is not None
    context, prompt, full_prompt, _schema, _targets = built

    assert context == get_context("sentence_decomposition", "translate_only")
    assert full_prompt == f"{context}\n\n{prompt}"
    assert "Sentence: The sky is blue." in prompt
    assert get_dialect_display_name("en") in prompt
    assert "(lt)" in prompt and "(vi)" in prompt
    # None of the dialog scaffolding appears for a standalone sentence.
    assert "one line of a dialog" not in prompt
    assert "Speaker of this line" not in prompt


def test_phase1_prompt_with_context_uses_the_dialog_variant() -> None:
    """A dialog line gets the scene, the cast, and the neighbouring turns."""
    block = format_conversation_context(_dialog_context())
    built = build_phase1_prompt(
        sentence_text="They are.",
        source_language="en",
        target_languages=["vi"],
        conversation_context=block,
    )
    assert built is not None
    context, prompt, _full_prompt, _schema, _targets = built

    assert context == get_context("sentence_decomposition", "translate_only_dialog")
    assert context != get_context("sentence_decomposition", "translate_only")
    # The sentence being translated is still the only thing asked for.
    assert "Sentence: They are." in prompt
    # ...but the dialog reached the prompt.
    assert "two children meeting at a playground" in prompt
    assert "They look happy." in prompt
    assert "Ben is usually shy." in prompt
    assert "Speaker of this line: Maria" in prompt
    assert "a small boy on the playground" in prompt


def test_conversation_context_block_omits_empty_sections() -> None:
    """No scene, no cast, no neighbours: nothing to say, so say nothing."""
    empty = ConversationContext(
        conversation_id=1,
        title=None,
        scene_prompt=None,
        speaker="",
        position=0,
        turn_index=None,
    )
    assert format_conversation_context(empty) == ""


def test_conversation_context_block_survives_a_missing_scene() -> None:
    """Cast and neighbours are worth sending even with no scene text."""
    context = _dialog_context()
    context.scene_prompt = None
    block = format_conversation_context(context)
    assert "Scene: At the playground" in block  # falls back to the title
    assert "They look happy." in block
