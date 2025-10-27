#!/usr/bin/env python3
"""
LLM-based validation helpers for wordfreq agents.

This module provides functions that use LLM queries to validate
word data quality, including lemma forms and translations.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


def validate_lemma_form(word: str, pos_type: str, model: str = "gpt-5-mini") -> Dict[str, any]:
    """
    Validate that a word is in its correct lemma (base) form.

    Args:
        word: The word to validate
        pos_type: Part of speech (noun, verb, adjective, etc.)
        model: LLM model to use

    Returns:
        Dictionary with validation results:
        - is_lemma: bool indicating if word is in lemma form
        - suggested_lemma: str with correct lemma form if different
        - reason: str explaining the issue
        - confidence: float 0-1
    """
    client = UnifiedLLMClient()

    schema = Schema(
        name="LemmaValidation",
        description="Validation of whether a word is in its lemma (dictionary) form",
        properties={
            "is_lemma": SchemaProperty("boolean", "True if the word is already in lemma form"),
            "suggested_lemma": SchemaProperty("string", "The correct lemma form if different from input"),
            "reason": SchemaProperty("string", "Explanation of why it's not a lemma or confirmation it is"),
            "confidence": SchemaProperty("number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0)
        }
    )

    # Load prompt from files
    context = util.prompt_loader.get_context("wordfreq", "lemma_validation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "lemma_validation")

    prompt = prompt_template.format(
        word=word,
        pos_type=pos_type
    )

    logger.debug(f"Validating lemma form for word: '{word}' (POS: {pos_type})")

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            context=context
        )

        if response.structured_data:
            return response.structured_data
        else:
            logger.error(f"No structured data received for lemma validation of '{word}'")
            return {
                'is_lemma': True,  # Assume correct if validation fails
                'suggested_lemma': word,
                'reason': 'Validation failed',
                'confidence': 0.0
            }

    except Exception as e:
        logger.error(f"Error validating lemma form for '{word}': {e}")
        return {
            'is_lemma': True,
            'suggested_lemma': word,
            'reason': f'Error: {str(e)}',
            'confidence': 0.0
        }


def validate_translation(
    english_word: str,
    translation: str,
    target_language: str,
    pos_type: str,
    model: str = "gpt-5-mini"
) -> Dict[str, any]:
    """
    Validate that a translation is correct and in lemma form.

    Args:
        english_word: English word (should be in lemma form)
        translation: Translation to validate
        target_language: Language code and name (e.g., "lt (Lithuanian)")
        pos_type: Part of speech
        model: LLM model to use

    Returns:
        Dictionary with validation results:
        - is_correct: bool indicating if translation is accurate
        - is_lemma_form: bool indicating if translation is in lemma form
        - suggested_translation: str with better translation if needed
        - issues: list of issues found
        - confidence: float 0-1
    """
    client = UnifiedLLMClient()

    schema = Schema(
        name="TranslationValidation",
        description="Validation of translation accuracy and lemma form",
        properties={
            "is_correct": SchemaProperty("boolean", "True if the translation is semantically correct"),
            "is_lemma_form": SchemaProperty("boolean", "True if the translation is in lemma/dictionary form"),
            "suggested_translation": SchemaProperty("string", "Better translation if current one has issues"),
            "issues": SchemaProperty(
                type="array",
                description="List of issues found",
                items={"type": "string"}
            ),
            "confidence": SchemaProperty("number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0)
        }
    )

    # Load prompt from files
    context = util.prompt_loader.get_context("wordfreq", "translation_validation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "translation_validation")

    prompt = prompt_template.format(
        english_word=english_word,
        target_language=target_language,
        translation=translation,
        pos_type=pos_type
    )

    logger.debug(f"Validating translation: '{english_word}' → '{translation}' ({target_language}, POS: {pos_type})")

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            context=context
        )

        if response.structured_data:
            return response.structured_data
        else:
            logger.error(f"No structured data received for translation validation of '{english_word}' → '{translation}'")
            return {
                'is_correct': True,  # Assume correct if validation fails
                'is_lemma_form': True,
                'suggested_translation': translation,
                'issues': ['Validation failed'],
                'confidence': 0.0
            }

    except Exception as e:
        logger.error(f"Error validating translation '{english_word}' → '{translation}': {e}")
        return {
            'is_correct': True,
            'is_lemma_form': True,
            'suggested_translation': translation,
            'issues': [f'Error: {str(e)}'],
            'confidence': 0.0
        }


def validate_definition(
    word: str,
    definition: str,
    pos_type: str,
    model: str = "gpt-5-mini",
    translation_language: Optional[str] = None,
    translation_text: Optional[str] = None
) -> Dict[str, any]:
    """
    Validate that a definition is well-formed and appropriate.

    Args:
        word: The word being defined
        definition: The definition text to validate
        pos_type: Part of speech
        model: LLM model to use
        translation_language: Optional language name (e.g., "Lithuanian") for translation context
        translation_text: Optional translation text to include in validation context

    Returns:
        Dictionary with validation results:
        - is_valid: bool indicating if definition is well-formed
        - issues: list of problems found (e.g., "Contains translation", "Too vague", "Empty")
        - suggested_definition: str with better definition if needed
        - confidence: float 0-1
    """
    client = UnifiedLLMClient()

    schema = Schema(
        name="DefinitionValidation",
        description="Validation of definition text quality",
        properties={
            "is_valid": SchemaProperty("boolean", "True if the definition is well-formed and appropriate"),
            "issues": SchemaProperty(
                type="array",
                description="List of issues found (e.g., 'Contains translation only', 'Too vague', 'Empty', 'Circular definition')",
                items={"type": "string"}
            ),
            "suggested_definition": SchemaProperty("string", "A better definition if the current one has issues, otherwise empty string"),
            "confidence": SchemaProperty("number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0)
        }
    )

    # Load prompt from files
    context = util.prompt_loader.get_context("wordfreq", "definition_validation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "definition_validation")

    # Format translation info
    if translation_language and translation_text:
        translation_info = f"{translation_language} Translation: {translation_text}"
    else:
        translation_info = "No translation available"

    prompt = prompt_template.format(
        word=word,
        pos_type=pos_type,
        definition=definition,
        translation_info=translation_info
    )

    logger.debug(f"Validating definition for word: '{word}' (POS: {pos_type})")

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            context=context
        )

        if response.structured_data:
            return response.structured_data
        else:
            logger.error(f"No structured data received for definition validation of '{word}'")
            return {
                'is_valid': True,  # Assume valid if validation fails
                'issues': ['Validation failed'],
                'suggested_definition': '',
                'confidence': 0.0
            }

    except Exception as e:
        logger.error(f"Error validating definition for '{word}': {e}")
        return {
            'is_valid': True,
            'issues': [f'Error: {str(e)}'],
            'suggested_definition': '',
            'confidence': 0.0
        }


def batch_validate_lemmas(
    words: List[Dict[str, str]],
    model: str = "gpt-5-mini",
    confidence_threshold: float = 0.7
) -> List[Dict[str, any]]:
    """
    Validate multiple words for lemma form.

    Args:
        words: List of dicts with 'word' and 'pos_type' keys
        model: LLM model to use
        confidence_threshold: Minimum confidence to flag issues

    Returns:
        List of validation results for words that have issues
    """
    issues = []

    for word_info in words:
        word = word_info['word']
        pos_type = word_info['pos_type']

        result = validate_lemma_form(word, pos_type, model)

        if not result['is_lemma'] and result['confidence'] >= confidence_threshold:
            issues.append({
                'word': word,
                'pos_type': pos_type,
                'validation': result
            })

    return issues


def validate_all_translations_for_word(
    english_word: str,
    translations: Dict[str, str],
    pos_type: str,
    model: str = "gpt-5-mini"
) -> Dict[str, any]:
    """
    Validate all translations for a single word in one LLM call.

    Args:
        english_word: English word (should be in lemma form)
        translations: Dict mapping language codes to translations
                     e.g., {'lt': 'batai', 'zh': '鞋子', 'ko': '신발', ...}
        pos_type: Part of speech
        model: LLM model to use

    Returns:
        Dictionary with validation results for each language:
        {
            'language_code': {
                'is_correct': bool,
                'is_lemma_form': bool,
                'suggested_translation': str,
                'issues': list,
                'confidence': float
            },
            ...
        }
    """
    client = UnifiedLLMClient()

    # Build schema for all translations
    language_properties = {}
    for lang_code in translations.keys():
        language_properties[f"{lang_code}_is_correct"] = SchemaProperty(
            "boolean",
            f"True if the {lang_code} translation is semantically correct"
        )
        language_properties[f"{lang_code}_is_lemma_form"] = SchemaProperty(
            "boolean",
            f"True if the {lang_code} translation is in lemma/dictionary form"
        )
        language_properties[f"{lang_code}_suggested"] = SchemaProperty(
            "string",
            f"Better {lang_code} translation if current one has issues, otherwise empty string"
        )
        language_properties[f"{lang_code}_issues"] = SchemaProperty(
            type="array",
            description=f"List of issues found for {lang_code} translation",
            items={"type": "string"}
        )

    language_properties["confidence"] = SchemaProperty(
        "number",
        "Overall confidence score 0.0-1.0",
        minimum=0.0,
        maximum=1.0
    )

    schema = Schema(
        name="MultilingualTranslationValidation",
        description="Validation of multiple translations for one word",
        properties=language_properties
    )

    # Build prompt with all translations
    translations_text = "\n".join([
        f"- {lang_code}: {trans}"
        for lang_code, trans in translations.items()
    ])

    language_names = {
        'lt': 'Lithuanian',
        'zh': 'Chinese',
        'ko': 'Korean',
        'fr': 'French',
        'sw': 'Swahili',
        'vi': 'Vietnamese'
    }

    language_list = ", ".join([language_names.get(lc, lc) for lc in translations.keys()])

    prompt = f"""Validate the following translations of the English word "{english_word}" (POS: {pos_type}):

{translations_text}

For each translation, determine:
1. Is it semantically correct for the English word?
2. Is it in lemma/dictionary form (not inflected)?
3. If there are issues, what would be a better translation?

Language guidance: Validate for {language_list}.
"""

    logger.debug(f"Validating all translations for word: '{english_word}' ({len(translations)} languages)")

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema
        )

        if response.structured_data:
            # Parse the flat structure into per-language results
            results = {}
            for lang_code in translations.keys():
                results[lang_code] = {
                    'is_correct': response.structured_data.get(f"{lang_code}_is_correct", True),
                    'is_lemma_form': response.structured_data.get(f"{lang_code}_is_lemma_form", True),
                    'suggested_translation': response.structured_data.get(f"{lang_code}_suggested", ""),
                    'issues': response.structured_data.get(f"{lang_code}_issues", []),
                    'confidence': response.structured_data.get("confidence", 0.0)
                }
            return results
        else:
            logger.error(f"No structured data received for multi-lingual validation of '{english_word}'")
            return {
                lang_code: {
                    'is_correct': True,
                    'is_lemma_form': True,
                    'suggested_translation': "",
                    'issues': ['Validation failed'],
                    'confidence': 0.0
                }
                for lang_code in translations.keys()
            }

    except Exception as e:
        logger.error(f"Error validating translations for '{english_word}': {e}")
        return {
            lang_code: {
                'is_correct': True,
                'is_lemma_form': True,
                'suggested_translation': "",
                'issues': [f'Error: {str(e)}'],
                'confidence': 0.0
            }
            for lang_code in translations.keys()
        }


def batch_validate_translations(
    translations: List[Dict[str, str]],
    model: str = "gpt-5-mini",
    confidence_threshold: float = 0.7
) -> List[Dict[str, any]]:
    """
    Validate multiple translations.

    Args:
        translations: List of dicts with 'english_word', 'translation',
                     'target_language', and 'pos_type' keys
        model: LLM model to use
        confidence_threshold: Minimum confidence to flag issues

    Returns:
        List of validation results for translations that have issues
    """
    issues = []

    for trans_info in translations:
        result = validate_translation(
            trans_info['english_word'],
            trans_info['translation'],
            trans_info['target_language'],
            trans_info['pos_type'],
            model
        )

        has_issues = (
            (not result['is_correct'] or not result['is_lemma_form'])
            and result['confidence'] >= confidence_threshold
        )

        if has_issues:
            issues.append({
                'english_word': trans_info['english_word'],
                'translation': trans_info['translation'],
                'target_language': trans_info['target_language'],
                'pos_type': trans_info['pos_type'],
                'validation': result
            })

    return issues


def validate_pronunciation(
    word: str,
    ipa_pronunciation: Optional[str],
    phonetic_pronunciation: Optional[str],
    pos_type: str,
    example_sentence: Optional[str] = None,
    definition: Optional[str] = None,
    model: str = "gpt-5-mini"
) -> Dict[str, any]:
    """
    Validate or generate pronunciations (both IPA and simplified phonetic).

    Args:
        word: The word to validate/generate pronunciation for
        ipa_pronunciation: Current IPA pronunciation (or None to generate)
        phonetic_pronunciation: Current simplified phonetic (or None to generate)
        pos_type: Part of speech
        example_sentence: Optional example sentence for context (preferred)
        definition: Optional definition text for context (used if no example sentence)
        model: LLM model to use

    Returns:
        Dictionary with validation/generation results:
        - needs_update: bool indicating if current pronunciation needs fixing
        - suggested_ipa: str with correct IPA pronunciation
        - suggested_phonetic: str with correct simplified phonetic
        - alternative_pronunciations: list of dicts with keys:
            - dialect: str (e.g., "British", "Australian")
            - ipa: str (IPA pronunciation for this dialect)
            - phonetic: str (simplified phonetic for this dialect, optional)
        - issues: list of issues found (if validating existing pronunciation)
        - confidence: float 0-1
        - notes: str with additional pronunciation notes
    """
    client = UnifiedLLMClient()

    schema = Schema(
        name="PronunciationValidation",
        description="Validation or generation of word pronunciations",
        properties={
            "needs_update": SchemaProperty("boolean", "True if the current pronunciation is incorrect or missing"),
            "suggested_ipa": SchemaProperty("string", "Correct IPA pronunciation (e.g., /ˈwɜːrd/)"),
            "suggested_phonetic": SchemaProperty("string", "Simplified phonetic pronunciation (e.g., WURD)"),
            "alternative_pronunciations": SchemaProperty(
                type="array",
                description="List of alternative pronunciations (British English, regional variations, etc.)",
                items={
                    "type": "object",
                    "properties": {
                        "dialect": {"type": "string", "description": "The dialect or variant (e.g., 'British', 'Australian', 'Southern US')"},
                        "ipa": {"type": "string", "description": "IPA pronunciation for this dialect"},
                        "phonetic": {"type": "string", "description": "Simplified phonetic pronunciation for this dialect"}
                    },
                    "required": ["dialect", "ipa", "phonetic"]
                }
            ),
            "issues": SchemaProperty(
                type="array",
                description="List of issues found with current pronunciation (if any)",
                items={"type": "string"}
            ),
            "confidence": SchemaProperty("number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0),
            "notes": SchemaProperty("string", "Additional notes about pronunciation")
        }
    )

    # Load prompt from files
    context = util.prompt_loader.get_context("wordfreq", "pronunciation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "pronunciation")

    # Build the validation/generation request with context
    # Priority: example sentence > definition > generic sentence
    if example_sentence:
        sentence = example_sentence
        context_type = "sentence"
    elif definition:
        sentence = f"Definition: {definition}"
        context_type = "definition"
    else:
        sentence = f"The word '{word}' is used here."
        context_type = "generic"

    if ipa_pronunciation or phonetic_pronunciation:
        # Validation mode
        current_info = []
        if ipa_pronunciation:
            current_info.append(f"IPA: {ipa_pronunciation}")
        if phonetic_pronunciation:
            current_info.append(f"Phonetic: {phonetic_pronunciation}")
        current_text = ", ".join(current_info)

        prompt = f"""Validate the pronunciation for the word '{word}' (POS: {pos_type}):

Current pronunciation: {current_text}

Context sentence: "{sentence}"

Check if the pronunciation is accurate and follows proper conventions:
- IPA should use correct symbols with stress markers (ˈ for primary, ˌ for secondary)
- Phonetic should be readable, hyphenated, with CAPS for stressed syllables
- Both should match American English pronunciation by default

If incorrect, provide the correct pronunciations. If correct, confirm them."""
    else:
        # Generation mode
        prompt = prompt_template.format(
            word=word,
            sentence=sentence
        )

    logger.debug(f"Validating/generating pronunciation for word: '{word}' (POS: {pos_type})")

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            context=context
        )

        if response.structured_data:
            return response.structured_data
        else:
            logger.error(f"No structured data received for pronunciation validation of '{word}'")
            return {
                'needs_update': False,
                'suggested_ipa': ipa_pronunciation or "",
                'suggested_phonetic': phonetic_pronunciation or "",
                'alternative_pronunciations': [],
                'issues': ['Validation failed'],
                'confidence': 0.0,
                'notes': ""
            }

    except Exception as e:
        logger.error(f"Error validating pronunciation for '{word}': {e}")
        return {
            'needs_update': False,
            'suggested_ipa': ipa_pronunciation or "",
            'suggested_phonetic': phonetic_pronunciation or "",
            'alternative_pronunciations': [],
            'issues': [f'Error: {str(e)}'],
            'confidence': 0.0,
            'notes': ""
        }


def generate_pronunciation(
    word: str,
    pos_type: str,
    example_sentence: Optional[str] = None,
    definition: Optional[str] = None,
    model: str = "gpt-5-mini"
) -> Dict[str, any]:
    """
    Generate both IPA and simplified phonetic pronunciations for a word.

    Args:
        word: The word to generate pronunciation for
        pos_type: Part of speech
        example_sentence: Optional example sentence for context (preferred)
        definition: Optional definition text for context (used if no example sentence)
        model: LLM model to use

    Returns:
        Dictionary with generation results:
        - ipa_pronunciation: str with IPA pronunciation
        - phonetic_pronunciation: str with simplified phonetic
        - alternative_pronunciations: list of dicts with keys:
            - dialect: str (e.g., "British", "Australian")
            - ipa: str (IPA pronunciation for this dialect)
            - phonetic: str (simplified phonetic for this dialect, optional)
        - confidence: float 0-1
        - notes: str with additional pronunciation notes
    """
    result = validate_pronunciation(
        word=word,
        ipa_pronunciation=None,
        phonetic_pronunciation=None,
        pos_type=pos_type,
        example_sentence=example_sentence,
        definition=definition,
        model=model
    )

    return {
        'ipa_pronunciation': result['suggested_ipa'],
        'phonetic_pronunciation': result['suggested_phonetic'],
        'alternative_pronunciations': result.get('alternative_pronunciations', []),
        'confidence': result['confidence'],
        'notes': result['notes']
    }
