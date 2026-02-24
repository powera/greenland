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
from langtools.verb_forms import get_language_verb_forms_config
from storage.backend.config import DataSourceConfig
from words import build_verb_forms_prompt

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_METADATA = BenchmarkMetadata(
    code="0121_verb_forms",
    name="Verb Forms",
    description="Generate full person/tense verb forms across multiple languages.",
    default_num_questions=56,
    category="word processing",
)

register_benchmark_metadata(BENCHMARK_METADATA)


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

    def _response_schema(
        self, language_code: str, required_extra_forms: List[str]
    ) -> Dict[str, Any]:
        language_config = get_language_verb_forms_config(language_code)
        person_slots = language_config.get("person_slots", [])
        core_slots = language_config.get("core_slots", [])

        extra_form_properties = {key: {"type": "string"} for key in required_extra_forms}

        form_properties: Dict[str, Any] = {}
        required_form_keys: List[str] = []

        for slot in core_slots:
            key = slot.get("key") if isinstance(slot, dict) else None
            kind = slot.get("kind") if isinstance(slot, dict) else None
            if not isinstance(key, str) or not key:
                continue

            required_form_keys.append(key)
            if kind == "person_map":
                form_properties[key] = {
                    "type": "object",
                    "properties": {person: {"type": "string"} for person in person_slots},
                    "required": person_slots,
                }
            else:
                form_properties[key] = {"type": "string"}

        if not required_form_keys:
            required_form_keys = ["present", "past", "future"]
            form_properties = {
                tense: {"type": "object", "properties": {}, "required": []}
                for tense in required_form_keys
            }

        return {
            "type": "object",
            "properties": {
                "language_code": {"type": "string"},
                "lemma": {"type": "string"},
                "forms": {
                    "type": "object",
                    "properties": form_properties,
                    "required": required_form_keys,
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
                language_code = sample["language_code"]
                required_extra_forms = sample.get("required_extra_forms", [])
                benchmark_config = kwargs.get("config")
                if benchmark_config is None:
                    benchmark_config = DataSourceConfig()

                language_layout = get_language_verb_forms_config(language_code)

                prompt_prefix = build_verb_forms_prompt(
                    language_code,
                    sample["target_infinitive"],
                    benchmark_config,
                )

                core_slot_summary = ", ".join(
                    slot.get("key", "")
                    for slot in language_layout.get("core_slots", [])
                    if isinstance(slot, dict)
                )
                person_slot_summary = ", ".join(language_layout.get("person_slots", []))
                if not person_slot_summary:
                    person_slot_summary = "(not person-indexed for this language)"

                question_text = (
                    f"{prompt_prefix}\n\n"
                    f"Language code: {sample['language_code']} ({sample['language_name']})\n"
                    f"Verb guid (from data/release): {sample['verb_guid']}\n"
                    f"English lemma: {sample['english_lemma']}\n"
                    f"Target infinitive: {sample['target_infinitive']}\n"
                    f"Irregular core verb: {sample['is_irregular']}\n"
                    f"Required core form slots: {core_slot_summary}\n"
                    f"Person slots (for person-mapped forms): {person_slot_summary}\n"
                    f"Required extra forms: {', '.join(required_extra_forms)}\n"
                )

                correct_answer = {
                    "language_code": sample["language_code"],
                    "lemma": sample["target_infinitive"],
                    "required_extra_forms": required_extra_forms,
                    "forms": sample.get("forms", {}),
                    "extra_forms": sample.get("extra_forms", {}),
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
                    schema=self._response_schema(language_code, required_extra_forms),
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=False,
                        case_sensitive=False,
                        required_fields=["language_code", "lemma", "forms", "extra_forms"],
                    ),
                )

        except (FileNotFoundError, json.JSONDecodeError) as error:
            logger.error("Error loading verb form samples: %s", error)
