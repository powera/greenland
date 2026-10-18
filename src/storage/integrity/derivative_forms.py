"""Integrity checks for derivative-form relationships.

These functions use a caller-owned session.  They never commit, roll back, or
close it.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from storage.models.schema import DerivativeForm, Lemma, WordToken
from storage.token_forms import TOKEN_FORM_SOURCES

logger = logging.getLogger(__name__)


def _texts_match(form_text: str, token_text: str, exact_case_only: bool) -> bool:
    if exact_case_only:
        return form_text == token_text
    return form_text.lower() == token_text.lower()


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
    """Return invalid token references and form/token text mismatches.

    Covers every form table in ``storage.token_forms.TOKEN_FORM_SOURCES`` --
    derivative, variant and name forms -- since any of them can be left
    pointing at the wrong token when token ids are reused.  The text comparison
    follows the linker's rule: exact for a source with ``exact_case_only``
    (names), case-insensitive otherwise, so a legitimate lowercase-fallback
    link is not reported.
    """
    logger.info("Checking form word token references...")
    try:
        word_tokens = {
            token_id: token_text
            for token_id, token_text in session.query(WordToken.id, WordToken.token).all()
        }
        issues: List[Dict[str, Any]] = []
        total_checked = 0
        for source in TOKEN_FORM_SOURCES:
            forms = session.query(source.model).filter(source.model.word_token_id.isnot(None)).all()
            total_checked += len(forms)
            for form in forms:
                form_issues: List[str] = []
                token_text = word_tokens.get(form.word_token_id)
                if token_text is None:
                    form_issues.append(f"invalid_word_token_id: {form.word_token_id}")
                elif not _texts_match(form.surface_text, token_text, source.exact_case_only):
                    form_issues.append(
                        f"text_mismatch: form_text='{form.surface_text}' "
                        f"but word_token.token='{token_text}'"
                    )
                if form_issues:
                    issues.append(
                        {
                            "table": source.table_name,
                            "id": form.id,
                            "form_text": form.surface_text,
                            "word_token_id": form.word_token_id,
                            "element_type": form.owner.element_type,
                            "element_id": form.owner.element_id,
                            "language_code": form.language_code,
                            "issues": form_issues,
                        }
                    )
        return {
            "total_checked": total_checked,
            "issue_count": len(issues),
            "issues": issues,
        }
    except Exception as error:
        logger.error("Error checking derivative form word tokens: %s", error)
        return {"error": str(error), "total_checked": 0, "issue_count": 0, "issues": []}
