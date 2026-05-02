"""POS-based query functions, ordered by ``Lemma.frequency_rank``.

Lemma-level frequency_rank is the combined rank computed by
``wordfreq.frequency.combined_rank``; it folds in every enabled wordfreq corpus
plus the YLE/CEFR tier signals, so per-corpus ordering here is no longer
required.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from storage.models.schema import DerivativeForm, Lemma, WordToken


def get_common_words_by_pos(
    session: Session,
    pos_type: str,
    language_code: str = "en",
    pos_subtype: Optional[str] = None,
    corpus_name: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return the most common word tokens for a part of speech.

    ``corpus_name`` is accepted for API compatibility but ignored — ranking is
    by ``Lemma.frequency_rank`` (combined across corpora and tier sources).
    """
    del corpus_name  # ignored

    query = (
        session.query(WordToken, DerivativeForm, Lemma)
        .join(DerivativeForm, DerivativeForm.word_token_id == WordToken.id)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(Lemma.pos_type == pos_type)
        .filter(DerivativeForm.language_code == language_code)
        .filter(Lemma.frequency_rank.isnot(None))
    )

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.order_by(Lemma.frequency_rank).limit(limit)

    results = []
    for word_token, derivative_form, lemma in query:
        results.append(
            {
                "token": word_token.token,
                "language_code": word_token.language_code,
                "rank": lemma.frequency_rank,
                "pos": pos_type,
                "pos_subtype": lemma.pos_subtype,
                "lemma": lemma.lemma_text,
                "definition": lemma.definition_text,
                "grammatical_form": derivative_form.grammatical_form,
                "is_base_form": derivative_form.is_base_form,
                "verified": derivative_form.verified,
            }
        )

    return results


def get_common_base_forms_by_pos(
    session: Session,
    pos_type: str,
    language_code: str = "en",
    pos_subtype: Optional[str] = None,
    corpus_name: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return the most common base forms for a part of speech.

    ``corpus_name`` is accepted for API compatibility but ignored — see
    ``get_common_words_by_pos``.
    """
    del corpus_name  # ignored

    query = (
        session.query(WordToken, DerivativeForm, Lemma)
        .join(DerivativeForm, DerivativeForm.word_token_id == WordToken.id)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(Lemma.pos_type == pos_type)
        .filter(DerivativeForm.is_base_form == True)
        .filter(DerivativeForm.language_code == language_code)
        .filter(Lemma.frequency_rank.isnot(None))
    )

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.order_by(Lemma.frequency_rank).limit(limit)

    results = []
    for word_token, derivative_form, lemma in query:
        results.append(
            {
                "token": word_token.token,
                "language_code": word_token.language_code,
                "rank": lemma.frequency_rank,
                "pos": pos_type,
                "pos_subtype": lemma.pos_subtype,
                "lemma": lemma.lemma_text,
                "definition": lemma.definition_text,
                "grammatical_form": derivative_form.grammatical_form,
                "verified": derivative_form.verified,
            }
        )

    return results
