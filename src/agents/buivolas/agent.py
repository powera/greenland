"""Shared Buivolas agent wrapper for sentence creation."""

import logging
from typing import Dict, List, Optional

from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma

from agents.buivolas.llm_sentences import LlmSentenceGenerator
from agents.buivolas.pattern_sentences import PatternSentenceGenerator

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

    def get_session(self):
        return create_backend_session(self.config)

    def generate_pattern_sentences_for_guid(
        self, guid: str, max_combinations: Optional[int] = None
    ) -> Dict:
        return self.pattern_generator.generate_candidates_for_guid(
            guid=guid, max_combinations=max_combinations
        )

    def generate_llm_sentences_for_lemma(
        self,
        lemma: Lemma,
        target_languages: List[str],
        num_sentences: int = 3,
        difficulty_context: Optional[int] = None,
    ) -> Dict[str, any]:
        return self.llm_generator.generate_sentences_for_noun(
            lemma=lemma,
            target_languages=target_languages,
            num_sentences=num_sentences,
            difficulty_context=difficulty_context,
        )

    def store_llm_sentences(self, sentences_data, source_lemma: Lemma, session) -> Dict:
        return self.llm_generator.store_sentences(
            sentences_data=sentences_data, source_lemma=source_lemma, session=session
        )
