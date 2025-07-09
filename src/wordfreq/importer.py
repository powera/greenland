#!/usr/bin/python3

"""Functions for importing corpus frequency data."""

import json
import csv
import logging
import os
import re
import time
from typing import Dict, List, Optional, Any, Tuple, Literal

import constants
from wordfreq import linguistic_db
from wordfreq.connection_pool import get_session
from wordfreq.linguistic_client import LinguisticClient
from wordfreq.linguistic_db import WordToken, Corpus, WordFrequency

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Regular expression to detect words containing numerals
CONTAINS_NUMERAL_PATTERN = re.compile(r'[0-9]')

def import_frequency_data(
    file_path: str, 
    corpus_name: str, 
    file_type: str = "json", 
    max_words: int = 5000,
    value_type: str = "auto"  # Parameter to specify what the numeric values represent: "rank", "frequency", or "auto"
) -> Tuple[int, int]:
    """
    Import word frequency data from a file into the database.
    
    Args:
        file_path: Path to the frequency data file
        corpus_name: Name of the corpus (gutenberg, books_20th, subtitles, wiki_vital)
        file_type: File type (json, subtlex)
        max_words: Maximum number of words to import
        value_type: How to interpret numeric values in simple word->number mappings:
                   - "rank": Values are treated as ranks (lower is more frequent)
                   - "frequency": Values are treated as frequencies (higher is more frequent)
                   - "auto": Auto-detect based on data characteristics
        
    Returns:
        Tuple of (words imported, total words)
    """
    logger.info(f"Importing frequency data from {file_path} for corpus '{corpus_name}'")
    
    # Get session and corpus
    session = get_session(constants.WORDFREQ_DB_PATH)
    corpus = session.query(Corpus).filter(Corpus.name == corpus_name).first()
    
    if not corpus:
        logger.error(f"Corpus '{corpus_name}' not found")
        raise ValueError(f"Corpus '{corpus_name}' not found")
    
    # Process the file based on type
    raw_words_data = {}
    
    try:
        if file_type.lower() == "json":
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Handle different JSON formats
                if isinstance(data, dict) and 'global_word_frequency' in data:
                    # Known format with explicit frequency data
                    raw_words_data = data['global_word_frequency']
                    # Mark that these are frequencies
                    detected_type = "frequency"
                elif isinstance(data, dict):
                    # Generic dictionary mapping
                    raw_words_data = data
                    # Will need to analyze
                    detected_type = "unknown"
                elif isinstance(data, list):
                    # Convert list to rank dictionary (1-indexed)
                    raw_words_data = {word: i+1 for i, word in enumerate(data)}
                    # Mark that these are ranks
                    detected_type = "rank"
                else:
                    logger.error(f"Unrecognized JSON format in {file_path}")
                    return (0, 0)
        elif file_type.lower() == "subtlex":
            # Handle SUBTLEX format
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter='\t')
                header = next(reader)
                row_count = 0
                for row in reader:
                    if len(row) < 2:
                        continue
                    word = row[0]
                    row_count += 1
                    raw_words_data[word] = row_count
                detected_type = "rank"
        else:
            logger.error(f"Unsupported file type: {file_type}")
            return (0, 0)
        
        # If value_type is "auto", try to determine whether values represent ranks or frequencies
        if value_type == "auto" and detected_type == "unknown":
            # Sample data to see if values look like ranks or frequencies
            sample_values = list(raw_words_data.values())[:100]  # Take first 100 values
            
            # Heuristics:
            # 1. Ranks are typically integers
            # 2. Frequencies are typically small decimal values < 1.0
            # 3. Frequencies typically sum to a value close to 1.0 for normalized data
            # 4. Ranks typically start from 1 and increment
            
            has_decimals = any(isinstance(v, float) and v != int(v) for v in sample_values)
            has_small_values = any(0 < v < 0.1 for v in sample_values)
            sum_near_one = 0.8 < sum(sample_values) < 1.2
            sequential_integers = all(isinstance(v, int) or v == int(v) for v in sample_values)
            
            if has_decimals and has_small_values and sum_near_one:
                logger.info("Auto-detected value type: frequency")
                value_type = "frequency"
            elif sequential_integers:
                logger.info("Auto-detected value type: rank")
                value_type = "rank"
            else:
                logger.info("Could not auto-detect value type, defaulting to 'rank'")
                value_type = "rank"
        elif value_type == "auto" and detected_type != "unknown":
            # Use the detected type
            value_type = detected_type
            logger.info(f"Using detected value type: {value_type}")
        
        # Process words: lowercase, filter out numerals, and merge duplicate entries
        words_data = {}
        skipped_numeral_count = 0
        merged_count = 0
        
        for word_text, data in raw_words_data.items():
            # Convert to lowercase
            word_text_lower = word_text.lower()
            
            # Skip words containing numerals
            if CONTAINS_NUMERAL_PATTERN.search(word_text_lower):
                skipped_numeral_count += 1
                continue
            
            # Determine rank and frequency for this entry
            rank = None
            frequency = None
            
            if isinstance(data, dict) and "rank" in data:
                # Explicit rank and possibly frequency in dictionary
                rank = data["rank"]
                frequency = data.get("frequency")
            elif isinstance(data, (int, float)):
                # If data is just a number, interpret based on value_type
                if value_type == "rank":
                    rank = int(data) if isinstance(data, int) else int(data + 0.5)  # Round floats
                    frequency = None
                else:  # value_type == "frequency"
                    frequency = float(data)
                    rank = None
            
            # If the lowercase word already exists in our processed data
            if word_text_lower in words_data:
                merged_count += 1
                existing_data = words_data[word_text_lower]
                
                # For ranks, keep the higher rank (lower number)
                if value_type == "rank" and rank is not None:
                    if existing_data.get("rank") is None or rank < existing_data["rank"]:
                        existing_data["rank"] = rank
                
                # For frequencies, keep the higher frequency
                if value_type == "frequency" and frequency is not None:
                    if existing_data.get("frequency") is None or frequency > existing_data["frequency"]:
                        existing_data["frequency"] = frequency
            else:
                # Add new entry
                words_data[word_text_lower] = {
                    "rank": rank,
                    "frequency": frequency
                }
        
        logger.info(f"Processed word data: {len(words_data)} unique lowercase words")
        logger.info(f"Filtered out {skipped_numeral_count} words containing numerals")
        logger.info(f"Merged {merged_count} duplicate words with different capitalization")
        
        # Import the processed words
        imported_count = 0
        total_count = len(words_data)
        
        for word_text, data in words_data.items():
            # Get or create the word token
            word_obj = linguistic_db.add_word_token(session, word_text)
            
            rank = data.get("rank")
            frequency = data.get("frequency")
            
            # Add or update the frequency record
            existing = session.query(WordFrequency).filter(
                WordFrequency.word_token_id == word_obj.id,
                WordFrequency.corpus_id == corpus.id
            ).first()
            
            if existing:
                if rank is not None:
                    existing.rank = rank
                if frequency is not None:
                    existing.frequency = frequency
            else:
                new_freq = WordFrequency(
                    word_token_id=word_obj.id,
                    corpus_id=corpus.id,
                    rank=rank,
                    frequency=frequency
                )
                session.add(new_freq)
                
            imported_count += 1
            
            # Commit in batches to avoid memory issues
            if imported_count % 500 == 0:
                session.commit()
                logger.info(f"Imported {imported_count}/{total_count} words")
            if imported_count >= max_words:
                logger.info(f"Reached max words limit of {max_words}")
                break
        
        # If we only have frequencies but no ranks, calculate ranks now
        if value_type == "frequency":
            logger.info("Calculating ranks from frequencies...")
            
            # Get all frequency records for this corpus ordered by frequency (descending)
            freq_records = session.query(WordFrequency).filter(
                WordFrequency.corpus_id == corpus.id,
                WordFrequency.frequency != None
            ).order_by(WordFrequency.frequency.desc()).all()
            
            # Update ranks
            for i, record in enumerate(freq_records):
                record.rank = i + 1  # 1-indexed
                
                # Commit in batches
                if (i + 1) % 500 == 0:
                    session.commit()
                    logger.info(f"Updated ranks for {i+1}/{len(freq_records)} words")
            
            # Final commit for ranks
            session.commit()
            logger.info(f"Finished calculating ranks for {len(freq_records)} words")
        
        # Final commit
        session.commit()
        logger.info(f"Successfully imported {imported_count}/{total_count} words for corpus '{corpus_name}'")
        return (imported_count, total_count)
        
    except Exception as e:
        logger.error(f"Error importing frequency data: {e}")
        session.rollback()
        raise

def import_all_corpus_data(
    word_limit: int = 5000,
    data_dir: str = None
) -> Dict[str, Tuple[int, int]]:
    """
    Import frequency data for all four corpus types defined in linguistic_db.py.
    
    Args:
        word_limit: How many words to import from each corpus (defaults to 5000)
        data_dir: Directory containing the corpus files (defaults to wordfreq/data)
        
    Returns:
        Dictionary mapping corpus names to tuples of (words imported, total words)
    """

    # Set default data directory if not provided
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    
    logger.info(f"Importing {word_limit} words for all corpus types from {data_dir}")
    
    # Define corpus configurations
    corpus_configs = [
        {
            "name": "19th_books",
            "file_name": "19th_books.json",
            "file_type": "json",
            "value_type": "auto"
        },
        {
            "name": "20th_books",
            "file_name": "20th_books.json",
            "file_type": "json",
            "value_type": "auto"
        },
        {
            "name": "subtitles",
            "file_name": "subtlex.txt",
            "file_type": "subtlex",
            "value_type": "auto"
        },
        {
            "name": "wiki_vital",
            "file_name": "wiki_vital.json",
            "file_type": "json",
            "value_type": "frequency"
        }
    ]
    
    # Initialize database session
    session = get_session(constants.WORDFREQ_DB_PATH)
    
    # Ensure corpora exist in the database
    linguistic_db.initialize_corpora(session)
    
    # Import each corpus
    results = {}
    
    for config in corpus_configs:
        corpus_name = config["name"]
        file_path = os.path.join(data_dir, config["file_name"])
        
        if not os.path.exists(file_path):
            logger.warning(f"Corpus file not found: {file_path}")
            results[corpus_name] = (0, 0)
            continue
        
        try:
            logger.info(f"Importing {corpus_name} from {file_path} (limit: {word_limit} words)")
            imported, total = import_frequency_data(
                file_path=file_path,
                corpus_name=corpus_name,
                file_type=config["file_type"],
                max_words=word_limit,
                value_type=config["value_type"]
            )
            results[corpus_name] = (imported, total)
            logger.info(f"Successfully imported {imported}/{total} words for {corpus_name}")
        except Exception as e:
            logger.error(f"Error importing {corpus_name}: {e}")
            results[corpus_name] = (0, 0)
    
    # Log summary
    logger.info("Import summary:")
    for corpus_name, (imported, total) in results.items():
        logger.info(f"  {corpus_name}: {imported}/{total} words imported")
    
    return results

def process_stopwords(refresh: bool = False, model: str = None) -> Dict[str, bool]:
    """
    Process all stop words from util/stopwords.py using linguistic_client.process_word.
    
    Args:
        refresh: If True, delete existing definitions and re-process all stop words
        model: Model name to use for processing (defaults to the default model in linguistic_client)
        
    Returns:
        Dictionary mapping words to success flags
    """
    from util.stopwords import all_stopwords, stopwords, CONTRACTIONS, COMMON_VERBS, COMMON_NOUNS, COMMON_ADVERBS, MISC_WORDS
    
    logger.info(f"Processing stop words (refresh={refresh})")
    
    # Initialize the linguistic client
    client = LinguisticClient.get_instance(model=model) if model else LinguisticClient.get_instance()
    
    # Collect all words to process
    all_words = set(all_stopwords)  # Start with the basic stopwords
    
    # Add other word categories
    all_words.update(CONTRACTIONS)
    all_words.update(COMMON_VERBS)
    all_words.update(COMMON_NOUNS)
    all_words.update(COMMON_ADVERBS)
    all_words.update(MISC_WORDS)
    
    # Sort for consistent processing order
    words_to_process = sorted(list(all_words))
    
    logger.info(f"Found {len(words_to_process)} unique stop words to process")
    
    # Process each word
    results = {}
    success_count = 0
    failure_count = 0
    
    for i, word in enumerate(words_to_process):
        logger.info(f"Processing word {i+1}/{len(words_to_process)}: '{word}'")
        
        try:
            # Process the word
            success = client.process_word(word, refresh=refresh)
            results[word] = success
            
            if success:
                success_count += 1
                logger.info(f"Successfully processed '{word}'")
            else:
                failure_count += 1
                logger.warning(f"Failed to process '{word}'")
            
            # Add a small delay to avoid overwhelming the API
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error processing word '{word}': {e}")
            results[word] = False
            failure_count += 1
        
        # Log progress every 10 words
        if (i + 1) % 10 == 0:
            logger.info(f"Progress: {i+1}/{len(words_to_process)} words processed")
    
    # Log summary
    logger.info("Stop words processing summary:")
    logger.info(f"Total words: {len(words_to_process)}")
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Failed to process: {failure_count}")
    
    return results