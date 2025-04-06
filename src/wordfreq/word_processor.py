#!/usr/bin/python3

"""Processor for loading and analyzing word lists."""

import json
import csv
import logging
import time
import os
from typing import Dict, List, Optional, Any, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from wordfreq import linguistic_db
from wordfreq.linguistic_client import LinguisticClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DB_PATH = 'linguistics.sqlite'
DEFAULT_BATCH_SIZE = 50
DEFAULT_THREADS = 4
DEFAULT_MAX_RETRIES = 3
DEFAULT_THROTTLE = 1.0  # seconds between API calls

class WordProcessor:
    """Processor for loading and analyzing word lists."""
    
    def __init__(
        self, 
        db_path: str = DEFAULT_DB_PATH,
        model: str = "llama3.2:3b",
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
            
        # Create database session
        self.session = linguistic_db.create_database_session(db_path)
        
        # Create linguistic client
        self.client = LinguisticClient(model=model, session=self.session, debug=debug)
        
        logger.info(f"Initialized WordProcessor with model {model}")
    
    def load_words_from_json(self, file_path: str) -> int:
        """
        Load words from a JSON file (output from compare.py).
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            Number of words loaded
        """
        logger.info(f"Loading words from JSON file: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Handle different JSON formats
            word_data = {}
            if isinstance(data, dict) and 'global_word_frequency' in data:
                # Format from compare.py
                word_data = data['global_word_frequency']
            elif isinstance(data, dict):
                # Simple word:frequency dictionary
                word_data = data
            elif isinstance(data, list):
                # List of words with no frequency
                word_data = {word: i+1 for i, word in enumerate(data)}
            else:
                logger.error(f"Unrecognized JSON format in {file_path}")
                return 0
                
            # Sort by frequency (highest first)
            sorted_words = sorted(word_data.items(), key=lambda x: x[1], reverse=True)
            
            # Add words to database with rankings
            count = 0
            for rank, (word, freq) in enumerate(sorted_words, start=1):
                if linguistic_db.add_word(self.session, word, rank):
                    count += 1
                    
            logger.info(f"Added {count} words from {file_path}")
            return count
            
        except Exception as e:
            logger.error(f"Error loading words from {file_path}: {e}")
            return 0
    
    def load_words_from_csv(self, file_path: str, word_column: int = 0, rank_column: Optional[int] = None, has_header: bool = True) -> int:
        """
        Load words from a CSV file.
        
        Args:
            file_path: Path to CSV file
            word_column: Column index containing words (0-based)
            rank_column: Column index containing rank/frequency (0-based), or None if not present
            has_header: Whether the file has a header row
            
        Returns:
            Number of words loaded
        """
        logger.info(f"Loading words from CSV file: {file_path}")
        
        try:
            count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                
                # Skip header if present
                if has_header:
                    next(reader, None)
                
                # Process rows
                for i, row in enumerate(reader):
                    if word_column < len(row):
                        word = row[word_column].strip()
                        
                        # Get rank if available
                        rank = None
                        if rank_column is not None and rank_column < len(row):
                            try:
                                rank = int(row[rank_column])
                            except (ValueError, TypeError):
                                rank = i + 1
                        else:
                            rank = i + 1
                            
                        if word:
                            if linguistic_db.add_word(self.session, word, rank):
                                count += 1
                                
            logger.info(f"Added {count} words from {file_path}")
            return count
            
        except Exception as e:
            logger.error(f"Error loading words from {file_path}: {e}")
            return 0
    
    def load_words_from_text(self, file_path: str) -> int:
        """
        Load words from a plain text file (one word per line).
        
        Args:
            file_path: Path to text file
            
        Returns:
            Number of words loaded
        """
        logger.info(f"Loading words from text file: {file_path}")
        
        try:
            count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    word = line.strip()
                    if word:
                        if linguistic_db.add_word(self.session, word, i+1):
                            count += 1
                            
            logger.info(f"Added {count} words from {file_path}")
            return count
            
        except Exception as e:
            logger.error(f"Error loading words from {file_path}: {e}")
            return 0
    
    def process_single_word(self, word: str, rank: Optional[int] = None) -> bool:
        """
        Process a single word to get linguistic information.
        
        Args:
            word: Word to process
            rank: Optional frequency ranking
            
        Returns:
            Success flag
        """
        logger.info(f"Processing word: {word}")
        return self.client.process_word(word, rank)
    
    def _worker(self, word_obj: Any) -> Tuple[str, bool]:
        """Worker function for thread pool."""
        word = word_obj.word
        rank = word_obj.frequency_rank
        
        for attempt in range(self.max_retries):
            try:
                success = self.client.process_word(word, rank)
                return (word, success)
            except Exception as e:
                logger.error(f"Error processing '{word}' (attempt {attempt+1}): {e}")
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
                time.sleep(self.throttle)
                
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
        if skip_processed:
            words = linguistic_db.get_words_needing_analysis(self.session, limit=limit or 100000)
        else:
            query = self.session.query(linguistic_db.Word).order_by(linguistic_db.Word.frequency_rank)
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
        """Close database session."""
        if self.session:
            self.session.close()
            logger.info("Database session closed")

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process word lists to extract linguistic information")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Load command
    load_parser = subparsers.add_parser("load", help="Load words from a file")
    load_parser.add_argument("file", help="File to load")
    load_parser.add_argument("--format", choices=["json", "csv", "text"], help="File format (default: auto-detect)")
    load_parser.add_argument("--word-column", type=int, default=0, help="Column index for words in CSV (0-based)")
    load_parser.add_argument("--rank-column", type=int, default=None, help="Column index for rank in CSV (0-based)")
    load_parser.add_argument("--no-header", action="store_true", help="CSV file has no header row")
    
    # Process command
    process_parser = subparsers.add_parser("process", help="Process words in database")
    process_parser.add_argument("--limit", type=int, default=None, help="Maximum number of words to process")
    process_parser.add_argument("--all", action="store_true", help="Process all words, including those already processed")
    process_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for processing")
    process_parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help="Number of threads for parallel processing")
    
    # Single word command
    word_parser = subparsers.add_parser("word", help="Process a single word")
    word_parser.add_argument("word", help="Word to process")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    
    # Common arguments
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Database file path")
    parser.add_argument("--model", default="llama3.2:3b", help="LLM model to use")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Create processor
    processor = WordProcessor(
        db_path=args.db,
        model=args.model,
        threads=getattr(args, 'threads', DEFAULT_THREADS),
        batch_size=getattr(args, 'batch_size', DEFAULT_BATCH_SIZE),
        debug=args.debug
    )
    
    try:
        if args.command == "load":
            # Auto-detect format if not specified
            if not args.format:
                ext = os.path.splitext(args.file)[1].lower()
                if ext == '.json':
                    args.format = 'json'
                elif ext == '.csv':
                    args.format = 'csv'
                else:
                    args.format = 'text'
            
            # Load file
            if args.format == 'json':
                count = processor.load_words_from_json(args.file)
            elif args.format == 'csv':
                count = processor.load_words_from_csv(
                    args.file, 
                    word_column=args.word_column,
                    rank_column=args.rank_column,
                    has_header=not args.no_header
                )
            else:  # text
                count = processor.load_words_from_text(args.file)
                
            print(f"Loaded {count} words from {args.file}")
            
        elif args.command == "process":
            stats = processor.process_all_words(
                limit=args.limit,
                skip_processed=not args.all
            )
            
            print(f"Processing complete: {stats['successful']}/{stats['processed']} words successful")
            
        elif args.command == "word":
            success = processor.process_single_word(args.word)
            if success:
                print(f"Successfully processed '{args.word}'")
            else:
                print(f"Failed to process '{args.word}'")
                
        elif args.command == "stats":
            stats = linguistic_db.get_processing_stats(processor.session)
            
            print("Database Statistics:")
            print(f"  Total words: {stats['total_words']}")
            print(f"  Words with POS: {stats['words_with_pos']} ({stats['words_with_pos']/stats['total_words']*100:.1f}%)")
            print(f"  Words with lemma: {stats['words_with_lemma']} ({stats['words_with_lemma']/stats['total_words']*100:.1f}%)")
            print(f"  Fully processed words: {stats['words_complete']} ({stats['percent_complete']:.1f}%)")
            
            # List problematic words
            print("\nProblematic words (sample):")
            problematic = linguistic_db.list_problematic_words(processor.session, limit=10)
            for item in problematic:
                print(f"  {item['word']} (rank {item['rank']}):")
                for pos_type, multiple, different, special, notes in item['parts_of_speech']:
                    flags = []
                    if multiple:
                        flags.append("multiple meanings")
                    if different:
                        flags.append("different POS")
                    if special:
                        flags.append("special case")
                    
                    print(f"    POS: {pos_type} {' - ' + ', '.join(flags) if flags else ''}")
                    if notes:
                        print(f"      Notes: {notes}")
                
                print(f"    Lemmas: {', '.join(l[0] for l in item['lemmas'])}")
                
        else:
            parser.print_help()
            
    finally:
        processor.close()

if __name__ == "__main__":
    main()
