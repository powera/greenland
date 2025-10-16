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

    pos_examples = {
        'noun': 'For nouns, the lemma is singular form (e.g., "shoe" not "shoes", "child" not "children")',
        'verb': 'For verbs, the lemma is infinitive form (e.g., "eat" not "eating" or "ate")',
        'adjective': 'For adjectives, the lemma is positive form (e.g., "good" not "better" or "best")',
        'adverb': 'For adverbs, the lemma is base form (e.g., "quickly" not "more quickly")'
    }

    pos_guidance = pos_examples.get(pos_type, 'The lemma is the dictionary/base form')

    prompt = prompt_template.format(
        word=word,
        pos_type=pos_type,
        pos_guidance=pos_guidance
    )

    full_prompt = f"{context}\n\n{prompt}"

    try:
        response = client.generate_chat(
            prompt=full_prompt,
            model=model,
            json_schema=schema
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

    full_prompt = f"{context}\n\n{prompt}"

    try:
        response = client.generate_chat(
            prompt=full_prompt,
            model=model,
            json_schema=schema
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
