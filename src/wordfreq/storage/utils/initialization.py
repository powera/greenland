"""Corpus initialization utilities."""

import logging


logger = logging.getLogger(__name__)


def initialize_corpora(session):
    """Initialize corpus configurations from the config file."""
    import wordfreq.frequency.corpus

    result = wordfreq.frequency.corpus.initialize_corpus_configs(session)
    if not result["success"]:
        logger.error(f"Failed to initialize corpora: {result['errors']}")
        raise RuntimeError(f"Corpus initialization failed: {result['errors']}")

    logger.info(
        f"Corpus initialization completed: {result['added']} added, {result['updated']} updated"
    )
