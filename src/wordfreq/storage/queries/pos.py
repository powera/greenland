"""POS-based query functions."""

from typing import Dict, Any, List

from wordfreq.storage.models.schema import WordToken, DerivativeForm, Lemma, WordFrequency, Corpus


def get_common_words_by_pos(session, pos_type: str, language_code: str = "en", pos_subtype: str = None, corpus_name: str = "wiki_vital", limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get the most common word tokens for a specified part of speech.

    Args:
        session: Database session
        pos_type: Part of speech type to filter by
        language_code: Language code to filter by (default: "en")
        pos_subtype: Optional POS subtype to filter by
        corpus_name: Corpus to use for frequency ranking
        limit: Maximum number of words to return

    Returns:
        List of dictionaries containing word information
    """
    # Query word tokens with derivative forms of the specified part of speech, ordered by frequency rank
    query = session.query(WordToken, DerivativeForm, Lemma, WordFrequency)\
        .join(DerivativeForm)\
        .join(Lemma)\
        .join(WordFrequency)\
        .join(Corpus)\
        .filter(Lemma.pos_type == pos_type)\
        .filter(DerivativeForm.language_code == language_code)\
        .filter(Corpus.name == corpus_name)\
        .filter(WordFrequency.rank != None)

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.order_by(WordFrequency.rank).limit(limit)

    results = []
    for word_token, derivative_form, lemma, word_frequency in query:
        results.append({
            "token": word_token.token,
            "language_code": word_token.language_code,
            "rank": word_frequency.rank,
            "pos": pos_type,
            "pos_subtype": lemma.pos_subtype,
            "lemma": lemma.lemma_text,
            "definition": lemma.definition_text,
            "grammatical_form": derivative_form.grammatical_form,
            "is_base_form": derivative_form.is_base_form,
            "verified": derivative_form.verified
        })

    return results


def get_common_base_forms_by_pos(session, pos_type: str, language_code: str = "en", pos_subtype: str = None, corpus_name: str = "wiki_vital", limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get the most common base forms for a specified part of speech.

    Args:
        session: Database session
        pos_type: Part of speech type to filter by
        language_code: Language code to filter by (default: "en")
        pos_subtype: Optional POS subtype to filter by
        corpus_name: Corpus to use for frequency ranking
        limit: Maximum number of words to return

    Returns:
        List of dictionaries containing base form information
    """
    query = session.query(WordToken, DerivativeForm, Lemma, WordFrequency)\
        .join(DerivativeForm)\
        .join(Lemma)\
        .join(WordFrequency)\
        .join(Corpus)\
        .filter(Lemma.pos_type == pos_type)\
        .filter(DerivativeForm.is_base_form == True)\
        .filter(DerivativeForm.language_code == language_code)\
        .filter(Corpus.name == corpus_name)\
        .filter(WordFrequency.rank != None)

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.order_by(WordFrequency.rank).limit(limit)

    results = []
    for word_token, derivative_form, lemma, word_frequency in query:
        results.append({
            "token": word_token.token,
            "language_code": word_token.language_code,
            "rank": word_frequency.rank,
            "pos": pos_type,
            "pos_subtype": lemma.pos_subtype,
            "lemma": lemma.lemma_text,
            "definition": lemma.definition_text,
            "grammatical_form": derivative_form.grammatical_form,
            "verified": derivative_form.verified
        })

    return results
