"""Wiktionary-based form generation as an alternative to LLM-based generation.

This module provides functions to generate derivative forms using Wiktionary
parsers instead of LLM queries. It can be used as a fallback or primary source
for form generation.

Supported languages:
- English (en): nouns, verbs, adjectives, adverbs
- Spanish (es): nouns, verbs, adjectives, adverbs
- French (fr): nouns, verbs
- Lithuanian (lt): nouns, verbs, adjectives, adverbs
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from wordfreq.storage import database as linguistic_db
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.connection_pool import get_session
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.translation.generate_forms_base import FormGenerationConfig

logger = logging.getLogger(__name__)


def _get_english_wiktionary_forms(word: str, pos_type: str) -> Tuple[Dict[str, str], bool]:
    """Get English forms from Wiktionary."""
    from langtools.en.wiktionary import EnglishParser

    parser = EnglishParser()
    result: Any  # Result type varies by POS
    if pos_type == "noun":
        result, success = parser.get_noun_declensions(word)
    elif pos_type == "verb":
        result, success = parser.get_verb_conjugations(word)
    elif pos_type == "adjective":
        result, success = parser.get_adjective_declensions(word)
    elif pos_type == "adverb":
        result, success = parser.get_adverb_forms(word)
    else:
        return {}, False
    return result.forms, success


def _get_spanish_wiktionary_forms(word: str, pos_type: str) -> Tuple[Dict[str, str], bool]:
    """Get Spanish forms from Wiktionary."""
    from langtools.es.wiktionary import SpanishParser

    parser = SpanishParser()
    result: Any  # Result type varies by POS
    if pos_type == "noun":
        result, success = parser.get_noun_declensions(word)
    elif pos_type == "verb":
        result, success = parser.get_verb_conjugations(word)
    elif pos_type == "adjective":
        result, success = parser.get_adjective_declensions(word)
    elif pos_type == "adverb":
        result, success = parser.get_adverb_forms(word)
    else:
        return {}, False
    return result.forms, success


def _get_french_wiktionary_forms(word: str, pos_type: str) -> Tuple[Dict[str, str], bool]:
    """Get French forms from Wiktionary."""
    from langtools.fr.wiktionary import FrenchParser

    parser = FrenchParser()
    result: Any  # Result type varies by POS
    if pos_type == "noun":
        result, success = parser.get_noun_declensions(word)
    elif pos_type == "verb":
        result, success = parser.get_verb_conjugations(word)
    else:
        return {}, False
    return result.forms, success


def _get_lithuanian_wiktionary_forms(word: str, pos_type: str) -> Tuple[Dict[str, str], bool]:
    """Get Lithuanian forms from Wiktionary."""
    from langtools.lt.wiktionary import LithuanianParser

    parser = LithuanianParser()
    result: Any  # Result type varies by POS
    if pos_type == "noun":
        result, success = parser.get_noun_declensions(word)
    elif pos_type == "verb":
        result, success = parser.get_verb_conjugations(word)
    elif pos_type == "adjective":
        result, success = parser.get_adjective_declensions(word)
    elif pos_type == "adverb":
        result, success = parser.get_adverb_forms(word)
    else:
        return {}, False
    return result.forms, success


# Mapping from Wiktionary form names to the form names expected by LLM tasks
# This allows Wiktionary output to be processed by the same storage logic

# English verb: Wiktionary returns 5 canonical forms; map the ones that
# correspond to person/tense slots through the task form_mapping, and map
# the rest (infinitive, participles) directly to GrammaticalForm values
# via WIKTIONARY_DIRECT_FORMS below.
ENGLISH_VERB_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "3s_present": "3s_present",
    "past": "3s_past",  # English simple past is the same for all persons
}

# English noun: Keys match directly
ENGLISH_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular": "singular",
    "plural": "plural",
}

# English adjective/adverb: Keys match directly
ENGLISH_ADJ_ADV_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "positive": "positive",
    "comparative": "comparative",
    "superlative": "superlative",
}

# Spanish noun: Keys match directly
SPANISH_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular": "singular",
    "plural": "plural",
}

# Spanish adjective: Keys match directly
SPANISH_ADJ_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular_m": "singular_m",
    "singular_f": "singular_f",
    "plural_m": "plural_m",
    "plural_f": "plural_f",
}

# Spanish adverb: Keys match directly
SPANISH_ADVERB_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "positive": "positive",
    "comparative": "comparative",
    "superlative": "superlative",
}

# French noun: Keys match directly
FRENCH_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular": "singular",
    "plural": "plural",
}

# Lithuanian noun: Wiktionary returns full case names
LITHUANIAN_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "nominative_singular": "nominative_singular",
    "nominative_plural": "nominative_plural",
    "genitive_singular": "genitive_singular",
    "genitive_plural": "genitive_plural",
    "dative_singular": "dative_singular",
    "dative_plural": "dative_plural",
    "accusative_singular": "accusative_singular",
    "accusative_plural": "accusative_plural",
    "instrumental_singular": "instrumental_singular",
    "instrumental_plural": "instrumental_plural",
    "locative_singular": "locative_singular",
    "locative_plural": "locative_plural",
    "vocative_singular": "vocative_singular",
    "vocative_plural": "vocative_plural",
}

# Lithuanian adjective: Limited forms from Wiktionary
LITHUANIAN_ADJ_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "nominative_singular_m": "nominative_singular_m",
    "nominative_singular_f": "nominative_singular_f",
    "nominative_plural_m": "nominative_plural_m",
    "nominative_plural_f": "nominative_plural_f",
}

# Lithuanian adverb: Keys match
LITHUANIAN_ADVERB_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "positive": "positive",
    "comparative": "comparative",
    "superlative": "superlative",
}


# Registry of Wiktionary-to-task mappings
WIKTIONARY_TO_TASK_MAPPINGS: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        "noun": ENGLISH_NOUN_WIKTIONARY_TO_TASK,
        "verb": ENGLISH_VERB_WIKTIONARY_TO_TASK,
        "adjective": ENGLISH_ADJ_ADV_WIKTIONARY_TO_TASK,
        "adverb": ENGLISH_ADJ_ADV_WIKTIONARY_TO_TASK,
    },
    "es": {
        "noun": SPANISH_NOUN_WIKTIONARY_TO_TASK,
        "verb": {},  # Spanish verb conjugation is complex, not yet mapped
        "adjective": SPANISH_ADJ_WIKTIONARY_TO_TASK,
        "adverb": SPANISH_ADVERB_WIKTIONARY_TO_TASK,
    },
    "fr": {
        "noun": FRENCH_NOUN_WIKTIONARY_TO_TASK,
        "verb": {},  # French verb conjugation is complex, not yet mapped
    },
    "lt": {
        "noun": LITHUANIAN_NOUN_WIKTIONARY_TO_TASK,
        "verb": {},  # Lithuanian verb conjugation is complex, not yet mapped
        "adjective": LITHUANIAN_ADJ_WIKTIONARY_TO_TASK,
        "adverb": LITHUANIAN_ADVERB_WIKTIONARY_TO_TASK,
    },
}


# Direct Wiktionary-to-GrammaticalForm mappings for forms that don't exist
# in the LLM task form_mapping (e.g., infinitive, participles).  These are
# looked up as a fallback when the Wiktionary key isn't found via the
# task-key-based path.
WIKTIONARY_DIRECT_FORMS: Dict[str, Dict[str, Dict[str, GrammaticalForm]]] = {
    "en": {
        "verb": {
            "infinitive": GrammaticalForm.VERB_INFINITIVE,
            "past_participle": GrammaticalForm.VERB_PAST_PARTICIPLE,
            "present_participle": GrammaticalForm.VERB_PRESENT_PARTICIPLE,
        },
    },
}


def get_wiktionary_forms(
    word: str, language_code: str, pos_type: str
) -> Tuple[Dict[str, str], bool]:
    """
    Get forms for a word from Wiktionary.

    Args:
        word: The word to look up
        language_code: Language code (en, es, fr, lt)
        pos_type: Part of speech (noun, verb, adjective, adverb)

    Returns:
        Tuple of (forms dict, success flag)
    """
    forms: Dict[str, str] = {}
    success = False

    try:
        if language_code == "en":
            forms, success = _get_english_wiktionary_forms(word, pos_type)
        elif language_code == "es":
            forms, success = _get_spanish_wiktionary_forms(word, pos_type)
        elif language_code == "fr":
            forms, success = _get_french_wiktionary_forms(word, pos_type)
        elif language_code == "lt":
            forms, success = _get_lithuanian_wiktionary_forms(word, pos_type)
        else:
            logger.warning(f"Wiktionary parsing not supported for language: {language_code}")

        return forms, success

    except Exception as e:
        logger.error(f"Error fetching Wiktionary forms for '{word}' ({language_code}): {e}")
        return {}, False


def process_lemma_forms_wiktionary(
    lemma_id: int,
    data_config: DataSourceConfig,
    form_config: FormGenerationConfig,
) -> bool:
    """
    Process and store forms for a single lemma using Wiktionary.

    This is the Wiktionary equivalent of process_lemma_forms from generate_forms_base.py.

    Args:
        lemma_id: ID of the lemma to process
        data_config: DataSourceConfig with database configuration
        form_config: FormGenerationConfig with language and form settings

    Returns:
        True if successful, False otherwise
    """
    session = get_session(data_config)

    try:
        lemma = (
            session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        )

        if not lemma:
            logger.error(f"Lemma ID {lemma_id} not found")
            return False

        # Determine the word to look up
        if form_config.language_code == "en":
            # For English, use the lemma text directly
            word = lemma.lemma_text
        else:
            # For other languages, get the translation
            word = get_translation(session, lemma, form_config.language_code)
            if not word:
                logger.warning(
                    f"No {form_config.language_code} translation for lemma ID {lemma_id}"
                )
                return False

        # Check if forms already exist
        existing_forms = (
            session.query(linguistic_db.DerivativeForm)
            .filter(
                linguistic_db.DerivativeForm.lemma_id == lemma_id,
                linguistic_db.DerivativeForm.language_code == form_config.language_code,
            )
            .all()
        )

        existing_grammatical_forms = {f.grammatical_form for f in existing_forms}
        expected_grammatical_forms = {g.value for g in form_config.form_mapping.values()}
        existing_count = len(existing_grammatical_forms & expected_grammatical_forms)

        if existing_count >= form_config.min_forms_threshold:
            logger.info(
                f"Lemma ID {lemma_id} already has {existing_count} "
                f"{form_config.language_name} forms, skipping"
            )
            return True

        # Get forms from Wiktionary
        wiktionary_forms, success = get_wiktionary_forms(
            word, form_config.language_code, form_config.pos_type
        )

        if not success or not wiktionary_forms:
            logger.warning(f"No Wiktionary forms found for '{word}' (lemma ID {lemma_id})")
            return False

        # Get the mapping from Wiktionary keys to task keys
        wiktionary_to_task = WIKTIONARY_TO_TASK_MAPPINGS.get(form_config.language_code, {}).get(
            form_config.pos_type, {}
        )

        # Get direct GrammaticalForm mappings for forms that aren't in the
        # LLM task form_mapping (e.g., infinitive, participles)
        direct_forms = WIKTIONARY_DIRECT_FORMS.get(form_config.language_code, {}).get(
            form_config.pos_type, {}
        )

        # Store each form
        stored = 0
        skipped = 0

        for wiktionary_key, form_text in wiktionary_forms.items():
            if not form_text or not form_text.strip():
                logger.debug(f"Skipping empty form: {wiktionary_key}")
                continue

            # First, check if this form has a direct GrammaticalForm mapping
            # (for forms like infinitive, participles that don't fit person/tense slots)
            grammatical_form_enum: Optional[GrammaticalForm] = None
            is_base = False

            if wiktionary_key in direct_forms:
                grammatical_form_enum = direct_forms[wiktionary_key]
                is_base = wiktionary_key == form_config.base_form_identifier
            else:
                # Map Wiktionary key to task key, then look up in form_mapping
                task_key = wiktionary_to_task.get(wiktionary_key, wiktionary_key)
                if task_key in form_config.form_mapping:
                    grammatical_form_enum = form_config.form_mapping[task_key]
                    is_base = task_key == form_config.base_form_identifier

            if grammatical_form_enum is None:
                logger.debug(f"Form key '{wiktionary_key}' has no mapping, skipping")
                continue

            grammatical_form_value = grammatical_form_enum.value

            # Check if this specific form already exists
            if grammatical_form_value in existing_grammatical_forms:
                logger.debug(
                    f"Form '{wiktionary_key}' already exists for lemma ID {lemma_id}, skipping"
                )
                skipped += 1
                continue

            # Get or create word token
            word_token = linguistic_db.add_word_token(session, form_text, form_config.language_code)

            # Create derivative form
            session.add(
                linguistic_db.DerivativeForm(
                    lemma_id=lemma_id,
                    derivative_form_text=form_text,
                    word_token_id=word_token.id,
                    language_code=form_config.language_code,
                    grammatical_form=grammatical_form_value,
                    is_base_form=is_base,
                    verified=False,
                    notes="Generated from Wiktionary",
                )
            )
            stored += 1

        session.commit()
        logger.info(
            f"Added {stored} Wiktionary forms for lemma ID {lemma_id} "
            f"('{word}', {form_config.language_code})"
        )
        return stored > 0

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id} with Wiktionary: {e}", exc_info=True)
        return False


def is_wiktionary_supported(language_code: str, pos_type: str) -> bool:
    """
    Check if Wiktionary-based form generation is supported for a language/POS combination.

    Args:
        language_code: Language code
        pos_type: Part of speech type

    Returns:
        True if supported, False otherwise
    """
    mapping = WIKTIONARY_TO_TASK_MAPPINGS.get(language_code, {}).get(pos_type, {})
    # Empty mapping means verb conjugation not yet mapped
    return language_code in WIKTIONARY_TO_TASK_MAPPINGS and (
        pos_type in WIKTIONARY_TO_TASK_MAPPINGS.get(language_code, {}) and len(mapping) > 0
    )


def get_supported_wiktionary_tasks() -> Dict[str, List[str]]:
    """
    Get a dictionary of supported Wiktionary tasks by language.

    Returns:
        Dictionary mapping language codes to list of supported POS types
    """
    result: Dict[str, List[str]] = {}
    for lang, pos_types in WIKTIONARY_TO_TASK_MAPPINGS.items():
        supported_pos = [pos for pos, mapping in pos_types.items() if mapping]
        if supported_pos:
            result[lang] = supported_pos
    return result
