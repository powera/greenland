#!/usr/bin/python3

"""Shared prompt + query helpers for sentence decomposition tasks."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from clients.unified_client import UnifiedLLMClient
from storage.models.schema import Lemma, Sentence, SentencePatternWord, SentenceTranslation
from storage.translation_helpers import LANGUAGE_NAMES, get_translation, normalize_llm_language_codes

logger = logging.getLogger(__name__)


def _normalize_target_languages(target_languages: List[str]) -> List[str]:
    return normalize_llm_language_codes(target_languages, operation_name="Sentence decomposition")


def _decomposition_context() -> str:
    context_lines = [
        "You are a multilingual linguistics expert.",
        "",
        "For each target language, provide detailed word-by-word breakdown including:",
        "- word: the actual inflected form as it appears in the sentence",
        "- english: English translation of this specific word/phrase",
        "- guid: the GUID for this word if provided in the word reference (e.g., 'N08_001'), or empty string if not provided",
        "- role: grammatical role (subject, verb, object, adjective, adverb, article, preposition, determiner, pronoun, etc.)",
        "- grammatical_form: Use format 'pos/lang_details' where:",
        "  * pos = part of speech (verb, noun, adjective, adverb, pronoun, preposition, conjunction, article, etc.)",
        "  * lang = language code for the target language (en, lt, fr, de, es, pt, ko, zh)",
        "  * details = specific form using this notation:",
        "    - Person/number: 1s, 2s, 3s, 1p, 2p, 3p (no gender unless the WORD FORM itself differs by gender)",
        "    - Gender ONLY when word form differs: use hyphen for person (3s-m, 3s-f, 3p-m, 3p-f) or underscore for case (singular_m, plural_f)",
        "    - Tense: present, past, future, impf, pc (passé composé), inf (infinitive), etc.",
        "    - Case (Lithuanian, German only): nominative, accusative, genitive, dative, instrumental, locative, vocative",
        "    - For languages WITHOUT grammatical case (English, French, Spanish, Portuguese, Korean, Chinese):",
        "      Use ONLY singular/plural without case: 'noun/en_singular', 'noun/fr_plural', 'noun/zh_singular'",
        "    - For languages WITH grammatical case (Lithuanian, German):",
        "      Use case_number: 'noun/lt_nominative_singular', 'noun/de_accusative_plural'",
        "    - Combine with underscores: nominative_singular, accusative_plural_m, etc.",
        "  * PRONOUNS: pronoun/LANG_function where function is subjective, objective, possessive, reflexive",
        "    - Case languages (lt, de): pronoun/LANG_case (nominative, accusative, genitive, dative, etc.)",
        "  * NUMERALS: numeral/LANG_type where type is cardinal or ordinal",
        "    - Lemma form is cardinal, masculine where gender applies",
        "    - Add _m, _f, _n suffix for gendered forms (lt, de, fr, es, pt)",
        "    - Chinese: zh_cardinal (二), zh_quantity (两 before measure words), zh_ordinal (第二)",
        "    - Korean: ko_native (둘), ko_sino (이), ko_ordinal (둘째)",
        "  * For invariant words: preposition/base, conjunction/base, article/base",
        "",
        "IMPORTANT: Do NOT include punctuation marks as separate words in the breakdown.",
        "Provide words in the order they appear in the translated sentence.",
    ]
    return "\n".join(context_lines)


def build_translate_and_decompose_prompt_from_english(
    sentence: Sentence,
    target_languages: List[str],
    session: Any,
    *,
    include_english: bool = True,
) -> Tuple[str, str]:
    """Build prompt for translating from English and decomposing each target translation."""
    target_languages = _normalize_target_languages(target_languages)

    en_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence.id, language_code="en")
        .first()
    )
    if not en_translation:
        raise ValueError(f"Sentence {sentence.id} has no English translation")

    template_text = en_translation.translation_text

    pattern_words = (
        session.query(SentencePatternWord)
        .filter_by(sentence_id=sentence.id)
        .order_by(SentencePatternWord.position)
        .all()
    )

    word_translations: Dict[str, Dict[str, str]] = {}
    for pattern_word in pattern_words:
        lemma = session.query(Lemma).filter_by(id=pattern_word.lemma_id).first()
        if not lemma:
            continue

        english_text = pattern_word.english_text
        word_translations[english_text] = {
            "guid": lemma.guid if lemma.guid else "",
            "role": pattern_word.slot_name,
        }

        for lang in target_languages:
            trans = get_translation(session, lemma, lang)
            if trans:
                word_translations[english_text][lang] = trans

    prompt_lines = [f"Template sentence: {template_text}", "", "Word translations for reference:"]
    for english_word, translations in word_translations.items():
        guid = translations.get("guid", "")
        role = translations.get("role", "")
        trans_items = [
            (lang, trans) for lang, trans in translations.items() if lang not in ("guid", "role")
        ]
        trans_str = ", ".join([f"{lang}={trans}" for lang, trans in trans_items])
        role_str = f" [{role}]" if role else ""
        guid_str = f" (GUID: {guid})" if guid else ""
        prompt_lines.append(f"  {english_word}{role_str}{guid_str}: {trans_str}")

    prompt_lines.append("")
    prompt_lines.append(
        f"Translate this sentence naturally into: {', '.join([LANGUAGE_NAMES[lang] for lang in target_languages if lang in LANGUAGE_NAMES])}."
    )
    prompt_lines.append("")

    if include_english:
        prompt_lines.append(
            "IMPORTANT: Also provide a grammatically correct English version (fixing issues like singular/plural, articles, etc.)."
        )
    else:
        prompt_lines.append(
            "IMPORTANT: The English translation with word-by-word breakdown is already complete. Do NOT include English in your response."
        )

    prompt_lines.append(
        "Use the provided word translations where appropriate, but prioritize natural translations. "
        "If the target language expresses the concept differently, use natural phrasing and map words "
        "to their actual meanings, not the English lemmas. Only include GUIDs for words that genuinely "
        "correspond to the referenced lemma's meaning."
    )

    return _decomposition_context(), "\n".join(prompt_lines)


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

    return (
        f"Create a sentence decomposition JSON for ONE language only.\n"
        f"Source sentence ({source_language}): \"{source_sentence}\"\n"
        f"Target language: {target_language}\n"
        f"Target translation: \"{target_translation}\"\n\n"
        "Additional translations for disambiguation (1-3 helper languages):\n"
        f"{helper_lines if helper_lines else '- (none provided)'}\n\n"
        "Lemma translation context: include source, target, and at most 3 helper languages.\n\n"
        "Candidate lemmas (must choose correct lemma_guid when a content word maps to one):\n"
        f"{candidate_lines}\n\n"
        "Grammatical form conventions (match translation prompt style):\n"
        "- Use format: <role>/<language_code>_<morphology> for inflected items.\n"
        "- Part-of-speech prefix should match role (verb, noun, adjective, adverb, pronoun, numeral, etc.).\n"
        "- Person/number notation: 1s, 2s, 3s, 1p, 2p, 3p.\n"
        "- Include gender only when the surface form differs by gender (examples: 3s-m, 3s-f, singular_f).\n"
        "- Tense/aspect examples: present, past, future, impf, pc, inf.\n"
        "- Case languages (lt, de): include case + number (example: noun/de_accusative_singular).\n"
        "- Non-case languages (en, fr, es, pt, ko, zh): use number only for nouns (example: noun/fr_singular).\n"
        "- Pronouns: pronoun/<lang>_subjective|objective|possessive|reflexive (case label for case languages).\n"
        "- Numerals: numeral/<lang>_cardinal|ordinal (or language-specific subtype where applicable).\n"
        "- For uninflected closed-class words, use <role>/base (example: preposition/base).\n"
        "- Keep language code aligned with the target token language.\n"
        "- IMPORTANT: Do NOT include punctuation as a word/token in words[].\n"
        "- word_count must equal the number of word entries.\n\n"
        "Return schema requirements:\n"
        f"- Return exactly one entry in languages[] and set language_code to '{target_language}'.\n"
        "- The languages[] breakdown must analyze tokens from the target translation only.\n"
        "- Each words[] item must include: position, role, english_gloss, surface_form, grammatical_form, lemma_guid, lemma.\n"
        "- Use lemma_guid=NONE for function words without a selected candidate lemma."
    )


def build_decomposition_schema(*, target_languages: List[str], include_english: bool = True) -> Dict[str, Any]:
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
        schema_properties["en"] = {"type": "string", "description": "Grammatically corrected English sentence"}
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
