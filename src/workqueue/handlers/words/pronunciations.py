"""Capability handlers for word pronunciation tasks."""

from __future__ import annotations

from typing import Any, Optional

from workqueue.handlers.papuga import generate_pronunciations_for_lemma
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_pronunciations(
    session: Any,
    lemma_id: int,
    lang_code: str = "en",
    all_forms_pronunciation: bool = False,
    **_: Any,
) -> str:
    """Generate pronunciations for all missing forms on a lemma."""
    lemma = get_lemma_or_raise(session, lemma_id)
    generated_count, errors = generate_pronunciations_for_lemma(
        session,
        lemma,
        lang_code,
        all_forms_pronunciation=all_forms_pronunciation,
    )
    session.commit()

    if generated_count == 0 and not errors:
        return f"No missing pronunciations for {lang_code} forms"
    if generated_count == 0 and errors:
        raise RuntimeError("; ".join(errors))
    return f"Generated pronunciations for {generated_count} form(s)"


@workqueue_payload_handler()
def handle_words_pronunciations(
    session: Any,
    lemma_id: Optional[int] = None,
    lemma_ids: Optional[list[int]] = None,
    lang_code: str = "en",
    all_forms_pronunciation: bool = False,
) -> str:
    """Workqueue wrapper for pronunciation generation."""
    if lemma_ids:
        results = [
            do_generate_pronunciations(
                session=session,
                lemma_id=queued_lemma_id,
                lang_code=lang_code,
                all_forms_pronunciation=all_forms_pronunciation,
            )
            for queued_lemma_id in lemma_ids
        ]
        return f"Batch completed for {len(lemma_ids)} lemmas: " + "; ".join(results)
    if lemma_id is None:
        raise ValueError("lemma_id or lemma_ids is required")
    return do_generate_pronunciations(
        session=session,
        lemma_id=lemma_id,
        lang_code=lang_code,
        all_forms_pronunciation=all_forms_pronunciation,
    )
