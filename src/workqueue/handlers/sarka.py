"""Workqueue handler for conversation generation tasks.

This module implements the conversation generation logic for background
processing via the Barsukas task worker.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agents.common.wq_tools import build_default_config
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from sqlalchemy.orm import Session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.crud.conversation import add_conversation, add_conversation_sentence
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.crud.sentence import add_sentence
from wordfreq.storage.crud.sentence_translation import add_sentence_translation
import util.prompt_loader

logger = logging.getLogger(__name__)


def _get_llm_client(config: DataSourceConfig) -> UnifiedLLMClient:
    """Get LLM client for queries."""
    client = UnifiedLLMClient.from_config(config)
    if config.model:
        client.warm_model(config.model)
    return client


def _query_conversation_llm(
    word_list: List[str], num_sentences: int, config: DataSourceConfig
) -> Dict[str, Any]:
    """Query the LLM to generate a conversation.

    Args:
        word_list: List of words to incorporate
        num_sentences: Target number of sentences
        config: DataSourceConfig for LLM settings

    Returns:
        Dictionary with conversation data or error
    """
    # Load prompts
    try:
        context = util.prompt_loader.get_context("conversations", "generate")
        prompt_template = util.prompt_loader.get_prompt("conversations", "generate")
    except Exception as e:
        logger.error(f"Failed to load conversation prompts: {e}")
        return {"success": False, "error": f"Failed to load prompts: {e}"}

    # Format word list for prompt
    word_list_str = "\n".join(f"- {word}" for word in word_list)

    prompt_text = prompt_template.format(
        word_list=word_list_str,
        num_sentences=num_sentences,
    )

    # Define JSON schema for response
    schema = Schema(
        name="ConversationGeneration",
        description="Generate a simple conversation for language learning",
        properties={
            "title": SchemaProperty("string", "A short title describing the conversation scenario"),
            "sentences": SchemaProperty(
                "array",
                "List of conversation exchanges",
                items={
                    "type": "object",
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "description": "Speaker identifier (A or B)",
                        },
                        "text": {
                            "type": "string",
                            "description": "The sentence spoken by this speaker",
                        },
                    },
                    "required": ["speaker", "text"],
                },
            ),
        },
    )

    try:
        client = _get_llm_client(config)
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

        if not response.structured_data:
            return {"success": False, "error": "Empty response from LLM"}

        result = response.structured_data
        title = result.get("title", "Conversation")
        sentences = result.get("sentences", [])

        if not sentences:
            return {"success": False, "error": "No sentences generated"}

        return {
            "success": True,
            "title": title,
            "conversation": sentences,
        }

    except Exception as e:
        logger.error(f"Error querying LLM for conversation: {e}")
        return {"success": False, "error": str(e)}


def generate_conversation_with_session(
    session: Session,
    words: List[Dict[str, Any]],
    level: int,
    num_sentences: int = 8,
    config: Optional[DataSourceConfig] = None,
) -> Dict[str, Any]:
    """Generate a conversation using the provided session.

    This function uses the passed-in session for all database operations,
    ensuring it works correctly with both SQLite and PostgreSQL backends.

    Args:
        session: Database session from the worker
        words: List of word info dictionaries to use
        level: Difficulty level (for metadata)
        num_sentences: Target number of sentences in conversation
        config: Optional DataSourceConfig for LLM settings (uses default if not provided)

    Returns:
        Dictionary with generation results including conversation data
    """
    if config is None:
        config = build_default_config()

    if not words:
        return {"error": "No words provided for conversation"}

    # Extract word texts for the prompt
    word_texts = [w["lemma_text"] for w in words]
    word_list_str = ", ".join(word_texts)

    logger.info(f"Generating conversation with words: {word_list_str}")

    # Generate the conversation using LLM
    result = _query_conversation_llm(word_texts, num_sentences, config)

    if not result.get("success"):
        return {
            "error": result.get("error", "Failed to generate conversation"),
            "words": word_texts,
        }

    conversation_data = result["conversation"]
    title = result.get("title", "Untitled Conversation")

    # Create the conversation in the database using the passed-in session
    conversation = add_conversation(
        session,
        title=title,
        theme=f"level_{level}",
        keywords=word_texts,
        verified=False,
    )

    # Set minimum level
    conversation.minimum_level = level

    # Create sentences and link them to the conversation
    created_sentences = []
    for idx, sent_data in enumerate(conversation_data):
        speaker = sent_data.get("speaker", "A" if idx % 2 == 0 else "B")
        text = sent_data.get("text", "")

        # Create the sentence
        sentence = add_sentence(
            session,
            pattern_type="conversation",
            verified=False,
            notes=f"Generated by Sarka agent for conversation {conversation.id}",
        )

        # Set minimum level on sentence too
        sentence.minimum_level = level

        # Add English translation
        add_sentence_translation(
            session,
            sentence=sentence,
            language_code="en",
            translation_text=text,
        )

        # Link to conversation
        add_conversation_sentence(
            session,
            conversation=conversation,
            sentence=sentence,
            position=idx,
            speaker=speaker,
        )

        created_sentences.append(
            {
                "sentence_id": sentence.id,
                "position": idx,
                "speaker": speaker,
                "text": text,
            }
        )

    # Log the operation
    log_operation(
        session,
        operation_type="conversation_generated",
        entity_type="conversation",
        entity_id=conversation.id,
        details={
            "title": title,
            "level": level,
            "words": word_texts,
            "num_sentences": len(created_sentences),
            "agent": "sarka",
            "model": config.model,
        },
    )

    logger.info(f"Created conversation {conversation.id} with {len(created_sentences)} sentences")

    return {
        "success": True,
        "conversation_id": conversation.id,
        "title": title,
        "level": level,
        "words": word_texts,
        "sentences": created_sentences,
        "num_sentences": len(created_sentences),
    }


def handle_generate_conversation(session: Session, payload: Dict) -> str:
    """Handle conversation generation task (workqueue entry point).

    Uses the session passed from the Barsukas worker to ensure database
    operations go to the correct backend (SQLite or PostgreSQL).

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

    # Use build_default_config only for LLM settings, not for database
    config = build_default_config()

    # Generate the conversation using the passed-in session
    result = generate_conversation_with_session(
        session=session,
        words=words,
        level=level,
        num_sentences=num_sentences,
        config=config,
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    # Commit the changes using the worker's session
    session.commit()

    conversation_id = result.get("conversation_id")
    title = result.get("title", "Untitled")
    num_generated = result.get("num_sentences", 0)
    word_list = ", ".join(result.get("words", []))

    return f"Generated conversation {conversation_id}: '{title}' with {num_generated} sentences (words: {word_list})"
