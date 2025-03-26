#!/usr/bin/python3

"""Translation benchmark generator implementation."""

import json
import logging
import random
from typing import Dict, Optional, List

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, 
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import benchmark, generator, register_benchmark_metadata
from benchmarks.data.wordlist_extended import TRANSLATIONS, TranslationEntry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define valid language codes
VALID_LANGS = {'en', 'fr', 'de', 'ind', 'sw', 'ko', 'kn', 'zh'}

# Define benchmark metadata creator
def get_translation_metadata(origin_lang: str, target_lang: str) -> BenchmarkMetadata:
    """
    Create metadata for a specific language pair.
    
    Args:
        origin_lang: Source language code
        target_lang: Target language code
        
    Returns:
        BenchmarkMetadata object
    """
    benchmark_code = f"0050_translation_{origin_lang}_{target_lang}"
    benchmark_name = f"Translation ({origin_lang.upper()} → {target_lang.upper()})"
    description = (f"Tests ability to translate {origin_lang.upper()} words to "
                  f"{target_lang.upper()} with multiple choice validation")
    
    return BenchmarkMetadata(
        code=benchmark_code,
        name=benchmark_name,
        description=description,
        version="1.0",
        tags=["translation", origin_lang, target_lang]
    )

@generator("0050_translation")
class TranslationGenerator(BenchmarkGenerator):
    """Generator for translation benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """
        Initialize generator with language pair from metadata.
        
        Args:
            metadata: Benchmark metadata
            session: Optional database session
        """
        super().__init__(metadata, session)
        
        # Extract language codes from metadata code
        parts = metadata.code.split('_')
        if len(parts) == 4:
            self.origin_lang = parts[2]
            self.target_lang = parts[3]
        else:
            raise ValueError(f"Invalid metadata code format: {metadata.code}")
        
        # Validate language codes
        if self.origin_lang not in VALID_LANGS or self.target_lang not in VALID_LANGS:
            raise ValueError(f"Language codes must be one of: {', '.join(VALID_LANGS)}")
        if self.origin_lang == self.target_lang:
            raise ValueError("Origin and target languages must be different")

    def get_translation(self, entry: TranslationEntry, lang: str) -> str:
        """Get translation for a specific language from entry."""
        return getattr(entry, lang, "")

    def get_translation_details(self, entry: TranslationEntry, lang: str) -> Optional[str]:
        """Get translation details for a specific language from entry."""
        return getattr(entry, f"{lang}_details", None)

    def generate_question(self, word_entry: TranslationEntry, 
                         include_choices: bool = True) -> BenchmarkQuestion:
        """
        Generate a single translation question.
        
        Args:
            word_entry: TranslationEntry object
            include_choices: Whether to include multiple choice options
            
        Returns:
            BenchmarkQuestion object
        """
        # Get translations for origin and target languages
        origin_word = self.get_translation(word_entry, self.origin_lang)
        target_word = self.get_translation(word_entry, self.target_lang)
        
        # Get any special notes about usage
        origin_details = self.get_translation_details(word_entry, self.origin_lang)
        target_details = self.get_translation_details(word_entry, self.target_lang)
        
        # Create question text
        question_text = f"Translate this word: \"{origin_word}\""
        
        # Create list of possible answers for multiple choice
        choices = []
        if include_choices:
            all_translations = [
                self.get_translation(entry, self.target_lang) 
                for entry in TRANSLATIONS 
                if self.get_translation(entry, self.target_lang)
            ]
            incorrect_choices = [t for t in all_translations if t != target_word]
            
            # Select 7 random incorrect choices
            choices = random.sample(incorrect_choices, min(7, len(incorrect_choices)))
            # Add the correct answer
            choices.append(target_word)
            # Shuffle the choices
            random.shuffle(choices)
            
            # Add choices to question text
            question_text += f"\nPossible translations: {', '.join(choices)}"
        
        # Create additional metadata as tags
        tags = ["translation", self.origin_lang, self.target_lang]
        if origin_details or target_details:
            tags.append("has_details")
        
        # Determine difficulty (could be enhanced based on word complexity)
        difficulty = Difficulty.MEDIUM
        
        # Create evaluation criteria
        eval_criteria = EvaluationCriteria(
            exact_match=True,
            case_sensitive=False,
            contains=False
        )
        
        # Create and return the question
        question = BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.MULTIPLE_CHOICE if include_choices else AnswerType.FREE_TEXT,
            correct_answer=target_word,
            category=f"translation_{self.origin_lang}_{self.target_lang}",
            difficulty=difficulty,
            tags=tags,
            choices=choices,
            evaluation_criteria=eval_criteria
        )
        
        # Add schema for structured response
        question.schema = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"}
            },
            "required": ["translation"]
        }
        
        return question

    def load_to_database(self) -> None:
        """Load generated translation questions into database."""
        # Filter for entries that have valid translations for both languages
        valid_entries = [
            entry for entry in TRANSLATIONS 
            if self.get_translation(entry, self.origin_lang) and 
               self.get_translation(entry, self.target_lang)
        ]
        
        if not valid_entries:
            raise ValueError(f"No valid translations found for {self.origin_lang} to {self.target_lang}")
        
        # Generate and save questions
        questions = []
        for idx, entry in enumerate(valid_entries):
            question = self.generate_question(entry)
            questions.append(question)
        
        # Batch save questions
        self.batch_save_questions(questions)
        logger.info(f"Generated and saved {len(questions)} translation questions")

class LanguagePairGenerator:
    """Helper class to generate benchmark data for all language pairs."""
    
    @staticmethod
    def generate_all_pairs(session=None):
        """Generate benchmark data for all valid language pairs."""
        all_pairs = []
        
        # Generate all possible language pairs
        for origin_lang in VALID_LANGS:
            for target_lang in VALID_LANGS:
                if origin_lang != target_lang:
                    all_pairs.append((origin_lang, target_lang))
        
        # Generate benchmark data for each pair
        for origin_lang, target_lang in all_pairs:
            try:
                # Create metadata
                metadata = get_translation_metadata(origin_lang, target_lang)
                
                # Create generator
                generator = TranslationGenerator(metadata, session)
                
                # Load to database
                generator.load_to_database()
                
                logger.info(f"Generated benchmark data for {origin_lang} to {target_lang}")
                
            except Exception as e:
                logger.error(f"Error generating benchmark for {origin_lang} to {target_lang}: {str(e)}")

    # Modified version to generate only specified pairs
    @staticmethod
    def generate_specific_pairs(pairs, session=None):
        """Generate benchmark data for specific language pairs."""
        for origin_lang, target_lang in pairs:
            try:
                # Create metadata
                metadata = get_translation_metadata(origin_lang, target_lang)
                register_benchmark_metadata(metadata)
                
                # Create generator
                generator = TranslationGenerator(metadata, session)
                
                # Load to database
                generator.load_to_database()
                
                logger.info(f"Generated benchmark data for {origin_lang} to {target_lang}")
                
            except Exception as e:
                logger.error(f"Error generating benchmark for {origin_lang} to {target_lang}: {str(e)}")

    

if __name__ == "__main__":
    # When run directly, generate data for all language pairs
    LanguagePairGenerator.generate_all_pairs()
