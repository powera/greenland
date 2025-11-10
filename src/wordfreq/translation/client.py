#!/usr/bin/python3

"""Client for querying LLMs for linguistic information about words."""

import logging
import threading
from typing import Dict, List, Optional, Any, Tuple

from clients.unified_client import UnifiedLLMClient
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.connection_pool import get_session, close_thread_sessions
import constants

# Import specialized modules
from wordfreq.translation import (
    definitions,
    translations,
    pronunciation,
    pos_subtype,
    word_processing
)
from wordfreq.translation.language_forms import (
    english,
    lithuanian,
    french,
    spanish,
    german,
    portuguese
)
from wordfreq.translation.constants import DEFAULT_MODEL

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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

    # Definition queries
    def query_definitions(self, word: str) -> Tuple[List[Dict[str, Any]], bool]:
        """Query LLM for definitions, POS, and lemma information."""
        return definitions.query_definitions(self.client, word, self.get_session)

    # Translation queries
    def query_translations(
        self,
        english_word: str,
        reference_translation: Tuple[str, str],
        definition: str,
        pos_type: str,
        pos_subtype: Optional[str] = None,
        languages: Optional[List[str]] = None
    ) -> Tuple[Dict[str, str], bool]:
        """
        Query LLM to generate translations for a word.

        Args:
            english_word: English lemma form
            reference_translation: Tuple of (language_code, translation) for context
            definition: Definition of the word
            pos_type: Part of speech
            pos_subtype: Optional POS subtype
            languages: List of language names to generate translations for

        Returns:
            Tuple of (translations dict, success flag)
        """
        return translations.query_translations(
            self.client, english_word, reference_translation, definition, pos_type,
            self.get_session, pos_subtype, languages, self.model
        )

    # Word processing
    def process_word(self, word: str, refresh: bool = False) -> bool:
        """Process a word to get linguistic information and store in database."""
        return word_processing.process_word(self.client, word, self.get_session, refresh)

    def process_words_batch(
        self,
        word_list: List[str],
        refresh: bool = False,
        throttle: float = 1.0
    ) -> Dict[str, Any]:
        """Process a batch of words."""
        return word_processing.process_words_batch(
            self.client, word_list, self.get_session, refresh, throttle
        )

    # Pronunciation queries
    def query_pronunciation(self, word: str, sentence: str) -> Tuple[Dict[str, Any], bool]:
        """Query LLM for IPA and phonetic pronunciation of a word."""
        return pronunciation.query_pronunciation(self.client, word, sentence, self.get_session)

    def update_pronunciation_for_definition(
        self,
        definition_id: int,
        sentence: Optional[str] = None
    ) -> bool:
        """Update the pronunciation information for a specific definition."""
        return pronunciation.update_pronunciation_for_definition(
            self.client, definition_id, self.get_session, sentence
        )

    def update_missing_pronunciations_for_word(
        self,
        word_text: str,
        throttle: float = 1.0
    ) -> Dict[str, Any]:
        """Add missing pronunciations for all definitions of a word."""
        return pronunciation.update_missing_pronunciations_for_word(
            self.client, word_text, self.get_session, throttle
        )

    def update_pronunciations_for_batch(
        self,
        limit: int = 100,
        throttle: float = 1.0
    ) -> Dict[str, Any]:
        """Add missing pronunciations for a batch of definitions."""
        return pronunciation.update_pronunciations_for_batch(
            self.client, self.get_session, limit, throttle
        )

    # POS subtype queries
    def query_pos_subtype(
        self,
        word: str,
        definition_text: str,
        pos_type: str
    ) -> Tuple[str, bool]:
        """Query LLM for POS subtype for a definition."""
        return pos_subtype.query_pos_subtype(
            self.client, word, definition_text, pos_type, self.get_session
        )

    def update_missing_subtypes_for_word(
        self,
        word_text: str,
        throttle: float = 1.0
    ) -> Dict[str, Any]:
        """Add missing POS subtypes for all definitions of a word."""
        return pos_subtype.update_missing_subtypes_for_word(
            self.client, word_text, self.get_session, throttle
        )

    def update_subtypes_for_batch(
        self,
        limit: int = 100,
        throttle: float = 1.0
    ) -> Dict[str, Any]:
        """Add missing POS subtypes for a batch of definitions."""
        return pos_subtype.update_subtypes_for_batch(
            self.client, self.get_session, limit, throttle
        )

    # English forms
    def query_english_verb_conjugations(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for English verb conjugations."""
        return english.query_english_verb_conjugations(self.client, lemma_id, self.get_session)

    # Lithuanian forms
    def query_lithuanian_noun_declensions(self, lemma_id: int) -> Tuple[Dict[str, str], bool, str]:
        """Query LLM for Lithuanian noun declensions."""
        return lithuanian.query_lithuanian_noun_declensions(self.client, lemma_id, self.get_session)

    def query_lithuanian_verb_conjugations(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for Lithuanian verb conjugations."""
        return lithuanian.query_lithuanian_verb_conjugations(self.client, lemma_id, self.get_session)

    def query_lithuanian_adjective_declensions(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for Lithuanian adjective declensions."""
        return lithuanian.query_lithuanian_adjective_declensions(self.client, lemma_id, self.get_session)

    def get_lithuanian_noun_forms(
        self,
        word: str = None,
        lemma_id: int = None,
        source: str = 'llm'
    ) -> Tuple[Dict[str, str], bool]:
        """
        Get Lithuanian noun declensions using either LLM or Wiktionary.

        Args:
            word: The Lithuanian word to decline (required if source='wiki')
            lemma_id: The lemma ID (required if source='llm')
            source: Source for noun forms - 'llm' (default) or 'wiki'

        Returns:
            Tuple of (dictionary mapping case names to forms, success flag)
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

    # French forms
    def query_french_noun_forms(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for French noun forms."""
        return french.query_french_noun_forms(self.client, lemma_id, self.get_session)

    def query_french_verb_conjugations(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for French verb conjugations."""
        return french.query_french_verb_conjugations(self.client, lemma_id, self.get_session)

    # Spanish forms
    def query_spanish_noun_forms(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for Spanish noun forms."""
        return spanish.query_spanish_noun_forms(self.client, lemma_id, self.get_session)

    def query_spanish_verb_conjugations(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for Spanish verb conjugations."""
        return spanish.query_spanish_verb_conjugations(self.client, lemma_id, self.get_session)

    # German forms
    def query_german_noun_forms(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for German noun forms."""
        return german.query_german_noun_forms(self.client, lemma_id, self.get_session)

    def query_german_verb_conjugations(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for German verb conjugations."""
        return german.query_german_verb_conjugations(self.client, lemma_id, self.get_session)

    # Portuguese forms
    def query_portuguese_noun_forms(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for Portuguese noun forms."""
        return portuguese.query_portuguese_noun_forms(self.client, lemma_id, self.get_session)

    def query_portuguese_verb_conjugations(self, lemma_id: int) -> Tuple[Dict[str, str], bool]:
        """Query LLM for Portuguese verb conjugations."""
        return portuguese.query_portuguese_verb_conjugations(self.client, lemma_id, self.get_session)

    # Legacy methods for compatibility
    def get_word_token_info(self, token_text: str) -> Dict[str, Any]:
        """Get comprehensive information about a word token using the new schema."""
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
                "examples": [],
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
        """Get all word tokens that represent forms of a specific lemma."""
        session = self.get_session()
        derivative_forms = linguistic_db.get_all_derivative_forms_for_lemma(session, lemma_text, pos_type)

        forms_info = []
        for derivative_form in derivative_forms:
            word_token = derivative_form.word_token

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
        """Add a translation for a specific derivative form using the new schema."""
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

        # Query for definitions (which includes all translations)
        definitions_list, success = self.query_definitions(word_token.token)

        if not success or not definitions_list:
            logger.warning(f"Failed to get definitions and translations for '{word_token.token}' (derivative form ID: {derivative_form.id})")
            return False

        # Find the matching definition and extract the requested translation
        translation = None
        language_key = f'{language.lower()}_translation'

        for def_data in definitions_list:
            # If we find a matching definition, use its translation
            if def_data.get('definition', '').lower().strip() == lemma.definition_text.lower().strip():
                translation = def_data.get(language_key)
                break

        # If no exact match, use the first available translation
        if not translation and definitions_list:
            translation = definitions_list[0].get(language_key)

        if translation:
            # Update the derivative form with the translation
            linguistic_db.update_translation(session, derivative_form.id, language.lower(), translation)
            logger.info(f"Added {language} translation '{translation}' for '{word_token.token}' (derivative form ID: {derivative_form.id})")
            return True
        else:
            logger.warning(f"No {language} translation found for '{word_token.token}' (derivative form ID: {derivative_form.id})")
            return False

    # Deprecated methods - retained for backwards compatibility
    def query_word_forms(self, lemma: str, pos_type: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Query LLM for all forms of a lemma based on its part of speech.

        DEPRECATED: This method is retained for backwards compatibility but should not be used.
        """
        logger.warning("query_word_forms is deprecated and should not be used")
        return [], False

    @classmethod
    def close_all(cls):
        """
        Close all resources for all threads.
        This should be called when the application is shutting down.
        """
        close_thread_sessions()
        logger.info("Closed all database sessions")
