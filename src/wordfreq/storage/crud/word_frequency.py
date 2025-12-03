"""CRUD operations for WordFrequency model."""

from typing import Optional

from wordfreq.storage.models.schema import WordToken, WordFrequency, Corpus


def add_word_frequency(
    session,
    word_token: WordToken,
    corpus_name: str,
    rank: Optional[int] = None,
    frequency: Optional[float] = None,
) -> WordFrequency:
    """Add word frequency data for a word token in a specific corpus."""
    # Get or create corpus
    corpus = session.query(Corpus).filter(Corpus.name == corpus_name).first()
    if not corpus:
        corpus = Corpus(name=corpus_name)
        session.add(corpus)
        session.flush()

    # Check if frequency already exists
    existing = (
        session.query(WordFrequency)
        .filter(WordFrequency.word_token_id == word_token.id, WordFrequency.corpus_id == corpus.id)
        .first()
    )

    if existing:
        # Update existing frequency
        if rank is not None:
            existing.rank = rank
        if frequency is not None:
            existing.frequency = frequency
        session.commit()
        return existing

    # Create new frequency record
    word_freq = WordFrequency(
        word_token_id=word_token.id, corpus_id=corpus.id, rank=rank, frequency=frequency
    )
    session.add(word_freq)
    session.commit()
    return word_freq
