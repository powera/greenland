"""
Voras Agent - Coverage Reporting

This module handles translation coverage reporting across languages.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from wordfreq.storage.models.schema import Lemma

logger = logging.getLogger(__name__)

# Language mappings
LANGUAGE_FIELDS = {
    'lt': ('lithuanian_translation', 'Lithuanian'),
    'zh': ('chinese_translation', 'Chinese'),
    'ko': ('korean_translation', 'Korean'),
    'fr': ('french_translation', 'French'),
    'es': ('spanish_translation', 'Spanish'),
    'de': ('german_translation', 'German'),
    'pt': ('portuguese_translation', 'Portuguese'),
    'sw': ('swahili_translation', 'Swahili'),
    'vi': ('vietnamese_translation', 'Vietnamese')
}


def check_overall_coverage(session) -> Dict[str, any]:
    """
    Check overall translation coverage across all languages.

    Args:
        session: Database session

    Returns:
        Dictionary with overall coverage statistics
    """
    logger.info("Checking overall translation coverage...")

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


def check_language_coverage(session, language_code: str) -> Dict[str, any]:
    """
    Check translation coverage for a specific language.

    Args:
        session: Database session
        language_code: Language code to check (lt, zh, ko, fr, sw, vi)

    Returns:
        Dictionary with language-specific coverage details
    """
    if language_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {language_code}")

    field_name, language_name = LANGUAGE_FIELDS[language_code]
    logger.info(f"Checking {language_name} translation coverage...")

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


def check_difficulty_level_coverage(session) -> Dict[str, any]:
    """
    Check translation coverage across difficulty levels.

    Args:
        session: Database session

    Returns:
        Dictionary with coverage by difficulty level
    """
    logger.info("Checking translation coverage by difficulty level...")

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


def print_summary(results: Dict, start_time: datetime, duration: float):
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
