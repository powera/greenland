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

    @classmethod
    def close_all(cls):
        """
        Close all resources for all threads.
        This should be called when the application is shutting down.
        """
        close_thread_sessions()
        logger.info("Closed all database sessions")