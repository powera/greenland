"""Tests for the auxiliary_verb task's French rule path."""

import unittest
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

from words.grammar_fact_tasks import auxiliary_verb
from words.grammar_facts import GrammarFactService


def _agent(llm_result: Optional[Dict[str, Any]] = None) -> Any:
    client = MagicMock()
    client.generate_chat.return_value = SimpleNamespace(structured_data=llm_result)
    return SimpleNamespace(
        AUXILIARY_SYSTEMS=GrammarFactService.AUXILIARY_SYSTEMS,
        get_llm_client=lambda: client,
    )


def _verb() -> Any:
    return SimpleNamespace(id=3, pos_type="verb", lemma_text="to go out", definition_text="x")


class TestFrenchAuxiliaryTask(unittest.TestCase):
    def test_rule_answers_avoir_without_llm(self) -> None:
        agent = _agent()
        value, _notes, confidence = auxiliary_verb.generate_auxiliary_verb(
            agent, _verb(), "parler", "fr"
        )
        self.assertEqual(value, "avoir")
        self.assertEqual(confidence, 1.0)
        agent.get_llm_client().generate_chat.assert_not_called()

    def test_rule_answers_etre_for_reflexive(self) -> None:
        agent = _agent()
        value, _notes, _confidence = auxiliary_verb.generate_auxiliary_verb(
            agent, _verb(), "se lever", "fr"
        )
        self.assertEqual(value, "être")
        agent.get_llm_client().generate_chat.assert_not_called()

    def test_sense_dependent_verb_asks_llm(self) -> None:
        agent = _agent({"auxiliary_verb": "être", "explanation": "", "confidence": 0.9})
        value, _notes, _confidence = auxiliary_verb.generate_auxiliary_verb(
            agent, _verb(), "sortir", "fr"
        )
        self.assertEqual(value, "être")
        agent.get_llm_client().generate_chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
