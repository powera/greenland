"""Workqueue handler for grammar fact generation tasks.

This module implements the core grammar fact generation logic that is shared
between the Barsukas task worker and the LapeAgent CLI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from agents.common.wq_tools import build_default_config, get_lemma_or_raise
import constants
import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from sqlalchemy.orm import Session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

# Language-specific gender systems configuration
GENDER_SYSTEMS = {
    "fr": {
        "name": "French",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
    "lt": {
        "name": "Lithuanian",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
    "es": {
        "name": "Spanish",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
    "de": {
        "name": "German",
        "genders": ["masculine", "feminine", "neuter"],
        "description": "3-way system (masculine/feminine/neuter)",
    },
    "pt": {
        "name": "Portuguese",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
    "ru": {
        "name": "Russian",
        "genders": ["masculine", "feminine", "neuter"],
        "description": "3-way system (masculine/feminine/neuter)",
    },
    "it": {
        "name": "Italian",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
}

# Supported fact types and their configuration
SUPPORTED_FACT_TYPES = {
    "measure_words": {
        "languages": ["zh"],
        "required_pos": ["noun"],
        "description": "Generate Chinese measure words/classifiers for nouns",
    },
    "grammatical_gender": {
        "languages": list(GENDER_SYSTEMS.keys()),
        "required_pos": ["noun"],
        "description": "Determine grammatical gender (masculine, feminine, neuter)",
    },
    "verb_transitivity": {
        "languages": ["en"],
        "required_pos": ["verb"],
        "description": "Classify verbs as transitive, intransitive, ditransitive, or ambitransitive",
    },
    "countability": {
        "languages": ["en"],
        "required_pos": ["noun"],
        "description": "Classify nouns as countable, uncountable, or both",
    },
    "animacy": {
        "languages": ["en"],
        "required_pos": ["noun"],
        "description": "Classify nouns as animate or inanimate",
    },
}


def _get_llm_client(config: DataSourceConfig) -> UnifiedLLMClient:
    """Get LLM client for queries."""
    client = UnifiedLLMClient.from_config(config)
    if config.model:
        client.warm_model(config.model)
    return client


def generate_measure_words(
    lemma: Lemma,
    chinese_translation: str,
    config: DataSourceConfig,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate Chinese measure word(s) for a noun using LLM.

    Returns:
        Tuple of (measure_word, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        return None, None, 0.0

    try:
        context = util.prompt_loader.get_context("wordfreq", "measure_words")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "measure_words")
    except Exception as e:
        logger.error(f"Failed to load measure_words prompts: {e}")
        return None, None, 0.0

    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        chinese_translation=chinese_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )

    schema = Schema(
        name="MeasureWordGeneration",
        description="Generate Chinese measure words/classifiers for nouns",
        properties={
            "primary_measure_word": SchemaProperty(
                "string", "The primary/most common measure word"
            ),
            "alternative_measure_words": SchemaProperty(
                "array",
                "List of alternative measure words that can also be used",
                items={"type": "string"},
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of why this measure word is appropriate"
            ),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )

    try:
        client = _get_llm_client(config)
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

        if not response.structured_data:
            return None, None, 0.0

        result = response.structured_data
        measure_word = result.get("primary_measure_word")
        alternatives = result.get("alternative_measure_words", [])
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        if alternatives:
            measure_word = f"{measure_word} (alt: {', '.join(alternatives)})"

        return measure_word, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate measure word for '{lemma.lemma_text}': {e}")
        return None, None, 0.0


def generate_grammatical_gender(
    lemma: Lemma,
    target_translation: str,
    language_code: str,
    config: DataSourceConfig,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate grammatical gender for a noun using LLM.

    Returns:
        Tuple of (gender, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        return None, None, 0.0

    if language_code not in GENDER_SYSTEMS:
        return None, None, 0.0

    gender_config = GENDER_SYSTEMS[language_code]
    language_name = gender_config["name"]
    valid_genders = ", ".join(gender_config["genders"])
    gender_system = gender_config["description"]

    try:
        context = util.prompt_loader.get_context("wordfreq", "grammatical_gender")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "grammatical_gender")
    except Exception as e:
        logger.error(f"Failed to load grammatical_gender prompts: {e}")
        return None, None, 0.0

    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
        gender_system=gender_system,
        valid_genders=valid_genders,
    )

    schema = Schema(
        name="GrammaticalGenderGeneration",
        description=f"Determine grammatical gender for {language_name} nouns",
        properties={
            "gender": SchemaProperty(
                "string",
                f"The grammatical gender: {valid_genders}",
                enum=list(gender_config["genders"]),
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of why this gender is correct"
            ),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )

    try:
        client = _get_llm_client(config)
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

        if not response.structured_data:
            return None, None, 0.0

        result = response.structured_data
        gender = result.get("gender")
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        return gender, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate gender for '{lemma.lemma_text}': {e}")
        return None, None, 0.0


def validate_grammar_fact_request(
    lemma: Lemma,
    fact_type: str,
    language_code: str,
    session: Session,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate that grammar fact generation can proceed.

    Args:
        lemma: Lemma to validate
        fact_type: Type of grammar fact
        language_code: Target language code
        session: Database session

    Returns:
        Tuple of (is_valid, error_message, translation)
    """
    if fact_type not in SUPPORTED_FACT_TYPES:
        return False, f"Unsupported fact type: {fact_type}", None

    fact_config = SUPPORTED_FACT_TYPES[fact_type]

    if language_code not in fact_config["languages"]:
        return False, f'Fact type "{fact_type}" does not support language "{language_code}"', None

    if lemma.pos_type not in fact_config["required_pos"]:
        return (
            False,
            f'This word is a {lemma.pos_type}. {fact_type} only works with: {", ".join(fact_config["required_pos"])}',
            None,
        )

    # Get translation for target language
    translation = get_translation(session, lemma, language_code)
    if not translation or not translation.strip():
        return False, f"No {language_code} translation found for this lemma", None

    return True, None, translation


def generate_grammar_fact_for_lemma(
    session: Session,
    lemma: Lemma,
    fact_type: str,
    language_code: str,
    config: Optional[DataSourceConfig] = None,
    min_confidence: float = 0.7,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    """
    Generate a grammar fact for a single lemma.

    This is the core grammar fact generation logic shared by both the workqueue
    handler and the LapeAgent.

    Args:
        session: Database session
        lemma: Lemma to generate fact for
        fact_type: Type of grammar fact to generate
        language_code: Target language code
        config: DataSourceConfig (uses default if not provided)
        min_confidence: Minimum confidence to save the fact
        skip_existing: Skip if fact already exists

    Returns:
        Dictionary with generation results
    """
    if config is None:
        config = build_default_config()

    # Check if fact already exists
    if skip_existing:
        existing_fact = get_grammar_fact_value(session, lemma.id, language_code, fact_type)
        if existing_fact is not None:
            return {
                "skipped": True,
                "reason": "existing",
                "existing_value": existing_fact,
                "lemma_id": lemma.id,
                "fact_type": fact_type,
                "language_code": language_code,
            }

    # Validate request
    is_valid, error, translation = validate_grammar_fact_request(
        lemma, fact_type, language_code, session
    )
    if not is_valid:
        return {
            "error": error,
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
        }

    # Generate fact based on type
    # translation is guaranteed to be non-None here due to validation check above
    assert translation is not None
    if fact_type == "measure_words":
        fact_value, notes, confidence = generate_measure_words(lemma, translation, config)
    elif fact_type == "grammatical_gender":
        fact_value, notes, confidence = generate_grammatical_gender(
            lemma, translation, language_code, config
        )
    else:
        return {
            "error": f"Handler not yet implemented for fact type: {fact_type}",
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
        }

    if not fact_value or confidence < min_confidence:
        return {
            "error": f"Could not generate {fact_type} with sufficient confidence (got {confidence:.2f}, need >= {min_confidence})",
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
            "confidence": confidence,
        }

    # Save to database
    add_grammar_fact(
        session,
        lemma_id=lemma.id,
        language_code=language_code,
        fact_type=fact_type,
        fact_value=fact_value,
        notes=notes,
        verified=False,
    )

    # Log operation
    log_operation(
        session,
        operation_type="grammar_fact_generated",
        entity_type="grammar_fact",
        entity_id=lemma.id,
        details={
            "fact_type": fact_type,
            "language_code": language_code,
            "fact_value": fact_value,
            "confidence": confidence,
            "agent": "lape",
            "model": config.model,
        },
    )

    return {
        "success": True,
        "lemma_id": lemma.id,
        "fact_type": fact_type,
        "language_code": language_code,
        "fact_value": fact_value,
        "notes": notes,
        "confidence": confidence,
        "translation": translation,
    }


def handle_generate_grammar_fact(session: Session, payload: Dict) -> str:
    """
    Handle grammar fact generation task (workqueue entry point).

    Payload schema:
        lemma_id: int - ID of the lemma to generate fact for
        fact_type: str - Type of grammar fact (e.g., "measure_words", "grammatical_gender")
        language_code: str - Target language code

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    fact_type = payload["fact_type"]
    language_code = payload["language_code"]

    lemma = get_lemma_or_raise(session, lemma_id)

    result = generate_grammar_fact_for_lemma(session, lemma, fact_type, language_code)

    session.commit()

    if result.get("skipped"):
        return f"Skipped: {fact_type} already exists ({result.get('existing_value')})"

    if result.get("error"):
        raise RuntimeError(result["error"])

    return f"Generated {fact_type}: {result['fact_value']} (confidence: {result['confidence']:.2f})"
