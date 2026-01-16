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
        keywords: dict - Keywords to use for generation (optional)
            - colors: list[str] - Color keywords
            - body_part: str - Body part keyword
            - emotion: str - Emotion keyword
            - occupation: str - Occupation keyword
            - theme: str - Conversation theme
        num_sentences: int - Target number of sentences (default: 6)

    Returns:
        str: Result message describing what was generated
    """
    keywords = payload.get("keywords")
    num_sentences = payload.get("num_sentences", 6)

    # Create agent with default config
    config = build_default_config()
    agent = SarkaAgent(config=config)

    # Generate the conversation
    result = agent.generate_conversation(
        keywords=keywords,
        num_sentences=num_sentences,
        dry_run=False,
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    conversation_id = result.get("conversation_id")
    title = result.get("title", "Untitled")
    num_generated = result.get("num_sentences", 0)

    return f"Generated conversation {conversation_id}: '{title}' with {num_generated} sentences"
