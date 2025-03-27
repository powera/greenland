#!/usr/bin/python3

"""Generator for part of speech benchmark questions."""

import json
import logging
import os
import random
from typing import Dict, List, Optional, Any, Tuple

import constants
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
        
    def _load_sample_data(self) -> List[Dict]:
        """
        Load sample sentences with part of speech data from JSON file.
        
        Returns:
            List of dictionaries containing sentence data
        """
        data_path = os.path.join(
            constants.BENCHMARK_DATA_DIR, 
            "0032_part_of_speech", 
            "samples.json"
        )
        
        try:
            with open(data_path, 'r') as f:
                samples = json.load(f)
            
            logger.info("Loaded %d sample sentences from %s", len(samples), data_path)
            return samples
            
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Error loading sample data: %s", str(e))
            return []
        
    def generate_question(self, sentence_data: Dict) -> BenchmarkQuestion:
        """
        Generate a question to identify the part of speech of a word.
        
        Args:
            sentence_data: Dictionary containing sentence, target_word, and pos
            
        Returns:
            BenchmarkQuestion object
        """
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
        
    def load_to_database(self) -> List[str]:
        """
        Load part of speech questions into the database.
        
        Returns:
            List of question IDs
        """
        logger.info("Generating part of speech benchmark questions")
        
        # Load sample data from JSON file
        samples = self._load_sample_data()
        
        if not samples:
            logger.error("No sample data available. Cannot generate questions.")
            return []
        
        questions = []
        for sentence_data in samples:
            question = self.generate_question(sentence_data)
            questions.append(question)
            
        # Save questions with sequential IDs
        question_ids = self.batch_save_questions(questions, "pos")
        logger.info("Generated %d part of speech questions", len(question_ids))
        
        return question_ids
