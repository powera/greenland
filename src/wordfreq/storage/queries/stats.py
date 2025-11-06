"""Statistics and reporting query functions."""

from typing import Dict, Any, List
from sqlalchemy.sql import func

from wordfreq.storage.models.schema import WordToken, DerivativeForm, Lemma, ExampleSentence, WordFrequency, Corpus


def get_processing_stats(session) -> Dict[str, Any]:
    """Get statistics about the current processing state."""
    total_word_tokens = session.query(func.count(WordToken.id)).scalar()
    tokens_with_derivative_forms = session.query(func.count(WordToken.id))\
        .join(DerivativeForm).scalar()

    # Count tokens with at least one example sentence
    tokens_with_examples = session.query(func.count(WordToken.id))\
        .join(DerivativeForm)\
        .join(ExampleSentence)\
        .scalar()

    # Count totals
    total_lemmas = session.query(func.count(Lemma.id)).scalar()
    total_derivative_forms = session.query(func.count(DerivativeForm.id)).scalar()
    total_example_sentences = session.query(func.count(ExampleSentence.id)).scalar()

    return {
        "total_word_tokens": total_word_tokens or 0,
        "tokens_with_derivative_forms": tokens_with_derivative_forms or 0,
        "tokens_with_examples": tokens_with_examples or 0,
        "total_lemmas": total_lemmas or 0,
        "total_derivative_forms": total_derivative_forms or 0,
        "total_example_sentences": total_example_sentences or 0,
        "percent_complete": (tokens_with_derivative_forms / total_word_tokens * 100) if total_word_tokens else 0
    }


def list_problematic_words(session, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get words that need review (unverified derivative forms).
    Returns data in format expected by reviewer.py.
    """
    # Query derivative forms that are unverified
    query = session.query(WordToken, DerivativeForm, Lemma, WordFrequency)\
        .join(DerivativeForm)\
        .join(Lemma)\
        .outerjoin(WordFrequency)\
        .outerjoin(Corpus, WordFrequency.corpus_id == Corpus.id)\
        .filter(DerivativeForm.verified == False)\
        .filter((Corpus.name == "wiki_vital") | (Corpus.name == None))\
        .order_by(WordFrequency.rank.nullslast())\
        .limit(limit)

    results = []
    word_groups = {}

    # Group by word token
    for word_token, derivative_form, lemma, word_frequency in query:
        word_text = word_token.token
        if word_text not in word_groups:
            word_groups[word_text] = {
                'word': word_text,
                'rank': word_frequency.rank if word_frequency else None,
                'definitions': []
            }

        word_groups[word_text]['definitions'].append({
            'text': lemma.definition_text,
            'pos': lemma.pos_type,
            'verified': derivative_form.verified
        })

    return list(word_groups.values())
