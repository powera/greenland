#!/usr/bin/python3

"""Processor for loading and analyzing word lists."""

import json
import csv
import logging
import time
import os
import threading
from typing import Dict, List, Optional, Any, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import constants
from wordfreq import linguistic_db
from wordfreq.linguistic_client import LinguisticClient
from wordfreq.connection_pool import get_session, close_thread_sessions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DB_PATH = constants.WORDFREQ_DB_PATH
DEFAULT_MODEL = constants.DEFAULT_MODEL
DEFAULT_BATCH_SIZE = 128
DEFAULT_THREADS = 4
DEFAULT_MAX_RETRIES = 1
DEFAULT_THROTTLE = 3.0  # seconds between API calls

class WordProcessor:
    """Processor for loading and analyzing word lists."""
    
    def __init__(
        self, 
        db_path: str = DEFAULT_DB_PATH,
        model: str = DEFAULT_MODEL,
        threads: int = DEFAULT_THREADS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        throttle: float = DEFAULT_THROTTLE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        debug: bool = False
    ):
        """
        Initialize word processor with database and LLM client.
        
        Args:
            db_path: Path to SQLite database
            model: Model name to use for queries
            threads: Number of threads for parallel processing
            batch_size: Number of words to process in a batch
            throttle: Time to wait between API calls
            max_retries: Maximum number of retries for failed API calls
            debug: Whether to enable debug logging
        """
        self.db_path = db_path
        self.model = model
        self.threads = threads
        self.batch_size = batch_size
        self.throttle = throttle
        self.max_retries = max_retries
        self.debug = debug
        
        if debug:
            logger.setLevel(logging.DEBUG)
        
        # Initialize the database if needed
        session = get_session(db_path, echo=debug)
        linguistic_db.ensure_tables_exist(session)
        
        logger.info(f"Initialized WordProcessor with model {model}")
    
    def get_session(self):
        """Get a thread-local database session."""
        return get_session(self.db_path, echo=self.debug)
    
    def process_single_word(self, word: str) -> bool:
        """
        Process a single word to get linguistic information.
        
        Args:
            word: Word to process
            
        Returns:
            Success flag
        """
        logger.info(f"Processing word: {word}")
        client = LinguisticClient.get_instance(model=self.model, db_path=self.db_path, debug=self.debug)
        return client.process_word(word)
    
    def _worker(self, word_obj: Any) -> Tuple[str, bool]:
        """Worker function for thread pool."""
        # Each thread gets its own client instance
        client = LinguisticClient.get_instance(model=self.model, db_path=self.db_path, debug=self.debug)
        
        word = word_obj.word
        thread_name = threading.current_thread().name
        
        logger.debug(f"[{thread_name}] Processing word: {word}")
        
        for attempt in range(self.max_retries):
            try:
                success = client.process_word(word)
                return (word, success)
            except Exception as e:
                logger.error(f"[{thread_name}] Error processing '{word}' (attempt {attempt+1}): {e}")
                time.sleep(self.throttle)
                
        return (word, False)
    
    def process_batch(self, words: List[Any]) -> Tuple[int, int]:
        """
        Process a batch of words in parallel.
        
        Args:
            words: List of Word objects to process
            
        Returns:
            Tuple of (successful count, total count)
        """
        success_count = 0
        total_count = len(words)
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = [executor.submit(self._worker, word) for word in words]
            
            for future in as_completed(futures):
                word, success = future.result()
                if success:
                    success_count += 1
                    logger.debug(f"Successfully processed '{word}'")
                else:
                    logger.warning(f"Failed to process '{word}'")
                
                # Throttle to avoid overloading the API
                time.sleep(self.throttle / self.threads)
                
        return (success_count, total_count)
    
    def process_all_words(self, limit: Optional[int] = None, skip_processed: bool = True) -> Dict[str, Any]:
        """
        Process all words in the database.
        
        Args:
            limit: Maximum number of words to process
            skip_processed: Whether to skip words that have already been processed
            
        Returns:
            Statistics about the processing
        """
        logger.info("Starting batch processing of words")
        
        # Get words to process
        session = self.get_session()
        if skip_processed:
            words = linguistic_db.get_words_needing_analysis(session, limit=limit or 100000)
        else:
            query = session.query(linguistic_db.Word).order_by(linguistic_db.Word.frequency_rank)
            if limit:
                query = query.limit(limit)
            words = query.all()
        
        total_words = len(words)
        logger.info(f"Found {total_words} words to process")
        
        if total_words == 0:
            return {
                "total": 0,
                "processed": 0,
                "successful": 0,
                "batches": 0
            }
        
        # Process in batches
        successful = 0
        processed = 0
        batch_count = 0
        
        for i in range(0, total_words, self.batch_size):
            batch = words[i:i + self.batch_size]
            batch_count += 1
            
            logger.info(f"Processing batch {batch_count} ({len(batch)} words)")
            success_count, batch_total = self.process_batch(batch)
            
            successful += success_count
            processed += batch_total
            
            # Log progress
            logger.info(f"Batch {batch_count} complete: {success_count}/{batch_total} successful")
            logger.info(f"Overall progress: {processed}/{total_words} words processed ({successful} successful)")
            
        return {
            "total": total_words,
            "processed": processed,
            "successful": successful,
            "batches": batch_count
        }
        

    def close(self):
        """Close database sessions and other resources."""
        close_thread_sessions()
        LinguisticClient.close_all()
        logger.info("All resources closed")