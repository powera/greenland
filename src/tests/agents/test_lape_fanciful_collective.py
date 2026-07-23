"""Tests for Lape fanciful collective noun generation."""

from types import SimpleNamespace
from typing import Any, Dict, Optional

from agents.lape.tasks.fanciful_collective import generate_fanciful_collective
from storage.models.schema import Lemma


class FakeResponse:
    def __init__(self, structured_data: Optional[Dict[str, Any]]) -> None:
        self.structured_data = structured_data


class FakeLLMClient:
    def __init__(self, structured_data: Optional[Dict[str, Any]]) -> None:
        self.structured_data = structured_data
        self.prompts: list[str] = []

    def generate_chat(self, prompt: str = "", **_: Any) -> FakeResponse:
        self.prompts.append(prompt)
        return FakeResponse(self.structured_data)


def _agent(structured_data: Optional[Dict[str, Any]]) -> Any:
    client = FakeLLMClient(structured_data)
    return SimpleNamespace(get_llm_client=lambda: client, _client=client)


def _lemma(text: str = "crow", pos_type: str = "noun") -> Lemma:
    return Lemma(
        lemma_text=text,
        definition_text=f"A {text}.",
        pos_type=pos_type,
        pos_subtype="animal",
        guid="N02_999",
    )


def test_returns_term_and_confidence_for_attested_collective() -> None:
    agent = _agent(
        {
            "primary_collective": "murder",
            "alternative_collectives": [],
            "explanation": "Traditional term of venery for crows.",
            "confidence": 0.95,
        }
    )

    value, notes, confidence = generate_fanciful_collective(agent, _lemma("crow"))

    assert value == "murder"
    assert confidence == 0.95
    assert notes is not None and "venery" in notes


def test_missing_term_yields_zero_confidence_so_nothing_is_stored() -> None:
    """Most animals have no fanciful collective; that is a normal result."""
    agent = _agent(
        {
            "primary_collective": None,
            "alternative_collectives": [],
            "explanation": "No traditional collective is attested for this animal.",
            "confidence": 0.9,
        }
    )

    value, _, confidence = generate_fanciful_collective(agent, _lemma("hamster"))

    assert value is None
    # Zero regardless of the model's own confidence, so the caller's
    # threshold check stores no fact.
    assert confidence == 0.0


def test_alternatives_go_to_notes_not_the_value() -> None:
    """One fact per (lemma, language, fact_type), so the value stays a single term."""
    agent = _agent(
        {
            "primary_collective": "gaggle",
            "alternative_collectives": ["skein", "wedge"],
            "explanation": "Used on the ground.",
            "confidence": 0.9,
        }
    )

    value, notes, _ = generate_fanciful_collective(agent, _lemma("goose"))

    assert value == "gaggle"
    assert notes is not None
    assert "skein" in notes and "wedge" in notes


def test_non_noun_is_skipped_without_calling_the_llm() -> None:
    agent = _agent({"primary_collective": "murder", "confidence": 1.0})

    value, _, confidence = generate_fanciful_collective(agent, _lemma("fly", pos_type="verb"))

    assert value is None
    assert confidence == 0.0
    assert agent._client.prompts == []


def test_absent_structured_data_is_handled() -> None:
    agent = _agent(None)

    value, _, confidence = generate_fanciful_collective(agent, _lemma("crow"))

    assert value is None
    assert confidence == 0.0


def test_prompt_includes_the_animal() -> None:
    agent = _agent(
        {
            "primary_collective": "parliament",
            "alternative_collectives": [],
            "explanation": "Traditional.",
            "confidence": 0.9,
        }
    )

    generate_fanciful_collective(agent, _lemma("owl"))

    assert "owl" in agent._client.prompts[0]
