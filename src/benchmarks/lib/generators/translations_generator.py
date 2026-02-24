#!/usr/bin/python3

"""Translation benchmark generator implementation."""

import json
import logging
from pathlib import Path
import random
from typing import Any, Dict, Iterator, List, Optional

from benchmarks.data.wordlist_extended import TRANSLATIONS, TranslationEntry
from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import benchmark, generator, register_benchmark_metadata

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Define valid language codes (includes both wordlist_extended and database export languages)
VALID_LANGS = {
    "en",
    "fr",
    "de",
    "ind",
    "sw",
    "ko",
    "kn",
    "zh",
    "lt",
    "es",
    "it",
    "nl",
    "pt",
    "sv",
    "vi",
    "ja",
}

# Release dataset constraints for translation benchmark generation
_RELEASE_LEMMAS_DIR = Path(__file__).resolve().parents[4] / "data" / "release" / "lemmas"
_SUPPORTED_POS_TYPES = {"nouns", "verbs", "adjectives"}
_MIN_CATEGORY_SIZE = 10
_DISTRACTOR_COUNT = 5


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
        category="translation",
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
        self.can_load_from_file = True  # We can load from exported translations file

        # Strategy order: prefer file, then local wordlist, then LLM
        self.strategy_order = ["file", "local", "llm"]

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
        self,
        origin_word: str,
        target_word: str,
        category: str,
        choices: Optional[List[str]] = None,
    ) -> BenchmarkQuestion:
        """
        Create a translation question from origin and target words.

        Args:
            origin_word: Word in the origin language
            target_word: Translation in the target language
            category: Category used for same-topic distractors
            choices: Optional answer choices

        Returns:
            BenchmarkQuestion object
        """
        # Create question text
        question_text = f'Translate this word: "{origin_word}"'
        normalized_choices = choices or []

        # Create additional metadata as tags
        tags = ["translation", self.origin_lang, self.target_lang]

        # Determine difficulty (could be enhanced based on word complexity)
        difficulty = Difficulty.MEDIUM

        # Create evaluation criteria
        eval_criteria = EvaluationCriteria(exact_match=True, case_sensitive=False, contains=False)

        # Create and return the question
        question = BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.MULTIPLE_CHOICE if normalized_choices else AnswerType.FREE_TEXT,
            correct_answer=target_word,
            category=category,
            difficulty=difficulty,
            tags=tags,
            choices=normalized_choices,
            evaluation_criteria=eval_criteria,
        )

        # Add schema for structured response
        question.schema = {
            "type": "object",
            "properties": {"translation": {"type": "string"}},
            "required": ["translation"],
        }

        return question

    def _release_category_key(self, pos_type: str, pos_subtype: str) -> str:
        return f"{pos_type}:{pos_subtype}"

    def _load_release_entries(self) -> Dict[str, List[Dict[str, str]]]:
        """Load release entries grouped by category for supported POS classes."""
        categories: Dict[str, List[Dict[str, str]]] = {}

        for pos_type in _SUPPORTED_POS_TYPES:
            pos_dir = _RELEASE_LEMMAS_DIR / pos_type
            if not pos_dir.exists():
                continue

            for jsonl_file in pos_dir.glob("*/base.jsonl"):
                pos_subtype = jsonl_file.parent.name
                category_key = self._release_category_key(pos_type, pos_subtype)
                entries: List[Dict[str, str]] = []

                with jsonl_file.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue

                        entry = json.loads(line)
                        translations = entry.get("translations") or {}
                        origin_word = (translations.get(self.origin_lang) or "").strip()
                        target_word = (translations.get(self.target_lang) or "").strip()

                        if not origin_word or not target_word:
                            continue

                        entries.append(
                            {
                                "origin_word": origin_word,
                                "target_word": target_word,
                                "category": category_key,
                            }
                        )

                if len(entries) >= _MIN_CATEGORY_SIZE:
                    categories[category_key] = entries

        return categories

    def _build_choices(
        self,
        target_word: str,
        category_entries: List[Dict[str, str]],
    ) -> List[str]:
        """Build translation options with same-category distractors."""
        distractors = list(
            {
                entry["target_word"]
                for entry in category_entries
                if entry["target_word"] != target_word
            }
        )
        if len(distractors) < _DISTRACTOR_COUNT:
            return []

        selected = random.sample(distractors, _DISTRACTOR_COUNT)
        selected.append(target_word)
        random.shuffle(selected)
        return selected

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """Generate translation questions from data/release lemma JSONL files."""
        categories = self._load_release_entries()
        if not categories:
            logger.warning(
                "No release categories found for %s -> %s",
                self.origin_lang,
                self.target_lang,
            )
            return

        logger.info(
            "Loaded %d release categories for %s -> %s",
            len(categories),
            self.origin_lang,
            self.target_lang,
        )

        category_keys = list(categories.keys())
        random.shuffle(category_keys)

        for category_key in category_keys:
            entries = categories[category_key]
            random.shuffle(entries)

            for entry in entries:
                choices = self._build_choices(entry["target_word"], entries)
                if not choices:
                    continue
                yield self._create_question(
                    origin_word=entry["origin_word"],
                    target_word=entry["target_word"],
                    category=category_key,
                    choices=choices,
                )

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
                "No valid translations found for %s to %s",
                self.origin_lang,
                self.target_lang,
            )
            return

        # Shuffle entries to get different questions each time
        random.shuffle(valid_entries)

        # Generate and yield questions
        for entry in valid_entries:
            origin_word = self.get_translation(entry, self.origin_lang)
            target_word = self.get_translation(entry, self.target_lang)

            # Create and yield question
            yield self._create_question(
                origin_word=origin_word,
                target_word=target_word,
                category=f"translation_{self.origin_lang}_{self.target_lang}",
            )

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
                yield self._create_question(
                    origin_word=origin_word,
                    target_word=target_word,
                    category=f"translation_{self.origin_lang}_{self.target_lang}",
                )

            except Exception as e:
                logger.error("Error generating translation with LLM: %s", e)
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

                logger.info("Generated benchmark data for %s to %s", origin_lang, target_lang)

            except Exception as e:
                logger.error(
                    "Error generating benchmark for %s to %s: %s",
                    origin_lang,
                    target_lang,
                    e,
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

                logger.info("Generated benchmark data for %s to %s", origin_lang, target_lang)

            except Exception as e:
                logger.error(
                    "Error generating benchmark for %s to %s: %s",
                    origin_lang,
                    target_lang,
                    e,
                )


if __name__ == "__main__":
    # When run directly, generate data for all language pairs
    LanguagePairGenerator.generate_specific_pairs([("en", "fr"), ("en", "zh"), ("sw", "ko")])
