#!/usr/bin/python3

"""Generator for the word-to-IPA benchmark."""

import logging
import random
from typing import Any, Dict, Iterator

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0061_english_to_ipa",
    name="Word to IPA Pronunciation",
    description="A benchmark to evaluate a model's ability to convert words from multiple languages to IPA pronunciation.",
)


def _format_question_text(item: Dict[str, Any]) -> str:
    """Format a consistent, parseable question text payload."""
    language_name = item.get("language_name", "English")
    language_code = item.get("language_code", "en").lower()
    word = item["word"]

    lines = [
        "Generate the IPA pronunciation for this word:",
        f"Language: {language_name} ({language_code})",
        f"Word: {word}",
    ]

    definition = item.get("definition", "").strip()
    sentence = item.get("sentence", "").strip()

    if definition:
        lines.append(f"Definition: {definition}")
    if sentence:
        lines.append(f"Sentence: {sentence}")

    lines.append("Respond with only the IPA transcription.")
    return "\n".join(lines)


@generator("0061_english_to_ipa")
class EnglishToIPAGenerator(BenchmarkGenerator):
    """Generator for word-to-IPA benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        self.can_load_from_file = True
        self.can_generate_with_llm = True
        self.can_generate_locally = False

        self.questions_file_path = "words_ipa_multilingual.json"

        self.context = """You are a helpful assistant creating benchmark questions to test language models'
ability to convert words from many languages to IPA (International Phonetic Alphabet) pronunciation.
Include language and optionally sentence/definition context when needed for disambiguation."""

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """Generate questions from predefined JSON file."""
        if not self.can_load_from_file or not self.questions_file_path:
            return

        try:
            words_data = self.load_json_file(self.questions_file_path)

            for item in words_data:
                language_code = item.get("language_code", "en").lower()
                language_name = item.get("language_name", language_code)
                question_text = _format_question_text(item)

                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.FREE_TEXT,
                    correct_answer=item["ipa"],
                    category=f"{language_name} Pronunciation",
                    difficulty=Difficulty(item.get("difficulty", "medium")),
                    tags=["ipa", "pronunciation", language_code],
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=False,
                        contains=False,
                        case_sensitive=True,
                    ),
                )

                if "alternatives" in item and item["alternatives"]:
                    question.evaluation_criteria.alternatives = item["alternatives"]

                yield question

        except Exception as error:
            logger.error("Error generating questions from file: %s", error)

    def _generate_with_llm(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """Generate questions using a language model."""
        if not self.can_generate_with_llm:
            return

        schema = {
            "type": "object",
            "properties": {
                "language_name": {"type": "string", "description": "Name of the language"},
                "language_code": {"type": "string", "description": "ISO-639 language code"},
                "word": {"type": "string", "description": "The word to pronounce"},
                "definition": {
                    "type": "string",
                    "description": "Short meaning note for disambiguation (optional)",
                },
                "sentence": {
                    "type": "string",
                    "description": "Sentence context only if disambiguation is needed",
                },
                "ipa": {
                    "type": "string",
                    "description": "IPA pronunciation for the given language",
                },
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternative valid IPA pronunciations",
                },
            },
            "required": ["language_name", "language_code", "word", "ipa"],
        }

        language_groups = [
            "Germanic languages (English, German, Dutch, Swedish)",
            "Romance languages (Spanish, French, Italian, Portuguese)",
            "Slavic languages (Russian, Polish, Czech)",
            "Semitic languages (Arabic, Hebrew)",
            "Indic languages (Hindi, Bengali)",
            "East Asian languages (Japanese, Korean, Mandarin)",
        ]

        batch_size = 5
        difficulty_levels = ["easy", "medium", "hard"]

        for difficulty in difficulty_levels:
            categories = random.sample(language_groups, 2)
            category_desc = "\n".join([f"- {cat}" for cat in categories])

            prompt = f"""
Create {batch_size} multilingual word-to-IPA benchmark items.

Focus on {difficulty} words from these language groups:
{category_desc}

For each item include:
1. language_name
2. language_code
3. word
4. ipa
5. optional definition or sentence ONLY when context is needed for pronunciation disambiguation
6. optional alternative IPA variants

Prefer straightforward examples; avoid deliberately ambiguous homographs unless context clearly resolves them.
"""

            try:
                response = self.get_llm_question(prompt=prompt, schema={"type": "array", "items": schema})

                if isinstance(response, list):
                    for item in response:
                        try:
                            language_code = item.get("language_code", "xx").lower()
                            language_name = item.get("language_name", language_code)
                            question_text = _format_question_text(item)

                            question = BenchmarkQuestion(
                                question_text=question_text,
                                answer_type=AnswerType.FREE_TEXT,
                                correct_answer=item["ipa"],
                                category=f"{language_name} Pronunciation",
                                difficulty=Difficulty(item.get("difficulty", difficulty)),
                                tags=["ipa", "pronunciation", language_code, "llm_generated"],
                                evaluation_criteria=EvaluationCriteria(
                                    exact_match=False,
                                    contains=False,
                                    case_sensitive=True,
                                ),
                            )

                            alternatives = item.get("alternatives", [])
                            if alternatives:
                                question.evaluation_criteria.alternatives = alternatives

                            yield question

                        except Exception as error:
                            logger.error("Error processing LLM-generated question: %s", error)
                            continue

            except Exception as error:
                logger.error("Error generating questions with LLM: %s", error)
