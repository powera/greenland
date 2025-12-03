#!/usr/bin/python3

"""Translation benchmark generator implementation."""

import json
import logging
import random
from typing import Dict, Optional, List, Iterator

from lib.benchmarks.base_generator import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion,
    BenchmarkMetadata,
    AnswerType,
    Difficulty,
    EvaluationCriteria,
)
from lib.benchmarks.factory import benchmark, generator, register_benchmark_metadata
from benchmarks.data.wordlist_extended import TRANSLATIONS, TranslationEntry

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define valid language codes
VALID_LANGS = {"en", "fr", "de", "ind", "sw", "ko", "kn", "zh"}


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
    description = (
        f"Tests ability to translate {origin_lang.upper()} words to "
        f"{target_lang.upper()} with multiple choice validation"
    )

    return BenchmarkMetadata(
        code=benchmark_code,
        name=benchmark_name,
        description=description,
        version="1.0",
        tags=["translation", origin_lang, target_lang],
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
        # Call the parent constructor first
        super().__init__(metadata, session)

        # Extract language codes from metadata code
        parts = metadata.code.split("_")
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

        # Set up generation strategy flags
        self.can_generate_locally = True  # We can generate locally from wordlist
        self.can_generate_with_llm = True  # We can also use LLM for more diverse translations
        self.can_load_from_file = False  # We don't have file-based translations

        # Set LLM context for generation
        self.context = f"""You are a helpful assistant creating translation questions.
        You will translate words from {self.origin_lang.upper()} to {self.target_lang.upper()}.
        Always provide accurate translations and include any important cultural or linguistic context.
        """

    def get_translation(self, entry: TranslationEntry, lang: str) -> str:
        """Get translation for a specific language from entry."""
        return getattr(entry, lang, "")

    def get_translation_details(self, entry: TranslationEntry, lang: str) -> Optional[str]:
        """Get translation details for a specific language from entry."""
        return getattr(entry, f"{lang}_details", None)

    def _create_question(
        self, origin_word: str, target_word: str, include_choices: bool = True
    ) -> BenchmarkQuestion:
        """
        Create a translation question from origin and target words.

        Args:
            origin_word: Word in the origin language
            target_word: Translation in the target language
            include_choices: Whether to include multiple choice options

        Returns:
            BenchmarkQuestion object
        """
        # Create question text
        question_text = f'Translate this word: "{origin_word}"'

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

        # Determine difficulty (could be enhanced based on word complexity)
        difficulty = Difficulty.MEDIUM

        # Create evaluation criteria
        eval_criteria = EvaluationCriteria(exact_match=True, case_sensitive=False, contains=False)

        # Create and return the question
        question = BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.MULTIPLE_CHOICE if include_choices else AnswerType.FREE_TEXT,
            correct_answer=target_word,
            category=f"translation_{self.origin_lang}_{self.target_lang}",
            difficulty=difficulty,
            tags=tags,
            choices=choices,
            evaluation_criteria=eval_criteria,
        )

        # Add schema for structured response
        question.schema = {
            "type": "object",
            "properties": {"translation": {"type": "string"}},
            "required": ["translation"],
        }

        return question

    def _generate_locally(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate translation questions from local wordlist.

        Yields:
            BenchmarkQuestion objects one at a time
        """
        # Filter for entries that have valid translations for both languages
        valid_entries = [
            entry
            for entry in TRANSLATIONS
            if self.get_translation(entry, self.origin_lang)
            and self.get_translation(entry, self.target_lang)
        ]

        if not valid_entries:
            logger.warning(
                f"No valid translations found for {self.origin_lang} to {self.target_lang}"
            )
            return

        # Shuffle entries to get different questions each time
        random.shuffle(valid_entries)

        # Generate and yield questions
        for entry in valid_entries:
            origin_word = self.get_translation(entry, self.origin_lang)
            target_word = self.get_translation(entry, self.target_lang)

            # Get any special notes about usage (potential future enhancement)
            origin_details = self.get_translation_details(entry, self.origin_lang)
            target_details = self.get_translation_details(entry, self.target_lang)

            # Create and yield question
            yield self._create_question(origin_word, target_word)

    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate translation questions using an LLM.

        This allows for more diverse translations that might not be in our database.

        Yields:
            BenchmarkQuestion objects one at a time
        """
        # Define schema for LLM responses
        schema = {
            "type": "object",
            "properties": {
                "origin_word": {
                    "type": "string",
                    "description": f"A word in {self.origin_lang.upper()}",
                },
                "target_word": {
                    "type": "string",
                    "description": f"The translation in {self.target_lang.upper()}",
                },
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            },
            "required": ["origin_word", "target_word", "difficulty"],
        }

        # Provide word categories to prompt more diverse responses
        categories = [
            "common nouns",
            "verbs",
            "adjectives",
            "adverbs",
            "food",
            "animals",
            "colors",
            "emotions",
            "technology",
            "culture-specific terms",
            "idioms",
            "body parts",
        ]

        # Generate questions indefinitely (until the caller stops iterating)
        while True:
            # Choose a random category for variety
            category = random.choice(categories)

            # Create prompt
            prompt = f"""Please generate a translation pair from {self.origin_lang.upper()} to {self.target_lang.upper()}.
            The word should be from the category: {category}.
            Provide the original word and its accurate translation.
            Also rate the difficulty of the translation as easy, medium, or hard.
            """

            try:
                # Get translation pair from LLM
                response = self.get_llm_question(prompt, schema=schema)

                if not response or "origin_word" not in response or "target_word" not in response:
                    logger.warning("Incomplete response from LLM, retrying...")
                    continue

                # Extract data
                origin_word = response["origin_word"]
                target_word = response["target_word"]

                # Create and yield question
                yield self._create_question(origin_word, target_word)

            except Exception as e:
                logger.error(f"Error generating translation with LLM: {e}")
                # Skip this iteration but continue generating
                continue


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
                logger.error(
                    f"Error generating benchmark for {origin_lang} to {target_lang}: {str(e)}"
                )

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
                logger.error(
                    f"Error generating benchmark for {origin_lang} to {target_lang}: {str(e)}"
                )


if __name__ == "__main__":
    # When run directly, generate data for all language pairs
    LanguagePairGenerator.generate_specific_pairs([("en", "fr"), ("en", "zh"), ("sw", "ko")])
