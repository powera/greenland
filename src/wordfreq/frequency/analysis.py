#!/usr/bin/python3

"""Functions for calculating combined word frequency rankings."""

import logging
import math
import statistics
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import case, func, or_

import constants
import wordfreq.frequency.corpus
from wordfreq.storage import database
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.connection_pool import get_session
from wordfreq.storage.models.schema import Corpus, WordFrequency, WordToken

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants
DEFAULT_UNKNOWN_RANK = 12500  # Default rank for words not in a corpus


def calculate_combined_ranks(
    config: Optional["DataSourceConfig"] = None,
    corpus_names: Optional[List[str]] = None,
    outlier_threshold: float = 2.0,
    unknown_rank: int = DEFAULT_UNKNOWN_RANK,
    update_db: bool = True,
) -> List[Dict[str, Any]]:
    """
    Calculate combined word ranks using arithmetic mean of harmonic and geometric means.

    This approach balances the harmonic mean (which prevents outliers from dominating)
    with the geometric mean (which prevents outliers from being completely ignored),
    providing more robust rankings for domain-specific corpora.

    Args:
        config: DataSourceConfig with backend settings (uses default if None)
        corpus_names: List of corpus names to include (or all if None)
        outlier_threshold: Z-score threshold for outlier detection
        unknown_rank: Default rank for words not in a corpus (used as penalty/placeholder)
        update_db: Whether to update the frequency_rank in the word_tokens table

    Returns:
        List of words with their combined ranks and outlier information
    """
    from wordfreq.storage.backend import create_session
    from wordfreq.storage.backend.config import DataSourceConfig

    logger.info("Calculating combined ranks using harmonic-geometric mean")

    # Get session
    if config is None:
        config = DataSourceConfig()
    session = create_session(config)

    # Get corpora to include (only enabled ones)
    if corpus_names:
        corpora = (
            session.query(Corpus)
            .filter(Corpus.name.in_(corpus_names), Corpus.enabled == True)
            .all()
        )
    else:
        corpora = wordfreq.frequency.corpus.get_corpus_configs_from_db(session, enabled_only=True)

    if not corpora:
        logger.error("No enabled corpora found")
        return []

    # Create corpus info mapping
    corpus_info = {}
    for corpus in corpora:
        effective_unknown_rank = wordfreq.frequency.corpus.get_effective_unknown_rank(
            corpus.name, unknown_rank, session
        )
        corpus_info[corpus.id] = {
            "name": corpus.name,
            "weight": corpus.corpus_weight,
            "unknown_rank": effective_unknown_rank,
        }

    corpus_ids = list(corpus_info.keys())

    # Get all words with their ranks in each corpus
    word_data = {}

    # Query all word tokens
    word_tokens = session.query(WordToken).all()

    # Get all frequency data
    all_frequencies = (
        session.query(WordFrequency).filter(WordFrequency.corpus_id.in_(corpus_ids)).all()
    )

    # Organize frequency data by word_token_id and corpus_id
    freq_by_word_token: Dict[int, Dict[int, int]] = {}
    for freq in all_frequencies:
        if freq.word_token_id not in freq_by_word_token:
            freq_by_word_token[freq.word_token_id] = {}
        freq_by_word_token[freq.word_token_id][freq.corpus_id] = freq.rank

    # Process each word token
    for word_token in word_tokens:
        corpus_ranks = {}
        weighted_ranks = []
        weights = []

        # Get ranks for each corpus
        for corpus_id in corpus_ids:
            corpus_config = corpus_info[corpus_id]

            if (
                word_token.id in freq_by_word_token
                and corpus_id in freq_by_word_token[word_token.id]
            ):
                rank = freq_by_word_token[word_token.id][corpus_id]
                corpus_ranks[corpus_id] = rank
            else:
                rank = corpus_config["unknown_rank"]
                corpus_ranks[corpus_id] = rank

            # Only include in weighted calculation if weight > 0
            if corpus_config["weight"] > 0:
                weighted_ranks.append(rank)
                weights.append(corpus_config["weight"])

        # Calculate combined rank using arithmetic mean of harmonic and geometric means
        if weighted_ranks and weights:
            try:
                # Weighted harmonic mean: sum(weights) / sum(weight_i / rank_i)
                weighted_sum_harmonic = sum(w / r for w, r in zip(weights, weighted_ranks))
                harmonic_mean = sum(weights) / weighted_sum_harmonic

                # Weighted geometric mean: exp(sum(weight_i * log(rank_i)) / sum(weights))
                weighted_log_sum = sum(w * math.log(r) for w, r in zip(weights, weighted_ranks))
                geometric_mean = math.exp(weighted_log_sum / sum(weights))

                # Combined rank: arithmetic mean of harmonic and geometric means
                combined_rank = (harmonic_mean + geometric_mean) / 2

            except (ZeroDivisionError, ValueError):
                # Fallback to maximum unknown rank if calculation fails
                combined_rank = max(corpus_info[cid]["unknown_rank"] for cid in corpus_ids)
        else:
            # No valid ranks, use the maximum unknown rank
            combined_rank = max(corpus_info[cid]["unknown_rank"] for cid in corpus_ids)

        word_data[word_token.id] = {
            "word": word_token.token,
            "word_token_id": word_token.id,
            "ranks": corpus_ranks,
            "harmonic_mean": harmonic_mean if "harmonic_mean" in locals() else combined_rank,
            "geometric_mean": geometric_mean if "geometric_mean" in locals() else combined_rank,
            "combined_rank_value": combined_rank,
            "is_outlier": False,
            "z_score": 0,
            "current_rank": word_token.frequency_rank,
        }

    # Convert to list for sorting and outlier detection
    word_list = list(word_data.values())

    # Sort by combined rank
    word_list.sort(key=lambda x: x["combined_rank_value"])

    # Assign new ranks
    for i, word_info in enumerate(word_list):
        word_info["combined_rank"] = i + 1

    # Detect outliers
    if len(word_list) > 10:  # Need a minimum number for meaningful statistics
        # Get log of combined ranks to normalize the distribution
        log_ranks = [math.log(w["combined_rank_value"]) for w in word_list]

        # Calculate z-scores
        mean_val = statistics.mean(log_ranks)
        std_val = statistics.pstdev(log_ranks)  # population std dev

        if std_val > 0:  # Avoid division by zero
            for i, word_info in enumerate(word_list):
                log_value = math.log(word_info["combined_rank_value"])
                z_score = (log_value - mean_val) / std_val
                word_info["z_score"] = z_score
                word_info["is_outlier"] = abs(z_score) > outlier_threshold

    # Update database if requested
    if update_db:
        # BATCH OPTIMIZATION: Build a map of id -> new_rank for batch update
        updates_needed = {}
        for word_info in word_list:
            word_token_id = word_info.get("word_token_id")
            if word_token_id and word_info["current_rank"] != word_info["combined_rank"]:
                updates_needed[word_token_id] = word_info["combined_rank"]

        if updates_needed:
            logger.info(f"Batch updating {len(updates_needed)} word ranks...")

            # Process in batches to avoid memory issues with large datasets
            batch_size = 1000
            token_ids = list(updates_needed.keys())
            updated_count = 0

            for i in range(0, len(token_ids), batch_size):
                batch_ids = token_ids[i : i + batch_size]

                # Fetch batch of word tokens
                batch_tokens = session.query(WordToken).filter(WordToken.id.in_(batch_ids)).all()

                # Update each token in the batch
                for token in batch_tokens:
                    token.frequency_rank = updates_needed[token.id]
                    updated_count += 1

                # Commit this batch
                session.commit()
                logger.info(f"Updated {updated_count}/{len(updates_needed)} word ranks")

            logger.info(f"Batch update complete: {updated_count} word ranks updated")
        else:
            logger.info("No word rank updates needed")

    # Return the list of words with their ranks
    return word_list


def export_ranked_word_list(
    output_path: str,
    db_path: Optional[str] = constants.WORDFREQ_DB_PATH,
    limit: Optional[int] = None,
    include_outliers: bool = True,
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
    config = DataSourceConfig(sqlite_path=db_path) if db_path else DataSourceConfig()
    word_list = calculate_combined_ranks(config=config, update_db=False)

    # Filter out outliers if requested
    if not include_outliers:
        word_list = [w for w in word_list if not w["is_outlier"]]

    # Sort by combined rank
    word_list.sort(key=lambda x: x["combined_rank"])

    # Apply limit if specified
    if limit:
        word_list = word_list[:limit]

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        for word_info in word_list:
            f.write(f"{word_info['word']}\n")

    logger.info(f"Exported {len(word_list)} words to {output_path}")
    return len(word_list)


def export_frequency_data(
    output_path: str,
    db_path: Optional[str] = constants.WORDFREQ_DB_PATH,
    format: str = "csv",
    limit: Optional[int] = None,
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
    config = DataSourceConfig(sqlite_path=db_path) if db_path else DataSourceConfig()
    word_list = calculate_combined_ranks(config=config, update_db=False)

    # Sort by combined rank
    word_list.sort(key=lambda x: x["combined_rank"])

    # Apply limit if specified
    if limit:
        word_list = word_list[:limit]

    # Get session
    config = DataSourceConfig(sqlite_path=db_path) if db_path else DataSourceConfig()
    session = get_session(config)

    # Get corpus names for headers
    corpora = session.query(Corpus).all()
    corpus_mapping = {c.id: c.name for c in corpora}

    if format.lower() == "csv":
        import csv

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            # Create headers
            headers = [
                "word",
                "combined_rank",
                "combined_rank_value",
                "harmonic_mean",
                "geometric_mean",
                "is_outlier",
                "z_score",
            ]
            for corpus in corpora:
                headers.append(f"rank_{corpus.name}")

            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            # Write data
            for word_info in word_list:
                row = {
                    "word": word_info["word"],
                    "combined_rank": word_info["combined_rank"],
                    "combined_rank_value": word_info["combined_rank_value"],
                    "harmonic_mean": word_info["harmonic_mean"],
                    "geometric_mean": word_info["geometric_mean"],
                    "is_outlier": "1" if word_info["is_outlier"] else "0",
                    "z_score": word_info["z_score"],
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

            json_data.append(
                {
                    "word": word_info["word"],
                    "combined_rank": word_info["combined_rank"],
                    "combined_rank_value": word_info["combined_rank_value"],
                    "harmonic_mean": word_info["harmonic_mean"],
                    "geometric_mean": word_info["geometric_mean"],
                    "is_outlier": word_info["is_outlier"],
                    "z_score": word_info["z_score"],
                    "corpus_ranks": named_ranks,
                }
            )

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
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
    config = DataSourceConfig()
    word_list = calculate_combined_ranks(config=config, update_db=False)

    # Get session
    session = get_session(config)

    # Get corpus information (only enabled corpora)
    corpora = wordfreq.frequency.corpus.get_corpus_configs_from_db(session, enabled_only=True)
    corpus_ids = [c.id for c in corpora]
    corpus_names = {c.id: c.name for c in corpora}

    if len(corpus_ids) < 2:
        logger.warning("Need at least 2 corpora for correlation analysis")
        return {}

    # Calculate correlations between each pair of corpora
    correlations: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for i, corpus1_id in enumerate(corpus_ids):
        corpus1_name = corpus_names[corpus1_id]
        correlations[corpus1_name] = {}

        for corpus2_id in corpus_ids[i + 1 :]:
            corpus2_name = corpus_names[corpus2_id]

            # Extract ranks for words that appear in both corpora
            ranks1 = []
            ranks2 = []

            for word_info in word_list:
                if corpus1_id in word_info["ranks"] and corpus2_id in word_info["ranks"]:
                    rank1 = word_info["ranks"][corpus1_id]
                    rank2 = word_info["ranks"][corpus2_id]

                    # Get effective unknown ranks for each corpus
                    unknown_rank1 = wordfreq.frequency.corpus.get_effective_unknown_rank(
                        corpus_names[corpus1_id], DEFAULT_UNKNOWN_RANK, session
                    )
                    unknown_rank2 = wordfreq.frequency.corpus.get_effective_unknown_rank(
                        corpus_names[corpus2_id], DEFAULT_UNKNOWN_RANK, session
                    )

                    # Only include if neither is the unknown rank
                    if rank1 != unknown_rank1 and rank2 != unknown_rank2:
                        ranks1.append(rank1)
                        ranks2.append(rank2)

            # Calculate correlation if enough data points
            if len(ranks1) > 10:
                try:
                    # Use Spearman rank correlation
                    from scipy.stats import spearmanr  # type: ignore[import-untyped]

                    corr, p_value = spearmanr(ranks1, ranks2)

                    correlations[corpus1_name][corpus2_name] = {
                        "correlation": corr,
                        "p_value": p_value,
                        "sample_size": len(ranks1),
                    }
                except ImportError:
                    logger.warning("scipy not available, using Pearson correlation")
                    # Fallback to Pearson correlation using standard library
                    mean1 = statistics.mean(ranks1)
                    mean2 = statistics.mean(ranks2)
                    numerator = sum((x - mean1) * (y - mean2) for x, y in zip(ranks1, ranks2))
                    sum_sq1 = sum((x - mean1) ** 2 for x in ranks1)
                    sum_sq2 = sum((y - mean2) ** 2 for y in ranks2)
                    denominator = math.sqrt(sum_sq1 * sum_sq2)
                    corr = numerator / denominator if denominator > 0 else 0.0
                    correlations[corpus1_name][corpus2_name] = {
                        "correlation": corr,
                        "p_value": None,
                        "sample_size": len(ranks1),
                    }

    return correlations
