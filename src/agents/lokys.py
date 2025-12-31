#!/usr/bin/env python3
"""
Lokys - English Lemma Validation Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/check-definition/<lemma_id> endpoint
    - /agents/apply-definition/<lemma_id> endpoint
    - /agents/check-disambiguation/<lemma_id> endpoint
    - /agents/apply-disambiguation/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

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
from agents.common_args import (
    add_common_args,
    add_llm_args,
    add_output_args,
    add_processing_args,
    add_guid_arg,
    add_backend_args,
    get_data_source_config,
    confirm_operation,
)
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig, BackendType
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.tools.llm_validators import (
    validate_lemma_form,
    validate_definition,
    batch_validate_lemmas,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LokysAgent:
    """Agent for validating English lemma forms and properties."""

    def __init__(
        self,
        db_path: str = None,
        config: Optional[DataSourceConfig] = None,
        debug: bool = False,
        model: str = "gpt-5-mini",
    ):
        """
        Initialize the Lokys agent.

        Args:
            db_path: Database path (uses default if None) - for backward compatibility
            config: Backend configuration (if provided, overrides db_path)
            debug: Enable debug logging
            model: LLM model to use for validation
        """
        # Set up backend configuration
        if config is not None:
            self.config = config
        elif db_path is not None:
            # Backward compatibility: db_path implies SQLite backend
            self.config = DataSourceConfig(
                backend_type=BackendType.SQLITE, sqlite_path=db_path
            )
        else:
            # Use default SQLite path
            self.config = DataSourceConfig(
                backend_type=BackendType.SQLITE, sqlite_path=constants.WORDFREQ_DB_PATH
            )

        # Keep db_path for backward compatibility
        if self.config.backend_type == BackendType.SQLITE:
            self.db_path = self.config.sqlite_path
        else:
            self.db_path = None

        self.debug = debug
        self.model = model

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def check_lemma_forms(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
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
            query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

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

                result = validate_lemma_form(lemma.lemma_text, lemma.pos_type, self.model)

                if not result["is_lemma"] and result["confidence"] >= confidence_threshold:
                    issues_found.append(
                        {
                            "guid": lemma.guid,
                            "current_lemma": lemma.lemma_text,
                            "suggested_lemma": result["suggested_lemma"],
                            "pos_type": lemma.pos_type,
                            "reason": result["reason"],
                            "confidence": result["confidence"],
                        }
                    )
                    logger.warning(
                        f"Lemma issue: '{lemma.lemma_text}' → '{result['suggested_lemma']}' "
                        f"({lemma.guid}, confidence: {result['confidence']:.2f})"
                    )

            logger.info(f"Found {len(issues_found)} lemmas with potential issues")

            return {
                "total_checked": checked_count,
                "issues_found": len(issues_found),
                "issue_rate": (len(issues_found) / checked_count * 100) if checked_count else 0,
                "issues": issues_found,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            logger.error(f"Error checking lemma forms: {e}")
            return {
                "error": str(e),
                "total_checked": 0,
                "issues_found": 0,
                "issue_rate": 0,
                "issues": [],
            }
        finally:
            session.close()

    def check_definitions(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
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
            query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

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
                    self.model,
                    translation_language="Lithuanian",
                    translation_text=get_translation(session, lemma, "lt"),
                )

                if not result["is_valid"] and result["confidence"] >= confidence_threshold:
                    issues_found.append(
                        {
                            "guid": lemma.guid,
                            "lemma": lemma.lemma_text,
                            "current_definition": lemma.definition_text,
                            "suggested_definition": result["suggested_definition"],
                            "pos_type": lemma.pos_type,
                            "issues": result["issues"],
                            "confidence": result["confidence"],
                        }
                    )

                    # Update the database with the suggested definition
                    if result["suggested_definition"]:
                        old_definition = lemma.definition_text
                        lemma.definition_text = result["suggested_definition"]
                        session.commit()
                        logger.info(
                            f"Updated definition for '{lemma.lemma_text}' (GUID: {lemma.guid}): "
                            f"'{old_definition}' → '{result['suggested_definition']}'"
                        )
                    else:
                        logger.warning(
                            f"Definition issue: '{lemma.lemma_text}' (GUID: {lemma.guid}) - {', '.join(result['issues'])} "
                            f"(confidence: {result['confidence']:.2f}) - No suggested definition provided"
                        )

            logger.info(f"Found {len(issues_found)} definitions with potential issues")

            return {
                "total_checked": checked_count,
                "issues_found": len(issues_found),
                "issue_rate": (len(issues_found) / checked_count * 100) if checked_count else 0,
                "issues": issues_found,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            logger.error(f"Error checking definitions: {e}")
            return {
                "error": str(e),
                "total_checked": 0,
                "issues_found": 0,
                "issue_rate": 0,
                "issues": [],
            }
        finally:
            session.close()

    def check_disambiguation(self, limit: Optional[int] = None) -> Dict[str, any]:
        """
        Check for lemmas that need disambiguation (parentheticals).

        Detects when multiple lemmas share the same base English word but have
        different translations, indicating they need parenthetical disambiguation
        like "mouse (animal)" vs "mouse (computer)".

        Args:
            limit: Maximum number of lemma groups to check

        Returns:
            Dictionary with check results including lemmas needing disambiguation
        """
        logger.info("Checking for lemmas needing disambiguation...")

        session = self.get_session()
        try:
            from sqlalchemy import func
            from wordfreq.storage.translation_helpers import (
                get_supported_languages,
                get_translation,
            )

            # Find lemma_text values that appear multiple times
            duplicates_query = (
                session.query(Lemma.lemma_text, func.count(Lemma.id).label("count"))
                .filter(Lemma.guid.isnot(None))  # Only curated lemmas
                .group_by(Lemma.lemma_text)
                .having(func.count(Lemma.id) > 1)
                .order_by(func.count(Lemma.id).desc())
            )

            if limit:
                duplicates_query = duplicates_query.limit(limit)

            duplicate_groups = duplicates_query.all()
            logger.info(f"Found {len(duplicate_groups)} lemma_text values with duplicates")

            # Get all supported languages
            supported_languages = get_supported_languages()

            issues = []
            total_checked = 0
            needs_disambiguation = 0

            for lemma_text, count in duplicate_groups:
                # Get all lemmas with this lemma_text
                lemmas = (
                    session.query(Lemma)
                    .filter(Lemma.lemma_text == lemma_text, Lemma.guid.isnot(None))
                    .all()
                )

                total_checked += len(lemmas)

                # Check if translations differ (indicating different meanings)
                translations_differ = False
                translation_map = {}

                for lemma in lemmas:
                    # Collect non-null translations for each lemma using the helper
                    lemma_translations = []
                    for lang_code in supported_languages.keys():
                        try:
                            translation = get_translation(session, lemma, lang_code)
                            if translation:
                                lemma_translations.append((lang_code, translation))
                        except ValueError:
                            # Language not supported, skip
                            continue

                    translation_map[lemma.guid] = lemma_translations

                # Compare translations across lemmas
                if len(translation_map) > 1:
                    guids = list(translation_map.keys())
                    for i in range(len(guids)):
                        for j in range(i + 1, len(guids)):
                            trans_i = dict(translation_map[guids[i]])
                            trans_j = dict(translation_map[guids[j]])

                            # Check if any shared language has different translations
                            for lang in set(trans_i.keys()) & set(trans_j.keys()):
                                if trans_i[lang] != trans_j[lang]:
                                    translations_differ = True
                                    break
                            if translations_differ:
                                break

                # If translations differ, check if lemmas have parentheticals
                if translations_differ:
                    missing_parentheticals = []
                    for lemma in lemmas:
                        has_parenthetical = "(" in lemma.lemma_text and ")" in lemma.lemma_text
                        if not has_parenthetical:
                            missing_parentheticals.append(
                                {
                                    "guid": lemma.guid,
                                    "lemma_text": lemma.lemma_text,
                                    "definition": (
                                        lemma.definition_text[:100]
                                        if lemma.definition_text
                                        else None
                                    ),
                                    "pos_type": lemma.pos_type,
                                    "disambiguation": lemma.disambiguation,
                                }
                            )

                    if missing_parentheticals:
                        needs_disambiguation += len(missing_parentheticals)
                        issues.append(
                            {
                                "lemma_text": lemma_text,
                                "total_count": count,
                                "missing_disambiguation": missing_parentheticals,
                                "all_guids": [l.guid for l in lemmas],
                            }
                        )

            logger.info(f"Checked {total_checked} lemmas in {len(duplicate_groups)} groups")
            logger.info(f"Found {needs_disambiguation} lemmas needing disambiguation")

            return {
                "total_checked": total_checked,
                "duplicate_groups": len(duplicate_groups),
                "needs_disambiguation": needs_disambiguation,
                "issues": issues,
            }

        except Exception as e:
            logger.error(f"Error checking disambiguation: {e}", exc_info=True)
            return {"error": str(e), "total_checked": 0, "needs_disambiguation": 0, "issues": []}
        finally:
            session.close()

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
        check_type: str = "both",
    ) -> Dict[str, any]:
        """
        Run English lemma validation and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            limit: Maximum items to check
            sample_rate: Fraction to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues
            check_type: Type of check to run ("lemma", "definitions", or "both")

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting English lemma validation check...")
        start_time = datetime.now()

        results = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "model": self.model,
            "sample_rate": sample_rate,
            "confidence_threshold": confidence_threshold,
            "check_type": check_type,
            "checks": {},
        }

        # Check English lemma forms
        if check_type in ["lemma", "both"]:
            results["checks"]["lemma_forms"] = self.check_lemma_forms(
                limit=limit, sample_rate=sample_rate, confidence_threshold=confidence_threshold
            )

        # Check English definitions
        if check_type in ["definitions", "both"]:
            results["checks"]["definitions"] = self.check_definitions(
                limit=limit, sample_rate=sample_rate, confidence_threshold=confidence_threshold
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

    # === Barsukas Web Interface Helper Methods ===
    # These methods provide a simplified, single-lemma interface for the web UI

    def check_single_definition(self, lemma, session=None) -> Dict[str, any]:
        """
        Check the definition of a single lemma using LLM validation.

        This is a convenience method for the Barsukas web interface.
        See src/barsukas/routes/agents.py for usage.

        Args:
            lemma: Lemma object to check
            session: Optional database session (if None, uses internal session)

        Returns:
            Dictionary with validation result from validate_definition()
        """
        result = validate_definition(
            word=lemma.lemma_text,
            definition=lemma.definition_text or "",
            pos_type=lemma.pos_type,
            model=self.model,
        )
        return result

    def check_single_disambiguation(self, lemma, session) -> Dict[str, any]:
        """
        Check if a lemma needs disambiguation (parentheticals in lemma_text).

        This method finds other lemmas with the same lemma_text and checks if they
        have different translations, indicating different meanings that need disambiguation.

        This is a convenience method for the Barsukas web interface.
        See src/barsukas/routes/agents.py for usage.

        Args:
            lemma: Lemma object to check
            session: Database session

        Returns:
            Dictionary with:
            - needs_disambiguation: bool
            - duplicate_count: int
            - has_parenthetical: bool
            - duplicates: list of Lemma objects
            - translations_by_guid: dict mapping GUID to translations
            - llm_suggestions: dict from suggest_disambiguation (if applicable)
        """
        from wordfreq.storage.translation_helpers import get_supported_languages, get_translation
        from wordfreq.tools.llm_validators import suggest_disambiguation

        # Find duplicates
        duplicates = (
            session.query(Lemma)
            .filter(Lemma.lemma_text == lemma.lemma_text, Lemma.guid.isnot(None))
            .all()
        )

        if len(duplicates) <= 1:
            return {
                "needs_disambiguation": False,
                "duplicate_count": len(duplicates),
                "reason": "no_duplicates",
            }

        # Get translations for all duplicates
        supported_languages = get_supported_languages()
        translations_by_guid = {}

        for dup in duplicates:
            translations = {}
            for lang_code in supported_languages.keys():
                try:
                    translation = get_translation(session, dup, lang_code)
                    if translation:
                        translations[lang_code] = translation
                except ValueError:
                    continue
            translations_by_guid[dup.guid] = translations

        # Check if translations differ
        translations_differ = False
        if len(translations_by_guid) > 1:
            guids = list(translations_by_guid.keys())
            for i in range(len(guids)):
                for j in range(i + 1, len(guids)):
                    trans_i = translations_by_guid[guids[i]]
                    trans_j = translations_by_guid[guids[j]]
                    for lang in set(trans_i.keys()) & set(trans_j.keys()):
                        if trans_i[lang] != trans_j[lang]:
                            translations_differ = True
                            break
                    if translations_differ:
                        break

        if not translations_differ:
            return {
                "needs_disambiguation": False,
                "duplicate_count": len(duplicates),
                "reason": "translations_identical",
                "duplicates": duplicates,
                "translations_by_guid": translations_by_guid,
            }

        # Check if already has parentheticals
        has_parenthetical = "(" in lemma.lemma_text and ")" in lemma.lemma_text

        # Get LLM suggestions
        definitions_data = []
        for dup in duplicates:
            item = {
                "guid": dup.guid,
                "definition": dup.definition_text or "No definition",
                "translations": {},
            }
            for lang_code in supported_languages.keys():
                try:
                    trans = get_translation(session, dup, lang_code)
                    if trans:
                        item["translations"][lang_code] = trans
                except ValueError:
                    continue
            definitions_data.append(item)

        llm_result = suggest_disambiguation(
            word=lemma.lemma_text, definitions=definitions_data, model=self.model
        )

        return {
            "needs_disambiguation": True,
            "duplicate_count": len(duplicates),
            "has_parenthetical": has_parenthetical,
            "duplicates": duplicates,
            "translations_by_guid": translations_by_guid,
            "llm_suggestions": llm_result,
        }

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
        if "lemma_forms" in results["checks"]:
            lemma_check = results["checks"]["lemma_forms"]
            logger.info(f"ENGLISH LEMMA FORMS:")
            logger.info(f"  Total checked: {lemma_check['total_checked']}")
            logger.info(f"  Issues found: {lemma_check['issues_found']}")
            logger.info(f"  Issue rate: {lemma_check['issue_rate']:.1f}%")
            logger.info("")

        # Definitions check
        if "definitions" in results["checks"]:
            def_check = results["checks"]["definitions"]
            logger.info(f"ENGLISH DEFINITIONS:")
            logger.info(f"  Total checked: {def_check['total_checked']}")
            logger.info(f"  Issues found: {def_check['issues_found']}")
            logger.info(f"  Issue rate: {def_check['issue_rate']:.1f}%")
            logger.info("")

        logger.info("=" * 80)


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(description="Lokys - English Lemma Validation Agent")

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Validate only the lemma with this GUID")
    add_backend_args(parser)

    # Lokys-specific arguments
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence to flag issues (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--check-type",
        choices=["lemma", "definitions", "both"],
        default="both",
        help='Type of checks to run: "lemma" (lemma form validation), "definitions" (definition validation), or "both" (default: both)',
    )

    return parser


def main():
    """Main entry point for the lokys agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate arguments: --dry-run is not allowed in batch mode (only in --guid mode)
    if args.dry_run and not args.guid:
        parser.error("--dry-run is not supported in batch mode. LOKYS always applies fixes in batch mode. Use --guid mode for testing individual lemmas.")

    # Create backend configuration using common helper
    backend_config = get_data_source_config(args)

    # Create agent with backend config
    if backend_config:
        agent = LokysAgent(config=backend_config, debug=args.debug, model=args.model)
    else:
        # Backward compatibility: use db_path
        agent = LokysAgent(db_path=args.db_path, debug=args.debug, model=args.model)

    # Handle --guid mode
    if args.guid:
        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
            if not lemma:
                print(f"\nError: No lemma found with GUID: {args.guid}")
                sys.exit(1)

            print(f"\nValidating lemma: {lemma.lemma_text} (GUID: {args.guid})")

            # Validate lemma form
            if args.check_type in ["lemma", "both"]:
                result = validate_lemma_form(lemma.lemma_text, lemma.pos_type, args.model)
                print(f"\nLemma form validation:")
                print(f"  Is lemma: {result['is_lemma']}")
                print(f"  Confidence: {result['confidence']:.2f}")
                if not result['is_lemma']:
                    print(f"  Suggested: {result['suggested_lemma']}")
                    print(f"  Reason: {result['reason']}")

            # Validate definition
            if args.check_type in ["definitions", "both"]:
                result = validate_definition(
                    lemma.lemma_text,
                    lemma.definition_text,
                    lemma.pos_type,
                    args.model
                )
                print(f"\nDefinition validation:")
                print(f"  Is valid: {result['is_valid']}")
                print(f"  Confidence: {result['confidence']:.2f}")
                if not result['is_valid']:
                    print(f"  Issues: {', '.join(result['issues'])}")
                    if result['suggested_definition']:
                        print(f"  Suggested: {result['suggested_definition']}")
                        # Apply the fix automatically (unless --dry-run)
                        if not args.dry_run:
                            old_definition = lemma.definition_text
                            lemma.definition_text = result['suggested_definition']
                            session.commit()
                            print(f"  ✓ Updated definition: '{old_definition}' → '{result['suggested_definition']}'")
                        else:
                            print(f"  [DRY RUN] Would update: '{lemma.definition_text}' → '{result['suggested_definition']}'")
                    else:
                        print(f"  ⚠ No suggested definition provided by LLM")

        finally:
            session.close()
        return

    # Confirm before running LLM queries (unless --yes or --dry-run was provided)
    if not args.yes and not args.dry_run:
        # Calculate estimated number of LLM calls
        session = agent.get_session()
        try:
            query = session.query(Lemma).filter(Lemma.guid.isnot(None))
            if args.limit:
                query = query.limit(args.limit)
            lemma_count = query.count()
            if args.sample_rate < 1.0:
                lemma_count = int(lemma_count * args.sample_rate)
            # Calculate based on check_type
            if args.check_type == "both":
                estimated_calls = lemma_count * 2
            else:
                estimated_calls = lemma_count
        finally:
            session.close()

        if not confirm_operation(
            message=f"Check type: {args.check_type}\nModel: {args.model}\n\nThis may incur costs and take some time to complete.",
            estimated_calls=estimated_calls,
            skip_confirmation=args.yes,
            dry_run=args.dry_run,
        ):
            print("Aborted.")
            sys.exit(0)

    agent.run_full_check(
        output_file=args.output,
        limit=args.limit,
        sample_rate=args.sample_rate,
        confidence_threshold=args.confidence_threshold,
        check_type=args.check_type,
    )


if __name__ == "__main__":
    main()
