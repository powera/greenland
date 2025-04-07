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

    def query_part_of_speech(self, word: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Query LLM for part of speech information.
        
        Args:
            word: Word to analyze
            
        Returns:
            Tuple of (list of POS data, success flag)
        """
        schema = {
            "type": "object",
            "properties": {
                "parts_of_speech": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pos": {
                                "type": "string",
                                "description": "The part of speech (noun, verb, etc.)"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score from 0-1"
                            },
                            "multiple_meanings": {
                                "type": "boolean",
                                "description": "Whether the word has multiple meanings in this part of speech"
                            },
                            "different_pos": {
                                "type": "boolean",
                                "description": "Whether the word can be used as different parts of speech"
                            },
                            "special_case": {
                                "type": "boolean",
                                "description": "Whether this is a special case (foreign word, part of name, etc.)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes about the word"
                            }
                        },
                        "additionalProperties": False,
                        "required": ["pos", "confidence", "multiple_meanings", "different_pos", "special_case", "notes"]
                    }
                }
            },
            "required": ["parts_of_speech"]
        }
        
        context = """
        You are a linguistic expert specialized in part of speech analysis.
        
        Your task is to identify all possible parts of speech for a given word.
        
        Valid parts of speech include: noun, verb, adjective, adverb, pronoun, preposition, 
        conjunction, interjection, determiner, article, numeral, auxiliary, modal.
        
        For each part of speech, provide:
        1. A confidence score (0-1)
        2. Whether the word has multiple meanings in this part of speech
        3. Whether the word can be used as different parts of speech
        4. Whether this is a special case (foreign word, part of name, etc.)
        5. Any additional notes about the word's usage
        
        Respond only with a structured JSON object following the schema provided.
        """
        
        prompt = f"What is the part of speech of the word '{word}'?"
        
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
                        query_type='pos',
                        prompt=prompt,
                        response=json.dumps(response.structured_data),
                        model=self.model
                    )
                except Exception as e:
                    logger.error(f"Failed to log query: {e}")
                
                if response.structured_data and 'parts_of_speech' in response.structured_data:
                    return response.structured_data['parts_of_speech'], True
                else:
                    logger.warning(f"Failed to get valid POS response for '{word}' (attempt {attempt+1})")
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Error querying for POS: {e} (attempt {attempt+1})")
                
                # Log the failed query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='pos',
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
                
    def query_lemma(self, word: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Query LLM for lemma information.
        
        Args:
            word: Word to analyze
            
        Returns:
            Tuple of (list of lemma data, success flag)
        """
        schema = {
            "type": "object",
            "properties": {
                "lemmas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lemma": {
                                "type": "string",
                                "description": "The base form (lemma) of the word"
                            },
                            "pos": {
                                "type": "string",
                                "description": "The part of speech this lemma applies to"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score from 0-1"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes about the lemma"
                            }
                        },
                        "required": ["lemma", "pos", "confidence", "notes"]
                    }
                }
            },
            "additionalProperties": False,
            "required": ["lemmas"]
        }
        
        context = """
        You are a linguistic expert specialized in lemmatization.
        
        Lemmatization is the process of finding the base form (lemma) of a word:
        - For nouns: the singular form (e.g., "cats" → "cat")
        - For verbs: the infinitive form without "to" (e.g., "running" → "run")
        - For adjectives and adverbs: the positive form (e.g., "better" → "good")
        
        Your task is to identify the lemma (base form) of a given word.
        
        If the word has multiple possible lemmas depending on part of speech, provide each one.
        
        For each lemma, provide:
        1. The lemma itself
        2. The part of speech it applies to (noun, verb, etc.)
        3. A confidence score (0-1)
        4. Any additional notes
        
        Respond only with a structured JSON object following the schema provided.
        """
        
        prompt = f"What is the lemma (base form) of the word '{word}'?"
        
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
                        query_type='lemma',
                        prompt=prompt,
                        response=json.dumps(response.structured_data),
                        model=self.model
                    )
                except Exception as e:
                    logger.error(f"Failed to log query: {e}")
                
                if response.structured_data and 'lemmas' in response.structured_data:
                    return response.structured_data['lemmas'], True
                else:
                    logger.warning(f"Failed to get valid lemma response for '{word}' (attempt {attempt+1})")
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Error querying for lemma: {e} (attempt {attempt+1})")
                
                # Log the failed query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='lemma',
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
    
    def query_combined(self, word: str) -> Tuple[Dict[str, List[Dict[str, Any]]], bool]:
        """
        Query LLM for both part of speech and lemma information.
        
        Args:
            word: Word to analyze
            
        Returns:
            Tuple of (dict with 'parts_of_speech' and 'lemmas' lists, success flag)
        """
        schema = {
            "type": "object",
            "properties": {
                "parts_of_speech": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pos": {
                                "type": "string",
                                "description": "The part of speech (noun, verb, etc.)"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score from 0-1"
                            },
                            "multiple_meanings": {
                                "type": "boolean",
                                "description": "Whether the word has multiple meanings in this part of speech"
                            },
                            "different_pos": {
                                "type": "boolean",
                                "description": "Whether the word can be used as different parts of speech"
                            },
                            "special_case": {
                                "type": "boolean",
                                "description": "Whether this is a special case (foreign word, part of name, etc.)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes about the word"
                            }
                        },
                        "additionalProperties": False,
                        "required": ["pos", "confidence", "multiple_meanings", "different_pos", "special_case", "notes"]
                    }
                },
                "lemmas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lemma": {
                                "type": "string",
                                "description": "The base form (lemma) of the word"
                            },
                            "pos": {
                                "type": "string",
                                "description": "The part of speech this lemma applies to"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score from 0-1"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes about the lemma"
                            }
                        },
                        "additionalProperties": False,
                        "required": ["lemma", "pos", "confidence", "notes"]
                    }
                }
            },
            "additionalProperties": False,
            "required": ["parts_of_speech", "lemmas"]
        }
        
        context = """
        You are a linguistic expert specialized in both part of speech analysis and lemmatization.
        
        Your task is to analyze a given word and provide:
        
        1. All possible parts of speech for the word
           - Valid parts of speech include: noun, verb, adjective, adverb, pronoun, preposition, 
             conjunction, interjection, determiner, article, numeral, auxiliary, modal
           - For each part of speech, provide:
             a. A confidence score (0-1)
             b. Whether the word has multiple meanings in this part of speech
             c. Whether the word can be used as different parts of speech
             d. Whether this is a special case (foreign word, part of name, etc.)
             e. Any additional notes about the word's usage
        
        2. All possible lemmas (base forms) for the word
           - Lemmatization is the process of finding the base form:
             a. For nouns: the singular form (e.g., "cats" → "cat")
             b. For verbs: the infinitive form without "to" (e.g., "running" → "run")
             c. For adjectives and adverbs: the positive form (e.g., "better" → "good")
           - For each lemma, provide:
             a. The lemma itself
             b. The part of speech it applies to (noun, verb, etc.)
             c. A confidence score (0-1)
             d. Any additional notes
        
        Respond only with a structured JSON object following the schema provided.
        """
        
        prompt = f"Analyze the word '{word}' for its parts of speech and lemma (base form)."
        
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
                        query_type='both',
                        prompt=prompt,
                        response=json.dumps(response.structured_data),
                        model=self.model
                    )
                except Exception as e:
                    logger.error(f"Failed to log query: {e}")
                
                if response.structured_data and 'parts_of_speech' in response.structured_data and 'lemmas' in response.structured_data:
                    return response.structured_data, True
                else:
                    logger.warning(f"Failed to get valid combined response for '{word}' (attempt {attempt+1})")
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Error querying for combined info: {e} (attempt {attempt+1})")
                
                # Log the failed query
                try:
                    session = self.get_session()
                    linguistic_db.log_query(
                        session,
                        word=word,
                        query_type='both',
                        prompt=prompt,
                        response=str(e),
                        model=self.model,
                        success=False,
                        error=str(e)
                    )
                except Exception as log_err:
                    logger.error(f"Failed to log query error: {log_err}")
                    
                time.sleep(RETRY_DELAY)
        
        # Return empty dict if all attempts failed
        return {'parts_of_speech': [], 'lemmas': []}, False
    
    def process_word(self, word: str, rank: Optional[int] = None, use_combined: bool = True) -> bool:
        """
        Process a word to get linguistic information and store in database.
        
        Args:
            word: Word to process
            rank: Optional frequency ranking of the word
            use_combined: Whether to use combined query for POS and lemma
            
        Returns:
            Success flag
        """
        session = self.get_session()
        
        # Add or get word in database
        word_obj = linguistic_db.add_word(session, word, rank)
        
        if use_combined:
            # Query for both POS and lemma in one call
            results, success = self.query_combined(word)
            
            if success:
                # Process parts of speech
                for pos_data in results.get('parts_of_speech', []):
                    linguistic_db.add_part_of_speech(
                        session,
                        word_obj,
                        pos_type=pos_data.get('pos', 'unknown'),
                        confidence=pos_data.get('confidence', 0.0),
                        multiple_meanings=pos_data.get('multiple_meanings', False),
                        different_pos=pos_data.get('different_pos', False),
                        special_case=pos_data.get('special_case', False),
                        notes=pos_data.get('notes')
                    )
                
                # Process lemmas
                for lemma_data in results.get('lemmas', []):
                    linguistic_db.add_lemma(
                        session,
                        word_obj,
                        lemma=lemma_data.get('lemma', word),
                        pos_type=lemma_data.get('pos'),
                        confidence=lemma_data.get('confidence', 0.0),
                        notes=lemma_data.get('notes')
                    )
                
                return True
            else:
                logger.warning(f"Combined query failed for '{word}', falling back to separate queries")
        
        # Separate queries if combined failed or not requested
        pos_success = False
        lemma_success = False
        
        # Get part of speech
        pos_results, pos_success = self.query_part_of_speech(word)
        if pos_success:
            for pos_data in pos_results:
                linguistic_db.add_part_of_speech(
                    session,
                    word_obj,
                    pos_type=pos_data.get('pos', 'unknown'),
                    confidence=pos_data.get('confidence', 0.0),
                    multiple_meanings=pos_data.get('multiple_meanings', False),
                    different_pos=pos_data.get('different_pos', False),
                    special_case=pos_data.get('special_case', False),
                    notes=pos_data.get('notes')
                )
        
        # Get lemma
        lemma_results, lemma_success = self.query_lemma(word)
        if lemma_success:
            for lemma_data in lemma_results:
                linguistic_db.add_lemma(
                    session,
                    word_obj,
                    lemma=lemma_data.get('lemma', word),
                    pos_type=lemma_data.get('pos'),
                    confidence=lemma_data.get('confidence', 0.0),
                    notes=lemma_data.get('notes')
                )
        
        return pos_success or lemma_success

    @classmethod
    def close_all(cls):
        """
        Close all resources for all threads.
        This should be called when the application is shutting down.
        """
        close_thread_sessions()
        logger.info("Closed all database sessions")