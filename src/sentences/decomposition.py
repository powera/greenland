#!/usr/bin/python3

"""Shared prompt + query helpers for sentence decomposition tasks."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.grammatical_words import is_function_word, is_grammatical_word
from storage.models.schema import Lemma, Sentence, SentencePatternWord, SentenceTranslation
from storage.translation_helpers import (
    LANGUAGE_NAMES,
    get_translation,
    normalize_llm_language_codes,
)

import util.prompt_loader

logger = logging.getLogger(__name__)

_TRANSLATE_DECOMPOSE_PROMPT_PATH = "translate_and_decompose"
_SINGLE_LANGUAGE_PROMPT_PATH = "single_language"

_NO_LEMMA_MARKERS = {"", "none", "null"}
_NO_LEMMA_TEXT_MARKERS = {"", "no lemma", "none", "null"}


def find_unresolved_non_grammatical_words(
    words: List[Dict[str, Any]], language_code: str
) -> List[Dict[str, Any]]:
    """Return decomposition words that have no lemma and are not grammatical/function words."""

    unresolved_words: List[Dict[str, Any]] = []
    normalized_language_code = language_code.strip().lower()

    for word_row in words:
        lemma_guid_value = str(word_row.get("lemma_guid", "")).strip().lower()
        lemma_text_value = str(word_row.get("lemma", "")).strip().lower()
        has_lemma = (
            lemma_guid_value not in _NO_LEMMA_MARKERS
            and lemma_text_value not in _NO_LEMMA_TEXT_MARKERS
        )
        if has_lemma:
            continue

        surface_form = str(word_row.get("surface_form", "")).strip()
        if not surface_form:
            unresolved_words.append(word_row)
            continue

        is_grammatical = is_grammatical_word(surface_form, normalized_language_code)
        is_function = is_function_word(surface_form, normalized_language_code)
        if is_grammatical or is_function:
            continue

        unresolved_words.append(word_row)

    return unresolved_words


def all_words_are_lemmas_or_grammatical(words: List[Dict[str, Any]], language_code: str) -> bool:
    """Return True when every word has a lemma or is a grammatical/function word."""

    unresolved_words = find_unresolved_non_grammatical_words(words, language_code)
    return len(unresolved_words) == 0


def _normalize_target_languages(target_languages: List[str]) -> List[str]:
    return normalize_llm_language_codes(target_languages, operation_name="Sentence decomposition")


def build_prompt_for_translate_and_decompose(
    sentence: Sentence,
    target_languages: List[str],
    session: Any,
    *,
    include_english: bool = True,
    source_language: str = "en",
) -> Tuple[str, str]:
    """Build context + prompt for translating and decomposing one sentence."""
    target_languages = _normalize_target_languages(target_languages)

    source_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence.id, language_code=source_language)
        .first()
    )
    if not source_translation:
        raise ValueError(
            f"Sentence {sentence.id} has no source translation for language '{source_language}'"
        )

    pattern_words = (
        session.query(SentencePatternWord)
        .filter_by(sentence_id=sentence.id)
        .order_by(SentencePatternWord.position)
        .all()
    )

    word_translation_lines: List[str] = []
    for pattern_word in pattern_words:
        lemma = session.query(Lemma).filter_by(id=pattern_word.lemma_id).first()
        if not lemma:
            continue

        english_text = pattern_word.english_text
        role = pattern_word.slot_name or ""
        guid = lemma.guid if lemma.guid else ""

        trans_items: List[str] = []
        for lang in target_languages:
            trans = get_translation(session, lemma, lang)
            if trans:
                trans_items.append(f"{lang}={trans}")

        role_str = f" [{role}]" if role else ""
        guid_str = f" (GUID: {guid})" if guid else ""
        trans_str = ", ".join(trans_items)
        word_translation_lines.append(f"  {english_text}{role_str}{guid_str}: {trans_str}")

    english_instruction = (
        "IMPORTANT: Also provide a grammatically correct English version "
        "(fixing issues like singular/plural, articles, etc.)."
        if include_english
        else "IMPORTANT: The English translation with word-by-word breakdown is already complete. "
        "Do NOT include English in your response."
    )

    language_names = [LANGUAGE_NAMES[lang] for lang in target_languages if lang in LANGUAGE_NAMES]

    prompt = util.prompt_loader.get_prompt(
        "sentence_decomposition",
        _TRANSLATE_DECOMPOSE_PROMPT_PATH,
    ).format(
        template_sentence=source_translation.translation_text,
        word_translations="\n".join(word_translation_lines) or "- (none provided)",
        target_language_names=", ".join(language_names),
        english_instruction=english_instruction,
    )
    context = util.prompt_loader.get_context(
        "sentence_decomposition",
        _TRANSLATE_DECOMPOSE_PROMPT_PATH,
    )
    return context, prompt


def build_sentence_decomposition_context() -> str:
    """Return context for single-language sentence decomposition."""
    return util.prompt_loader.get_context("sentence_decomposition", _SINGLE_LANGUAGE_PROMPT_PATH)


def build_sentence_decomposition_prompt(
    *,
    source_sentence: str,
    source_language: str,
    target_language: str,
    target_translation: str,
    helper_translations: Optional[List[Dict[str, str]]] = None,
    candidate_lemmas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build prompt for decomposing one already-provided translation."""
    helper_translations = helper_translations or []
    candidate_lemmas = candidate_lemmas or []

    helper_lines = "\n".join(
        f"- {entry['language_code']}: {entry['translation']}" for entry in helper_translations
    )

    helper_languages = [
        entry["language_code"] for entry in helper_translations if entry.get("language_code")
    ]
    allowed_languages = [source_language, target_language, *helper_languages[:3]]

    if candidate_lemmas:
        candidate_lines = "\n".join(
            (
                f"- {item['guid']} - {item['lemma']} ({item['disambiguation']}) | "
                f"POS: {item['pos']} | Definition: {item['definition']} | "
                "Translations: "
                + ", ".join(
                    f"{lang}={translation}"
                    for lang, translation in item.get("translations", {}).items()
                    if lang in allowed_languages
                )
            )
            for item in candidate_lemmas
        )
    else:
        candidate_lines = "- (none provided)"

    return util.prompt_loader.get_prompt(
        "sentence_decomposition", _SINGLE_LANGUAGE_PROMPT_PATH
    ).format(
        source_sentence=source_sentence,
        source_language=source_language,
        target_language=target_language,
        target_translation=target_translation,
        helper_translations=helper_lines if helper_lines else "- (none provided)",
        candidate_lemmas=candidate_lines,
    )


def build_decomposition_schema(
    *, target_languages: List[str], include_english: bool = True
) -> Dict[str, Any]:
    """Schema for translate+decompose requests (ZVIRBLIS and sentence translator)."""
    target_languages = _normalize_target_languages(target_languages)
    word_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "word": {"type": "string"},
            "english": {"type": "string"},
            "guid": {"type": "string"},
            "role": {"type": "string"},
            "grammatical_form": {"type": ["string", "null"]},
        },
        "required": ["word", "english", "guid", "role", "grammatical_form"],
        "additionalProperties": False,
    }

    schema_properties: Dict[str, Any] = {}
    required_fields: List[str] = []

    if include_english:
        schema_properties["en"] = {
            "type": "string",
            "description": "Grammatically corrected English sentence",
        }
        schema_properties["words_en"] = {
            "type": "array",
            "description": "English word breakdown",
            "items": word_schema,
        }
        required_fields.extend(["en", "words_en"])

    for lang in target_languages:
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        schema_properties[lang] = {"type": "string", "description": f"{lang_name} translation"}
        schema_properties[f"words_{lang}"] = {
            "type": "array",
            "description": f"{lang_name} word breakdown",
            "items": word_schema,
        }
        required_fields.extend([lang, f"words_{lang}"])

    return {
        "type": "object",
        "properties": schema_properties,
        "required": required_fields,
        "additionalProperties": False,
    }


def build_single_language_decomposition_schema() -> Dict[str, Any]:
    """Schema for decomposing one language translation (benchmark 0062)."""
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


def query_sentence_decomposition(
    *,
    prompt: str,
    client: UnifiedLLMClient,
    model: str,
    json_schema: Dict[str, Any],
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a sentence decomposition/translation query and return structured JSON."""
    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema,
            context=context,
        )
    except Exception as error:
        logger.error("Error querying sentence decomposition: %s", error)
        return {"success": False, "error": str(error)}

    result: Any = response.structured_data or response.response_text
    if not result:
        return {"success": False, "error": "Empty response from LLM"}

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError as error:
            return {"success": False, "error": f"Invalid JSON response: {error}"}

    if not isinstance(result, dict):
        return {"success": False, "error": "Structured response is not an object"}

    merged: Dict[str, Any] = {"success": True}
    merged.update(result)
    return merged
