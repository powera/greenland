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
from wordfreq.storage.database import Lemma
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

        # Combine context and prompt
        full_prompt = f"{context}\n\n{prompt}"

        # Schema for multiple sentences
        sentence_schema = Schema(
            name="Sentence",
            description="A generated sentence",
            properties={
                "en": SchemaProperty(
                    type="string",
                    description="The English sentence",
                ),
                "tense": SchemaProperty(
                    type="string",
                    description="Verb tense (present or past)",
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
                prompt=full_prompt,
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
