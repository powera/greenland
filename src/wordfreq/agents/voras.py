#!/usr/bin/env python3
"""
Voras - Multi-lingual Translation Validator and Populator

This agent runs autonomously to:
1. Validate multi-lingual translations for correctness and proper lemma form
2. Report on translation coverage across all languages
3. Generate missing translations using LLM

Modes:
- check-only: Validate existing translations without populating missing ones
- populate-only: Add missing translations without validating existing ones
- both: Validate existing translations AND populate missing ones

"Voras" means "spider" in Lithuanian - weaving together the web of translations!
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma
from wordfreq.translation.client import LinguisticClient
from wordfreq.tools.llm_validators import (
    validate_translation,
    validate_all_translations_for_word,
    batch_validate_translations
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Language mappings
LANGUAGE_FIELDS = {
    'lt': ('lithuanian_translation', 'Lithuanian'),
    'zh': ('chinese_translation', 'Chinese'),
    'ko': ('korean_translation', 'Korean'),
    'fr': ('french_translation', 'French'),
    'sw': ('swahili_translation', 'Swahili'),
    'vi': ('vietnamese_translation', 'Vietnamese')
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

    def validate_translations(
        self,
        language_code: str,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Validate translations for a specific language using efficient single-call-per-word approach.
        Note: This validates ALL translations for each word, but only reports on the specified language.

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
                import random
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

                # Gather all translations for this lemma (efficient: validate all at once)
                translations = {}
                for lang_code, (field_name_iter, _) in LANGUAGE_FIELDS.items():
                    translation = getattr(lemma, field_name_iter)
                    if translation and translation.strip():
                        translations[lang_code] = translation

                if not translations:
                    continue  # Skip if no translations

                # Log which word is being validated
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
                        logger.debug(f"  Issue found: '{translations[language_code]}' → '{lang_validation['suggested_translation']}' (confidence: {lang_validation['confidence']:.2f})")
                        logger.warning(
                            f"Translation issue ({lemma.guid}): '{lemma.lemma_text}' → '{translations[language_code]}' "
                            f"(suggested: '{lang_validation['suggested_translation']}', confidence: {lang_validation['confidence']:.2f})"
                        )
                    else:
                        logger.debug(f"  No issues found for '{lemma.lemma_text}'")

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
                import random
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
                    continue  # Skip if no translations

                # Log which word is being validated
                logger.debug(f"Validating word '{lemma.lemma_text}' (GUID: {lemma.guid}) with {len(translations)} translations")

                # Validate all translations in one call
                validation_results = validate_all_translations_for_word(
                    lemma.lemma_text,
                    translations,
                    lemma.pos_type,
                    self.model
                )

                # Process results for each language
                issues_for_this_word = []
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
                        issues_for_this_word.append(f"{lang_code}: {translations[lang_code]} → {lang_validation['suggested_translation']}")

                # Log issues found for this word
                if issues_for_this_word:
                    logger.debug(f"  Issues found for '{lemma.lemma_text}': {', '.join(issues_for_this_word)}")
                else:
                    logger.debug(f"  No issues found for '{lemma.lemma_text}'")

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

    def fix_missing_translations(
        self,
        language_code: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate missing translations using LLM and update the database.
        Uses efficient batching: 1 LLM call per word for all missing translations.

        Args:
            language_code: Specific language to fix (None = all languages)
            limit: Maximum number of words to process
            dry_run: If True, only report what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        logger.info("Starting translation generation (efficient mode: 1 LLM call per word)...")

        session = self.get_session()
        client = self.get_linguistic_client()

        languages_to_fix = [language_code] if language_code else list(LANGUAGE_FIELDS.keys())

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
            missing_filter = None
            for lang_code in languages_to_fix:
                field_name, _ = LANGUAGE_FIELDS[lang_code]
                lang_filter = (
                    (getattr(Lemma, field_name).is_(None)) |
                    (getattr(Lemma, field_name) == '')
                )
                if missing_filter is None:
                    missing_filter = lang_filter
                else:
                    missing_filter = missing_filter | lang_filter

            query = session.query(Lemma).filter(
                Lemma.guid.isnot(None),
                missing_filter
            ).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            words_to_process = query.all()
            total_words = len(words_to_process)

            logger.info(f"Found {total_words} words with missing translations in target languages")

            # Count missing translations per language
            for lemma in words_to_process:
                for lang_code in languages_to_fix:
                    field_name, _ = LANGUAGE_FIELDS[lang_code]
                    translation = getattr(lemma, field_name)
                    if not translation or not translation.strip():
                        results['by_language'][lang_code]['total_missing'] += 1

            # Process each word once
            for i, lemma in enumerate(words_to_process, 1):
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{total_words} words processed")

                # Find which languages are missing for this word
                missing_languages = []
                for lang_code in languages_to_fix:
                    field_name, language_name = LANGUAGE_FIELDS[lang_code]
                    translation = getattr(lemma, field_name)
                    if not translation or not translation.strip():
                        missing_languages.append((lang_code, field_name, language_name))

                if not missing_languages:
                    continue

                logger.debug(f"Processing word '{lemma.lemma_text}' (GUID: {lemma.guid}), missing {len(missing_languages)} translations")

                try:
                    if dry_run:
                        for lang_code, _, language_name in missing_languages:
                            logger.info(f"[DRY RUN] Would generate {language_name} translation for '{lemma.lemma_text}'")
                            results['by_language'][lang_code]['fixed'] += 1
                            results['total_fixed'] += 1
                        continue

                    # Query LLM for full definition data (includes all translations) - ONE CALL
                    definitions, success = client.query_definitions(lemma.lemma_text)

                    if not success or not definitions:
                        logger.warning(f"Failed to get definitions for '{lemma.lemma_text}'")
                        for lang_code, _, _ in missing_languages:
                            results['by_language'][lang_code]['failed'] += 1
                            results['total_failed'] += 1
                        continue

                    # Find the matching definition (by POS and definition text similarity)
                    matching_def = None
                    for def_data in definitions:
                        if def_data.get('pos') == lemma.pos_type:
                            matching_def = def_data
                            break

                    # If no POS match, use the first definition
                    if not matching_def and definitions:
                        matching_def = definitions[0]

                    # Update all missing translations for this word
                    # Map language codes to the field names used by LinguisticClient
                    translation_field_map = {
                        'lt': 'lithuanian_translation',
                        'zh': 'chinese_translation',
                        'ko': 'korean_translation',
                        'fr': 'french_translation',
                        'sw': 'swahili_translation',
                        'vi': 'vietnamese_translation'
                    }

                    for lang_code, field_name, language_name in missing_languages:
                        llm_field = translation_field_map.get(lang_code)
                        translation = matching_def.get(llm_field, '').strip()

                        if translation:
                            # Update the lemma with the new translation
                            setattr(lemma, field_name, translation)
                            logger.debug(f"  Added {language_name} translation: '{translation}'")
                            results['by_language'][lang_code]['fixed'] += 1
                            results['total_fixed'] += 1
                        else:
                            logger.warning(f"  LLM returned empty {language_name} translation for '{lemma.lemma_text}'")
                            results['by_language'][lang_code]['failed'] += 1
                            results['total_failed'] += 1

                    # Commit all updates for this word at once
                    session.commit()
                    added_count = len([lc for lc, _, _ in missing_languages if matching_def.get(translation_field_map.get(lc), '').strip()])
                    logger.info(f"Added {added_count} translations for '{lemma.lemma_text}' (GUID: {lemma.guid})")

                except Exception as e:
                    logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                    session.rollback()
                    for lang_code, _, _ in missing_languages:
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

    def check_overall_coverage(self) -> Dict[str, any]:
        """
        Check overall translation coverage across all languages.

        Returns:
            Dictionary with overall coverage statistics
        """
        logger.info("Checking overall translation coverage...")

        session = self.get_session()
        try:
            # Get all lemmas with GUIDs (curated words)
            all_lemmas = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            ).all()

            total_lemmas = len(all_lemmas)
            logger.info(f"Found {total_lemmas} curated lemmas")

            # Calculate coverage for each language
            language_coverage = {}
            for lang_code, (field_name, language_name) in LANGUAGE_FIELDS.items():
                with_translation = 0
                without_translation = []

                for lemma in all_lemmas:
                    translation = getattr(lemma, field_name)
                    if translation and translation.strip():
                        with_translation += 1
                    else:
                        without_translation.append({
                            'guid': lemma.guid,
                            'lemma_text': lemma.lemma_text,
                            'pos_type': lemma.pos_type,
                            'pos_subtype': lemma.pos_subtype,
                            'difficulty_level': lemma.difficulty_level
                        })

                coverage_percentage = (with_translation / total_lemmas * 100) if total_lemmas else 0

                language_coverage[lang_code] = {
                    'language_name': language_name,
                    'total_lemmas': total_lemmas,
                    'with_translation': with_translation,
                    'without_translation': len(without_translation),
                    'coverage_percentage': coverage_percentage,
                    'missing_translations': without_translation
                }

                logger.info(f"{language_name}: {with_translation}/{total_lemmas} ({coverage_percentage:.1f}%)")

            # Find lemmas with complete translation coverage (all languages)
            fully_translated = []
            partially_translated = []
            not_translated = []

            for lemma in all_lemmas:
                translation_count = 0
                missing_languages = []

                for lang_code, (field_name, language_name) in LANGUAGE_FIELDS.items():
                    translation = getattr(lemma, field_name)
                    if translation and translation.strip():
                        translation_count += 1
                    else:
                        missing_languages.append(language_name)

                if translation_count == len(LANGUAGE_FIELDS):
                    fully_translated.append(lemma.guid)
                elif translation_count == 0:
                    not_translated.append({
                        'guid': lemma.guid,
                        'lemma_text': lemma.lemma_text,
                        'pos_type': lemma.pos_type,
                        'difficulty_level': lemma.difficulty_level
                    })
                else:
                    partially_translated.append({
                        'guid': lemma.guid,
                        'lemma_text': lemma.lemma_text,
                        'pos_type': lemma.pos_type,
                        'difficulty_level': lemma.difficulty_level,
                        'translation_count': translation_count,
                        'missing_languages': missing_languages
                    })

            return {
                'total_lemmas': total_lemmas,
                'language_coverage': language_coverage,
                'fully_translated_count': len(fully_translated),
                'partially_translated_count': len(partially_translated),
                'not_translated_count': len(not_translated),
                'fully_translated_guids': fully_translated,
                'partially_translated': partially_translated,
                'not_translated': not_translated
            }

        except Exception as e:
            logger.error(f"Error checking overall coverage: {e}")
            return {
                'error': str(e),
                'total_lemmas': 0,
                'language_coverage': {},
                'fully_translated_count': 0,
                'partially_translated_count': 0,
                'not_translated_count': 0
            }
        finally:
            session.close()

    def check_language_coverage(self, language_code: str) -> Dict[str, any]:
        """
        Check translation coverage for a specific language.

        Args:
            language_code: Language code to check (lt, zh, ko, fr, sw, vi)

        Returns:
            Dictionary with language-specific coverage details
        """
        if language_code not in LANGUAGE_FIELDS:
            raise ValueError(f"Unsupported language code: {language_code}")

        field_name, language_name = LANGUAGE_FIELDS[language_code]
        logger.info(f"Checking {language_name} translation coverage...")

        session = self.get_session()
        try:
            # Get all lemmas with GUIDs
            all_lemmas = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            ).all()

            total_lemmas = len(all_lemmas)

            # Categorize by POS type
            coverage_by_pos = {}
            missing_by_pos = {}

            for lemma in all_lemmas:
                pos_type = lemma.pos_type or 'unknown'

                if pos_type not in coverage_by_pos:
                    coverage_by_pos[pos_type] = {'total': 0, 'with_translation': 0}
                    missing_by_pos[pos_type] = []

                coverage_by_pos[pos_type]['total'] += 1

                translation = getattr(lemma, field_name)
                if translation and translation.strip():
                    coverage_by_pos[pos_type]['with_translation'] += 1
                else:
                    missing_by_pos[pos_type].append({
                        'guid': lemma.guid,
                        'lemma_text': lemma.lemma_text,
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level
                    })

            # Calculate percentages
            pos_statistics = {}
            for pos_type, stats in coverage_by_pos.items():
                percentage = (stats['with_translation'] / stats['total'] * 100) if stats['total'] else 0
                pos_statistics[pos_type] = {
                    'total': stats['total'],
                    'with_translation': stats['with_translation'],
                    'without_translation': stats['total'] - stats['with_translation'],
                    'coverage_percentage': percentage,
                    'missing': missing_by_pos[pos_type]
                }

            # Overall stats
            total_with_translation = sum(stats['with_translation'] for stats in coverage_by_pos.values())
            overall_percentage = (total_with_translation / total_lemmas * 100) if total_lemmas else 0

            return {
                'language_code': language_code,
                'language_name': language_name,
                'total_lemmas': total_lemmas,
                'with_translation': total_with_translation,
                'without_translation': total_lemmas - total_with_translation,
                'coverage_percentage': overall_percentage,
                'coverage_by_pos': pos_statistics
            }

        except Exception as e:
            logger.error(f"Error checking {language_name} coverage: {e}")
            return {
                'error': str(e),
                'language_code': language_code,
                'language_name': language_name,
                'total_lemmas': 0,
                'with_translation': 0,
                'without_translation': 0,
                'coverage_percentage': 0,
                'coverage_by_pos': {}
            }
        finally:
            session.close()

    def check_difficulty_level_coverage(self) -> Dict[str, any]:
        """
        Check translation coverage across difficulty levels.

        Returns:
            Dictionary with coverage by difficulty level
        """
        logger.info("Checking translation coverage by difficulty level...")

        session = self.get_session()
        try:
            # Get all lemmas with GUIDs and difficulty levels
            all_lemmas = session.query(Lemma).filter(
                Lemma.guid.isnot(None),
                Lemma.difficulty_level.isnot(None)
            ).all()

            logger.info(f"Found {len(all_lemmas)} lemmas with difficulty levels")

            # Organize by difficulty level
            coverage_by_level = {}

            for lemma in all_lemmas:
                level = lemma.difficulty_level

                if level not in coverage_by_level:
                    coverage_by_level[level] = {
                        'total': 0,
                        'language_coverage': {lang: 0 for lang in LANGUAGE_FIELDS.keys()}
                    }

                coverage_by_level[level]['total'] += 1

                for lang_code, (field_name, _) in LANGUAGE_FIELDS.items():
                    translation = getattr(lemma, field_name)
                    if translation and translation.strip():
                        coverage_by_level[level]['language_coverage'][lang_code] += 1

            # Calculate percentages
            level_statistics = {}
            for level in sorted(coverage_by_level.keys()):
                stats = coverage_by_level[level]
                total = stats['total']

                language_percentages = {}
                for lang_code, count in stats['language_coverage'].items():
                    language_percentages[lang_code] = (count / total * 100) if total else 0

                level_statistics[level] = {
                    'total_lemmas': total,
                    'language_coverage': stats['language_coverage'],
                    'language_percentages': language_percentages
                }

            return {
                'total_levels': len(coverage_by_level),
                'coverage_by_level': level_statistics
            }

        except Exception as e:
            logger.error(f"Error checking difficulty level coverage: {e}")
            return {
                'error': str(e),
                'total_levels': 0,
                'coverage_by_level': {}
            }
        finally:
            session.close()

    def run_full_check(self, output_file: Optional[str] = None) -> Dict[str, any]:
        """
        Run all coverage checks and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report

        Returns:
            Dictionary with all check results
        """
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
        self._print_summary(results, start_time, duration)

        # Write to output file if requested
        if output_file:
            import json
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_summary(self, results: Dict, start_time: datetime, duration: float):
        """Print a summary of the check results."""
        logger.info("=" * 80)
        logger.info("VORAS AGENT REPORT - Multi-lingual Translation Coverage")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Overall coverage
        if 'overall_coverage' in results['checks']:
            overall = results['checks']['overall_coverage']
            logger.info(f"OVERALL COVERAGE:")
            logger.info(f"  Total curated lemmas: {overall['total_lemmas']}")
            logger.info(f"  Fully translated (all languages): {overall['fully_translated_count']} ({overall['fully_translated_count']/overall['total_lemmas']*100 if overall['total_lemmas'] else 0:.1f}%)")
            logger.info(f"  Partially translated: {overall['partially_translated_count']} ({overall['partially_translated_count']/overall['total_lemmas']*100 if overall['total_lemmas'] else 0:.1f}%)")
            logger.info(f"  Not translated: {overall['not_translated_count']} ({overall['not_translated_count']/overall['total_lemmas']*100 if overall['total_lemmas'] else 0:.1f}%)")
            logger.info("")

            logger.info(f"COVERAGE BY LANGUAGE:")
            for lang_code, lang_data in overall['language_coverage'].items():
                logger.info(f"  {lang_data['language_name']} ({lang_code}):")
                logger.info(f"    Translated: {lang_data['with_translation']}/{lang_data['total_lemmas']} ({lang_data['coverage_percentage']:.1f}%)")
                logger.info(f"    Missing: {lang_data['without_translation']}")
            logger.info("")

        # Difficulty level coverage
        if 'difficulty_level_coverage' in results['checks']:
            level_data = results['checks']['difficulty_level_coverage']
            logger.info(f"COVERAGE BY DIFFICULTY LEVEL:")
            logger.info(f"  Total levels with data: {level_data['total_levels']}")

            if level_data['coverage_by_level']:
                logger.info(f"  Sample (first 5 levels):")
                for level in sorted(level_data['coverage_by_level'].keys())[:5]:
                    stats = level_data['coverage_by_level'][level]
                    logger.info(f"    Level {level} ({stats['total_lemmas']} words):")
                    for lang_code, percentage in stats['language_percentages'].items():
                        lang_name = LANGUAGE_FIELDS[lang_code][1]
                        logger.info(f"      {lang_name}: {percentage:.1f}%")

        logger.info("=" * 80)


def main():
    """Main entry point for the voras agent."""
    parser = argparse.ArgumentParser(
        description="Voras - Multi-lingual Translation Validator and Populator"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--mode',
                       choices=['check-only', 'populate-only', 'both', 'coverage'],
                       default='coverage',
                       help='Operation mode: check-only (validate existing), populate-only (add missing), both (validate + populate), coverage (report only, default)')
    parser.add_argument('--language',
                       choices=list(LANGUAGE_FIELDS.keys()),
                       help='Specific language to process (lt, zh, ko, fr, sw, vi)')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompt before running LLM queries')
    parser.add_argument('--model', default='gpt-5-mini',
                       help='LLM model to use (default: gpt-5-mini)')
    parser.add_argument('--limit', type=int,
                       help='Maximum items to process per language')
    parser.add_argument('--sample-rate', type=float, default=1.0,
                       help='Fraction of items to sample for validation (0.0-1.0, default: 1.0)')
    parser.add_argument('--confidence-threshold', type=float, default=0.7,
                       help='Minimum confidence to flag issues (0.0-1.0, default: 0.7)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')

    args = parser.parse_args()

    # Create agent with model parameter
    agent = VorasAgent(db_path=args.db_path, debug=args.debug, model=args.model)

    # Handle different modes
    if args.mode == 'coverage':
        # Coverage reporting mode (no LLM calls)
        agent.run_full_check(output_file=args.output)
        return

    # For modes requiring LLM, confirm before running (unless --yes was provided)
    if not args.yes and not args.dry_run:
        session = agent.get_session()
        try:
            estimated_calls = 0
            languages_to_process = [args.language] if args.language else list(LANGUAGE_FIELDS.keys())

            if args.mode in ['check-only', 'both']:
                # Calculate validation calls
                if args.language:
                    # Single language: still validates all languages per word, just filters which words
                    field_name, language_name = LANGUAGE_FIELDS[args.language]
                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        getattr(Lemma, field_name).isnot(None),
                        getattr(Lemma, field_name) != ''
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    logger.info(f"{language_name}: {count} words to validate (all translations per word)")
                else:
                    # All languages: one call per word with any translation
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

                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        has_translation_filter
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    logger.info(f"All languages: {count} words to validate (all translations per word)")

            if args.mode in ['populate-only', 'both']:
                # Calculate population calls - one call per word with any missing translation
                missing_filter = None
                for lang_code in languages_to_process:
                    field_name, language_name = LANGUAGE_FIELDS[lang_code]
                    lang_filter = (
                        (getattr(Lemma, field_name).is_(None)) |
                        (getattr(Lemma, field_name) == '')
                    )
                    if missing_filter is None:
                        missing_filter = lang_filter
                    else:
                        missing_filter = missing_filter | lang_filter

                query = session.query(Lemma).filter(
                    Lemma.guid.isnot(None),
                    missing_filter
                )
                if args.limit:
                    query = query.limit(args.limit)

                words_to_populate = query.all()
                count = len(words_to_populate)
                estimated_calls += count

                # Count missing per language for reporting
                for lang_code in languages_to_process:
                    field_name, language_name = LANGUAGE_FIELDS[lang_code]
                    missing_count = sum(
                        1 for lemma in words_to_populate
                        if not getattr(lemma, field_name) or not getattr(lemma, field_name).strip()
                    )
                    logger.info(f"{language_name}: {missing_count} missing translations to populate")

                logger.info(f"Total: {count} words to populate (1 LLM call per word for all missing translations)")

        finally:
            session.close()

        print(f"\nThis will make approximately {estimated_calls} LLM API calls using model '{args.model}'.")
        print("This may incur costs and take some time to complete.")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()

        if response not in ['y', 'yes']:
            print("Aborted.")
            sys.exit(0)

        print()  # Extra newline for readability

    # Execute the requested mode
    results = {}

    if args.mode == 'check-only':
        # Validate existing translations
        if args.language:
            results = agent.validate_translations(
                args.language,
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
            print(f"\n{results['language_name']} validation results:")
            print(f"  Issues found: {results['issues_found']} out of {results['total_checked']}")
            print(f"  Issue rate: {results['issue_rate']:.1f}%")
        else:
            results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
            print(f"\nTotal translation issues (all languages): {results['total_issues_all_languages']}")

    elif args.mode == 'populate-only':
        # Generate missing translations only
        results = agent.fix_missing_translations(
            language_code=args.language,
            limit=args.limit,
            dry_run=args.dry_run
        )
        print("\n" + "=" * 80)
        print("TRANSLATION POPULATION SUMMARY")
        print("=" * 80)
        for lang_code, lang_results in results['by_language'].items():
            print(f"\n{lang_results['language_name']}:")
            print(f"  Total missing: {lang_results['total_missing']}")
            print(f"  Populated: {lang_results['fixed']}")
            print(f"  Failed: {lang_results['failed']}")
        print(f"\nTotal populated: {results['total_fixed']}")
        print(f"Total failed: {results['total_failed']}")
        print("=" * 80)

    elif args.mode == 'both':
        # First validate existing translations
        print("\n=== STEP 1: Validating Existing Translations ===\n")
        if args.language:
            validation_results = agent.validate_translations(
                args.language,
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
        else:
            validation_results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )

        # Then populate missing translations
        print("\n=== STEP 2: Populating Missing Translations ===\n")
        population_results = agent.fix_missing_translations(
            language_code=args.language,
            limit=args.limit,
            dry_run=args.dry_run
        )

        # Combined summary
        print("\n" + "=" * 80)
        print("COMBINED VALIDATION + POPULATION SUMMARY")
        print("=" * 80)

        if args.language:
            print(f"\nValidation ({validation_results['language_name']}):")
            print(f"  Issues found: {validation_results['issues_found']} out of {validation_results['total_checked']}")
            print(f"  Issue rate: {validation_results['issue_rate']:.1f}%")
        else:
            print(f"\nValidation (all languages):")
            print(f"  Total issues: {validation_results['total_issues_all_languages']}")

        print(f"\nPopulation:")
        for lang_code, lang_results in population_results['by_language'].items():
            print(f"  {lang_results['language_name']}: {lang_results['fixed']} populated, {lang_results['failed']} failed")
        print("=" * 80)


if __name__ == '__main__':
    main()
