#!/usr/bin/python3

"""Functions for calculating combined word frequency rankings."""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Set, Tuple
from sqlalchemy import func, case, or_

import constants
from wordfreq import linguistic_db
from wordfreq.connection_pool import get_session
from wordfreq.linguistic_db import Word, Corpus, WordFrequency

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_UNKNOWN_RANK = 12500  # Default rank for words not in a corpus

def calculate_harmonic_mean_ranks(
    db_path: Optional[str] = constants.WORDFREQ_DB_PATH, 
    corpus_names: Optional[List[str]] = None,
    outlier_threshold: float = 2.0,
    unknown_rank: int = DEFAULT_UNKNOWN_RANK,
    update_db: bool = True
) -> List[Dict[str, Any]]:
    """
    Calculate harmonic mean of word ranks across different corpora.
    
    Args:
        db_path: Optional database path
        corpus_names: List of corpus names to include (or all if None)
        outlier_threshold: Z-score threshold for outlier detection
        unknown_rank: Rank to use for words not in a corpus
        update_db: Whether to update the frequency_rank in the words table
        
    Returns:
        List of words with their combined ranks and outlier information
    """
    logger.info("Calculating harmonic mean ranks")
    
    # Get session
    session = get_session(db_path) if db_path else get_session()
    
    # Get corpora to include
    if corpus_names:
        corpora = session.query(Corpus).filter(Corpus.name.in_(corpus_names)).all()
    else:
        corpora = session.query(Corpus).all()
        
    corpus_ids = [c.id for c in corpora]
    
    if not corpus_ids:
        logger.error("No corpora found")
        return []
    
    # Get all words with their ranks in each corpus
    word_data = {}
    
    # Query all words
    words = session.query(Word).all()
    
    # Get all frequency data
    all_frequencies = session.query(WordFrequency).filter(WordFrequency.corpus_id.in_(corpus_ids)).all()
    
    # Organize frequency data by word_id and corpus_id
    freq_by_word = {}
    for freq in all_frequencies:
        if freq.word_id not in freq_by_word:
            freq_by_word[freq.word_id] = {}
        freq_by_word[freq.word_id][freq.corpus_id] = freq.rank
    
    # Process each word
    for word in words:
        word_ranks = []
        corpus_ranks = {}
        
        # Get ranks for each corpus
        for corpus_id in corpus_ids:
            if word.id in freq_by_word and corpus_id in freq_by_word[word.id]:
                corpus_ranks[corpus_id] = freq_by_word[word.id][corpus_id]
            else:
                corpus_ranks[corpus_id] = unknown_rank
            word_ranks.append(corpus_ranks[corpus_id])
        
        # If no ranks found, use unknown_rank for all corpora
        if not word_ranks:
            word_ranks = [unknown_rank] * len(corpus_ids)
            
        # Calculate harmonic mean
        try:
            harmonic_mean = len(word_ranks) / sum(1/r for r in word_ranks)
        except ZeroDivisionError:
            harmonic_mean = unknown_rank
            
        word_data[word.id] = {
            "word": word.word,
            "ranks": corpus_ranks,
            "harmonic_mean": harmonic_mean,
            "is_outlier": False,
            "z_score": 0,
            "current_rank": word.frequency_rank
        }
    
    # Convert to list for sorting and outlier detection
    word_list = list(word_data.values())
    
    # Sort by harmonic mean
    word_list.sort(key=lambda x: x["harmonic_mean"])
    
    # Assign new ranks
    for i, word_info in enumerate(word_list):
        word_info["combined_rank"] = i + 1
    
    # Detect outliers
    if len(word_list) > 10:  # Need a minimum number for meaningful statistics
        # Get log of harmonic means to normalize the distribution
        log_means = np.log([w["harmonic_mean"] for w in word_list])
        
        # Calculate z-scores
        mean = np.mean(log_means)
        std = np.std(log_means)
        
        if std > 0:  # Avoid division by zero
            for i, word_info in enumerate(word_list):
                log_value = np.log(word_info["harmonic_mean"])
                z_score = (log_value - mean) / std
                word_info["z_score"] = z_score
                word_info["is_outlier"] = abs(z_score) > outlier_threshold
    
    # Update database if requested
    if update_db:
        updated_count = 0
        for word_info in word_list:
            word = session.query(Word).filter(Word.word == word_info["word"]).first()
            if word and word.frequency_rank != word_info["combined_rank"]:
                word.frequency_rank = word_info["combined_rank"]
                updated_count += 1
                
                # Commit in batches
                if updated_count % 500 == 0:
                    session.commit()
                    logger.info(f"Updated {updated_count} word ranks")
        
        # Final commit
        session.commit()
        logger.info(f"Updated {updated_count} word ranks in the database")
    
    # Return the list of words with their ranks
    return word_list

def export_ranked_word_list(
    output_path: str,
    db_path: Optional[str] = constants.WORDFREQ_DB_PATH,
    limit: Optional[int] = None,
    include_outliers: bool = True
) -> int:
    """
    Export the ranked word list to a text file.
    
    Args:
        output_path: Path to output file
        db_path: Optional database path
        limit: Optional limit on the number of words to export
        include_outliers: Whether to include words detected as outliers
        
    Returns:
        Number of words exported
    """
    logger.info(f"Exporting ranked word list to {output_path}")
    
    # Calculate combined ranks
    word_list = calculate_harmonic_mean_ranks(db_path=db_path, update_db=False)
    
    # Filter out outliers if requested
    if not include_outliers:
        word_list = [w for w in word_list if not w["is_outlier"]]
    
    # Sort by combined rank
    word_list.sort(key=lambda x: x["combined_rank"])
    
    # Apply limit if specified
    if limit:
        word_list = word_list[:limit]
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        for word_info in word_list:
            f.write(f"{word_info['word']}\n")
    
    logger.info(f"Exported {len(word_list)} words to {output_path}")
    return len(word_list)

def export_frequency_data(
    output_path: str,
    db_path: Optional[str] = constants.WORDFREQ_DB_PATH,
    format: str = "csv",
    limit: Optional[int] = None
) -> int:
    """
    Export detailed frequency data for all words.
    
    Args:
        output_path: Path to output file
        db_path: Optional database path
        format: Output format (csv or json)
        limit: Optional limit on the number of words to export
        
    Returns:
        Number of words exported
    """
    logger.info(f"Exporting detailed frequency data to {output_path}")
    
    # Get combined ranks and corpus information
    word_list = calculate_harmonic_mean_ranks(db_path=db_path, update_db=False)
    
    # Sort by combined rank
    word_list.sort(key=lambda x: x["combined_rank"])
    
    # Apply limit if specified
    if limit:
        word_list = word_list[:limit]
    
    # Get session
    session = get_session(db_path) if db_path else get_session()
    
    # Get corpus names for headers
    corpora = session.query(Corpus).all()
    corpus_mapping = {c.id: c.name for c in corpora}
    
    if format.lower() == "csv":
        import csv
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            # Create headers
            headers = ["word", "combined_rank", "harmonic_mean", "is_outlier", "z_score"]
            for corpus in corpora:
                headers.append(f"rank_{corpus.name}")
            
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            # Write data
            for word_info in word_list:
                row = {
                    "word": word_info["word"],
                    "combined_rank": word_info["combined_rank"],
                    "harmonic_mean": word_info["harmonic_mean"],
                    "is_outlier": "1" if word_info["is_outlier"] else "0",
                    "z_score": word_info["z_score"]
                }
                
                # Add ranks for each corpus
                for corpus_id, rank in word_info["ranks"].items():
                    corpus_name = corpus_mapping.get(corpus_id, f"corpus_{corpus_id}")
                    row[f"rank_{corpus_name}"] = rank
                
                writer.writerow(row)
    
    elif format.lower() == "json":
        import json
        
        # Create JSON data
        json_data = []
        for word_info in word_list:
            # Rename ranks to use corpus names
            named_ranks = {}
            for corpus_id, rank in word_info["ranks"].items():
                corpus_name = corpus_mapping.get(corpus_id, f"corpus_{corpus_id}")
                named_ranks[corpus_name] = rank
            
            json_data.append({
                "word": word_info["word"],
                "combined_rank": word_info["combined_rank"],
                "harmonic_mean": word_info["harmonic_mean"],
                "is_outlier": word_info["is_outlier"],
                "z_score": word_info["z_score"],
                "corpus_ranks": named_ranks
            })
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
    
    else:
        logger.error(f"Unsupported format: {format}")
        return 0
    
    logger.info(f"Exported {len(word_list)} words to {output_path}")
    return len(word_list)

def analyze_corpus_correlations() -> Dict[str, Any]:
    """
    Analyze correlations between word ranks in different corpora.
    
        
    Returns:
        Dictionary with correlation statistics
    """
    logger.info("Analyzing corpus correlations")
    
    # Calculate combined ranks
    word_list = calculate_harmonic_mean_ranks(db_path=constants.WORDFREQ_DB_PATH, update_db=False)
    
    # Get session
    session = get_session(constants.WORDFREQ_DB_PATH)
    
    # Get corpus information
    corpora = session.query(Corpus).all()
    corpus_ids = [c.id for c in corpora]
    corpus_names = {c.id: c.name for c in corpora}
    
    if len(corpus_ids) < 2:
        logger.warning("Need at least 2 corpora for correlation analysis")
        return {}
    
    # Calculate correlations between each pair of corpora
    correlations = {}
    
    for i, corpus1_id in enumerate(corpus_ids):
        corpus1_name = corpus_names[corpus1_id]
        correlations[corpus1_name] = {}
        
        for corpus2_id in corpus_ids[i+1:]:
            corpus2_name = corpus_names[corpus2_id]
            
            # Extract ranks for words that appear in both corpora
            ranks1 = []
            ranks2 = []
            
            for word_info in word_list:
                if corpus1_id in word_info["ranks"] and corpus2_id in word_info["ranks"]:
                    rank1 = word_info["ranks"][corpus1_id]
                    rank2 = word_info["ranks"][corpus2_id]
                    
                    # Only include if neither is the unknown rank
                    if rank1 != DEFAULT_UNKNOWN_RANK and rank2 != DEFAULT_UNKNOWN_RANK:
                        ranks1.append(rank1)
                        ranks2.append(rank2)
            
            # Calculate correlation if enough data points
            if len(ranks1) > 10:
                try:
                    # Use Spearman rank correlation
                    from scipy.stats import spearmanr
                    corr, p_value = spearmanr(ranks1, ranks2)
                    
                    correlations[corpus1_name][corpus2_name] = {
                        "correlation": corr,
                        "p_value": p_value,
                        "sample_size": len(ranks1)
                    }
                except ImportError:
                    logger.warning("scipy not available, using numpy correlation")
                    # Fallback to numpy correlation
                    corr = np.corrcoef(ranks1, ranks2)[0, 1]
                    correlations[corpus1_name][corpus2_name] = {
                        "correlation": corr,
                        "p_value": None,
                        "sample_size": len(ranks1)
                    }
    
    return correlations