"""Capability handlers for word synonym tasks."""

from __future__ import annotations

from typing import Any, Optional

from workqueue.handlers.sernas import generate_synonyms_for_lemma
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_synonyms(
    session: Any,
    lemma_id: int,
    lang_code: str,
    form_type: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate synonyms/alternative forms for a lemma and language."""
    lemma = get_lemma_or_raise(session, lemma_id)
    result = generate_synonyms_for_lemma(session, lemma, lang_code)
    session.commit()

    if not result.get("success"):
        error_message = result.get("error", "Unknown synonym generation error")
        raise RuntimeError(error_message)

    if form_type:
        return f"Generated {form_type} for {lang_code}"
    total = (
        result.get("stored_synonyms", 0)
        + result.get("stored_abbreviations", 0)
        + result.get("stored_expanded_forms", 0)
    )
    return f"Generated {total} synonym/alternative form(s)"


@workqueue_payload_handler()
def handle_words_synonyms(
    session: Any,
    lemma_id: int,
    lang_code: str,
    form_type: Optional[str] = None,
) -> str:
    """Workqueue wrapper for synonym generation."""
    return do_generate_synonyms(
        session=session,
        lemma_id=lemma_id,
        lang_code=lang_code,
        form_type=form_type,
    )
