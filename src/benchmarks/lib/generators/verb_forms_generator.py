#!/usr/bin/python3

"""Generator for multilingual verb-form production benchmark."""

import json
import logging
from typing import Any, Dict, Iterator, List, Optional

from benchmarks.lib.utils.base import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import generator, register_benchmark_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BENCHMARK_METADATA = BenchmarkMetadata(
    code="0121_verb_forms",
    name="Verb Forms",
    description="Generate full person/tense verb forms across multiple languages.",
)

register_benchmark_metadata(BENCHMARK_METADATA)

PERSON_SLOTS = ["1s", "2s", "3s", "1p", "2p", "3p"]


@generator("0121_verb_forms")
class VerbFormsGenerator(BenchmarkGenerator):
    """Generator for multilingual verb-form production questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)

        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"
        self._samples: Optional[List[Dict[str, Any]]] = None

    def _response_schema(self, required_extra_forms: List[str]) -> Dict[str, Any]:
        extra_form_properties = {key: {"type": "string"} for key in required_extra_forms}

        person_map_schema = {
            "type": "object",
            "properties": {slot: {"type": "string"} for slot in PERSON_SLOTS},
            "required": PERSON_SLOTS,
        }

        return {
            "type": "object",
            "properties": {
                "language_code": {"type": "string"},
                "lemma": {"type": "string"},
                "forms": {
                    "type": "object",
                    "properties": {
                        "present": person_map_schema,
                        "past": person_map_schema,
                        "future": person_map_schema,
                    },
                    "required": ["present", "past", "future"],
                },
                "extra_forms": {
                    "type": "object",
                    "properties": extra_form_properties,
                    "required": required_extra_forms,
                },
            },
            "required": ["language_code", "lemma", "forms", "extra_forms"],
        }

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        try:
            if self._samples is None:
                self._samples = self.load_json_file(self.questions_file_path)

            for sample in self._samples:
                prompt_lines = self.load_text_file(sample["prompt_file"])
                prompt_prefix = "\n".join(prompt_lines)
                required_extra_forms = sample.get("required_extra_forms", [])

                question_text = (
                    f"{prompt_prefix}\n\n"
                    f"Language code: {sample['language_code']} ({sample['language_name']})\n"
                    f"Verb guid (from data/release): {sample['verb_guid']}\n"
                    f"English lemma: {sample['english_lemma']}\n"
                    f"Target infinitive: {sample['target_infinitive']}\n"
                    f"Irregular core verb: {sample['is_irregular']}\n"
                    f"Required extra forms: {', '.join(required_extra_forms)}\n"
                )

                correct_answer = {
                    "language_code": sample["language_code"],
                    "lemma": sample["target_infinitive"],
                    "required_extra_forms": required_extra_forms,
                }

                yield BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.JSON,
                    correct_answer=correct_answer,
                    category="morphology",
                    difficulty=Difficulty.HARD,
                    tags=[
                        "morphology",
                        "verb-forms",
                        f"lang:{sample['language_code']}",
                        f"verb:{sample['english_lemma']}",
                    ],
                    schema=self._response_schema(required_extra_forms),
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=False,
                        case_sensitive=False,
                        required_fields=["language_code", "lemma", "forms", "extra_forms"],
                    ),
                )

        except (FileNotFoundError, json.JSONDecodeError) as error:
            logger.error("Error loading verb form samples: %s", error)
