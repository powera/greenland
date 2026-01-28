#!/usr/bin/env python3
"""
Papuga Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import logging
import sys
from typing import Any, Dict, List

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
    validate_cache_args,
)
from agents.common.lemma_selection import get_lemmas_for_agent
from wordfreq.storage.models.schema import DerivativeForm

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
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
    add_level_args(parser)
    add_pos_type_args(parser)
    add_backend_args(parser)

    # Papuga-specific arguments
    parser.add_argument(
        "--all-languages", action="store_true", help="Process all languages (default: English only)"
    )

    # Mode selection - mutually exclusive flags
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--coverage",
        action="store_true",
        help="Report pronunciation coverage statistics (default mode)",
    )
    mode_group.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing pronunciations",
    )

    parser.add_argument(
        "--base-forms-only",
        action="store_true",
        help="Only process base forms (populate mode only)",
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker",
    )

    return parser


def enqueue_papuga_work(
    session: Any,
    lemmas: List[Any],
    only_english: bool = True,
    base_forms_only: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Enqueue pronunciation generation work items to the queue.

    Args:
        session: Database session
        lemmas: List of lemmas to process
        only_english: Only process English forms
        base_forms_only: Only process base forms
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    from workqueue.task_queue import enqueue_task

    enqueued_count = 0
    skipped_count = 0

    # Get derivative forms that need pronunciations
    lemma_ids = [l.id for l in lemmas]
    query = session.query(DerivativeForm).filter(
        DerivativeForm.lemma_id.in_(lemma_ids),
        DerivativeForm.ipa_pronunciation.is_(None),
        DerivativeForm.phonetic_pronunciation.is_(None),
    )
    if only_english:
        query = query.filter(DerivativeForm.language_code == "en")
    if base_forms_only:
        query = query.filter(DerivativeForm.is_base_form == True)

    forms = query.all()

    for form in forms:
        if not dry_run:
            dedup_key = f"papuga_{form.id}"
            result = enqueue_task(
                session,
                task_type="papuga_generate_pronunciation",
                target_type="derivative_form",
                target_id=form.id,
                payload={
                    "form_id": form.id,
                    "form_text": form.derivative_form_text,
                    "language_code": form.language_code,
                    "lemma_id": form.lemma_id,
                },
                dedup_key=dedup_key,
            )
            if result.created:
                enqueued_count += 1
            else:
                skipped_count += 1
        else:
            enqueued_count += 1

    if not dry_run:
        session.commit()

    return {
        "enqueued": enqueued_count,
        "skipped": skipped_count,
        "dry_run": dry_run,
    }


def main() -> None:
    """Main entry point for the papuga agent."""
    from agents.papuga.agent import PapugaAgent

    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate cache arguments
    validate_cache_args(args)

    # Create data source configuration (includes backend, cache, and LLM model)
    config = get_data_source_config(args, default_model="gpt-5-mini")

    # Determine mode from flags (default to coverage if none specified)
    if args.populate:
        mode = "populate"
    else:
        mode = "coverage"  # default

    only_english = not args.all_languages

    # Get lemmas to process (either single lemma from --guid or batch)
    agent_temp = PapugaAgent(config=config)
    session = agent_temp.get_session()
    try:
        lemmas = get_lemmas_for_agent(session, args)
    finally:
        session.close()

    # Extract lemma_id if processing a single lemma
    lemma_id = None
    if len(lemmas) == 1:
        lemma = lemmas[0]
        lemma_id = lemma.id
        logger.info(f"Processing lemma: {lemma.lemma_text} (GUID: {lemma.guid}, ID: {lemma_id})")
    elif len(lemmas) == 0:
        logger.error("No lemmas found to process")
        sys.exit(1)

    # WORKQUEUE MODE: Enqueue work items for barsukas worker
    if args.use_workqueue and mode == "populate":
        print("\n" + "=" * 80)
        print("PAPUGA AGENT - ENQUEUING WORK")
        print("=" * 80)

        session = PapugaAgent(config=config).get_session()
        try:
            results = enqueue_papuga_work(
                session=session,
                lemmas=lemmas,
                only_english=only_english,
                base_forms_only=args.base_forms_only,
                dry_run=args.dry_run,
            )

            print(f"\nEnqueued: {results['enqueued']}")
            print(f"Skipped: {results['skipped']}")
            if results["dry_run"]:
                print("\n⚠️  DRY RUN - No work items were actually enqueued")
            print("=" * 80)
        finally:
            session.close()

        return

    # Confirm before running LLM queries (unless --yes or --dry-run was provided)
    if not args.yes and not args.dry_run and mode == "populate":
        agent_temp = PapugaAgent(config=config)
        session = agent_temp.get_session()
        try:
            # Count forms without pronunciations
            query = session.query(DerivativeForm).filter(
                DerivativeForm.ipa_pronunciation.is_(None),
                DerivativeForm.phonetic_pronunciation.is_(None),
            )
            if lemma_id:
                query = query.filter(DerivativeForm.lemma_id == lemma_id)
            if only_english:
                query = query.filter(DerivativeForm.language_code == "en")
            if args.base_forms_only:
                query = query.filter(DerivativeForm.is_base_form == True)
            if args.limit:
                query = query.limit(args.limit)
            populate_count = query.count()

            estimated_calls = populate_count
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
    agent = PapugaAgent(config=config)

    # Work phase: execute the requested mode with all filters applied
    if mode == "coverage":
        # Coverage mode - report missing pronunciations (no LLM calls)
        result = agent.check_missing_pronunciations(
            limit=args.limit,
            only_english=only_english,
            only_base_forms=args.base_forms_only,
            lemma_id=lemma_id,
            lemmas=lemmas,
        )
        logger.info(
            f"\nCoverage check complete: {result['total_missing']} forms missing pronunciations"
        )
    elif mode == "populate":
        result = agent.populate_missing_pronunciations(
            limit=args.limit,
            only_english=only_english,
            only_base_forms=args.base_forms_only,
            dry_run=args.dry_run,
            lemma_id=lemma_id,
            lemmas=lemmas,
        )
        logger.info(
            f"\nPopulation complete: {result['populated']} populated, {result['failed']} failed "
            f"({result.get('lemma_lang_pairs', 0)} lemma/language pairs: "
            f"{result.get('batch_calls', 0)} batch, {result.get('single_calls', 0)} single)"
        )


if __name__ == "__main__":
    main()
