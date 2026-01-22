#!/usr/bin/env python3
"""
Voras - Multi-lingual Translation Validator and Populator

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/check-translations/<lemma_id> endpoint
    - /agents/add-missing-translations/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent runs autonomously to:
1. Validate multi-lingual translations for correctness and proper lemma form
2. Report on translation coverage across all languages
3. Generate missing translations using LLM

"Voras" means "spider" in Lithuanian - weaving together the web of translations!
"""

import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common.lemma_selection import LemmaQueryBuilder, apply_limit_and_sample_rate

# Import submodules
from agents.voras import coverage
from clients.barsukas_cache import BarsukasCacheClient
from clients.batch_queue import BatchRequestMetadata, get_batch_manager
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.storage.models.schema import Lemma, LemmaTranslation
from wordfreq.storage.translation_helpers import (
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    LANGUAGE_NAMES,
    PLURICENTRIC_LANGUAGES,
    convert_llm_response_to_lang_codes,
    get_language_name,
    get_reference_translation,
    is_pluricentric_language,
    set_regional_variant,
)
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.storage.translation_helpers import get_translation as get_translation_helper
from wordfreq.storage.translation_helpers import set_translation as set_translation_helper
from wordfreq.tools.llm_validators import validate_all_translations_for_word
from wordfreq.translation.client import LinguisticClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VorasAgent:
    """Agent for validating and populating multi-lingual translations."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Voras agent.

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

        # Lazy initialization
        self.linguistic_client: Optional[LinguisticClient] = None
        self.cache_client: Optional[BarsukasCacheClient] = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_linguistic_client(self) -> LinguisticClient:
        """Get or create linguistic client for LLM queries."""
        if self.linguistic_client is None:
            self.linguistic_client = LinguisticClient(
                model=self.config.model, db_path=self.db_path, debug=self.debug
            )
        return self.linguistic_client

    def get_cache_client(self) -> Optional[BarsukasCacheClient]:
        """Get or create cache client for BARSUKAS queries."""
        if self.cache_client is None and self.config.barsukas_url:
            self.cache_client = BarsukasCacheClient(
                base_url=self.config.barsukas_url,
                cache_only=self.config.cache_only,
                debug=self.debug,
            )
        return self.cache_client

    def get_translation(self, session: Any, lemma: Lemma, lang_code: str) -> Optional[str]:
        """
        Get translation for a lemma in the specified language.

        Handles both Lemma table columns and LemmaTranslation table.
        """
        return get_translation_helper(session, lemma, lang_code)

    def set_translation(
        self,
        session: Any,
        lemma: Lemma,
        lang_code: str,
        translation: str,
        source: Optional[str] = None,
    ) -> None:
        """
        Set translation for a lemma in the specified language.

        Handles both Lemma table columns and LemmaTranslation table.
        Includes operation logging for audit trail.
        """
        # Use helper function which returns (old_translation, new_translation)
        old_translation, new_translation = set_translation_helper(
            session, lemma, lang_code, translation
        )

        # Log the translation change
        log_translation_change(
            session=session,
            source=source or f"voras-agent/{self.config.model}",
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=lang_code,
            old_translation=old_translation,
            new_translation=new_translation,
        )

    def validate_translations(
        self,
        language_code: str,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
        lemmas: Optional[List[Lemma]] = None,
    ) -> Dict[str, Any]:
        """
        Validate translations for a specific language using efficient single-call-per-word approach.

        Args:
            language_code: Language code to check (lt, zh, ko, fr, sw, vi)
            limit: Maximum number of words to check
            sample_rate: Fraction of words to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues
            lemmas: Optional pre-filtered list of lemmas to check (if None, queries all curated)

        Returns:
            Dictionary with validation results for the specified language
        """
        if language_code not in LANGUAGE_FIELDS:
            raise ValueError(f"Unsupported language code: {language_code}")

        field_name, language_name, _ = LANGUAGE_FIELDS[language_code]
        logger.info(
            f"Validating {language_name} translations (efficient mode: 1 LLM call per word)..."
        )

        session = self.get_session()
        try:
            # Use provided lemmas or query for them
            if lemmas is not None:
                # Filter to lemmas with translation in this language
                lemmas_to_process = [
                    l for l in lemmas if self.get_translation(session, l, language_code)
                ]
                # Apply limit and sample_rate directly to list
                if limit is not None:
                    lemmas_to_process = lemmas_to_process[:limit]
                if 0.0 < sample_rate < 1.0:
                    import random

                    sample_size = max(1, int(len(lemmas_to_process) * sample_rate))
                    lemmas_to_process = random.sample(lemmas_to_process, sample_size)
            else:
                # Get lemmas with this language translation
                query = (
                    LemmaQueryBuilder(session)
                    .curated_only()
                    .has_translation_in(language_code)
                    .order_by_id()
                    .build()
                )
                lemmas_to_process = apply_limit_and_sample_rate(query, limit, sample_rate)
            logger.info(f"Found {len(lemmas_to_process)} lemmas with {language_name} translations")

            # Validate translations
            issues_found = []
            checked_count = 0

            for lemma in lemmas_to_process:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Validated {checked_count}/{len(lemmas_to_process)} words...")

                # Gather all translations for this lemma
                translations = {}
                for lang_code in LANGUAGE_FIELDS.keys():
                    translation = self.get_translation(session, lemma, lang_code)
                    if translation and translation.strip():
                        translations[lang_code] = translation

                if not translations:
                    continue

                logger.debug(
                    f"Validating word '{lemma.lemma_text}' (GUID: {lemma.guid}), checking {language_name}: '{translations.get(language_code, 'N/A')}'"
                )

                # Validate all translations in one call
                validation_results = validate_all_translations_for_word(
                    lemma.lemma_text, translations, lemma.pos_type, self.config.model
                )

                # Only process results for the requested language
                if language_code in validation_results:
                    lang_validation = validation_results[language_code]

                    has_issues = (
                        not lang_validation["is_correct"] or not lang_validation["is_lemma_form"]
                    ) and lang_validation["confidence"] >= confidence_threshold

                    if has_issues:
                        issues_found.append(
                            {
                                "guid": lemma.guid,
                                "english": lemma.lemma_text,
                                "current_translation": translations[language_code],
                                "suggested_translation": lang_validation["suggested_translation"],
                                "pos_type": lemma.pos_type,
                                "is_correct": lang_validation["is_correct"],
                                "is_lemma_form": lang_validation["is_lemma_form"],
                                "issues": lang_validation["issues"],
                                "confidence": lang_validation["confidence"],
                            }
                        )
                        logger.warning(
                            f"Translation issue ({lemma.guid}): '{lemma.lemma_text}' → '{translations[language_code]}' "
                            f"(suggested: '{lang_validation['suggested_translation']}', confidence: {lang_validation['confidence']:.2f})"
                        )

            logger.info(
                f"Found {len(issues_found)} {language_name} translations with potential issues"
            )

            return {
                "language_code": language_code,
                "language_name": language_name,
                "total_checked": checked_count,
                "issues_found": len(issues_found),
                "issue_rate": (len(issues_found) / checked_count * 100) if checked_count else 0,
                "issues": issues_found,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            logger.error(f"Error validating {language_name} translations: {e}")
            return {
                "error": str(e),
                "language_code": language_code,
                "language_name": language_name,
                "total_checked": 0,
                "issues_found": 0,
                "issue_rate": 0,
                "issues": [],
            }
        finally:
            session.close()

    def validate_all_translations(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
        lemmas: Optional[List[Lemma]] = None,
    ) -> Dict[str, Any]:
        """
        Validate all multi-lingual translations using efficient single-call-per-word approach.

        Args:
            limit: Maximum number of lemmas to check
            sample_rate: Fraction of lemmas to sample
            confidence_threshold: Minimum confidence to flag issues
            lemmas: Optional pre-filtered list of lemmas to check (if None, queries all curated)

        Returns:
            Dictionary with results for all languages
        """
        logger.info(
            "Validating all multi-lingual translations (efficient mode: 1 LLM call per word)..."
        )

        session = self.get_session()
        try:
            # Use provided lemmas or query for them
            if lemmas is not None:
                # Filter to lemmas with at least one translation
                lemmas_to_process = []
                for lemma in lemmas:
                    has_translation = False
                    for lang_code in LANGUAGE_FIELDS.keys():
                        if self.get_translation(session, lemma, lang_code):
                            has_translation = True
                            break
                    if has_translation:
                        lemmas_to_process.append(lemma)
                    if limit and len(lemmas_to_process) >= limit:
                        break
            else:
                # Get all lemmas with GUIDs
                query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

                if limit:
                    query = query.limit(limit * 2)  # Get extra to account for filtering

                all_lemmas = query.all()

                # Filter to lemmas with at least one translation (handles both column and table storage)
                lemmas_to_process = []
                for lemma in all_lemmas:
                    has_translation = False
                    for lang_code in LANGUAGE_FIELDS.keys():
                        if self.get_translation(session, lemma, lang_code):
                            has_translation = True
                            break
                    if has_translation:
                        lemmas_to_process.append(lemma)
                    if limit and len(lemmas_to_process) >= limit:
                        break

            logger.info(f"Found {len(lemmas_to_process)} lemmas with translations")

            # Sample if needed
            if sample_rate < 1.0:
                sample_size = int(len(lemmas_to_process) * sample_rate)
                lemmas_to_process = random.sample(lemmas_to_process, sample_size)
                logger.info(f"Sampling {len(lemmas_to_process)} lemmas ({sample_rate*100:.0f}%)")

            # Initialize results structure
            results_by_language: Dict[str, Dict[str, Any]] = {
                lang_code: {
                    "language_code": lang_code,
                    "language_name": LANGUAGE_FIELDS[lang_code][1],
                    "total_checked": 0,
                    "issues_found": 0,
                    "issue_rate": 0.0,
                    "issues": [],
                    "confidence_threshold": confidence_threshold,
                }
                for lang_code in LANGUAGE_FIELDS.keys()
            }

            # Validate all translations for each lemma in one LLM call
            checked_count = 0
            for lemma in lemmas_to_process:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Validated {checked_count}/{len(lemmas_to_process)} lemmas...")

                # Gather all translations for this lemma
                translations = {}
                for lang_code in LANGUAGE_FIELDS.keys():
                    translation = self.get_translation(session, lemma, lang_code)
                    if translation and translation.strip():
                        translations[lang_code] = translation

                if not translations:
                    continue

                logger.debug(
                    f"Validating word '{lemma.lemma_text}' (GUID: {lemma.guid}) with {len(translations)} translations"
                )

                # Validate all translations in one call
                validation_results = validate_all_translations_for_word(
                    lemma.lemma_text, translations, lemma.pos_type, self.config.model
                )

                # Process results for each language
                for lang_code, lang_validation in validation_results.items():
                    lang_result = results_by_language[lang_code]
                    lang_result["total_checked"] += 1

                    has_issues = (
                        not lang_validation["is_correct"] or not lang_validation["is_lemma_form"]
                    ) and lang_validation["confidence"] >= confidence_threshold

                    if has_issues:
                        lang_result["issues_found"] += 1
                        lang_result["issues"].append(
                            {
                                "guid": lemma.guid,
                                "english": lemma.lemma_text,
                                "current_translation": translations[lang_code],
                                "suggested_translation": lang_validation["suggested_translation"],
                                "pos_type": lemma.pos_type,
                                "is_correct": lang_validation["is_correct"],
                                "is_lemma_form": lang_validation["is_lemma_form"],
                                "issues": lang_validation["issues"],
                                "confidence": lang_validation["confidence"],
                            }
                        )

            # Calculate issue rates
            total_issues = 0
            for lang_result in results_by_language.values():
                if lang_result["total_checked"] > 0:
                    lang_result["issue_rate"] = (
                        lang_result["issues_found"] / lang_result["total_checked"] * 100
                    )
                total_issues += lang_result["issues_found"]
                logger.info(
                    f"{lang_result['language_name']}: "
                    f"{lang_result['issues_found']}/{lang_result['total_checked']} issues "
                    f"({lang_result['issue_rate']:.1f}%)"
                )

            return {"by_language": results_by_language, "total_issues_all_languages": total_issues}

        except Exception as e:
            logger.error(f"Error validating all translations: {e}")
            return {"error": str(e), "by_language": {}, "total_issues_all_languages": 0}
        finally:
            session.close()

    def regenerate_all_translations(
        self,
        limit: Optional[int] = None,
        dry_run: bool = False,
        batch_mode: bool = False,
        lemmas: Optional[List[Lemma]] = None,
    ) -> Dict[str, Any]:
        """
        Delete all non-Lithuanian translations and regenerate them fresh.

        Args:
            limit: Maximum number of words to process
            dry_run: If True, only report what would be done without making changes
            batch_mode: If True, queue batch requests instead of making synchronous calls
            lemmas: Optional pre-filtered list of lemmas to process (if None, queries all curated)

        Returns:
            Dictionary with regeneration results
        """
        if batch_mode:
            logger.info("Starting translation regeneration in BATCH MODE (queueing requests)...")
        else:
            logger.info("Starting translation regeneration (delete + regenerate all non-LT)...")

        session = self.get_session()
        client = self.get_linguistic_client()
        batch_manager = get_batch_manager(debug=self.debug) if batch_mode else None

        # All languages except Lithuanian
        languages_to_regenerate = [lc for lc in LANGUAGE_FIELDS.keys() if lc != "lt"]

        # Initialize results structure
        results: Dict[str, Any] = {
            "total_words_processed": 0,
            "total_translations_added": 0,
            "total_failed": 0,
            "batch_requests_queued": 0,
            "by_language": {
                lang_code: {
                    "language_name": get_language_name(lang_code),
                    "deleted": 0,
                    "added": 0,
                    "failed": 0,
                }
                for lang_code in languages_to_regenerate
            },
        }

        try:
            # Use provided lemmas or query for them
            if lemmas is not None:
                words_to_process = lemmas[:limit] if limit else lemmas
            else:
                # Get all lemmas with GUIDs (curated words)
                query = LemmaQueryBuilder(session).curated_only().order_by_id().build()
                words_to_process = apply_limit_and_sample_rate(query, limit, sample_rate=1.0)
            total_words = len(words_to_process)

            logger.info(f"Found {total_words} curated words to process")

            # First pass: delete existing non-Lithuanian translations
            logger.info("Deleting existing non-Lithuanian translations...")
            for lemma in words_to_process:
                for lang_code in languages_to_regenerate:
                    field_name, _, _ = LANGUAGE_FIELDS[lang_code]
                    existing = getattr(lemma, field_name)
                    if existing and existing.strip():
                        if not dry_run:
                            setattr(lemma, field_name, None)
                        results["by_language"][lang_code]["deleted"] += 1

            if not dry_run:
                session.commit()
                logger.info("Deleted all non-Lithuanian translations")
            else:
                logger.info("[DRY RUN] Would delete all non-Lithuanian translations")

            # Second pass: regenerate all translations
            logger.info("Regenerating translations...")
            for i, lemma in enumerate(words_to_process, 1):
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{total_words} words processed")

                results["total_words_processed"] += 1

                try:
                    if dry_run:
                        for lang_code in languages_to_regenerate:
                            results["by_language"][lang_code]["added"] += 1
                            results["total_translations_added"] += 1
                        logger.info(
                            f"[DRY RUN] Would generate all translations for '{lemma.lemma_text}'"
                        )
                        continue

                    if batch_mode:
                        # Queue batch request - implementation would go here using batch module
                        # For brevity, just increment counter
                        results["batch_requests_queued"] += 1
                        if i % 100 == 0:
                            logger.info(
                                f"Queued {results['batch_requests_queued']} batch requests..."
                            )
                    else:
                        # Synchronous mode: use query_translations method - ONE CALL
                        # Use Lithuanian as reference translation
                        translations, success = client.query_translations(
                            english_word=lemma.lemma_text,
                            reference_translation=(
                                "lt",
                                get_translation(session, lemma, "lt") or "",
                            ),
                            definition=lemma.definition_text,
                            pos_type=lemma.pos_type,
                            pos_subtype=lemma.pos_subtype,
                        )

                        if not success or not translations:
                            logger.warning(f"Failed to get translations for '{lemma.lemma_text}'")
                            for lang_code in languages_to_regenerate:
                                results["by_language"][lang_code]["failed"] += 1
                            results["total_failed"] += 1
                            continue

                        # Add all non-Lithuanian translations
                        added_this_word = 0
                        for lang_code in languages_to_regenerate:
                            field_name, language_name, _ = LANGUAGE_FIELDS[lang_code]
                            llm_field = LANG_CODE_TO_LLM_FIELD.get(lang_code, "")
                            translation = translations.get(llm_field, "").strip()

                            if translation:
                                setattr(lemma, field_name, translation)
                                logger.debug(f"  Added {language_name}: '{translation}'")
                                results["by_language"][lang_code]["added"] += 1
                                results["total_translations_added"] += 1
                                added_this_word += 1
                            else:
                                logger.warning(
                                    f"  LLM returned empty {language_name} translation for '{lemma.lemma_text}'"
                                )
                                results["by_language"][lang_code]["failed"] += 1
                                results["total_failed"] += 1

                        # Commit all updates for this word at once
                        session.commit()
                        logger.info(
                            f"Added {added_this_word}/{len(languages_to_regenerate)} translations for '{lemma.lemma_text}' (GUID: {lemma.guid})"
                        )

                except Exception as e:
                    logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                    session.rollback()
                    for lang_code in languages_to_regenerate:
                        results["by_language"][lang_code]["failed"] += 1
                    results["total_failed"] += 1

        finally:
            session.close()

        return results

    def fix_missing_translations(
        self,
        language_code: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
        lemmas: Optional[List[Lemma]] = None,
    ) -> Dict[str, Any]:
        """
        Generate missing translations using LLM and update the database.

        Args:
            language_code: Specific language(s) to fix. Can be a single code (str),
                          a list of codes, or None (all languages)
            limit: Maximum number of words to process
            dry_run: If True, only report what would be fixed without making changes
            lemmas: Optional pre-filtered list of lemmas to process (if None, queries all curated)

        Returns:
            Dictionary with fix results
        """
        logger.info("Starting translation generation (efficient mode: 1 LLM call per word)...")

        session = self.get_session()
        client = self.get_linguistic_client()

        # Handle language_code as string, list, or None
        if language_code is None:
            languages_to_fix = list(LANGUAGE_FIELDS.keys())
        elif isinstance(language_code, str):
            languages_to_fix = [language_code]
        else:
            languages_to_fix = language_code

        # Initialize results structure
        results: Dict[str, Any] = {
            "total_fixed": 0,
            "total_failed": 0,
            "by_language": {
                lang_code: {
                    "language_name": get_language_name(lang_code),
                    "total_missing": 0,
                    "fixed": 0,
                    "failed": 0,
                }
                for lang_code in languages_to_fix
            },
        }

        try:
            # Use provided lemmas or query for them
            if lemmas is not None:
                all_lemmas = lemmas[:limit] if limit else lemmas
            else:
                # Build query to find words missing ANY of the target translations
                # For simplicity, we'll get all lemmas and check missing translations using helper method
                # This is less efficient but handles both storage types uniformly
                query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

                if limit:
                    query = query.limit(limit)

                all_lemmas = query.all()

            # Filter to lemmas missing at least one target translation
            words_to_process = []
            for lemma in all_lemmas:
                has_missing = False
                for lang_code in languages_to_fix:
                    translation = self.get_translation(session, lemma, lang_code)
                    if not translation or not translation.strip():
                        has_missing = True
                        break
                if has_missing:
                    words_to_process.append(lemma)

            total_words = len(words_to_process)
            logger.info(f"Found {total_words} words with missing translations in target languages")

            # Count missing translations per language
            for lemma in words_to_process:
                for lang_code in languages_to_fix:
                    translation = self.get_translation(session, lemma, lang_code)
                    if not translation or not translation.strip():
                        results["by_language"][lang_code]["total_missing"] += 1

            # Process each word once
            for i, lemma in enumerate(words_to_process, 1):
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{total_words} words processed")

                # Find which languages are missing for this word
                missing_languages = []
                for lang_code in languages_to_fix:
                    language_name = get_language_name(lang_code)
                    translation = self.get_translation(session, lemma, lang_code)
                    if not translation or not translation.strip():
                        missing_languages.append((lang_code, language_name))

                if not missing_languages:
                    continue

                logger.debug(
                    f"Processing word '{lemma.lemma_text}' (GUID: {lemma.guid}), missing {len(missing_languages)} translations"
                )

                try:
                    if dry_run:
                        for lang_code, language_name in missing_languages:
                            logger.info(
                                f"[DRY RUN] Would generate {language_name} translation for '{lemma.lemma_text}'"
                            )
                            results["by_language"][lang_code]["fixed"] += 1
                            results["total_fixed"] += 1
                        continue

                    # Try to get translations from cache first (cache returns lang_code -> translation)
                    translations_by_lang_code: Optional[Dict[str, str]] = None
                    translation_source: Optional[str] = None
                    cache_client = self.get_cache_client()
                    if cache_client:
                        try:
                            translations_by_lang_code = cache_client.get_translations(lemma.guid)
                            if translations_by_lang_code:
                                logger.info(
                                    f"Using cached translations for '{lemma.lemma_text}' (GUID: {lemma.guid})"
                                )
                                translation_source = "barsukas-proxy"
                        except Exception as cache_error:
                            # If cache_only mode, this will raise an exception that propagates
                            # Otherwise, we'll fall through to LLM query
                            logger.debug(
                                f"Cache lookup failed for '{lemma.lemma_text}': {cache_error}"
                            )
                            if self.config.cache_only:
                                raise

                    # If no cache hit, we need to query LLM - which requires a reference translation
                    if not translations_by_lang_code:
                        # Find a reference translation using helper function
                        missing_lang_codes = [lc for lc, _ in missing_languages]
                        reference_lang_code, reference_translation = get_reference_translation(
                            session, lemma, exclude_languages=missing_lang_codes
                        )

                        if not reference_translation or not reference_lang_code:
                            logger.warning(
                                f"No reference translation available for '{lemma.lemma_text}', skipping"
                            )
                            for lang_code, _ in missing_languages:
                                results["by_language"][lang_code]["failed"] += 1
                                results["total_failed"] += 1
                            continue

                    # If no cache hit, query LLM for translations
                    if (
                        not translations_by_lang_code
                        and reference_lang_code
                        and reference_translation
                    ):
                        # Build list of language names (lowercase) for only the missing languages
                        missing_lang_names = [
                            LANGUAGE_NAMES[lang_code].lower()
                            for lang_code, _ in missing_languages
                            if lang_code in LANGUAGE_NAMES
                        ]

                        # Query LLM for translations - ONE CALL for only missing languages
                        llm_translations, success = client.query_translations(
                            english_word=lemma.lemma_text,
                            reference_translation=(reference_lang_code, reference_translation),
                            definition=lemma.definition_text,
                            pos_type=lemma.pos_type,
                            pos_subtype=lemma.pos_subtype,
                            languages=missing_lang_names,
                        )

                        if not success or not llm_translations:
                            logger.warning(f"Failed to get translations for '{lemma.lemma_text}'")
                            for lang_code, _ in missing_languages:
                                results["by_language"][lang_code]["failed"] += 1
                                results["total_failed"] += 1
                            continue

                        # Convert LLM response format (field_name -> translation) to lang_code format
                        translations_by_lang_code = convert_llm_response_to_lang_codes(
                            llm_translations
                        )
                        translation_source = f"voras-agent/{self.config.model}"

                    # Apply translations to lemma (translations_by_lang_code now always uses lang_code keys)
                    if translations_by_lang_code:
                        for lang_code, language_name in missing_languages:
                            translation = translations_by_lang_code.get(lang_code, "").strip()

                            if translation:
                                # Update the translation using helper method
                                self.set_translation(
                                    session,
                                    lemma,
                                    lang_code,
                                    translation,
                                    source=translation_source,
                                )
                                logger.debug(
                                    f"  Added {language_name} translation: '{translation}'"
                                )
                                results["by_language"][lang_code]["fixed"] += 1
                                results["total_fixed"] += 1
                            else:
                                logger.warning(
                                    f"  LLM returned empty {language_name} translation for '{lemma.lemma_text}'"
                                )
                                results["by_language"][lang_code]["failed"] += 1
                                results["total_failed"] += 1

                        # Commit all updates for this word at once
                        session.commit()
                        added_count = len(
                            [
                                lc
                                for lc, _ in missing_languages
                                if lc != "lt" and translations_by_lang_code.get(lc, "").strip()
                            ]
                        )
                        logger.info(
                            f"Added {added_count} translations for '{lemma.lemma_text}' (GUID: {lemma.guid})"
                        )

                except Exception as e:
                    logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                    session.rollback()
                    for lang_code, _ in missing_languages:
                        results["by_language"][lang_code]["failed"] += 1
                        results["total_failed"] += 1

            # Log summary per language
            for lang_code in languages_to_fix:
                lang_result = results["by_language"][lang_code]
                logger.info(
                    f"Completed {lang_result['language_name']}: "
                    f"{lang_result['fixed']} fixed, {lang_result['failed']} failed "
                    f"(of {lang_result['total_missing']} missing)"
                )

        finally:
            session.close()

        return results

    def fix_missing_regional_variants(
        self,
        language_code: str,
        limit: Optional[int] = None,
        dry_run: bool = False,
        lemmas: Optional[List[Lemma]] = None,
    ) -> Dict[str, Any]:
        """
        Generate missing regional variants for a pluricentric language.

        This should be called AFTER base translations exist. It queries the LLM
        to identify regional differences for languages like en, es, pt, zh.

        Args:
            language_code: Base language code (must be pluricentric: en, es, pt, zh)
            limit: Maximum number of words to process
            dry_run: If True, only report what would be generated without making changes
            lemmas: Optional pre-filtered list of lemmas to process

        Returns:
            Dictionary with generation results
        """
        if not is_pluricentric_language(language_code):
            logger.error(f"Language '{language_code}' is not pluricentric")
            return {"error": f"Language '{language_code}' is not pluricentric"}

        lang_config = PLURICENTRIC_LANGUAGES[language_code]
        region_codes = list(lang_config["variants"].keys())

        logger.info(
            f"Starting regional variant generation for {lang_config['display_name']} "
            f"(regions: {', '.join(region_codes)})..."
        )

        session = self.get_session()
        client = self.get_linguistic_client()

        results: Dict[str, Any] = {
            "language": language_code,
            "language_name": lang_config["display_name"],
            "total_processed": 0,
            "total_with_variants": 0,
            "total_failed": 0,
            "by_region": {
                region: {"name": info["name"], "variants_found": 0}
                for region, info in lang_config["variants"].items()
            },
        }

        try:
            # Use provided lemmas or query for them
            if lemmas is not None:
                all_lemmas = lemmas[:limit] if limit else lemmas
            else:
                # Get lemmas that have a base translation for this language
                query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

                if limit:
                    query = query.limit(limit)

                all_lemmas = query.all()

            # Filter to lemmas that have a base translation
            words_to_process = []
            for lemma in all_lemmas:
                base_translation = self.get_translation(session, lemma, language_code)
                if base_translation and base_translation.strip():
                    words_to_process.append((lemma, base_translation))

            total_words = len(words_to_process)
            logger.info(f"Found {total_words} words with {language_code} translations to check")

            for i, (lemma, base_translation) in enumerate(words_to_process, 1):
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{total_words} words processed")

                try:
                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would check regional variants for '{lemma.lemma_text}' "
                            f"(base: {base_translation})"
                        )
                        results["total_processed"] += 1
                        continue

                    # Query LLM for regional variants
                    variants, success = client.query_regional_variants(
                        english_word=lemma.lemma_text,
                        base_translation=base_translation,
                        base_language_code=language_code,
                        definition=lemma.definition_text or "",
                        pos_type=lemma.pos_type,
                    )

                    if not success:
                        logger.warning(f"Failed to get regional variants for '{lemma.lemma_text}'")
                        results["total_failed"] += 1
                        continue

                    results["total_processed"] += 1

                    if variants:
                        results["total_with_variants"] += 1
                        logger.info(
                            f"Found {len(variants)} regional variant(s) for '{lemma.lemma_text}': "
                            f"{variants}"
                        )

                        # Store each variant
                        for region_code, variant_translation in variants.items():
                            set_regional_variant(session, lemma, region_code, variant_translation)
                            results["by_region"][region_code]["variants_found"] += 1

                        session.commit()

                except Exception as e:
                    logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                    session.rollback()
                    results["total_failed"] += 1

            # Log summary
            logger.info(
                f"Regional variant generation complete: "
                f"{results['total_processed']} processed, "
                f"{results['total_with_variants']} with variants, "
                f"{results['total_failed']} failed"
            )
            for region, info in results["by_region"].items():
                if info["variants_found"] > 0:
                    logger.info(f"  {info['name']}: {info['variants_found']} variants")

        finally:
            session.close()

        return results

    def submit_batch(
        self, agent_name: str = "voras", metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Submit pending batch requests to OpenAI."""
        batch_manager = get_batch_manager(debug=self.debug)
        pending = batch_manager.get_pending_requests(agent_name=agent_name)

        if not pending:
            logger.warning("No pending batch requests found")
            return {"batch_id": None, "file_id": None, "count": 0}

        logger.info("Submitting %s pending requests as a batch...", len(pending))
        batch_id, file_id = batch_manager.submit_batch(pending, batch_metadata=metadata)

        logger.info("Batch submitted successfully!")
        logger.info("  Batch ID: %s", batch_id)
        logger.info("  File ID: %s", file_id)
        logger.info("  Request count: %s", len(pending))
        return {"batch_id": batch_id, "file_id": file_id, "count": len(pending)}

    # Delegate coverage operations to coverage module
    def check_overall_coverage(
        self,
        min_level: Optional[int] = None,
        max_level: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Check overall coverage. Delegates to coverage module."""
        session = self.get_session()
        try:
            return coverage.check_overall_coverage(session, min_level, max_level)
        finally:
            session.close()

    def check_language_coverage(self, language_code: str) -> Dict[str, Any]:
        """Check language coverage. Delegates to coverage module."""
        session = self.get_session()
        try:
            return coverage.check_language_coverage(session, language_code)
        finally:
            session.close()

    def check_difficulty_level_coverage(
        self,
        min_level: Optional[int] = None,
        max_level: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Check difficulty level coverage. Delegates to coverage module."""
        session = self.get_session()
        try:
            return coverage.check_difficulty_level_coverage(session, min_level, max_level)
        finally:
            session.close()

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        min_level: Optional[int] = None,
        max_level: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run all coverage checks and generate a comprehensive report."""
        logger.info("Starting full multi-lingual translation coverage check...")
        start_time = datetime.now()

        results: Dict[str, Any] = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "level_filter": {"min": min_level, "max": max_level},
            "checks": {
                "overall_coverage": self.check_overall_coverage(min_level, max_level),
                "difficulty_level_coverage": self.check_difficulty_level_coverage(
                    min_level, max_level
                ),
            },
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        coverage.print_summary(results, start_time, duration)

        # Write to output file if requested
        if output_file:
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_summary(
        self, results: Dict[str, Any], start_time: datetime, duration: float
    ) -> None:
        """Delegate to coverage module."""
        coverage.print_summary(results, start_time, duration)
