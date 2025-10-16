#!/usr/bin/env python3
"""
Lokys - Translation and Lemma Validation Agent

This agent runs autonomously to validate:
1. Multi-lingual translations are correct
2. Lemma forms are in proper dictionary/base form (e.g., "shoe" not "shoes")

"Lokys" means "bear" in Lithuanian - thorough and careful in checking quality.
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
from wordfreq.tools.llm_validators import (
    validate_lemma_form,
    validate_translation,
    batch_validate_lemmas,
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


class LokysAgent:
    """Agent for validating translations and lemma forms."""

    def __init__(self, db_path: str = None, debug: bool = False, model: str = "gpt-5-mini"):
        """
        Initialize the Lokys agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            model: LLM model to use for validation
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.model = model

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def check_lemma_forms(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Check that English lemma_text values are in proper lemma form.

        Args:
            limit: Maximum number of lemmas to check
            sample_rate: Fraction of lemmas to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with check results
        """
        logger.info("Checking English lemma forms...")

        session = self.get_session()
        try:
            # Get lemmas with GUIDs (these are the curated ones)
            query = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            ).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} lemmas to check")

            # Sample if needed
            if sample_rate < 1.0:
                import random
                sample_size = int(len(lemmas) * sample_rate)
                lemmas = random.sample(lemmas, sample_size)
                logger.info(f"Sampling {len(lemmas)} lemmas ({sample_rate*100:.0f}%)")

            # Validate lemma forms
            issues_found = []
            checked_count = 0

            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Checked {checked_count}/{len(lemmas)} lemmas...")

                result = validate_lemma_form(
                    lemma.lemma_text,
                    lemma.pos_type,
                    self.model
                )

                if not result['is_lemma'] and result['confidence'] >= confidence_threshold:
                    issues_found.append({
                        'guid': lemma.guid,
                        'current_lemma': lemma.lemma_text,
                        'suggested_lemma': result['suggested_lemma'],
                        'pos_type': lemma.pos_type,
                        'reason': result['reason'],
                        'confidence': result['confidence']
                    })
                    logger.warning(
                        f"Lemma issue: '{lemma.lemma_text}' → '{result['suggested_lemma']}' "
                        f"({lemma.guid}, confidence: {result['confidence']:.2f})"
                    )

            logger.info(f"Found {len(issues_found)} lemmas with potential issues")

            return {
                'total_checked': checked_count,
                'issues_found': len(issues_found),
                'issue_rate': (len(issues_found) / checked_count * 100) if checked_count else 0,
                'issues': issues_found,
                'confidence_threshold': confidence_threshold
            }

        except Exception as e:
            logger.error(f"Error checking lemma forms: {e}")
            return {
                'error': str(e),
                'total_checked': 0,
                'issues_found': 0,
                'issue_rate': 0,
                'issues': []
            }
        finally:
            session.close()

    def check_translations(
        self,
        language_code: str,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Check translations for a specific language.

        Args:
            language_code: Language code to check (lt, zh, ko, fr, sw, vi)
            limit: Maximum number of translations to check
            sample_rate: Fraction of translations to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with check results
        """
        if language_code not in LANGUAGE_FIELDS:
            raise ValueError(f"Unsupported language code: {language_code}")

        field_name, language_name = LANGUAGE_FIELDS[language_code]
        logger.info(f"Checking {language_name} translations...")

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
                logger.info(f"Sampling {len(lemmas)} translations ({sample_rate*100:.0f}%)")

            # Validate translations
            issues_found = []
            checked_count = 0

            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Checked {checked_count}/{len(lemmas)} translations...")

                translation = getattr(lemma, field_name)

                result = validate_translation(
                    lemma.lemma_text,
                    translation,
                    f"{language_code} ({language_name})",
                    lemma.pos_type,
                    self.model
                )

                has_issues = (
                    (not result['is_correct'] or not result['is_lemma_form'])
                    and result['confidence'] >= confidence_threshold
                )

                if has_issues:
                    issues_found.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'current_translation': translation,
                        'suggested_translation': result['suggested_translation'],
                        'pos_type': lemma.pos_type,
                        'is_correct': result['is_correct'],
                        'is_lemma_form': result['is_lemma_form'],
                        'issues': result['issues'],
                        'confidence': result['confidence']
                    })
                    logger.warning(
                        f"Translation issue ({lemma.guid}): '{lemma.lemma_text}' → '{translation}' "
                        f"(suggested: '{result['suggested_translation']}', confidence: {result['confidence']:.2f})"
                    )

            logger.info(f"Found {len(issues_found)} translations with potential issues")

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
            logger.error(f"Error checking {language_name} translations: {e}")
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

    def check_all_translations(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Check all multi-lingual translations.

        Args:
            limit: Maximum number of lemmas to check per language
            sample_rate: Fraction of translations to sample per language
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with results for all languages
        """
        logger.info("Checking all multi-lingual translations...")

        results = {}
        total_issues = 0

        for lang_code in LANGUAGE_FIELDS.keys():
            result = self.check_translations(
                lang_code,
                limit=limit,
                sample_rate=sample_rate,
                confidence_threshold=confidence_threshold
            )
            results[lang_code] = result
            total_issues += result.get('issues_found', 0)

        return {
            'by_language': results,
            'total_issues_all_languages': total_issues
        }

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        check_lemmas: bool = True,
        check_translations_flag: bool = True,
        languages: Optional[List[str]] = None,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Run all checks and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            limit: Maximum items to check
            sample_rate: Fraction to sample (0.0-1.0)
            check_lemmas: Whether to check English lemma forms
            check_translations_flag: Whether to check translations
            languages: Specific language codes to check (None = all)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting full translation and lemma validation check...")
        start_time = datetime.now()

        results = {
            'timestamp': start_time.isoformat(),
            'database_path': self.db_path,
            'model': self.model,
            'sample_rate': sample_rate,
            'confidence_threshold': confidence_threshold,
            'checks': {}
        }

        # Check English lemma forms
        if check_lemmas:
            results['checks']['lemma_forms'] = self.check_lemma_forms(
                limit=limit,
                sample_rate=sample_rate,
                confidence_threshold=confidence_threshold
            )

        # Check translations
        if check_translations_flag:
            if languages:
                # Check specific languages
                results['checks']['translations'] = {}
                for lang_code in languages:
                    if lang_code in LANGUAGE_FIELDS:
                        results['checks']['translations'][lang_code] = self.check_translations(
                            lang_code,
                            limit=limit,
                            sample_rate=sample_rate,
                            confidence_threshold=confidence_threshold
                        )
            else:
                # Check all languages
                results['checks']['translations'] = self.check_all_translations(
                    limit=limit,
                    sample_rate=sample_rate,
                    confidence_threshold=confidence_threshold
                )

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
        logger.info("LOKYS AGENT REPORT - Translation & Lemma Validation")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Model: {results['model']}")
        logger.info(f"Sample Rate: {results['sample_rate']*100:.0f}%")
        logger.info(f"Confidence Threshold: {results['confidence_threshold']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Lemma forms check
        if 'lemma_forms' in results['checks']:
            lemma_check = results['checks']['lemma_forms']
            logger.info(f"ENGLISH LEMMA FORMS:")
            logger.info(f"  Total checked: {lemma_check['total_checked']}")
            logger.info(f"  Issues found: {lemma_check['issues_found']}")
            logger.info(f"  Issue rate: {lemma_check['issue_rate']:.1f}%")
            logger.info("")

        # Translation checks
        if 'translations' in results['checks']:
            trans_results = results['checks']['translations']

            # Handle both formats (direct check or all languages)
            if 'by_language' in trans_results:
                logger.info(f"MULTI-LINGUAL TRANSLATIONS:")
                for lang_code, lang_result in trans_results['by_language'].items():
                    logger.info(f"  {lang_result['language_name']} ({lang_code}):")
                    logger.info(f"    Checked: {lang_result['total_checked']}")
                    logger.info(f"    Issues: {lang_result['issues_found']} ({lang_result['issue_rate']:.1f}%)")
                logger.info(f"  Total issues (all languages): {trans_results['total_issues_all_languages']}")
            else:
                for lang_code, lang_result in trans_results.items():
                    logger.info(f"  {lang_result['language_name']} ({lang_code}):")
                    logger.info(f"    Checked: {lang_result['total_checked']}")
                    logger.info(f"    Issues: {lang_result['issues_found']} ({lang_result['issue_rate']:.1f}%)")

        logger.info("=" * 80)


def main():
    """Main entry point for the lokys agent."""
    parser = argparse.ArgumentParser(
        description="Lokys - Translation and Lemma Validation Agent"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--model', default='gpt-5-mini', help='LLM model to use (default: gpt-5-mini)')
    parser.add_argument('--check',
                       choices=['lemmas', 'translations', 'all'],
                       default='all',
                       help='Which check to run (default: all)')
    parser.add_argument('--language',
                       choices=list(LANGUAGE_FIELDS.keys()),
                       help='Specific language to check (for translations check)')
    parser.add_argument('--limit', type=int, help='Maximum items to check')
    parser.add_argument('--sample-rate', type=float, default=1.0,
                       help='Fraction of items to sample (0.0-1.0, default: 1.0)')
    parser.add_argument('--confidence-threshold', type=float, default=0.7,
                       help='Minimum confidence to flag issues (0.0-1.0, default: 0.7)')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompt before running LLM queries')

    args = parser.parse_args()

    # Confirm before running LLM queries (unless --yes was provided)
    if not args.yes:
        # Calculate estimated number of LLM calls
        agent_temp = LokysAgent(db_path=args.db_path, debug=args.debug, model=args.model)
        session = agent_temp.get_session()
        try:
            estimated_calls = 0

            if args.check in ['lemmas', 'all']:
                query = session.query(Lemma).filter(Lemma.guid.isnot(None))
                if args.limit:
                    query = query.limit(args.limit)
                lemma_count = query.count()
                if args.sample_rate < 1.0:
                    lemma_count = int(lemma_count * args.sample_rate)
                estimated_calls += lemma_count

            if args.check in ['translations', 'all']:
                if args.language:
                    # Single language
                    field_name, _ = LANGUAGE_FIELDS[args.language]
                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        getattr(Lemma, field_name).isnot(None),
                        getattr(Lemma, field_name) != ''
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    translation_count = query.count()
                    if args.sample_rate < 1.0:
                        translation_count = int(translation_count * args.sample_rate)
                    estimated_calls += translation_count
                else:
                    # All languages
                    for lang_code, (field_name, _) in LANGUAGE_FIELDS.items():
                        query = session.query(Lemma).filter(
                            Lemma.guid.isnot(None),
                            getattr(Lemma, field_name).isnot(None),
                            getattr(Lemma, field_name) != ''
                        )
                        if args.limit:
                            query = query.limit(args.limit)
                        translation_count = query.count()
                        if args.sample_rate < 1.0:
                            translation_count = int(translation_count * args.sample_rate)
                        estimated_calls += translation_count
        finally:
            session.close()

        print(f"\nThis will make approximately {estimated_calls} LLM API calls using model '{args.model}'.")
        print("This may incur costs and take some time to complete.")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()

        if response not in ['y', 'yes']:
            print("Aborted.")
            sys.exit(0)

        print()  # Extra newline for readability

    agent = LokysAgent(db_path=args.db_path, debug=args.debug, model=args.model)

    if args.check == 'lemmas':
        results = agent.check_lemma_forms(
            limit=args.limit,
            sample_rate=args.sample_rate,
            confidence_threshold=args.confidence_threshold
        )
        print(f"\nLemma issues: {results['issues_found']} out of {results['total_checked']}")
        print(f"Issue rate: {results['issue_rate']:.1f}%")

    elif args.check == 'translations':
        if args.language:
            results = agent.check_translations(
                args.language,
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
            print(f"\n{results['language_name']} translation issues: {results['issues_found']} out of {results['total_checked']}")
            print(f"Issue rate: {results['issue_rate']:.1f}%")
        else:
            results = agent.check_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
            print(f"\nTotal translation issues (all languages): {results['total_issues_all_languages']}")

    else:  # all
        languages = [args.language] if args.language else None
        agent.run_full_check(
            output_file=args.output,
            limit=args.limit,
            sample_rate=args.sample_rate,
            languages=languages,
            confidence_threshold=args.confidence_threshold
        )


if __name__ == '__main__':
    main()
