#!/usr/bin/env python3
"""
Dramblys - Missing Words Detection Agent

This agent runs autonomously to identify missing words that should be in the
dictionary. It scans frequency corpora, checks category coverage, and identifies
high-priority words to add.

"Dramblys" means "elephant" in Lithuanian - never forgets what's missing!
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
import util.stopwords
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, WordToken, WordFrequency, Corpus, DerivativeForm
from wordfreq.translation.client import LinguisticClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DramblysAgent:
    """Agent for detecting missing words in the dictionary."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Dramblys agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def _is_valid_word(self, word: str) -> bool:
        """
        Check if a word is valid (not a stopword, has only letters, etc.).

        Args:
            word: Word to check

        Returns:
            True if valid
        """
        word_lower = word.lower()

        # Skip stopwords - check all categories
        if word_lower in util.stopwords.all_stopwords:
            return False

        # Also check common words that shouldn't be priorities
        if word_lower in util.stopwords.COMMON_VERBS:
            return False
        if word_lower in util.stopwords.COMMON_NOUNS:
            return False
        if word_lower in util.stopwords.COMMON_ADVERBS:
            return False
        if word_lower in util.stopwords.MISC_WORDS:
            return False

        # Check contractions
        if word in util.stopwords.CONTRACTIONS:
            return False

        # Must contain at least one letter
        if not any(c.isalpha() for c in word):
            return False

        # Skip very short words (likely abbreviations or noise)
        if len(word) < 2:
            return False

        # Skip words with numbers
        if any(c.isdigit() for c in word):
            return False

        # Skip words with special characters (except hyphens and apostrophes)
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'-")
        if not all(c in allowed_chars for c in word):
            return False

        return True

    def check_high_frequency_missing_words(
        self,
        top_n: int = 5000,
        min_rank: int = 1
    ) -> Dict[str, any]:
        """
        Check for high-frequency words in corpora that are missing from lemmas.

        Args:
            top_n: Check top N words by frequency
            min_rank: Minimum frequency rank to consider

        Returns:
            Dictionary with missing words and their frequency info
        """
        logger.info(f"Checking top {top_n} frequency words for missing lemmas...")

        session = self.get_session()
        try:
            # Get all existing lemma texts (English)
            existing_lemmas = set()
            lemmas = session.query(Lemma).all()
            for lemma in lemmas:
                existing_lemmas.add(lemma.lemma_text.lower())

            # Also get all English derivative forms
            english_forms = session.query(DerivativeForm).filter(
                DerivativeForm.language_code == 'en'
            ).all()
            for form in english_forms:
                existing_lemmas.add(form.derivative_form_text.lower())

            logger.info(f"Found {len(existing_lemmas)} existing English words in database")

            # Get high-frequency words from word_tokens
            high_freq_tokens = session.query(WordToken).filter(
                WordToken.language_code == 'en',
                WordToken.frequency_rank.isnot(None),
                WordToken.frequency_rank >= min_rank
            ).order_by(WordToken.frequency_rank).limit(top_n).all()

            logger.info(f"Checking {len(high_freq_tokens)} high-frequency tokens")

            # Find missing words
            missing_words = []
            for token in high_freq_tokens:
                word = token.token
                word_lower = word.lower()

                # Skip if already in database
                if word_lower in existing_lemmas:
                    continue

                # Skip if not a valid word
                if not self._is_valid_word(word):
                    continue

                # Get frequency data
                frequencies = session.query(WordFrequency).filter(
                    WordFrequency.word_token_id == token.id
                ).all()

                corpus_info = []
                for freq in frequencies:
                    corpus = session.query(Corpus).filter(
                        Corpus.id == freq.corpus_id
                    ).first()
                    if corpus:
                        corpus_info.append({
                            'corpus': corpus.name,
                            'rank': freq.rank,
                            'frequency': freq.frequency
                        })

                missing_words.append({
                    'word': word,
                    'overall_rank': token.frequency_rank,
                    'corpus_frequencies': corpus_info
                })

            logger.info(f"Found {len(missing_words)} high-frequency missing words")

            return {
                'total_checked': len(high_freq_tokens),
                'missing_count': len(missing_words),
                'missing_words': missing_words,
                'existing_word_count': len(existing_lemmas)
            }

        except Exception as e:
            logger.error(f"Error checking high-frequency missing words: {e}")
            return {
                'error': str(e),
                'total_checked': 0,
                'missing_count': 0,
                'missing_words': []
            }
        finally:
            session.close()

    def check_orphaned_derivative_forms(self) -> Dict[str, any]:
        """
        Find derivative forms that exist in the database but have no lemma entry.

        Returns:
            Dictionary with orphaned forms
        """
        logger.info("Checking for derivative forms without corresponding lemmas...")

        session = self.get_session()
        try:
            # Get all English derivative forms
            derivative_forms = session.query(DerivativeForm).filter(
                DerivativeForm.language_code == 'en'
            ).all()

            logger.info(f"Found {len(derivative_forms)} English derivative forms")

            # Get all lemma IDs
            existing_lemma_ids = set()
            lemmas = session.query(Lemma.id).all()
            for lemma_id_tuple in lemmas:
                existing_lemma_ids.add(lemma_id_tuple[0])

            # Find orphaned forms
            orphaned_forms = []
            for form in derivative_forms:
                if form.lemma_id not in existing_lemma_ids:
                    orphaned_forms.append({
                        'derivative_form_id': form.id,
                        'word': form.derivative_form_text,
                        'grammatical_form': form.grammatical_form,
                        'lemma_id': form.lemma_id
                    })

            logger.info(f"Found {len(orphaned_forms)} orphaned derivative forms")

            return {
                'total_forms_checked': len(derivative_forms),
                'orphaned_count': len(orphaned_forms),
                'orphaned_forms': orphaned_forms
            }

        except Exception as e:
            logger.error(f"Error checking orphaned derivative forms: {e}")
            return {
                'error': str(e),
                'total_forms_checked': 0,
                'orphaned_count': 0,
                'orphaned_forms': []
            }
        finally:
            session.close()

    def check_subtype_coverage(self, min_expected: int = 10) -> Dict[str, any]:
        """
        Check coverage of different POS subtypes and identify underrepresented ones.

        Args:
            min_expected: Minimum expected count for a subtype to be well-covered

        Returns:
            Dictionary with subtype coverage info
        """
        logger.info("Checking POS subtype coverage...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            # Get counts by subtype
            subtype_counts = session.query(
                Lemma.pos_type,
                Lemma.pos_subtype,
                func.count(Lemma.id).label('count')
            ).filter(
                Lemma.pos_subtype.isnot(None),
                Lemma.pos_subtype != ''
            ).group_by(
                Lemma.pos_type,
                Lemma.pos_subtype
            ).all()

            logger.info(f"Found {len(subtype_counts)} subtypes")

            # Categorize by coverage
            well_covered = []
            under_covered = []

            for pos_type, pos_subtype, count in subtype_counts:
                entry = {
                    'pos_type': pos_type,
                    'pos_subtype': pos_subtype,
                    'count': count
                }

                if count >= min_expected:
                    well_covered.append(entry)
                else:
                    under_covered.append(entry)

            # Sort under-covered by count (ascending)
            under_covered.sort(key=lambda x: x['count'])

            logger.info(f"Well-covered subtypes: {len(well_covered)}")
            logger.info(f"Under-covered subtypes: {len(under_covered)}")

            return {
                'total_subtypes': len(subtype_counts),
                'well_covered_count': len(well_covered),
                'under_covered_count': len(under_covered),
                'well_covered': well_covered,
                'under_covered': under_covered,
                'min_expected_threshold': min_expected
            }

        except Exception as e:
            logger.error(f"Error checking subtype coverage: {e}")
            return {
                'error': str(e),
                'total_subtypes': 0,
                'well_covered_count': 0,
                'under_covered_count': 0,
                'well_covered': [],
                'under_covered': []
            }
        finally:
            session.close()

    def check_difficulty_level_distribution(self) -> Dict[str, any]:
        """
        Check distribution of words across difficulty levels.

        Returns:
            Dictionary with level distribution info
        """
        logger.info("Checking difficulty level distribution...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            # Get counts by difficulty level
            level_counts = session.query(
                Lemma.difficulty_level,
                func.count(Lemma.id).label('count')
            ).filter(
                Lemma.difficulty_level.isnot(None),
                Lemma.guid.isnot(None)  # Only count trakaido words
            ).group_by(
                Lemma.difficulty_level
            ).order_by(
                Lemma.difficulty_level
            ).all()

            distribution = {}
            total_words = 0
            for level, count in level_counts:
                distribution[level] = count
                total_words += count

            # Identify gaps and imbalances
            gaps = []
            imbalanced = []
            avg_per_level = total_words / 20 if total_words > 0 else 0

            for level in range(1, 21):
                count = distribution.get(level, 0)

                if count == 0:
                    gaps.append(level)
                elif avg_per_level > 0 and count < avg_per_level * 0.5:
                    imbalanced.append({
                        'level': level,
                        'count': count,
                        'expected_avg': avg_per_level
                    })

            logger.info(f"Total trakaido words: {total_words}")
            logger.info(f"Level gaps: {len(gaps)}")
            logger.info(f"Imbalanced levels: {len(imbalanced)}")

            return {
                'total_words': total_words,
                'distribution': distribution,
                'average_per_level': avg_per_level,
                'gaps': gaps,
                'imbalanced': imbalanced
            }

        except Exception as e:
            logger.error(f"Error checking difficulty level distribution: {e}")
            return {
                'error': str(e),
                'total_words': 0,
                'distribution': {},
                'gaps': [],
                'imbalanced': []
            }
        finally:
            session.close()

    def fix_missing_words(
        self,
        top_n: int = 5000,
        limit: Optional[int] = None,
        model: str = 'gpt-5-mini',
        throttle: float = 1.0,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Process high-frequency missing words using LLM to add them to the database.

        This handles various types of missing words:
        - Plurals (e.g., "years" when "year" exists as lemma)
        - Polysemous words (e.g., "set", "light", "part" - may have multiple meanings/lemmas)
        - Grammatical words (e.g., "since") that aren't always base forms

        The LLM will identify:
        - The lemma(s) for each word token
        - Whether it's a base form or not
        - POS type and grammatical form
        - Potentially multiple lemmas for polysemous words

        Args:
            top_n: Check top N words by frequency (default: 5000)
            limit: Maximum number of words to process
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed WITHOUT making any LLM calls

        Returns:
            Dictionary with fix results
        """
        logger.info("Finding high-frequency missing words to process...")

        # Get missing words check results
        check_results = self.check_high_frequency_missing_words(top_n=top_n)

        if 'error' in check_results:
            return check_results

        missing_words = check_results['missing_words']
        total_missing = len(missing_words)

        if total_missing == 0:
            logger.info("No high-frequency missing words found!")
            return {
                'total_missing': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'dry_run': dry_run
            }

        logger.info(f"Found {total_missing} high-frequency missing words")

        # Apply limit if specified
        if limit:
            words_to_process = missing_words[:limit]
            logger.info(f"Processing limited to {limit} words")
        else:
            words_to_process = missing_words

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(words_to_process)} words:")
            for word_info in words_to_process[:20]:  # Show first 20
                corpus_str = ", ".join([f"{c['corpus']}:{c['rank']}" for c in word_info['corpus_frequencies'][:2]])
                logger.info(f"  - '{word_info['word']}' (overall rank: {word_info['overall_rank']}, {corpus_str})")
            if len(words_to_process) > 20:
                logger.info(f"  ... and {len(words_to_process) - 20} more")
            return {
                'total_missing': total_missing,
                'would_process': len(words_to_process),
                'dry_run': True,
                'sample': words_to_process[:20]
            }

        # Initialize client for LLM-based processing
        client = LinguisticClient(model=model, db_path=self.db_path, debug=self.debug)

        # Process each word
        successful = 0
        failed = 0

        for i, word_info in enumerate(words_to_process, 1):
            word = word_info['word']
            logger.info(f"\n[{i}/{len(words_to_process)}] Processing: '{word}' (rank: {word_info['overall_rank']})")

            # Use LinguisticClient.process_word to query definitions and store in database
            # This will:
            # - Query the LLM for definitions, POS, lemmas, grammatical forms
            # - Handle multiple definitions for polysemous words
            # - Correctly identify whether this is a base form or derived form
            # - Create WordToken, Lemma(s), and DerivativeForm entries
            success = client.process_word(word, refresh=False)

            if success:
                successful += 1
                logger.info(f"Successfully processed '{word}'")
            else:
                failed += 1
                logger.error(f"Failed to process '{word}'")

            # Throttle to avoid overloading the API
            if i < len(words_to_process):  # Don't sleep after the last one
                time.sleep(throttle)

        logger.info(f"\n{'='*60}")
        logger.info(f"Fix complete:")
        logger.info(f"  Total missing: {total_missing}")
        logger.info(f"  Processed: {len(words_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            'total_missing': total_missing,
            'processed': len(words_to_process),
            'successful': successful,
            'failed': failed,
            'dry_run': dry_run
        }

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        top_n_frequency: int = 5000,
        min_subtype_count: int = 10
    ) -> Dict[str, any]:
        """
        Run all missing words checks and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            top_n_frequency: Number of top frequency words to check
            min_subtype_count: Minimum expected count for subtypes

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting full missing words detection check...")
        start_time = datetime.now()

        results = {
            'timestamp': start_time.isoformat(),
            'database_path': self.db_path,
            'checks': {
                'high_frequency_missing': self.check_high_frequency_missing_words(
                    top_n=top_n_frequency
                ),
                'orphaned_forms': self.check_orphaned_derivative_forms(),
                'subtype_coverage': self.check_subtype_coverage(
                    min_expected=min_subtype_count
                ),
                'difficulty_distribution': self.check_difficulty_level_distribution()
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
        logger.info("DRAMBLYS AGENT REPORT - Missing Words Detection")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # High-frequency missing words
        if 'high_frequency_missing' in results['checks']:
            freq_check = results['checks']['high_frequency_missing']
            logger.info(f"HIGH-FREQUENCY MISSING WORDS:")
            logger.info(f"  Frequency tokens checked: {freq_check['total_checked']}")
            logger.info(f"  Missing words found: {freq_check['missing_count']}")
            logger.info(f"  Existing words in database: {freq_check.get('existing_word_count', 'N/A')}")
            if freq_check['missing_count'] > 0:
                logger.info(f"  Top 10 missing by rank:")
                for i, word_info in enumerate(freq_check['missing_words'][:10], 1):
                    logger.info(f"    {i}. '{word_info['word']}' (rank: {word_info['overall_rank']})")
            logger.info("")

        # Orphaned forms
        if 'orphaned_forms' in results['checks']:
            orphan_check = results['checks']['orphaned_forms']
            logger.info(f"ORPHANED DERIVATIVE FORMS:")
            logger.info(f"  Total forms checked: {orphan_check['total_forms_checked']}")
            logger.info(f"  Orphaned forms: {orphan_check['orphaned_count']}")
            logger.info("")

        # Subtype coverage
        if 'subtype_coverage' in results['checks']:
            subtype_check = results['checks']['subtype_coverage']
            logger.info(f"POS SUBTYPE COVERAGE:")
            logger.info(f"  Total subtypes: {subtype_check['total_subtypes']}")
            logger.info(f"  Well-covered: {subtype_check['well_covered_count']}")
            logger.info(f"  Under-covered: {subtype_check['under_covered_count']}")
            if subtype_check['under_covered_count'] > 0:
                logger.info(f"  Most under-covered subtypes:")
                for i, subtype in enumerate(subtype_check['under_covered'][:5], 1):
                    logger.info(f"    {i}. {subtype['pos_subtype']} ({subtype['pos_type']}): {subtype['count']} words")
            logger.info("")

        # Difficulty distribution
        if 'difficulty_distribution' in results['checks']:
            dist_check = results['checks']['difficulty_distribution']
            logger.info(f"DIFFICULTY LEVEL DISTRIBUTION:")
            logger.info(f"  Total trakaido words: {dist_check['total_words']}")
            logger.info(f"  Average per level: {dist_check['average_per_level']:.1f}")
            logger.info(f"  Empty levels: {len(dist_check['gaps'])}")
            if dist_check['gaps']:
                logger.info(f"    Levels: {dist_check['gaps']}")
            logger.info(f"  Imbalanced levels: {len(dist_check['imbalanced'])}")
            if dist_check['imbalanced']:
                for level_info in dist_check['imbalanced'][:5]:
                    logger.info(f"    Level {level_info['level']}: {level_info['count']} words (expected ~{level_info['expected_avg']:.0f})")

        logger.info("=" * 80)


def main():
    """Main entry point for the dramblys agent."""
    parser = argparse.ArgumentParser(
        description="Dramblys - Missing Words Detection Agent"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')

    # Check mode options (reporting only, no changes)
    parser.add_argument('--check',
                       choices=['frequency', 'orphaned', 'subtypes', 'levels', 'all'],
                       default='all',
                       help='Which check to run in reporting mode (default: all)')
    parser.add_argument('--top-n', type=int, default=5000,
                       help='Number of top frequency words to check (default: 5000)')
    parser.add_argument('--min-subtype-count', type=int, default=10,
                       help='Minimum expected words per subtype (default: 10)')

    # Fix mode options (process missing words)
    parser.add_argument('--fix', action='store_true',
                       help='Fix mode: Process high-frequency missing words using LLM')
    parser.add_argument('--limit', type=int, default=20,
                       help='[Fix mode] Maximum number of words to process (default: 20)')
    parser.add_argument('--model', default='gpt-5-mini',
                       help='[Fix mode] LLM model to use (default: gpt-5-mini)')
    parser.add_argument('--throttle', type=float, default=1.0,
                       help='[Fix mode] Seconds to wait between API calls (default: 1.0)')
    parser.add_argument('--dry-run', action='store_true',
                       help='[Fix mode] Show what would be fixed WITHOUT making any LLM calls')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='[Fix mode] Skip confirmation prompt')

    args = parser.parse_args()

    agent = DramblysAgent(db_path=args.db_path, debug=args.debug)

    # Handle --fix mode
    if args.fix:
        # Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            check_results = agent.check_high_frequency_missing_words(top_n=args.top_n)
            total_missing = check_results.get('missing_count', 0)

            print(f"\n{'='*60}")
            print(f"Ready to process high-frequency missing words using LLM")
            print(f"Total missing words found: {total_missing}")
            if args.limit:
                print(f"Limit: {args.limit} words")
            print(f"Model: {args.model}")
            print(f"Throttle: {args.throttle}s between calls")
            print(f"\nThis will:")
            print(f"  - Query LLM for definitions, lemmas, and POS info")
            print(f"  - Handle plurals, polysemous words, and grammatical words")
            print(f"  - Create multiple lemmas for words with multiple meanings")
            print(f"  - Correctly identify base forms vs. inflected forms")
            print(f"{'='*60}")
            response = input("\nContinue? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Aborted.")
                return

        results = agent.fix_missing_words(
            top_n=args.top_n,
            limit=args.limit,
            model=args.model,
            throttle=args.throttle,
            dry_run=args.dry_run
        )

        if 'error' in results:
            print(f"\nError: {results['error']}")
        else:
            if args.dry_run:
                print(f"\nDRY RUN: Would process {results['would_process']} words out of {results['total_missing']} total")
            else:
                print(f"\nFix complete:")
                print(f"  Total missing: {results['total_missing']}")
                print(f"  Processed: {results['processed']}")
                print(f"  Successful: {results['successful']}")
                print(f"  Failed: {results['failed']}")
        return

    # Handle check mode (existing functionality)
    if args.check == 'frequency':
        results = agent.check_high_frequency_missing_words(top_n=args.top_n)
        print(f"\nMissing high-frequency words: {results['missing_count']} out of {results['total_checked']} checked")

    elif args.check == 'orphaned':
        results = agent.check_orphaned_derivative_forms()
        print(f"\nOrphaned derivative forms: {results['orphaned_count']} out of {results['total_forms_checked']}")

    elif args.check == 'subtypes':
        results = agent.check_subtype_coverage(min_expected=args.min_subtype_count)
        print(f"\nUnder-covered subtypes: {results['under_covered_count']} out of {results['total_subtypes']}")

    elif args.check == 'levels':
        results = agent.check_difficulty_level_distribution()
        print(f"\nEmpty difficulty levels: {len(results['gaps'])}")
        print(f"Imbalanced levels: {len(results['imbalanced'])}")

    else:  # all
        agent.run_full_check(
            output_file=args.output,
            top_n_frequency=args.top_n,
            min_subtype_count=args.min_subtype_count
        )


if __name__ == '__main__':
    main()
