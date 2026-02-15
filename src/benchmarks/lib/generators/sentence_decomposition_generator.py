#!/usr/bin/python3

"""Generator for multilingual sentence decomposition benchmark questions."""

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

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0062_sentence_decomposition",
    name="Sentence Decomposition",
    description="A benchmark to evaluate a model's ability to produce multilingual token-level sentence decomposition with grammatical metadata.",
)

# Register benchmark metadata
register_benchmark_metadata(BENCHMARK_METADATA)


@generator("0062_sentence_decomposition")
class SentenceDecompositionGenerator(BenchmarkGenerator):
    """Generator for multilingual sentence decomposition benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)

        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

        self.context = """You are a multilingual linguistics expert.
Generate token-level decomposition for ONE target language per request.
Return only valid JSON matching the provided schema."""

        self._samples: Optional[List[Dict[str, Any]]] = None

    def _response_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "languages": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "language_code": {"type": "string"},
                            "translation": {"type": "string"},
                            "word_count": {"type": "integer"},
                            "words": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "position": {"type": "integer"},
                                        "role": {"type": "string"},
                                        "english_gloss": {"type": "string"},
                                        "surface_form": {"type": "string"},
                                        "grammatical_form": {"type": "string"},
                                        "lemma_guid": {"type": "string"},
                                        "lemma": {"type": "string"},
                                    },
                                    "required": [
                                        "position",
                                        "role",
                                        "english_gloss",
                                        "surface_form",
                                        "grammatical_form",
                                        "lemma_guid",
                                        "lemma",
                                    ],
                                },
                            },
                        },
                        "required": ["language_code", "translation", "word_count", "words"],
                    },
                }
            },
            "required": ["languages"],
        }

    def _format_candidate_lemmas(self, candidate_lemmas: List[Dict[str, Any]]) -> str:
        if not candidate_lemmas:
            return "- (none provided)"

        return "\n".join(
            (
                f"- {item['guid']} - {item['lemma']} ({item['disambiguation']}) | "
                f"POS: {item['pos']} | Definition: {item['definition']} | "
                f"Translations: "
                + ", ".join(
                    f"{lang}={translation}" for lang, translation in item.get("translations", {}).items()
                )
            )
            for item in candidate_lemmas
        )

    def _build_question_text(
        self,
        source_sentence: str,
        source_language: str,
        target_entry: Dict[str, Any],
        helper_entries: List[Dict[str, Any]],
        candidate_lemmas: List[Dict[str, Any]],
    ) -> str:
        helper_lines = "\n".join(
            f"- {entry['language_code']}: {entry['translation']}" for entry in helper_entries
        )
        candidate_lines = self._format_candidate_lemmas(candidate_lemmas)

        return (
            f"Create a sentence decomposition JSON for ONE language only.\n"
            f"Source sentence ({source_language}): \"{source_sentence}\"\n"
            f"Target language: {target_entry['language_code']}\n"
            f"Target translation: \"{target_entry['translation']}\"\n\n"
            "Additional translations for disambiguation (1-3 helper languages):\n"
            f"{helper_lines if helper_lines else '- (none provided)'}\n\n"
            "Candidate lemmas (must choose correct lemma_guid when a content word maps to one):\n"
            f"{candidate_lines}\n\n"
            "Grammatical form conventions (match translation prompt style):\n"
            "- Use format: <role>/<language_code>_<morphology> for inflected items.\n"
            "- Examples: verb/es_3p_present, pronoun/fr_subjective, article/es_singular_f, noun/en_singular.\n"
            "- For uninflected closed-class words, use <role>/base (example: preposition/base).\n"
            "- Keep language code aligned with the target token language.\n"
            "- word_count must equal the number of word entries.\n\n"
            "Return schema requirements:\n"
            "- Return exactly one entry in languages[] (the target language only).\n"
            "- Each words[] item must include: position, role, english_gloss, surface_form, "
            "grammatical_form, lemma_guid, lemma.\n"
            "- Use lemma_guid=NONE and lemma='No lemma' for function words without a selected candidate lemma."
        )

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        if not self.questions_file_path:
            logger.warning("No questions file path set")
            return

        try:
            if self._samples is None:
                self._samples = self.load_json_file(self.questions_file_path)

            samples = self._samples
            logger.info("Loaded %d sentence decomposition samples", len(samples))

            for sample in samples:
                source_sentence = sample["source_sentence"]
                source_language = sample.get("source_language", "en")
                translations = sample.get("translations", [])
                candidate_lemmas = sample.get("candidate_lemmas", [])

                expected_languages = sample.get("decomposition", {}).get("languages", [])
                expected_by_code = {
                    item.get("language_code", "").lower(): item
                    for item in expected_languages
                    if isinstance(item, dict) and item.get("language_code")
                }

                for target_entry in translations:
                    target_code = target_entry.get("language_code", "").lower()
                    if target_code not in expected_by_code:
                        continue

                    helper_entries = [
                        entry
                        for entry in translations
                        if entry.get("language_code", "").lower() != target_code
                    ][:3]

                    question_text = self._build_question_text(
                        source_sentence=source_sentence,
                        source_language=source_language,
                        target_entry=target_entry,
                        helper_entries=helper_entries,
                        candidate_lemmas=candidate_lemmas,
                    )

                    correct_answer = {"languages": [expected_by_code[target_code]]}

                    yield BenchmarkQuestion(
                        question_text=question_text,
                        answer_type=AnswerType.JSON,
                        correct_answer=correct_answer,
                        category="linguistics",
                        difficulty=Difficulty.HARD,
                        tags=[
                            "linguistics",
                            "sentence-decomposition",
                            "morphology",
                            f"lang:{target_code}",
                        ],
                        schema=self._response_schema(),
                        evaluation_criteria=EvaluationCriteria(
                            exact_match=False,
                            case_sensitive=False,
                            required_fields=["languages"],
                        ),
                    )

        except (FileNotFoundError, json.JSONDecodeError) as error:
            logger.error("Error loading sentence decomposition samples: %s", error)
