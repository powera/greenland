#!/usr/bin/env python3
"""
Database Integrity Checker

Checks database structural integrity and identifies data quality issues like
orphaned records, missing required fields, and constraint violations.
"""

import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import (
    Lemma, WordToken, DerivativeForm, Corpus, WordFrequency
)

logger = logging.getLogger(__name__)


class IntegrityChecker:
    """Database integrity checker."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the integrity checker.

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

    def check_orphaned_derivative_forms(self) -> Dict[str, any]:
        """Check for derivative forms with invalid lemma_id references."""
        logger.info("Checking for orphaned derivative forms...")

        session = self.get_session()
        try:
            valid_lemma_ids = set(lemma_id for lemma_id, in session.query(Lemma.id).all())
            logger.info(f"Found {len(valid_lemma_ids)} valid lemma IDs")

            derivative_forms = session.query(DerivativeForm).all()
            orphaned = [
                {
                    'id': form.id,
                    'derivative_form_text': form.derivative_form_text,
                    'language_code': form.language_code,
                    'invalid_lemma_id': form.lemma_id
                }
                for form in derivative_forms
                if form.lemma_id not in valid_lemma_ids
            ]

            logger.info(f"Found {len(orphaned)} orphaned derivative forms")

            return {
                'total_checked': len(derivative_forms),
                'orphaned_count': len(orphaned),
                'orphaned_forms': orphaned
            }

        except Exception as e:
            logger.error(f"Error checking orphaned derivative forms: {e}")
            return {
                'error': str(e),
                'total_checked': 0,
                'orphaned_count': 0,
                'orphaned_forms': []
            }
        finally:
            session.close()

    def check_derivative_form_word_tokens(self) -> Dict[str, any]:
        """Check for derivative forms with invalid word_token_id references or mismatched text."""
        logger.info("Checking derivative form word token references...")

        session = self.get_session()
        try:
            word_tokens_dict = {token_id: token_text for token_id, token_text in session.query(WordToken.id, WordToken.token).all()}
            logger.info(f"Found {len(word_tokens_dict)} valid word tokens")

            derivative_forms = session.query(DerivativeForm).filter(
                DerivativeForm.word_token_id.isnot(None)
            ).all()

            issues = []
            for form in derivative_forms:
                form_issues = []
                if form.word_token_id not in word_tokens_dict:
                    form_issues.append(f"invalid_word_token_id: {form.word_token_id}")
                elif form.derivative_form_text != word_tokens_dict[form.word_token_id]:
                    expected_token = word_tokens_dict[form.word_token_id]
                    form_issues.append(
                        f"text_mismatch: derivative_form_text='{form.derivative_form_text}' "
                        f"but word_token.token='{expected_token}'"
                    )

                if form_issues:
                    issues.append({
                        'id': form.id,
                        'derivative_form_text': form.derivative_form_text,
                        'word_token_id': form.word_token_id,
                        'lemma_id': form.lemma_id,
                        'language_code': form.language_code,
                        'issues': form_issues
                    })

            logger.info(f"Found {len(issues)} derivative forms with word token issues")

            return {
                'total_checked': len(derivative_forms),
                'issue_count': len(issues),
                'issues': issues
            }

        except Exception as e:
            logger.error(f"Error checking derivative form word tokens: {e}")
            return {
                'error': str(e),
                'total_checked': 0,
                'issue_count': 0,
                'issues': []
            }
        finally:
            session.close()

    def check_orphaned_word_frequencies(self) -> Dict[str, any]:
        """Check for word frequencies with invalid word_token_id or corpus_id."""
        logger.info("Checking for orphaned word frequencies...")

        session = self.get_session()
        try:
            valid_token_ids = set(token_id for token_id, in session.query(WordToken.id).all())
            valid_corpus_ids = set(corpus_id for corpus_id, in session.query(Corpus.id).all())

            logger.info(f"Found {len(valid_token_ids)} valid token IDs and {len(valid_corpus_ids)} valid corpus IDs")

            frequencies = session.query(WordFrequency).all()
            orphaned = []

            for freq in frequencies:
                issues = []
                if freq.word_token_id not in valid_token_ids:
                    issues.append(f"invalid_word_token_id: {freq.word_token_id}")
                if freq.corpus_id not in valid_corpus_ids:
                    issues.append(f"invalid_corpus_id: {freq.corpus_id}")

                if issues:
                    orphaned.append({
                        'id': freq.id,
                        'word_token_id': freq.word_token_id,
                        'corpus_id': freq.corpus_id,
                        'issues': issues
                    })

            logger.info(f"Found {len(orphaned)} orphaned word frequencies")

            return {
                'total_checked': len(frequencies),
                'orphaned_count': len(orphaned),
                'orphaned_frequencies': orphaned
            }

        except Exception as e:
            logger.error(f"Error checking orphaned word frequencies: {e}")
            return {
                'error': str(e),
                'total_checked': 0,
                'orphaned_count': 0,
                'orphaned_frequencies': []
            }
        finally:
            session.close()

    def check_missing_required_fields(self) -> Dict[str, any]:
        """Check for records with missing required fields."""
        logger.info("Checking for missing required fields...")

        session = self.get_session()
        try:
            issues = []

            # Check Lemmas for missing fields
            for lemma in session.query(Lemma).filter(
                (Lemma.definition_text.is_(None)) | (Lemma.definition_text == '')
            ).all():
                issues.append({
                    'table': 'lemmas',
                    'id': lemma.id,
                    'guid': lemma.guid,
                    'lemma_text': lemma.lemma_text,
                    'missing_field': 'definition_text',
                    'severity': 'high'
                })

            for lemma in session.query(Lemma).filter(
                (Lemma.pos_type.is_(None)) | (Lemma.pos_type == '')
            ).all():
                issues.append({
                    'table': 'lemmas',
                    'id': lemma.id,
                    'guid': lemma.guid,
                    'lemma_text': lemma.lemma_text,
                    'missing_field': 'pos_type',
                    'severity': 'high'
                })

            for lemma in session.query(Lemma).filter(
                Lemma.guid.isnot(None),
                Lemma.difficulty_level.is_(None)
            ).all():
                issues.append({
                    'table': 'lemmas',
                    'id': lemma.id,
                    'guid': lemma.guid,
                    'lemma_text': lemma.lemma_text,
                    'missing_field': 'difficulty_level',
                    'severity': 'medium'
                })

            logger.info(f"Found {len(issues)} records with missing required fields")

            high_severity = [i for i in issues if i['severity'] == 'high']
            medium_severity = [i for i in issues if i['severity'] == 'medium']

            return {
                'total_issues': len(issues),
                'high_severity_count': len(high_severity),
                'medium_severity_count': len(medium_severity),
                'high_severity_issues': high_severity,
                'medium_severity_issues': medium_severity
            }

        except Exception as e:
            logger.error(f"Error checking missing required fields: {e}")
            return {
                'error': str(e),
                'total_issues': 0,
                'high_severity_count': 0,
                'medium_severity_count': 0,
                'high_severity_issues': [],
                'medium_severity_issues': []
            }
        finally:
            session.close()

    def check_lemmas_without_derivatives(self) -> Dict[str, any]:
        """Check for lemmas that have no derivative forms at all."""
        logger.info("Checking for lemmas without derivative forms...")

        session = self.get_session()
        try:
            all_lemma_ids = set(lemma.id for lemma in session.query(Lemma).all())
            lemmas_with_forms = set(lemma_id for lemma_id, in session.query(DerivativeForm.lemma_id).distinct().all())
            lemmas_without_forms_ids = all_lemma_ids - lemmas_with_forms

            lemmas_without_forms = [
                {
                    'id': lemma.id,
                    'guid': lemma.guid,
                    'lemma_text': lemma.lemma_text,
                    'pos_type': lemma.pos_type,
                    'difficulty_level': lemma.difficulty_level
                }
                for lemma_id in lemmas_without_forms_ids
                if (lemma := session.query(Lemma).filter(Lemma.id == lemma_id).first())
            ]

            logger.info(f"Found {len(lemmas_without_forms)} lemmas without derivative forms")

            return {
                'total_lemmas': len(all_lemma_ids),
                'without_forms_count': len(lemmas_without_forms),
                'lemmas_without_forms': lemmas_without_forms
            }

        except Exception as e:
            logger.error(f"Error checking lemmas without derivative forms: {e}")
            return {
                'error': str(e),
                'total_lemmas': 0,
                'without_forms_count': 0,
                'lemmas_without_forms': []
            }
        finally:
            session.close()

    def check_duplicate_guids(self) -> Dict[str, any]:
        """Check for duplicate GUIDs in lemmas table."""
        logger.info("Checking for duplicate GUIDs...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            guid_counts = session.query(
                Lemma.guid,
                func.count(Lemma.id).label('count')
            ).filter(
                Lemma.guid.isnot(None)
            ).group_by(
                Lemma.guid
            ).having(
                func.count(Lemma.id) > 1
            ).all()

            duplicates = []
            for guid, count in guid_counts:
                lemmas = session.query(Lemma).filter(Lemma.guid == guid).all()
                duplicate_entry = {
                    'guid': guid,
                    'count': count,
                    'lemmas': [
                        {
                            'id': lemma.id,
                            'lemma_text': lemma.lemma_text,
                            'pos_type': lemma.pos_type,
                            'difficulty_level': lemma.difficulty_level
                        }
                        for lemma in lemmas
                    ]
                }
                duplicates.append(duplicate_entry)

            logger.info(f"Found {len(duplicates)} duplicate GUIDs")

            return {
                'duplicate_count': len(duplicates),
                'duplicates': duplicates
            }

        except Exception as e:
            logger.error(f"Error checking duplicate GUIDs: {e}")
            return {
                'error': str(e),
                'duplicate_count': 0,
                'duplicates': []
            }
        finally:
            session.close()

    def check_invalid_difficulty_levels(self) -> Dict[str, any]:
        """Check for difficulty levels outside the valid range (1-20)."""
        logger.info("Checking for invalid difficulty levels...")

        session = self.get_session()
        try:
            invalid_lemmas = session.query(Lemma).filter(
                Lemma.difficulty_level.isnot(None),
                ((Lemma.difficulty_level < 1) | (Lemma.difficulty_level > 20))
            ).all()

            invalid_entries = [
                {
                    'id': lemma.id,
                    'guid': lemma.guid,
                    'lemma_text': lemma.lemma_text,
                    'invalid_level': lemma.difficulty_level
                }
                for lemma in invalid_lemmas
            ]

            logger.info(f"Found {len(invalid_entries)} lemmas with invalid difficulty levels")

            return {
                'invalid_count': len(invalid_entries),
                'invalid_entries': invalid_entries
            }

        except Exception as e:
            logger.error(f"Error checking invalid difficulty levels: {e}")
            return {
                'error': str(e),
                'invalid_count': 0,
                'invalid_entries': []
            }
        finally:
            session.close()

    def run_full_check(self, output_file: Optional[str] = None) -> Dict[str, any]:
        """Run all integrity checks and generate a comprehensive report."""
        logger.info("Starting full database integrity check...")
        start_time = datetime.now()

        results = {
            'timestamp': start_time.isoformat(),
            'database_path': self.db_path,
            'checks': {
                'orphaned_derivative_forms': self.check_orphaned_derivative_forms(),
                'derivative_form_word_tokens': self.check_derivative_form_word_tokens(),
                'orphaned_word_frequencies': self.check_orphaned_word_frequencies(),
                'missing_required_fields': self.check_missing_required_fields(),
                'lemmas_without_derivatives': self.check_lemmas_without_derivatives(),
                'duplicate_guids': self.check_duplicate_guids(),
                'invalid_difficulty_levels': self.check_invalid_difficulty_levels()
            }
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results['duration_seconds'] = duration

        self._print_summary(results, start_time, duration)

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
        logger.info("BEBRAS INTEGRITY CHECK REPORT")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        checks = results['checks']

        logger.info("ORPHANED RECORDS:")
        logger.info(f"  Derivative forms (invalid lemma_id): {checks['orphaned_derivative_forms']['orphaned_count']}")
        logger.info(f"  Derivative forms (invalid/mismatched word_token): {checks['derivative_form_word_tokens']['issue_count']}")
        logger.info(f"  Word frequencies: {checks['orphaned_word_frequencies']['orphaned_count']}")
        logger.info("")

        missing_fields = checks['missing_required_fields']
        logger.info("MISSING REQUIRED FIELDS:")
        logger.info(f"  High severity: {missing_fields['high_severity_count']}")
        logger.info(f"  Medium severity: {missing_fields['medium_severity_count']}")
        logger.info("")

        logger.info("LEMMAS WITHOUT DERIVATIVE FORMS:")
        logger.info(f"  Count: {checks['lemmas_without_derivatives']['without_forms_count']}")
        logger.info("")

        logger.info("DUPLICATE GUIDs:")
        logger.info(f"  Count: {checks['duplicate_guids']['duplicate_count']}")
        logger.info("")

        logger.info("INVALID DIFFICULTY LEVELS:")
        logger.info(f"  Count: {checks['invalid_difficulty_levels']['invalid_count']}")

        total_issues = (
            checks['orphaned_derivative_forms']['orphaned_count'] +
            checks['derivative_form_word_tokens']['issue_count'] +
            checks['orphaned_word_frequencies']['orphaned_count'] +
            missing_fields['total_issues'] +
            checks['lemmas_without_derivatives']['without_forms_count'] +
            checks['duplicate_guids']['duplicate_count'] +
            checks['invalid_difficulty_levels']['invalid_count']
        )

        logger.info("")
        logger.info(f"TOTAL ISSUES FOUND: {total_issues}")
        logger.info("=" * 80)


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Bebras Database Integrity Checker"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--check',
                       choices=['orphaned', 'missing-fields', 'no-derivatives',
                               'duplicates', 'invalid-levels', 'all'],
                       default='all',
                       help='Which check to run (default: all)')

    return parser


def main():
    """Main entry point for the integrity checker."""
    parser = get_argument_parser()
    args = parser.parse_args()

    checker = IntegrityChecker(db_path=args.db_path, debug=args.debug)

    if args.check == 'orphaned':
        results = {
            'derivative_forms': checker.check_orphaned_derivative_forms(),
            'derivative_form_word_tokens': checker.check_derivative_form_word_tokens(),
            'word_frequencies': checker.check_orphaned_word_frequencies()
        }
        total = (results['derivative_forms']['orphaned_count'] +
                results['derivative_form_word_tokens']['issue_count'] +
                results['word_frequencies']['orphaned_count'])
        print(f"\nTotal orphaned records: {total}")

    elif args.check == 'missing-fields':
        results = checker.check_missing_required_fields()
        print(f"\nMissing required fields: {results['total_issues']} " +
              f"(High: {results['high_severity_count']}, Medium: {results['medium_severity_count']})")

    elif args.check == 'no-derivatives':
        results = checker.check_lemmas_without_derivatives()
        print(f"\nLemmas without derivative forms: {results['without_forms_count']} out of {results['total_lemmas']}")

    elif args.check == 'duplicates':
        results = checker.check_duplicate_guids()
        print(f"\nDuplicate GUIDs: {results['duplicate_count']}")

    elif args.check == 'invalid-levels':
        results = checker.check_invalid_difficulty_levels()
        print(f"\nInvalid difficulty levels: {results['invalid_count']}")

    else:  # all
        checker.run_full_check(output_file=args.output)


if __name__ == '__main__':
    main()
