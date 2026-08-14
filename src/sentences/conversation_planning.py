"""Plan and generate vocabulary-driven conversations.

This service generates simple conversations for the Trakaido language-learning app.
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
from words.lemma_selection import LemmaQueryBuilder
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.conversation import (
    add_conversation,
    add_conversation_sentence,
    calculate_minimum_level,
    get_conversation_by_id,
)
from storage.crud.sentence import add_sentence, find_sentence_by_text
from storage.crud.sentence_translation import add_sentence_translation
from storage.crud.operation_log import log_operation
from storage.models.schema import Conversation, ConversationSentence, Lemma, Sentence

logger = logging.getLogger(__name__)


# Target number of conversations per level
CONVERSATIONS_PER_LEVEL = 12

# Target number of times each word should appear across all conversations at a level
WORD_USAGE_TARGET = 2

# Target words per conversation
WORDS_PER_CONVERSATION = 5


class ConversationPlanner:
    """Plan and generate vocabulary-driven conversations for language learning."""

    def __init__(self, config: DataSourceConfig):
        """Initialize the conversation planner.

        Args:
            config: DataSourceConfig with model, debug, and backend settings
        """
        self.config = config
        self.debug = config.debug

        # Lazy initialization for LLM client
        self._llm_client: Optional[UnifiedLLMClient] = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
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
        self, level: int, session: Any = None
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
                    "difficulty_level": lemma.difficulty_level,
                }
                pos_type = lemma.pos_type or "unknown"
                pos_subtype = lemma.pos_subtype or "other"
                words_by_type[pos_type][pos_subtype].append(word_info)

            return dict(words_by_type)

        finally:
            if close_session:
                session.close()

    def get_words_up_to_level(
        self,
        max_level: int,
        min_level: int = 1,
        category: Optional[str] = None,
        session: Any = None,
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Get all curated words up to a maximum difficulty level.

        Args:
            max_level: Maximum difficulty level (inclusive)
            min_level: Minimum difficulty level (inclusive, default 1)
            category: Optional pos_subtype to filter by (e.g., 'food_drink')
            session: Optional database session (creates one if not provided)

        Returns:
            Dictionary organized by pos_type -> pos_subtype -> list of word info dicts
        """
        close_session = session is None
        if session is None:
            session = self.get_session()

        try:
            # Query lemmas up to this level
            builder = (
                LemmaQueryBuilder(session)
                .curated_only()
                .by_level_range(min_level, max_level)
                .order_by_id()
            )
            query = builder.build()
            lemmas = query.all()

            # Organize by pos_type and pos_subtype
            words_by_type: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
                lambda: defaultdict(list)
            )

            for lemma in lemmas:
                # Filter by category if specified
                if category and lemma.pos_subtype != category:
                    continue

                word_info = {
                    "lemma_id": lemma.id,
                    "lemma_text": lemma.lemma_text,
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                    "pos_subtype": lemma.pos_subtype,
                    "definition": lemma.definition_text,
                    "difficulty_level": lemma.difficulty_level,
                }
                pos_type = lemma.pos_type or "unknown"
                pos_subtype = lemma.pos_subtype or "other"
                words_by_type[pos_type][pos_subtype].append(word_info)

            return dict(words_by_type)

        finally:
            if close_session:
                session.close()

    def get_word_usage_counts(self, session: Any = None) -> Dict[str, int]:
        """Get count of conversations each word appears in.

        Parses the keywords JSON field from Conversation table to count
        how many times each word has been used.

        Args:
            session: Optional database session

        Returns:
            Dictionary mapping lemma_text -> conversation count
        """
        close_session = session is None
        if session is None:
            session = self.get_session()

        try:
            conversations = (
                session.query(Conversation).filter(Conversation.keywords.isnot(None)).all()
            )

            usage_counts: Dict[str, int] = defaultdict(int)
            for conv in conversations:
                try:
                    keywords = json.loads(conv.keywords) if conv.keywords else []
                    for word in keywords:
                        usage_counts[word] += 1
                except (json.JSONDecodeError, TypeError):
                    continue

            return dict(usage_counts)

        finally:
            if close_session:
                session.close()

    def filter_words_by_usage(
        self,
        words_by_type: Dict[str, Dict[str, List[Dict[str, Any]]]],
        max_usage: int,
        usage_counts: Dict[str, int],
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Filter out words that have been used too many times.

        Args:
            words_by_type: Words organized by pos_type -> pos_subtype
            max_usage: Maximum number of conversations a word can appear in
            usage_counts: Dictionary of word -> usage count

        Returns:
            Filtered words_by_type dictionary
        """
        filtered: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for pos_type, subtypes in words_by_type.items():
            for subtype, words in subtypes.items():
                for word in words:
                    current_usage = usage_counts.get(word["lemma_text"], 0)
                    if current_usage < max_usage:
                        filtered[pos_type][subtype].append(word)

        return dict(filtered)

    def get_level_summary(self, level: int, session: Any = None) -> Dict[str, Any]:
        """Get a summary of words available at a level.

        Args:
            level: Difficulty level to query
            session: Optional database session

        Returns:
            Dictionary with level summary statistics
        """
        words_by_type = self.get_words_at_level(level, session)

        summary: Dict[str, Any] = {
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

    def plan_conversations_by_category(
        self,
        words_by_type: Dict[str, Dict[str, List[Dict[str, Any]]]],
        num_conversations: int = CONVERSATIONS_PER_LEVEL,
    ) -> List[List[Dict[str, Any]]]:
        """Plan conversations where each groups words by category for coherence.

        The strategy:
        - Group nouns by their pos_subtype (category like 'food_drink', 'animal')
        - Each conversation gets nouns from the same/related categories
        - Verbs, adjectives, and other POS types are distributed across all conversations

        Args:
            words_by_type: Words organized by pos_type -> pos_subtype
            num_conversations: Number of conversations to generate

        Returns:
            List of word lists, one per planned conversation
        """
        # Separate nouns from other POS types
        noun_categories: Dict[str, List[Dict[str, Any]]] = {}
        universal_words: List[Dict[str, Any]] = []

        for pos_type, subtypes in words_by_type.items():
            for subtype, words in subtypes.items():
                if pos_type == "noun":
                    if subtype not in noun_categories:
                        noun_categories[subtype] = []
                    noun_categories[subtype].extend(words)
                else:
                    # Verbs, adjectives, adverbs, etc. are "universal"
                    universal_words.extend(words)

        if not noun_categories:
            # No nouns - fall back to random distribution
            logger.warning("No nouns found, using random distribution")
            all_words = universal_words
            random.shuffle(all_words)
            return self._distribute_words_randomly(all_words, num_conversations)

        # Sort categories by size (largest first) for better distribution
        sorted_categories = sorted(noun_categories.items(), key=lambda x: len(x[1]), reverse=True)

        # Assign categories to conversations round-robin style
        # Each category gets approximately equal representation
        conversations_plan: List[List[Dict[str, Any]]] = []
        category_idx = 0
        nouns_used: Dict[int, int] = defaultdict(int)  # lemma_id -> times used

        # Shuffle universal words for random distribution
        random.shuffle(universal_words)
        universal_idx = 0

        for conv_num in range(num_conversations):
            conv_words: List[Dict[str, Any]] = []
            used_lemma_ids: set = set()

            # Pick the category for this conversation (round-robin through categories)
            category_name, category_nouns = sorted_categories[category_idx % len(sorted_categories)]
            category_idx += 1

            # Try to get 2-3 nouns from this category
            target_nouns = min(3, WORDS_PER_CONVERSATION - 2)  # Leave room for verbs/adjectives
            available_nouns = [
                n for n in category_nouns if nouns_used[n["lemma_id"]] < WORD_USAGE_TARGET
            ]
            random.shuffle(available_nouns)

            for noun in available_nouns[:target_nouns]:
                if noun["lemma_id"] not in used_lemma_ids:
                    conv_words.append(noun)
                    used_lemma_ids.add(noun["lemma_id"])
                    nouns_used[noun["lemma_id"]] += 1

            # Fill remaining slots with universal words (verbs, adjectives)
            # If no universal words available, fill with more nouns from same category
            if universal_words:
                attempts = 0
                while len(conv_words) < WORDS_PER_CONVERSATION and attempts < 50:
                    if universal_idx >= len(universal_words):
                        random.shuffle(universal_words)
                        universal_idx = 0

                    candidate = universal_words[universal_idx]
                    universal_idx += 1
                    attempts += 1

                    if candidate["lemma_id"] not in used_lemma_ids:
                        conv_words.append(candidate)
                        used_lemma_ids.add(candidate["lemma_id"])

            # If still need more words (no universal words or not enough), add more nouns
            if len(conv_words) < WORDS_PER_CONVERSATION:
                extra_nouns = [n for n in available_nouns if n["lemma_id"] not in used_lemma_ids]
                for noun in extra_nouns:
                    if len(conv_words) >= WORDS_PER_CONVERSATION:
                        break
                    conv_words.append(noun)
                    used_lemma_ids.add(noun["lemma_id"])
                    nouns_used[noun["lemma_id"]] += 1

            if conv_words:
                conversations_plan.append(conv_words)
                logger.debug(
                    f"Conversation {conv_num + 1}: category={category_name}, "
                    f"words={[w['lemma_text'] for w in conv_words]}"
                )

        return conversations_plan

    def _distribute_words_randomly(
        self, all_words: List[Dict[str, Any]], num_conversations: int
    ) -> List[List[Dict[str, Any]]]:
        """Distribute words randomly across conversations (fallback method).

        Args:
            all_words: Flat list of all words
            num_conversations: Number of conversations to create

        Returns:
            List of word lists
        """
        if not all_words:
            return []

        word_pool = all_words * WORD_USAGE_TARGET
        random.shuffle(word_pool)

        conversations_plan = []
        word_idx = 0

        for _ in range(num_conversations):
            conv_words: List[Dict[str, Any]] = []
            attempts = 0
            while len(conv_words) < WORDS_PER_CONVERSATION and attempts < 100:
                if word_idx >= len(word_pool):
                    random.shuffle(word_pool)
                    word_idx = 0

                candidate = word_pool[word_idx]
                word_idx += 1
                attempts += 1

                if candidate["lemma_id"] not in [w["lemma_id"] for w in conv_words]:
                    conv_words.append(candidate)

            if conv_words:
                conversations_plan.append(conv_words)

        return conversations_plan

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
                conv_words: List[Dict[str, Any]] = []
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

    def plan_conversations_with_options(
        self,
        max_level: Optional[int] = None,
        level: Optional[int] = None,
        category: Optional[str] = None,
        by_category: bool = False,
        max_word_usage: Optional[int] = None,
        num_conversations: int = CONVERSATIONS_PER_LEVEL,
    ) -> Tuple[List[List[Dict[str, Any]]], Dict[str, Any]]:
        """Plan conversations with advanced filtering and category options.

        Args:
            max_level: Maximum difficulty level (inclusive). If set, selects words
                      from level 1 up to max_level.
            level: Exact difficulty level. Ignored if max_level is set.
            category: Filter to a specific pos_subtype (e.g., 'food_drink')
            by_category: If True, group words by noun category for coherence
            max_word_usage: Skip words already used in this many conversations
            num_conversations: Number of conversations to generate

        Returns:
            Tuple of (conversation_plans, stats_dict)
        """
        session = self.get_session()
        try:
            # Get words based on level selection
            if max_level is not None:
                words_by_type = self.get_words_up_to_level(
                    max_level=max_level, category=category, session=session
                )
                level_desc = f"1-{max_level}"
            elif level is not None:
                words_by_type = self.get_words_at_level(level, session)
                if category:
                    # Filter by category
                    filtered: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
                        lambda: defaultdict(list)
                    )
                    for pos_type, subtypes in words_by_type.items():
                        for subtype, words in subtypes.items():
                            if subtype == category:
                                filtered[pos_type][subtype] = words
                    words_by_type = dict(filtered)
                level_desc = str(level)
            else:
                raise ValueError("Either max_level or level must be specified")

            # Count total words before filtering
            total_before = sum(
                len(words) for subtypes in words_by_type.values() for words in subtypes.values()
            )

            # Filter by usage if requested
            filtered_count = 0
            if max_word_usage is not None:
                usage_counts = self.get_word_usage_counts(session)
                words_by_type = self.filter_words_by_usage(
                    words_by_type, max_word_usage, usage_counts
                )
                total_after = sum(
                    len(words) for subtypes in words_by_type.values() for words in subtypes.values()
                )
                filtered_count = total_before - total_after
                logger.info(f"Filtered out {filtered_count} words with {max_word_usage}+ usages")

            total_words = sum(
                len(words) for subtypes in words_by_type.values() for words in subtypes.values()
            )

            if total_words == 0:
                logger.warning(f"No words available after filtering")
                return [], {
                    "level_desc": level_desc,
                    "total_words": 0,
                    "filtered_out": filtered_count,
                }

            # Plan conversations
            if by_category:
                conversations_plan = self.plan_conversations_by_category(
                    words_by_type, num_conversations
                )
            else:
                # Flatten and distribute randomly
                all_words = []
                for subtypes in words_by_type.values():
                    for words in subtypes.values():
                        all_words.extend(words)
                conversations_plan = self._distribute_words_randomly(all_words, num_conversations)

            stats = {
                "level_desc": level_desc,
                "total_words": total_words,
                "filtered_out": filtered_count,
                "by_category": by_category,
                "category": category,
                "planned_conversations": len(conversations_plan),
            }

            logger.info(
                f"Planned {len(conversations_plan)} conversations "
                f"with {total_words} words (levels {level_desc})"
            )

            return conversations_plan, stats

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

    def generate_with_options(
        self,
        max_level: Optional[int] = None,
        level: Optional[int] = None,
        category: Optional[str] = None,
        by_category: bool = False,
        max_word_usage: Optional[int] = None,
        num_conversations: int = CONVERSATIONS_PER_LEVEL,
        num_sentences: int = 8,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate conversations with advanced options.

        Args:
            max_level: Maximum difficulty level (inclusive)
            level: Exact difficulty level (ignored if max_level set)
            category: Filter to specific pos_subtype
            by_category: Group words by noun category for coherence
            max_word_usage: Skip words used in this many conversations
            num_conversations: Number of conversations to generate
            num_sentences: Target sentences per conversation
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results and statistics
        """
        # Determine effective level for conversation minimum_level
        effective_level = max_level if max_level is not None else level
        if effective_level is None:
            return {"error": "Either max_level or level must be specified"}

        logger.info(
            f"Generating {num_conversations} conversations "
            f"(max_level={max_level}, level={level}, category={category}, "
            f"by_category={by_category}, max_word_usage={max_word_usage})"
        )

        # Plan conversations with options
        conversation_plans, plan_stats = self.plan_conversations_with_options(
            max_level=max_level,
            level=level,
            category=category,
            by_category=by_category,
            max_word_usage=max_word_usage,
            num_conversations=num_conversations,
        )

        if not conversation_plans:
            return {
                "error": "No conversations could be planned (no words available)",
                "plan_stats": plan_stats,
            }

        # Generate each conversation
        results = []
        successful = 0
        failed = 0

        for i, words in enumerate(conversation_plans):
            logger.info(
                f"Generating conversation {i + 1}/{len(conversation_plans)} "
                f"with {len(words)} words: {[w['lemma_text'] for w in words]}"
            )

            result = self.generate_conversation(
                words=words,
                level=effective_level,
                num_sentences=num_sentences,
                dry_run=dry_run,
            )

            if result.get("success") or result.get("dry_run"):
                successful += 1
            else:
                failed += 1

            results.append(result)

        return {
            "plan_stats": plan_stats,
            "total": len(conversation_plans),
            "successful": successful,
            "failed": failed,
            "results": results,
            "dry_run": dry_run,
        }

    def plan_word_definition_pairs(
        self,
        level: int,
        max_level: Optional[int] = None,
        category: Optional[str] = None,
        max_word_usage: Optional[int] = None,
        num_pairs: int = CONVERSATIONS_PER_LEVEL,
    ) -> Tuple[List[List[Dict[str, Any]]], Dict[str, Any]]:
        """Plan word pairs for definition/comparison generation.

        Groups words by (pos_type, pos_subtype) and creates pairs within
        each group. Words in the same subtype are natural comparison targets
        (e.g., two animals, two foods, two furniture items).

        Args:
            level: Difficulty level to select words from
            max_level: If set, select words from level 1 up to max_level
            category: Optional pos_subtype filter
            max_word_usage: Skip words already used in this many definition conversations
            num_pairs: Maximum number of pairs to generate

        Returns:
            Tuple of (list of word pair lists, stats dict)
        """
        session = self.get_session()
        try:
            # Get words based on level selection
            if max_level is not None:
                words_by_type = self.get_words_up_to_level(
                    max_level=max_level, min_level=level, category=category, session=session
                )
                level_desc = f"{level}-{max_level}"
            else:
                words_by_type = self.get_words_at_level(level, session)
                if category:
                    filtered: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
                        lambda: defaultdict(list)
                    )
                    for pos_type, subtypes in words_by_type.items():
                        for subtype, words in subtypes.items():
                            if subtype == category:
                                filtered[pos_type][subtype] = words
                    words_by_type = dict(filtered)
                level_desc = str(level)

            # Count total words before filtering
            total_before = sum(
                len(words) for subtypes in words_by_type.values() for words in subtypes.values()
            )

            # Filter by usage if requested
            filtered_count = 0
            if max_word_usage is not None:
                usage_counts = self.get_word_usage_counts(session)
                words_by_type = self.filter_words_by_usage(
                    words_by_type, max_word_usage, usage_counts
                )
                total_after = sum(
                    len(words) for subtypes in words_by_type.values() for words in subtypes.values()
                )
                filtered_count = total_before - total_after

            total_words = sum(
                len(words) for subtypes in words_by_type.values() for words in subtypes.values()
            )

            if total_words == 0:
                return [], {
                    "level_desc": level_desc,
                    "total_words": 0,
                    "filtered_out": filtered_count,
                }

            # Group words by (pos_type, pos_subtype) and create pairs
            pairs: List[List[Dict[str, Any]]] = []
            for pos_type, subtypes in words_by_type.items():
                for subtype, words in subtypes.items():
                    # Shuffle within subtype for variety
                    shuffled = list(words)
                    random.shuffle(shuffled)

                    # Create pairs from consecutive words
                    for i in range(0, len(shuffled) - 1, 2):
                        pairs.append([shuffled[i], shuffled[i + 1]])
                        if len(pairs) >= num_pairs:
                            break
                    if len(pairs) >= num_pairs:
                        break
                if len(pairs) >= num_pairs:
                    break

            stats = {
                "level_desc": level_desc,
                "total_words": total_words,
                "filtered_out": filtered_count,
                "category": category,
                "planned_pairs": len(pairs),
            }

            logger.info(
                f"Planned {len(pairs)} word definition pairs "
                f"from {total_words} words (levels {level_desc})"
            )

            return pairs, stats

        finally:
            session.close()

    def _query_word_definition(self, word_list: List[str], num_sentences: int) -> Dict[str, Any]:
        """Query the LLM to generate a word definition/comparison narrative.

        Args:
            word_list: List of words to describe and compare (typically 2)
            num_sentences: Target number of sentences

        Returns:
            Dictionary with definition data or error
        """
        try:
            context = util.prompt_loader.get_context("conversations", "definitions")
            prompt_template = util.prompt_loader.get_prompt("conversations", "definitions")
        except Exception as e:
            logger.error(f"Failed to load word definition prompts: {e}")
            return {"success": False, "error": f"Failed to load prompts: {e}"}

        word_list_str = ", ".join(word_list)

        prompt_text = prompt_template.format(
            word_list=word_list_str,
            num_sentences=num_sentences,
        )

        schema = Schema(
            name="WordDefinition",
            description="Generate a short narrative comparing and describing words",
            properties={
                "title": SchemaProperty(
                    "string", "A short title for the comparison (e.g., 'Table vs. Desk')"
                ),
                "sentences": SchemaProperty(
                    "array",
                    "List of descriptive sentences",
                    items={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "A single descriptive sentence",
                            },
                        },
                        "required": ["text"],
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
            title = result.get("title", "Word Definition")
            sentences = result.get("sentences", [])

            if not sentences:
                return {"success": False, "error": "No sentences generated"}

            return {
                "success": True,
                "title": title,
                "sentences": sentences,
            }

        except Exception as e:
            logger.error(f"Error querying LLM for word definition: {e}")
            return {"success": False, "error": str(e)}

    def generate_word_definition(
        self,
        words: List[Dict[str, Any]],
        level: int,
        num_sentences: int = 10,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate a word definition/comparison narrative.

        Creates a short narrative describing and comparing a pair of words,
        stored as a conversation with speaker="narrator".

        Args:
            words: List of word info dictionaries (typically a pair)
            level: Difficulty level (for metadata)
            num_sentences: Target number of sentences (default 10)
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results
        """
        session = self.get_session()

        try:
            if not words:
                return {"error": "No words provided for word definition"}

            word_texts = [w["lemma_text"] for w in words]
            word_list_str = ", ".join(word_texts)

            logger.info(f"Generating word definition for: {word_list_str}")

            result = self._query_word_definition(word_texts, num_sentences)

            if not result.get("success"):
                return {
                    "error": result.get("error", "Failed to generate word definition"),
                    "words": word_texts,
                }

            definition_sentences = result["sentences"]
            title = result.get("title", f"{' vs. '.join(word_texts)}")

            if dry_run:
                return {
                    "dry_run": True,
                    "words": word_texts,
                    "level": level,
                    "title": title,
                    "sentences": definition_sentences,
                    "num_sentences": len(definition_sentences),
                }

            # Create conversation record with theme="word_definition"
            conversation = add_conversation(
                session,
                title=title,
                theme="word_definition",
                keywords=word_texts,
                verified=False,
            )

            conversation.minimum_level = level

            created_sentences = []
            reused_count = 0
            for idx, sent_data in enumerate(definition_sentences):
                text = sent_data.get("text", "")

                # Check for duplicate sentences
                existing_sentence = find_sentence_by_text(session, text, language_code="en")

                if existing_sentence:
                    sentence = existing_sentence
                    reused_count += 1
                    logger.debug(f"Reusing existing sentence #{sentence.id}: {text[:50]}...")
                else:
                    sentence = add_sentence(
                        session,
                        pattern_type="definition",
                        verified=False,
                        notes=f"Generated by Sarka agent for word definition {conversation.id}",
                    )

                    sentence.minimum_level = level

                    add_sentence_translation(
                        session,
                        sentence=sentence,
                        language_code="en",
                        translation_text=text,
                    )

                # Link to conversation with speaker="narrator"
                add_conversation_sentence(
                    session,
                    conversation=conversation,
                    sentence=sentence,
                    position=idx,
                    speaker="narrator",
                )

                created_sentences.append(
                    {
                        "sentence_id": sentence.id,
                        "position": idx,
                        "speaker": "narrator",
                        "text": text,
                        "reused": existing_sentence is not None,
                    }
                )

            if reused_count > 0:
                logger.info(f"Reused {reused_count} existing sentence(s) in word definition")

            log_operation(
                session,
                operation_type="word_definition_generated",
                entity_type="conversation",
                entity_id=conversation.id,
                details={
                    "title": title,
                    "level": level,
                    "words": word_texts,
                    "num_sentences": len(created_sentences),
                    "agent": "sarka",
                    "model": self.config.model,
                    "type": "word_definition",
                },
            )

            session.commit()

            logger.info(
                f"Created word definition {conversation.id} with "
                f"{len(created_sentences)} sentences"
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
            logger.exception(f"Error generating word definition: {e}")
            return {"error": str(e), "words": [w["lemma_text"] for w in words] if words else []}
        finally:
            session.close()

    def generate_definitions_for_level(
        self,
        level: int,
        max_level: Optional[int] = None,
        category: Optional[str] = None,
        max_word_usage: Optional[int] = None,
        num_pairs: int = CONVERSATIONS_PER_LEVEL,
        num_sentences: int = 10,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate word definition narratives for a level.

        Plans word pairs by grouping words with the same pos_subtype,
        then generates comparison narratives for each pair.

        Args:
            level: Difficulty level
            max_level: Maximum difficulty level (inclusive)
            category: Optional pos_subtype filter
            max_word_usage: Skip words used in this many conversations
            num_pairs: Maximum number of pairs to generate
            num_sentences: Target sentences per definition (default 10)
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results and statistics
        """
        effective_level = max_level if max_level is not None else level

        logger.info(
            f"Generating word definitions "
            f"(level={level}, max_level={max_level}, category={category})"
        )

        pairs, plan_stats = self.plan_word_definition_pairs(
            level=level,
            max_level=max_level,
            category=category,
            max_word_usage=max_word_usage,
            num_pairs=num_pairs,
        )

        if not pairs:
            return {
                "error": "No word pairs could be planned (need 2+ words in same category)",
                "plan_stats": plan_stats,
            }

        results = []
        successful = 0
        failed = 0

        for i, word_pair in enumerate(pairs):
            pair_texts = [w["lemma_text"] for w in word_pair]
            logger.info(f"Generating definition {i + 1}/{len(pairs)}: {', '.join(pair_texts)}")

            result = self.generate_word_definition(
                words=word_pair,
                level=effective_level,
                num_sentences=num_sentences,
                dry_run=dry_run,
            )

            if result.get("success") or result.get("dry_run"):
                successful += 1
            else:
                failed += 1

            results.append(result)

        return {
            "plan_stats": plan_stats,
            "total": len(pairs),
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


# Compatibility name retained for callers of the former agent package.
SarkaAgent = ConversationPlanner
