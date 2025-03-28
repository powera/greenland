#!/usr/bin/python3

"""
Unit tests for benchmark generators.

This file should be located at src/tests/lib/benchmarks/test_generators.py

Usage:
    python -m tests.lib.benchmarks.test_generators [options]

Options:
    --stub-llm         Stub out LLM calls using cached responses
    --record           Record LLM responses to cache file for future stub runs
    --cache-file PATH  Path to the cache file (default: llm_responses_cache.json)
    --seed SEED        Random seed for deterministic tests (default: 42)
"""

import unittest
import logging
import json
import os
import sys
import argparse
import hashlib
import pickle
import random
from unittest.mock import patch, MagicMock
from typing import Dict, List, Any, Optional, Type, Tuple

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import BenchmarkQuestion, BenchmarkMetadata
from lib.benchmarks.factory import get_all_benchmark_codes, get_generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MockSession:
    """Mock database session for testing."""

    def __init__(self):
        self.committed = False
        self.queries = []
        self.inserts = []

    def commit(self):
        self.committed = True

    def add(self, obj):
        self.inserts.append(obj)

    def rollback(self):
        pass

    def query(self, *args):
        self.queries.append(args)
        return self


class LLMResponseCache:
    """Cache for storing and retrieving LLM responses."""

    def __init__(self, cache_file_path="llm_responses_cache.json"):
        """Initialize the cache.
        
        Args:
            cache_file_path: Path to the cache file
        """
        self.cache_file_path = cache_file_path
        self.cache = {}
        self.load_cache()
        # Count of cache hits and misses for diagnostics
        self.hit_count = 0
        self.miss_count = 0

    def load_cache(self):
        """Load the cache from file if it exists."""
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached LLM responses from {self.cache_file_path}")
            except Exception as e:
                logger.error(f"Failed to load cache file: {e}")
                self.cache = {}
        else:
            logger.info(f"Cache file {self.cache_file_path} not found, starting with empty cache")
            self.cache = {}

    def save_cache(self):
        """Save the cache to file."""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(self.cache_file_path)), exist_ok=True)
            
            with open(self.cache_file_path, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"Saved {len(self.cache)} cached LLM responses to {self.cache_file_path}")
            logger.info(f"Cache hits: {self.hit_count}, misses: {self.miss_count}")
        except Exception as e:
            logger.error(f"Failed to save cache file: {e}")

    def compute_key(self, prompt: str, model: str, schema: Optional[Dict] = None, context: Optional[str] = None) -> str:
        """Compute a unique key for the request.
        
        Args:
            prompt: The prompt text
            model: The model name
            schema: Optional JSON schema
            context: Optional context
            
        Returns:
            A unique key for this request
        """
        # Combine all request parameters into a single string
        request_str = f"prompt:{prompt}|model:{model}"
        if schema:
            request_str += f"|schema:{json.dumps(schema, sort_keys=True)}"
        if context:
            request_str += f"|context:{context}"
            
        # Generate a hash of the request string
        return hashlib.md5(request_str.encode()).hexdigest()

    def get(self, prompt: str, model: str, schema: Optional[Dict] = None, context: Optional[str] = None) -> Optional[Dict]:
        """Get a cached response for the given request parameters.
        
        Args:
            prompt: The prompt text
            model: The model name
            schema: Optional JSON schema
            context: Optional context
            
        Returns:
            Cached response or None if not found
        """
        key = self.compute_key(prompt, model, schema, context)
        if key in self.cache:
            self.hit_count += 1
            return self.cache[key]
        self.miss_count += 1
        return None

    def put(self, prompt: str, model: str, response: Dict, schema: Optional[Dict] = None, context: Optional[str] = None) -> None:
        """Store a response in the cache.
        
        Args:
            prompt: The prompt text
            model: The model name
            response: The response to cache
            schema: Optional JSON schema
            context: Optional context
        """
        key = self.compute_key(prompt, model, schema, context)
        self.cache[key] = response


# Global cache instance
llm_cache = LLMResponseCache()


class GeneratorTestCase(unittest.TestCase):
    """Base test case for all benchmark generators."""

    generator_class: Optional[Type[BenchmarkGenerator]] = None
    benchmark_code: Optional[str] = None
    
    # Class variables for controlling test behavior
    stub_llm: bool = False
    record_mode: bool = False
    cache_file: str = "llm_responses_cache.json"
    random_seed: int = 42

    def setUp(self):
        # Set random seed for deterministic behavior
        random.seed(self.random_seed)
        
        # Create a mock session to prevent database writes
        self.mock_session = MockSession()
        
        # Initialize or update the cache as needed
        global llm_cache
        if self.cache_file != llm_cache.cache_file_path:
            llm_cache = LLMResponseCache(self.cache_file)
        
        # Use the specific generator class if provided, otherwise load from factory
        if self.generator_class and self.benchmark_code:
            metadata = BenchmarkMetadata(
                code=self.benchmark_code,
                name=f"Test {self.benchmark_code}",
                description="Test benchmark description"
            )
            self.generator = self.generator_class(metadata, session=self.mock_session)
        elif self.benchmark_code:
            # If only benchmark code is provided, use the factory
            self.generator = get_generator(self.benchmark_code, session=self.mock_session)
        else:
            self.skipTest("No generator_class or benchmark_code specified")

        # Patch the insert_benchmark function to prevent database writes
        self.insert_benchmark_patcher = patch('datastore.benchmarks.insert_benchmark')
        self.mock_insert_benchmark = self.insert_benchmark_patcher.start()
        self.mock_insert_benchmark.return_value = (True, "Benchmark inserted")

        # Patch the insert_question function to prevent database writes
        self.insert_question_patcher = patch('datastore.benchmarks.insert_question')
        self.mock_insert_question = self.insert_question_patcher.start()
        self.mock_insert_question.return_value = (True, "Question inserted")
        
        # If stub_llm is enabled but not in record mode, patch LLM functions
        if self.stub_llm and not self.record_mode:
            self._setup_llm_stubs()

    def _setup_llm_stubs(self):
        """Set up LLM function stubs with cached responses."""
        # Patch random.choice, random.sample, etc. to ensure deterministic behavior
        self.random_choice_patcher = patch('random.choice')
        self.mock_random_choice = self.random_choice_patcher.start()
        self.mock_random_choice.side_effect = lambda seq: seq[0]  # Always choose first item
        
        self.random_sample_patcher = patch('random.sample')
        self.mock_random_sample = self.random_sample_patcher.start()
        self.mock_random_sample.side_effect = lambda population, k: population[:k]  # Always take first k items
        
        # Patch unified_client.generate_chat to use cache
        self.generate_chat_patcher = patch('lib.benchmarks.base.unified_client.generate_chat')
        self.mock_generate_chat = self.generate_chat_patcher.start()
        self.mock_generate_chat.side_effect = self._mock_generate_chat
        
        # Patch unified_client.warm_model
        self.warm_model_patcher = patch('lib.benchmarks.base.unified_client.warm_model')
        self.mock_warm_model = self.warm_model_patcher.start()
        self.mock_warm_model.return_value = True

    def _mock_generate_chat(self, prompt, model, brief=False, json_schema=None, context=None, timeout=None):
        """Mock implementation for unified_client.generate_chat that uses the cache."""
        cached = llm_cache.get(prompt, model, json_schema, context)
        
        if cached:
            # Create a mock response object using the cached data
            mock_response = MagicMock()
            mock_response.structured_data = cached.get('structured_data')
            mock_response.response_text = cached.get('response_text')
            mock_response.usage = cached.get('usage')
            return mock_response
        else:
            # If no cached response, create a fallback response
            logger.warning(f"No cached response for prompt: {prompt[:30]}... Using fallback.")
            mock_response = MagicMock()
            
            # Different fallback responses based on schema
            if json_schema:
                if 'antonym' in str(json_schema):
                    mock_response.structured_data = {
                        "word": "example", 
                        "candidates": ["opposite", "similar", "unrelated", "different", "contrasting", "antonym"],
                        "antonym": "antonym",
                        "difficulty": "medium",
                        "category": "adjectives"
                    }
                elif 'valid' in str(json_schema):
                    mock_response.structured_data = {"valid": True, "reason": "Good question"}
                else:
                    # Generic fallback
                    mock_response.structured_data = {"key": "value"}
            else:
                mock_response.response_text = "Fallback response for uncached prompt"
                
            mock_response.usage = {"total_msec": 500, "total_tokens": 100}
            return mock_response

    def tearDown(self):
        # Stop patchers
        self.insert_benchmark_patcher.stop()
        self.insert_question_patcher.stop()
        
        # If LLM calls are stubbed but not in record mode, stop those patchers too
        if self.stub_llm and not self.record_mode:
            self.generate_chat_patcher.stop()
            self.warm_model_patcher.stop()
            self.random_choice_patcher.stop()
            self.random_sample_patcher.stop()
            
        # If in record mode, save the cache
        if self.record_mode:
            llm_cache.save_cache()

    def test_generator_initialization(self):
        """Test that the generator is properly initialized."""
        self.assertIsNotNone(self.generator)
        self.assertEqual(self.generator.metadata.code, self.benchmark_code)

    def test_generate_question(self):
        """Test that the generator can generate a question."""
        question = self.generator.generate_question()
        self.assertIsInstance(question, BenchmarkQuestion)
        self.assertIsNotNone(question.question_text)
        self.assertIsNotNone(question.correct_answer)

    def test_question_structure(self):
        """Test that generated questions have the correct structure."""
        question = self.generator.generate_question()
        
        # Check that the question has all required attributes
        self.assertTrue(hasattr(question, 'question_text'))
        self.assertTrue(hasattr(question, 'answer_type'))
        self.assertTrue(hasattr(question, 'correct_answer'))
        
        # Check that converting to dict works
        question_dict = question.to_dict()
        self.assertIsInstance(question_dict, dict)
        self.assertIn('question_text', question_dict)
        self.assertIn('answer_type', question_dict)
        self.assertIn('correct_answer', question_dict)

    def test_save_question(self):
        """Test that the generator can save a question."""
        question = self.generator.generate_question()
        question_id = self.generator.save_question(question, "test_id")
        
        # Check that the question_id has the correct format
        self.assertTrue(question_id.startswith(self.benchmark_code + ":"))
        
        # Verify insert_question was called
        self.mock_insert_question.assert_called_once()

    def test_batch_save_questions(self):
        """Test that the generator can batch save questions."""
        questions = [self.generator.generate_question() for _ in range(3)]
        question_ids = self.generator.batch_save_questions(questions)
        
        # Check we got the right number of question IDs
        self.assertEqual(len(question_ids), 3)
        
        # Verify insert_question was called the right number of times
        self.assertEqual(self.mock_insert_question.call_count, 3)

    def test_generate_llm_question(self):
        """Test LLM-based question generation."""
        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        
        # If in record mode, we need to wrap the original method to capture responses
        if self.record_mode:
            # Create a wrapper for the real generate_chat function
            original_generate_chat = getattr(
                __import__('lib.benchmarks.base', fromlist=['unified_client']).unified_client, 
                'generate_chat'
            )
            
            def record_wrapper(prompt, model, **kwargs):
                # Call the original function
                response = original_generate_chat(prompt, model, **kwargs)
                
                # Cache the response
                cached_data = {
                    'structured_data': response.structured_data,
                    'response_text': response.response_text,
                    'usage': response.usage.__dict__ if hasattr(response.usage, '__dict__') else response.usage
                }
                llm_cache.put(prompt, model, cached_data, kwargs.get('json_schema'), kwargs.get('context'))
                
                return response
                
            # Apply the wrapper for this test
            with patch('lib.benchmarks.base.unified_client.generate_chat', side_effect=record_wrapper):
                result = self.generator.generate_llm_question("test prompt", schema=schema)
                self.assertIsNotNone(result)
                
                # Also test without schema
                result = self.generator.generate_llm_question("test prompt without schema", schema=None)
                self.assertIsNotNone(result)
        
        elif self.stub_llm:
            # When using stubbed responses, just verify we get something
            result = self.generator.generate_llm_question("test prompt", schema=schema)
            self.assertIsNotNone(result)
            
            # Also test without schema
            result = self.generator.generate_llm_question("test prompt without schema", schema=None)
            self.assertIsNotNone(result)
        
        else:
            # Without stubbing or recording, use temporary mocks
            with patch('lib.benchmarks.base.unified_client.generate_chat') as mock_generate_chat:
                # Configure the mock
                mock_response = MagicMock()
                mock_response.structured_data = {"key": "value"}
                mock_response.response_text = "Test response"
                mock_generate_chat.return_value = mock_response
                
                # Test with schema
                result = self.generator.generate_llm_question("test prompt", schema=schema)
                self.assertEqual(result, {"key": "value"})
                
                # Test without schema
                result = self.generator.generate_llm_question("test prompt", schema=None)
                self.assertEqual(result, "Test response")

    def test_validate_question(self):
        """Test question validation."""
        question = self.generator.generate_question()
        
        # If in record mode, we need to wrap the original method to capture responses
        if self.record_mode:
            # Create a wrapper for the real generate_chat function
            original_generate_chat = getattr(
                __import__('lib.benchmarks.base', fromlist=['unified_client']).unified_client, 
                'generate_chat'
            )
            
            def record_wrapper(prompt, model, **kwargs):
                # Call the original function
                response = original_generate_chat(prompt, model, **kwargs)
                
                # Cache the response
                cached_data = {
                    'structured_data': response.structured_data,
                    'response_text': response.response_text,
                    'usage': response.usage.__dict__ if hasattr(response.usage, '__dict__') else response.usage
                }
                llm_cache.put(prompt, model, cached_data, kwargs.get('json_schema'), kwargs.get('context'))
                
                return response
                
            # Apply the wrapper for this test
            with patch('lib.benchmarks.base.unified_client.generate_chat', side_effect=record_wrapper):
                is_valid, reason = self.generator.validate_question(question)
                self.assertIsNotNone(is_valid)
                self.assertIsNotNone(reason)
        
        elif self.stub_llm:
            # When using stubbed responses, just verify we get something
            is_valid, reason = self.generator.validate_question(question)
            self.assertIsNotNone(is_valid)
            self.assertIsNotNone(reason)
        
        else:
            # Without stubbing or recording, use temporary mocks
            with patch('lib.benchmarks.base.unified_client.generate_chat') as mock_generate_chat:
                # Configure the mock
                mock_response = MagicMock()
                mock_response.structured_data = {"valid": True, "reason": "Good question"}
                mock_generate_chat.return_value = mock_response
                
                is_valid, reason = self.generator.validate_question(question)
                
                self.assertTrue(is_valid)
                self.assertEqual(reason, "Good question")


class TestLetterCountGenerator(GeneratorTestCase):
    """Test case for the LetterCountGenerator."""
    benchmark_code = "0012_letter_count"

    def test_letter_count_question(self):
        """Test specific functionality of the LetterCountGenerator."""
        # Generate a question with specific word and letter
        question = self.generator.generate_question(word="hello", letter="l")
        
        # Check the specific content
        self.assertIn("letter 'l'", question.question_text)
        self.assertIn("word 'hello'", question.question_text)
        self.assertEqual(question.correct_answer, 2)  # 'l' appears twice in 'hello'


class TestAntonymGenerator(GeneratorTestCase):
    """Test case for the AntonymGenerator."""
    benchmark_code = "0016_antonym"

    def test_antonym_question(self):
        """Test specific functionality of the AntonymGenerator."""
        question = self.generator.generate_question()
        
        # Check for antonym-specific properties
        self.assertIn("antonym", question.question_text.lower())
        self.assertTrue(hasattr(question, 'choices'))
        self.assertIsInstance(question.choices, list)


def get_test_suite():
    """Create a test suite with all generator tests."""
    suite = unittest.TestSuite()
    
    # Add specific test cases
    suite.addTest(unittest.makeSuite(TestLetterCountGenerator))
    suite.addTest(unittest.makeSuite(TestAntonymGenerator))
    
    # Dynamically add test cases for all registered benchmarks
    for benchmark_code in get_all_benchmark_codes():
        # Skip the ones we've already added specific tests for
        if benchmark_code in ["0012_letter_count", "0016_antonym"]:
            continue
            
        # Create a new test case class for this benchmark
        test_class_name = f"Test{benchmark_code.replace('_', '')}Generator"
        test_class = type(
            test_class_name,
            (GeneratorTestCase,),
            {"benchmark_code": benchmark_code}
        )
        
        # Add test class to the suite
        suite.addTest(unittest.makeSuite(test_class))
    
    return suite


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Run generator tests')
    
    # LLM stubbing options
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument('--stub-llm', action='store_true', 
                          help='Stub out LLM calls using cached responses')
    cache_group.add_argument('--record', action='store_true',
                          help='Record LLM responses to cache file for future stub runs')
    
    # Cache file path
    parser.add_argument('--cache-file', default='llm_responses_cache.json',
                      help='Path to the cache file (default: llm_responses_cache.json)')
    
    # Random seed
    parser.add_argument('--seed', type=int, default=42,
                      help='Random seed for deterministic tests (default: 42)')
    
    return parser.parse_args()


def run_tests(stub_llm=False, record_mode=False, cache_file='llm_responses_cache.json', random_seed=42):
    """Run all generator tests.
    
    Args:
        stub_llm: Whether to stub out LLM calls using cached responses
        record_mode: Whether to record LLM responses to cache file
        cache_file: Path to the cache file
        random_seed: Random seed for deterministic tests
    """
    # Set the control flags on the test case class
    GeneratorTestCase.stub_llm = stub_llm
    GeneratorTestCase.record_mode = record_mode
    GeneratorTestCase.cache_file = cache_file
    GeneratorTestCase.random_seed = random_seed
    
    # Set global random seed for consistent randomness across all modules
    random.seed(random_seed)
    
    print(f"Using random seed: {random_seed}")
    
    if record_mode:
        print(f"Running tests in RECORD mode - saving responses to {cache_file}")
    elif stub_llm:
        print(f"Running tests with STUBBED LLM calls from cache file {cache_file}")
    else:
        print("Running tests with real LLM calls (can be slow and incur API costs)")
    
    # Initialize the cache
    global llm_cache
    llm_cache = LLMResponseCache(cache_file)
    
    runner = unittest.TextTestRunner(verbosity=2)
    suite = get_test_suite()
    runner.run(suite)
    
    # Save the cache if in record mode
    if record_mode:
        llm_cache.save_cache()


if __name__ == "__main__":
    args = parse_args()
    run_tests(
        stub_llm=args.stub_llm, 
        record_mode=args.record, 
        cache_file=args.cache_file,
        random_seed=args.seed
    )