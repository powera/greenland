"""
CLI interface for the Lokys agent.
"""

import argparse
import logging
import sys

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_level_args,
    add_llm_args,
    add_output_args,
    add_pos_type_args,
    add_processing_args,
    confirm_operation,
    get_data_source_config,
)
from agents.common.lemma_selection import (
    LemmaQueryBuilder,
    count_for_confirmation,
    get_lemmas_for_agent,
)
from agents.lokys.agent import LokysAgent
from agents.lokys.display import (
    display_definition_validation_result,
    display_disambiguation_validation_result,
    display_fix_applied,
    display_lemma_validation_result,
    display_single_lemma_header,
)
from wordfreq.tools.llm_validators import validate_definition, validate_lemma_form

# Configure logging
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(description="Lokys - English Lemma Validation Agent")

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Validate only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
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
        choices=["lemma", "definitions", "disambiguation", "both"],
        default="both",
        help='Type of checks to run: "lemma" (lemma form validation), "definitions" (definition validation), "disambiguation" (polysemy/disambiguation checks), or "both" (default: all checks)',
    )

    return parser


def main() -> None:
    """Main entry point for the lokys agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Create agent with config
    agent = LokysAgent(config=config)

    # Get lemmas to process (either single lemma from --guid or batch)
    session = agent.get_session()
    try:
        lemmas = get_lemmas_for_agent(session, args)
    finally:
        session.close()

    # Show what we're processing
    if len(lemmas) == 1:
        lemma = lemmas[0]
        display_single_lemma_header(lemma, lemma.guid or "")

        # Validate lemma form
        if args.check_type in ["lemma", "both"]:
            result = validate_lemma_form(lemma.lemma_text, lemma.pos_type, args.model)
            display_lemma_validation_result(result, lemma.lemma_text)

        # Validate definition
        if args.check_type in ["definitions", "both"]:
            result = validate_definition(
                lemma.lemma_text, lemma.definition_text, lemma.pos_type, args.model
            )
            should_apply_fix, new_definition = display_definition_validation_result(
                result, lemma.lemma_text, lemma.definition_text, dry_run=args.dry_run
            )

            # Apply the fix if suggested
            if should_apply_fix and new_definition:
                session = agent.get_session()
                try:
                    old_definition = lemma.definition_text
                    lemma.definition_text = new_definition
                    session.commit()
                    display_fix_applied(old_definition, new_definition)
                finally:
                    session.close()

        if args.check_type in ["disambiguation", "both"]:
            session = agent.get_session()
            try:
                result = agent.check_single_disambiguation(lemma, session=session)
            finally:
                session.close()
            display_disambiguation_validation_result(result, lemma.lemma_text)

        return
    elif len(lemmas) == 0:
        logger.error("No lemmas found to process")
        sys.exit(1)

    # Batch mode - validate arguments
    if args.dry_run:
        parser.error(
            "--dry-run is not supported in batch mode. LOKYS always applies fixes in batch mode. Use --guid mode for testing individual lemmas."
        )

    # Confirm before running LLM queries (unless --yes was provided)
    if not args.yes and not args.dry_run:
        # Calculate estimated number of LLM calls
        session = agent.get_session()
        try:
            query = LemmaQueryBuilder(session).curated_only().build()
            lemma_count = count_for_confirmation(query, args.limit, args.sample_rate)
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
        lemmas=lemmas,
    )


if __name__ == "__main__":
    main()
