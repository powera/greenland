"""Guided sentence generation with vocabulary context.

Generates sentences using an LLM with knowledge of the available vocabulary,
encouraging use of words from the wordlist while prioritizing natural sentences.
"""

import logging
from typing import Any, Dict, List, Optional, cast

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.database import (
    Lemma,
    add_sentence,
    add_sentence_translation,
)
from wordfreq.storage.models.schema import SentencePatternWord
from wordfreq.tools.vocabulary_budget import build_prompt_vocabulary_section

logger = logging.getLogger(__name__)


class GuidedSentenceGenerator:
    """Generate sentences using vocabulary-aware prompts."""

    def __init__(self, config: DataSourceConfig, dry_run: bool = False):
        self.config = config
        self.debug = config.debug
        self.dry_run = dry_run
        self.llm_client = UnifiedLLMClient.from_config(config)

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        return create_backend_session(self.config)

    def generate_sentences_for_lemma(
        self,
        lemma: Lemma,
        num_sentences: int = 5,
        max_vocabulary_level: int = 8,
    ) -> Dict[str, Any]:
        """Generate multiple varied sentences for a lemma.

        Args:
            lemma: The lemma to generate sentences for
            num_sentences: Number of sentences to generate (default 5)
            max_vocabulary_level: Max level for vocabulary context (default 8)

        Returns:
            Dict with 'success', 'sentences', and optionally 'error'
        """
        # Support nouns, verbs, and adjectives
        if lemma.pos_type not in ("noun", "verb", "adjective"):
            logger.info(
                "Skipping lemma %s: POS type '%s' not supported",
                lemma.guid,
                lemma.pos_type,
            )
            return {
                "success": True,
                "skipped": True,
                "reason": f"POS type '{lemma.pos_type}' not supported",
                "sentences": [],
            }

        logger.info(
            "Generating %d guided sentences for %s: %s (GUID: %s)",
            num_sentences,
            lemma.pos_type,
            lemma.lemma_text,
            lemma.guid,
        )

        try:
            # Build vocabulary context
            vocabulary_section = build_prompt_vocabulary_section(
                target_word=lemma.lemma_text,
                target_pos_type=lemma.pos_type,
                target_pos_subtype=lemma.pos_subtype or "misc",
                max_level=max_vocabulary_level,
            )

            # Generate all sentences in one call for better variety
            result = self._call_llm_for_sentences(
                lemma=lemma,
                num_sentences=num_sentences,
                vocabulary_section=vocabulary_section,
            )

            if not result or not result.get("sentences"):
                logger.error(
                    "LLM failed to generate sentences for %s",
                    lemma.lemma_text,
                )
                return {"success": False, "error": "LLM generation failed"}

            return {
                "success": True,
                "sentences": result["sentences"],
                "lemma_guid": lemma.guid,
            }

        except Exception as e:
            logger.error(
                "Error generating sentences for %s: %s",
                lemma.lemma_text,
                e,
                exc_info=True,
            )
            return {"success": False, "error": str(e)}

    def _call_llm_for_sentences(
        self,
        lemma: Lemma,
        num_sentences: int,
        vocabulary_section: str,
    ) -> Optional[Dict[Any, Any]]:
        """Call LLM to generate multiple sentences at once."""
        # Load context and prompt template
        context = util.prompt_loader.get_context("sentences", "guided")
        prompt_template = util.prompt_loader.get_prompt("sentences", "guided")

        # Build extra context
        extra_parts = []
        if lemma.disambiguation:
            extra_parts.append(f"Disambiguation: {lemma.disambiguation}")
        extra_context = "\n".join(extra_parts) if extra_parts else ""

        # Strip disambiguation from word for display
        word = lemma.lemma_text
        if "(" in word:
            word = word.split("(")[0].strip()

        # Format the prompt
        prompt = prompt_template.format(
            word=word,
            definition=lemma.definition_text or "",
            pos_type=lemma.pos_type,
            extra_context=extra_context,
            vocabulary_section=vocabulary_section,
            previous_sentences="",
            num_sentences=num_sentences,
        )

        # Context and prompt are passed separately to the LLM

        # Schema for word usage tracking
        word_used_schema = Schema(
            name="WordUsed",
            description="A content word used in the sentence",
            properties={
                "word": SchemaProperty(
                    type="string",
                    description="The word as it appears in the sentence",
                ),
                "lemma": SchemaProperty(
                    type="string",
                    description="The dictionary/base form of the word",
                ),
                "role": SchemaProperty(
                    type="string",
                    description="Part of speech: noun, verb, adjective, adverb, or other",
                ),
            },
        )

        # Schema for multiple sentences
        sentence_schema = Schema(
            name="Sentence",
            description="A generated sentence",
            properties={
                "en": SchemaProperty(
                    type="string",
                    description="The English sentence",
                ),
                "words_used": SchemaProperty(
                    type="array",
                    description="List of content words used (nouns, verbs, adjectives, adverbs)",
                    array_items_schema=word_used_schema,
                ),
            },
        )

        schema = Schema(
            name="SentenceGeneration",
            description="Generated sentences",
            properties={
                "sentences": SchemaProperty(
                    type="array",
                    description=f"List of {num_sentences} generated sentences",
                    array_items_schema=sentence_schema,
                ),
            },
        )

        try:
            response = self.llm_client.generate_chat(
                prompt=prompt,
                context=context,
                json_schema=schema,
                timeout=120,  # Longer timeout for multiple sentences
            )

            if response.structured_data:
                return cast(Dict[Any, Any], response.structured_data)

            logger.error("No structured data received from LLM")
            return None

        except Exception as e:
            logger.error("Error calling LLM: %s", e, exc_info=True)
            return None

    def store_sentences(
        self, sentences_data: List[Dict[str, Any]], source_lemma: Lemma, session: Any
    ) -> Dict[str, Any]:
        """Store generated sentences to the database.

        Args:
            sentences_data: List of sentence dicts with 'en' and 'words_used'
            source_lemma: The lemma the sentences were generated for
            session: Database session

        Returns:
            Dict with 'stored', 'failed', 'errors', 'sentence_ids'
        """
        stored_count = 0
        failed_count = 0
        errors = []
        sentence_ids = []

        for sentence_data in sentences_data:
            try:
                sentence = add_sentence(
                    session=session,
                    pattern_type="guided",
                    tense=None,
                    source_filename=f"buivolas_guided_{source_lemma.guid}",
                    verified=False,
                    notes=(
                        "Guided generation for %s (GUID: %s)"
                        % (source_lemma.lemma_text, source_lemma.guid)
                    ),
                )

                # Store English translation
                en_text = sentence_data.get("en", "")
                if en_text:
                    add_sentence_translation(
                        session=session,
                        sentence=sentence,
                        language_code="en",
                        translation_text=en_text,
                        verified=False,
                    )

                # Store words_used as SentencePatternWord entries
                # Only store words where we can find a matching lemma
                words_used = sentence_data.get("words_used", [])
                position = 0
                for word_data in words_used:
                    if not isinstance(word_data, dict):
                        continue

                    word_lemma = self._find_lemma_for_word(
                        session,
                        word_data.get("lemma", ""),
                        word_data.get("role", "unknown"),
                        source_lemma=source_lemma,
                    )

                    # Only create SentencePatternWord if we found a lemma
                    if word_lemma:
                        pattern_word = SentencePatternWord(
                            sentence_id=sentence.id,
                            lemma_id=word_lemma.id,
                            position=position,
                            slot_name=word_data.get("role", "unknown"),
                            english_text=word_data.get("lemma", ""),
                        )
                        session.add(pattern_word)
                        position += 1

                # Set minimum level to -1 (unverified)
                sentence.minimum_level = -1

                session.flush()
                stored_count += 1
                sentence_ids.append(sentence.id)

                logger.info(
                    "✓ Stored sentence %s: %s",
                    sentence.id,
                    en_text[:50] if en_text else "N/A",
                )

            except Exception as e:
                logger.error("Failed to store sentence: %s", e, exc_info=True)
                failed_count += 1
                errors.append(str(e))
                session.rollback()

        if stored_count > 0:
            session.commit()

        return {
            "stored": stored_count,
            "failed": failed_count,
            "errors": errors,
            "sentence_ids": sentence_ids,
        }

    def _find_lemma_for_word(
        self,
        session: Any,
        word_text: str,
        word_role: str,
        source_lemma: Optional[Lemma] = None,
    ) -> Optional[Lemma]:
        """Find a lemma matching the given word text and role."""
        if not word_text:
            return None

        # Check if it matches the source lemma
        if source_lemma:
            source_text = source_lemma.lemma_text
            if "(" in source_text:
                source_base = source_text.split("(")[0].strip()
            else:
                source_base = source_text

            if word_text.lower() == source_base.lower():
                logger.debug(
                    "Matched word '%s' to source lemma: %s (%s)",
                    word_text,
                    source_lemma.guid,
                    source_lemma.lemma_text,
                )
                return source_lemma

        # Map roles to POS types
        role_to_pos = {
            "noun": "noun",
            "verb": "verb",
            "adjective": "adjective",
            "adverb": "adverb",
        }

        pos_hint = role_to_pos.get(word_role)

        # Try exact match
        query = session.query(Lemma).filter(Lemma.lemma_text == word_text)
        if pos_hint:
            query = query.filter(Lemma.pos_type == pos_hint)
        lemma = query.first()

        if lemma:
            logger.debug("Found lemma for '%s': %s", word_text, lemma.guid)
            return cast(Lemma, lemma)

        # Try case-insensitive match
        query = session.query(Lemma).filter(Lemma.lemma_text.ilike(word_text))
        if pos_hint:
            query = query.filter(Lemma.pos_type == pos_hint)
        lemma = query.first()

        if lemma:
            logger.debug(
                "Found lemma (case-insensitive) for '%s': %s",
                word_text,
                lemma.guid,
            )
            return cast(Lemma, lemma)

        logger.debug("No lemma found for word '%s' (role: %s)", word_text, word_role)
        return None


def generate_guided_sentences(
    config: DataSourceConfig,
    lemma: Lemma,
    num_sentences: int = 5,
    max_vocabulary_level: int = 8,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Convenience function to generate guided sentences for a lemma.

    Args:
        config: DataSourceConfig for database/LLM access
        lemma: The lemma to generate sentences for
        num_sentences: Number of sentences to generate
        max_vocabulary_level: Max vocabulary level to include in prompt
        dry_run: If True, don't persist to database

    Returns:
        Dict with generation results
    """
    generator = GuidedSentenceGenerator(config, dry_run=dry_run)
    return generator.generate_sentences_for_lemma(
        lemma=lemma,
        num_sentences=num_sentences,
        max_vocabulary_level=max_vocabulary_level,
    )
