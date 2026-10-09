"""
Grammar-fact generation workflows.

This module contains the service that coordinates grammar-fact generation.
The actual generation logic for each fact type is in the tasks/ subdirectory.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from words.grammar_fact_tasks import (
    FACT_TASKS,
    animacy,
    auxiliary_verb,
    countability,
    declension_class,
    fanciful_collective,
    grammatical_gender,
    measure_words,
    systems,
    verb_reflexivity,
    verb_transitivity,
)
from words.grammar_fact_generation import save_generated_fact
from words.grammar_fact_tasks.common import FactResult, run_live
from words.grammar_fact_tasks.english_principal_parts import (
    ENGLISH_PRINCIPAL_PARTS_TASK,
    PRINCIPAL_PART_FACT_TYPES,
    generate_and_store_english_principal_parts,
    principal_parts_coverage,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.config.grammar_fact_registry import legacy_supported_fact_types
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation
from wordfreq.translation.client import LinguisticClient
from clients.unified_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


class GrammarFactService:
    """Service for generating grammar facts for lemmas."""

    # Language-specific value sets (gender, auxiliary, reflexivity)
    GENDER_SYSTEMS = systems.GENDER_SYSTEMS
    AUXILIARY_SYSTEMS = systems.AUXILIARY_SYSTEMS
    REFLEXIVITY_SYSTEMS = systems.REFLEXIVITY_SYSTEMS

    # Supported fact types and their required parameters.
    SUPPORTED_FACT_TYPES = legacy_supported_fact_types()
    COMPOUND_FACT_TASKS = {
        ENGLISH_PRINCIPAL_PARTS_TASK: {
            "languages": ["en"],
            "required_pos": ["verb"],
        },
    }

    # Grouped task presets mapping to multiple fact types
    TASK_PRESETS = {
        "all": list(SUPPORTED_FACT_TYPES.keys()),
        "gender": ["grammatical_gender"],
        "measure-words": ["measure_words"],
        "fanciful-collectives": ["fanciful_collective"],
        "nouns": ["grammatical_gender", "countability", "animacy", "declension_class"],
        "verbs": ["verb_transitivity", "verb_reflexivity", "auxiliary_verb"],
        "english-principal-parts": [ENGLISH_PRINCIPAL_PARTS_TASK],
    }

    @classmethod
    def get_fact_config(cls, fact_type: str) -> Dict[str, Any]:
        """Return configuration for a scalar fact or compound fact task."""
        if fact_type in cls.COMPOUND_FACT_TASKS:
            return cls.COMPOUND_FACT_TASKS[fact_type]
        return cls.SUPPORTED_FACT_TYPES[fact_type]

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the grammar-fact service.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
        """
        self.config = config
        self.debug = config.debug

        # Keep db_path for backward compatibility with LinguisticClient
        if self.config.backend_type == BackendType.SQLITE:
            self.db_path = self.config.sqlite_path
        else:
            self.db_path = None

        self.linguistic_client: Optional[LinguisticClient] = None  # Lazy initialization
        self.llm_client: Optional[UnifiedLLMClient] = None  # For direct LLM calls

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Session:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_linguistic_client(self) -> LinguisticClient:
        """Get or create linguistic client for LLM queries."""
        if self.linguistic_client is None:
            client = LinguisticClient(
                model=self.config.model, db_path=self.db_path, debug=self.debug
            )
            self.linguistic_client = client
            return client
        return self.linguistic_client

    def get_llm_client(self) -> UnifiedLLMClient:
        """Get or create LLM client for direct queries."""
        if self.llm_client is None:
            client = UnifiedLLMClient.from_config(self.config)
            if self.config.model:
                client.warm_model(self.config.model)
            self.llm_client = client
            return client
        return self.llm_client

    def generate_fact(
        self,
        fact_type: str,
        lemma: Lemma,
        language_code: str,
        translation: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Dispatch to appropriate task handler based on fact type.

        Args:
            fact_type: Type of grammar fact to generate
            lemma: The Lemma object
            language_code: Language code for language-specific facts
            translation: Translation in target language (if needed)
            session: Database session (optional)

        Returns:
            Tuple of (fact_value, notes, confidence)
        """
        task = FACT_TASKS.get(fact_type)
        if task is None:
            logger.error(f"Unsupported fact type: {fact_type}")
            return None, None, 0.0
        return run_live(
            self, task, session, lemma, translation, language_code, fact_type.replace("_", " ")
        )

    # Backward compatibility methods for Barsukas API
    # These delegate to the task modules

    def generate_measure_words(
        self, lemma: Lemma, chinese_translation: str, session: Optional[Session] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate Chinese measure word(s) for a noun using LLM."""
        return measure_words.generate_measure_words(self, lemma, chinese_translation, session)

    def generate_grammatical_gender(
        self,
        lemma: Lemma,
        target_translation: str,
        language_code: str,
        session: Optional[Session] = None,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate grammatical gender for a noun using LLM."""
        return grammatical_gender.generate_grammatical_gender(
            self, lemma, target_translation, language_code, session
        )

    def generate_verb_transitivity(
        self, lemma: Lemma, session: Optional[Session] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate verb transitivity classification using LLM."""
        return verb_transitivity.generate_verb_transitivity(self, lemma, session)

    def generate_verb_reflexivity(
        self,
        lemma: Lemma,
        target_translation: str,
        language_code: str,
        session: Optional[Session] = None,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate verb reflexivity classification using LLM."""
        return verb_reflexivity.generate_verb_reflexivity(
            self, lemma, target_translation, language_code, session
        )

    def generate_countability(
        self, lemma: Lemma, session: Optional[Session] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate the English noun usage classification using LLM."""
        return countability.generate_countability(self, lemma, session)

    def generate_declension_class(
        self,
        lemma: Lemma,
        target_translation: str,
        language_code: str,
        session: Optional[Session] = None,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate noun declension class using LLM."""
        return declension_class.generate_declension_class(
            self, lemma, target_translation, language_code, session
        )

    def generate_auxiliary_verb(
        self,
        lemma: Lemma,
        target_translation: str,
        language_code: str,
        session: Optional[Session] = None,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate auxiliary verb classification for compound tenses using LLM."""
        return auxiliary_verb.generate_auxiliary_verb(
            self, lemma, target_translation, language_code, session
        )

    def generate_animacy(
        self, lemma: Lemma, session: Optional[Session] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """Generate noun animacy classification using LLM."""
        return animacy.generate_animacy(self, lemma, session)

    def generate_grammar_facts(
        self,
        fact_type: str,
        language_code: str,
        lemmas: Optional[List[Lemma]] = None,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        min_confidence: float = 0.7,
        dry_run: bool = False,
        retry_uncertain: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate grammar facts for lemmas.

        Args:
            fact_type: Type of grammar fact to generate (e.g., 'measure_words')
            language_code: Language code (e.g., 'zh', 'fr')
            lemmas: List of lemmas to process (if None, returns empty result)
            limit: Maximum number of lemmas to process
            skip_existing: Skip lemmas that already have this fact
            min_confidence: Minimum confidence to save the fact
            dry_run: If True, don't save to database
            retry_uncertain: Ask again where a model was uncertain before
                (uncertain_llm_results); by default those lemmas are skipped

        Returns:
            Dictionary with generation results
        """
        if fact_type == ENGLISH_PRINCIPAL_PARTS_TASK and language_code != "en":
            raise ValueError("english_principal_parts only supports language 'en'")
        if language_code == "en" and (
            fact_type == ENGLISH_PRINCIPAL_PARTS_TASK or fact_type in PRINCIPAL_PART_FACT_TYPES
        ):
            return self.generate_english_principal_parts_for_lemmas(
                lemmas=lemmas,
                limit=limit,
                skip_existing=skip_existing,
                min_confidence=min_confidence,
                dry_run=dry_run,
                retry_uncertain=retry_uncertain,
            )

        # Validate fact type
        if fact_type not in self.SUPPORTED_FACT_TYPES:
            raise ValueError(
                f"Unsupported fact type: {fact_type}. "
                f"Supported types: {', '.join(self.SUPPORTED_FACT_TYPES.keys())}"
            )

        fact_config = self.SUPPORTED_FACT_TYPES[fact_type]

        # Validate language
        if language_code not in fact_config["languages"]:
            raise ValueError(
                f"Fact type '{fact_type}' does not support language '{language_code}'. "
                f"Supported languages: {', '.join(fact_config['languages'])}"
            )

        logger.info(f"Generating {fact_type} for language {language_code}...")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be saved")

        # If no lemmas provided, return empty result
        if not lemmas:
            return {
                "fact_type": fact_type,
                "language_code": language_code,
                "processed": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
                "dry_run": dry_run,
            }

        session = self.get_session()
        try:
            # Filter lemmas by required POS types for this fact type
            required_pos = fact_config["required_pos"]
            lemmas = [l for l in lemmas if l.pos_type in required_pos]

            logger.info(f"Found {len(lemmas)} candidate lemmas")

            # Process lemmas
            processed_count = 0
            skipped_count = 0
            success_count = 0
            failed_count = 0
            results = []

            for lemma in lemmas:
                if limit and processed_count >= limit:
                    break

                # Check if fact already exists
                if skip_existing:
                    existing_fact = get_grammar_fact_value(
                        session, lemma.id, language_code, fact_type
                    )
                    if existing_fact is not None:
                        skipped_count += 1
                        continue

                if not retry_uncertain and add_grammar_fact.is_uncertain(
                    session, lemma_id=lemma.id, language_code=language_code, fact_type=fact_type
                ):
                    skipped_count += 1
                    continue

                # Get translation for target language
                translation = get_translation(session, lemma, language_code)
                if not translation:
                    logger.debug(
                        f"No {language_code} translation for '{lemma.lemma_text}', skipping"
                    )
                    skipped_count += 1
                    continue

                processed_count += 1
                logger.info(f"Processing {processed_count}/{limit or '∞'}: {lemma.lemma_text}")

                # Generate fact using dispatch method
                fact_value, notes, confidence = self.generate_fact(
                    fact_type, lemma, language_code, translation, session
                )

                outcome = None
                if not dry_run:
                    # Also records a low-confidence answer as uncertain.
                    outcome = save_generated_fact(
                        session,
                        lemma.id,
                        language_code,
                        fact_type,
                        FactResult(fact_value, notes, confidence),
                        min_confidence,
                        self.config.model,
                    )
                    session.commit()
                if outcome == "exists":
                    # Added by someone else since the check above.
                    skipped_count += 1
                    continue

                if fact_value and confidence >= min_confidence:
                    success_count += 1
                    results.append(
                        {
                            "lemma_id": lemma.id,
                            "lemma_text": lemma.lemma_text,
                            "translation": translation,
                            "fact_value": fact_value,
                            "notes": notes,
                            "confidence": confidence,
                        }
                    )
                    logger.info(f"  ✓ Generated: {fact_value} (confidence: {confidence:.2f})")
                else:
                    failed_count += 1
                    logger.warning(
                        f"  ✗ Failed or low confidence: {fact_value} (confidence: {confidence:.2f})"
                    )

            logger.info(
                f"Complete! Processed: {processed_count}, Success: {success_count}, "
                f"Failed: {failed_count}, Skipped: {skipped_count}"
            )

            return {
                "fact_type": fact_type,
                "language_code": language_code,
                "processed": processed_count,
                "success": success_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "results": results,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error generating grammar facts: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    def generate_english_principal_parts_for_lemmas(
        self,
        *,
        lemmas: Optional[List[Lemma]],
        limit: Optional[int] = None,
        skip_existing: bool = True,
        min_confidence: float = 0.7,
        dry_run: bool = False,
        retry_uncertain: bool = False,
    ) -> Dict[str, Any]:
        """Generate the paired English verb principal parts for selected lemmas."""
        selected = [lemma for lemma in (lemmas or []) if lemma.pos_type == "verb"]
        session = self.get_session()
        processed = 0
        success = 0
        failed = 0
        skipped = 0
        results: List[Dict[str, Any]] = []
        try:
            for selected_lemma in selected:
                if limit is not None and processed >= limit:
                    break
                lemma = session.get(Lemma, selected_lemma.id)
                if lemma is None:
                    skipped += 1
                    continue
                if skip_existing and all(principal_parts_coverage(session, lemma).values()):
                    skipped += 1
                    continue
                processed += 1
                result = generate_and_store_english_principal_parts(
                    self,
                    session,
                    lemma,
                    min_confidence=min_confidence,
                    skip_existing=skip_existing,
                    dry_run=dry_run,
                    retry_uncertain=retry_uncertain,
                )
                if result.get("error"):
                    failed += 1
                elif result.get("skipped"):
                    skipped += 1
                else:
                    success += 1
                    results.append(result)
            return {
                "fact_type": ENGLISH_PRINCIPAL_PARTS_TASK,
                "language_code": "en",
                "processed": processed,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "results": results,
                "dry_run": dry_run,
            }
        finally:
            session.close()
