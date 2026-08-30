"""CRUD operations for WordToken model."""

from typing import List, Optional, cast

from sqlalchemy.orm import Session

from storage.models.schema import DerivativeForm, WordToken


def add_word_token(session: Session, token: str, language_code: str) -> WordToken:
    """Add a word token to the database if it doesn't exist, or return existing one."""
    existing: Optional[WordToken] = (
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


def get_word_token_by_text(
    session: Session, token_text: str, language_code: str
) -> Optional[WordToken]:
    """Get a word token from the database by its text and language."""
    result: Optional[WordToken] = (
        session.query(WordToken)
        .filter(WordToken.token == token_text, WordToken.language_code == language_code)
        .first()
    )
    return result


def get_word_tokens_needing_analysis(session: Session, limit: int = 100) -> List[WordToken]:
    """Get word tokens that need linguistic analysis (no derivative forms)."""
    result: list[WordToken] = (
        session.query(WordToken)
        .outerjoin(DerivativeForm)
        .filter(DerivativeForm.id == None)
        .limit(limit)
        .all()
    )
    return result


def get_word_tokens_by_combined_frequency_rank(
    session: Session, limit: int = 1000
) -> List[WordToken]:
    """
    Get word tokens ordered by their combined frequency rank.

    Args:
        session: Database session
        limit: Maximum number of words to retrieve

    Returns:
        List of WordToken objects ordered by frequency_rank (combined harmonic mean rank)
    """
    result: list[WordToken] = (
        session.query(WordToken)
        .filter(WordToken.frequency_rank != None)
        .order_by(WordToken.frequency_rank)
        .limit(limit)
        .all()
    )
    return result
