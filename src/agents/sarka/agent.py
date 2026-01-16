"""
Sarka - Conversation Generator Agent

This agent generates simple conversations for the Trakaido language-learning app.
It creates dialogs using LLM prompts with words from the database at specific
difficulty levels to generate natural-sounding exchanges between two speakers.

The agent plans conversations so that each word at a given level is used
approximately twice across 12 conversations per level.

"Sarka" means "magpie" in Lithuanian - known for being talkative and social.

Supported languages:
- English (en) - source language for generation
- All target languages via sentence translation pipeline
"""

import json
import logging
import math
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import util.prompt_loader
from agents.common.lemma_selection import LemmaQueryBuilder
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
from wordfreq.storage.crud.sentence import add_sentence, find_sentence_by_text
from wordfreq.storage.crud.sentence_translation import add_sentence_translation
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.models.schema import Conversation, Lemma, Sentence

logger = logging.getLogger(__name__)


# Target number of conversations per level
CONVERSATIONS_PER_LEVEL = 12

# Target number of times each word should appear across all conversations at a level
WORD_USAGE_TARGET = 2

# Target words per conversation
WORDS_PER_CONVERSATION = 5


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

    def get_words_at_level(
        self, level: int, session=None
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Get all curated words at a specific difficulty level.

        Args:
            level: Difficulty level to query
            session: Optional database session (creates one if not provided)

        Returns:
            Dictionary organized by pos_type -> pos_subtype -> list of word info dicts
        """
        close_session = session is None
        if session is None:
            session = self.get_session()

        try:
            # Query lemmas at this level
            query = (
                LemmaQueryBuilder(session)
                .curated_only()
                .by_difficulty_level(level)
                .order_by_id()
                .build()
            )
            lemmas = query.all()

            # Organize by pos_type and pos_subtype
            words_by_type: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
                lambda: defaultdict(list)
            )

            for lemma in lemmas:
                word_info = {
                    "lemma_id": lemma.id,
                    "lemma_text": lemma.lemma_text,
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                    "pos_subtype": lemma.pos_subtype,
                    "definition": lemma.definition_text,
                }
                pos_type = lemma.pos_type or "unknown"
                pos_subtype = lemma.pos_subtype or "other"
                words_by_type[pos_type][pos_subtype].append(word_info)

            return dict(words_by_type)

        finally:
            if close_session:
                session.close()

    def get_level_summary(self, level: int, session=None) -> Dict[str, Any]:
        """Get a summary of words available at a level.

        Args:
            level: Difficulty level to query
            session: Optional database session

        Returns:
            Dictionary with level summary statistics
        """
        words_by_type = self.get_words_at_level(level, session)

        summary = {
            "level": level,
            "total_words": 0,
            "by_pos_type": {},
        }

        for pos_type, subtypes in words_by_type.items():
            pos_total = sum(len(words) for words in subtypes.values())
            summary["total_words"] += pos_total
            summary["by_pos_type"][pos_type] = {
                "total": pos_total,
                "subtypes": {subtype: len(words) for subtype, words in subtypes.items()},
            }

        return summary

    def plan_conversations_for_level(
        self, level: int, num_conversations: int = CONVERSATIONS_PER_LEVEL
    ) -> List[List[Dict[str, Any]]]:
        """Plan word assignments for conversations at a given level.

        Each word should appear approximately twice across all conversations.

        Args:
            level: Difficulty level to plan for
            num_conversations: Number of conversations to generate (default 12)

        Returns:
            List of word lists, one per planned conversation
        """
        session = self.get_session()
        try:
            words_by_type = self.get_words_at_level(level, session)

            # Flatten all words into a single list
            all_words = []
            for pos_type, subtypes in words_by_type.items():
                for subtype, words in subtypes.items():
                    all_words.extend(words)

            if not all_words:
                logger.warning(f"No words found at level {level}")
                return []

            # Calculate how many times each word should appear
            total_word_slots = num_conversations * WORDS_PER_CONVERSATION
            total_words = len(all_words)

            # Each word should appear approximately:
            # total_word_slots / total_words times
            # But we target WORD_USAGE_TARGET (2) times per word
            target_per_word = WORD_USAGE_TARGET

            # Create a pool of words where each word appears target_per_word times
            word_pool = all_words * target_per_word
            random.shuffle(word_pool)

            # Distribute words across conversations
            conversations_plan = []
            word_idx = 0

            for conv_num in range(num_conversations):
                conv_words = []
                words_needed = WORDS_PER_CONVERSATION

                # Try to get diverse words for this conversation
                attempts = 0
                while len(conv_words) < words_needed and attempts < 100:
                    if word_idx >= len(word_pool):
                        # Reshuffle and start over if we run out
                        random.shuffle(word_pool)
                        word_idx = 0

                    candidate = word_pool[word_idx]
                    word_idx += 1

                    # Avoid duplicates in the same conversation
                    if candidate["lemma_id"] not in [w["lemma_id"] for w in conv_words]:
                        conv_words.append(candidate)
                    attempts += 1

                # If we still don't have enough, just add what we have
                if conv_words:
                    conversations_plan.append(conv_words)

            logger.info(
                f"Planned {len(conversations_plan)} conversations for level {level} "
                f"with {total_words} unique words"
            )

            return conversations_plan

        finally:
            session.close()

    def generate_conversation(
        self,
        words: List[Dict[str, Any]],
        level: int,
        num_sentences: int = 8,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate a conversation using the specified words.

        Args:
            words: List of word info dictionaries to use
            level: Difficulty level (for metadata)
            num_sentences: Target number of sentences in conversation (default 8)
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results including conversation data
        """
        session = self.get_session()

        try:
            if not words:
                return {"error": "No words provided for conversation"}

            # Extract word texts for the prompt
            word_texts = [w["lemma_text"] for w in words]
            word_list_str = ", ".join(word_texts)

            logger.info(f"Generating conversation with words: {word_list_str}")

            # Generate the conversation using LLM
            result = self._query_conversation(word_texts, num_sentences)

            if not result.get("success"):
                return {
                    "error": result.get("error", "Failed to generate conversation"),
                    "words": word_texts,
                }

            conversation_data = result["conversation"]
            title = result.get("title", "Untitled Conversation")

            if dry_run:
                return {
                    "dry_run": True,
                    "words": word_texts,
                    "level": level,
                    "title": title,
                    "sentences": conversation_data,
                    "num_sentences": len(conversation_data),
                }

            # Create the conversation in the database
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
            reused_count = 0
            for idx, sent_data in enumerate(conversation_data):
                speaker = sent_data.get("speaker", "A" if idx % 2 == 0 else "B")
                text = sent_data.get("text", "")

                # Check if an identical sentence already exists (dedupe)
                existing_sentence = find_sentence_by_text(session, text, language_code="en")

                if existing_sentence:
                    # Reuse existing sentence
                    sentence = existing_sentence
                    reused_count += 1
                    logger.debug(f"Reusing existing sentence #{sentence.id}: {text[:50]}...")
                else:
                    # Create new sentence
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
                        "reused": existing_sentence is not None,
                    }
                )

            if reused_count > 0:
                logger.info(f"Reused {reused_count} existing sentence(s) in conversation")

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
                "level": level,
                "words": word_texts,
                "sentences": created_sentences,
                "num_sentences": len(created_sentences),
            }

        except Exception as e:
            session.rollback()
            logger.exception(f"Error generating conversation: {e}")
            return {"error": str(e), "words": [w["lemma_text"] for w in words] if words else []}
        finally:
            session.close()

    def _query_conversation(self, word_list: List[str], num_sentences: int) -> Dict[str, Any]:
        """Query the LLM to generate a conversation.

        Args:
            word_list: List of words to incorporate
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

    def generate_for_level(
        self,
        level: int,
        num_conversations: int = CONVERSATIONS_PER_LEVEL,
        num_sentences: int = 8,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate all conversations for a specific difficulty level.

        Plans word assignments so each word is used approximately twice,
        then generates the specified number of conversations.

        Args:
            level: Difficulty level to generate for
            num_conversations: Number of conversations to generate (default 12)
            num_sentences: Target sentences per conversation (default 8)
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results
        """
        logger.info(f"Generating {num_conversations} conversations for level {level}")

        # Get level summary first
        summary = self.get_level_summary(level)
        logger.info(f"Level {level} has {summary['total_words']} words")

        if summary["total_words"] == 0:
            return {
                "error": f"No words found at level {level}",
                "level": level,
                "level_summary": summary,
            }

        # Plan word assignments
        conversation_plans = self.plan_conversations_for_level(level, num_conversations)

        if not conversation_plans:
            return {
                "error": "Failed to plan conversations",
                "level": level,
                "level_summary": summary,
            }

        # Generate each conversation
        results = []
        successful = 0
        failed = 0

        for i, words in enumerate(conversation_plans):
            logger.info(
                f"Generating conversation {i + 1}/{len(conversation_plans)} "
                f"with {len(words)} words"
            )

            result = self.generate_conversation(
                words=words,
                level=level,
                num_sentences=num_sentences,
                dry_run=dry_run,
            )

            if result.get("success") or result.get("dry_run"):
                successful += 1
            else:
                failed += 1

            results.append(result)

        return {
            "level": level,
            "level_summary": summary,
            "total": len(conversation_plans),
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
