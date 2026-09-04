"""Standalone verification for sentence translations and lemma links."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

from sqlalchemy.orm import Session

import constants
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.models.schema import Sentence, SentenceTranslation, SentenceWord
from storage.translation_helpers import get_translation
from verification.common import (
    DEFAULT_VERIFY_LANGUAGES,
    filter_languages_for_model,
    get_dialect_display_name,
    parse_verdict,
)

VerificationVerdict = Literal["correct", "incorrect"]


class SentenceTranslationVerdict(TypedDict):
    """Meaning and grammar verdicts for one language version."""

    translation: str
    meaning_correct: VerificationVerdict
    grammar_correct: VerificationVerdict


class SentenceTranslationVerificationResult(TypedDict):
    """Result of checking requested language versions of one sentence."""

    sentence_id: int
    english_text: str
    results: Dict[str, SentenceTranslationVerdict]
    success: Literal[True]


class SentenceLinkVerdict(TypedDict):
    """Sense and surface-form verdicts for one linked lemma."""

    lemma_guid: Optional[str]
    sense_correct: VerificationVerdict
    form_matches: VerificationVerdict


class SentenceLinkVerificationResult(TypedDict):
    """Read-only verification report for one sentence's lemma links."""

    sentence_id: int
    english_text: str
    results: Dict[str, Dict[str, SentenceLinkVerdict]]
    success: Literal[True]


def _get_sentence_or_raise(session: Session, sentence_id: int) -> Sentence:
    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise ValueError(f"Sentence {sentence_id} not found")
    return sentence


def _get_english_text(session: Session, sentence_id: int) -> str:
    english_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .one_or_none()
    )
    if english_translation is None:
        raise ValueError(f"Sentence {sentence_id} has no English translation")
    return str(english_translation.translation_text)


def _supported_languages(config: DataSourceConfig, languages: Optional[List[str]]) -> List[str]:
    model = config.model or constants.DEFAULT_MODEL
    supported_languages = filter_languages_for_model(languages or DEFAULT_VERIFY_LANGUAGES, model)
    if not supported_languages:
        raise ValueError(f"No supported verification languages for model {model}")
    return supported_languages


def build_sentence_translation_verification_prompt(
    english_text: str, translations: Dict[str, str]
) -> str:
    """Build the LLM prompt for sentence-level meaning and grammar checks."""
    translation_sections = [
        (
            f"=== {get_dialect_display_name(language_code)} ({language_code}) ===\n"
            f'Translation: "{translation_text}"'
        )
        for language_code, translation_text in translations.items()
    ]
    return "\n\n".join(
        [
            "Verify each sentence translation for meaning and grammar.",
            f'English sentence: "{english_text}"',
            *translation_sections,
            (
                'For each language, return only "correct" or "incorrect" for '
                "both meaning and grammar. Consider the indicated dialect."
            ),
        ]
    )


def build_sentence_translation_verification_schema(language_codes: List[str]) -> Schema:
    """Build the structured response schema for sentence translations."""
    properties: Dict[str, SchemaProperty] = {}
    for language_code in language_codes:
        dialect_name = get_dialect_display_name(language_code)
        properties[f"{language_code}_meaning"] = SchemaProperty(
            type="string",
            description=f"{dialect_name} meaning verdict",
            enum=["correct", "incorrect"],
        )
        properties[f"{language_code}_grammar"] = SchemaProperty(
            type="string",
            description=f"{dialect_name} grammar verdict",
            enum=["correct", "incorrect"],
        )
    return Schema(
        name="SentenceTranslationVerification",
        description="Meaning and grammar verdicts for sentence translations",
        properties=properties,
    )


def verify_sentence_translations(
    session: Session,
    sentence_id: int,
    config: DataSourceConfig,
    languages: Optional[List[str]] = None,
    *,
    persist: bool = True,
    llm_client: Optional[UnifiedLLMClient] = None,
) -> SentenceTranslationVerificationResult:
    """Verify sentence translations and update their flags without committing."""
    _get_sentence_or_raise(session, sentence_id)
    english_text = _get_english_text(session, sentence_id)
    supported_languages = _supported_languages(config, languages)

    translations: Dict[str, str] = {}
    translation_rows: Dict[str, SentenceTranslation] = {}
    for language_code in supported_languages:
        translation_row = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code=language_code)
            .one_or_none()
        )
        if translation_row is None or not translation_row.translation_text.strip():
            continue
        translations[language_code] = translation_row.translation_text
        translation_rows[language_code] = translation_row
    if not translations:
        raise ValueError("No sentence translations found for requested languages")

    client = llm_client or UnifiedLLMClient.from_config(config)
    response = client.generate_chat(
        prompt=build_sentence_translation_verification_prompt(english_text, translations),
        json_schema=build_sentence_translation_verification_schema(list(translations)),
        timeout=90,
    )
    if not response.structured_data:
        raise RuntimeError("LLM did not return structured sentence verification data")

    results: Dict[str, SentenceTranslationVerdict] = {}
    for language_code in translations:
        meaning_verdict = parse_verdict(response.structured_data.get(f"{language_code}_meaning"))
        grammar_verdict = parse_verdict(response.structured_data.get(f"{language_code}_grammar"))
        results[language_code] = {
            "translation": translations[language_code],
            "meaning_correct": meaning_verdict,
            "grammar_correct": grammar_verdict,
        }
        if persist:
            translation_rows[language_code].verified = (
                meaning_verdict == "correct" and grammar_verdict == "correct"
            )
    if persist:
        session.flush()

    return {
        "sentence_id": sentence_id,
        "english_text": english_text,
        "results": results,
        "success": True,
    }


def _link_field(language_code: str, sentence_word_id: int, check_name: str) -> str:
    return f"{language_code}_link_{sentence_word_id}_{check_name}"


def _get_links(
    session: Session, sentence_id: int, language_codes: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    links_by_language: Dict[str, List[Dict[str, Any]]] = {}
    for language_code in language_codes:
        sentence_words = (
            session.query(SentenceWord)
            .filter_by(sentence_id=sentence_id, language_code=language_code)
            .filter(SentenceWord.lemma_id.isnot(None))
            .order_by(SentenceWord.position)
            .all()
        )
        link_rows: List[Dict[str, Any]] = []
        for sentence_word in sentence_words:
            if sentence_word.lemma is None:
                continue
            link_rows.append(
                {
                    "sentence_word_id": sentence_word.id,
                    "position": sentence_word.position,
                    "english_text": sentence_word.english_text,
                    "target_text": sentence_word.target_language_text,
                    "declined_form": sentence_word.declined_form,
                    "part_of_speech": sentence_word.part_of_speech,
                    "lemma_guid": sentence_word.lemma.guid,
                    "expected_translation": get_translation(
                        session, sentence_word.lemma, language_code
                    ),
                }
            )
        if link_rows:
            links_by_language[language_code] = link_rows
    return links_by_language


def build_sentence_link_verification_prompt(
    english_text: str,
    translations: Dict[str, str],
    links_by_language: Dict[str, List[Dict[str, Any]]],
) -> str:
    """Build the prompt for verifying stored sentence-to-lemma links."""
    prompt_lines = [
        "Verify each stored sentence-word to lemma link.",
        f'English sentence: "{english_text}"',
    ]
    for language_code, link_rows in links_by_language.items():
        prompt_lines.extend(
            [
                "",
                f"=== {get_dialect_display_name(language_code)} ({language_code}) ===",
                f'Translation: "{translations[language_code]}"',
                "| Link ID | Position | English | Lemma GUID | Expected | Actual |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for link_row in link_rows:
            actual_form = link_row["declined_form"] or link_row["target_text"] or "(n/a)"
            prompt_lines.append(
                f"| {link_row['sentence_word_id']} | {link_row['position']} | "
                f"{link_row['english_text'] or '(n/a)'} | {link_row['lemma_guid']} | "
                f"{link_row['expected_translation'] or '(n/a)'} | {actual_form} |"
            )
    prompt_lines.extend(
        [
            "",
            "For each Link ID, return two verdicts:",
            "- sense: whether the linked lemma is the right word sense in context.",
            "- form: whether the actual surface form is valid for that lemma in context.",
            'Return only "correct" or "incorrect" for every field.',
        ]
    )
    return "\n".join(prompt_lines)


def build_sentence_link_verification_schema(
    links_by_language: Dict[str, List[Dict[str, Any]]]
) -> Schema:
    """Build a schema containing explicit fields for every stored link."""
    properties: Dict[str, SchemaProperty] = {}
    for language_code, link_rows in links_by_language.items():
        for link_row in link_rows:
            sentence_word_id = int(link_row["sentence_word_id"])
            properties[_link_field(language_code, sentence_word_id, "sense")] = SchemaProperty(
                type="string",
                description="Whether this is the correct lemma sense",
                enum=["correct", "incorrect"],
            )
            properties[_link_field(language_code, sentence_word_id, "form")] = SchemaProperty(
                type="string",
                description="Whether the sentence form matches the lemma",
                enum=["correct", "incorrect"],
            )
    return Schema(
        name="SentenceLinkVerification",
        description="Sense and form verdicts for sentence lemma links",
        properties=properties,
    )


def verify_sentence_links(
    session: Session,
    sentence_id: int,
    config: DataSourceConfig,
    languages: Optional[List[str]] = None,
    *,
    llm_client: Optional[UnifiedLLMClient] = None,
) -> SentenceLinkVerificationResult:
    """Verify stored lemma links for one sentence and return a read-only report.

    ``SentenceWord`` currently has no verification-status columns, so this
    operation intentionally does not mutate the database.
    """
    _get_sentence_or_raise(session, sentence_id)
    english_text = _get_english_text(session, sentence_id)
    supported_languages = _supported_languages(config, languages)
    translation_rows = (
        session.query(SentenceTranslation)
        .filter(
            SentenceTranslation.sentence_id == sentence_id,
            SentenceTranslation.language_code.in_(supported_languages),
        )
        .all()
    )
    translations = {
        translation_row.language_code: translation_row.translation_text
        for translation_row in translation_rows
    }
    links_by_language = _get_links(session, sentence_id, list(translations))
    if not links_by_language:
        return {
            "sentence_id": sentence_id,
            "english_text": english_text,
            "results": {},
            "success": True,
        }

    client = llm_client or UnifiedLLMClient.from_config(config)
    response = client.generate_chat(
        prompt=build_sentence_link_verification_prompt(
            english_text, translations, links_by_language
        ),
        json_schema=build_sentence_link_verification_schema(links_by_language),
        timeout=90,
    )
    if not response.structured_data:
        raise RuntimeError("LLM did not return structured sentence link verification data")

    results: Dict[str, Dict[str, SentenceLinkVerdict]] = {}
    for language_code, link_rows in links_by_language.items():
        language_results: Dict[str, SentenceLinkVerdict] = {}
        for link_row in link_rows:
            sentence_word_id = int(link_row["sentence_word_id"])
            language_results[str(sentence_word_id)] = {
                "lemma_guid": link_row["lemma_guid"],
                "sense_correct": parse_verdict(
                    response.structured_data.get(
                        _link_field(language_code, sentence_word_id, "sense")
                    )
                ),
                "form_matches": parse_verdict(
                    response.structured_data.get(
                        _link_field(language_code, sentence_word_id, "form")
                    )
                ),
            }
        results[language_code] = language_results

    return {
        "sentence_id": sentence_id,
        "english_text": english_text,
        "results": results,
        "success": True,
    }
