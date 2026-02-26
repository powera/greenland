#!/usr/bin/python3

"""Generator for plural noun benchmark questions."""

import logging
import random
from typing import Any, Dict, Iterator, List, Optional

from benchmarks.lib.utils.base import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import benchmark, generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

benchmark(
    "0033_plural",
    "English Plural Generation",
    "Tests ability to produce the correct plural form of English nouns, "
    "including regular, irregular, invariant, and Latin/Greek forms.",
    category="word processing",
)(__name__)

# Rules for LLM-based generation
PLURAL_RULES = [
    "regular (add -s)",
    "words ending in -ch, -sh, -s, -x, -z (add -es)",
    "words ending in consonant + y (change to -ies)",
    "words ending in -f or -fe (change to -ves)",
    "irregular plurals (man/men, child/children, tooth/teeth, foot/feet, mouse/mice)",
    "invariant nouns (same singular and plural, e.g. sheep, deer, fish)",
    "Latin/Greek plurals (e.g. cactus/cacti, criterion/criteria, phenomenon/phenomena)",
]

# Difficulty map by rule
_RULE_DIFFICULTY: Dict[str, Difficulty] = {
    "regular": Difficulty.EASY,
    "-es": Difficulty.EASY,
    "-ies": Difficulty.MEDIUM,
    "-ves": Difficulty.MEDIUM,
    "irregular": Difficulty.HARD,
    "invariant": Difficulty.HARD,
    "latin": Difficulty.HARD,
}


@generator("0033_plural")
class PluralGenerator(BenchmarkGenerator):
    """Generator for plural noun benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Any = None) -> None:
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = True

        self.questions_file_path = "samples.json"

        self.context = (
            "You are a linguistics expert creating benchmark questions about English noun plurals. "
            "Your task is to provide clear singular/plural pairs that test knowledge of English "
            "pluralization rules, including regular, irregular, invariant, and Latin/Greek forms."
        )

        self._samples: Optional[List[Dict[str, Any]]] = None

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """Generate questions from the samples file."""
        if not self.questions_file_path:
            logger.warning("No questions file path set")
            return

        try:
            if self._samples is None:
                self._samples = self.load_json_file(self.questions_file_path)

            samples = self._samples
            logger.info("Loaded %d plural samples from file", len(samples))

            for sample in samples:
                singular = sample["singular"]
                plural = sample["plural"]
                rule = sample.get("rule", "regular")
                difficulty = _RULE_DIFFICULTY.get(rule, Difficulty.MEDIUM)

                question_text = f"What is the plural form of the noun '{singular}'?"

                schema = {
                    "type": "object",
                    "properties": {
                        "plural": {
                            "type": "string",
                            "description": "The plural form of the noun",
                        }
                    },
                    "required": ["plural"],
                }

                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.JSON,
                    correct_answer={"plural": plural},
                    category="pluralization",
                    difficulty=difficulty,
                    tags=["pluralization", "morphology", rule],
                    schema=schema,
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=True,
                        case_sensitive=False,
                        required_fields=["plural"],
                    ),
                )

                yield question

        except (FileNotFoundError, ValueError) as e:
            logger.error("Error loading plural samples: %s", str(e))

    def _generate_with_llm(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """Generate questions using a language model."""
        schema = {
            "type": "object",
            "properties": {
                "singular": {
                    "type": "string",
                    "description": "A singular English noun",
                },
                "plural": {
                    "type": "string",
                    "description": "The correct plural form of the noun",
                },
                "rule": {
                    "type": "string",
                    "description": "The pluralization rule that applies",
                },
            },
            "required": ["singular", "plural", "rule"],
        }

        response_schema = {
            "type": "object",
            "properties": {
                "plural": {
                    "type": "string",
                    "description": "The plural form of the noun",
                }
            },
            "required": ["plural"],
        }

        while True:
            rule = random.choice(PLURAL_RULES)

            prompt = (
                f"Create one example of an English noun that uses the pluralization rule: {rule}. "
                "Provide the singular noun and its correct plural form. "
                "Choose a clear, unambiguous example that has exactly one accepted plural."
            )

            try:
                pair_data = self.get_llm_question(prompt, schema=schema)

                singular = pair_data["singular"]
                plural = pair_data["plural"]
                rule_label = pair_data.get("rule", rule)

                question_text = f"What is the plural form of the noun '{singular}'?"

                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.JSON,
                    correct_answer={"plural": plural},
                    category="pluralization",
                    difficulty=Difficulty.MEDIUM,
                    tags=["pluralization", "morphology"],
                    schema=response_schema,
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=True,
                        case_sensitive=False,
                        required_fields=["plural"],
                    ),
                )

                yield question

            except Exception as e:
                logger.error("Error generating plural question with LLM: %s", str(e))
