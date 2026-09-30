"""Tests for the grammatical_gender task's es-419 copy and ending-rule flag."""

import unittest
from types import SimpleNamespace
from typing import Any, Dict, Optional, cast
from unittest.mock import MagicMock, patch

from words.grammar_fact_tasks import grammatical_gender
from words.grammar_facts import GrammarFactService

_TASK = "words.grammar_fact_tasks.grammatical_gender"


def _agent(llm_result: Optional[Dict[str, Any]] = None) -> Any:
    client = MagicMock()
    client.generate_chat.return_value = SimpleNamespace(structured_data=llm_result)
    return SimpleNamespace(
        GENDER_SYSTEMS=GrammarFactService.GENDER_SYSTEMS,
        get_llm_client=lambda: client,
    )


def _noun() -> Any:
    return SimpleNamespace(id=7, pos_type="noun", lemma_text="house", definition_text="a home")


class TestSpanishDialectCopy(unittest.TestCase):
    def test_copies_es_fact_when_word_matches(self) -> None:
        agent = _agent()
        with (
            patch(f"{_TASK}.get_translation", return_value="casa"),
            patch(f"{_TASK}.get_grammatical_gender", return_value="feminine") as get_gender,
        ):
            gender, notes, confidence = grammatical_gender.generate_grammatical_gender(
                agent, _noun(), "casa", "es-419", session=cast(Any, object())
            )
        self.assertEqual(gender, "feminine")
        self.assertEqual(confidence, 1.0)
        self.assertIn("Copied from es", notes or "")
        get_gender.assert_called_once()
        agent.get_llm_client().generate_chat.assert_not_called()

    def test_asks_llm_when_words_differ(self) -> None:
        agent = _agent({"gender": "masculine", "explanation": "", "confidence": 0.9})
        with (
            patch(f"{_TASK}.get_translation", return_value="ordenador"),
            patch(f"{_TASK}.get_grammatical_gender", return_value="masculine"),
        ):
            gender, _notes, _confidence = grammatical_gender.generate_grammatical_gender(
                agent, _noun(), "computadora", "es-419", session=cast(Any, object())
            )
        # The LLM answered masculine; the -a rule disagrees, which is flagged
        # rather than overriding the answer.
        self.assertEqual(gender, "masculine")
        agent.get_llm_client().generate_chat.assert_called_once()


class TestRuleDisagreementFlag(unittest.TestCase):
    def test_flags_disagreement_in_notes(self) -> None:
        agent = _agent({"gender": "masculine", "explanation": "", "confidence": 0.9})
        _gender, notes, _confidence = grammatical_gender.generate_grammatical_gender(
            agent, _noun(), "nation", "fr"
        )
        self.assertTrue((notes or "").startswith(grammatical_gender.RULE_DISAGREEMENT_NOTE))

    def test_no_flag_when_rule_agrees(self) -> None:
        agent = _agent({"gender": "feminine", "explanation": "", "confidence": 0.9})
        _gender, notes, _confidence = grammatical_gender.generate_grammatical_gender(
            agent, _noun(), "nation", "fr"
        )
        self.assertEqual(notes, "")


if __name__ == "__main__":
    unittest.main()
