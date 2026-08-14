"""Application service coordinating sentence generation strategies."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from sentences.guided_generation import GuidedSentenceGenerator
from sentences.llm_generation import LlmSentenceGenerator
from sentences.pattern_generation import PatternSentenceGenerator
from sentences.pattern_generation import ALL_PATTERNS
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def generate_pattern_candidates(
    session: Session,
    config: DataSourceConfig,
    *,
    pattern_ids: Optional[List[str]] = None,
    all_patterns: bool = False,
    max_combinations: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate and store candidates for selected sentence patterns."""
    patterns_by_id = {pattern["pattern_id"]: pattern for pattern in ALL_PATTERNS}
    if all_patterns:
        selected_patterns = list(ALL_PATTERNS)
    else:
        requested_ids = pattern_ids or []
        unknown_ids = sorted(set(requested_ids) - set(patterns_by_id))
        if unknown_ids:
            raise ValueError(f"Unknown sentence pattern(s): {', '.join(unknown_ids)}")
        selected_patterns = [patterns_by_id[pattern_id] for pattern_id in requested_ids]

    if not selected_patterns:
        raise ValueError("pattern_ids must be non-empty unless all_patterns is true")

    generator = PatternSentenceGenerator(config=config)
    pattern_results = [
        generator.generate_candidates_for_pattern(
            pattern,
            max_combinations=max_combinations,
            session=session,
        )
        for pattern in selected_patterns
    ]
    return {
        "patterns_processed": len(pattern_results),
        "total_candidates": sum(result.get("total", 0) for result in pattern_results),
        "stored": sum(result.get("success_count", 0) for result in pattern_results),
        "duplicates": sum(result.get("duplicate_count", 0) for result in pattern_results),
        "errors": sum(result.get("error_count", 0) for result in pattern_results),
    }


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
    lemma = session.get(Lemma, lemma_id)
    if lemma is None:
        raise ValueError(f"Lemma {lemma_id} not found")
    if lemma.guid is None:
        raise ValueError(f"Lemma {lemma_id} has no GUID")

    service = SentenceGenerationService(config=config)
    if mode == "pattern":
        return service.generate_pattern_sentences_for_guid(
            guid=lemma.guid,
            max_combinations=max_combinations,
            session=session,
        )
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
    """Coordinate pattern, basic LLM, and vocabulary-guided generation."""

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
        self,
        guid: str,
        max_combinations: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        return self.pattern_generator.generate_candidates_for_guid(
            guid=guid,
            max_combinations=max_combinations,
            session=session,
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


# Compatibility name retained for callers of the former agent package.
BuivolasAgent = SentenceGenerationService
