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

    def test_asks_llm_for_regional_gender_word_even_when_words_match(self) -> None:
        agent = _agent({"gender": "masculine", "explanation": "", "confidence": 0.9})
        with (
            patch(f"{_TASK}.get_translation", return_value="radio"),
            patch(f"{_TASK}.get_grammatical_gender", return_value="feminine"),
        ):
            gender, notes, _confidence = grammatical_gender.generate_grammatical_gender(
                agent, _noun(), "radio", "es-419", session=cast(Any, object())
            )
        # la radio (Spain) is not copied; el radio is the Latin American answer,
        # and the ending rule makes no prediction to flag it against.
        self.assertEqual(gender, "masculine")
        self.assertEqual(notes, "")
        agent.get_llm_client().generate_chat.assert_called_once()

    def test_prompt_names_the_region_for_each_variety(self) -> None:
        for language_code, region in (("es", "Spain"), ("es-419", "Latin America")):
            agent = _agent({"gender": "feminine", "explanation": "", "confidence": 0.9})
            grammatical_gender.generate_grammatical_gender(agent, _noun(), "casa", language_code)
            prompt = agent.get_llm_client().generate_chat.call_args.kwargs["prompt"]
            self.assertIn(f"Spanish ({region})", prompt)


class TestCommonGender(unittest.TestCase):
    def test_offered_for_spanish_and_french_only(self) -> None:
        systems = GrammarFactService.GENDER_SYSTEMS
        for language_code in ("es", "es-419", "fr"):
            self.assertIn("common", systems[language_code]["genders"])
        for language_code in ("lt", "de", "it", "pt"):
            self.assertNotIn("common", systems[language_code]["genders"])

    def test_llm_schema_allows_common_and_answer_is_kept(self) -> None:
        agent = _agent({"gender": "common", "explanation": "", "confidence": 0.9})
        gender, _notes, _confidence = grammatical_gender.generate_grammatical_gender(
            agent, _noun(), "estudiante", "es"
        )
        self.assertEqual(gender, "common")
        schema = agent.get_llm_client().generate_chat.call_args.kwargs["json_schema"]
        self.assertIn("common", schema.properties["gender"].enum)


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
