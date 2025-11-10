#!/usr/bin/python3

"""Core word processing logic for linguistic analysis."""

import logging
import time
from typing import Dict, List, Any

from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.translations import Translation, TranslationSet
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.constants import VALID_POS_TYPES
from wordfreq.translation import definitions

logger = logging.getLogger(__name__)


def determine_default_grammatical_form(word_text: str, pos_type: str, lemma_text: str) -> str:
    """
    Determine a default grammatical form based on word, POS, and lemma.

    This is a heuristic fallback when the LLM doesn't provide grammatical_form.
    """
    pos_lower = pos_type.lower()

    if word_text == lemma_text:
        # Word matches lemma, likely base form
        if pos_lower == 'verb':
            return GrammaticalForm.VERB_INFINITIVE.value
        elif pos_lower == 'noun':
            return GrammaticalForm.NOUN_SINGULAR.value
        elif pos_lower == 'adjective':
            return GrammaticalForm.ADJECTIVE_POSITIVE.value
        elif pos_lower == 'adverb':
            return GrammaticalForm.ADVERB_POSITIVE.value
        elif pos_lower == 'preposition':
            return GrammaticalForm.PREPOSITION.value
        elif pos_lower == 'conjunction':
            return GrammaticalForm.CONJUNCTION.value
        elif pos_lower == 'interjection':
            return GrammaticalForm.INTERJECTION.value
        elif pos_lower == 'determiner':
            return GrammaticalForm.DETERMINER.value
        elif pos_lower == 'article':
            return GrammaticalForm.ARTICLE.value
        else:
            return GrammaticalForm.BASE_FORM.value

    # Basic heuristics for English inflected forms
    if pos_lower == 'verb':
        if word_text.endswith('ing'):
            return GrammaticalForm.VERB_PRESENT_PARTICIPLE.value  # Default to participle
        elif word_text.endswith('ed'):
            return GrammaticalForm.VERB_PAST_TENSE.value
        elif word_text.endswith('s'):
            return GrammaticalForm.VERB_PRESENT_TENSE.value

    elif pos_lower == 'noun':
        if word_text.endswith('s') and not lemma_text.endswith('s'):
            return GrammaticalForm.NOUN_PLURAL.value
        elif word_text.endswith("'s"):
            return GrammaticalForm.NOUN_POSSESSIVE_SINGULAR.value

    elif pos_lower == 'adjective':
        if word_text.endswith('er'):
            return GrammaticalForm.ADJECTIVE_COMPARATIVE.value
        elif word_text.endswith('est'):
            return GrammaticalForm.ADJECTIVE_SUPERLATIVE.value

    elif pos_lower == 'adverb':
        if word_text.endswith('er'):
            return GrammaticalForm.ADVERB_COMPARATIVE.value
        elif word_text.endswith('est'):
            return GrammaticalForm.ADVERB_SUPERLATIVE.value

    return GrammaticalForm.OTHER.value


def is_likely_base_form(word_text: str, lemma_text: str, pos_type: str) -> bool:
    """
    Determine if a word is likely the base form based on heuristics.
    """
    # If word matches lemma, it's likely the base form
    if word_text == lemma_text:
        return True

    # For some POS types, check specific patterns
    pos_lower = pos_type.lower()

    if pos_lower == 'verb':
        # Base form for verbs is typically the infinitive
        return word_text == lemma_text
    elif pos_lower == 'noun':
        # Base form for nouns is typically the singular
        return not (word_text.endswith('s') and not lemma_text.endswith('s'))
    elif pos_lower in ['adjective', 'adverb']:
        # Base form is the positive degree
        return not (word_text.endswith('er') or word_text.endswith('est'))

    # For other POS types, assume base form if it matches lemma
    return word_text == lemma_text


def process_word(
    client,
    word: str,
    get_session_func,
    refresh: bool = False
) -> bool:
    """
    Process a word to get linguistic information and store in database using new schema.

    Args:
        client: LinguisticClient instance
        word: Word token to process
        get_session_func: Function to get database session
        refresh: If True, delete existing derivative forms and re-populate the word

    Returns:
        Success flag
    """
    session = get_session_func()
    try:
        # Add or get word token in database (assuming English)
        word_token = linguistic_db.add_word_token(session, word, 'en')

        # If the word token already has derivative forms and refresh is False, return early
        if len(word_token.derivative_forms) > 0:
            if not refresh:
                logger.info(f"Word token '{word}' already exists in the database with {len(word_token.derivative_forms)} derivative forms")
                return True
            else:  # len(word_token.derivative_forms) > 0 and refresh
                logger.info(f"Refreshing derivative forms for word token '{word}'")
                if not linguistic_db.delete_derivative_forms_for_token(session, word_token.id):
                    logger.error(f"Failed to delete existing derivative forms for word token '{word}'")
                    return False
                # Refresh the word token object after deleting derivative forms
                session.refresh(word_token)

        # Query for definitions, POS, lemmas, and examples
        definitions_list, success = definitions.query_definitions(client, word, get_session_func)

        if not success:
            logger.warning(f"Failed to process word '{word}'")
            return False

        # Process each definition/form
        for def_data in definitions_list:
            # Validate POS type
            pos_type = def_data.get('pos', 'unknown')
            if pos_type != 'unknown' and pos_type not in VALID_POS_TYPES:
                logger.warning(f"Invalid POS type '{pos_type}' for word '{word}', defaulting to 'unknown'")
                pos_type = 'unknown'

            # Get grammatical form, defaulting based on POS if not provided
            grammatical_form = def_data.get('grammatical_form')
            if not grammatical_form:
                grammatical_form = determine_default_grammatical_form(word, pos_type, def_data.get('lemma', word))

            # Validate grammatical form
            valid_forms = [form.value for form in GrammaticalForm]
            if grammatical_form not in valid_forms:
                logger.warning(f"Invalid grammatical form '{grammatical_form}' for word '{word}', defaulting to 'other'")
                grammatical_form = GrammaticalForm.OTHER.value

            # Determine if this is a base form
            is_base_form_flag = def_data.get('is_base_form', False)
            if not is_base_form_flag:
                is_base_form_flag = is_likely_base_form(word, def_data.get('lemma', word), pos_type)

            # Create Translation objects for each language
            chinese_trans = None
            if def_data.get('chinese_translation'):
                chinese_trans = Translation(text=def_data.get('chinese_translation'))

            korean_trans = None
            if def_data.get('korean_translation'):
                korean_trans = Translation(text=def_data.get('korean_translation'))

            french_trans = None
            if def_data.get('french_translation'):
                french_trans = Translation(text=def_data.get('french_translation'))

            swahili_trans = None
            if def_data.get('swahili_translation'):
                swahili_trans = Translation(text=def_data.get('swahili_translation'))

            vietnamese_trans = None
            if def_data.get('vietnamese_translation'):
                vietnamese_trans = Translation(text=def_data.get('vietnamese_translation'))

            lithuanian_trans = None
            if def_data.get('lithuanian_translation'):
                lithuanian_trans = Translation(text=def_data.get('lithuanian_translation'))

            # Create TranslationSet with Translation objects
            translations_set = TranslationSet(
                chinese=chinese_trans,
                korean=korean_trans,
                french=french_trans,
                swahili=swahili_trans,
                vietnamese=vietnamese_trans,
                lithuanian=lithuanian_trans
            )

            # Create complete word entry (WordToken + Lemma + DerivativeForm)
            derivative_form = linguistic_db.add_complete_word_entry(
                session=session,
                token=word,
                lemma_text=def_data.get('lemma', word),
                definition_text=def_data.get('definition', f"Definition for {word}"),
                pos_type=pos_type,
                grammatical_form=grammatical_form,
                pos_subtype=def_data.get('pos_subtype'),
                is_base_form=is_base_form_flag,
                ipa_pronunciation=def_data.get('ipa_spelling'),
                phonetic_pronunciation=def_data.get('phonetic_spelling'),
                translations=translations_set,
                confidence=def_data.get('confidence', 0.0),
                notes=def_data.get('notes')
            )

            if not derivative_form:
                logger.error(f"Failed to create derivative form for word '{word}'")
                continue

        # Commit the transaction
        session.commit()
        logger.info(f"Successfully processed word token '{word}' with {len(word_token.derivative_forms)} derivative forms.")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing word '{word}': {e}", exc_info=True)
        return False


def process_words_batch(
    client,
    word_list: List[str],
    get_session_func,
    refresh: bool = False,
    throttle: float = 1.0
) -> Dict[str, Any]:
    """
    Process a batch of words using the new schema.

    Args:
        client: LinguisticClient instance
        word_list: List of word tokens to process
        get_session_func: Function to get database session
        refresh: Whether to refresh existing entries
        throttle: Time to wait between API calls

    Returns:
        Dictionary with processing statistics
    """
    logger.info(f"Processing batch of {len(word_list)} words")

    successful = 0
    failed = 0
    skipped = 0

    for word in word_list:
        try:
            success = process_word(client, word, get_session_func, refresh=refresh)
            if success:
                successful += 1
                logger.info(f"Successfully processed '{word}'")
            else:
                failed += 1
                logger.warning(f"Failed to process '{word}'")

            # Throttle to avoid overloading the API
            time.sleep(throttle)

        except Exception as e:
            failed += 1
            logger.error(f"Error processing '{word}': {e}")

    logger.info(f"Batch processing complete: {successful} successful, {failed} failed, {skipped} skipped")

    return {
        "total": len(word_list),
        "successful": successful,
        "failed": failed,
        "skipped": skipped
    }
