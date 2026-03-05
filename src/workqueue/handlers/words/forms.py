"""Capability handlers for word form tasks."""

from __future__ import annotations

from typing import Any

from workqueue.handlers.vilkas import generate_forms_for_lemma
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_forms(
    session: Any,
    lemma_id: int,
    lang_code: str = "lt",
    language_code: str | None = None,
    **_: Any,
) -> str:
    """Generate forms for a lemma/language pair."""
    effective_lang_code = language_code or lang_code
    lemma = get_lemma_or_raise(session, lemma_id)
    success, error_message = generate_forms_for_lemma(session, lemma, effective_lang_code)
    session.commit()
    if success:
        return f"Generated {effective_lang_code} {lemma.pos_type} forms"
    raise RuntimeError(error_message)


@workqueue_payload_handler()
def handle_words_forms(
    session: Any,
    lemma_id: int,
    lang_code: str = "lt",
    language_code: str | None = None,
) -> str:
    """Workqueue wrapper for form generation."""
    return do_generate_forms(
        session=session,
        lemma_id=lemma_id,
        lang_code=lang_code,
        language_code=language_code,
    )
