"""Countability prompts must identify one lemma sense at a time."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from storage.models.schema import Lemma
from words.grammar_fact_tasks.countability import generate_countability


def test_countability_query_keeps_chicken_senses_separate() -> None:
    client: Any = MagicMock()
    client.generate_chat.return_value = SimpleNamespace(
        structured_data={"countability": "countable", "confidence": 0.9}
    )
    agent: Any = MagicMock()
    agent.get_llm_client.return_value = client

    animal = Lemma(
        lemma_text="chicken",
        definition_text="a domesticated bird kept for eggs and meat",
        disambiguation="animal",
        pos_type="noun",
        pos_subtype="animal",
    )
    meat = Lemma(
        lemma_text="chicken",
        definition_text="meat from a chicken, prepared for eating",
        disambiguation="meat",
        pos_type="noun",
        pos_subtype="food",
    )

    generate_countability(agent, animal)
    animal_query = client.generate_chat.call_args.kwargs
    generate_countability(agent, meat)
    meat_query = client.generate_chat.call_args.kwargs

    assert "Sense disambiguation: animal" in animal_query["prompt"]
    assert "Noun subtype: animal" in animal_query["prompt"]
    assert "domesticated bird" in animal_query["prompt"]
    assert "Sense disambiguation: meat" in meat_query["prompt"]
    assert "Noun subtype: food" in meat_query["prompt"]
    assert "prepared for eating" in meat_query["prompt"]
    assert (
        "Do not combine count and mass usages belonging to separate lemmas" in meat_query["prompt"]
    )
    assert "chicken meaning the animal is countable" in meat_query["context"]
