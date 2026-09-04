"""Statistics and reporting query functions."""

from typing import Any, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from storage.models.schema import DerivativeForm, Lemma, WordToken
from storage.models.variant_form import VariantForm


def get_processing_stats(session: Session) -> Dict[str, Any]:
    """Get statistics about the current processing state.

    ``tokens_with_derivative_forms`` counts tokens some lemma claims, which is
    the coverage question worth asking. A lemma reaches a token through a
    ``DerivativeForm`` *or* a ``VariantForm`` -- the same two attachments
    ``storage.word_token_view`` collects -- so both count, or the British
    spelling of a word would read as uncovered vocabulary.

    Counting is over *distinct* tokens: a token with five inflections attached
    is one covered token, not five. Counting the join's rows instead let this
    figure exceed the total and put ``percent_complete`` above 100.
    """
    total_word_tokens = session.query(func.count(WordToken.id)).scalar()

    claimed_by_derivative = session.query(DerivativeForm.word_token_id).filter(
        DerivativeForm.word_token_id.isnot(None)
    )
    claimed_by_variant = session.query(VariantForm.word_token_id).filter(
        VariantForm.word_token_id.isnot(None)
    )
    tokens_with_derivative_forms = (
        session.query(func.count(WordToken.id))
        .filter(WordToken.id.in_(claimed_by_derivative.union(claimed_by_variant)))
        .scalar()
    )

    total_lemmas = session.query(func.count(Lemma.id)).scalar()
    total_derivative_forms = session.query(func.count(DerivativeForm.id)).scalar()

    return {
        "total_word_tokens": total_word_tokens or 0,
        "tokens_with_derivative_forms": tokens_with_derivative_forms or 0,
        "total_lemmas": total_lemmas or 0,
        "total_derivative_forms": total_derivative_forms or 0,
        "percent_complete": (
            (tokens_with_derivative_forms / total_word_tokens * 100) if total_word_tokens else 0
        ),
    }


def list_problematic_words(session: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """Get words that need review (unverified derivative forms).

    Ordered by ``Lemma.frequency_rank`` (combined across corpora and tier
    sources). Returns data in format expected by reviewer.py.
    """
    query = (
        session.query(WordToken, DerivativeForm, Lemma)
        .join(DerivativeForm, DerivativeForm.word_token_id == WordToken.id)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(DerivativeForm.verified == False)
        .order_by(Lemma.frequency_rank.nullslast())
        .limit(limit)
    )

    word_groups: Dict[str, Dict[str, Any]] = {}

    for word_token, derivative_form, lemma in query:
        word_text = word_token.token
        if word_text not in word_groups:
            word_groups[word_text] = {
                "word": word_text,
                "rank": lemma.frequency_rank,
                "definitions": [],
            }

        word_groups[word_text]["definitions"].append(
            {
                "text": lemma.definition_text,
                "pos": lemma.pos_type,
                "verified": derivative_form.verified,
            }
        )

    return list(word_groups.values())
