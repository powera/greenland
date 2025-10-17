#!/usr/bin/env python3
"""
Lokys - English Lemma Validation Agent

This agent runs autonomously to validate English-language properties:
1. Lemma forms are in proper dictionary/base form (e.g., "shoe" not "shoes")
2. English definitions are accurate and well-formed
3. POS types and subtypes are correct

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
    validate_definition,
    batch_validate_lemmas
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LokysAgent:
    """Agent for validating English lemma forms and properties."""

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

    def check_definitions(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Check that definition_text values are well-formed and appropriate.

        Args:
            limit: Maximum number of definitions to check
            sample_rate: Fraction of definitions to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with check results
        """
        logger.info("Checking English definitions...")

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

            # Validate definitions
            issues_found = []
            checked_count = 0

            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Checked {checked_count}/{len(lemmas)} definitions...")

                result = validate_definition(
                    lemma.lemma_text,
                    lemma.definition_text or "",
                    lemma.pos_type,
                    self.model
                )

                if not result['is_valid'] and result['confidence'] >= confidence_threshold:
                    issues_found.append({
                        'guid': lemma.guid,
                        'lemma': lemma.lemma_text,
                        'current_definition': lemma.definition_text,
                        'suggested_definition': result['suggested_definition'],
                        'pos_type': lemma.pos_type,
                        'issues': result['issues'],
                        'confidence': result['confidence']
                    })
                    logger.warning(
                        f"Definition issue: '{lemma.lemma_text}' (GUID: {lemma.guid}) - {', '.join(result['issues'])} "
                        f"(confidence: {result['confidence']:.2f})"
                    )

            logger.info(f"Found {len(issues_found)} definitions with potential issues")

            return {
                'total_checked': checked_count,
                'issues_found': len(issues_found),
                'issue_rate': (len(issues_found) / checked_count * 100) if checked_count else 0,
                'issues': issues_found,
                'confidence_threshold': confidence_threshold
            }

        except Exception as e:
            logger.error(f"Error checking definitions: {e}")
            return {
                'error': str(e),
                'total_checked': 0,
                'issues_found': 0,
                'issue_rate': 0,
                'issues': []
            }
        finally:
            session.close()

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7
    ) -> Dict[str, any]:
        """
        Run English lemma validation and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            limit: Maximum items to check
            sample_rate: Fraction to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting English lemma validation check...")
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
        results['checks']['lemma_forms'] = self.check_lemma_forms(
            limit=limit,
            sample_rate=sample_rate,
            confidence_threshold=confidence_threshold
        )

        # Check English definitions
        results['checks']['definitions'] = self.check_definitions(
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
        logger.info("LOKYS AGENT REPORT - English Lemma Validation")
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

        # Definitions check
        if 'definitions' in results['checks']:
            def_check = results['checks']['definitions']
            logger.info(f"ENGLISH DEFINITIONS:")
            logger.info(f"  Total checked: {def_check['total_checked']}")
            logger.info(f"  Issues found: {def_check['issues_found']}")
            logger.info(f"  Issue rate: {def_check['issue_rate']:.1f}%")
            logger.info("")

        logger.info("=" * 80)


def main():
    """Main entry point for the lokys agent."""
    parser = argparse.ArgumentParser(
        description="Lokys - English Lemma Validation Agent"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--model', default='gpt-5-mini', help='LLM model to use (default: gpt-5-mini)')
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
            query = session.query(Lemma).filter(Lemma.guid.isnot(None))
            if args.limit:
                query = query.limit(args.limit)
            lemma_count = query.count()
            if args.sample_rate < 1.0:
                lemma_count = int(lemma_count * args.sample_rate)
            estimated_calls = lemma_count
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

    agent.run_full_check(
        output_file=args.output,
        limit=args.limit,
        sample_rate=args.sample_rate,
        confidence_threshold=args.confidence_threshold
    )


if __name__ == '__main__':
    main()
