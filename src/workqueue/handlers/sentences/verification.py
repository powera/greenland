"""Sentence translation and lemma-link verification handlers."""

from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from sentences.verification import verify_sentence_links, verify_sentence_translations
from workqueue.tools import build_default_config, workqueue_payload_handler


@workqueue_payload_handler()
def handle_sentences_translations_verify(
    session: Session,
    sentence_id: int,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Verify one sentence's translations and persist verdicts by default."""
    config = build_default_config()
    if model:
        config = config.with_model(model)
    result = verify_sentence_translations(
        session=session,
        sentence_id=sentence_id,
        config=config,
        languages=languages,
        persist=True,
    )
    language_results = result["results"]
    correct_count = sum(
        language_result["meaning_correct"] == "correct"
        and language_result["grammar_correct"] == "correct"
        for language_result in language_results.values()
    )
    return (
        f"Verified {len(language_results)} translation(s) for sentence {sentence_id}: "
        f"{correct_count} correct, {len(language_results) - correct_count} incorrect"
    )


@workqueue_payload_handler()
def handle_sentences_links_verify(
    session: Session,
    sentence_id: int,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Verify one sentence's lemma links and return a result summary."""
    config = build_default_config()
    if model:
        config = config.with_model(model)
    result = verify_sentence_links(
        session=session,
        sentence_id=sentence_id,
        config=config,
        languages=languages,
    )
    link_count = sum(len(language_results) for language_results in result["results"].values())
    incorrect_count = sum(
        link_result["sense_correct"] != "correct" or link_result["form_matches"] != "correct"
        for language_results in result["results"].values()
        for link_result in language_results.values()
    )
    return json.dumps(
        {
            "summary": (
                f"Verified {link_count} lemma link(s) for sentence {sentence_id}: "
                f"{incorrect_count} with issues"
            ),
            "results": result["results"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
