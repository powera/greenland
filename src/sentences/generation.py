"""Application service coordinating sentence generation strategies."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from sentences.guided_generation import GuidedSentenceGenerator
from sentences.llm_generation import LlmSentenceGenerator
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def generate_examples_for_lemma(
    session: Session,
    config: DataSourceConfig,
    *,
    lemma_id: int,
    mode: str,
    num_sentences: int = 3,
    max_combinations: Optional[int] = None,
    difficulty_context: Optional[int] = None,
    max_vocabulary_level: int = 7,
) -> Dict[str, Any]:
    """Generate and store example sentences for one lemma."""
    if mode == "pattern":
        raise ValueError("Stored pattern generation is retired; use langtools.sentence_patterns")
    lemma = session.get(Lemma, lemma_id)
    if lemma is None:
        raise ValueError(f"Lemma {lemma_id} not found")
    if lemma.guid is None:
        raise ValueError(f"Lemma {lemma_id} has no GUID")

    service = SentenceGenerationService(config=config)
    if mode == "llm":
        generated = service.generate_llm_sentences_for_lemma(
            lemma=lemma,
            num_sentences=num_sentences,
            difficulty_context=difficulty_context,
        )
        if generated.get("success") and generated.get("sentences"):
            generated["storage"] = service.store_llm_sentences(
                sentences_data=generated["sentences"],
                source_lemma=lemma,
                session=session,
            )
        return generated
    if mode == "guided":
        generated = service.generate_guided_sentences_for_lemma(
            lemma=lemma,
            num_sentences=num_sentences,
            max_vocabulary_level=max_vocabulary_level,
        )
        if generated.get("success") and generated.get("sentences"):
            generated["storage"] = service.store_guided_sentences(
                sentences_data=generated["sentences"],
                source_lemma=lemma,
                session=session,
            )
        return generated
    raise ValueError(f"Unsupported sentence generation mode: {mode}")


class SentenceGenerationService:
    """Coordinate basic LLM and vocabulary-guided example generation."""

    def __init__(self, config: DataSourceConfig, dry_run: bool = False) -> None:
        self.config = config
        self.debug = config.debug
        self.dry_run = dry_run

        if self.debug:
            logger.setLevel(logging.DEBUG)

        self.llm_generator = LlmSentenceGenerator(config=config, dry_run=dry_run)
        self.guided_generator = GuidedSentenceGenerator(config=config, dry_run=dry_run)

    def get_session(self) -> Any:
        return create_backend_session(self.config)

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


# Compatibility name retained for callers of the former agent package.
BuivolasAgent = SentenceGenerationService
