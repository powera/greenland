"""Unit tests for the 3-phase translate-and-decompose pipeline.

Covers orchestration behavior with a mocked LLM client. The DB-touching
Phase 2 path is exercised separately in ``test_candidate_lookup.py``.
"""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from sentences.translate_and_decompose import (
    DecomposedLanguage,
    TranslateAndDecomposeResult,
    translate_and_decompose,
)


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
            }
        )
        return _FakeResponse(payload)


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


def test_pipeline_translates_and_decomposes_english_by_default() -> None:
    """With ``decompose_languages=None`` the pipeline runs Phase 3 only for English."""
    phase1_payload = {
        "en": "I read a book",
        "fr": "Je lis un livre",
        "zh": "我读一本书",
        "bn": "আমি একটি বই পড়ি",
        "uk": "Я читаю книгу",
        "kn": "ನಾನು ಪುಸ್ತಕ ಓದುತ್ತೇನೆ",
    }
    phase3_en_payload = {
        "languages": [
            {
                "language_code": "en",
                "translation": "I read a book",
                "word_count": 4,
                "words": [
                    {
                        "position": 0,
                        "role": "pronoun",
                        "english_gloss": "I",
                        "surface_form": "I",
                        "grammatical_form": "subject",
                        "lemma_guid": "SYN1",
                        "lemma": "I",
                    },
                    {
                        "position": 1,
                        "role": "verb",
                        "english_gloss": "read",
                        "surface_form": "read",
                        "grammatical_form": "present",
                        "lemma_guid": "SYN2",
                        "lemma": "read",
                    },
                ],
            }
        ]
    }
    client = _ScriptedLLMClient([phase1_payload, phase3_en_payload])

    result = translate_and_decompose(
        sentence_text="Leo un libro",
        source_language="es",
        session=_make_session_with_no_candidates(),
        client=client,
        target_languages=["en", "fr", "zh"],
    )

    assert isinstance(result, TranslateAndDecomposeResult)
    assert result.phase1_ok
    assert result.translations["en"] == "I read a book"
    assert result.translations["fr"] == "Je lis un livre"
    assert "en" in result.decompositions
    assert result.decompositions["en"].success
    assert len(result.decompositions["en"].words) == 2
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
        "languages": [
            {
                "language_code": "en",
                "translation": "I read",
                "word_count": 0,
                "words": [],
            }
        ]
    }
    client = _ScriptedLLMClient([phase1_payload, phase3_en_payload])

    result = translate_and_decompose(
        sentence_text="I read a book",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=client,
        target_languages=["en", "fr"],
        decompose_languages=["en"],
    )
    assert result.phase1_ok
    # Phase 1 schema must NOT have requested English.
    phase1_schema = client.calls[0]["json_schema"]
    assert phase1_schema is not None
    assert "en" not in phase1_schema["properties"]
    assert "fr" in phase1_schema["properties"]


def test_pipeline_runs_phase3_per_requested_language() -> None:
    """Multiple ``decompose_languages`` mean multiple Phase 3 calls."""
    phase1_payload = {
        "fr": "Je lis",
        "lt": "Aš skaitau",
        "bn": "আমি পড়ি",
        "uk": "Я читаю",
        "kn": "ನಾನು ಓದುತ್ತೇನೆ",
    }
    fr_decomposition = {
        "languages": [
            {
                "language_code": "fr",
                "translation": "Je lis",
                "word_count": 2,
                "words": [],
            }
        ]
    }
    lt_decomposition = {
        "languages": [
            {
                "language_code": "lt",
                "translation": "Aš skaitau",
                "word_count": 2,
                "words": [],
            }
        ]
    }
    client = _ScriptedLLMClient([phase1_payload, fr_decomposition, lt_decomposition])

    result = translate_and_decompose(
        sentence_text="I read",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=client,
        target_languages=["fr", "lt"],
        decompose_languages=["fr", "lt"],
    )

    assert result.phase1_ok
    assert set(result.decompositions.keys()) == {"fr", "lt"}
    assert all(d.success for d in result.decompositions.values())
    assert len(client.calls) == 3  # 1 translate + 2 decompose


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


def test_pipeline_records_phase3_failure_without_aborting() -> None:
    """Phase 3 failure for one language is recorded but doesn't stop other languages."""
    phase1_payload = {
        "fr": "Je lis",
        "lt": "Aš skaitau",
        "bn": "আমি পড়ি",
        "uk": "Я читаю",
        "kn": "ನಾನು ಓದುತ್ತೇನೆ",
    }
    good_decomposition = {
        "languages": [
            {
                "language_code": "fr",
                "translation": "Je lis",
                "word_count": 2,
                "words": [],
            }
        ]
    }

    client = _ScriptedLLMClient([phase1_payload, good_decomposition])
    # Third call (lt) will raise because no more scripted responses exist; we
    # need to inject a failing response instead. Re-do with a richer stub.

    class _MixedClient:
        def __init__(self) -> None:
            self.call_count = 0

        def generate_chat(self, **kwargs: Any) -> _FakeResponse:
            self.call_count += 1
            if self.call_count == 1:
                return _FakeResponse(phase1_payload)
            if self.call_count == 2:
                return _FakeResponse(good_decomposition)
            raise RuntimeError("LT decomposition exploded")

    client2 = _MixedClient()
    result = translate_and_decompose(
        sentence_text="I read",
        source_language="en",
        session=_make_session_with_no_candidates(),
        client=client2,
        target_languages=["fr", "lt"],
        decompose_languages=["fr", "lt"],
    )
    assert result.phase1_ok
    assert result.decompositions["fr"].success
    assert not result.decompositions["lt"].success
    assert "LT decomposition exploded" in (result.decompositions["lt"].error or "")


def test_decomposed_language_dataclass_defaults() -> None:
    """Sanity check on the small result dataclass."""
    decomposed = DecomposedLanguage(language_code="es", translation="Hola")
    assert decomposed.success is True
    assert decomposed.error is None
    assert decomposed.words == []
