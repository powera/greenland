#!/usr/bin/python3

"""Client for querying LLMs for linguistic information about words."""

import json
import logging
import time
import threading
from typing import Dict, List, Optional, Any, Tuple

from clients.unified_client import UnifiedLLMClient
from wordfreq import linguistic_db
from wordfreq.connection_pool import get_session, close_thread_sessions
import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Common model information
DEFAULT_MODEL = "llama3.2:3b"
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
        schema = {
            "type": "object",
            "properties": {
                "definitions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "definition": {
                                "type": "string",
                                "description": "The definition of the word for this specific meaning"
                            },
                            "pos": {
                                "type": "string",
                                "description": "The part of speech for this definition (noun, verb, etc.)"
                            },
                            "lemma": {
                                "type": "string",
                                "description": "The base form (lemma) for this definition"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score from 0-1"
                            },
                            "multiple_meanings": {
                                "type": "boolean",
                                "description": "Whether this definition covers multiple related meanings"
                            },
                            "special_case": {
                                "type": "boolean",
                                "description": "Whether this is a special case (foreign word, part of name, etc.)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes about this definition"
                            },
                            "examples": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "description": "Example sentence using this definition"
                                }
                            }
                        },
                        "additionalProperties": False,
                        "required": ["definition", "pos", "lemma", "confidence", "multiple_meanings", "special_case", "notes", "examples"]
                    }
                }
            },
            "additionalProperties": False,
            "required": ["definitions"]
        }
        
        context = """
        You are a linguistic expert specialized in dictionary definitions.
        
        Your task is to provide comprehensive definitions for a given word, including:
        - All distinct meanings of the word
        - The part of speech for each definition
        - The base form (lemma) for each definition
        - Example sentences for each definition
        
        Valid parts of speech include: noun, verb, adjective, adverb, pronoun, preposition, 
        conjunction, interjection, determiner, article, numeral, auxiliary, modal.
        
        For lemmatization (finding the base form):
        - For nouns: the singular form (e.g., "cats" → "cat")
        - For verbs: the infinitive form without "to" (e.g., "running" → "run")
        - For adjectives and adverbs: the positive form (e.g., "better" → "good")
        
        For each definition, provide:
        1. The definition text
        2. The part of speech
        3. The lemma (base form)
        4. A confidence score (0-1)
        5. Whether this definition covers multiple related meanings
        6. Whether this is a special case (foreign word, part of name, etc.)
        7. Any additional notes about the definition
        8. At least one example sentence
        
        Make sure to separate different definitions (e.g., "bank" as a financial institution vs. "bank" as the side of a river).
        
        Respond only with a structured JSON object following the schema provided.
        """
        
        prompt = f"Provide comprehensive dictionary definitions for the word '{word}'."
        
        # Try multiple times in case of failure
        for attempt in range(RETRY_COUNT):
            try:
                response = self.client.generate_chat(
                    prompt=prompt,
                    model=self.model,
                    json_schema=schema,
                    context=context
                )
                
                # Log the query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='definitions',
                        prompt=prompt,
                        response=json.dumps(response.structured_data),
                        model=self.model
                    )
                except Exception as e:
                    logger.error(f"Failed to log query: {e}")
                
                if response.structured_data and 'definitions' in response.structured_data:
                    return response.structured_data['definitions'], True
                else:
                    logger.warning(f"Failed to get valid definitions response for '{word}' (attempt {attempt+1})")
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Error querying for definitions: {e} (attempt {attempt+1})")
                
                # Log the failed query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='definitions',
                        prompt=prompt,
                        response=str(e),
                        model=self.model,
                        success=False,
                        error=str(e)
                    )
                except Exception as log_err:
                    logger.error(f"Failed to log query error: {log_err}")
                    
                time.sleep(RETRY_DELAY)
        
        # Return empty list if all attempts failed
        return [], False
    
    def process_word(self, word: str, rank: Optional[int] = None) -> bool:
        """
        Process a word to get linguistic information and store in database.
        
        Args:
            word: Word to process
            rank: Optional frequency ranking of the word
            
        Returns:
            Success flag
        """
        session = self.get_session()
        
        # Add or get word in database
        word_obj = linguistic_db.add_word(session, word, rank)
        
        # Query for definitions, POS, lemmas, and examples
        definitions, success = self.query_definitions(word)
        
        if success:
            for def_data in definitions:
                # Add definition with POS and lemma
                definition = linguistic_db.add_definition(
                    session,
                    word_obj,
                    definition_text=def_data.get('definition', f"Definition for {word}"),
                    pos_type=def_data.get('pos', 'unknown'),
                    lemma=def_data.get('lemma', word),
                    confidence=def_data.get('confidence', 0.0),
                    multiple_meanings=def_data.get('multiple_meanings', False),
                    special_case=def_data.get('special_case', False),
                    notes=def_data.get('notes')
                )
                
                # Add examples
                for example_text in def_data.get('examples', []):
                    linguistic_db.add_example(
                        session,
                        definition,
                        example_text=example_text
                    )
            
            return True
        else:
            logger.warning(f"Failed to process word '{word}'")
            return False
        
    def query_chinese_translation(self, word: str, definition: str, example: str) -> Tuple[str, bool]:
        """
        Query LLM for a Chinese translation of a specific word definition.
        
        Args:
            word: The English word to translate
            definition: The specific definition of the word
            example: An example sentence using the word
            
        Returns:
            Tuple of (translation string, success flag)
        """
        schema = {
            "type": "object",
            "properties": {
                "translation": {
                    "type": "object",
                    "properties": {
                        "chinese": {
                            "type": "string",
                            "description": "The Chinese translation (preferably two characters when possible)"
                        },
                        "pinyin": {
                            "type": "string",
                            "description": "The pinyin pronunciation of the Chinese translation"
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score from 0-1"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Additional notes about this translation"
                        }
                    },
                    "additionalProperties": False,
                    "required": ["chinese", "pinyin", "confidence", "notes"]
                }
            },
            "additionalProperties": False,
            "required": ["translation"]
        }
        
        context = """
        You are a bilingual English-Chinese linguistic expert.
        
        Your task is to provide an accurate Chinese translation for a specific definition of an English word.
        
        Guidelines:
        - Provide a translation that specifically matches the given definition, not other meanings of the word
        - Unless a one-character term is unambiguous, provide a two-character term (e.g., prefer '跳舞' over '舞')
        - Include proper pinyin pronunciation with tone marks
        - When multiple translations are possible, choose the most common or appropriate one
        - Only provide translations into standard Mandarin Chinese (not regional variants)
        
        Respond only with a structured JSON object following the schema provided.
        """
        
        prompt = f"""Provide a Chinese translation for the English word '{word}' with the following definition:
        
        Definition: {definition}
        Example sentence: {example}
        
        Return only a JSON object with the translation, pinyin, confidence score, and any notes."""
        
        # Try multiple times in case of failure
        for attempt in range(RETRY_COUNT):
            try:
                response = self.client.generate_chat(
                    prompt=prompt,
                    model=self.model,
                    json_schema=schema,
                    context=context
                )
                
                # Log the query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='chinese_translation',
                        prompt=prompt,
                        response=json.dumps(response.structured_data),
                        model=self.model
                    )
                except Exception as e:
                    logger.error(f"Failed to log translation query: {e}")
                
                if response.structured_data and 'translation' in response.structured_data:
                    return response.structured_data['translation']['chinese'], True
                else:
                    logger.warning(f"Failed to get valid translation response for '{word}' (attempt {attempt+1})")
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Error querying for translation: {e} (attempt {attempt+1})")
                
                # Log the failed query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='chinese_translation',
                        prompt=prompt,
                        response=str(e),
                        model=self.model,
                        success=False,
                        error=str(e)
                    )
                except Exception as log_err:
                    logger.error(f"Failed to log query error: {log_err}")
                    
                time.sleep(RETRY_DELAY)
    
        # Return empty string if all attempts failed
        return "", False

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

    @classmethod
    def close_all(cls):
        """
        Close all resources for all threads.
        This should be called when the application is shutting down.
        """
        close_thread_sessions()
        logger.info("Closed all database sessions")