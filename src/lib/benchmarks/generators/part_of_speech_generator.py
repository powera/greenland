#!/usr/bin/python3

"""Generator for part of speech benchmark questions."""

import json
import logging
import random
from typing import Dict, List, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Supported parts of speech for the benchmark
PARTS_OF_SPEECH = [
    "noun", "verb", "adjective", "adverb", "pronoun", 
    "preposition", "conjunction", "interjection", "determiner"
]

@generator("0032_part_of_speech")
class PartOfSpeechGenerator(BenchmarkGenerator):
    """Generator for part of speech identification benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        
        # Set custom context for LLM-based generation
        self.context = """You are a linguistics expert helping to create part-of-speech benchmark questions.
Your task is to create clear, unambiguous questions about identifying parts of speech in sentences.
Each question should have a clear, correct answer based on standard English grammar rules."""
    
    def _load_sample_data(self) -> List[Dict]:
        """
        Load sample sentences with part of speech data from JSON file.
        
        Returns:
            List of dictionaries containing sentence data
        """
        try:
            # Use base class method to load JSON file
            samples = self.load_json_file("samples.json")
            logger.info(f"Loaded {len(samples)} sample sentences")
            return samples
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading sample data: {str(e)}")
            return []
    
    def _generate_sentence_with_llm(self) -> Dict:
        """
        Generate a sentence with target word and part of speech using an LLM.
        
        Returns:
            Dictionary with sentence, target_word, and pos
        """
        # Schema for structured LLM response
        schema = {
            "type": "object",
            "properties": {
                "sentence": {
                    "type": "string",
                    "description": "A clear, grammatically correct sentence"
                },
                "target_word": {
                    "type": "string",
                    "description": "A word from the sentence to analyze"
                },
                "pos": {
                    "type": "string",
                    "description": "The part of speech of the target word",
                    "enum": PARTS_OF_SPEECH
                }
            },
            "required": ["sentence", "target_word", "pos"]
        }
        
        # Create prompt for the LLM
        pos_type = random.choice(PARTS_OF_SPEECH)
        prompt = f"""Create a simple, clear sentence that contains at least one {pos_type}.
Choose one {pos_type} from your sentence as the target word.
Return the sentence, the target word (which must be a {pos_type}), and confirm that the part of speech is '{pos_type}'."""
        
        # Generate sentence data using LLM
        sentence_data = self.generate_llm_question(prompt, schema=schema)
        return sentence_data
        
    def generate_question(self, sentence_data: Optional[Dict] = None) -> BenchmarkQuestion:
        """
        Generate a question to identify the part of speech of a word.
        
        Args:
            sentence_data: Optional dictionary containing sentence, target_word, and pos.
                          If None, will first try to use sample data, then fall back to LLM.
            
        Returns:
            BenchmarkQuestion object
        """
        # If no sentence data provided, try to get from samples before using LLM
        if not sentence_data:
            # Try to load sample data if we haven't already
            if not hasattr(self, '_samples') or not self._samples:
                self._samples = self._load_sample_data()
                self._sample_index = 0
            
            # Use a sample if available, otherwise generate with LLM
            if hasattr(self, '_samples') and self._samples and self._sample_index < len(self._samples):
                sentence_data = self._samples[self._sample_index]
                self._sample_index += 1
                logger.info(f"Using sample data ({self._sample_index}/{len(self._samples)})")
            else:
                sentence_data = self._generate_sentence_with_llm()
                logger.info("Generated sentence data using LLM")
        
        sentence = sentence_data["sentence"]
        target_word = sentence_data["target_word"]
        correct_pos = sentence_data["pos"]
        
        # Create prompt for the model
        question_text = f"In the sentence '{sentence}', what is the part of speech of the word '{target_word}'?"
        
        # Create schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "part_of_speech": {
                    "type": "string",
                    "description": "The part of speech of the target word"
                }
            },
            "required": ["part_of_speech"]
        }
        
        # Create the benchmark question
        return BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.JSON,
            correct_answer={"part_of_speech": correct_pos},
            category="grammar",
            difficulty=Difficulty.MEDIUM,
            tags=["grammar", "part-of-speech", "linguistics"],
            schema=schema,
            evaluation_criteria=EvaluationCriteria(
                exact_match=False,
                case_sensitive=False,
                required_fields=["part_of_speech"]
            )
        )
