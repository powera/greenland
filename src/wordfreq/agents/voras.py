#!/usr/bin/env python3
"""
Voras - Multi-lingual Translation Coverage Reporter

This agent runs autonomously to report on the coverage of multi-lingual
translations across all languages in the database. It identifies gaps,
calculates statistics, and provides insights into translation completeness.

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
    """Agent for reporting multi-lingual translation coverage."""

    def __init__(self, db_path: str = None, debug: bool = False, model: str = None):
        """
        Initialize the Voras agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            model: LLM model to use for generating translations (default: from constants)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.model = model or constants.DEFAULT_MODEL
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

    def fix_missing_translations(
        self,
        language_code: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate missing translations using LLM and update the database.

        Args:
            language_code: Specific language to fix (None = all languages)
            limit: Maximum number of translations to generate per language
            dry_run: If True, only report what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        logger.info("Starting translation generation...")

        session = self.get_session()
        client = self.get_linguistic_client()

        languages_to_fix = [language_code] if language_code else list(LANGUAGE_FIELDS.keys())

        results = {
            'total_fixed': 0,
            'total_failed': 0,
            'by_language': {}
        }

        try:
            for lang_code in languages_to_fix:
                field_name, language_name = LANGUAGE_FIELDS[lang_code]
                logger.info(f"Processing {language_name} translations...")

                # Get lemmas missing this translation
                query = session.query(Lemma).filter(
                    Lemma.guid.isnot(None),
                    (getattr(Lemma, field_name).is_(None)) |
                    (getattr(Lemma, field_name) == '')
                )

                if limit:
                    query = query.limit(limit)

                missing_lemmas = query.all()
                total_missing = len(missing_lemmas)

                logger.info(f"Found {total_missing} lemmas missing {language_name} translations")

                fixed = 0
                failed = 0

                for i, lemma in enumerate(missing_lemmas, 1):
                    if i % 10 == 0:
                        logger.info(f"Progress: {i}/{total_missing} ({language_name})")

                    try:
                        if dry_run:
                            logger.info(f"[DRY RUN] Would generate {language_name} translation for '{lemma.lemma_text}'")
                            fixed += 1
                            continue

                        # Query LLM for full definition data (includes all translations)
                        definitions, success = client.query_definitions(lemma.lemma_text)

                        if not success or not definitions:
                            logger.warning(f"Failed to get definitions for '{lemma.lemma_text}'")
                            failed += 1
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

                        # Extract the translation for the target language
                        translation_field = f"{lang_code}_translation"
                        translation = matching_def.get(translation_field, '').strip()

                        if translation:
                            # Update the lemma with the new translation
                            setattr(lemma, field_name, translation)
                            session.commit()

                            logger.info(f"Added {language_name} translation '{translation}' for '{lemma.lemma_text}' (GUID: {lemma.guid})")
                            fixed += 1
                        else:
                            logger.warning(f"LLM returned empty {language_name} translation for '{lemma.lemma_text}'")
                            failed += 1

                    except Exception as e:
                        logger.error(f"Error processing '{lemma.lemma_text}': {e}")
                        session.rollback()
                        failed += 1

                results['by_language'][lang_code] = {
                    'language_name': language_name,
                    'total_missing': total_missing,
                    'fixed': fixed,
                    'failed': failed
                }
                results['total_fixed'] += fixed
                results['total_failed'] += failed

                logger.info(f"Completed {language_name}: {fixed} fixed, {failed} failed")

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
        description="Voras - Multi-lingual Translation Coverage Reporter"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--check',
                       choices=['overall', 'language', 'difficulty', 'all'],
                       default='all',
                       help='Which check to run (default: all)')
    parser.add_argument('--language',
                       choices=list(LANGUAGE_FIELDS.keys()),
                       help='Specific language to check (for language check)')
    parser.add_argument('--fix', action='store_true',
                       help='Generate missing translations using LLM')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompt before running LLM queries')
    parser.add_argument('--model', default=constants.DEFAULT_MODEL,
                       help=f'LLM model to use for translations (default: {constants.DEFAULT_MODEL})')
    parser.add_argument('--limit', type=int,
                       help='Maximum translations to generate per language (for --fix)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be fixed without making changes (for --fix)')

    args = parser.parse_args()

    # Handle --fix mode with confirmation
    if args.fix:
        # Create agent with model parameter
        agent = VorasAgent(db_path=args.db_path, debug=args.debug, model=args.model)

        # Confirm before running LLM queries (unless --yes was provided)
        if not args.yes and not args.dry_run:
            # Calculate estimated number of LLM calls
            session = agent.get_session()
            try:
                estimated_calls = 0
                languages_to_fix = [args.language] if args.language else list(LANGUAGE_FIELDS.keys())

                for lang_code in languages_to_fix:
                    field_name, language_name = LANGUAGE_FIELDS[lang_code]
                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        (getattr(Lemma, field_name).is_(None)) |
                        (getattr(Lemma, field_name) == '')
                    )
                    if args.limit:
                        query = query.limit(args.limit)

                    count = query.count()
                    estimated_calls += count
                    logger.info(f"{language_name}: {count} missing translations")

            finally:
                session.close()

            print(f"\nThis will make approximately {estimated_calls} LLM API calls using model '{args.model}'.")
            print("This may incur costs and take some time to complete.")
            response = input("Do you want to proceed? [y/N]: ").strip().lower()

            if response not in ['y', 'yes']:
                print("Aborted.")
                sys.exit(0)

            print()  # Extra newline for readability

        # Run the fix
        results = agent.fix_missing_translations(
            language_code=args.language,
            limit=args.limit,
            dry_run=args.dry_run
        )

        # Print summary
        print("\n" + "=" * 80)
        print("TRANSLATION GENERATION SUMMARY")
        print("=" * 80)
        for lang_code, lang_results in results['by_language'].items():
            print(f"\n{lang_results['language_name']}:")
            print(f"  Total missing: {lang_results['total_missing']}")
            print(f"  Fixed: {lang_results['fixed']}")
            print(f"  Failed: {lang_results['failed']}")

        print(f"\nTotal fixed: {results['total_fixed']}")
        print(f"Total failed: {results['total_failed']}")
        print("=" * 80)

        return

    # Normal reporting mode (no --fix)
    agent = VorasAgent(db_path=args.db_path, debug=args.debug)

    if args.check == 'overall':
        results = agent.check_overall_coverage()
        print(f"\nOverall translation coverage:")
        print(f"  Fully translated: {results['fully_translated_count']}/{results['total_lemmas']}")
        print(f"  Partially translated: {results['partially_translated_count']}/{results['total_lemmas']}")
        print(f"  Not translated: {results['not_translated_count']}/{results['total_lemmas']}")

    elif args.check == 'language':
        if not args.language:
            print("Error: --language is required for language-specific checks")
            sys.exit(1)

        results = agent.check_language_coverage(args.language)
        print(f"\n{results['language_name']} translation coverage:")
        print(f"  Translated: {results['with_translation']}/{results['total_lemmas']} ({results['coverage_percentage']:.1f}%)")
        print(f"\nCoverage by POS type:")
        for pos_type, stats in results['coverage_by_pos'].items():
            print(f"  {pos_type}: {stats['with_translation']}/{stats['total']} ({stats['coverage_percentage']:.1f}%)")

    elif args.check == 'difficulty':
        results = agent.check_difficulty_level_coverage()
        print(f"\nTranslation coverage by difficulty level:")
        print(f"  Total levels: {results['total_levels']}")

    else:  # all
        agent.run_full_check(output_file=args.output)


if __name__ == '__main__':
    main()
