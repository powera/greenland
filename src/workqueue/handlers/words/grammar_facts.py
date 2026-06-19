"""Capability handlers for word grammar fact tasks."""

from __future__ import annotations

from typing import Any

from workqueue.handlers.lape import generate_grammar_fact_for_lemma
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_grammar_fact(
    session: Any,
    lemma_id: int,
    fact_type: str,
    lang_code: str = "en",
    language_code: str | None = None,
    **_: Any,
) -> str:
    """Generate one grammar fact for one lemma."""
    effective_language_code = language_code or lang_code
    lemma = get_lemma_or_raise(session, lemma_id)
    result = generate_grammar_fact_for_lemma(session, lemma, fact_type, effective_language_code)

    session.commit()

    if result.get("skipped"):
        return f"Skipped: {fact_type} already exists ({result.get('existing_value')})"
    if result.get("error"):
        raise RuntimeError(result["error"])

    return f"Generated {fact_type}: {result['fact_value']} (confidence: {result['confidence']:.2f})"


@workqueue_payload_handler()
def handle_words_grammar_facts(
    session: Any,
    lemma_id: int,
    fact_type: str,
    lang_code: str = "en",
    language_code: str | None = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for grammar fact generation.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    return do_generate_grammar_fact(
        session=session,
        lemma_id=lemma_id,
        fact_type=fact_type,
        lang_code=lang_code,
        language_code=language_code,
    )
