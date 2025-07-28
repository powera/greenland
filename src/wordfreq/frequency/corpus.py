#!/usr/bin/python3

"""Corpus configuration and management for wordfreq analysis."""

import logging
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session

import wordfreq.storage.connection_pool
import wordfreq.storage.models.schema
import wordfreq.frequency.analysis
import wordfreq.frequency.importer
import constants
import wordfreq.storage.database

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class CorpusConfig:
    """Configuration for a single corpus."""
    name: str
    description: str
    file_path: str  # Path to the data file
    max_words: int  # Maximum number of words to import
    language_code: str = "en"  # Language code for the words in this corpus (e.g., "en", "lt", "zh", "fr")
    file_type: str = "json"  # File type (json, subtlex)
    value_type: str = "auto"  # How to interpret values: "rank", "frequency", or "auto"
    corpus_weight: float = 1.0  # Overall weight of this corpus in calculations (0.0 = exclude, 1.0 = full weight)
    max_unknown_rank: Optional[int] = None  # Maximum rank for unknown words (None = use corpus size)
    enabled: bool = True
    
    def get_effective_unknown_rank(self, corpus_size: int, default_unknown_rank: int) -> int:
        """
        Calculate the effective unknown rank for this corpus.
        
        The unknown rank should never make a word more common than if it was excluded
        from the average. This means the unknown rank should be at least as high as
        the worst rank in the corpus.
        
        Args:
            corpus_size: Number of words in this corpus
            default_unknown_rank: Global default unknown rank
            
        Returns:
            Effective unknown rank for this corpus
        """
        if self.max_unknown_rank is not None:
            base_rank = min(self.max_unknown_rank, max(corpus_size, default_unknown_rank))
        else:
            base_rank = max(corpus_size, default_unknown_rank)
            
        return base_rank

# Corpus configurations
CORPUS_CONFIGS = [
    CorpusConfig(
        name="19th_books",
        description="Word frequency data from 19th century books",
        file_path="19th_books.json",
        max_words=4000,
        file_type="json",
        value_type="auto",
        corpus_weight=0.8,
        max_unknown_rank=10000,
        enabled=True
    ),
    CorpusConfig(
        name="20th_books", 
        description="Word frequency data from 20th century books",
        file_path="20th_books.json",
        max_words=4000,
        file_type="json",
        value_type="auto",
        corpus_weight=0.9,
        max_unknown_rank=10000,
        enabled=True
    ),
    CorpusConfig(
        name="subtitles",
        description="Word frequency data from movie and TV subtitles",
        file_path="subtlex.txt",
        max_words=7500,
        file_type="subtlex",
        value_type="auto",
        corpus_weight=1.0,
        max_unknown_rank=12000,
        enabled=True
    ),
    CorpusConfig(
        name="wiki_vital",
        description="Word frequency data from Wikipedia vital articles",
        file_path="wiki_vital.json",
        max_words=6000,
        file_type="json",
        value_type="frequency",
        corpus_weight=1.0,
        max_unknown_rank=12000,
        enabled=True
    ),
    CorpusConfig(
        name="cooking",
        description="Word frequency data from Cookbooks",
        file_path="cooking_wordfreq.json",
        max_words=1000,
        file_type="json",
        value_type="frequency",
        corpus_weight=0.7,
        max_unknown_rank=1500,
        enabled=True
    )
]

def get_corpus_config(name: str) -> Optional[CorpusConfig]:
    """Get configuration for a specific corpus by name."""
    for config in CORPUS_CONFIGS:
        if config.name == name:
            return config
    return None

def get_enabled_corpus_configs() -> List[CorpusConfig]:
    """Get all enabled corpus configurations."""
    return [config for config in CORPUS_CONFIGS if config.enabled]

def get_all_corpus_configs() -> List[CorpusConfig]:
    """Get all corpus configurations."""
    return CORPUS_CONFIGS.copy()

def get_corpus_names() -> List[str]:
    """Get names of all configured corpora."""
    return [config.name for config in CORPUS_CONFIGS]

def get_enabled_corpus_names() -> List[str]:
    """Get names of all enabled corpora."""
    return [config.name for config in CORPUS_CONFIGS if config.enabled]

def validate_corpus_configs() -> List[str]:
    """
    Validate corpus configurations and return any error messages.
    
    Returns:
        List of validation error messages (empty if all valid)
    """
    errors = []
    names = set()
    
    for config in CORPUS_CONFIGS:
        # Check for duplicate names
        if config.name in names:
            errors.append(f"Duplicate corpus name: {config.name}")
        names.add(config.name)
        
        # Validate unknown rank weight
        if not 0.0 <= config.corpus_weight <= 1.0:
            errors.append(f"Invalid corpus_weight for {config.name}: {config.corpus_weight} (must be 0.0-1.0)")
            
        # Validate max unknown rank
        if config.max_unknown_rank is not None and config.max_unknown_rank <= 0:
            errors.append(f"Invalid max_unknown_rank for {config.name}: {config.max_unknown_rank} (must be positive)")
    
    return errors

def sync_corpus_configs_to_db(
    session: Optional[Session] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronize corpus configurations from config file to database.
    
    This function will:
    - Add new corpora from config
    - Update existing corpora with new configuration values
    - Mark corpora as disabled if they're not in the config
    
    Args:
        session: Optional database session
        db_path: Optional database path
        
    Returns:
        Dictionary with sync results
    """
    # Validate configurations first
    validation_errors = validate_corpus_configs()
    if validation_errors:
        logger.error(f"Corpus configuration validation failed: {validation_errors}")
        return {
            "success": False,
            "errors": validation_errors,
            "added": 0,
            "updated": 0,
            "disabled": 0
        }
    
    # Get session
    if session is None:
        session = wordfreq.storage.connection_pool.get_session(db_path) if db_path else wordfreq.storage.connection_pool.get_session()
        should_close = True
    else:
        should_close = False
    
    try:
        # Get existing corpora from database
        existing_corpora = {corpus.name: corpus for corpus in session.query(wordfreq.storage.models.schema.Corpus).all()}
        config_names = {config.name for config in CORPUS_CONFIGS}
        
        added_count = 0
        updated_count = 0
        disabled_count = 0
        
        # Add or update corpora from config
        for config in CORPUS_CONFIGS:
            if config.name in existing_corpora:
                # Update existing corpus
                corpus = existing_corpora[config.name]
                updated = False
                
                if corpus.description != config.description:
                    corpus.description = config.description
                    updated = True
                    
                if corpus.corpus_weight != config.corpus_weight:
                    corpus.corpus_weight = config.corpus_weight
                    updated = True
                    
                if corpus.max_unknown_rank != config.max_unknown_rank:
                    corpus.max_unknown_rank = config.max_unknown_rank
                    updated = True
                    
                if corpus.enabled != config.enabled:
                    corpus.enabled = config.enabled
                    updated = True
                
                if updated:
                    updated_count += 1
                    logger.info(f"Updated corpus configuration: {config.name}")
            else:
                # Add new corpus
                new_corpus = wordfreq.storage.models.schema.Corpus(
                    name=config.name,
                    description=config.description,
                    corpus_weight=config.corpus_weight,
                    max_unknown_rank=config.max_unknown_rank,
                    enabled=config.enabled
                )
                session.add(new_corpus)
                added_count += 1
                logger.info(f"Added new corpus: {config.name}")
        
        # Disable corpora that are no longer in config
        for corpus_name, corpus in existing_corpora.items():
            if corpus_name not in config_names and corpus.enabled:
                corpus.enabled = False
                disabled_count += 1
                logger.info(f"Disabled corpus not in config: {corpus_name}")
        
        # Commit changes
        session.commit()
        
        logger.info(f"Corpus sync completed: {added_count} added, {updated_count} updated, {disabled_count} disabled")
        
        return {
            "success": True,
            "errors": [],
            "added": added_count,
            "updated": updated_count,
            "disabled": disabled_count
        }
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error syncing corpus configurations: {e}")
        return {
            "success": False,
            "errors": [str(e)],
            "added": 0,
            "updated": 0,
            "disabled": 0
        }
    finally:
        if should_close:
            session.close()

def get_corpus_size(corpus_name: str, session: Optional[Session] = None, db_path: Optional[str] = None) -> int:
    """
    Get the number of words in a corpus.
    
    Args:
        corpus_name: Name of the corpus
        session: Optional database session
        db_path: Optional database path
        
    Returns:
        Number of words in the corpus
    """
    if session is None:
        session = wordfreq.storage.connection_pool.get_session(db_path) if db_path else wordfreq.storage.connection_pool.get_session()
        should_close = True
    else:
        should_close = False
    
    try:
        corpus = session.query(wordfreq.storage.models.schema.Corpus).filter(wordfreq.storage.models.schema.Corpus.name == corpus_name).first()
        if not corpus:
            return 0
            
        count = session.query(wordfreq.storage.models.schema.WordFrequency).filter(wordfreq.storage.models.schema.WordFrequency.corpus_id == corpus.id).count()
        return count
        
    finally:
        if should_close:
            session.close()

def get_effective_unknown_rank(
    corpus_name: str, 
    default_unknown_rank: int,
    session: Optional[Session] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Get the effective unknown rank for a corpus based on its configuration and size.
    
    Args:
        corpus_name: Name of the corpus
        default_unknown_rank: Global default unknown rank
        session: Optional database session
        db_path: Optional database path
        
    Returns:
        Effective unknown rank for the corpus
    """
    if session is None:
        session = wordfreq.storage.connection_pool.get_session(db_path) if db_path else wordfreq.storage.connection_pool.get_session()
        should_close = True
    else:
        should_close = False
    
    try:
        corpus = session.query(wordfreq.storage.models.schema.Corpus).filter(wordfreq.storage.models.schema.Corpus.name == corpus_name).first()
        if not corpus:
            return default_unknown_rank
            
        corpus_size = get_corpus_size(corpus_name, session, db_path)
        
        # Calculate effective unknown rank
        if corpus.max_unknown_rank is not None:
            base_rank = min(corpus.max_unknown_rank, max(corpus_size, default_unknown_rank))
        else:
            base_rank = max(corpus_size, default_unknown_rank)
            
        return base_rank
        
    finally:
        if should_close:
            session.close()

def get_corpus_configs_from_db(
    session: Optional[Session] = None,
    db_path: Optional[str] = None,
    enabled_only: bool = True
) -> List[wordfreq.storage.models.schema.Corpus]:
    """
    Get corpus configurations from the database.
    
    Args:
        session: Optional database session
        db_path: Optional database path
        enabled_only: Whether to return only enabled corpora
        
    Returns:
        List of Corpus objects from database
    """
    if session is None:
        session = wordfreq.storage.connection_pool.get_session(db_path) if db_path else wordfreq.storage.connection_pool.get_session()
        should_close = True
    else:
        should_close = False
    
    try:
        query = session.query(wordfreq.storage.models.schema.Corpus)
        if enabled_only:
            query = query.filter(wordfreq.storage.models.schema.Corpus.enabled == True)
        return query.all()
        
    finally:
        if should_close:
            session.close()

def initialize_corpus_configs(
    session: Optional[Session] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Initialize corpus configurations in the database.
    This is a convenience function that calls sync_corpus_configs_to_db.
    
    Args:
        session: Optional database session
        db_path: Optional database path
        
    Returns:
        Dictionary with initialization results
    """
    logger.info("Initializing corpus configurations from config file")
    return sync_corpus_configs_to_db(session, db_path)

def load_corpus(corpus_name: str) -> tuple[int, int]:
    """
    Load a corpus by name using its configuration.
    
    This function replaces the need to call import_frequency_data directly
    by looking up the corpus configuration and using those parameters.
    
    Args:
        corpus_name: Name of the corpus to load
        
    Returns:
        Tuple of (words imported, total words)
        
    Raises:
        ValueError: If corpus_name is not found in configuration
    """
    # Find the corpus configuration
    config = get_corpus_config(corpus_name)
    if config is None:
        raise ValueError(f"Corpus '{corpus_name}' not found in configuration")
    
    # Build the full file path
    # Assume data files are in src/wordfreq/data directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    data_dir = os.path.join(project_root, "src", "wordfreq", "data")
    full_file_path = os.path.join(data_dir, config.file_path)
    
    # Check if file exists
    if not os.path.exists(full_file_path):
        raise FileNotFoundError(f"Data file not found: {full_file_path}")
    
    logger.info(f"Loading corpus '{corpus_name}' from {full_file_path}")
    
    # Call the import function with the configuration parameters
    return wordfreq.frequency.importer.import_frequency_data(
        file_path=full_file_path,
        corpus_name=config.name,
        language_code=config.language_code,
        file_type=config.file_type,
        max_words=config.max_words,
        value_type=config.value_type,
        corpus_description=config.description
    )

def load_all_corpora() -> Dict[str, tuple[int, int]]:
    """
    Load all enabled corpora using their configurations.
    
    This function replaces the functionality from create_wordfreq_simple.py
    by loading all enabled corpora in the configuration.
    
    Returns:
        Dictionary mapping corpus names to (words imported, total words) tuples
    """
    logger.info("Initializing database and clients...")
    
    # Create database session
    session = wordfreq.storage.database.create_database_session()
    
    # Ensure all database tables exist
    logger.info("Initializing database tables...")
    wordfreq.storage.database.ensure_tables_exist(session)
    
    # Initialize corpora entries
    logger.info("Initializing corpora...")
    wordfreq.storage.database.initialize_corpora(session)
    
    # Load all enabled corpora
    results = {}
    enabled_configs = get_enabled_corpus_configs()
    
    for config in enabled_configs:
        try:
            logger.info(f"Loading corpus: {config.name}")
            result = load_corpus(config.name)
            results[config.name] = result
            logger.info(f"Successfully loaded {config.name}: {result[0]}/{result[1]} words")
        except Exception as e:
            logger.error(f"Failed to load corpus {config.name}: {e}")
            results[config.name] = (0, 0)
    
    # Calculate combined mean ranks (from original script)
    logger.info("Calculating combined ranks...")
    try:
        wordfreq.frequency.analysis.calculate_combined_ranks(db_path=constants.WORDFREQ_DB_PATH)
        logger.info("Harmonic mean ranks calculation completed!")
    except Exception as e:
        logger.error(f"Failed to calculate combined ranks: {e}")
    
    logger.info("Word frequency data population completed!")
    return results