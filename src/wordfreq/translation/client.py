#!/usr/bin/python3

"""Client for querying LLMs for linguistic information about words."""

import json
import logging
import time
import threading
from typing import Dict, List, Optional, Any, Tuple

import clients.lib
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
import util.prompt_loader
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.translations import Translation, TranslationSet
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.connection_pool import get_session, close_thread_sessions
import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Common model information
DEFAULT_MODEL = constants.DEFAULT_MODEL
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds

# Valid parts of speech
VALID_POS_TYPES = {
    "noun", "verb", "adjective", "adverb", "pronoun", 
    "preposition", "conjunction", "interjection", "determiner",
    "article", "numeral", "auxiliary", "modal"
}

class LinguisticClient:
    """Client for querying LLMs for linguistic information."""

    # Thread-local storage for client instances
    _thread_local = threading.local()
    # Lock for thread safety
    _lock = threading.Lock()

    def __init__(self, model: str = DEFAULT_MODEL, db_path: str = None, debug: bool = False):
        """
        Initialize client with model and database path.

        Args:
            model: Model name to use for queries
            db_path: Path to the SQLite database, or None to use default
            debug: Whether to enable debug logging
        """
        self.model = model
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.client = UnifiedLLMClient(debug=debug)

        if debug:
            logger.setLevel(logging.DEBUG)

        # Warm up the model
        try:
            self.client.warm_model(model)
            logger.info(f"Model {model} warmed up successfully")
        except Exception as e:
            logger.warning(f"Failed to warm up model {model}: {e}")

    @classmethod
    def get_instance(cls, model: str = DEFAULT_MODEL, db_path: str = None, debug: bool = False) -> 'LinguisticClient':
        """
        Get a thread-local instance of the LinguisticClient.

        This method ensures that each thread gets its own client instance.

        Args:
            model: Model name to use for queries
            db_path: Path to the SQLite database, or None to use default
            debug: Whether to enable debug logging

        Returns:
            Thread-local LinguisticClient instance
        """
        if not hasattr(cls._thread_local, 'instance'):
            with cls._lock:
                # Initialize the thread-local instance
                cls._thread_local.instance = cls(model=model, db_path=db_path, debug=debug)
                logger.debug(f"Created new LinguisticClient for thread {threading.current_thread().name}")
        return cls._thread_local.instance

    def get_session(self):
        """
        Get a thread-local database session.

        Returns:
            Thread-local database session
        """
        return get_session(self.db_path, echo=self.debug)

    def query_definitions(self, word: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Query LLM for definitions, POS, and lemma information.

        Args:
            word: Word to analyze

        Returns:
            Tuple of (list of definition data, success flag)
        """
        if not word or not isinstance(word, str):
            logger.error("Invalid word parameter provided")
            return [], False

        # Get valid grammatical forms for the schema
        valid_grammatical_forms = [form.value for form in GrammaticalForm]

        schema = Schema(
            name="WordDefinitions",
            description="Definitions and forms for a word",
            properties={
                "definitions": SchemaProperty(
                    type="array",
                    description="List of definitions and forms for the word",
                    array_items_schema=Schema(
                        name="WordForm",
                        description="A single form/definition of the word",
                        properties={
                            "definition": SchemaProperty("string", "The definition of the word for this specific meaning"),
                            "pos": SchemaProperty("string", "The part of speech for this definition (noun, verb, etc.)", enum=list(VALID_POS_TYPES)),
                            "pos_subtype": SchemaProperty("string", "A subtype for the part of speech", enum=linguistic_db.get_all_pos_subtypes()),
                            "lemma": SchemaProperty("string", "The base form (lemma) for this definition"),
                            "grammatical_form": SchemaProperty("string", "The specific grammatical form (e.g., verb/infinitive, noun/plural)", enum=valid_grammatical_forms),
                            "is_base_form": SchemaProperty("boolean", "Whether this is the base form (infinitive, singular, etc.)"),
                            "phonetic_spelling": SchemaProperty("string", "Phonetic spelling of the word"),
                            "ipa_spelling": SchemaProperty("string", "International Phonetic Alphabet for the word"),
                            "special_case": SchemaProperty("boolean", "Whether this is a special case (foreign word, part of name, etc.)"),
                            "examples": SchemaProperty(
                                type="array",
                                description="Example sentences using this specific form",
                                items={"type": "string", "description": "Example sentence using this form"}
                            ),
                            "notes": SchemaProperty("string", "Additional notes about this form"),
                            "chinese_translation": SchemaProperty("string", "The Chinese translation of this form"),
                            "korean_translation": SchemaProperty("string", "The Korean translation of this form"),
                            "french_translation": SchemaProperty("string", "The French translation of this form"),
                            "swahili_translation": SchemaProperty("string", "The Swahili translation of this form"),
                            "vietnamese_translation": SchemaProperty("string", "The Vietnamese translation of this form"),
                            "lithuanian_translation": SchemaProperty("string", "The Lithuanian translation of this form"),
                            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
                        }
                    )
                )
            }
        )

        context = util.prompt_loader.get_context("wordfreq", "definitions")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "definitions")
        prompt = prompt_template.format(word=word)

        try:
            # Make a single API call without retries
            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Log successful query
            session = self.get_session()
            try:
                linguistic_db.log_query(
                    session,
                    word=word,
                    query_type='definitions',
                    prompt=prompt,
                    response=json.dumps(response.structured_data),
                    model=self.model
                )
            except Exception as log_err:
                logger.error(f"Failed to log successful query: {log_err}")

            # Validate and return response data
            if (response.structured_data and 
                isinstance(response.structured_data, dict) and 
                'definitions' in response.structured_data and 
                isinstance(response.structured_data['definitions'], list)):
                return response.structured_data['definitions'], True
            else:
                logger.warning(f"Invalid response format for word '{word}'")
                return [], False

        except Exception as e:
            # More specific error logging
            logger.error(f"Error querying definitions for '{word}': {type(e).__name__}: {e}")

            return [], False

    # Define major parts of speech as a set for efficient lookup
    MAJOR_POS_TYPES = {"noun", "verb", "adjective", "adverb"}

    def process_word(self, word: str, refresh: bool = False) -> bool:
        """
        Process a word to get linguistic information and store in database using new schema.

        Args:
            word: Word token to process
            refresh: If True, delete existing derivative forms and re-populate the word

        Returns:
            Success flag
        """
        session = self.get_session()
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
            definitions, success = self.query_definitions(word)

            if not success:
                logger.warning(f"Failed to process word '{word}'")
                return False

            # Process each definition/form
            for def_data in definitions:
                # Validate POS type
                pos_type = def_data.get('pos', 'unknown')
                if pos_type != 'unknown' and pos_type not in VALID_POS_TYPES:
                    logger.warning(f"Invalid POS type '{pos_type}' for word '{word}', defaulting to 'unknown'")
                    pos_type = 'unknown'

                # Get grammatical form, defaulting based on POS if not provided
                grammatical_form = def_data.get('grammatical_form')
                if not grammatical_form:
                    grammatical_form = self._determine_default_grammatical_form(word, pos_type, def_data.get('lemma', word))

                # Validate grammatical form
                valid_forms = [form.value for form in GrammaticalForm]
                if grammatical_form not in valid_forms:
                    logger.warning(f"Invalid grammatical form '{grammatical_form}' for word '{word}', defaulting to 'other'")
                    grammatical_form = GrammaticalForm.OTHER.value

                # Determine if this is a base form
                is_base_form = def_data.get('is_base_form', False)
                if not is_base_form:
                    is_base_form = self._is_likely_base_form(word, def_data.get('lemma', word), pos_type)

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
                translations = TranslationSet(
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
                    is_base_form=is_base_form,
                    ipa_pronunciation=def_data.get('ipa_spelling'),
                    phonetic_pronunciation=def_data.get('phonetic_spelling'),
                    translations=translations,
                    confidence=def_data.get('confidence', 0.0),
                    notes=def_data.get('notes')
                )

                if not derivative_form:
                    logger.error(f"Failed to create derivative form for word '{word}'")
                    continue

                # Add example sentences
                for example_text in def_data.get('examples', []):
                    linguistic_db.add_example_sentence(
                        session,
                        derivative_form,
                        example_text=example_text
                    )

            # Commit the transaction
            session.commit()
            logger.info(f"Successfully processed word token '{word}' with {len(word_token.derivative_forms)} derivative forms.")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing word '{word}': {e}", exc_info=True)
            return False

    def _determine_default_grammatical_form(self, word_text: str, pos_type: str, lemma_text: str) -> str:
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

    def _is_likely_base_form(self, word_text: str, lemma_text: str, pos_type: str) -> bool:
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

    def query_chinese_translation(self, word: str, definition: str, example: str) -> Tuple[str, bool]:
        """
        Query LLM for a Chinese translation of a specific word definition.

        DEPRECATED: Use query_definitions() instead, which returns translations
        for all languages in a single call.

        Args:
            word: The English word to translate
            definition: The specific definition of the word
            example: An example sentence using the word

        Returns:
            Tuple of (translation string, success flag)
        """
        import warnings
        warnings.warn(
            "query_chinese_translation() is deprecated. Use query_definitions() instead, "
            "which returns translations for all languages in a single call.",
            DeprecationWarning,
            stacklevel=2
        )

        if not word or not isinstance(word, str):
            logger.error("Invalid word parameter provided")
            return "", False

        schema = clients.lib.Schema(
            name = "ChineseTranslation",
            description= "Response schema for a Chinese translation",
            properties={
                "chinese_translation": clients.lib.SchemaProperty(
                    type="string",
                    description="The Chinese translation (preferably two characters when possible)"
                ),
                "pinyin": clients.lib.SchemaProperty(
                    type="string",
                    description="The pinyin pronunciation of the Chinese translation"
                ),
                "confidence": clients.lib.SchemaProperty(
                    type="number",
                    description="Confidence score from 0-1"
                ),
                "notes": clients.lib.SchemaProperty(
                    type="string",
                    description="Additional notes about this translation"
                )
            })

        context = util.prompt_loader.get_context("wordfreq", "chinese_translation")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "chinese_translation")
        prompt = prompt_template.format(word=word, definition=definition, example=example)

        try:
            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Log successful query
            session = self.get_session()
            try:
                linguistic_db.log_query(
                    session,
                    word=word,
                    query_type='chinese_translation',
                    prompt=prompt,
                    response=json.dumps(response.structured_data),
                    model=self.model
                )
            except Exception as log_err:
                logger.error(f"Failed to log successful translation query: {log_err}")

            # Validate and return response data
            if (response.structured_data and 
                isinstance(response.structured_data, dict) and 
                'chinese_translation' in response.structured_data):
                return response.structured_data['chinese_translation'], True
            else:
                logger.warning(f"Invalid translation response format for word '{word}'")
                return "", False

        except Exception as e:
            # More specific error logging
            logger.error(f"Error querying Chinese translation for '{word}': {type(e).__name__}: {e}")

            return "", False

    def query_word_forms(self, lemma: str, pos_type: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Query LLM for all forms of a lemma based on its part of speech.

        Args:
            lemma: The base form of the word (lemma)
            pos_type: Part of speech (noun, verb, adjective, adverb)

        Returns:
            Tuple of (list of word forms data, success flag)
        """
        if not lemma or not isinstance(lemma, str) or not pos_type or not isinstance(pos_type, str):
            logger.error("Invalid lemma or pos_type parameter provided")
            return [], False

        schema = Schema(
            name="WordForms",
            description="All forms of a lemma based on its part of speech",
            properties={
                "word_forms": SchemaProperty(
                    type="array",
                    description="List of word forms",
                    array_items_schema=Schema(
                        name="WordForm",
                        description="A single word form",
                        properties={
                            "form": SchemaProperty("string", "The inflected form of the word"),
                            "form_type": SchemaProperty("string", "The grammatical form (e.g., past tense, plural, comparative)"),
                            "examples": SchemaProperty(
                                type="array",
                                description="Example sentences using this word form",
                                items={"type": "string", "description": "Example sentence using this word form"}
                            )
                        }
                    )
                )
            }
        )

        context = util.prompt_loader.get_context("wordfreq", "word_forms")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "word_forms")
        prompt = prompt_template.format(pos_type=pos_type, lemma=lemma)

        try:
            # Make a single API call without retries
            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Log successful query
            session = self.get_session()
            try:
                linguistic_db.log_query(
                    session,
                    word=lemma,
                    query_type='word_forms',
                    prompt=prompt,
                    response=json.dumps(response.structured_data),
                    model=self.model
                )
            except Exception as log_err:
                logger.error(f"Failed to log successful word forms query: {log_err}")

            # Validate and return response data
            if (response.structured_data and 
                isinstance(response.structured_data, dict) and 
                'word_forms' in response.structured_data and 
                isinstance(response.structured_data['word_forms'], list)):
                return response.structured_data['word_forms'], True
            else:
                logger.warning(f"Invalid word forms response format for lemma '{lemma}'")
                return [], False

        except Exception as e:
            # More specific error logging
            logger.error(f"Error querying word forms for '{lemma}': {type(e).__name__}: {e}")

            return [], False

    def add_translation_for_definition(self, definition_id: int) -> bool:
        """
        Add a Chinese translation for a specific definition.

        Args:
            definition_id: The ID of the definition to translate

        Returns:
            Success flag
        """
        session = self.get_session()

        # Get the definition
        definition = session.query(linguistic_db.Definition).filter(linguistic_db.Definition.id == definition_id).first()
        if not definition:
            logger.warning(f"Definition with ID {definition_id} not found")
            return False

        # Get the word
        word = definition.word

        # Get an example sentence if available
        example_text = "No example available."
        if definition.examples and len(definition.examples) > 0:
            example_text = definition.examples[0].example_text

        # Query for translation
        translation, success = self.query_chinese_translation(
            word.word, 
            definition.definition_text,
            example_text
        )

        if success and translation:
            # Update the definition with the translation
            linguistic_db.update_chinese_translation(session, definition.id, translation)
            logger.info(f"Added Chinese translation '{translation}' for '{word.word}' (definition ID: {definition.id})")
            return True
        else:
            logger.warning(f"Failed to get Chinese translation for '{word.word}' (definition ID: {definition.id})")
            return False

    def add_missing_translations_for_word(self, word_text: str, throttle: float = 1.0) -> Dict[str, Any]:
        """
        Add Chinese translations for all definitions of a word that don't have translations yet.

        Args:
            word_text: Word to add translations for
            throttle: Time to wait between API calls (seconds)

        Returns:
            Dictionary with statistics about the processing
        """
        logger.info(f"Adding missing Chinese translations for definitions of '{word_text}'")

        session = self.get_session()
        word = linguistic_db.get_word_by_text(session, word_text)

        if not word:
            logger.warning(f"Word '{word_text}' not found in the database")
            return {
                "word": word_text,
                "total_definitions": 0,
                "missing_translations": 0,
                "processed": 0,
                "successful": 0
            }

        # Get all definitions for the word
        definitions = word.definitions
        total_definitions = len(definitions)

        if total_definitions == 0:
            logger.warning(f"No definitions found for word '{word_text}'")
            return {
                "word": word_text,
                "total_definitions": 0,
                "missing_translations": 0,
                "processed": 0,
                "successful": 0
            }

        # Filter for definitions without translations
        definitions_without_translations = [
            d for d in definitions 
            if not d.chinese_translation or not d.chinese_translation.strip()
        ]

        missing_translations = len(definitions_without_translations)
        logger.info(f"Found {missing_translations} definitions without translations (out of {total_definitions} total)")

        successful = 0
        processed = 0

        for definition in definitions_without_translations:
            success = self.add_translation_for_definition(definition.id)
            processed += 1

            if success:
                successful += 1
                logger.info(f"Added translation for definition ID {definition.id}")
            else:
                logger.warning(f"Failed to add translation for definition ID {definition.id}")

            # Throttle to avoid overloading the API
            time.sleep(throttle)

        logger.info(f"Processing complete for '{word_text}': {successful}/{processed} successful " 
                    f"({missing_translations} missing, {total_definitions} total)")

        return {
            "word": word_text,
            "total_definitions": total_definitions,
            "missing_translations": missing_translations,
            "processed": processed,
            "successful": successful
        }

    def query_pos_subtype(self, word: str, definition_text: str, pos_type: str) -> Tuple[str, bool]:
        """
        Query LLM for POS subtype for a definition.

        Args:
            word: The word to classify
            definition_text: The definition text
            pos_type: The part of speech (noun, verb, adjective, adverb)

        Returns:
            Tuple of (subtype string, success flag)
        """
        if not word or not isinstance(word, str) or not definition_text or not pos_type:
            logger.error("Invalid parameters provided for POS subtype query")
            return "other", False

        # Normalize pos_type to lowercase for consistency
        pos_type = pos_type.lower()
        valid_subtypes = linguistic_db.get_subtype_values_for_pos(pos_type)

        # Check if the POS is one we have subtypes for
        if pos_type not in ['noun', 'verb', 'adjective', 'adverb']:
            logger.warning(f"No subtypes defined for part of speech: {pos_type}")
            return "other", True

        schema = Schema(
            name="POSSubtype",
            description="Classification of a word into a specific part of speech subtype",
            properties={
                "classification": SchemaProperty(
                    type="object",
                    description="The classification result",
                    properties={
                        "pos_subtype": SchemaProperty(
                            type="string", 
                            description="The specific subtype within the part of speech category",
                            enum=valid_subtypes
                        ),
                        "confidence": SchemaProperty(
                            type="number", 
                            description="Confidence score from 0-1"
                        ),
                        "reasoning": SchemaProperty(
                            type="string", 
                            description="Explanation for the classification"
                        )
                    }
                )
            }
        )

        # Select the appropriate context based on the part of speech
        context = util.prompt_loader.get_context("wordfreq", "pos_subtype", pos_type)
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "pos_subtype")
        prompt = prompt_template.format(word=word, pos_type=pos_type, definition_text=definition_text)

        try:
            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Log successful query
            session = self.get_session()
            try:
                linguistic_db.log_query(
                    session,
                    word=word,
                    query_type=f'pos_subtype_{pos_type}',
                    prompt=prompt,
                    response=json.dumps(response.structured_data),
                    model=self.model
                )
            except Exception as log_err:
                logger.error(f"Failed to log successful subtype query: {log_err}")

            # Validate and return response data
            if (response.structured_data and 
                isinstance(response.structured_data, dict) and 
                'classification' in response.structured_data and
                'pos_subtype' in response.structured_data['classification']):
                return response.structured_data['classification']['pos_subtype'], True
            else:
                logger.warning(f"Invalid subtype response format for word '{word}'")
                return "other", False

        except Exception as e:
            # More specific error logging
            logger.error(f"Error querying POS subtype for '{word}': {type(e).__name__}: {e}")

            return "other", False

    def update_missing_subtypes_for_word(self, word_text: str, throttle: float = 1.0) -> Dict[str, Any]:
        """
        Add missing POS subtypes for all definitions of a word.

        Args:
            word_text: Word to update subtypes for
            throttle: Time to wait between API calls (seconds)

        Returns:
            Dictionary with statistics about the processing
        """
        logger.info(f"Adding missing POS subtypes for definitions of '{word_text}'")

        session = self.get_session()
        word = linguistic_db.get_word_by_text(session, word_text)

        if not word:
            logger.warning(f"Word '{word_text}' not found in the database")
            return {
                "word": word_text,
                "total_definitions": 0,
                "missing_subtypes": 0,
                "processed": 0,
                "successful": 0
            }

        # Get all definitions for the word
        definitions = word.definitions
        total_definitions = len(definitions)

        if total_definitions == 0:
            logger.warning(f"No definitions found for word '{word_text}'")
            return {
                "word": word_text,
                "total_definitions": 0,
                "missing_subtypes": 0,
                "processed": 0,
                "successful": 0
            }

        # Filter for definitions without subtypes
        definitions_without_subtypes = [
            d for d in definitions 
            if not d.pos_subtype or d.pos_subtype.strip() == ""
        ]

        missing_subtypes = len(definitions_without_subtypes)
        logger.info(f"Found {missing_subtypes} definitions without subtypes (out of {total_definitions} total)")

        successful = 0
        processed = 0

        for definition in definitions_without_subtypes:
            # Only process nouns, verbs, adjectives, and adverbs
            if definition.pos_type.lower() not in ['noun', 'verb', 'adjective', 'adverb']:
                logger.info(f"Skipping definition ID {definition.id} with POS '{definition.pos_type}'")
                continue

            subtype, success = self.query_pos_subtype(
                word.word, 
                definition.definition_text,
                definition.pos_type
            )

            if success and subtype:
                # Update the definition with the subtype
                linguistic_db.update_definition(session, definition.id, pos_subtype=subtype)
                successful += 1
                logger.info(f"Added subtype '{subtype}' for definition ID {definition.id}")
            else:
                logger.warning(f"Failed to get subtype for definition ID {definition.id}")

            processed += 1

            # Throttle to avoid overloading the API
            time.sleep(throttle)

        logger.info(f"Processing complete for '{word_text}': {successful}/{processed} successful " 
                    f"({missing_subtypes} missing, {total_definitions} total)")

        return {
            "word": word_text,
            "total_definitions": total_definitions,
            "missing_subtypes": missing_subtypes,
            "processed": processed,
            "successful": successful
        }

    def update_subtypes_for_batch(self, limit: int = 100, throttle: float = 1.0) -> Dict[str, Any]:
        """
        Add missing POS subtypes for a batch of definitions.

        Args:
            limit: Maximum number of definitions to process
            throttle: Time to wait between API calls (seconds)

        Returns:
            Dictionary with statistics about the processing
        """
        logger.info(f"Processing batch of {limit} definitions for POS subtypes")

        session = self.get_session()
        definitions = linguistic_db.get_definitions_without_subtypes(session, limit=limit)

        total = len(definitions)
        successful = 0
        processed = 0

        logger.info(f"Found {total} definitions without subtypes")

        for definition in definitions:
            # Only process nouns, verbs, adjectives, and adverbs
            if definition.pos_type.lower() not in ['noun', 'verb', 'adjective', 'adverb']:
                logger.info(f"Skipping definition ID {definition.id} with POS '{definition.pos_type}'")
                continue

            word = definition.word

            subtype, success = self.query_pos_subtype(
                word.word, 
                definition.definition_text,
                definition.pos_type
            )

            if success and subtype:
                # Update the definition with the subtype
                linguistic_db.update_definition(session, definition.id, pos_subtype=subtype)
                successful += 1
                logger.info(f"Added subtype '{subtype}' for '{word.word}' definition ID {definition.id}")
            else:
                logger.warning(f"Failed to get subtype for '{word.word}' definition ID {definition.id}")

            processed += 1

            # Throttle to avoid overloading the API
            time.sleep(throttle)

        logger.info(f"Batch processing complete: {successful}/{processed} successful (out of {total} total)")

        return {
            "total": total,
            "processed": processed,
            "successful": successful
        }

    def query_pronunciation(self, word: str, sentence: str) -> Tuple[Dict[str, Any], bool]:
        """
        Query LLM for IPA and phonetic pronunciation of a word.

        Args:
            word: Word to get pronunciation for
            sentence: Context sentence showing usage of the word

        Returns:
            Tuple of (pronunciation data, success flag)
        """
        if not word or not isinstance(word, str) or not sentence or not isinstance(sentence, str):
            logger.error("Invalid parameters provided for pronunciation query")
            return {}, False

        schema = Schema(
            name="Pronunciation",
            description="Pronunciation information for a word",
            properties={
                "pronunciation": SchemaProperty(
                    type="object",
                    description="Pronunciation details",
                    properties={
                        "ipa": SchemaProperty(
                            type="string", 
                            description="IPA pronunciation for the word in American English"
                        ),
                        "phonetic": SchemaProperty(
                            type="string", 
                            description="Simple phonetic pronunciation (e.g. 'SOO-duh-nim' for 'pseudonym')"
                        ),
                        "alternatives": SchemaProperty(
                            type="array",
                            description="Alternative valid pronunciations (British, Australian, etc.)",
                            array_items_schema=Schema(
                                name="AlternativePronunciation",
                                description="An alternative pronunciation variant",
                                properties={
                                    "variant": SchemaProperty(
                                        type="string", 
                                        description="Variant name (e.g. 'British', 'Australian', 'Alternative')"
                                    ),
                                    "ipa": SchemaProperty(
                                        type="string", 
                                        description="IPA pronunciation for this variant"
                                    )
                                }
                            )
                        ),
                        "confidence": SchemaProperty(
                            type="number", 
                            description="Confidence score from 0-1"
                        ),
                        "notes": SchemaProperty(
                            type="string", 
                            description="Additional notes about the pronunciation"
                        )
                    }
                )
            }
        )

        context = util.prompt_loader.get_context("wordfreq", "pronunciation")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "pronunciation")
        prompt = prompt_template.format(word=word, sentence=sentence)

        try:
            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Log successful query
            session = self.get_session()
            try:
                linguistic_db.log_query(
                    session,
                    word=word,
                    query_type='pronunciation',
                    prompt=prompt,
                    response=json.dumps(response.structured_data),
                    model=self.model
                )
            except Exception as log_err:
                logger.error(f"Failed to log successful pronunciation query: {log_err}")

            # Validate and return response data
            if (response.structured_data and 
                isinstance(response.structured_data, dict) and 
                'pronunciation' in response.structured_data and
                isinstance(response.structured_data['pronunciation'], dict)):
                return response.structured_data['pronunciation'], True
            else:
                logger.warning(f"Invalid pronunciation response format for word '{word}'")
                return {}, False

        except Exception as e:
            # More specific error logging
            logger.error(f"Error querying pronunciation for '{word}': {type(e).__name__}: {e}")

            return {}, False

    def update_pronunciation_for_definition(self, definition_id: int, sentence: Optional[str] = None) -> bool:
        """
        Update the pronunciation information for a specific definition.

        Args:
            definition_id: The ID of the definition to update
            sentence: Optional context sentence (if not provided, will use example or create one)

        Returns:
            Success flag
        """
        session = self.get_session()

        # Get the definition
        definition = session.query(linguistic_db.Definition).filter(linguistic_db.Definition.id == definition_id).first()
        if not definition:
            logger.warning(f"Definition with ID {definition_id} not found")
            return False

        # Get the word
        word = definition.word

        # Get a context sentence (from provided sentence, example, or generate a simple one)
        if not sentence:
            # Try to get an example sentence from the definition
            if definition.examples and len(definition.examples) > 0:
                sentence = definition.examples[0].example_text
            else:
                # This case should ideally not happen if definitions always have examples or a fallback
                # For now, we'll raise an error or log and return False
                logger.error(f"Could not get context sentence for definition ID {definition_id}")
                return False

        # Query for pronunciation
        pronunciation_data, success = self.query_pronunciation(word.word, sentence)

        if success:
            # Update the definition with the pronunciation information
            try:
                ipa = pronunciation_data.get('ipa', '')
                phonetic = pronunciation_data.get('phonetic', '')

                # Update the definition with the pronunciation
                linguistic_db.update_definition(
                    session, 
                    definition.id, 
                    ipa_pronunciation=ipa,
                    phonetic_pronunciation=phonetic
                )

                logger.info(f"Added pronunciations for '{word.word}' (definition ID: {definition.id})")
                logger.debug(f"IPA: {ipa}, Phonetic: {phonetic}")
                return True
            except Exception as e:
                logger.error(f"Error updating pronunciation for definition {definition_id}: {e}")
                return False
        else:
            logger.warning(f"Failed to get pronunciation for '{word.word}' (definition ID: {definition.id})")
            return False

    def update_missing_pronunciations_for_word(self, word_text: str, throttle: float = 1.0) -> Dict[str, Any]:
        """
        Add missing pronunciations for all definitions of a word.

        Args:
            word_text: Word to update pronunciations for
            throttle: Time to wait between API calls (seconds)

        Returns:
            Dictionary with statistics about the processing
        """
        logger.info(f"Adding missing pronunciations for definitions of '{word_text}'")

        session = self.get_session()
        word = linguistic_db.get_word_by_text(session, word_text)

        if not word:
            logger.warning(f"Word '{word_text}' not found in the database")
            return {
                "word": word_text,
                "total_definitions": 0,
                "missing_pronunciations": 0,
                "processed": 0,
                "successful": 0
            }

        # Get all definitions for the word
        definitions = word.definitions
        total_definitions = len(definitions)

        if total_definitions == 0:
            logger.warning(f"No definitions found for word '{word_text}'")
            return {
                "word": word_text,
                "total_definitions": 0,
                "missing_pronunciations": 0,
                "processed": 0,
                "successful": 0
            }

        # Filter for definitions without pronunciations
        definitions_without_pronunciations = [
            d for d in definitions 
            if not d.ipa_pronunciation or not d.phonetic_pronunciation
        ]

        missing_pronunciations = len(definitions_without_pronunciations)
        logger.info(f"Found {missing_pronunciations} definitions without pronunciations (out of {total_definitions} total)")

        successful = 0
        processed = 0

        for definition in definitions_without_pronunciations:
            success = self.update_pronunciation_for_definition(definition.id)
            processed += 1

            if success:
                successful += 1
                logger.info(f"Added pronunciation for definition ID {definition.id}")
            else:
                logger.warning(f"Failed to add pronunciation for definition ID {definition.id}")

            # Throttle to avoid overloading the API
            time.sleep(throttle)

        logger.info(f"Processing complete for '{word_text}': {successful}/{processed} successful " 
                    f"({missing_pronunciations} missing, {total_definitions} total)")

        return {
            "word": word_text,
            "total_definitions": total_definitions,
            "missing_pronunciations": missing_pronunciations,
            "processed": processed,
            "successful": successful
        }

    def update_pronunciations_for_batch(self, limit: int = 100, throttle: float = 1.0) -> Dict[str, Any]:
        """
        Add missing pronunciations for a batch of definitions.

        Args:
            limit: Maximum number of definitions to process
            throttle: Time to wait between API calls (seconds)

        Returns:
            Dictionary with statistics about the processing
        """
        logger.info(f"Processing batch of {limit} definitions for pronunciations")

        session = self.get_session()
        definitions = linguistic_db.get_definitions_without_pronunciation(session, limit=limit)

        total = len(definitions)
        successful = 0
        processed = 0

        logger.info(f"Found {total} definitions without pronunciations")

        for definition in definitions:
            word = definition.word
            logger.info(f"Processing definition ID {definition.id} for word '{word.word}'")

            success = self.update_pronunciation_for_definition(definition.id)
            processed += 1

            if success:
                successful += 1
                logger.info(f"Added pronunciation for '{word.word}' definition ID {definition.id}")
            else:
                logger.warning(f"Failed to add pronunciation for '{word.word}' definition ID {definition.id}")

            # Throttle to avoid overloading the API
            time.sleep(throttle)

        logger.info(f"Batch processing complete: {successful}/{processed} successful (out of {total} total)")

        return {
            "total": total,
            "processed": processed,
            "successful": successful
        }

    # New methods for working with the updated schema

    def get_word_token_info(self, token_text: str) -> Dict[str, Any]:
        """
        Get comprehensive information about a word token using the new schema.

        Args:
            token_text: The word token to look up

        Returns:
            Dictionary with token information including all derivative forms
        """
        session = self.get_session()
        word_token = linguistic_db.get_word_token_by_text(session, token_text)

        if not word_token:
            return {
                "token": token_text,
                "exists": False,
                "derivative_forms": []
            }

        forms_info = []
        for derivative_form in word_token.derivative_forms:
            lemma = derivative_form.lemma
            examples = [ex.example_text for ex in derivative_form.example_sentences]

            form_info = {
                "lemma_text": lemma.lemma_text,
                "definition": lemma.definition_text,
                "pos_type": lemma.pos_type,
                "pos_subtype": lemma.pos_subtype,
                "grammatical_form": derivative_form.grammatical_form,
                "is_base_form": derivative_form.is_base_form,
                "ipa_pronunciation": derivative_form.ipa_pronunciation,
                "phonetic_pronunciation": derivative_form.phonetic_pronunciation,
                "confidence": derivative_form.confidence,
                "verified": derivative_form.verified,
                "examples": examples,
                "translations": {
                    "chinese": derivative_form.chinese_translation,
                    "korean": derivative_form.korean_translation,
                    "french": derivative_form.french_translation,
                    "swahili": derivative_form.swahili_translation,
                    "vietnamese": derivative_form.vietnamese_translation,
                    "lithuanian": derivative_form.lithuanian_translation
                }
            }
            forms_info.append(form_info)

        return {
            "token": token_text,
            "exists": True,
            "derivative_forms": forms_info
        }

    def get_lemma_forms(self, lemma_text: str, pos_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all word tokens that represent forms of a specific lemma.

        Args:
            lemma_text: The lemma to look up
            pos_type: Optional POS filter

        Returns:
            List of dictionaries with token and form information
        """
        session = self.get_session()
        derivative_forms = linguistic_db.get_all_derivative_forms_for_lemma(session, lemma_text, pos_type)

        forms_info = []
        for derivative_form in derivative_forms:
            word_token = derivative_form.word_token
            examples = [ex.example_text for ex in derivative_form.example_sentences]

            form_info = {
                "token": word_token.token,
                "grammatical_form": derivative_form.grammatical_form,
                "is_base_form": derivative_form.is_base_form,
                "ipa_pronunciation": derivative_form.ipa_pronunciation,
                "phonetic_pronunciation": derivative_form.phonetic_pronunciation,
                "confidence": derivative_form.confidence,
                "verified": derivative_form.verified,
                "examples": examples
            }
            forms_info.append(form_info)

        return forms_info

    def add_translation_for_derivative_form(self, derivative_form_id: int, language: str) -> bool:
        """
        Add a translation for a specific derivative form using the new schema.

        Args:
            derivative_form_id: ID of the derivative form to translate
            language: Language to translate to (chinese, korean, french, etc.)

        Returns:
            Success flag
        """
        session = self.get_session()

        # Get the derivative form
        derivative_form = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.id == derivative_form_id
        ).first()

        if not derivative_form:
            logger.warning(f"Derivative form with ID {derivative_form_id} not found")
            return False

        # Get the word token and lemma
        word_token = derivative_form.word_token
        lemma = derivative_form.lemma

        # Get an example sentence if available
        example_text = "No example available."
        if derivative_form.example_sentences:
            example_text = derivative_form.example_sentences[0].example_text

        # Query for translation (using existing translation method)
        if language.lower() == 'chinese':
            translation, success = self.query_chinese_translation(
                word_token.token,
                lemma.definition_text,
                example_text
            )

            if success and translation:
                # Update the derivative form with the translation
                linguistic_db.update_translation(session, derivative_form.id, 'chinese', translation)
                logger.info(f"Added Chinese translation '{translation}' for '{word_token.token}' (derivative form ID: {derivative_form.id})")
                return True
            else:
                logger.warning(f"Failed to get Chinese translation for '{word_token.token}' (derivative form ID: {derivative_form.id})")
                return False
        else:
            logger.warning(f"Translation for language '{language}' not yet implemented")
            return False

    def process_words_batch(self, word_list: List[str], refresh: bool = False, throttle: float = 1.0) -> Dict[str, Any]:
        """
        Process a batch of words using the new schema.

        Args:
            word_list: List of word tokens to process
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
                success = self.process_word(word, refresh=refresh)
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

    def query_lithuanian_noun_declensions(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """
        Query LLM for all Lithuanian noun declensions (7 cases × 2 numbers).

        Args:
            lemma_id: The ID of the lemma to generate declensions for

        Returns:
            Tuple of (dict mapping form names to declensions, success flag)
        """
        session = self.get_session()

        # Get the lemma
        lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        if not lemma:
            logger.error(f"Lemma with ID {lemma_id} not found")
            return {}, False

        if not lemma.lithuanian_translation:
            logger.error(f"Lemma ID {lemma_id} has no Lithuanian translation")
            return {}, False

        if lemma.pos_type.lower() != 'noun':
            logger.error(f"Lemma ID {lemma_id} is not a noun (pos_type: {lemma.pos_type})")
            return {}, False

        noun = lemma.lithuanian_translation
        english_word = lemma.lemma_text
        definition = lemma.definition_text
        pos_subtype = lemma.pos_subtype

        # All 14 forms (7 cases × 2 numbers)
        # For plurale tantum, use empty string for singular forms
        # For singulare tantum, use empty string for plural forms
        singular_fields = [
            "nominative_singular", "genitive_singular", "dative_singular", "accusative_singular",
            "instrumental_singular", "locative_singular", "vocative_singular"
        ]
        plural_fields = [
            "nominative_plural", "genitive_plural", "dative_plural", "accusative_plural",
            "instrumental_plural", "locative_plural", "vocative_plural"
        ]

        # Build schema properties for all forms (all required, but can be empty string for tantum cases)
        form_properties = {}
        for form in singular_fields + plural_fields:
            form_properties[form] = SchemaProperty(
                "string",
                f"Lithuanian {form.replace('_', ' ')} (use empty string if not applicable)"
            )

        schema = Schema(
            name="LithuanianNounDeclensions",
            description="All declension forms for a Lithuanian noun",
            properties={
                "number_type": SchemaProperty(
                    "string",
                    "The number type of this noun",
                    enum=["regular", "plurale_tantum", "singulare_tantum"]
                ),
                "forms": SchemaProperty(
                    type="object",
                    description="Dictionary of all noun declension forms. Use empty string for forms that don't exist (e.g., singular forms for plurale tantum)",
                    properties=form_properties
                ),
                "confidence": SchemaProperty("number", "Confidence score from 0-1"),
                "notes": SchemaProperty("string", "Notes about the declension pattern")
            }
        )

        subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

        try:
            context = util.prompt_loader.get_context("wordfreq", "lithuanian_noun_declensions")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "lithuanian_noun_declensions")
            prompt = prompt_template.format(
                noun=noun,
                english_word=english_word,
                definition=definition,
                subtype_context=subtype_context
            )

            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Log successful query
            try:
                linguistic_db.log_query(
                    session,
                    word=noun,
                    query_type='lithuanian_noun_declensions',
                    prompt=prompt,
                    response=json.dumps(response.structured_data),
                    model=self.model
                )
            except Exception as log_err:
                logger.error(f"Failed to log Lithuanian declension query: {log_err}")

            # Validate and return response data
            if (response.structured_data and
                isinstance(response.structured_data, dict) and
                'forms' in response.structured_data and
                isinstance(response.structured_data['forms'], dict)):
                # Filter out forms based on number_type
                forms = response.structured_data['forms']
                number_type = response.structured_data.get('number_type', 'regular')

                # For plurale_tantum, remove all singular forms
                if number_type == 'plurale_tantum':
                    forms = {k: v for k, v in forms.items() if not k.endswith('_singular')}
                    logger.info(f"Filtered singular forms for plurale_tantum noun '{noun}'")
                # For singulare_tantum, remove all plural forms
                elif number_type == 'singulare_tantum':
                    forms = {k: v for k, v in forms.items() if not k.endswith('_plural')}
                    logger.info(f"Filtered plural forms for singulare_tantum noun '{noun}'")

                return forms, True
            else:
                logger.warning(f"Invalid response format for Lithuanian noun '{noun}'")
                return {}, False

        except Exception as e:
            logger.error(f"Error querying Lithuanian declensions for '{noun}': {type(e).__name__}: {e}")
            return {}, False

    def get_lithuanian_noun_forms(self, word: str = None, lemma_id: int = None, source: str = 'llm') -> Tuple[Dict[str, str], bool]:
        """
        Get Lithuanian noun declensions using either LLM or Wiktionary.

        This is a unified API wrapper that supports both implementations.

        Args:
            word: The Lithuanian word to decline (required if source='wiki')
            lemma_id: The lemma ID (required if source='llm')
            source: Source for noun forms - 'llm' (default) or 'wiki'

        Returns:
            Tuple of (dictionary mapping case names to forms, success flag)
            Forms use keys like: nominative_singular, genitive_plural, etc.
        """
        if source == 'wiki':
            if word is None:
                raise ValueError("word parameter is required when source='wiki'")
            from wordfreq.translation.wiki import get_lithuanian_noun_forms
            return get_lithuanian_noun_forms(word)
        elif source == 'llm':
            if lemma_id is None:
                raise ValueError("lemma_id parameter is required when source='llm'")
            return self.query_lithuanian_noun_declensions(lemma_id)
        else:
            raise ValueError(f"Invalid source: {source}. Must be 'llm' or 'wiki'")

    @classmethod
    def close_all(cls):
        """
        Close all resources for all threads.
        This should be called when the application is shutting down.
        """
        close_thread_sessions()
        logger.info("Closed all database sessions")