#!/usr/bin/python3

"""Generator for Bebras bulk IPA/phonetic verification benchmark."""

from typing import Any, Dict, Iterator, List

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)

BENCHMARK_CODE = "0141_validate_pronunciation_bulk"


class ValidatePronunciationBulkGenerator(BenchmarkGenerator):
    """Generate batch pronunciation QA questions from curated sample lists."""

    def __init__(self, metadata: BenchmarkMetadata, session: Any = None) -> None:
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        samples: List[Dict[str, Any]] = self.load_json_file("samples.json")

        for sample_index, sample in enumerate(samples, start=1):
            case_id = sample["case_id"]
            entries = sample["entries"]
            wrong_ipa_entries = sample.get("wrong_ipa_entries", [])
            wrong_phonetic_entries = sample.get("wrong_phonetic_entries", [])
            legacy_wrong_entries = sample.get("wrong_entries", [])

            short_entries: List[Dict[str, Any]] = []
            id_map: Dict[str, str] = {}
            for entry_index, entry in enumerate(entries, start=1):
                original_entry_id = str(entry.get("entry_id", f"item_{entry_index:02d}"))
                short_entry_id = f"C{sample_index}_{entry_index:03d}"
                id_map[original_entry_id] = short_entry_id

                short_entry = dict(entry)
                short_entry["entry_id"] = short_entry_id
                short_entries.append(short_entry)

            if legacy_wrong_entries and not (wrong_ipa_entries or wrong_phonetic_entries):
                wrong_ipa_entries = []
                wrong_phonetic_entries = []
                for wrong_entry in legacy_wrong_entries:
                    if not isinstance(wrong_entry, dict):
                        continue
                    original_entry_id = str(wrong_entry.get("entry_id", ""))
                    short_entry_id = id_map.get(original_entry_id, original_entry_id)
                    issue_type = str(wrong_entry.get("issue_type", "")).strip().lower()

                    normalized_ipa_entry = {
                        "entry_id": short_entry_id,
                        "word": wrong_entry.get("word", ""),
                        "correct_ipa": str(wrong_entry.get("correct_ipa", "")),
                    }
                    normalized_phonetic_entry = {
                        "entry_id": short_entry_id,
                        "word": wrong_entry.get("word", ""),
                        "correct_phonetic": str(wrong_entry.get("correct_phonetic", "")),
                    }

                    if issue_type in {"ipa", "both"}:
                        wrong_ipa_entries.append(normalized_ipa_entry)
                    if issue_type in {"phonetic", "both"}:
                        wrong_phonetic_entries.append(normalized_phonetic_entry)

            normalized_wrong_ipa_entries = [
                {
                    "entry_id": id_map.get(
                        str(entry.get("entry_id", "")), str(entry.get("entry_id", ""))
                    ),
                    "word": entry.get("word", ""),
                    "correct_ipa": str(entry.get("correct_ipa", "")),
                }
                for entry in wrong_ipa_entries
                if isinstance(entry, dict)
            ]
            normalized_wrong_phonetic_entries = [
                {
                    "entry_id": id_map.get(
                        str(entry.get("entry_id", "")), str(entry.get("entry_id", ""))
                    ),
                    "word": entry.get("word", ""),
                    "correct_phonetic": str(entry.get("correct_phonetic", "")),
                }
                for entry in wrong_phonetic_entries
                if isinstance(entry, dict)
            ]

            wrong_word_count = len(
                {
                    str(entry.get("entry_id", ""))
                    for entry in normalized_wrong_ipa_entries + normalized_wrong_phonetic_entries
                }
            )
            difficulty = (
                Difficulty.EASY
                if not (normalized_wrong_ipa_entries or normalized_wrong_phonetic_entries)
                else Difficulty.MEDIUM
            )
            if wrong_word_count >= 4:
                difficulty = Difficulty.HARD

            yield BenchmarkQuestion(
                question_text=f"Bulk pronunciation QA case: {case_id}",
                answer_type=AnswerType.JSON,
                correct_answer={
                    "inputs": {"entries": short_entries},
                    "expected": {
                        "wrong_ipa_entries": normalized_wrong_ipa_entries,
                        "wrong_phonetic_entries": normalized_wrong_phonetic_entries,
                    },
                },
                category="agent_regression_pronunciation",
                difficulty=difficulty,
                tags=[
                    "agent_benchmark",
                    "bebras",
                    "pronunciation",
                    "ipa",
                    f"case:{case_id}",
                ],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True,
                    case_sensitive=False,
                    required_fields=["wrong_ipa_entries", "wrong_phonetic_entries"],
                ),
            )
