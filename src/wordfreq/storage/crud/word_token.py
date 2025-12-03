"""CRUD operations for WordToken model."""

from typing import List, Optional

from wordfreq.storage.models.schema import WordToken, DerivativeForm, WordFrequency, Corpus


def add_word_token(session, token: str, language_code: str) -> WordToken:
    """Add a word token to the database if it doesn't exist, or return existing one."""
    existing = (
        session.query(WordToken)
        .filter(WordToken.token == token, WordToken.language_code == language_code)
        .first()
    )
    if existing:
        return existing

    new_token = WordToken(token=token, language_code=language_code)
    session.add(new_token)
    session.commit()
    return new_token


def get_word_token_by_text(session, token_text: str, language_code: str) -> Optional[WordToken]:
    """Get a word token from the database by its text and language."""
    return (
        session.query(WordToken)
        .filter(WordToken.token == token_text, WordToken.language_code == language_code)
        .first()
    )


def get_word_tokens_needing_analysis(session, limit: int = 100) -> List[WordToken]:
    """Get word tokens that need linguistic analysis (no derivative forms)."""
    return (
        session.query(WordToken)
        .outerjoin(DerivativeForm)
        .filter(DerivativeForm.id == None)
        .limit(limit)
        .all()
    )


def get_word_tokens_by_frequency_rank(
    session, corpus_name: str, limit: int = 100
) -> List[WordToken]:
    """Get word tokens ordered by frequency rank in a specific corpus."""
    return (
        session.query(WordToken)
        .join(WordFrequency)
        .join(Corpus)
        .filter(Corpus.name == corpus_name)
        .filter(WordFrequency.rank != None)
        .order_by(WordFrequency.rank)
        .limit(limit)
        .all()
    )


def get_word_tokens_by_combined_frequency_rank(session, limit: int = 1000) -> List[WordToken]:
    """
    Get word tokens ordered by their combined frequency rank.

    Args:
        session: Database session
        limit: Maximum number of words to retrieve

    Returns:
        List of WordToken objects ordered by frequency_rank (combined harmonic mean rank)
    """
    return (
        session.query(WordToken)
        .filter(WordToken.frequency_rank != None)
        .order_by(WordToken.frequency_rank)
        .limit(limit)
        .all()
    )
