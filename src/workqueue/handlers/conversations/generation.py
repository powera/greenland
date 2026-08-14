"""Workqueue entry points for vocabulary-driven conversation generation."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from sentences.conversation_generation import (
    generate_conversation_with_session,
    generate_definition_with_session,
)
from workqueue.tools import build_default_config


def handle_conversations_generate(session: Session, payload: Dict[str, Any]) -> str:
    """Generate and store a vocabulary-driven conversation."""
    words = payload.get("words", [])
    if not words:
        raise ValueError("No words provided in payload")

    config = build_default_config()
    if payload.get("model"):
        config = config.with_model(payload["model"])
    result = generate_conversation_with_session(
        session=session,
        words=words,
        level=payload.get("level", 1),
        num_sentences=payload.get("num_sentences", 8),
        config=config,
    )
    if result.get("error"):
        raise RuntimeError(result["error"])

    session.commit()
    word_list = ", ".join(result.get("words", []))
    return (
        f"Generated conversation {result.get('conversation_id')}: "
        f"'{result.get('title', 'Untitled')}' with "
        f"{result.get('num_sentences', 0)} sentences (words: {word_list})"
    )


def handle_conversations_definitions_generate(session: Session, payload: Dict[str, Any]) -> str:
    """Generate and store a vocabulary comparison narrative."""
    words = payload.get("words", [])
    if not words:
        raise ValueError("No words provided in payload")

    config = build_default_config()
    if payload.get("model"):
        config = config.with_model(payload["model"])
    result = generate_definition_with_session(
        session=session,
        words=words,
        level=payload.get("level", 1),
        num_sentences=payload.get("num_sentences", 10),
        config=config,
    )
    if result.get("error"):
        raise RuntimeError(result["error"])

    session.commit()
    word_list = ", ".join(result.get("words", []))
    return (
        f"Generated word definition {result.get('conversation_id')}: "
        f"'{result.get('title', 'Untitled')}' with "
        f"{result.get('num_sentences', 0)} sentences (words: {word_list})"
    )


# Compatibility names for imports used before capability-based handler naming.
handle_generate_conversation = handle_conversations_generate
handle_generate_definition = handle_conversations_definitions_generate

__all__ = [
    "handle_conversations_definitions_generate",
    "handle_conversations_generate",
    "handle_generate_conversation",
    "handle_generate_definition",
]
