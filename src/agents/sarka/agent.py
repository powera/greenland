"""
Sarka - Conversation Generator Agent

This agent generates simple conversations for the Trakaido language-learning app.
It creates dialogs using LLM prompts with curated keywords (colors, body parts,
emotions, occupations) to generate natural-sounding exchanges between two speakers.

"Sarka" means "magpie" in Lithuanian - known for being talkative and social.

Supported languages:
- English (en) - source language for generation
- All target languages via sentence translation pipeline
"""

import json
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.crud.conversation import (
    add_conversation,
    add_conversation_sentence,
    calculate_minimum_level,
    get_conversation_by_id,
)
from wordfreq.storage.crud.sentence import add_sentence
from wordfreq.storage.crud.sentence_translation import add_sentence_translation
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.models.schema import Conversation, Sentence

logger = logging.getLogger(__name__)


# Keyword categories for generating conversation topics
KEYWORD_CATEGORIES = {
    "colors": [
        "red",
        "blue",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "brown",
        "black",
        "white",
        "gray",
        "gold",
    ],
    "body_parts": [
        "head",
        "hand",
        "arm",
        "leg",
        "foot",
        "eye",
        "ear",
        "nose",
        "mouth",
        "hair",
        "back",
        "shoulder",
        "knee",
        "finger",
        "heart",
    ],
    "emotions": [
        "happy",
        "sad",
        "angry",
        "scared",
        "surprised",
        "tired",
        "excited",
        "nervous",
        "calm",
        "proud",
        "confused",
        "bored",
    ],
    "occupations": [
        "doctor",
        "teacher",
        "cook",
        "driver",
        "farmer",
        "artist",
        "musician",
        "nurse",
        "builder",
        "student",
        "shop assistant",
        "waiter",
    ],
}

# Common themes that conversations can fall into
CONVERSATION_THEMES = [
    "greeting",
    "shopping",
    "restaurant",
    "directions",
    "medical",
    "school",
    "work",
    "family",
    "hobbies",
    "travel",
    "weather",
    "daily_routine",
]


class SarkaAgent:
    """Agent for generating conversations for language learning."""

    def __init__(self, config: DataSourceConfig):
        """Initialize the Sarka agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings
        """
        self.config = config
        self.debug = config.debug

        # Lazy initialization for LLM client
        self._llm_client: Optional[UnifiedLLMClient] = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_llm_client(self) -> UnifiedLLMClient:
        """Get or create the LLM client (lazy initialization)."""
        if self._llm_client is None:
            self._llm_client = UnifiedLLMClient.from_config(self.config)
            if self.config.model:
                self._llm_client.warm_model(self.config.model)
        return self._llm_client

    def select_keywords(self, num_colors: int = 2, seed: Optional[int] = None) -> Dict[str, Any]:
        """Select random keywords for conversation generation.

        Args:
            num_colors: Number of colors to select (default 2)
            seed: Random seed for reproducibility (optional)

        Returns:
            Dictionary with selected keywords by category
        """
        if seed is not None:
            random.seed(seed)

        keywords = {
            "colors": random.sample(KEYWORD_CATEGORIES["colors"], min(num_colors, 2)),
            "body_part": random.choice(KEYWORD_CATEGORIES["body_parts"]),
            "emotion": random.choice(KEYWORD_CATEGORIES["emotions"]),
            "occupation": random.choice(KEYWORD_CATEGORIES["occupations"]),
        }

        # Also select a theme
        keywords["theme"] = random.choice(CONVERSATION_THEMES)

        return keywords

    def generate_conversation(
        self,
        keywords: Optional[Dict[str, Any]] = None,
        num_sentences: int = 6,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate a conversation using the specified keywords.

        Args:
            keywords: Dictionary of keywords to use, or None to auto-select
            num_sentences: Target number of sentences in conversation (default 6)
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results including conversation data
        """
        session = self.get_session()

        try:
            # Select keywords if not provided
            if keywords is None:
                keywords = self.select_keywords()

            logger.info(f"Generating conversation with keywords: {keywords}")

            # Generate the conversation using LLM
            result = self._query_conversation(keywords, num_sentences)

            if not result.get("success"):
                return {
                    "error": result.get("error", "Failed to generate conversation"),
                    "keywords": keywords,
                }

            conversation_data = result["conversation"]
            title = result.get("title", "Untitled Conversation")
            theme = keywords.get("theme", "general")

            if dry_run:
                return {
                    "dry_run": True,
                    "keywords": keywords,
                    "title": title,
                    "theme": theme,
                    "sentences": conversation_data,
                    "num_sentences": len(conversation_data),
                }

            # Create the conversation in the database
            all_keywords = []
            for key, val in keywords.items():
                if isinstance(val, list):
                    all_keywords.extend(val)
                else:
                    all_keywords.append(val)

            conversation = add_conversation(
                session,
                title=title,
                theme=theme,
                keywords=all_keywords,
                verified=False,
            )

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
                    "theme": theme,
                    "keywords": all_keywords,
                    "num_sentences": len(created_sentences),
                    "agent": "sarka",
                    "model": self.config.model,
                },
            )

            session.commit()

            logger.info(
                f"Created conversation {conversation.id} with {len(created_sentences)} sentences"
            )

            return {
                "success": True,
                "conversation_id": conversation.id,
                "title": title,
                "theme": theme,
                "keywords": all_keywords,
                "sentences": created_sentences,
                "num_sentences": len(created_sentences),
            }

        except Exception as e:
            session.rollback()
            logger.exception(f"Error generating conversation: {e}")
            return {"error": str(e), "keywords": keywords}
        finally:
            session.close()

    def _query_conversation(self, keywords: Dict[str, Any], num_sentences: int) -> Dict[str, Any]:
        """Query the LLM to generate a conversation.

        Args:
            keywords: Dictionary of keywords to incorporate
            num_sentences: Target number of sentences

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

        # Format keywords for prompt
        colors_str = ", ".join(keywords.get("colors", []))
        body_part = keywords.get("body_part", "hand")
        emotion = keywords.get("emotion", "happy")
        occupation = keywords.get("occupation", "teacher")
        theme = keywords.get("theme", "general")

        prompt_text = prompt_template.format(
            colors=colors_str,
            body_part=body_part,
            emotion=emotion,
            occupation=occupation,
            theme=theme,
            num_sentences=num_sentences,
        )

        # Define JSON schema for response
        schema = Schema(
            name="ConversationGeneration",
            description="Generate a simple conversation for language learning",
            properties={
                "title": SchemaProperty(
                    "string", "A short title describing the conversation scenario"
                ),
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
            client = self.get_llm_client()
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

    def generate_batch(
        self,
        count: int = 10,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate multiple conversations.

        Args:
            count: Number of conversations to generate
            dry_run: If True, don't save to database

        Returns:
            Dictionary with batch generation results
        """
        results = []
        successful = 0
        failed = 0

        for i in range(count):
            logger.info(f"Generating conversation {i + 1}/{count}")

            # Use different seeds for variety
            keywords = self.select_keywords(seed=None)  # Random each time
            result = self.generate_conversation(keywords=keywords, dry_run=dry_run)

            if result.get("success") or result.get("dry_run"):
                successful += 1
                results.append(result)
            else:
                failed += 1
                results.append(result)

        return {
            "total": count,
            "successful": successful,
            "failed": failed,
            "results": results,
            "dry_run": dry_run,
        }

    def get_conversation_details(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a conversation.

        Args:
            conversation_id: ID of the conversation to retrieve

        Returns:
            Dictionary with conversation details or None if not found
        """
        session = self.get_session()
        try:
            conversation = get_conversation_by_id(
                session, conversation_id, include_sentences=True, include_translations=True
            )

            if not conversation:
                return None

            sentences = []
            for cs in sorted(conversation.conversation_sentences, key=lambda x: x.position):
                translations = {}
                for trans in cs.sentence.translations:
                    translations[trans.language_code] = trans.translation_text

                sentences.append(
                    {
                        "position": cs.position,
                        "speaker": cs.speaker,
                        "sentence_id": cs.sentence_id,
                        "translations": translations,
                    }
                )

            return {
                "id": conversation.id,
                "title": conversation.title,
                "theme": conversation.theme,
                "keywords": json.loads(conversation.keywords) if conversation.keywords else [],
                "minimum_level": conversation.minimum_level,
                "verified": conversation.verified,
                "sentences": sentences,
            }
        finally:
            session.close()
