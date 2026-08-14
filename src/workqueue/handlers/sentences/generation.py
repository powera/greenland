"""Capability handlers for sentence generation tasks."""

from __future__ import annotations

from typing import Any, List, Optional

from sentences.generation import (
    generate_examples_for_lemma,
    generate_pattern_candidates,
)
from workqueue.tools import build_default_config, workqueue_payload_handler


@workqueue_payload_handler()
def handle_sentences_patterns_generate(
    session: Any,
    pattern_ids: Optional[List[str]] = None,
    all_patterns: bool = False,
    max_combinations: Optional[int] = None,
    **_: Any,
) -> str:
    """Generate stored sentence candidates from one or more patterns."""
    result = generate_pattern_candidates(
        session=session,
        config=build_default_config(),
        pattern_ids=pattern_ids,
        all_patterns=all_patterns,
        max_combinations=max_combinations,
    )
    return (
        f"Generated {result['stored']} candidates from "
        f"{result['patterns_processed']} patterns; "
        f"{result['duplicates']} duplicates, {result['errors']} errors"
    )


@workqueue_payload_handler()
def handle_sentences_examples_generate(
    session: Any,
    lemma_id: int,
    mode: str,
    num_sentences: int = 3,
    max_combinations: Optional[int] = None,
    difficulty_context: Optional[int] = None,
    max_vocabulary_level: int = 7,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate and store examples for one lemma."""
    config = build_default_config()
    if model:
        config = config.with_model(model)
    result = generate_examples_for_lemma(
        session=session,
        config=config,
        lemma_id=lemma_id,
        mode=mode,
        num_sentences=num_sentences,
        max_combinations=max_combinations,
        difficulty_context=difficulty_context,
        max_vocabulary_level=max_vocabulary_level,
    )
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    storage = result.get("storage", {})
    stored = result.get("stored", storage.get("stored", 0))
    return f"Generated sentence examples for lemma {lemma_id} in {mode} mode; stored {stored}"
