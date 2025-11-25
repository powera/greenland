#!/usr/bin/python3

"""Generator for the lemma identification benchmark."""

import json
import os
import random
from typing import Dict, List, Optional, Any, Iterator

from lib.benchmarks.base_generator import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata,
    AnswerType, Difficulty, EvaluationCriteria
)
import constants

class LemmaGenerator(BenchmarkGenerator):
    """Generator for lemma identification benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        
        # Configure generation strategies
        self.can_load_from_file = True
        self.can_generate_with_llm = True
        self.can_generate_locally = False
        
        # File paths for file-based generation
        self.questions_file_path = "lemma_words.json"
        
        # LLM generation context
        self.context = """
        You are a linguistic expert helping to create benchmark questions about lemmatization.
        
        Lemmatization is the process of finding the base form (lemma) of a word:
        - For nouns: the singular form (e.g., "cats" → "cat")
        - For verbs: the infinitive form without "to" (e.g., "running" → "run")
        - For adjectives and adverbs: the positive form (e.g., "better" → "good")
        
        The questions should test a model's ability to identify the lemma of a given word.
        """

    def _generate_from_file(self) -> Iterator[BenchmarkQuestion]:
        """Generate questions from file."""
        if not self.can_load_from_file:
            return
            
        try:
            # Load word pairs from JSON file
            words_file_path = os.path.join(
                constants.BENCHMARK_DATA_DIR, 
                self.metadata.code, 
                self.questions_file_path
            )
            
            with open(words_file_path, "r") as f:
                word_pairs = json.load(f)
                
            for word_pair in word_pairs:
                inflected = word_pair["inflected"]
                lemma = word_pair["lemma"]
                
                question = BenchmarkQuestion(
                    question_text=f"What is the lemma (base form) of the word '{inflected}'?",
                    answer_type=AnswerType.FREE_TEXT,
                    correct_answer=lemma,
                    difficulty=Difficulty.MEDIUM,
                    tags=["lemmatization", "linguistics"],
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=True,
                        case_sensitive=False
                    )
                )
                yield question
                
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading lemma words file: {e}")
            raise

    def _generate_with_llm(self) -> Iterator[BenchmarkQuestion]:
        """Generate questions using an LLM."""
        if not self.can_generate_with_llm:
            return
            
        # Define a schema for structured output
        schema = {
            "type": "object",
            "properties": {
                "inflected_word": {
                    "type": "string",
                    "description": "The inflected form of the word"
                },
                "lemma": {
                    "type": "string",
                    "description": "The base form (lemma) of the word"
                },
                "part_of_speech": {
                    "type": "string",
                    "description": "The part of speech (noun, verb, adjective, adverb)",
                    "enum": ["noun", "verb", "adjective", "adverb"]
                },
                "difficulty": {
                    "type": "string",
                    "description": "The difficulty level of this lemmatization",
                    "enum": ["easy", "medium", "hard"]
                }
            },
            "required": ["inflected_word", "lemma", "part_of_speech", "difficulty"]
        }
        
        # List of categories to generate questions for
        categories = [
            "irregular verbs",
            "plural nouns",
            "comparative and superlative adjectives",
            "irregular plurals",
            "irregular past tense verbs",
            "participles",
            "loan words from Latin/Greek with irregular plurals"
        ]
        
        # Generate 3 questions per category
        for category in categories:
            # Generate 3 different questions per category
            for i in range(3):
                prompt = f"""
                Create a lemmatization challenge using {category}.
                The challenge should test identifying the correct lemma (base form) of a word.
                Provide an inflected word and its proper lemma.
                """
                
                try:
                    # Generate structured question data
                    question_data = self.get_llm_question(
                        prompt=prompt,
                        schema=schema
                    )
                    
                    if not question_data or "inflected_word" not in question_data or "lemma" not in question_data:
                        continue
                        
                    # Create benchmark question
                    question = BenchmarkQuestion(
                        question_text=f"What is the lemma (base form) of the word '{question_data['inflected_word']}'?",
                        answer_type=AnswerType.FREE_TEXT,
                        correct_answer=question_data["lemma"],
                        category=question_data.get("part_of_speech", ""),
                        difficulty=Difficulty(question_data.get("difficulty", "medium")),
                        tags=["lemmatization", category.replace(" ", "_")],
                        evaluation_criteria=EvaluationCriteria(
                            exact_match=True,
                            case_sensitive=False
                        )
                    )
                    yield question
                    
                except Exception as e:
                    print(f"Error generating lemma question: {e}")
                    continue