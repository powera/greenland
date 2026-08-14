#!/usr/bin/env python3
"""Legacy Bebras compatibility code for bulk pronunciation verification."""

import logging
from typing import Any, Dict, List, Literal, TypedDict, cast

from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig

logger = logging.getLogger(__name__)

IncorrectPronunciationAction = Literal["log", "remove", "regenerate"]


class PronunciationCheckItem(TypedDict, total=False):
    """Single pronunciation entry used by bulk IPA/phonetic validation."""

    entry_id: str
    word: str
    chinese_hint: str
    ipa: str
    phonetic: str


def build_bulk_pronunciation_verification_context() -> str:
    """Build context for bulk IPA/phonetic verification."""
    return (
        "You are a strict pronunciation QA checker.\n"
        "You receive 10-50 English words with Chinese disambiguation hints, "
        "IPA, and plain-English phonetic spellings.\n"
        "Return only entries where IPA or phonetic pronunciation is wrong.\n"
        "Also provide corrected pronunciations for wrong entries as reference data."
    )


def build_bulk_pronunciation_verification_prompt(items: List[PronunciationCheckItem]) -> str:
    """Build a compact prompt with a short preamble and a numbered list."""
    prompt_lines: List[str] = [
        "Check this list and identify pronunciation problems.",
        "A problem means incorrect IPA, incorrect phonetic spelling, "
        "or IPA/phonetic mismatch for the intended English sense.",
        "Return two arrays only: wrong_ipa_entries and wrong_phonetic_entries.",
        "For each wrong IPA entry include entry_id, word, and correct_ipa.",
        "For each wrong phonetic entry include entry_id, word, and correct_phonetic.",
        "If an entry has both problems, include it in both arrays.",
        "",
    ]
    for index, item in enumerate(items, start=1):
        entry_id = str(item.get("entry_id", f"item_{index:02d}"))
        prompt_lines.append(
            f'{index}. ID: "{entry_id}" | English: "{item["word"]}" | Chinese: "{item["chinese_hint"]}" '
            f'| IPA: "{item["ipa"]}" | Phonetic: "{item["phonetic"]}"'
        )
    return "\n".join(prompt_lines)


def build_bulk_pronunciation_verification_schema() -> Dict[str, Any]:
    """Build JSON schema for wrong IPA and wrong phonetic entries."""
    return {
        "type": "object",
        "properties": {
            "wrong_ipa_entries": {
                "type": "array",
                "description": "Only entries where IPA is wrong.",
                "items": {
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "string"},
                        "word": {"type": "string"},
                        "correct_ipa": {"type": "string"},
                    },
                    "required": ["entry_id", "word", "correct_ipa"],
                    "additionalProperties": False,
                },
            },
            "wrong_phonetic_entries": {
                "type": "array",
                "description": "Only entries where phonetic spelling is wrong.",
                "items": {
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "string"},
                        "word": {"type": "string"},
                        "correct_phonetic": {"type": "string"},
                    },
                    "required": ["entry_id", "word", "correct_phonetic"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["wrong_ipa_entries", "wrong_phonetic_entries"],
        "additionalProperties": False,
    }


class PronunciationVerificationService:
    """Bulk pronunciation verification retained with the audio subsystem."""

    def __init__(self, config: DataSourceConfig):
        """Initialize the verification agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings
        """
        self.debug = config.debug
        self.llm_client = UnifiedLLMClient.from_config(config)

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def verify_bulk_pronunciations(
        self,
        items: List[PronunciationCheckItem],
        incorrect_action: IncorrectPronunciationAction = "log",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Verify 10-50 word pronunciation entries and return only wrong words."""
        if len(items) < 10 or len(items) > 50:
            raise ValueError("Bulk pronunciation checker requires between 10 and 50 items.")

        context = build_bulk_pronunciation_verification_context()
        prompt = build_bulk_pronunciation_verification_prompt(items)
        schema = build_bulk_pronunciation_verification_schema()

        response = self.llm_client.generate_chat(
            prompt=prompt,
            context=context,
            json_schema=schema,
            timeout=90,
        )
        structured_data = response.structured_data or {}
        raw_wrong_ipa_entries = structured_data.get("wrong_ipa_entries", [])
        raw_wrong_phonetic_entries = structured_data.get("wrong_phonetic_entries", [])
        normalized_items: List[PronunciationCheckItem] = []
        for index, item in enumerate(items, start=1):
            normalized_item = dict(item)
            normalized_item["entry_id"] = str(item.get("entry_id", f"item_{index:02d}"))
            normalized_items.append(cast(PronunciationCheckItem, normalized_item))

        wrong_ipa_entries: List[Dict[str, str]] = []
        for entry in raw_wrong_ipa_entries if isinstance(raw_wrong_ipa_entries, list) else []:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("entry_id", "")).strip()
            word = str(entry.get("word", "")).strip()
            correct_ipa = str(entry.get("correct_ipa", "")).strip()
            if not entry_id or not word:
                continue
            wrong_ipa_entries.append(
                {
                    "entry_id": entry_id,
                    "word": word,
                    "correct_ipa": correct_ipa,
                }
            )

        wrong_phonetic_entries: List[Dict[str, str]] = []
        for entry in (
            raw_wrong_phonetic_entries if isinstance(raw_wrong_phonetic_entries, list) else []
        ):
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("entry_id", "")).strip()
            word = str(entry.get("word", "")).strip()
            correct_phonetic = str(entry.get("correct_phonetic", "")).strip()
            if not entry_id or not word:
                continue
            wrong_phonetic_entries.append(
                {
                    "entry_id": entry_id,
                    "word": word,
                    "correct_phonetic": correct_phonetic,
                }
            )

        wrong_id_set = {entry["entry_id"] for entry in wrong_ipa_entries + wrong_phonetic_entries}
        wrong_word_set = {entry["word"] for entry in wrong_ipa_entries + wrong_phonetic_entries}
        wrong_items = [item for item in normalized_items if item["entry_id"] in wrong_id_set]

        self._hook_log_correct_pronunciation_verifications(normalized_items, wrong_word_set)
        action_summary = self._handle_incorrect_pronunciation_words(
            wrong_items=wrong_items,
            action=incorrect_action,
            dry_run=dry_run,
        )

        return {
            "wrong_ipa_entries": wrong_ipa_entries,
            "wrong_phonetic_entries": wrong_phonetic_entries,
            "wrong_words": sorted(wrong_word_set),
            "checked_count": len(normalized_items),
            "wrong_count": len(wrong_id_set),
            "incorrect_action": incorrect_action,
            "action_summary": action_summary,
        }

    def _hook_log_correct_pronunciation_verifications(
        self, items: List[PronunciationCheckItem], wrong_word_set: set[str]
    ) -> None:
        """Hook for future metadata logging of correct pronunciation validations."""
        correct_count = sum(1 for item in items if item["word"] not in wrong_word_set)
        logger.debug(
            "Pronunciation verification hook: %s correct words (metadata logging not enabled yet).",
            correct_count,
        )

    def _handle_incorrect_pronunciation_words(
        self,
        wrong_items: List[PronunciationCheckItem],
        action: IncorrectPronunciationAction,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Handle incorrect words via log/remove/regenerate strategy hooks."""
        if action == "log":
            logger.info("Pronunciation issues found: %s words", len(wrong_items))
            return {"action": "log", "affected_count": len(wrong_items), "executed": True}
        if action == "remove":
            logger.info(
                "Pronunciation remove hook requested for %s words (dry_run=%s).",
                len(wrong_items),
                dry_run,
            )
            return {
                "action": "remove",
                "affected_count": len(wrong_items),
                "executed": False,
                "hook_only": True,
            }
        logger.info(
            "Pronunciation regenerate hook requested for %s words (dry_run=%s).",
            len(wrong_items),
            dry_run,
        )
        return {
            "action": "regenerate",
            "affected_count": len(wrong_items),
            "executed": False,
            "hook_only": True,
        }


VerificationAgent = PronunciationVerificationService
