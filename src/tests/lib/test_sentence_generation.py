#!/usr/bin/python3

"""
Tests for the sentence generation library.
"""

import unittest
from unittest.mock import Mock, patch
from lib.sentence_generation import SentenceGenerator

class TestSentenceGenerator(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.sample_matrices = {
            "subjects": {
                "I": {"english": "I", "lithuanian": "aš", "guid": "PRON_001"}
            },
            "verbs": {
                "eat": {
                    "english": "eat",
                    "lithuanian": "valgyti", 
                    "compatible_subjects": ["subjects"],
                    "compatible_objects": ["foods"]
                }
            },
            "foods": {
                "apple": {"english": "apple", "lithuanian": "obuolys", "guid": "F01_001"}
            }
        }
        
        self.sample_grammar = {
            "lt": {
                "cases": {
                    "accusative": {"endings": {"default": "ą"}}
                }
            }
        }
        
        self.generator = SentenceGenerator(
            word_matrices=self.sample_matrices,
            grammar_rules=self.sample_grammar
        )
    
    def test_create_sentence_pattern(self):
        """Test basic sentence pattern creation."""
        pattern = self.generator.create_sentence_pattern("SVO")
        
        self.assertIsNotNone(pattern)
        self.assertIn("subject", pattern)
        self.assertIn("verb", pattern)
        self.assertIn("object", pattern)
        self.assertIn("tense", pattern)
        self.assertEqual(pattern["pattern_type"], "SVO")
    
    def test_pattern_to_sentences(self):
        """Test converting pattern to sentences."""
        pattern = {
            "subject": {"key": "I", "data": self.sample_matrices["subjects"]["I"]},
            "verb": {"key": "eat", "data": self.sample_matrices["verbs"]["eat"]},
            "object": {"key": "apple", "data": self.sample_matrices["foods"]["apple"]},
            "tense": "present"
        }
        
        sentences = self.generator.pattern_to_sentences(pattern, ["en", "lt"])
        
        self.assertIn("en", sentences)
        self.assertIn("lt", sentences)
        self.assertTrue(len(sentences["en"]) > 0)
        self.assertTrue(len(sentences["lt"]) > 0)
    
    def test_english_verb_forms(self):
        """Test English verb conjugation."""
        # Present tense
        self.assertEqual(
            self.generator._get_english_verb_form("eat", "I", "present"),
            "eat"
        )
        self.assertEqual(
            self.generator._get_english_verb_form("eat", "he", "present"), 
            "eats"
        )
        
        # Future tense
        self.assertEqual(
            self.generator._get_english_verb_form("eat", "I", "future"),
            "will eat"
        )
    
    def test_incompatible_pattern(self):
        """Test handling of incompatible word combinations."""
        # Create matrices with no compatible combinations
        incompatible_matrices = {
            "subjects": {"I": {"english": "I"}},
            "verbs": {
                "eat": {
                    "compatible_subjects": ["animals"],  # No animals in subjects
                    "compatible_objects": ["foods"]
                }
            },
            "foods": {"apple": {"english": "apple"}}
        }
        
        generator = SentenceGenerator(incompatible_matrices, {})
        pattern = generator.create_sentence_pattern("SVO")
        
        self.assertIsNone(pattern)
    
    @patch('lib.sentence_generation.UnifiedLLMClient')
    def test_llm_generation(self, mock_client_class):
        """Test LLM-enhanced generation."""
        # Mock LLM client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.structured_data = {
            "makes_sense": True,
            "english": "I eat an apple.",
            "target_sentence": "Aš valgau obuolį.",
            "adjective_used": None
        }
        mock_client.generate_chat.return_value = mock_response
        
        generator = SentenceGenerator(
            self.sample_matrices,
            self.sample_grammar,
            llm_client=mock_client
        )
        
        pattern = {
            "subject": {"key": "I", "data": self.sample_matrices["subjects"]["I"]},
            "verb": {"key": "eat", "data": self.sample_matrices["verbs"]["eat"]},
            "object": {"key": "apple", "data": self.sample_matrices["foods"]["apple"]},
            "tense": "present"
        }
        
        result = generator.generate_with_llm(pattern, "lt")
        
        self.assertIsNotNone(result)
        self.assertTrue(result["llm_generated"])
        self.assertEqual(result["english"], "I eat an apple.")
        self.assertEqual(result["target_sentence"], "Aš valgau obuolį.")

if __name__ == "__main__":
    unittest.main()