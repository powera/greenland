#!/usr/bin/env python3
"""
Papuga - Pronunciation Validation and Generation Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/check-pronunciations/<lemma_id> endpoint
    - /agents/generate-pronunciations/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent runs autonomously to validate and generate pronunciations:
1. Validate existing IPA pronunciations for correctness
2. Validate existing phonetic (simplified) pronunciations
3. Generate missing pronunciations for derivative forms
4. Ensure pronunciations follow proper conventions

"Papuga" means "parrot" in Lithuanian - repeating sounds with perfect accuracy!
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
from agents.common_args import (
    add_common_args,
    add_llm_args,
    add_output_args,
    add_processing_args,
    add_guid_arg,
    add_backend_args,
    get_data_source_config,
    validate_cache_args,
    confirm_operation,
)
from clients.barsukas_cache import BarsukasCacheClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig, BackendType
from wordfreq.storage.models.schema import (
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.tools.llm_validators import validate_pronunciation, generate_pronunciation

# Backward compatibility
BackendConfig = DataSourceConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PapugaAgent:
    """Agent for validating and generating pronunciations."""

    def __init__(
        self,
        config: DataSourceConfig = None,
        db_path: str = None,
        debug: bool = False,
        model: str = None,
        backend_config: DataSourceConfig = None,
    ):
        """
        Initialize the Papuga agent.

        Args:
            config: DataSourceConfig with storage backend, cache, and LLM settings
            db_path: Path to SQLite database (backward compatibility)
            debug: Enable debug logging
            model: LLM model to use (backward compatibility)
            backend_config: Old name for config parameter (backward compatibility)
        """
        # Handle backward compatibility for parameter names
        if backend_config is not None and config is None:
            config = backend_config

        # Set up data source configuration
        if config is not None:
            self.config = config
        elif db_path is not None or model is not None:
            # Backward compatibility: build config from individual parameters
            self.config = DataSourceConfig(
                backend_type=BackendType.SQLITE,
                sqlite_path=db_path or constants.WORDFREQ_DB_PATH,
                model=model or "gpt-5-mini",
            )
        else:
            # Use default configuration
            self.config = DataSourceConfig(
                backend_type=BackendType.SQLITE,
                sqlite_path=constants.WORDFREQ_DB_PATH,
                model="gpt-5-mini",
            )

        # Extract commonly-used config values
        self.debug = debug
        self.model = self.config.model or "gpt-5-mini"

        # Keep db_path for backward compatibility
        if self.config.backend_type == BackendType.SQLITE:
            self.db_path = self.config.sqlite_path
        else:
            self.db_path = None

        # Lazy initialization
        self.cache_client = None

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_cache_client(self):
        """Get or create cache client for BARSUKAS queries."""
        if self.cache_client is None and self.config.barsukas_url:
            self.cache_client = BarsukasCacheClient(
                base_url=self.config.barsukas_url,
                cache_only=self.config.cache_only,
                debug=self.debug
            )
        return self.cache_client

    def _get_example_sentence(self, session, lemma: Lemma) -> Optional[str]:
        """
        Get an example sentence featuring this lemma from the new sentences system.

        Args:
            session: Database session
            lemma: Lemma object to find sentences for

        Returns:
            English sentence text, or None if no sentences found
        """
        if not lemma:
            return None

        # Query for sentences that use this lemma
        sentence_word = (
            session.query(SentenceWord).filter(SentenceWord.lemma_id == lemma.id).first()
        )

        if not sentence_word:
            return None

        # Get the English translation of this sentence
        sentence_translation = (
            session.query(SentenceTranslation)
            .filter(
                SentenceTranslation.sentence_id == sentence_word.sentence_id,
                SentenceTranslation.language_code == "en",
            )
            .first()
        )

        if sentence_translation:
            return sentence_translation.translation_text

        return None

    def check_pronunciations(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
        only_english: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Check existing pronunciations for correctness.

        Args:
            limit: Maximum number of forms to check
            sample_rate: Fraction of forms to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues
            only_english: Only check English forms (language_code='en')
            dry_run: If True, don't make LLM API calls, just count what would be checked

        Returns:
            Dictionary with check results
        """
        logger.info(f"{'DRY RUN: ' if dry_run else ''}Checking existing pronunciations...")

        session = self.get_session()
        try:
            # Get derivative forms with pronunciations
            query = session.query(DerivativeForm).filter(
                (DerivativeForm.ipa_pronunciation.isnot(None))
                | (DerivativeForm.phonetic_pronunciation.isnot(None))
            )

            if only_english:
                query = query.filter(DerivativeForm.language_code == "en")

            query = query.order_by(DerivativeForm.id)

            if limit:
                query = query.limit(limit)

            forms = query.all()
            logger.info(f"Found {len(forms)} forms with pronunciations to check")

            # Sample if needed
            if sample_rate < 1.0:
                import random

                sample_size = int(len(forms) * sample_rate)
                forms = random.sample(forms, sample_size)
                logger.info(f"Sampling {len(forms)} forms ({sample_rate*100:.0f}%)")

            # Validate pronunciations
            issues_found = []
            checked_count = 0

            if dry_run:
                # In dry run, just count what would be checked
                checked_count = len(forms)
                logger.info(f"Would check {checked_count} pronunciations (dry run)")
            else:
                for form in forms:
                    checked_count += 1
                    if checked_count % 10 == 0:
                        logger.info(f"Checked {checked_count}/{len(forms)} pronunciations...")

                    # Get lemma info for POS type and definition
                    lemma = session.query(Lemma).filter(Lemma.id == form.lemma_id).first()
                    if not lemma:
                        continue

                    # Get example sentence from the new sentences system if available
                    example_text = self._get_example_sentence(session, lemma)

                    result = validate_pronunciation(
                        word=form.derivative_form_text,
                        ipa_pronunciation=form.ipa_pronunciation,
                        phonetic_pronunciation=form.phonetic_pronunciation,
                        pos_type=lemma.pos_type,
                        example_sentence=example_text,
                        definition=lemma.definition_text,
                        model=self.model,
                    )

                    if result["needs_update"] and result["confidence"] >= confidence_threshold:
                        issues_found.append(
                            {
                                "form_id": form.id,
                                "word": form.derivative_form_text,
                                "lemma_guid": lemma.guid,
                                "current_ipa": form.ipa_pronunciation,
                                "current_phonetic": form.phonetic_pronunciation,
                                "suggested_ipa": result["suggested_ipa"],
                                "suggested_phonetic": result["suggested_phonetic"],
                                "issues": result["issues"],
                                "confidence": result["confidence"],
                                "notes": result["notes"],
                            }
                        )
                        logger.warning(
                            f"Pronunciation issue: '{form.derivative_form_text}' (form_id: {form.id}) - "
                            f"{', '.join(result['issues'])} (confidence: {result['confidence']:.2f})"
                        )

                logger.info(f"Found {len(issues_found)} pronunciations with potential issues")

            return {
                "total_checked": checked_count,
                "issues_found": len(issues_found),
                "issue_rate": (len(issues_found) / checked_count * 100) if checked_count else 0,
                "issues": issues_found,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            logger.error(f"Error checking pronunciations: {e}")
            return {
                "error": str(e),
                "total_checked": 0,
                "issues_found": 0,
                "issue_rate": 0,
                "issues": [],
            }
        finally:
            session.close()

    def check_missing_pronunciations(
        self, limit: Optional[int] = None, only_english: bool = True, only_base_forms: bool = False
    ) -> Dict[str, any]:
        """
        Find derivative forms that are missing pronunciations.

        Args:
            limit: Maximum number to report
            only_english: Only check English forms (language_code='en')
            only_base_forms: Only check base forms (is_base_form=True)

        Returns:
            Dictionary with missing pronunciation counts
        """
        logger.info("Checking for missing pronunciations...")

        session = self.get_session()
        try:
            # Get derivative forms without pronunciations
            query = session.query(DerivativeForm).filter(
                DerivativeForm.ipa_pronunciation.is_(None),
                DerivativeForm.phonetic_pronunciation.is_(None),
            )

            if only_english:
                query = query.filter(DerivativeForm.language_code == "en")

            if only_base_forms:
                query = query.filter(DerivativeForm.is_base_form == True)

            query = query.order_by(DerivativeForm.id)

            if limit:
                query = query.limit(limit)

            missing_forms = query.all()

            # Get lemma info for reporting
            missing_list = []
            for form in missing_forms[:100]:  # Limit detail list to 100
                lemma = session.query(Lemma).filter(Lemma.id == form.lemma_id).first()
                missing_list.append(
                    {
                        "form_id": form.id,
                        "word": form.derivative_form_text,
                        "lemma_guid": lemma.guid if lemma else None,
                        "pos_type": lemma.pos_type if lemma else None,
                        "grammatical_form": form.grammatical_form,
                        "is_base_form": form.is_base_form,
                    }
                )

            logger.info(f"Found {len(missing_forms)} forms missing pronunciations")

            return {
                "total_missing": len(missing_forms),
                "missing_forms": missing_list,
                "only_english": only_english,
                "only_base_forms": only_base_forms,
            }

        except Exception as e:
            logger.error(f"Error checking missing pronunciations: {e}")
            return {"error": str(e), "total_missing": 0, "missing_forms": []}
        finally:
            session.close()

    def populate_missing_pronunciations(
        self,
        limit: Optional[int] = None,
        only_english: bool = True,
        only_base_forms: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Generate pronunciations for forms that are missing them.

        Args:
            limit: Maximum number of forms to process
            only_english: Only process English forms
            only_base_forms: Only process base forms
            dry_run: If True, don't actually update the database

        Returns:
            Dictionary with population results
        """
        logger.info(f"{'DRY RUN: ' if dry_run else ''}Populating missing pronunciations...")

        session = self.get_session()
        try:
            # Get derivative forms without pronunciations
            query = session.query(DerivativeForm).filter(
                DerivativeForm.ipa_pronunciation.is_(None),
                DerivativeForm.phonetic_pronunciation.is_(None),
            )

            if only_english:
                query = query.filter(DerivativeForm.language_code == "en")

            if only_base_forms:
                query = query.filter(DerivativeForm.is_base_form == True)

            query = query.order_by(DerivativeForm.id)

            if limit:
                query = query.limit(limit)

            forms = query.all()
            logger.info(f"Found {len(forms)} forms to populate")

            populated_count = 0
            failed_count = 0

            if dry_run:
                # In dry run, just count what would be processed
                logger.info(
                    f"Would process {len(forms)} forms to generate pronunciations (dry run)"
                )
                # Show a few examples
                for idx, form in enumerate(forms[:5], 1):
                    lemma = session.query(Lemma).filter(Lemma.id == form.lemma_id).first()
                    logger.info(
                        f"  {idx}. '{form.derivative_form_text}' ({lemma.pos_type if lemma else 'unknown'})"
                    )
                if len(forms) > 5:
                    logger.info(f"  ... and {len(forms) - 5} more")
            else:
                for idx, form in enumerate(forms, 1):
                    logger.info(f"Processing {idx}/{len(forms)}: '{form.derivative_form_text}'...")

                    # Get lemma info for POS type and definition
                    lemma = session.query(Lemma).filter(Lemma.id == form.lemma_id).first()
                    if not lemma:
                        logger.warning(f"No lemma found for form {form.id}")
                        failed_count += 1
                        continue

                    # Get example sentence from the new sentences system if available
                    example_text = self._get_example_sentence(session, lemma)

                    try:
                        result = generate_pronunciation(
                            word=form.derivative_form_text,
                            pos_type=lemma.pos_type,
                            example_sentence=example_text,
                            definition=lemma.definition_text,
                            model=self.model,
                        )

                        if result["confidence"] >= 0.5:  # Minimum confidence threshold
                            form.ipa_pronunciation = result["ipa_pronunciation"]
                            form.phonetic_pronunciation = result["phonetic_pronunciation"]
                            session.commit()

                            logger.info(
                                f"  Generated: IPA={result['ipa_pronunciation']}, "
                                f"Phonetic={result['phonetic_pronunciation']} "
                                f"(confidence: {result['confidence']:.2f})"
                            )
                            populated_count += 1
                        else:
                            logger.warning(
                                f"  Low confidence ({result['confidence']:.2f}), skipping"
                            )
                            failed_count += 1

                    except Exception as e:
                        logger.error(f"  Failed to generate pronunciation: {e}")
                        failed_count += 1

            return {
                "total_processed": len(forms),
                "populated": populated_count,
                "failed": failed_count,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error populating pronunciations: {e}")
            if not dry_run:
                session.rollback()
            return {
                "error": str(e),
                "total_processed": 0,
                "populated": 0,
                "failed": 0,
                "dry_run": dry_run,
            }
        finally:
            session.close()

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
        only_english: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Run full pronunciation validation and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            limit: Maximum items to check
            sample_rate: Fraction to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues
            only_english: Only check English forms
            dry_run: If True, don't make LLM API calls, just count what would be checked

        Returns:
            Dictionary with all check results
        """
        logger.info(f"{'DRY RUN: ' if dry_run else ''}Starting pronunciation validation check...")
        start_time = datetime.now()

        results = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "model": self.model,
            "sample_rate": sample_rate,
            "confidence_threshold": confidence_threshold,
            "only_english": only_english,
            "dry_run": dry_run,
            "checks": {},
        }

        # Check existing pronunciations
        results["checks"]["pronunciation_validation"] = self.check_pronunciations(
            limit=limit,
            sample_rate=sample_rate,
            confidence_threshold=confidence_threshold,
            only_english=only_english,
            dry_run=dry_run,
        )

        # Check for missing pronunciations
        results["checks"]["missing_pronunciations"] = self.check_missing_pronunciations(
            limit=limit, only_english=only_english, only_base_forms=False
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        self._print_summary(results, start_time, duration)

        # Write to output file if requested
        if output_file:
            import json

            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_summary(self, results: Dict, start_time: datetime, duration: float):
        """Print a summary of the check results."""
        logger.info("=" * 80)
        logger.info("PAPUGA AGENT REPORT - Pronunciation Validation")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Model: {results['model']}")
        logger.info(f"Sample Rate: {results['sample_rate']*100:.0f}%")
        logger.info(f"Confidence Threshold: {results['confidence_threshold']}")
        logger.info(f"Only English: {results['only_english']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Pronunciation validation check
        if "pronunciation_validation" in results["checks"]:
            pron_check = results["checks"]["pronunciation_validation"]
            logger.info(f"PRONUNCIATION VALIDATION:")
            logger.info(f"  Total checked: {pron_check['total_checked']}")
            logger.info(f"  Issues found: {pron_check['issues_found']}")
            logger.info(f"  Issue rate: {pron_check['issue_rate']:.1f}%")
            logger.info("")

        # Missing pronunciations check
        if "missing_pronunciations" in results["checks"]:
            missing_check = results["checks"]["missing_pronunciations"]
            logger.info(f"MISSING PRONUNCIATIONS:")
            logger.info(f"  Total missing: {missing_check['total_missing']}")
            logger.info("")

        logger.info("=" * 80)


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Papuga - Pronunciation Validation and Generation Agent"
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Validate/generate pronunciation for the lemma with this GUID")
    add_backend_args(parser)

    # Papuga-specific arguments
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence to flag issues (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--all-languages", action="store_true", help="Check all languages (default: English only)"
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check", action="store_true", help="Check existing pronunciations only (default)"
    )
    mode_group.add_argument(
        "--populate", action="store_true", help="Generate missing pronunciations"
    )
    mode_group.add_argument(
        "--both", action="store_true", help="Check existing AND populate missing"
    )

    parser.add_argument(
        "--base-forms-only",
        action="store_true",
        help="Only process base forms (populate mode only)",
    )

    return parser


def main():
    """Main entry point for the papuga agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate cache arguments
    validate_cache_args(args)

    # Create data source configuration (includes backend, cache, and LLM model)
    config = get_data_source_config(args, default_model="gpt-5-mini")

    # Determine mode
    if args.populate:
        mode = "populate"
    elif args.both:
        mode = "both"
    else:
        mode = "check"  # default

    only_english = not args.all_languages

    # Handle --guid mode
    if args.guid:
        agent = PapugaAgent(config=config, debug=args.debug)
        session = agent.get_session()
        try:
            # Find the lemma by GUID
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
            if not lemma:
                print(f"\nError: No lemma found with GUID: {args.guid}")
                sys.exit(1)

            # Get the base form for this lemma
            form = (
                session.query(DerivativeForm)
                .filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.is_base_form == True,
                )
                .first()
            )

            if not form:
                print(f"\nError: No base form found for lemma: {lemma.lemma_text} ({args.guid})")
                sys.exit(1)

            print(f"\nProcessing pronunciation for: {form.derivative_form_text} (GUID: {args.guid})")

            # Check if pronunciation exists
            has_pronunciation = form.ipa_pronunciation or form.phonetic_pronunciation

            if mode == "check" or mode == "both":
                if has_pronunciation:
                    # Validate existing pronunciation
                    example_text = agent._get_example_sentence(session, lemma)
                    result = validate_pronunciation(
                        word=form.derivative_form_text,
                        ipa_pronunciation=form.ipa_pronunciation,
                        phonetic_pronunciation=form.phonetic_pronunciation,
                        pos_type=lemma.pos_type,
                        example_sentence=example_text,
                        definition=lemma.definition_text,
                        model=args.model,
                    )

                    print(f"\nValidation result:")
                    print(f"  Needs update: {result['needs_update']}")
                    print(f"  Confidence: {result['confidence']:.2f}")
                    if result['issues']:
                        print(f"  Issues: {', '.join(result['issues'])}")
                    if result['suggested_ipa']:
                        print(f"  Suggested IPA: {result['suggested_ipa']}")
                    if result['suggested_phonetic']:
                        print(f"  Suggested phonetic: {result['suggested_phonetic']}")
                else:
                    print(f"\nNo existing pronunciation to validate.")

            if mode == "populate" or mode == "both":
                if not has_pronunciation or mode == "both":
                    # Generate pronunciation
                    example_text = agent._get_example_sentence(session, lemma)
                    result = generate_pronunciation(
                        word=form.derivative_form_text,
                        pos_type=lemma.pos_type,
                        example_sentence=example_text,
                        definition=lemma.definition_text,
                        model=args.model,
                    )

                    print(f"\nGenerated pronunciation:")
                    print(f"  IPA: {result['ipa_pronunciation']}")
                    print(f"  Phonetic: {result['phonetic_pronunciation']}")
                    print(f"  Confidence: {result['confidence']:.2f}")

                    if not args.dry_run and result['confidence'] >= 0.5:
                        form.ipa_pronunciation = result['ipa_pronunciation']
                        form.phonetic_pronunciation = result['phonetic_pronunciation']
                        session.commit()
                        print(f"\n✓ Updated pronunciation in database")
                    elif args.dry_run:
                        print(f"\n[DRY RUN] Would update pronunciation")
        finally:
            session.close()
        return

    # Confirm before running LLM queries (unless --yes or --dry-run was provided)
    if not args.yes and not args.dry_run:
        agent_temp = PapugaAgent(config=config, debug=args.debug)
        session = agent_temp.get_session()
        try:
            if mode in ["check", "both"]:
                # Count forms with pronunciations
                query = session.query(DerivativeForm).filter(
                    (DerivativeForm.ipa_pronunciation.isnot(None))
                    | (DerivativeForm.phonetic_pronunciation.isnot(None))
                )
                if only_english:
                    query = query.filter(DerivativeForm.language_code == "en")
                if args.limit:
                    query = query.limit(args.limit)
                check_count = query.count()
                if args.sample_rate < 1.0:
                    check_count = int(check_count * args.sample_rate)
            else:
                check_count = 0

            if mode in ["populate", "both"]:
                # Count forms without pronunciations
                query = session.query(DerivativeForm).filter(
                    DerivativeForm.ipa_pronunciation.is_(None),
                    DerivativeForm.phonetic_pronunciation.is_(None),
                )
                if only_english:
                    query = query.filter(DerivativeForm.language_code == "en")
                if args.base_forms_only:
                    query = query.filter(DerivativeForm.is_base_form == True)
                if args.limit:
                    query = query.limit(args.limit)
                populate_count = query.count()
            else:
                populate_count = 0

            estimated_calls = check_count + populate_count
        finally:
            session.close()

        if not confirm_operation(
            message=f"Mode: {mode}\nModel: {args.model}\n\nThis may incur costs and take some time to complete.",
            estimated_calls=estimated_calls,
            skip_confirmation=args.yes,
            dry_run=args.dry_run,
        ):
            print("Aborted.")
            sys.exit(0)

    # Create agent with unified configuration
    agent = PapugaAgent(config=config, debug=args.debug)

    if mode == "check":
        agent.run_full_check(
            output_file=args.output,
            limit=args.limit,
            sample_rate=args.sample_rate,
            confidence_threshold=args.confidence_threshold,
            only_english=only_english,
            dry_run=args.dry_run,
        )
    elif mode == "populate":
        result = agent.populate_missing_pronunciations(
            limit=args.limit,
            only_english=only_english,
            only_base_forms=args.base_forms_only,
            dry_run=args.dry_run,
        )
        logger.info(
            f"\nPopulation complete: {result['populated']} populated, {result['failed']} failed"
        )
    elif mode == "both":
        # First check
        agent.run_full_check(
            output_file=args.output,
            limit=args.limit,
            sample_rate=args.sample_rate,
            confidence_threshold=args.confidence_threshold,
            only_english=only_english,
            dry_run=args.dry_run,
        )
        # Then populate
        result = agent.populate_missing_pronunciations(
            limit=args.limit,
            only_english=only_english,
            only_base_forms=args.base_forms_only,
            dry_run=args.dry_run,
        )
        logger.info(
            f"\nPopulation complete: {result['populated']} populated, {result['failed']} failed"
        )


if __name__ == "__main__":
    main()
