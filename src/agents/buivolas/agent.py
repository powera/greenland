"""Shared Buivolas agent wrapper for sentence creation."""

import logging
from typing import Any, Dict, Optional

from agents.buivolas.guided_sentences import GuidedSentenceGenerator
from agents.buivolas.llm_sentences import LlmSentenceGenerator
from agents.buivolas.pattern_sentences import PatternSentenceGenerator
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma

logger = logging.getLogger(__name__)


class BuivolasAgent:
    """Buivolas agent that can generate pattern or LLM sentences."""

    def __init__(self, config: DataSourceConfig, dry_run: bool = False):
        self.config = config
        self.debug = config.debug
        self.dry_run = dry_run

        if self.debug:
            logger.setLevel(logging.DEBUG)

        self.pattern_generator = PatternSentenceGenerator(config=config, dry_run=dry_run)
        self.llm_generator = LlmSentenceGenerator(config=config, dry_run=dry_run)
        self.guided_generator = GuidedSentenceGenerator(config=config, dry_run=dry_run)

    def get_session(self) -> Any:
        return create_backend_session(self.config)

    def generate_pattern_sentences_for_guid(
        self, guid: str, max_combinations: Optional[int] = None
    ) -> Dict[str, Any]:
        return self.pattern_generator.generate_candidates_for_guid(
            guid=guid, max_combinations=max_combinations
        )

    def generate_llm_sentences_for_lemma(
        self,
        lemma: Lemma,
        num_sentences: int = 3,
        difficulty_context: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.llm_generator.generate_sentences_for_lemma(
            lemma=lemma,
            num_sentences=num_sentences,
            difficulty_context=difficulty_context,
        )

    def store_llm_sentences(
        self, sentences_data: Any, source_lemma: Lemma, session: Any
    ) -> Dict[str, Any]:
        return self.llm_generator.store_sentences(
            sentences_data=sentences_data, source_lemma=source_lemma, session=session
        )

    def generate_guided_sentences_for_lemma(
        self,
        lemma: Lemma,
        num_sentences: int = 5,
        max_vocabulary_level: int = 7,
    ) -> Dict[str, Any]:
        """Generate sentences using vocabulary-aware prompts."""
        return self.guided_generator.generate_sentences_for_lemma(
            lemma=lemma,
            num_sentences=num_sentences,
            max_vocabulary_level=max_vocabulary_level,
        )

    def store_guided_sentences(
        self, sentences_data: Any, source_lemma: Lemma, session: Any
    ) -> Dict[str, Any]:
        """Store guided sentences to the database."""
        return self.guided_generator.store_sentences(
            sentences_data=sentences_data, source_lemma=source_lemma, session=session
        )
