"""The ``words.translations.verify`` capability handler."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.orm import Session

from words.verification import verify_word_translations
from workqueue.tools import build_default_config, workqueue_payload_handler


@workqueue_payload_handler()
def handle_words_translations_verify(
    session: Session,
    lemma_id: int,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Verify one lemma's translations and persist verdicts by default."""
    config = build_default_config()
    if model:
        config = config.with_model(model)
    result = verify_word_translations(
        session=session,
        lemma_id=lemma_id,
        config=config,
        languages=languages,
        persist=True,
    )
    verdicts = result["results"]
    correct_count = sum(verdict == "correct" for verdict in verdicts.values())
    return (
        f"Verified {len(verdicts)} translation(s) for lemma {lemma_id}: "
        f"{correct_count} correct, {len(verdicts) - correct_count} incorrect"
    )
