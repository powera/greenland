#!/usr/bin/python3

"""Generator for Bebras bulk IPA/phonetic verification benchmark."""

from typing import Any, Dict, Iterator, List, TypeAlias

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)

BENCHMARK_CODE = "0141_validate_pronunciation_bulk"
EntryDict: TypeAlias = Dict[str, Any]
EntryList: TypeAlias = List[EntryDict]
EntryIdMap: TypeAlias = Dict[str, str]
EntryByIdMap: TypeAlias = Dict[str, EntryDict]
ShortEntriesBundle: TypeAlias = tuple[EntryList, EntryIdMap, EntryByIdMap]
WrongEntryResult: TypeAlias = List[Dict[str, str]]


class ValidatePronunciationBulkGenerator(BenchmarkGenerator):
    """Generate batch pronunciation QA questions from curated sample lists."""

    def __init__(self, metadata: BenchmarkMetadata, session: Any = None) -> None:
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

    def _load_base_entries(self) -> EntryList:
        """Load canonical correct pronunciation entries used for all cases."""
        samples_data = self.load_json_file("samples.json")
        if isinstance(samples_data, dict):
            entries = samples_data.get("entries", [])
            if isinstance(entries, list):
                return [entry for entry in entries if isinstance(entry, dict)]
            return []
        if isinstance(samples_data, list):
            if all(isinstance(entry, dict) and "word" in entry for entry in samples_data):
                return [entry for entry in samples_data if isinstance(entry, dict)]
            if samples_data and isinstance(samples_data[0], dict):
                legacy_entries = samples_data[0].get("entries", [])
                if isinstance(legacy_entries, list):
                    return [entry for entry in legacy_entries if isinstance(entry, dict)]
        return []

    def _build_short_entries(self, sample_index: int, entries: EntryList) -> ShortEntriesBundle:
        """Build short-id input entries and source-id maps for a generated case."""
        short_entries: EntryList = []
        original_to_short_id_map: EntryIdMap = {}
        source_entries_by_original_id: EntryByIdMap = {}

        for entry_index, entry in enumerate(entries, start=1):
            original_entry_id = str(entry.get("entry_id", f"item_{entry_index:02d}"))
            short_entry_id = f"C{sample_index}_{entry_index:03d}"
            original_to_short_id_map[original_entry_id] = short_entry_id

            short_entry: EntryDict = dict(entry)
            short_entry["entry_id"] = short_entry_id
            short_entries.append(short_entry)
            source_entries_by_original_id[original_entry_id] = entry

        return short_entries, original_to_short_id_map, source_entries_by_original_id

    def _normalize_wrong_entries(
        self,
        wrong_entries: Any,
        field_name: str,
        replacement_key: str,
        correct_key: str,
        short_entries_by_id: EntryByIdMap,
        original_to_short_id_map: EntryIdMap,
        source_entries_by_original_id: EntryByIdMap,
    ) -> WrongEntryResult:
        """Apply wrong values to short entries and build expected answer payload."""
        normalized_entries: WrongEntryResult = []
        if not isinstance(wrong_entries, list):
            return normalized_entries

        for wrong_entry in wrong_entries:
            if not isinstance(wrong_entry, dict):
                continue

            original_entry_id = str(wrong_entry.get("entry_id", ""))
            short_entry_id = original_to_short_id_map.get(original_entry_id, original_entry_id)
            source_entry = source_entries_by_original_id.get(original_entry_id, {})
            short_entry = short_entries_by_id.get(short_entry_id)
            if short_entry is None:
                continue

            short_entry[field_name] = str(wrong_entry.get(replacement_key, ""))

            normalized_entries.append(
                {
                    "entry_id": short_entry_id,
                    "word": str(wrong_entry.get("word") or source_entry.get("word") or ""),
                    correct_key: str(
                        wrong_entry.get(correct_key) or source_entry.get(field_name) or ""
                    ),
                }
            )

        return normalized_entries

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        base_entries = self._load_base_entries()
        wrong_entries_by_case_id: Dict[str, EntryDict] = {
            str(case.get("case_id", "")): case
            for case in self.load_json_file("wrong_entries.json")
            if isinstance(case, dict)
        }

        for sample_index, case_id in enumerate(wrong_entries_by_case_id, start=1):
            wrong_case_data = wrong_entries_by_case_id.get(
                str(case_id),
                {
                    "wrong_ipa_entries": [],
                    "wrong_phonetic_entries": [],
                },
            )
            wrong_ipa_entries = wrong_case_data.get("wrong_ipa_entries", [])
            wrong_phonetic_entries = wrong_case_data.get("wrong_phonetic_entries", [])

            short_entries, original_to_short_id_map, source_entries_by_original_id = (
                self._build_short_entries(sample_index=sample_index, entries=base_entries)
            )
            short_entries_by_id = {
                str(entry.get("entry_id", "")): entry
                for entry in short_entries
                if isinstance(entry, dict)
            }
            normalized_wrong_ipa_entries = self._normalize_wrong_entries(
                wrong_entries=wrong_ipa_entries,
                field_name="ipa",
                replacement_key="wrong_ipa",
                correct_key="correct_ipa",
                short_entries_by_id=short_entries_by_id,
                original_to_short_id_map=original_to_short_id_map,
                source_entries_by_original_id=source_entries_by_original_id,
            )
            normalized_wrong_phonetic_entries = self._normalize_wrong_entries(
                wrong_entries=wrong_phonetic_entries,
                field_name="phonetic",
                replacement_key="wrong_phonetic",
                correct_key="correct_phonetic",
                short_entries_by_id=short_entries_by_id,
                original_to_short_id_map=original_to_short_id_map,
                source_entries_by_original_id=source_entries_by_original_id,
            )

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
