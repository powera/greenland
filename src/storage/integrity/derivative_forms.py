"""Integrity checks for derivative-form relationships.

These functions use a caller-owned session.  They never commit, roll back, or
close it.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from storage.models.schema import DerivativeForm, Lemma, WordToken

logger = logging.getLogger(__name__)


def check_orphaned_derivative_forms(session: Session) -> Dict[str, Any]:
    """Return derivative forms whose lemma reference does not exist."""
    logger.info("Checking for orphaned derivative forms...")
    try:
        valid_lemma_ids = {lemma_id for lemma_id, in session.query(Lemma.id).all()}
        derivative_forms = session.query(DerivativeForm).all()
        orphaned_forms = [
            {
                "id": form.id,
                "derivative_form_text": form.derivative_form_text,
                "language_code": form.language_code,
                "invalid_lemma_id": form.lemma_id,
            }
            for form in derivative_forms
            if form.lemma_id not in valid_lemma_ids
        ]
        return {
            "total_checked": len(derivative_forms),
            "orphaned_count": len(orphaned_forms),
            "orphaned_forms": orphaned_forms,
        }
    except Exception as error:
        logger.error("Error checking orphaned derivative forms: %s", error)
        return {
            "error": str(error),
            "total_checked": 0,
            "orphaned_count": 0,
            "orphaned_forms": [],
        }


def check_derivative_form_word_tokens(session: Session) -> Dict[str, Any]:
    """Return invalid token references and derivative/token text mismatches."""
    logger.info("Checking derivative form word token references...")
    try:
        word_tokens = {
            token_id: token_text
            for token_id, token_text in session.query(WordToken.id, WordToken.token).all()
        }
        derivative_forms = (
            session.query(DerivativeForm).filter(DerivativeForm.word_token_id.isnot(None)).all()
        )
        issues: List[Dict[str, Any]] = []
        for derivative_form in derivative_forms:
            form_issues: List[str] = []
            if derivative_form.word_token_id not in word_tokens:
                form_issues.append(f"invalid_word_token_id: {derivative_form.word_token_id}")
            elif derivative_form.derivative_form_text != word_tokens[derivative_form.word_token_id]:
                expected_token = word_tokens[derivative_form.word_token_id]
                form_issues.append(
                    f"text_mismatch: derivative_form_text='{derivative_form.derivative_form_text}' "
                    f"but word_token.token='{expected_token}'"
                )
            if form_issues:
                issues.append(
                    {
                        "id": derivative_form.id,
                        "derivative_form_text": derivative_form.derivative_form_text,
                        "word_token_id": derivative_form.word_token_id,
                        "lemma_id": derivative_form.lemma_id,
                        "language_code": derivative_form.language_code,
                        "issues": form_issues,
                    }
                )
        return {
            "total_checked": len(derivative_forms),
            "issue_count": len(issues),
            "issues": issues,
        }
    except Exception as error:
        logger.error("Error checking derivative form word tokens: %s", error)
        return {"error": str(error), "total_checked": 0, "issue_count": 0, "issues": []}
