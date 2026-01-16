"""Workqueue handler for conversation generation tasks.

This module implements the conversation generation logic for background
processing via the Barsukas task worker.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from agents.common.wq_tools import build_default_config
from agents.sarka.agent import SarkaAgent
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def handle_generate_conversation(session: Session, payload: Dict) -> str:
    """Handle conversation generation task (workqueue entry point).

    Payload schema:
        words: list[dict] - List of word info dicts with lemma_text and lemma_id
        level: int - Difficulty level for the conversation
        num_sentences: int - Target number of sentences (default: 8)

    Returns:
        str: Result message describing what was generated
    """
    words = payload.get("words", [])
    level = payload.get("level", 1)
    num_sentences = payload.get("num_sentences", 8)

    if not words:
        raise ValueError("No words provided in payload")

    # Create agent with default config
    config = build_default_config()
    agent = SarkaAgent(config=config)

    # Generate the conversation
    result = agent.generate_conversation(
        words=words,
        level=level,
        num_sentences=num_sentences,
        dry_run=False,
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    conversation_id = result.get("conversation_id")
    title = result.get("title", "Untitled")
    num_generated = result.get("num_sentences", 0)
    word_list = ", ".join(result.get("words", []))

    return f"Generated conversation {conversation_id}: '{title}' with {num_generated} sentences (words: {word_list})"
