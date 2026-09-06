#!/usr/bin/python3

"""Shared prompt + query helpers for sentence decomposition tasks."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.dialect_overrides import get_dialect_display_name, get_llm_prompt_note
from langtools.directions import get_language_direction_note
from langtools.grammatical_words import is_grammatical_word
from storage.crud.name_entity import get_name_by_id, get_name_renderings
from storage.models.schema import (
    Lemma,
    Sentence,
    SentenceWordHint,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    LANGUAGE_NAMES,
    get_translation,
    normalize_llm_language_codes,
)

import util.prompt_loader

logger = logging.getLogger(__name__)

_TRANSLATE_DECOMPOSE_PROMPT_PATH = "translate_and_decompose"
_SINGLE_LANGUAGE_PROMPT_PATH = "single_language"
_MULTI_LANGUAGE_PROMPT_PATH = "multi_language"

_NO_LEMMA_MARKERS = {"", "none", "null"}
_NO_LEMMA_TEXT_MARKERS = {"", "no lemma", "none", "null"}


def find_unresolved_non_grammatical_words(
    words: List[Dict[str, Any]], language_code: str
) -> List[Dict[str, Any]]:
    """Return words missing lemmas, excluding tokens that never have release lemmas."""

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

        if is_grammatical_word(surface_form, normalized_language_code):
            continue

        unresolved_words.append(word_row)

    return unresolved_words


def all_words_are_lemmas_or_grammatical(words: List[Dict[str, Any]], language_code: str) -> bool:
    """Return True when every word has a lemma or never has a release lemma."""

    unresolved_words = find_unresolved_non_grammatical_words(words, language_code)
    return len(unresolved_words) == 0


def _normalize_target_languages(target_languages: List[str]) -> List[str]:
    return normalize_llm_language_codes(target_languages, operation_name="Sentence decomposition")


def build_decomposed_word_schema(*, additional_properties: bool = True) -> Dict[str, Any]:
    """Return the canonical JSON schema for one decomposed word.

    Every decomposition path - single-language, multi-language, translate+
    decompose, and verbalator - shares this shape. Add new per-word fields
    here and only here, so the schemas cannot drift apart.

    Set ``additional_properties=False`` for providers that need the object
    closed; the field set is otherwise identical across callers.
    """
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "position": {"type": "integer"},
            "part_of_speech": {
                "type": "string",
                "description": "Part of speech, never subject/object syntactic role",
            },
            "english_gloss": {"type": "string"},
            "surface_form": {"type": "string"},
            "grammatical_form": {"type": ["string", "null"]},
            "lemma_guid": {"type": "string"},
            "lemma": {"type": "string"},
        },
        "required": [
            "position",
            "part_of_speech",
            "english_gloss",
            "surface_form",
            "grammatical_form",
            "lemma_guid",
            "lemma",
        ],
    }
    if not additional_properties:
        schema["additionalProperties"] = False
    return schema


def build_name_rendering_lines(
    sentence: Sentence,
    target_languages: List[str],
    session: Any,
) -> List[str]:
    """Render the pinned spelling of each name in a sentence, one line per name.

    A name has to be written *somehow* in every target language -- Lithuanian
    needs a declinable ``Džonas``, Chinese needs ``约翰`` -- and if the prompt
    does not say which, the model invents one per call and the same character is
    spelled differently in consecutive sentences. These lines pin the answer we
    have already curated.

    A name with no rendering in a given language is simply omitted for that
    language, leaving the model to do what it does today; that gap is the signal
    that the name needs a rendering, not an error.

    Args:
        sentence: The sentence being translated.
        target_languages: Already-normalized target language codes.
        session: Database session.

    Returns:
        Formatted lines, empty when the sentence casts no names.
    """
    sentence_names = (
        session.query(SentenceWord)
        .filter(
            SentenceWord.sentence_id == sentence.id,
            SentenceWord.name_id.isnot(None),
        )
        .order_by(SentenceWord.position)
        .all()
    )

    lines: List[str] = []
    seen_name_ids: set[int] = set()
    for sentence_word in sentence_names:
        if sentence_word.name_id in seen_name_ids:
            continue
        seen_name_ids.add(sentence_word.name_id)

        name = get_name_by_id(session, sentence_word.name_id)
        if name is None:
            continue

        renderings = get_name_renderings(session, name)
        rendering_items = [
            f"{lang}={renderings[lang]}" for lang in target_languages if lang in renderings
        ]
        if not rendering_items:
            continue
        lines.append(f"  {name.name_text}: {', '.join(rendering_items)}")

    return lines


def build_prompt_for_translate_and_decompose(
    sentence: Sentence,
    target_languages: List[str],
    session: Any,
    *,
    include_english: bool = True,
    source_language: str = "en",
    candidate_lemmas: Optional[List[Lemma]] = None,
) -> Tuple[str, str]:
    """Build context + prompt for translating and decomposing one sentence.

    ``candidate_lemmas`` is an optional ranked list of Lemmas the LLM should
    prefer when a word in the sentence corresponds to one of these meanings.
    Typically sourced from pivot-disambiguated candidate lookup for sentences
    that have no SentenceWordHint.lemma_id rows yet. Rendered as a flat
    block alongside the existing word_translations block; the two are
    independent.
    """
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

    word_hints = (
        session.query(SentenceWordHint)
        .filter_by(sentence_id=sentence.id)
        .order_by(SentenceWordHint.position)
        .all()
    )

    # Collect lemma_id -> (English text, part of speech) from word hints first.
    seen_lemma_ids: set[int] = set()
    lemma_entries: List[tuple[int, str, str]] = []
    for word_hint in word_hints:
        if word_hint.lemma_id and word_hint.lemma_id not in seen_lemma_ids:
            seen_lemma_ids.add(word_hint.lemma_id)
            lemma_entries.append(
                (
                    word_hint.lemma_id,
                    word_hint.english_text or "",
                    word_hint.slot_name or "",
                )
            )

    # Also collect lemmas from SentenceWord (e.g. sentences imported via genys)
    sentence_words = (
        session.query(SentenceWord)
        .filter(
            SentenceWord.sentence_id == sentence.id,
            SentenceWord.lemma_id.isnot(None),
        )
        .order_by(SentenceWord.position)
        .all()
    )
    for sw in sentence_words:
        if sw.lemma_id not in seen_lemma_ids:
            seen_lemma_ids.add(sw.lemma_id)
            lemma_entries.append((sw.lemma_id, sw.english_text or "", sw.part_of_speech or ""))

    word_translation_lines: List[str] = []
    for lemma_id, english_text, part_of_speech in lemma_entries:
        lemma = session.query(Lemma).filter_by(id=lemma_id).first()
        if not lemma:
            continue

        guid = lemma.guid if lemma.guid else ""

        trans_items: List[str] = []
        for lang in target_languages:
            trans = get_translation(session, lemma, lang)
            if trans:
                trans_items.append(f"{lang}={trans}")

        part_of_speech_str = f" [{part_of_speech}]" if part_of_speech else ""
        guid_str = f" (GUID: {guid})" if guid else ""
        trans_str = ", ".join(trans_items)
        word_translation_lines.append(
            f"  {english_text}{part_of_speech_str}{guid_str}: {trans_str}"
        )

    candidate_lines: List[str] = []
    if candidate_lemmas:
        seen_candidate_ids: set[int] = set()
        for lemma in candidate_lemmas:
            if not lemma or lemma.id in seen_candidate_ids or lemma.id in seen_lemma_ids:
                continue
            seen_candidate_ids.add(lemma.id)
            candidate_guid = lemma.guid or ""
            candidate_trans_items: List[str] = []
            for lang in target_languages:
                candidate_trans = get_translation(session, lemma, lang)
                if candidate_trans:
                    candidate_trans_items.append(f"{lang}={candidate_trans}")
            disambiguation_str = f" ({lemma.disambiguation})" if lemma.disambiguation else ""
            pos_str = f" [{lemma.pos_type}]" if lemma.pos_type else ""
            candidate_guid_str = f" (GUID: {candidate_guid})" if candidate_guid else ""
            candidate_trans_str = ", ".join(candidate_trans_items)
            candidate_lines.append(
                f"  {lemma.lemma_text}{disambiguation_str}{pos_str}"
                f"{candidate_guid_str}: {candidate_trans_str}"
            )

    name_rendering_lines = build_name_rendering_lines(sentence, target_languages, session)

    english_instruction = (
        "IMPORTANT: Also provide a grammatically correct English version "
        "(fixing issues like singular/plural, articles, etc.)."
        if include_english
        else "IMPORTANT: The English translation with word-by-word breakdown is already complete. "
        "Do NOT include English in your response."
    )

    target_language_lines: List[str] = []
    for lang in target_languages:
        display_name = get_dialect_display_name(lang)
        notes: List[str] = []
        direction_note = get_language_direction_note(lang)
        if direction_note:
            notes.append(direction_note.lstrip("- ").strip())
        dialect_note = get_llm_prompt_note(lang)
        if dialect_note:
            notes.append(dialect_note)
        line = f"- {display_name} ({lang})"
        if notes:
            line += ": " + "; ".join(notes)
        target_language_lines.append(line)

    prompt = util.prompt_loader.get_prompt(
        "sentence_decomposition",
        _TRANSLATE_DECOMPOSE_PROMPT_PATH,
    ).format(
        template_sentence=source_translation.translation_text,
        word_translations="\n".join(word_translation_lines) or "- (none provided)",
        candidate_lemmas="\n".join(candidate_lines) or "- (none provided)",
        name_renderings="\n".join(name_rendering_lines) or "  (none)",
        target_languages_with_notes="\n".join(target_language_lines),
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


def _format_candidate_line(item: Dict[str, Any], allowed_languages: List[str]) -> str:
    """Format one candidate lemma as a single bullet line."""
    translations = ", ".join(
        f"{lang}={translation}"
        for lang, translation in item.get("translations", {}).items()
        if lang in allowed_languages
    )
    return (
        f"  - {item['guid']} - {item['lemma']} ({item['disambiguation']}) | "
        f"POS: {item['pos']} | Definition: {item['definition']} | "
        f"Translations: {translations}"
    )


def build_sentence_decomposition_prompt(
    *,
    source_sentence: str,
    source_language: str,
    target_language: str,
    target_translation: str,
    helper_translations: Optional[List[Dict[str, str]]] = None,
    candidate_lemmas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build prompt for decomposing one already-provided translation.

    ``candidate_lemmas`` is a flat ranked list rendered as a single bullet
    list. Items must be dict-like with keys ``guid``, ``lemma``,
    ``disambiguation``, ``pos``, ``definition``, and ``translations`` (a
    mapping of language_code -> surface form).
    """
    helper_translations = (helper_translations or [])[:3]
    candidate_lemmas = candidate_lemmas or []

    helper_lines = "\n".join(
        f"- {entry['language_code']}: {entry['translation']}" for entry in helper_translations
    )

    helper_languages = [
        entry["language_code"] for entry in helper_translations if entry.get("language_code")
    ]
    allowed_languages = [source_language, target_language, *helper_languages]

    if candidate_lemmas:
        candidate_lines = "\n".join(
            _format_candidate_line(item, allowed_languages) for item in candidate_lemmas
        )
    else:
        candidate_lines = "- (none provided)"

    return util.prompt_loader.get_prompt(
        "sentence_decomposition", _SINGLE_LANGUAGE_PROMPT_PATH
    ).format(
        source_sentence=source_sentence,
        source_language=source_language,
        target_language=target_language,
        target_language_name=LANGUAGE_NAMES.get(target_language, target_language),
        target_translation=target_translation,
        helper_translations=helper_lines if helper_lines else "- (none provided)",
        candidate_lemmas=candidate_lines,
    )


def build_multi_language_decomposition_prompt(
    *,
    source_sentence: str,
    source_language: str,
    target_translations: Dict[str, str],
    helper_translations: Optional[List[Dict[str, str]]] = None,
    candidate_lemmas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build prompt for decomposing several already-provided translations in one call.

    ``target_translations`` maps language_code -> already-known translation text;
    every entry is decomposed in the response. The LLM is instructed not to
    retranslate. ``candidate_lemmas`` is a flat ranked list rendered as a
    single bullet list (same item shape as
    :func:`build_sentence_decomposition_prompt`).
    """
    helper_translations = (helper_translations or [])[:3]
    candidate_lemmas = candidate_lemmas or []

    target_lines = "\n".join(
        f'- {lang} ({LANGUAGE_NAMES.get(lang, lang)}): "{text}"'
        for lang, text in target_translations.items()
    )

    helper_lines = "\n".join(
        f"- {entry['language_code']}: {entry['translation']}" for entry in helper_translations
    )

    helper_languages = [
        entry["language_code"] for entry in helper_translations if entry.get("language_code")
    ]
    allowed_languages = [source_language, *target_translations.keys(), *helper_languages]

    if candidate_lemmas:
        candidate_lines = "\n".join(
            _format_candidate_line(item, allowed_languages) for item in candidate_lemmas
        )
    else:
        candidate_lines = "- (none provided)"

    return util.prompt_loader.get_prompt(
        "sentence_decomposition", _MULTI_LANGUAGE_PROMPT_PATH
    ).format(
        source_sentence=source_sentence,
        source_language=source_language,
        target_translations=target_lines if target_lines else "- (none provided)",
        helper_translations=helper_lines if helper_lines else "- (none provided)",
        candidate_lemmas=candidate_lines,
    )


def build_multi_language_decomposition_context() -> str:
    """Return context for multi-language sentence decomposition."""
    return util.prompt_loader.get_context("sentence_decomposition", _MULTI_LANGUAGE_PROMPT_PATH)


def build_multi_language_decomposition_schema(*, target_languages: List[str]) -> Dict[str, Any]:
    """Schema for combined Phase 3 decomposition of several already-translated languages.

    For each ``lang`` in ``target_languages`` the response object must include a
    string field ``lang`` (echo of the provided translation) and an array field
    ``words_lang`` whose entries match the single-language Phase 3 word shape
    (``position``, ``part_of_speech``, ``english_gloss``, ``surface_form``,
    ``grammatical_form``, ``lemma_guid``, ``lemma``).
    """
    target_languages = _normalize_target_languages(target_languages)
    word_schema = build_decomposed_word_schema()

    schema_properties: Dict[str, Any] = {}
    required_fields: List[str] = []
    for lang in target_languages:
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        schema_properties[lang] = {
            "type": "string",
            "description": f"{lang_name} translation (echo of provided text)",
        }
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
    }


def build_decomposition_schema(
    *, target_languages: List[str], include_english: bool = True
) -> Dict[str, Any]:
    """Schema for translate+decompose requests (ZVIRBLIS and sentence translator).

    Uses the same per-word shape as every other decomposition path; only the
    outer structure (``words_<lang>`` keys plus an optional English echo)
    differs.
    """
    target_languages = _normalize_target_languages(target_languages)
    word_schema = build_decomposed_word_schema(additional_properties=False)

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
                        "words": {
                            "type": "array",
                            "items": build_decomposed_word_schema(),
                        },
                    },
                    "required": ["language_code", "translation", "words"],
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
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute a sentence decomposition/translation query and return structured JSON.

    ``max_tokens`` should come from ``clients.lib.limit_from_estimate()`` applied
    to an estimate from ``sentences.token_estimates``; a decomposition's size is
    predictable from its word count, and the backend default is not large enough
    for long sentences. A backend that hits its limit raises
    ``TruncatedResponseError``, which is caught below and reported as a failed
    call rather than a short one.
    """
    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema,
            context=context,
            max_tokens=max_tokens,
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
    if response.usage is not None:
        merged["_usage"] = {
            "tokens_in": getattr(response.usage, "tokens_in", None),
            "tokens_out": getattr(response.usage, "tokens_out", None),
            "total_tokens": getattr(response.usage, "total_tokens", None),
        }
    return merged
