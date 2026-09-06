#!/usr/bin/python3

"""Core word processing logic for linguistic analysis."""

import logging
import time
from typing import Any, Dict, List, Optional

from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.models.translations import Translation, TranslationSet
from wordfreq.translation import definitions
from wordfreq.translation.constants import VALID_POS_TYPES

logger = logging.getLogger(__name__)


# Base (dictionary) form per part of speech, for English. The definitions
# prompt analyses one English word per definition, so the form follows from the
# POS -- there is nothing to ask the LLM about. Language-tagged ("en_") values
# only; the untagged generic forms (verb/infinitive, noun/singular, ...) are
# deprecated because they carry no language code.
#
# The en_ members are added by _auto_extend_grammatical_form() at import time
# and are not real class attributes, so they must be looked up by name via
# GrammaticalForm[...] rather than GrammaticalForm.NAME.
EN_BASE_FORM_BY_POS: Dict[str, str] = {
    "verb": GrammaticalForm["VERB_EN_INFINITIVE"].value,
    "noun": GrammaticalForm["NOUN_EN_SINGULAR"].value,
    "adjective": GrammaticalForm["ADJ_EN_POSITIVE"].value,
    "adverb": GrammaticalForm["ADVERB_EN_POSITIVE"].value,
    "pronoun": GrammaticalForm["PRONOUN_EN_SUBJECTIVE"].value,
    "preposition": GrammaticalForm.PREPOSITION.value,
    "conjunction": GrammaticalForm.CONJUNCTION.value,
    "interjection": GrammaticalForm.INTERJECTION.value,
    "determiner": GrammaticalForm.DETERMINER.value,
    "numeral": GrammaticalForm["NUMERAL_EN_CARDINAL"].value,
    "article": GrammaticalForm["ARTICLE_EN_BASE"].value,
}

# Inflected English forms used by the suffix heuristics below.
_EN_INFLECTED = {
    name: GrammaticalForm[name].value
    for name in (
        "VERB_EN_PRESENT_PARTICIPLE",
        "VERB_EN_PAST_PARTICIPLE",
        "NOUN_EN_PLURAL",
        "ADJ_EN_COMPARATIVE",
        "ADJ_EN_SUPERLATIVE",
        "ADVERB_EN_COMPARATIVE",
        "ADVERB_EN_SUPERLATIVE",
    )
}


def determine_default_grammatical_form(word_text: str, pos_type: str, lemma_text: str) -> str:
    """
    Determine the English grammatical form for a word given its POS and lemma.

    ``query_definitions`` analyses English words and ``process_word`` records a
    single form per definition, so this is derived rather than asked for. When
    the word is its own lemma the form is the POS's base form; otherwise a few
    suffix heuristics cover the common inflections.
    """
    pos_lower = pos_type.lower()

    if word_text == lemma_text:
        return str(EN_BASE_FORM_BY_POS.get(pos_lower, GrammaticalForm.OTHER.value))

    # Basic heuristics for English inflected forms
    if pos_lower == "verb":
        if word_text.endswith("ing"):
            return str(_EN_INFLECTED["VERB_EN_PRESENT_PARTICIPLE"])
        elif word_text.endswith("ed"):
            return str(_EN_INFLECTED["VERB_EN_PAST_PARTICIPLE"])

    elif pos_lower == "noun":
        if word_text.endswith("s") and not lemma_text.endswith("s"):
            return str(_EN_INFLECTED["NOUN_EN_PLURAL"])

    elif pos_lower == "adjective":
        if word_text.endswith("er"):
            return str(_EN_INFLECTED["ADJ_EN_COMPARATIVE"])
        elif word_text.endswith("est"):
            return str(_EN_INFLECTED["ADJ_EN_SUPERLATIVE"])

    elif pos_lower == "adverb":
        if word_text.endswith("er"):
            return str(_EN_INFLECTED["ADVERB_EN_COMPARATIVE"])
        elif word_text.endswith("est"):
            return str(_EN_INFLECTED["ADVERB_EN_SUPERLATIVE"])

    return str(GrammaticalForm.OTHER.value)


def is_likely_base_form(word_text: str, lemma_text: str, pos_type: str) -> bool:
    """
    Determine if a word is likely the base form based on heuristics.
    """
    # If word matches lemma, it's likely the base form
    if word_text == lemma_text:
        return True

    # For some POS types, check specific patterns
    pos_lower = pos_type.lower()

    if pos_lower == "verb":
        # Base form for verbs is typically the infinitive
        return word_text == lemma_text
    elif pos_lower == "noun":
        # Base form for nouns is typically the singular
        return not (word_text.endswith("s") and not lemma_text.endswith("s"))
    elif pos_lower in ["adjective", "adverb"]:
        # Base form is the positive degree
        return not (word_text.endswith("er") or word_text.endswith("est"))

    # For other POS types, assume base form if it matches lemma
    return word_text == lemma_text


def process_word(
    client: Any,
    word: str,
    get_session_func: Any,
    refresh: bool = False,
    definitions_list: Optional[List[Any]] = None,
) -> bool:
    """
    Process a word to get linguistic information and store in database using new schema.

    Args:
        client: LinguisticClient instance
        word: Word token to process
        get_session_func: Function to get database session
        refresh: If True, delete existing derivative forms and re-populate the word
        definitions_list: Optional pre-fetched definitions list. If provided, skip LLM query.

    Returns:
        Success flag
    """
    session = get_session_func()
    try:
        # Add or get word token in database (assuming English)
        word_token = linguistic_db.add_word_token(session, word, "en")

        # If the word token already has derivative forms and refresh is False, return early
        if len(word_token.derivative_forms) > 0:
            if not refresh:
                logger.info(
                    f"Word token '{word}' already exists in the database with {len(word_token.derivative_forms)} derivative forms"
                )
                return True
            else:  # len(word_token.derivative_forms) > 0 and refresh
                logger.info(f"Refreshing derivative forms for word token '{word}'")
                if not linguistic_db.delete_derivative_forms_for_token(session, word_token.id):
                    logger.error(
                        f"Failed to delete existing derivative forms for word token '{word}'"
                    )
                    return False
                # Refresh the word token object after deleting derivative forms
                session.refresh(word_token)

        # Query for definitions, POS, lemmas, and examples (unless already provided)
        if definitions_list is None:
            definitions_list, success = definitions.query_definitions(
                client, word, get_session_func
            )

            if not success:
                logger.warning(f"Failed to process word '{word}'")
                return False
        else:
            # Using pre-fetched definitions
            logger.info(f"Using {len(definitions_list)} pre-fetched definition(s) for '{word}'")

        # Process each definition/form
        for def_data in definitions_list:
            # Validate POS type
            pos_type = def_data.get("pos", "unknown")
            if pos_type != "unknown" and pos_type not in VALID_POS_TYPES:
                logger.warning(
                    f"Invalid POS type '{pos_type}' for word '{word}', defaulting to 'unknown'"
                )
                pos_type = "unknown"

            # Get grammatical form, defaulting based on POS if not provided
            grammatical_form = def_data.get("grammatical_form")
            if not grammatical_form:
                grammatical_form = determine_default_grammatical_form(
                    word, pos_type, def_data.get("lemma", word)
                )

            # Validate grammatical form
            valid_forms = [form.value for form in GrammaticalForm]
            if grammatical_form not in valid_forms:
                logger.warning(
                    f"Invalid grammatical form '{grammatical_form}' for word '{word}', defaulting to 'other'"
                )
                grammatical_form = GrammaticalForm.OTHER.value

            # Determine if this is a base form
            is_base_form_flag = def_data.get("is_base_form", False)
            if not is_base_form_flag:
                is_base_form_flag = is_likely_base_form(word, def_data.get("lemma", word), pos_type)

            # Create Translation objects for each language the definitions
            # prompt returns, which is DEFINITIONS_PROMPT_LANGUAGES:
            # lt/es/es-419/fr/zh. The prompt previously also asked for Korean,
            # Swahili and Vietnamese; those dated to an older target language
            # set and are no longer requested.
            lithuanian_trans = None
            lithuanian_text = def_data.get("lithuanian_translation")
            if lithuanian_text and isinstance(lithuanian_text, str):
                lithuanian_trans = Translation(text=lithuanian_text)

            spanish_trans = None
            spanish_text = def_data.get("spanish_translation")
            if spanish_text and isinstance(spanish_text, str):
                spanish_trans = Translation(text=spanish_text)

            spanish_latam_trans = None
            spanish_latam_text = def_data.get("spanish_latam_translation")
            if spanish_latam_text and isinstance(spanish_latam_text, str):
                spanish_latam_trans = Translation(text=spanish_latam_text)

            french_trans = None
            french_text = def_data.get("french_translation")
            if french_text and isinstance(french_text, str):
                french_trans = Translation(text=french_text)

            chinese_trans = None
            chinese_text = def_data.get("chinese_translation")
            if chinese_text and isinstance(chinese_text, str):
                chinese_trans = Translation(text=chinese_text)

            # Create TranslationSet with Translation objects
            translations_set = TranslationSet(
                lithuanian=lithuanian_trans,
                spanish=spanish_trans,
                spanish_latam=spanish_latam_trans,
                french=french_trans,
                chinese=chinese_trans,
            )

            # Create complete word entry (WordToken + Lemma + DerivativeForm)
            derivative_form = linguistic_db.add_complete_word_entry(
                session=session,
                token=word,
                lemma_text=def_data.get("lemma", word),
                definition_text=def_data.get("definition", f"Definition for {word}"),
                pos_type=pos_type,
                grammatical_form=grammatical_form,
                pos_subtype=def_data.get("pos_subtype"),
                is_base_form=is_base_form_flag,
                ipa_pronunciation=def_data.get("ipa_spelling"),
                phonetic_pronunciation=def_data.get("phonetic_spelling"),
                translations=translations_set,
                confidence=def_data.get("confidence", 0.0),
                notes=def_data.get("notes"),
                sense_prominence=def_data.get("sense_prominence"),
            )

            if not derivative_form:
                logger.error(f"Failed to create derivative form for word '{word}'")
                continue

        # Commit the transaction
        session.commit()
        logger.info(
            f"Successfully processed word token '{word}' with {len(word_token.derivative_forms)} derivative forms."
        )
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing word '{word}': {e}", exc_info=True)
        return False


def process_words_batch(
    client: Any,
    word_list: List[str],
    get_session_func: Any,
    refresh: bool = False,
    throttle: float = 1.0,
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

    logger.info(
        f"Batch processing complete: {successful} successful, {failed} failed, {skipped} skipped"
    )

    return {"total": len(word_list), "successful": successful, "failed": failed, "skipped": skipped}
