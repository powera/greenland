#!/usr/bin/python3

"""Generator for the English-to-IPA benchmark."""

import json
import logging
import os
import random
from typing import Dict, List, Optional, Iterator

from lib.benchmarks.base_generator import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata,
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0061_english_to_ipa",
    name="English to IPA Pronunciation",
    description="A benchmark to evaluate a model's ability to convert English words to their IPA pronunciation."
)

@generator("0061_english_to_ipa")
class EnglishToIPAGenerator(BenchmarkGenerator):
    """Generator for English-to-IPA benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        
        # Configure available generation strategies
        self.can_load_from_file = True
        self.can_generate_with_llm = True
        self.can_generate_locally = False
        
        # Set file paths for file-based generation
        self.questions_file_path = "words_ipa.json"
        
        # Set context for LLM-based generation
        self.context = """You are a helpful assistant creating benchmark questions to test language models' 
ability to convert English words to their IPA (International Phonetic Alphabet) pronunciation.
When providing IPA pronunciations, use American English pronunciation as the default."""
    
    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """Generate questions from predefined JSON file."""
        if not self.can_load_from_file:
            return
            
        try:
            # Load words and their IPA pronunciations from the JSON file
            words_data = self.load_json_file(self.questions_file_path)
            
            for item in words_data:
                word = item["word"]
                sentence = item["sentence"]
                
                # Format the question text
                question_text = f"Convert the word '{word}' to IPA pronunciation. Context: {sentence}"
                
                # Create the question object
                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.FREE_TEXT,
                    correct_answer=item["ipa"],
                    category="English Pronunciation",
                    difficulty=Difficulty(item.get("difficulty", "medium")),
                    tags=["ipa", "pronunciation", "english"],
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=False,  # Don't require exact match because of potential variations
                        contains=False,  # Full pronunciation should be correct, not just contain part
                        case_sensitive=True,  # IPA symbols are case-sensitive
                    )
                )
                
                # If there are alternative pronunciations, add them to evaluation criteria
                if "alternatives" in item and item["alternatives"]:
                    question.evaluation_criteria.alternatives = item["alternatives"]
                
                yield question
                
        except Exception as e:
            logger.error(f"Error generating questions from file: {e}")
    
    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """Generate questions using a language model."""
        if not self.can_generate_with_llm:
            return
        
        # Define the schema for LLM-generated questions
        schema = {
            "type": "object",
            "properties": {
                "word": {"type": "string", "description": "The English word to be pronounced"},
                "sentence": {"type": "string", "description": "A sentence using the word for context"},
                "ipa": {"type": "string", "description": "The IPA pronunciation of the word (American English)"},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternative valid IPA pronunciations (British, Australian, etc.)"
                }
            },
            "required": ["word", "sentence", "ipa"]
        }
        
        # Categories of words that are interesting for IPA conversion
        word_categories = [
            "Words with silent letters (knight, psychology, subtle)",
            "Words with unusual pronunciation (choir, colonel, island)",
            "Homographs with different pronunciations (read, wound, tear)",
            "Words with irregular stress patterns (photography, biology)",
            "Words with multiple accepted pronunciations (either, tomato, caramel)",
            "Words that differ in American vs British pronunciation (schedule, leisure)",
            "Words with diphthongs (coin, town, face)",
            "Words with consonant clusters (strengths, sixths)"
        ]
        
        # Generate questions by using the LLM to create words and their IPA
        batch_size = 5  # Generate 5 questions per prompt
        difficulty_levels = ["easy", "medium", "hard"]
        
        for difficulty in difficulty_levels:
            # Select two random categories to focus on
            categories = random.sample(word_categories, 2)
            category_desc = "\n".join([f"- {cat}" for cat in categories])
            
            # Create a prompt for generating a batch of questions
            prompt = f"""
Create {batch_size} English words for an English-to-IPA pronunciation benchmark.

Focus on {difficulty} difficulty words from these categories:
{category_desc}

For each word:
1. Provide the word itself
2. A natural-sounding sentence using the word to clarify its meaning
3. The correct IPA pronunciation using American English
4. Any alternative valid pronunciations (British, Australian variants, etc.)

Use precise IPA notation with proper stress marks. 
Ensure the words are appropriate for testing pronunciation skills.
"""
            
            try:
                # Get LLM response
                response = self.get_llm_question(
                    prompt=prompt,
                    schema={
                        "type": "array",
                        "items": schema
                    }
                )
                
                if isinstance(response, list):
                    for item in response:
                        try:
                            # Format the question text
                            question_text = f"Convert the word '{item['word']}' to IPA pronunciation. Context: {item['sentence']}"
                            
                            # Create the question object
                            alternatives = item.get("alternatives", [])
                            
                            question = BenchmarkQuestion(
                                question_text=question_text,
                                answer_type=AnswerType.FREE_TEXT,
                                correct_answer=item["ipa"],
                                category="English Pronunciation",
                                difficulty=Difficulty(item.get("difficulty", difficulty)),
                                tags=["ipa", "pronunciation", "english", "llm_generated"],
                                evaluation_criteria=EvaluationCriteria(
                                    exact_match=False,
                                    contains=False,
                                    case_sensitive=True
                                )
                            )
                            
                            # Add alternatives if provided
                            if alternatives:
                                question.evaluation_criteria.alternatives = alternatives
                            
                            yield question
                            
                        except Exception as e:
                            logger.error(f"Error processing LLM-generated question: {e}")
                            continue
                    
            except Exception as e:
                logger.error(f"Error generating questions with LLM: {e}")