#!/usr/bin/env python3
"""
Vilkas - Lithuanian Word Forms Checker Agent

This agent runs autonomously to check for the presence of Lithuanian word forms
in the database. It identifies lemmas that should have derivative forms but don't,
and reports on data quality issues.

"Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, DerivativeForm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VilkasAgent:
    """Agent for checking Lithuanian word forms in the database."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Vilkas agent.

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

    def check_missing_lithuanian_base_forms(self) -> Dict[str, any]:
        """
        Check for lemmas with Lithuanian translations but no Lithuanian derivative forms.

        Returns:
            Dictionary with check results
        """
        logger.info("Checking for lemmas missing Lithuanian base forms...")

        session = self.get_session()
        try:
            # Find lemmas with Lithuanian translations
            lemmas_with_lt = session.query(Lemma).filter(
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).all()

            logger.info(f"Found {len(lemmas_with_lt)} lemmas with Lithuanian translations")

            # Check which ones are missing Lithuanian derivative forms
            missing_forms = []

            for lemma in lemmas_with_lt:
                # Check for Lithuanian derivative forms
                lt_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == 'lt'
                ).all()

                if not lt_forms:
                    missing_forms.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'lithuanian_translation': lemma.lithuanian_translation,
                        'pos_type': lemma.pos_type,
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level
                    })

            logger.info(f"Found {len(missing_forms)} lemmas missing Lithuanian derivative forms")

            return {
                'total_with_translation': len(lemmas_with_lt),
                'missing_forms': missing_forms,
                'missing_count': len(missing_forms),
                'coverage_percentage': ((len(lemmas_with_lt) - len(missing_forms)) / len(lemmas_with_lt) * 100) if lemmas_with_lt else 0
            }

        except Exception as e:
            logger.error(f"Error checking missing Lithuanian base forms: {e}")
            return {
                'error': str(e),
                'total_with_translation': 0,
                'missing_forms': [],
                'missing_count': 0,
                'coverage_percentage': 0
            }
        finally:
            session.close()

    def check_noun_declension_coverage(self) -> Dict[str, any]:
        """
        Check for Lithuanian nouns that have base forms but missing declensions.

        For Lithuanian nouns, we expect various declension forms (cases/numbers).
        This checks which nouns only have the base (nominative singular) form.

        Returns:
            Dictionary with check results
        """
        logger.info("Checking Lithuanian noun declension coverage...")

        session = self.get_session()
        try:
            # Find lemmas that are nouns with Lithuanian translations
            noun_lemmas = session.query(Lemma).filter(
                Lemma.pos_type == 'noun',
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).all()

            logger.info(f"Found {len(noun_lemmas)} noun lemmas with Lithuanian translations")

            # Check declension coverage
            needs_declensions = []
            has_declensions = []

            for lemma in noun_lemmas:
                # Count Lithuanian derivative forms for this noun
                lt_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == 'lt'
                ).all()

                # If we only have 1 form (the base form), it needs declensions
                if len(lt_forms) <= 1:
                    needs_declensions.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'lithuanian': lemma.lithuanian_translation,
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level,
                        'current_form_count': len(lt_forms)
                    })
                else:
                    has_declensions.append({
                        'guid': lemma.guid,
                        'form_count': len(lt_forms)
                    })

            logger.info(f"Nouns with declensions: {len(has_declensions)}")
            logger.info(f"Nouns needing declensions: {len(needs_declensions)}")

            return {
                'total_nouns': len(noun_lemmas),
                'with_declensions': len(has_declensions),
                'needs_declensions': len(needs_declensions),
                'nouns_needing_declensions': needs_declensions,
                'declension_coverage_percentage': (len(has_declensions) / len(noun_lemmas) * 100) if noun_lemmas else 0
            }

        except Exception as e:
            logger.error(f"Error checking noun declension coverage: {e}")
            return {
                'error': str(e),
                'total_nouns': 0,
                'with_declensions': 0,
                'needs_declensions': 0,
                'nouns_needing_declensions': [],
                'declension_coverage_percentage': 0
            }
        finally:
            session.close()

    def check_verb_conjugation_coverage(self) -> Dict[str, any]:
        """
        Check for Lithuanian verbs that have base forms but missing conjugations.

        Returns:
            Dictionary with check results
        """
        logger.info("Checking Lithuanian verb conjugation coverage...")

        session = self.get_session()
        try:
            # Find lemmas that are verbs with Lithuanian translations
            verb_lemmas = session.query(Lemma).filter(
                Lemma.pos_type == 'verb',
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).all()

            logger.info(f"Found {len(verb_lemmas)} verb lemmas with Lithuanian translations")

            # Check conjugation coverage
            needs_conjugations = []
            has_conjugations = []

            for lemma in verb_lemmas:
                # Count Lithuanian derivative forms for this verb
                lt_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == 'lt'
                ).all()

                # If we only have 1 form (the infinitive), it needs conjugations
                if len(lt_forms) <= 1:
                    needs_conjugations.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'lithuanian': lemma.lithuanian_translation,
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level,
                        'current_form_count': len(lt_forms)
                    })
                else:
                    has_conjugations.append({
                        'guid': lemma.guid,
                        'form_count': len(lt_forms)
                    })

            logger.info(f"Verbs with conjugations: {len(has_conjugations)}")
            logger.info(f"Verbs needing conjugations: {len(needs_conjugations)}")

            return {
                'total_verbs': len(verb_lemmas),
                'with_conjugations': len(has_conjugations),
                'needs_conjugations': len(needs_conjugations),
                'verbs_needing_conjugations': needs_conjugations,
                'conjugation_coverage_percentage': (len(has_conjugations) / len(verb_lemmas) * 100) if verb_lemmas else 0
            }

        except Exception as e:
            logger.error(f"Error checking verb conjugation coverage: {e}")
            return {
                'error': str(e),
                'total_verbs': 0,
                'with_conjugations': 0,
                'needs_conjugations': 0,
                'verbs_needing_conjugations': [],
                'conjugation_coverage_percentage': 0
            }
        finally:
            session.close()

    def run_full_check(self, output_file: Optional[str] = None) -> Dict[str, any]:
        """
        Run all checks and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting full Lithuanian word forms check...")
        start_time = datetime.now()

        results = {
            'timestamp': start_time.isoformat(),
            'database_path': self.db_path,
            'checks': {
                'missing_base_forms': self.check_missing_lithuanian_base_forms(),
                'noun_declensions': self.check_noun_declension_coverage(),
                'verb_conjugations': self.check_verb_conjugation_coverage()
            }
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results['duration_seconds'] = duration

        # Print summary
        logger.info("=" * 80)
        logger.info("VILKAS AGENT REPORT - Lithuanian Word Forms Check")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Missing base forms
        base_check = results['checks']['missing_base_forms']
        logger.info(f"MISSING LITHUANIAN BASE FORMS:")
        logger.info(f"  Total lemmas with Lithuanian translation: {base_check['total_with_translation']}")
        logger.info(f"  Missing derivative forms: {base_check['missing_count']}")
        logger.info(f"  Coverage: {base_check['coverage_percentage']:.1f}%")
        logger.info("")

        # Noun declensions
        noun_check = results['checks']['noun_declensions']
        logger.info(f"LITHUANIAN NOUN DECLENSIONS:")
        logger.info(f"  Total nouns: {noun_check['total_nouns']}")
        logger.info(f"  With declensions: {noun_check['with_declensions']}")
        logger.info(f"  Needing declensions: {noun_check['needs_declensions']}")
        logger.info(f"  Coverage: {noun_check['declension_coverage_percentage']:.1f}%")
        logger.info("")

        # Verb conjugations
        verb_check = results['checks']['verb_conjugations']
        logger.info(f"LITHUANIAN VERB CONJUGATIONS:")
        logger.info(f"  Total verbs: {verb_check['total_verbs']}")
        logger.info(f"  With conjugations: {verb_check['with_conjugations']}")
        logger.info(f"  Needing conjugations: {verb_check['needs_conjugations']}")
        logger.info(f"  Coverage: {verb_check['conjugation_coverage_percentage']:.1f}%")
        logger.info("=" * 80)

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


def main():
    """Main entry point for the vilkas agent."""
    parser = argparse.ArgumentParser(
        description="Vilkas - Lithuanian Word Forms Checker Agent"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--check',
                       choices=['base-forms', 'noun-declensions', 'verb-conjugations', 'all'],
                       default='all',
                       help='Which check to run (default: all)')

    args = parser.parse_args()

    agent = VilkasAgent(db_path=args.db_path, debug=args.debug)

    if args.check == 'base-forms':
        results = agent.check_missing_lithuanian_base_forms()
        print(f"\nMissing base forms: {results['missing_count']} out of {results['total_with_translation']}")
        print(f"Coverage: {results['coverage_percentage']:.1f}%")

    elif args.check == 'noun-declensions':
        results = agent.check_noun_declension_coverage()
        print(f"\nNouns needing declensions: {results['needs_declensions']} out of {results['total_nouns']}")
        print(f"Coverage: {results['declension_coverage_percentage']:.1f}%")

    elif args.check == 'verb-conjugations':
        results = agent.check_verb_conjugation_coverage()
        print(f"\nVerbs needing conjugations: {results['needs_conjugations']} out of {results['total_verbs']}")
        print(f"Coverage: {results['conjugation_coverage_percentage']:.1f}%")

    else:  # all
        agent.run_full_check(output_file=args.output)


if __name__ == '__main__':
    main()
