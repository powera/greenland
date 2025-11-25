#!/usr/bin/python3
"""Unit tests for validation module with precise response mocking."""

import unittest
from unittest.mock import patch, MagicMock
import json
import re

from lib.validation import ResponseValidator, ValidationResult

class MockOllamaClient:
    """Mock client for testing with precise response matching."""

    def __init__(self):
        # Pre-compile regex patterns for efficiency
        self.definition_pattern = re.compile(
            r'Given this definition: "([^"]+)"\s*Does this definition accurately describe the word "([^"]+)"\?'
        )
        self.general_knowledge_pattern = re.compile(
            r'Given this question and answer:\s*Question: ([^\n]+)\s*Response: ([^\n]+)\s*Expected: ([^\n]+)'
        )
        self.ambiguous_pattern = re.compile(
            r'In this sentence: "([^"]+)"\s*Are there multiple valid interpretations of the word "([^"]+)"\?'
        )

    def generate_chat(self, prompt, model, json_schema=None, structured_json=False):
        """
        Mock generate_chat with specific response patterns.
        Returns predefined responses based on exact prompt content matching.
        """
        # Definition validation responses
        definition_match = self.definition_pattern.search(prompt)
        if definition_match:
            definition, word = definition_match.groups()
            if definition == "A large gray mammal with a trunk" and word == "elephant":
                responses = {
                    "granite3-dense": {"explanation": "Accurate definition capturing key features", "valid": True, "confidence": 95},
                    "qwen2.5": {"explanation": "Definition matches primary characteristics", "valid": True, "confidence": 90},
                    "gemma2": {"explanation": "Definition is correct but could be more specific", "valid": True, "confidence": 85}
                }
            elif definition == "An incorrect definition" and word == "test":
                responses = {
                    "granite3-dense": {"explanation": "Definition does not match the word", "valid": False, "confidence": 80},
                    "qwen2.5": {"explanation": "No relationship between definition and word", "valid": False, "confidence": 85},
                    "gemma2": {"explanation": "Completely mismatched definition", "valid": False, "confidence": 75}
                }
            else:
                responses = self._get_default_responses("Unknown definition case")

        # General knowledge validation responses
        elif general_knowledge_match := self.general_knowledge_pattern.search(prompt):
            question, response, expected = general_knowledge_match.groups()
            if question == "What is the capital of France?" and response == "Paris" and expected == "Paris":
                responses = {
                    "granite3-dense": {"explanation": "Answer is exactly correct", "valid": True, "confidence": 100},
                    "qwen2.5": {"explanation": "Perfect match with expected answer", "valid": True, "confidence": 98},
                    "gemma2": {"explanation": "Correct capital city identified", "valid": True, "confidence": 95}
                }
            elif question == "What is 2+2?" and response == "5" and expected == "4":
                responses = {
                    "granite3-dense": {"explanation": "Mathematical error in response", "valid": False, "confidence": 100},
                    "qwen2.5": {"explanation": "Incorrect arithmetic answer", "valid": False, "confidence": 98},
                    "gemma2": {"explanation": "Response does not match correct solution", "valid": False, "confidence": 95}
                }
            else:
                responses = self._get_default_responses("Unknown general knowledge case")

        # Ambiguous meaning validation responses
        elif ambiguous_match := self.ambiguous_pattern.search(prompt):
            sentence, word = ambiguous_match.groups()
            if sentence == "I went to the bank yesterday" and word == "bank":
                responses = {
                    "granite3-dense": {"explanation": "Multiple valid meanings (financial/river)", "valid": True, "confidence": 90},
                    "qwen2.5": {"explanation": "Word has financial and geographical meanings", "valid": True, "confidence": 85},
                    "gemma2": {"explanation": "Clear case of lexical ambiguity", "valid": True, "confidence": 88}
                }
            else:
                responses = self._get_default_responses("Unknown ambiguity case")

        else:
            responses = self._get_default_responses("Unrecognized prompt format")

        model_base = model.split(":")[0]
        response = responses.get(model_base, {"explanation": "Unknown model", "valid": False, "confidence": 0})
        return json.dumps(response), {"total_msec": 100}

    def _get_default_responses(self, explanation):
        """Generate default negative responses for unknown cases."""
        return {
            "granite3-dense": {"explanation": explanation, "valid": False, "confidence": 50},
            "qwen2.5": {"explanation": explanation, "valid": False, "confidence": 45},
            "gemma2": {"explanation": explanation, "valid": False, "confidence": 40}
        }

@patch("lib.validation.ollama_client", MockOllamaClient())
class TestResponseValidator(unittest.TestCase):
    def setUp(self):
        self.validator = ResponseValidator()

    def test_validate_correct_definition(self):
        """Test validation of a correct definition."""
        result = self.validator.validate(
            "A large gray mammal with a trunk",
            "definition",
            expected="elephant"
        )
        self.assertTrue(result.valid)
        self.assertAlmostEqual(result.confidence, 90.0, places=2)
        self.assertTrue(all(r["valid"] for r in result.validator_results))

    def test_validate_incorrect_definition(self):
        """Test validation of an incorrect definition."""
        result = self.validator.validate(
            "An incorrect definition",
            "definition",
            expected="test"
        )
        self.assertFalse(result.valid)
        self.assertTrue(all(not r["valid"] for r in result.validator_results))

    def test_validate_correct_general_knowledge(self):
        """Test validation of a correct general knowledge answer."""
        result = self.validator.validate(
            "Paris",
            "general_knowledge",
            expected="Paris",
            context="What is the capital of France?"
        )
        self.assertTrue(result.valid)
        self.assertGreater(result.confidence, 95)

    def test_validate_incorrect_general_knowledge(self):
        """Test validation of an incorrect general knowledge answer."""
        result = self.validator.validate(
            "5",
            "general_knowledge",
            expected="4",
            context="What is 2+2?"
        )
        self.assertFalse(result.valid)
        self.assertGreater(result.confidence, 95)

    def test_validate_ambiguous_meaning(self):
        """Test validation of ambiguous word meaning."""
        result = self.validator.validate(
            "bank",
            "ambiguous_meaning",
            expected="bank",
            context="I went to the bank yesterday"
        )
        self.assertTrue(result.valid)
        self.assertGreater(result.confidence, 85)

    def test_validate_unsupported_task(self):
        """Test handling of unsupported validation task."""
        with self.assertRaises(ValueError) as context:
            self.validator.validate("test", "unsupported_task")
        self.assertIn("Unsupported task type", str(context.exception))

    def test_validator_results_structure(self):
        """Test the structure of validator results."""
        result = self.validator.validate(
            "A large gray mammal with a trunk",
            "definition",
            expected="elephant"
        )
        for validator_result in result.validator_results:
            self.assertIn("validator_model", validator_result)
            self.assertIn("explanation", validator_result)
            self.assertIn("valid", validator_result)
            self.assertIn("confidence", validator_result)
            self.assertIsInstance(validator_result["confidence"], int)
            self.assertGreaterEqual(validator_result["confidence"], 0)
            self.assertLessEqual(validator_result["confidence"], 100)

if __name__ == "__main__":
    unittest.main()
