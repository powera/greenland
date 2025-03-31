#!/usr/bin/python3

"""
Unit tests for benchmark generator 'from file' and 'local' code paths.
Verifies that these paths work correctly without making LLM calls.
"""

import unittest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock, ANY

from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.base_generator import BenchmarkGenerator
from lib.benchmarks.generators.spell_check_generator import SpellCheckGenerator
from lib.benchmarks.generators.definitions_generator import DefinitionsGenerator
from lib.benchmarks.generators.letter_count_generator import LetterCountGenerator

class TestBenchmarkGenerators(unittest.TestCase):
    """Test case for benchmark generators."""

    def setUp(self):
        """Set up test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Create a mock session
        self.mock_session = MagicMock()
        
        # Create a patch for the database insert_benchmark function
        self.patch_insert_benchmark = patch('datastore.benchmarks.insert_benchmark', return_value=(True, "Success"))
        self.mock_insert_benchmark = self.patch_insert_benchmark.start()
        
        # Create a patch for the unified_client to ensure no LLM calls
        self.patch_unified_client = patch('clients.unified_client.generate_chat')
        self.mock_unified_client = self.patch_unified_client.start()
        self.mock_unified_client.side_effect = self.unified_client_error
        
        # Create sample benchmark metadata
        self.test_metadata = BenchmarkMetadata(
            code="test_benchmark",
            name="Test Benchmark",
            description="Test benchmark for unit tests"
        )
    
    def tearDown(self):
        """Clean up after test."""
        # Stop patches
        self.patch_insert_benchmark.stop()
        self.patch_unified_client.stop()
        
        # Clean up temporary directory
        self.temp_dir.cleanup()
    
    def unified_client_error(self, *args, **kwargs):
        """Raises an exception if unified_client is called."""
        self.fail("unified_client.generate_chat was called, but should not have been")
    
    def create_test_file(self, filename, content):
        """Helper to create a test file in the temporary directory."""
        path = os.path.join(self.temp_dir.name, filename)
        with open(path, 'w') as f:
            if filename.endswith('.json'):
                json.dump(content, f)
            else:
                f.write('\n'.join(content))
        return path
    
    @patch('os.path.join')
    @patch('builtins.open')
    def test_base_generator_load_files(self, mock_open, mock_path_join):
        """Test the file loading methods in BenchmarkGenerator."""
        # Setup mocks for load_json_file
        mock_path_join.return_value = "/mock/path/file.json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = '{"key": "value"}'
        mock_open.return_value = mock_file
        
        # Create a basic generator
        generator = BenchmarkGenerator(self.test_metadata, self.mock_session)
        
        # Test load_json_file
        result = generator.load_json_file("file.json")
        self.assertEqual(result, {"key": "value"})
        mock_open.assert_called_once()
        
        # Reset mocks for load_text_file
        mock_open.reset_mock()
        mock_path_join.return_value = "/mock/path/file.txt"
        mock_file.__enter__.return_value.read.side_effect = None
        mock_file.__enter__.return_value.__iter__.return_value = ["line1", "line2", "", "line3"]
        
        # Test load_text_file
        result = generator.load_text_file("file.txt")
        self.assertEqual(result, ["line1", "line2", "line3"])
        mock_open.assert_called_once()
    
    @patch('os.listdir')
    def test_spell_check_generator_from_file(self, mock_listdir):
        """Test SpellCheckGenerator's from_file generation."""
        # Create test data
        spell_check_data = [
            {
                "sentence": "The atention span of children varies widely.",
                "incorrect": "atention",
                "correct": "attention"
            }
        ]
        
        # Setup mocks
        mock_listdir.return_value = ["attention.json"]
        
        # Create patched generator with mocked file loading
        metadata = BenchmarkMetadata(code="0015_spell_check", name="Spell Check", description="Test")
        
        with patch.object(SpellCheckGenerator, 'load_json_file', return_value=spell_check_data):
            generator = SpellCheckGenerator(metadata, self.mock_session)
            generator.word_files = ["attention"]
            
            # Get questions from file
            questions = list(generator._generate_from_file())
            
            # Verify we got expected questions without calling the LLM
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0].correct_answer["incorrect"], "atention")
            self.assertEqual(questions[0].correct_answer["correct"], "attention")
            
            # Ensure no LLM calls
            self.mock_unified_client.assert_not_called()
    
    def test_letter_count_generator_local(self):
        """Test LetterCountGenerator's local generation."""
        # Create metadata
        metadata = BenchmarkMetadata(code="0012_letter_count", name="Letter Count", description="Test")
        
        # Create generator
        generator = LetterCountGenerator(metadata, self.mock_session)
        
        # Get questions using local generation
        questions = list(itertools.islice(generator._generate_locally(), 10))
        
        # Verify we got expected questions without calling the LLM
        self.assertEqual(len(questions), 10)
        for question in questions:
            self.assertTrue(question.question_text.startswith("How many times does the letter"))
            self.assertIsInstance(question.correct_answer, int)
        
        # Ensure no LLM calls
        self.mock_unified_client.assert_not_called()
    
    @patch('builtins.open')
    @patch('os.path.join')
    def test_definitions_generator_with_wordlist(self, mock_path_join, mock_open):
        """Test DefinitionsGenerator with a mock wordlist."""
        # Setup mock for wordlist
        mock_path_join.return_value = "/mock/path/wordlist.txt"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.__iter__.return_value = ["apple", "banana", "cherry"]
        mock_open.return_value = mock_file
        
        # Create metadata
        metadata = BenchmarkMetadata(code="0020_definitions", name="Definitions", description="Test")
        
        # Create generator with mock load_text_file method
        with patch.object(DefinitionsGenerator, 'load_text_file', return_value=["apple", "banana", "cherry"]):
            generator = DefinitionsGenerator(metadata, self.mock_session)
            
            # Check that _load_word_list returns expected words
            word_list = generator._load_word_list()
            self.assertEqual(word_list, ["apple", "banana", "cherry"])
            
            # Verify the _generate_with_llm method would be called for definitions
            # We don't actually test it since we're avoiding LLM calls
            self.assertTrue(generator.can_generate_with_llm)
            self.assertFalse(generator.can_generate_locally)
    
    def test_combined_generator_prefers_file_over_llm(self):
        """Test that the combined generator prefers file-based over LLM when available."""
        # Create a custom generator with file and LLM methods
        class TestGenerator(BenchmarkGenerator):
            def __init__(self, metadata, session):
                super().__init__(metadata, session)
                self.can_load_from_file = True
                self.can_generate_locally = False
                self.can_generate_with_llm = True
                self.file_called = False
                self.llm_called = False
            
            def _generate_from_file(self, **kwargs):
                self.file_called = True
                yield MagicMock()
                yield MagicMock()
            
            def _generate_with_llm(self, **kwargs):
                self.llm_called = True
                yield MagicMock()
        
        # Create generator
        generator = TestGenerator(self.test_metadata, self.mock_session)
        
        # Make sure we're starting fresh
        generator._combined_generator = None

        # Get first question using the combined generator
        question = generator.generate_question()
        
        # Verify file method was called but LLM was not
        self.assertTrue(generator.file_called)
        self.assertFalse(generator.llm_called)
        
        # Ensure no LLM calls via unified_client
        self.mock_unified_client.assert_not_called()
    
    def test_save_question(self):
        """Test the save_question method."""
        # Create a mock for insert_question
        with patch('datastore.benchmarks.insert_question', return_value=(True, "Success")) as mock_insert_question:
            # Create a basic generator
            generator = BenchmarkGenerator(self.test_metadata, self.mock_session)
            
            # Create a mock question
            mock_question = MagicMock()
            mock_question.to_dict.return_value = {"question_text": "test"}
            
            # Test save_question with custom ID
            question_id = generator.save_question(mock_question, "custom_id")
            self.assertEqual(question_id, "test_benchmark:custom_id")
            mock_insert_question.assert_called_once_with(
                self.mock_session, 
                "test_benchmark:custom_id", 
                "test_benchmark", 
                ANY
            )
            
            # Reset mock and test without custom ID (should generate UUID)
            mock_insert_question.reset_mock()
            question_id = generator.save_question(mock_question)
            self.assertTrue(question_id.startswith("test_benchmark:"))
            self.assertGreater(len(question_id), len("test_benchmark:"))
            mock_insert_question.assert_called_once()


# Additional imports needed
import itertools

if __name__ == "__main__":
    unittest.main()