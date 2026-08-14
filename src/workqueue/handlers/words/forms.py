"""Capability handlers for word form tasks."""

from __future__ import annotations

from typing import Any, Optional

from workqueue.handlers.vilkas import generate_forms_for_lemma
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_forms(
    session: Any,
    lemma_id: int,
    language_code: str = "lt",
    lang_code: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate forms for a lemma/language pair."""
    effective_language_code = lang_code or language_code
    lemma = get_lemma_or_raise(session, lemma_id)
    success, error_message = generate_forms_for_lemma(session, lemma, effective_language_code)
    session.commit()
    if success:
        return f"Generated {effective_language_code} {lemma.pos_type} forms"
    raise RuntimeError(error_message)


@workqueue_payload_handler()
def handle_words_forms(
    session: Any,
    lemma_id: Optional[int] = None,
    lemma_ids: Optional[list[int]] = None,
    language_code: str = "lt",
    lang_code: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for form generation.

    Accepts and ignores extra payload kwargs (``model``, ``batch``, etc.) added
    by the route so it is tolerant of payload changes.
    """
    if lemma_ids:
        results = [
            do_generate_forms(
                session=session,
                lemma_id=queued_lemma_id,
                language_code=language_code,
                lang_code=lang_code,
            )
            for queued_lemma_id in lemma_ids
        ]
        return f"Batch completed for {len(lemma_ids)} lemmas: " + "; ".join(results)
    if lemma_id is None:
        raise ValueError("lemma_id or lemma_ids is required")
    return do_generate_forms(
        session=session,
        lemma_id=lemma_id,
        language_code=language_code,
        lang_code=lang_code,
    )
