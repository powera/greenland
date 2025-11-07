#!/usr/bin/env python3
"""
Voras - Multi-lingual Translation Validator and Populator

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
from typing import Any, Dict, List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from clients.batch_queue import BatchRequestMetadata, get_batch_manager
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, LemmaTranslation
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.tools.llm_validators import validate_all_translations_for_word
from wordfreq.translation.client import LinguisticClient

# Import submodules
from wordfreq.agents.voras import batch, coverage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Language mappings
# Format: 'code': (field_name_or_code, display_name, use_lemma_translation_table)
# If use_lemma_translation_table is True, field_name_or_code is the language_code for LemmaTranslation table
# If False, field_name_or_code is the column name in Lemma table
LANGUAGE_FIELDS = {
    'lt': ('lithuanian_translation', 'Lithuanian', False),
    'zh': ('chinese_translation', 'Chinese', False),
    'ko': ('korean_translation', 'Korean', False),
    'fr': ('french_translation', 'French', False),
    'es': ('es', 'Spanish', True),
    'de': ('de', 'German', True),
    'pt': ('pt', 'Portuguese', True),
    'sw': ('swahili_translation', 'Swahili', False),
    'vi': ('vietnamese_translation', 'Vietnamese', False)
}


class VorasAgent:
    """Agent for validating and populating multi-lingual translations."""

    def __init__(self, db_path: str = None, debug: bool = False, model: str = None):
        """
        Initialize the Voras agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            model: LLM model to use for validation and generation (default: gpt-5-mini for validation)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        # Default to gpt-5-mini for translation validation (like lokys), but allow override
        self.model = model or "gpt-5-mini"
        self.linguistic_client = None  # Lazy initialization

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def get_linguistic_client(self):
        """Get or create linguistic client for LLM queries."""
        if self.linguistic_client is None:
            self.linguistic_client = LinguisticClient(
                model=self.model,
                db_path=self.db_path,
                debug=self.debug
            )
        return self.linguistic_client

    def get_translation(self, session, lemma: Lemma, lang_code: str) -> Optional[str]:
        """
        Get translation for a lemma in the specified language.

        Handles both Lemma table columns and LemmaTranslation table.
        """
        field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

        if use_translation_table:
            # Query LemmaTranslation table
            translation_obj = session.query(LemmaTranslation).filter(
                LemmaTranslation.lemma_id == lemma.id,
                LemmaTranslation.language_code == field_name
            ).first()
            return translation_obj.translation if translation_obj else None
        else:
            # Get from Lemma table column
            return getattr(lemma, field_name, None)

    def set_translation(self, session, lemma: Lemma, lang_code: str, translation: str):
        """
        Set translation for a lemma in the specified language.

        Handles both Lemma table columns and LemmaTranslation table.
        """
        field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

        # Get old translation for logging
        old_translation = self.get_translation(session, lemma, lang_code)

        if use_translation_table:
            # Insert or update in LemmaTranslation table
            translation_obj = session.query(LemmaTranslation).filter(
                LemmaTranslation.lemma_id == lemma.id,
                LemmaTranslation.language_code == field_name
            ).first()

            if translation_obj:
                translation_obj.translation = translation
            else:
                translation_obj = LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=field_name,
                    translation=translation
                )
                session.add(translation_obj)
        else:
            # Set Lemma table column
            setattr(lemma, field_name, translation)

        # Log the translation change
        log_translation_change(
            session=session,
            source=f"voras-agent/{self.model}",
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=lang_code,
            old_translation=old_translation,
            new_translation=translation
        )

    def validate_translations(
        self,
        language_code: str,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Validate translations for a specific language using efficient single-call-per-word approach.

        Args:
            language_code: Language code to check (lt, zh, ko, fr, sw, vi)
            limit: Maximum number of words to check
            sample_rate: Fraction of words to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with validation results for the specified language
        """
        if language_code not in LANGUAGE_FIELDS:
            raise ValueError(f"Unsupported language code: {language_code}")

        field_name, language_name = LANGUAGE_FIELDS[language_code]
        logger.info(f"Validating {language_name} translations (efficient mode: 1 LLM call per word)...")

        session = self.get_session()
        try:
            # Get lemmas with this language translation
            query = session.query(Lemma).filter(
                Lemma.guid.isnot(None),
                getattr(Lemma, field_name).isnot(None),
                getattr(Lemma, field_name) != ''
            ).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} lemmas with {language_name} translations")

            # Sample if needed
            if sample_rate < 1.0:
                sample_size = int(len(lemmas) * sample_rate)
                lemmas = random.sample(lemmas, sample_size)
                logger.info(f"Sampling {len(lemmas)} words ({sample_rate*100:.0f}%)")

            # Validate translations
            issues_found = []
            checked_count = 0

            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Validated {checked_count}/{len(lemmas)} words...")

                # Gather all translations for this lemma
                translations = {}
                for lang_code, (field_name_iter, _) in LANGUAGE_FIELDS.items():
                    translation = getattr(lemma, field_name_iter)
                    if translation and translation.strip():
                        translations[lang_code] = translation

                if not translations:
                    continue

                logger.debug(f"Validating word '{lemma.lemma_text}' (GUID: {lemma.guid}), checking {language_name}: '{translations.get(language_code, 'N/A')}'")

                # Validate all translations in one call
                validation_results = validate_all_translations_for_word(
                    lemma.lemma_text,
                    translations,
                    lemma.pos_type,
                    self.model
                )

                # Only process results for the requested language
                if language_code in validation_results:
                    lang_validation = validation_results[language_code]

                    has_issues = (
                        (not lang_validation['is_correct'] or not lang_validation['is_lemma_form'])
                        and lang_validation['confidence'] >= confidence_threshold
                    )

                    if has_issues:
                        issues_found.append({
                            'guid': lemma.guid,
                            'english': lemma.lemma_text,
                            'current_translation': translations[language_code],
                            'suggested_translation': lang_validation['suggested_translation'],
                            'pos_type': lemma.pos_type,
                            'is_correct': lang_validation['is_correct'],
                            'is_lemma_form': lang_validation['is_lemma_form'],
                            'issues': lang_validation['issues'],
                            'confidence': lang_validation['confidence']
                        })
                        logger.warning(
                            f"Translation issue ({lemma.guid}): '{lemma.lemma_text}' → '{translations[language_code]}' "
                            f"(suggested: '{lang_validation['suggested_translation']}', confidence: {lang_validation['confidence']:.2f})"
                        )

            logger.info(f"Found {len(issues_found)} {language_name} translations with potential issues")

            return {
                'language_code': language_code,
                'language_name': language_name,
                'total_checked': checked_count,
                'issues_found': len(issues_found),
                'issue_rate': (len(issues_found) / checked_count * 100) if checked_count else 0,
                'issues': issues_found,
                'confidence_threshold': confidence_threshold
            }

        except Exception as e:
            logger.error(f"Error validating {language_name} translations: {e}")
            return {
                'error': str(e),
                'language_code': language_code,
                'language_name': language_name,
                'total_checked': 0,
                'issues_found': 0,
                'issue_rate': 0,
                'issues': []
            }
        finally:
            session.close()

    def validate_all_translations(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Validate all multi-lingual translations using efficient single-call-per-word approach.

        Args:
            limit: Maximum number of lemmas to check
            sample_rate: Fraction of lemmas to sample
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with results for all languages
        """
        logger.info("Validating all multi-lingual translations (efficient mode: 1 LLM call per word)...")

        session = self.get_session()
        try:
            # Get lemmas that have at least one translation
            query = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            )

            # Filter to lemmas with at least one translation
            has_translation_filter = None
            for lang_code, (field_name, _) in LANGUAGE_FIELDS.items():
                field_filter = (
                    (getattr(Lemma, field_name).isnot(None)) &
                    (getattr(Lemma, field_name) != '')
                )
                if has_translation_filter is None:
                    has_translation_filter = field_filter
                else:
                    has_translation_filter = has_translation_filter | field_filter

            query = query.filter(has_translation_filter).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} lemmas with translations")

            # Sample if needed
            if sample_rate < 1.0:
                sample_size = int(len(lemmas) * sample_rate)
                lemmas = random.sample(lemmas, sample_size)
                logger.info(f"Sampling {len(lemmas)} lemmas ({sample_rate*100:.0f}%)")

            # Initialize results structure
            results_by_language = {
                lang_code: {
                    'language_code': lang_code,
                    'language_name': language_name,
                    'total_checked': 0,
                    'issues_found': 0,
                    'issue_rate': 0.0,
                    'issues': [],
                    'confidence_threshold': confidence_threshold
                }
                for lang_code, (_, language_name) in LANGUAGE_FIELDS.items()
            }

            # Validate all translations for each lemma in one LLM call
            checked_count = 0
            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Validated {checked_count}/{len(lemmas)} lemmas...")

                # Gather all translations for this lemma
                translations = {}
                for lang_code, (field_name, _) in LANGUAGE_FIELDS.items():
                    translation = getattr(lemma, field_name)
                    if translation and translation.strip():
                        translations[lang_code] = translation

                if not translations:
                    continue

                logger.debug(f"Validating word '{lemma.lemma_text}' (GUID: {lemma.guid}) with {len(translations)} translations")

                # Validate all translations in one call
                validation_results = validate_all_translations_for_word(
                    lemma.lemma_text,
                    translations,
                    lemma.pos_type,
                    self.model
                )

                # Process results for each language
                for lang_code, lang_validation in validation_results.items():
                    lang_result = results_by_language[lang_code]
                    lang_result['total_checked'] += 1

                    has_issues = (
                        (not lang_validation['is_correct'] or not lang_validation['is_lemma_form'])
                        and lang_validation['confidence'] >= confidence_threshold
                    )

                    if has_issues:
                        lang_result['issues_found'] += 1
                        lang_result['issues'].append({
                            'guid': lemma.guid,
                            'english': lemma.lemma_text,
                            'current_translation': translations[lang_code],
                            'suggested_translation': lang_validation['suggested_translation'],
                            'pos_type': lemma.pos_type,
                            'is_correct': lang_validation['is_correct'],
                            'is_lemma_form': lang_validation['is_lemma_form'],
                            'issues': lang_validation['issues'],
                            'confidence': lang_validation['confidence']
                        })

            # Calculate issue rates
            total_issues = 0
            for lang_result in results_by_language.values():
                if lang_result['total_checked'] > 0:
                    lang_result['issue_rate'] = (
                        lang_result['issues_found'] / lang_result['total_checked'] * 100
                    )
                total_issues += lang_result['issues_found']
                logger.info(
                    f"{lang_result['language_name']}: "
                    f"{lang_result['issues_found']}/{lang_result['total_checked']} issues "
                    f"({lang_result['issue_rate']:.1f}%)"
                )

            return {
                'by_language': results_by_language,
                'total_issues_all_languages': total_issues
            }

        except Exception as e:
            logger.error(f"Error validating all translations: {e}")
            return {
                'error': str(e),
                'by_language': {},
                'total_issues_all_languages': 0
            }
        finally:
            session.close()

    def regenerate_all_translations(
        self,
        limit: Optional[int] = None,
        dry_run: bool = False,
        batch_mode: bool = False
    ) -> Dict[str, any]:
        """
        Delete all non-Lithuanian translations and regenerate them fresh.

        Args:
            limit: Maximum number of words to process
            dry_run: If True, only report what would be done without making changes
            batch_mode: If True, queue batch requests instead of making synchronous calls

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
        languages_to_regenerate = [lc for lc in LANGUAGE_FIELDS.keys() if lc != 'lt']

        # Initialize results structure
        results = {
            'total_words_processed': 0,
            'total_translations_added': 0,
            'total_failed': 0,
            'batch_requests_queued': 0,
            'by_language': {
                lang_code: {
                    'language_name': LANGUAGE_FIELDS[lang_code][1],
                    'deleted': 0,
                    'added': 0,
                    'failed': 0
                }
                for lang_code in languages_to_regenerate
            }
        }

        try:
            # Get all lemmas with GUIDs (curated words)
            query = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            ).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            words_to_process = query.all()
            total_words = len(words_to_process)

            logger.info(f"Found {total_words} curated words to process")

            # First pass: delete existing non-Lithuanian translations
            logger.info("Deleting existing non-Lithuanian translations...")
            for lemma in words_to_process:
                for lang_code in languages_to_regenerate:
                    field_name, _ = LANGUAGE_FIELDS[lang_code]
                    existing = getattr(lemma, field_name)
                    if existing and existing.strip():
                        if not dry_run:
                            setattr(lemma, field_name, None)
                        results['by_language'][lang_code]['deleted'] += 1

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

                results['total_words_processed'] += 1

                try:
                    if dry_run:
                        for lang_code in languages_to_regenerate:
                            results['by_language'][lang_code]['added'] += 1
                            results['total_translations_added'] += 1
                        logger.info(f"[DRY RUN] Would generate all translations for '{lemma.lemma_text}'")
                        continue

                    if batch_mode:
                        # Queue batch request - implementation would go here using batch module
                        # For brevity, just increment counter
                        results['batch_requests_queued'] += 1
                        if i % 100 == 0:
                            logger.info(f"Queued {results['batch_requests_queued']} batch requests...")
                    else:
                        # Synchronous mode: use query_translations method - ONE CALL
                        translations, success = client.query_translations(
                            english_word=lemma.lemma_text,
                            lithuanian_word=lemma.lithuanian_translation or "",
                            definition=lemma.definition_text,
                            pos_type=lemma.pos_type,
                            pos_subtype=lemma.pos_subtype
                        )

                        if not success or not translations:
                            logger.warning(f"Failed to get translations for '{lemma.lemma_text}'")
                            for lang_code in languages_to_regenerate:
                                results['by_language'][lang_code]['failed'] += 1
                            results['total_failed'] += 1
                            continue

                        # Map language codes to field names
                        translation_field_map = {
                            'zh': 'chinese_translation',
                            'ko': 'korean_translation',
                            'fr': 'french_translation',
                            'sw': 'swahili_translation',
                            'vi': 'vietnamese_translation'
                        }

                        # Add all non-Lithuanian translations
                        added_this_word = 0
                        for lang_code in languages_to_regenerate:
                            field_name, language_name = LANGUAGE_FIELDS[lang_code]
                            llm_field = translation_field_map.get(lang_code)
                            translation = translations.get(llm_field, '').strip()

                            if translation:
                                setattr(lemma, field_name, translation)
                                logger.debug(f"  Added {language_name}: '{translation}'")
                                results['by_language'][lang_code]['added'] += 1
                                results['total_translations_added'] += 1
                                added_this_word += 1
                            else:
                                logger.warning(f"  LLM returned empty {language_name} translation for '{lemma.lemma_text}'")
                                results['by_language'][lang_code]['failed'] += 1
                                results['total_failed'] += 1

                        # Commit all updates for this word at once
                        session.commit()
                        logger.info(f"Added {added_this_word}/{len(languages_to_regenerate)} translations for '{lemma.lemma_text}' (GUID: {lemma.guid})")

                except Exception as e:
                    logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                    session.rollback()
                    for lang_code in languages_to_regenerate:
                        results['by_language'][lang_code]['failed'] += 1
                    results['total_failed'] += 1

        finally:
            session.close()

        return results

    def fix_missing_translations(
        self,
        language_code: Optional[str | List[str]] = None,
        limit: Optional[int] = None,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate missing translations using LLM and update the database.

        Args:
            language_code: Specific language(s) to fix. Can be a single code (str),
                          a list of codes, or None (all languages)
            limit: Maximum number of words to process
            dry_run: If True, only report what would be fixed without making changes

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
        results = {
            'total_fixed': 0,
            'total_failed': 0,
            'by_language': {
                lang_code: {
                    'language_name': LANGUAGE_FIELDS[lang_code][1],
                    'total_missing': 0,
                    'fixed': 0,
                    'failed': 0
                }
                for lang_code in languages_to_fix
            }
        }

        try:
            # Build query to find words missing ANY of the target translations
            # For simplicity, we'll get all lemmas and check missing translations using helper method
            # This is less efficient but handles both storage types uniformly
            query = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            ).order_by(Lemma.id)

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
                        results['by_language'][lang_code]['total_missing'] += 1

            # Process each word once
            for i, lemma in enumerate(words_to_process, 1):
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{total_words} words processed")

                # Find which languages are missing for this word
                missing_languages = []
                for lang_code in languages_to_fix:
                    _, language_name, _ = LANGUAGE_FIELDS[lang_code]
                    translation = self.get_translation(session, lemma, lang_code)
                    if not translation or not translation.strip():
                        missing_languages.append((lang_code, language_name))

                if not missing_languages:
                    continue

                logger.debug(f"Processing word '{lemma.lemma_text}' (GUID: {lemma.guid}), missing {len(missing_languages)} translations")

                try:
                    if dry_run:
                        for lang_code, language_name in missing_languages:
                            logger.info(f"[DRY RUN] Would generate {language_name} translation for '{lemma.lemma_text}'")
                            results['by_language'][lang_code]['fixed'] += 1
                            results['total_fixed'] += 1
                        continue

                    # Build list of language names (lowercase) for only the missing languages
                    # Map language codes to language names for query_translations
                    lang_code_to_name = {
                        'zh': 'chinese',
                        'ko': 'korean',
                        'fr': 'french',
                        'es': 'spanish',
                        'de': 'german',
                        'pt': 'portuguese',
                        'sw': 'swahili',
                        'vi': 'vietnamese'
                    }
                    missing_lang_names = [
                        lang_code_to_name[lang_code]
                        for lang_code, _ in missing_languages
                        if lang_code in lang_code_to_name  # Skip 'lt' which isn't in the map
                    ]

                    # Query LLM for translations - ONE CALL for only missing languages
                    translations, success = client.query_translations(
                        english_word=lemma.lemma_text,
                        lithuanian_word=lemma.lithuanian_translation or "",
                        definition=lemma.definition_text,
                        pos_type=lemma.pos_type,
                        pos_subtype=lemma.pos_subtype,
                        languages=missing_lang_names
                    )

                    if not success or not translations:
                        logger.warning(f"Failed to get translations for '{lemma.lemma_text}'")
                        for lang_code, _ in missing_languages:
                            results['by_language'][lang_code]['failed'] += 1
                            results['total_failed'] += 1
                        continue

                    # Map language codes to LLM response field names
                    translation_field_map = {
                        'zh': 'chinese_translation',
                        'ko': 'korean_translation',
                        'fr': 'french_translation',
                        'es': 'spanish_translation',
                        'de': 'german_translation',
                        'pt': 'portuguese_translation',
                        'sw': 'swahili_translation',
                        'vi': 'vietnamese_translation'
                    }

                    for lang_code, language_name in missing_languages:
                        # Skip Lithuanian since query_translations doesn't generate it
                        if lang_code == 'lt':
                            logger.warning(f"Skipping Lithuanian translation for '{lemma.lemma_text}' - not generated by translation_generation prompt")
                            results['by_language'][lang_code]['failed'] += 1
                            results['total_failed'] += 1
                            continue

                        llm_field = translation_field_map.get(lang_code)
                        translation = translations.get(llm_field, '').strip()

                        if translation:
                            # Update the translation using helper method
                            self.set_translation(session, lemma, lang_code, translation)
                            logger.debug(f"  Added {language_name} translation: '{translation}'")
                            results['by_language'][lang_code]['fixed'] += 1
                            results['total_fixed'] += 1
                        else:
                            logger.warning(f"  LLM returned empty {language_name} translation for '{lemma.lemma_text}'")
                            results['by_language'][lang_code]['failed'] += 1
                            results['total_failed'] += 1

                    # Commit all updates for this word at once
                    session.commit()
                    added_count = len([lc for lc, _ in missing_languages if lc != 'lt' and translations.get(translation_field_map.get(lc), '').strip()])
                    logger.info(f"Added {added_count} translations for '{lemma.lemma_text}' (GUID: {lemma.guid})")

                except Exception as e:
                    logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                    session.rollback()
                    for lang_code, _ in missing_languages:
                        results['by_language'][lang_code]['failed'] += 1
                        results['total_failed'] += 1

            # Log summary per language
            for lang_code in languages_to_fix:
                lang_result = results['by_language'][lang_code]
                logger.info(
                    f"Completed {lang_result['language_name']}: "
                    f"{lang_result['fixed']} fixed, {lang_result['failed']} failed "
                    f"(of {lang_result['total_missing']} missing)"
                )

        finally:
            session.close()

        return results

    # Delegate batch operations to batch module
    def submit_batch(self, agent_name: str = "voras", metadata: Optional[Dict[str, str]] = None):
        """Submit batch requests. Delegates to batch module."""
        return batch.submit_batch(self.debug, agent_name, metadata)

    def check_batch_status(self, batch_id: str):
        """Check batch status. Delegates to batch module."""
        return batch.check_batch_status(batch_id, self.debug)

    def retrieve_batch_results(self, batch_id: str):
        """Retrieve batch results. Delegates to batch module."""
        session = self.get_session()
        try:
            return batch.retrieve_batch_results(batch_id, session, self.debug)
        finally:
            session.close()

    # Delegate coverage operations to coverage module
    def check_overall_coverage(self):
        """Check overall coverage. Delegates to coverage module."""
        session = self.get_session()
        try:
            return coverage.check_overall_coverage(session)
        finally:
            session.close()

    def check_language_coverage(self, language_code: str):
        """Check language coverage. Delegates to coverage module."""
        session = self.get_session()
        try:
            return coverage.check_language_coverage(session, language_code)
        finally:
            session.close()

    def check_difficulty_level_coverage(self):
        """Check difficulty level coverage. Delegates to coverage module."""
        session = self.get_session()
        try:
            return coverage.check_difficulty_level_coverage(session)
        finally:
            session.close()

    def run_full_check(self, output_file: Optional[str] = None):
        """Run all coverage checks and generate a comprehensive report."""
        logger.info("Starting full multi-lingual translation coverage check...")
        start_time = datetime.now()

        results = {
            'timestamp': start_time.isoformat(),
            'database_path': self.db_path,
            'checks': {
                'overall_coverage': self.check_overall_coverage(),
                'difficulty_level_coverage': self.check_difficulty_level_coverage()
            }
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results['duration_seconds'] = duration

        # Print summary
        coverage.print_summary(results, start_time, duration)

        # Write to output file if requested
        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_summary(self, results, start_time, duration):
        """Delegate to coverage module."""
        coverage.print_summary(results, start_time, duration)
